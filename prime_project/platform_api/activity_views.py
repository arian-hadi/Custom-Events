"""Member-owned event applications and earlier edit records in the V2 account."""
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from edithub.models import EditSubmission
from edithub.league.integration import fetch_verified_video, ProviderSetupRequired
from edithub.league.providers import ProviderError
from events.forms import EventApplicationForm
from events.models import EventApplication, EventFieldResponse
from .views import application_data, endpoint, paginate, payload


@endpoint(("GET", "POST"), authenticated=True)
def event_application(request, application_id):
    with transaction.atomic():
        query = EventApplication.objects.select_related("event").prefetch_related("event__custom_fields", "field_responses__field")
        if request.method == "POST":
            query = query.select_for_update(of=("self",))
        application = get_object_or_404(query, pk=application_id, applicant=request.user)
        if request.method == "POST":
            if application.status != "pending" or not application.event.is_active or timezone.now() > application.event.deadline:
                return JsonResponse({"error": "This application is no longer open for changes."}, status=409)
            data = payload(request)
            cover = data.get("cover_letter", "")
            if not isinstance(cover, str) or len(cover) > 10000:
                return JsonResponse({"error": "Additional message must be text, up to 10,000 characters."}, status=400)
            form = EventApplicationForm(data, event=application.event)
            if not form.is_valid():
                return JsonResponse({"error": "Please check the application fields.", "errors": form.errors.get_json_data()}, status=400)
            for field in application.event.custom_fields.all():
                # A field can change type in admin; clear obsolete typed values.
                values = {"value_text": None, "value_number": None, "value_date": None, "value_boolean": False}
                values[f"value_{field.field_type}"] = form.cleaned_data[f"field_{field.pk}"]
                response = EventFieldResponse.objects.filter(application=application, field=field).first()
                if response:
                    for name, value in values.items():
                        setattr(response, name, value)
                    response.save(update_fields=list(values))
                else:
                    EventFieldResponse.objects.create(application=application, field=field, **values)
            application.cover_letter = cover
            application.save(update_fields=["cover_letter", "updated_date"])
            application._prefetched_objects_cache = {}
        return JsonResponse({"application": application_data(application)})


def edit_deadline(edit):
    start = edit.scheduled_week
    if start is None:
        submitted = edit.submitted_date.astimezone(dt_timezone.utc).date()
        start = submitted - timedelta(days=submitted.weekday()) + timedelta(days=7)
    return datetime.combine(start, time.min, tzinfo=dt_timezone.utc)


def edit_open(edit):
    return edit.status in {"pending", "verified"} and timezone.now() < edit_deadline(edit)


def earlier_edit_data(edit):
    return {"id": edit.pk, "title": edit.title, "description": edit.description,
        "video_url": edit.video_url, "platform": edit.channel_type, "status": edit.status,
        "submitted_at": edit.submitted_date, "deadline": edit_deadline(edit),
        "upvotes": edit.upvote_count, "can_edit": edit_open(edit),
        "can_confirm": edit_open(edit) and edit.status == "pending",
        "url": f"/account/edits/{edit.pk}"}


@endpoint(authenticated=True)
def earlier_edits(request):
    query = EditSubmission.objects.filter(user=request.user).order_by("-submitted_date", "-pk")
    return JsonResponse(paginate(request, query, earlier_edit_data))


@endpoint(("GET", "POST"), authenticated=True)
def earlier_edit(request, edit_id):
    with transaction.atomic():
        query = EditSubmission.objects.select_related("approved_application")
        if request.method == "POST":
            query = query.select_for_update(of=("self",))
        edit = get_object_or_404(query, pk=edit_id, user=request.user)
        if request.method == "POST":
            if request.user.role != "user" or not edit_open(edit):
                return JsonResponse({"error": "The submission is locked. Its entry deadline has passed or it is no longer editable."}, status=409)
            data = payload(request)
            operation = data.get("operation", "save")
            if operation == "withdraw":
                try:
                    edit.delete()
                except ProtectedError:
                    return JsonResponse({"error": "This submission has protected records. Please contact support."}, status=409)
                return JsonResponse({"withdrawn": True})
            application = edit.approved_application
            if not application or application.user_id != request.user.pk or application.status != "accepted" or not application.channel_verified or application.removal_requested:
                return JsonResponse({"error": "An approved, verified channel is required to update this submission."}, status=409)
            if operation == "confirm":
                if data.get("owns_edit") is not True:
                    return JsonResponse({"error": "Confirm that this is your edit before submitting it."}, status=400)
                if edit.status == "pending":
                    edit.status, edit.verified_date = "verified", timezone.now()
                    edit.save(update_fields=["status", "verified_date", "updated_date"])
            elif operation == "save":
                fields = {"title": 200, "description": 10000, "video_url": 500}
                for name, limit in fields.items():
                    value = data.get(name, getattr(edit, name))
                    if not isinstance(value, str) or len(value) > limit:
                        return JsonResponse({"error": f"Invalid {name.replace('_', ' ')}."}, status=400)
                    data[name] = value.strip()
                if data["video_url"] != edit.video_url:
                    try:
                        verified = fetch_verified_video(application, data["video_url"])
                    except (ValueError, ProviderError, ProviderSetupRequired):
                        return JsonResponse({"error": "The replacement video could not be verified against your approved channel."}, status=400)
                    data["video_url"] = verified["canonical_url"]
                for name in fields:
                    setattr(edit, name, data[name])
                edit.save(update_fields=[*fields, "updated_date"])
            else:
                return JsonResponse({"error": "Unknown submission action."}, status=400)
        return JsonResponse({"edit": earlier_edit_data(edit)})
