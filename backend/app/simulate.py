"""Simulated farm roof-station readings, for the demo.

In production these would come from the grower's climate computer (CSV export or a
controller integration). For the demo we derive them from the official reference reading
plus a fixed site offset, small noise, and an optional fault that worsens over time, so
the drift check has something real to catch.
"""
import random
from datetime import datetime

SCENARIOS = {
    "none": "Healthy station",
    "dusty_radiation": "Dirty sunlight sensor (reads lower each day)",
    "humidity_drift": "Ageing humidity sensor (drifts upward)",
    "stuck_temperature": "Frozen temperature sensor (stuck value)",
}
FAULT_DAYS_AGO = 5  # demo faults start this many days before the greenhouse is added

# The roof station is not in the same spot as the Meteocat station, so a healthy pair still
# differs a bit. The drift check learns this offset during the baseline window.
SITE_OFFSET = {"temperature": 0.6, "humidity": -3.0, "radiation": 0.95}
NOISE = {"temperature": 0.25, "humidity": 1.5, "radiation": 0.03}


def _days_between(start, ts):
    return (datetime.fromisoformat(ts) - datetime.fromisoformat(start)).total_seconds() / 86400


def farm_value(greenhouse_id, variable, ts, ref, scenario="none", fault_start=None, stuck_value=None):
    rng = random.Random(f"{greenhouse_id}:{variable}:{ts}")
    faulty_days = _days_between(fault_start, ts) if fault_start and ts >= fault_start else None

    if variable == "radiation":
        value = ref * SITE_OFFSET["radiation"] * (1 + rng.gauss(0, NOISE["radiation"]))
        if scenario == "dusty_radiation" and faulty_days is not None:
            value *= max(0.5, 1 - 0.055 * faulty_days)
        return round(max(0.0, value), 1)

    if variable == "temperature" and scenario == "stuck_temperature" and faulty_days is not None:
        return stuck_value if stuck_value is not None else round(ref + SITE_OFFSET["temperature"], 1)

    value = ref + SITE_OFFSET[variable] + rng.gauss(0, NOISE[variable])
    if variable == "humidity":
        if scenario == "humidity_drift" and faulty_days is not None:
            value += min(15.0, 2.4 * faulty_days)
        value = min(100.0, max(0.0, value))
    return round(value, 1)
