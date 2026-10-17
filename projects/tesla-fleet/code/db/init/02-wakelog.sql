-- Wake log: connectivity events + our own API calls + heuristic reason view. Idempotent.
-- Local times use the DB TimeZone setting (e.g. ALTER DATABASE tesla SET timezone = '<Area/City>').
DO $$ BEGIN
  IF to_regclass('public.telemetry_connectivity') IS NOT NULL AND to_regclass('public.wake_events') IS NULL THEN
    ALTER TABLE telemetry_connectivity RENAME TO wake_events;
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS wake_events (
  vin               text        NOT NULL,
  ts                timestamptz NOT NULL,   -- server-side createdAt of the connectivity event
  connection_id     text        NOT NULL,
  status            text        NOT NULL,   -- CONNECTED (= awake) / DISCONNECTED (= asleep/offline)
  network_interface text,                   -- e.g. wifi / cellular
  received_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (vin, ts, connection_id, status)
);

-- Every Fleet API call made through /opt/tesla/bin/tesla (no tokens stored)
CREATE TABLE IF NOT EXISTS api_calls (
  id          bigserial PRIMARY KEY,
  ts          timestamptz NOT NULL DEFAULT now(),
  vin         text,
  method      text NOT NULL,
  endpoint    text NOT NULL,          -- path with VIN replaced by {vin}
  command     text,                   -- e.g. wake_up, honk_horn, vehicle_data
  http_status int,
  duration_ms int,
  may_wake    boolean NOT NULL DEFAULT false,  -- wake_up and vehicle commands
  source      text                    -- caller (script name / user)
);
CREATE INDEX IF NOT EXISTS api_calls_vin_ts ON api_calls (vin, ts);

-- Fields used as wake context (first value seen in [wake-5s, wake+90s])
CREATE OR REPLACE FUNCTION wake_context_fields() RETURNS text[] LANGUAGE sql IMMUTABLE AS $$
  SELECT ARRAY['Locked','DoorState','FdWindow','FpWindow','RdWindow','RpWindow','SentryMode',
    'DetailedChargeState','ChargeState','ChargePortDoorOpen','ChargePortLatch','ChargingCableType','FastChargerPresent',
    'ScheduledChargingPending','ScheduledChargingStartTime','ScheduledChargingMode','ScheduledDepartureTime','PreconditioningEnabled',
    'HvacPower','HvacACEnabled','ClimateKeeperMode','CabinOverheatProtectionMode','DefrostForPreconditioning','DefrostMode',
    'BatteryHeaterOn','BMSState','DCDCEnable',
    'SoftwareUpdateDownloadPercentComplete','SoftwareUpdateInstallationPercentComplete','SoftwareUpdateVersion',
    'SoftwareUpdateInProgress','SoftwareUpdateAvailable','SoftwareUpdateScheduledStartTime',
    'Location','LocatedAtHome','Gear','VehicleSpeed','DriverSeatOccupied','DriverSeatBelt','PairedPhoneKeyAndKeyFobQty',
    'GuestModeEnabled','GuestModeMobileAccessState','ValetModeEnabled','CenterDisplay','RemoteStartActive','ServiceMode',
    'HomelinkNearby','MediaPlaybackStatus','Soc']::text[]
$$;

DROP VIEW IF EXISTS wake_summary;
CREATE VIEW wake_summary AS
WITH w AS (
  SELECT e.vin, e.ts AS wake_ts, e.connection_id, e.network_interface,
    (SELECT max(d.ts) FROM wake_events d WHERE d.vin = e.vin AND d.status = 'DISCONNECTED' AND d.ts <= e.ts) AS prev_disconnect_ts,
    (SELECT min(d.ts) FROM wake_events d WHERE d.vin = e.vin AND d.status = 'DISCONNECTED' AND d.ts > e.ts)  AS sleep_ts
  FROM wake_events e WHERE e.status = 'CONNECTED'
), c AS (
  SELECT w.*,
    (SELECT jsonb_object_agg(s.field, s.val) FROM (
       SELECT DISTINCT ON (r.field) r.field,
              COALESCE(r.value_json, to_jsonb(COALESCE(r.value_text, r.value_num::text))) AS val
       FROM telemetry_raw r
       WHERE r.vin = w.vin AND r.ts >= w.wake_ts - interval '5 seconds' AND r.ts < w.wake_ts + interval '90 seconds'
         AND r.field = ANY (wake_context_fields())
       ORDER BY r.field, r.ts) s) AS context,
    (SELECT string_agg(a.method || ' ' || a.endpoint || ' @' || to_char(a.ts AT TIME ZONE current_setting('TimeZone'), 'HH24:MI:SS'), ', ' ORDER BY a.ts)
       FROM api_calls a WHERE a.vin = w.vin AND a.may_wake
        AND a.ts BETWEEN w.wake_ts - interval '3 minutes' AND w.wake_ts + interval '30 seconds') AS our_calls
  FROM w
)
SELECT vin, wake_ts, wake_ts AT TIME ZONE current_setting('TimeZone') AS wake_local, network_interface,
  wake_ts - prev_disconnect_ts AS asleep_for,
  sleep_ts - wake_ts AS awake_for,
  CASE
    WHEN our_calls IS NOT NULL THEN 'our_api_call'
    WHEN context->>'Gear' IN ('ShiftStateD','ShiftStateR','ShiftStateN')
      OR (context->>'VehicleSpeed') ~ '^[0-9.]+$' AND (context->>'VehicleSpeed')::float > 0 THEN 'driving'
    WHEN context->>'SoftwareUpdateInProgress' = 'true'
      OR (COALESCE(context->>'SoftwareUpdateVersion','') NOT IN ('','null') AND (
           ((context->>'SoftwareUpdateDownloadPercentComplete') ~ '^[0-9.]+$' AND (context->>'SoftwareUpdateDownloadPercentComplete')::float BETWEEN 1 AND 99)
        OR ((context->>'SoftwareUpdateInstallationPercentComplete') ~ '^[0-9.]+$' AND (context->>'SoftwareUpdateInstallationPercentComplete')::float BETWEEN 2 AND 99))) THEN 'software_update'
    WHEN context->>'DetailedChargeState' IN ('DetailedChargeStateStarting','DetailedChargeStateCharging')
      OR context->>'ScheduledChargingPending' = 'true' AND context->>'DetailedChargeState' <> 'DetailedChargeStateDisconnected'
      OR context->>'BatteryHeaterOn' = 'true' THEN 'charging_or_schedule'
    WHEN context->>'SentryMode' IN ('SentryModeStateAware','SentryModeStatePanic') THEN 'sentry_event'
    WHEN context->>'Locked' = 'false' OR context->>'DriverSeatOccupied' = 'true'
      OR EXISTS (SELECT 1 FROM jsonb_each(CASE WHEN jsonb_typeof(context->'DoorState') = 'object' THEN context->'DoorState' ELSE '{}'::jsonb END) d WHERE d.value = 'true'::jsonb)
      OR context->>'CenterDisplay' IN ('DisplayStateOn','DisplayStateCharging','DisplayStateSentry','DisplayStateDog','DisplayStateEntertainment') AND context->>'Locked' = 'false'
      THEN 'door_or_key_activity'
    WHEN context->>'SentryMode' IN ('SentryModeStateArmed','SentryModeStateIdle','SentryModeStateQuiet') THEN 'sentry_armed'
    WHEN context->>'HvacPower' IN ('HvacPowerStateOn','HvacPowerStatePrecondition','HvacPowerStateOverheatProtect')
      OR context->>'ClimateKeeperMode' IN ('ClimateKeeperModeStateOn','ClimateKeeperModeStateDog','ClimateKeeperModeStateParty')
      OR context->>'DefrostForPreconditioning' = 'true' THEN 'climate'
    WHEN context IS NULL THEN 'unknown_no_context'
    ELSE 'unknown'
  END AS reason_guess,
  our_calls,
  context->>'Locked' AS locked,
  context->>'SentryMode' AS sentry,
  context->>'DetailedChargeState' AS charge_state,
  context->>'ChargingCableType' AS cable,
  context->>'HvacPower' AS hvac,
  context->>'Gear' AS gear,
  context->>'LocatedAtHome' AS at_home,
  (context->'Location'->>'latitude')::double precision AS lat,
  (context->'Location'->>'longitude')::double precision AS lon,
  context
FROM c ORDER BY wake_ts DESC;
