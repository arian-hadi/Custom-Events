# V2 member dashboard

The member overview is `/account`. It uses the existing V2 website shell,
typography, configurable accent colour, dark panels, buttons, and spacing.
The frontend fallback accent matches the backend default (`#ef233c`).

## Member journeys

- `/account`: identity, actionable updates, league, latest edit, combined
  applications, notification preview, recent orders, and secondary shortcuts.
- `/account/profile`: current display identity and access to the existing photo,
  editor title, and profile appearance controls.
- `/account/settings`: the existing username, verified email, password, and
  Google connection controls. Successful Google linking returns here.
- `/account/preferences`: optional email and in-app notification choices.
- `/applications`: editor application statuses together with existing event
  applications and their edit/withdrawal actions.
- `/account/orders`, `/favorites`, `/notifications`: existing member pages,
  connected with consistent member navigation.
- `/editing-hub`: V2 league standings and entry management. Dashboard entry
  links target the member's specific entry where available.

## Data and ranking rules

`GET /api/v2/member/dashboard/` is an authenticated, uncached read endpoint.
It composes existing records and serializers; it neither collects external
platform metrics nor sends messages or recalculates competition scores.

The member's rank and league points come from V2 league standings and effective
finalized results. A latest round result uses that round's current result
revision. Follower counts, old ranking positions, and old calculated edit points
are not used as V2 league performance. Missing results stay unknown rather than
becoming fabricated zero scores. No tier or movement history is invented.
Legacy follower-ranking notifications are excluded from this overview's preview;
the unread count still reflects the full inbox, where that history remains available.

The most recently submitted edit provides the creative preview, comparing the
submission dates of league entries and earlier-system edits.
Its source is labelled and its legacy upvotes are distinguished from league
points. The dashboard does not combine the two scoring systems.

Order information uses the existing payment and fulfillment states. The current
order model does not provide a shipping ETA; the dashboard does not invent one.
Internal fulfillment notes and Stripe identifiers are not shown to members.

Only relevant attention items are shown. New members see a useful introduction
and participation links. Orders without activity take little space. Loading,
failed requests, unavailable scoring, and missing media each have explicit UI
states. General promotional discovery content is omitted to keep this overview
focused on the member.

## Layout and references

Desktop uses the width of the existing site container, with competition and
creative work as the primary pair. Mobile follows identity, attention, league,
latest edit, applications, notifications, orders, and quick access in that order.

The information hierarchy draws on [F1 Fantasy](https://fantasy.formula1.com/)
for competition, [Behance](https://www.behance.net/search/projects/video%20editing)
for creative work, and [Riot's progression identity](https://www.leagueoflegends.com/en-us/news/dev/progression-identity-changes/)
for member identity. The visual design uses the existing Transformers V2 site.

## Configuration

This dashboard requires no additional environment variables, credentials,
database models, or migrations. Existing league, payment, email, and Google
configuration still controls those underlying features. Docker verification
remains deferred under the existing project instructions.

## Verification and previews

- Production Next.js build, including TypeScript validation, passed.
- `npm run test:dashboard`: 14 tests passed for presentation, empty states,
  official versus missing results, application statuses, notification previews,
  deadlines, payment states, and access to existing account functions.
- `python manage.py test platform_api edithub --settings=prime_project.test_settings --noinput`:
  49 tests passed, including 10 private dashboard API tests.
- Authentication regression tests passed (34 tests), including the Google-link
  return destination in Settings.
- `npm run verify` passed across 21 routes, 15 assets, the public APIs, private
  access checks, and CSRF checks through the local frontend origin.
- Browser checks covered the authenticated empty dashboard and Settings, plus
  populated presentation fixtures at desktop, tablet, and mobile widths.
  Member content stayed within the viewport. Mobile navigation was corrected
  so a long username cannot hide the menu control. No dashboard console errors
  were reported during the authenticated browser check.
- Full-project `npm run lint` is not clean: imported/generated template code,
  vendor scripts, and Next.js link/image rules still report issues. Focused lint
  on the new member components/helper reports only the project's existing
  plain-anchor and image conventions.

The temporary QA account, credential file, and HTML fixture were removed after
verification. Populated previews contain explicitly labelled **sample test data**;
they are not seeded into the website or presented as real member results.

- [Live empty dashboard, desktop](previews/member-dashboard-empty-desktop.jpg)
- [Live empty dashboard, mobile](previews/member-dashboard-empty-mobile.jpg)
- [Populated layout fixture, desktop](previews/member-dashboard-populated-desktop.jpg)
- [Populated layout fixture, mobile](previews/member-dashboard-populated-mobile.jpg)
