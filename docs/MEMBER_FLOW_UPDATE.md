# Member flow changes — 11 October 2026

Local changes on `version-2.0`. No deployment or production data changes.

1. Main navigation shows **Dashboard** (`/account`) instead of Home for signed-in members. Guests retain Home.
2. Registration already sends a verification code in its backend request. The signup redirect now shows the destination as text and asks only for the code. Resending keeps the code form open; only successful verification exposes Continue to account. Direct verification visits without an email still provide an email field for recovery. SMTP errors remain explicit rather than reporting success.
3. Store filters no longer show a currency chooser or the legacy **1.0 Merges & Figures** category. Existing products and their original prices/currencies are retained. Price filtering/sorting remains available where a single currency is known; mixed currencies are not compared as equivalent amounts.
4. **Admin → Platform API → Website settings → Branding** has main and secondary accent color pickers. Refresh the website after saving. The secondary color is blended into button gradients; the main accent controls highlights and glows across V2. Uploaded artwork retains its original colors. No environment variables are needed.
5. A member can create one active editor application: **YouTube or TikTok**. Pending/accepted applications without a removal request block another application across platforms. V2, legacy creation, and admin activation paths enforce the rule; pre-existing historical records remain available. Dashboard no longer invents an unapplied card for the other platform.
6. League intake no longer requires an originality checkbox. Database constraints reject canonical video identities and known shared content identities repeated within the target competition month. The month is determined by the round's Friday date. A later month permits the edit again; one entry per editor per week still applies. Withdrawn entries release their slot; disqualified entries do not. Unknown cross-posts/reuploads still need moderation.

## Local database changes

- `platform_api.0002_sitesettings_secondary_accent_color_and_more` adds the secondary accent.
- `edithub.0028_monthly_entry_identity` backfills Friday-based month identity and replaces lifetime uniqueness with monthly uniqueness. Stored results, points, snapshots, awards and historical scoring versions are preserved. Existing scheduled scoring versions remain frozen; the new intake policy is separately reported as `repeat_policy: one_per_month` in league status.

Both migrations were applied to the local Docker V2 database. No `.env` changes or Docker image rebuild are required for these changes in the bind-mounted development setup.

## Verification

Focused backend coverage checks automatic OTP delivery, verification using the signup session, cross-platform application rejection, admin activation, month/year identity, alternate URLs, known cross-posts, withdrawal/disqualification, historical backfill and preserved awards. Browser checks intercept account writes and do not send real emails or submit real entries.

Completed: 226 backend tests, 55 frontend tests, TypeScript checking, Django system checks and migration drift checks for project apps. The local headless browser flow passed signup → OTP → resend → verification, guest/member navigation, desktop/mobile shop cleanup, two theme variables, existing/new platform application states, and the monthly entry form without a checkbox. Actual SMTP delivery was not triggered by browser testing.


## Global navigation — 14 October 2026

The primary navbar now highlights the active section with the configured main accent, a persistent underline and a subtle background. Hover/focus adds a short underline/lift transition; the mobile menu opens with a short fade/slide and uses a vertical active marker. Reduced-motion preferences disable these animations. `aria-current` exposes the current destination to assistive technology.

The active link follows Next.js client navigation and browser Back/Forward, matching the most specific local destination. Product/category, blog aliases, editor application and nested event routes retain their parent section highlight. Home only matches the homepage. Signed-in members retain Dashboard in place of Home; notifications and account controls also have active styling. External links do not become active based on their path alone. The mobile menu closes on selection, route change or Escape, returning focus to its toggle on Escape.

Validation: TypeScript and 58 frontend tests passed, plus targeted route-matching checks and desktop/tablet/mobile browser checks. Docker was stopped during final verification, so browser checks used the real Next.js frontend on a temporary port with isolated API responses; no database writes, emails or production changes occurred. No environment changes or migrations are needed. The development Docker stack picks up these source changes when restarted.
