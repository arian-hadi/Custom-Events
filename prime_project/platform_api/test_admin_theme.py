from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .templatetags.platform_admin import admin_workspace


class AdminThemeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="owner@example.test", username="owner", password="test", is_staff=True, is_superuser=True)
        cls.editor = get_user_model().objects.create_user(email="editor@example.test", username="editor", password="test", is_staff=True)
        cls.editor.user_permissions.add(Permission.objects.get(content_type__app_label="platform_api", codename="view_blogpost"))

    def test_admin_home_includes_grouped_workspace_and_real_youtube_shortcut(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Control center")
        self.assertContains(response, "Find a module")
        self.assertContains(response, "Content &amp; website")
        self.assertContains(response, "Prepare videos and import drafts")
        self.assertContains(response, reverse("admin:platform_api_youtubeblogvideo_changelist"))
        self.assertContains(response, "platform_admin/admin.css")

    def test_module_grouping_cannot_grant_permissions(self):
        apps = [{"app_label": "platform_api", "name": "Website content", "models": [{"object_name": "BlogPost", "name": "Blog posts", "admin_url": "/admin/blog/"}]}]
        result = admin_workspace(apps)
        self.assertEqual(result["module_count"], 1)
        self.assertEqual(result["actions"], [])  # A view-only model never gets the add quick action.
        self.assertEqual(result["groups"][0]["key"], "content")

    def test_restricted_editor_only_sees_permitted_modules(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Blog posts")
        self.assertNotContains(response, "YouTube channels")
        self.assertNotContains(response, "Editor applications")
        self.assertNotContains(response, "Write a blog post")
        self.assertNotContains(response, "Admin email settings")

    def test_login_remains_native_csrf_form_and_next_destination(self):
        response = self.client.get(reverse("admin:login"), {"next": "/admin/platform_api/blogpost/"})
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, 'name="password"')
        self.assertContains(response, "/admin/platform_api/blogpost/")
        self.assertContains(response, "2.0Transformers Admin")

    def test_blog_editor_still_contains_summernote_and_publish_controls(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("admin:platform_api_blogpost_add"))
        self.assertContains(response, "summernote-div")
        self.assertContains(response, '"width": "100%"')
        self.assertContains(response, 'name="status"')
        self.assertContains(response, 'name="_save"')

    def test_native_changelist_search_actions_and_filter_survive_theme(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("admin:platform_api_blogpost_changelist"))
        self.assertContains(response, 'id="changelist"')
        self.assertContains(response, 'id="searchbar"')
        self.assertContains(response, "YouTube → Blog workspace")
