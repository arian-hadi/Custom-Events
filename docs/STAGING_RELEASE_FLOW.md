# V2 staging release preparation

Start with [the migration runbook](V2_STAGING_MIGRATION.md) for server discovery,
data copying and acceptance checks. This document covers source/image preparation.

V2 is prepared alongside the running V1 staging application. This flow packages
committed source and builds images; database copying, migration, container
startup, and routing changes are separate operator work requiring approval.
Production remains on its existing `master` workflow.

## What runs automatically

Pushing to `staging` runs validation only: Bash syntax, the standalone staging
Compose configuration with example values, and a complete `git archive` source
check. It does not connect to the VPS. The former staging workflow that stopped
V1 containers has been replaced.

The **Validate and prepare V2 staging** workflow can also be dispatched manually.
Select the `staging` branch. Its preparation job runs only for that branch, after
validation and the `staging-v2` GitHub environment gate. Configure required
reviewers and restrict deployment branches to `staging` in that environment;
declaring an environment in YAML does not create an approval policy by itself.
The environment must provide `SSH_HOST`, `SSH_USER`, `SSH_KEY`, and optionally
`SSH_PORT` (default `22`). Do not dispatch until the exact commit has been reviewed
and permission to upload and build on the staging server has been given.

## Commit the complete candidate first

The release is a `git archive` of the workflow's exact full commit SHA. It includes
the tracked frontend, Django backend, deployment configuration, scripts, and docs.
Untracked work and uncommitted changes are absent. In particular, all V2 source,
frontend public assets, the frontend lockfile, migrations, settings, and these
staging files must be reviewed and committed before preparing a candidate.

Check `git status --short` and review the staged diff before committing. Keep real
environment files, database dumps, uploaded media, provider credentials, virtual
environments, and build caches outside Git. `.gitignore` does not remove files
that were already tracked. Archive validation rejects environment files other
than `*.example`, common runtime directories, database files, logs, and links.
It supplements the staged diff review; it cannot identify every possible secret
filename or secret embedded in ordinary source.

Continue local V2 development using the existing local Compose files and env
files. The standalone `compose.v2.staging.yml` must never be combined with
`compose.v2.yml`, `compose.v2.dev.yml`, or a V1 Compose file. The workflow changes
neither local runtime configuration nor the V1 staging deployment.

## Separate server layout

The server requires Bash, Python 3, `realpath`, `flock`, Docker, and Docker Compose
v2. Provision the following paths before the first approved preparation:

```text
/root/Custom-Events-Staging-V2/
  .env.v2.staging                  server-only configuration; never uploaded by CI
  incoming/<full-commit-sha>/
    source.tar                    complete tracked git archive
    prepare-release.sh            helper from the same commit
  releases/<full-commit-sha>/      immutable extracted source
```

Create the server env file from `.env.v2.staging.example`, replace its placeholder
secrets with separate staging credentials, and restrict access to the operator
account, for example with mode `600`. Missing server configuration fails before
release extraction or image builds. Do not copy production or local credentials
into the staging file. The required settings are `STAGING_SECRET_KEY`,
`STAGING_DB_PASSWORD`, and `STAGING_PUBLIC_URL`; review the example for optional
database, port, and HTTP settings. Runtime staging settings reject placeholder
secrets. Compose configuration validation and image builds alone do not prove
that runtime settings or database migrations will succeed.

V2 uses the Compose project `platform-v2-staging`, separate from V1's `staging`
project. Its resources must remain separate from `/root/Custom-Events-Staging`
and `/root/Custom-Events`. The helper rejects inconsistent roots and symlinks;
the archive must be at the exact incoming path for the requested full commit SHA.
Never point V2 at a V1 database volume or media volume.

## What a manual preparation does

1. Validate the committed source and the example Compose configuration.
2. Upload the archive and helper into the separate V2 incoming directory.
3. Verify the archive's Git commit metadata, safe paths, complete source, and
   matching helper, then extract a new release directory atomically.
4. Run `docker compose ... config --quiet` using the server env file.
5. Build only the `backend` and `frontend` images, tagged with the full commit SHA.

The helper overrides `STAGING_IMAGE_TAG` with that commit SHA for both commands.
Any later approved operation using the release must use the same image tag;
otherwise the example's default `candidate` tag will not select the built images.
It does not start or stop containers, restore or migrate a database, collect
static files, start workers, change the reverse proxy, or change traffic.
Builds consume server CPU, disk, and network, so schedule them appropriately.

A failed build leaves the source release intact. Rerunning the same commit is
allowed only if all extracted files and permissions still match the archive;
existing source is never overwritten. A source validation or extraction failure
may leave a `.partial-<commit>-...` directory for inspection. Cleanup is an
explicit operator action on a verified path; this flow performs no recursive
deletion. The workflow and a host lock serialize preparation runs.

## Review before any activation

After preparation, review the exact release and image tags, independent staging
configuration, V1 database/media backup and restore plan, migration effects,
integration switches, and rollback plan. Copy data to separate V2 resources and
test migrations there before considering a traffic change. Keep outbound jobs
disabled until their behavior against the copied data is reviewed. Starting V2,
changing V1, and routing staging traffic require a separate explicit decision;
none of those actions is implemented by this workflow.

Local validation without a server connection:

```bash
bash -n deploy/staging/prepare-release.sh
docker compose --env-file .env.v2.staging.example -f compose.v2.staging.yml -p platform-v2-staging config --quiet
# After the complete candidate is committed:
commit=$(git rev-parse HEAD)
git archive --format=tar --output=/tmp/staging-v2-source.tar "$commit"
bash deploy/staging/prepare-release.sh --validate-archive "$commit" /tmp/staging-v2-source.tar
```
