# V2 staging data and compatibility audit

Audit updated: 2026-10-18. Compared local `version-2.0` HEAD `1f4c657`, its V2 working tree, and fetched `origin/staging` `aa2f9c3`. This is a source audit and isolated test result, not proof that a remote database has been backed up or migrated. No production deployment or source-database modification was performed for this audit. Start with [the migration runbook](V2_STAGING_MIGRATION.md).

## Preservation conclusion

The V2 migration set preserves legacy tables and primary keys. There are 22 migrations absent from the staging tree, creating 33 models and extending existing notification preferences. No new migration removes a legacy table, removes a legacy field, runs raw SQL, or deletes legacy rows. This permits a complete V1 logical database restore followed by V2 migrations; it does not justify recreating the database from selected model exports.

The working tree contains substantial uncommitted/untracked V2 implementation. Deploying the current branch commit alone omits that implementation. Capture and review the intended source files, migrations, frontend and deployment files before producing a deployable revision; exclude credentials, local database copies, media backups and caches. Retain the staging branch's independent fixes during reconciliation.

| Data | Source evidence | Expected preservation / behavior |
| --- | --- | --- |
| Accounts, authentication, roles and profiles | `accounts/models.py`; `accounts/migrations/0016_googleidentity.py` | Existing user schema, password hashes, flags, titles and profile image paths remain. Google identity is an additional table; existing users are not automatically linked to provider subjects. Keep groups and permission join tables in the full database restore. |
| Editor applications and channel verification | `edithub/models.py`; `accounts/models.py:get_profile_application` | IDs, statuses, channel links, selected titles and follower counts remain. V2 display identity requires an explicitly selected, accepted, verified channel. A historical account without that choice may display its username while all channel rows remain stored. Review these cases rather than rewriting approvals. |
| Legacy edit history and top-three winners | `edithub/models.py:EditSubmission`, `WeekWinner`, `UserTitleUnlock`; `edithub/admin.py` | All historical submissions, points, upvotes, reports, tournament records and winner rows remain. Admin registration remains. V2 member views expose earlier submission counts and a latest historical edit. |
| V2 league | `edithub/league_models.py`; `platform_api/league_views.py:standings,winners`; `edithub/league/services.py:aggregate_standings` | Uses separate entry/result/award tables. No migration converts legacy winner or calculated-point rows to monthly points. Preserve legacy top-three records as historical awards, with their original week and place. Do not manufacture V2 rounds, monthly awards or league points from them. |
| Shop products, favourites, logos and images | `shop/models.py`; `shop/migrations/0010_stripe_checkout.py` | Existing product and favourite rows remain. Stripe orders/configuration/receipts are new tables; a V1 database has no native Stripe payment orders to migrate. Restore all tables if the source already contains V2 orders. Payment orders protect their referenced users/products. Orders held only by an external shop are not imported by these migrations. |
| Events and applications | Unchanged `events/models.py` and migrations; `platform_api/activity_views.py` | Events, applications, custom fields and typed responses remain in their original tables and are reused by V2. No event data migration exists. |
| Notifications | `notifications/migrations/0003*` through `0006*` | Existing notification and preference rows remain. Three new marketing topic preferences default false. Changing the model default of existing `email_enabled` to true does not reset existing stored preferences. Added delivery/campaign tables are independent. |
| Media | `prime_project/settings.py:MEDIA_ROOT`; both Compose files; `deploy/v2/nginx.conf` | Database image/file fields contain relative names, not file bytes. Copy the complete source media volume to a separate target media volume, preserving relative paths. Include avatars, product images, editor verification uploads, event/editor assets and rich-text uploads. Rebuild static assets separately. |

### Visibility is separate from retention

The new league `winners` endpoint reads `WeeklyResult` and `MonthlyAward`, not `WeekWinner`. The new all-time leaderboard also aggregates only V2 points. Legacy winners therefore survive storage without appearing in the V2 league podium. Keep an accessible historical archive or explicit legacy route if V2 must display those awards; label their original period and rank and keep them separate from V2 monthly points. Legacy routes remain mounted under `/editinghub/`, with the gateway forwarding that path to Django. A dedicated archive should read stored historical rows without invoking legacy rescoring.

The new profile API lists existing title grants. If historical points qualify a user for a title whose grant was never materialized, an achievement refresh is needed before listing the title. The staging legacy endpoint fix below performs that refresh. Ensure the V2 profile path also covers this case or perform a recorded, intentional grant reconciliation on the copied database.

## Migration inventory and mutating steps

| App / new migrations | Operations |
| --- | --- |
| `accounts 0016` | Create `GoogleIdentity`; no existing-account backfill. |
| `edithub 0025` | Create 11 league models, related fields, indexes and constraints. Legacy score signals remain attached to legacy classes. |
| `edithub 0026–0027` | Create `LeagueHistorySync`, `LeagueSettings` and singleton constraint. No seed enables the league. |
| `edithub 0028` | Add nullable `CompetitionEntry.competition_month`; RunPython sets it to the first day of each related round's scoring month; require non-null; replace global active-video/edit uniqueness with monthly uniqueness. It updates V2 entry scope only, including withdrawn entries, and leaves snapshots/results/awards untouched. The reverse data function is a no-op. |
| `edithub 0029` | Add debut/history-reference fields; update league-setting defaults/labels. Existing stored weights are not rewritten to the new defaults. |
| `notifications 0002–0006` | Create admin email settings/outbox, member campaign/settings/delivery, member activity delivery and league notification event models. Add notification event key/topic preferences and extend choice lists. No RunPython. |
| `platform_api 0001–0006` | Create site settings, blog posts, YouTube channels/videos/imports/suppressions; add display and caption fields. Migration 0005 changes import references to nullable `SET_NULL`, preserving import audit rows on later related-content deletion. No RunPython. |
| `shop 0010–0013` | Create payment/configuration/receipt, Amazon source/sync-run and featured-request models; add worker heartbeat and uniqueness constraints. |
| `shop 0014` | RunPython creates two active placeholder request cards with purchasing disabled. This is the only new seed migration; reverse is a no-op to retain edited cards. Reapplying after manually altering migration history can duplicate them. |

There are exactly two new RunPython operations: `assign_competition_month` and `seed_requests`. No new `RunSQL`, `DeleteModel` or `RemoveField` operation was found. The two `RemoveConstraint` operations affect only V2 league identities.

Historical migrations already present in staging are a separate concern: `accounts 0010` removes first/last-name fields; `edithub 0008` removes old submission fields; `edithub 0004` maps legacy editing tools; `edithub 0011` populates scheduled weeks. Check the copied `django_migrations` ledger against the source before running migrations. If any old destructive step is genuinely pending, review its affected source columns and preserve their values separately first. Do not delete the ledger, fake initial migrations, or reverse migrations to reconcile the branches.

For a previously used V2 source, validate `0028` constraints and `0012_amazon_worker_lock` uniqueness before migrating. Preserve a pre-migration dump even when the nominal migration plan is additive; database constraints and PostgreSQL behavior still need a rehearsal on the real data copy.

## Copied database activity controls

The local `compose.v2.yml` starts five worker services by default. The separate `compose.v2.staging.yml` profile-gates all workers and migrations. `v2_initialize.py` runs migrations and collectstatic; migration `shop 0014` seeds two placeholder cards, and the initializer docstring now makes data migration steps explicit. Start only the database and required one-shot maintenance services for the initial restore/verification.

| Entry point | Concrete behavior | Rehearsal control |
| --- | --- | --- |
| Legacy Django startup | `edithub/apps.py` starts legacy rescoring and immediately calls `update_edit_points` unless `ENABLE_EDITHUB_SCHEDULER=False`. | Set false in every web/management process. |
| League worker | `v2_worker.py` consults `league_enabled`; `edithub/league/automation.py:16–18` prefers saved `LeagueSettings.enabled` over `LEAGUE_ENABLED`. `league_tick` alone has no feature gate. | Stop `jobs-league`. On the copy, explicitly disable saved league settings before normal startup; do not rely only on the environment flag. Avoid unguarded tick/ensure/collect/history commands. |
| Admin emails | `notifications/admin_email.py` defaults enabled when no settings row exists, can fall back to active superuser addresses, and can send immediately after a request transaction. `ADMIN_EMAIL_SEND_IMMEDIATELY=False` disables immediate sending but not the delivery worker. | Keep `jobs-admin-email` stopped; disable saved settings on the copy and force Mailpit/another local capture backend. Remove real SMTP credentials and override inherited mail host configuration. |
| Member notifications | `member_email_tick` processes pending league events before checking `MEMBER_EMAIL_ENABLED`; campaign and activity delivery have separate flags. | Keep `jobs-email` stopped; disable both email flags and inspect copied pending queues before release. |
| YouTube blog | `youtube_blog_tick` selects stored channels with `automatic_checks=True`; provider requests and admin alerts can follow. There is no overall env-off check in that command. | Keep `jobs-youtube-blog` stopped; disable automatic checks on copied channel rows before later startup. |
| Amazon | Even with `AMAZON_AUTOMATION_ENABLED=False`, the worker calls purge-only. `shop/amazon.py:purge_expired` clears expired price, currency, availability, title, image URL and detail URL fields. | Keep `jobs-amazon` stopped while comparing source/copy. Disable credentials and fetching; only release purge after preserving the baseline and accepting expiry behavior. |
| Payments | Stripe flags/key configuration controls new checkout; copied order state and webhook IDs are real history. | Keep checkout and live payments disabled, remove live keys, and prevent production webhook routing to the rehearsal. Preserve order/receipt rows. |

A plain V1 copy has none of the new V2 job configuration/queue tables, but admin alerts still default enabled after migration. A previously used V2 copy may carry enabled switches and pending jobs. Apply controls according to the actual source schema.

## Staging code reconciliation

Fourteen commits exist on `origin/staging` beyond the V2 branch base, affecting only these six tracked paths. Merge their intent into the working V2 implementation; do not replace V2 files wholesale with staging versions.

| Path / staging change | Audit outcome |
| --- | --- |
| `edithub/models.py` — Alight Motion logo crop/size | Was absent. Applied the staging `h-8 w-8` and cropped viewBox line locally, preserving the V2 league-model imports. |
| `edithub/views.py` — refresh achievements on title read; expose progress after unlock | Was absent. Applied those two small changes locally. They operate on legacy grants/history and do not change league ranking. |
| `edithub/utils.py` — channel thumbnail/identity fix (`f23cc48`) | V2 `/@handle` onboarding already uses `_fetch_youtube_handle`, a direct `forHandle` lookup with high/medium/default thumbnail fallback and safe failure reporting. This supersedes staging's search fallback for that path. |
| `edithub/utils.py` — commit labelled Shorts fix (`9b0dde5`) | Reconciled `get_youtube_channel_id_from_link` through the existing exact V2 provider resolver (`id`, `forHandle`, `forUsername`). Removed the substring/custom-URL ownership fallback. Unsupported `/c/` identity links now fail explicitly; use a canonical `/channel/UC…` or `/@handle` link. Existing application records are not rewritten. Regression tests cover supported forms, deceptive hosts, failures and ownership mismatch. |
| `edithub/utils.py` — total-points comparison (`fe624ff`) | Explicit None handling/threshold float conversion is absent in the initial V2 copy. Existing `sum or 0` with integer threshold already handles normal saved numeric values; regression tests now verify historical decimal points qualify. The meaningful missing title refresh was in views and is restored. Reconcile equivalent numeric normalization if this helper is edited. |
| `edithub/templates/edithub/customize_profile.html` | Staging shows progress/requirements for unlocked titles and hides misleading coin/free labels for achievement titles. This is legacy-template presentation, not the new profile UI. Do not copy it into React; decide separately whether to maintain legacy customization display. API progress fix is retained. |
| `edithub/templates/edithub/ranking_table.html` | Staging removed a promotional “Coming Soon” footer. Its updated legacy template stays in the candidate because the worktree starts from `origin/staging`. V2 has its own league interface. |
| `theme/templates/base.html` | Staging adds a production Google Analytics tag. V2 uses a different frontend. Do not introduce the production analytics tag into the staging rehearsal; configure analytics deliberately for the actual frontend/environment. |

The three legacy templates stay at their `origin/staging` versions in the candidate. They are not copied into the React frontend. The legacy base template retains staging's analytics tag; V2 does not inherit it. Review analytics separately before enabling legacy routes in a public rehearsal.

## Rehearsal and acceptance sequence

1. Record exact source/target revisions, source PostgreSQL version, applied migration ledger and actual Compose project/volume names. Capture a complete logical dump plus a complete media snapshot. Preserve the original service volumes and maintain an independent backup. Quiesce source writes for the final consistent database/media pair; do not mistake a live snapshot taken earlier for the final cutover copy.
2. Restore to a fresh, separately named PostgreSQL 16 database and media volume. V1 Compose uses PostgreSQL 14 (`docker-compose.staging.yml`); V2 uses 16 (`compose.v2.yml`). Do not attach the PG14 data directory to PG16. Use a logical dump/restore for this rehearsal. PostgreSQL recommends newer-version dump tools and documents why a filesystem copy cannot perform this major-version migration: [PostgreSQL 16 upgrade documentation](https://www.postgresql.org/docs/16/upgrading.html).
3. Before starting application/worker processes, apply the copied-state controls above. Keep production endpoints, provider credentials and workers isolated. Avoid loading demo fixtures or running `seed_v2_demo.py` against the copy.
4. Compare the restored copy to the source manifest before V2 migrations: table counts, ordered primary-key sets, FK integrity, password hashes and account flags, application statuses, editor titles/grants, original `WeekWinner` `(week_start, week_rank, user_id, submission_id)` history, calculated points, shop favourites/products, event fields/responses and notification preferences. Include every join/audit table. Do not print password hashes, addresses or private uploads in logs; compare hashes/manifests internally.
5. Inspect `migrate --plan`; apply reviewed migrations on the copy. Recheck every legacy table and original media path. Expected new content is schema/permission metadata plus the two placeholder request cards; no monthly point conversion is expected. Record intentional copied-state switch edits and any explicit title-grant reconciliation separately from the invariance checks.
6. Verify media file counts and checksums, not only database paths. Open representative existing avatars, product images, editor uploads and rich-text assets through the target gateway. Verify a member login, superuser admin, existing event application, favourite/product, saved title, legacy edit/history, historical top-three archive and V2 empty/new league behavior.
7. Keep the source deployment available and preserve the pre-migration dump/media. Rollback means switching to that preserved source snapshot/service; reversing additive migrations can drop new V2 tables and is not a safe data rollback after V2 writes.

## Verification performed

The package-wide migration check found a pre-existing Summernote ID mismatch:
its shipped attachment migration uses `AutoField`, while it inherited this
project's `BigAutoField` at runtime. A local AppConfig now explicitly retains
Summernote's original `AutoField`, in normal and test settings. No vendor file,
database column or historical migration was changed.

- Parsed the migration operations in every migration absent from `origin/staging`; enumerated all creates, alterations and RunPython steps without accessing a live database.
- Compared all six staging-changed paths and inspected V2 readers, models, startup/worker commands and media mounts.
- Applied the `edithub/models.py`, `edithub/views.py` and exact identity-resolution compatibility changes described above.
- Ran `manage.py test edithub.test_staging_compatibility edithub.test_youtube_onboarding edithub.test_league_providers edithub.test_league_integration --settings=prime_project.test_settings --noinput`: 38 tests passed using isolated SQLite and mocked provider requests. These do not validate a PostgreSQL restore or remote staging data.
- Nine staging configuration checks and 26 manifest tests passed. Six release archive checks passed; the POSIX file-permission retry test is skipped on Windows and is included in the Linux workflow. Bash syntax and Compose interpolation passed locally.
- In the isolated staging worktree, all 515 Django tests for accounts, edithub, platform_api, shop, notifications and dashboard passed, followed by a clean `makemigrations --check --dry-run`. All 64 frontend tests, TypeScript checking and the frontend production build passed there too. Docker image/runtime and real PostgreSQL restore checks remain outstanding because the local Docker engine is unavailable.

Remote source counts, real migration ledger state, backup integrity, copied media integrity and a PostgreSQL 16 restore remain deployment acceptance checks, not established findings of this source audit.
