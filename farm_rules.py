"""Crop calendar and farm alert rules. Pure Python (no Streamlit) so the app and the daily SMS job share them.
Stage dates in data/crop_calendar.csv are indicative defaults: replace them with values from your extension service."""
import csv
from pathlib import Path

CAL_PATH = Path(__file__).parent / "data" / "crop_calendar.csv"


def load_calendar(path=CAL_PATH):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return []
    for r in rows:
        r["start_day"], r["end_day"] = int(r["start_day"]), int(r["end_day"])
        r["water_critical"], r["ndvi_falls"] = int(r["water_critical"]), int(r["ndvi_falls"])
    return rows


def stages(crop, cal):
    return sorted((r for r in cal if r["crop"].lower() == str(crop).lower()), key=lambda r: r["start_day"])


def season_length(crop, cal):
    st_ = stages(crop, cal)
    return max((r["end_day"] for r in st_), default=0)


def current_stage(crop, days, cal):
    """Stage for `days` since planting, or None if the crop has no calendar. After the last stage: 'Past expected harvest'."""
    st_ = stages(crop, cal)
    if not st_:
        return None
    for r in st_:
        if r["start_day"] <= days < r["end_day"]:
            return r
    last = st_[-1]
    if days >= last["end_day"]:
        return {**last, "stage": "Past expected harvest", "ndvi_expectation": "Low or falling", "watch": "Harvest if not done",
                "water_critical": 0, "ndvi_falls": 1}
    return st_[0]


def weather_alerts(dry_days, soil, tmax3, rain3, stage=None, t_heat=38.0):
    """Stage-aware weather alerts for one farm. Returns a list of short messages."""
    critical = bool(stage and stage.get("water_critical"))
    at = f" at {stage['stage'].lower()}, when water matters most" if critical else ""
    out = []
    if dry_days >= (5 if critical else 7):
        out.append(f"No meaningful rain (under 1 mm) for {dry_days} days{at}.")
    if soil is not None and soil < 0.10:
        out.append(f"Topsoil is dry (moisture {soil:.2f}){at}.")
    if tmax3 is not None and tmax3 >= t_heat:
        out.append(f"Heat: up to {tmax3:.0f}C in the next 3 days.")
    if rain3 is not None and rain3 >= 50:
        out.append(f"Heavy rain forecast: {rain3:.0f} mm in 3 days (waterlogging or flood risk).")
    return out
