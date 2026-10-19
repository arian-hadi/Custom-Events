"""Deployment decisions tested without Docker or server data changes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'deploy/staging/deploy_release.py'
SPEC = importlib.util.spec_from_file_location('staging_deploy', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
OLD, NEW = 'a' * 40, 'b' * 40
PROJECT = MODULE.PROJECT


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='deploy-test-', dir=SOURCE.parents[2] / 'scripts')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for revision in (OLD, NEW):
            release = self.root / 'releases' / revision
            release.mkdir(parents=True)
            (release / 'compose.v2.staging.yml').write_text('name: platform-v2-staging\n')
        self.env = self.root / '.env.v2.staging'
        self.original = 'STAGING_SECRET_KEY=test-only\nSTAGING_IMAGE_TAG=' + OLD + '\n'
        self.env.write_text(self.original)
        self.calls = []
        self.services = 'db\nbackend\nfrontend\ngateway\nmailpit\n'
        self.volume = PROJECT + '_staging_postgres'
        self.backend_image = PROJECT + '-backend:' + OLD
        self.fail_migration = False
        self.fail_health = set()
        self.transient_failures = 0
        self.sleeps = []
        self.deployment = MODULE.Deployment(self.root, NEW, self.runner, self.sleeps.append)

    def runner(self, args, *, env=None, capture=False):
        revision = env.get('STAGING_IMAGE_TAG') if env else None
        self.calls.append((revision, args))
        if args[:2] == ['docker', 'inspect']:
            if args[-1] == PROJECT + '-db-1':
                return json.dumps([{'Config': {'Labels': {
                    'com.docker.compose.project': PROJECT,
                    'com.docker.compose.service': 'db'}}, 'State': {'Running': True},
                    'Mounts': [{'Name': self.volume, 'Destination': '/var/lib/postgresql/data'}]}])
            return json.dumps([{'Config': {'Image': self.backend_image, 'Labels': {
                'com.docker.compose.project.config_files': str(self.root / 'releases' / OLD / 'compose.v2.staging.yml')}}}])
        if args[:2] == ['docker', 'ps']:
            return self.services
        if args[-2:] == ['migrate', '--check'] and self.fail_migration:
            raise subprocess.CalledProcessError(1, args)
        if 'wget' in args and (revision in self.fail_health or self.transient_failures):
            self.transient_failures = max(0, self.transient_failures - 1)
            raise subprocess.CalledProcessError(1, args)
        return '[]' if capture else None

    def test_success_preserves_configuration_and_persists_healthy_revision(self):
        self.deployment.execute()
        self.assertEqual(self.env.read_text(), self.original.replace(OLD, NEW))
        self.assertEqual((self.root / 'current-release').read_text().strip(), NEW)
        result = json.loads((self.root / 'last-deployment.json').read_text())
        self.assertEqual(result['previous_revision'], OLD)
        self.assertFalse(result['database_migrated'])
        self.assertFalse(result['workers_started'])
        commands = [args for _, args in self.calls]
        app = next(i for i, args in enumerate(commands) if '--wait' in args)
        gateway = next(i for i, args in enumerate(commands) if '--force-recreate' in args)
        self.assertLess(app, gateway)
        self.assertFalse(any('down' in args or 'prune' in args for args in commands))
        self.assertEqual([args[-2:] for args in commands if 'manage.py' in args and 'migrate' in args[-2:]], [['migrate', '--check']])

    def test_pending_migrations_leave_services_unchanged(self):
        self.fail_migration = True
        with self.assertRaisesRegex(RuntimeError, 'Pending database migrations'):
            self.deployment.execute()
        self.assertFalse(any('up' in args or 'collectstatic' in args for _, args in self.calls))
        self.assertEqual(self.env.read_text(), self.original)

    def test_failed_health_restores_previous_release(self):
        self.fail_health.add(NEW)
        with self.assertRaisesRegex(RuntimeError, 'previous V2 release restored'):
            self.deployment.execute()
        self.assertTrue(any(rev == OLD and '--wait' in args for rev, args in self.calls))
        self.assertEqual(self.env.read_text(), self.original)
        self.assertFalse((self.root / 'current-release').exists())

    def test_gateway_startup_retries_without_rollback(self):
        self.transient_failures = 2
        self.deployment.execute()
        self.assertEqual(self.sleeps, [2, 2])
        self.assertFalse(any(rev == OLD and 'up' in args for rev, args in self.calls))

    def test_failed_rollback_does_not_report_success(self):
        self.fail_health.update((NEW, OLD))
        with self.assertRaises(subprocess.CalledProcessError):
            self.deployment.execute()
        self.assertFalse((self.root / 'last-deployment.json').exists())
        self.assertEqual(self.env.read_text(), self.original)

    def test_foreign_database_volume_rejected(self):
        self.volume = 'production_postgres'
        with self.assertRaisesRegex(ValueError, 'isolated V2 staging database'):
            self.deployment.execute()
        self.assertEqual(len(self.calls), 1)

    def test_running_workers_require_review(self):
        self.services += 'jobs-email\n'
        with self.assertRaisesRegex(ValueError, 'worker deployment'):
            self.deployment.execute()
        self.assertFalse(any(args[:2] == ['docker', 'compose'] for _, args in self.calls))

    def test_unknown_rollback_image_rejected(self):
        self.backend_image = 'production-web'
        with self.assertRaisesRegex(ValueError, 'rollback'):
            self.deployment.execute()
        self.assertFalse(any(args[:2] == ['docker', 'compose'] for _, args in self.calls))

    def test_invalid_revision_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.Deployment(self.root, '../staging', self.runner)


if __name__ == '__main__':
    unittest.main()
