# Version 2 API and feature map

11 October update: the automatic league now has a simple admin switch, automatic future-week scheduling and disclosed within-round starter scoring. See [automatic league delivery](AUTOMATIC_LEAGUE_UPDATE.md).

Current league scope (10 October 2026): open calendar-month leagues supported by weekly competitions. Annual competition is retired; historical records are preserved. See [the current league plan](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md).

This describes the implemented local V2 integration. It is not a production migration plan. The Next.js frontend and future clients use the Django backend's domain records; no independent microservices or copied user/product databases were introduced.

## Current scope

| Feature | Integration now | Existing behavior retained / deferred |
| --- | --- | --- |
| Website appearance | Admin-managed accent color, hero image and copy, buttons, homepage sections, navigation, social links, footer | Logo/favicon continue using `shop.SiteLogo` |
| Shop | Catalog/favorites plus configured Stripe checkout and curated Amazon Creators API product refresh | External affiliate purchases stay external; provider setup required; fulfillment is managed by staff |
| Blog | Separate `platform_api.BlogPost` with admin rich-text editing, categories, draft/published states and publication time | Existing announcements remain separate and retain their data and routes |
| Contact | Existing contact fields and honeypot validation, optional configured reCAPTCHA, rate limit, actual email submission with explicit failures | Local email goes to the configured development mail service; campaign delivery is unrelated |
| Accounts | Email/password login, verified registration, OTP resend, password reset/change, username editing, optional Google sign-in/linking | Legacy account/profile pages remain for existing profile controls |
| Events | Active event listing/detail, dynamic application fields, member submission, own applications, safe pending-application withdrawal | Existing dashboard handles application editing and organizer review/status changes |
| Notifications | Own records/read actions, preferences, scheduled member newsletters and automatic blog/shop campaigns | `email_delivery_active: false` applies to legacy event emails; separate campaign delivery/capture flags report the configured campaign state |
| Editing Hub | League implementation foundation and schema, not yet accepted for official scoring | Legacy editor data, routes, competitions, points and historical rankings are retained; V2 disables the legacy scheduled scoring job |
| Discord | Backend operations are independent of frontend page components | Bot commands, identity linking, role synchronization and submissions through Discord are deferred |

Administration uses Django's existing staff/model permissions at `/admin/`. New appearance controls are in **Website content → Website settings**; blog authoring is in **Website content → Blog posts**. Publishing a post can queue an opt-in email when member campaigns and automatic blog discovery are enabled and the external worker runs. No data migration converts old announcements into blog posts.

The footer support link is configured at **Website settings → Navigation and footer → Buy Me a Coffee profile link**. Enter an HTTPS `buymeacoffee.com/<your-profile>` link, save, and refresh the website. Leave it blank to hide the support button. There is no hardcoded account or environment variable. Migration `platform_api.0006_sitesettings_buy_me_a_coffee_url` adds the optional field without changing existing settings.

The October 15 homepage presentation update keeps existing content, products, articles, community sections and winner cards. Admin-uploaded hero artwork is cropped inside a responsive circle; entrance and section-reveal animations respect reduced-motion preferences. Collection artwork follows a bounded circular path as the visitor scrolls. The charcoal footer keeps account, contact, social and information links. Events links and direct homepage promotion are temporarily hidden in the frontend; event routes, settings, applications and records are preserved for later reactivation. The qualitative “Active editors” and “Weekly challenges” labels do not claim live user counts.

Homepage loading uses neutral placeholders until website settings arrive; no demo hero image is requested. The text entrance starts when settings resolve, and the artwork entrance starts after the configured image loads (including cached-image and failed-image handling). If all motion remains static, check the browser's reduced-motion preference: Windows **Accessibility → Visual effects → Animation effects** being off suppresses both CSS entrances and the JavaScript collection orbit. The site does not override that accessibility preference.

The isolated non-Docker preview uses Django's file email backend with `V2_LOCAL_PREVIEW=True`. Contact submission is permitted in that explicit local mode and reports that the message was saved to the local email inbox for testing. File delivery is otherwise rejected; a local capture is never described as external delivery.

## Transport and permissions

- API base is `/api/v2/`, on the same browser origin as Next.js through the V2 gateway/proxy.
- Browser identity uses the existing Django session cookie. Obtain a `csrf_token` with `GET /api/v2/auth/session/` or `/auth/csrf/`, then include it as `X-CSRFToken` on POST/PATCH requests. Send JSON bodies with `Content-Type: application/json`.
- Refresh the frontend's token after login, logout, verification and password changes because sessions/tokens may rotate.
- Content API private endpoints require an authenticated, active, verified account. They derive the owner from the session; submitted user IDs never select another user's data.
- Public reads do not create settings/preferences records. Responses have `Cache-Control: no-store` so session-derived favorites, application state and private data are not shared or stale.
- Public rich text is reconstructed with a conservative HTML allowlist. Scripts, embedded active content, event attributes and non-HTTP(S)/non-relative links are removed. The frontend also restricts rich-text rendering.
- Content errors return `{ "error": "...", "errors": { ... } }`; auth errors use `{ "detail": "...", "errors": { ... }, "code": "..." }`. `errors` and `code` are optional. Form errors may contain structured `{message, code}` entries. Use HTTP status codes, not text matching, to detect failures.
- Content lists use `{ "results": [...], "count": 0, "page": 1, "pages": 1 }`, with 24 records per page. Query `page`, plus filters listed below. Dates are ISO strings; monetary values are strings. Existing shop currency presentation is dollars and has no currency model field.

## Content endpoints

All paths below are relative to `/api/v2/` and include a trailing slash.

| Method/path | Access | Request and response |
| --- | --- | --- |
| `GET site/` | Public | `{site: {name, accent_color, secondary_accent_color, hero_title, hero_subtitle, hero_image, hero_button_text, hero_button_url, logo, favicon, footer_text, buy_me_a_coffee_url, navigation, social_links, home_sections}}` |
| `GET products/` | Public | Paginated active products; optional `category`, `search`; adds `categories: [{value,label}]` |
| `GET products/<id>/` | Public | `{product: ...}`; inactive/missing products return 404 |
| `GET favorites/` | Member | Same product list format/filters, restricted to own favorites |
| `POST products/<id>/favorite/` | Member + CSRF | `{is_favorite: true/false}` → `{is_favorite: ...}`; setting a state is idempotent |
| `GET blog/` | Public | Paginated published posts whose publication time has arrived; optional `category`, `search`; adds `categories: string[]` |
| `GET blog/<slug>/` | Public | `{post: ...}`; drafts and future posts return 404 even for a signed-in author |
| `GET announcements/` | Public | Paginated active existing announcements |
| `GET events/` | Public | Paginated active events; optional `search` |
| `GET events/<id>/` | Public | `{event: ...}` with dynamic fields and current user's `has_applied` |
| `POST events/<id>/apply/` | Member + CSRF | `{field_<id>: value, cover_letter?: string}` → `{application: ...}` with HTTP 201; 409 for duplicate application |
| `GET applications/` | Member | Paginated own applications, never other applicants' responses |
| `POST applications/<id>/withdraw/` | Owner + CSRF | `{}` → `{success: true}`; only pending applications, 409 otherwise; another owner's ID is 404 |
| `GET notifications/` | Member | Own paginated notifications plus `unread_count` |
| `POST notifications/<id>/read/` | Owner + CSRF | `{}` → `{success: true}` |
| `POST notifications/read-all/` | Member + CSRF | `{}` → `{success: true, count: number}` |
| `GET notification-preferences/` | Member | `{preferences: {...}, email_delivery_active: false}` |
| `PATCH notification-preferences/` | Member + CSRF | Flat partial boolean fields → same response; unknown fields/non-booleans rejected |
| `GET contact/` | Public | `{recaptcha_site_key, recaptcha_enabled}` |
| `POST contact/` | Public + CSRF | `{name,email,subject,message,website:"","g-recaptcha-response"?:token}`; success only after mail backend accepts the message; failure is 400, 429 or 503 |

Product fields: `id`, `name`, sanitized `description`, `category`, `category_label`, `thumbnail`, `main_image`, `images` (URL strings), `video_url`, `original_price`, `current_price`, `discount_percentage`, `is_free`, `free_deadline`, `redirect_url`, `ecommerce_platform`, `is_favorite`.

Post fields: `id`, `slug`, `title`, `excerpt`, sanitized `body`, `category`, `cover_image`, `published_at`, `author` (public username, never email).

Event fields: `id`, `title`, sanitized `description`/`details`, `deadline`, `date`, `deadline_passed`, `has_applied`, `fields: [{id,name,field_type,required}]`. Existing field types are `text`, `number`, `date`, and `boolean`. Boolean fields are optional. Public events never contain applicant identities or answers.

Application fields: `id`, `event`, `status`, `cover_letter`, `applied_date`, `updated_date`, `responses: [{field_id,name,field_type,value}]`, `legacy_url`, `edit_url`, `can_edit`, `can_withdraw`, `withdraw_api_url`. `legacy_url` goes to the member's legacy application listing. `edit_url` exists only while pending. `withdraw_api_url` is a POST action, not a navigation link.

Preference fields: `email_enabled`, `in_app_enabled`, and each combination of `email_` / `in_app_` with `application_updates`, `ranking_updates`, `edit_reports`, `achievements`. These are the existing preference fields, not newly active campaign subscriptions.

Site navigation/social links are lists of `{label,url}`. `home_sections` contains `{key,title,body,button_text,button_url}` records, initially `access`, `community`, and `features`. Defaults exist for a new empty development database; real records are authored in admin.

## Authentication endpoints

Relative to `/api/v2/auth/`:

| Method/path | Request / behavior |
| --- | --- |
| `GET session/` or `GET csrf/` | `{user,csrf_token,google_enabled,recaptcha_site_key}`; `user` is null when signed out |
| `POST login/` | `{email,password}`; returns session payload after verified login |
| `POST logout/` | `{}`; returns signed-out session payload |
| `POST register/` | `{email,username,password1,password2,recaptcha_token?}`; requires email verification before sign-in |
| `POST verify-email/` | `{email,code}`; successful verification consumes OTP and signs in |
| `POST resend-verification/` | `{email,recaptcha_token?}` |
| `POST password-reset/` | `{email,recaptcha_token?}`; sends frontend reset link when account is eligible |
| `POST password-reset-confirm/` | `{uid,token,new_password1,new_password2}` |
| `POST password-change/` | `{old_password,new_password1,new_password2}`; authenticated |
| `GET profile/` | Current session/user payload; authenticated |
| `PATCH profile/` | `{username}`; authenticated; cannot change email/role/staff status |
| `GET google/start/` | Redirects to Google when server credentials are configured |
| `POST google/link/` | Authenticated verified user + CSRF → `{authorization_url}` |
| `GET google/callback/` | Provider redirect; validates state, PKCE, nonce, signed identity and audience |

Google uses an additive `accounts.GoogleIdentity` record keyed by provider subject. Matching email alone never links to an existing account: users sign into their existing account first and link explicitly. Google accounts using third-party email addresses complete the site's email verification before activation. Live provider acceptance still requires real development OAuth credentials and registered redirect URLs.

## Legacy links and data preservation

The original Django route tables stay mounted. `/legacy/` aliases the old homepage. The gateway retains Django account pages, `/dashboard/`, `/shop/`, `/announcements/`, legacy notification action/API subpaths, `/editinghub/`, original `/events/events/...` and event administration routes, plus existing legal/about pages. The user-facing `/notifications` page uses Next.js.

Member applications are managed at `/dashboard/user/applications/`; editing pending responses uses `/dashboard/application/<id>/edit/`. Organizer review uses `/dashboard/admin/` and existing ownership checks. `/dashboard/application/<id>/` is an organizer-only detail view and must not be used as a member detail link.

The existing legacy withdrawal handler has historical GET mutation behavior. New frontend/API clients must use the CSRF-protected V2 POST withdrawal endpoint, never navigate to that handler. Legacy URLs are retained for compatibility; this release is not a full security rewrite of the old application.

Migrations are additive: blog/settings, Google identity, administrator/member email records, league foundation tables, Stripe configurations/orders and Amazon sources/runs. Existing accounts, products, announcements, events, applications, notifications and editing records remain in their original tables. `ENABLE_EDITHUB_SCHEDULER=False` disables legacy scheduled scoring in V2 without deleting those records or changing scoring logic.

## Verification

Run from the repository root using the project Python environment:

```powershell
.venv/Scripts/python.exe prime_project/manage.py test platform_api accounts.test_api --settings=prime_project.test_settings
.venv/Scripts/python.exe prime_project/manage.py check --settings=prime_project.test_settings
.venv/Scripts/python.exe prime_project/manage.py makemigrations accounts platform_api edithub shop events notifications announcements --check --dry-run --settings=prime_project.test_settings
```

The isolated settings never read `.env`, use an in-memory SQLite database, disable scoring jobs, and capture test email in memory. Tests cover private ownership, legacy inactive sessions, CSRF including anonymous contact, unpublished content, duplicate/invalid applications, withdrawal rules, favorites, preferences, mail failure reporting, Google account linking protections and verification flows.

The unscoped migration drift check also detects an existing `django_summernote` AutoField/BigAutoField discrepancy in the installed third-party package. The scoped project-app check passes; do not create migrations inside the installed package to hide that baseline issue.

The current rate-limit cache is process-local. A future multi-worker public deployment needs shared rate-limit storage. Trusted client IP rewriting is explicitly opt-in and safe only behind the private V2 gateway that replaces the incoming header; do not expose the backend port while enabling it.

Once the dedicated Compose stack is running, `scripts/check_v2.py` checks public APIs, private endpoint rejection and CSRF through `http://localhost:8082`. Add `--run-flows` for a synthetic registration/OTP/login/preferences/contact test using Mailpit at `http://localhost:8026`. The script first inspects the exact local `platform-v2` containers, verifies loopback port mappings and SMTP routing to capture-only Mailpit, and refuses external origins. It requires Docker daemon access for that optional flow. One unique `example.com` test account and its captured messages are intentionally retained for inspection; no existing account or mailbox message is deleted.

## Campaign and commerce API additions — 2026-10-01

See [COMMERCE_EMAIL_SETUP.md](COMMERCE_EMAIL_SETUP.md) for configuration. Existing session, verified-active-member and CSRF rules apply to private APIs.

| Endpoint | Contract |
| --- | --- |
| `GET/PATCH /api/v2/notification-preferences/` | Adds `email_newsletter`, `email_blog_updates`, `email_shop_updates`, default false. `email_enabled` is the master. Reports `email_campaign_delivery_active` and `email_campaign_capture_mode` separately from legacy `email_delivery_active`. Opt-out cancels unsent campaign deliveries. |
| `GET/POST /api/v2/email/unsubscribe/<token>/` | Signed no-login confirmation page; GET never changes settings, POST requires CSRF. Turns off all campaign topics. |
| `POST /api/v2/email/one-click/<token>/` | Signed RFC8058 capability; requires form `List-Unsubscribe=One-Click`, no session or CSRF cookie. |
| `POST /api/v2/payments/checkout/` | JSON `{product_id, idempotency_key}` with UUID key reused for retries. Returns `{order, checkout_url}`; disabled configuration returns 503. Clients cannot choose price, amount, currency or redirects. Expired uncertain request returns 409 `code: expired_request` with `order_id`. |
| `GET /api/v2/payments/orders/` | Own latest 100 orders only, `{orders}`. |
| `GET /api/v2/payments/orders/<uuid>/` | Own order `{order}`, 404 for another member's order. |
| `POST /api/v2/payments/stripe/webhook/` | Signature-authenticated Stripe event receiver; no browser/session authorization. Current provider session and line items are checked before recording payment. |

Product JSON adds `checkout` with `configured`, `enabled`, exact `amount_minor`, `currency`, `display_amount`, `fulfillment_kind` and `fulfillment_note`. The UI uses this authoritative checkout price when configured. A free/affiliate product cannot use checkout.

Automated Amazon product JSON overlays current provider fields, remote images, nullable `current_price`/`original_price`, `currency`, `price_available`, `price_updated_at`, affiliate/content/price notices and `amazon_automated`. `amazon_observed_at`, `amazon_offer_expires_at` and `amazon_content_expires_at` let open tabs expire cached content using elapsed time relative to the server observation. Expired price is never interpreted as free. Fresh published Amazon sources appear in list/detail/search/favorites; expired or disabled sources are unavailable.

Orders expose payment and fulfillment status, product name, exact amount/currency, delivery note and timestamps. Internal staff notes, payment credentials and checkout request parameters are never returned. Visiting a success URL cannot update payment state.
