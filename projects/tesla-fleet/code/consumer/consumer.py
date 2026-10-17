"""Kafka (fleet-telemetry, transmit_decoded_records=true) -> TimescaleDB.

At-least-once: offsets are committed only after the DB transaction commits.
Duplicates are dropped by primary keys (ON CONFLICT DO NOTHING).
On any error the process exits non-zero; Docker restarts it and Kafka
re-delivers uncommitted messages. Only VINs in ALLOWED_VINS are stored.
Payload contents are never logged.
"""
import json, logging, os, signal, sys, time
from confluent_kafka import Consumer, KafkaError
import psycopg
from psycopg.types.json import Jsonb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consumer")

NS = os.environ.get("NAMESPACE", "tesla")
TOPICS = {f"{NS}_V": "V", f"{NS}_connectivity": "connectivity",
          f"{NS}_alerts": "alerts", f"{NS}_errors": "errors"}
ALLOWED = {v.strip() for v in os.environ.get("ALLOWED_VINS", "").split(",") if v.strip()}
DSN = os.environ["DATABASE_URL"]

running = True
def stop(*_):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def decode_value(v):
    """protojson Value (oneof) -> (type, num, text, json)."""
    if not isinstance(v, dict) or not v:
        return None, None, None, None
    k, x = next(iter(v.items()))
    if k == "invalid":
        return "invalid", None, None, None
    if isinstance(x, bool):
        return k, 1.0 if x else 0.0, "true" if x else "false", None
    if isinstance(x, (int, float)):
        return k, float(x), None, None
    if isinstance(x, str):
        try:
            return k, float(x), x, None          # int64 values arrive as strings; numeric strings
        except ValueError:
            return k, None, x, None               # enums / text
    if isinstance(x, (dict, list)):
        return k, None, None, Jsonb(x)
    return k, None, str(x), None


def rows_for(kind, p):
    vin = p.get("vin")
    if ALLOWED and vin not in ALLOWED:
        return kind, []
    if kind == "V":
        ts = p.get("createdAt")
        resend = bool(p.get("isResend", False))
        out = []
        for d in p.get("data", []):
            t, n, s, j = decode_value(d.get("value"))
            out.append((vin, ts, d.get("key"), t, n, s, j, resend))
        return kind, out
    if kind == "connectivity":
        return kind, [(vin, p.get("createdAt"), p.get("connectionId", ""), p.get("status", ""),
                       p.get("networkInterface"))]
    if kind == "alerts":
        return kind, [(vin, a.get("name"), a.get("startedAt") or p.get("createdAt"), a.get("endedAt"),
                       Jsonb(a.get("audiences", []))) for a in p.get("alerts", [])]
    if kind == "errors":
        return kind, [(vin, e.get("createdAt"), e.get("name"), e.get("body"), Jsonb(e.get("tags", {})))
                      for e in p.get("errors", [])]
    return kind, []


SQL = {
    "V": "INSERT INTO telemetry_raw (vin, ts, field, value_type, value_num, value_text, value_json, is_resend) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
    "connectivity": "INSERT INTO wake_events (vin, ts, connection_id, status, network_interface) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
    "alerts": "INSERT INTO telemetry_alerts (vin, name, started_at, ended_at, audiences) VALUES (%s,%s,%s,%s,%s) "
              "ON CONFLICT (vin, name, started_at) DO UPDATE SET ended_at = EXCLUDED.ended_at",
    "errors": "INSERT INTO telemetry_errors (vin, ts, name, body, tags) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
}


def main():
    c = Consumer({
        "bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"),
        "group.id": os.environ.get("GROUP_ID", "tesla-timescale"),
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        "allow.auto.create.topics": True,
    })
    c.subscribe(list(TOPICS))
    db = psycopg.connect(DSN, autocommit=False)
    log.info("started; topics=%s allowed_vins=%d", list(TOPICS), len(ALLOWED))
    total, last_log = 0, time.time()
    try:
        while running:
            msgs = c.consume(num_messages=500, timeout=1.0)
            if not msgs:
                continue
            batch = {k: [] for k in SQL}
            for m in msgs:
                if m.error():
                    if m.error().code() in (KafkaError._PARTITION_EOF, KafkaError.UNKNOWN_TOPIC_OR_PART):
                        continue
                    raise RuntimeError(f"kafka error: {m.error()}")
                kind = TOPICS.get(m.topic())
                try:
                    p = json.loads(m.value())
                except Exception:
                    log.warning("skipping non-JSON message on %s offset %s", m.topic(), m.offset())
                    continue
                k, rows = rows_for(kind, p)
                batch[k].extend(rows)
            with db.cursor() as cur:
                for k, rows in batch.items():
                    if rows:
                        cur.executemany(SQL[k], rows)
            db.commit()
            c.commit(asynchronous=False)
            total += sum(len(r) for r in batch.values())
            if time.time() - last_log > 300:
                log.info("rows written since start: %d", total)
                last_log = time.time()
    finally:
        log.info("shutting down; rows written: %d", total)
        c.close()
        db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error("fatal: %s", type(e).__name__ + ": " + str(e)[:300])
        sys.exit(1)
