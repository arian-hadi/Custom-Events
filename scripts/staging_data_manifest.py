#!/usr/bin/env python3
r"""Read-only database/media preservation checks for a staged migration.

Run from the Django project directory (for example /app), with
DJANGO_SETTINGS_MODULE already set; the script may be mounted at /tools.
No django.setup(), application models, migration recorder, or signals are used.

    python /tools/staging_data_manifest.py snapshot --output /audit/before.json \
        --media-root /app/mediafiles
    python /tools/staging_data_manifest.py snapshot --output /audit/after.json \
        --baseline /audit/before.json --media-root /app/mediafiles
    python /tools/staging_data_manifest.py compare /audit/before.json /audit/after.json

Stop ALL writers, including web requests and workers, for both snapshots and the
migration. PostgreSQL reads use a read-only repeatable-read transaction. SQLite
uses query_only and a read transaction. Database and media cannot share an atomic
snapshot. No external object storage, views, sequences, constraints, permissions,
or application behavior is verified. Symlinked media is rejected. PostgreSQL
tables must be visible in the connection's search_path; use the same DB backend,
settings, and search_path for both snapshots. Tables without a primary key are
compared as multisets of complete row hashes. A changed row fails even when a
data migration intended the change: investigate every failure before promotion.

New tables, rows, columns, migrations, and files are allowed; baseline columns
alone are hashed for existing tables after migration. Runtime table exclusions
must be explicit via --exclude-table (repeatable); a baseline carries them into
the second snapshot. Nothing is implicitly excluded, including django_session
and django_migrations. Excluded tables are NOT checked. Comparisons require the
same exclusions. Snapshots contain schema names, migration identifiers, relative
media filenames and hashes, never raw row values. Treat manifests as private:
hashes can reveal equality and permit guesses of low-entropy values. Database
rows and files are streamed when snapshotting; comparing loads both manifests
into memory, so memory use grows with the number of rows and files.
"""

import argparse
import base64
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID


FORMAT_VERSION = 1
CHUNK_SIZE = 1000


class ManifestError(Exception):
    """An actionable error that contains no raw database values."""


def typed_value(value):
    """Canonical, type-preserving in-memory encoding; never persist these values."""
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        return ["float", value.hex()]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return ["bytes", base64.b64encode(bytes(value)).decode("ascii")]
    if isinstance(value, Decimal):
        return ["decimal", str(value)]
    if isinstance(value, datetime):
        if value.utcoffset() is not None:
            value = value.astimezone(timezone.utc)
        return ["datetime", value.isoformat(timespec="microseconds")]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, time):
        return ["time", value.isoformat(timespec="microseconds")]
    if isinstance(value, timedelta):
        return ["timedelta", value.days, value.seconds, value.microseconds]
    if isinstance(value, UUID):
        return ["uuid", value.hex]
    if isinstance(value, (list, tuple)):
        return ["array", [typed_value(item) for item in value]]
    if isinstance(value, dict):
        items = [[typed_value(key), typed_value(item)] for key, item in value.items()]
        items.sort(key=lambda item: json.dumps(item[0], ensure_ascii=True))
        return ["map", items]
    raise ManifestError(f"Unsupported database value type: {type(value).__name__}")


def row_hash(values):
    encoded = json.dumps([typed_value(value) for value in values],
                         ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def read_manifest(path):
    with Path(path).open(encoding="utf-8") as source:
        manifest = json.load(source)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest):
    """Reject incomplete/invalid manifests instead of accidentally passing them."""
    try:
        if manifest["format_version"] != FORMAT_VERSION or manifest["complete"] is not True:
            raise ValueError
        if manifest["database_vendor"] not in ("postgresql", "sqlite"):
            raise ValueError
        if not isinstance(manifest["excluded_tables"], list):
            raise ValueError
        if not isinstance(manifest["tables"], dict) or not isinstance(manifest["media"], dict):
            raise ValueError
        if not isinstance(manifest["migration_ids"], list):
            raise ValueError
        for table in manifest["tables"].values():
            for field in ("columns", "actual_columns", "primary_key", "missing_columns"):
                if not isinstance(table[field], list):
                    raise ValueError
            if table["row_count"] != len(table["rows"]):
                raise ValueError
            for key_hash, digest in table["rows"]:
                if key_hash is not None and not valid_hash(key_hash):
                    raise ValueError
                if not valid_hash(digest):
                    raise ValueError
        for item in manifest["media"].values():
            if not valid_hash(item["sha256"]) or not isinstance(item["size"], int):
                raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ManifestError("Invalid or incomplete manifest; create a fresh snapshot.") from None


def valid_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@contextmanager
def read_only_snapshot(connection):
    """Enforce database read-only access and always roll back the read transaction."""
    from django.db import transaction

    if connection.vendor not in ("postgresql", "sqlite"):
        raise ManifestError("Only PostgreSQL and SQLite snapshots are supported.")
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ManifestError("Snapshots require a fresh connection outside any transaction.")
    previous_query_only = None
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA query_only")
            previous_query_only = cursor.fetchone()[0]
            cursor.execute("PRAGMA query_only = ON")
    try:
        with transaction.atomic(using=connection.alias):
            try:
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                yield
            finally:
                transaction.set_rollback(True, using=connection.alias)
    finally:
        if previous_query_only is not None:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA query_only = " + ("ON" if previous_query_only else "OFF"))


def inspect_table(connection, table_name):
    with connection.cursor() as cursor:
        columns = [column.name for column in connection.introspection.get_table_description(cursor, table_name)]
        constraints = connection.introspection.get_constraints(cursor, table_name)
    primary_key = next((list(item["columns"]) for item in constraints.values() if item["primary_key"]), [])
    return columns, primary_key


def write_table(output, connection, table_name, baseline):
    actual_columns, primary_key = inspect_table(connection, table_name)
    expected_columns = baseline["columns"] if baseline is not None else actual_columns
    columns = [name for name in expected_columns if name in actual_columns]
    missing_columns = [name for name in expected_columns if name not in actual_columns]
    metadata = {"columns": columns, "actual_columns": actual_columns,
                "primary_key": primary_key, "missing_columns": missing_columns}
    output.write(json.dumps(metadata, ensure_ascii=True)[:-1] + ', "rows": [')
    # Include a new/replaced PK only for its hash; the row digest stays restricted
    # to baseline columns. Identifier quoting comes from the DB backend.
    selected = columns + [name for name in primary_key if name not in columns]
    quote = connection.ops.quote_name
    query = "SELECT " + (", ".join(quote(name) for name in selected) or "1")
    query += " FROM " + quote(table_name)
    if primary_key:
        query += " ORDER BY " + ", ".join(quote(name) for name in primary_key)
    primary_indexes = [selected.index(name) for name in primary_key]
    count = 0
    # Django's PostgreSQL chunked_cursor is server-side; a normal psycopg cursor
    # can buffer the entire result despite fetchmany(). SQLite streams locally.
    with connection.chunked_cursor() as cursor:
        cursor.execute(query)
        while True:
            rows = cursor.fetchmany(CHUNK_SIZE)
            if not rows:
                break
            for row in rows:
                key = row_hash([row[index] for index in primary_indexes]) if primary_key else None
                digest = row_hash(row[:len(columns)])
                if count:
                    output.write(",")
                output.write(json.dumps([key, digest], separators=(",", ":")))
                count += 1
    output.write('], "row_count": ' + str(count) + "}")


def media_paths(root):
    paths = []
    for directory, directories, filenames in os.walk(root, followlinks=False,
                                                    onerror=lambda error: fail_media_walk()):
        for name in directories + filenames:
            path = Path(directory) / name
            if path.is_symlink():
                raise ManifestError("Media symlinks are unsupported; snapshot a regular-file media tree.")
        for name in filenames:
            path = Path(directory) / name
            if not path.is_file():
                raise ManifestError("Media contains a non-regular file.")
            paths.append(path.relative_to(root).as_posix())
    return sorted(paths)


def fail_media_walk():
    raise ManifestError("Cannot read the complete media directory.")


def write_media(output, root):
    paths = media_paths(root)
    output.write("{")
    for index, relative in enumerate(paths):
        path = root / relative
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as media:
            while chunk := media.read(1024 * 1024):
                digest.update(chunk)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ManifestError("A media file changed during the snapshot; stop all writers and retry.")
        if index:
            output.write(",")
        output.write(json.dumps(relative, ensure_ascii=True) + ":")
        output.write(json.dumps({"size": after.st_size, "sha256": digest.hexdigest()}))
    if paths != media_paths(root):
        raise ManifestError("The media file list changed during the snapshot; stop all writers and retry.")
    output.write("}")


def snapshot(output_path, media_root, *, baseline_path=None, excluded_tables=None, connection=None):
    baseline = read_manifest(baseline_path) if baseline_path else None
    excluded = sorted(set(excluded_tables if excluded_tables is not None else
                          (baseline["excluded_tables"] if baseline else [])))
    if baseline and excluded != sorted(baseline["excluded_tables"]):
        raise ManifestError("Exclusions must match the baseline; existing data cannot be newly excluded.")
    root = Path(media_root)
    output_path = Path(output_path)
    if root.is_symlink() or not root.is_dir():
        raise ManifestError("--media-root must be an existing, non-symlink directory, even if empty.")
    root = root.resolve()
    if output_path.resolve().is_relative_to(root):
        raise ManifestError("Write the manifest outside the media root.")
    if connection is None:
        from django.db import connection
    if baseline and connection.vendor != baseline["database_vendor"]:
        raise ManifestError("The database backend must match the baseline.")
    # Exclusive creation prevents overwriting evidence. Only remove this new
    # incomplete file on failure; no database or media files are ever modified.
    with output_path.open("x", encoding="utf-8", newline="\n") as output:
        try:
            with read_only_snapshot(connection):
                with connection.cursor() as cursor:
                    table_names = sorted(connection.introspection.table_names(cursor, include_views=False))
                unknown_exclusions = set(excluded) - set(table_names)
                if unknown_exclusions and not baseline:
                    raise ManifestError("An excluded table does not exist; check --exclude-table spelling.")
                header = {"format_version": FORMAT_VERSION, "database_vendor": connection.vendor,
                          "excluded_tables": excluded, "created_at": datetime.now(timezone.utc).isoformat()}
                output.write(json.dumps(header, ensure_ascii=True)[:-1] + ', "tables": {')
                included = [name for name in table_names if name not in excluded]
                for index, table_name in enumerate(included):
                    if index:
                        output.write(",")
                    output.write(json.dumps(table_name, ensure_ascii=True) + ":")
                    previous = baseline["tables"].get(table_name) if baseline else None
                    write_table(output, connection, table_name, previous)
                output.write('}, "migration_ids": ')
                migrations = []
                if "django_migrations" in included:
                    names, _ = inspect_table(connection, "django_migrations")
                    if "app" not in names or "name" not in names:
                        raise ManifestError("django_migrations is missing its app/name columns.")
                    quote = connection.ops.quote_name
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT " + quote("app") + ", " + quote("name") +
                                       " FROM " + quote("django_migrations") + " ORDER BY 1, 2")
                        migrations = [[app, name] for app, name in cursor]
                output.write(json.dumps(migrations, ensure_ascii=True))
            output.write(', "media": ')
            write_media(output, root)
            output.write(', "complete": true}\n')
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            output.close()
            output_path.unlink()
            raise


def compare(before, after):
    validate_manifest(before)
    validate_manifest(after)
    failures = []
    if before["database_vendor"] != after["database_vendor"]:
        failures.append("Database backends differ.")
    if sorted(before["excluded_tables"]) != sorted(after["excluded_tables"]):
        failures.append("Excluded table lists differ.")
    for name, old in before["tables"].items():
        new = after["tables"].get(name)
        if new is None:
            failures.append(f"Table {name!r} is missing.")
            continue
        if old["columns"] != new["columns"] or new["missing_columns"] or old["missing_columns"]:
            failures.append(f"Table {name!r}: baseline columns differ or are missing (use --baseline).")
            continue
        if old["primary_key"] != new["primary_key"]:
            failures.append(f"Table {name!r}: primary key columns changed.")
        old_rows = Counter(tuple(row) for row in old["rows"])
        new_rows = Counter(tuple(row) for row in new["rows"])
        missing = sum((old_rows - new_rows).values())
        if missing:
            failures.append(f"Table {name!r}: {missing} existing row(s) changed or missing.")
    if set(map(tuple, before["migration_ids"])) - set(map(tuple, after["migration_ids"])):
        failures.append("Existing migration identifiers are missing.")
    for relative, old in before["media"].items():
        new = after["media"].get(relative)
        if new != old:
            failures.append(f"Media {relative!r} changed or is missing.")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("snapshot", help="Create a new, read-only database/media manifest.")
    capture.add_argument("--output", required=True, help="New JSON path outside media; never overwritten.")
    capture.add_argument("--media-root", required=True, help="Existing local media directory (empty is allowed).")
    capture.add_argument("--baseline", help="Before manifest: hash its original columns on existing tables.")
    capture.add_argument("--exclude-table", action="append", dest="excluded_tables",
                         help="Exact runtime table name to omit; repeat as needed. No implicit exclusions.")
    check = commands.add_parser("compare", help="Fail on changed/deleted baseline data; additions are allowed.")
    check.add_argument("before")
    check.add_argument("after")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            # /tools is sys.path[0] when mounted; Django project imports live in
            # the container working directory (/app), not alongside this script.
            sys.path.insert(0, str(Path.cwd()))
            snapshot(args.output, args.media_root, baseline_path=args.baseline,
                     excluded_tables=args.excluded_tables)
            print("Snapshot complete; no database or media data was modified.")
            return 0
        failures = compare(read_manifest(args.before), read_manifest(args.after))
        if failures:
            for failure in failures:
                print("FAIL: " + failure)
            return 1
        print("PASS: all included baseline tables, rows, migration IDs, and media files are preserved.")
        return 0
    except ManifestError as error:
        print("ERROR: " + str(error), file=sys.stderr)
    except Exception as error:
        # Driver errors can contain SQL, row values, credentials, or hostnames.
        print(f"ERROR: snapshot/compare failed ({type(error).__name__}); no raw error details are printed.",
              file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
