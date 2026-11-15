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
    print("01/26 isolated HTTPS health 204 and local TLS certificate verified")

    status, _, _ = http("/panel/api/openapi.json")
    require(status == 401, "unauthenticated panel API must reject requests")
    print("02/26 anonymous admin API rejected")

    original_csrf = csrf_token()
    require(any(c.secure for c in jar), "Mini App cookie must have Secure flag")
    require(any(c.has_nonstandard_attr("HttpOnly") for c in jar),
            "Mini App session cookie must be HttpOnly")
    status, _, _ = login(good)
    require(status == 403, "missing CSRF token must block signed Mini App auth")
    print("03/26 secure browser cookie and login CSRF enforced")

    tampered = good.replace("Synthetic", "Impersonator", 1)
    status, _, _ = login(tampered, original_csrf)
    require(status == 401, "changed Telegram initData must fail HMAC")
    print("04/26 altered Telegram signature rejected")

    other = signed_init_data(token, 1002, now)
    status, _, _ = login(other, original_csrf)
    require(status == 401, "unauthorized Telegram identity accepted")
    stale = signed_init_data(token, ADMIN_ID, now - 900)
    status, _, _ = login(stale, original_csrf)
    require(status == 401, "replayed expired Telegram initData accepted")
    print("05/26 unauthorized ID and expired signature rejected")

    status, body, _ = login(good, original_csrf)
    require(status == 200 and json.loads(body).get("success") is True,
            "signed allowlisted Telegram admin failed to login")
    status, _, _ = http("/panel/api/openapi.json")
    require(status == 200, "authenticated Mini App admin cannot access API")
    # The bootstrap and authenticated SPA are distinct documents.
    # Verify the official SDK and Mini App mode survive the navigation.
    panel_request = request.Request(BASE + "/panel/", headers={
        "X-Requested-With": "XMLHttpRequest",
    })
    with opener.open(panel_request, timeout=6) as panel_response:
        status = panel_response.status
        panel_html = panel_response.read(512 * 1024)
        csp = panel_response.headers.get("Content-Security-Policy", "")
    require(status == 200 and
            b"window.X_UI_TG_MINIAPP_MODE=true" in panel_html and
            panel_html.count(b'src="https://telegram.org/js/telegram-web-app.js"') == 1,
            "signed Telegram panel missing the official SDK or Mini App mode")
    # Relax script-src for the official bridge ONLY. Never permit Telegram
    # in connect-src, default-src, framing, or as a broad arbitrary origin.
    policies = {}
    for directive in csp.split(";"):
        parts = directive.strip().split()
        if parts:
            policies[parts[0]] = parts[1:]
    require("https://telegram.org" in policies.get("script-src", []) and
            policies.get("default-src") == ["'self'"] and
            "https://telegram.org" not in policies.get("connect-src", []) and
            policies.get("frame-ancestors") == ["'none'"],
            "Telegram official SDK exception unexpectedly weakened panel CSP")
    print("06/26 signed admin panel SDK and script-only CSP exception verified")

    refreshed_csrf = csrf_token()
    require(refreshed_csrf != original_csrf, "privilege change retained old CSRF")
    status, _, _ = login(good, original_csrf)
    require(status == 403, "pre-auth CSRF token was accepted after login")
    status, body, _ = login(good, refreshed_csrf)
    require(status == 200 and json.loads(body).get("success") is True,
            "fresh CSRF after login did not work")
    print("07/26 CSRF rotates on session privilege change")

    status, _, _ = http("/panel/api/openapi.json")
    require(status == 200, "post-login API access unexpectedly lost")
    print("08/26 HTTPS session remained functional")

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
    print("09/26 signed session reached real server, inbound, client and certificate APIs")

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
    print("10/26 signed admin cannot mutate an Xray inbound without CSRF")

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
    print("11/26 signed admin created and listed a disabled synthetic Xray inbound")

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
    print("12/26 signed admin read and updated disabled synthetic inbound")

    deleted = api_obj(f"/panel/api/inbounds/del/{inbound_id}", "POST", {}, crud_csrf)
    require(deleted == inbound_id, "real inbound deletion returned incorrect ID")
    listed = api_obj("/panel/api/inbounds/list")
    require(not any(row.get("id") == inbound_id for row in (listed or [])),
            "deleted synthetic inbound remained in database")
    print("13/26 signed admin deleted the synthetic inbound and verified removal")

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
    print("14/26 disabled synthetic VLESS inbound did not open a TCP listener")

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
    print("15/26 signed admin created and listed a disabled synthetic VLESS client")

    api_obj("/panel/api/clients/update/" + encoded_email, "POST",
            {"comment": "updated synthetic fixture"}, crud_csrf)
    client_detail = api_obj("/panel/api/clients/get?email=" + encoded_email)
    require(client_detail.get("client", {}).get("comment") == "updated synthetic fixture"
            and client_detail.get("client", {}).get("uuid") == client_uuid,
            "partial client update failed or rotated credentials unexpectedly")
    print("16/26 partial VLESS client update preserved its generated identifier")

    # Exercise the original traffic API with a disabled synthetic VLESS client.
    # No Xray network traffic is generated: these are isolated SQLite counters.
    traffic = api_obj("/panel/api/clients/traffic/" + encoded_email)
    require(isinstance(traffic, dict) and traffic.get("email") == email
            and traffic.get("up") == 0 and traffic.get("down") == 0,
            "new disabled VLESS client did not have zeroed traffic counters")
    print("17/26 read zeroed traffic counters for the synthetic VLESS client")

    status, _, _ = http("/panel/api/clients/updateTraffic/" + encoded_email,
                        method="POST", payload={"upload": 4096, "download": 8192})
    require(status == 403, "traffic mutation without CSRF must fail")
    api_obj("/panel/api/clients/updateTraffic/" + encoded_email, "POST",
            {"upload": 4096, "download": 8192}, crud_csrf)
    traffic = api_obj("/panel/api/clients/traffic/" + encoded_email)
    require(traffic.get("up") == 4096 and traffic.get("down") == 8192,
            "traffic counter updates were not persisted")
    print("18/26 CSRF protected traffic update persisted exact synthetic byte totals")

    # Read both upstream link-generation routes. A disabled inbound may
    # intentionally produce no connectable links; neither response body nor
    # synthetic subscription identifier is ever logged to Actions output.
    sub_id = client_detail["client"].get("subId")
    require(isinstance(sub_id, str) and len(sub_id) > 0,
            "synthetic client missing subscription identifier")
    api_obj("/panel/api/clients/subLinks/" + parse.quote(sub_id, safe=""))
    api_obj("/panel/api/clients/links/" + encoded_email)
    print("19/26 signed session accessed original subscription and client link APIs")

    api_obj("/panel/api/clients/resetTraffic/" + encoded_email, "POST",
            {}, crud_csrf)
    traffic = api_obj("/panel/api/clients/traffic/" + encoded_email)
    require(traffic.get("up") == 0 and traffic.get("down") == 0,
            "traffic reset failed to clear synthetic client counters")
    post_reset = api_obj("/panel/api/clients/get?email=" + encoded_email)
    require(post_reset.get("client", {}).get("enable") is False,
            "reset unexpectedly enabled the synthetic client")
    print("20/26 traffic reset cleared counters without enabling the synthetic client")

    # True TCP dataplane test. The CI Docker container runs --network none:
    # the HTTP proxy and synthetic origin bind only loopback inside it.
    import http.server as http_server
    import socket
    import threading

    class LocalOrigin(http_server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/ci-xray-probe":
                self.send_error(404)
                return
            body = b"vela-loopback-xray-tcp-ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # No request data in public CI output.

    # Upstream deliberately blocks geoip:private in BOTH routing and the
    # freedom outbound finalRules. An ordinary local proxy request must stay
    # blocked. Only this disposable container's named test inbound may reach
    # one exact loopback address, using a dedicated test-only outbound.
    default_config = api_obj("/panel/api/xray/getDefaultJsonConfig")
    require(isinstance(default_config, dict), "original Xray template is unavailable")
    base_rules = default_config.get("routing", {}).get("rules", [])
    require(isinstance(base_rules, list) and
            any("geoip:private" in rule.get("ip", []) and
                rule.get("outboundTag") == "blocked" for rule in base_rules),
            "default private-address routing protection unexpectedly absent")
    original_direct = next((outbound for outbound in default_config.get("outbounds", [])
                            if outbound.get("tag") == "direct"), None)
    require(original_direct is not None and
            any("geoip:private" in rule.get("ip", []) and
                rule.get("action") == "block"
                for rule in original_direct.get("settings", {}).get("finalRules", [])),
            "original freedom outbound private-address block unexpectedly absent")

    confined = json.loads(json.dumps(default_config))
    confined["outbounds"].append({
        "tag": "ci-only-local-egress",
        "protocol": "freedom",
        "settings": {},
    })
    confined["routing"]["rules"].insert(0, {
        "type": "field",
        "inboundTag": ["ci-loopback-tcp"],
        "ip": ["127.0.0.1/32"],
        "outboundTag": "ci-only-local-egress",
    })
    def write_isolated_xray_template(config):
        body = parse.urlencode({
            "xraySetting": json.dumps(config, separators=(",", ":")),
        }).encode("utf-8")
        req = request.Request(
            BASE + "/panel/api/xray/update",
            method="POST",
            data=body,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRF-Token": crud_csrf,
            },
        )
        try:
            resp = opener.open(req, timeout=10)
        except error.HTTPError as exc:
            resp = exc
        with resp as response:
            code = response.status
            payload = response.read(512 * 1024)
        require(code == 200, "protected Xray test-template update rejected")
        result = json.loads(payload)
        require(result.get("success") is True,
                "Xray rejected synthetic confined loopback routing")
    write_isolated_xray_template(confined)
    print("TCP-CI stage: private-IP default protections retained; precise test-only route installed", flush=True)

    origin = http_server.ThreadingHTTPServer(("127.0.0.1", 0), LocalOrigin)
    thread = threading.Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    port = 28343
    live_id = None
    try:
        live = api_obj("/panel/api/inbounds/add", "POST", {
            "remark": "CI disposable local TCP dataplane",
            "enable": True, "listen": "127.0.0.1", "port": port,
            "protocol": "http", "settings": {"accounts": []},
            "streamSettings": {"network": "tcp", "security": "none"},
            "sniffing": {"enabled": False}, "tag": "ci-loopback-tcp",
            "trafficReset": "never",
        }, crud_csrf)
        require(isinstance(live, dict) and isinstance(live.get("id"), int)
                and live.get("enable") is True and live.get("listen") == "127.0.0.1",
                "synthetic enabled inbound did not retain loopback binding")
        live_id = live["id"]
        print("TCP-CI stage: inbound created", flush=True)
        api_obj("/panel/api/server/restartXrayService", "POST", {}, crud_csrf)
        print("TCP-CI stage: Xray restarted", flush=True)
        dst_port = origin.server_address[1]
        packet = (f"GET http://127.0.0.1:{dst_port}/ci-xray-probe HTTP/1.1\r\n"
                  f"Host: 127.0.0.1:{dst_port}\r\n"
                  "Connection: close\r\n\r\n").encode("ascii")
        passed = False
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2) as conn:
                    conn.settimeout(2)
                    conn.sendall(packet)
                    reply = bytearray()
                    while len(reply) < 8192:
                        part = conn.recv(8192 - len(reply))
                        if not part:
                            break
                        reply.extend(part)
                if b" 200 " in reply[:64] and b"vela-loopback-xray-tcp-ok" in reply:
                    passed = True
                    break
            except OSError:
                pass
            time.sleep(1)
        require(passed, "genuine Xray TCP proxy did not reach synthetic origin")
        print("TCP-CI stage: real proxy roundtrip succeeded", flush=True)
        addresses = []
        for line in Path("/proc/net/tcp").read_text(encoding="ascii").splitlines()[1:]:
            cols = line.split()
            if cols[3] == "0A" and cols[1].endswith(f":{port:04X}"):
                addresses.append(cols[1].split(":")[0])
        require(addresses and set(addresses) == {"0100007F"},
                "live TCP proxy listener was not restricted to 127.0.0.1")
    finally:
        if live_id is not None:
            api_obj(f"/panel/api/inbounds/del/{live_id}", "POST", {}, crud_csrf)
            api_obj("/panel/api/server/restartXrayService", "POST", {}, crud_csrf)
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=3)
        # Restore the exact original policy before subsequent test actions,
        # even if the TCP test raised. This container is destroyed by CI too.
        write_isolated_xray_template(default_config)
    for _ in range(15):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass
        except OSError:
            break
        time.sleep(1)
    else:
        raise AssertionError("deleted Xray TCP inbound retained a listener")
    print("21/26 real Xray TCP dataplane, kernel loopback binding and teardown verified")

    # SOCKS5 UDP ASSOCIATE reaches a real UDP echo service through Xray.
    # All sockets stay inside the --network none Docker namespace. Unlike
    # merely creating a UDP inbound, this checks an application-layer reply.
    # The temporary routing exception is tied to one inbound and /32 target;
    # every other inbound still uses upstream private-IP blocking rules.
    import struct
    udp_confined = json.loads(json.dumps(confined))
    udp_confined["routing"]["rules"].insert(0, {
        "type": "field",
        "inboundTag": ["ci-loopback-udp"],
        "ip": ["127.0.0.1/32"],
        "network": "udp",
        "outboundTag": "ci-only-local-egress",
    })
    echo_stop = threading.Event()
    echo_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    echo_socket.bind(("127.0.0.1", 0))
    echo_socket.settimeout(0.2)

    def udp_echo():
        while not echo_stop.is_set():
            try:
                data, peer = echo_socket.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            if data == b"vela-udp-loopback-request":
                try:
                    echo_socket.sendto(b"vela-udp-loopback-response", peer)
                except OSError:
                    break

    echo_thread = threading.Thread(target=udp_echo, daemon=True)
    echo_thread.start()
    udp_id = None
    udp_control = None
    relay_port = None
    try:
        write_isolated_xray_template(udp_confined)
        udp_row = api_obj("/panel/api/inbounds/add", "POST", {
            "remark": "CI disposable SOCKS5 UDP dataplane",
            "enable": True, "listen": "127.0.0.1", "port": 28344,
            "protocol": "mixed",
            "settings": {"auth": "noauth", "udp": True,
                         "ip": "127.0.0.1"},
            "streamSettings": {"network": "tcp", "security": "none"},
            "sniffing": {"enabled": False}, "tag": "ci-loopback-udp",
            "trafficReset": "never",
        }, crud_csrf)
        require(isinstance(udp_row, dict) and
                isinstance(udp_row.get("id"), int) and
                udp_row.get("listen") == "127.0.0.1" and
                udp_row.get("enable") is True,
                "synthetic SOCKS5 UDP inbound did not persist as loopback-only")
        udp_id = udp_row["id"]
        api_obj("/panel/api/server/restartXrayService", "POST", {}, crud_csrf)
        print("UDP-CI stage: isolated SOCKS5 inbound started", flush=True)

        for _ in range(15):
            try:
                udp_control = socket.create_connection(("127.0.0.1", 28344),
                                                       timeout=2)
                udp_control.settimeout(3)
                break
            except OSError:
                time.sleep(0.5)
        require(udp_control is not None, "SOCKS5 control listener not reachable")

        def recv_exact(sock, count):
            pieces = bytearray()
            while len(pieces) < count:
                part = sock.recv(count - len(pieces))
                if not part:
                    raise AssertionError("truncated SOCKS5 UDP control reply")
                pieces.extend(part)
            return bytes(pieces)

        udp_control.sendall(b"\x05\x01\x00")
        require(recv_exact(udp_control, 2) == b"\x05\x00",
                "SOCKS5 no-auth negotiation rejected")
        # 0.0.0.0:0 tells the SOCKS5 server that the UDP source port is
        # dynamically allocated; the destination remains strict loopback.
        udp_control.sendall(b"\x05\x03\x00\x01" + b"\x00" * 6)
        answer = recv_exact(udp_control, 4)
        require(answer == b"\x05\x00\x00\x01",
                "SOCKS5 UDP ASSOCIATE rejected or returned non-IPv4 address")
        relay_ip = socket.inet_ntoa(recv_exact(udp_control, 4))
        relay_port = struct.unpack("!H", recv_exact(udp_control, 2))[0]
        require(relay_ip == "127.0.0.1" and 1 <= relay_port <= 65535,
                "SOCKS5 UDP relay advertised a non-loopback address")
        print("UDP-CI stage: SOCKS5 UDP ASSOCIATE negotiated", flush=True)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.bind(("127.0.0.1", 0))
            udp.settimeout(1.5)
            target_port = echo_socket.getsockname()[1]
            datagram = (b"\x00\x00\x00\x01" +
                        socket.inet_aton("127.0.0.1") +
                        struct.pack("!H", target_port) +
                        b"vela-udp-loopback-request")
            echoed = False
            for _ in range(8):
                udp.sendto(datagram, (relay_ip, relay_port))
                try:
                    response, _ = udp.recvfrom(512)
                except socket.timeout:
                    continue
                if (response[:4] == b"\x00\x00\x00\x01" and
                        response[10:] == b"vela-udp-loopback-response"):
                    echoed = True
                    break
            require(echoed, "UDP packet did not traverse Xray and return via SOCKS5")
        print("UDP-CI stage: application-layer datagram echoed through Xray", flush=True)

        # Detect the core's known wildcard UDP binding pitfall, which is
        # unsafe on Vela host-network deployments even if 'listen' is local.
        bindings = []
        for line in Path("/proc/net/udp").read_text(encoding="ascii").splitlines()[1:]:
            columns = line.split()
            if columns[1].endswith(f":{relay_port:04X}"):
                bindings.append(columns[1].split(":")[0])
        require(bindings and set(bindings) == {"0100007F"},
                "Xray SOCKS5 UDP relay bound a non-loopback interface")
        print("UDP-CI stage: kernel UDP relay socket restricted to loopback", flush=True)
    finally:
        if udp_control is not None:
            udp_control.close()
        if udp_id is not None:
            api_obj(f"/panel/api/inbounds/del/{udp_id}", "POST", {}, crud_csrf)
            api_obj("/panel/api/server/restartXrayService", "POST", {}, crud_csrf)
        echo_stop.set()
        echo_socket.close()
        echo_thread.join(timeout=3)
        write_isolated_xray_template(default_config)

    # The UDP association is closed and its inbound was removed.
    if relay_port is not None:
        for _ in range(15):
            in_use = any(
                line.split()[1].endswith(f":{relay_port:04X}")
                for line in Path("/proc/net/udp").read_text(encoding="ascii").splitlines()[1:]
            )
            if not in_use:
                break
            time.sleep(0.25)
        else:
            raise AssertionError("removed SOCKS5 UDP relay retained a kernel UDP listener")
    print("22/26 genuine SOCKS5 UDP relay, loopback bind and teardown verified")

    api_obj("/panel/api/clients/del/" + encoded_email, "POST", {}, crud_csrf)
    clients = api_obj("/panel/api/clients/list")
    require(not any(row.get("email") == email for row in (clients or [])),
            "deleted synthetic client still appears in client list")
    api_obj(f"/panel/api/inbounds/del/{vless_id}", "POST", {}, crud_csrf)
    listed = api_obj("/panel/api/inbounds/list")
    require(not any(row.get("id") == vless_id for row in (listed or [])),
            "synthetic VLESS inbound remained after cleanup")
    print("23/26 signed admin deleted synthetic client and VLESS inbound")

    # In Mini App mode the original password login route must never be an
    # alternative to the Telegram-signed, allowlisted identity.
    current_csrf = csrf_token()
    require(current_csrf != refreshed_csrf, "second privileged login did not rotate CSRF")
    status, _, _ = http("/login", method="POST", payload={}, csrf=current_csrf)
    require(status == 404, "legacy password login was not disabled in Mini App mode")
    print("24/26 legacy password login endpoint was disabled")

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
    # The unauthenticated panel redirect may show the public Telegram login
    # page (with its bootstrap SDK), but it must NOT render authenticated
    # Mini App navigation or re-enable the panel WebApp bridge.
    status, anonymous_page, _ = http("/panel/")
    require(status in (200, 401, 403) and
            b"window.X_UI_TG_MINIAPP_MODE=true" not in anonymous_page,
            "logout left authenticated Telegram Mini App panel mode enabled")
    print("25/26 logout revoked APIs and authenticated Telegram panel mode")

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
    print("26/26 replay of a copied signed cookie after logout rejected; HTTPS smoke PASS")

if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, ValueError, OSError, ssl.SSLError,
            json.JSONDecodeError, TimeoutError):
        # Never leak HTTP bodies, raw initData, cookies, keys or user details.
        print("FAIL: isolated Mini App HTTPS session or signature contract")
        raise SystemExit(1)
