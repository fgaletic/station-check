"""Station Check API.

    .venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
"""
import os
import threading
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, health, simulate, sync
from .source_client import SourceApiError, SourceClient

SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL", "1800"))
SEED_DEMO = os.environ.get("SEED_DEMO", "1") == "1"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

DEMO_GREENHOUSES = [  # fictional farms; companies exist only in the Source mock
    ("Cabrils tomatoes", 41.527, 2.369, "6f1c2a9e-1b7d-4c55-9a3e-0d8e2b4f7a11", "dusty_radiation"),
    ("El Prat lettuce tunnels", 41.317, 2.090, "6f1c2a9e-1b7d-4c55-9a3e-0d8e2b4f7a11", "none"),
    ("Vilassar de Mar carnations", 41.505, 2.392, "6f1c2a9e-1b7d-4c55-9a3e-0d8e2b4f7a11", "stuck_temperature"),
    ("Amposta peppers", 40.708, 0.580, "b3e8d4c2-7a1f-4e60-8c2b-5f9a1d3e6c22", "humidity_drift"),
]

client = SourceClient(
    api_url=os.environ.get("SOURCE_API_URL", "http://localhost:8787/v2"),
    token_url=os.environ.get("SOURCE_TOKEN_URL", "http://localhost:8787/oauth2/token"),
    client_id=os.environ.get("SOURCE_CLIENT_ID", "demo-client"),
    client_secret=os.environ.get("SOURCE_CLIENT_SECRET", "demo-secret"),
)
sync_lock = threading.Lock()


def background_sync(stop):
    with db.session() as conn:
        empty = conn.execute("SELECT COUNT(*) FROM greenhouses").fetchone()[0] == 0
        if SEED_DEMO and empty:
            for name, lat, lon, company, scenario in DEMO_GREENHOUSES:
                with sync_lock:
                    try:
                        sync.create_greenhouse(conn, name, lat, lon, company, scenario, client)
                    except Exception as e:
                        print(f"seeding {name} failed: {e}")
    while not stop.wait(SYNC_INTERVAL):
        with sync_lock:
            sync.sync_all(client)


@asynccontextmanager
async def lifespan(_app):
    db.init()
    stop = threading.Event()
    threading.Thread(target=background_sync, args=(stop,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Station Check", lifespan=lifespan)


class GreenhouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=40.4, le=42.95)  # Catalonia
    lon: float = Field(ge=0.1, le=3.4)
    companyId: str
    scenario: str = "none"


def summary(conn, gh, with_detail=False):
    report = health.check(conn, gh)
    out = {
        "id": gh["id"], "name": gh["name"], "lat": gh["lat"], "lon": gh["lon"], "companyId": gh["company_id"],
        "station": {"code": gh["station_code"], "name": gh["station_name"], "km": gh["station_km"]},
        "scenario": gh["scenario"], "scenarioLabel": simulate.SCENARIOS.get(gh["scenario"], gh["scenario"]),
        "status": report["status"],
        "variables": report["variables"] if with_detail else
                     [{k: v[k] for k in ("variable", "label", "status", "deviation", "unit")} for v in report["variables"]],
        "source": {"refSensorId": gh["ref_sensor_id"], "healthSensorId": gh["health_sensor_id"],
                   "syncedUntil": gh["source_synced_until"], "lastSyncAt": gh["last_sync_at"],
                   "lastSyncError": gh["last_sync_error"]},
        "baseline": {"start": gh["baseline_start"], "end": gh["baseline_end"]},
    }
    return out


def require(conn, greenhouse_id):
    gh = sync.get_greenhouse(conn, greenhouse_id)
    if not gh:
        raise HTTPException(404, "Greenhouse not found")
    return gh


@app.get("/api/greenhouses")
def list_greenhouses():
    with db.session() as conn:
        return [summary(conn, gh) for gh in conn.execute("SELECT * FROM greenhouses ORDER BY id").fetchall()]


@app.post("/api/greenhouses", status_code=201)
def create_greenhouse(body: GreenhouseIn):
    if body.scenario not in simulate.SCENARIOS:
        raise HTTPException(400, f"scenario must be one of {list(simulate.SCENARIOS)}")
    with sync_lock, db.session() as conn:
        try:
            greenhouse_id = sync.create_greenhouse(conn, body.name, body.lat, body.lon, body.companyId,
                                                   body.scenario, client)
        except OSError as e:
            raise HTTPException(502, f"Meteocat unavailable: {e}")
        return summary(conn, sync.get_greenhouse(conn, greenhouse_id), with_detail=True)


@app.get("/api/greenhouses/{greenhouse_id}")
def get_greenhouse(greenhouse_id: int):
    with db.session() as conn:
        return summary(conn, require(conn, greenhouse_id), with_detail=True)


@app.get("/api/greenhouses/{greenhouse_id}/series")
def get_series(greenhouse_id: int, variable: str, days: int = 14):
    if variable not in health.VARIABLES:
        raise HTTPException(400, "unknown variable")
    with db.session() as conn:
        require(conn, greenhouse_id)
        since = (sync.utc_now() - timedelta(days=max(1, min(days, 60)))).isoformat()
        pairs = db.paired_series(conn, greenhouse_id, variable, since)
        return {"variable": variable, "points": [{"ts": ts + "Z", "farm": f, "ref": r} for ts, f, r in pairs]}


@app.post("/api/greenhouses/{greenhouse_id}/sync")
def sync_now(greenhouse_id: int):
    with sync_lock, db.session() as conn:
        result = sync.sync_greenhouse(conn, require(conn, greenhouse_id), client)
        return {**result, "greenhouse": summary(conn, sync.get_greenhouse(conn, greenhouse_id), with_detail=True)}


@app.delete("/api/greenhouses/{greenhouse_id}", status_code=204)
def delete_greenhouse(greenhouse_id: int):
    with db.session() as conn:
        require(conn, greenhouse_id)
        conn.execute("DELETE FROM greenhouses WHERE id = ?", (greenhouse_id,))


@app.get("/api/stations/nearest")
def nearest_station(lat: float, lon: float):
    try:
        return sync.nearest_station(lat, lon)
    except OSError as e:
        raise HTTPException(502, f"Meteocat unavailable: {e}")


@app.get("/api/companies")
def companies():
    try:
        return client.companies()
    except (SourceApiError, OSError) as e:
        raise HTTPException(502, f"Source unavailable: {e}")


@app.get("/api/scenarios")
def scenarios():
    return [{"id": k, "label": v} for k, v in simulate.SCENARIOS.items()]


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and FRONTEND_DIST.resolve() in file.parents:
            return FileResponse(file)  # e.g. favicon.svg
        return FileResponse(FRONTEND_DIST / "index.html")
