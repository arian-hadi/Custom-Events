# Editing league implementation plan — Version 2.0

Updated: 11 October 2026. Branch: `version-2.0`.
Current scope: one open monthly league, supported by weekly competitions. This supersedes the earlier annual proposal. Historical records remain intact; no production cutover is authorized.

## 1. Open monthly participation

Each UTC calendar month is a fresh league season. Approved, verified editors can join throughout the year; there is no annual registration, qualification, tournament or final. A member joining mid-month starts with zero monthly points and no official placement until an eligible finalized result exists. There are no catch-up bonuses. There is no separate registration window beyond weekly entry deadlines.

All finalized weekly league points count. No best-N rule, monthly bonus points, judges, participant reviews or website voting. Previous months, wins and profile achievements remain archived; career totals are separate from this month's leaderboard. A reset is a new month filter, not deletion or zeroing of past records.

The automatic league is opened through Admin → League settings. Its worker keeps four future weeks scheduled and creates immutable starter rules without manual calibration or weekly setup. Real provider access and verified editor channels remain required. Advanced calibrated-reference scoring remains available separately. See [automatic operation](AUTOMATIC_LEAGUE_UPDATE.md).

## 2. Weekly calendar and intake

- One entry per editor per competition week across supported platforms.
- Entries submitted during the current UTC week queue for the following Monday. Replacement/withdrawal is allowed until that target Monday 00:00 UTC. Display the target week and entry deadline separately from the scoring cutoff.
- Provisional scoring runs `[Monday 00:00, Saturday 00:00)` UTC. Saturday 00:00 is excluded. Saturday and Sunday show frozen results, or an honest finalizing/missing-data state.
- Older edits are eligible and their existing lifetime likes and views count. Engagement is never reduced to growth since entry or activation.
- The same underlying edit may enter once per competition month, and may enter again in a later month (updated 11 October 2026). The month is the one containing the target week’s Friday scoring date, not the submission date. Canonical platform video IDs prevent alternate-URL repeats. A reviewed shared content key identifies known cross-posts. Withdrawn pre-activation entries may be replaced; activated entries stay locked, including disqualifications.
- Practical limit: provider IDs do not identify every reupload or unknown cross-post. There is no perceptual duplicate detector. No originality checkbox is required. Enforce canonical IDs and known shared content keys within the month at the database level, retain ownership/provenance, and use audited moderation for discovered duplicates. Do not claim all reuploads are detected automatically.
- V1 history stays archived. Old top-three finishes are not reclassified as first-place wins. V1-to-V2 eligibility remains a policy decision; there is no automatic transfer of legacy points or awards.

## 3. Count existing engagement and freeze totals at the cutoff

Store timestamped snapshots of the video's current lifetime likes and views. Live scoring uses the latest valid totals; final scoring uses the eligible closing snapshot. **Do not subtract the totals present at submission or Monday activation.**

Example: an older edit already has 8,000 likes when submitted. It has 8,200 likes at the Friday cutoff. Use **8,200 likes**, not only the 200 new likes. If its total remains 8,000, those 8,000 still count. Likes feed the scoring formula; they are not directly added as 8,000 league points.

An old edit earns its league points in the round it enters, not retroactively in its publication month or year. Current cumulative totals preserve earlier engagement without claiming to reconstruct the video's original first-week performance. Historical first-week totals are unknown unless trustworthy snapshots already exist.

Every entry has the same finalization deadline, but older entries have had longer to collect interactions. The bounded popularity component limits its weight, but the current automatic policy does not correct for edit age; do not describe lifetime totals alone as age-neutral.

Proposed collection policy:

- Collect totals at submission and poll hourly during the active week, more frequently near the closing boundary.
- Opening snapshots support provisional display and anomaly checks; they are not subtraction baselines or prerequisites for an otherwise valid final snapshot.
- Use the latest successfully completed snapshot **before Saturday 00:00**, with a proposed maximum age of 15 minutes at cutoff.
- A response completed after cutoff is not a valid closing snapshot: cumulative counters cannot reveal exactly which interactions occurred before cutoff.
- Freeze scoring at cutoff even if publishing the results is delayed for data validation.
- Show `data_pending` or `finalizing` when required snapshots are missing. Never substitute zero, fabricated values or weekend totals.
- Retry collection while the round is open. After cutoff, missing historical data cannot be repaired by fetching new cumulative totals. Use a recorded exception decision; cancel an affected round if fair results cannot be established.

Counter decreases can reflect platform corrections. Preserve raw observations, use the latest valid nonnegative lifetime totals before cutoff, and flag substantial anomalies. Do not select the historical maximum to hide legitimate corrections, and reject invalid negative counters. Missing counters remain missing, not zero. Provider corrections and suspicious traffic require a published exception policy.

## 4. Automated weekly score

### Current automatic starter policy

Updated 16 October 2026: new automatic rounds use `round_cohort_v2`. Frozen V1 versions retain their original likes-based popularity and channel-history rules. See [website-history grading](LEAGUE_WEBSITE_GRADING.md) for rollout and worked examples.

| Component | Weight | Input in the new automatic version |
| --- | --- | --- |
| Like rate | 50% | Current lifetime likes / current lifetime views |
| Website performance | 30% | Current likes / median likes of the last 1–5 distinct eligible finalized website submissions, capped at 5×; baseline denominator floor 1 |
| Total views | 20% | Current lifetime views, not likes |

History uses the saved closing snapshot of each previous result, not old edit scores or awarded league points. Use the latest revision that existed before this week's start. A later correction cannot silently change a baseline already frozen for another week. Source result and snapshot IDs are retained. Scored exhibitions are experience; missing, disqualified, canceled, unfinalized results, duplicate underlying edits and the current edit are excluded. No channel-wide history fetching or age/format filtering is used for this version.

First-ever V2 competition week: a clearly labeled **Debut** performance component of **85/100**, configurable in League settings (90 is supported). At the default 30% weight, this contributes **25.5/100** overall, not 85 overall points or extra league points. It applies once to the editor's first participating week across months/platforms. Subsequent participation with no usable finalized history receives the neutral 50/100 performance component; missing data, disqualification and exhibitions do not renew the debut bonus. Withdrawn entries that never participated do not consume it.

Each measured component uses mid-rank percentile: `100 * (number below + (number tied - 1) / 2) / (sample count - 1)`. One comparable value maps to 50. Debut and neutral-history editors are excluded from the measured performance-ratio sample. They still participate in the like-rate and total-views comparison. Missing/invalid provider counters stay pending; disqualified entries are excluded. Scores and debut metadata are persisted with each finalized result.

This is an initial, **unvalidated** policy. It has no independent normalization for platform or video age. Real observations determine component ranks, which can move as other entries receive valid snapshots. The 85 debut score is a deliberate participation incentive, not measured performance. The default minimum remains five entries. No `calibrated=True` claim is made for generated starter versions.

### Advanced calibrated-reference policy (retained)

The following describes the existing `linear_knots_clamped_v1` option. Its pilot/reference requirements apply when selecting that advanced policy, not to opening the automatic starter league.

Each component becomes a score from 0 to 100 before weighting:

`weekly_score = 0.50 * response_score + 0.30 * improvement_score + 0.20 * popularity_score`

| Component | Weight | Input |
| --- | --- | --- |
| Audience response | 50% | Adjusted lifetime likes-to-views ratio at the scoring snapshot |
| Relative performance | 30% | Lifetime likes compared with the creator's other edits observed at a comparable age |
| Popularity | 20% | Lifetime likes at the scoring snapshot |

Do not add raw likes, views and percentages together. Do not include followers, website upvotes, comments, attendance streak multipliers or judging in the initial formula. Views are the denominator for audience response, not a separate unlimited points source.

### 4.1 Audience response and small samples

Use smoothing so a few likes from a handful of views do not dominate:

`adjusted_like_rate = (total_likes + prior_rate * prior_views) / (total_views + prior_views)`

Illustration only: `prior_rate = 0.05` and `prior_views = 1000` make 8 likes / 20 views approximately 5.7%, and 800 likes / 10,000 views approximately 7.7%.

Calibrate the prior separately for each platform and supported video format using pilot observations; 5% and 1,000 are not established production constants. Likes/views is a response proxy, not the fraction of unique viewers who approved: views can include repeat plays, and reactions can lag views.

### 4.2 Relative performance for new and older edits

Compare cumulative likes with other edits from the same creator, platform and format observed at a comparable age. Do not compare a six-month-old entry directly with a baseline of five-day-old videos, or claim that current lifetime totals reveal first-week performance.

Proposed baseline: the median of the latest eight eligible comparison videos, requiring at least five distinct videos with trustworthy observations in the same age band. Collect comparison data only through supported provider access. Use at most one observation per comparison video; select the observation closest in age to the entry's projected age at Friday cutoff, breaking equal-distance ties with the earlier observation. Only observations already available at activation may be used. Exclude the current entry, duplicates, disqualified videos and incomplete observations. Freeze the sample and baseline when the round activates.

Proposed age bands for pilot evaluation: under 7 days, 7–29 days, 30–89 days, and 90 days or older. These are unvalidated defaults; broad bands still contain age differences. Version their boundaries after calibration. Assign the entry's band using its projected age at cutoff and keep it fixed throughout the live round.

`relative_performance = total_likes / max(baseline_median_likes, baseline_floor)`

Use a platform-specific baseline floor and an improvement cap, calibrated in the pilot. Cap this input before its conversion to a component score. Do not assume a zero baseline is valid or let a near-zero denominator create an unlimited bonus.

Until five comparable observations exist, assign a neutral relative-performance score of 50/100 and disclose it. The entry remains eligible: its existing engagement still contributes to response and popularity. Do not invent missing age-matched history or penalize an old video for lacking a recorded first-week snapshot. The internal `improvement_score` field means relative performance here, not growth during the competition week.

Keep baselines under the editor's verified identity. Switching accounts or hiding previous submissions must not reset league history. Review intentional baseline suppression as an exception risk; this formula cannot automatically eliminate strategic underperformance.

### 4.3 Component scales and platform comparison

Use platform/format-specific reference distributions from the pilot to convert each input into a percentile score from 0–100. Calibrate response and popularity mappings by the same fixed video-age bands used for baseline selection, so older videos are not automatically compared against newly published ones. Freeze these reference distributions and their tie/interpolation rules in the scoring version before official rounds begin. Bound values beyond the reference range at 0 or 100.

The pilot must include both new and old edits. Missing creator history can use the neutral relative-performance score, but missing platform/age reference data requires calibration before official scoring. Do not silently reject old edits to avoid this requirement or claim age adjustment removes every exposure advantage.

Do not rely on percentiles from a tiny current-week platform subgroup, where one or two entries could receive misleadingly high scores. Use consistent reference mappings for live and final scores.

The proposed public format has a **single combined weekly winner**, rather than two platform winner cards. Platform-specific reference mappings support that format, but do not prove perfect cross-platform fairness. The pilot must check this explicitly. If one platform lacks sufficient calibration data, launch with the supported platform and disclose its scope; do not improvise a new conversion during a live round.

Round scores should be reproducible with decimal arithmetic, stored input snapshots, baseline snapshots and scoring-version identifiers. Round only for display; use stored precision for ranking.

## 5. Edit scores and league points

The edit score ranks eligible weekly entries. Placement awards league points:

| Placement | League points |
| --- | ---: |
| 1st | 25 |
| 2nd | 20 |
| 3rd | 16 |
| 4th | 13 |
| 5th | 11 |
| 6th | 10 |
| 7th | 9 |
| 8th | 8 |
| 9th | 7 |
| 10th | 6 |
| Other eligible finishers | 2 |
| Missing or disqualified entry | 0 |

Missing provider counters are never fabricated as zero: unresolved required data blocks normal finalization. An audited cancellation/disqualification can resolve an exception with zero points. The existing configurable minimum is five eligible entries; smaller rounds are exhibitions without an official winner or points. This minimum remains an operational default requiring rule review.

Exactly first place wins **Edit of the Week**. Keep the full standings table, but never a top-three winner showcase. Weekly ties compare full-precision edit score, audience response, then relative performance. The final fallback is a deterministic hash draw using the round's recorded seed and entry ID; the seed freezes at activation. Retries and corrections reuse it. No follower counts or submission-speed priority.

## 6. Monthly standings and Editor of the Month

Monthly points sum every effective finalized weekly points award assigned to that month. A week belongs to the month and year of its Friday scoring date. A July 31 Friday counts in July even if results publish August 1. A December-starting week with a January Friday counts in January.

20 + 11 + 25 + 16 = **72 monthly points**. The next month begins at zero without altering those four results.

The highest monthly total wins **Editor of the Month**. There is no separate monthly video competition and no points bonus for the title. A single winner card shows the editor and monthly points. It may show the editor's highest-scoring eligible edit, explicitly labeled **Representative edit**. Selection compares full-precision edit score, response score, earlier round date, then entry ID.

Monthly ties compare points, number of first places, number of second places and so on, then the sum of finalized edit scores. Exact remaining ties use a deterministic hash draw of editor ID and the recorded monthly seed. Before finalization exact ties may share rank; finalization stores one complete ordering and one winner. Frozen standings and the winner use that same ordering. Corrections reuse the seed.

Finalize only after month-end and after every included week is finalized, exhibition or canceled. No qualifying results means no winner. Display the last finalized winner while this month's standings develop, with a finalizing indicator when the previous month remains unresolved.

## 7. Persistence, automation and historical compatibility

Weekly revisions, metric/baseline snapshots, results and effective points awards remain authoritative. Row locks, uniqueness constraints and idempotent finalization prevent duplicate awards. Later provider totals, votes and profile changes cannot recompute frozen scores. Explicit staff corrections require permission, a reason and a new retained revision; dependent monthly standings/awards are revised without erasing history.

`league_tick` processes weeks and months only. Annual API standings are rejected and annual finalization is retired. Existing `LeagueSeason` records remain internal calendar-year grouping/locking containers to preserve foreign keys, not active competitive seasons. Existing `SeasonAward` records remain read-only archives; the worker, notifications and monthly corrections do not create or rewrite them. No destructive schema migration is required.

Official metrics must be genuine observations completed and received before cutoff and within the versioned freshness window. A delayed weekend request cannot reconstruct Friday counters. Missing data remains pending until an explicit, audited exception decision. Provider polling, calibration evidence, server-side ownership checks and immutable baselines remain as implemented.

## 8. V2 interface

- Default: this week's league standings. Monthly league is second and All-time points third. Past weeks and months are selected beside the table with calendar-year navigation.
- Weekly provisional/frozen standings and a single Edit of the Week card.
- Single Editor of the Month card, with a clearly labeled optional representative edit.
- Member queued entry, target week, deadline, component score breakdown and monthly points.
- Distinct Edit score and League points labels; the All-time table sums finalized V2 weekly awards separately from the monthly league.
- Honest empty, loading, exhibition, data-pending, finalizing and frozen states.
- No annual competition, qualification, finals or annual leaderboard messaging.

## 9. Calibration and provider requirements

Weights remain configurable with the initial proposed 50/30/20 split. Advanced reference distributions are intentionally empty by default; automatic starter mode does not require or fabricate them. Synthetic test scales are not pilot evidence. Smoothing, age bands, minimum cohort size, baseline floor/cap and freshness tolerance require review against real provider observations. Missing history uses the disclosed neutral baseline, never invented historical metrics. Cross-platform comparisons are not proven fair merely by normalization.

See [League operations](LEAGUE_OPERATIONS.md) and [Provider setup](LEAGUE_PROVIDER_SETUP.md). YouTube/TikTok access, quotas and per-editor TikTok authorization remain operational requirements. Real pilot review is required before claiming validated reference-based scoring. Local automatic competition is enabled; production data is unchanged.

## 10. Acceptance

Focused isolated tests cover UTC intake/cutoff, Friday month/year attribution, late joining at zero, monthly reset without deletion, the 72-point example, lifetime engagement, missing/late snapshots, retry-safe awards, monthly ties and representative selection, audited corrections and preservation of legacy/annual archives. Frontend checks cover monthly default, absence of annual controls, score/point labels and member monthly identity. Latest checks and local activation are recorded in [Automatic league delivery](AUTOMATIC_LEAGUE_UPDATE.md); earlier monthly migration checks remain in [Monthly league delivery](MONTHLY_LEAGUE_UPDATE.md).

### Monthly identity rollout — 11 October 2026

Migration `0028_monthly_entry_identity` backfills each historical entry’s `competition_month` from its week’s Friday date, then replaces lifetime video/content uniqueness with monthly uniqueness. One editor per week remains enforced. Withdrawn pre-activation entries release the slot; disqualified entries retain it. Finalized snapshots, scores, awards and prior scoring versions are unchanged. New intake follows `one_per_month` even for an already scheduled round whose frozen scoring metadata records the older `one_v2_result` policy; the public status endpoint reports the current intake policy separately. New scoring versions use `one_per_month`. This is an intake-rule change, not a recalculation of results.


## October 13: live display, career points and notifications

- Standings tabs are **Weekly league** (default), **Monthly league**, then **All-time points**. Weekly rows include an external **View edit** link and accessible YouTube/TikTok icons.
- The backend returns `projected_points` for provisional placements, using that week's versioned placement schedule. `points` remains null until awarded. The UI labels estimates **Projected**; missing metrics/placement remain unknown. Estimates may be shown in under-quorum rounds with an explicit qualification caveat; exhibition rounds ultimately award zero. Estimates never enter the award ledger or monthly/career totals.
- All-time standings sum effective, finalized V2 weekly awards across all months and calendar years. Monthly titles/totals are not added again. Corrections replace superseded awards; follower ranks and legacy competition points are excluded. Exact career ties can share a rank; this is a cumulative history table, not a revived annual competition.
- Weekly and monthly winner cards display click-to-load provider players where supported, plus an external link if playback is unavailable. The monthly video remains a clearly labeled representative edit. These cards also appear on the homepage when an official winner exists. No autoplay or invented winners.
- The provider collector checks the complete, qualifying provisional weekly cohort after each collection pass. Each editor gets at most one first-lead notification/email per week, even if they lose and regain first place. Monthly first-lead milestones are similarly deduplicated per editor/calendar month, using finalized weekly points. Public page reads never send mail.
- Finalized weekly result emails are sent once per editor/revision; the weekly win and any newly achieved monthly first place are included in that message rather than sending several emails. Standalone monthly first-lead email remains available when result emails are disabled but ranking emails are enabled. Routine standings changes and the duplicate weekly winner notice stay in-app. Monthly winner emails and audited correction notices remain supported.
- All optional emails respect existing account preferences and the worker's master switch. Pending provisional notices are canceled when the round closes; superseded result emails are canceled on correction. Durable unique notification keys prevent duplicate queueing; SMTP cannot guarantee exactly-once delivery after an ambiguous network failure.
- OTP/reset, admin alerts, member activity and campaign emails share a dark branded HTML wrapper with a plain-text alternative. Existing unsubscribe links and security-mail behavior remain intact. No new environment variables or migration are required for these presentation/notification changes.

Verification includes backend projection/award separation, missing metrics, under-quorum estimates, cross-year career aggregation, corrected awards, weekly/monthly first-lead deduplication, opt-out and HTML escaping; frontend and local desktop/mobile checks cover tabs, points, links, icons and player activation. Player URLs are checked using isolated browser fixtures, not a claim that every remote video permits embedding. Scoring calibration and actual provider access remain the requirements described earlier in this plan.


## Standings archives and existing title presentation

Round centre and its separate history list have been removed. The standings toolbar provides Week / Month selectors and calendar-year navigation using real scheduled history, with future weekly rounds omitted from the results picker. A compact current-competition countdown and next-entry deadline remain above the table even when browsing older results. Existing `#league-rounds` links resolve to this area for compatibility.

The V1 `EditorTitle`, `UserTitleUnlock`, user selection and approved-channel fallback remain authoritative. V2 table rows, winner cards, the member dashboard and profile show the active, unlocked selection and its rarity; this is identity presentation, never a follower-based rank or a change to league scoring. Users choose their available titles under **Account → Profile**. Titles can still be maintained/granted using the existing admin tools; no titles are fabricated or automatically upgraded by this UI change.

Legendary titles use a gold light sweep and Epic titles use a purple gradient; Rare and Ordinary retain calmer treatments. Visual references: [React Bits Shiny Text](https://reactbits.dev/text-animations/shiny-text) and [Gradient Text](https://reactbits.dev/text-animations/gradient-text). The implementation is native CSS in a shared React title component, without a new runtime dependency. The Editing Hub header action has a subtle sheen, hover lift and arrow movement. Reduced-motion preferences disable animation, and forced-colors mode restores readable text.

Checks: 46 focused backend API/profile/dashboard tests, 58 frontend tests, TypeScript checking, and local browser coverage for current timer, archive week/month/year switching, actual-title display, header motion, mobile/tablet layout and reduced motion. Browser title/history fixtures are isolated to the test browser; no real user grants, historical results or point totals were changed. No migrations or new environment settings are required.
