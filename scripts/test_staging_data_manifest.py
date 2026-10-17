"""Offline preservation tests. Run with the project's Django-capable interpreter:

    .venv/Scripts/python.exe -m unittest discover -s scripts -p test_staging_data_manifest.py -v

Only a dedicated Django SQLite :memory: connection is used. Project settings and
application models are never loaded; PostgreSQL transaction setup is mocked.
"""

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from django.conf import settings

if not settings.configured:
    settings.configure(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
                       INSTALLED_APPS=[], USE_TZ=True)

from django.db.utils import ConnectionHandler

import staging_data_manifest as manifest


class HashTests(unittest.TestCase):
    def test_hashes_preserve_types_and_do_not_leak_values(self):
        hashes = [manifest.row_hash([value]) for value in (None, True, 1, 1.0, "1", b"1", Decimal("1"))]
        self.assertEqual(len(set(hashes)), len(hashes))
        self.assertTrue(all(manifest.valid_hash(value) for value in hashes))

    def test_typed_values_are_repeatable(self):
        values = [datetime(2026, 1, 1, tzinfo=timezone.utc), date(2026, 1, 1), time(1, 2, 3),
                  timedelta(days=-1, microseconds=2), Decimal("1.2300"), Decimal("NaN"),
                  UUID(int=42), memoryview(b"binary"), [1, None], {"z": 2, "a": [1]}, float("inf")]
        self.assertEqual(manifest.row_hash(values), manifest.row_hash(values))
        self.assertEqual(manifest.row_hash([{"a": 1, "b": 2}]), manifest.row_hash([{"b": 2, "a": 1}]))
        self.assertEqual(manifest.row_hash([bytes(b"abc")]), manifest.row_hash([memoryview(b"abc")]))
        equivalent = datetime(2026, 1, 1, 3, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(manifest.row_hash([values[0]]), manifest.row_hash([equivalent]))

    def test_unknown_type_fails_closed(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.row_hash([object()])


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        # Keep fixtures under the writable workspace on restricted Windows hosts.
        self.temporary = tempfile.TemporaryDirectory(prefix="manifest-test-", dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.media = self.directory / "media"
        self.media.mkdir()
        (self.media / "upload.bin").write_bytes(b"private media fixture")
        # A separate handler ensures even a test runner with configured project
        # settings cannot connect to its actual default database.
        self.handler = ConnectionHandler({"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
        self.connection = self.handler["default"]
        self.addCleanup(self.connection.close)
        self.connection_patch = patch("django.db.transaction.get_connection", return_value=self.connection)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.execute('CREATE TABLE people (id INTEGER PRIMARY KEY, email TEXT, amount NUMERIC, content BLOB)')
        self.execute('INSERT INTO people VALUES (2, %s, %s, %s)', ["private.two@example.invalid", 1.25, b"secret2"])
        self.execute('INSERT INTO people VALUES (1, %s, %s, %s)', ["private.one@example.invalid", 2.50, b"secret1"])
        self.execute('CREATE TABLE django_migrations (id INTEGER PRIMARY KEY, app TEXT, name TEXT, applied TEXT)')
        self.execute('INSERT INTO django_migrations VALUES (1, %s, %s, %s)', ["example", "0001_initial", "2026-01-01"])
        self.serial = 0

    def execute(self, sql, params=None):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)

    def capture(self, baseline=None, excluded_tables=None):
        self.serial += 1
        path = self.directory / f"snapshot-{self.serial}.json"
        manifest.snapshot(path, self.media, baseline_path=baseline, excluded_tables=excluded_tables,
                          connection=self.connection)
        return path, manifest.read_manifest(path)

    def test_snapshot_only_contains_hashes_and_metadata(self):
        path, snapshot = self.capture()
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("private.one", text)
        self.assertNotIn("secret1", text)
        self.assertNotIn("private media fixture", text)
        table = snapshot["tables"]["people"]
        self.assertEqual(table["row_count"], 2)
        self.assertEqual(table["primary_key"], ["id"])
        self.assertEqual(table["rows"][0][0], manifest.row_hash([1]))
        self.assertEqual(snapshot["migration_ids"], [["example", "0001_initial"]])
        self.assertEqual(manifest.compare(snapshot, self.capture()[1]), [])

    def test_baseline_allows_added_columns_rows_tables_migrations_and_media(self):
        path, before = self.capture()
        self.execute("ALTER TABLE people ADD COLUMN enabled BOOLEAN DEFAULT 1")
        self.execute("INSERT INTO people (id, email) VALUES (3, %s)", ["new@example.invalid"])
        self.execute("CREATE TABLE added (id INTEGER PRIMARY KEY)")
        self.execute("INSERT INTO added VALUES (1)")
        self.execute("INSERT INTO django_migrations VALUES (2, 'example', '0002_next', '2026-01-02')")
        (self.media / "new.txt").write_text("new", encoding="utf-8")
        _, after = self.capture(baseline=path)
        self.assertEqual(before["tables"]["people"]["columns"], after["tables"]["people"]["columns"])
        self.assertIn("enabled", after["tables"]["people"]["actual_columns"])
        self.assertEqual(manifest.compare(before, after), [])
        self.assertTrue(manifest.compare(before, self.capture()[1]))

    def test_changed_and_deleted_rows_fail(self):
        path, before = self.capture()
        self.execute("UPDATE people SET email = 'changed' WHERE id = 1")
        self.execute("DELETE FROM people WHERE id = 2")
        failures = manifest.compare(before, self.capture(baseline=path)[1])
        self.assertTrue(any("2 existing row(s) changed or missing" in value for value in failures))

    def test_dropped_table_fails(self):
        path, before = self.capture()
        self.execute("DROP TABLE people")
        self.assertIn("Table 'people' is missing.", manifest.compare(before, self.capture(baseline=path)[1]))

    def test_dropped_column_fails(self):
        path, before = self.capture()
        self.execute("ALTER TABLE people DROP COLUMN email")
        failures = manifest.compare(before, self.capture(baseline=path)[1])
        self.assertTrue(any("baseline columns differ or are missing" in value for value in failures))

    def test_primary_key_changes_fail(self):
        _, before = self.capture()
        after = deepcopy(before)
        after["tables"]["people"]["primary_key"] = []
        self.assertTrue(any("primary key" in value for value in manifest.compare(before, after)))

    def test_changed_and_deleted_media_fail(self):
        path, before = self.capture()
        (self.media / "upload.bin").write_bytes(b"changed")
        self.assertTrue(any("Media" in value for value in manifest.compare(before, self.capture(baseline=path)[1])))
        (self.media / "upload.bin").unlink()
        self.assertTrue(any("Media" in value for value in manifest.compare(before, self.capture(baseline=path)[1])))

    def test_no_primary_key_uses_multiset_not_set(self):
        self.execute("CREATE TABLE bag (value TEXT)")
        self.execute("INSERT INTO bag VALUES ('duplicate'), ('duplicate'), ('other')")
        path, before = self.capture()
        self.execute("DELETE FROM bag WHERE rowid = (SELECT MIN(rowid) FROM bag)")
        self.assertTrue(any("1 existing row(s)" in value for value in
                            manifest.compare(before, self.capture(baseline=path)[1])))

    def test_explicit_exclusions_are_inherited_and_cannot_expand(self):
        path, before = self.capture(excluded_tables=["people"])
        self.assertNotIn("people", before["tables"])
        self.execute("DELETE FROM people")
        self.assertEqual(manifest.compare(before, self.capture(baseline=path)[1]), [])
        with self.assertRaises(manifest.ManifestError):
            self.capture(baseline=path, excluded_tables=["people", "django_migrations"])
        with self.assertRaises(manifest.ManifestError):
            self.capture(excluded_tables=["misspelled_table"])

    def test_exclusion_mismatch_fails_comparison(self):
        _, before = self.capture()
        after = deepcopy(before)
        after["excluded_tables"] = ["people"]
        self.assertIn("Excluded table lists differ.", manifest.compare(before, after))

    def test_existing_manifest_never_overwritten(self):
        path, _ = self.capture()
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            manifest.snapshot(path, self.media, connection=self.connection)
        self.assertEqual(path.read_bytes(), original)

    def test_failure_removes_only_its_partial_manifest(self):
        path = self.directory / "failed.json"
        with patch.object(manifest, "write_media", side_effect=OSError("private detail")):
            with self.assertRaises(OSError):
                manifest.snapshot(path, self.media, connection=self.connection)
        self.assertFalse(path.exists())
        self.assertTrue((self.media / "upload.bin").is_file())

    def test_output_in_media_and_missing_media_fail(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.snapshot(self.media / "manifest.json", self.media, connection=self.connection)
        with self.assertRaises(manifest.ManifestError):
            manifest.snapshot(self.directory / "manifest.json", self.directory / "missing", connection=self.connection)

    def test_read_only_context_rejects_writes_and_restores_connection(self):
        with manifest.read_only_snapshot(self.connection):
            with self.assertRaises(Exception):
                self.execute("INSERT INTO people (id) VALUES (99)")
        self.execute("INSERT INTO people (id) VALUES (99)")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM people WHERE id = 99")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_chunked_cursor_used(self):
        with patch.object(self.connection, "chunked_cursor", wraps=self.connection.chunked_cursor) as chunked, \
                patch.object(manifest, "CHUNK_SIZE", 1):
            _, snapshot = self.capture()
        self.assertEqual(chunked.call_count, 2)
        self.assertEqual(snapshot["tables"]["people"]["row_count"], 2)

    def test_snapshot_does_not_initialize_django_apps(self):
        with patch("django.setup", side_effect=AssertionError("App startup must not run")) as setup:
            self.capture()
        setup.assert_not_called()

    def test_table_and_column_identifiers_are_quoted(self):
        self.execute('CREATE TABLE "quoted table" ("key column" INTEGER PRIMARY KEY, "select" TEXT)')
        self.execute('INSERT INTO "quoted table" VALUES (1, %s)', ["private fixture"])
        _, before = self.capture()
        self.assertEqual(before["tables"]["quoted table"]["row_count"], 1)
        self.assertEqual(manifest.compare(before, self.capture()[1]), [])

    def test_symlinks_fail_without_reading_their_target(self):
        path = self.directory / "symlink-failure.json"
        original = Path.is_symlink

        def fake_symlink(candidate):
            return candidate.name == "upload.bin" or original(candidate)

        with patch.object(Path, "is_symlink", fake_symlink):
            with self.assertRaisesRegex(manifest.ManifestError, "symlinks"):
                manifest.snapshot(path, self.media, connection=self.connection)
        self.assertFalse(path.exists())

    def test_media_list_change_during_snapshot_fails(self):
        path = self.directory / "changed-list.json"
        with patch.object(manifest, "media_paths", side_effect=[["upload.bin"], ["upload.bin", "new.bin"]]):
            with self.assertRaisesRegex(manifest.ManifestError, "file list changed"):
                manifest.snapshot(path, self.media, connection=self.connection)
        self.assertFalse(path.exists())

    def test_incomplete_or_corrupt_manifests_fail(self):
        _, before = self.capture()
        for field, value in [("complete", False), ("format_version", 99)]:
            invalid = deepcopy(before)
            invalid[field] = value
            with self.assertRaises(manifest.ManifestError):
                manifest.compare(before, invalid)
        before["tables"]["people"]["rows"][0][1] = "invalid"
        with self.assertRaises(manifest.ManifestError):
            manifest.validate_manifest(before)

    def test_cli_exit_status_and_error_redaction(self):
        before_path, _ = self.capture()
        after_path, _ = self.capture(baseline=before_path)
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(manifest.main(["compare", str(before_path), str(after_path)]), 0)
        self.execute("DELETE FROM people")
        changed_path, _ = self.capture(baseline=before_path)
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(manifest.main(["compare", str(before_path), str(changed_path)]), 1)
        with patch.object(manifest, "snapshot", side_effect=RuntimeError("password=private")), \
                patch("sys.stderr", new_callable=io.StringIO) as error:
            self.assertEqual(manifest.main(["snapshot", "--output", "unused", "--media-root", str(self.media)]), 2)
        self.assertNotIn("password", error.getvalue())


class PostgreSQLTransactionTests(unittest.TestCase):
    def test_read_only_repeatable_read_is_first_statement_and_rolled_back(self):
        connection = MagicMock(vendor="postgresql", in_atomic_block=False, alias="default")
        connection.get_autocommit.return_value = True
        with patch("django.db.transaction.atomic") as atomic, \
                patch("django.db.transaction.set_rollback") as rollback:
            with manifest.read_only_snapshot(connection):
                connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        atomic.assert_called_once_with(using="default")
        rollback.assert_called_once_with(True, using="default")

    def test_unsupported_backend_and_nested_transaction_fail(self):
        for connection in (MagicMock(vendor="mysql"), MagicMock(vendor="postgresql", in_atomic_block=True)):
            with self.assertRaises(manifest.ManifestError):
                with manifest.read_only_snapshot(connection):
                    self.fail("must not enter")


if __name__ == "__main__":
    unittest.main()
