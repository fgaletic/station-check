"""Offline tests: drift detection per fault scenario, and create -> sync -> Source mock.

    .venv/Scripts/python -m unittest discover -s backend/tests -t . -v
"""
import math
import tempfile
import threading
import unittest
from datetime import timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from backend.app import db, health, meteocat, sync
from backend.app.source_client import SourceApiError, SourceClient
from mock_source import server

STATIONS = [{"code": "UP", "name": "Cabrils", "comarca": "Maresme", "lat": 41.52, "lon": 2.38},
            {"code": "UU", "name": "Amposta", "comarca": "Montsià", "lat": 40.71, "lon": 0.58}]
INCOMPLETE = {"code": "KP", "name": "No sunlight sensor", "comarca": "Selva", "lat": 41.53, "lon": 2.37}
COMPANY = server.COMPANIES[0]["id"]


def synthetic_readings(station_code, codes, since_utc):
    """Smooth daily cycles for 14 days up to an hour ago, every 30 min (UTC)."""
    end = sync.utc_now().replace(minute=0, second=0) - timedelta(hours=1)
    t = end - timedelta(days=15)
    rows = []
    while t <= end:
        ts = t.isoformat()
        if ts > since_utc:
            h = t.hour + t.minute / 60
            day = 0.6 * math.sin(t.toordinal())  # some day-to-day variation
            values = {"32": 15 + 5 * math.sin(2 * math.pi * (h - 9) / 24) + day,
                      "33": 70 - 15 * math.sin(2 * math.pi * (h - 9) / 24),
                      "36": max(0.0, 700 * math.sin(math.pi * (h - 6) / 12)) if 6 <= h <= 18 else 0.0}
            rows += [{"variable": c, "time_utc": ts, "value": round(values[c], 1)} for c in codes]
        t += timedelta(minutes=30)
    return rows


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init()
        sync._stations_cache.update(at=0.0, stations=[])
        sync._types_cache.update(at=0.0, names=set())

        server.STATE_FILE = Path(self.tmp.name) / "mock_state.json"
        server.state.update({"sensors": {}, "measurements": []})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{self.httpd.server_port}"
        self.client = SourceClient(f"{base}/v2", f"{base}/oauth2/token", "demo-client", "demo-secret")

        for p in (mock.patch.object(meteocat, "fetch_stations", return_value=STATIONS + [INCOMPLETE]),
                  mock.patch.object(meteocat, "stations_reporting", return_value={"UP", "UU"}),
                  mock.patch.object(meteocat, "fetch_readings", side_effect=synthetic_readings)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def create(self, scenario, lat=41.53, lon=2.37):
        with db.session() as conn:
            gid = sync.create_greenhouse(conn, f"gh-{scenario}", lat, lon, COMPANY, scenario, self.client)
            gh = sync.get_greenhouse(conn, gid)
            return gh, {v["variable"]: v for v in health.check(conn, gh)["variables"]}

    def test_healthy_station_is_ok(self):
        gh, report = self.create("none")
        self.assertEqual(gh["station_code"], "UP")  # KP is closer but has no sunlight sensor
        self.assertEqual({v["status"] for v in report.values()}, {"ok"})

    def test_dirty_radiation_sensor_is_flagged(self):
        _, report = self.create("dusty_radiation")
        self.assertEqual(report["radiation"]["status"], "alert")
        self.assertLess(report["radiation"]["deviation"], -20)
        self.assertIn("dirty", report["radiation"]["message"])
        self.assertEqual(report["temperature"]["status"], "ok")

    def test_humidity_drift_is_flagged(self):
        _, report = self.create("humidity_drift")
        self.assertIn(report["humidity"]["status"], ("warning", "alert"))
        self.assertGreater(report["humidity"]["deviation"], 5)
        self.assertEqual(report["radiation"]["status"], "ok")

    def test_stuck_temperature_is_flagged(self):
        _, report = self.create("stuck_temperature")
        self.assertEqual(report["temperature"]["status"], "alert")
        self.assertIn("hasn't changed", report["temperature"]["message"])

    def test_sync_pushes_reference_and_health_to_source_once(self):
        gh, _ = self.create("dusty_radiation")
        self.assertEqual(len(server.state["sensors"]), 2)
        types = {m["measurementType"] for m in server.state["measurements"]}
        self.assertTrue({"outside_temperature", "outside_global_radiation",
                         "weather_station_radiation_deviation"} <= types)
        self.assertTrue(all(m["timestamp"].endswith("Z") for m in server.state["measurements"]))

        sent = len(server.state["measurements"])
        with db.session() as conn:
            result = sync.sync_greenhouse(conn, sync.get_greenhouse(conn, gh["id"]), self.client)
        self.assertEqual((result["newReadings"], result["sentToSource"], result["error"]), (0, 0, None))
        self.assertEqual(len(server.state["measurements"]), sent)

    def test_types_source_does_not_accept_are_skipped_not_fatal(self):
        known = [t for t in server.MEASUREMENT_TYPES if not t["name"].startswith("weather_station_")]
        with mock.patch.object(server, "MEASUREMENT_TYPES", known), \
                mock.patch.object(server, "TYPE_NAMES", {t["name"] for t in known}):
            gh, _ = self.create("dusty_radiation")
        self.assertIsNone(gh["last_sync_error"])
        self.assertIsNotNone(gh["source_synced_until"])
        types = {m["measurementType"] for m in server.state["measurements"]}
        self.assertIn("outside_temperature", types)
        self.assertFalse(any(t.startswith("weather_station_") for t in types))

    def test_source_outage_is_recorded_without_losing_data(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        with mock.patch("backend.app.source_client.time.sleep"):
            gh, _ = self.create("none")
        self.assertIn("Source", gh["last_sync_error"])
        self.assertIsNone(gh["source_synced_until"])  # cursor did not advance

    def test_mock_rejects_timestamp_without_timezone(self):
        sensor_id = self.client.ensure_sensor("s1", COMPANY, "s1")
        with self.assertRaises(SourceApiError) as ctx:
            self.client.submit_measurements([{"timestamp": "2026-10-21T10:00:00", "measurementType": "outside_temperature",
                                              "sensorId": sensor_id, "value": 1}])
        self.assertEqual(ctx.exception.status, 400)

    def test_bad_credentials(self):
        bad = SourceClient(self.client.api_url, self.client.token_url, "demo-client", "wrong")
        with self.assertRaises(SourceApiError) as ctx:
            bad.companies()
        self.assertEqual(ctx.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
