"""Member profile controls, using existing accounts, channels and title grants."""
import logging
import time
import warnings
from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from django.contrib.auth import get_user_model, logout
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import JsonResponse

from accounts.api_views import limited
from edithub.models import EditorApplication, EditorTitle
from edithub.utils import is_title_unlocked_for_user
from .views import endpoint, image_url, payload
from .member_titles import selected_editor_title

logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
RECENT_AUTH_SECONDS = 600


def approved_channels(user):
    return EditorApplication.objects.filter(user=user, status="accepted", channel_verified=True,
        removal_requested=False).select_related("selected_title").order_by("channel_type", "-applied_date", "-pk")


def profile_data(user):
    applications = list(approved_channels(user))
    by_platform = {}
    for application in applications:
        by_platform.setdefault(application.channel_type, application)
    titles = [title for title in EditorTitle.objects.filter(is_active=True).exclude(category="comment")
              if is_title_unlocked_for_user(user, title)] if applications else []
    primary = by_platform.get(user.profile_channel_source) or next(iter(by_platform.values()), None)
    selected = selected_editor_title(user, primary)
    return {
        "member": {"display_name": user.get_display_name(), "username": user.username,
                   "profile_picture": user.get_display_picture(),
                   "editor_title": selected.name if selected else ("Editor" if applications else "Community member"),
                   "editor_title_rarity": selected.rarity if selected else None,
                   "verified_editor": bool(applications), "verified_platforms": list(by_platform)},
        "profile": {"mode": user.profile_display_mode, "approved_channel_source": user.profile_channel_source or "",
                    "selected_title_id": selected.pk if selected else None, "uploaded_picture": image_url(user.profile_picture)},
        "channels": [{"platform": platform, "name": app.channel_name, "thumbnail": app.channel_thumbnail}
                     for platform, app in by_platform.items()],
        "titles": [{"id": title.pk, "name": title.name, "rarity": title.get_rarity_display(),
                    "description": title.description} for title in titles],
        "max_image_mb": MAX_IMAGE_BYTES // (1024 * 1024),
        "deletion": {"password_required": user.has_usable_password(), "recent_login_required": not user.has_usable_password(),
                     "reauth_url": "/login?next=%2Faccount%2Fprofile"},
    }


def validated_picture(upload):
    """Decode, bound and re-encode image pixels; never store arbitrary upload bytes."""
    if not upload.size or upload.size > MAX_IMAGE_BYTES:
        raise ValueError("Choose a profile image smaller than 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Use a JPEG, PNG or WebP image.")
                if max(source.size) > MAX_IMAGE_DIMENSION:
                    raise ValueError("Profile images must be at most 4096 pixels wide and high.")
                source.verify()
            upload.seek(0)
            with Image.open(upload) as source:
                source.load()
                picture = ImageOps.exif_transpose(source).convert("RGBA")
                picture.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                # Copy pixels to strip source metadata, profiles and appended payloads.
                clean = Image.new("RGBA", picture.size)
                clean.paste(picture)
                output = BytesIO()
                clean.save(output, format="PNG")
        return ContentFile(output.getvalue(), name=f"{uuid4().hex}.png")
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("This file is not a valid JPEG, PNG or WebP image.") from exc


def clean_replaced_picture(name, storage):
    """Remove an old account upload only after commit and if it is not shared."""
    if not name or not name.startswith("profile_pictures/"):
        return
    if get_user_model().objects.filter(profile_picture=name).exists():
        return
    try:
        storage.delete(name)
    except OSError:
        logger.warning("A replaced account profile image could not be removed from storage.")


def field_error(field, message, status=400):
    return JsonResponse({"error": "Please check your profile settings.", "errors": {field: [message]}}, status=status)


@endpoint(("GET", "POST"), authenticated=True)
def profile(request):
    if request.method == "GET":
        return JsonResponse(profile_data(request.user))
    if limited(request, "member-profile", limit=30, period=600, identity=str(request.user.pk)):
        return JsonResponse({"error": "Too many updates. Please try again later."}, status=429)
    if request.content_type == "application/json":
        data = payload(request)
    elif request.content_type in {"multipart/form-data", "application/x-www-form-urlencoded"}:
        data = request.POST
    else:
        return JsonResponse({"error": "Use a profile form or JSON request."}, status=415)
    allowed = {"profile_display_mode", "approved_channel_source", "selected_title_id", "remove_picture"}
    if set(data) - allowed or set(request.FILES) - {"profile_picture"}:
        return JsonResponse({"error": "These fields cannot be changed from profile settings."}, status=400)
    if any(not isinstance(value, (str, bool, int, type(None))) for value in data.values()):
        return JsonResponse({"error": "Invalid profile settings."}, status=400)
    remove = data.get("remove_picture", False)
    if remove not in (True, False, "true", "false", "", "on"):
        return field_error("remove_picture", "Choose whether to remove your uploaded picture.")
    remove = remove in (True, "true", "on")
    upload = request.FILES.get("profile_picture")
    if remove and upload:
        return field_error("profile_picture", "Choose either a new image or removal of your current image.")
    picture = None
    if upload:
        try:
            picture = validated_picture(upload)
        except ValueError as exc:
            return field_error("profile_picture", str(exc))
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        mode = data.get("profile_display_mode", user.profile_display_mode)
        source = data.get("approved_channel_source", user.profile_channel_source or "")
        if mode not in {"account", "channel"}:
            return field_error("profile_display_mode", "Choose your account or an approved channel.")
        if source not in {"", "youtube", "tiktok"}:
            return field_error("approved_channel_source", "Choose one of your approved channels.")
        channels = approved_channels(user)
        if source and not channels.filter(channel_type=source).exists():
            if mode == "account" and "approved_channel_source" not in data:
                source = ""
            else:
                return field_error("approved_channel_source", "This channel is not an approved, verified channel on your account.")
        if mode == "channel" and not source:
            return field_error("approved_channel_source", "Select which approved channel to display.")
        title = user.selected_title
        if "selected_title_id" in data:
            title_id = data.get("selected_title_id")
            if title_id in (None, ""):
                title = None
            elif isinstance(title_id, bool) or not str(title_id).isascii() or not str(title_id).isdigit() or len(str(title_id)) > 18:
                return field_error("selected_title_id", "Select one of your available editor titles.")
            else:
                title = EditorTitle.objects.filter(pk=int(title_id), is_active=True).exclude(category="comment").first()
                if not channels.exists() or not title or not is_title_unlocked_for_user(user, title):
                    return field_error("selected_title_id", "This editor title is not available for your account.", 403)
        previous_name = user.profile_picture.name if user.profile_picture else None
        storage = user.profile_picture.storage
        user.profile_display_mode, user.profile_channel_source = mode, source or None
        user.selected_title = title
        fields = ["profile_display_mode", "profile_channel_source", "selected_title"]
        if picture is not None or remove:
            user.profile_picture = picture if picture is not None else None
            fields.append("profile_picture")
        user.save(update_fields=fields)
        if "selected_title_id" in data:
            # Keep old approved records consistent without calling ranking/title-award saves.
            EditorApplication.objects.filter(user=user, status="accepted").update(selected_title=title)
        if previous_name and (picture is not None or remove):
            transaction.on_commit(lambda: clean_replaced_picture(previous_name, storage))
    return JsonResponse(profile_data(user))


@endpoint(("POST",), authenticated=True)
def delete_profile(request):
    if limited(request, "member-delete", limit=5, period=600, identity=str(request.user.pk)):
        return JsonResponse({"error": "Too many attempts. Please try again later."}, status=429)
    data = payload(request)
    if set(data) - {"confirmation", "password"} or data.get("confirmation") != "DELETE":
        return field_error("confirmation", "Type DELETE to confirm permanent account deletion.")
    user = request.user
    if user.has_usable_password():
        password = data.get("password")
        if not isinstance(password, str) or not user.check_password(password):
            return field_error("password", "Enter your current password to delete your account.", 403)
    else:
        authenticated_at = request.session.get("v2_authenticated_at")
        if type(authenticated_at) not in (int, float) or not 0 <= time.time() - authenticated_at <= RECENT_AUTH_SECONDS:
            return JsonResponse({"error": "Sign in again with Google, then return here to confirm deletion.",
                                 "code": "recent_login_required"}, status=403)
    previous_name = user.profile_picture.name if user.profile_picture else None
    storage = user.profile_picture.storage
    try:
        with transaction.atomic():
            # Financial and frozen community history remain protected by their existing relations.
            get_user_model().objects.select_for_update().get(pk=user.pk).delete()
            if previous_name:
                transaction.on_commit(lambda: clean_replaced_picture(previous_name, storage))
    except (ProtectedError, RestrictedError):
        return JsonResponse({"error": "Your account has order or community records that need review before deletion. Your account is still active. Contact support to request removal.",
                             "code": "protected_records", "support_url": "/contact"}, status=409)
    logout(request)
    return JsonResponse({"detail": "Your account has been deleted."})
