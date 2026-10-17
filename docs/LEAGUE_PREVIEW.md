# Local weekly league preview

From the repository root, with the local Docker development stack running:

```powershell
docker compose --env-file .env.v2 -f compose.v2.yml -f compose.v2.dev.yml exec backend python manage.py league_preview
```

Open the URL printed by the command. It expires after two hours; run the command again for another link. No migrations, environment changes or image rebuilds are needed in the bind-mounted development setup.

The preview uses the existing standings and winner-card components with six fictional editors. Switch between **Live weekday**, **Frozen weekend**, and **Missing closing data**. You can search editors, filter platforms, expand score breakdowns and switch between weekly, monthly and all-time standings. Weekly is first and selected by default; live rows show projected placement points, while monthly/all-time sample totals contain only finalized sample awards. All scores and awards are illustrative sample data, not real provider measurements or validation evidence.

The initial view can also be selected with `--state frozen` or `--state pending`. Without Docker, run `python manage.py league_preview --settings=prime_project.settings_v2_local` from `prime_project` and open the printed URL for your configured local frontend.

This command does **not** start the actual competition early. No real entries, dates, accounts, metrics, awards, notifications or point totals are created or changed. Real league pages and scheduler commands are unaffected. Submission is disabled on the preview page; leave via **Return to the actual Editing Hub**. Closing the preview requires no cleanup.

The command and fixture API require `DEBUG=True` and a loopback `V2_FRONTEND_URL`. The read-only endpoint additionally requires the temporary signed link. Production settings reject it; do not enable debug mode on production to use a preview.

Verified locally: 24 preview/league API tests, TypeScript checking, and desktop/mobile browser checks for live, frozen, pending, monthly totals, score breakdown and search. Preview tests forbid database queries; browser checks confirmed no writes to the local app.

Latest verification also covers live projected points, the three-tab order on the real hub, accessible platform icons, and click-to-load winner players using browser-only fixtures. No real emails or league records are created by these checks.
