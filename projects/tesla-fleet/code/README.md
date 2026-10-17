# Tesla Fleet API – personal setup (example.com)

Server: small cloud VPS, Ubuntu 26.04, `/opt/tesla`. Everything runs from `/opt/tesla/docker-compose.yml`.
Vehicle: Model 3 Highland "<CAR_NAME>", VIN `${TESLA_VIN}`, id <VEHICLE_ID>, EU region.
Fleet API is pay-as-you-go. Don't poll `vehicle_data`. Use telemetry, which pushes data only when values change.

Official references: https://developer.tesla.com/docs/fleet-api ,
https://github.com/teslamotors/vehicle-command , https://github.com/teslamotors/fleet-telemetry

## Services (docker compose)

| service   | image                              | listens                     | purpose |
|-----------|------------------------------------|-----------------------------|---------|
| caddy     | `tesla-caddy-l4` (caddy:2 + caddy-l4, built from `caddy/Dockerfile`) | 0.0.0.0:80/443 | HTTPS site, `/auth/*` → auth, LE certs, **SNI passthrough** of `telemetry.example.com` → telemetry:8443 |
| auth      | `tesla-auth`                | 127.0.0.1:8081              | OAuth login/callback, writes `data/tokens.json` |
| proxy     | `tesla/vehicle-command:0.4.1`      | 127.0.0.1:4443 (TLS, self-signed `proxy/tls-cert.pem`) | tesla-http-proxy: signs vehicle commands and the telemetry config with `keys/private-key.pem`. Forwards everything else to the EU Fleet API (host taken from the token) |
| telemetry | `tesla/fleet-telemetry:v0.9.5`     | internal :8443 (mTLS), reached via caddy :443 | Vehicle streams here over a WebSocket with mTLS |
| kafka     | `apache/kafka:4.1.0` (KRaft, 1 node, 256 MB heap) | internal :9092 | Durable buffer. Topics `tesla_V`, `tesla_connectivity`, `tesla_alerts`, `tesla_errors` (7 days / 1 GB retention each) |
| consumer  | `tesla-consumer` (`consumer/`) | –                        | Kafka → TimescaleDB, at-least-once, VIN allowlist |
| db        | `timescale/timescaledb:latest-pg17` | 127.0.0.1:5432             | Storage. DB/user `tesla`, password in `db.env` (0600) |
| shortcut  | `tesla-shortcut` (`shortcut/`) | 127.0.0.1:8082           | iOS Shortcuts / Siri command endpoint, caddy `/car/*` → shortcut (see below) |

Restart a service after you edit its config: `cd /opt/tesla && docker compose restart <service>`. Bind-mounted files that get replaced aren't picked up otherwise.
Approximate RAM: kafka ~420 MB, the rest <50 MB each.

### Port / firewall decision
The telemetry server shares **port 443** with the website. The caddy-l4 listener wrapper looks at the TLS SNI. Connections for
`telemetry.example.com` are passed through as raw TCP to fleet-telemetry, which terminates mTLS itself (Tesla requires this).
All other traffic goes to Caddy's normal HTTPS. **No extra port is needed. The cloud firewall and ufw stay at 22/80/443.**

### Telemetry TLS certificate
* Caddy obtains and renews the Let's Encrypt cert for `telemetry.example.com` (site block in `caddy/Caddyfile`, HTTP-01 on :80, TLS-ALPN disabled).
* `bin/telemetry_cert_sync` (systemd `tesla-telemetry-cert-sync.timer`, every 12 h) copies the cert to `telemetry/certs/`
  (owner uid 65532) and restarts `telemetry` when it changes. fleet-telemetry only loads the cert at startup.
* The chain is currently leaf ← LE **YE2** ← Root YE (cross-signed by X2) ← ISRG Root X2 (cross-signed by X1).
* `telemetry/ca-chain.pem` is the CA bundle the vehicle receives: the served intermediates, int-YE1/YE3, Root YE, ISRG Root X2, and ISRG Root X1.
  It still verifies after LE rotates within the YE family. If LE ever switches this host to a different family, rebuild it (see `telemetry/ca/`) and re-run `configure_telemetry`.
  Check it with: `fleet-telemetry/tools/check_server_cert.sh` (hostname telemetry.example.com, port 443, ca = ca-chain.pem). It currently reports valid.

## CLI helper: `/opt/tesla/bin/tesla`
Uses the current access token from `data/tokens.json` (it auto-refreshes via `bin/refresh_token --if-needed`) and calls the proxy.
Output is JSON. The exit code is 2 on an HTTP error. Token values are never printed.
```
tesla status                 # online/asleep/offline (does not wake)
tesla data [--no-wake] [endpoints]   # vehicle_data; wakes if 408 (costly, avoid polling)
tesla wake                   # wake_up and wait until online
tesla cmd <command> [json]   # e.g. tesla cmd set_charge_limit '{"percent":80}', tesla cmd flash_lights
                             # honk_horn, door_lock, door_unlock, auto_conditioning_start/stop,
                             # set_temps '{"driver_temp":21,"passenger_temp":21}', charge_start/stop,
                             # actuate_trunk '{"which_trunk":"rear"}'
tesla fleet-status           # key pairing / firmware / telemetry client version
tesla telemetry-config       # synced?   tesla telemetry-errors
tesla get|post|delete <path> [json]   # raw; {vin} is substituted
```
Every call is logged without tokens to the DB table `api_calls` and to `data/api_calls.log` (JSONL), so wakes we cause can be identified.
Set `TESLA_CALLER=name` to tag calls from scripts. Calls made to the proxy directly (curl) are **not** logged, so always use the helper.

## Vehicle telemetry configuration
`/opt/tesla/bin/configure_telemetry [--dry-run]` builds the config from `telemetry/fields.json` and `telemetry/ca-chain.pem`
(hostname telemetry.example.com, port 443, `delivery_policy: latest`, `alert_types: [service]`, exp = now + 360 days)
and POSTs it to `/api/1/vehicles/fleet_telemetry_config` through the proxy. The proxy signs it and forwards it as `fleet_telemetry_config_jws`.
* Tesla requires exp < now + 364 days. **Re-run before ~2027-10-12** (current exp 2027-10-12, 1823362816).
* `SelfDrivingMilesSinceReset`/`MilesSinceReset` need `minimum_delta` ≥ 1.
* Every field streams on change, at most once per `interval_seconds`. `minimum_delta` filters out noise.
  * Fast fields: VehicleSpeed 2 s, Location 3 s/5 m, PackCurrent 2 s, Gear/Locked/DoorState/charge state 1 s.
  * Most other fields: 10–60 s.
  * Static fields: 600 s.
* The car rejected two fields as `unsupported_field` (LifetimeEnergyGainedRegen, ScheduledDepartureTime). They have been removed from fields.json (they are still in the config currently on the car, which is harmless).
* Units are as sent by the car: speed in mph, Odometer/ranges/MilesToArrival in **miles**, temperatures in °C, pressures in bar, energy in kWh.

## iOS Shortcuts / Siri endpoint: `https://example.com/car/<action>`
Code: `shortcut/app.py` (stdlib + psycopg). Container `shortcut`: 127.0.0.1:8082, read-only, caps dropped. Caddy routes `/car/*` to it (body ≤ 8 KB, 120 s upstream timeout).
* **Auth:** header `Authorization: Bearer <SHORTCUT_TOKEN>`. The token is in `secrets.env` (`SHORTCUT_TOKEN`, 64 chars = 48 random bytes) and is copied to `data/shortcut_token.txt` (0600 root).
  The token is compared in constant time. A missing or wrong token gets **404** `{"error":"not found"}`, the same as an unknown path, so probing reveals nothing.
  `/car/health` works only locally (`curl 127.0.0.1:8082/car/health`). Through Caddy it returns 404.
  **Rotate:** edit `SHORTCUT_TOKEN` in `secrets.env` and `data/shortcut_token.txt`. The service rereads the file on every request, so no restart is needed. Then update the Shortcuts.
* **Rate limit:** 10 requests/min per client IP and 20/min overall (failed requests count too). Over the limit, a valid token gets 429 `{"ok":false,"message":"Too many requests. Wait a minute."}` and an invalid one gets 404.
* **Methods:** POST for everything. GET is accepted for `/car/status`, `/car/distance` (legacy alias) and `/car/car_location` only (GET on another action returns 405). An unknown action with a valid token returns 404 `"I don't know that command"` (and GET on a non-status action: "This command needs a POST request").
* **Response:** `{"ok": bool, "message": "<short spoken sentence for Siri>"}` with HTTP 200, including when the car refuses the command (`ok:false`, plus `reason`, e.g. "The car is already charging", "The charge cable isn't plugged in", "Someone is in the car, so the command wasn't run", otherwise "The command failed"). In the Shortcut, speak `message`.
* **Language:** env `SHORTCUT_LANG` on the `shortcut` service in `docker-compose.yml`: `en` (default, natural spoken English, km and °C, 12-hour time in `LOCAL_TZ`) or `ru` (the original Russian strings). All strings are in the `STRINGS` dict in `app.py`. To switch: edit the value, then `docker compose up -d --no-deps shortcut`. The startup log shows `lang=…`.
* **Dry run:** add `?dry_run=1` (or put `"dry_run": true` in the JSON body). It returns `would_send` (command path and body) and **sends nothing to Tesla**.
* **Wake:** before a command, the service calls `GET /api/1/vehicles/{vin}`. If the car isn't online, it sends `wake_up` and polls every 3–5 s for up to 30 s, then sends the command through the signing proxy. On 408/offline it wakes once more and retries.
  If the car still doesn't come online, the reply is "The car is not responding. Try again." If another command is running: "The car is busy with another command. Try again." Only one vehicle command runs at a time.
* **Logging:** every Tesla call is written to `api_calls` and `data/api_calls.log` with `source='shortcut'`. Token values are never logged. View the service log with `docker compose logs shortcut`.

| path (POST) | Fleet command → body | Siri reply |
|---|---|---|
| `/car/trunk_open` | `actuate_trunk {"which_trunk":"rear"}` (proximity check) | Trunk opened |
| `/car/frunk_open` | `actuate_trunk {"which_trunk":"front"}` (proximity check) | Front trunk opened |
| `/car/trunk_close` | `actuate_trunk {"which_trunk":"rear"}`, **only if the rear trunk is open** (see below) | Trunk closing / Trunk is already closed |
| `/car/climate_on` | `auto_conditioning_start` | Climate on. Cabin is 14 degrees, target 21 (temperatures from telemetry) |
| `/car/climate_off` | `auto_conditioning_stop` | Climate off |
| `/car/lock`, `/car/unlock` | `door_lock`, `door_unlock` | Car locked / Car unlocked |
| `/car/charge_port_open`, `/car/charge_port_close` | `charge_port_door_open` (proximity check), `charge_port_door_close` | Charge port opened / closed |
| `/car/charge_start`, `/car/charge_stop` | `charge_start`, `charge_stop` | Charging started / stopped |
| `/car/defrost_on`, `/car/defrost_off` | `set_preconditioning_max {"on":true/false,"manual_override":false}` | Max defrost on. Windows are defrosting / Defrost off |
| `/car/seat_heat_driver`, `/car/seat_heat_off` | `remote_seat_heater_request {"heater":0,"seat_position":0,"level":3 / 0}` | Driver seat heater on high / Seat heater off |
| `/car/honk`, `/car/flash` | `honk_horn`, `flash_lights` | Honked the horn / Lights flashed |
| `/car/set_temp` + JSON `{"temp":21}` (or `?temp=21`) | `set_temps {"driver_temp":t,"passenger_temp":t}`, 15–28 °C, rounded to 0.5 | Temperature set to 21 degrees (no/invalid temp: "Tell me a temperature, for example 21"; out of range: "Temperature must be between 15 and 28 degrees") |
| `/car/status` (GET or POST), optional phone `lat`/`lon` | `GET vehicles/{vin}`; if online, `vehicle_data?endpoints=charge_state;climate_state;vehicle_state`. Distance part: telemetry DB only | SOC, range in km, lock, climate, inside/outside temperature, charging; with lat/lon also "The car is 140 meters away, to the west." |
| `/car/distance` (GET or POST) + phone `lat`/`lon` | **none**: telemetry DB only, never wakes. **Legacy alias**, prefer status + lat/lon | The car is 140 meters away, to the north-east. It's locked |
| `/car/car_location` (GET or POST) | **none**: telemetry DB only, never wakes, no phone location needed | The car is at <STREET_ADDRESS>, <CITY> |

`status` **never wakes the car**. It optionally takes the phone `lat`/`lon` and then also says where the car is (see "status + phone location" below). If the car is asleep or offline, it answers e.g. "The car is asleep or offline. Last data at 7:40 PM: battery 50 percent, range 230 kilometers. Locked. Climate off. Inside 15 degrees, outside 12 degrees. Charging complete." (older data: "Last data on October 15 at …") using `v_latest` (BatteryLevel, RatedRange in miles → km, Locked, HvacPower, In/OutsideTemp, DetailedChargeState).
Note on seat heat: the vehicle-command proxy (v0.4.1, `pkg/proxy/command.go`) reads `seat_position` (0 = front left = driver on a LHD car) and `level` (0–3). The Fleet REST docs call the seat parameter `heater`, so the service sends both.

### Proximity check (trunk_open, frunk_open, charge_port_open)
These actions run only when the phone is near the car. Code: `Proximity` class in `shortcut/app.py`.
* **Phone location** in the request: JSON body `{"lat": <LAT>, "lon": <LON>, "accuracy": 8}` or query params `?lat=&lon=&accuracy=` (fallback).
  Numbers or numeric strings are accepted, including comma decimals (`"12,34"`, iOS locale formatting), spaces/NBSP and a trailing `m`. Aliases: `latitude`, `longitude`/`lng`, `acc`.
  * Missing/invalid lat/lon → "Location required for this command".
  * `accuracy` > `PROXIMITY_MAX_ACCURACY_M` (or negative) → "Your location isn't precise enough. Try again outside".
    `accuracy` is **optional**, because the Shortcuts Location variable does not expose horizontal accuracy. If it is absent, the accuracy check is skipped. Set `PROXIMITY_REQUIRE_ACCURACY=1` to refuse instead.
* **Car location.** Cheapest/most reliable source first:
  1. Telemetry DB (`telemetry_raw`, field `Location`). Trusted if **fresh** (≤ `PROXIMITY_FRESH_S` = 120 s old), **or streaming** (telemetry is CONNECTED and that Location arrived after the current connect; the car sends all fields on connect and Location on every 5 m change), **or parked** (latest Gear = P, the Location is newer than the last non-P gear (= last drive), and Odometer grew < 0.15 mi since that Location).
  2. Otherwise (real commands only, after wake): wait up to `PROXIMITY_TELEMETRY_WAIT_S` (4 s) for the reconnect snapshot, then `GET vehicle_data?endpoints=location_data`. Highland returns no GPS unless `location_data` is requested. Needs the `vehicle_location` scope, which the token has.
  3. Nothing → "Couldn't get the car's location. Command blocked".
  * If the DB location is trusted, it is checked **before** waking. A far-away request is refused without waking the car or calling Tesla. An allowed request wakes the car and then re-reads the DB once in case a fresher Location arrived.
  * Residual risk: "parked" assumes the telemetry pipeline didn't miss a drive. The car buffers and resends un-acked data, and every reconnect resends all fields, so this would need the server to be down while the car drove *and* no reconnect since.
* **Decision:** haversine distance > `PROXIMITY_MAX_M` (8) → "You're 18 meters from the car. Command blocked" (≥ 1 km: "You're 2.3 kilometers …").
* **Config** (`docker-compose.yml`, shortcut env): `PROXIMITY_ACTIONS` (default `trunk_open,frunk_open,charge_port_open`, comma list, any action incl. `trunk_close`), `PROXIMITY_MAX_M=8`, `PROXIMITY_MAX_ACCURACY_M=50`, `PROXIMITY_REQUIRE_ACCURACY=0`, `PROXIMITY_FRESH_S=120`, `PROXIMITY_TELEMETRY_WAIT_S=4`. Apply with `docker compose up -d --no-deps shortcut`.
* **Dry run** runs the full check with the DB car location (no wake, no vehicle_data). It answers e.g. "Test only: you're 0 meters from the car, would send actuate_trunk" or "Test only, blocked: You're 1 kilometer from the car. Command blocked", plus a `proximity` object (decision, reason, distance_m, accuracy_m, car_rule, car_age_s, check_ms).
* **Log:** one row per decision in table `proximity_checks` (`db/init/03-proximity.sql`): ts, action, dry_run, decision, reason, distance_m, accuracy_m, car_source/car_rule/car_age_s, phone/car coordinates rounded to 4 decimals (~10 m), check_ms. The container log shows only distance/accuracy/decision.
  `SELECT ts, action, dry_run, decision, reason, distance_m, accuracy_m, car_rule, check_ms FROM proximity_checks ORDER BY id DESC LIMIT 20;`
* **Added latency** (measured 2026-10-17): ~55–65 ms per DB lookup (new DB connection + one query). An allowed real command does 2 lookups (~18 ms). A denied one costs ~60 ms and no wake. Only when the DB location is stale: up to +4 s snapshot wait, then vehicle_data (~0.5–1.5 s).

### status + phone location (where is the car from here?)
**`/car/status` is the main endpoint** for "how's the car and where is it". Send the phone location along and status appends how far the car is and in which direction.
Code: `do_status()` + `distance_part()` in `shortcut/app.py`.
* **Without lat/lon** status behaves exactly as before (no `distance` key, nothing logged to `proximity_checks`).
* **With lat/lon** (GET `?lat=&lon=` or POST JSON `{"lat":…,"lon":…}`), the distance sentence is appended to the normal status message, and the JSON gets a `distance` object. The lock state is **not** repeated (status already says Locked/Unlocked). Examples:
  "The car is asleep. Last data at 7:40 PM: battery 50 percent, range 230 kilometers. Locked. Climate off. Inside 15 degrees, outside 12 degrees. Charging complete. The car is 140 meters away, to the west."
  / "… Charging complete. You're right next to the car, 7 meters."
  Dry run: "Test only: would check status without waking the car. The car is 140 meters away, to the west." (the distance part is computed for real in dry run too; it is DB only).
  No car location in the DB → "… Couldn't get the car's location." and `distance: null`. Invalid lat/lon counts as absent.
* The distance part reads the car position **only from the telemetry DB**, never wakes the car and makes no Tesla call. status as a whole still **never wakes the car**.
* `distance` object: {distance_m, bearing_deg, direction, accuracy_m, car_rule, car_age_s, car_trusted, car_as_of, check_ms, tesla_api_calls: 0} (`tesla_api_calls` counts the distance part only). The top-level `car_*` fields are returned as before.
* Log: one `proximity_checks` row with `action='status'`, `decision='info'`, reason `distance` / `car_location_unavailable`.
* **iOS Shortcut "Car status"/"Where's my car":** Get Current Location → Get Contents of URL `https://example.com/car/status`, Method POST, header `Authorization: Bearer <token>`, JSON body `lat`/`lon` (Number) from the location → Get Dictionary Value `message` → Speak Text.

#### `/car/distance` (legacy alias, kept for old Shortcuts)
Same distance sentence, but without the status part and **with** the lock state at the end. New Shortcuts should call status with lat/lon instead. Code: `do_distance()`.
The rules below (input parsing, car location, rounding, direction) apply to the distance part of status as well.
* **Input:** the phone location, parsed exactly like the proximity check (JSON body `{"lat":…,"lon":…}` or `?lat=&lon=`, comma decimals, aliases). `accuracy` is optional and only logged; it is never refused for imprecision.
  Missing/invalid lat/lon → "Location required for this command".
* **Car location:** only the latest telemetry `Location` from the DB (`car_location_db()`, same fresh/streaming/parked trust rules). **No Tesla API call at all, never wakes the car**, no command lock, not subject to proximity blocking.
  If the location is not trusted (rule `stale`), it still answers from the last known location and appends its age: "…, based on location from 2 hours ago". No location in the DB → "Couldn't get the car's location".
* **Reply:** distance (< 100 m exact, then rounded to 10 m, ≥ 1 km as "2.3 kilometers") plus the 8-point compass direction **from the phone to the car** (initial great-circle bearing: north, north-east, east, … north-west).
  Under 10 m: "You're right next to the car, 8 meters". Then the last telemetry `Locked` value: "It's locked" / "It's unlocked".
  Examples: "The car is 140 meters away, to the north-east. It's locked." / "The car is 2.3 kilometers away, to the south, based on location from 2 hours ago. It's locked."
  JSON also has `distance` {distance_m, bearing_deg, direction, accuracy_m, car_rule, car_age_s, car_trusted, car_as_of, locked, check_ms, tesla_api_calls: 0}. `dry_run` makes no difference (it never calls Tesla anyway).
* **Log:** one row in `proximity_checks` with `action='distance'`, `decision='info'`, reason `distance` / `no_phone_location` / `car_location_unavailable`, `max_m` NULL, coordinates rounded to 4 dp.
  Nothing goes to `api_calls`, because no Tesla API call is made (that table logs Tesla calls only).
* **Cost:** ~2 DB lookups (location, lock state), ~110–190 ms end to end.
* Old Shortcuts that POST to `/car/distance` keep working; to migrate, just change the URL to `/car/status`.

### Car location fields (parked car in Apple Maps) and `car_location`
`distance`, `status` and `car_location` all add these **top-level** fields (car position = latest telemetry `Location` from the DB via `car_location_db()`; never wakes the car, no Tesla call for this part):
* `car_lat`, `car_lon` (numbers, 6 decimals), `car_coords` (text `"<LAT>,<LON>"`),
* `car_address` (short street address, e.g. `"<STREET_ADDRESS>, <CITY>"`; **omitted** when geocoding fails),
* `car_maps_url` = `https://maps.apple.com/?ll=<lat>,<lon>&q=<CAR_NAME>` (label from env `CAR_MAPS_LABEL`), `car_location_url` = same without `q` (cleanest input for the Shortcuts Location conversion),
* `car_as_of`, `car_age_s`, `car_trusted` (same trust rules as distance; untrusted = possibly stale).
`distance` returns them even when the phone location is missing (then `ok:false`, "Location required…"). `status` returns them in both the live and the asleep path (and in dry run).
`/car/car_location` returns only these (+ `car_rule`, `check_ms`, `tesla_api_calls: 0`) with message "The car is at <address>." (no address → coordinates; stale → ", based on location from 2 hours ago").
* **Reverse geocoding:** Nominatim/OpenStreetMap (`GEOCODER_URL`), User-Agent `tesla-shortcut/1.0 (+https://example.com; personal use)`, timeout 2 s (`GEOCODER_TIMEOUT_S`), at most 1 live lookup/s (policy).
  Cache key = coordinates rounded to 4 dp (~11 m): good answers 30 days in memory + `data/geocode_cache.json` (survives restarts, max 2000), failures 5 min in memory only. Cache hit ≈ 0 ms, miss ≈ 150–300 ms, worst case +2 s once per 5 min.
* **iOS Shortcut "Mark parked car":** Get Contents of URL `https://example.com/car/car_location` (GET, header `Authorization: Bearer <token>`) → Get Dictionary Value `car_location_url` → URL (the value) → Location (tap the location field, pick the URL variable) → Set Parked Car Location (Location = output of Location). Text addresses also convert but are geocoded by Apple (less exact), so prefer the URL.

### trunk_close
`actuate_trunk rear` **toggles** a Model 3 power liftgate, so it's sent only when the rear trunk is confirmed open:
* Before wake: telemetry `DoorState.TrunkRear == false` → "Trunk is already closed" (no wake, nothing sent). The trunk can't open without the car waking and streaming the change.
* After wake: the open state must be current, i.e. DoorState ≤ 120 s old or received after the current telemetry connect (4 s wait for the snapshot). Otherwise `vehicle_data?endpoints=vehicle_state` (`rt` ≠ 0 = open). Closed → "Trunk is already closed". Unknown → "Couldn't check whether the trunk is open. Command not sent". Open → send → "Trunk closing".
* No proximity check by default (closing is safe). Add `trunk_close` to `PROXIMITY_ACTIONS` to require it.

**iOS Shortcut:** use the **Get Contents of URL** action. Set the URL to `https://example.com/car/trunk_open`, Method POST, and add the header `Authorization` = `Bearer <token>`.
For set_temp, set Request Body = JSON with `temp` (Number), or pass `?temp=21`. For trunk_open / frunk_open / charge_port_open, first add **Get Current Location**. Then set Request Body = JSON with `lat` (Number) = Current Location › Latitude and `lon` (Number) = Current Location › Longitude. Shortcuts has no accuracy property, so omit `accuracy`. Turn on Settings › Privacy & Security › Location Services › Shortcuts › Precise Location.
Then add **Get Dictionary Value** `message` → **Speak Text**. Name the shortcut after the Siri phrase, e.g. "Open the trunk". Dry runs answer "Test only: would send <command>".
Test without touching the car: `curl -X POST -H "Authorization: Bearer $SHORTCUT_TOKEN" "https://example.com/car/trunk_open?dry_run=1"`

## Database
Connect with `docker compose -f /opt/tesla/docker-compose.yml exec db psql -U tesla tesla`, or use 127.0.0.1:5432 through an SSH tunnel.

Tables:
* `telemetry_raw(vin, ts, field, value_type, value_num, value_text, value_json, is_resend, received_at)`
  * Hypertable, PK (vin, field, ts). `ts` is the vehicle timestamp.
  * Numbers and booleans (1/0) go in value_num. Enums and strings go in value_text. Location and DoorState go in value_json.
  * Compressed after 30 days.
* `wake_events(vin, ts, connection_id, status CONNECTED|DISCONNECTED, network_interface)`: fleet-telemetry connectivity events.
* `telemetry_alerts`, `telemetry_errors`: vehicle alerts, and errors the vehicle reports (e.g. unsupported_field).
* `api_calls(ts, vin, method, endpoint, command, http_status, duration_ms, may_wake, source)`
* `proximity_checks(ts, action, dry_run, decision, reason, distance_m, accuracy_m, car_source, car_rule, car_age_s, phone_/car_lat/lon (4 dp), check_ms)`: shortcut proximity decisions, plus distance lookups from `/car/status` with lat/lon and `/car/distance` (`decision='info'`)

Views: `v_latest` (latest value per field), `v_location` (lat/lon track), `v_minute` (1-minute wide table with SOC, range,
odometer, max speed, pack V/A, AC/DC kW, temperatures, charge state, gear), `v_ingest_24h`, and `wake_summary`.

Examples:
```sql
SELECT field, value_num, value_text, value_json, ts FROM v_latest ORDER BY field;
SELECT * FROM v_minute WHERE minute > now() - interval '1 day' ORDER BY minute;
SELECT ts, lat, lon FROM v_location WHERE ts > now() - interval '2 hours' ORDER BY ts;
SELECT time_bucket('1 hour', ts) h, max(value_num) FROM telemetry_raw WHERE field='DCChargingPower' GROUP BY h ORDER BY h;
```

## Wake log ("why does the car wake up?")
Tesla does not expose a wake reason. This setup approximates it:
1. **Connected/disconnected events.** When the vehicle connects to or disconnects from the telemetry server, a row goes into `wake_events`. Tesla describes connectivity as matching online state ~99% of the time.
2. **Context.** On every (re)connect the vehicle sends the current value of all configured fields. `wake_summary` takes the first value of each
   context field in [wake − 5 s, wake + 90 s]. The fields are listed in `wake_context_fields()`:
   * Locked, DoorState, windows, SentryMode
   * charge state, port and cable fields; scheduled charging and preconditioning fields
   * HvacPower, climate keeper, cabin overheat protection, defrost; BatteryHeaterOn, BMSState, DCDCEnable
   * software update fields
   * Location, LocatedAtHome, Gear, VehicleSpeed
   * DriverSeatOccupied/Belt, PairedPhoneKeyAndKeyFobQty, GuestMode, Valet, CenterDisplay, RemoteStartActive, ServiceMode, HomelinkNearby, MediaPlaybackStatus
3. **Our own calls.** Calls from `api_calls` with `may_wake` (wake_up, any command, and the telemetry-config POST) within [wake − 3 min, wake + 30 s] are attached as `our_calls`.
4. **Reason guess.** `reason_guess` is assigned in this priority order:
   1. `our_api_call`
   2. `driving`
   3. `software_update`
   4. `charging_or_schedule`
   5. `sentry_event` (Aware/Panic)
   6. `door_or_key_activity` (unlocked / door open / driver seat occupied)
   7. `sentry_armed`
   8. `climate`
   9. `unknown` / `unknown_no_context`

   Wakes caused by the owner's phone app, a key approach, or the 12 V battery top-up will usually show as `door_or_key_activity` or `unknown`.
```sql
SELECT wake_local, asleep_for, awake_for, reason_guess, our_calls, locked, sentry, charge_state, hvac, at_home
FROM wake_summary LIMIT 50;
SELECT reason_guess, count(*) FROM wake_summary WHERE wake_ts > now() - interval '30 days' GROUP BY 1;
SELECT context FROM wake_summary WHERE reason_guess LIKE 'unknown%' LIMIT 5;  -- inspect raw context
```

## Files
* `docker-compose.yml`
* `caddy/` (Dockerfile, Caddyfile)
* `proxy/` (self-signed TLS for the local proxy)
* `keys/` (app key pair)
* `telemetry/` (config.json, fields.json, ca-chain.pem, ca/, certs/)
* `consumer/`
* `shortcut/` (iOS Shortcuts endpoint: app.py, Dockerfile)
* `db/init/` (01-schema.sql, 02-wakelog.sql, 03-proximity.sql; idempotent; to re-apply: `docker compose exec -T db psql -U tesla -d tesla < db/init/02-wakelog.sql`)
* `bin/` (tesla, configure_telemetry, telemetry_cert_sync, refresh_token)
* `data/` (tokens.json, api_calls.log, shortcut_token.txt; 0700)
* Secrets: `secrets.env`, `db.env`, `consumer.env` (0600). Never print them.

## Operations
* Status: `docker compose ps`; `docker compose logs --tail 50 telemetry consumer`
* Data flowing? `SELECT * FROM v_ingest_24h;`
* Telemetry: `tesla telemetry-config | jq .response.synced`, `tesla telemetry-errors`
* Reliability: Kafka keeps messages for 7 days. The consumer commits offsets only after the DB commit and exits on error (Docker restarts it), so nothing is lost and duplicates are dropped by PK.
  fleet-telemetry acks the vehicle only after Kafka has accepted the data (`reliable_ack_sources.V=kafka`), and the vehicle resends un-acked data (`delivery_policy: latest`). The car buffers ~5000 messages while it is offline.
* Logs: proxy is not verbose (it would log request bodies). fleet-telemetry runs at `info` (`debug` would log payloads).
