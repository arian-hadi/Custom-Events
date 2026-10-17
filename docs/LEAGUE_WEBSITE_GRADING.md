# Website-history grading — 16 October 2026

New automatic scoring version: `round_cohort_v2`. This changes the edit score, not the placement points schedule or monthly totals. No production deployment or data changes.

## Three inputs

1. **Like rate (50%)**: lifetime likes divided by lifetime views.
2. **Website performance (30%)**: current likes divided by the median likes of the editor's latest 1–5 distinct eligible finalized website edits. Use 1 if only 1 is available, 2 if 2 are available, and so on. The denominator has a floor of 1; the ratio is capped at 5×.
3. **Total views (20%)**: lifetime views, replacing total likes for this component.

Each measured input is compared with the other eligible entries in that round. Its component score is `100 × (number below + (number tied − 1)/2) / (number compared − 1)`. A single comparable value gets 50; tied values share the mid-rank score. This remains a relative ranking model: a 2× improvement does not automatically mean a specific fixed component score. It depends on the other returning editors' ratios.

**Debut:** in the first-ever V2 competition week, the performance component is **85/100**. At 30%, that contributes **25.5** to the edit score. Admin → League settings → First competition week can change this to 90 (27 overall at 30%), or another value between 0 and 100. Debut editors still earn their like-rate and views components normally. This is not an extra league-points award, a monthly catch-up bonus, or a guarantee of a high placement.

The debut state is frozen at activation and displayed on the weekly table and score breakdown. It does not renew after month/year changes, changing platform, missing closing data, disqualification or an exhibition. A pre-start withdrawal without participation does not consume it. A returning editor without usable finalized history gets neutral 50/100 instead. Debut/neutral editors are excluded from the measured performance-ratio comparison sample.

## Worked example (synthetic, not calibration evidence)

Prior amounts below are **likes from saved closing snapshots**, not previous scores or league points.

| Editor | Prior saved likes | Median | Current likes | Current views | Like rate | Performance ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | 100, 200, 300 | 200 | 400 | 4,000 | 10% | 2× |
| B | 200, 300, 400 | 300 | 300 | 6,000 | 5% | 1× |
| C | 100, 300 | 200 | 100 | 2,000 | 5% | 0.5× |
| D | 150, 250 | 200 | 600 | 12,000 | 5% | 3× |
| E | None; debut | — | 300 | 3,000 | 10% | Debut 85/100 component |

| Editor | Like-rate score | Performance score | Views score | Weighted edit score | Placement | League points |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E | 87.5 | 85 | 25 | 74.25 | 1 | 25 |
| A | 87.5 | 66.666… | 50 | 73.75 | 2 | 20 |
| D | 25 | 100 | 100 | 62.5 | 3 | 16 |
| B | 25 | 33.333… | 75 | 37.5 | 4 | 13 |
| C | 25 | 0 | 0 | 12.5 | 5 | 11 |

For E: `87.5 × 0.50 + 85 × 0.30 + 25 × 0.20 = 74.25`. Only finalized placement points count toward monthly/all-time totals. There is no 25-participant limit.

## Frozen website history

- Use prior result revisions available before the new round's Monday start. Select the newest five distinct eligible edits by competition week, across the member's platforms.
- Read real likes/views from each result's saved closing snapshot. Never fetch old videos again to update that baseline, and never use channel-wide comparison snapshots. Providers are still needed for the current submitted video's lifetime likes/views and channel ownership.
- Scored exhibition results count as history; they award no league points. Missing/unfinalized, disqualified or canceled results do not supply a baseline. Exclude the current video and known shared underlying content; repeated videos/cross-posts supply at most one history item.
- Keep source result IDs, source snapshot IDs, median, sample count and debut status. Later corrections or engagement changes cannot silently replace an activated baseline. An audit correction to an old round is used by future rounds only if known before their start.
- Legacy V1 top-three records are not imported as V2 wins or fabricated metric history. Frozen old scoring versions retain their likes-popularity model and original baseline rules.

## Local rollout

1. Start Docker Desktop, then run the existing development Compose stack; its migration service applies `edithub.0029_website_history_grading`. Alternatively run `python manage.py migrate` with the project's intended local settings/database.
2. League settings defaults to debut 85. New scheduled rounds automatically use the revised version; weights and placement awards remain configurable.
3. Already scheduled rounds keep their versions. For each future round that should adopt the change now, open **Admin → Competition weeks → Operations → Apply current league settings to this future round** and provide a reason. The administrator, old/new versions and reason are logged. Running it again with the same settings does not duplicate the upgrade. Live or finalized rounds cannot be switched.
4. Keep the league worker running. Its channel-history discovery step now skips V2 rounds; legacy rounds retain their old collector behavior.

From the repository root, after Docker Desktop is running, explicitly apply the migration and start the development stack:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml run --rm migrate
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml up -d
```

These commands use the existing local database volume. No database reset or new secrets are required.

## Limits

The 50/30/20 weights, 85 debut incentive, median/floor/cap and within-round percentiles are configurable/versioned launch choices, not empirically validated fairness guarantees. Older edits and platforms are not independently normalized. Very small comparison groups can produce coarse scores; a sole returning editor gets a neutral percentile of 50 even when their measured ratio is high. This rule is disclosed, not hidden behind the bonus.

Separate accounts cannot automatically be recognized as one person; ownership review is still needed to deter repeated-debut abuse. Provider IDs and reviewed content keys cannot identify every reupload. Missing provider data remains pending; no weekend counters, made-up historical engagement or missing-as-zero substitutions are used.

## Verification

- 165 focused backend tests pass, including the existing league lifecycle, cutoffs, monthly/year boundaries, providers, notifications, API and admin suites. New cases cover views scoring, the configurable debut component, 1–5 saved history items, duplicate historical videos, corrections known before/after activation, exhibitions, cross-platform history, retries and audited prospective upgrades.
- 64 frontend tests pass, including score-breakdown labels, 25.5 debut contribution, saved-history explanations and legacy likes labels. TypeScript and the Next.js production build pass.
- Migration `0029` applies successfully in the isolated SQLite test database; the Edithub migration drift check is clean. A full-project drift check separately reports `django_summernote.Attachment.id`; no dependency migration was generated or changed.
- Docker's local engine was unavailable during this task. The migration and future-round upgrades have not been applied to the local website database. No production data, deployment or push was performed. Live browser verification remains outstanding.
