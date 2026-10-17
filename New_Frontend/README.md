# Version 2 frontend

Next.js 16, React, and TypeScript, connected to Django through same-origin `/api/v2/` requests. The active UI preserves the supplied Playo artwork, typography, dark presentation, hero, floating image composition and community sections. Reference snapshots and generated components remain available for design comparison; they are not used to serve the new pages.

The original frontend Git metadata was preserved intact at the repository's ignored `.local-v2/frontend-original-git` directory. Frontend source can now be tracked as part of the parent `version-2.0` branch. No original history was deleted.

## Run locally without Docker

Use the repository's [native setup instructions](../docs/VERSION_2_SETUP.md) to migrate and start the isolated Django backend at `http://127.0.0.1:8000`. This configuration has its own SQLite database, media, and email outbox under `.local-v2`, and does not read production `.env` settings.

Then, from this directory:

```sh
npm ci
npm run dev
```

Open `http://localhost:5173`. Requests to `/api/`, `/media/`, and preserved Django pages are proxied to the backend so session cookies and CSRF work without CORS or browser token storage. Sign in, registration, verification and password recovery are functional. In local mode, verification and password-recovery emails are saved to the backend's local email outbox rather than delivered externally.

Only if Django runs at a different internal URL, add this to `New_Frontend/.env.local` and restart Next:

```dotenv
BACKEND_INTERNAL_URL=http://127.0.0.1:8000
```

Never put database credentials, Google secrets or mail credentials in a `NEXT_PUBLIC_*` variable. Google OAuth and mail configuration belong to Django; see the root setup document. Google buttons appear only when the backend reports that Google is configured. Optional reCAPTCHA is also configured on Django and rendered when required.

## Routes and behavior

| Route | Data and behavior |
|---|---|
| `/` | Admin-editable brand, accent, hero, homepage copy, navigation and footer; published shop/blog content |
| `/store`, `/category/:category` | Product search, category filters and pagination |
| `/product/:id` | Product data/gallery/favorites, configured Stripe checkout or external affiliate link, Amazon freshness/disclosures |
| `/favorites` | Signed-in user's saved products |
| `/blog`, `/blog/:slug` | Published posts and article content; `/news` aliases listing |
| `/contact-us`, `/contact` | Real validated backend contact submission; honest delivery/configuration errors |
| `/editing-hub` | League status/calendar, one weekly and one monthly winner, week/month/season standings, score breakdowns and own scheduled-entry submission/replacement/withdrawal |
| `/events`, `/events/:id` | Existing active events, eligibility status, custom application fields and submission |
| `/applications` | Own applications, confirmed withdrawal, and links to preserved edit/management flows |
| `/account` | Username update, password change, Google linking and preserved full profile/dashboard links |
| `/account/preferences` | Master email switch and newsletter/blog/shop opt-ins; campaign setup is required |
| `/account/orders`, `/account/orders/:uuid` | Private purchase history and webhook-confirmed payment status |
| `/notifications` | Own notifications, unread count, mark one/all read |
| `/login`, `/register`, `/verify-email`, `/forgot-password`, `/reset-password` | Django-backed authentication flows |
| `/community-updates` | Existing active announcements |

Legacy `/admin/`, `/accounts/`, `/dashboard/`, `/editinghub/`, `/shop/`, announcement detail pages, event management, about and legal pages remain Django routes. Authorization is enforced by Django. Stripe checkout/order pages and member campaign preference controls are implemented; campaign authoring uses Django admin. Carts, automatic fulfillment and the Discord bot remain outside this phase. See ../docs/COMMERCE_EMAIL_SETUP.md. League calculations and provider collection run in Django jobs, never from a page refresh.

## Development structure

- `app/layout.tsx` and `components/platform/site-shell.tsx`: shared layout, theme and session state.
- `components/platform/home.tsx`: supplied homepage composition with dynamic content.
- `components/platform/catalog.tsx`: product and blog workflows.
- `components/platform/auth.tsx`: account, authentication and notification settings.
- `components/platform/community.tsx`: contact, events, applications, notifications and Editing Hub.
- `components/platform/league.tsx`: league status, standings, single-winner showcases and authenticated entry workflows.
- `lib/league-view.ts`: league API types and display helpers that preserve missing data and distinguish /100 scores from league points.
- `components/platform/ui.tsx`: reusable UI, safe rich-text rendering and optional CAPTCHA.
- `lib/api.ts`: fetch, CSRF, error normalization, resource loading and API types.
- `app/platform.css`: reusable theme variables, page styles and responsive behavior.
- `app/[...slug]/page.tsx`: dynamic routing, no fixed export list.

Rich text from the backend is converted to an allowlist of React elements. Inline HTML, scripts and event attributes are not injected. Mutation requests include CSRF; authentication uses backend session cookies. The notification badge checks periodically while the tab is visible and refreshes after reading notifications.

`components/generated`, `reference`, `lib/site-pages.ts`, `public/replica.js`, and import scripts are historical design inputs. The active frontend never loads the old Webflow/jQuery runtime or demonstration form/cart handlers. Do not run `npm run replicate` or `npm run convert-reference` on active pages without reviewing their generator output; they belong to the original reference import workflow.

## Checks and production build

```sh
npm run typecheck
npm run test:league
npm run build
npm run verify
```

`verify` is a read-only HTTP smoke test against the running frontend and Django API. It checks page routes, local artwork, public APIs, private endpoint access and CSRF. Override its origin with `FRONTEND_URL`. It does not replace backend tests or browser testing of authenticated flows. The historical 24-page reference verifier is retained as `verify-reference` and is not an acceptance test for Version 2.

The league page reads `/api/v2/league/status/`, `standings/?period=week|month|season`, `winners/`, and authenticated `entries/me/`. Its submit, replace and withdraw actions use session cookies and CSRF. Read-only standings refresh every minute while the tab is visible; already-entered form values survive background refreshes. A client countdown is informational: backend flags and timestamps control eligibility and locking. When disabled, uncalibrated, waiting for data, canceled, or running an exhibition, the page displays those states instead of inventing scores or winners. Scores, points, baseline disclosures, and winner periods come from Django. Google/platform credentials remain server-side. Tests exercise missing-versus-zero metrics, score units, authoritative entry gating, cutoff boundaries, and exceptional-state wording.

The production build uses `output: 'standalone'`; it is not a static export. Docker copies `.next/standalone`, `.next/static` and `public` into the runtime image and runs `node server.js`. `npm start` invokes Next's production command on port 3000; for deployment use the standalone entrypoint as documented by Next. Frontend Docker/Compose configuration is retained at the repository level for later use; current local evaluation does not require Docker.

