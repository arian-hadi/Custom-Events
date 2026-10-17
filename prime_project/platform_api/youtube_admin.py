from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from notifications.admin import SuperuserOnlyAdmin
from .blog_markdown import ai_brief, import_article, parse_article, read_text_upload
from .models import YouTubeBlogChannel, YouTubeBlogVideo, BlogMarkdownImport
from .youtube_blog import sync_channel, prepare_captions, add_video, delete_workspace_videos
from .youtube_source import ProviderError, normalize_transcript


class ChannelForm(forms.ModelForm):
    class Meta:
        model = YouTubeBlogChannel
        fields = "__all__"

    def clean_channel_url(self):
        from urllib.parse import urlsplit
        import re
        value = self.cleaned_data["channel_url"]
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}
                or parsed.username or parsed.password or parsed.port not in {None, 443}
                or not re.fullmatch(r"/(?:@[^/\s?#]+|channel/UC[\w-]{22}|user/[\w.-]+)(?:/videos)?/?", parsed.path)):
            raise forms.ValidationError("Use a YouTube HTTPS /@handle, /channel/UC… or /user/name URL.")
        value = value.rstrip("/").removesuffix("/videos")
        if self.instance.pk and value != self.instance.channel_url.rstrip("/").removesuffix("/videos") and self.instance.videos.exists():
            raise forms.ValidationError("This channel already has videos. Add a separate channel instead of changing its source URL.")
        return value


@admin.register(YouTubeBlogChannel)
class YouTubeBlogChannelAdmin(SuperuserOnlyAdmin):
    form = ChannelForm
    change_form_template = "admin/platform_api/youtube_channel.html"
    list_display = ("name", "automatic_checks", "fetch_captions", "notify_admins", "last_checked_at", "last_error")
    readonly_fields = ("channel_id", "uploads_playlist_id", "last_checked_at", "next_check_at", "last_error")
    fieldsets = (
        ("Your channel", {"fields": ("name", "channel_url"), "description": "Each check considers only the newest video from the channel's Videos tab. Shorts are excluded. An existing video ID or matching title is skipped; older uploads are never added automatically."}),
        ("Automation", {"fields": ("automatic_checks", "check_interval_minutes", "notify_admins", "fetch_captions", "language"), "description": "New videos create preparation items, not published posts. Caption downloads require owner OAuth credentials; pasting or uploading a script also works."}),
        ("AI writing brief", {"fields": ("writing_instructions",)}),
        ("Latest check", {"fields": ("last_checked_at", "next_check_at", "last_error", "channel_id", "uploads_playlist_id")}),
    )

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def get_urls(self):
        return [path("<int:object_id>/check/", self.admin_site.admin_view(self.check_view), name="youtube_channel_check"),
                path("<int:object_id>/add-video/", self.admin_site.admin_view(self.add_video_view), name="youtube_channel_add_video")] + super().get_urls()

    def channel_object(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404()
        if not self.has_change_permission(request, obj):
            raise PermissionDenied()
        return obj

    def check_view(self, request, object_id):
        obj = self.channel_object(request, object_id)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        try:
            result = sync_channel(obj.pk, force=True)
            if result["skipped"]:
                text = "A check is already running."
            elif result["created"]:
                text = "The latest video was added. Open YouTube → Blog workspace to prepare it."
            elif result["outcome"] == "existing":
                text = "The latest video or its title is already in this channel's workspace. Nothing was added and no new notification was queued."
            elif result["outcome"] == "removed":
                text = "The latest video was previously deleted from the workspace. It was skipped. Use Add an older video to import it again intentionally."
            else:
                text = "No published video was found in the channel's latest Videos list. Nothing was added."
            if result["caption_errors"]:
                text += " Some captions could not be retrieved; see each video's message or upload your script."
            self.message_user(request, text, messages.SUCCESS)
            self.log_change(request, obj, "Manually checked channel for videos.")
        except ProviderError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return redirect("admin:platform_api_youtubeblogchannel_change", object_id)

    def add_video_view(self, request, object_id):
        obj = self.channel_object(request, object_id)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        try:
            video, created = add_video(obj, request.POST.get("video_url", ""))
            self.log_change(request, obj, f"Added video {video.video_id} to blog workspace.")
            self.message_user(request, "Video added." if created else "A video with this ID or title is already in the workspace. Opening the existing item.")
            return redirect("admin:platform_api_youtubeblogvideo_change", video.pk)
        except ProviderError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return redirect("admin:platform_api_youtubeblogchannel_change", object_id)


class VideoForm(forms.ModelForm):
    script_file = forms.FileField(required=False, label="Upload script or subtitles", help_text="Optional UTF-8 .txt, .md, .srt or .vtt file, up to 1 MB. Upload replaces the script field.")

    class Meta:
        model = YouTubeBlogVideo
        fields = "__all__"

    def clean(self):
        data = super().clean()
        upload = data.get("script_file")
        try:
            if upload:
                if not upload.name.lower().endswith((".txt", ".md", ".srt", ".vtt")):
                    raise ValidationError("Choose a .txt, .md, .srt or .vtt file.")
                data["transcript"] = normalize_transcript(read_text_upload(upload))
            elif "transcript" in self.changed_data:
                data["transcript"] = normalize_transcript(data.get("transcript", "")) if data.get("transcript", "").strip() else ""
        except (ValidationError, ProviderError) as exc:
            raise forms.ValidationError(str(exc)) from exc
        return data


class ArticleForm(forms.Form):
    markdown_file = forms.FileField(required=False, label="AI-written Markdown file")
    markdown_text = forms.CharField(required=False, label="Or paste Markdown", widget=forms.Textarea(attrs={"rows": 18, "cols": 90}))

    def clean(self):
        data = super().clean()
        if data.get("markdown_file") and data.get("markdown_text", "").strip():
            raise forms.ValidationError("Choose a file or paste the text, rather than both.")
        if data.get("markdown_file"):
            if not data["markdown_file"].name.lower().endswith(".md"):
                raise forms.ValidationError("Upload a UTF-8 .md file.")
            data["markdown_text"] = read_text_upload(data["markdown_file"])
        if not data.get("markdown_text", "").strip():
            raise forms.ValidationError("Choose or paste your completed Markdown document.")
        return data


@admin.register(YouTubeBlogVideo)
class YouTubeBlogVideoAdmin(admin.ModelAdmin):
    form = VideoForm
    change_form_template = "admin/platform_api/youtube_video.html"
    list_display = ("title", "channel", "preparation_status", "published_at", "article_link")
    list_filter = ("channel", "blog_post__status", "transcript_source")
    search_fields = ("title", "video_id", "description")
    list_select_related = ("channel", "blog_post")
    readonly_fields = ("channel", "video_id", "title", "description", "published_at", "watch_link", "transcript_source", "transcript_error", "caption_checked_at", "preparation_status", "article_link", "discovered_at")
    fieldsets = (
        ("1 · Source video", {"fields": ("title", "channel", "watch_link", "published_at", "description", "preparation_status")}),
        ("2 · Prepare the script", {"fields": ("transcript", "script_file", "transcript_source", "transcript_error", "caption_checked_at", "instructions"), "description": "Save your script before downloading the AI brief. Your original source stays here after importing an article."}),
        ("3 · Blog draft", {"fields": ("article_link",), "description": "Download the AI brief above, give it to your AI, then use Import Markdown. Review the preview and create your draft."}),
    )

    def has_add_permission(self, request):
        return False

    def delete_queryset(self, request, queryset):
        delete_workspace_videos(queryset)

    def delete_model(self, request, obj):
        delete_workspace_videos(YouTubeBlogVideo.objects.filter(pk=obj.pk))

    @admin.display(description="Video")
    def watch_link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">Watch on YouTube ↗</a>', obj.video_url)

    @admin.display(description="Blog article")
    def article_link(self, obj):
        if obj.blog_post_id:
            return format_html('<a href="{}">Edit blog article</a>', reverse("admin:platform_api_blogpost_change", args=[obj.blog_post_id]))
        return "No draft imported yet"

    def save_model(self, request, obj, form, change):
        if "transcript" in form.changed_data or form.cleaned_data.get("script_file"):
            obj.transcript_source, obj.transcript_error = "Administrator script", ""
        super().save_model(request, obj, form, change)

    def get_urls(self):
        return [path("<int:object_id>/brief/", self.admin_site.admin_view(self.brief), name="youtube_video_brief"),
                path("<int:object_id>/captions/", self.admin_site.admin_view(self.captions), name="youtube_video_captions"),
                path("<int:object_id>/import/", self.admin_site.admin_view(self.import_view), name="youtube_video_import")] + super().get_urls()

    def video_object(self, request, object_id, *, change=False):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404()
        allowed = self.has_change_permission(request, obj) if change else self.has_view_permission(request, obj)
        if not allowed:
            raise PermissionDenied()
        return obj

    def brief(self, request, object_id):
        obj = self.video_object(request, object_id)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        try:
            response = HttpResponse(ai_brief(obj), content_type="text/markdown; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="youtube-{obj.video_id}-ai-brief.md"'
            return response
        except ValidationError as exc:
            self.message_user(request, "; ".join(exc.messages), messages.ERROR)
            return redirect("admin:platform_api_youtubeblogvideo_change", object_id)

    def captions(self, request, object_id):
        obj = self.video_object(request, object_id, change=True)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        try:
            changed = prepare_captions(obj)
            self.message_user(request, "Captions retrieved. You can now download the AI brief." if changed else "An existing script was preserved. Clear and save it first if you want to replace it with captions.")
            if changed:
                self.log_change(request, obj, "Retrieved YouTube captions.")
        except ProviderError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return redirect("admin:platform_api_youtubeblogvideo_change", object_id)

    def import_view(self, request, object_id):
        obj = self.video_object(request, object_id, change=True)
        if not request.user.has_perms(("platform_api.add_blogpost", "platform_api.change_blogpost")):
            raise PermissionDenied()
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        form = ArticleForm(request.POST or None, request.FILES or None)
        preview = None
        if request.method == "POST" and form.is_valid():
            text = form.cleaned_data["markdown_text"]
            try:
                preview = parse_article(text, obj)
                if request.POST.get("action") == "import":
                    post = import_article(obj.pk, text, request.user)
                    self.log_change(request, obj, f"Imported Markdown into draft #{post.pk}.")
                    self.message_user(request, "Markdown imported as a draft. Review and edit below; publish only when ready.", messages.SUCCESS)
                    return redirect("admin:platform_api_blogpost_change", post.pk)
                form = ArticleForm(initial={"markdown_text": text})
            except ValidationError as exc:
                form.add_error(None, exc)
        context = {**self.admin_site.each_context(request), "opts": self.model._meta, "original": obj,
                   "title": f"Import Markdown · {obj.title}", "form": form, "preview": preview}
        return TemplateResponse(request, "admin/platform_api/youtube_import.html", context)


@admin.register(BlogMarkdownImport)
class BlogMarkdownImportAdmin(admin.ModelAdmin):
    list_display = ("video", "post", "imported_by", "created_at")
    readonly_fields = tuple(field.name for field in BlogMarkdownImport._meta.fields)
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
