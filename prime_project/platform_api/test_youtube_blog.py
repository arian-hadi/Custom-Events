from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from notifications.admin_email import deliver
from notifications.models import AdminEmailDelivery, AdminEmailSettings
from .blog_markdown import ai_brief, import_article, parse_article
from .models import BlogPost, YouTubeBlogChannel, YouTubeBlogVideo, BlogMarkdownImport
from .youtube_admin import VideoForm, ChannelForm
from .youtube_blog import sync_channel, prepare_captions, add_video
from .youtube_source import ProviderError


VIDEO_ID = "AbcDefGh_12"
CHANNEL_ID = "UC" + "a" * 22


@override_settings(ADMIN_NOTIFICATION_RECIPIENTS="owner@example.test", ADMIN_EMAIL_SEND_IMMEDIATELY=False,
                   ADMIN_NOTIFICATION_BASE_URL="http://testserver")
class YouTubeBlogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="owner@example.test", username="owner", password="test-password", is_staff=True, is_superuser=True)
        cls.staff = get_user_model().objects.create_user(email="staff@example.test", username="staff", password="test-password", is_staff=True)
        cls.channel = YouTubeBlogChannel.objects.create(name="Creator", channel_url="https://www.youtube.com/@creator")
        cls.video = YouTubeBlogVideo.objects.create(channel=cls.channel, video_id=VIDEO_ID, title="Source video", transcript="Real script text.", transcript_source="Administrator script")

    def article(self, body="## A heading\n\nA thoughtful article."):
        return f'---\ntitle: "A new article"\nexcerpt: "A short summary"\ncategory: "Transformers"\nsource_video_id: "{VIDEO_ID}"\n---\n\n{body}'

    def resolved(self):
        return {"channel_id": CHANNEL_ID, "title": "Creator", "uploads_playlist_id": "UUuploads"}

    def metadata(self, video_id="OtherVideo1"):
        return {"video_id": video_id, "title": "Discovered video", "description": "Description", "published_at": timezone.now(), "thumbnail_url": "https://i.ytimg.com/vi/video/default.jpg", "channel_id": CHANNEL_ID}

    def test_brief_contains_complete_source_and_import_contract(self):
        self.channel.writing_instructions = "Keep the author's tone."
        self.channel.save()
        brief = ai_brief(self.video)
        self.assertIn("Real script text.", brief)
        self.assertIn("source_video_id", brief)
        self.assertIn(VIDEO_ID, brief)
        self.assertIn("Keep the author's tone.", brief)

    def test_brief_requires_script_and_does_not_invent_one(self):
        self.video.transcript = ""
        with self.assertRaisesMessage(ValidationError, "Add your script"):
            ai_brief(self.video)

    def test_import_creates_unpublished_editable_draft_and_audit(self):
        post = import_article(self.video.pk, self.article(), self.owner)
        self.assertEqual(post.status, "draft")
        self.assertEqual(post.author, self.owner)
        self.assertIn("<h2>A heading</h2>", post.body)
        self.assertEqual(BlogMarkdownImport.objects.get().original_markdown, self.article())
        self.assertEqual(self.client.get(f"/api/v2/blog/{post.slug}/").status_code, 404)

    def test_repeat_import_is_idempotent_and_preserves_later_editor_changes(self):
        post = import_article(self.video.pk, self.article(), self.owner)
        post.body = "Human revision"
        post.save()
        repeated = import_article(self.video.pk, self.article(), self.owner)
        self.assertEqual(repeated.pk, post.pk)
        self.assertEqual(repeated.body, "Human revision")
        self.assertEqual(BlogPost.objects.count(), 1)
        self.assertEqual(BlogMarkdownImport.objects.count(), 1)

    def test_revised_markdown_updates_draft_and_retains_import_history(self):
        post = import_article(self.video.pk, self.article(), self.owner)
        revised = import_article(self.video.pk, self.article("## Revised\nBetter text."), self.owner)
        self.assertEqual(post.pk, revised.pk)
        self.assertEqual(BlogMarkdownImport.objects.count(), 2)

    def test_published_article_cannot_be_overwritten(self):
        post = import_article(self.video.pk, self.article(), self.owner)
        post.status = "published"
        post.save()
        with self.assertRaisesMessage(ValidationError, "already published"):
            import_article(self.video.pk, self.article("Different content"), self.owner)
        post.refresh_from_db()
        self.assertIn("thoughtful", post.body)

    def test_slug_collision_is_resolved_without_overwriting_existing_post(self):
        BlogPost.objects.create(title="Existing", slug=f"a-new-article-{VIDEO_ID.lower()}", body="Existing")
        new = import_article(self.video.pk, self.article(), self.owner)
        self.assertTrue(new.slug.endswith("-2"))

    def test_import_rejects_wrong_video_extra_fields_aliases_and_empty_content(self):
        for text in (self.article().replace(VIDEO_ID, "WrongVideo1"), self.article().replace("title:", "status: published\ntitle:"),
                     self.article().replace('"A new article"', '&a [nested]'),
                     self.article().replace('"A new article"', '[' * 1100 + '"nested"' + ']' * 1100),
                     self.article("<script>alert(1)</script>"), "plain text"):
            with self.subTest(text=text), self.assertRaises(ValidationError):
                parse_article(text, self.video)
        self.assertFalse(BlogPost.objects.exists())

    def test_import_sanitizes_active_html_and_unsafe_links(self):
        data = parse_article(self.article('<script>alert(1)</script>\n\nSafe text <img src="x" onerror="evil()"> [bad](javascript:alert) <iframe src="x"></iframe>'), self.video)
        for token in ("<script", "onerror", "javascript:", "<iframe", "evil()"):
            self.assertNotIn(token, data["html"])
        self.assertIn("Safe text", data["html"])

    def test_disabled_automatic_channel_does_not_call_provider(self):
        with patch("platform_api.youtube_blog.provider.resolve_channel") as resolve:
            result = sync_channel(self.channel.pk)
        resolve.assert_not_called()
        self.assertTrue(result["skipped"])

    def test_manual_scan_deduplicates_videos_and_admin_email(self):
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=self.metadata()):
            self.assertEqual(sync_channel(self.channel.pk, force=True)["created"], 1)
            self.assertEqual(sync_channel(self.channel.pk, force=True)["created"], 0)
        delivery = AdminEmailDelivery.objects.get(kind="youtube_blog_video")
        self.assertTrue(deliver(delivery.pk))
        self.assertFalse(deliver(delivery.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Nothing has been published", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.assertFalse(BlogPost.objects.exists())

    def test_disabled_notifications_are_respected(self):
        self.channel.notify_admins = False
        self.channel.save()
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=self.metadata()):
            sync_channel(self.channel.pk, force=True)
        self.assertFalse(AdminEmailDelivery.objects.exists())

    @override_settings(ADMIN_EMAIL_SEND_IMMEDIATELY=True)
    def test_discovery_defers_mail_to_worker_even_with_immediate_global_setting(self):
        with self.captureOnCommitCallbacks(execute=True), patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=self.metadata()):
            sync_channel(self.channel.pk, force=True)
        self.assertEqual(AdminEmailDelivery.objects.get().status, "pending")
        self.assertEqual(len(mail.outbox), 0)

    def test_caption_retries_only_latest_item_and_preserves_backlog(self):
        self.channel.fetch_captions = True
        self.channel.save()
        older = YouTubeBlogVideo.objects.create(channel=self.channel, video_id="OlderVideo1", title="Older video")
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=self.metadata()), patch("platform_api.youtube_blog.provider.fetch_transcript", side_effect=ProviderError("No captions yet")) as captions:
            self.assertEqual(sync_channel(self.channel.pk, force=True)["caption_errors"], 1)
            sync_channel(self.channel.pk, force=True)
        self.assertEqual([call.args[0] for call in captions.call_args_list], ["OtherVideo1", "OtherVideo1"])
        older.refresh_from_db()
        self.assertIsNone(older.caption_checked_at)
        self.assertEqual(AdminEmailDelivery.objects.count(), 1)

    def test_latest_title_duplicate_is_skipped_without_backfill_or_email(self):
        self.channel.fetch_captions = True
        self.channel.save()
        data = {**self.metadata(), "title": "  SOURCE\u00a0   VIDEO  "}
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=data) as latest, patch("platform_api.youtube_blog.provider.fetch_transcript") as captions:
            result = sync_channel(self.channel.pk, force=True)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["outcome"], "existing")
        latest.assert_called_once_with(CHANNEL_ID)
        captions.assert_not_called()
        self.assertEqual(YouTubeBlogVideo.objects.count(), 1)
        self.assertFalse(AdminEmailDelivery.objects.exists())
        self.video.refresh_from_db()
        self.assertEqual(self.video.title, "Source video")
        self.assertEqual(self.video.transcript, "Real script text.")

    def test_newest_only_on_first_and_subsequent_due_checks(self):
        self.channel.automatic_checks = True
        self.channel.check_interval_minutes = 90
        self.channel.save()
        now = timezone.now()
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=self.metadata()) as latest:
            self.assertEqual(sync_channel(self.channel.pk, now=now)["created"], 1)
            self.assertTrue(sync_channel(self.channel.pk, now=now + timedelta(minutes=89))["skipped"])
            self.assertEqual(sync_channel(self.channel.pk, now=now + timedelta(minutes=90))["created"], 0)
            latest.return_value = {**self.metadata("NewestVideo"), "title": "A newer upload"}
            self.assertEqual(sync_channel(self.channel.pk, now=now + timedelta(minutes=180))["created"], 1)
        self.assertEqual(latest.call_count, 3)
        self.assertEqual(AdminEmailDelivery.objects.count(), 2)
        self.assertEqual(YouTubeBlogVideo.objects.count(), 3)

    def test_no_published_video_does_not_import_or_process_backlog(self):
        self.channel.fetch_captions = True
        self.channel.save()
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=None), patch("platform_api.youtube_blog.provider.fetch_transcript") as captions:
            result = sync_channel(self.channel.pk, force=True)
        self.assertEqual(result["outcome"], "no_video")
        self.assertEqual(result["created"], 0)
        self.assertFalse(AdminEmailDelivery.objects.exists())
        captions.assert_not_called()

    def test_manual_older_video_import_still_works_and_deduplicates_titles(self):
        data = {**self.metadata(), "published_at": timezone.now() - timedelta(days=400)}
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.fetch_video", return_value=data) as fetch, patch("platform_api.youtube_blog.provider.latest_regular_video") as latest:
            video, created = add_video(self.channel, "https://youtu.be/OtherVideo1")
            self.assertTrue(created)
            fetch.return_value = {**data, "video_id": "Reupload001", "title": "DISCOVERED   video"}
            duplicate, created = add_video(self.channel, "https://youtu.be/Reupload001")
        self.assertFalse(created)
        self.assertEqual(video.pk, duplicate.pk)
        latest.assert_not_called()
        self.assertEqual(AdminEmailDelivery.objects.count(), 1)

    def test_failed_videos_tab_check_does_not_import_and_releases_lease(self):
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", side_effect=ProviderError("Could not read Videos tab")), self.assertRaises(ProviderError):
            sync_channel(self.channel.pk, force=True)
        self.channel.refresh_from_db()
        self.assertIsNone(self.channel.lease_until)
        self.assertIn("Videos tab", self.channel.last_error)
        self.assertEqual(YouTubeBlogVideo.objects.count(), 1)
        self.assertFalse(AdminEmailDelivery.objects.exists())

    def test_caption_fetch_preserves_script_saved_while_provider_is_running(self):
        self.video.transcript = ""
        self.video.save()
        def provider_result(*args, **kwargs):
            YouTubeBlogVideo.objects.filter(pk=self.video.pk).update(transcript="Human script")
            return "Downloaded captions"
        with patch("platform_api.youtube_blog.provider.fetch_transcript", side_effect=provider_result):
            self.assertFalse(prepare_captions(self.video))
        self.video.refresh_from_db()
        self.assertEqual(self.video.transcript, "Human script")

    def test_existing_script_survives_scan_and_caption_fetch(self):
        self.channel.fetch_captions = True
        self.channel.save()
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=self.metadata(VIDEO_ID)), patch("platform_api.youtube_blog.provider.fetch_transcript") as captions:
            sync_channel(self.channel.pk, force=True)
            prepare_captions(self.video)
        captions.assert_not_called()
        self.video.refresh_from_db()
        self.assertEqual(self.video.transcript, "Real script text.")

    def test_missing_captions_explicit_error_not_fake_script(self):
        self.video.transcript = ""
        self.video.save()
        with patch("platform_api.youtube_blog.provider.fetch_transcript", side_effect=ProviderError("No authorized captions.")), self.assertRaises(ProviderError):
            prepare_captions(self.video)
        self.video.refresh_from_db()
        self.assertEqual(self.video.transcript, "")
        self.assertEqual(self.video.transcript_error, "No authorized captions.")

    def test_failed_scan_releases_lease_and_sets_retry_time(self):
        with patch("platform_api.youtube_blog.provider.resolve_channel", side_effect=ProviderError("Configure API key")), self.assertRaises(ProviderError):
            sync_channel(self.channel.pk, force=True)
        self.channel.refresh_from_db()
        self.assertIsNone(self.channel.lease_until)
        self.assertIn("API key", self.channel.last_error)
        self.assertIsNotNone(self.channel.next_check_at)

    def test_active_lease_blocks_overlap_and_scheduled_check_obeys_interval(self):
        self.channel.automatic_checks = True
        self.channel.lease_until = timezone.now() + timedelta(minutes=5)
        self.channel.save()
        with patch("platform_api.youtube_blog.provider.resolve_channel") as resolve:
            self.assertTrue(sync_channel(self.channel.pk, force=True)["skipped"])
            self.channel.lease_until = None
            self.channel.next_check_at = timezone.now() + timedelta(minutes=5)
            self.channel.save()
            self.assertTrue(sync_channel(self.channel.pk)["skipped"])
        resolve.assert_not_called()

    def test_manual_video_must_belong_to_selected_channel(self):
        data = self.metadata()
        data["channel_id"] = "another-channel"
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.fetch_video", return_value=data), self.assertRaisesMessage(ProviderError, "does not belong"):
            add_video(self.channel, "https://youtube.com/watch?v=OtherVideo1")

    def test_admin_forms_render_and_public_visitors_are_redirected(self):
        paths = [reverse("admin:platform_api_youtubeblogchannel_change", args=[self.channel.pk]), reverse("admin:platform_api_youtubeblogvideo_change", args=[self.video.pk]), reverse("admin:youtube_video_import", args=[self.video.pk])]
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 302)
        self.client.force_login(self.owner)
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_admin_latest_check_explains_existing_item(self):
        self.client.force_login(self.owner)
        data = {**self.metadata(), "title": "Source video"}
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=self.resolved()), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=data):
            response = self.client.post(reverse("admin:youtube_channel_check", args=[self.channel.pk]), follow=True)
        self.assertContains(response, "no new notification was queued")
        self.assertContains(response, "Check latest video now")
        self.assertNotContains(response, "latest 50")
        self.assertFalse(AdminEmailDelivery.objects.exists())

    def test_channel_form_accepts_videos_tab_url_without_changing_source(self):
        form = ChannelForm(instance=self.channel)
        form.cleaned_data = {"channel_url": self.channel.channel_url + "/videos"}
        self.assertEqual(form.clean_channel_url(), self.channel.channel_url)

    def test_import_preview_does_not_save_and_confirm_creates_draft(self):
        self.client.force_login(self.owner)
        url = reverse("admin:youtube_video_import", args=[self.video.pk])
        response = self.client.post(url, {"markdown_text": self.article(), "action": "preview"})
        self.assertContains(response, "Article preview")
        self.assertFalse(BlogPost.objects.exists())
        response = self.client.post(url, {"markdown_text": self.article(), "action": "import"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BlogPost.objects.get().status, "draft")

    def test_staff_permissions_protect_source_and_import(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:youtube_video_brief", args=[self.video.pk])).status_code, 403)
        permissions = Permission.objects.filter(content_type__app_label="platform_api", codename__in=["view_youtubeblogvideo", "change_youtubeblogvideo"])
        self.staff.user_permissions.set(permissions)
        self.assertEqual(self.client.get(reverse("admin:youtube_video_brief", args=[self.video.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("admin:youtube_video_import", args=[self.video.pk]), {"markdown_text": self.article(), "action": "import"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:youtube_channel_check", args=[self.channel.pk])).status_code, 403)

    def test_mutations_require_post_and_csrf(self):
        self.client.force_login(self.owner)
        url = reverse("admin:youtube_channel_check", args=[self.channel.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(url).status_code, 403)

    def test_utf8_script_upload_updates_source(self):
        # Test the actual admin form field set (metadata are readonly there).
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get("/admin/")
        request.user = self.owner
        form_class = admin.site._registry[YouTubeBlogVideo].get_form(request, self.video)
        upload = SimpleUploadedFile("script.srt", b"1\n00:00:01,000 --> 00:00:02,000\nHello creator.\n")
        form = form_class({"transcript": "", "instructions": ""}, {"script_file": upload}, instance=self.video)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn("Hello creator.", form.cleaned_data["transcript"])
        self.assertNotIn("-->", form.cleaned_data["transcript"])
