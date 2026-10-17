"""Exercise the release helper's actual embedded validator without SSH/Docker."""
import ast
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / 'deploy/staging/prepare-release.sh'
COMMIT = 'a' * 40
SOURCE = HELPER.read_text(encoding='utf-8').split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
TREE = ast.parse(SOURCE)
REQUIRED = next(ast.literal_eval(node.value) for node in TREE.body
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'required' for t in node.targets))


class ReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='release-test-', dir=ROOT / 'scripts')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'source.tar'
        self.validator = self.root / 'validator.py'
        self.validator.write_text(SOURCE, encoding='utf-8')

    def archive_with(self, extras=(), omit=(), commit=COMMIT):
        files = REQUIRED - set(omit)
        directories = {str(p) for name in files for p in Path(name).parents if str(p) != '.'}
        with tarfile.open(self.archive, 'w', format=tarfile.PAX_FORMAT, pax_headers={'comment': commit}) as archive:
            for name in sorted(directories):
                entry = tarfile.TarInfo(name.replace('\\', '/'))
                entry.type = tarfile.DIRTYPE
                entry.mode = 0o755
                archive.addfile(entry)
            for name in sorted(files):
                content = HELPER.read_bytes() if name.endswith('prepare-release.sh') else b'source\n'
                entry = tarfile.TarInfo(name)
                entry.mode, entry.size = 0o644, len(content)
                archive.addfile(entry, io.BytesIO(content))
            for name, kind in extras:
                entry = tarfile.TarInfo(name)
                entry.type = kind
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    entry.linkname = '/outside'
                archive.addfile(entry)

    def run_validator(self, mode='validate'):
        return subprocess.run([sys.executable, str(self.validator), mode, COMMIT,
            str(self.archive), str(self.root / 'releases' / COMMIT), str(HELPER)],
            capture_output=True, text=True, timeout=20)

    def test_complete_archive_accepted_without_extraction(self):
        self.archive_with()
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'releases').exists())

    def test_wrong_commit_rejected(self):
        self.archive_with(commit='b' * 40)
        self.assertNotEqual(self.run_validator().returncode, 0)

    def test_missing_runtime_source_rejected(self):
        for path in ['New_Frontend/package-lock.json', 'prime_project/prime_project/settings_v2_staging.py',
                     'scripts/staging_data_manifest.py', 'deploy/staging/nginx.conf.template']:
            with self.subTest(path=path):
                self.archive_with(omit=[path])
                self.assertNotEqual(self.run_validator().returncode, 0)

    def test_secret_and_runtime_files_rejected(self):
        for path in ['.env', '.env.v2.staging', 'prime_project/.env', 'db.sqlite3', 'debug.log',
                     '.staging-v2/private', 'node_modules/pkg', '.test-media/private', '.git/config']:
            with self.subTest(path=path):
                self.archive_with(extras=[(path, tarfile.REGTYPE)])
                self.assertNotEqual(self.run_validator().returncode, 0)

    def test_unsafe_paths_duplicates_and_links_rejected(self):
        for path, kind in [('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE),
                ('a\\escape', tarfile.REGTYPE), ('a/../escape', tarfile.REGTYPE),
                ('compose.v2.staging.yml', tarfile.REGTYPE), ('link', tarfile.SYMTYPE),
                ('hard', tarfile.LNKTYPE), ('device', tarfile.CHRTYPE)]:
            with self.subTest(path=path, kind=kind):
                self.archive_with(extras=[(path, kind)])
                self.assertNotEqual(self.run_validator().returncode, 0)
        self.assertFalse((self.root / 'escape').exists())

    def test_corrupt_archive_fails_without_extracting(self):
        self.archive.write_bytes(b'not a tar file')
        self.assertNotEqual(self.run_validator().returncode, 0)
        self.assertFalse((self.root / 'releases').exists())

    @unittest.skipIf(os.name == 'nt', 'Release permission retry semantics require POSIX')
    def test_prepare_retry_accepts_only_identical_release(self):
        self.archive_with()
        for _ in range(2):
            result = self.run_validator('prepare')
            self.assertEqual(result.returncode, 0, result.stderr)
        target = self.root / 'releases' / COMMIT / 'compose.v2.staging.yml'
        target.write_text('changed', encoding='utf-8')
        self.assertNotEqual(self.run_validator('prepare').returncode, 0)
        self.assertEqual(target.read_text(), 'changed')


if __name__ == '__main__':
    unittest.main()
