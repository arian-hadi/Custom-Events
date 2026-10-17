# V2 integration status — 8 October 2026

18 October staging preparation: independent V2 staging Compose/settings, a guarded release preparation workflow, database/media preservation manifests, and staging compatibility fixes are prepared locally. Existing staging and production have not been deployed or migrated. See [the staging migration runbook](V2_STAGING_MIGRATION.md) for the branch workflow, configuration and remaining server checks.

15 October admin list update: shared **Delete selected** shortcut and selection guidance on deletable lists. Enabled YouTube workspace/channel deletion, allowed imported blog deletion while retaining Markdown audit history, and suppressed rediscovery of explicitly removed YouTube items. Local migration `platform_api.0005` applied; 71 focused tests passed. Existing protected history/payment/settings restrictions remain.

15 October YouTube discovery update: checks now consider only the newest regular video in the channel's Videos → Latest tab, excluding Shorts. Stored video IDs or matching titles are skipped without importing older uploads or queuing another alert. The configured interval and manual URL imports remain available. Existing workspace records are preserved; no additional settings or migrations are required. See the workflow guide for the public-tab parser's failure handling.

14 October editorial update: refreshed Django admin with grouped modules and quick actions; YouTube channel discovery (manual or scheduled), deduplicated admin email alerts, script/subtitle input, optional owner-authorized captions, AI Markdown brief downloads and validated Markdown-to-draft import. Existing blog editing and publication remain in Django admin. See [YouTube → Blog setup and workflow](YOUTUBE_BLOG_WORKFLOW.md). Automatic discovery is opt-in per channel; no AI provider is called by this workflow.

11 October update: the automatic league now has a simple admin switch, automatic future-week scheduling and disclosed within-round starter scoring. See [automatic league delivery](AUTOMATIC_LEAGUE_UPDATE.md).

Current league scope (10 October 2026): open calendar-month leagues supported by weekly competitions. Annual competition is retired; historical records are preserved. See [the current league plan](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md).

This records the requested order: editing league (step 2), remaining member pages (step 1), then member activity emails (step 3). Work is on `version-2.0`.

## Editing league

Implemented league administration, version readiness checks, UTC round scheduling, frozen baselines/results, audited corrections/cancellation, monthly point aggregation, and read-only audit records. Intake and history collection respect the configured platform/format scope. Provider polling and bounded comparison-history harvesting run in the existing league worker. Pilot calibration tooling builds a reviewable draft from selected provider observations and retains the evidence IDs.

`LEAGUE_ENABLED` remains `False` in the local environment. Real provider access, reviewed pilot calibration and scheduled rounds are still needed before opening official entries. No fake calibration, points or winners were added to the running database. TikTok authorization is supplied per editor through a server credentials file; a member-facing TikTok OAuth connection/refresh screen is not implemented.

See [league operations](LEAGUE_OPERATIONS.md) and [provider setup](LEAGUE_PROVIDER_SETUP.md).

## Member pages

- `/account/profile`: validated image upload/removal, account/channel display, explicit approved channel choice, existing unlocked editor titles, and account removal with identity confirmation and protected-record handling.
- `/applications/events/<id>`: private application detail and editing of pending applications while the event is active and before its deadline. Supports existing dynamic fields, including false/zero answers.
- `/account/edits` and `/account/edits/<id>`: earlier edit history, original media links, and permitted editing/confirmation/withdrawal before its deadline. Historical locked entries remain viewable. These pages do not show legacy follower ranks or calculated scores as V2 league results.
- Dashboard, application and notification links use V2 destinations. Relevant old GET bookmarks redirect to V2; old backend POSTs and Django administration remain server-owned.
- Existing username/password/Google settings remain under `/account/settings`. Optional email controls remain under `/account/preferences`.

These pages reuse the existing V2 dark/red styles and responsive account navigation.

## Member activity emails

Implemented a durable, deduplicated outbox for editor/event application decisions, edit verification/rejection, editor titles, official league results, standings and awards. League events are recorded with result revisions, processed after commit, and recoverable by the worker. Corrections cancel pending superseded messages. Legacy follower-ranking emails are suppressed on V2.

The existing `jobs-email` service sends activity mail separately from marketing campaigns. It rechecks account state, destination address and the member's master/topic preferences before sending. Signed unsubscribe links turn off optional member email; security mail and receipts remain separate. Failures have bounded retries, safe error summaries and admin recovery actions; ambiguous interrupted SMTP sends require explicit admin requeue because delivery may already have occurred.

Local `.env.v2` now includes `MEMBER_ACTIVITY_EMAIL_ENABLED=True`, using the existing Gmail SMTP settings. This is for future activity; the notification history was not backfilled. Example env files keep the switch off by default. Native local mode uses `V2_LOCAL_MEMBER_ACTIVITY_EMAIL_ENABLED`. Marketing campaign enablement remains independent.

## Database and verification

Applied to the confirmed local `platform_v2` PostgreSQL database:

- `edithub.0026_leaguehistorysync`
- `notifications.0004_member_activity_email`

The legacy database was not changed. Verification completed:

- Relevant backend acceptance suite: 370 tests run, passing with one platform-specific skip.
- Frontend TypeScript check and all 48 frontend tests passed.
- Project-app migration check found no pending model changes.
- The local Docker backend, frontend, database and scheduled workers are running; services with health checks report healthy.
- Desktop/mobile fixture checks cover profile saving, dynamic event application editing and locked historical edits without modifying real accounts.
- Live checks through `http://localhost:8082` passed for profile, preferences, earlier edits and an existing event application at desktop and mobile sizes. No page errors or horizontal overflow were found. Private member APIs returned successfully, activity email enablement was confirmed, and relevant old bookmarks redirected to V2.

The live checks signed in to the existing demo account but created no applications, profile changes or emails. Live SMTP delivery and live social-provider access remain untested.

The repository has an existing third-party `django_summernote` attachment ID migration drift when running an unrestricted `makemigrations --check`. Project-app migration checks should be scoped to `accounts edithub notifications platform_api events shop`; no dependency files were rewritten for that unrelated drift.
