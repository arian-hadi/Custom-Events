"""Check the local V2 gateway; --run-flows adds isolated Mailpit-backed user flows.

Usage: .venv/Scripts/python.exe scripts/check_v2.py [--run-flows]
No real accounts are modified. An opt-in run leaves one uniquely named synthetic
account and its captured email for inspection. Container secrets are never printed.
"""
import argparse
import json
import re
import secrets
import string
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests


class CheckFailed(Exception):
    pass


def local_origin(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username or parsed.password or parsed.path not in {"", "/"}
        or parsed.query or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("Use an http://localhost or loopback origin without a path.")
    return value.rstrip("/")


def demand(condition, message):
    if not condition:
        raise CheckFailed(message)


class LocalChecks:
    def __init__(self, site, mailpit):
        self.site = site
        self.mailpit = mailpit
        self.session = requests.Session()
        self.session.trust_env = False
        self.mail = requests.Session()
        self.mail.trust_env = False
        self.token = None
        self.synthetic_email = None

    def request(self, method, path, *, data=None, status=200, csrf=True):
        headers = {"X-CSRFToken": self.token} if self.token and csrf else {}
        response = self.session.request(
            method, self.site + "/api/v2/" + path, json=data, headers=headers,
            timeout=20, allow_redirects=False,
        )
        demand(response.status_code == status, f"{method} {path}: expected HTTP {status}, got {response.status_code}.")
        try:
            result = response.json()
        except ValueError as exc:
            raise CheckFailed(f"{method} {path}: expected JSON.") from exc
        if "csrf_token" in result:
            self.token = result["csrf_token"]
        return result

    def read_only(self):
        self.request("GET", "site/")
        for path in ("products/", "blog/", "announcements/", "events/"):
            data = self.request("GET", path)
            demand(isinstance(data.get("results"), list), f"{path}: missing list payload.")
        self.request("GET", "contact/")
        session = self.request("GET", "auth/session/")
        demand(session.get("user") is None and bool(self.token), "Expected a fresh anonymous session and CSRF token.")
        for path in ("favorites/", "applications/", "notifications/", "notification-preferences/"):
            self.request("GET", path, status=401)
        # Empty requests cannot send email or create a user, even if CSRF regresses.
        self.request("POST", "contact/", data={}, status=403, csrf=False)
        self.request("POST", "auth/login/", data={}, status=403, csrf=False)
        print("PASS public API, anonymous permissions, and CSRF rejection")

    @staticmethod
    def docker_json(arguments):
        result = subprocess.run(
            ["docker", *arguments], capture_output=True, text=True, timeout=30,
            cwd=Path(__file__).resolve().parents[1], check=False,
        )
        # Docker stderr can include local paths/config; never dump inspect output.
        demand(result.returncode == 0, "Docker inspection failed. Run with access to the local Docker daemon.")
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise CheckFailed("Docker returned an unexpected inspection response.") from exc

    def verify_mail_sandbox(self):
        names = ["platform-v2-backend-1", "platform-v2-mailpit-1", "platform-v2-gateway-1"]
        inspected = self.docker_json(["inspect", *names])
        services = {}
        for item in inspected:
            labels = item.get("Config", {}).get("Labels", {}) or {}
            demand(labels.get("com.docker.compose.project") == "platform-v2" and item.get("State", {}).get("Running"), "Only the running, dedicated platform-v2 Compose project is supported.")
            services[labels.get("com.docker.compose.service")] = item
        demand(set(services) == {"backend", "mailpit", "gateway"}, "Missing V2 services.")
        environment = dict(item.split("=", 1) for item in services["backend"]["Config"].get("Env", []) if "=" in item)
        demand(environment.get("EMAIL_BACKEND") == "django.core.mail.backends.smtp.EmailBackend", "Flow check requires the SMTP development mail backend.")
        demand(environment.get("EMAIL_HOST") == "mailpit" and environment.get("EMAIL_PORT") == "1025", "Refusing flows: backend mail does not point at local Mailpit.")
        demand(environment.get("ENABLE_EDITHUB_SCHEDULER", "").lower() == "false", "Refusing flows: V2 legacy scoring scheduler must be disabled.")
        demand(not environment.get("RECAPTCHA_SITE_KEY") and not environment.get("RECAPTCHA_SECRET_KEY"), "Automated local signup requires blank development reCAPTCHA keys; keep configured keys for manual browser testing.")
        config = services["mailpit"]["Config"]
        relay_env = [entry for entry in config.get("Env", []) if entry.startswith(("MP_SMTP_RELAY", "MP_SMTP_FORWARD"))]
        demand(not any(entry.partition("=")[2] for entry in relay_env), "Refusing flows: Mailpit relay/forward configuration is present.")
        command = " ".join(config.get("Cmd") or [])
        demand("smtp-relay" not in command and "smtp-forward" not in command and not services["mailpit"].get("Mounts"), "Refusing flows: Mailpit has custom relay/configuration mounts.")
        for service, origin, container_port in (("gateway", self.site, "80/tcp"), ("mailpit", self.mailpit, "8025/tcp")):
            bindings = services[service].get("NetworkSettings", {}).get("Ports", {}).get(container_port) or []
            port = str(urlsplit(origin).port or 80)
            demand(any(binding.get("HostPort") == port and binding.get("HostIp") in {"127.0.0.1", "::1"} for binding in bindings), f"{service}: origin does not match a loopback-only published V2 port.")
        self.mail_get("/api/v1/messages")
        print("PASS dedicated local gateway and Mailpit capture-only configuration")

    def mail_get(self, path):
        response = self.mail.get(self.mailpit + path, timeout=10, allow_redirects=False)
        demand(response.status_code == 200, f"Mailpit {path.split('?')[0]} did not return HTTP 200.")
        try:
            return response.json()
        except ValueError as exc:
            raise CheckFailed("Mailpit returned unexpected content.") from exc

    def find_message(self, *, recipient=None, subject=None):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            listing = self.mail_get("/api/v1/messages?start=0&limit=100")
            for message in listing.get("messages", []):
                recipients = {item.get("Address", "").lower() for item in message.get("To", [])}
                if (not recipient or recipient.lower() in recipients) and (not subject or message.get("Subject") == subject):
                    return self.mail_get("/api/v1/message/" + message["ID"])
            time.sleep(0.5)
        raise CheckFailed("Expected synthetic message was not captured by Mailpit within 10 seconds.")

    def flows(self):
        self.verify_mail_sandbox()
        suffix = "".join(secrets.choice(string.ascii_lowercase) for _ in range(12))
        self.synthetic_email = f"v2-smoke-{suffix}@example.com"
        username = f"v2smoke_{suffix}"
        password = secrets.token_urlsafe(24) + "Aa1!"
        result = self.request("POST", "auth/register/", data={
            "email": self.synthetic_email, "username": username,
            "password1": password, "password2": password,
            "website": "", "url": "", "phone": "",
        }, status=201)
        demand(result.get("verification_required"), "Signup must require verification.")
        email = self.find_message(recipient=self.synthetic_email)
        code = re.search(r"\b\d{6}\b", email.get("Text", ""))
        demand(code, "Captured verification message did not contain a six-digit OTP.")
        verified = self.request("POST", "auth/verify-email/", data={"email": self.synthetic_email, "code": code.group()})
        demand(verified.get("user", {}).get("is_verified"), "OTP verification did not establish a verified session.")
        self.request("POST", "auth/logout/", data={})
        signed_in = self.request("POST", "auth/login/", data={"email": self.synthetic_email, "password": password})
        demand(signed_in.get("user", {}).get("email") == self.synthetic_email, "Signed into an unexpected user.")
        print("PASS synthetic signup -> captured OTP -> verification -> logout/login")
        self.request("PATCH", "notification-preferences/", data={"email_enabled": False, "in_app_enabled": True})
        prefs = self.request("GET", "notification-preferences/")
        demand(prefs["preferences"]["email_enabled"] is False and prefs["email_delivery_active"] is False, "Preferences did not persist or deferred email was incorrectly enabled.")
        self.request("PATCH", "notification-preferences/", data={"email_enabled": True}, status=403, csrf=False)
        subject = f"V2 smoke contact {suffix}"
        self.request("POST", "contact/", data={"name": username, "email": self.synthetic_email, "subject": subject, "message": "Local synthetic integration check; no reply needed.", "website": ""})
        captured = self.find_message(subject="Contact Form: " + subject)
        demand(self.synthetic_email in captured.get("Text", ""), "Captured contact message did not match the synthetic sender.")
        self.request("POST", "auth/logout/", data={})
        self.request("GET", "notification-preferences/", status=401)
        print("PASS persisted preferences, authenticated CSRF rejection, contact captured in Mailpit, and logout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=local_origin, default="http://localhost:8082")
    parser.add_argument("--mailpit", type=local_origin, default="http://localhost:8026")
    parser.add_argument("--run-flows", action="store_true", help="Create one synthetic account and local Mailpit messages after checking Docker isolation.")
    args = parser.parse_args()
    checks = LocalChecks(args.site, args.mailpit)
    try:
        checks.read_only()
        if args.run_flows:
            checks.flows()
        else:
            print("Read-only checks complete. Add --run-flows to test local signup, preferences, and contact email.")
        return 0
    except (CheckFailed, requests.RequestException, subprocess.SubprocessError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if checks.synthetic_email:
            print(f"Synthetic test account (if created) and Mailpit messages retained: {checks.synthetic_email}")


if __name__ == "__main__":
    raise SystemExit(main())
