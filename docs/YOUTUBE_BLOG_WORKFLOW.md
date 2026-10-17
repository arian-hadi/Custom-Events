# Admin refresh and YouTube → Blog workflow

The Django admin keeps existing model permissions, actions and rich-text editors, with a new dark/red control-center design. No third-party admin theme or new AI subscription is required.

## Start here

1. Open `/admin/` and choose **YouTube channels** under Website content.
2. Add your channel's name and `https://www.youtube.com/@yourhandle` URL. Save.
3. Click **Check latest video now**. This considers just the newest regular video, creating a preparation item only if it is new. It never publishes a post.
4. Open **YouTube → Blog workspace** and choose a video.
5. Paste its script or upload a UTF-8 `.txt`, `.md`, `.srt` or `.vtt` file. Save. If owner-authorized captions are configured, **Fetch captions from YouTube** is another option.
6. **Download AI brief (.md)**. Give the downloaded file to your own AI. It includes the full saved script, video details, your writing instructions and the exact return format.
7. Choose **Import Markdown**, upload the AI's returned `.md` file, then **Preview article**.
8. Choose **Import as draft**. The normal Blog post editor opens with formatted, editable content. Add a cover image and review the article before changing its status to Published.

There is no built-in AI text-generation call. Nothing is automatically sent to an AI provider. The creator decides which AI to give the downloaded file to.

## Delete items from an admin list

Select individual row checkboxes, or use the header checkbox for the current page. For a list spanning multiple pages, choose Django's **Select all …** link to include every result matching the current filters. Click **Delete selected**, review the affected objects, and confirm. The existing Action dropdown works without JavaScript. Staff must have the model's delete permission.

Blog posts (including Markdown-imported posts) and YouTube workspace items support this flow. Removing a workspace item keeps its blog post; removing a blog post keeps its source item. Import history retains the original Markdown and author/time, with deleted-object links cleared. Deleted YouTube IDs and titles are remembered so automatic checks do not recreate them or notify again; explicit **Add an older video** imports can restore them. Remove a channel's workspace items before deleting the channel itself.

The shortcut appears throughout admin wherever deletion is permitted. Existing restrictions remain for payment records, finalized league records, audit logs and singleton settings. No general permission bypass or permanent-history purge is introduced.

Migration `platform_api.0005` enables these changes and has been applied to the local V2 database. Bulk-action tests cover confirmation, filtered select-all, permissions/CSRF, related-record preservation, deletion logs and scheduled-discovery suppression.

## Automatic checks and email

On the channel, enable **Automatic checks** and choose a check interval (minimum 15 minutes). The Docker `jobs-youtube-blog` worker checks for due channels every 300 seconds by default. Keep one worker; don't also schedule the same job on the host.

- Each check, including the first and the manual **Check latest video now** button, considers **one video only**: the first regular video in the channel's **Videos → Latest** tab. Shorts are excluded, with no automatic backlog import or pagination.
- If that video's ID is already stored, or its title matches a stored title in the same channel's workspace, the check skips it. It does **not** move on to an older video. Title matching ignores capitalization, repeated whitespace and Unicode compatibility differences. It does not use fuzzy similarity.
- If several videos were uploaded between checks, only the newest is considered. To prepare another one, use **Add an older video** on the channel. This explicit URL import still works for older content (and intentionally selected Shorts); its URL must belong to that channel. The same duplicate rules apply.
- When enabled, new-video emails go to **Admin email settings → Recipients** (or the existing environment/superuser fallback). Both that settings page's **New YouTube videos for the blog** switch and the channel's **Notify admins** switch are respected.
- Email uses the existing branded admin-email outbox and retry worker. Only a newly created preparation item queues an alert. Duplicate IDs/titles do not queue a new alert. Per-channel database locking serializes manual and scheduled imports, while the unique video ID also prevents cross-channel ID duplicates.
- New preparation items remain visible in the admin workspace even if email fails or is disabled. Email status is in **Admin email deliveries**.
- If **Fetch captions** is enabled, a check attempts/retries missing captions only for the exact latest video, provided it has no script or imported article. A matching title belonging to a different video ID is skipped entirely. Older items use their individual **Fetch captions from YouTube** action. Missing captions and permission/quota failures appear on the affected video; no transcript is invented. Manual scripts are preserved.
- Turning off automatic checks stops scheduled discovery. Manual checks remain available.
- SMTP cannot guarantee exactly-once delivery if a process fails after provider acceptance; existing explicit interrupted-delivery retry controls still apply.

Existing preparation items, scripts, imported articles and previously queued emails are preserved. This change does not remove earlier Shorts or backlog items.

### How regular videos are selected

The public Data API's uploads playlist contains both Shorts and regular videos and has no documented `isShort` field. Duration alone would incorrectly exclude short landscape videos. Discovery therefore reads one bounded public **Videos** page, verifies the channel identity, selected Videos tab and Latest sorting, and takes its first video. The official Data API then verifies that video's public metadata and owning channel. Upcoming premieres/live broadcasts are not imported by the scheduled check.

The public page schema is not a supported API contract. If YouTube changes it, blocks access, redirects to consent, or returns an unrecognized layout, the check records an admin error and imports nothing; it never falls back to the mixed uploads feed. Manual URL import remains available. No cookies, media downloads, private browser sessions or extra credentials are used for the tab lookup.

## Configuration

**Discovery:** reuse `YOUTUBE_API_KEY` in `.env.v2`, with YouTube Data API v3 enabled. It is the existing key used for editor-channel lookup. No extra key is needed for manually pasting scripts after discovery.

**Optional automatic caption retrieval:** an API key alone does not grant caption-download permission. YouTube requires OAuth authorization from an account that can edit the video, with `https://www.googleapis.com/auth/youtube.force-ssl` scope. A Google login connection on the member website does not grant that permission.

1. Create/use your own Google OAuth client and authorize the channel owner for the above scope with offline access. Obtain a refresh token using your own client. The Google OAuth Playground can be used with **Use your own OAuth credentials** enabled; its redirect URI must be configured on that client. Keep this separate from member-login permissions.
2. Save this private file at `.local-v2/secrets/youtube-blog.json` (that directory is ignored by Git and mounted read-only by Compose):

```json
{
  "client_id": "YOUR_GOOGLE_OAUTH_CLIENT_ID",
  "client_secret": "YOUR_GOOGLE_OAUTH_CLIENT_SECRET",
  "refresh_token": "YOUR_CHANNEL_OWNER_REFRESH_TOKEN"
}
```

3. In `.env.v2` set:

```dotenv
YOUTUBE_BLOG_CREDENTIALS_FILE=/run/v2-secrets/youtube-blog.json
V2_YOUTUBE_BLOG_INTERVAL_SECONDS=300
```

4. Recreate the backend and new worker after changing environment values:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml up -d --no-deps backend jobs-youtube-blog
```

Credential refresh/revocation errors are shown as actionable messages. Tokens are not stored in the database or exported in Markdown. If Google OAuth consent is in testing, tokens may expire; configure the Google project appropriately for ongoing use. Until OAuth is ready, upload or paste your original script.

Official references: [channels list](https://developers.google.com/youtube/v3/docs/channels/list), [video resource fields](https://developers.google.com/youtube/v3/docs/videos), [YouTube Shorts classification](https://support.google.com/youtube/answer/15424877?hl=en), [caption download authorization](https://developers.google.com/youtube/v3/docs/captions/download), [OAuth Playground](https://developers.google.com/oauthplayground/).

For the isolated non-Docker settings file, use `V2_LOCAL_YOUTUBE_API_KEY` and `V2_LOCAL_YOUTUBE_BLOG_CREDENTIALS_FILE` with an absolute host file path in `.env.v2.local`.

## Commands and migrations

New migrations are `platform_api.0003`, `platform_api.0004` and `notifications.0006`. Normal initialization applies them. To apply only these additions to an already-running local V2 stack:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend python manage.py migrate notifications 0006
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend python manage.py migrate platform_api 0004
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml up -d --no-deps jobs-youtube-blog
```

Non-Docker: use your configured settings and database, run `python manage.py migrate`, then `python v2_worker.py youtube-blog` alongside the existing web/email processes. `python manage.py youtube_blog_tick --channel 1` performs one manual check for channel #1; omit `--channel` to check only due automatic channels.

Development serves the new admin assets live. Built/non-development installations need their normal backend rebuild/collectstatic step.

## Markdown contract and data integrity

The returned file must contain exactly these four YAML text fields, followed by Markdown. Use the real ID supplied in the downloaded brief:

```markdown
---
title: "Article title"
excerpt: "A short summary"
category: "Transformers"
source_video_id: "AbcDefGh_12"
---

## Section heading

Article paragraphs, lists and links.
```

- UTF-8 input is limited to 1 MB. YAML aliases/tags, extra metadata and mismatched source IDs are rejected.
- Markdown becomes sanitized HTML using the existing website sanitizer. Imported HTML cannot execute scripts.
- Imports always create/update **drafts**. An existing published article cannot be replaced through this workflow.
- Original Markdown, importer and time are retained in read-only **Blog Markdown import history**. A retry of the latest identical import does not overwrite later manual editor changes.
- Saved transcripts and existing blog posts are not overwritten by discovery. A revised Markdown import updates the associated draft with an additional audit record.
- Channel configuration and manual discovery require a superuser. Editorial staff need view/change permissions for YouTube videos, plus add/change Blog post permissions to import. Model permissions apply to downloads and custom admin endpoints; mutations require POST with CSRF protection.
- Existing blog articles, competition results, users and other unrelated content are preserved.

## Verification

Focused tests cover discovery deduplication, schedules/leases, caption failures, existing-script preservation, source ownership, admin permissions/CSRF, Markdown import/preview, sanitization, repeat imports, published-post protection and HTML admin-email delivery. Provider tests use mocked responses and do not contact Google or send external email.

The latest-only update adds coverage for current/previous Videos-tab layouts, Shorts exclusion, explicit Latest sorting, bounded requests, consent/schema failures, no backlog fallback, matching-title duplicates, interval handling, latest-only caption retries and manual older-video imports. All 80 selected provider/workflow/admin/alert tests passed on 15 October 2026, with no platform_api model migration changes. A read-only live lookup of the configured creator's public Videos tab selected its newest regular upload; this probe created no database records or emails. The local backend and YouTube worker reported healthy. This update requires no additional environment variables or database migrations.

Original admin/workflow verification completed 15 October 2026: 78 focused backend tests passed; the worker suite passed 14 tests with one Linux-only test skipped on Windows. Desktop and mobile browser checks confirmed the grouped admin, module search, Markdown preview → draft import and responsive rich-text editor. These UI checks used a separate disposable database. The local V2 database has the three migrations above applied. No external email was sent during verification. Live caption access remains dependent on the owner's credentials.
