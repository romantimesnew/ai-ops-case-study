# Sanitization notes

This is a sanitized copy of a personal Tesla Fleet API / Fleet Telemetry deployment, published as a portfolio case study.
It is not a drop-in deployment: fill in the placeholders and create the secret files first (see `secrets.env.example`).

## Not included
- `secrets.env`, `db.env`, `consumer.env` and any other `.env` files (OAuth client ID/secret, auth start token, Shortcuts token, DB credentials)
- `data/` (OAuth tokens, API call logs, Shortcuts token copy, reverse-geocode cache)
- `keys/` (Fleet API app key pair), `proxy/` TLS key/cert, `telemetry/certs/`, `telemetry/ca*`, `site/.well-known/` public key, every `*.pem` / `*.key`
- Kafka, TimescaleDB and Caddy Docker volumes
- `*.bak-*` backup copies and `site/index.html`

## Replaced
| Original | Replacement |
|---|---|
| Personal domain and its subdomains | `example.com`, `www.example.com`, `telemetry.example.com` |
| Server IPv4 / IPv6 | `203.0.113.10` / `2001:db8::10` (documentation ranges; none were in the copied files) |
| Vehicle VIN / vehicle id | `${TESLA_VIN}` (Compose `.env`) or `<VIN>` in script defaults / `<VEHICLE_ID>` |
| Car display name | `<CAR_NAME>` |
| Domain-derived Docker image and HTTP server names | `tesla-*` |
| Kafka KRaft cluster ID | `${KAFKA_CLUSTER_ID}` (generate one with `kafka-storage.sh random-uuid`) |
| Real car coordinates and street address in examples | `<LAT>,<LON>`, `<STREET_ADDRESS>, <CITY>`. Example phone coordinates were replaced with dummy values |
| Hard-coded secret/token file paths in `bin/*` | env vars with defaults (`TESLA_HOME`, `SECRETS_FILE`, `TOKENS_FILE`, `API_LOG`, `TELEMETRY_DIR`, `TESLA_CLI`, `TESLA_REFRESH_CMD`, `TELEMETRY_HOSTNAME`) |
| `cat` of the token file in a README curl example | `$SHORTCUT_TOKEN` |
| Hosting provider name in the ops notes | "small cloud VPS" / "cloud firewall" |
| Hard-coded local time zone (`shortcut/app.py`, `db/init/02-wakelog.sql`) | `LOCAL_TZ` env (default `UTC`) and the DB `TimeZone` setting |

We also checked for the Fleet app name, the server hostname, email addresses, tokens, passwords and API keys. None of them appeared in the copied files, because the code reads secrets only from the excluded env files.

## Kept on purpose
- `127.0.0.1` / `0.0.0.0` bind addresses (loopback and wildcard, so they identify nothing), public Tesla / Let's Encrypt / OpenStreetMap endpoints, the `ru-RU` locale and the Russian message strings.
