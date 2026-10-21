"""Meteocat XEMA weather-station data from the Generalitat open-data portal (no API key).

Datasets on analisi.transparenciacatalunya.cat:
  yqwd-vj5e  station metadata (location, status)
  nzvn-apee  half-hourly readings, one row per station x variable; timestamps are UTC
"""
import json
import math
import urllib.parse
import urllib.request

BASE = "https://analisi.transparenciacatalunya.cat/resource"
STATIONS_DATASET = "yqwd-vj5e"
READINGS_DATASET = "nzvn-apee"
OPERATIONAL = "2"


def _get(dataset, params, timeout=30):
    url = f"{BASE}/{dataset}.json?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_stations():
    rows = _get(STATIONS_DATASET, {"$limit": 2000, "codi_estat_ema": OPERATIONAL})
    return [{"code": r["codi_estacio"], "name": r["nom_estacio"], "comarca": r.get("nom_comarca", ""),
             "lat": float(r["latitud"]), "lon": float(r["longitud"])} for r in rows]


def stations_reporting(variable_codes, since_utc):
    """Codes of stations that reported every one of `variable_codes` since `since_utc`."""
    codes = ",".join(f"'{c}'" for c in variable_codes)
    rows = _get(READINGS_DATASET, {"$select": "codi_estacio,codi_variable",
                                   "$where": f"codi_variable in({codes}) AND data_lectura > '{since_utc}'",
                                   "$group": "codi_estacio,codi_variable", "$limit": 50000})
    seen = {}
    for r in rows:
        seen.setdefault(r["codi_estacio"], set()).add(r["codi_variable"])
    return {code for code, found in seen.items() if found >= set(variable_codes)}


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def nearest_station(lat, lon, stations):
    station = min(stations, key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]))
    return station, haversine_km(lat, lon, station["lat"], station["lon"])


def fetch_readings(station_code, variable_codes, since_utc):
    """Readings after `since_utc` (naive 'YYYY-MM-DDTHH:MM:SS' in UTC), oldest first."""
    codes = ",".join(f"'{c}'" for c in variable_codes)
    where = (f"codi_estacio='{station_code}' AND codi_variable in({codes}) "
             f"AND data_lectura > '{since_utc}'")
    rows = _get(READINGS_DATASET, {"$where": where, "$order": "data_lectura ASC", "$limit": 50000})
    return [{"variable": r["codi_variable"], "time_utc": r["data_lectura"][:19], "value": float(r["valor_lectura"])}
            for r in rows if r.get("valor_lectura") not in (None, "")]
