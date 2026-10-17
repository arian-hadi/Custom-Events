# League provider setup

The automatic league creates upcoming weeks and starter rules through Admin → League settings. Real provider access and approved, verified editor channels are still required. Pilot calibration is an optional advanced scoring mode, not a prerequisite for starter-mode entry. Follow [League operations](LEAGUE_OPERATIONS.md).

## Credentials

Use `.env.v2` for Docker. Only backend processes receive these values; do not put them in frontend variables.

```dotenv
LEAGUE_YOUTUBE_API_KEY=your_youtube_data_api_key
LEAGUE_PROVIDER_CREDENTIALS_FILE=/run/v2-secrets/league-providers.json
# Optional initial fallback; the saved admin switch takes precedence.
LEAGUE_ENABLED=False
```

Create the JSON at `.local-v2/secrets/league-providers.json`. Compose already mounts this ignored directory read-only at `/run/v2-secrets` for the backend and workers. Recreate Compose services after changing environment values; edits to the mounted JSON are read on subsequent requests without rebuilding an image.

For the non-Docker preview (`prime_project.settings_v2_local`), use `.env.v2.local` with its prefixed settings: `V2_LOCAL_LEAGUE_YOUTUBE_API_KEY`, `V2_LOCAL_LEAGUE_PROVIDER_CREDENTIALS_FILE` and `V2_LOCAL_LEAGUE_ENABLED`. Set the credentials file to its absolute Windows path, and restart the local backend/league worker after environment changes.

The JSON is keyed by **editor application ID**, with the owning website **user ID** inside each item. The example values below are placeholders, not working credentials:

```json
{
  "12": {
    "user_id": 34,
    "reviewed_formats": {
      "AbCdEfGhI_1": "short",
      "AbCdEfGhI_2": "short"
    },
    "reviewed_content_keys": {
      "AbCdEfGhI_1": "same-underlying-edit-001"
    }
  },
  "15": {
    "user_id": 34,
    "access_token": "creator-authorized-tiktok-access-token",
    "open_id": "that-creators-verified-tiktok-open-id",
    "reviewed_content_keys": {
      "7080217258545735586": "same-underlying-edit-001"
    }
  }
}
```

Every channel must be accepted, verified, and not pending removal. The code checks the returned video's owner against that approved channel. The optional shared content key lets an administrator identify known cross-posts as one underlying edit; use the same key for those videos in their respective application records.

## YouTube

Configure a server API key with access to YouTube Data API v3. The dedicated `LEAGUE_YOUTUBE_API_KEY` takes priority over the existing `YOUTUBE_API_KEY`. An approved `/channel/ID`, `/@handle`, or `/user/name` link resolves to a canonical channel ID. The collector discovers uploads through the uploads playlist and retrieves current lifetime likes/views; it never uses search to guess the channel. Pagination follows YouTube's documented page tokens. [YouTube playlist API](https://developers.google.com/youtube/v3/docs/playlistItems/list)

The current adapter deliberately leaves YouTube format as `unknown`: a pasted `/shorts/` URL or short duration is not accepted as proof of classification. Automatic mode accepts `youtube:unknown` directly and does not claim Shorts classification. No per-video format mapping is needed. For the advanced calibrated-reference mode, supply administrator-reviewed per-video `reviewed_formats` for competition entries **and comparison videos**, matching the formats in the calibrated scoring version (for example `short`). Alternatively, explicitly calibrate a youtube:unknown scope when you intentionally include that provider classification. Both entry intake and comparison history require the exact configured platform/format; neither silently changes buckets.

## TikTok

Supply an access token authorized by each editor and the corresponding verified `open_id`. The integration verifies that identity, then queries only videos accessible to that creator. TikTok's Display API uses the `video.list` scope for video listing/querying. Its list endpoint returns cursor-based pages; the collector resumes them between bounded batches. [TikTok listing](https://developers.tiktok.com/docs/en/tiktok-api-v2-video-list), [TikTok querying](https://developers.tiktok.com/docs/en/tiktok-api-v2-video-query)

This integration does **not** implement a member-facing TikTok OAuth connect/refresh screen. Obtain authorization through your approved developer integration and maintain the per-editor server credentials. Missing or expired access leaves observations unavailable. A global token is not used as a substitute for each editor's authorization. The adapter labels TikTok resources `video`, which automatic mode accepts directly. Advanced reference scoring still needs a calibrated `tiktok:video` scope (or an explicitly reviewed alternative). Missing credentials are not bypassed by automatic scoring.

## Automatic comparison history

After migrations through `edithub.0029_website_history_grading`, the existing `jobs-league` worker maintains upcoming weeks, processes rounds and collects entry metrics while League settings is enabled. No additional container or host scheduler is needed. Do not run duplicate worker replicas.

**Current automatic version (`round_cohort_v2`):** no channel-wide comparison discovery. History comes exclusively from the saved closing metrics of the member's last 1–5 eligible finalized website submissions. Debut editors receive the configured first-week component; returning editors with no usable history use neutral 50. Providers remain necessary for each submitted video's current likes/views. See [grading rules](LEAGUE_WEBSITE_GRADING.md).

The bounded channel discovery behavior below is retained only for existing `round_cohort_v1` and advanced calibrated-reference rounds:

- History considers approved channels with a queued future entry or an active live entry. Finished-only, revoked and inactive-member channels are skipped.
- Each channel is attempted at most once per hour. A cycle processes at most four channels and eight videos per channel by default, with a 30-second budget for starting more fetches. An in-flight provider operation can finish after that budget, subject to the adapter's request timeouts.
- Discovery fetches up to 20 IDs at a time. Pending IDs and page cursors are retained so older videos are reached on later hourly passes. A large archive can take multiple days to traverse; this is not a full historical backfill or a promise that every video is refreshed hourly.
- Current competition videos and disqualified submissions are excluded as comparison candidates. A completed eligible older competition video may be observed for a different edit's future baseline.
- History pauses during the final 30 minutes of live rounds so closing entry metrics take priority. Separate entry polling still runs.
- Provider failures record a safe error class in **Admin → League history syncs**, never a credential-bearing error message or invented zero snapshot. Review provider quota and failures before opening a larger cohort; the bounded batch is not a quota guarantee.
- Every observation has its actual collection time. Later history cannot modify an already frozen baseline. Insufficient comparable history uses the scoring version's neutral improvement rule.

To run one bounded history cycle manually (when enabled), from the repository root:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend python manage.py league_history --application 12 --limit 8 --channels 1 --budget-seconds 30
```

For pilot preparation before enabling the league, collect chosen comparison videos explicitly with `league_observe --application 12 --video VIDEO_URL`. This stores a current observation and awards no points; it cannot reconstruct likes/views from a past date. Then use the calibration workflow in `LEAGUE_OPERATIONS.md`.

