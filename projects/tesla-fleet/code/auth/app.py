#!/usr/bin/env python3
"""Tesla Fleet API OAuth helper for example.com (stdlib only).

Modes:
  app.py serve                 -> HTTP server (/auth/start/<token>, /auth/callback, /auth/health)
  app.py refresh [--if-needed] -> refresh tokens in TOKENS_FILE (rotating refresh token)
  app.py status                -> print token metadata (no token values)
Secrets never logged.
"""
import fcntl, hmac, html, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

AUTHORIZE_URL = "https://auth.tesla.com/oauth2/v3/authorize"
TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
AUDIENCE = os.environ.get("TESLA_AUDIENCE", "https://fleet-api.prd.eu.vn.cloud.tesla.com")
REDIRECT_URI = os.environ.get("TESLA_REDIRECT_URI", "https://example.com/auth/callback")
SCOPES = os.environ.get("TESLA_SCOPES", "openid offline_access user_data vehicle_device_data vehicle_location vehicle_cmds vehicle_charging_cmds")
LOCALE = os.environ.get("TESLA_LOCALE", "ru-RU")
SECRETS_FILE = os.environ.get("SECRETS_FILE", "/opt/tesla/secrets.env")
TOKENS_FILE = os.environ.get("TOKENS_FILE", "/opt/tesla/data/tokens.json")
STATE_TTL = 600
COOKIE = "tesla_oauth_state"


def load_secrets():
    env = {}
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    for k in ("TESLA_CLIENT_ID", "TESLA_CLIENT_SECRET", "AUTH_START_TOKEN"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg, file=sys.stderr, flush=True)


def token_request(params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            j = json.loads(body)
        except Exception:
            j = {"raw": body[:300]}
        # strip anything token-like from error payloads
        return e.code, {k: v for k, v in j.items() if "token" not in k}


def save_tokens(resp, previous=None):
    now = int(time.time())
    data = {
        "access_token": resp["access_token"],
        "refresh_token": resp.get("refresh_token") or (previous or {}).get("refresh_token"),
        "id_token": resp.get("id_token"),
        "token_type": resp.get("token_type"),
        "scope": resp.get("scope"),
        "expires_in": resp.get("expires_in"),
        "obtained_at": now,
        "expires_at": now + int(resp.get("expires_in") or 0),
        "audience": AUDIENCE,
    }
    if previous and previous.get("refresh_token") and previous.get("refresh_token") != data["refresh_token"]:
        # previous refresh token stays valid ~24h; keep it as a fallback
        data["previous_refresh_token"] = previous["refresh_token"]
    d = os.path.dirname(TOKENS_FILE)
    os.makedirs(d, mode=0o700, exist_ok=True)
    tmp = TOKENS_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKENS_FILE)
    return data


class Lock:
    def __enter__(self):
        os.makedirs(os.path.dirname(TOKENS_FILE), mode=0o700, exist_ok=True)
        self.f = open(TOKENS_FILE + ".lock", "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self
    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()


# ---------------- HTTP server ----------------
PENDING = {}  # state -> (expires, nonce)


def page(title, body):
    return ("<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>body{{font-family:system-ui,sans-serif;max-width:36em;margin:4em auto;padding:0 1em}}</style>"
            f"</head><body>{body}</body></html>").encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "tesla-auth"
    sys_version = ""

    def log_message(self, fmt, *args):
        # never log query strings (code/state) or the start token
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/auth/start/"):
            path = "/auth/start/<redacted>"
        log(f'{self.headers.get("X-Forwarded-For", self.client_address[0])} {self.command} {path} {args[1] if len(args) > 1 else ""}')

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or []):
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/auth/health":
            return self.send(200, b"ok\n", "text/plain")
        if u.path.startswith("/auth/start/"):
            return self.start(u.path[len("/auth/start/"):])
        if u.path == "/auth/callback":
            return self.callback(q)
        return self.send(404, page("Not found", "<p>Not found</p>"))

    def start(self, tok):
        sec = load_secrets()
        want = sec.get("AUTH_START_TOKEN", "")
        if not want or not hmac.compare_digest(tok.encode(), want.encode()):
            return self.send(404, page("Not found", "<p>Not found</p>"))
        now = time.time()
        for s in [s for s, (exp, _) in PENDING.items() if exp < now]:
            PENDING.pop(s, None)
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(16)
        PENDING[state] = (now + STATE_TTL, nonce)
        params = {
            "response_type": "code",
            "client_id": sec["TESLA_CLIENT_ID"],
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "locale": LOCALE,
            "prompt_missing_scopes": "true",
        }
        loc = AUTHORIZE_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        cookie = f"{COOKIE}={state}; Path=/auth/callback; Max-Age={STATE_TTL}; HttpOnly; Secure; SameSite=Lax"
        log("auth flow started")
        return self.send(302, b"", headers=[("Location", loc), ("Set-Cookie", cookie)])

    def callback(self, q):
        state = (q.get("state") or [""])[0]
        c = SimpleCookie(self.headers.get("Cookie", ""))
        cstate = c[COOKIE].value if COOKIE in c else ""
        entry = PENDING.get(state) if state else None
        if not entry or entry[0] < time.time() or not cstate or not hmac.compare_digest(state, cstate):
            log("callback rejected: invalid state")
            return self.send(400, page("Ошибка", "<h1>Ошибка</h1><p>Неверный или просроченный параметр state. Начните заново по ссылке запуска.</p>"))
        PENDING.pop(state, None)
        clear = f"{COOKIE}=; Path=/auth/callback; Max-Age=0; HttpOnly; Secure; SameSite=Lax"
        if q.get("error"):
            err = html.escape(q["error"][0]); desc = html.escape((q.get("error_description") or [""])[0])
            log(f"callback: authorization error {q['error'][0]}")
            return self.send(400, page("Ошибка", f"<h1>Доступ не получен</h1><p>{err}: {desc}</p>"), headers=[("Set-Cookie", clear)])
        code = (q.get("code") or [""])[0]
        if not code:
            return self.send(400, page("Ошибка", "<h1>Ошибка</h1><p>Нет параметра code.</p>"), headers=[("Set-Cookie", clear)])
        sec = load_secrets()
        status, resp = token_request({
            "grant_type": "authorization_code",
            "client_id": sec["TESLA_CLIENT_ID"],
            "client_secret": sec["TESLA_CLIENT_SECRET"],
            "code": code,
            "audience": AUDIENCE,
            "redirect_uri": REDIRECT_URI,
        })
        if status != 200 or "access_token" not in resp:
            log(f"code exchange failed: HTTP {status} {resp.get('error', '')} {resp.get('error_description', '')}")
            return self.send(502, page("Ошибка", f"<h1>Ошибка обмена кода</h1><p>HTTP {status}: {html.escape(str(resp.get('error', '')))}</p>"), headers=[("Set-Cookie", clear)])
        with Lock():
            d = save_tokens(resp)
        log(f"tokens saved (scope={d.get('scope')}, expires_in={d.get('expires_in')}, refresh={'yes' if d.get('refresh_token') else 'no'})")
        return self.send(200, page("Готово", "<h1>Готово, доступ получен. Можно закрыть страницу.</h1>"), headers=[("Set-Cookie", clear)])


def serve():
    port = int(os.environ.get("PORT", "8000"))
    log(f"listening on :{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def refresh(if_needed=False, min_valid=7200):
    sec = load_secrets()
    with Lock():
        if not os.path.exists(TOKENS_FILE):
            print("no tokens file yet; complete the /auth/start flow first", file=sys.stderr)
            return 0 if if_needed else 2
        with open(TOKENS_FILE) as f:
            cur = json.load(f)
        left = int(cur.get("expires_at", 0)) - int(time.time())
        if if_needed and left > min_valid:
            print(f"access token still valid for {left}s; skip"); return 0
        status, resp = token_request({"grant_type": "refresh_token", "client_id": sec["TESLA_CLIENT_ID"],
                                      "refresh_token": cur["refresh_token"]})
        if status != 200 and cur.get("previous_refresh_token"):
            print(f"refresh failed (HTTP {status}); trying previous refresh token", file=sys.stderr)
            status, resp = token_request({"grant_type": "refresh_token", "client_id": sec["TESLA_CLIENT_ID"],
                                          "refresh_token": cur["previous_refresh_token"]})
        if status != 200 or "access_token" not in resp:
            print(f"refresh FAILED: HTTP {status} {resp.get('error', '')} {resp.get('error_description', '')}", file=sys.stderr)
            return 1
        d = save_tokens(resp, previous=cur)
    print(f"refreshed: expires_in={d.get('expires_in')} rotated={'yes' if d.get('refresh_token') != cur.get('refresh_token') else 'no'}")
    return 0


def status():
    if not os.path.exists(TOKENS_FILE):
        print("no tokens yet"); return 2
    with open(TOKENS_FILE) as f:
        d = json.load(f)
    left = int(d.get("expires_at", 0)) - int(time.time())
    print(json.dumps({"scope": d.get("scope"), "obtained_at": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(d.get("obtained_at", 0))),
                      "access_token_valid_for_s": left, "has_refresh_token": bool(d.get("refresh_token"))}, indent=2))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve": serve()
    elif cmd == "refresh": sys.exit(refresh("--if-needed" in sys.argv))
    elif cmd == "status": sys.exit(status())
    else: print(__doc__); sys.exit(64)
