# Version 2 local setup

Campaigns, Amazon automation and Stripe checkout now have a dedicated [setup guide](COMMERCE_EMAIL_SETUP.md), including environment keys, migrations, webhook events and worker schedules. Their switches remain disabled until configured.

## Run locally without Docker

For the complete Docker stack with live source updates and scheduled jobs, use
[the Docker development guide](VERSION_2_DOCKER.md). The independent non-Docker
preview below remains available.

The preview uses `prime_project.settings_v2_local`, which never imports production
settings or reads `prime_project/.env`. Its database is
`.local-v2/db.sqlite3`, uploads are in `.local-v2/media`, and email messages are
captured as local text files in `.local-v2/emails`. It uses Django PBKDF2 password
hashing, a persistent random local secret, separate cookies, and disabled legacy
ranking jobs. It sends no external email.

Use Python 3.12 and Node.js 22.13 or later. If the repository's `.venv` is not
already installed, create it with Python 3.12 and install the backend dependencies
from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r prime_project/requirements.txt
```

Then run from the repository root:

```powershell
.\.venv\Scripts\python.exe prime_project/manage.py migrate --settings=prime_project.settings_v2_local
.\.venv\Scripts\python.exe prime_project/manage.py createsuperuser --settings=prime_project.settings_v2_local
.\.venv\Scripts\python.exe prime_project/manage.py runserver 127.0.0.1:8000 --settings=prime_project.settings_v2_local
```

In another terminal, start Next.js:

```powershell
Set-Location New_Frontend
npm ci
$env:BACKEND_INTERNAL_URL = 'http://127.0.0.1:8000'
npm run dev
```

Visit <http://localhost:5173> and <http://localhost:5173/admin/>. Next.js proxies
the API, administration, static assets, and uploads to the loopback-only Django
server. Open the newest `.local-v2/emails/*.log` file to retrieve a registration
code or password reset link. These files are a local email outbox, not a claim
that messages reached an external recipient. Keep the preview running as one
Django process while the rate-limit cache is in memory.

No environment file is required for this preview. For optional Google or
reCAPTCHA configuration, copy `.env.v2.local.example` to `.env.v2.local` and fill
the `V2_LOCAL_*` variables. Google requires all three
`V2_LOCAL_GOOGLE_OAUTH_CLIENT_ID`, `V2_LOCAL_GOOGLE_OAUTH_CLIENT_SECRET`, and
`V2_LOCAL_GOOGLE_OAUTH_REDIRECT_URI`. Register the exact callback
`http://localhost:5173/api/v2/auth/google/callback/` in Google Cloud. Restart Django
after editing the file. Do not reuse the Docker callback port `8082` for this
preview. Live OAuth remains unverified until your credentials are supplied.

The local directories and environment file are ignored by Git. The preview is
separate from the test configuration, which uses an in-memory database and faster
test-only password hashing.

Run backend checks without Docker or production data:

```powershell
.\.venv\Scripts\python.exe prime_project/manage.py test platform_api accounts.test_api dashboard notifications --settings=prime_project.test_settings
.\.venv\Scripts\python.exe prime_project/manage.py check --settings=prime_project.settings_v2_local
.\.venv\Scripts\python.exe scripts/check_v2.py --site http://localhost:5173
```

The last command requires both local servers and performs read-only HTTP checks.
Do not use its Docker-only `--run-flows` option for this preview. From
`New_Frontend`, `npm run typecheck`, `npm run build`, and `npm run verify` check
types, the production build, and the running frontend/API integration respectively.

For owner alerts about applications, submissions and reports, see
[Admin email alerts](ADMIN_EMAIL_ALERTS.md). Configure recipients and categories
under **Notifications → Admin email settings**; local delivery is captured in
the same file outbox as account/contact mail.

## Docker development and built preview

Use [VERSION_2_DOCKER.md](VERSION_2_DOCKER.md) for the maintained Docker workflow.
It covers one-command startup, live frontend/backend editing, background email,
Amazon and league jobs, administrator creation, captured email, migrations,
credentials, logs and preserving local data.

From the repository root with Docker Desktop's Linux engine running:

```powershell
.\scripts\start-v2.ps1
```

Development mode is the default. For a compiled preview, use
`start-v2.ps1 -Mode preview`. Both modes use `.env.v2`, port `8082`, Mailpit on
`8026`, and the same isolated PostgreSQL/upload volumes. They do not import the
non-Docker SQLite database or its uploads automatically. The launcher creates a
new environment file with random local secrets only when it is absent; an
existing `.env.v2` is preserved.

The V2 Compose stack disables the legacy follower-ranking scheduler. Official
league scoring still needs its approved configuration and calibration; running a
Docker job does not complete those application workflows. Member campaigns,
Stripe hosted checkout and Amazon website refresh are implemented and remain off
until configured. External credentialed acceptance and production cutover remain
separate from local Docker setup.

The local Docker configuration captures email in Mailpit and is not a production
hosting specification. See the Docker guide for runtime verification limits.
