# Station Check

**Is your greenhouse weather station telling the truth?**

High-tech greenhouses steer ventilation, shading, heating and irrigation from one roof
weather station. When that station drifts (a dusty sunlight sensor, an ageing humidity
sensor, a frozen logger), the climate computer keeps acting on wrong numbers, and
nobody notices until the crop shows it.

Station Check compares each greenhouse's roof station with the nearest official
**Meteocat** station in Catalonia. It flags a sensor when the usual difference between
the two shifts, and sends both the reference data and the health results to
**Source.ag** through the [Source Sensor API](https://www.source.ag/source-api). Growers
then see station health inside Source, next to their climate data.

## Persona and problem

**Who:** the head grower or climate manager at a high-tech vegetable or flower greenhouse
in Catalonia (Maresme, Baix Llobregat, Ebro Delta) that already runs a climate computer,
and possibly Source.

**Problem:** the roof station is a single point of failure that nobody audits. Some
examples:
- **Dirty pyranometer:** it reads 20–30% less sunlight, so radiation-based irrigation
  under-waters and shading opens late.
- **Ageing humidity sensor:** it drifts upward, so the climate computer vents and heats
  to fight humidity that isn't there, which costs energy.
- **Frozen sensor or logger:** the climate computer acts on a stale value.

> **Hypothesis, not yet validated with growers:** roof stations drift without anyone
> noticing, and climate control acts on the bad data. I'd love to know if this matches
> what Source's growers see.

## How the check works
A healthy roof station never matches the Meteocat station exactly: they're in different
places, at different heights, with different exposure. What stays stable is the
*difference* between them. So:

1. **Baseline week:** learn the normal difference: the median for temperature and
   humidity, and the daylight ratio for sunlight.
2. **Last 24 h:** compute the same figure and compare it with the baseline.
3. **Flag it:** warning or alert thresholds (±1/2 °C, ±5/10 humidity points, ±10/20%
   sunlight), plus a "stuck" check: the reading is flat for 6 h while Meteocat keeps
   moving.
4. **Explain it** in plain language, with the likely cause and what to do.

## Screens
- **Overview:** all greenhouses on a map, with health per sensor.
- **Greenhouse:** a card per sensor with the deviation history, a 14-day chart of
  "your station vs Meteocat" with the baseline week shaded, and the Source sync status
  with a "Sync now" button.
- **Add greenhouse:** click the map, and the nearest Meteocat station is picked
  automatically.

## Architecture
```
Meteocat open data ──► backend (FastAPI, SQLite) ──► Source Sensor API v2
 (XEMA, every 30 min)   · ingest + roof-station feed       · reference sensor: outside_*
                        · drift check                      · health sensor: weather_station_*_deviation
                        · background sync loop
                               ▲
                      frontend (React, TypeScript, Leaflet, Recharts)
```
- `backend/app/`: `meteocat.py` (open-data client), `sync.py` (ingest and push),
  `health.py` (drift check), `source_client.py` (OAuth2, retries, batching), `main.py`
  (API, and serves the built frontend)
- `mock_source/`: a local mock of the Source Sensor API, built from their published
  OpenAPI spec ([spec/](spec/source-sensors-api-v2.yaml)), with a debug dashboard at
  http://localhost:8787
- `frontend/`: React + Vite app

## Run it locally
Requires Python 3.10+ and Node 20+.

```bash
py -m venv .venv
```
```bash
.venv/Scripts/python -m pip install -r backend/requirements.txt
```
```bash
npm --prefix frontend install
```

Then run each of these in its own terminal:
```bash
py -m mock_source.server
```
```bash
.venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
```
```bash
npm --prefix frontend run dev
```

Open http://localhost:5173. On first start, 4 demo greenhouses are created with real
Meteocat data. Three of them have a simulated fault: a dirty sunlight sensor, humidity
drift and a frozen temperature sensor.

Tests (offline):
```bash
.venv/Scripts/python -m unittest discover -s backend/tests -t . -v
```

## Deploy
The [Dockerfile](Dockerfile) builds a single service. [serve.py](serve.py) runs the app
on `$PORT` and the Source mock privately next to it. When `SOURCE_API_URL` is set, the
app sends to that address and the mock doesn't start.

```bash
docker build -t station-check .
```
```bash
docker run -p 8000:8000 station-check
```

**Render (free):** New → Blueprint → select this repo. [render.yaml](render.yaml) does
the rest. On the free plan the service sleeps after 15 minutes without traffic, so the
first visit takes about a minute. The SQLite data resets on each restart, and the demo
greenhouses are recreated automatically.

## What's real and what's simulated
| | |
|---|---|
| Meteocat reference data | **Real**, live from the Generalitat open-data portal (datasets `nzvn-apee`, `yqwd-vj5e`) |
| Source API contract | **Real** (v2.8.0 spec); runs against a local mock until Source issues credentials |
| Roof-station readings | **Simulated**: the reference plus a site offset, noise and an optional fault. In production they'd come from the climate computer (CSV export or a controller integration). |
| Source measurement type names | **Assumed.** Only `substrate_weight` is documented. They're checked against `GET /measurement-types` at runtime. |

To point it at Source's real dev environment, set `SOURCE_API_URL`,
`SOURCE_TOKEN_URL`, `SOURCE_CLIENT_ID` and `SOURCE_CLIENT_SECRET`. The URLs are in the
spec.

## Next steps
- Read real roof-station data (climate-computer CSV upload as a first step).
- "I cleaned it" button: record the maintenance and start a fresh baseline.
- Catalan and Spanish UI; alerts by email or WhatsApp.
