# Admin email alerts

Operational alerts notify the site owner about submissions that need attention.
They are separate from contact mail and member newsletter/notification preferences.
They do not enable newsletters, ranking campaigns or Discord integration.

## Events covered

| Alert | Trigger |
| --- | --- |
| Editor application | The applicant confirms their channel application; unconfirmed drafts do not send |
| Editor removal | An editor requests removal |
| Edit submission | The existing submission preview is confirmed and the edit becomes `verified` |
| Moderation report | A new active, unresolved edit report is submitted |
| Event application | A new application is saved, including its completed custom-field answers |

Each email contains the submitter's name/email, the relevant channel, video,
report or event details, and a link to the specific Django administration record.
The review link requires the existing administrator permissions. Visiting it
does not approve, reject or delete anything. Replying to an email does not change
an application.

## Configure recipients and topics

Log in as a superuser and open **Notifications → Admin email settings** in Django
administration. Enable/disable all alerts or individual categories and enter the
recipient addresses, one per line or separated by commas. Only superusers can
change these settings or inspect the delivery log.

Recipient precedence is:

1. Addresses saved in Admin email settings.
2. `ADMIN_NOTIFICATION_RECIPIENTS` from backend configuration.
3. Email addresses of active superusers.

Ordinary staff, event organizers and applicants are not automatically added as
global recipients. With no recipients, no email is queued; the server logs a
configuration warning. Up to 20 unique recipients are supported, and each receives
a separate email. Subscriber opt-outs do not disable owner operational alerts.

For the non-Docker local preview, optionally set these in `.env.v2.local`:

```dotenv
V2_LOCAL_ADMIN_NOTIFICATION_RECIPIENTS=owner@example.test
V2_LOCAL_ADMIN_EMAIL_SEND_IMMEDIATELY=True
```

Restart Django after changing environment settings. Changes saved in Django admin
take effect without a restart. This preview always captures mail under
`.local-v2/emails`; it never sends to an external inbox. Captured messages are
labelled **Captured locally** in **Notifications → Admin email deliveries**.

For Docker, use unprefixed values in `.env.v2` and the origin
`http://localhost:8082`. Mailpit captures messages at <http://localhost:8026>.
The `jobs-admin-email` service runs due retries automatically every 60 seconds
after each completed cycle. Do not also add a host schedule for the same worker.
See [the Docker development guide](VERSION_2_DOCKER.md) for startup and logs.

For a later deployed environment, configure Django's real email backend and
sender, plus:

```dotenv
ADMIN_NOTIFICATION_RECIPIENTS=your-admin-address@example.com
ADMIN_NOTIFICATION_BASE_URL=https://your-website.example.com
ADMIN_EMAIL_SEND_IMMEDIATELY=True
```

Replace the example values. The base URL must be the public website origin so
review links point to the correct deployment. These are server-only settings.
SMTP acceptance is recorded as **Sent**; it does not prove delivery to the inbox.
No real SMTP deployment or external mail sending was performed during development.

## Delivery and retries

The application creates a delivery record inside its database transaction, with
one record per event, object and recipient. Email is attempted only after commit.
Rollbacks therefore discard the queued alert. Repeated saves do not create
duplicate emails for the same event/object/recipient.

Delivery failure leaves the submission saved and the email marked **Failed**.
An owner can select failed records in Admin email deliveries and use **Retry
selected failed emails now**. Removed recipients, disabled topics and records
that no longer need attention are checked again before delivery.

This command processes due pending/failed records, with retry backoff:

```powershell
.\.venv\Scripts\python.exe prime_project/manage.py send_admin_alerts --settings=prime_project.settings_v2_local
```

Run it against the appropriate deployment settings when deployed. Outside the V2
Compose stack, automatic retries require scheduling this command periodically.
The Compose stack already includes the retry service. To move all delivery out
of web requests, set `ADMIN_EMAIL_SEND_IMMEDIATELY=False` with a running delivery
worker/schedule. Keep it `True` until that worker/schedule is configured.

Atomic claiming prevents concurrent senders from processing the same record.
A process interrupted during delivery can leave a record in **Sending**; it is
not automatically resent because SMTP may already have accepted the message.
Check the provider logs before using the owner-only **Retry interrupted sends
older than 15 minutes (may send duplicates)** action. This action ignores recent
in-progress deliveries; it does not run automatically. SMTP cannot
guarantee exactly-once delivery across a crash or an ambiguous transport failure.

Existing historical applications are not backfilled or emailed by the migration.
The outbox stores application details for owner review; include it in the site's
data-retention policy before production rollout.

## Local migration and verification

```powershell
.\.venv\Scripts\python.exe prime_project/manage.py migrate --settings=prime_project.settings_v2_local
.\.venv\Scripts\python.exe prime_project/manage.py test notifications --settings=prime_project.test_settings
```

Docker runs checked-in migrations through its initialization service. Admin
alerts do not require WebSockets. See the Docker guide for runtime verification
requirements; captured local email does not prove delivery to a real inbox.
