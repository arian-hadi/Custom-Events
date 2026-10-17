# Monthly league delivery — 10 October 2026

Superseded activation/setup notes: [11 October automatic league update](AUTOMATIC_LEAGUE_UPDATE.md) opens the local league and replaces manual scheduling/calibration prerequisites with disclosed starter scoring. Historical statements below describe the 10 October delivery.

Implemented locally on `version-2.0`. The authoritative rules are in [the implementation plan](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md). Existing unrelated V2 work and competition history have been preserved. No deployment, push, production data changes, live scoring enablement or database migration was performed.

## Result

- The active competition is an open calendar-month league supported by weekly rounds. There is no annual registration, qualification, final or competitive leaderboard. The next month starts at zero; every eligible finalized weekly result counts in its Friday's month. Joining late adds no catch-up points.
- Weekly intake continues to queue for the following Monday, with one editor entry across supported platforms. Monday–Friday provisional scoring uses lifetime engagement. Saturday 00:00 UTC closes scoring; genuine pre-cutoff observations are required. Missing provider data stays pending instead of becoming zero or weekend engagement.
- The existing configurable 50/30/20 edit-score model remains separate from the placement points schedule: 25, 20, 16, 13, 11, 10, 9, 8, 7, 6, then 2 for other eligible finishers; missing/disqualified entries receive no points. No judges, participant reviews, website votes or follower rankings are involved.
- Exactly first place receives Edit of the Week. Accumulated monthly points select one Editor of the Month, with no bonus points or separate monthly video contest. Ties use the documented recorded-seed ordering. Finalized monthly standings now reuse the persisted winner ordering, including after audited corrections.
- The Editing Hub defaults to monthly standings, retains the full weekly table and calendar archives, and presents one card for each award. Monthly videos are explicitly representative edits. The member summary uses monthly points/rank; career points have a separate label. Queued entries show their target week and deadline, live entries expose score components, and finalized entries are labeled finalized. Cutoff status becomes pending immediately even before the next worker tick.
- The worker and notifications process weekly/monthly competition only. `LeagueSeason` remains an internal calendar-year grouping/lock for foreign-key compatibility. Existing `SeasonAward` rows remain read-only historical records. Annual finalization rejects new calls; corrections do not rewrite archived annual awards. Legacy top-three results are not converted into V2 wins.

## API changes

- `league/status/`: `month` replaces the annual `season` display object.
- `league/rounds/`: `years` replaces `seasons`; rounds expose `calendar_year`.
- `league/standings/`: accepts `week` or `month`; `season` returns 400. Monthly states distinguish accumulating, finalizing and finalized.
- `member/dashboard/`: monthly standing replaces `season`/`season_standing`; an editor without a result has zero monthly points and no rank.
- `league/winners/`: monthly winner includes `award_title` and `representative_edit`, with weekly/monthly period states. The latest finalized winner stays visible during the next period.
- `league/entries/me/`: includes available provisional score components without private snapshot/baseline audit fields; league points remain unset until awarded.

## Checks

- Django regression suite: **383 tests run, one platform-specific skip, no failures**, using the isolated test database and `prime_project.test_settings`. Includes API/authentication, league core/admin/calibration/collection/history/providers, notifications, shop integrations and worker behavior.
- League coverage includes cutoff exclusivity, genuine closing snapshots, month/year attribution, 72-point accumulation, late joining, reset without deletion, lifetime engagement, repeated finalization, single-winner ties, audited correction, historical preservation and immediate cutoff presentation.
- Frontend: TypeScript check and **51 component/behavior tests**. Monthly/frozen/pending labels, winner presentation, score/point distinction and member identity are covered.
- Local headless-browser checks at desktop 1440px and mobile 390px verified monthly default, single winner cards, representative-edit labeling, queued entry, score breakdown, frozen/missing-data states and no horizontal page overflow. Every API request was intercepted with synthetic fixtures; no real submission, email or database write occurred. Screenshots and the helper are in ignored `.local-v2/`.
- Migration dry run for `accounts`, `edithub`, `notifications`, `platform_api`, `events` and `shop`: no changes. A repository-wide dry run separately reports existing third-party `django_summernote` attachment-ID drift; this update does not generate or modify that package migration.

## Remaining operational requirements

The weights and smoothing/reference choices are proposed calibration settings, not proven fairness. Official operation still requires representative real provider observations, reviewed platform/format/age references, documented calibration approval, provider credentials/access and scheduled future weeks. YouTube quotas and TikTok per-editor authorization need operational verification. See [provider setup](LEAGUE_PROVIDER_SETUP.md) and [operations](LEAGUE_OPERATIONS.md).

Canonical platform IDs reject alternate URLs for the same upload. Reviewed shared content keys can link cross-posts, but arbitrary reuploads cannot always be recognized automatically. The 11 October update removes the originality checkbox and scopes automatic duplicate checks to the competition month. Audited moderation remains available for unrecognized reuploads; no claim of universal video fingerprinting is made.

The existing configurable minimum of five eligible entries remains: smaller rounds are exhibitions with no official winner or points. Review that operational rule before launch. An outage that misses genuine closing snapshots needs an explicit audited resolution; a later fetch cannot recreate Friday history.
