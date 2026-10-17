"""Session-authenticated website API; domain records remain in their existing apps."""
import json
import logging
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.core.mail import BadHeaderError, EmailMessage
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Case, CharField, Count, DecimalField, ExpressionWrapper, F, Q, Value, When
from django.db.models.functions import Upper
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.csrf import csrf_failure as django_csrf_failure
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from accounts.utils import verify_recaptcha
from announcements.models import Announcement
from contact.forms import ContactForm
from events.forms import EventApplicationForm
from events.models import Event, EventApplication, EventFieldResponse
from notifications.models import Notification, NotificationPreference
from shop.models import Product, SiteLogo, FeaturedShopRequest
from shop.amazon import catalog_queryset, product_overlay
from shop.payments import THREE_DECIMAL, ZERO_DECIMAL, checkout_product_data

from .models import BlogPost, SiteSettings
from .sanitization import safe_html

logger = logging.getLogger(__name__)


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/v2/"):
        return JsonResponse({"error": "Security token expired or missing. Refresh and try again."}, status=403)
    return django_csrf_failure(request, reason=reason)


def endpoint(methods=("GET",), *, authenticated=False):
    """Keep JSON errors, CSRF enforcement, and private response caching consistent."""
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                response = JsonResponse({"error": "Method not allowed."}, status=405)
                response["Allow"] = ", ".join(methods)
                return response
            if authenticated and not active_member(request):
                return JsonResponse({"error": "Please sign in to continue."}, status=401)
            try:
                return view(request, *args, **kwargs)
            except Http404:
                return JsonResponse({"error": "Not found."}, status=404)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError) as exc:
                # Invalid JSON and expected shape errors never produce HTML error pages.
                logger.debug("Invalid V2 request: %s", exc)
                return JsonResponse({"error": "Invalid request data."}, status=400)
        return never_cache(csrf_protect(wrapped))
    return decorate


def active_member(request):
    # The legacy EmailBackend restores inactive users, unlike ModelBackend.
    # V2 must enforce its account rules regardless of which login created the session.
    return request.user.is_authenticated and request.user.is_active and request.user.is_verified


def payload(request):
    if request.content_type != "application/json":
        raise ValueError("Expected application/json")
    data = json.loads(request.body or b"{}")
    if not isinstance(data, dict):
        raise ValueError("Expected an object")
    return data


def image_url(field):
    return field.url if field else None


def paginate(request, queryset, serialize):
    paginator = Paginator(queryset, 24)
    page = paginator.get_page(request.GET.get("page"))
    return {"results": [serialize(item) for item in page], "count": paginator.count, "page": page.number, "pages": paginator.num_pages}


@endpoint()
def site(request):
    config = SiteSettings.objects.first() or SiteSettings()
    logo = SiteLogo.objects.filter(is_active=True).first()
    values = {name: getattr(config, name) for name in (
        "name", "accent_color", "secondary_accent_color", "hero_title", "hero_subtitle", "hero_button_text", "hero_button_url", "footer_text", "buy_me_a_coffee_url", "navigation", "social_links", "home_sections",
    )}
    values.update(hero_image=image_url(config.hero_image), logo=image_url(logo.image) if logo else None, favicon=image_url(logo.favicon) if logo else None)
    return JsonResponse({"site": values})


@endpoint()
def featured_shop_requests(request):
    results = []
    for item in FeaturedShopRequest.objects.filter(is_active=True):
        values = {name: getattr(item, name) for name in (
            'id', 'title', 'description', 'details', 'icon', 'badge', 'price_label',
            'turnaround', 'button_label', 'placeholder_label', 'is_placeholder',
        )}
        values.update(image=image_url(item.image), purchase_url='' if item.is_placeholder else item.purchase_url)
        results.append(values)
    return JsonResponse({'results': results})


def product_data(product, favorites):
    values = {
        "id": product.pk, "name": product.name, "description": safe_html(product.description),
        "category": product.category, "category_label": product.get_category_display(),
        "thumbnail": image_url(product.thumbnail), "main_image": image_url(product.main_image),
        "images": [field.url for field in (product.main_image, product.image_2, product.image_3, product.image_4) if field],
        "video_url": product.video_url, "original_price": str(product.original_price),
        "current_price": str(product.get_current_price()), "discount_percentage": str(product.get_discount_percentage()),
        "is_free": product.is_free(), "free_deadline": product.free_deadline if product.free_deadline_active else None,
        "redirect_url": product.redirect_url, "ecommerce_platform": product.ecommerce_platform,
        "is_favorite": product.pk in favorites,
    }
    amazon_values = product_overlay(product)
    if amazon_values:
        values.update(amazon_values)
    values['checkout'] = checkout_product_data(product)
    if values['checkout']['configured']:
        values.update(is_free=False, discount_percentage='0', free_deadline=None)
    return values


def favorite_ids(request):
    return set(request.user.favorite_products.values_list("pk", flat=True)) if active_member(request) else set()


def browsing_prices(queryset, now):
    """Database equivalents of the public serializers, never stale provider prices."""
    amount_field = DecimalField(max_digits=20, decimal_places=3)
    free = Q(category='transformers_2_0', free_deadline_active=True, free_deadline__gte=now, amazon_source__isnull=True)
    checkout = Q(payment_config__enabled=True, is_active=True, category='transformers_2_0', ecommerce_platform='none', amazon_source__isnull=True) & ~free
    fresh_offer = Q(amazon_source__content_expires_at__gt=now, amazon_source__offer_expires_at__gt=now, amazon_source__price__isnull=False)
    discounted = Q(discount_active=True, discounted_price__gt=0, discounted_price__lt=F('original_price'), amazon_source__isnull=True) & ~free & ~checkout
    checkout_amount = Case(
        When(payment_config__currency__in=ZERO_DECIMAL, then=F('payment_config__amount_minor')),
        When(payment_config__currency__in=THREE_DECIMAL, then=ExpressionWrapper(F('payment_config__amount_minor') / Value(1000.0), output_field=amount_field)),
        default=ExpressionWrapper(F('payment_config__amount_minor') / Value(100.0), output_field=amount_field), output_field=amount_field,
    )
    return queryset.annotate(
        browse_price=Case(
            When(fresh_offer, then=F('amazon_source__price')),
            When(amazon_source__isnull=False, then=Value(None)),
            When(checkout, then=checkout_amount), When(free, then=Value(Decimal('0'))),
            When(discount_active=True, discounted_price__gt=0, then=F('discounted_price')),
            default=F('original_price'), output_field=amount_field,
        ),
        browse_currency=Case(When(fresh_offer, then=Upper('amazon_source__currency')),
            When(amazon_source__isnull=False, then=Value('')), When(checkout, then=Upper('payment_config__currency')),
            default=Value('USD'), output_field=CharField()),
        browse_free=Case(When(free, then=Value(True)), default=Value(False), output_field=BooleanField()),
        browse_sale=Case(When(discounted, then=Value(True)), default=Value(False), output_field=BooleanField()),
        browse_platform=Case(When(amazon_source__isnull=False, then=Value('amazon')), default=F('ecommerce_platform'), output_field=CharField()),
    )


def product_list_response(request, queryset):
    sort = request.GET.get('sort', 'newest')
    platform = request.GET.get('platform', '')
    offer = request.GET.get('offer', '')
    currency = request.GET.get('currency', '').upper()
    if sort not in {'newest', 'oldest', 'price_asc', 'price_desc'} or platform not in {'', *dict(Product.ECOMMERCE_PLATFORM_CHOICES)} or offer not in {'', 'sale', 'free'}:
        return JsonResponse({'error': 'Choose a supported sort or filter.'}, status=400)
    if currency and (len(currency) != 3 or not currency.isascii() or not currency.isalpha()):
        return JsonResponse({'error': 'Choose a valid currency.'}, status=400)
    bounds = {}
    try:
        for key in ('min_price', 'max_price'):
            if request.GET.get(key):
                value = Decimal(request.GET[key])
                if not value.is_finite() or value < 0 or value > Decimal('999999999999'):
                    raise InvalidOperation
                bounds[key] = value
    except InvalidOperation:
        return JsonResponse({'error': 'Use valid, non-negative price amounts.'}, status=400)
    if bounds.get('min_price', Decimal('0')) > bounds.get('max_price', Decimal('999999999999')):
        return JsonResponse({'error': 'Minimum price must not exceed maximum price.'}, status=400)
    if (bounds or sort.startswith('price_')) and not currency:
        return JsonResponse({'error': 'Choose one currency to compare prices.'}, status=400)
    queryset = browsing_prices(queryset, timezone.now())
    total_count = queryset.count()
    if request.GET.get('search'):
        term = request.GET['search'][:200]
        # Automated products expose only the fresh provider title, not placeholder descriptions.
        queryset = queryset.filter(Q(amazon_source__isnull=True) & (Q(name__icontains=term) | Q(description__icontains=term)) | Q(amazon_source__title__icontains=term))
    def counts(field):
        return dict(queryset.order_by().values(field).annotate(count=Count('pk')).values_list(field, 'count'))
    categories = counts('category')
    platforms = counts('browse_platform')
    currencies = counts('browse_currency')
    offers = queryset.aggregate(sale=Count('pk', filter=Q(browse_sale=True)), free=Count('pk', filter=Q(browse_free=True)))
    facets = {
        'platforms': [{'value': value, 'label': 'Direct / creator' if value == 'none' else label, 'count': platforms[value]} for value, label in Product.ECOMMERCE_PLATFORM_CHOICES if platforms.get(value)],
        'currencies': [{'value': value, 'label': value, 'count': count} for value, count in sorted(currencies.items()) if value],
        'offers': [{'value': value, 'label': label, 'count': offers[value]} for value, label in [('sale', 'On sale'), ('free', 'Free for a limited time')]],
    }
    if request.GET.get('category'):
        queryset = queryset.filter(category=request.GET['category'])
    if platform:
        queryset = queryset.filter(browse_platform=platform)
    if offer:
        queryset = queryset.filter(**{f'browse_{offer}': True})
    if currency:
        queryset = queryset.filter(browse_currency=currency)
    if 'min_price' in bounds:
        queryset = queryset.filter(browse_price__gte=bounds['min_price'])
    if 'max_price' in bounds:
        queryset = queryset.filter(browse_price__lte=bounds['max_price'])
    ordering = {'newest': ['-created_at', '-pk'], 'oldest': ['created_at', 'pk'],
                'price_asc': [F('browse_price').asc(nulls_last=True), '-pk'],
                'price_desc': [F('browse_price').desc(nulls_last=True), '-pk']}[sort]
    favorites = favorite_ids(request)
    data = paginate(request, queryset.select_related('payment_config').order_by(*ordering), lambda p: product_data(p, favorites))
    data['categories'] = [{'value': value, 'label': label, 'count': categories.get(value, 0)} for value, label in Product.PRODUCT_CATEGORY_CHOICES]
    data.update(facets=facets, total_count=total_count, sort=sort)
    return JsonResponse(data)


@endpoint()
def products(request):
    return product_list_response(request, catalog_queryset(Product.objects.all()))


@endpoint(authenticated=True)
def favorites(request):
    return product_list_response(request, catalog_queryset(request.user.favorite_products.all()))


@endpoint()
def product_detail(request, product_id):
    return JsonResponse({"product": product_data(get_object_or_404(catalog_queryset(Product.objects.all()), pk=product_id), favorite_ids(request))})


@endpoint(("POST",), authenticated=True)
def product_favorite(request, product_id):
    value = payload(request).get("is_favorite")
    if not isinstance(value, bool):
        return JsonResponse({"error": "is_favorite must be true or false."}, status=400)
    product = get_object_or_404(catalog_queryset(Product.objects.all()), pk=product_id)
    if value:
        product.favorites.add(request.user)
    else:
        product.favorites.remove(request.user)
    return JsonResponse({"is_favorite": value})


def public_blog():
    return BlogPost.objects.filter(status="published", published_at__lte=timezone.now()).select_related("author")


def post_data(post):
    return {"id": post.pk, "slug": post.slug, "title": post.title, "excerpt": post.excerpt, "body": safe_html(post.body), "category": post.category, "cover_image": image_url(post.cover_image), "published_at": post.published_at, "author": post.author.username if post.author else ""}


@endpoint()
def blog(request):
    queryset = public_blog()
    categories = list(queryset.exclude(category="").order_by("category").values_list("category", flat=True).distinct())
    if request.GET.get("category"):
        queryset = queryset.filter(category=request.GET["category"])
    if request.GET.get("search"):
        queryset = queryset.filter(Q(title__icontains=request.GET["search"][:200]) | Q(excerpt__icontains=request.GET["search"][:200]))
    data = paginate(request, queryset, post_data)
    data["categories"] = categories
    return JsonResponse(data)


@endpoint()
def blog_detail(request, slug):
    return JsonResponse({"post": post_data(get_object_or_404(public_blog(), slug=slug))})


@endpoint()
def announcements(request):
    queryset = Announcement.objects.filter(is_active=True).order_by("-created_at", "-pk")
    if request.GET.get('announcement'):
        try:
            queryset = queryset.filter(pk=int(request.GET['announcement']))
        except (ValueError, OverflowError):
            queryset = queryset.none()
    return JsonResponse(paginate(request, queryset, lambda item: {
        "id": item.pk, "title": item.title, "message": safe_html(item.message),
        "thumbnail": image_url(item.thumbnail), "image": image_url(item.image), "created_at": item.created_at,
    }))


def event_data(event, applied_ids=()):
    return {
        "id": event.pk, "title": event.title, "description": safe_html(event.description), "details": safe_html(event.details),
        "deadline": event.deadline, "date": event.date, "deadline_passed": timezone.now() > event.deadline,
        "has_applied": event.pk in applied_ids,
        "fields": [{"id": field.pk, "name": field.name, "field_type": field.field_type, "required": field.field_type != "boolean"} for field in event.custom_fields.all()],
    }


def applied_ids(request):
    return set(EventApplication.objects.filter(applicant=request.user).values_list("event_id", flat=True)) if active_member(request) else set()


@endpoint()
def events(request):
    queryset = Event.objects.filter(is_active=True).prefetch_related("custom_fields").order_by("-posted_date", "-pk")
    if request.GET.get("search"):
        queryset = queryset.filter(Q(title__icontains=request.GET["search"][:200]) | Q(description__icontains=request.GET["search"][:200]))
    applied = applied_ids(request)
    return JsonResponse(paginate(request, queryset, lambda event: event_data(event, applied)))


@endpoint()
def event_detail(request, event_id):
    event = get_object_or_404(Event.objects.prefetch_related("custom_fields"), pk=event_id, is_active=True)
    return JsonResponse({"event": event_data(event, applied_ids(request))})


@endpoint(("POST",), authenticated=True)
def event_apply(request, event_id):
    if request.user.role != "user":
        return JsonResponse({"error": "Only members can apply for events."}, status=403)
    event = get_object_or_404(Event.objects.prefetch_related("custom_fields"), pk=event_id, is_active=True)
    if timezone.now() > event.deadline:
        return JsonResponse({"error": "The application deadline has passed."}, status=400)
    data = payload(request)
    cover_letter = data.get("cover_letter", "")
    if not isinstance(cover_letter, str) or len(cover_letter) > 10000:
        return JsonResponse({"error": "Cover letter must be text, at most 10,000 characters."}, status=400)
    form = EventApplicationForm(data, event=event)
    if not form.is_valid():
        return JsonResponse({"error": "Please check the application fields.", "errors": form.errors.get_json_data()}, status=400)
    try:
        with transaction.atomic():
            application = EventApplication.objects.create(event=event, applicant=request.user, cover_letter=cover_letter)
            responses = []
            for field in event.custom_fields.all():
                value = form.cleaned_data[f"field_{field.pk}"]
                responses.append(EventFieldResponse(application=application, field=field, **{f"value_{field.field_type}": value}))
            EventFieldResponse.objects.bulk_create(responses)
    except IntegrityError:
        return JsonResponse({"error": "You have already applied for this event."}, status=409)
    return JsonResponse({"application": application_data(application)}, status=201)


def application_data(application):
    return {
        "id": application.pk, "event": event_data(application.event, (application.event_id,)),
        "status": application.status, "cover_letter": application.cover_letter,
        "applied_date": application.applied_date, "updated_date": application.updated_date,
        "responses": [{"field_id": response.field_id, "name": response.field.name, "field_type": response.field.field_type, "value": getattr(response, f"value_{response.field.field_type}")} for response in application.field_responses.all()],
        "url": f"/applications/events/{application.pk}",
        "can_edit": application.status == "pending" and application.event.is_active and timezone.now() <= application.event.deadline,
        "can_withdraw": application.status == "pending",
        "edit_url": f"/applications/events/{application.pk}" if application.status == "pending" else None,
        "withdraw_api_url": reverse("platform_api:application-withdraw", args=[application.pk]),
    }


@endpoint(authenticated=True)
def applications(request):
    queryset = EventApplication.objects.filter(applicant=request.user).select_related("event").prefetch_related("field_responses__field", "event__custom_fields").order_by("-applied_date", "-pk")
    return JsonResponse(paginate(request, queryset, application_data))


@endpoint(("POST",), authenticated=True)
def application_withdraw(request, application_id):
    with transaction.atomic():
        application = get_object_or_404(EventApplication.objects.select_for_update(), pk=application_id, applicant=request.user)
        if application.status != "pending":
            return JsonResponse({"error": "Only pending applications can be withdrawn."}, status=409)
        application.delete()
    return JsonResponse({"success": True})


@endpoint(authenticated=True)
def notifications(request):
    from notifications.announcement_inbox import member_notifications
    queryset = member_notifications(request.user).order_by("-created_at", "-pk")
    data = paginate(request, queryset, notification_data)
    data["unread_count"] = queryset.filter(is_read=False).count()
    return JsonResponse(data)


def notification_data(item):
    from notifications.activity_email import target_path
    target = target_path(item)
    return {"id": item.pk, "title": item.title, "message": item.message,
        "notification_type": item.notification_type, "is_read": item.is_read,
        "created_at": item.created_at, "url": target if target != '/notifications' else None}


@endpoint(("POST",), authenticated=True)
def notification_read(request, notification_id):
    item = get_object_or_404(Notification, pk=notification_id, user=request.user)
    item.mark_as_read()
    return JsonResponse({"success": True})


@endpoint(("POST",), authenticated=True)
def notifications_read_all(request):
    from notifications.announcement_inbox import member_notifications
    count = member_notifications(request.user).filter(is_read=False).update(is_read=True)
    return JsonResponse({"success": True, "count": count})


PREFERENCE_FIELDS = (
    "email_enabled", "in_app_enabled", "email_application_updates", "email_ranking_updates", "email_edit_reports", "email_achievements",
    "email_newsletter", "email_blog_updates", "email_shop_updates",
    "in_app_application_updates", "in_app_ranking_updates", "in_app_edit_reports", "in_app_achievements",
)


@endpoint(("GET", "PATCH"), authenticated=True)
def notification_preferences(request):
    preferences = NotificationPreference.objects.filter(user=request.user).first() or NotificationPreference(user=request.user)
    if request.method == "PATCH":
        data = payload(request)
        if not data or set(data) - set(PREFERENCE_FIELDS) or any(not isinstance(value, bool) for value in data.values()):
            return JsonResponse({"error": "Supply notification preference fields as true or false."}, status=400)
        with transaction.atomic():
            preferences, _ = NotificationPreference.objects.get_or_create(user=request.user)
            # Update only supplied fields so independent preference changes do not overwrite each other.
            NotificationPreference.objects.filter(pk=preferences.pk).update(**data, updated_at=timezone.now())
            preferences.refresh_from_db()
            from notifications.campaigns import cancel_opted_out_deliveries
            cancel_opted_out_deliveries(request.user.pk)
            from notifications.activity_email import cancel_opted_out_activity
            cancel_opted_out_activity(request.user.pk)
    from notifications.campaigns import delivery_state
    from notifications.activity_email import delivery_state as activity_delivery_state
    activity = activity_delivery_state()
    return JsonResponse({"preferences": {field: getattr(preferences, field) for field in PREFERENCE_FIELDS},
        "email_delivery_active": activity["email_activity_delivery_active"], **delivery_state(), **activity})


@endpoint(("GET", "POST"))
def contact(request):
    site_key = getattr(settings, "RECAPTCHA_SITE_KEY", "")
    secret_key = getattr(settings, "RECAPTCHA_SECRET_KEY", "")
    if request.method == "GET":
        return JsonResponse({"recaptcha_site_key": site_key, "recaptcha_enabled": bool(site_key and secret_key)})
    data = payload(request)
    form = ContactForm(data)
    if not form.is_valid():
        return JsonResponse({"error": "Please check the contact fields.", "errors": form.errors.get_json_data()}, status=400)
    if len(form.cleaned_data["message"]) > 10000:
        return JsonResponse({"error": "Message must be at most 10,000 characters."}, status=400)
    if bool(site_key) != bool(secret_key):
        return JsonResponse({"error": "Contact verification is not configured correctly."}, status=503)
    if site_key and secret_key:
        # Reuse the existing verification implementation for JSON form submissions.
        request.POST = {"g-recaptcha-response": data.get("g-recaptcha-response", "")}
        if not verify_recaptcha(request):
            return JsonResponse({"error": "Please complete the reCAPTCHA verification."}, status=400)
    throttle_key = "v2-contact:" + request.META.get("REMOTE_ADDR", "unknown")
    if not cache.add(throttle_key, 1, timeout=600):
        try:
            attempts = cache.incr(throttle_key)
        except ValueError:
            cache.set(throttle_key, 1, timeout=600)
            attempts = 1
        if attempts > 5:
            return JsonResponse({"error": "Too many messages. Please try again later."}, status=429)
    recipient = getattr(settings, "SUPPORT_INBOX", "")
    backend = settings.EMAIL_BACKEND
    local_file_delivery = backend == "django.core.mail.backends.filebased.EmailBackend" and getattr(settings, "V2_LOCAL_PREVIEW", False)
    if not recipient or backend in ("django.core.mail.backends.dummy.EmailBackend", "django.core.mail.backends.console.EmailBackend") or (backend == "django.core.mail.backends.filebased.EmailBackend" and not local_file_delivery):
        return JsonResponse({"error": "Contact email delivery is not configured yet."}, status=503)
    values = form.cleaned_data
    message = EmailMessage(
        subject=f"Contact Form: {values['subject']}",
        body=f"From: {values['name']}\nEmail: {values['email']}\n\n{values['message']}",
        from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient], reply_to=[values["email"]],
    )
    try:
        if message.send(fail_silently=False) != 1:
            return JsonResponse({"error": "The mail server did not accept your message."}, status=503)
    except BadHeaderError:
        return JsonResponse({"error": "Invalid email header."}, status=400)
    except Exception:
        logger.exception("V2 contact delivery failed")
        return JsonResponse({"error": "Unable to send your message. Please try again later."}, status=503)
    message = "Your message was saved to the local email inbox for testing." if local_file_delivery else "Your message was accepted by the mail service."
    return JsonResponse({"success": True, "message": message})
