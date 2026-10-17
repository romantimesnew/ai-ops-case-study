#!/usr/bin/env python3
"""Car command endpoint for iOS Shortcuts / Siri (example.com/car/<action>).

  POST /car/<action>          (GET allowed for /car/status, /car/distance and /car/car_location only)
  Authorization: Bearer <SHORTCUT_TOKEN from secrets.env>
  ?dry_run=1 (or JSON {"dry_run": true}) -> show what would be sent, nothing is sent to Tesla
  Response: JSON {"ok": bool, "message": "<short spoken sentence for Siri>", ...}
  Language: SHORTCUT_LANG=en (default) or ru.

Bad/missing token -> 404 (endpoint looks absent). Rate limit: 10 req/min per client IP
(and 20/min overall) -> 429 for authenticated callers, 404 otherwise.
Commands go through the local tesla-http-proxy (signs them; Highland needs signed commands).
The car is woken first (wake_up, poll up to ~30 s). status never wakes the car: when it
sleeps, the last known values come from the telemetry DB (v_latest).
Every Tesla API call is logged to api_calls (source=shortcut) + data/api_calls.log.
PROXIMITY_ACTIONS (trunk/frunk/charge port) need the phone location (JSON lat/lon/accuracy or
query params) within PROXIMITY_MAX_M of the car; decisions go to table proximity_checks.
/car/status optionally takes the phone lat/lon too (JSON or query, same parsing): it then appends
how far and in which direction the car is (telemetry DB only, no wake) and adds a `distance` object.
/car/distance is kept as a backward-compatible alias (distance sentence + lock state only).
/car/car_location (GET/POST) returns where the car is (DB only, no wake, no Tesla call).
distance, status and car_location add top-level car_lat/car_lon/car_coords/car_maps_url and
car_address (reverse geocoded via Nominatim, cached per ~11 m cell, 2 s timeout, omitted on failure).
Secrets and tokens are never logged. stdlib + psycopg only.
"""
import hmac, json, os, ssl, sys, threading, time, urllib.error, urllib.parse, urllib.request
from collections import deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

sys.path.insert(0, "/auth")
import app as authapp  # noqa: E402  (shared token refresh logic, same lock file)

PROXY = os.environ.get("TESLA_PROXY", "https://proxy:4443")
CA = os.environ.get("TESLA_PROXY_CA", "/proxy/tls-cert.pem")
TOKENS = os.environ.get("TOKENS_FILE", "/data/tokens.json")
SECRETS = os.environ.get("SECRETS_FILE", "/run/tesla/secrets.env")
API_LOG = os.environ.get("API_LOG", "/data/api_calls.log")
VIN = os.environ.get("TESLA_VIN", "<VIN>")
DB_URL = os.environ.get("DATABASE_URL", "")
SOURCE = "shortcut"
TZ = ZoneInfo(os.environ.get("LOCAL_TZ", "UTC"))
WAKE_MAX = int(os.environ.get("WAKE_MAX_S", "30"))
RATE_IP = int(os.environ.get("RATE_PER_MIN", "10"))
RATE_ALL = int(os.environ.get("RATE_GLOBAL_PER_MIN", "20"))
MI_TO_KM = 1.609344
LANG = os.environ.get("SHORTCUT_LANG", "en").strip().lower()
LANG = LANG if LANG in ("en", "ru") else "en"

# Proxy cert is self-signed for localhost/127.0.0.1. We pin exactly that cert (it is the
# only trust anchor), so skipping the hostname match (we connect as "proxy") stays safe.
_ctx = ssl.create_default_context(cafile=CA)
_ctx.check_hostname = False

# action -> (fleet command, params); the success message is STRINGS[lang][action]
ACTIONS = {
    "trunk_open":       ("actuate_trunk", {"which_trunk": "rear"}),
    "frunk_open":       ("actuate_trunk", {"which_trunk": "front"}),
    # actuate_trunk rear TOGGLES the power liftgate: only sent when the trunk is confirmed open
    "trunk_close":      ("actuate_trunk", {"which_trunk": "rear"}),
    "climate_on":       ("auto_conditioning_start", {}),
    "climate_off":      ("auto_conditioning_stop", {}),
    "lock":             ("door_lock", {}),
    "unlock":           ("door_unlock", {}),
    "charge_port_open": ("charge_port_door_open", {}),
    "charge_port_close": ("charge_port_door_close", {}),
    "charge_start":     ("charge_start", {}),
    "charge_stop":      ("charge_stop", {}),
    "defrost_on":       ("set_preconditioning_max", {"on": True, "manual_override": False}),
    "defrost_off":      ("set_preconditioning_max", {"on": False, "manual_override": False}),
    # vehicle-command proxy reads seat_position (0 = front left = driver); Fleet REST name is "heater"
    "seat_heat_driver": ("remote_seat_heater_request", {"heater": 0, "seat_position": 0, "level": 3}),
    "seat_heat_off":    ("remote_seat_heater_request", {"heater": 0, "seat_position": 0, "level": 0}),
    "honk":             ("honk_horn", {}),
    "flash":            ("flash_lights", {}),
    "set_temp":         ("set_temps", None),
}
REASON_KEYS = ("is_charging", "not_charging", "complete", "disconnected", "already_set", "user_present")
CHARGE_KEYS = ("charging", "complete", "disconnected", "stopped", "nopower", "starting")

# User-facing (spoken by Siri) messages. Keep them short and natural.
STRINGS = {
    "en": {
        "trunk_open": "Trunk opened", "frunk_open": "Front trunk opened",
        "trunk_close": "Trunk closing", "trunk_already_closed": "Trunk is already closed",
        "trunk_state_unknown": "Couldn't check whether the trunk is open. Command not sent",
        "climate_on": "Climate on", "climate_off": "Climate off",
        "lock": "Car locked", "unlock": "Car unlocked",
        "charge_port_open": "Charge port opened", "charge_port_close": "Charge port closed",
        "charge_start": "Charging started", "charge_stop": "Charging stopped",
        "defrost_on": "Max defrost on. Windows are defrosting", "defrost_off": "Defrost off",
        "seat_heat_driver": "Driver seat heater on high", "seat_heat_off": "Seat heater off",
        "honk": "Honked the horn", "flash": "Lights flashed",
        "set_temp": "Temperature set to {t} degrees",
        "climate_cabin": "Cabin is {t}", "climate_target": "target {t}",
        "deg": "{t} degrees",
        "r_is_charging": "The car is already charging", "r_not_charging": "The car isn't charging",
        "r_complete": "Charging is already complete", "r_disconnected": "The charge cable isn't plugged in",
        "r_already_set": "Already done", "r_user_present": "Someone is in the car, so the command wasn't run",
        "c_charging": "Charging", "c_complete": "Charging complete", "c_disconnected": "Charge cable unplugged",
        "c_stopped": "Charging stopped", "c_nopower": "No power at the charger", "c_starting": "Charging is starting",
        "temp_missing": "Tell me a temperature, for example 21",
        "temp_range": "Temperature must be between 15 and 28 degrees",
        "not_responding": "The car is not responding. Try again.",
        "failed": "The command failed",
        "busy": "The car is busy with another command. Try again.",
        "server_error": "Server error. Try again.",
        "rate_limit": "Too many requests. Wait a minute.",
        "unknown_cmd": "I don't know that command",
        "post_only": "This command needs a POST request",
        "dry_cmd": "Test only: would send {cmd}",
        "dry_status": "Test only: would check status without waking the car",
        "st_battery": "Battery {soc} percent", "st_range": "range {km} kilometers",
        "st_locked": "Locked", "st_unlocked": "Unlocked",
        "st_inside": "inside {t}", "st_outside": "outside {t}",
        "head_asleep": "The car is asleep", "head_offline": "The car is asleep or offline",
        "head_unknown": "The car is not responding",
        "last_today": "{head}. Last data at {time}: {body}",
        "last_day": "{head}. Last data on {date} at {time}: {body}",
        "loc_required": "Location required for this command",
        "loc_imprecise": "Your location isn't precise enough. Try again outside",
        "too_far": "You're {dist} from the car. Command blocked",
        "car_loc_unknown": "Couldn't get the car's location. Command blocked",
        "dist_m": "{n} meters", "dist_m1": "{n} meter", "dist_km": "{n} kilometers", "dist_km1": "{n} kilometer",
        "dry_prox_allow": "Test only: you're {dist} from the car, would send {cmd}",
        "dry_prox_deny": "Test only, blocked: {msg}",
        "dist_away": "The car is {dist} away, to the {dir}",
        "dist_here": "You're right next to the car, {dist}",
        "dist_stale": "based on location from {age} ago",
        "dist_no_car": "Couldn't get the car's location",
        "dist_locked": "It's locked", "dist_unlocked": "It's unlocked",
        "age_min": "{n} minutes", "age_min1": "a minute", "age_h": "{n} hours", "age_h1": "an hour",
        "age_d": "{n} days", "age_d1": "a day",
        "carloc_at": "The car is at {where}",
        "dir_0": "north", "dir_1": "north-east", "dir_2": "east", "dir_3": "south-east",
        "dir_4": "south", "dir_5": "south-west", "dir_6": "west", "dir_7": "north-west",
    },
    "ru": {
        "trunk_open": "Багажник открыт", "frunk_open": "Передний багажник открыт",
        "trunk_close": "Багажник закрывается", "trunk_already_closed": "Багажник уже закрыт",
        "trunk_state_unknown": "Не удалось проверить багажник, команда не отправлена",
        "climate_on": "Климат включён", "climate_off": "Климат выключен",
        "lock": "Машина закрыта", "unlock": "Машина открыта",
        "charge_port_open": "Лючок зарядки открыт", "charge_port_close": "Лючок зарядки закрыт",
        "charge_start": "Зарядка началась", "charge_stop": "Зарядка остановлена",
        "defrost_on": "Обогрев на максимум, стёкла оттаивают", "defrost_off": "Обогрев стёкол выключен",
        "seat_heat_driver": "Подогрев водительского сиденья включён на максимум", "seat_heat_off": "Подогрев сиденья выключен",
        "honk": "Посигналил", "flash": "Фары мигнули",
        "set_temp": "Температура {t}°",
        "climate_cabin": "в салоне {t}", "climate_target": "цель {t}°",
        "deg": "{t}°",
        "r_is_charging": "Машина уже заряжается", "r_not_charging": "Машина и так не заряжается",
        "r_complete": "Зарядка уже завершена", "r_disconnected": "Кабель не подключён",
        "r_already_set": "Уже сделано", "r_user_present": "В машине кто-то есть, команда не выполнена",
        "c_charging": "Идёт зарядка", "c_complete": "Зарядка завершена", "c_disconnected": "Кабель не подключён",
        "c_stopped": "Зарядка остановлена", "c_nopower": "Нет питания на зарядке", "c_starting": "Зарядка начинается",
        "temp_missing": "Скажи температуру, например 21",
        "temp_range": "Температура должна быть от 15 до 28 градусов",
        "not_responding": "Машина не отвечает, попробуй ещё раз",
        "failed": "Команда не выполнена",
        "busy": "Машина занята другой командой, попробуй ещё раз",
        "server_error": "Ошибка сервера, попробуй ещё раз",
        "rate_limit": "Слишком много запросов, подожди минуту",
        "unknown_cmd": "Не знаю такой команды",
        "post_only": "Эту команду нужно отправлять методом POST",
        "dry_cmd": "Тест: отправил бы {cmd}",
        "dry_status": "Тест: проверил бы состояние без пробуждения",
        "st_battery": "Заряд {soc}%", "st_range": "запас {km} км",
        "st_locked": "Машина закрыта", "st_unlocked": "Машина открыта",
        "st_inside": "в салоне {t}", "st_outside": "снаружи {t}",
        "head_asleep": "Машина спит", "head_offline": "Машина спит или не в сети",
        "head_unknown": "Машина не отвечает",
        "last_today": "{head}. Последние данные на {time}: {body}",
        "last_day": "{head}. Последние данные на {date} {time}: {body}",
        "loc_required": "Для этой команды нужна геопозиция",
        "loc_imprecise": "Геопозиция недостаточно точная, попробуй на улице",
        "too_far": "До машины {dist}, команда заблокирована",
        "car_loc_unknown": "Не удалось узнать, где машина, команда заблокирована",
        "dist_m": "{n} м", "dist_m1": "{n} м", "dist_km": "{n} км", "dist_km1": "{n} км",
        "dry_prox_allow": "Тест: до машины {dist}, отправил бы {cmd}",
        "dry_prox_deny": "Тест, заблокировано: {msg}",
        "dist_away": "Машина в {dist}, направление {dir}",
        "dist_here": "Машина совсем рядом, {dist}",
        "dist_stale": "по данным {age} назад",
        "dist_no_car": "Не удалось узнать, где машина",
        "dist_locked": "Машина закрыта", "dist_unlocked": "Машина открыта",
        "age_min": "{n} мин", "age_min1": "1 мин", "age_h": "{n} ч", "age_h1": "1 ч",
        "age_d": "{n} дн", "age_d1": "1 дн",
        "carloc_at": "Машина здесь: {where}",
        "dir_0": "север", "dir_1": "северо-восток", "dir_2": "восток", "dir_3": "юго-восток",
        "dir_4": "юг", "dir_5": "юго-запад", "dir_6": "запад", "dir_7": "северо-запад",
    },
}


def T(key, **kw):
    msg = STRINGS[LANG].get(key) or STRINGS["en"][key]
    return msg.format(**kw) if kw else msg


def fmt_time(dt):
    return dt.strftime("%-I:%M %p") if LANG == "en" else dt.strftime("%H:%M")


def fmt_date(dt):
    return dt.strftime("%B %-d") if LANG == "en" else dt.strftime("%d.%m")


def log(msg):
    print(datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S%z"), msg, file=sys.stderr, flush=True)


# ---------------- Tesla API via proxy ----------------
def load_secrets():
    env = {}
    try:
        with open(SECRETS) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except OSError:
        pass
    return env


def access_token():
    with open(TOKENS) as f:
        t = json.load(f)
    if float(t.get("expires_at", 0)) - time.time() < 600:
        try:
            authapp.refresh(if_needed=True)
        except Exception as e:
            log(f"token refresh error: {type(e).__name__}")
        with open(TOKENS) as f:
            t = json.load(f)
    return t["access_token"]


def db_exec(sql, params=(), fetch=False):
    import psycopg
    with psycopg.connect(DB_URL, connect_timeout=5) as c:
        cur = c.execute(sql, params)
        return cur.fetchall() if fetch else None


def log_call(method, path, status, dur_ms):
    ep = path.replace(VIN, "{vin}")
    parts = ep.split("?")[0].strip("/").split("/")
    cmd = parts[-1] if parts else ""
    may_wake = "/command/" in ep or cmd == "wake_up" or (method == "POST" and cmd == "fleet_telemetry_config")
    rec = {"ts": datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S%z"), "vin": VIN, "method": method, "endpoint": ep, "command": cmd,
           "http_status": status, "duration_ms": dur_ms, "may_wake": may_wake, "source": SOURCE}
    try:
        with open(API_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    try:
        db_exec("INSERT INTO api_calls (vin, method, endpoint, command, http_status, duration_ms, may_wake, source) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (VIN, method, ep, cmd, status, dur_ms, may_wake, SOURCE))
    except Exception as e:
        log(f"api_calls insert failed: {type(e).__name__}")


def call(method, path, body=None, timeout=40):
    path = path.replace("{vin}", VIN)
    t0, status, out = time.time(), 0, {}
    try:
        headers = {"Authorization": "Bearer " + access_token(), "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(PROXY + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, context=_ctx, timeout=timeout) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        try:
            out = json.loads(raw) if raw else {}
        except ValueError:
            out = {"raw": raw[:300].decode(errors="replace")}
    except Exception as e:
        out = {"error": f"request failed: {type(e).__name__}"}
    finally:
        log_call(method, path, status, int((time.time() - t0) * 1000))
    return status, out


def vehicle_state():
    s, o = call("GET", "/api/1/vehicles/{vin}", timeout=15)
    return (o.get("response") or {}).get("state") if s == 200 else None


def ensure_awake():
    """True when online. wake_up, then poll every 3-5 s up to WAKE_MAX seconds."""
    if vehicle_state() == "online":
        return True
    s, o = call("POST", "/api/1/vehicles/{vin}/wake_up", timeout=15)
    if s >= 400:
        return False
    if (o.get("response") or {}).get("state") == "online":
        return True
    t0, delay = time.time(), 3
    while time.time() - t0 < WAKE_MAX:
        time.sleep(delay)
        delay = min(delay + 1, 5)
        if vehicle_state() == "online":
            time.sleep(1)  # give the car a moment to bring up the vehicle-command session
            return True
    return False


def asleep_error(s, o):
    txt = json.dumps(o).lower()
    return s == 408 or "offline" in txt or "asleep" in txt or "unavailable" in txt


# ---------------- telemetry DB ----------------
LATEST_FIELDS = ("Soc", "BatteryLevel", "RatedRange", "EstBatteryRange", "Locked", "HvacPower", "InsideTemp",
                 "OutsideTemp", "DetailedChargeState", "ChargeState", "HvacLeftTemperatureRequest")


def latest():
    rows = db_exec("SELECT field, value_num, value_text, ts FROM v_latest WHERE vin = %s AND field = ANY(%s)",
                   (VIN, list(LATEST_FIELDS)), fetch=True)
    return {f: (n, t, ts) for f, n, t, ts in rows}


def rnd(x):
    return None if x is None else round(x, 1)


def deg(x):
    return T("deg", t=round(x))


# ---------------- proximity check (trunk/frunk/charge port) ----------------
# The phone sends its location ({"lat","lon","accuracy"} JSON body or ?lat=&lon=&accuracy=).
# Car location, cheapest/most reliable source first:
#   1. telemetry DB (Location field), accepted when one of these holds:
#      fresh     - Location timestamp <= PROXIMITY_FRESH_S old (default 120 s)
#      streaming - telemetry is CONNECTED and a Location arrived after that connect
#                  (the car sends every field on connect and Location on every 5 m change)
#      parked    - Gear is P, the Location is newer than the last non-P gear (last drive)
#                  and Odometer didn't grow since that Location (< PROXIMITY_ODO_SLACK_MI)
#   2. otherwise (real commands only, after wake): give the telemetry reconnect snapshot
#      PROXIMITY_TELEMETRY_WAIT_S to land, then GET vehicle_data?endpoints=location_data
#      (Highland/2023.38+ returns no GPS unless location_data is requested explicitly).
# A DB location that is trusted is checked BEFORE waking, so a far-away request never wakes
# the car; after wake the DB is re-read once (cheap) in case a fresher Location arrived.
import math  # noqa: E402

PROX_ACTIONS = {a.strip() for a in os.environ.get(
    "PROXIMITY_ACTIONS", "trunk_open,frunk_open,charge_port_open").split(",") if a.strip()}
PROX_MAX_M = float(os.environ.get("PROXIMITY_MAX_M", "50"))
PROX_MAX_ACC = float(os.environ.get("PROXIMITY_MAX_ACCURACY_M", "50"))
PROX_REQUIRE_ACC = os.environ.get("PROXIMITY_REQUIRE_ACCURACY", "0").strip().lower() in ("1", "true", "yes")
PROX_FRESH_S = float(os.environ.get("PROXIMITY_FRESH_S", "120"))
PROX_TEL_WAIT = float(os.environ.get("PROXIMITY_TELEMETRY_WAIT_S", "4"))
PROX_ODO_SLACK = float(os.environ.get("PROXIMITY_ODO_SLACK_MI", "0.15"))


def parse_num(v):
    """Number from int/float or a string like '12.3456', '12,3456', ' 5 m', '1 234,5'."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = str(v).strip().replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace("\u2212", "-")
        s = s.rstrip("m°").strip()
        if "," in s and "." in s:          # 1,234.5 or 1.234,5
            s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            x = float(s)
        except ValueError:
            return None
    return x if math.isfinite(x) else None


def phone_location(extra, q):
    def get(*keys):
        for k in keys:
            if k in extra and extra[k] not in (None, ""):
                return extra[k]
        for k in keys:
            if k in q and q[k][0] != "":
                return q[k][0]
        return None
    lat, lon = parse_num(get("lat", "latitude")), parse_num(get("lon", "lng", "longitude"))
    acc = parse_num(get("accuracy", "acc", "horizontal_accuracy"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return lat, lon, acc


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def car_location_db():
    """Latest telemetry Location + whether it can be trusted without asking the car."""
    rows = db_exec("""
        WITH loc AS (SELECT ts, (value_json->>'latitude')::float8 lat, (value_json->>'longitude')::float8 lon
                     FROM telemetry_raw WHERE vin=%(v)s AND field='Location' AND value_json ? 'latitude'
                     ORDER BY ts DESC LIMIT 1)
        SELECT loc.ts, loc.lat, loc.lon, extract(epoch FROM now()-loc.ts),
          (SELECT value_text FROM telemetry_raw WHERE vin=%(v)s AND field='Gear' ORDER BY ts DESC LIMIT 1),
          (SELECT max(ts) FROM telemetry_raw WHERE vin=%(v)s AND field='Gear'
                  AND coalesce(value_text,'') NOT IN ('ShiftStateP','ShiftStateInvalid','ShiftStateSNA','')),
          (SELECT value_num FROM telemetry_raw WHERE vin=%(v)s AND field='Odometer' ORDER BY ts DESC LIMIT 1),
          (SELECT value_num FROM telemetry_raw WHERE vin=%(v)s AND field='Odometer' AND ts <= loc.ts + interval '5 seconds'
                  ORDER BY ts DESC LIMIT 1),
          (SELECT status FROM wake_events WHERE vin=%(v)s ORDER BY ts DESC LIMIT 1),
          (SELECT max(ts) FROM wake_events WHERE vin=%(v)s AND status='CONNECTED')
        FROM loc""", {"v": VIN}, fetch=True)
    if not rows or rows[0][1] is None:
        return None
    ts, lat, lon, age, gear, last_drive, odo_now, odo_at, tstatus, tconn = rows[0]
    rule = None
    if age <= PROX_FRESH_S:
        rule = "fresh"
    elif tstatus == "CONNECTED" and tconn is not None and ts >= tconn - timedelta(seconds=15):
        rule = "streaming"
    elif gear == "ShiftStateP" and (last_drive is None or ts >= last_drive) and \
            (odo_now is None or odo_at is None or odo_now - odo_at <= PROX_ODO_SLACK):
        rule = "parked"
    return {"lat": lat, "lon": lon, "ts": ts, "age_s": int(age), "trusted": rule is not None,
            "rule": rule or "stale", "source": "telemetry"}


def car_location_api():
    s, o = call("GET", "/api/1/vehicles/{vin}/vehicle_data?endpoints=location_data", timeout=20)
    r = o.get("response") if s == 200 and isinstance(o, dict) else None
    ds = (r or {}).get("drive_state") or {}
    lat, lon = ds.get("latitude"), ds.get("longitude")
    if lat is None or lon is None:
        lat, lon = ds.get("active_route_latitude"), ds.get("active_route_longitude")
        lat = lon = None  # route destination is not the car position
    if lat is None or lon is None:
        log(f"vehicle_data location_data: HTTP {s}, no coordinates")
        return None
    age = None
    if ds.get("gps_as_of"):
        age = int(time.time() - float(ds["gps_as_of"]))
    return {"lat": float(lat), "lon": float(lon), "age_s": age, "trusted": True, "rule": "vehicle_data",
            "source": "vehicle_data"}


def fmt_distance(m, clamp=True):
    mm = int(round(m / 10.0) * 10) if m >= 100 else int(round(m))
    if clamp and m > PROX_MAX_M and mm <= PROX_MAX_M:   # never say "50 meters" for a blocked 50.3 m
        mm = int(PROX_MAX_M) + 1
    if mm < 1000:
        return T("dist_m1" if mm == 1 else "dist_m", n=mm)
    km = m / 1000.0
    n = f"{km:.1f}".rstrip("0").rstrip(".") if km < 10 else str(int(round(km)))
    if LANG == "ru":
        n = n.replace(".", ",")
    return T("dist_km1" if n == "1" else "dist_km", n=n)


def log_proximity(action, dry, decision, reason, dist, acc, car, phone, ms, max_m=None):
    log(f"proximity {action}{' dry_run' if dry else ''}: {decision} reason={reason} "
        f"distance_m={'-' if dist is None else int(round(dist))} accuracy_m={'-' if acc is None else round(acc)} "
        f"car={car.get('source') + '/' + car.get('rule') if car else '-'} {ms}ms")
    try:
        r4 = lambda x: None if x is None else round(x, 4)
        db_exec("INSERT INTO proximity_checks (vin, action, dry_run, decision, reason, distance_m, accuracy_m, "
                "max_m, car_source, car_rule, car_age_s, phone_lat, phone_lon, car_lat, car_lon, check_ms) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (VIN, action, dry, decision, reason, None if dist is None else int(round(dist)),
                 None if acc is None else round(acc, 1), int(PROX_MAX_M) if max_m is None else max_m or None,
                 car.get("source") if car else None, car.get("rule") if car else None,
                 car.get("age_s") if car else None, r4(phone[0]) if phone else None,
                 r4(phone[1]) if phone else None, r4(car["lat"]) if car else None,
                 r4(car["lon"]) if car else None, ms))
    except Exception as e:
        log(f"proximity_checks insert failed: {type(e).__name__}")


class Proximity:
    """Runs the check in stages so the command path can interleave it with the wake step."""

    def __init__(self, action, extra, q, dry):
        self.action, self.dry, self.q, self.extra = action, dry, q, extra
        self.phone = phone_location(extra, q)
        self.car, self.dist, self.ms = None, None, 0

    def _t(self, f, *a):
        t0 = time.time()
        try:
            return f(*a)
        finally:
            self.ms += int((time.time() - t0) * 1000)

    def result(self, decision, reason, msg_key=None, **kw):
        acc = self.phone[2] if self.phone else None
        log_proximity(self.action, self.dry, decision, reason, self.dist, acc, self.car, self.phone, self.ms)
        info = {"decision": decision, "reason": reason, "max_m": PROX_MAX_M, "check_ms": self.ms,
                "distance_m": None if self.dist is None else int(round(self.dist)),
                "accuracy_m": None if acc is None else round(acc, 1)}
        if self.car:
            info.update(car_source=self.car["source"], car_rule=self.car["rule"], car_age_s=self.car.get("age_s"))
        return info, (T(msg_key, **kw) if msg_key else None)

    def pre(self):
        """Before wake / any Tesla call.
        Returns (info, message) when denied (final), (info, None) for a dry-run allow,
        (None, None) when a trusted DB location already says "near" (re-checked after wake),
        or None when the DB can't decide (no or stale car location)."""
        if self.phone is None:
            return self.result("deny", "no_phone_location", "loc_required")
        acc = self.phone[2]
        if acc is not None and (acc < 0 or acc > PROX_MAX_ACC):
            return self.result("deny", "accuracy", "loc_imprecise")
        if acc is None and PROX_REQUIRE_ACC:
            return self.result("deny", "accuracy_missing", "loc_imprecise")
        try:
            self.car = self._t(car_location_db)
        except Exception as e:
            log(f"car_location_db failed: {type(e).__name__}")
            self.car = None
        if not self.car or not (self.car["trusted"] or self.dry):
            return None
        self.dist = haversine_m(self.phone[0], self.phone[1], self.car["lat"], self.car["lon"])
        if self.dist > PROX_MAX_M:
            return self.result("deny", "too_far", "too_far", dist=fmt_distance(self.dist))
        if self.dry:
            return self.result("allow", "near")
        return None, None

    def decide(self):
        c, p = self.car, self.phone
        self.dist = haversine_m(p[0], p[1], c["lat"], c["lon"])
        if self.dist > PROX_MAX_M:
            return self.result("deny", "too_far", "too_far", dist=fmt_distance(self.dist))
        return self.result("allow", "near")

    def post_wake(self):
        """After wake (car online). Returns (info, deny_message_or_None) - always final."""
        prev = self.car if self.car and self.car["trusted"] else None
        try:
            c = self._t(car_location_db)
        except Exception:
            c = None
        if c and c["trusted"] and (prev is None or c["ts"] >= prev["ts"]):
            self.car = c
            return self.decide()
        if prev:
            return self.decide()
        # untrusted DB: the wake normally triggers a telemetry reconnect snapshot; wait briefly
        deadline = time.time() + PROX_TEL_WAIT
        while time.time() < deadline:
            self._t(time.sleep, 1)
            try:
                c = self._t(car_location_db)
            except Exception:
                c = None
            if c and c["rule"] in ("fresh", "streaming"):
                self.car = c
                return self.decide()
        self.car = self._t(car_location_api)
        if not self.car:
            return self.result("deny", "car_location_unavailable", "car_loc_unknown")
        return self.decide()


# ---------------- distance / direction to the car (DB only, never wakes) ----------------
DIST_HERE_M = 10


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing from point 1 (phone) to point 2 (car), 0 = north, clockwise."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def fmt_age(s):
    m = max(1, int(round(s / 60.0)))
    if m < 60:
        return T("age_min1" if m == 1 else "age_min", n=m)
    h = int(round(s / 3600.0))
    if h < 24:
        return T("age_h1" if h == 1 else "age_h", n=h)
    d = int(round(s / 86400.0))
    return T("age_d1" if d == 1 else "age_d", n=d)


def distance_part(phone, car):
    """Distance sentence phone -> car (no lock state, no final period) + JSON object. DB data only."""
    acc = phone[2]
    dist = haversine_m(phone[0], phone[1], car["lat"], car["lon"])
    brg = bearing_deg(phone[0], phone[1], car["lat"], car["lon"])
    direction = T("dir_%d" % (int((brg + 22.5) // 45) % 8))
    if dist < DIST_HERE_M:
        msg = T("dist_here", dist=fmt_distance(dist, clamp=False))
    else:
        msg = T("dist_away", dist=fmt_distance(dist, clamp=False), dir=direction)
    if not car["trusted"]:
        msg += ", " + T("dist_stale", age=fmt_age(car["age_s"]))
    obj = {"distance_m": int(round(dist)), "bearing_deg": int(round(brg)) % 360,
           "direction": direction, "accuracy_m": None if acc is None else round(acc, 1),
           "car_rule": car["rule"], "car_age_s": car["age_s"], "car_trusted": car["trusted"],
           "car_as_of": car["ts"].astimezone(TZ).isoformat()}
    return dist, msg, obj


def do_distance(extra, q, dry):
    """Backward-compatible alias (/car/distance): distance + direction + lock state, DB only.
    status with phone lat/lon is the main way now. No Tesla API call, no wake."""
    t0 = time.time()
    phone = phone_location(extra, q)
    acc = phone[2] if phone else None
    car = car_db_safe()   # also without phone location: the car_* fields are still returned
    cf = car_fields(car)
    ms = lambda: int((time.time() - t0) * 1000)
    dryk = {"dry_run": True} if dry else {}
    if phone is None:
        log_proximity("distance", dry, "info", "no_phone_location", None, acc, None, None, ms(), max_m=0)
        return {"ok": False, "message": T("loc_required"), **dryk, **cf}
    if not car:
        log_proximity("distance", dry, "info", "car_location_unavailable", None, acc, None, phone, ms(), max_m=0)
        return {"ok": False, "message": T("dist_no_car"), **dryk}
    dist, msg, obj = distance_part(phone, car)
    locked = None
    try:
        lk = latest().get("Locked")
        locked = None if not lk or lk[0] is None else bool(lk[0])
    except Exception as e:
        log(f"latest() failed: {type(e).__name__}")
    if locked is not None:
        msg += ". " + T("dist_locked" if locked else "dist_unlocked")
    msg += "."
    log_proximity("distance", dry, "info", "distance", dist, acc, car, phone, ms(), max_m=0)
    return {"ok": True, "message": msg, **dryk, **cf,
            "distance": {**obj, "locked": locked, "check_ms": ms(), "tesla_api_calls": 0}}


# ---------------- car location fields for Shortcuts (Set Parked Car etc.) ----------------
# Reverse geocoding: Nominatim (OpenStreetMap), usage policy: identifying User-Agent, <= 1 req/s,
# cache results. Cache key = coordinates rounded to 4 dp (~11 m). Memory + /data file (survives restarts).
GEO_URL = os.environ.get("GEOCODER_URL", "https://nominatim.openstreetmap.org/reverse")
GEO_UA = os.environ.get("GEOCODER_UA", "tesla-shortcut/1.0 (+https://example.com; personal use)")
GEO_TIMEOUT = float(os.environ.get("GEOCODER_TIMEOUT_S", "2"))
GEO_CACHE_FILE = os.environ.get("GEOCODER_CACHE_FILE", "/data/geocode_cache.json")
GEO_TTL = 30 * 86400        # good answers
GEO_FAIL_TTL = 300          # failures: don't retry (and wait 2 s) on every request
GEO_MAX = 2000
CAR_LABEL = os.environ.get("CAR_MAPS_LABEL", "<CAR_NAME>")
_geo_lock = threading.Lock()
_geo_cache = None           # key -> [address or None, expires_epoch]
_geo_last = 0.0


def _geo_load():
    global _geo_cache
    if _geo_cache is None:
        try:
            with open(GEO_CACHE_FILE) as f:
                _geo_cache = {k: v for k, v in json.load(f).items() if v[0]}
        except Exception:
            _geo_cache = {}
    return _geo_cache


def _geo_save():
    try:
        items = sorted(((k, v) for k, v in _geo_cache.items() if v[0]), key=lambda kv: -kv[1][1])[:GEO_MAX]
        tmp = GEO_CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(dict(items), f, ensure_ascii=False)
        os.replace(tmp, GEO_CACHE_FILE)
    except Exception as e:
        log(f"geocode cache save failed: {type(e).__name__}")


def _fmt_address(o):
    a = o.get("address") or {}
    street = a.get("road") or a.get("pedestrian") or a.get("footway") or a.get("square") or a.get("place") \
        or a.get("neighbourhood") or a.get("hamlet")
    num = a.get("house_number")
    if street and num:
        street = f"{street} {num}"
    elif not street and o.get("name"):
        street = o["name"]
    city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county")
    district = a.get("city_district") or a.get("suburb") or a.get("quarter")
    parts = [p for p in (street, district if district and district != city else None, city) if p]
    if parts:
        return ", ".join(dict.fromkeys(parts))
    dn = o.get("display_name") or ""
    return ", ".join(dn.split(", ")[:3]) or None


def reverse_geocode(lat, lon):
    """Short street address or None. Cached; at most one live lookup per second; 2 s timeout."""
    global _geo_last
    key = f"{lat:.4f},{lon:.4f}"
    now = time.time()
    with _geo_lock:
        c = _geo_load()
        hit = c.get(key)
        if hit and hit[1] > now:
            return hit[0]
        if now - _geo_last < 1.1:       # Nominatim: max 1 request/s
            return hit[0] if hit else None
        _geo_last = now
    addr = None
    t0 = time.time()
    try:
        qs = urllib.parse.urlencode({"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 18,
                                     "addressdetails": 1, "accept-language": "en" if LANG == "en" else "ru"})
        req = urllib.request.Request(GEO_URL + "?" + qs, headers={"User-Agent": GEO_UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=GEO_TIMEOUT) as r:
            o = json.loads(r.read(65536))
        if isinstance(o, dict) and not o.get("error"):
            addr = _fmt_address(o)
    except Exception as e:
        log(f"reverse geocode failed: {type(e).__name__} {int((time.time()-t0)*1000)}ms")
    with _geo_lock:
        _geo_cache[key] = [addr, time.time() + (GEO_TTL if addr else GEO_FAIL_TTL)]
        if addr:
            _geo_save()
    return addr


def car_fields(car, geocode=True):
    """Top-level JSON fields for Shortcuts from a car location dict (car_location_db())."""
    if not car:
        return {}
    lat, lon = round(car["lat"], 6), round(car["lon"], 6)
    coords = f"{lat:.6f},{lon:.6f}"
    out = {"car_lat": lat, "car_lon": lon, "car_coords": coords}
    addr = reverse_geocode(lat, lon) if geocode else None
    if addr:
        out["car_address"] = addr
    out["car_maps_url"] = f"https://maps.apple.com/?ll={coords}&q={urllib.parse.quote(CAR_LABEL)}"
    out["car_location_url"] = f"https://maps.apple.com/?ll={coords}"   # no label: cleanest for Location coercion
    if car.get("ts") is not None:
        out["car_as_of"] = car["ts"].astimezone(TZ).isoformat()
    out["car_age_s"] = car.get("age_s")
    out["car_trusted"] = car.get("trusted")
    return out


def car_db_safe():
    try:
        return car_location_db()
    except Exception as e:
        log(f"car_location_db failed: {type(e).__name__}")
        return None


def do_car_location(dry):
    """Where is the car: DB only, no wake, no Tesla call."""
    t0 = time.time()
    car = car_db_safe()
    dryk = {"dry_run": True} if dry else {}
    if not car:
        return {"ok": False, "message": T("dist_no_car"), **dryk}
    f = car_fields(car)
    where = f.get("car_address") or f"{f['car_lat']:.6f}, {f['car_lon']:.6f}"
    msg = T("carloc_at", where=where)
    if not car["trusted"]:
        msg += ", " + T("dist_stale", age=fmt_age(car["age_s"]))
    msg += "."
    return {"ok": True, "message": msg, **dryk, **f, "car_rule": car["rule"],
            "check_ms": int((time.time() - t0) * 1000), "tesla_api_calls": 0}


# ---------------- rear trunk state (trunk_close) ----------------
# actuate_trunk(rear) toggles a power liftgate, so trunk_close is sent only when the trunk is
# confirmed OPEN. Before wake: telemetry DoorState.TrunkRear == false -> "already closed" (no wake;
# the trunk can't open without the car waking and streaming the change). After wake the open
# state must be current: DoorState that is fresh (<= PROXIMITY_FRESH_S) or arrived after the
# current telemetry connect; otherwise vehicle_data?endpoints=vehicle_state (rt != 0 = open).
def trunk_db():
    rows = db_exec("""
        SELECT (d.value_json->>'TrunkRear')::boolean, d.ts, extract(epoch FROM now()-d.ts),
          (SELECT status FROM wake_events WHERE vin=%(v)s ORDER BY ts DESC LIMIT 1),
          (SELECT max(ts) FROM wake_events WHERE vin=%(v)s AND status='CONNECTED')
        FROM telemetry_raw d WHERE d.vin=%(v)s AND d.field='DoorState' AND d.value_json ? 'TrunkRear'
        ORDER BY d.ts DESC LIMIT 1""", {"v": VIN}, fetch=True)
    if not rows or rows[0][0] is None:
        return None
    is_open, ts, age, tstatus, tconn = rows[0]
    current = age <= PROX_FRESH_S or (tstatus == "CONNECTED" and tconn is not None
                                      and ts >= tconn - timedelta(seconds=15))
    return {"open": bool(is_open), "age_s": int(age), "current": current, "source": "telemetry"}


def trunk_api():
    s, o = call("GET", "/api/1/vehicles/{vin}/vehicle_data?endpoints=vehicle_state", timeout=20)
    vs = ((o.get("response") or {}).get("vehicle_state") or {}) if s == 200 and isinstance(o, dict) else {}
    rt = vs.get("rt")
    if rt is None:
        log(f"vehicle_data vehicle_state: HTTP {s}, no rt")
        return None
    return {"open": rt != 0, "age_s": 0, "current": True, "source": "vehicle_data"}


def trunk_state(after_wake):
    try:
        t = trunk_db()
    except Exception as e:
        log(f"trunk_db failed: {type(e).__name__}")
        t = None
    if not after_wake or (t and t["current"]):
        return t
    deadline = time.time() + PROX_TEL_WAIT   # wake usually triggers a fresh telemetry snapshot
    while time.time() < deadline:
        time.sleep(1)
        try:
            t = trunk_db()
        except Exception:
            t = None
        if t and t["current"]:
            return t
    return trunk_api()


# ---------------- actions ----------------
def climate_msg():
    try:
        L = latest()
        inside = L.get("InsideTemp", (None,))[0]
        target = L.get("HvacLeftTemperatureRequest", (None,))[0]
        extra = []
        if inside is not None:
            extra.append(T("climate_cabin", t=deg(inside)))
        if target is not None:
            extra.append(T("climate_target", t=f"{target:g}"))
        if not extra:
            return T("climate_on")
        return T("climate_on") + (". " if LANG == "en" else ", ") + ", ".join(extra)
    except Exception:
        return T("climate_on")


def do_command(action, extra, dry, q=None):
    cmd, params = ACTIONS[action]
    okmsg = T(action)
    if action == "set_temp":
        t = extra.get("temp")
        try:
            t = float(str(t).replace(",", "."))
        except (TypeError, ValueError):
            return {"ok": False, "message": T("temp_missing")}
        if not 15 <= t <= 28:
            return {"ok": False, "message": T("temp_range")}
        t = round(t * 2) / 2
        params = {"driver_temp": t, "passenger_temp": t}
        okmsg = T("set_temp", t=f"{t:g}")
    path = f"/api/1/vehicles/{{vin}}/command/{cmd}"
    prox = Proximity(action, extra, q or {}, dry) if action in PROX_ACTIONS else None
    pre = prox.pre() if prox else None
    if pre and pre[1]:  # denied before any Tesla call (the car is not woken)
        info, msg = pre
        if dry:
            return {"ok": False, "dry_run": True, "message": T("dry_prox_deny", msg=msg), "proximity": info}
        return {"ok": False, "message": msg, "proximity": info}
    tinfo = None
    if action == "trunk_close":
        t0 = time.time()
        t = trunk_state(after_wake=False)
        tinfo = {"trunk_open": t["open"] if t else None, "source": t["source"] if t else None,
                 "age_s": t["age_s"] if t else None, "check_ms": int((time.time() - t0) * 1000)}
        log(f"trunk_close pre-check: open={tinfo['trunk_open']} age_s={tinfo['age_s']}")
        if t and not t["open"]:
            return {"ok": True, "message": T("trunk_already_closed"), "trunk": tinfo,
                    **({"dry_run": True} if dry else {})}
    if dry:
        out = {"ok": True, "dry_run": True, "message": T("dry_cmd", cmd=cmd),
               "would_send": {"wake_first": "if not online (wake_up, poll ≤%ds)" % WAKE_MAX,
                              "method": "POST", "path": path, "body": params}}
        if prox:
            if pre is None:  # no car location in the DB at all
                info, msg = prox.result("deny", "car_location_unavailable", "car_loc_unknown")
                info["live_would_try"] = "vehicle_data?endpoints=location_data after wake"
                return {"ok": False, "dry_run": True, "message": T("dry_prox_deny", msg=msg), "proximity": info}
            info = pre[0]
            if not prox.car["trusted"]:
                info["live_would_try"] = "telemetry snapshot after wake, else vehicle_data?endpoints=location_data"
            out["proximity"] = info
            out["message"] = T("dry_prox_allow", dist=fmt_distance(prox.dist), cmd=cmd)
        if tinfo:
            tinfo["live_would_check"] = ("current DoorState after wake, else vehicle_data?endpoints=vehicle_state "
                                         "(rt); sends only if open")
            out["trunk"] = tinfo
        return out
    if not ensure_awake():
        if prox:
            prox.result("deny", "car_not_responding")
        return {"ok": False, "message": T("not_responding")}
    pinfo = None
    if prox:
        pinfo, msg = prox.post_wake()
        if msg:
            return {"ok": False, "message": msg, "proximity": pinfo}
    if action == "trunk_close":
        t = trunk_state(after_wake=True)
        log(f"trunk_close post-wake: open={t['open'] if t else None} source={t['source'] if t else None}")
        if t is None:
            return {"ok": False, "message": T("trunk_state_unknown")}
        if not t["open"]:
            return {"ok": True, "message": T("trunk_already_closed")}
    s, o = call("POST", path, params, timeout=40)
    if s != 200 and asleep_error(s, o) and ensure_awake():
        s, o = call("POST", path, params, timeout=40)
    resp = o.get("response") if isinstance(o, dict) else None
    if s == 200 and isinstance(resp, dict) and resp.get("result"):
        if action == "climate_on":
            okmsg = climate_msg()
        return {"ok": True, "message": okmsg, **({"proximity": pinfo} if pinfo else {})}
    reason = (resp or {}).get("reason") if isinstance(resp, dict) else None
    reason = reason or (o.get("error") if isinstance(o, dict) else None) or f"HTTP {s}"
    log(f"command {cmd} failed: HTTP {s} {str(reason)[:200]}")
    if asleep_error(s, o) or s == 0:
        return {"ok": False, "message": T("not_responding")}
    for k in REASON_KEYS:
        if k in str(reason).lower():
            return {"ok": False, "message": T("r_" + k), "reason": reason}
    return {"ok": False, "message": T("failed"), "reason": str(reason)[:200]}


def status_msg(soc, range_mi, locked, climate, inside, outside, charge):
    p = []
    if soc is not None:
        p.append(T("st_battery", soc=round(soc))
                 + (", " + T("st_range", km=round(range_mi * MI_TO_KM)) if range_mi is not None else ""))
    if locked is not None:
        p.append(T("st_locked") if locked else T("st_unlocked"))
    if climate is not None:
        p.append(T("climate_on") if climate else T("climate_off"))
    t = []
    if inside is not None:
        t.append(T("st_inside", t=deg(inside)))
    if outside is not None:
        t.append(T("st_outside", t=deg(outside)))
    if t:
        s = ", ".join(t)
        p.append(s[0].upper() + s[1:])
    if charge:
        c = str(charge).lower().replace("detailedchargestate", "")
        if c in CHARGE_KEYS:
            p.append(T("c_" + c))
    return ". ".join(p) + "." if p else ""


def _append_sentence(msg, sentence):
    msg = (msg or "").strip()
    if msg and msg[-1] not in ".!?":
        msg += "."
    return (msg + " " if msg else "") + sentence


def do_status(dry, extra=None, q=None):
    phone = phone_location(extra or {}, q or {})   # optional; same parsing as distance/proximity
    res = _do_status(dry)
    t0 = time.time()
    car = car_db_safe()                      # car location from the telemetry DB only (never wakes)
    res.update(car_fields(car))
    if phone is None:
        return res                           # no phone location: unchanged behaviour
    acc = phone[2]
    ms = lambda: int((time.time() - t0) * 1000)
    if not car:
        log_proximity("status", dry, "info", "car_location_unavailable", None, acc, None, phone, ms(), max_m=0)
        res["message"] = _append_sentence(res.get("message"), T("dist_no_car") + ".")
        res["distance"] = None
        return res
    dist, sentence, obj = distance_part(phone, car)   # lock state is already in the status message
    log_proximity("status", dry, "info", "distance", dist, acc, car, phone, ms(), max_m=0)
    res["message"] = _append_sentence(res.get("message"), sentence + ".")
    res["distance"] = {**obj, "check_ms": ms(), "tesla_api_calls": 0}
    return res


def _do_status(dry):
    if dry:
        return {"ok": True, "dry_run": True, "message": T("dry_status"),
                "would_send": [{"method": "GET", "path": "/api/1/vehicles/{vin}"},
                               {"if": "online", "method": "GET",
                                "path": "/api/1/vehicles/{vin}/vehicle_data?endpoints=charge_state;climate_state;vehicle_state"},
                               {"if": "asleep/offline", "source": "telemetry DB v_latest"}]}
    st = vehicle_state()
    if st == "online":
        s, o = call("GET", "/api/1/vehicles/{vin}/vehicle_data?endpoints="
                    + urllib.parse.quote("charge_state;climate_state;vehicle_state", safe=""), timeout=25)
        r = o.get("response") if s == 200 and isinstance(o, dict) else None
        if r:
            cs, cl, vs = r.get("charge_state") or {}, r.get("climate_state") or {}, r.get("vehicle_state") or {}
            rng = cs.get("battery_range")
            d = {"state": "online", "soc": cs.get("battery_level"),
                 "range_km": round(rng * MI_TO_KM) if rng is not None else None,
                 "locked": vs.get("locked"), "climate_on": cl.get("is_climate_on"),
                 "inside_temp": cl.get("inside_temp"), "outside_temp": cl.get("outside_temp"),
                 "charging_state": cs.get("charging_state"), "source": "vehicle_data"}
            msg = status_msg(d["soc"], rng, d["locked"], d["climate_on"], d["inside_temp"], d["outside_temp"],
                             d["charging_state"])
            return {"ok": True, "message": msg, "data": d}
        if not asleep_error(s, o):
            log(f"vehicle_data failed: HTTP {s}")
        st = "asleep" if asleep_error(s, o) else st
    # asleep/offline/unknown -> last known values from telemetry
    try:
        L = latest()
    except Exception as e:
        log(f"latest() failed: {type(e).__name__}")
        L = {}
    num = lambda f: (L.get(f) or (None,))[0]
    txt = lambda f: (L.get(f) or (None, None))[1]
    soc = num("BatteryLevel") if num("BatteryLevel") is not None else num("Soc")
    rng = num("RatedRange") if num("RatedRange") is not None else num("EstBatteryRange")
    locked = None if num("Locked") is None else bool(num("Locked"))
    hv = txt("HvacPower")
    climate = None if not hv else ("on" in hv.lower().replace("hvacpowerstate", ""))
    charge = txt("DetailedChargeState") or txt("ChargeState")
    tss = [v[2] for v in L.values() if v[2] is not None]
    when = max(tss).astimezone(TZ) if tss else None
    head = T({"asleep": "head_asleep", "offline": "head_offline"}.get(st, "head_unknown"))
    body = status_msg(soc, rng, locked, climate, num("InsideTemp"), num("OutsideTemp"), charge)
    if when and body:
        b = body[0].lower() + body[1:]
        if when.date() == datetime.now(TZ).date():
            msg = T("last_today", head=head, time=fmt_time(when), body=b)
        else:
            msg = T("last_day", head=head, date=fmt_date(when), time=fmt_time(when), body=b)
    else:
        msg = head + "." + (" " + body if body else "")
    d = {"state": st or "unknown", "soc": round(soc, 1) if soc is not None else None,
         "range_km": round(rng * MI_TO_KM) if rng is not None else None, "locked": locked, "climate_on": climate,
         "inside_temp": rnd(num("InsideTemp")), "outside_temp": rnd(num("OutsideTemp")), "charging_state": charge,
         "as_of": when.isoformat() if when else None, "source": "telemetry"}
    return {"ok": True, "message": msg, "data": d}


# ---------------- HTTP ----------------
_rl_lock = threading.Lock()
_hits = {}          # ip -> deque of timestamps
_hits_all = deque()


def rate_ok(ip):
    now = time.time()
    with _rl_lock:
        q = _hits.setdefault(ip, deque())
        for d in (q, _hits_all):
            while d and d[0] < now - 60:
                d.popleft()
        if len(q) >= RATE_IP or len(_hits_all) >= RATE_ALL:
            return False
        q.append(now); _hits_all.append(now)
        for k in [k for k, d in _hits.items() if not d]:
            _hits.pop(k, None)
        return True


_cmd_lock = threading.Lock()  # one vehicle operation at a time
INFO_ACTIONS = ("status", "distance", "car_location")   # GET allowed


class Handler(BaseHTTPRequestHandler):
    server_version = "tesla-car"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # we log our own line (never headers/query)

    def client_ip(self):
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def not_found(self):
        self.send_json(404, {"error": "not found"})

    def authed(self):
        want = load_secrets().get("SHORTCUT_TOKEN", "")
        h = self.headers.get("Authorization", "")
        got = h[7:].strip() if h[:7].lower() == "bearer " else ""
        return bool(want) and len(want) >= 32 and hmac.compare_digest(got.encode(), want.encode())

    def do_GET(self):
        self.handle_req("GET")

    def do_POST(self):
        self.handle_req("POST")

    def handle_req(self, method):
        t0 = time.time()
        u = urllib.parse.urlsplit(self.path)
        ip = self.client_ip()
        # drain body (bounded) so keep-alive stays consistent
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 8192)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n > 0 else b""
        if u.path == "/car/health" and not self.headers.get("X-Forwarded-For"):
            return self.send_json(200, {"ok": True})  # local only (not via caddy)
        action = u.path[len("/car/"):].strip("/") if u.path.startswith("/car/") else None
        within = rate_ok(ip)
        ok_auth = self.authed()
        if not ok_auth or action is None:
            log(f"{ip} {method} {u.path} -> 404 (auth)")
            return self.not_found()
        if not within:
            log(f"{ip} {method} /car/{action} -> 429")
            return self.send_json(429, {"ok": False, "message": T("rate_limit")})
        if action not in INFO_ACTIONS and action not in ACTIONS:
            log(f"{ip} {method} /car/{action} -> unknown action")
            return self.send_json(404, {"ok": False, "message": T("unknown_cmd")})
        if method == "GET" and action not in INFO_ACTIONS:
            return self.send_json(405, {"ok": False, "message": T("post_only")})
        q = urllib.parse.parse_qs(u.query)
        extra = {}
        if raw.strip():
            try:
                extra = json.loads(raw)
                if not isinstance(extra, dict):
                    extra = {}
            except ValueError:
                extra = {}
        for k in ("temp",):
            if k in q and k not in extra:
                extra[k] = q[k][0]
        dry = (q.get("dry_run", ["0"])[0].lower() in ("1", "true", "yes")) or extra.get("dry_run") in (True, 1, "1", "true")
        try:
            if action == "status":
                res = do_status(dry, extra, q)
            elif action == "distance":   # alias kept for old Shortcuts; DB only, no Tesla call, no lock
                res = do_distance(extra, q, dry)
            elif action == "car_location":   # DB only, no Tesla call
                res = do_car_location(dry)
            elif dry:
                res = do_command(action, extra, True, q)
            else:
                if not _cmd_lock.acquire(timeout=60):
                    res = {"ok": False, "message": T("busy")}
                else:
                    try:
                        res = do_command(action, extra, False, q)
                    finally:
                        _cmd_lock.release()
        except Exception as e:
            log(f"error in {action}: {type(e).__name__}")
            res = {"ok": False, "message": T("server_error")}
        log(f"{ip} {method} /car/{action}{' dry_run' if dry else ''} -> ok={res.get('ok')} {int((time.time()-t0)*1000)}ms")
        self.send_json(200, res)


def main():
    port = int(os.environ.get("PORT", "8000"))
    try:
        import psycopg  # noqa: F401  warm import (~0.5 s) so the first request doesn't pay it
    except Exception:
        pass
    log(f"listening on :{port} lang={LANG} proximity={','.join(sorted(PROX_ACTIONS))} max_m={PROX_MAX_M:g} "
        f"max_acc_m={PROX_MAX_ACC:g}")
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == "__main__":
    main()
