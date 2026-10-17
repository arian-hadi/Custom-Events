# Version 2 handoff and phased plan

11 October update: the automatic league now has a simple admin switch, automatic future-week scheduling and disclosed within-round starter scoring. See [automatic league delivery](AUTOMATIC_LEAGUE_UPDATE.md).

Current league scope (10 October 2026): open calendar-month leagues supported by weekly competitions. Annual competition is retired; historical records are preserved. See [the current league plan](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md).

## Current direction

Version 2 is a modular Django backend with a separate Next.js frontend. Keep business rules and authoritative records in Django's existing apps. Separate website sections do not introduce independently deployed microservices.

The immediate objective is to connect the supplied frontend design to existing backend capabilities, add manageable website content/blog authoring and complete account integration. Preserve existing data and behavior while replacing presentation incrementally. Discord remains a future workstream. League implementation has started; official scoring remains disabled pending completion and calibration. Member campaigns, Amazon automation and Stripe checkout are implemented with explicit configuration gates.

Use [COMMERCE_EMAIL_SETUP.md](COMMERCE_EMAIL_SETUP.md) for campaign/Amazon/Stripe credentials, migrations and worker commands.

Use [VERSION_2_API.md](VERSION_2_API.md) for endpoint contracts, permissions and the implemented/legacy/deferred feature map. Use [VERSION_2_SETUP.md](VERSION_2_SETUP.md) for the isolated preview, optional credentials and prepared deployment files.

The user-designated reference for the editing points structure and league work is
[EDITING_LEAGUE_IMPLEMENTATION_PLAN.md](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md).
Follow its implementation sequence and acceptance checks. Preserve its distinction
between confirmed requirements and proposed defaults; the unresolved defaults
are not automatically confirmed by adopting this reference.

## Architecture and working boundaries

- Working branch: `version-2.0`. The current checkout is a branch in the existing repository; no separate worktree is assumed. Do not merge the redesign into `master`, `staging` or `develop`, push release branches, or deploy production as part of ordinary V2 implementation.
- Frontend: `New_Frontend`, using reusable Next.js components adapted from the supplied design. Browser requests use the relative `/api/v2/` base.
- Repository integration: the frontend's original embedded Git history is preserved at `.local-v2/frontend-original-git`, allowing its source to be tracked by the parent repository. No changes have been staged, committed or pushed.
- Backend: `prime_project`, retaining existing account, shop, event, announcement, notification and editor models. New `platform_api` adds site settings/blog models and content endpoints; `accounts` owns authentication endpoints and Google identities.
- Authentication: Django sessions and CSRF on the same browser origin through a proxy. Google credentials remain server-side. Website account IDs come from authenticated sessions, never user-supplied request ownership fields.
- Notifications: the visible browser tab polls unread counts every 60 seconds and refreshes after reads. WebSockets are not required by the current implementation. Future instant updates can be evaluated separately from background email delivery.
- Administration: Django admin manages site settings, blog content, products and other existing records. Some profile and event-management functions still use their preserved Django pages.
- Background work: member campaigns and Amazon refresh have bounded management commands, persistent delivery/run records and retry handling. Admin alerts retain their immediate delivery and retry command. External schedules still require deployment configuration; no background scheduler starts inside web processes.
- Local isolation: `prime_project.settings_v2_local` uses `.local-v2/db.sqlite3`, `.local-v2/media` and `.local-v2/emails`, separate cookies and a separate secret. It does not import production settings or read `prime_project/.env`. Legacy ranking scheduling is disabled.
- Current runtime preference: non-Docker local preview. The user explicitly deferred further Docker setup, repair, builds and runtime testing. Prepared Compose/Docker files may be retained for later; do not resume Docker work without new authorization.

## Phase 1 — implemented integration

| Area | Implemented | Scope boundary |
| --- | --- | --- |
| Appearance/content | Admin-editable accent color, hero image/text, homepage sections/buttons, navigation/social links and footer; existing logo/favicon records | Existing supplied layout remains the design basis; visual acceptance still needs a browser review |
| Blog | Public lists/articles, categories as a post field, draft/published states, publication time, admin rich-text authoring | Existing announcements remain separate; no automatic conversion or email campaign |
| Shop | Existing catalog/favorites plus opt-in Stripe hosted checkout, private orders and curated Amazon Creators API refresh | Provider credentials and live testing remain; delivery is managed by staff; affiliate products remain external |
| Contact | Existing validation/honeypot, optional reCAPTCHA, rate limiting and truthful delivery results | Non-Docker preview captures mail to files; contact messages are not stored as separate database records |
| Accounts | Email registration/verification, login/logout, resend, password reset/change, username settings and optional Google sign-in/linking | Existing extended profile controls remain on legacy account pages; live Google consent flow needs credentials |
| Events | Listings/details, existing dynamic application fields, own application status/answers and safe POST withdrawal API | Organizer review and application editing retain existing dashboard routes |
| Notifications | Own records/unread count, read actions, channel/topic preferences, scheduled newsletters and automatic blog/shop campaigns with unsubscribe controls | Campaigns default disabled until configured; existing ranking/application/achievement member emails remain inactive |
| Admin email alerts | Owner-configurable recipients/categories, confirmed editor/edit submissions, removal requests, moderation reports and event applications; delivery log and retry command | Local mail capture only during validation; deployed SMTP and an automatic retry schedule still need operational configuration. See [admin email setup](ADMIN_EMAIL_ALERTS.md) |
| Editing Hub | League schema/migration, scoring/provider/service/API/frontend foundations exist | Full league acceptance, admin integration, provider setup and real pilot calibration remain unfinished; official scoring stays disabled |
| Existing sections | Legacy dashboard, account controls, editor functionality, announcements and legal/about pages remain available through deliberate route mapping | A preserved legacy page is not the same as a newly implemented Next.js screen |

Migrations in this work are additive: site settings, blog posts, Google identity, administrator/member email records, league tables, Stripe configurations/orders and Amazon source/run records. Existing users, products, applications, announcements, notifications and editing records retain their original tables. A fresh local database naturally starts empty; do not confuse that with deletion of production data.

## Phase 2 — complete local acceptance

1. Finish the integration review against the actual running local backend/frontend. Check authentication/token rotation, public/private routing, product favorites, event submission/status, notification preferences, contact capture and administrator-edited content.
2. When browser access is available, inspect desktop/mobile layouts and form behavior using the supplied design as the reference. Check error, loading and empty states, navigation, accessibility, images and theme changes. An HTTP response or successful build does not prove visual correctness.
3. Configure optional local Google credentials and exact redirect URLs, then exercise sign-in, explicit linking, existing-account collisions and provider cancellation. Configure paired reCAPTCHA keys only when testing the actual challenge experience.
4. Inventory any remaining existing behavior users need in Next.js. Preserve working legacy links until each native replacement is accepted. Avoid rebuilding deferred competition functionality just because legacy code exists.
5. Record verified results and remaining limitations in the final integration review. Fix current integration defects before adding another major feature stream.

Acceptance for this phase means a user can use the connected website features locally, administrators can edit the agreed content, permission boundaries hold, and captured test email is clearly distinguished from external email delivery.

## Phase 3 — future feature decisions

The following workstreams have separate implementation and launch boundaries:

- **Email campaigns:** implemented for opt-in newsletters and new blog/shop publications. Configure SMTP/sender, website origin, postal address and the worker schedule before enabling. Provider bounce/complaint ingestion and automatic ranking/application/achievement member emails remain future work.
- **Discord bot:** create a separate feature plan for the bot's commands and community tools. Later expose authenticated, permission-controlled backend operations to it; keep shared submission/scoring rules out of bot-only code. Discord account linking and role synchronization are not implemented now.
- **Leagues and points:** the [Editing league implementation plan](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md) now specifies automated social-metric scoring, older-edit eligibility with existing lifetime likes/views included, Monday–Friday score updates, frozen weekend results, accumulated monthly points and first-place-only weekly/monthly showcases. The foundation and missing schema migration now exist. Core/API acceptance, administrative workflows, provider integration, unresolved eligibility/defaults and real pilot calibration still need completion before official scoring. Legacy editor data remains intact.
- **Shop expansion:** Stripe hosted checkout and a verified payment/order ledger are implemented. Staff handle fulfillment. Carts, stock reservations, subscriptions, automatic delivery and refund/dispute synchronization remain future work.
- **Amazon automation:** curated ASIN refresh into the website is implemented using Creators API, with expiring prices/content and affiliate disclosure. Credentials, approved access, initial import and deployment scheduling remain. Discord/email resharing is not implemented.

These streams can receive separate plans and implementation tasks once their rules are agreed. Reuse the modular backend; revisit microservices only for a concrete deployment, scaling, ownership or isolation need.

## Phase 4 — preview deployment and production migration

This phase requires an explicit later release/deployment decision. Local development does not authorize a production cutover.

1. Resume and verify the isolated V2 deployment only when requested. Keep the current live release/staging paths usable for maintenance. A separate preview server/environment is preferable for a prolonged redesign.
2. Use separate database, media storage, secrets, email destinations and external integration credentials. Never point V2 migrations or scoring jobs at the live database during development.
3. Inventory existing users/identities, uploads, product URLs, event applications, announcements, rankings and notification settings. Rehearse using a sanitized production copy and document any intentional transformations.
4. Preserve identifiers and relationships. Define historical ranking treatment before introducing future league tables; do not overwrite old totals to prototype new scoring.
5. Rehearse the final migration against realistic data volume. Plan a backup and restore test, verification checks, maintenance/write-freeze needs and media handling.
6. Cut over from current production data, never from an old preview database. Decide how writes after launch are protected if rollback is needed; reverting Git alone does not revert schema or data changes.

## Verification status at handoff

| Check | Status and limit |
| --- | --- |
| Backend account/content tests | 53 combined tests passed under isolated SQLite settings at the latest review; includes CSRF, private ownership, visibility, validation, OTP/Google mocks and mail capture/failure cases |
| Current backend validation | The 85-test combined suite passed on 2026-09-20. Two subsequent focused cases also passed (real editor confirmation and manual interrupted-send recovery), bringing coverage to 87 tests: the previous 57 plus 30 admin-alert tests (17 lifecycle/integration, 13 delivery). Covers committed delivery, complete custom answers, duplicate prevention, rollback, permissions, category settings, retries and local file capture |
| Legacy dashboard entry | Fixed the missing-template error with an authenticated redirect to existing role-specific dashboards. Four focused tests passed, including anonymous login and staff/member role separation |
| Django system check | Passed under isolated settings |
| Project migration drift | Scoped project-app check passed; unscoped check reports the pre-existing third-party Summernote AutoField discrepancy |
| Source-level API/frontend review | Completed, including an independent account/OAuth review; identified contract and proxy issues were fixed |
| Frontend validation | Production build and TypeScript check passed. HTTP smoke check passed for 18 routes, 15 assets, seven public APIs, five protected endpoint denials, CSRF and redirect handling |
| Local HTTP integration | Passed through Next.js port 5173 to Django port 8000: login/session/CSRF rotation, catalog prices/sanitized content/media, favorites, published-versus-draft blog visibility, decimal event responses/duplicate rejection/withdrawal, notification reads/preferences, captured contact mail, admin-edited theme reflection and logout. Theme restored after validation; synthetic records retained only in `.local-v2` |
| Live account flows | 20 assertions passed through the frontend proxy: registration, PBKDF2 hashing, captured verification/reset emails, single-use verification/reset tokens, session/profile/preferences, privilege rejection, session invalidation, new-password login and logout. The disposable account was removed; external mail was not sent |
| Browser/visual verification | Pending; browser surfaces are currently unavailable in this session |
| Live Google/reCAPTCHA | Pending real local credentials/provider testing; mock tests are not live-provider evidence |
| Docker runtime | Explicitly deferred by the user; prepared configuration is not a verified deployment |
| Production migration/deployment | Not performed and outside this local phase |

Keep the final test record current when another task completes validation. Do not report deferred Docker work, visual QA or production migration as completed based on unit-test success.

## Remaining work, in priority order

1. **Local acceptance:** browser review of desktop/mobile pages and real user interactions, including administrator theme editing and the admin-alert settings/log screens. Automated HTTP and backend tests have passed; visual review remains open.
2. **Provider setup:** choose admin email recipients, configure a deployed SMTP service/sender and public review-link origin, and validate inbox delivery. Set up Google credentials and test its real consent flow if enabling it. Configure reCAPTCHA only if required.
3. **Operational delivery:** choose and configure a periodic `send_admin_alerts` run for automatic retries. Immediate successful admin sends already work; no new recurring worker has been deployed.
4. **Deployment validation:** resume Docker testing when explicitly requested, then create a separate V2 preview on Hetzner with isolated storage, HTTPS and secrets.
5. **Release preparation:** rehearse production-data migration, backups/restore, rollback, existing URL compatibility and the final production cutover. No production merge, push or deployment has been performed.
6. **League completion and later features:** finish league acceptance/calibration and administration separately; Discord/bot linking, automatic fulfillment, refund synchronization and broader member event emails remain future work. Campaigns, Stripe checkout and Amazon website refresh are implemented and await provider/deployment setup.

## Integration completion update — 2026-10-01

- Member campaigns: manual scheduling, automatic blog/shop discovery, explicit topic opt-ins, master opt-out, signed unsubscribe and delivery logs/retries are implemented. Amazon provider content is excluded from automated emails.
- Stripe: hosted checkout, server-owned price verification, signed webhook reconciliation, private order pages and staff fulfillment controls are implemented. Protected account deletion now gives a support path instead of failing.
- Amazon: curated Creators API refresh, per-source/run locks, failure backoff, freshness limits, public catalog/favorites integration and frontend expiry handling are implemented.
- Applied locally: league `0025`, notifications `0003`, shop `0010`–`0012`. Project-app migration drift and unapplied-local-migration checks pass. No production database was used.
- Final combined backend suite: **197 tests passed**, including 29 campaign, 33 payment, 24 Amazon and four protected-account-deletion tests, plus the existing account/content/admin-alert/provider suites. Provider calls are mocked.
- Frontend TypeScript check and production build passed; four commerce tests and five league-display tests passed. Browser UI acceptance remains pending: no browser surface was available on the final attempt.
- Local integration: **38 HTTP assertions passed** through the running Next.js proxy, covering login/CSRF, persisted campaign preferences (restored afterward), private orders and payment states, disabled checkout without an order, frontend page responses and authenticated campaign admin pages. This does not verify browser hydration or visual layout. Synthetic fixture records remain only in `.local-v2`.
- Independent review fixes include preference saving controls, checkout retry keys across reloads, explicit expired-attempt recovery, stale-order clearing and Amazon expiry in open/suspended tabs.
- All provider feature switches remain off by default. No external campaign, live provider import, charge, deployment, commit or push was performed. Follow [COMMERCE_EMAIL_SETUP.md](COMMERCE_EMAIL_SETUP.md) for setup.
