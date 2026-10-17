# V2 Docker development and preview

Use this guide for the complete local V2 stack. Docker Compose runs Next.js,
Django, PostgreSQL, the website gateway, Mailpit and the background job services
together. Development mode watches the files in this checkout: saving frontend
code updates the browser, and saving Python code reloads Django.

This is an isolated local environment, not the Hetzner production deployment.
Existing production/staging Compose files are not used. The old follower-ranking
scheduler remains disabled.

## Start with live editing

Install Docker Desktop and start its Linux container engine. Run the following
from the repository root in PowerShell:

```powershell
cd C:\Users\LENOVO\Documents\Python\transformers
.\scripts\start-v2.ps1
```

The launcher selects development mode by default. It creates `.env.v2` with random
local signing/database secrets when the file is missing, and starts the stack.
An existing `.env.v2` is never overwritten; replace its template placeholders
yourself if it has not yet been configured. You do not need
to install Python, Node.js or PostgreSQL on the host for this workflow.

The equivalent Compose command, after preparing `.env.v2`, is:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml up -d --build
```

Use `-PrepareOnly` to prepare/check local configuration without starting services.
After a successful build, `-NoBuild` skips rebuilding when dependencies and
Dockerfiles have not changed. The default launcher builds images before stopping
the application/job services to apply migrations, then waits for service health.

The first build downloads dependencies and takes longer. Containers keep running
in the background after the terminal closes; Docker Desktop and the computer must
remain running for the website and jobs to continue.

Open:

- Website: <http://localhost:8082>
- Administration: <http://localhost:8082/admin/>
- Mailpit inbox (when local capture is selected): <http://localhost:8026>

Use `localhost` consistently for sessions, CSRF and Google callbacks. The old
non-Docker preview at port `5173` is a separate runtime and database.

## Configuration and local data

Use **`.env.v2.example` copied to `.env.v2`** for Docker. The launcher can create
this file for you. Do not use `.env.v2.local`, which belongs to the separate
non-Docker preview, or the legacy `prime_project/.env`.

Integration credentials stay server-side. Keep `.env.v2` out of Git, and do not
copy production secrets into this local environment. For manual setup, use random
URL-safe values, such as hexadecimal strings, for `SECRET_KEY` and
`V2_DB_PASSWORD`.

Docker stores PostgreSQL data and uploaded files in persistent volumes belonging
to the `platform-v2` Compose project. These volumes are separate from
`.local-v2/db.sqlite3` and `.local-v2/media`. Your current non-Docker accounts,
uploads and products are **not imported automatically**. A fresh Docker database
starts empty. Transferring existing data is a separate migration task.

Keep database credentials stable after the PostgreSQL volume has been created.
Changing `V2_DB_PASSWORD` in the environment alone does not change the password
inside an existing database.

Startup waits for PostgreSQL, applies checked-in database migrations, then starts
the application and jobs. It does not generate migrations, create accounts or
invent sample data. A completed `migrate` container with exit code zero is normal.
Development serves source static files directly and skips static collection at
startup. Built preview mode collects static files after migrations; that step can
take longer because it also processes the legacy application's assets.

Create the first administrator once:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend python manage.py createsuperuser
```

The command creates a verified superuser. By default, registration and password
reset messages arrive in Mailpit. If using the preserved organizer dashboard,
also set that account's application role to `admin` in Django admin.

## Gmail SMTP instead of Mailpit

Docker reads the email settings in `.env.v2`. To deliver real email through Gmail,
use your sender address and app password there:

```dotenv
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-address@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=your-address@gmail.com
```

Apply changes with `.\scripts\start-v2.ps1 -NoBuild`. This changes delivery for
signup codes, password resets, contact messages and enabled notification jobs.
Mailpit remains available but does not capture new Gmail-delivered messages.
Use **Resend code** on an existing verification page to request a fresh email.
Optional member campaigns still require their own enablement and opt-in settings.

To return to local capture, set `EMAIL_HOST=mailpit`, `EMAIL_PORT=1025`, blank
the username/password and set both TLS/SSL flags to `False`, then rerun the launcher.
The `check_v2.py --run-flows` test deliberately refuses real SMTP; use the
read-only check without `--run-flows` when Gmail is selected.

## What updates when you save

| Change | What to do |
| --- | --- |
| Next.js components, CSS and frontend source | Save the file. Development mode rebuilds the affected page and updates the browser. |
| Django Python code | Save the file. Django's development server reloads automatically. |
| Django templates and source static assets | Save and refresh the page if necessary. Development mode serves source static files. |
| Background job Python code | The next scheduled invocation starts a fresh command and reads the saved code. A command already running finishes its current invocation. |
| Content edited in Django admin | Refresh the relevant page; no container rebuild is needed. |
| Database models or a new migration file | Create/review the migration if needed and apply it explicitly; source reload does not change the database schema. |
| Python requirements or npm dependency/lock files | Run the launcher again with a build so container dependencies are refreshed. |
| `.env.v2` | Run the launcher again to recreate services with the new settings. A plain container restart does not load changed Compose environment values. |
| Dockerfiles, Compose configuration or gateway configuration | Run the launcher again. Restart the gateway explicitly if changing only its mounted configuration. |

For model changes, stop scheduled jobs first so they do not process data while
the schema is being changed:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml stop jobs-email jobs-admin-email jobs-amazon jobs-league
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend python manage.py makemigrations
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend python manage.py migrate
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml up -d jobs-email jobs-admin-email jobs-amazon jobs-league
```

Run `makemigrations` only when you intentionally changed models. If you received
an existing migration from another change, run only `migrate`. Review migrations
before applying them; do not edit schema while testing concurrent activity.

Frontend dependencies and build output stay inside Docker rather than mixing
Linux container files with a Windows `node_modules` directory. Windows file
watching uses polling for reliable save detection. First visits and changes may
take a few seconds to compile; development performance differs from a built
preview.

## Scheduled jobs

The same startup command starts these background services. No host Task Scheduler
or manually opened worker terminals are required:

| Service | Default pause after each cycle | Work performed |
| --- | --- | --- |
| `jobs-email` | 60 seconds | Discover enabled automatic campaigns, queue due member campaigns and deliver eligible messages through the configured email server. |
| `jobs-admin-email` | 60 seconds | Process pending or failed administrator email alerts. |
| `jobs-amazon` | 900 seconds | Remove expired cached Amazon content and refresh due curated sources when automation is enabled. |
| `jobs-league` | 60 seconds | Process due league rounds and collect provider metrics when the V2 league is enabled and configured. |

Each service runs commands sequentially on a repeating interval. Do not scale a
job service or run another scheduler for the same work. Jobs do not run while
Docker/the machine is stopped. A later league run cannot invent provider totals
for a cutoff that was missed.

Feature switches still apply. Starting a scheduler does not enable a disabled
campaign integration, approve advanced scoring calibration or grant access to
an external provider. Unconfigured features stay disabled.

The intervals are configured with `V2_EMAIL_INTERVAL_SECONDS`,
`V2_ADMIN_EMAIL_INTERVAL_SECONDS`, `V2_AMAZON_INTERVAL_SECONDS` and
`V2_LEAGUE_INTERVAL_SECONDS`. `V2_JOB_TIMEOUT_SECONDS` limits a job invocation
(default 600 seconds). Keep one instance of each job service.

## Optional integrations

See [the commerce/email guide](COMMERCE_EMAIL_SETUP.md) and
[the admin alert guide](ADMIN_EMAIL_ALERTS.md) for the application workflows.
For Docker, use their unprefixed environment names in `.env.v2`.

| Integration | Required configuration |
| --- | --- |
| Member campaigns | `MEMBER_EMAIL_ENABLED=True`, `MEMBER_EMAIL_POSTAL_ADDRESS`, campaign/automation settings in admin and members who have opted in. Set `MEMBER_EMAIL_BASE_URL=http://localhost:8082`. Uses the configured SMTP server. |
| Admin alerts | Recipients and categories in **Admin email settings**, or the documented environment defaults. Immediate sending and the retry worker use the same configured SMTP server. |
| Google | Client ID, client secret and exact authorized callback `http://localhost:8082/api/v2/auth/google/callback/`. |
| Stripe | Test secret key, webhook signing secret, checkout switch and a matching active Stripe Price configuration for each owned product. Live payments remain disabled. |
| Amazon | Creators API credentials/credential version, approved partner tag and marketplace, enabled automation and curated ASIN sources in admin. Review the first fetch before enabling publication. |
| V2 league | Open Admin → League settings after migration 0027. The league worker prepares future weeks automatically. Approved editor channels and real provider credentials are still required; starter scoring is explicitly unvalidated. |

For the league's optional per-channel provider credential JSON, save the file at
`.local-v2/secrets/league-providers.json` and set
`LEAGUE_PROVIDER_CREDENTIALS_FILE=/run/v2-secrets/league-providers.json` in `.env.v2`.
That host directory is mounted read-only into backend/job containers. Use the
container path in the setting, not a Windows `C:\...` path. The directory remains
ignored by Git. The existing YouTube adapter uses `YOUTUBE_API_KEY`; Docker falls
back to `LEAGUE_YOUTUBE_API_KEY` when that value is blank. If both are configured,
`YOUTUBE_API_KEY` takes precedence for that shared adapter.

Stripe needs events forwarded from Stripe to your local gateway while testing.
The Docker URL is:

```text
http://localhost:8082/api/v2/payments/stripe/webhook/
```

Use the signing secret for that forwarded webhook session in `.env.v2`, then
recreate the services. Port `8000` is internal to Docker and is not published on
the host. A checkout return page alone cannot mark an order paid.

If changing `V2_PORT`, update all public origins/links to match: `V2_FRONTEND_URL`,
`CSRF_TRUSTED_ORIGINS`, `ADMIN_NOTIFICATION_BASE_URL`, `MEMBER_EMAIL_BASE_URL`,
`STRIPE_CHECKOUT_BASE_URL`, and the Google callback both locally and at Google.

## Built preview mode

Use a built frontend and Gunicorn backend when you want to review the compiled
site without development reload behavior:

```powershell
.\scripts\start-v2.ps1 -Mode preview
```

The underlying command is:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml up -d --build
```

Preview uses the same local database/uploads and background jobs, but source edits
require another build. Return to live editing with `start-v2.ps1 -Mode dev`.
Development and preview are alternative modes of the same Compose project; do
not try to run both simultaneously. Neither is a production deployment.

## Inspect and stop

Use both Compose files when working in development mode:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml ps -a
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml logs --tail=100 backend frontend migrate
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml logs --tail=100 jobs-email jobs-admin-email jobs-amazon jobs-league
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml stop
```

`stop` preserves the containers and data. `down` removes the containers/network
while retaining named database/upload volumes. **Do not add `-v` to `down` when
you want to retain local accounts, content and uploads.** Omit the development
override for equivalent preview-mode commands.

If startup says it cannot connect to the Docker engine, open Docker Desktop,
wait for its Linux engine to become ready, and rerun the launcher. If a port is
already in use, stop the conflicting service or update the port and related
origin settings. Check `migrate` logs first if backend or workers cannot start.

## Verification and remaining setup

The configuration supports the full local V2 runtime and live source editing.
External Google/Amazon/Stripe acceptance still requires your credentials and test
accounts. Mailpit confirms that the local mail backend accepted a message, not
delivery to an external recipient. Discord, unfinished league administration and
production cutover remain separate work.

Verified on Windows with Docker Desktop's Linux engine on October 4, 2026:

- Both development and built-preview images build and start successfully.
- Database migrations complete, and both modes retain the same PostgreSQL data.
- All four worker services become healthy; repeat cycles respect disabled
  integrations, with Amazon expiration cleanup remaining active.
- Next.js Fast Refresh works through the gateway and preserves component state.
- Django reloads after host Python edits, and source CSS updates without static
  collection or rebuilding.
- Signup, Mailpit verification code, login/logout, preferences, CSRF checks and
  contact mail pass the local integration checks.
- The bundled Chromium browser launches as the backend's non-root user.
- 13 Docker/settings/initializer tests, 14 worker tests (including Linux signal
  handling), and 6 frontend launcher tests pass. The optimized frontend build
  also passes TypeScript checking.

The signup checks leave synthetic `v2-smoke-...@example.com` accounts and captured
messages for inspection. No external provider credentials were used in these
checks, and no existing non-Docker accounts/data were transferred.

Optional repeat checks, on a host with the repository's Python dependencies:

```powershell
.\.venv\Scripts\python.exe scripts/check_v2.py --run-flows
.\.venv\Scripts\python.exe scripts/check_v2_reload.py
```

The reload check requires live development on the default port 8082 and either
Microsoft Edge or Playwright Chromium on the host. It creates a temporary React
page and source CSS file, briefly appends a unique Python comment, and removes
its probes afterward. It checks the Docker source mounts before editing files.

During verification, this machine's Docker Desktop installation twice failed
before engine startup with `userAnalyticsOtlpHttp.sock: The file cannot be
accessed by the system`. Preserving its temporary `AppData/Local/Docker/run`
directory under a timestamped backup name let Docker recreate it and start.
Image/database storage was preserved. This is a host Docker Desktop startup
issue, not a project migration error; the project launcher deliberately does
not alter Docker's private runtime files. If it returns after quitting Docker,
resolve that Desktop issue before rerunning the launcher; a factory reset is
not needed for the project configuration.
