"""Local mock of the Source.ag Sensor API v2 (spec/source-sensors-api-v2.yaml).

Implements the same contract as https://sensors.sourceapis.com/v2 plus the OAuth2
client-credentials token endpoint, so the bridge can be developed without real
credentials. Also serves a small dashboard at / showing what has been received.

    python -m mock_source.server            # http://localhost:8787

Measurement type names are NOT published by Source; the list below is a guess.
Swap it for the real list from GET /measurement-types once you have access.
"""
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("MOCK_PORT", "8787"))
STATE_FILE = Path(os.environ.get("MOCK_STATE_FILE", Path(__file__).with_name("mock_state.json")))
CLIENTS = {"demo-client": "demo-secret"}  # test-only credentials for the mock
TOKEN_TTL = 3600
RATE_LIMIT_PER_MIN = int(os.environ.get("MOCK_RATE_LIMIT", "120"))

COMPANIES = [  # fictional growers
    {"id": "6f1c2a9e-1b7d-4c55-9a3e-0d8e2b4f7a11", "name": "Hortícola del Maresme (demo)"},
    {"id": "b3e8d4c2-7a1f-4e60-8c2b-5f9a1d3e6c22", "name": "Pagesos del Delta (demo)"},
]
MEASUREMENT_TYPES = [
    {"name": "substrate_weight", "unitOfMeasurement": "g"},  # the only name the spec confirms
    {"name": "outside_temperature", "unitOfMeasurement": "°C"},
    {"name": "outside_relative_humidity", "unitOfMeasurement": "%"},
    {"name": "outside_global_radiation", "unitOfMeasurement": "W/m2"},
    {"name": "outside_wind_speed", "unitOfMeasurement": "m/s"},
    {"name": "outside_precipitation", "unitOfMeasurement": "mm"},
    {"name": "weather_station_temperature_deviation", "unitOfMeasurement": "°C"},
    {"name": "weather_station_humidity_deviation", "unitOfMeasurement": "%"},
    {"name": "weather_station_radiation_deviation", "unitOfMeasurement": "%"},
    {"name": "drain_ec", "unitOfMeasurement": "mS/cm"},
    {"name": "drain_volume", "unitOfMeasurement": "l"},
]
TYPE_NAMES = {t["name"] for t in MEASUREMENT_TYPES}
COMPANY_IDS = {c["id"] for c in COMPANIES}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_STORED_MEASUREMENTS = 50_000

lock = Lock()
tokens = {}  # token -> expiry epoch
request_times = []
state = {"sensors": {}, "measurements": []}


def load_state():
    if STATE_FILE.exists():
        state.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))


def save_state():
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def parse_iso_with_tz(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


class Handler(BaseHTTPRequestHandler):
    server_version = "SourceMock/2.8.0"

    # ---- plumbing -------------------------------------------------------
    def log_message(self, fmt, *args):
        print(f"[mock] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    def send_json(self, status, body=None, headers=None):
        payload = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def read_json(self):
        try:
            return json.loads(self.read_body() or b"null")
        except json.JSONDecodeError:
            return None

    def authorized(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
        with lock:
            ok = token in tokens and tokens[token] > time.time()
        if not ok:
            self.send_json(401)
        return ok

    def rate_limited(self):
        now = time.time()
        with lock:
            request_times[:] = [t for t in request_times if t > now - 60]
            request_times.append(now)
            limited = len(request_times) > RATE_LIMIT_PER_MIN
        if limited:
            self.send_json(429, headers={"Retry-After": "5"})
        return limited

    # ---- routing --------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self.dashboard()
        if path == "/debug/state":
            with lock:
                return self.send_json(200, {"sensors": list(state["sensors"].values()),
                                            "measurementCount": len(state["measurements"]),
                                            "latest": state["measurements"][-5000:]})
        if self.rate_limited() or not self.authorized():
            return
        if path == "/v2/companies":
            return self.send_json(200, {"companies": COMPANIES})
        if path == "/v2/measurement-types":
            return self.send_json(200, {"measurementTypes": MEASUREMENT_TYPES})
        if path == "/v2/sensors":
            with lock:
                return self.send_json(200, {"sensors": list(state["sensors"].values())})
        m = re.fullmatch(r"/v2/sensors/([^/]+)", path)
        if m:
            sensor = state["sensors"].get(m.group(1))
            return self.send_json(200, sensor) if sensor else self.send_json(404, {"message": "Sensor not found"})
        self.send_json(404, {"message": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/oauth2/token":
            return self.token()
        if self.rate_limited() or not self.authorized():
            return
        if path == "/v2/sensors":
            return self.create_sensor()
        if path == "/v2/measurements":
            return self.submit_measurements()
        self.send_json(404, {"message": "Not found"})

    def do_PATCH(self):
        path = urlparse(self.path).path
        if self.rate_limited() or not self.authorized():
            return
        m = re.fullmatch(r"/v2/sensors/([^/]+)", path)
        if not m:
            return self.send_json(404, {"message": "Not found"})
        body = self.read_json()
        if not isinstance(body, dict) or not isinstance(body.get("name"), str) or not body["name"]:
            return self.send_json(400, {"message": "Bad request", "validationErrors": ["name is required"]})
        with lock:
            sensor = state["sensors"].get(m.group(1))
            if not sensor:
                return self.send_json(404, {"message": "Sensor not found"})
            sensor["name"] = body["name"]
            save_state()
        self.send_json(204)

    # ---- handlers -------------------------------------------------------
    def token(self):
        form = parse_qs(self.read_body().decode())
        grant = form.get("grant_type", [""])[0]
        cid, secret = form.get("client_id", [""])[0], form.get("client_secret", [""])[0]
        if grant != "client_credentials" or CLIENTS.get(cid) != secret:
            return self.send_json(401, {"error": "invalid_client"})
        token = secrets.token_urlsafe(24)
        with lock:
            tokens[token] = time.time() + TOKEN_TTL
        self.send_json(200, {"access_token": token, "token_type": "Bearer", "expires_in": TOKEN_TTL})

    def create_sensor(self):
        body = self.read_json()
        errors = []
        if not isinstance(body, dict):
            errors.append("body must be a JSON object")
        else:
            for field in ("serial", "companyId", "name"):
                if not isinstance(body.get(field), str) or not body[field]:
                    errors.append(f"{field} is required")
        if errors:
            return self.send_json(400, {"message": "Bad request", "validationErrors": errors})
        if body["companyId"] not in COMPANY_IDS:
            return self.send_json(403, {"message": "Permission denied"})
        with lock:
            if any(s["serial"] == body["serial"] and s["companyId"] == body["companyId"]
                   for s in state["sensors"].values()):
                return self.send_json(409, {"message": "Sensor already exists"})
            sensor_id = str(uuid.uuid4())
            state["sensors"][sensor_id] = {"id": sensor_id, "serial": body["serial"],
                                           "companyId": body["companyId"], "name": body["name"]}
            save_state()
        self.send_json(201, {"sensorId": sensor_id}, {"Location": f"/v2/sensors/{sensor_id}"})

    def submit_measurements(self):
        body = self.read_json()
        if not isinstance(body, dict) or not isinstance(body.get("measurements"), list):
            return self.send_json(400, {"message": "Bad request", "validationErrors": ["measurements array is required"]})
        errors = []
        for i, m in enumerate(body["measurements"]):
            if not isinstance(m, dict):
                errors.append(f"measurements[{i}] must be an object")
                continue
            if parse_iso_with_tz(m.get("timestamp")) is None:
                errors.append(f"measurements[{i}].timestamp must be ISO 8601 with timezone")
            if not isinstance(m.get("sensorId"), str) or not UUID_RE.match(m["sensorId"]):
                errors.append(f"measurements[{i}].sensorId must be a UUID")
            if not isinstance(m.get("measurementType"), str):
                errors.append(f"measurements[{i}].measurementType is required")
            if isinstance(m.get("value"), bool) or not isinstance(m.get("value"), (int, float)):
                errors.append(f"measurements[{i}].value must be a number")
        if errors:
            return self.send_json(400, {"message": "Bad request", "validationErrors": errors[:50]})
        with lock:
            for m in body["measurements"]:
                if m["sensorId"] not in state["sensors"]:
                    return self.send_json(403, {"message": "Permission denied"})
                if m["measurementType"] not in TYPE_NAMES:
                    return self.send_json(422, {"message": f"Unknown measurement type {m['measurementType']}"})
            state["measurements"].extend(body["measurements"])
            del state["measurements"][:-MAX_STORED_MEASUREMENTS]
            save_state()
        self.send_json(202)

    def dashboard(self):
        html = Path(__file__).with_name("dashboard.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def main():
    load_state()
    print(f"Source mock on http://localhost:{PORT}  (API base http://localhost:{PORT}/v2)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
