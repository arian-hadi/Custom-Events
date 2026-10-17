from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from announcements.models import Announcement
from events.models import Event, EventApplication, EventField, EventFieldResponse
from notifications.models import Notification, NotificationPreference
from shop.models import Product

from .models import BlogPost, SiteSettings
from .sanitization import safe_html


class WebsiteAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.member = User.objects.create_user(email="member@example.test", username="member", password="Testing-Password-123", is_verified=True)
        cls.other = User.objects.create_user(email="other@example.test", username="other", password="Testing-Password-123", is_verified=True)
        cls.admin = User.objects.create_user(email="admin@example.test", username="admin", password="Testing-Password-123", role="admin", is_staff=True, is_verified=True)
        # Existing products reference stored images; these tests do not write media.
        cls.product = Product(name="Figure", description='<p>Details</p><script>alert(1)</script>', thumbnail="shop/test.png", main_image="shop/test.png", original_price="20.00", redirect_url="https://example.com/buy")
        cls.inactive = Product(name="Hidden", description="Hidden", thumbnail="shop/test.png", main_image="shop/test.png", original_price="30.00", redirect_url="https://example.com/buy", is_active=False)
        Product.objects.bulk_create([cls.product, cls.inactive])
        cls.event = Event.objects.create(title="Community event", description="Join us", created_by=cls.admin, deadline=timezone.now() + timedelta(days=1), date=timezone.now() + timedelta(days=2))
        cls.text_field = EventField.objects.create(event=cls.event, name="Your entry", field_type="text")
        cls.number_field = EventField.objects.create(event=cls.event, name="Number", field_type="number")
        cls.boolean_field = EventField.objects.create(event=cls.event, name="Agree", field_type="boolean")

    def setUp(self):
        cache.clear()

    def login(self, user=None):
        self.client.force_login(user or self.member)

    def json_post(self, path, data):
        return self.client.post(path, data, content_type="application/json")

    def test_public_settings_defaults_do_not_write_and_admin_saved_content_is_used(self):
        response = self.client.get("/api/v2/site/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SiteSettings.objects.count(), 0)
        SiteSettings.objects.create(accent_color="#123abc", secondary_accent_color="#456def", hero_title="New hero")
        site = self.client.get("/api/v2/site/").json()["site"]
        self.assertEqual(site["accent_color"], "#123abc")
        self.assertEqual(site["secondary_accent_color"], "#456def")
        self.assertEqual(site["hero_title"], "New hero")
        self.assertEqual(site["home_sections"][2]["button_url"], "/editing-hub")
        self.assertEqual(self.json_post("/api/v2/site/", {"hero_title": "Unauthorized"}).status_code, 405)

    def test_site_settings_reject_executable_links_and_invalid_color(self):
        for values in ({"hero_button_url": "javascript:alert(1)"}, {"accent_color": "red;background:url(x)"}, {"secondary_accent_color": "red;background:url(x)"}, {"social_links": [{"label": "Bad", "url": "//evil.test"}]}):
            with self.assertRaises(ValidationError):
                SiteSettings(**values).full_clean()

    def test_support_link_is_optional_admin_managed_and_can_be_cleared(self):
        self.assertEqual(self.client.get("/api/v2/site/").json()["site"]["buy_me_a_coffee_url"], "")
        self.assertFalse(SiteSettings.objects.exists())
        config = SiteSettings.objects.create(buy_me_a_coffee_url="https://buymeacoffee.com/creator")
        self.assertEqual(
            self.client.get("/api/v2/site/").json()["site"]["buy_me_a_coffee_url"],
            "https://buymeacoffee.com/creator",
        )
        config.buy_me_a_coffee_url = ""
        config.save()
        self.assertEqual(self.client.get("/api/v2/site/").json()["site"]["buy_me_a_coffee_url"], "")

    def test_support_link_rejects_unsafe_or_non_profile_destinations(self):
        for url in (
            "javascript:alert(1)", "http://buymeacoffee.com/creator",
            "https://buymeacoffee.com.evil.test/creator", "https://evil.test/creator",
            "https://user@buymeacoffee.com/creator", "https://buymeacoffee.com:8443/creator",
            "https://buymeacoffee.com/", "https://buymeacoffee.com/creator/posts",
            "https://buymeacoffee.com/creator?redirect=https://evil.test",
            "https://buymeacoffee.com/creator#other", "https://buymeacoffee.com/crea tor",
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                SiteSettings(buy_me_a_coffee_url=url).full_clean()
        SiteSettings(buy_me_a_coffee_url="https://www.buymeacoffee.com/creator/").full_clean()

    def test_products_filter_inactive_and_sanitize_rich_content(self):
        response = self.client.get("/api/v2/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["description"], "<p>Details</p>")
        self.assertEqual(response.json()["results"][0]["current_price"], "20.00")
        self.assertEqual(self.client.get(f"/api/v2/products/{self.inactive.pk}/").status_code, 404)

    def test_favorite_is_idempotent_private_and_never_accepts_other_user_id(self):
        path = f"/api/v2/products/{self.product.pk}/favorite/"
        self.assertEqual(self.json_post(path, {"is_favorite": True}).status_code, 401)
        self.login()
        for _ in range(2):
            self.assertEqual(self.json_post(path, {"is_favorite": True, "user": self.other.pk}).status_code, 200)
        self.assertEqual(self.product.favorites.count(), 1)
        self.assertTrue(self.product.favorites.filter(pk=self.member.pk).exists())
        self.assertEqual(self.client.get("/api/v2/favorites/").json()["count"], 1)
        self.login(self.other)
        self.assertEqual(self.client.get("/api/v2/favorites/").json()["count"], 0)
        self.assertFalse(self.client.get(f"/api/v2/products/{self.product.pk}/").json()["product"]["is_favorite"])
        self.assertEqual(self.json_post(path, {"is_favorite": "false"}).status_code, 400)

    def test_draft_future_blog_and_inactive_announcements_are_not_public(self):
        BlogPost.objects.create(title="Draft", slug="draft", body="Secret")
        BlogPost.objects.create(title="Future", slug="future", body="Secret", status="published", published_at=timezone.now() + timedelta(days=1))
        BlogPost.objects.create(title="Published", slug="published", body="<p>Hello</p>", status="published", category="Community")
        Announcement.objects.create(title="Hidden announcement", message="Secret", is_active=False)
        Announcement.objects.create(title="Announcement", message="Hello")
        self.assertEqual(self.client.get("/api/v2/blog/").json()["count"], 1)
        self.assertEqual(self.client.get("/api/v2/blog/").json()["categories"], ["Community"])
        self.assertEqual(self.client.get("/api/v2/blog/draft/").status_code, 404)
        self.assertEqual(self.client.get("/api/v2/blog/future/").status_code, 404)
        self.assertEqual(self.client.get("/api/v2/announcements/").json()["count"], 1)

    def test_event_application_validates_fields_is_atomic_and_rejects_duplicates(self):
        self.login()
        url = f"/api/v2/events/{self.event.pk}/apply/"
        self.assertEqual(self.json_post(url, {f"field_{self.text_field.pk}": "Entry", f"field_{self.number_field.pk}": "invalid"}).status_code, 400)
        self.assertEqual(EventApplication.objects.count(), 0)
        data = {f"field_{self.text_field.pk}": "Entry", f"field_{self.number_field.pk}": 5, f"field_{self.boolean_field.pk}": False, "applicant": self.other.pk, "status": "accepted"}
        response = self.json_post(url, data)
        self.assertEqual(response.status_code, 201, response.content)
        application = EventApplication.objects.get()
        self.assertEqual(application.applicant_id, self.member.pk)
        self.assertEqual(application.status, "pending")
        self.assertEqual(EventFieldResponse.objects.count(), 3)
        self.assertEqual(self.json_post(url, data).status_code, 409)
        self.assertEqual(EventFieldResponse.objects.count(), 3)
        self.assertTrue(self.client.get(f"/api/v2/events/{self.event.pk}/").json()["event"]["has_applied"])

    def test_expired_and_unpublished_event_cannot_accept_applications(self):
        self.login()
        Event.objects.filter(pk=self.event.pk).update(deadline=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.json_post(f"/api/v2/events/{self.event.pk}/apply/", {}).status_code, 400)
        Event.objects.filter(pk=self.event.pk).update(is_active=False)
        self.assertEqual(self.client.get(f"/api/v2/events/{self.event.pk}/").status_code, 404)
        self.assertEqual(self.json_post(f"/api/v2/events/{self.event.pk}/apply/", {}).status_code, 404)

    def test_application_lists_are_private_and_public_event_does_not_leak_applicants(self):
        EventApplication.objects.create(event=self.event, applicant=self.other, cover_letter="Private secret")
        self.assertEqual(self.client.get("/api/v2/applications/").status_code, 401)
        self.login()
        self.assertEqual(self.client.get("/api/v2/applications/").json()["count"], 0)
        self.assertNotIn(b"Private secret", self.client.get(f"/api/v2/events/{self.event.pk}/").content)
        self.login(self.other)
        result = self.client.get("/api/v2/applications/").json()["results"][0]
        self.assertEqual(result["cover_letter"], "Private secret")
        self.assertEqual(result["url"], f"/applications/events/{result['id']}")
        self.assertNotIn("legacy_url", result)
        self.assertTrue(result["can_withdraw"])
        self.assertNotIn("withdraw_url", result)

    def test_withdraw_requires_post_owner_and_pending_status(self):
        application = EventApplication.objects.create(event=self.event, applicant=self.member)
        url = f"/api/v2/applications/{application.pk}/withdraw/"
        self.login()
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(EventApplication.objects.filter(pk=application.pk).exists())
        self.login(self.other)
        self.assertEqual(self.json_post(url, {}).status_code, 404)
        self.login()
        EventApplication.objects.filter(pk=application.pk).update(status="accepted")
        self.assertEqual(self.json_post(url, {}).status_code, 409)
        EventApplication.objects.filter(pk=application.pk).update(status="pending")
        self.assertEqual(self.json_post(url, {}).status_code, 200)
        self.assertFalse(EventApplication.objects.filter(pk=application.pk).exists())

    def test_inactive_and_unverified_legacy_sessions_cannot_use_private_v2_api(self):
        for changes in ({"is_active": False}, {"is_active": True, "is_verified": False}):
            get_user_model().objects.filter(pk=self.member.pk).update(**changes)
            self.member.refresh_from_db()
            self.client.force_login(self.member, backend="accounts.authentication.EmailBackend")
            self.assertEqual(self.client.get("/api/v2/applications/").status_code, 401)
            self.assertEqual(self.client.get("/api/v2/notification-preferences/").status_code, 401)
            self.assertEqual(self.json_post(f"/api/v2/products/{self.product.pk}/favorite/", {"is_favorite": True}).status_code, 401)

    def test_notifications_and_preferences_cannot_access_other_users(self):
        private = Notification.objects.create(user=self.other, title="Private", message="Secret", notification_type="ranking_updated")
        mine = Notification.objects.create(user=self.member, title="Mine", message="Hello", notification_type="ranking_updated")
        self.assertEqual(self.client.get("/api/v2/notifications/").status_code, 401)
        self.login()
        data = self.client.get("/api/v2/notifications/").json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["unread_count"], 1)
        self.assertEqual(self.json_post(f"/api/v2/notifications/{private.pk}/read/", {}).status_code, 404)
        self.assertEqual(self.json_post(f"/api/v2/notifications/{mine.pk}/read/", {}).status_code, 200)
        self.assertEqual(self.client.get("/api/v2/notifications/").json()["unread_count"], 0)
        self.assertEqual(NotificationPreference.objects.count(), 0)
        self.assertFalse(self.client.get("/api/v2/notification-preferences/").json()["email_delivery_active"])
        self.assertEqual(NotificationPreference.objects.count(), 0)
        result = self.client.patch("/api/v2/notification-preferences/", {"email_enabled": False}, content_type="application/json")
        self.assertEqual(result.status_code, 200)
        self.assertFalse(NotificationPreference.objects.get(user=self.member).email_enabled)
        self.assertFalse(NotificationPreference.objects.filter(user=self.other).exists())
        self.assertEqual(self.client.patch("/api/v2/notification-preferences/", {"user_id": self.other.pk}, content_type="application/json").status_code, 400)

    def test_mutations_enforce_csrf_including_anonymous_contact(self):
        secure = Client(enforce_csrf_checks=True)
        self.assertEqual(secure.post("/api/v2/contact/", {}, content_type="application/json").status_code, 403)
        secure.force_login(self.member)
        url = f"/api/v2/products/{self.product.pk}/favorite/"
        self.assertEqual(secure.post(url, {"is_favorite": True}, content_type="application/json").status_code, 403)
        self.assertEqual(secure.patch("/api/v2/notification-preferences/", {"email_enabled": False}, content_type="application/json").status_code, 403)
        token = secure.get("/api/v2/auth/csrf/").json()["csrf_token"]
        self.assertEqual(secure.post(url, {"is_favorite": True}, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 200)

    def contact_data(self):
        return {"name": "Person", "email": "sender@example.test", "subject": "Question", "message": "Can you help?", "website": ""}

    def test_contact_sends_to_configured_inbox_and_validates_honeypot(self):
        response = self.json_post("/api/v2/contact/", self.contact_data())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["support@example.test"])
        self.assertEqual(mail.outbox[0].reply_to, ["sender@example.test"])
        data = self.contact_data()
        data["website"] = "https://spam.test"
        self.assertEqual(self.json_post("/api/v2/contact/", data).status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_reports_delivery_failure_instead_of_fake_success(self):
        with patch("platform_api.views.EmailMessage.send", return_value=0):
            self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 503)
        with patch("platform_api.views.EmailMessage.send", side_effect=OSError("Mail server unavailable")):
            self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 503)
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 503)

    def test_contact_file_capture_requires_explicit_local_preview_and_honest_message(self):
        with TemporaryDirectory() as email_directory:
            with override_settings(EMAIL_BACKEND="django.core.mail.backends.filebased.EmailBackend", EMAIL_FILE_PATH=email_directory, V2_LOCAL_PREVIEW=False):
                self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 503)
                self.assertEqual(list(Path(email_directory).iterdir()), [])
            with override_settings(EMAIL_BACKEND="django.core.mail.backends.filebased.EmailBackend", EMAIL_FILE_PATH=email_directory, V2_LOCAL_PREVIEW=True):
                response = self.json_post("/api/v2/contact/", self.contact_data())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["message"], "Your message was saved to the local email inbox for testing.")
                saved = list(Path(email_directory).iterdir())
                self.assertEqual(len(saved), 1)
                self.assertIn("Can you help?", saved[0].read_text())

    @override_settings(RECAPTCHA_SITE_KEY="site-key", RECAPTCHA_SECRET_KEY="secret-key")
    def test_contact_checks_captcha_when_configured(self):
        self.assertTrue(self.client.get("/api/v2/contact/").json()["recaptcha_enabled"])
        with patch("platform_api.views.verify_recaptcha", return_value=False):
            self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 400)
        with patch("platform_api.views.verify_recaptcha", return_value=True):
            self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 200)

    def test_contact_throttles_repeated_messages(self):
        for _ in range(5):
            self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 200)
        self.assertEqual(self.json_post("/api/v2/contact/", self.contact_data()).status_code, 429)

    def test_rich_text_sanitizer_removes_active_content_but_preserves_formatting(self):
        dirty = '<p onclick="alert(1)">Hello <strong>friend</strong></p><img src="/media/a.png" onerror="alert(1)"><a href="javascript:alert(1)">bad</a><svg><script>alert(1)</script></svg><a href="https://example.com">safe</a>'
        clean = safe_html(dirty)
        self.assertIn("<strong>friend</strong>", clean)
        self.assertIn('src="/media/a.png"', clean)
        self.assertIn('href="https://example.com"', clean)
        for unsafe in ("onclick", "onerror", "javascript:", "<svg", "<script", "alert(1)"):
            self.assertNotIn(unsafe, clean)

    def test_malformed_json_and_wrong_methods_have_json_errors(self):
        self.assertEqual(self.client.post("/api/v2/contact/", "{invalid", content_type="application/json").status_code, 400)
        self.assertEqual(self.json_post("/api/v2/products/", {}).status_code, 405)
