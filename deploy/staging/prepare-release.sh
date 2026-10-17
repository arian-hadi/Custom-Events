#!/usr/bin/env bash
# Prepare images only. Database changes and service activation are separate work.
set -euo pipefail

fail() { printf 'V2 staging preparation failed: %s\n' "$*" >&2; exit 1; }

mode=prepare
if [[ ${1:-} == --validate-archive ]]; then
  mode=validate
  shift
fi
[[ $# == 2 ]] || fail 'Usage: prepare-release.sh [--validate-archive] FULL_COMMIT_SHA ARCHIVE.tar'
release_sha=$1
[[ $release_sha =~ ^[0-9a-f]{40}$ ]] || fail 'A full, lowercase 40-character Git commit SHA is required.'
command -v python3 >/dev/null || fail 'python3 is required.'
command -v realpath >/dev/null || fail 'realpath is required.'
[[ -f $2 && ! -L $2 ]] || fail 'The source archive must be a regular file, not a symlink.'
archive=$(realpath -e -- "$2")

readonly base=/root/Custom-Events-Staging-V2
readonly env_file="$base/.env.v2.staging"
readonly release_dir="$base/releases/$release_sha"

if [[ $mode == prepare ]]; then
  [[ -d $base && ! -L $base && $(realpath -e -- "$base") == "$base" ]] || fail 'The V2 staging root must exist at /root/Custom-Events-Staging-V2 without symlinked parents.'
  [[ $archive == "$base/incoming/$release_sha/source.tar" ]] || fail 'The archive must be in the matching V2 incoming/<commit>/source.tar directory, without symlinked parents.'
  [[ -f $env_file && ! -L $env_file ]] || fail "Create $env_file with separate staging credentials before preparing a release. The example file is not server configuration."
  [[ ! -L $base/releases && ! -L $base/.prepare.lock ]] || fail 'The releases directory and preparation lock must not be symlinks.'
  command -v docker >/dev/null || fail 'Docker with the Compose plugin is required.'
  command -v flock >/dev/null || fail 'flock is required to serialize preparation on the server.'
  docker compose version >/dev/null
  exec 9> "$base/.prepare.lock"
  flock -n 9 || fail 'Another V2 staging preparation is already running.'
fi

python3 - "$mode" "$release_sha" "$archive" "$release_dir" "${BASH_SOURCE[0]}" <<'PY'
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile

mode, commit, archive_name, release_name, helper_name = sys.argv[1:]
release = Path(release_name)
required = {
    "compose.v2.staging.yml",
    ".env.v2.staging.example",
    "deploy/staging/prepare-release.sh",
    "deploy/staging/nginx.conf.template",
    "prime_project/Dockerfile.v2",
    "prime_project/prime_project/settings_v2_staging.py",
    "prime_project/manage.py",
    "prime_project/requirements.txt",
    "New_Frontend/Dockerfile",
    "New_Frontend/package.json",
    "New_Frontend/package-lock.json",
    "scripts/check_v2.py",
    "scripts/staging_data_manifest.py",
}
runtime_dirs = {
    ".git", ".local-v2", ".staging-v2", ".staging-v2-upload", ".venv", "venv",
    ".test-media", ".v2-test-media",
    "node_modules", ".next", "__pycache__", "mediafiles", "staticfiles",
    "postgres_data", "pg_data", "db_data", "volumes",
}


def fail(message):
    raise ValueError(message)


def digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.digest()


def verify_existing(tar, members):
    if release.is_symlink() or not release.is_dir():
        fail("The release path already exists and is not a regular directory.")
    actual = set()
    for directory, dirs, files in os.walk(release, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                fail("The existing release contains a symlink; refusing to reuse it.")
            actual.add(path.relative_to(release).as_posix())
    if actual != set(members):
        fail("The existing release differs from the archive; refusing to overwrite it.")
    for name, member in members.items():
        path = release / name
        if member.isdir():
            if not path.is_dir():
                fail("An existing release directory has changed.")
        else:
            if not path.is_file() or path.stat().st_size != member.size:
                fail("An existing release file has changed.")
            with path.open("rb") as current, tar.extractfile(member) as expected:
                if digest(current) != digest(expected):
                    fail("An existing release file has changed; refusing to overwrite it.")
            if path.stat().st_mode & 0o777 != member.mode & 0o777:
                fail("An existing release file's permissions have changed.")


try:
    with tarfile.open(archive_name, "r:") as tar:
        if tar.pax_headers.get("comment") != commit:
            fail("The archive must be produced by git archive for the requested commit.")
        members = {}
        for member in tar.getmembers():
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or "\\" in name
                    or any(ord(char) < 32 for char in name)
                    or any(part in {"", ".", ".."} for part in name.split("/"))):
                fail("The archive contains an unsafe path.")
            if name in members or not (member.isfile() or member.isdir()):
                fail("The archive contains a duplicate path, link, or special file.")
            if any(part in runtime_dirs for part in path.parts):
                fail("The archive contains a runtime directory; remove it from Git first.")
            if any(part == ".env" or (part.startswith(".env.") and not part.endswith(".example"))
                   for part in path.parts):
                fail("The archive contains an environment file; only *.example files are allowed.")
            if member.isfile() and name.endswith((".sqlite3", ".sqlite3-journal", ".log", ".pyc")):
                fail("The archive contains runtime data; remove it from Git first.")
            members[name] = member
        if not required.issubset(members) or any(not members[name].isfile() for name in required):
            fail("The committed archive is missing required V2 frontend, backend, staging, or script files.")
        for name in members:
            for parent in PurePosixPath(name).parents:
                if str(parent) != "." and (str(parent) not in members or not members[str(parent)].isdir()):
                    fail("The archive has an invalid directory structure.")
        if mode == "validate":
            print(f"Validated complete V2 source archive for {commit}.")
            sys.exit(0)
        with tar.extractfile(members["deploy/staging/prepare-release.sh"]) as committed_helper:
            if Path(helper_name).read_bytes() != committed_helper.read():
                fail("The uploaded helper does not match the committed archive.")
        release.parent.mkdir(mode=0o750, exist_ok=True)
        if release.parent.is_symlink() or release.parent.resolve() != release.parent:
            fail("The release root is inconsistent with the fixed V2 staging root.")
        if release.exists() or release.is_symlink():
            verify_existing(tar, members)
            print(f"Verified unchanged release {commit}; retrying image preparation.")
        else:
            partial = Path(tempfile.mkdtemp(prefix=f".partial-{commit}-", dir=release.parent))
            # Links/devices are rejected; failed extraction stays isolated for inspection.
            for name, member in members.items():
                destination = partial / name
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    destination.chmod(0o755)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as source, destination.open("xb") as target:
                        shutil.copyfileobj(source, target)
                    destination.chmod(member.mode & 0o777)
            partial.rename(release)
            print(f"Prepared immutable source directory for {commit}.")
except ValueError as error:
    # Validation messages never contain credentials or untrusted archive names.
    print(f"Archive/release validation failed: {error}", file=sys.stderr)
    sys.exit(1)
except (OSError, tarfile.TarError):
    print("Cannot read the archive or prepare the release directory. Check the file format, disk space, and permissions.", file=sys.stderr)
    sys.exit(1)
PY

if [[ $mode == validate ]]; then
  exit 0
fi

# Use commit-specific image tags even when the server env has a candidate tag.
export STAGING_IMAGE_TAG="$release_sha"
compose=(docker compose --env-file "$env_file" -f "$release_dir/compose.v2.staging.yml" -p platform-v2-staging)
"${compose[@]}" config --quiet
"${compose[@]}" build backend frontend
printf 'V2 staging images prepared for %s. Services, databases, and traffic were not changed.\n' "$release_sha"
