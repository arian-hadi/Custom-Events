"""Offline tests: no database, email delivery or external provider requests."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import v2_worker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.heartbeat = Path(self.directory.name) / "heartbeat.json"

    def worker(self, **kwargs):
        return v2_worker.Worker("member-email", interval=1, heartbeat_file=self.heartbeat, **kwargs)

    def test_every_cycle_starts_manage_in_a_fresh_process(self):
        worker = self.worker()
        fake_child = Mock(returncode=0)
        fake_child.poll.return_value = 0
        with patch.object(v2_worker.subprocess, "Popen", return_value=fake_child) as start:
            self.assertEqual(worker.run_cycle(), 0)
            self.assertEqual(worker.run_cycle(), 0)
        self.assertEqual(start.call_count, 2)
        argv = start.call_args.args[0]
        self.assertEqual(argv[:2], [sys.executable, "-u"])
        self.assertEqual(Path(argv[2]).name, "manage.py")
        self.assertEqual(argv[3:], ["member_email_tick", "--limit", "100"])
        self.assertNotIn("shell", start.call_args.kwargs)

    def execute_guarded_cycle(self, script, **switches):
        command = Mock()
        conf = ModuleType("django.conf")
        conf.settings = SimpleNamespace(**switches)
        management = ModuleType("django.core.management")
        management.call_command = command
        automation = ModuleType("edithub.league.automation")
        automation.league_enabled = lambda: switches.get("LEAGUE_ENABLED", False)
        with patch.dict(sys.modules, {"django.conf": conf, "django.core.management": management, "edithub.league.automation": automation}):
            exec(script, {})
        return command

    def test_disabled_league_performs_no_commands(self):
        command = self.execute_guarded_cycle(v2_worker.LEAGUE_CYCLE, LEAGUE_ENABLED=False)
        command.assert_not_called()

    def test_youtube_blog_worker_uses_discovery_command(self):
        self.assertEqual(v2_worker.command_for("youtube-blog")[-1], "youtube_blog_tick")
        self.assertEqual(v2_worker.DEFAULT_INTERVALS["youtube-blog"], 300)

    def test_enabled_league_collects_history_then_ticks_and_collects_entries(self):
        command = self.execute_guarded_cycle(v2_worker.LEAGUE_CYCLE, LEAGUE_ENABLED=True)
        self.assertEqual([call.args for call in command.call_args_list], [("league_ensure",), ("league_history",), ("league_tick",), ("league_collect",)])

    def test_disabled_amazon_still_purges_expired_content(self):
        command = self.execute_guarded_cycle(v2_worker.AMAZON_CYCLE, AMAZON_AUTOMATION_ENABLED=False)
        command.assert_called_once_with("sync_amazon_products", purge_only=True)

    def test_enabled_amazon_uses_bounded_batch(self):
        command = self.execute_guarded_cycle(v2_worker.AMAZON_CYCLE, AMAZON_AUTOMATION_ENABLED=True)
        command.assert_called_once_with("sync_amazon_products", limit=25)

    def test_failed_cycle_waits_then_retries_and_recovers_health(self):
        worker = self.worker()
        health = []
        def wait():
            health.append(v2_worker.healthcheck(self.heartbeat))
            if len(health) == 2:
                worker.request_stop()
        with patch.object(worker, "run_cycle", side_effect=[1, 0]) as run, patch.object(worker, "wait_for_next_cycle", side_effect=wait) as wait_mock:
            self.assertEqual(worker.run(), 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(wait_mock.call_count, 2)
        self.assertEqual(health, [False, True])
        self.assertFalse(v2_worker.healthcheck(self.heartbeat))  # Stopped process.

    def test_idle_wait_obeys_interval_and_keeps_heartbeat(self):
        worker = self.worker()
        worker.interval = 12
        waits = []
        worker.stop = Mock()
        worker.stop.is_set.return_value = False
        worker.stop.wait.side_effect = waits.append
        with patch.object(v2_worker.time, "monotonic", side_effect=[0, 0, 5, 10, 12]):
            worker.wait_for_next_cycle()
        self.assertEqual(waits, [5, 5, 2])
        self.assertTrue(v2_worker.healthcheck(self.heartbeat))

    def test_missing_malformed_stale_and_failed_heartbeats_are_unhealthy(self):
        self.assertFalse(v2_worker.healthcheck(self.heartbeat))
        self.heartbeat.write_text("not json", encoding="utf-8")
        self.assertFalse(v2_worker.healthcheck(self.heartbeat))
        for updated, status, code in [(0, "waiting", 0), (time.time(), "stopped", 0), (time.time(), "waiting", 1)]:
            self.heartbeat.write_text(json.dumps({"updated_at": updated, "status": status, "last_exit_code": code}), encoding="utf-8")
            self.assertFalse(v2_worker.healthcheck(self.heartbeat))
        worker = self.worker()
        worker.heartbeat()
        self.assertTrue(v2_worker.healthcheck(self.heartbeat))

    def test_child_launch_failure_does_not_crash_supervisor(self):
        worker = self.worker()
        with patch.object(v2_worker.subprocess, "Popen", side_effect=OSError("unavailable")):
            self.assertEqual(worker.run_cycle(), 1)

    def test_timeout_terminates_and_reaps_real_child(self):
        worker = self.worker(timeout=0.1)
        command = [sys.executable, "-c", "import time; time.sleep(60)"]
        with patch.object(v2_worker, "command_for", return_value=command):
            self.assertEqual(worker.run_cycle(), 124)
        self.assertIsNone(worker.child)

    def test_stop_request_terminates_and_reaps_real_child(self):
        worker = self.worker()
        command = [sys.executable, "-c", "import time; time.sleep(60)"]
        timer = threading.Timer(0.2, worker.request_stop)
        timer.start()
        self.addCleanup(timer.cancel)
        with patch.object(v2_worker, "command_for", return_value=command):
            self.assertEqual(worker.run_cycle(), 130)
        self.assertIsNone(worker.child)

    @unittest.skipUnless(os.name == "posix", "Process-group shutdown is Linux-specific.")
    def test_sigterm_stops_entire_child_process_group(self):
        worker = self.worker(timeout=0.3)
        command = [sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"]
        worker.shutdown_grace = 0.1
        with patch.object(v2_worker, "command_for", return_value=command), patch.object(v2_worker.os, "killpg", wraps=os.killpg) as killpg:
            self.assertEqual(worker.run_cycle(), 124)
        self.assertEqual([call.args[1] for call in killpg.call_args_list], [signal.SIGTERM, signal.SIGKILL])

    def test_invalid_intervals_cannot_create_busy_loop(self):
        for value in ("0", "-1", "nan", "inf", "bad"):
            with self.assertRaises(v2_worker.argparse.ArgumentTypeError):
                v2_worker.positive_seconds(value)

    def test_once_returns_child_failure_code(self):
        worker = self.worker()
        with patch.object(worker, "run_cycle", return_value=7), patch.object(worker, "wait_for_next_cycle") as wait:
            self.assertEqual(worker.run(once=True), 7)
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
