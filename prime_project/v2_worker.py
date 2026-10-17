"""Small, single-job local Compose scheduler with reloadable Django children.

Each cycle starts a fresh manage.py process. Bind-mounted application edits are
therefore loaded on the following cycle, without Django autoreload or a second
scheduler inside the web process. Run one container for each job, not replicas.
"""

import argparse
import json
import logging
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_HEARTBEAT = Path(tempfile.gettempdir()) / "v2-worker.json"
DEFAULT_INTERVALS = {"member-email": 60, "admin-email": 60, "amazon": 900, "league": 60, "youtube-blog": 300}
HEARTBEAT_INTERVAL = 5
LOG = logging.getLogger("v2-worker")

# Evaluate feature switches in the child after the current Django settings load.
# league_tick itself does not check LEAGUE_ENABLED, so never call it unguarded.
LEAGUE_CYCLE = """from edithub.league.automation import league_enabled
from django.core.management import call_command
if league_enabled():
    call_command('league_ensure')
    call_command('league_history')
    call_command('league_tick')
    call_command('league_collect')
else:
    print('League processing is disabled; no rounds or scores changed.', flush=True)
"""

# Expired Amazon content must be removed even when fetching is switched off.
# sync_sources() raises on disabled fetching, whereas purge-only is a safe job.
AMAZON_CYCLE = """from django.conf import settings
from django.core.management import call_command
if getattr(settings, 'AMAZON_AUTOMATION_ENABLED', False):
    call_command('sync_amazon_products', limit=25)
else:
    call_command('sync_amazon_products', purge_only=True)
"""


def command_for(job):
    """Return an argv list, never a shell command or provider credentials."""
    command = [sys.executable, "-u", str(BASE_DIR / "manage.py")]
    if job == "member-email":
        return command + ["member_email_tick", "--limit", "100"]
    if job == "admin-email":
        return command + ["send_admin_alerts", "--limit", "100"]
    if job == "youtube-blog":
        return command + ["youtube_blog_tick"]
    if job == "amazon":
        return command + ["shell", "--command", AMAZON_CYCLE]
    if job == "league":
        return command + ["shell", "--command", LEAGUE_CYCLE]
    raise ValueError("Unknown worker job.")


def healthcheck(path, max_age=45):
    """Return health from heartbeat freshness and the last completed cycle."""
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        age = time.time() - state["updated_at"]
        return (
            math.isfinite(age)
            and -10 <= age <= max_age
            and state["status"] in {"starting", "running", "waiting"}
            and state["last_exit_code"] in {None, 0}
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


class Worker:
    def __init__(self, job, *, interval, timeout=600, heartbeat_file=DEFAULT_HEARTBEAT,
                 shutdown_grace=10):
        self.job = job
        self.interval = interval
        self.timeout = timeout
        self.heartbeat_file = Path(heartbeat_file)
        self.shutdown_grace = shutdown_grace
        self.stop = threading.Event()
        self.child = None
        self.state = {
            "job": job, "pid": os.getpid(), "status": "starting",
            "last_exit_code": None, "last_finished_at": None,
        }

    def request_stop(self, signum=None, frame=None):
        # Signal handlers only set a flag; the main loop reaps the child.
        self.stop.set()

    def heartbeat(self):
        self.state["updated_at"] = time.time()
        self.heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.heartbeat_file.with_name(self.heartbeat_file.name + ".tmp")
        temporary.write_text(json.dumps(self.state), encoding="utf-8")
        temporary.replace(self.heartbeat_file)

    def terminate_child(self):
        child = self.child
        if child is None or child.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(child.pid, signal.SIGTERM)
            else:
                child.terminate()
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=self.shutdown_grace)
        except subprocess.TimeoutExpired:
            LOG.warning("%s child did not stop in time; terminating it.", self.job)
            try:
                if os.name == "posix":
                    os.killpg(child.pid, signal.SIGKILL)
                else:
                    child.kill()
            except ProcessLookupError:
                pass
            child.wait(timeout=5)

    def run_cycle(self):
        """Run at most one child, inheriting settings and streaming its logs."""
        try:
            self.child = subprocess.Popen(
                command_for(self.job), cwd=BASE_DIR,
                # A group lets Docker shutdown stop any children too.
                start_new_session=(os.name == "posix"),
            )
        except OSError as exc:
            LOG.error("%s could not start (%s); retrying next cycle.", self.job, type(exc).__name__)
            return 1
        deadline = time.monotonic() + self.timeout
        next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL
        try:
            while self.child.poll() is None:
                if self.stop.is_set():
                    self.terminate_child()
                    return 130
                if time.monotonic() >= deadline:
                    LOG.error("%s exceeded its %.0fs time limit.", self.job, self.timeout)
                    self.terminate_child()
                    return 124
                if time.monotonic() >= next_heartbeat:
                    self.heartbeat()
                    next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL
                self.stop.wait(min(0.5, max(0, deadline - time.monotonic())))
            return self.child.returncode
        finally:
            self.terminate_child()
            self.child = None

    def wait_for_next_cycle(self):
        # Delay from completion avoids overlaps and catch-up bursts after a slow
        # provider request. A failed cycle waits the same bounded interval.
        deadline = time.monotonic() + self.interval
        while not self.stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self.stop.wait(min(HEARTBEAT_INTERVAL, remaining))
            self.heartbeat()

    def run(self, *, once=False):
        self.heartbeat()
        try:
            while not self.stop.is_set():
                self.state["status"] = "running"
                self.heartbeat()
                code = self.run_cycle()
                self.state.update(last_exit_code=code, last_finished_at=time.time(), status="waiting")
                self.heartbeat()
                if self.stop.is_set():
                    return 0
                if code:
                    LOG.error("%s cycle exited with code %s; retrying in %.0fs.", self.job, code, self.interval)
                else:
                    LOG.info("%s cycle complete; next run in %.0fs.", self.job, self.interval)
                if once:
                    return code
                self.wait_for_next_cycle()
            return 0
        finally:
            self.terminate_child()
            self.state["status"] = "stopped"
            self.heartbeat()


def positive_seconds(value):
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use a number of seconds.") from exc
    if not math.isfinite(seconds) or seconds < 1:
        raise argparse.ArgumentTypeError("Use a finite number of seconds of at least 1.")
    return seconds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=[*DEFAULT_INTERVALS, "healthcheck"])
    parser.add_argument("--interval", type=positive_seconds)
    parser.add_argument("--timeout", type=positive_seconds, default=600)
    parser.add_argument("--heartbeat-file", type=Path, default=DEFAULT_HEARTBEAT)
    parser.add_argument("--max-age", type=positive_seconds, default=45)
    parser.add_argument("--once", action="store_true", help="Run exactly one bounded cycle and exit.")
    args = parser.parse_args(argv)
    if args.job == "healthcheck":
        return 0 if healthcheck(args.heartbeat_file, args.max_age) else 1
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = Worker(args.job, interval=args.interval or DEFAULT_INTERVALS[args.job],
                    timeout=args.timeout, heartbeat_file=args.heartbeat_file)
    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    return worker.run(once=args.once)


if __name__ == "__main__":
    sys.exit(main())
