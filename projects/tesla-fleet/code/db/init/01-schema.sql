-- Tesla Fleet Telemetry storage (TimescaleDB). Idempotent.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- One row per (vin, field, vehicle timestamp). Raw, typed-ish.
CREATE TABLE IF NOT EXISTS telemetry_raw (
  vin         text        NOT NULL,
  ts          timestamptz NOT NULL,           -- vehicle createdAt of the payload
  field       text        NOT NULL,           -- vehicle_data.proto Field name, e.g. VehicleSpeed
  value_type  text,                           -- protojson oneof key, e.g. doubleValue, locationValue, invalid
  value_num   double precision,               -- numeric / boolean(0/1) representation when possible
  value_text  text,                           -- string / enum representation
  value_json  jsonb,                          -- structured values (Location, DoorState, ...)
  is_resend   boolean     NOT NULL DEFAULT false,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (vin, field, ts)
);
SELECT create_hypertable('telemetry_raw', by_range('ts', INTERVAL '7 days'), if_not_exists => TRUE);
ALTER TABLE telemetry_raw SET (timescaledb.compress,
  timescaledb.compress_segmentby = 'vin, field', timescaledb.compress_orderby = 'ts DESC');
SELECT add_compression_policy('telemetry_raw', INTERVAL '30 days', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS wake_events (
  vin               text        NOT NULL,
  ts                timestamptz NOT NULL,
  connection_id     text        NOT NULL,
  status            text        NOT NULL,
  network_interface text,
  received_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (vin, ts, connection_id, status)
);

CREATE TABLE IF NOT EXISTS telemetry_alerts (
  vin         text        NOT NULL,
  name        text        NOT NULL,
  started_at  timestamptz NOT NULL,
  ended_at    timestamptz,
  audiences   jsonb,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (vin, name, started_at)
);

CREATE TABLE IF NOT EXISTS telemetry_errors (
  id          bigserial PRIMARY KEY,
  vin         text,
  ts          timestamptz,
  name        text,
  body        text,
  tags        jsonb,
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (vin, ts, name)
);

-- Latest value per field
CREATE OR REPLACE VIEW v_latest AS
SELECT DISTINCT ON (vin, field) vin, field, ts, value_num, value_text, value_json, value_type
FROM telemetry_raw ORDER BY vin, field, ts DESC;

-- GPS track
CREATE OR REPLACE VIEW v_location AS
SELECT vin, ts, (value_json->>'latitude')::double precision AS lat,
       (value_json->>'longitude')::double precision AS lon
FROM telemetry_raw WHERE field = 'Location' AND value_json ? 'latitude';

-- 1-minute wide view of common numeric signals (last value in the minute)
CREATE OR REPLACE VIEW v_minute AS
SELECT vin, time_bucket('1 minute', ts) AS minute,
  last(value_num, ts) FILTER (WHERE field = 'Soc')               AS soc,
  last(value_num, ts) FILTER (WHERE field = 'BatteryLevel')      AS battery_level,
  last(value_num, ts) FILTER (WHERE field = 'EstBatteryRange')   AS est_range_mi,
  last(value_num, ts) FILTER (WHERE field = 'RatedRange')        AS rated_range_mi,
  last(value_num, ts) FILTER (WHERE field = 'EnergyRemaining')   AS energy_remaining_kwh,
  last(value_num, ts) FILTER (WHERE field = 'Odometer')          AS odometer_mi,
  max(value_num)      FILTER (WHERE field = 'VehicleSpeed')      AS max_speed,
  last(value_num, ts) FILTER (WHERE field = 'PackVoltage')       AS pack_v,
  last(value_num, ts) FILTER (WHERE field = 'PackCurrent')       AS pack_a,
  last(value_num, ts) FILTER (WHERE field = 'ACChargingPower')   AS ac_kw,
  last(value_num, ts) FILTER (WHERE field = 'DCChargingPower')   AS dc_kw,
  last(value_num, ts) FILTER (WHERE field = 'InsideTemp')        AS inside_c,
  last(value_num, ts) FILTER (WHERE field = 'OutsideTemp')       AS outside_c,
  last(value_text, ts) FILTER (WHERE field = 'DetailedChargeState') AS charge_state,
  last(value_text, ts) FILTER (WHERE field = 'Gear')             AS gear
FROM telemetry_raw GROUP BY vin, minute;

-- Ingest stats
CREATE OR REPLACE VIEW v_ingest_24h AS
SELECT field, count(*) AS rows, max(ts) AS last_ts
FROM telemetry_raw WHERE received_at > now() - interval '24 hours'
GROUP BY field ORDER BY rows DESC;
