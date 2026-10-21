"""Drift check: is the farm's roof station still telling the truth?

A healthy roof station never matches the nearest Meteocat station exactly (different spot,
height, exposure), but the *difference* between them is stable. So we learn the normal
difference over a baseline week, then flag when the last 24 h move away from it:

  temperature, humidity   median(farm - ref), compared with the baseline median
  radiation               sum(farm) / sum(ref) in daylight, compared with the baseline ratio

A sensor whose reading stops changing while the reference keeps moving is flagged as stuck.
"""
from datetime import datetime, timedelta
from statistics import median

from . import db

VARIABLES = {
    "temperature": {"label": "Temperature", "xema": "32", "unit": "°C", "warn": 1.0, "alert": 2.0,
                    "ref_type": "outside_temperature", "health_type": "weather_station_temperature_deviation"},
    "humidity": {"label": "Humidity", "xema": "33", "unit": "pp", "warn": 5.0, "alert": 10.0,
                 "ref_type": "outside_relative_humidity", "health_type": "weather_station_humidity_deviation"},
    "radiation": {"label": "Sunlight", "xema": "36", "unit": "%", "warn": 10.0, "alert": 20.0,
                  "ref_type": "outside_global_radiation", "health_type": "weather_station_radiation_deviation"},
}
XEMA_TO_VARIABLE = {v["xema"]: k for k, v in VARIABLES.items()}
STATUS_ORDER = ["unknown", "ok", "warning", "alert"]
DAYLIGHT_W_M2 = 100
MIN_DAYLIGHT_SAMPLES = 6
STUCK_SAMPLES = 12  # 6 h of half-hourly readings
STUCK_REF_RANGE = {"temperature": 0.5, "humidity": 3.0, "radiation": 50.0}

ADVICE = {
    ("temperature", "stuck"): "Temperature hasn't changed in 6 h while Meteocat moved {ref_range:.1f} °C. "
                              "The sensor or logger may be frozen; ventilation and heating are running on a stale value.",
    ("humidity", "stuck"): "Humidity hasn't changed in 6 h while Meteocat moved {ref_range:.0f} pp. "
                           "Check the sensor and its cable.",
    ("radiation", "stuck"): "Sunlight hasn't changed in 6 h of daylight. Check the pyranometer and its cable.",
    ("temperature", 1): "Reads {abs:.1f} °C warmer than usual compared with Meteocat {station}. "
                        "Check the radiation shield and fan; a sun-heated sensor over-ventilates.",
    ("temperature", -1): "Reads {abs:.1f} °C colder than usual compared with Meteocat {station}. "
                         "Check sensor placement and calibration.",
    ("humidity", 1): "Reads {abs:.1f} pp higher than usual compared with Meteocat {station}. "
                     "Humidity sensors drift upward with age; recalibrate or replace it.",
    ("humidity", -1): "Reads {abs:.1f} pp lower than usual compared with Meteocat {station}. "
                      "Recalibrate or replace the sensor.",
    ("radiation", -1): "Reads {abs:.0f}% less sunlight than usual compared with Meteocat {station}. "
                       "The pyranometer is probably dirty; clean it. Shading and irrigation on radiation sums are affected.",
    ("radiation", 1): "Reads {abs:.0f}% more sunlight than usual compared with Meteocat {station}. "
                      "Check for reflections or a recalibration.",
}


def _bias(variable, pairs):
    if variable == "radiation":
        day = [(f, r) for _, f, r in pairs if r >= DAYLIGHT_W_M2]
        if len(day) < MIN_DAYLIGHT_SAMPLES:
            return None
        return sum(f for f, _ in day) / sum(r for _, r in day)
    return median(f - r for _, f, r in pairs) if pairs else None


def _deviation(variable, current, baseline):
    if current is None or baseline is None:
        return None
    if variable == "radiation":
        return (current / baseline - 1) * 100 if baseline else None
    return current - baseline


def _round(x):
    return None if x is None else round(x, 2) + 0.0  # + 0.0 turns -0.0 into 0.0


def _status(variable, deviation):
    if deviation is None:
        return "unknown"
    spec = VARIABLES[variable]
    size = abs(deviation)
    return "alert" if size >= spec["alert"] else "warning" if size >= spec["warn"] else "ok"


def _stuck(variable, pairs):
    if len(pairs) < STUCK_SAMPLES:
        return None
    recent = pairs[-STUCK_SAMPLES:]
    farm = [f for _, f, _ in recent]
    ref = [r for _, _, r in recent]
    ref_range = max(ref) - min(ref)
    if max(farm) - min(farm) < 0.05 and ref_range >= STUCK_REF_RANGE[variable]:
        return ref_range
    return None


def check_variable(conn, gh, variable):
    spec = VARIABLES[variable]
    result = {"variable": variable, "label": spec["label"], "unit": spec["unit"], "status": "unknown",
              "thresholds": {"warning": spec["warn"], "alert": spec["alert"]},
              "deviation": None, "message": "Not enough data from Meteocat yet.", "daily": []}
    pairs = db.paired_series(conn, gh["id"], variable, since=gh["baseline_start"])
    if not pairs:
        result["message"] = f"Meteocat {gh['station_name']} doesn't report {spec['label'].lower()}, so it can't be checked."
        return result
    baseline = _bias(variable, [p for p in pairs if p[0] < gh["baseline_end"]])
    if baseline is None:
        return result

    window_start = (datetime.fromisoformat(pairs[-1][0]) - timedelta(hours=24)).isoformat()
    deviation = _deviation(variable, _bias(variable, [p for p in pairs if p[0] > window_start]), baseline)

    by_day = {}
    for p in pairs:
        by_day.setdefault(p[0][:10], []).append(p)
    result["daily"] = [{"day": day, "deviation": _round(d)} for day, day_pairs in sorted(by_day.items())
                       if (d := _deviation(variable, _bias(variable, day_pairs), baseline)) is not None]

    stuck_range = _stuck(variable, pairs)
    if stuck_range is not None:
        result.update(status="alert", deviation=_round(deviation),
                      message=ADVICE[(variable, "stuck")].format(ref_range=stuck_range))
        return result

    status = _status(variable, deviation)
    result.update(status=status, deviation=_round(deviation))
    if status == "unknown":
        result["message"] = "Not enough daylight in the last 24 h to compare." if variable == "radiation" \
            else result["message"]
    elif status == "ok":
        result["message"] = f"In line with Meteocat {gh['station_name']}."
    else:
        result["message"] = ADVICE[(variable, 1 if deviation > 0 else -1)].format(
            abs=abs(deviation), station=gh["station_name"])
    return result


def check(conn, gh):
    variables = [check_variable(conn, gh, v) for v in VARIABLES]
    overall = max((v["status"] for v in variables), key=STATUS_ORDER.index)
    return {"status": overall, "variables": variables}
