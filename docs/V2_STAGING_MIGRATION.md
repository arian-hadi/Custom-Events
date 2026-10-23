# V2 staging migration — start here

Updated on 19 October 2026 after private V2 staging deployment and acceptance
checks. The V1
staging and production databases were confirmed to use separate containers,
networks and volumes. V1 staging was backed up and restored into a new, isolated
PostgreSQL 16 database and media volume. All 31 tables, 275 database rows and 14
media files matched the source manifests. Server and user-approved local backup
copies were checksum-verified.

Both Linux application images built successfully. All 22 pending V2 migrations
applied to the isolated copy, and 296 static files were collected. Database,
backend, frontend, gateway and Mailpit services are running. Preservation checks
passed both after migration and after acceptance testing. No original record or
uploaded file was changed by these steps.

The user-approved public staging switch completed on 19 October 2026. V2 now
serves `http://128.140.40.7:8080/`, with admin at `/admin/`. No SSH tunnel is
required for the website. The V1 staging gateway is stopped and retained for
rollback; its database and media remain intact. Production was not changed.
The V2 gateway binds `0.0.0.0:8080`; the server env sets `STAGING_PUBLIC_URL` to
that public HTTP origin. Future staging CI runs retain those server settings.
Mailpit remains private at server loopback port 8027; use an SSH tunnel for it.
No workers were started. Provider keys and live payments remain disabled;
emails are captured in Mailpit. HTTPS is deferred at the user's request.

Private records are in `.local-v2/staging-backups/20261018-initial-copy/OPERATION.md`
and `.local-v2/staging-deployment-20261019.md`. The reconnect helper is
`.local-v2/open-staging.ps1`. Do not rerun the empty-database restore instructions
against the now-populated V2 volume. Next steps are member/admin acceptance with
the user's existing staging account, deliberate V2 content configuration, and
individual integration setup before worker activation or public routing changes.

## Which copy is which?

| Purpose | Code / configuration | Data |
| --- | --- | --- |
| Continue developing locally | `version-2.0`, existing `.env.v2`, `compose.v2.yml` plus `compose.v2.dev.yml` | Existing local V2 database |
| Review the V2 migration candidate | `codex/staging-v2-migration`, separate managed worktree based on `origin/staging` | No database copied into Git |
| Rehearse on Hetzner | `compose.v2.staging.yml` alone, server `.env.v2.staging` | New PostgreSQL 16 and media volumes, restored from a backup of the confirmed V1 staging database |
| Existing staging | Existing `staging` deployment, `/root/Custom-Events-Staging` | Keep its original PostgreSQL 14 database and media |
| Live website | `master`, `/root/Custom-Events` | No changes |

The candidate is saved as local Git checkpoint
`438611efab3c586ed9989ea35f9849aa3cef2e63`; its verified source archive has been
uploaded to an immutable server release directory and was initially served by private
V2 staging before the public switch. Subsequent reviewed commits pushed to `staging` use the
[V2 deployment workflow](STAGING_RELEASE_FLOW.md) to update this isolated site.
New local changes only enter it when committed and pushed. The first candidate includes the
current V2 source and reconciles staging's title/YouTube fixes; staging-only
legacy templates remain in the candidate. Do not merge the whole old staging
implementation over V2 or copy a live database into this repository.

## Phase 1 — identify the server and source

Find the server's public IP in Hetzner Console → project → server → Networking.
Use your existing SSH account/key. Do not send passwords, private keys or env
file contents in chat. The old workflow references `SSH_HOST` in GitHub secrets;
its value cannot be recovered from the repository.

After connecting, these commands only inspect container names, ports and mounts:

```bash
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
docker inspect staging_db --format '{{range .Mounts}}{{println .Name .Destination}}{{end}}'
docker inspect staging_web --format '{{range .Mounts}}{{println .Name .Destination}}{{end}}'
```

The repository suggests `staging_db`, `staging_web`, public port `8080`, and
PostgreSQL 14; verify these on the server. Container names are not proof that
Django connects to that database. Check the source application's effective
database **host, port and name locally on the server**, without displaying its
password. Confirm it is distinct from production before copying or pausing it.
If it shares production's database, stop and redesign the rehearsal around an
approved backup; do not pause production or run V2 migrations there.

Record the deployed revision, applied migration ledger, media mount, database
version and available disk space. A database dump plus an uploaded-media copy
are both necessary. Retain an independent backup outside the Docker volumes.

## Phase 2 — prepare source and independent configuration

Review and commit the complete candidate, including all previously untracked V2
source, assets, lockfile and migrations. Real `.env` files, provider JSON secrets,
database dumps and user uploads must not be committed. Promote that reviewed
revision to `staging` only when ready. See [release preparation](STAGING_RELEASE_FLOW.md)
for the validation-only push workflow and the manual image preparation workflow.
The new workflow does not take effect remotely until it has been committed and
pushed. The current remote workflow remains unchanged for now.

Create `/root/Custom-Events-Staging-V2/.env.v2.staging` from
`.env.v2.staging.example`. Use new random values for `STAGING_SECRET_KEY` and
`STAGING_DB_PASSWORD` (hexadecimal avoids URL escaping issues). Leave provider
keys blank initially. Keep the default loopback bind and SSH tunnel URL while
there is no staging domain. Use absolute `STAGING_SECRETS_DIR` and
`STAGING_AUDIT_DIR` paths outside the immutable source release.

Create the private directories on the server, with the audit directory writable
by the backend container's UID/GID `10001`. Credential files, if later added,
must be readable by that user and not publicly readable. Keep the env file
operator-only. Do not place credentials inside a release or the media volume.

After the reviewed release has been built, use these Bash variables for later
commands in this guide. Replace the placeholder with the exact prepared commit:

```bash
set -euo pipefail
release_sha=REPLACE_WITH_PREPARED_40_CHARACTER_COMMIT
release_root="/root/Custom-Events-Staging-V2/releases/$release_sha"
export STAGING_IMAGE_TAG="$release_sha"
v2=(docker compose --env-file /root/Custom-Events-Staging-V2/.env.v2.staging
    -f "$release_root/compose.v2.staging.yml" -p platform-v2-staging)
"${v2[@]}" config --quiet
```

Do not combine this Compose file with a V1 or local development Compose file.
The default project is `platform-v2-staging`. Migrations, audit tools and workers
require explicit service selection; a normal `up` does not run them.

## Phase 3 — back up V1 and restore into an empty V2 database

Plan a short pause for **confirmed staging-only writers** so the DB and media
represent one consistent state. Include web requests, schedulers, workers and
any other process writing those volumes. Keep its DB running for the dump.
Do not use `docker compose down -v`. Keep production running unchanged.

Use PostgreSQL's logical `pg_dump` custom format and `pg_restore`. Do not attach
the old PostgreSQL 14 data volume to PostgreSQL 16. Preserve database IDs,
password hashes, groups, permissions, migrations and all legacy tables; don't
try to rebuild the site from selected Django fixtures.

For a verified `staging_db` container whose `POSTGRES_USER`/`POSTGRES_DB` identify
the actual source database, the dump can be created without printing credentials:

```bash
umask 077
# Choose a NEW backup path in an existing private directory; never overwrite one.
backup_file=/root/Custom-Events-Staging-V2/backups/REPLACE_WITH_UNIQUE_NAME.dump
test ! -e "$backup_file" || exit 1
docker exec staging_db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_file"
# Inspect the command's exit status and validate the archive before proceeding.
```

Copy the **complete media volume** at the same pause, preserving relative paths,
and record counts/checksums. A database dump does not include avatars, products,
verification screenshots or blog images. Resume V1 staging only after the pair
is safely captured. File-copy commands depend on the inspected volume/storage
type; do not guess volume names or use a source volume as V2's writable mount.

On the new V2 project, start only its DB and verify the target is empty:

```bash
"${v2[@]}" up -d db
target_tables=$("${v2[@]}" exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM pg_tables WHERE schemaname = '\''public'\'';"')
[[ "$target_tables" == 0 ]] || { echo 'Target is not empty; stop and inspect it.'; exit 1; }
"${v2[@]}" exec -T db pg_restore --list < "$backup_file"
"${v2[@]}" exec -T db sh -c 'pg_restore --exit-on-error --single-transaction --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$backup_file"
```

No `--clean`, no dropped database, and no replacement of the old volumes. If
restore fails, investigate it; don't continue with a partial copy. Restore the
media snapshot into V2's own `staging_media` volume and make it writable by UID
10001. Static files are rebuilt later; they do not replace uploaded media.

## Phase 4 — verify preservation and migrate the copy

Keep the V2 backend, frontend and all workers stopped. First reconcile source
backup counts/media checksums against the restored copy. A successful restore
alone is not a full integrity check. Check its migration ledger against the
source; never fake migrations or reset the ledger to make errors disappear.

Capture a private baseline on the restored copy, inspect the plan, migrate, then
compare. The audit service uses raw database reads without initializing app
signals, and mounts media read-only:

```bash
"${v2[@]}" run --rm audit python /tools/staging_data_manifest.py snapshot --output /audit/before.json --media-root /app/mediafiles
"${v2[@]}" run --rm migrate python manage.py migrate --plan
# Review the plan against STAGING_DATA_AUDIT.md before this next command.
"${v2[@]}" run --rm migrate
"${v2[@]}" run --rm audit python /tools/staging_data_manifest.py snapshot --output /audit/after.json --baseline /audit/before.json --media-root /app/mediafiles
"${v2[@]}" run --rm audit python /tools/staging_data_manifest.py compare /audit/before.json /audit/after.json
```

Manifest files are never overwritten. Use new filenames for another rehearsal.
Existing row values, primary keys and media must remain; additional tables,
columns and records are allowed. Every mismatch needs investigation. The tool
does not verify sequences, indexes, constraints or application behavior and
does not prove the original backup was complete. Its manifests include private
filenames/hashes and should stay on the server, outside Git.

See [data audit](STAGING_DATA_AUDIT.md) for the full migration inventory. Existing
legacy winners remain historical records; second/third places are not converted
to first-place V2 wins. Old follower counts do not become monthly league points.
Pending historical destructive migrations require separate review. A previously
used V2 source may have intentional V2 data changes, which must be recorded and
reviewed rather than ignored by broad exclusions.

## Phase 5 — open the private staging site and test

After preservation passes:

```bash
"${v2[@]}" up -d backend frontend gateway
"${v2[@]}" ps
```

From your computer, open a separate terminal and keep this tunnel running:

```bash
ssh -L 8083:127.0.0.1:8083 -L 8027:127.0.0.1:8027 USER@SERVER_IP
```

Visit `http://localhost:8083/`, `/admin/`, and the captured mail inbox at
`http://localhost:8027/`. These are staging ports, distinct from your local
development ports 8082/8026. No public domain is needed for this first test.

Check normal member and admin login; old profiles/titles, products/favourites,
applications and media; V2 dashboard; blog and Markdown draft import; contact,
signup/OTP and notification emails in Mailpit; league entry/standings/frozen
history; and test-mode checkout once configured. New staging secrets intentionally
invalidate old sessions/tokens; stored password hashes remain usable. Test users
must log in again. OAuth requires a matching callback configuration; external
webhooks cannot reach your SSH tunnel automatically.

Staging mail is forced into Mailpit even when copied settings contain real
addresses. Stripe live keys are rejected. No outbound workers start by default.
Review copied DB switches/queues before enabling a particular worker: saved
league settings and YouTube automatic checks can override assumed env defaults.
Amazon expiry cleanup can modify product metadata even when fetching is off.
Make intentional test changes only after the preservation baseline has passed.
Do not run demo seeding over the restored data.

## Phase 6 — subsequent development and eventual cutover

Keep coding on `version-2.0`. Commit a reviewed checkpoint, incorporate it into
the migration candidate, verify it, and promote a specific commit to `staging`.
Avoid continuously copying a changing working directory into a deployed release.
Use one reviewed release SHA at a time and the same image tag for every service.

Before replacing the old staging URL, confirm the server routing, backup pair,
test results, job switches and rollback choice. Traffic changes and activation
are not part of the preparation workflow. Keep V1's source, volumes and backup
available. Rollback restores routing to that preserved V1 deployment; do not
reverse migrations on a database that already has V2 writes. Staging test data
must never be synchronized back into production automatically.

## Local checks completed / remaining

Configuration isolation, archive validation and row/media comparison have focused
automated tests: 41 passed, with the POSIX permission retry test skipped on Windows
and included in the Linux workflow. All 515 Django tests for accounts, editors,
the V2 API, shop, notifications and dashboard passed in the candidate worktree,
using isolated SQLite and mocked provider requests. The release helper parses
with Bash and Compose configuration renders without connecting to Docker.
The copied frontend's 64 tests, TypeScript check and production build pass.
The Django migration check reports no pending model changes. Summernote's ID
configuration explicitly matches its shipped migration rather than generating
a migration in site-packages.

Server acceptance completed on 19 October 2026: PostgreSQL 14 → 16 logical
restore, all 22 V2 migrations, original-row/media preservation, both Linux image
builds, healthy service startup, zero pending migrations and clean Django system
checks. Thirty-five backend checks passed, including CSRF enforcement, member and
admin password login, imported-member rendering and admin lists. Synthetic test
accounts were rolled back. Fourteen public pages/API routes, 23 browser assets
and all 14 preserved media files passed HTTP checks through the SSH tunnel. A
multipart HTML test email was captured by Mailpit. Homepage, shop and Editing
Hub were visually checked in the browser. The old staging and production
containers' start timestamps did not change during V2 deployment/acceptance.

Still required: user acceptance of the imported content, provider-specific test
credentials and end-to-end external integration checks, deliberate job activation,
and any future public URL/cutover. This is a V1 staging-data copy, not an import
of the local V2 development database; local-only hero images, blog posts and V2
configuration do not appear automatically. No remote workflow was dispatched.
