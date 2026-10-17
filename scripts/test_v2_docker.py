"""Offline Docker wiring regression tests; never start containers or read secrets.

Run: .venv/Scripts/python.exe -m unittest discover -s scripts -p test_v2_docker.py -v
Compose rendering only requires the Docker CLI/plugin, not its daemon. PowerShell
launcher tests run against a temporary project copy with generated test settings.
"""

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

import environ
import yaml


ROOT = Path(__file__).resolve().parent.parent
JOBS = {"jobs-email": "member-email", "jobs-admin-email": "admin-email",
        "jobs-amazon": "amazon", "jobs-league": "league"}
BACKEND_SERVICES = ["migrate", "backend", *JOBS]


def command_environment():
    """Keep OS tooling usable without inheriting project/provider credentials."""
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "HOME", "USERPROFILE"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


class SettingsIsolationTests(unittest.TestCase):
    def load_settings(self, *, read_file=None, legacy_values=None):
        isolated = {
            "SECRET_KEY": "offline-regression-key", "DEBUG": "True",
            "ALLOWED_HOSTS": "localhost,backend", "DATABASE_URL": "sqlite:///:memory:",
            "ENABLE_EDITHUB_SCHEDULER": "False",
        }
        if read_file is not None:
            isolated["DJANGO_READ_ENV_FILE"] = read_file

        def fake_read_env(*args, **kwargs):
            os.environ.update(legacy_values or {})

        with patch.dict(os.environ, isolated, clear=True), patch.object(environ.Env, "read_env", side_effect=fake_read_env) as read_env:
            settings = runpy.run_path(str(ROOT / "prime_project/prime_project/settings.py"))
        return settings, read_env

    def test_compose_guard_never_reads_mounted_legacy_env(self):
        settings, read_env = self.load_settings(read_file="False", legacy_values={
            "GOOGLE_OAUTH_CLIENT_SECRET": "legacy-secret-sentinel",
            "EMAIL_HOST": "legacy-smtp.invalid", "LEAGUE_ENABLED": "True",
        })
        read_env.assert_not_called()
        self.assertEqual(settings["GOOGLE_OAUTH_CLIENT_SECRET"], "")
        self.assertEqual(settings["EMAIL_HOST"], "localhost")
        self.assertFalse(settings["LEAGUE_ENABLED"])

    def test_default_legacy_setting_preserves_existing_loading_behavior(self):
        settings, read_env = self.load_settings(legacy_values={"EMAIL_HOST": "fake-legacy.invalid"})
        read_env.assert_called_once_with(str(ROOT / "prime_project/.env"))
        self.assertEqual(settings["EMAIL_HOST"], "fake-legacy.invalid")


class ComposeSourceTests(unittest.TestCase):
    """Keep key safety checks available even without the Docker CLI."""

    def test_all_backend_services_have_explicit_environment_isolation(self):
        source = yaml.safe_load((ROOT / "compose.v2.yml").read_text(encoding="utf-8"))
        for name in BACKEND_SERVICES:
            with self.subTest(service=name):
                environment = source["services"][name]["environment"]
                self.assertEqual(environment["DJANGO_READ_ENV_FILE"], "False")
                self.assertEqual(environment["ENABLE_EDITHUB_SCHEDULER"], "False")
                self.assertEqual(environment["DJANGO_SETTINGS_MODULE"], "prime_project.settings")
                self.assertEqual(environment["EMAIL_HOST"], "${EMAIL_HOST:-mailpit}")
                self.assertEqual(environment["STRIPE_ALLOW_LIVE_PAYMENTS"], "False")


class InitializeTests(unittest.TestCase):
    def initialize(self, *, collect_static=None, migration_error=None):
        isolated = {}
        if collect_static is not None:
            isolated["V2_COLLECT_STATIC"] = collect_static
        with patch.dict(os.environ, isolated, clear=True), \
             patch("django.setup") as setup, \
             patch("django.core.management.call_command", side_effect=migration_error) as command:
            if migration_error is not None:
                with self.assertRaisesRegex(RuntimeError, "migration failed"):
                    runpy.run_path(str(ROOT / "prime_project/v2_initialize.py"))
            else:
                runpy.run_path(str(ROOT / "prime_project/v2_initialize.py"))
            self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "prime_project.settings")
        setup.assert_called_once_with()
        return command

    def test_preview_migrates_before_collecting_static(self):
        command = self.initialize()
        self.assertEqual(command.call_args_list, [
            call("migrate", interactive=False),
            call("collectstatic", interactive=False),
        ])

    def test_live_development_only_applies_migrations(self):
        command = self.initialize(collect_static="False")
        command.assert_called_once_with("migrate", interactive=False)

    def test_failed_migration_aborts_initialization(self):
        command = self.initialize(migration_error=RuntimeError("migration failed"))
        command.assert_called_once_with("migrate", interactive=False)


class ComposeMergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker") and not shutil.which("docker-compose"):
            raise unittest.SkipTest("Docker CLI is not installed; static checks still run.")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        temporary = Path(cls.directory.name)
        config_dir = temporary / "docker-config"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("{}", encoding="utf-8")
        cls.command_env = command_environment()
        cls.command_env["DOCKER_CONFIG"] = str(config_dir)
        # Desktop can register its plugin path in the real Docker config. Use
        # the standalone V2 binary if present so even that file stays unread.
        compose = [shutil.which("docker-compose")] if shutil.which("docker-compose") else ["docker", "compose"]
        result = subprocess.run([*compose, "version"], env=cls.command_env,
                                text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise unittest.SkipTest("Docker Compose plugin is unavailable.")
        env_file = temporary / "fake.env"
        env_file.write_text(
            "SECRET_KEY=offline-compose-test-only\nV2_DB_PASSWORD=offline-db-test-only\n"
            "LEAGUE_YOUTUBE_API_KEY=offline-youtube-sentinel\n"
            "STRIPE_ALLOW_LIVE_PAYMENTS=True\n",
            encoding="utf-8",
        )
        common = [*compose, "--env-file", str(env_file), "-f", str(ROOT / "compose.v2.yml")]
        cls.compose_arguments = common
        cls.configurations = {}
        for mode in ["preview", "dev"]:
            command = list(common)
            if mode == "dev":
                command.extend(["-f", str(ROOT / "compose.v2.dev.yml")])
            command.extend(["config", "--format", "json"])
            result = subprocess.run(command, cwd=ROOT, env=cls.command_env, text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise AssertionError(f"{mode} Compose validation failed with isolated fake values: {result.stderr}")
            cls.configurations[mode] = json.loads(result.stdout)

    def test_explicit_smtp_settings_reach_backend_and_workers_only(self):
        smtp = {
            'EMAIL_HOST': 'smtp.example.invalid', 'EMAIL_PORT': '587',
            'EMAIL_HOST_USER': 'sender@example.invalid',
            'EMAIL_HOST_PASSWORD': 'fake-app-password-for-offline-test',
            'EMAIL_USE_TLS': 'True', 'EMAIL_USE_SSL': 'False',
        }
        for mode in ['preview', 'dev']:
            command = list(self.compose_arguments)
            if mode == 'dev':
                command.extend(['-f', str(ROOT / 'compose.v2.dev.yml')])
            result = subprocess.run(command + ['config', '--format', 'json'], cwd=ROOT,
                                    env={**self.command_env, **smtp}, text=True,
                                    capture_output=True, timeout=30, check=True)
            config = json.loads(result.stdout)
            for name in BACKEND_SERVICES:
                with self.subTest(mode=mode, service=name):
                    environment = config['services'][name]['environment']
                    for key, value in smtp.items():
                        self.assertEqual(environment[key], value)
            self.assertNotIn('EMAIL_HOST_PASSWORD', config['services']['frontend']['environment'])

    def test_default_email_stays_in_mailpit(self):
        for config in self.configurations.values():
            for name in BACKEND_SERVICES:
                environment = config['services'][name]['environment']
                self.assertEqual(environment['EMAIL_HOST'], 'mailpit')
                self.assertEqual(environment['EMAIL_PORT'], '1025')
                self.assertEqual(environment['EMAIL_HOST_PASSWORD'], '')
                self.assertEqual(environment['EMAIL_USE_TLS'], 'False')

    def test_both_modes_start_all_jobs_after_migrations(self):
        for mode, config in self.configurations.items():
            for name, job in JOBS.items():
                with self.subTest(mode=mode, job=job):
                    service = config["services"][name]
                    self.assertEqual(service["command"][:3], ["python", "v2_worker.py", job])
                    self.assertEqual(service["depends_on"]["migrate"]["condition"], "service_completed_successfully")
                    self.assertTrue(service["init"])
                    self.assertEqual(service["restart"], "unless-stopped")
                    self.assertEqual(service["stop_grace_period"], "30s")
                    self.assertEqual(service["healthcheck"]["test"][:4], ["CMD", "python", "v2_worker.py", "healthcheck"])
                    self.assertEqual(service["healthcheck"]["start_period"], "30s")

    def test_only_development_skips_static_collection(self):
        for mode, config in self.configurations.items():
            with self.subTest(mode=mode):
                migrate = config["services"]["migrate"]
                self.assertEqual(migrate["command"], ["python", "v2_initialize.py"])
                expected = "False" if mode == "dev" else "True"
                self.assertEqual(migrate["environment"].get("V2_COLLECT_STATIC", "True"), expected)

    def test_live_mounts_preserve_persistent_uploads_and_secret_isolation(self):
        config = self.configurations["dev"]
        for name in BACKEND_SERVICES:
            with self.subTest(service=name):
                volumes = {volume["target"]: volume for volume in config["services"][name]["volumes"]}
                self.assertEqual(volumes["/app"]["type"], "bind")
                self.assertEqual(Path(volumes["/app"]["source"]), ROOT / "prime_project")
                self.assertEqual(volumes["/app/mediafiles"]["type"], "volume")
                self.assertEqual(volumes["/app/staticfiles"]["type"], "volume")
                self.assertTrue(volumes["/run/v2-secrets"]["read_only"])
                environment = config["services"][name]["environment"]
                self.assertEqual(environment["DJANGO_READ_ENV_FILE"], "False")
                self.assertEqual(environment["EMAIL_HOST"], "mailpit")
                self.assertEqual(environment["STRIPE_ALLOW_LIVE_PAYMENTS"], "False")
                self.assertEqual(environment["YOUTUBE_API_KEY"], "offline-youtube-sentinel")

    def test_frontend_uses_linux_dependency_volume_and_polling(self):
        frontend = self.configurations["dev"]["services"]["frontend"]
        self.assertEqual(frontend["build"]["target"], "development")
        self.assertEqual(frontend["environment"]["WATCHPACK_POLLING"], "true")
        self.assertEqual(frontend["environment"]["NODE_ENV"], "development")
        volumes = {volume["target"]: volume for volume in frontend["volumes"]}
        self.assertEqual(volumes["/app"]["type"], "bind")
        self.assertEqual(volumes["/app/node_modules"]["type"], "volume")
        self.assertEqual(volumes["/app/.next"]["type"], "volume")
        self.assertEqual(self.configurations["dev"]["services"]["backend"]["command"],
                         ["python", "manage.py", "runserver", "0.0.0.0:8000"])

    def test_preview_and_dev_share_data_and_only_expose_loopback_ports(self):
        preview, dev = self.configurations["preview"], self.configurations["dev"]
        self.assertEqual(preview["name"], dev["name"])
        self.assertEqual(preview["services"]["db"]["volumes"], dev["services"]["db"]["volumes"])
        for mode, config in self.configurations.items():
            for name, service in config["services"].items():
                for port in service.get("ports", []):
                    with self.subTest(mode=mode, service=name):
                        self.assertEqual(port["host_ip"], "127.0.0.1")
            self.assertNotIn("ports", config["services"]["db"])

    def test_dev_gateway_replaces_config_without_losing_media_volume(self):
        gateway = self.configurations["dev"]["services"]["gateway"]
        volumes = {volume["target"]: volume for volume in gateway["volumes"]}
        self.assertEqual(Path(volumes["/etc/nginx/conf.d/default.conf"]["source"]), ROOT / "deploy/v2/nginx.dev.conf")
        self.assertEqual(volumes["/app/mediafiles"]["type"], "volume")
        self.assertTrue(volumes["/app/mediafiles"]["read_only"])


class PrepareLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not cls.powershell:
            raise unittest.SkipTest("PowerShell is not installed.")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/start-v2.ps1", self.root / "scripts/start-v2.ps1")
        shutil.copyfile(ROOT / ".env.v2.example", self.root / ".env.v2.example")

    def prepare(self):
        result = subprocess.run([self.powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                 str(self.root / "scripts/start-v2.ps1"), "-PrepareOnly"],
                                cwd=self.root, env=command_environment(), text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return (self.root / ".env.v2").read_bytes()

    def test_preparation_generates_local_secrets_and_preserves_existing_values(self):
        generated = self.prepare()
        values = dict(line.split("=", 1) for line in generated.decode("utf-8").splitlines() if line and not line.startswith("#"))
        self.assertRegex(values["SECRET_KEY"], r"^[0-9a-f]{64}$")
        self.assertRegex(values["V2_DB_PASSWORD"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(values["SECRET_KEY"], values["V2_DB_PASSWORD"])
        self.assertEqual(values["LEAGUE_ENABLED"], "False")
        self.assertEqual(values["STRIPE_CHECKOUT_ENABLED"], "False")
        self.assertTrue((self.root / ".local-v2/secrets").is_dir())
        customized = generated + b"\n# Test custom setting\nEXISTING_VALUE=keep-me\n"
        (self.root / ".env.v2").write_bytes(customized)
        self.assertEqual(self.prepare(), customized)


if __name__ == "__main__":
    unittest.main()
