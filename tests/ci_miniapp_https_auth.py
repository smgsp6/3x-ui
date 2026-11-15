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
    print("01/24 isolated HTTPS health 204 and local TLS certificate verified")

    status, _, _ = http("/panel/api/openapi.json")
    require(status == 401, "unauthenticated panel API must reject requests")
    print("02/24 anonymous admin API rejected")

    original_csrf = csrf_token()
    require(any(c.secure for c in jar), "Mini App cookie must have Secure flag")
    require(any(c.has_nonstandard_attr("HttpOnly") for c in jar),
            "Mini App session cookie must be HttpOnly")
    status, _, _ = login(good)
    require(status == 403, "missing CSRF token must block signed Mini App auth")
    print("03/24 secure browser cookie and login CSRF enforced")

    tampered = good.replace("Synthetic", "Impersonator", 1)
    status, _, _ = login(tampered, original_csrf)
    require(status == 401, "changed Telegram initData must fail HMAC")
    print("04/24 altered Telegram signature rejected")

    other = signed_init_data(token, 1002, now)
    status, _, _ = login(other, original_csrf)
    require(status == 401, "unauthorized Telegram identity accepted")
    stale = signed_init_data(token, ADMIN_ID, now - 900)
    status, _, _ = login(stale, original_csrf)
    require(status == 401, "replayed expired Telegram initData accepted")
    print("05/24 unauthorized ID and expired signature rejected")

    status, body, _ = login(good, original_csrf)
    require(status == 200 and json.loads(body).get("success") is True,
            "signed allowlisted Telegram admin failed to login")
    status, _, _ = http("/panel/api/openapi.json")
    require(status == 200, "authenticated Mini App admin cannot access API")
    print("06/24 signed admin logged in and accessed real guarded panel API")

    refreshed_csrf = csrf_token()
    require(refreshed_csrf != original_csrf, "privilege change retained old CSRF")
    status, _, _ = login(good, original_csrf)
    require(status == 403, "pre-auth CSRF token was accepted after login")
    status, body, _ = login(good, refreshed_csrf)
    require(status == 200 and json.loads(body).get("success") is True,
            "fresh CSRF after login did not work")
    print("07/24 CSRF rotates on session privilege change")

    status, _, _ = http("/panel/api/openapi.json")
    require(status == 200, "post-login API access unexpectedly lost")
    print("08/24 HTTPS session remained functional")

    # Real management routes, synthetic data, disposable Docker only. The
    # inbound is disabled throughout to avoid opening a real proxy listener.
    def api_obj(path, method="GET", payload=None, csrf=None):
        code, data, _ = http(path, method=method, payload=payload, csrf=csrf)
        require(code == 200, "guarded management API returned unexpected status")
        parsed = json.loads(data)
        require(parsed.get("success") is True, "management API returned an error")
        return parsed.get("obj")

    for route in ("/panel/api/server/status", "/panel/api/inbounds/list",
                  "/panel/api/clients/list", "/panel/api/certificates/status"):
        api_obj(route)
    print("09/24 signed session reached real server, inbound, client and certificate APIs")

    fixture = {
        "remark": "CI disposable disabled HTTP inbound",
        "enable": False, "listen": "127.0.0.1", "port": 28341,
        "protocol": "http", "settings": {"accounts": []},
        "streamSettings": {"network": "tcp", "security": "none"},
        "sniffing": {"enabled": False}, "tag": "ci-vela-disabled-http",
        "trafficReset": "never",
    }
    status, _, _ = http("/panel/api/inbounds/add", method="POST", payload=fixture)
    require(status == 403, "Xray mutation without CSRF should be refused")
    print("10/24 signed admin cannot mutate an Xray inbound without CSRF")

    crud_csrf = csrf_token()
    created = api_obj("/panel/api/inbounds/add", "POST", fixture, crud_csrf)
    require(isinstance(created, dict) and isinstance(created.get("id"), int)
            and created["id"] > 0 and created.get("enable") is False,
            "disabled synthetic inbound was not persisted")
    inbound_id = created["id"]
    listed = api_obj("/panel/api/inbounds/list")
    require(isinstance(listed, list) and
            any(row.get("id") == inbound_id and row.get("enable") is False for row in listed),
            "new disabled inbound was missing from list API")
    print("11/24 signed admin created and listed a disabled synthetic Xray inbound")

    detail = api_obj(f"/panel/api/inbounds/get/{inbound_id}")
    require(isinstance(detail, dict) and detail.get("id") == inbound_id,
            "real inbound detail route failed")
    edited = {**fixture, "remark": "CI disposable updated inbound",
              "tag": detail.get("tag", fixture["tag"])}
    updated = api_obj(f"/panel/api/inbounds/update/{inbound_id}", "POST", edited, crud_csrf)
    require(isinstance(updated, dict) and updated.get("remark") == edited["remark"]
            and updated.get("enable") is False, "inbound update unexpectedly enabled listener")
    persisted = api_obj(f"/panel/api/inbounds/get/{inbound_id}")
    require(persisted.get("remark") == edited["remark"] and
            persisted.get("enable") is False, "updated disabled inbound not persisted")
    print("12/24 signed admin read and updated disabled synthetic inbound")

    deleted = api_obj(f"/panel/api/inbounds/del/{inbound_id}", "POST", {}, crud_csrf)
    require(deleted == inbound_id, "real inbound deletion returned incorrect ID")
    listed = api_obj("/panel/api/inbounds/list")
    require(not any(row.get("id") == inbound_id for row in (listed or [])),
            "deleted synthetic inbound remained in database")
    print("13/24 signed admin deleted the synthetic inbound and verified removal")

    # A second disabled inbound exercises the VLESS client lifecycle and the
    # original client API without opening TCP or UDP proxy traffic.
    vless = {
        "remark": "CI synthetic disabled VLESS inbound",
        "enable": False, "listen": "127.0.0.1", "port": 28342,
        "protocol": "vless", "settings": {"clients": [], "decryption": "none"},
        "streamSettings": {"network": "tcp", "security": "none"},
        "sniffing": {"enabled": False}, "tag": "ci-vela-disabled-vless",
        "trafficReset": "never",
    }
    vless_row = api_obj("/panel/api/inbounds/add", "POST", vless, crud_csrf)
    require(isinstance(vless_row, dict) and
            isinstance(vless_row.get("id"), int) and
            vless_row.get("enable") is False,
            "VLESS fixture must stay disabled")
    vless_id = vless_row["id"]
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        require(probe.connect_ex(("127.0.0.1", 28342)) != 0,
                "disabled VLESS inbound opened a proxy TCP listener")
    print("14/24 disabled synthetic VLESS inbound did not open a TCP listener")

    email = "vela-ci-client@synthetic.invalid"
    api_obj("/panel/api/clients/add", "POST",
            {"client": {"email": email, "enable": False,
                        "comment": "synthetic fixture"},
             "inboundIds": [vless_id]}, crud_csrf)
    encoded_email = parse.quote(email, safe="")
    client_detail = api_obj("/panel/api/clients/get?email=" + encoded_email)
    require(isinstance(client_detail, dict) and
            client_detail.get("client", {}).get("email") == email and
            vless_id in client_detail.get("inboundIds", []),
            "created client is not attached to disabled VLESS inbound")
    clients = api_obj("/panel/api/clients/list")
    require(isinstance(clients, list) and
            any(row.get("email") == email for row in clients),
            "synthetic VLESS client missing from clients list")
    client_uuid = client_detail["client"].get("uuid")
    require(isinstance(client_uuid, str) and len(client_uuid) >= 32,
            "VLESS client did not receive a valid synthetic identifier")
    print("15/24 signed admin created and listed a disabled synthetic VLESS client")

    api_obj("/panel/api/clients/update/" + encoded_email, "POST",
            {"comment": "updated synthetic fixture"}, crud_csrf)
    client_detail = api_obj("/panel/api/clients/get?email=" + encoded_email)
    require(client_detail.get("client", {}).get("comment") == "updated synthetic fixture"
            and client_detail.get("client", {}).get("uuid") == client_uuid,
            "partial client update failed or rotated credentials unexpectedly")
    print("16/24 partial VLESS client update preserved its generated identifier")

    # Exercise the original traffic API with a disabled synthetic VLESS client.
    # No Xray network traffic is generated: these are isolated SQLite counters.
    traffic = api_obj("/panel/api/clients/traffic/" + encoded_email)
    require(isinstance(traffic, dict) and traffic.get("email") == email
            and traffic.get("up") == 0 and traffic.get("down") == 0,
            "new disabled VLESS client did not have zeroed traffic counters")
    print("17/24 read zeroed traffic counters for the synthetic VLESS client")

    status, _, _ = http("/panel/api/clients/updateTraffic/" + encoded_email,
                        method="POST", payload={"upload": 4096, "download": 8192})
    require(status == 403, "traffic mutation without CSRF must fail")
    api_obj("/panel/api/clients/updateTraffic/" + encoded_email, "POST",
            {"upload": 4096, "download": 8192}, crud_csrf)
    traffic = api_obj("/panel/api/clients/traffic/" + encoded_email)
    require(traffic.get("up") == 4096 and traffic.get("down") == 8192,
            "traffic counter updates were not persisted")
    print("18/24 CSRF protected traffic update persisted exact synthetic byte totals")

    # Read both upstream link-generation routes. A disabled inbound may
    # intentionally produce no connectable links; neither response body nor
    # synthetic subscription identifier is ever logged to Actions output.
    sub_id = client_detail["client"].get("subId")
    require(isinstance(sub_id, str) and len(sub_id) > 0,
            "synthetic client missing subscription identifier")
    api_obj("/panel/api/clients/subLinks/" + parse.quote(sub_id, safe=""))
    api_obj("/panel/api/clients/links/" + encoded_email)
    print("19/24 signed session accessed original subscription and client link APIs")

    api_obj("/panel/api/clients/resetTraffic/" + encoded_email, "POST",
            {}, crud_csrf)
    traffic = api_obj("/panel/api/clients/traffic/" + encoded_email)
    require(traffic.get("up") == 0 and traffic.get("down") == 0,
            "traffic reset failed to clear synthetic client counters")
    post_reset = api_obj("/panel/api/clients/get?email=" + encoded_email)
    require(post_reset.get("client", {}).get("enable") is False,
            "reset unexpectedly enabled the synthetic client")
    print("20/24 traffic reset cleared counters without enabling the synthetic client")

    api_obj("/panel/api/clients/del/" + encoded_email, "POST", {}, crud_csrf)
    clients = api_obj("/panel/api/clients/list")
    require(not any(row.get("email") == email for row in (clients or [])),
            "deleted synthetic client still appears in client list")
    api_obj(f"/panel/api/inbounds/del/{vless_id}", "POST", {}, crud_csrf)
    listed = api_obj("/panel/api/inbounds/list")
    require(not any(row.get("id") == vless_id for row in (listed or [])),
            "synthetic VLESS inbound remained after cleanup")
    print("21/24 signed admin deleted synthetic client and VLESS inbound")

    # In Mini App mode the original password login route must never be an
    # alternative to the Telegram-signed, allowlisted identity.
    current_csrf = csrf_token()
    require(current_csrf != refreshed_csrf, "second privileged login did not rotate CSRF")
    status, _, _ = http("/login", method="POST", payload={}, csrf=current_csrf)
    require(status == 404, "legacy password login was not disabled in Mini App mode")
    print("22/24 legacy password login endpoint was disabled")

    # The signed admin session must cease to authorize API calls immediately
    # after logout, rather than lingering in a browser cookie.
    logout_csrf = csrf_token()
    # Capture a fully authenticated signed cookie BEFORE logout. Sending it
    # again after deletion must fail, even without a browser cookie jar.
    privileged_cookie = next((c for c in jar if c.name == "3x-ui"), None)
    require(privileged_cookie is not None, "admin session cookie is unavailable")
    copied_cookie_header = privileged_cookie.name + "=" + privileged_cookie.value
    status, body, _ = http("/logout", method="POST", payload={}, csrf=logout_csrf)
    require(status == 200 and json.loads(body).get("success") is True,
            "Mini App logout did not complete")
    status, _, _ = http("/panel/api/openapi.json")
    require(status == 401, "logout did not revoke admin API permissions")
    for route in ("/panel/api/inbounds/list", "/panel/api/clients/list",
                  "/panel/api/server/status", "/panel/api/certificates/status"):
        status, _, _ = http(route)
        require(status == 401, "logout left a sensitive management API accessible")
    print("23/24 logout removed session and protected all management APIs")

    replay_request = request.Request(
        BASE + "/panel/api/inbounds/list",
        headers={"X-Requested-With": "XMLHttpRequest",
                 "Cookie": copied_cookie_header},
    )
    try:
        replay_response = request.urlopen(replay_request, context=context, timeout=6)
    except error.HTTPError as exc:
        replay_response = exc
    with replay_response as r:
        replay_status = r.status
        r.read(512)
    require(replay_status == 401,
            "copied pre-logout signed Mini App cookie retained admin access")
    print("24/24 replay of a copied signed cookie after logout rejected; HTTPS smoke PASS")

if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, ValueError, OSError, ssl.SSLError,
            json.JSONDecodeError, TimeoutError):
        # Never leak HTTP bodies, raw initData, cookies, keys or user details.
        print("FAIL: isolated Mini App HTTPS session or signature contract")
        raise SystemExit(1)
