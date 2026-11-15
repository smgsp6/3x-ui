#!/usr/bin/env python3
"""CI-only Telegram Mini App end-to-end HTTP auth contract via real local TLS.

Executed INSIDE an isolated Vela Docker container. Only synthetic signed
initData and dummy Bot Token; it never calls Telegram or exposes credentials.
A successful result does NOT claim Telegram WebView/device validation.
"""
import base64
import hashlib
import hmac
import http.cookiejar
import json
from pathlib import Path
import ssl
import time
from urllib import error, parse, request

BASE = "https://127.0.0.1:2053"
TRUST = "/etc/x-ui/vela-ci-cert.pem"
BOT_TOKEN_FILE = "/run/secrets/vela_bot_token"
ADMIN_ID = 1001

context = ssl.create_default_context(cafile=TRUST)
jar = http.cookiejar.CookieJar()
opener = request.build_opener(request.HTTPSHandler(context=context),
                              request.HTTPCookieProcessor(jar))

def http(path, method="GET", payload=None, csrf=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"X-Requested-With": "XMLHttpRequest"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    req = request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        response = opener.open(req, timeout=6)
    except error.HTTPError as exc:
        response = exc
    with response as r:
        status = r.status
        # Do not print response bodies; admin details may be present.
        body = r.read(512 * 1024)
        cookie = r.headers.get_all("Set-Cookie", [])
    return status, body, cookie

def require(value, message):
    if not value:
        raise AssertionError(message)

def signed_init_data(token, telegram_id, issued_at):
    fields = {
        "auth_date": str(issued_at),
        "query_id": "CI_SYNTHETIC_ONLY",
        "user": json.dumps({"id": telegram_id, "first_name": "Synthetic"},
                           separators=(",", ":")),
    }
    canonical = "\n".join(k + "=" + fields[k] for k in sorted(fields))
    k = hmac.new(b"WebAppData", token.encode("ascii"),
                 hashlib.sha256).digest()
    digest = hmac.new(k, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return parse.urlencode({**fields, "hash": digest})

def csrf_token():
    status, body, _ = http("/csrf-token")
    require(status == 200, "public CSRF bootstrap is not available")
    parsed = json.loads(body)
    token = parsed.get("obj")
    require(parsed.get("success") is True and isinstance(token, str) and len(token) >= 24,
            "CSRF bootstrap returned invalid token")
    return token

def login(payload, csrf=None):
    return http("/tg-miniapp/auth", method="POST",
                payload={"initData": payload}, csrf=csrf)

def main():
    token = Path(BOT_TOKEN_FILE).read_text().strip()
    require(len(token) > 30 and " " not in token, "CI-only secret is missing")
    now = int(time.time())
    good = signed_init_data(token, ADMIN_ID, now)

    for i in range(40):
        try:
            status, _, _ = http("/tg-miniapp/health")
            if status == 204:
                break
        except (OSError, ssl.SSLError):
            pass
        time.sleep(1)
    else:
        raise AssertionError("real HTTPS Mini App health did not become ready")
    print("01/08 isolated HTTPS health 204 and local TLS certificate verified")

    status, _, _ = http("/panel/api/openapi.json")
    require(status == 401, "unauthenticated panel API must reject requests")
    print("02/08 anonymous admin API rejected")

    original_csrf = csrf_token()
    require(any(c.secure for c in jar), "Mini App cookie must have Secure flag")
    require(any(c.has_nonstandard_attr("HttpOnly") for c in jar),
            "Mini App session cookie must be HttpOnly")
    status, _, _ = login(good)
    require(status == 403, "missing CSRF token must block signed Mini App auth")
    print("03/08 secure browser cookie and login CSRF enforced")

    tampered = good.replace("Synthetic", "Impersonator", 1)
    status, _, _ = login(tampered, original_csrf)
    require(status == 401, "changed Telegram initData must fail HMAC")
    print("04/08 altered Telegram signature rejected")

    other = signed_init_data(token, 1002, now)
    status, _, _ = login(other, original_csrf)
    require(status == 401, "unauthorized Telegram identity accepted")
    stale = signed_init_data(token, ADMIN_ID, now - 900)
    status, _, _ = login(stale, original_csrf)
    require(status == 401, "replayed expired Telegram initData accepted")
    print("05/08 unauthorized ID and expired signature rejected")

    status, body, _ = login(good, original_csrf)
    require(status == 200 and json.loads(body).get("success") is True,
            "signed allowlisted Telegram admin failed to login")
    status, _, _ = http("/panel/api/openapi.json")
    require(status == 200, "authenticated Mini App admin cannot access API")
    print("06/08 signed admin logged in and accessed real guarded panel API")

    refreshed_csrf = csrf_token()
    require(refreshed_csrf != original_csrf, "privilege change retained old CSRF")
    status, _, _ = login(good, original_csrf)
    require(status == 403, "pre-auth CSRF token was accepted after login")
    status, body, _ = login(good, refreshed_csrf)
    require(status == 200 and json.loads(body).get("success") is True,
            "fresh CSRF after login did not work")
    print("07/08 CSRF rotates on session privilege change")

    status, _, _ = http("/panel/api/openapi.json")
    require(status == 200, "post-login API access unexpectedly lost")
    print("08/08 HTTPS session remained functional; synthetic smoke PASS")

if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, ValueError, OSError, ssl.SSLError,
            json.JSONDecodeError, TimeoutError):
        # Never leak HTTP bodies, raw initData, cookies, keys or user details.
        print("FAIL: isolated Mini App HTTPS session or signature contract")
        raise SystemExit(1)
