from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.admin.models import LogEntry, DELETION
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from .blog_markdown import import_article
from .models import BlogPost, BlogMarkdownImport, YouTubeBlogChannel, YouTubeBlogVideo, YouTubeBlogSuppression
from .youtube_blog import sync_channel, add_video


@override_settings(ADMIN_NOTIFICATION_RECIPIENTS="", ADMIN_EMAIL_SEND_IMMEDIATELY=False)
class AdminBulkDeleteTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(email="owner@example.test", username="owner", password="test", is_staff=True, is_superuser=True)
        self.staff = get_user_model().objects.create_user(email="staff@example.test", username="staff", password="test", is_staff=True)
        self.channel = YouTubeBlogChannel.objects.create(name="Creator", channel_url="https://youtube.com/@creator", notify_admins=False)
        self.video = YouTubeBlogVideo.objects.create(channel=self.channel, video_id="AbcDefGh_12", title="My video")
        self.other = YouTubeBlogVideo.objects.create(channel=self.channel, video_id="OtherVideo1", title="Other video")
        self.article = '---\ntitle: "My article"\nexcerpt: "Summary"\ncategory: "News"\nsource_video_id: "AbcDefGh_12"\n---\n\nArticle body.'
        self.post = import_article(self.video.pk, self.article, self.owner)
        self.client.force_login(self.owner)

    def url(self, model):
        return reverse(f"admin:platform_api_{model}_changelist")

    def selection(self, *ids, confirm=False, across=False):
        data = {"action": "delete_selected", "_selected_action": [str(pk) for pk in ids], "select_across": "1" if across else "0"}
        if confirm:
            data["post"] = "yes"
        return data

    def test_lists_show_checkboxes_and_bulk_delete_shortcut(self):
        for model in ("blogpost", "youtubeblogvideo", "youtubeblogchannel"):
            response = self.client.get(self.url(model))
            self.assertContains(response, 'id="action-toggle"')
            self.assertContains(response, 'name="_selected_action"')
            self.assertContains(response, 'data-bulk-delete')
            self.assertContains(response, "Select rows using the checkboxes")

    def test_delete_blog_requires_confirmation_and_retains_source_and_import_history(self):
        url = self.url("blogpost")
        response = self.client.post(url, self.selection(self.post.pk))
        self.assertContains(response, "Are you sure?")
        self.assertTrue(BlogPost.objects.filter(pk=self.post.pk).exists())
        response = self.client.post(url, self.selection(self.post.pk, confirm=True))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BlogPost.objects.filter(pk=self.post.pk).exists())
        self.video.refresh_from_db()
        self.assertIsNone(self.video.blog_post_id)
        history = BlogMarkdownImport.objects.get()
        self.assertIsNone(history.post_id)
        self.assertEqual(history.original_markdown, self.article)
        self.assertEqual(history.video_id, self.video.pk)

    def test_delete_selected_source_keeps_blog_and_unselected_items(self):
        response = self.client.post(self.url("youtubeblogvideo"), self.selection(self.video.pk, confirm=True))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(BlogPost.objects.filter(pk=self.post.pk).exists())
        self.assertTrue(YouTubeBlogVideo.objects.filter(pk=self.other.pk).exists())
        self.assertFalse(YouTubeBlogVideo.objects.filter(pk=self.video.pk).exists())
        self.assertEqual(YouTubeBlogSuppression.objects.get().video_id, self.video.video_id)
        history = BlogMarkdownImport.objects.get()
        self.assertIsNone(history.video_id)
        self.assertIn("Deleted source video", str(history))
        self.assertEqual(history.original_markdown, self.article)
        self.assertTrue(LogEntry.objects.filter(action_flag=DELETION, object_id=str(self.video.pk)).exists())

    def test_select_all_obeys_current_filter_and_preserves_other_rows(self):
        second = BlogPost.objects.create(title="Second", slug="second", category="News", body="Body")
        keep = BlogPost.objects.create(title="Keep", slug="keep", category="Other", body="Body")
        url = self.url("blogpost") + "?category__exact=News"
        response = self.client.post(url, self.selection(self.post.pk, confirm=True, across=True))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BlogPost.objects.filter(pk__in=[self.post.pk, second.pk]).exists())
        self.assertTrue(BlogPost.objects.filter(pk=keep.pk).exists())

    def test_staff_without_delete_permission_cannot_delete_by_forged_action(self):
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="platform_api", codename__in=["view_youtubeblogvideo", "change_youtubeblogvideo"]))
        self.client.force_login(self.staff)
        url = self.url("youtubeblogvideo")
        self.assertNotContains(self.client.get(url), "data-bulk-delete")
        self.client.post(url, self.selection(self.video.pk, confirm=True))
        self.assertTrue(YouTubeBlogVideo.objects.filter(pk=self.video.pk).exists())
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(url, self.selection(self.video.pk, confirm=True)).status_code, 403)

    def test_removed_latest_video_stays_removed_until_explicit_manual_import(self):
        self.client.post(self.url("youtubeblogvideo"), self.selection(self.video.pk, confirm=True))
        channel_id = "UC" + "a" * 22
        resolved = {"channel_id": channel_id, "uploads_playlist_id": "UU" + "a" * 22}
        data = {"video_id": self.video.video_id, "title": self.video.title, "description": "", "published_at": timezone.now(), "channel_id": channel_id}
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=resolved), patch("platform_api.youtube_blog.provider.latest_regular_video", return_value=data):
            result = sync_channel(self.channel.pk, force=True)
        self.assertEqual(result["outcome"], "removed")
        self.assertEqual(result["created"], 0)
        self.assertFalse(YouTubeBlogVideo.objects.filter(video_id=self.video.video_id).exists())
        with patch("platform_api.youtube_blog.provider.resolve_channel", return_value=resolved), patch("platform_api.youtube_blog.provider.fetch_video", return_value=data):
            _, created = add_video(self.channel, self.video.video_url)
        self.assertTrue(created)
        self.assertFalse(YouTubeBlogSuppression.objects.exists())

    def test_single_video_delete_uses_same_suppression(self):
        url = reverse("admin:platform_api_youtubeblogvideo_delete", args=[self.video.pk])
        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(YouTubeBlogSuppression.objects.filter(video_id=self.video.video_id).exists())

    def test_import_audit_remains_read_only(self):
        self.assertNotContains(self.client.get(self.url("blogmarkdownimport")), "data-bulk-delete")
