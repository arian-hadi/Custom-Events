# Member email, Amazon and Stripe setup

These integrations are implemented on `version-2.0` and disabled by default. They are independent switches. Production has not been changed. For Docker with live editing and included job services, use [the Docker development guide](VERSION_2_DOCKER.md).

## Where to put configuration

For the existing non-Docker preview, copy the missing entries from `.env.v2.local.example` into the git-ignored `.env.v2.local` at the repository root. Do not overwrite existing values. These settings use the `V2_LOCAL_` prefix, and the preview reads only that dedicated file. Restart Django after changing settings.

For Docker, use the unprefixed names below in the git-ignored `.env.v2`, based on `.env.v2.example`. The launcher prepares a new file when needed; preserve existing secrets. Docker runs the job services automatically. Email defaults to Mailpit, or uses Gmail/other SMTP when its EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD and TLS/SSL settings are explicitly configured in .env.v2. Recreate services after changing the environment. For a separately deployed Django environment, use the same unprefixed names in the server's private environment. Never put server keys in `NEXT_PUBLIC_*`, frontend code, or Git. No additional secret-key file is required for these three integrations. A stable Django `SECRET_KEY` signs email unsubscribe links; the non-Docker local preview already keeps its secret under `.local-v2/django-secret.key`.

### Configuration checklist

| Feature | Server settings / account information you provide |
| --- | --- |
| Member campaigns | `MEMBER_EMAIL_ENABLED`, `MEMBER_EMAIL_BASE_URL`, `MEMBER_EMAIL_POSTAL_ADDRESS`; existing `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`/`EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL` and `EMAIL_TIMEOUT` |
| Stripe | `STRIPE_CHECKOUT_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CHECKOUT_BASE_URL`; `STRIPE_ALLOW_LIVE_PAYMENTS=False` until test acceptance |
| Amazon | `AMAZON_AUTOMATION_ENABLED`, `AMAZON_CREATORS_CLIENT_ID`, `AMAZON_CREATORS_CLIENT_SECRET`, `AMAZON_CREATORS_CREDENTIAL_VERSION`, `AMAZON_PARTNER_TAG`, `AMAZON_MARKETPLACE`; optional refresh/timeout settings below |

The local equivalents are in `.env.v2.local.example`. `MEMBER_EMAIL_BASE_URL` and `STRIPE_CHECKOUT_BASE_URL` use `V2_LOCAL_FRONTEND_URL` locally, normally `http://localhost:5173`. The local email backend always captures messages to `.local-v2/emails`; SMTP environment variables cannot silently switch it to real delivery. Live Stripe payments are blocked in local settings.

## Migrations

From the repository root in PowerShell:

```powershell
& ./.venv/Scripts/python.exe prime_project/manage.py migrate --settings=prime_project.settings_v2_local
```

New migrations are additive:

- `edithub/0025_league_foundation`: the previously missing league schema. This does not calibrate or enable the league.
- `notifications/0003_memberemailcampaign_memberemailsettings_and_more`: marketing topic preferences, campaigns, automation settings and delivery records. Existing members start with the three new marketing topics turned off.
- `shop/0010_stripe_checkout`: per-product Stripe configuration, orders and webhook receipts.
- `shop/0011_amazon_automation` and `0012_amazon_worker_lock`: curated Amazon sources, refresh records and a worker lock.

Stop Amazon workers before applying the worker-lock migration. The local preview database is `.local-v2/db.sqlite3`. Deployment requires applying the same migrations to the intended V2 database after its normal backup/release checks; do not point local preview commands at production.

Docker's initialization service applies checked-in migrations automatically. The launcher stops application/job services before initialization when restarting the stack. For migrations during development, use the worker-stop/migrate/start sequence in [the Docker guide](VERSION_2_DOCKER.md). Docker PostgreSQL and the non-Docker SQLite database are separate; neither is imported into the other automatically.

## Member campaigns

Members manage preferences at `/account/preferences`. The email master switch controls optional member emails, with separate opt-ins for newsletters, blog posts and new shop products. Account verification/password recovery and operational administrator alerts are separate workflows. Existing ranking/application/achievement email preferences remain saved, but those automatic member emails are still not implemented by this campaign work.

Each campaign message includes the sender's postal address, a preferences link and a signed unsubscribe link that works without signing in. Opening the link shows a confirmation; submitting it turns off all campaign topics. Mail clients can use the signed RFC8058 one-click POST endpoint. Previously queued messages are cancelled when a member opts out, and preferences are checked again immediately before delivery. A message already accepted by an email provider cannot be recalled.

1. Configure a verified sender and SMTP service in the deployed environment. Set `MEMBER_EMAIL_BASE_URL` to the exact public HTTPS origin, without a path, and `MEMBER_EMAIL_POSTAL_ADDRESS` to the sender's mailing address.
2. Set `MEMBER_EMAIL_ENABLED=True` when ready. For a local captured-email exercise, use `V2_LOCAL_MEMBER_EMAIL_ENABLED=True` instead.
3. As a superuser, open **Member email campaigns** in Django admin. Create a draft, choose a topic, write a plain-text subject/body, and set a scheduled time or use **Schedule selected drafts**. Content and recipients freeze when queued.
4. In **Member email automation settings**, independently enable automatic blog and/or shop campaigns. Discovery starts from each switch's enable time; existing content is not emailed as a historical backlog. Amazon products are excluded from automatic shop emails.
5. In Docker, `jobs-email` starts with the stack and runs a cycle every 60 seconds after the previous cycle finishes. Do not also install a host schedule for it. For the non-Docker preview, run the command manually or schedule it yourself:

```powershell
& ./.venv/Scripts/python.exe prime_project/manage.py member_email_tick --limit 100 --settings=prime_project.settings_v2_local
```

Use `--queue-only` to create delivery records without sending. For a deployment that does not use the Compose worker, schedule the command every minute with the server's scheduler and the correct Django environment. Failed sends have bounded backoff and a five-attempt limit. Superusers can inspect **Member email deliveries**, retry failures, or recover an interrupted send older than 15 minutes. Interrupted sends are not retried automatically because SMTP may already have accepted them; manual recovery can duplicate an email.

`captured` means a local file was written. `sent` means the mail backend accepted the message, not proof it arrived in an inbox. Configure sender authentication, SPF/DKIM/DMARC, bounce/complaint handling and provider limits with your email service. For RFC8058 support, the service's DKIM signature must cover both unsubscribe headers. The application does not yet ingest delivery-provider bounce webhooks. References: [RFC8058](https://www.rfc-editor.org/rfc/rfc8058), [Google sender guidelines](https://support.google.com/mail/answer/81126).

## Amazon product automation

This integration refreshes a curated list of ASINs through Amazon **Creators API** into the V2 website. It does not scrape Amazon, discover an unlimited product feed, post to Discord, or forward Amazon product content in campaign emails. Affiliate purchases finish on Amazon.

1. Obtain Creators API access and credentials through your Amazon Associates account, plus your approved partner tag. Use the credential version and marketplace matching that account. Supported credential versions are `3.1`, `3.2` and `3.3`; their authentication endpoints differ by region.
2. Set the Amazon values above. `AMAZON_MARKETPLACE` is a host such as `www.amazon.com`, not a URL. `AMAZON_REFRESH_MINUTES` defaults to 45 and is capped at 60; `AMAZON_HTTP_TIMEOUT` defaults to 15 seconds.
3. Add an **Amazon source** in Django admin by pasting the full Amazon product link into **Amazon product link**. Saving extracts the ASIN and marketplace from the URL; manual ten-character ASIN entry is also available. For `amzn.to` or `a.co` short links, open the link in your browser first and copy the full product address. Keep **Publish** off during the first fetch/review. Existing handmade products are not overwritten or converted. The source marketplace must match the configured API marketplace; a link does not change the server configuration or partner tag.
4. Preview due source IDs without network requests or database writes:

```powershell
& ./.venv/Scripts/python.exe prime_project/manage.py sync_amazon_products --dry-run --settings=prime_project.settings_v2_local
```

5. After supplying credentials, enable `AMAZON_AUTOMATION_ENABLED` (or its local-prefixed equivalent), then run `sync_amazon_products --limit 25`. Review **Amazon sources** and **Amazon sync runs**, and turn **Publish** on for the desired sources.
6. Docker's `jobs-amazon` service runs automatically with a 15-minute pause after each completed cycle. For a deployment without that Compose worker, schedule the command every 15 minutes. Do not run duplicate schedulers. Only due sources refresh; failures back off, one worker runs at a time, and abandoned work can recover. The command supports `--source ID` and `--force` for a targeted refresh. Neither bypasses disabled sources or an active worker lock.

Prices expire after at most one hour, or sooner if an offer ends; expired prices become **Check price on Amazon**, never a zero/free offer. Product content expires after 24 hours and is then omitted from the V2 catalog. Amazon images remain remote URLs. The Docker Amazon worker removes expired cached content even when refresh is disabled. Outside Docker, keep a scheduled `sync_amazon_products --purge-only` run when old provider content remains. Do not retain expired provider content through your database backup/restore policy without checking the applicable Amazon terms.

The original Product record for an imported ASIN is an inactive identity record; managed provider fields stay in the expiring Amazon source. Edit its **Publish** switch in Amazon sources, not its legacy product status. The frontend displays affiliate disclosure, price timestamps and content/price notices.

Account approval, granted marketplaces, quotas and a real credentialed fetch still require your setup. The protocol and response parser were checked against [Amazon's Creators API curl guide](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/get-started/using-curl); mocked tests are not proof of access for your account.

## Stripe checkout

This is hosted Stripe Checkout for a single owned product per order. Amazon and other affiliate products keep external purchase links. It does not collect card details on this website, and it does not require a frontend publishable key.

1. Create a Stripe sandbox/test account configuration. Put the secret test key (`sk_test_…` or appropriately scoped `rk_test_…`) in `STRIPE_SECRET_KEY`. Set `STRIPE_CHECKOUT_BASE_URL` to the frontend HTTPS origin; HTTP localhost is allowed only for test payments.
2. Configure a webhook for **your account**, not Connect/organization events, at:

   `/api/v2/payments/stripe/webhook/`

   Subscribe to `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed` and `checkout.session.expired`. Copy the endpoint's `whsec_…` signing secret into `STRIPE_WEBHOOK_SECRET`.
3. For non-Docker local testing, Stripe CLI can forward those events to `http://localhost:8000/api/v2/payments/stripe/webhook/`. Use that CLI session's signing secret in `V2_LOCAL_STRIPE_WEBHOOK_SECRET` and restart Django. For Docker, forward to `http://localhost:8082/api/v2/payments/stripe/webhook/`, use `STRIPE_WEBHOOK_SECRET` in `.env.v2`, and recreate services. The backend's port `8000` is not exposed on the Docker host. Test payment setup has not been performed with your account.
4. In Stripe, create an active, fixed, one-time Price. In Django admin, add a **Stripe product configuration** for the matching active owned product, with the Price ID (`price_…`), lowercase currency and exact minor-unit amount. For example, USD 29.99 is `2999`, while JPY 2999 is `2999`. The backend verifies the actual Stripe Price before creating checkout.
5. Enter delivery instructions and choose staff-managed digital delivery or physical shipping. Physical orders require permitted destination country codes. The current fixed price must include any shipping/tax you intend to charge: dynamic shipping, automatic tax, promotion codes and adaptive pricing are disabled. Review your pricing before launch.
6. Enable the per-product setting and global `STRIPE_CHECKOUT_ENABLED`. Local settings always block live keys. Test the full payment and webhook flow before separately enabling `STRIPE_ALLOW_LIVE_PAYMENTS` in a deployed environment.

Members see **Buy with Stripe** on configured products and can view `/account/orders`. Only a verified webhook, checked against current Stripe session data, can mark an order paid. A success/cancel return URL cannot do so. Payment amount, currency, product and owner are checked, retries reuse the original session request, and paid orders cannot be downgraded by a late failure event.

In Django admin, **Payment orders** show payment status and a link to Stripe. Staff can record fulfillment after payment confirmation. Shipping/contact details for physical orders are collected by Stripe and reviewed in its dashboard. Automatic downloads, shipping labels, subscriptions, shopping carts, refund/dispute synchronization and stock reservation are not implemented. Refunds/disputes must be managed in Stripe and separately reflected in your operational records; the local paid state records payment confirmation, not the current net refunded balance.

References: [Checkout fulfillment](https://docs.stripe.com/checkout/fulfillment?payment-ui=stripe-hosted), [webhooks](https://docs.stripe.com/webhooks), [idempotent requests](https://docs.stripe.com/api/idempotent_requests), [currency units](https://docs.stripe.com/currencies).

## Verification and remaining setup

The final combined suite passed 197 backend tests; 38 live HTTP assertions passed through the local frontend proxy. Backend validation uses isolated test settings and mocked providers. Local preview email is captured to files; no real campaign, Amazon API request or Stripe charge was sent during implementation. The frontend passes a production build, TypeScript checks and commerce/league helper tests. Browser visual acceptance remains pending because no browser surface was available on the final attempt. See `VERSION_2_PLAN.md` for the final verification counts and remaining league work.

Before enabling these features for members, supply the provider credentials, validate inbox delivery and an actual Amazon fetch, complete a Stripe test payment/webhook cycle, and verify the background services run successfully. For deployment outside the V2 Compose stack, install the documented schedules yourself. These are account/deployment setup steps, not actions performed by saving the environment examples. Docker's local Mailpit capture is not real inbox delivery.
