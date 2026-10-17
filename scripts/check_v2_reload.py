"""Opt-in live Docker development check with temporary, self-cleaning probes.

Run from a host with this project's Python/Playwright dependencies installed.
Uses Edge if installed, otherwise Playwright Chromium. No accounts or emails are
created. Temporary frontend route and Python comment are removed in finally.
"""
import json
from pathlib import Path
import subprocess
import time
import uuid

import requests
from playwright.sync_api import sync_playwright, expect


ROOT = Path(__file__).resolve().parents[1]
SITE = "http://localhost:8082"


def docker(*arguments):
    result = subprocess.run(["docker", *arguments], cwd=ROOT, capture_output=True,
                            text=True, timeout=30, check=True)
    return result.stdout


def validate_development_stack():
    inspected = json.loads(docker("inspect", "platform-v2-frontend-1", "platform-v2-backend-1"))
    for container in inspected:
        service = container["Config"]["Labels"]["com.docker.compose.service"]
        expected = ROOT / ("New_Frontend" if service == "frontend" else "prime_project")
        mount = next((item for item in container["Mounts"] if item["Destination"] == "/app"), None)
        if not mount or mount["Type"] != "bind":
            raise RuntimeError("This check requires the V2 live development source mounts.")
        # Docker Desktop may return Windows paths or a Linux host-mount path.
        actual = mount["Source"].replace("\\", "/").rstrip("/").lower()
        expected_path = expected.as_posix().lower()
        candidates = {expected_path}
        if len(expected_path) > 2 and expected_path[1:3] == ':/':
            drive_path = expected_path[0] + '/' + expected_path[3:]
            candidates.update('/' + prefix + drive_path for prefix in ['run/desktop/mnt/host/', 'host_mnt/'])
        if actual not in candidates:
            raise RuntimeError("The running source mount does not match this checkout.")
        if container["Config"]["Labels"]["com.docker.compose.project"] != "platform-v2":
            raise RuntimeError("Refusing to probe a different Docker project.")
    if requests.get(SITE + "/api/v2/site/", timeout=20).status_code != 200:
        raise RuntimeError("The local V2 gateway is not ready on port 8082.")


def frontend_probe():
    name = "docker-live-test-" + uuid.uuid4().hex
    directory = ROOT / "New_Frontend/app" / name
    directory.mkdir()
    page_file = directory / "page.tsx"
    content = """'use client';
import {useEffect, useState} from 'react';
export default function DockerReloadProbe() {
  const [count, setCount] = useState(0);
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  return <main><h1>PROBE_MARKER</h1><button disabled={!ready} onClick={() => setCount(count + 1)}>Increment test counter</button><p data-testid="counter">{count}</p></main>;
}
"""
    try:
        page_file.write_text(content.replace("PROBE_MARKER", "Docker live probe one"), encoding="utf-8")
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
            except Exception:
                browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                sockets = []
                page.on("websocket", lambda socket: sockets.append(socket.url))
                page.goto(SITE + "/" + name, wait_until="domcontentloaded", timeout=120000)
                page.get_by_role("button", name="Increment test counter").click()
                expect(page.get_by_test_id("counter")).to_have_text("1")
                page_file.write_text(content.replace("PROBE_MARKER", "Docker live probe two"), encoding="utf-8")
                expect(page.get_by_role("heading", name="Docker live probe two")).to_be_visible(timeout=60000)
                expect(page.get_by_test_id("counter")).to_have_text("1")
                if not any("/_next/" in url for url in sockets):
                    raise RuntimeError("No Next development WebSocket was observed through the gateway.")
                print("PASS frontend Fast Refresh through gateway; edited text appeared without losing component state")
            finally:
                browser.close()
    finally:
        page_file.unlink(missing_ok=True)
        directory.rmdir()


def backend_processes():
    return docker("top", "platform-v2-backend-1", "-eo", "pid,args")


def backend_probe():
    source = ROOT / "prime_project/platform_api/views.py"
    marker = ("\n# Docker reload probe " + uuid.uuid4().hex + "\n").encode()
    before = backend_processes()
    with source.open("ab") as stream:
        stream.write(marker)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if backend_processes() != before:
                try:
                    if requests.get(SITE + "/api/v2/site/", timeout=5).status_code == 200:
                        print("PASS Django restarted its development process after a host Python edit")
                        return
                except requests.RequestException:
                    pass
            time.sleep(1)
        raise RuntimeError("Django did not reload after a source edit.")
    finally:
        # Remove only our unique comment; retain any concurrent unrelated edit.
        current = source.read_bytes()
        if marker in current:
            source.write_bytes(current.replace(marker, b"", 1))


def static_probe():
    name = 'docker-live-test-' + uuid.uuid4().hex + '.css'
    source = ROOT / 'prime_project/theme/static_src' / name
    try:
        for marker in ['source-one', 'source-two']:
            content = '/* ' + marker + ' */\n'
            source.write_bytes(content.encode('utf-8'))
            response = requests.get(SITE + '/static/' + name, timeout=15)
            assert response.status_code == 200 and response.text == content, (response.status_code, repr(response.text[:150]))
        print('PASS Django static source changes appear through the gateway without collectstatic')
    finally:
        source.unlink(missing_ok=True)


if __name__ == "__main__":
    validate_development_stack()
    frontend_probe()
    static_probe()
    backend_probe()
