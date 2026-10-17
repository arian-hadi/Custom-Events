# V2 league operations

To see a started round without changing the real calendar, run the read-only [`league_preview` command](LEAGUE_PREVIEW.md). It prints a temporary local sample-data page with live, frozen and missing-data scenarios.

Current league scope (10 October 2026): open calendar-month leagues supported by weekly competitions. Annual competition is retired; historical records are preserved. See [the current league plan](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md).

League scoring uses provider likes/views and the V2 points ledger. Followers and legacy upvotes do not affect it.

Updated 11 October 2026: a member chooses one active editor platform (YouTube or TikTok). Each edit can enter once per competition month, scoped by the target round's Friday date. Canonical IDs and known shared content keys are checked automatically; no originality checkbox is required. Existing results remain archived. See [member flow changes](MEMBER_FLOW_UPDATE.md).

## Open the automatic league

1. Apply migrations through `edithub.0029_website_history_grading`.
2. Open **Admin → Edithub → League settings** (`/admin/edithub/leaguesettings/`). Add the singleton settings if this is a fresh installation, check **Open automatic league**, and save. The defaults are 50/30/20 weights, the agreed placement points, and five eligible entries for a qualifying round.
3. Keep the existing `jobs-league` worker running. It maintains four upcoming weeks, freezes website submission history, activates weeks, polls metrics, freezes results and totals each calendar month. No recurring registration, manual JSON or weekly scheduling is needed.

The local site was enabled on 11 October 2026 (Europe/Istanbul). The equivalent bootstrap command is `python manage.py league_ensure --enable`; a plain `league_ensure` is safe to repeat and honors the admin switch. `LEAGUE_ENABLED` is only the fallback before a League settings row exists; the admin switch takes precedence afterward. No environment edit/restart is needed for subsequent settings changes.

Point/weight changes create a new immutable scoring version for newly scheduled weeks only. Already scheduled weeks (including queued entries) and past results retain their rules; the four-week planning window means a change may first appear several weeks later. Use the existing audited correction workflow for a genuine past-result correction, never this settings page.

## Starter scoring and advanced calibration

New automatic mode (`round_cohort_v2`) uses 50% like rate, 30% performance against an editor's last 1–5 finalized website edits, and 20% lifetime views. The first competition week receives an admin-configurable 85/100 performance component (25.5 overall at 30%); returning editors without usable history receive 50. This incentive never repeats each month. No channel-wide history fetching is needed for V2. Existing versions remain unchanged. This policy is **not empirically validated across platforms or video ages**. See [website-history grading](LEAGUE_WEBSITE_GRADING.md).

To apply current settings to an already scheduled future round, open **Competition weeks → Operations → Apply current league settings to this future round**, enter an audit reason, and submit. This is an explicit administrator action; it is recorded and repeat-safe. It rejects live, elapsed or finalized weeks, including attempts to regrade archived results. Newly scheduled weeks automatically use the latest League settings.

The older calibrated-reference policy remains available for advanced use. Collect real evidence with `league_observe`, build a draft with `league_calibrate`, then review it in Scoring versions. Calibrated-reference versions still require genuine complete references and approval. Manual scheduling remains an advanced option; automation preserves any existing rounds. Never tick calibrated to bypass missing evidence.

Provider access and approved, verified editor channels remain required. YouTube uses the existing API key without per-video format setup in automatic mode. TikTok needs each editor’s authorized provider connection. See [provider setup](LEAGUE_PROVIDER_SETUP.md).

For Docker commands, prepend `docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend` to `python manage.py ...`, from the repository root. Host commands run from `prime_project` with the project's virtual environment.

## How rounds run

- Entries received this calendar week enter the following Monday's round. Monday 00:00 UTC to Saturday 00:00 UTC is the scoring window.
- Activation freezes the scoring version, age group, baseline and tie seed. Normal polling is hourly; near cutoff it is more frequent. Lifetime counters are used.
- Finalization requires valid pre-cutoff snapshots. Missing/stale data leaves a round pending; later weekend counters cannot be substituted. Fewer than five eligible entries produce an exhibition, with no official points or winner.
- Only the weekly winner earns a weekly award. Monthly standings sum finalized league points, attributed by the round's Friday date. Period winners wait until the period ends and all its rounds are resolved.

## Admin review and corrections

The round's **Readiness and operations** page shows current results, revision history and links to entries and snapshots. It supports activation and finalization through the same services used by the worker. Cancellation and corrections require an audit reason and the round-change permission.

For corrections, snapshot overrides map entry IDs to existing valid snapshot IDs. A supplied disqualification list is the complete intended list; leaving it blank preserves prior decisions. No arbitrary score entry is supported. Corrections add a revision, replace effective points and refresh affected period awards. Audit records remain read-only.

The calibration builder uses empirical mid-rank percentiles rescaled to 0–100, one latest observation per video/bucket, and prior available, age-matched creator history for improvement samples. It retains snapshot IDs and sample counts in the draft's evidence. This is review tooling, not proof that a small or biased sample is suitable for official competition.
