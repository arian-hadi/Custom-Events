# Automatic league — 11 October 2026

**Scoring update, 16 October:** the delivery notes below describe the original V1 starter policy. New rounds now use [website-history grading](LEAGUE_WEBSITE_GRADING.md): views for popularity, last five finalized website submissions for history, and an 85/100 first-week performance component. Existing frozen versions remain unchanged.

The local `version-2.0` site now accepts weekly entries without manually creating scoring JSON or scheduling each competition. Monthly rules and historical records remain intact. Nothing was pushed or deployed to production.

## Everyday use

- Editors: sign in with an approved, verified channel and visit `/editing-hub#league-entry`. One submitted video enters the following Monday's competition. Existing lifetime engagement counts.
- Admin: use `/admin/edithub/leaguesettings/1/change/`. **Open automatic league** controls entry and automatic processing. Normal numeric fields control the 50/30/20 score weights, ten placement awards, other-finisher points and minimum qualifying entries. Defaults remain 25/20/16/13/11/10/9/8/7/6, other eligible finishers 2, minimum 5. Below the minimum, the round is an exhibition without official points/winner.
- Keep `jobs-league` running. Each cycle prepares four future Mondays, collects available creator history, activates due weeks, finalizes closed weeks/months and collects live metrics. No monthly reopening is necessary. The calendar crosses months and years automatically; no elapsed weeks are manufactured.
- Settings changes apply to newly scheduled rounds only, so their first effect may be beyond the existing four-week calendar. Already scheduled and entered rounds retain their rules. Admin changes are recorded by Django's admin log. Corrections of completed results still require the audited correction process.

## What changed in scoring

The prior reference-based model could not run without independently collected, reviewed pilot distributions for every platform/format/age bucket. Those references do not exist merely because a YouTube key is configured.

Automatic starter mode (`round_cohort_v1`) uses real observations from eligible entries in the same competition:

1. Audience response: lifetime likes divided by lifetime views. Two genuine zero counters give zero; likes with zero views remain pending as inconsistent data.
2. Relative performance: lifetime likes divided by the frozen creator median (floor 1), capped at 5. The baseline still requires genuine, previously available, same-platform/format and comparable-age history. Fewer than five comparable videos gives the disclosed neutral component score of 50, not invented history.
3. Popularity: lifetime likes.

For each component, the percentile is `100 × (count below + (count tied − 1) / 2) / (sample count − 1)`. A single comparable value maps to 50; equal values share a percentile. Neutral-history entries receive 50 directly and are excluded from the improvement sample. The weighted result retains the initial 50/30/20 split. Missing and disqualified entries are excluded from provisional component comparisons. Missing closing data prevents normal finalization.

**This is an initial competition policy, not a validated fairness model.** It has no independent platform or video-age normalization, and low-view rates/small cohorts can be volatile. All generated versions keep `calibrated=False` and explicit notes. No pilot distributions are fabricated. Review real outcomes before claiming fairness; the advanced calibrated-reference model remains available and unchanged for existing rounds.

Frozen weekly revisions, closing snapshot requirements, deterministic tie seeds, one weekly winner, Friday-to-month attribution, all-results monthly totals and a single Editor of the Month remain authoritative in the backend. No additional monthly title points are awarded. Retries do not duplicate results or points.

## Provider requirements

Automatic mode accepts YouTube's native `unknown` video-format label instead of requiring manual Shorts classification per video. It accepts TikTok's native `video` label as well. This is explicit scope, not a claim that every YouTube video is a Short.

YouTube still needs a functioning `LEAGUE_YOUTUBE_API_KEY` or the existing `YOUTUBE_API_KEY`. TikTok still needs each editor's authorized credentials; there is no new member OAuth screen in this update. Ownership checks and rate limits remain enforced. The 11 October intake update removes the no-repeat declaration: canonical IDs and reviewed cross-post matches now enforce one entry per edit per competition month automatically, while keeping the one-entry-per-editor weekly limit. Unknown reuploads cannot all be detected automatically.

## Local activation and checks

- Applied additive migration `edithub.0027_leaguesettings_and_more` to the verified local Docker database (`db`, Docker Desktop context).
- Ran `league_ensure --enable`, creating the singleton settings and four upcoming rounds; restarted only `jobs-league` so it uses the new scheduling loop.
- Live local API confirms `enabled=true`, `can_submit=true`, `configuration_ready=true`, `scoring_method=round_cohort_v1`, `scoring_validated=false`. First target week: 12–16 October 2026; entry deadline Monday 12 October 00:00 UTC (03:00 Istanbul).
- The admin switch takes precedence over the old environment switch once saved. `LEAGUE_ENABLED` remains an initial fallback for installations without settings. Later admin changes do not require a Docker rebuild or environment edit.
- Backend regression: 390 tests run, one platform-specific skip, no failures. Includes automatic scheduling/retries, settings and audit, real-counter scoring, native-format intake, freeze/points/monthly winner, and existing legacy/history/auth/shop/notification behavior.
- A final focused run of 25 automation/admin tests also passed, including automatic December-to-January rollover and the advanced-form guidance.
- Frontend: TypeScript passes and 52 tests pass. Live-status browser checks show the entry form on desktop and mobile without overflow. Browser identity/channel responses were synthetic; no real user entry or outbound notification was submitted during verification.
- Django system checks and league migration drift check pass.

CLI setup for another local installation: migrate, run `python manage.py league_ensure --enable`, then keep the league worker running. Do not run duplicate scheduler replicas. Existing advanced rounds are deliberately preserved and may still require their original calibration; automatic scheduling does not overwrite them.


## Follow-up: approved channel confirmation loop

An admin could accept a channel before its member completed the separate ownership declaration. The member API then allowed confirmation only for pending applications, while the league required both acceptance and confirmation. This stranded approved/unconfirmed members.

Approved members can now confirm their existing application without changing its approval or submitting another application. Existing consent and screenshot requirements still apply; rejected/removal-requested applications remain blocked. Confirmation remains owner-only and idempotent. The league shows a direct link to the existing application and distinguishes pending review, missing confirmation, removal and rejection. The detail page links back to submission after confirmation. Admin lists show the confirmation and channel eligibility flags, with a warning when bulk approval still leaves confirmation outstanding.

Verified with 133 relevant backend tests, 54 frontend tests, TypeScript and a browser regression following the entire approved → confirmed → entry-form flow. Browser account writes were intercepted; no member ownership declaration was made on their behalf. No migration is required for this follow-up.
