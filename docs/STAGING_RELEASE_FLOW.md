# V2 staging delivery

Push reviewed, committed code to `staging`. The **Deploy V2 staging** GitHub
Actions workflow validates the release, uploads its exact Git archive, builds
backend and frontend images sequentially, and updates the existing V2 staging
application. Uncommitted local changes are not included. Production still uses
its separate `master` workflow. The old V1 staging deployment is not updated.

## Current access and GitHub configuration

The V2 site is private: open the SSH tunnel described in
[the migration runbook](V2_STAGING_MIGRATION.md), then visit
`http://localhost:8083/`. Test emails are captured at `http://localhost:8027/`.
The public V1 address on port 8080 continues to serve V1. This workflow does not
change public routing, HTTPS, credentials, or integration settings.

The workflow uses repository or `staging-v2` environment secrets `SSH_HOST`,
`SSH_USER`, `SSH_KEY`, optional `SSH_PORT` (default 22), and optional
`SSH_PASSPHRASE` for an encrypted SSH key. Existing environment protection rules
are honored; an environment declaration alone does not require approval.
Manual workflow dispatch is supported on `staging` for retrying a release.
Runs are serialized, and a server lock prevents overlapping preparation or
activation. Never upload real env files, database dumps, or private keys to Git.

## Deployment safeguards

1. Validate shell syntax, release/deployment tests, example Compose settings,
   and the committed archive. Reject unsafe paths, links, runtime data, and
   env files other than examples.
2. Upload to `/root/Custom-Events-Staging-V2/incoming/<full-commit-sha>/` and
   extract immutable source under `releases/<full-commit-sha>/`. Retries must
   match the existing release exactly. Build both images with the same SHA tag.
3. Require the existing `platform-v2-staging` PostgreSQL container and its
   independent `platform-v2-staging_staging_postgres` volume. Refuse automatic
   activation when V2 workers are running or the previous release is unknown.
4. Run Django checks and `migrate --check` against the already-migrated staging
   copy. **Pending migrations stop deployment before services are replaced.**
5. Collect static files and replace backend/frontend. Wait for their health
   checks, recreate the V2 gateway to refresh upstream addresses, then verify
   the homepage and site API through that gateway.
6. If activation fails, restore the previous application images and static
   files and check them again. CI stays failed, including if rollback fails.
7. Only after successful checks, save the SHA in the server env file,
   `current-release`, and `last-deployment.json`.

There is no automatic database restore, migration execution, volume deletion,
image pruning, or worker startup. Rollback restores code, not database contents.
Images and immutable source for the previous release must remain available.
Builds consume server resources; inspect disk usage periodically.

## Future migrations and initial provisioning

When pending migrations stop CI, review them and back up the **V2 staging**
database/media first. Rehearse migrations on a separate copy. During a reviewed
maintenance window, apply them using the prepared release's image and server
env file to the isolated V2 database, then rerun the workflow. For a schema
change incompatible with old code, plan data restore/rollback rather than
relying on automatic code rollback. Never target production or the V1 volume.

For initial provisioning, data copying, and migration acceptance, use the
[migration runbook](V2_STAGING_MIGRATION.md). This update workflow requires an
existing initial deployment; it does not bootstrap an empty server.

The server requires Bash, Python 3, realpath, flock, Docker, and Docker Compose
v2. Its `.env.v2.staging` remains server-only with restricted permissions.
Preparation does not overwrite immutable source. Failed partial extractions
remain available for inspection; cleanup is a separate operator action.

## Local checks

```bash
python -m unittest discover -s scripts -p test_staging_release.py -v
python -m unittest discover -s scripts -p test_staging_deploy.py -v
bash -n deploy/staging/prepare-release.sh
docker compose --env-file .env.v2.staging.example -f compose.v2.staging.yml -p platform-v2-staging config --quiet
# After committing:
commit=$(git rev-parse HEAD)
git archive --format=tar --output=/tmp/staging-v2-source.tar "$commit"
bash deploy/staging/prepare-release.sh --validate-archive "$commit" /tmp/staging-v2-source.tar
```
