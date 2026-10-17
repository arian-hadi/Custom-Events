"""Offline staging configuration checks: no server, database, or real secrets."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parent.parent


def environment():
    # Docker Desktop discovers CLI plugins using these Windows installation
    # paths. Keep only OS paths, never inherited application/provider settings.
    allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
        'HOME', 'USERPROFILE', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432',
        'PROGRAMDATA', 'APPDATA', 'LOCALAPPDATA'}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


class StagingSettingsTests(unittest.TestCase):
    def settings(self, **overrides):
        env = {**environment(), 'PYTHONPATH': str(ROOT / 'prime_project'),
            'STAGING_SECRET_KEY': 's' * 64, 'STAGING_PUBLIC_URL': 'https://staging.example.test',
            'DATABASE_URL': 'postgres://staging:test@db:5432/staging',
            # These deliberately conflict with staging; never inherit them.
            'DJANGO_READ_ENV_FILE': 'True', 'DEBUG': 'True', 'ENABLE_EDITHUB_SCHEDULER': 'True',
            'EMAIL_HOST': 'smtp.production.invalid', 'EMAIL_HOST_PASSWORD': 'must-not-be-used',
            'STRIPE_ALLOW_LIVE_PAYMENTS': 'True', **overrides}
        keys = ['DEBUG', 'ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'ENABLE_EDITHUB_SCHEDULER',
            'EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_HOST_PASSWORD', 'EMAIL_USE_TLS', 'EMAIL_USE_SSL',
            'SESSION_COOKIE_NAME', 'CSRF_COOKIE_NAME', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
            'STRIPE_ALLOW_LIVE_PAYMENTS', 'V2_FRONTEND_URL', 'MEMBER_EMAIL_BASE_URL', 'SECURE_SSL_REDIRECT']
        code = "import json,runpy; s=runpy.run_module('prime_project.settings_v2_staging'); print(json.dumps({k:s[k] for k in " + repr(keys) + "}))"
        result = subprocess.run([sys.executable, '-c', code], env=env, cwd=ROOT,
            capture_output=True, text=True, timeout=30)
        return result

    def test_staging_overrides_production_side_effects_and_sets_own_cookies(self):
        result = self.settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertFalse(values['DEBUG'])
        self.assertFalse(values['ENABLE_EDITHUB_SCHEDULER'])
        self.assertFalse(values['STRIPE_ALLOW_LIVE_PAYMENTS'])
        self.assertEqual(values['EMAIL_HOST'], 'mailpit')
        self.assertEqual(values['EMAIL_PORT'], 1025)
        self.assertEqual(values['EMAIL_HOST_PASSWORD'], '')
        self.assertTrue(values['SESSION_COOKIE_SECURE'])
        self.assertTrue(values['CSRF_COOKIE_SECURE'])
        self.assertEqual(values['SESSION_COOKIE_NAME'], 'v2_staging_sessionid')
        self.assertEqual(values['CSRF_TRUSTED_ORIGINS'], ['https://staging.example.test'])
        self.assertEqual(values['MEMBER_EMAIL_BASE_URL'], values['V2_FRONTEND_URL'])

    def test_loopback_http_requires_explicit_option(self):
        rejected = self.settings(STAGING_PUBLIC_URL='http://localhost:8083')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('STAGING_ALLOW_HTTP', rejected.stderr)
        accepted = self.settings(STAGING_PUBLIC_URL='http://localhost:8083', STAGING_ALLOW_HTTP='True')
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertFalse(json.loads(accepted.stdout)['SESSION_COOKIE_SECURE'])

    def test_live_stripe_external_database_and_placeholder_secret_rejected(self):
        for values in ({'STRIPE_SECRET_KEY': 'sk_live_fake'},
                       {'DATABASE_URL': 'postgres://user:fake@production.invalid:5432/live'},
                       {'STAGING_SECRET_KEY': 'replace-with-a-new-independent-secret-at-least-50-characters-long'},
                       {'STAGING_PUBLIC_URL': 'https://user:password@staging.example.test'},
                       {'STAGING_PUBLIC_URL': 'https://staging.example.test/path'}):
            with self.subTest(values=list(values)):
                self.assertNotEqual(self.settings(**values).returncode, 0)

    def test_stripe_test_key_is_allowed(self):
        result = self.settings(STRIPE_SECRET_KEY='sk_test_fake')
        self.assertEqual(result.returncode, 0, result.stderr)


class StagingComposeTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((ROOT / 'compose.v2.staging.yml').read_text())

    def test_default_start_has_no_migrations_or_workers(self):
        self.assertEqual(self.config['name'], 'platform-v2-staging')
        services = self.config['services']
        self.assertEqual(services['migrate']['profiles'], ['migration'])
        self.assertEqual(services['audit']['profiles'], ['tools'])
        for name, service in services.items():
            if name.startswith('jobs-'):
                self.assertEqual(service['profiles'], ['jobs'])
            self.assertNotIn('container_name', service)
            self.assertNotIn('env_file', service)
        self.assertNotIn('migrate', services['backend']['depends_on'])

    def test_storage_and_ports_are_distinct_and_no_code_bind_mounts(self):
        services = self.config['services']
        self.assertNotIn('ports', services['db'])
        self.assertTrue(services['gateway']['ports'][0].startswith('${STAGING_BIND_ADDRESS:-127.0.0.1}'))
        self.assertEqual(set(self.config['volumes']), {'staging_postgres', 'staging_static', 'staging_media'})
        for name in ['backend', 'frontend', 'migrate']:
            self.assertTrue(services[name]['image'].startswith('platform-v2-staging-'))
            for volume in services[name].get('volumes', []):
                self.assertNotIn('./prime_project:', volume)
                self.assertNotIn('./New_Frontend:', volume)
                self.assertNotIn('postgres_data_staging', volume)

    def test_all_python_services_use_guarded_settings(self):
        for name, service in self.config['services'].items():
            if name in {'backend', 'migrate', 'audit'} or name.startswith('jobs-'):
                env = service['environment']
                self.assertEqual(env['DJANGO_SETTINGS_MODULE'], 'prime_project.settings_v2_staging')
                self.assertEqual(env['DJANGO_READ_ENV_FILE'], 'False')
                self.assertEqual(env['STRIPE_ALLOW_LIVE_PAYMENTS'], 'False')

    @unittest.skipUnless(shutil.which('docker'), 'Docker CLI unavailable')
    def test_compose_interpolation_without_daemon_or_private_env(self):
        result = subprocess.run(['docker', 'compose', '--env-file', '.env.v2.staging.example',
            '-f', 'compose.v2.staging.yml', 'config', '--format', 'json'], cwd=ROOT,
            env=environment(), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = json.loads(result.stdout)
        self.assertEqual(rendered['services']['backend']['environment']['STAGING_PUBLIC_URL'], 'http://localhost:8083')
        self.assertEqual(rendered['volumes']['staging_postgres']['name'], 'platform-v2-staging_staging_postgres')
        self.assertEqual(rendered['services']['gateway']['ports'][0]['host_ip'], '127.0.0.1')
        self.assertNotIn('ports', rendered['services']['backend'])

    def test_gateway_uses_configured_scheme_and_disables_indexing(self):
        text = (ROOT / 'deploy/staging/nginx.conf.template').read_text()
        self.assertIn('map "${STAGING_PUBLIC_URL}" $staging_public_scheme', text)
        self.assertIn('proxy_set_header X-Forwarded-Proto $staging_public_scheme', text)
        self.assertNotIn('$http_x_forwarded_proto', text)
        self.assertIn('noindex, nofollow, noarchive', text)


if __name__ == '__main__':
    unittest.main()
