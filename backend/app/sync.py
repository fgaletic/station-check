"""Pull Meteocat reference data, record roof-station readings, push both to Source."""
import time
from datetime import datetime, timedelta, timezone

from . import db, health, meteocat, simulate
from .source_client import SourceApiError

BACKFILL_DAYS = 14
BASELINE_DAYS = 7
_stations_cache = {"at": 0.0, "stations": []}
_types_cache = {"at": 0.0, "names": set()}


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def accepted_types(client):
    """Measurement type names Source accepts (cached for an hour).

    Our type names are guesses; Source rejects a batch containing an unknown type, so
    anything not on Source's own list is dropped before sending.
    """
    if time.time() - _types_cache["at"] > 3600 or not _types_cache["names"]:
        _types_cache.update(at=time.time(), names={t["name"] for t in client.measurement_types()})
    return _types_cache["names"]


def stations():
    """Operational stations that report temperature, humidity and sunlight (cached for a day)."""
    if time.time() - _stations_cache["at"] > 86400 or not _stations_cache["stations"]:
        since = (utc_now() - timedelta(days=2)).isoformat()
        complete = meteocat.stations_reporting(list(health.XEMA_TO_VARIABLE), since)
        usable = [s for s in meteocat.fetch_stations() if s["code"] in complete]
        _stations_cache.update(at=time.time(), stations=usable)
    return _stations_cache["stations"]


def nearest_station(lat, lon):
    station, km = meteocat.nearest_station(lat, lon, stations())
    return {"code": station["code"], "name": station["name"], "comarca": station["comarca"],
            "lat": station["lat"], "lon": station["lon"], "km": round(km, 1)}


def get_greenhouse(conn, greenhouse_id):
    return conn.execute("SELECT * FROM greenhouses WHERE id = ?", (greenhouse_id,)).fetchone()


def create_greenhouse(conn, name, lat, lon, company_id, scenario, client):
    station = nearest_station(lat, lon)
    now = utc_now()
    fault_start = None if scenario == "none" else (now - timedelta(days=simulate.FAULT_DAYS_AGO)).isoformat()
    cur = conn.execute(
        """INSERT INTO greenhouses (name, lat, lon, company_id, station_code, station_name, station_km,
                                    scenario, fault_start, baseline_start, baseline_end, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, lat, lon, company_id, station["code"], station["name"], station["km"], scenario, fault_start,
         (now - timedelta(days=BACKFILL_DAYS)).isoformat(), (now - timedelta(days=BACKFILL_DAYS - BASELINE_DAYS)).isoformat(),
         now.isoformat()))
    conn.commit()
    greenhouse_id = cur.lastrowid
    sync_greenhouse(conn, get_greenhouse(conn, greenhouse_id), client)
    return greenhouse_id


def _ingest(conn, gh):
    """Fetch new Meteocat readings and the matching roof-station readings. Returns rows added."""
    last = conn.execute("SELECT MAX(ts) FROM readings WHERE greenhouse_id = ? AND source = 'ref'",
                        (gh["id"],)).fetchone()[0]
    since = last or (datetime.fromisoformat(gh["baseline_start"]) - timedelta(minutes=1)).isoformat()
    xema_codes = list(health.XEMA_TO_VARIABLE)
    readings = meteocat.fetch_readings(gh["station_code"], xema_codes, since)

    stuck_value = None
    if gh["scenario"] == "stuck_temperature":
        row = conn.execute("""SELECT value FROM readings WHERE greenhouse_id = ? AND source = 'farm'
                               AND variable = 'temperature' AND ts < ? ORDER BY ts DESC LIMIT 1""",
                           (gh["id"], gh["fault_start"])).fetchone()
        stuck_value = row["value"] if row else None

    rows = []
    for r in readings:
        variable = health.XEMA_TO_VARIABLE[r["variable"]]
        ts = r["time_utc"]
        farm = simulate.farm_value(gh["id"], variable, ts, r["value"], gh["scenario"], gh["fault_start"], stuck_value)
        if variable == "temperature" and gh["fault_start"] and ts < gh["fault_start"]:
            stuck_value = farm
        rows += [(gh["id"], "ref", variable, ts, r["value"]), (gh["id"], "farm", variable, ts, farm)]
    conn.executemany("INSERT OR IGNORE INTO readings VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    return len(readings)


def _push_to_source(conn, gh, client, new_readings):
    ref_sensor, health_sensor = gh["ref_sensor_id"], gh["health_sensor_id"]
    if not ref_sensor:
        ref_sensor = client.ensure_sensor(f"stationcheck-ref:{gh['id']}", gh["company_id"],
                                          f"{gh['name']} · Meteocat {gh['station_name']} (reference)")
    if not health_sensor:
        health_sensor = client.ensure_sensor(f"stationcheck-health:{gh['id']}", gh["company_id"],
                                             f"{gh['name']} · roof station health check")
    conn.execute("UPDATE greenhouses SET ref_sensor_id = ?, health_sensor_id = ? WHERE id = ?",
                 (ref_sensor, health_sensor, gh["id"]))
    conn.commit()

    rows = conn.execute("""SELECT variable, ts, value FROM readings WHERE greenhouse_id = ? AND source = 'ref'
                           AND ts > ? ORDER BY ts""", (gh["id"], gh["source_synced_until"] or "")).fetchall()
    batch = [{"timestamp": r["ts"] + "Z", "measurementType": health.VARIABLES[r["variable"]]["ref_type"],
              "sensorId": ref_sensor, "value": r["value"]} for r in rows]
    if new_readings and rows:
        report = health.check(conn, gh)
        batch += [{"timestamp": rows[-1]["ts"] + "Z", "measurementType": health.VARIABLES[v["variable"]]["health_type"],
                   "sensorId": health_sensor, "value": v["deviation"]}
                  for v in report["variables"] if v["deviation"] is not None]
    accepted = accepted_types(client)
    skipped = sorted({m["measurementType"] for m in batch} - accepted)
    batch = [m for m in batch if m["measurementType"] in accepted]
    if batch:
        client.submit_measurements(batch)
    if rows:  # advance even when everything was skipped, or we'd retry the same rows forever
        conn.execute("UPDATE greenhouses SET source_synced_until = ? WHERE id = ?", (rows[-1]["ts"], gh["id"]))
    return len(batch), skipped


def sync_greenhouse(conn, gh, client):
    """Never raises: errors are recorded on the greenhouse so the UI can show them."""
    result = {"newReadings": 0, "sentToSource": 0, "skippedTypes": [], "error": None}
    try:
        result["newReadings"] = _ingest(conn, gh)
    except Exception as e:
        result["error"] = f"Meteocat: {e}"
    if result["error"] is None:
        try:
            result["sentToSource"], result["skippedTypes"] = _push_to_source(
                conn, get_greenhouse(conn, gh["id"]), client, result["newReadings"])
            if result["skippedTypes"]:
                print(f"[{gh['name']}] Source doesn't accept {', '.join(result['skippedTypes'])}; not sent")
        except (SourceApiError, OSError) as e:
            result["error"] = f"Source: {e}"
    conn.execute("UPDATE greenhouses SET last_sync_at = ?, last_sync_error = ? WHERE id = ?",
                 (utc_now().isoformat(), result["error"], gh["id"]))
    conn.commit()
    return result


def sync_all(client):
    with db.session() as conn:
        for gh in conn.execute("SELECT * FROM greenhouses").fetchall():
            sync_greenhouse(conn, gh, client)
