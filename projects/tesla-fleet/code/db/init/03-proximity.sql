-- Proximity decisions of the shortcut service (trunk/frunk/charge port need the phone near the car).
-- Coordinates rounded to 4 decimals (~10 m). Idempotent.
CREATE TABLE IF NOT EXISTS proximity_checks (
  id          bigserial PRIMARY KEY,
  ts          timestamptz NOT NULL DEFAULT now(),
  vin         text,
  action      text NOT NULL,
  dry_run     boolean NOT NULL DEFAULT false,
  decision    text NOT NULL,          -- allow | deny | info (/car/distance)
  reason      text,                   -- near | too_far | no_phone_location | accuracy | accuracy_missing | car_location_unavailable | car_not_responding | distance
  distance_m  integer,
  accuracy_m  real,                   -- phone horizontal accuracy (NULL = not sent)
  max_m       integer,
  car_source  text,                   -- telemetry | vehicle_data
  car_rule    text,                   -- fresh | streaming | parked | stale | vehicle_data
  car_age_s   integer,
  phone_lat   numeric(8,4), phone_lon numeric(8,4),
  car_lat     numeric(8,4), car_lon   numeric(8,4),
  check_ms    integer                 -- time spent in the check itself (DB queries / vehicle_data / waits)
);
CREATE INDEX IF NOT EXISTS proximity_checks_ts ON proximity_checks (ts);
