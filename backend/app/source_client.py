"""Client for the Source.ag Sensor API v2 (OAuth2 client credentials)."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_BATCH = 500
MAX_RETRIES = 5


class SourceApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"Source API returned {status}: {body}")
        self.status = status
        self.body = body


class SourceClient:
    def __init__(self, api_url, token_url, client_id, client_secret, timeout=30):
        self.api_url = api_url.rstrip("/")
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._token = None
        self._token_expiry = 0.0

    # ---- auth -----------------------------------------------------------
    def _access_token(self, force=False):
        if force or not self._token or time.time() > self._token_expiry - 60:
            form = urllib.parse.urlencode({"grant_type": "client_credentials",
                                           "client_id": self.client_id,
                                           "client_secret": self.client_secret}).encode()
            req = urllib.request.Request(self.token_url, data=form, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read())
            except urllib.error.HTTPError as e:
                with e:
                    raise SourceApiError(e.code, e.read().decode(errors="replace")) from None
            self._token = body["access_token"]
            self._token_expiry = time.time() + int(body.get("expires_in", 300))
        return self._token

    # ---- transport ------------------------------------------------------
    def _request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        refreshed = False
        for attempt in range(MAX_RETRIES):
            req = urllib.request.Request(f"{self.api_url}{path}", data=data, method=method)
            req.add_header("Authorization", f"Bearer {self._access_token()}")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    return resp.status, (json.loads(raw) if raw else None)
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                e.close()
                if e.code == 401 and not refreshed:
                    self._access_token(force=True)
                    refreshed = True
                    continue
                if e.code == 429 or e.code >= 500:
                    retry_after = e.headers.get("Retry-After")
                    time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
                    continue
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    pass
                raise SourceApiError(e.code, raw) from None
            except urllib.error.URLError:
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(2 ** attempt)
        raise SourceApiError(429, "gave up after retries")

    # ---- endpoints ------------------------------------------------------
    def companies(self):
        return self._request("GET", "/companies")[1]["companies"]

    def measurement_types(self):
        return self._request("GET", "/measurement-types")[1]["measurementTypes"]

    def sensors(self):
        return self._request("GET", "/sensors")[1].get("sensors", [])

    def update_sensor(self, sensor_id, name):
        self._request("PATCH", f"/sensors/{sensor_id}", {"name": name})

    def ensure_sensor(self, serial, company_id, name):
        """Create the sensor, or return the existing one's id if it already exists (409)."""
        try:
            return self._request("POST", "/sensors",
                                 {"serial": serial, "companyId": company_id, "name": name})[1]["sensorId"]
        except SourceApiError as e:
            if e.status != 409:
                raise
        for s in self.sensors():
            if s["serial"] == serial and s["companyId"] == company_id:
                return s["id"]
        raise SourceApiError(409, f"sensor {serial} exists but is not listed")

    def submit_measurements(self, measurements):
        for i in range(0, len(measurements), MAX_BATCH):
            self._request("POST", "/measurements", {"measurements": measurements[i:i + MAX_BATCH]})
