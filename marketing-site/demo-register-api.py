#!/usr/bin/env python3
"""Marketing-site form API with email + SMTP delivery.

All adicc-uae.com marketing forms POST here through Caddy
(``/api/* -> 172.19.0.1:8891/...``) so they share a single SMTP path
and a single per-IP rate-limiter. Backend FastAPI restarts during a
deploy do NOT interrupt form submission because this service is its
own process.

Endpoints
---------
POST /register          - Demo signup with email verification flow.
GET  /verify?token=X    - Confirms a demo signup, redirects to /demo.
POST /license-request   - Commercial licence quote request.
POST /inquiry           - General contact / custom-build inquiry.
POST /subscribe         - Newsletter signup (footer + popup forms).
POST /partners-apply    - Partner program application.
GET  /health            - Liveness probe ({status, email backend}).

All POSTs are rate-limited per IP (sliding 1h window) and honeypot-
protected via the form's ``_honey`` hidden field. Failed SMTP sends do
NOT fail the request - submissions are persisted to JSONL first so
the lead survives mail-server outages.

Supports: SMTP (any provider) or Resend API. SMTP is preferred when
both are configured (this is the in-house hosting SMTP setup).

Listens on port 8891.

Environment variables:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM  - for SMTP
  RESEND_API_KEY, RESEND_FROM                              - for Resend API
  ADMIN_EMAIL                                              - admin notification
  BASE_URL                                                 - site URL
"""

import hashlib
import json
import os
import re
import secrets
import smtplib
import sys
import threading
import time
import urllib.request
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8891

# ─── Rate limiting ───────────────────────────────────────────────────────
#
# Per-IP sliding-window throttle for the marketing form endpoints. We
# keep one timestamp deque per (ip, bucket) pair and drop entries older
# than the window. Memory stays bounded because we trim on every check
# and only buckets that recently received traffic are retained - there
# is a janitor thread that prunes idle buckets every 5 min.
#
# Caps are intentionally generous for legitimate users (5/h for the
# heavyweight forms, 30/h for newsletter) and tight enough to throttle
# the typical bot floods we saw in production logs.

_RATE_WINDOW_SEC = 3600
_RATE_LIMITS: dict[str, int] = {
    "subscribe": 30,        # Newsletter - light, cheap, lots of legit re-tries
    "inquiry": 5,           # Custom build / contact - heavier; humans rarely re-send
    "partners_apply": 5,    # Partner application - same shape as inquiry
    "license_request": 5,   # Mirrors inquiry - keep existing behaviour
    "register": 5,          # Demo registration - keep existing behaviour
}

_rate_state: dict[tuple[str, str], deque[float]] = {}
_rate_lock = threading.Lock()


def _rate_limit_check(ip: str, bucket: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_sec). Caller MUST respect retry."""
    limit = _RATE_LIMITS.get(bucket)
    if not limit:
        return True, 0
    now = time.time()
    cutoff = now - _RATE_WINDOW_SEC
    key = (ip, bucket)
    with _rate_lock:
        q = _rate_state.get(key)
        if q is None:
            q = deque()
            _rate_state[key] = q
        # Drop expired entries
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            # Oldest entry tells us when the window will free up
            retry = max(1, int(q[0] + _RATE_WINDOW_SEC - now))
            return False, retry
        q.append(now)
        return True, 0


def _rate_state_janitor() -> None:
    """Drop fully-expired buckets every 5 min so memory stays bounded."""
    while True:
        time.sleep(300)
        cutoff = time.time() - _RATE_WINDOW_SEC
        with _rate_lock:
            dead = [k for k, q in _rate_state.items() if not q or q[-1] < cutoff]
            for k in dead:
                _rate_state.pop(k, None)

# ─── Anti-spam / fake-identity gate ──────────────────────────────────────
#
# Goal: stop the firehose of "Test / 123 / тест / asdf" registrations
# from polluting the demo-signups list and (more importantly) auto-
# verifying themselves into the live demo. Two layers:
#
#   1. Junk-name detection - rejects literal "test", "тест", "123",
#      "asdf", repeated single chars, all-digit names, and obvious
#      keyboard runs ("qwerty", "asdf", "zxcv").
#   2. Disposable / fake email domain detection - rejects mailinator-
#      style throwaway addresses, plus the specific domains we already
#      saw being abused in production data (lealking.com, nyspring.com,
#      nazisat.com, agoalz.com, algarr.com).
#
# Tuning principle: prefer false-negatives over false-positives. A real
# user named "Li" or with a personal gmail must always pass. Only
# reject when *strongly* confident the input is junk.

_DISPOSABLE_EMAIL_DOMAINS: frozenset[str] = frozenset({
    # Well-known throwaway providers
    "mailinator.com", "tempmail.com", "tempmail.net", "temp-mail.org",
    "10minutemail.com", "10minutemail.net", "guerrillamail.com",
    "guerrillamail.net", "guerrillamail.org", "throwawaymail.com",
    "yopmail.com", "trashmail.com", "trashmail.net", "fakeinbox.com",
    "sharklasers.com", "getairmail.com", "dispostable.com",
    "mailnesia.com", "maildrop.cc", "mintemail.com", "mohmal.com",
    "dropmail.me", "harakirimail.com", "mvrht.net", "spam4.me",
    "tmpmail.org", "tmpmail.net", "spamgourmet.com", "discard.email",
    "incognitomail.com", "anonbox.net", "mytrashmail.com",
    # Caught in our production logs (Apr 2026 batch)
    "lealking.com", "nyspring.com", "nazisat.com", "agoalz.com",
    "algarr.com",
    # Obvious test placeholders
    "example.com", "example.org", "example.net", "test.com", "test.test",
    "localhost", "localhost.localdomain", "invalid", "invalid.com",
    "qq.com.test", "asdf.com", "qwerty.com", "123.com", "123.ry",
})

# Email local-part patterns we always reject (case-insensitive).
# Tied to common spam shapes - be conservative.
_JUNK_LOCALPART_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^test\d*$", re.I),
    re.compile(r"^tests\d*$", re.I),
    re.compile(r"^demo\d*$", re.I),
    re.compile(r"^asdf*$", re.I),
    re.compile(r"^qwer(ty)?\d*$", re.I),
    re.compile(r"^abc\d*$", re.I),
    re.compile(r"^123+$"),
    re.compile(r"^a+$", re.I),
    re.compile(r"^x+$", re.I),
    re.compile(r"^(.)\1{2,}$"),  # "aaaa", "1111", "...."
)

# Junk first/last name shapes. Lower-cased before matching.
_JUNK_NAME_LITERALS: frozenset[str] = frozenset({
    "test", "tests", "testing", "тест", "тестт", "тесттт",
    "demo", "demouser", "user", "юзер",
    "asdf", "asdfg", "asdfgh", "asd", "asdq", "asdwq", "asde",
    "qwer", "qwerty", "qwertyu", "qwe",
    "zxcv", "zxcvb", "zxcvbn",
    "abc", "abcd", "abcde", "abcdef",
    "aaa", "bbb", "ccc", "xxx", "yyy", "zzz",
    "wer", "werd", "wert",
    "fff", "ggg", "ddd", "sss", "aaaa",
    "fake", "n/a", "na", "none", "nobody", "anonymous",
    "lol", "lmao", "kek", "hehe", "haha",
    "ыва", "фыв", "фыва", "ываф", "йцу", "йцук", "йцукен",
})


def _validate_real_identity(data: dict) -> tuple[bool, str | None, str | None]:
    """Reject obviously-fake demo signups.

    Returns (ok, field, message). When ok is False, field names the
    offending input ("firstName" / "lastName" / "email") and message
    is a user-facing string the form should display verbatim.
    Backend is the source of truth - even if a client skips its own
    validation, this gate runs before anything is persisted.
    """
    first = (data.get("firstName") or "").strip()
    last = (data.get("lastName") or "").strip()
    email = (data.get("email") or "").strip().lower()

    # Names: minimum 2 chars each (covers "Li", "Wu", etc. - real),
    # rejects single-letter and empty after trim.
    if len(first) < 2:
        return False, "firstName", "Please enter your real first name."
    if len(last) < 2:
        return False, "lastName", "Please enter your real last name."

    def _is_junk_name(name: str) -> bool:
        lc = name.lower()
        if lc in _JUNK_NAME_LITERALS:
            return True
        # All digits ("123", "12345")
        if lc.isdigit():
            return True
        # All the same character ("aaa", "....", "----")
        if len(set(lc)) == 1 and len(lc) >= 2:
            return True
        # Strip non-letters and check what's left - catches "123 abc"
        letters_only = re.sub(r"[^a-zа-яё]", "", lc)
        if letters_only and letters_only in _JUNK_NAME_LITERALS:
            return True
        return False

    if _is_junk_name(first):
        return False, "firstName", (
            "Please enter your real first name - placeholder values "
            "like \"test\" or \"123\" are not allowed."
        )
    if _is_junk_name(last):
        return False, "lastName", (
            "Please enter your real last name - placeholder values "
            "like \"test\" or \"123\" are not allowed."
        )

    # Email shape: must contain @ and a dot in the domain. The form
    # already does a basic regex but we re-check to be safe.
    if "@" not in email or "." not in email.split("@", 1)[-1]:
        return False, "email", "Please enter a valid email address."
    local, _, domain = email.partition("@")
    domain = domain.strip(".")

    if domain in _DISPOSABLE_EMAIL_DOMAINS:
        return False, "email", (
            "Please use a real email address - disposable and "
            "throwaway addresses are not allowed for demo access."
        )
    # Sub-domain match (e.g. anything.mailinator.com)
    for bad in _DISPOSABLE_EMAIL_DOMAINS:
        if domain.endswith("." + bad):
            return False, "email", (
                "Please use a real email address - disposable and "
                "throwaway addresses are not allowed for demo access."
            )

    for pat in _JUNK_LOCALPART_PATTERNS:
        if pat.match(local):
            return False, "email", (
                "Please use your real email address - placeholder "
                "addresses like \"test@…\" or \"123@…\" are not allowed."
            )

    # All-numeric domain second-level ("123.com", "1.com")
    domain_parts = domain.split(".")
    if domain_parts and domain_parts[0].isdigit():
        return False, "email", (
            "Please enter a valid email address from a real domain."
        )

    return True, None, None

DATA_FILE = "/root/clawd/demo-registrations.jsonl"
TOKENS_FILE = "/root/clawd/demo-tokens.json"
LICENSE_DATA_FILE = "/root/clawd/license-requests.jsonl"
# Marketing-site form leads - three new endpoints (newsletter / general
# inquiry / partner application) all funnel into one of these JSONL files
# so the existing ops tooling (tail, grep, jq, daily backup cron) keeps
# working without per-form special-cases.
INQUIRY_DATA_FILE = "/root/clawd/contact-requests.jsonl"
SUBSCRIBE_DATA_FILE = "/root/clawd/newsletter-subscribers.jsonl"
PARTNERS_DATA_FILE = "/root/clawd/partner-applications.jsonl"
# Best-effort log of email-delivery failures. A future cron job
# (or any tail -F watcher) can monitor this to alert when SMTP / Resend
# falls over. We keep it separate from the lead JSONL files so the
# operations data stays clean.
EMAIL_FAILURE_LOG = "/root/clawd/email-delivery-failures.jsonl"
BASE_URL = os.environ.get("BASE_URL", "https://adicc-uae.com")


def _log_email_failure(endpoint: str, recipient: str, error: str) -> None:
    """Append one JSON line describing an outbound email delivery failure.

    Swallows its own errors - logging the log failure is not useful and
    we never want this helper to break the request flow.
    """
    try:
        with open(EMAIL_FAILURE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "endpoint": endpoint,
                "recipient": recipient,
                "error": str(error)[:500],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass

TIER_LABELS = {
    "starter": "Starter (on request)",
    "whitelabel": "White-label SaaS (up to 10 tenants)",
    "converters": "DDC cad2data converters",
    "other": "Not sure yet - please advise",
}

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "info@datadrivenconstruction.io")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "OpenConstructionERP <info@datadrivenconstruction.io>")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "info@datadrivenconstruction.io")


def load_tokens():
    try:
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def send_email(to, subject, html_body, text_body=""):
    if RESEND_API_KEY:
        return _send_resend(to, subject, html_body)
    if SMTP_HOST:
        return _send_smtp(to, subject, html_body, text_body)
    print("[WARN] No email provider configured", file=sys.stderr)
    return False


def _send_smtp(to, subject, html_body, text_body=""):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    # Port 465 is implicit TLS (SMTPS), 587/25 are plain + STARTTLS.
    # Mixing them hangs forever - Hostinger uses 465 with SSL on connect.
    if int(SMTP_PORT) == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to], msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to], msg.as_string())
    return True


def _send_resend(to, subject, html_body):
    data = json.dumps({
        "from": RESEND_FROM, "to": [to], "subject": subject, "html": html_body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=data,
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status == 200


def make_license_admin_email(data, ref_id):
    """Internal notification to admin with full lead details."""
    name = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
    tier_key = (data.get("tier") or "").lower()
    tier_label = TIER_LABELS.get(tier_key, tier_key or "-")
    ref = data.get("ref") or "(direct)"
    ref_first = data.get("ref_first_seen") or "-"
    utm = " / ".join(
        [
            data.get("utm_source") or "",
            data.get("utm_medium") or "",
            data.get("utm_campaign") or "",
        ]
    ).strip(" /") or "-"
    landing = data.get("landing_page") or "-"
    msg = (data.get("message") or "").strip() or "-"
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#0f172a;">
<h2 style="margin:0 0 4px;font-size:18px;">New commercial licence request</h2>
<p style="color:#64748b;margin:0 0 16px;font-size:13px;">Reference: <strong>{ref_id}</strong></p>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr><td style="padding:6px 0;color:#64748b;width:140px;">Name</td><td style="padding:6px 0;"><strong>{name}</strong></td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Email</td><td style="padding:6px 0;"><a href="mailto:{data.get('email','')}" style="color:#0066ff;">{data.get('email','')}</a></td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Company</td><td style="padding:6px 0;">{data.get('company','')}</td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Country</td><td style="padding:6px 0;">{data.get('country','')}</td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Tier</td><td style="padding:6px 0;"><strong>{tier_label}</strong></td></tr>
<tr><td style="padding:6px 0;color:#64748b;vertical-align:top;">Notes</td><td style="padding:6px 0;white-space:pre-wrap;">{msg}</td></tr>
<tr><td colspan="2" style="padding:14px 0 6px;color:#64748b;font-size:12px;border-top:1px solid #e2e8f0;">Attribution</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">Referrer</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{ref}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">First seen</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{ref_first}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">UTM</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{utm}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">Landing</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:12px;word-break:break-all;">{landing}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">IP</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{data.get('ip','')}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">Submitted</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{data.get('server_time','')}</td></tr>
</table>
</body></html>'''


def make_license_customer_email(data, ref_id):
    """Acknowledgement to the requester."""
    name = data.get("firstName", "").strip() or "there"
    tier_key = (data.get("tier") or "").lower()
    tier_label = TIER_LABELS.get(tier_key, tier_key or "-")
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#0f172a;">
<div style="text-align:center;margin-bottom:24px;">
<h1 style="font-size:22px;margin:0;">OpenConstructionERP</h1>
<p style="color:#64748b;font-size:14px;margin-top:4px;">Commercial licence request received</p>
</div>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:24px;">
<p style="font-size:15px;">Hi {name},</p>
<p style="font-size:15px;">Thanks for your interest in licensing OpenConstructionERP commercially.</p>
<p style="font-size:15px;">We received your request for <strong>{tier_label}</strong> and will reply within <strong>two business days</strong> with a draft agreement and an invoice in EUR.</p>
<p style="font-size:14px;color:#64748b;margin-top:18px;">Reference ID: <span style="font-family:ui-monospace,monospace;background:#fff;padding:3px 8px;border-radius:6px;border:1px solid #e2e8f0;">{ref_id}</span></p>
<p style="font-size:14px;color:#64748b;margin-top:12px;">If anything is urgent, just reply to this email or write to <a href="mailto:info@datadrivenconstruction.io" style="color:#0066ff;">info@datadrivenconstruction.io</a>.</p>
</div>
<div style="text-align:center;margin-top:24px;font-size:12px;color:#94a3b8;">
<p><a href="https://adicc-uae.com" style="color:#94a3b8;">adicc-uae.com</a> &middot; DataDrivenConstruction.io &middot; Graben-Neudorf, Germany</p>
</div>
</body></html>'''


def _esc(value) -> str:
    """Minimal HTML escape for values rendered into email bodies."""
    if value is None:
        return ""
    s = str(value)
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _make_generic_admin_email(data: dict, ref_id: str, kind: str) -> str:
    """Admin notification used by /inquiry and /partners-apply.

    Renders every field on the submission so triage doesn't require
    opening the JSONL row. Field ordering is stable; unknown fields
    fall through to the bottom in alphabetical order.
    """
    pinned_order = [
        "name", "email", "company", "country", "website",
        "team_size", "target_tier", "audience_type", "interests",
        "brief", "message",
    ]
    seen = set()
    rows: list[str] = []
    for key in pinned_order:
        if key in data and data.get(key) not in (None, ""):
            rows.append(_render_row(key, data[key]))
            seen.add(key)
    for key in sorted(data.keys()):
        if key in seen or key in {
            "server_time", "ip", "reference_id", "kind",
            "user_agent", "_honey",
        }:
            continue
        if data.get(key) in (None, ""):
            continue
        rows.append(_render_row(key, data[key]))

    meta_rows = "".join([
        "<tr><td colspan=\"2\" style=\"padding:14px 0 6px;color:#64748b;"
        "font-size:12px;border-top:1px solid #e2e8f0;\">Attribution &amp; "
        "context</td></tr>",
        _render_row("Submitted", data.get("server_time", "-"), muted=True),
        _render_row("IP", data.get("ip", "-"), muted=True),
        _render_row("User-Agent", data.get("user_agent", "-"), muted=True),
    ])

    kind_label = {
        "inquiry": "general inquiry",
        "partner_application": "partner application",
        "newsletter_subscribe": "newsletter signup",
    }.get(kind, kind)

    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"></head>"
        "<body style=\"font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
        "max-width:680px;margin:0 auto;padding:20px;color:#0f172a;\">"
        f"<h2 style=\"margin:0 0 4px;font-size:18px;\">New {kind_label}</h2>"
        f"<p style=\"color:#64748b;margin:0 0 16px;font-size:13px;\">Reference: "
        f"<strong>{_esc(ref_id)}</strong></p>"
        "<table style=\"width:100%;border-collapse:collapse;font-size:14px;\">"
        f"{''.join(rows)}{meta_rows}"
        "</table></body></html>"
    )


def _render_row(label, value, muted: bool = False) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    label_color = "#64748b" if muted else "#64748b"
    value_style = (
        "padding:6px 0;font-family:ui-monospace,monospace;font-size:13px;"
        if muted else "padding:6px 0;"
    )
    pretty = _esc(value).replace("\n", "<br>")
    return (
        f"<tr><td style=\"padding:6px 0;color:{label_color};width:140px;\">"
        f"{_esc(label).title()}</td>"
        f"<td style=\"{value_style}\">{pretty}</td></tr>"
    )


def _make_generic_customer_email(data: dict, ref_id: str, kind: str) -> str:
    """Customer acknowledgement for /inquiry and /partners-apply."""
    name = (data.get("name") or data.get("firstName") or "there").strip()
    body_intro = {
        "inquiry": (
            "Thanks for reaching out - we read every message personally. "
            "I will reply within a few business days with the next step."
        ),
        "partner_application": (
            "Thanks for applying to the OpenConstructionERP partner program. "
            "We read every application personally; typical response time is "
            "1-3 business days."
        ),
    }.get(kind, "Thanks for your message - we will get back to you shortly.")

    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"></head>"
        "<body style=\"font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
        "max-width:600px;margin:0 auto;padding:20px;color:#0f172a;\">"
        "<div style=\"text-align:center;margin-bottom:24px;\">"
        "<h1 style=\"font-size:22px;margin:0;\">OpenConstructionERP</h1>"
        "<p style=\"color:#64748b;font-size:14px;margin-top:4px;\">"
        "Message received</p></div>"
        "<div style=\"background:#f8fafc;border:1px solid #e2e8f0;"
        "border-radius:12px;padding:24px;\">"
        f"<p style=\"font-size:15px;\">Hi {_esc(name)},</p>"
        f"<p style=\"font-size:15px;\">{_esc(body_intro)}</p>"
        f"<p style=\"font-size:14px;color:#64748b;margin-top:18px;\">"
        "Reference ID: <span style=\"font-family:ui-monospace,monospace;"
        "background:#fff;padding:3px 8px;border-radius:6px;"
        f"border:1px solid #e2e8f0;\">{_esc(ref_id)}</span></p>"
        "<p style=\"font-size:14px;color:#64748b;margin-top:12px;\">"
        "Anything urgent? Just reply to this email or write to "
        "<a href=\"mailto:info@datadrivenconstruction.io\" "
        "style=\"color:#0066ff;\">info@datadrivenconstruction.io</a>.</p>"
        "</div>"
        "<div style=\"text-align:center;margin-top:24px;font-size:12px;"
        "color:#94a3b8;\">"
        "<p><a href=\"https://adicc-uae.com\" "
        "style=\"color:#94a3b8;\">adicc-uae.com</a> &middot; "
        "DataDrivenConstruction.io &middot; Graben-Neudorf, Germany</p>"
        "</div></body></html>"
    )


def make_confirmation_email(data, verify_url):
    name = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="text-align:center;margin-bottom:24px;">
<h1 style="font-size:22px;color:#1a1a1a;margin:0;">OpenConstructionERP</h1>
<p style="color:#666;font-size:14px;margin-top:4px;">Confirm your demo access</p>
</div>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:24px;">
<p style="font-size:15px;color:#333;">Hi {name},</p>
<p style="font-size:15px;color:#333;">Thank you for your interest! Please confirm your email to activate demo access:</p>
<div style="text-align:center;margin:24px 0;">
<a href="{verify_url}" style="display:inline-block;background:#2563eb;color:white;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
Activate Demo Access</a>
</div>
<p style="font-size:13px;color:#888;">Or copy: <a href="{verify_url}" style="color:#2563eb;">{verify_url}</a></p>
</div>
<div style="text-align:center;margin-top:24px;font-size:12px;color:#aaa;">
<p><a href="https://adicc-uae.com" style="color:#888;">adicc-uae.com</a>
&middot; <a href="mailto:info@datadrivenconstruction.io" style="color:#888;">info@datadrivenconstruction.io</a></p>
</div></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/verify":
            params = urllib.parse.parse_qs(parsed.query)
            token = params.get("token", [""])[0]
            if not token:
                self.send_json(400, {"error": "Missing token"})
                return
            tokens = load_tokens()
            entry = tokens.get(token)
            if not entry:
                self.send_response(302)
                self.send_header("Location", f"{BASE_URL}/demo?error=invalid_token")
                self.end_headers()
                return
            entry["verified"] = True
            entry["verified_at"] = datetime.now(timezone.utc).isoformat()
            save_tokens(tokens)
            # Notify admin
            try:
                admin_text = (
                    f"Verified: {entry.get('firstName','')} {entry.get('lastName','')}\n"
                    f"Email: {entry.get('email','')}\n"
                    f"Company: {entry.get('company','')}\n"
                    f"Role: {entry.get('role','-')}\n"
                    f"IP: {entry.get('ip','')}"
                )
                send_email(ADMIN_EMAIL,
                    f"[Demo] Verified: {entry.get('firstName','')} {entry.get('lastName','')} - {entry.get('company','')}",
                    f"<pre>{admin_text}</pre>", admin_text)
            except Exception as e:
                print(f"[WARN] Admin email failed: {e}", file=sys.stderr)
                _log_email_failure("verify:admin", ADMIN_EMAIL, str(e))
            print(f"[VERIFIED] {entry.get('email')}")
            self.send_response(302)
            self.send_header("Location", f"{BASE_URL}/demo?verified=true")
            self.end_headers()
        elif parsed.path == "/health":
            self.send_json(200, {"status": "ok", "email": "smtp" if SMTP_HOST else ("resend" if RESEND_API_KEY else "none")})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/license-request":
            self._handle_license_request()
            return
        # Marketing-site forms (Caddy rewrites /api/* -> these paths)
        if self.path == "/inquiry":
            self._handle_marketing_form(
                bucket="inquiry",
                kind="inquiry",
                data_file=INQUIRY_DATA_FILE,
                required=["name", "email"],
                admin_subject_fn=lambda d, ref: (
                    f"[Inquiry] {(d.get('source') or 'contact')} · "
                    f"{(d.get('company') or '-')} · "
                    f"{d.get('name', '')} <{d.get('email', '')}>"
                ),
                customer_subject="Thanks - we received your message",
            )
            return
        if self.path == "/subscribe":
            self._handle_subscribe()
            return
        if self.path == "/partners-apply":
            self._handle_marketing_form(
                bucket="partners_apply",
                kind="partner_application",
                data_file=PARTNERS_DATA_FILE,
                required=["name", "email", "company", "country", "brief"],
                admin_subject_fn=lambda d, ref: (
                    f"[Partner] {(d.get('target_tier') or '-')} · "
                    f"{(d.get('audience_type') or '-')} · "
                    f"{d.get('company', '')} · {d.get('name', '')}"
                ),
                customer_subject="Thanks - your partner application is in",
            )
            return
        if self.path != "/register":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return
        for field in ["firstName", "lastName", "email", "company"]:
            if not data.get(field, "").strip():
                self.send_json(400, {
                    "error": f"Missing: {field}",
                    "field": field,
                    "message": "Please fill in all required fields.",
                })
                return
        # Anti-spam gate: reject "test / 123 / asdf" placeholder
        # signups before they hit the data file or the verification
        # email pipeline.
        ok, bad_field, bad_message = _validate_real_identity(data)
        if not ok:
            self.send_json(400, {
                "error": "invalid_identity",
                "field": bad_field,
                "message": bad_message,
            })
            print(
                f"[REJECT] {bad_field}: {data.get(bad_field, '')!r} "
                f"from {self.client_address[0]}",
                file=sys.stderr,
            )
            return
        email = data["email"].strip().lower()
        data["server_time"] = datetime.now(timezone.utc).isoformat()
        data["ip"] = self.client_address[0]
        data["verified"] = False
        token = secrets.token_urlsafe(32)
        verify_url = f"{BASE_URL}/demo-api/verify?token={token}"
        # Save
        try:
            with open(DATA_FILE, "a") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ERROR] Save: {e}", file=sys.stderr)
        tokens = load_tokens()
        tokens[token] = {**data, "token": token}
        save_tokens(tokens)
        # Send confirmation
        email_sent = False
        try:
            html = make_confirmation_email(data, verify_url)
            email_sent = send_email(email, "Confirm your OpenConstructionERP demo access", html)
            if not email_sent:
                _log_email_failure("register:confirm", email, "send_email returned False")
        except Exception as e:
            print(f"[ERROR] Email: {e}", file=sys.stderr)
            _log_email_failure("register:confirm", email, str(e))
        if email_sent:
            self.send_json(200, {"status": "confirmation_sent"})
            print(f"[REG] Confirmation -> {email}")
        else:
            # SMTP down / send failed.
            #
            # We INTENTIONALLY do NOT auto-verify the token here.
            #
            # Auto-verifying on SMTP failure (the previous behaviour) leaks
            # leads two ways:
            #   1. The user never receives the confirmation, so they never
            #      come back to log in -> lead is dead in the JSONL.
            #   2. The user sees a generic "ok" with no reference id, so
            #      they can't follow up either.
            #
            # The lead is already persisted in DATA_FILE above, so an
            # operator can reach out manually. The token stays unverified
            # so when SMTP comes back up the lead can still be re-engaged
            # by re-sending the confirmation. Do NOT change this back to
            # auto-verify without first wiring a retry queue.
            ref_id = data.get("ref_id") or token[:12]
            self.send_json(200, {
                "status": "queued_no_email",
                "ref_id": ref_id,
                "message": (
                    "Saved - our email service is temporarily unreachable. "
                    "An operator will reach out within one business day. "
                    "Reference: " + ref_id
                ),
            })
            print(f"[REG] Queued, no email (SMTP fail): {email} ref={ref_id}", file=sys.stderr)

    # ── Shared marketing-form plumbing ──────────────────────────────
    #
    # Three of the marketing endpoints (general inquiry, newsletter
    # subscribe, partner application) share the same lifecycle:
    # 1. Parse JSON body (reject on malformed input)
    # 2. Apply honeypot check - silently 202 on bot fills so they
    #    don't learn the trick worked.
    # 3. Per-IP sliding-window rate limit -> 429 with Retry-After.
    # 4. Required-field validation -> 400 with offending field.
    # 5. Identity / disposable-email check (the same gate used by
    #    /register and /license-request).
    # 6. Append to JSONL (source of truth).
    # 7. Best-effort SMTP send to admin + customer ack; failure
    #    here is logged but doesn't fail the request because we
    #    already persisted the lead.
    # 8. Return 202 with a reference_id the form can quote back.

    def _read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            return json.loads(body)
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return None

    def _honeypot_triggered(self, data: dict) -> bool:
        """Common bot-trap field names. Quietly drop on match.

        Only genuinely hidden fields belong here. Do NOT add "website" or
        "url": the partner application form collects a real, visible website
        field, so trapping that name silently dropped every legitimate
        application that filled it in. The hidden "_honey" input off screen
        stays the actual trap.
        """
        for trap in ("_honey", "honeypot", "bot_field"):
            v = data.get(trap)
            if isinstance(v, str) and v.strip():
                print(
                    f"[HONEYPOT] {trap}={v!r} from {self.client_address[0]}",
                    file=sys.stderr,
                )
                return True
        return False

    def _enforce_rate_limit(self, bucket: str) -> bool:
        ok, retry = _rate_limit_check(self.client_address[0], bucket)
        if ok:
            return True
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.send_header("Retry-After", str(retry))
        self.send_header("Access-Control-Allow-Origin", "*")
        body = json.dumps({
            "error": "rate_limited",
            "message": (
                "Too many requests from your address. Please try again "
                f"in {max(60, retry) // 60} minute(s) or email "
                "info@datadrivenconstruction.io directly."
            ),
            "retry_after": retry,
        }).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(
            f"[RATE] {bucket} blocked {self.client_address[0]} retry={retry}s",
            file=sys.stderr,
        )
        return False

    def _handle_marketing_form(
        self,
        *,
        bucket: str,
        kind: str,
        data_file: str,
        required: list[str],
        admin_subject_fn,
        customer_subject: str,
    ) -> None:
        # Honeypot must run BEFORE rate limit so we don't penalise the
        # IP-level cap with bot traffic.
        data = self._read_json_body()
        if data is None:
            return
        if self._honeypot_triggered(data):
            # 202 keeps bots in the dark. We don't persist or email.
            ref_id = "OCERP-DROP-" + secrets.token_hex(3).upper()
            self.send_json(202, {"status": "received", "reference_id": ref_id})
            return
        if not self._enforce_rate_limit(bucket):
            return

        # Normalise common identity fields so the existing junk-name /
        # disposable-email gate (designed around firstName/lastName)
        # also catches "name" / "email" submissions from the contact
        # and partner forms.
        full = (data.get("name") or "").strip()
        if full and not data.get("firstName") and not data.get("lastName"):
            parts = full.split(None, 1)
            data["firstName"] = parts[0]
            data["lastName"] = parts[1] if len(parts) > 1 else parts[0]

        for field in required:
            if not (str(data.get(field) or "")).strip():
                self.send_json(400, {
                    "error": f"Missing: {field}",
                    "field": field,
                    "message": "Please fill in all required fields.",
                })
                return

        # Identity gate (reuses the demo-registration gate when we have
        # first/last name shaped data - skip if the form is name-only).
        if data.get("firstName") and data.get("lastName") and data.get("email"):
            ok, bad_field, bad_message = _validate_real_identity(data)
            if not ok:
                self.send_json(400, {
                    "error": "invalid_identity",
                    "field": bad_field,
                    "message": bad_message,
                })
                print(
                    f"[{bucket.upper()}-REJECT] {bad_field}: "
                    f"{data.get(bad_field, '')!r} from {self.client_address[0]}",
                    file=sys.stderr,
                )
                return

        # Reference ID shape matches /license-request so the existing
        # ops scripts and partner dashboard don't need a special case.
        ref_id = (
            "OCERP-"
            + datetime.now(timezone.utc).strftime("%Y%m%d")
            + "-"
            + secrets.token_hex(3).upper()
        )

        if "email" in data and isinstance(data.get("email"), str):
            data["email"] = data["email"].strip().lower()
        data["server_time"] = datetime.now(timezone.utc).isoformat()
        data["ip"] = self.client_address[0]
        data["reference_id"] = ref_id
        data["kind"] = kind
        data["user_agent"] = self.headers.get("User-Agent", "")

        # JSONL append - source of truth even when SMTP is down.
        try:
            with open(data_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ERROR] Save {kind}: {e}", file=sys.stderr)

        # Admin notification - full lead. Best-effort; we already saved
        # the row so the failure mode is "I won't get pinged" rather
        # than "the lead vanishes".
        try:
            admin_html = _make_generic_admin_email(data, ref_id, kind)
            send_email(ADMIN_EMAIL, admin_subject_fn(data, ref_id), admin_html)
        except Exception as e:
            print(f"[WARN] Admin {kind} email failed: {e}", file=sys.stderr)
            _log_email_failure(f"{kind}:admin", ADMIN_EMAIL, str(e))

        # Customer ack - only if we have an email and the form is not
        # just a newsletter subscribe (subscribe sends its own confirm).
        try:
            if data.get("email"):
                customer_html = _make_generic_customer_email(
                    data, ref_id, kind
                )
                send_email(data["email"], customer_subject, customer_html)
        except Exception as e:
            print(f"[WARN] Customer {kind} email failed: {e}", file=sys.stderr)
            _log_email_failure(f"{kind}:customer", data.get("email", ""), str(e))

        print(
            f"[{bucket.upper()}] {ref_id} from {self.client_address[0]} "
            f"company={data.get('company') or '-'!r}"
        )
        self.send_json(202, {"status": "received", "reference_id": ref_id})

    def _handle_subscribe(self) -> None:
        """Newsletter signup. Lightweight: email + optional source/lang."""
        data = self._read_json_body()
        if data is None:
            return
        if self._honeypot_triggered(data):
            self.send_json(202, {"status": "subscribed"})
            return
        if not self._enforce_rate_limit("subscribe"):
            return
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email or "." not in email.split("@", 1)[-1]:
            self.send_json(400, {
                "error": "invalid_email",
                "field": "email",
                "message": "Please enter a valid email address.",
            })
            return
        # Block disposable domains - same list as demo registration.
        local, _, domain = email.partition("@")
        domain = domain.strip(".")
        if domain in _DISPOSABLE_EMAIL_DOMAINS or any(
            domain.endswith("." + bad) for bad in _DISPOSABLE_EMAIL_DOMAINS
        ):
            self.send_json(400, {
                "error": "invalid_email",
                "field": "email",
                "message": "Please use a real email address.",
            })
            return
        for pat in _JUNK_LOCALPART_PATTERNS:
            if pat.match(local):
                self.send_json(400, {
                    "error": "invalid_email",
                    "field": "email",
                    "message": "Please use a real email address.",
                })
                return

        record = {
            "email": email,
            "source": (data.get("source") or "newsletter").strip()[:64],
            "lang": (data.get("lang") or "").strip()[:8],
            "server_time": datetime.now(timezone.utc).isoformat(),
            "ip": self.client_address[0],
            "user_agent": self.headers.get("User-Agent", ""),
            "kind": "newsletter_subscribe",
        }
        try:
            with open(SUBSCRIBE_DATA_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ERROR] Save subscribe: {e}", file=sys.stderr)

        # Admin ping - informational, low-volume.
        try:
            admin_text = (
                f"New newsletter subscriber:\n  Email: {email}\n"
                f"  Source: {record['source']}\n  Lang: {record['lang']}\n"
                f"  IP: {record['ip']}\n  Time: {record['server_time']}"
            )
            send_email(
                ADMIN_EMAIL,
                f"[Newsletter] +1 subscriber ({email})",
                f"<pre style=\"font-family:ui-monospace,monospace\">{admin_text}</pre>",
                admin_text,
            )
        except Exception as e:
            print(f"[WARN] Subscribe admin email failed: {e}", file=sys.stderr)
            _log_email_failure("subscribe:admin", ADMIN_EMAIL, str(e))

        # Customer confirmation.
        try:
            html = (
                "<!DOCTYPE html><html><body style=\"font-family:-apple-system,"
                "BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;"
                "padding:24px;color:#0f172a;\">"
                "<h2 style=\"font-size:20px;margin:0 0 8px;\">"
                "You are subscribed</h2>"
                "<p style=\"font-size:14.5px;line-height:1.6;color:#334155;\">"
                "Thanks for subscribing to OpenConstructionERP product updates. "
                "We send a short digest when we ship a new release - usually "
                "monthly, never more than weekly.</p>"
                "<p style=\"font-size:13px;color:#64748b;margin-top:18px;\">"
                "If this wasn't you, just ignore this email - we will not add "
                "you again.</p>"
                "<p style=\"font-size:12px;color:#94a3b8;margin-top:22px;\">"
                "<a href=\"https://adicc-uae.com\" "
                "style=\"color:#94a3b8;\">adicc-uae.com</a> &middot; "
                "DataDrivenConstruction.io</p></body></html>"
            )
            send_email(email, "Welcome to OpenConstructionERP updates", html)
        except Exception as e:
            print(f"[WARN] Subscribe ack email failed: {e}", file=sys.stderr)
            _log_email_failure("subscribe:customer", email, str(e))

        print(f"[SUB] {email} source={record['source']}")
        self.send_json(202, {"status": "subscribed"})

    def _handle_license_request(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return

        # Required fields (mirrors the form). Country and tier are
        # licence-specific compared with the demo registration flow.
        required = ["firstName", "lastName", "email", "company", "country", "tier"]
        for field in required:
            if not (data.get(field) or "").strip():
                self.send_json(400, {
                    "error": f"Missing: {field}",
                    "field": field,
                    "message": "Please fill in all required fields.",
                })
                return

        if data["tier"] not in TIER_LABELS:
            self.send_json(400, {
                "error": "invalid_tier",
                "field": "tier",
                "message": "Please select a valid licence tier.",
            })
            return

        # Same anti-spam gate as demo signups - junk names and
        # disposable email domains are blocked before we persist
        # anything or fire emails.
        ok, bad_field, bad_message = _validate_real_identity(data)
        if not ok:
            self.send_json(400, {
                "error": "invalid_identity",
                "field": bad_field,
                "message": bad_message,
            })
            print(
                f"[LIC-REJECT] {bad_field}: {data.get(bad_field, '')!r} "
                f"from {self.client_address[0]}",
                file=sys.stderr,
            )
            return

        # Reference ID - short, monotonic-ish, easy to quote on the
        # phone. Same shape Kristijan/partners will see in their
        # affiliate dashboard later.
        ref_id = "OCERP-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()

        data["email"] = data["email"].strip().lower()
        data["server_time"] = datetime.now(timezone.utc).isoformat()
        data["ip"] = self.client_address[0]
        data["reference_id"] = ref_id
        data["kind"] = "license_request"

        # Persist before sending mail - if SMTP/Resend fails we
        # still have the lead. JSONL append, one row per request.
        try:
            with open(LICENSE_DATA_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ERROR] Save license request: {e}", file=sys.stderr)

        # Admin notification - full lead + attribution. We deliberately
        # don't fail the request when email delivery fails; the JSONL
        # is the source of truth and the form already returned success.
        try:
            admin_html = make_license_admin_email(data, ref_id)
            admin_subject = (
                f"[Licence] {data.get('tier','?')} · "
                f"{data.get('company','')} · "
                f"{data.get('firstName','')} {data.get('lastName','')}"
            )
            send_email(ADMIN_EMAIL, admin_subject, admin_html)
        except Exception as e:
            print(f"[WARN] Admin license email failed: {e}", file=sys.stderr)
            _log_email_failure("license:admin", ADMIN_EMAIL, str(e))

        # Customer acknowledgement. Best-effort: any failure here is
        # logged but doesn't affect the user-facing success state.
        try:
            customer_html = make_license_customer_email(data, ref_id)
            send_email(
                data["email"],
                "Your OpenConstructionERP commercial licence request",
                customer_html,
            )
        except Exception as e:
            print(f"[WARN] Customer license email failed: {e}", file=sys.stderr)
            _log_email_failure("license:customer", data.get("email", ""), str(e))

        print(
            f"[LIC] {ref_id} tier={data.get('tier')} "
            f"company={data.get('company')!r} ref={data.get('ref') or '-'}"
        )
        self.send_json(200, {"status": "received", "reference_id": ref_id})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    # Janitor for the per-IP rate-limit map - keeps memory bounded
    # under sustained traffic. Daemon thread dies with the process.
    threading.Thread(
        target=_rate_state_janitor, name="rate-janitor", daemon=True
    ).start()
    print(f"Marketing-site form API v3 on port {PORT}")
    print(f"  Email: {'SMTP' if SMTP_HOST else ('Resend' if RESEND_API_KEY else 'NONE (auto-verify)')}")
    print(f"  Admin: {ADMIN_EMAIL}")
    print(
        "  Endpoints: /register, /verify, /license-request, "
        "/inquiry, /subscribe, /partners-apply, /health"
    )
    server.serve_forever()
