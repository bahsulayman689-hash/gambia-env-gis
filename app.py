"""Gambia Environmental GIS Dashboard
Live weather + air quality/dust (Open-Meteo, no API key), interactive map,
protected-area layer, 1-year climate history, composite risk index, custom layer upload.
Run:  streamlit run app.py
"""
import base64
import hmac
import html
import io
import json
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import branca.colormap as cm
import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as pgo
from plotly.subplots import make_subplots
import requests
import streamlit as st
from folium.plugins import Draw, Fullscreen, HeatMap, MiniMap
from streamlit_folium import st_folium

st.set_page_config(page_title="Gambia Environmental GIS", page_icon="🌍", layout="wide")

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = ["#0E7C86", "#1C6DD0", "#1F8A5B", "#E08A00", "#C8372D", "#7B5EA7"]

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Figtree:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, label, button, input { font-family: 'Figtree', sans-serif; }
h1, h2, h3, .hero-org, .hero-status, .stat .v { font-family: 'Bricolage Grotesque', sans-serif; letter-spacing: -0.02em; }
.block-container { padding-top: 1.1rem; max-width: 1400px; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { background: #123F7A; border-right: none; }
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] .brand, section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: #fff; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: rgba(255,255,255,.8); }
section[data-testid="stSidebar"] button { background: #fff; border: none; }
section[data-testid="stSidebar"] button p { color: #123F7A; font-weight: 600; }
.brand { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.3rem; font-weight: 700; color: #fff; }
.hero { position: relative; overflow: hidden; border-radius: 22px; padding: 30px 36px; color: #fff;
  background: linear-gradient(115deg, #0B3C49 0%, #0E5E6B 55%, #13806F 100%); }
.hero:after { content: ""; position: absolute; inset: 0; pointer-events: none;
  background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='60' viewBox='0 0 240 60'%3E%3Cpath d='M0 30 Q30 10 60 30 T120 30 T180 30 T240 30' fill='none' stroke='white' stroke-opacity='.10' stroke-width='2'/%3E%3C/svg%3E") repeat;
  background-size: 240px 60px; }
.hero-row { position: relative; z-index: 1; display: flex; gap: 22px; align-items: center; }
.hero-row img { width: 72px; height: 72px; border-radius: 18px; flex: none; }
.hero-org { font-size: 1rem; font-weight: 500; opacity: .85; }
.hero-status { font-size: 2.2rem; font-weight: 700; line-height: 1.15; margin: 4px 0 8px; }
.hero-status .dot { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 12px;
  box-shadow: 0 0 0 5px rgba(255,255,255,.18); vertical-align: middle; }
.hero-sub { font-size: .95rem; opacity: .8; max-width: 70ch; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 18px 0 8px; }
.stat { background: #fff; border-radius: 14px; padding: 14px 18px; border-left: 6px solid var(--c);
  box-shadow: 0 1px 3px rgba(16,36,43,.08); }
.stat .l { color: #5a6f77; font-size: .88rem; }
.stat .v { font-size: 1.9rem; font-weight: 700; color: #10242B; line-height: 1.2; }
.stat .d { font-size: .82rem; color: var(--c); font-weight: 600; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #d5e0e3; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 10px 18px; }
iframe { border-radius: 16px; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
.chips { position: relative; z-index: 1; margin-top: 14px; }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; margin: 4px 8px 0 0;
  border-radius: 999px; background: rgba(255,255,255,.14); font-size: .9rem; font-weight: 600; }
.chip i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.avatar-wrap { text-align: center; margin: 6px 0 10px; }
.avatar { width: 92px; height: 92px; border-radius: 50%; object-fit: cover; border: 3px solid rgba(255,255,255,.9);
  display: block; margin: 0 auto; }
.avatar.ph { display: flex; align-items: center; justify-content: center; background: #0E7C86; color: #fff;
  font: 700 1.8rem 'Bricolage Grotesque', sans-serif; }
.avatar-name { color: #fff; font-weight: 600; margin-top: 8px; }
.avatar-role { color: rgba(255,255,255,.75); font-size: .85rem; }
.hero-person { position: relative; z-index: 1; margin-left: auto; text-align: center; min-width: 110px; }
.hero-person .avatar { width: 84px; height: 84px; }
.hero-pname { font-weight: 600; margin-top: 6px; }
.hero-prole { font-size: .8rem; opacity: .75; }
@media (max-width: 700px) { .hero { padding: 22px 20px; } .hero-status { font-size: 1.5rem; } .hero-row img, .hero-person { display: none; } }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

# ---------------------------------------------------------------- reference data
REGIONS = {  # name: (lat, lon)
    "Banjul": (13.4549, -16.5790),
    "Kanifing": (13.4383, -16.6781),
    "Brikama (West Coast)": (13.2714, -16.6494),
    "Kerewan (North Bank)": (13.4903, -16.0894),
    "Mansakonko (Lower River)": (13.4667, -15.5333),
    "Kuntaur (Central River N.)": (13.6667, -14.8833),
    "Janjanbureh (Central River S.)": (13.5333, -14.7667),
    "Basse (Upper River)": (13.3081, -14.2167),
}

# Approximate locations of protected areas / key ecosystems (for orientation only)
SITES = [
    ("Abuko Nature Reserve", 13.3900, -16.6450, "Protected area", "green"),
    ("Tanji Bird Reserve", 13.3400, -16.7900, "Protected area", "green"),
    ("Niumi National Park", 13.5500, -16.5500, "Protected area", "green"),
    ("Kiang West National Park", 13.3000, -15.9000, "Protected area", "green"),
    ("River Gambia National Park", 13.5500, -14.9000, "Protected area", "green"),
    ("Tanbi Wetland Complex", 13.4000, -16.6200, "Wetland / mangrove", "blue"),
    ("Bao Bolong Wetland Reserve", 13.4500, -16.1000, "Wetland / mangrove", "blue"),
]

FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FLOOD = "https://flood-api.open-meteo.com/v1/flood"

# Towns: (name, region, lat, lon, flood exposure 1-5, indicative issues). Exposure and issues are
# general, indicative judgements (low-lying, coastal/riverine, drainage) - verify with NEA / NDMA / DWR.
_T = [
    ("Banjul", "Banjul", 13.4549, -16.5790, 5, "Low-lying island, tidal and storm-surge flooding; sea-level rise; high water table; blocked drains and waste in canals"),
    ("Serrekunda", "Kanifing", 13.4383, -16.6781, 5, "Flash flooding from poor drainage in low-lying neighbourhoods; informal settlements in flood paths; solid waste; traffic dust and air pollution"),
    ("Bakau", "Kanifing", 13.4781, -16.6819, 4, "Coastal erosion; flooding near creeks and Kotu stream; tourism pressure on the coast; waste"),
    ("Sukuta", "West Coast", 13.3833, -16.7000, 4, "Flash flooding; unplanned settlement; sand mining; loss of green cover"),
    ("Brikama", "West Coast", 13.2714, -16.6494, 4, "Rapid growth with weak drainage; flash floods; deforestation and charcoal; waste disposal"),
    ("Gunjur", "West Coast", 13.2000, -16.7500, 3, "Coastal erosion; sand mining; mangrove loss; fish-processing waste and pollution"),
    ("Kartong", "West Coast", 13.0833, -16.7667, 3, "Coastal erosion; sand mining; saline intrusion; wetland degradation"),
    ("Essau", "North Bank", 13.4833, -16.5333, 3, "Estuary tidal flooding; mangrove loss; saline intrusion into rice fields"),
    ("Kerewan", "North Bank", 13.4903, -16.0894, 3, "Tidal flooding around Bao Bolong; saline intrusion; rice-land degradation"),
    ("Farafenni", "North Bank", 13.5667, -15.6000, 2, "Bushfires; deforestation; runoff flooding in rainy season; dust and heat along trade route"),
    ("Mansa Konko", "Lower River", 13.4667, -15.5333, 3, "Saline intrusion; river flooding; deforestation; bushfires"),
    ("Bansang", "Central River", 13.4333, -14.6500, 3, "Riverine flooding; bushfires; wood harvesting; soil erosion"),
    ("Janjanbureh", "Central River", 13.5333, -14.7667, 4, "River-island flooding; riverbank erosion; bushfires"),
    ("Kuntaur", "Central River", 13.6667, -14.8833, 3, "River flooding; bushfires; overgrazing; drought stress"),
    ("Basse", "Upper River", 13.3081, -14.2167, 3, "Extreme heat and drought; riverine and flash flooding; gully erosion; land degradation; bushfires"),
]
TOWNS = {t[0]: dict(region=t[1], lat=t[2], lon=t[3], exp=t[4], issues=t[5]) for t in _T}
LEVEL_COLORS = {"Low": "#2ecc71", "Watch": "#f1c40f", "Warning": "#e67e22", "Severe": "#c0392b"}


_CUSTOMER = {"https://api.open-meteo.com": "https://customer-api.open-meteo.com",
             "https://air-quality-api.open-meteo.com": "https://customer-air-quality-api.open-meteo.com",
             "https://archive-api.open-meteo.com": "https://customer-archive-api.open-meteo.com",
             "https://marine-api.open-meteo.com": "https://customer-marine-api.open-meteo.com",
             "https://flood-api.open-meteo.com": "https://customer-flood-api.open-meteo.com"}


def get(url, params, timeout=30):
    """GET JSON with retries on timeouts and temporary errors (429, 5xx). Uses the Open-Meteo
    commercial endpoints when OPEN_METEO_KEY is set in secrets."""
    key = None
    try:
        key = st.secrets["OPEN_METEO_KEY"]
    except Exception:
        pass
    if key:
        for free, cust in _CUSTOMER.items():
            if url.startswith(free):
                url, params = url.replace(free, cust, 1), {**params, "apikey": key}
                break
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 3:
                time.sleep(1.5 * 2 ** attempt)
                continue
            raise
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(1.5 * 2 ** attempt)   # 1.5 s, 3 s, 6 s
            continue
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------- data loaders
@st.cache_data(ttl=1800, show_spinner="Fetching live environmental data…")
def load_live():
    lats = ",".join(str(v[0]) for v in REGIONS.values())
    lons = ",".join(str(v[1]) for v in REGIONS.values())
    base = {"latitude": lats, "longitude": lons, "timezone": "Africa/Banjul"}
    w = get(FORECAST, {**base, "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                       "daily": "precipitation_sum", "forecast_days": 7})
    a = get(AIR, {**base, "current": "pm10,pm2_5,dust,us_aqi"})
    w = w if isinstance(w, list) else [w]
    a = a if isinstance(a, list) else [a]
    rows = []
    for (name, (lat, lon)), wi, ai in zip(REGIONS.items(), w, a):
        rows.append({
            "Region": name, "lat": lat, "lon": lon,
            "Temp (°C)": wi["current"]["temperature_2m"],
            "Humidity (%)": wi["current"]["relative_humidity_2m"],
            "Wind (km/h)": wi["current"]["wind_speed_10m"],
            "Rain next 7d (mm)": sum(x or 0 for x in wi["daily"]["precipitation_sum"]),
            "PM10 (µg/m³)": ai["current"]["pm10"],
            "PM2.5 (µg/m³)": ai["current"]["pm2_5"],
            "Dust (µg/m³)": ai["current"]["dust"],
            "US AQI": ai["current"]["us_aqi"],
        })
    df = pd.DataFrame(rows)
    num = df.columns.drop(["Region", "lat", "lon"])
    df[num] = df[num].apply(pd.to_numeric, errors="coerce").fillna(0)
    heat = ((df["Temp (°C)"] - 30) / 10).clip(0, 1)
    air = (df["PM10 (µg/m³)"] / 150).clip(0, 1)
    flood = (df["Rain next 7d (mm)"] / 80).clip(0, 1)
    df["Composite risk (0-100)"] = ((heat + air + flood) / 3 * 100).round(1)
    return df


@st.cache_data(ttl=86400, show_spinner="Loading 1-year climate history…")
def load_history(lat, lon):
    end = date.today() - timedelta(days=6)
    start = end - timedelta(days=365)
    j = get(ARCHIVE, {"latitude": lat, "longitude": lon, "start_date": start.isoformat(),
                      "end_date": end.isoformat(), "timezone": "Africa/Banjul",
                      "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum"})
    d = pd.DataFrame(j["daily"])
    d["time"] = pd.to_datetime(d["time"])
    return d


def flood_metrics(coords):
    """7-day rain + GloFAS river discharge -> hazard 0-1 per (lat, lon)."""
    base = {"latitude": ",".join(str(c[0]) for c in coords), "longitude": ",".join(str(c[1]) for c in coords),
            "forecast_days": 7}
    w = get(FORECAST, {**base, "daily": "precipitation_sum", "timezone": "Africa/Banjul"})
    w = w if isinstance(w, list) else [w]
    try:
        f = get(FLOOD, {**base, "daily": "river_discharge,river_discharge_mean"})
        f = f if isinstance(f, list) else [f]
    except Exception:
        f = [{}] * len(coords)
    out = []
    for wi, fi in zip(w, f):
        rain = [x or 0 for x in wi["daily"]["precipitation_sum"]]
        d = fi.get("daily", {}) if isinstance(fi, dict) else {}
        q = [x for x in d.get("river_discharge", []) if x is not None]
        qm = [x for x in d.get("river_discharge_mean", []) if x is not None]
        peak = max(q) if q else 0.0
        ratio = peak / (sum(qm) / len(qm)) if q and qm and sum(qm) > 0 else 0.0
        hazard = max(min(sum(rain) / 80, 1), min(max(rain) / 50, 1), min(max(ratio - 1, 0) / 2, 1))
        out.append(dict(rain=rain, dates=wi["daily"]["time"], rain7=sum(rain), rain_max=max(rain),
                        discharge=peak, ratio=ratio, hazard=hazard))
    return out


@st.cache_data(ttl=1800, show_spinner="Checking flood forecasts for every town…")
def load_towns():
    m = flood_metrics([(t["lat"], t["lon"]) for t in TOWNS.values()])
    rows = []
    for (n, t), x in zip(TOWNS.items(), m):
        h = x["hazard"]
        lvl = ("Low", "Watch", "Warning", "Severe")[0 if h < .25 else 1 if h < .5 else 2 if h < .75 else 3]
        rows.append({"Town": n, "Region": t["region"], "lat": t["lat"], "lon": t["lon"], "Flood level": lvl,
                     "Flood risk (0-100)": round(100 * (0.6 * h + 0.4 * t["exp"] / 5), 1),
                     "Rain 7d (mm)": round(x["rain7"], 1), "Max daily rain (mm)": round(x["rain_max"], 1),
                     "River discharge (m³/s)": round(x["discharge"], 1),
                     "Discharge vs normal (x)": round(x["ratio"], 2), "Exposure (1-5)": t["exp"],
                     "Issues": t["issues"], "_rain": x["rain"], "_dates": x["dates"]})
    return pd.DataFrame(rows)


MARINE = "https://marine-api.open-meteo.com/v1/marine"
COAST = [("North coast", 13.55, -17.00), ("Banjul coast", 13.40, -17.00), ("South coast", 13.15, -17.00)]
INCIDENT_TYPES = ["Flood", "Storm / wind damage", "Coastal erosion", "Fire", "Drought / crop damage",
                  "Heat or health impact", "Pollution / waste", "Other"]
SEV_COLORS = {"Minor": "#f1c40f", "Moderate": "#e67e22", "Severe": "#c0392b"}


@st.cache_data(ttl=3600, show_spinner="Checking sea conditions…")
def load_marine():
    j = get(MARINE, {"latitude": ",".join(str(c[1]) for c in COAST), "longitude": ",".join(str(c[2]) for c in COAST),
                     "daily": "wave_height_max,wave_period_max", "hourly": "sea_level_height_msl",
                     "forecast_days": 7, "timezone": "Africa/Banjul"})
    j = j if isinstance(j, list) else [j]
    rows = []
    for (n, la, lo), x in zip(COAST, j):
        wh = [v for v in x.get("daily", {}).get("wave_height_max", []) if v is not None]
        wp = [v for v in x.get("daily", {}).get("wave_period_max", []) if v is not None]
        sl = [v for v in x.get("hourly", {}).get("sea_level_height_msl", []) if v is not None]
        rows.append({"Coast": n, "lat": la, "lon": lo,
                     "Max wave (m)": round(max(wh), 1) if wh else None,
                     "Max wave period (s)": round(max(wp), 1) if wp else None,
                     "Highest sea level (m)": round(max(sl), 2) if sl else None,
                     "Lowest sea level (m)": round(min(sl), 2) if sl else None})
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner="Checking drought indicators…")
def load_drought():
    items = list(REGIONS.items())
    j = get(FORECAST, {"latitude": ",".join(str(v[0]) for _, v in items), "longitude": ",".join(str(v[1]) for _, v in items),
                       "daily": "precipitation_sum,et0_fao_evapotranspiration", "hourly": "soil_moisture_0_to_7cm",
                       "past_days": 14, "forecast_days": 1, "timezone": "Africa/Banjul"})
    j = j if isinstance(j, list) else [j]
    rows = []
    for (n, _), x in zip(items, j):
        p = [v or 0 for v in x["daily"]["precipitation_sum"][:-1]]
        dry = 0
        for v in reversed(p):
            if v >= 1:
                break
            dry += 1
        sm = [v for v in x.get("hourly", {}).get("soil_moisture_0_to_7cm", []) if v is not None]
        smv = sm[-1] if sm else None
        et = x["daily"]["et0_fao_evapotranspiration"][-1] or 0
        idx = 100 * (0.5 * min(dry / 14, 1) + 0.5 * (1 - min((smv if smv is not None else 0.3) / 0.30, 1)))
        rows.append({"Region": n, "Dry days (last 14)": dry, "Rain last 14d (mm)": round(sum(p), 1),
                     "Soil moisture (m³/m³)": None if smv is None else round(smv, 3),
                     "ET0 today (mm)": round(et, 1), "Drought index (0-100)": round(idx, 1)})
    return pd.DataFrame(rows)


def sb_rest(method, table, token, params=None, body=None):
    r = requests.request(method, f"{secret('SUPABASE_URL')}/rest/v1/{table}", params=params, timeout=30,
                         data=json.dumps(body) if body is not None else None,
                         headers={"apikey": secret("SUPABASE_KEY"), "Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json", "Prefer": "return=minimal"})
    if r.status_code >= 400:
        try:
            msg = r.json().get("message")
        except Exception:
            msg = r.text[:150]
        raise ValueError(msg or "Request failed")
    return r.json() if r.content else None


@st.cache_data(ttl=60)
def load_incidents(token):
    rows = sb_rest("GET", "incidents", token, {"select": "*", "order": "created_at.desc", "limit": "500"})
    return pd.DataFrame(rows or [])


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def count_buildings(lat, lon, radius=1000):
    """Mapped OpenStreetMap buildings within `radius` m (exposure proxy; OSM coverage varies)."""
    q = f'[out:json][timeout:30];way["building"](around:{radius},{lat},{lon});out count;'
    r = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=45,
                      headers={"User-Agent": "gambia-env-gis"})
    r.raise_for_status()
    el = r.json().get("elements", [])
    return int(el[0]["tags"]["total"]) if el else 0


def upload_photo(token, f):
    data = f.getvalue()
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("Photo must be under 5 MB")
    path = f"{uuid.uuid4().hex}.{(f.name.rsplit('.', 1)[-1] or 'jpg').lower()}"
    base = secret("SUPABASE_URL")
    r = requests.post(f"{base}/storage/v1/object/incident-photos/{path}", data=data, timeout=60,
                      headers={"apikey": secret("SUPABASE_KEY"), "Authorization": f"Bearer {token}",
                               "Content-Type": f.type or "image/jpeg"})
    if r.status_code >= 400:
        raise ValueError("Photo upload failed (is the incident-photos bucket set up?)")
    return f"{base}/storage/v1/object/public/incident-photos/{path}"


@st.cache_data(ttl=1800, show_spinner="Loading timeline…")
def load_timeline(lat, lon):
    w = get(FORECAST, {"latitude": lat, "longitude": lon, "past_days": 7, "forecast_days": 7,
                       "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                       "timezone": "Africa/Banjul"})
    a = get(AIR, {"latitude": lat, "longitude": lon, "past_days": 3, "forecast_days": 4,
                  "hourly": "pm10,pm2_5,dust", "timezone": "Africa/Banjul"})
    d = pd.DataFrame(w["daily"])
    d["time"] = pd.to_datetime(d["time"])
    d["Period"] = ["Past" if t.date() < date.today() else "Forecast" for t in d["time"]]
    h = pd.DataFrame(a["hourly"])
    h["time"] = pd.to_datetime(h["time"])
    return d, h


@st.cache_data(ttl=3600, show_spinner="Searching Sentinel-2 scenes…")
def s2_search(lat, lon, half, start, end, cloud):
    import sentinel
    return sentinel.search(lat, lon, half, start, end, cloud)


@st.cache_data(ttl=86400, show_spinner=False, max_entries=200)
def s2_stats(fid, bbox, max_px, _feature):
    import sentinel
    return sentinel.stats(_feature, list(bbox), max_px)


@st.cache_data(ttl=86400, show_spinner="Reading Sentinel-2 pixels…", max_entries=6)
def s2_scene(fid, bbox, max_px, _feature):
    import sentinel
    return sentinel.load_scene(_feature, list(bbox), max_px)


FIRMS_BBOX = "-16.9,13.0,-13.7,13.9"
CONF_MAP = {"l": "Low", "n": "Nominal", "h": "High"}


@st.cache_data(ttl=3600, show_spinner=False)
def load_firms_source(key, source, days):
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{FIRMS_BBOX}/{days}"
    r = requests.get(url, timeout=40)
    r.raise_for_status()
    f = pd.read_csv(io.StringIO(r.text))
    if "latitude" not in f.columns:
        raise ValueError(r.text[:120])
    return f


def hav_km(la1, lo1, la2, lo2):
    la1, lo1, la2, lo2 = map(np.radians, (la1, lo1, la2, lo2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def match_rate(a, b, km):
    """Share of detections in `a` that have a detection in `b` within `km` on the same date."""
    if a is None or b is None or not len(a):
        return None
    hits = 0
    for d, ga in a.groupby("acq_date"):
        gb = b[b["acq_date"] == d]
        if gb.empty:
            continue
        dist = hav_km(ga["latitude"].values[:, None], ga["longitude"].values[:, None],
                      gb["latitude"].values[None, :], gb["longitude"].values[None, :])
        hits += int((dist.min(axis=1) <= km).sum())
    return round(100 * hits / len(a), 1)


@st.cache_data(ttl=600, show_spinner="Checking data sources…")
def health_checks(key):
    rows = []

    def add(src, check, t0, ok, fresh="-", note=""):
        rows.append({"Source": src, "Check": check, "Status": "Up" if ok else "Down",
                     "Latency (ms)": int((time.perf_counter() - t0) * 1000), "Freshness": fresh, "Note": note})

    t0 = time.perf_counter()
    try:
        r = requests.get(FORECAST, params={"latitude": 13.45, "longitude": -16.58, "current": "temperature_2m",
                                           "timezone": "UTC"}, timeout=20)
        note = ""
        if r.ok:
            age = (pd.Timestamp.now("UTC").tz_localize(None) - pd.to_datetime(r.json()["current"]["time"])).total_seconds() / 60
            note = f"Latest reading {age:.0f} min old"
        add("Open-Meteo", "Weather API", t0, r.ok, note=note)
    except Exception as e:
        add("Open-Meteo", "Weather API", t0, False, note=str(e)[:60])
    t0 = time.perf_counter()
    try:
        r = requests.get("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_NDVI_8Day/default/default/"
                         "GoogleMapsCompatible_Level9/2/1/1.png", timeout=20)
        add("NASA GIBS", "NDVI map tile", t0, r.ok and len(r.content) > 0, note=f"{len(r.content)} bytes")
    except Exception as e:
        add("NASA GIBS", "NDVI map tile", t0, False, note=str(e)[:60])
    t0 = time.perf_counter()
    try:
        r = requests.get("https://earth-search.aws.element84.com/v1", timeout=20)
        add("Earth Search (Sentinel-2)", "STAC API", t0, r.ok)
    except Exception as e:
        add("Earth Search (Sentinel-2)", "STAC API", t0, False, note=str(e)[:60])
    if key:
        t0 = time.perf_counter()
        try:
            r = requests.get(f"https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{key}/ALL", timeout=20)
            r.raise_for_status()
            av = pd.read_csv(io.StringIO(r.text))
            mcol = [c for c in av.columns if "max" in c.lower()][0]
            for sensor in ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"):
                sel = av[av.iloc[:, 0] == sensor]
                if len(sel):
                    mx = pd.to_datetime(sel.iloc[0][mcol])
                    age = (pd.Timestamp.now("UTC").tz_localize(None).normalize() - mx.normalize()).days
                    fr = "Fresh" if age <= 1 else "Delayed" if age <= 3 else "Stale"
                    add("NASA FIRMS", sensor, t0, True, fresh=fr, note=f"Newest data {mx.date()} ({age} day(s) old)")
        except Exception as e:
            add("NASA FIRMS", "Data availability", t0, False, note=str(e)[:60])
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_dq_log(token):
    rows = sb_rest("GET", "data_quality_log", token, {"select": "*", "order": "created_at.desc", "limit": "500"})
    return pd.DataFrame(rows or [])


CROPS = ["Groundnut", "Rice", "Millet", "Maize", "Sorghum", "Cowpea", "Cassava", "Vegetables", "Other"]


@st.cache_data(ttl=3600, show_spinner=False)
def geocode(name):
    j = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": name, "count": 10, "language": "en", "format": "json"}, timeout=20).json()
    res = [r for r in j.get("results", []) if r.get("country_code") == "GM"] or j.get("results", [])
    return [{"label": f"{r['name']}, {r.get('admin1', '')}, {r.get('country_code', '')}", "lat": r["latitude"],
             "lon": r["longitude"]} for r in res]


def square_geom(lat, lon, ha):
    half = (ha * 10000) ** 0.5 / 2
    dlat, dlon = half / 110540, half / (111320 * float(np.cos(np.radians(lat))))
    return {"type": "Polygon", "coordinates": [[[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat],
                                                [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]]}


def geom_info(g):
    ring = g["coordinates"][0]
    lat0 = sum(c[1] for c in ring) / len(ring)
    lon0 = sum(c[0] for c in ring) / len(ring)
    pts = [((c[0] - lon0) * 111320 * float(np.cos(np.radians(lat0))), (c[1] - lat0) * 110540) for c in ring]
    area = abs(sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))) / 2 / 10000
    return lat0, lon0, area


@st.cache_data(ttl=1800, show_spinner="Loading farm weather…")
def load_farm_weather(lat, lon, past_days):
    j = get(FORECAST, {"latitude": round(lat, 4), "longitude": round(lon, 4), "past_days": past_days, "forecast_days": 7,
                       "timezone": "Africa/Banjul", "daily": "precipitation_sum,temperature_2m_max,et0_fao_evapotranspiration",
                       "hourly": "soil_moisture_0_to_7cm"})
    d = pd.DataFrame(j["daily"])
    d["time"] = pd.to_datetime(d["time"])
    h = pd.DataFrame(j["hourly"])
    h["time"] = pd.to_datetime(h["time"])
    sm = h.set_index("time")["soil_moisture_0_to_7cm"].resample("D").mean().reset_index()
    return d.merge(sm, on="time", how="left")


@st.cache_data(ttl=86400, show_spinner=False, max_entries=300)
def farm_ndvi(fid, geom_json, _feature):
    import sentinel
    return sentinel.field_ndvi(_feature, json.loads(geom_json))


@st.cache_data(ttl=60)
def load_farms(token):
    rows = sb_rest("GET", "farms", token, {"select": "*", "order": "created_at.desc", "limit": "100"})
    return pd.DataFrame(rows or [])


NDVI_LABEL = "Vegetation greenness (NDVI, Sentinel-2)"
METRICS_TS = {  # name: (archive variable, monthly aggregation, hourly?)
    "Rainfall (mm per month)": ("precipitation_sum", "sum", False),
    "Average daily max temperature (°C)": ("temperature_2m_max", "mean", False),
    "Average daily min temperature (°C)": ("temperature_2m_min", "mean", False),
    "Soil moisture, top 7 cm (m³/m³)": ("soil_moisture_0_to_7cm", "mean", True),
    "Evapotranspiration (mm per month)": ("et0_fao_evapotranspiration", "sum", False),
    "Average maximum wind (km/h)": ("wind_speed_10m_max", "mean", False)}


@st.cache_data(ttl=86400, show_spinner=False)
def _archive_chunk(lat, lon, start, end, var, hourly):
    p = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "timezone": "Africa/Banjul",
         ("hourly" if hourly else "daily"): var}
    blk = get(ARCHIVE, p, timeout=90)["hourly" if hourly else "daily"]
    return pd.Series(blk[var], index=pd.to_datetime(blk["time"]), dtype="float64")


def load_monthly(lat, lon, start, end, metric):
    """Monthly values from the Open-Meteo archive, fetched one calendar year at a time so each
    piece is small and saved separately (a failed year does not lose the others)."""
    var, how, hourly = METRICS_TS[metric]
    cur, last, parts = date.fromisoformat(start), date.fromisoformat(end), []
    while cur <= last:
        nxt = min(date(cur.year, 12, 31), last)
        parts.append(_archive_chunk(round(lat, 3), round(lon, 3), str(cur), str(nxt), var, hourly))
        cur = nxt + timedelta(days=1)
    ser = pd.concat(parts)
    if hourly:
        ser = ser.resample("D").mean()
    m = (ser.resample("MS").sum(min_count=1) if how == "sum" else ser.resample("MS").mean()).reset_index()
    m.columns = ["month", "value"]
    return m


def block_change(d, how):
    """Latest 12 months vs the average of earlier 12-month blocks."""
    d = d.dropna().sort_values("month").reset_index(drop=True)
    n = len(d) // 12
    if n < 2:
        return None
    d = d.iloc[len(d) - n * 12:]
    vals = [(d.iloc[i * 12:(i + 1) * 12]["value"].sum() if how == "sum" else d.iloc[i * 12:(i + 1) * 12]["value"].mean())
            for i in range(n)]
    prev = float(np.mean(vals[:-1]))
    return vals[-1], prev, (100 * (vals[-1] - prev) / prev if prev else None)


@st.cache_data(ttl=86400, show_spinner="Comparing the two scenes…", max_entries=8)
def s2_change(id1, id2, bbox, max_px, _f1, _f2):
    import sentinel
    return sentinel.change(_f1, _f2, list(bbox), max_px)


def secret(k):
    try:
        v = st.secrets[k]
    except Exception:
        return None
    if k == "SUPABASE_URL" and v:  # keep only https://<project>.supabase.co, even if a longer URL was pasted
        from urllib.parse import urlparse
        u = urlparse(str(v).strip())
        return f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else str(v).strip().rstrip("/")
    return v


@st.cache_data(ttl=3600, show_spinner="Fetching NASA FIRMS fire hotspots…")
def load_fires(key, days):
    url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/"
           f"-16.9,13.0,-13.7,13.9/{days}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    f = pd.read_csv(io.StringIO(r.text))
    if "latitude" not in f.columns:
        raise ValueError(r.text[:120])
    return f


def log_alerts(rows):
    """Insert alerts into Supabase table `alerts` (see README.md for SQL)."""
    r = requests.post(f"{secret('SUPABASE_URL')}/rest/v1/alerts",
                      headers={"apikey": secret("SUPABASE_KEY"),
                               **({"Authorization": f"Bearer {secret('SUPABASE_KEY')}"}
                                  if str(secret("SUPABASE_KEY")).startswith("eyJ") else {}),
                               "Content-Type": "application/json"},
                      data=json.dumps(rows), timeout=30)
    r.raise_for_status()


def build_report(org, df, tw, alerts):
    css = ("body{font-family:Arial,sans-serif;margin:32px;color:#222}h1{color:#1b4f72}"
           "table{border-collapse:collapse;font-size:12px;margin-bottom:18px}"
           "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}th{background:#eaf2f8}")
    parts = [f"<h1>{html.escape(org)}: Environmental Report</h1>",
             f"<p>Generated {datetime.now():%d %b %Y %H:%M} (print to PDF from your browser)</p>",
             "<h2>Active alerts</h2>" + (pd.DataFrame(alerts).to_html(index=False) if alerts else "<p>None</p>"),
             "<h2>Regional conditions</h2>" + df.drop(columns=["lat", "lon"]).round(1).to_html(index=False)]
    if tw is not None:
        parts.append("<h2>Town flood outlook (7 days)</h2>" + tw[["Town", "Region", "Flood level", "Flood risk (0-100)",
                     "Rain 7d (mm)", "Issues"]].to_html(index=False))
    parts.append("<p><small>Sources: Open-Meteo (weather, CAMS air quality, GloFAS flood), NASA GIBS/FIRMS. "
                 "Exposure and issue lists are indicative; verify with NEA / NDMA / DWR.</small></p>")
    return f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(parts)}</body></html>"


# ---- white-label + access gate (all optional, set in secrets) ----
ORG = secret("ORG_NAME") or "Gambia"
_pw = secret("APP_PASSWORD")
SB_ON = bool(secret("SUPABASE_URL") and secret("SUPABASE_KEY"))
LOGIN_REQUIRED = SB_ON and str(secret("REQUIRE_LOGIN")).lower() != "false"


def sb_auth(path, payload, params=None):
    """Supabase Auth (GoTrue) REST call. Returns JSON or raises ValueError with a readable message."""
    r = requests.post(f"{secret('SUPABASE_URL')}/auth/v1/{path}", params=params, json=payload, timeout=30,
                      headers={"apikey": secret("SUPABASE_KEY"), "Content-Type": "application/json"})
    j = r.json() if r.content else {}
    if r.status_code >= 400:
        raise ValueError(j.get("msg") or j.get("error_description") or j.get("message") or "Request failed")
    return j


def _login(j, fallback_email):
    u = j.get("user") or {}
    meta = u.get("user_metadata") or {}
    st.session_state["user"] = {"email": u.get("email", fallback_email), "token": j.get("access_token"),
                                "id": u.get("id"), "avatar": meta.get("avatar_url", ""),
                                "name": meta.get("full_name", "")}
    st.rerun()


if LOGIN_REQUIRED and not st.session_state.get("user"):
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.markdown(
            f'<div class="hero" style="min-height:430px"><div style="position:relative;z-index:1">'
            f'<div class="hero-org">{html.escape(ORG)}</div>'
            f'<div class="hero-status" style="font-size:2rem">Environmental monitoring for The Gambia</div>'
            f'<div class="hero-sub">Flood outlook for 15 towns, air quality and dust, heat, fire hotspots and '
            f'satellite vegetation in one live map. Sign in to open the dashboard.</div></div></div>',
            unsafe_allow_html=True)
    with right:
        t_in, t_up = st.tabs(["Sign in", "Create account"])
        with t_in:
            with st.form("signin"):
                em = st.text_input("Email")
                pw = st.text_input("Password", type="password")
                go = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if go:
                try:
                    _login(sb_auth("token", {"email": em.strip(), "password": pw}, {"grant_type": "password"}), em)
                except ValueError as e:
                    st.error(f"Could not sign in: {e}. If you just signed up, confirm your email first.")
            with st.expander("Forgot your password?"):
                rem = st.text_input("Account email", key="reset_email")
                if st.button("Send reset link"):
                    try:
                        sb_auth("recover", {"email": rem.strip()})
                        st.success("If that email has an account, a reset link is on its way.")
                    except ValueError as e:
                        st.error(str(e))
        with t_up:
            with st.form("signup"):
                nm = st.text_input("Full name")
                em2 = st.text_input("Work email")
                pw2 = st.text_input("Password (at least 8 characters)", type="password")
                pw3 = st.text_input("Confirm password", type="password")
                go2 = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if go2:
                if len(pw2) < 8:
                    st.error("Use a password with at least 8 characters.")
                elif pw2 != pw3:
                    st.error("The two passwords do not match.")
                else:
                    try:
                        j = sb_auth("signup", {"email": em2.strip(), "password": pw2, "data": {"full_name": nm.strip()}})
                        if j.get("access_token"):
                            _login(j, em2)
                        st.success("Account created. Check your email and confirm it, then sign in.")
                    except ValueError as e:
                        st.error(f"Could not create account: {e}")
    st.stop()
elif not SB_ON and _pw and not st.session_state.get("auth"):
    st.title(f"🔒 {ORG}")
    code = st.text_input("Access code", type="password")
    if st.button("Enter"):
        if hmac.compare_digest(code, str(_pw)):
            st.session_state["auth"] = True
            st.rerun()
        st.error("Wrong access code")
    st.stop()
if secret("ORG_LOGO_URL"):
    st.sidebar.image(secret("ORG_LOGO_URL"))
if secret("PRIMARY_COLOR"):
    st.markdown(f"<style>h1,h2,h3{{color:{secret('PRIMARY_COLOR')}}}</style>", unsafe_allow_html=True)

def _person():
    u = st.session_state.get("user") or {}
    name = u.get("name") or u.get("email") or ORG
    src = u.get("avatar") or ""
    if not src and st.session_state.get("avatar_bytes"):
        src = "data:image/jpeg;base64," + base64.b64encode(st.session_state["avatar_bytes"]).decode()
    parts = str(name).split()
    ini = (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper() if parts else "?"
    inner = f'<img class="avatar" src="{html.escape(src)}" alt="Profile photo">' if src else f'<div class="avatar ph">{html.escape(ini)}</div>'
    return name, src, inner


def save_avatar(f):
    from PIL import Image
    if f.size > 5 * 1024 * 1024:
        raise ValueError("Photo must be under 5 MB")
    im = Image.open(f).convert("RGB")
    w, h = im.size
    m = min(w, h)
    im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((256, 256))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    data = buf.getvalue()
    u = st.session_state.get("user")
    if SB_ON and u and u.get("token") and u.get("id"):
        base, key, tok = secret("SUPABASE_URL"), secret("SUPABASE_KEY"), u["token"]
        r = requests.post(f"{base}/storage/v1/object/avatars/{u['id']}/avatar.jpg", data=data, timeout=60,
                          headers={"apikey": key, "Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg",
                                   "x-upsert": "true"})
        if r.status_code >= 400:
            raise ValueError("Upload failed. Is the avatars bucket set up, and is your session still valid?")
        url = f"{base}/storage/v1/object/public/avatars/{u['id']}/avatar.jpg?v={int(time.time())}"
        requests.put(f"{base}/auth/v1/user", json={"data": {"avatar_url": url}}, timeout=30,
                     headers={"apikey": key, "Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        u["avatar"] = url
    else:
        st.session_state["avatar_bytes"] = data   # not signed in: kept for this session only


# ---------------------------------------------------------------- sidebar
st.sidebar.markdown("<div class='brand'>Gambia Env GIS</div>", unsafe_allow_html=True)
_pn, _psrc, _pinner = _person()
st.sidebar.markdown(f'<div class="avatar-wrap">{_pinner}<div class="avatar-name">{html.escape(str(_pn))}</div>'
                    f'<div class="avatar-role">Person in charge</div></div>', unsafe_allow_html=True)
with st.sidebar.expander("Change profile photo"):
    _up = st.file_uploader("Profile photo", type=["jpg", "jpeg", "png"], key="avatar_up", label_visibility="collapsed")
    if _up is not None and st.button("Save photo"):
        try:
            save_avatar(_up)
            st.rerun()
        except Exception as e:
            st.error(str(e))
if st.session_state.get("user"):
    _u = st.session_state["user"]
    st.sidebar.caption(f"Signed in as {_u.get('name') or _u['email']}")
    if st.sidebar.button("Sign out"):
        st.session_state.pop("user", None)
        st.rerun()
LAYERS = ["Temp (°C)", "PM10 (µg/m³)", "PM2.5 (µg/m³)", "Dust (µg/m³)", "US AQI",
          "Rain next 7d (mm)", "Humidity (%)", "Wind (km/h)", "Drought index (0-100)", "Composite risk (0-100)"]
layer = st.sidebar.selectbox("Map layer", LAYERS, index=LAYERS.index("Composite risk (0-100)"))
show_sites = st.sidebar.checkbox("Protected areas & wetlands", True)
show_heat = st.sidebar.checkbox("Heatmap surface", True)
show_towns = st.sidebar.checkbox("Towns: flood level & issues", True)
show_inc = st.sidebar.checkbox("Reported incidents", True)
basemap = st.sidebar.selectbox("Basemap", ["OpenStreetMap", "CartoDB positron", "CartoDB dark_matter"], index=1)
up = st.sidebar.file_uploader("Add your own layer (GeoJSON, or CSV with lat, lon, name)",
                              type=["geojson", "json", "csv"])
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()

st.sidebar.markdown("### Satellite layers (NASA GIBS)")
show_ndvi = st.sidebar.checkbox("Vegetation (MODIS NDVI, 8-day)", True)
show_true = st.sidebar.checkbox("True-colour satellite (yesterday)", False)

st.sidebar.markdown("### Fire hotspots (NASA FIRMS)")
firms_key = secret("FIRMS_KEY") or st.sidebar.text_input("FIRMS MAP_KEY", type="password",
                                                          help="Free at firms.modaps.eosdis.nasa.gov/api/map_key")
fire_days = st.sidebar.slider("Days of fire history", 1, 10, 3)

st.sidebar.markdown("### Alert thresholds")
T_HEAT = st.sidebar.number_input("Temperature °C", value=38.0)
T_PM10 = st.sidebar.number_input("PM10 µg/m³", value=150.0)
T_AQI = st.sidebar.number_input("US AQI", value=100.0)
T_RAIN = st.sidebar.number_input("7-day rain mm (flood)", value=80.0)

try:
    df = load_live()
except Exception as e:
    st.error(f"Could not load live data: {e}")
    st.stop()

try:
    tw = load_towns()
except Exception as e:
    tw = None
    st.warning(f"Flood data unavailable: {e}")

try:
    mar = load_marine()
except Exception:
    mar = None
try:
    dr = load_drought()
    df = df.merge(dr[["Region", "Drought index (0-100)"]], on="Region", how="left")
except Exception:
    dr = None
df["Drought index (0-100)"] = df.get("Drought index (0-100)", pd.Series(0, index=df.index)).fillna(0)

TOKEN = (st.session_state.get("user") or {}).get("token")
inc, inc_err = None, None
if SB_ON and TOKEN:
    try:
        inc = load_incidents(TOKEN)
    except Exception as e:
        inc_err = str(e)

farms = None
if SB_ON and TOKEN:
    try:
        farms = load_farms(TOKEN)
    except Exception:
        farms = None

# ---------------------------------------------------------------- header / KPIs
def _logo():
    try:
        return base64.b64encode((Path(__file__).parent / "assets" / "logo.svg").read_bytes()).decode()
    except Exception:
        return ""


OK_C, WATCH_C, ALERT_C, NA_C = "#5be3a1", "#ffc233", "#ff6b5e", "#9fb3b9"

# --- multi-hazard status: flood, heat, air and dust, fire ---
hazards = []  # (name, state, text)
if tw is None:
    hazards.append(("Flood", "na", "Flood: no data"))
else:
    lv = tw["Flood level"].value_counts()
    n_hi, n_w = int(lv.get("Warning", 0) + lv.get("Severe", 0)), int(lv.get("Watch", 0))
    if n_hi:
        hazards.append(("Flood", "alert", f"Flood: {n_hi} warning, {n_w} watch"))
    elif n_w:
        hazards.append(("Flood", "watch", f"Flood: {n_w} town{'s' if n_w > 1 else ''} on watch"))
    else:
        hazards.append(("Flood", "ok", "Flood: no alerts"))

n_heat = int((df["Temp (°C)"] >= T_HEAT).sum())
if n_heat:
    hazards.append(("Heat", "alert", f"Heat: {n_heat} region{'s' if n_heat > 1 else ''} above {T_HEAT:.0f}°C"))
elif df["Temp (°C)"].max() >= T_HEAT - 3:
    hazards.append(("Heat", "watch", f"Heat: up to {df['Temp (°C)'].max():.0f}°C"))
else:
    hazards.append(("Heat", "ok", "Heat: normal"))

n_air = int(((df["PM10 (µg/m³)"] >= T_PM10) | (df["US AQI"] >= T_AQI)).sum())
if n_air:
    hazards.append(("Air and dust", "alert", f"Air and dust: {n_air} region{'s' if n_air > 1 else ''} above limit"))
elif df["PM10 (µg/m³)"].max() >= 0.7 * T_PM10:
    hazards.append(("Air and dust", "watch", f"Air and dust: PM10 up to {df['PM10 (µg/m³)'].max():.0f}"))
else:
    hazards.append(("Air and dust", "ok", "Air and dust: good"))

try:
    n_fire = len(load_fires(firms_key, fire_days)) if firms_key else None
except Exception:
    n_fire = None
if n_fire is None:
    hazards.append(("Fire", "na", "Fire: add FIRMS key"))
elif n_fire:
    hazards.append(("Fire", "watch", f"Fire: {n_fire} hotspot{'s' if n_fire > 1 else ''} in {fire_days} day{'s' if fire_days > 1 else ''}"))
else:
    hazards.append(("Fire", "ok", "Fire: none detected"))

if mar is not None and mar["Max wave (m)"].notna().any():
    wv = float(mar["Max wave (m)"].max())
    lvl = "alert" if wv >= 3 else "watch" if wv >= 2 else "ok"
    hazards.append(("Sea", lvl, f"Sea: waves up to {wv:.1f} m"))
else:
    hazards.append(("Sea", "na", "Sea: no data"))
if dr is not None:
    di = float(dr["Drought index (0-100)"].max())
    lvl = "alert" if di >= 75 else "watch" if di >= 50 else "ok"
    hazards.append(("Drought", lvl, "Drought: " + {"alert": "severe", "watch": "building", "ok": "none"}[lvl]))
else:
    hazards.append(("Drought", "na", "Drought: no data"))

COL = {"ok": OK_C, "watch": WATCH_C, "alert": ALERT_C, "na": NA_C}
active = [(n, st_) for n, st_, _ in hazards if st_ in ("alert", "watch")]
if not active:
    status, dot = "All clear across The Gambia", OK_C
else:
    status = ", ".join(f"{n.lower()} {'alert' if st_ == 'alert' else 'watch'}" for n, st_ in active)
    status = status[0].upper() + status[1:]
    dot = ALERT_C if any(st_ == "alert" for _, st_ in active) else WATCH_C
chips = "".join(f'<span class="chip"><i style="background:{COL[st_]}"></i>{t}</span>' for _, st_, t in hazards)

_hn, _hsrc, _hinner = _person()
_person_html = (f'<div class="hero-person">{_hinner}<div class="hero-pname">{html.escape(str(_hn))}</div>'
                f'<div class="hero-prole">Person in charge</div></div>'
                if (_hsrc or st.session_state.get("user")) else "")
_lg = _logo()
_img = f'<img src="data:image/svg+xml;base64,{_lg}" alt="">' if _lg else ""
st.markdown(
    f'<div class="hero"><div class="hero-row">{_img}<div>'
    f'<div class="hero-org">{html.escape(ORG)}: Environmental Monitor</div>'
    f'<div class="hero-status"><span class="dot" style="background:{dot}"></span>{status}</div>'
    f'<div class="hero-sub">Updated {datetime.now():%H:%M} from Open-Meteo and NASA for 15 towns in 8 regions. '
    f'These are forecast and satellite indicators, not official warnings.</div></div>{_person_html}</div>'
    f'<div class="chips">{chips}</div></div>',
    unsafe_allow_html=True)


def _short(col, fn):
    return df.loc[getattr(df[col], fn)(), "Region"].split(" (")[0]


def tile(label, value, note, color):
    return (f'<div class="stat" style="--c:{color}"><div class="l">{label}</div>'
            f'<div class="v">{value}</div><div class="d">{note}</div></div>')


top = df.loc[df["Composite risk (0-100)"].idxmax()]
st.markdown('<div class="stats">' + "".join([
    tile("Average temperature", f"{df['Temp (°C)'].mean():.1f}°C", f"Hottest: {_short('Temp (°C)', 'idxmax')}", "#E08A00"),
    tile("Average PM10", f"{df['PM10 (µg/m³)'].mean():.0f} µg/m³", f"Dustiest: {_short('PM10 (µg/m³)', 'idxmax')}. WHO 24h guide: 45", "#A67C52"),
    tile("Average PM2.5", f"{df['PM2.5 (µg/m³)'].mean():.0f} µg/m³", "WHO 24h guide: 15", "#7B5EA7"),
    tile("Rain next 7 days", f"{df['Rain next 7d (mm)'].mean():.0f} mm", f"Wettest: {_short('Rain next 7d (mm)', 'idxmax')}", "#1C6DD0"),
    tile("Highest combined risk", top["Region"].split(" (")[0], f"{top['Composite risk (0-100)']:.0f} out of 100", "#C8372D"),
]) + "</div>", unsafe_allow_html=True)

alerts = []
for _, r in df.iterrows():
    for col, thr, label in [("Temp (°C)", T_HEAT, "Extreme heat"), ("PM10 (µg/m³)", T_PM10, "High dust/PM10"),
                            ("US AQI", T_AQI, "Poor air quality"), ("Rain next 7d (mm)", T_RAIN, "Flood risk")]:
        if r[col] >= thr:
            alerts.append({"region": r["Region"], "type": label, "value": float(r[col]), "threshold": float(thr)})
if tw is not None:
    for _, r in tw[tw["Flood level"].isin(["Warning", "Severe"])].iterrows():
        alerts.append({"region": r["Town"], "type": f"Flood {r['Flood level'].lower()}",
                       "value": float(r["Flood risk (0-100)"]), "threshold": 50.0})
if alerts:
    with st.expander(f"🚨 {len(alerts)} active alert(s)", expanded=True):
        st.dataframe(pd.DataFrame(alerts), hide_index=True, use_container_width=True)
        if secret("SUPABASE_URL") and secret("SUPABASE_KEY"):
            if st.button("Log alerts to Supabase"):
                try:
                    log_alerts(alerts)
                    st.success("Logged.")
                except Exception as e:
                    st.error(f"Supabase error: {e}")
        else:
            st.caption("Add SUPABASE_URL and SUPABASE_KEY to secrets to log alerts.")
else:
    st.success("No alerts: all regions are below your thresholds.")

fires = None
if firms_key:
    try:
        fires = load_fires(firms_key, fire_days)
        st.metric("🔥 Fire hotspots detected", len(fires), help=f"VIIRS, last {fire_days} day(s)")
    except Exception as e:
        st.warning(f"FIRMS unavailable: {e}")

tab_map, tab_flood, tab_land, tab_an, tab_cmp, tab_s2, tab_farm, tab_dq, tab_inc, tab_clim, tab_data = st.tabs(["🗺️ Map", "🌊 Flooding & town issues", "🌾 Drought & coast", "📊 Analysis", "🕒 Compare over time", "🛰️ Sentinel-2", "🌱 Farm monitor", "🧪 Data quality", "📝 Incident reports", "📈 Climate history", "📋 Data & export"])

# ---------------------------------------------------------------- map
with tab_map:
    m = folium.Map(location=[13.45, -15.4], zoom_start=8, tiles=basemap, control_scale=True)
    Fullscreen().add_to(m)
    MiniMap(toggle_display=True).add_to(m)

    vmin, vmax = float(df[layer].min()), float(df[layer].max())
    if vmin == vmax:
        vmax = vmin + 1
    cmap = cm.LinearColormap(["#2ecc71", "#f1c40f", "#e74c3c"], vmin=vmin, vmax=vmax, caption=layer)
    cmap.add_to(m)

    fg = folium.FeatureGroup(name=f"Regions: {layer}", show=True)
    for _, r in df.iterrows():
        popup = (f"<b>{r['Region']}</b><br>" +
                 "<br>".join(f"{c}: {r[c]:.1f}" for c in LAYERS))
        folium.CircleMarker([r.lat, r.lon], radius=14 + 14 * (r[layer] - vmin) / (vmax - vmin),
                            color="#222", weight=1, fill=True, fill_color=cmap(r[layer]),
                            fill_opacity=0.8, popup=folium.Popup(popup, max_width=260),
                            tooltip=f"{r['Region']}: {r[layer]:.1f}").add_to(fg)
    fg.add_to(m)

    if show_heat:
        HeatMap(df[["lat", "lon", layer]].values.tolist(), radius=60, blur=45,
                min_opacity=0.25, name="Heat surface").add_to(m)

    if show_towns and tw is not None:
        tg = folium.FeatureGroup(name="Towns: flood level")
        for _, r in tw.iterrows():
            issues = "".join(f"<li>{i}</li>" for i in r["Issues"].split("; "))
            pop = (f"<b>{r['Town']}</b> ({r['Region']})<br>Flood level: <b>{r['Flood level']}</b> "
                   f"(risk {r['Flood risk (0-100)']:.0f}/100)<br>Rain 7d: {r['Rain 7d (mm)']} mm · "
                   f"river {r['River discharge (m³/s)']} m³/s<br><b>Issues</b><ul>{issues}</ul>")
            folium.CircleMarker([r.lat, r.lon], radius=7 + r["Flood risk (0-100)"] / 10, color="#1b4f72", weight=2,
                                fill=True, fill_color=LEVEL_COLORS[r["Flood level"]], fill_opacity=0.9,
                                popup=folium.Popup(pop, max_width=320),
                                tooltip=f"{r['Town']}: {r['Flood level']}").add_to(tg)
        tg.add_to(m)

    if show_inc and inc is not None and len(inc) and {"lat", "lon"} <= set(inc.columns):
        ig = folium.FeatureGroup(name="Reported incidents")
        for _, r in inc.iterrows():
            _ph = r.get("photo_url")
            ph = f'<br><img src="{_ph}" width="240">' if isinstance(_ph, str) and _ph else ""
            pop = (f"<b>{r.get('type', '')}</b> ({r.get('severity', '')})<br>{r.get('town', '')}<br>"
                   f"{r.get('description', '') or ''}{ph}<br>Houses: {r.get('houses_affected', 0)}, "
                   f"people: {r.get('people_affected', 0)}<br><small>{str(r.get('created_at', ''))[:10]}</small>")
            folium.CircleMarker([r["lat"], r["lon"]], radius=8, color="#222", weight=2, fill=True,
                                fill_color=SEV_COLORS.get(r.get("severity"), "#888"), fill_opacity=0.95,
                                popup=folium.Popup(pop, max_width=280),
                                tooltip=f"{r.get('type', '')}: {r.get('severity', '')}").add_to(ig)
        ig.add_to(m)

    if farms is not None and len(farms) and "geojson" in farms.columns:
        fg2 = folium.FeatureGroup(name="My farms")
        for _, r in farms.iterrows():
            try:
                folium.GeoJson(json.loads(r["geojson"]), tooltip=f"{r['name']} ({r['crop']})",
                               style_function=lambda _x: {"color": "#1F8A5B", "weight": 3, "fillOpacity": 0.25}).add_to(fg2)
            except Exception:
                pass
        fg2.add_to(m)

    G = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
    if show_ndvi:
        folium.TileLayer(f"{G}/MODIS_Terra_NDVI_8Day/default/default/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.png",
                         attr="NASA GIBS / MODIS", name="MODIS NDVI (8-day)", overlay=True,
                         opacity=0.65, max_native_zoom=9).add_to(m)
    if show_true:
        d = (date.today() - timedelta(days=1)).isoformat()
        folium.TileLayer(f"{G}/MODIS_Terra_CorrectedReflectance_TrueColor/default/{d}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.jpg",
                         attr="NASA GIBS / MODIS", name="True colour (MODIS)", overlay=True,
                         opacity=0.9, max_native_zoom=9).add_to(m)

    if fires is not None and len(fires):
        ff = folium.FeatureGroup(name="Fire hotspots (VIIRS)")
        for _, r in fires.iterrows():
            folium.CircleMarker([r["latitude"], r["longitude"]], radius=4 + min(float(r.get("frp", 1)), 20) / 4,
                                color="#c0392b", fill=True, fill_color="#e67e22", fill_opacity=0.85,
                                tooltip=f"{r.get('acq_date', '')} {r.get('acq_time', '')} · FRP {r.get('frp', '')} MW").add_to(ff)
        ff.add_to(m)

    if show_sites:
        sg = folium.FeatureGroup(name="Protected areas & wetlands")
        for n, la, lo, t, c in SITES:
            folium.Marker([la, lo], tooltip=f"{n} ({t})", popup=f"<b>{n}</b><br>{t}",
                          icon=folium.Icon(color=c, icon="leaf", prefix="fa")).add_to(sg)
        sg.add_to(m)

    if up is not None:
        try:
            ug = folium.FeatureGroup(name=f"Uploaded: {up.name}")
            if up.name.lower().endswith(".csv"):
                u = pd.read_csv(up)
                u.columns = [c.lower() for c in u.columns]
                for _, r in u.iterrows():
                    folium.CircleMarker([r["lat"], r["lon"]], radius=6, color="#8e44ad", fill=True,
                                        tooltip=str(r.get("name", ""))).add_to(ug)
            else:
                folium.GeoJson(json.load(up), name=up.name).add_to(ug)
            ug.add_to(m)
        except Exception as e:
            st.warning(f"Could not read uploaded layer: {e}")

    folium.LayerControl(collapsed=False).add_to(m)
    out = st_folium(m, height=580, use_container_width=True, returned_objects=["last_clicked"])
    clk = (out or {}).get("last_clicked")
    if clk:
        try:
            st.session_state["picked"] = (clk["lat"], clk["lng"])
            x = flood_metrics([(clk["lat"], clk["lng"])])[0]
            st.info(f"📍 {clk['lat']:.4f}, {clk['lng']:.4f}: rain next 7d {x['rain7']:.0f} mm "
                    f"(max {x['rain_max']:.0f} mm/day) · river discharge {x['discharge']:.1f} m³/s "
                    f"({x['ratio']:.1f}× normal) · flood hazard {x['hazard'] * 100:.0f}/100")
            try:
                nb = count_buildings(round(clk["lat"], 3), round(clk["lng"], 3))
                st.caption(f"Exposure: about {nb:,} mapped buildings within 1 km (OpenStreetMap; coverage varies).")
            except Exception:
                st.caption("Exposure estimate unavailable right now.")
        except Exception as e:
            st.warning(f"Could not check that point: {e}")
    else:
        st.caption("Click anywhere on the map to check the 7-day flood hazard at that point.")

    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(df.sort_values(layer), x=layer, y="Region", orientation="h",
                           color=layer, color_continuous_scale="RdYlGn_r", title=f"{layer} by region"),
                    use_container_width=True)
    c2.plotly_chart(px.scatter(df, x="Temp (°C)", y="PM10 (µg/m³)", size="Rain next 7d (mm)",
                               color="Composite risk (0-100)", hover_name="Region",
                               color_continuous_scale="RdYlGn_r", title="Heat vs dust (bubble = rain)"),
                    use_container_width=True)

# ---------------------------------------------------------------- flooding
with tab_flood:
    if tw is None:
        st.info("Flood data is unavailable right now. Try Refresh data.")
    else:
        a = st.columns(4)
        a[0].metric("Towns monitored", len(tw))
        a[1].metric("Watch or higher", int((tw["Flood level"] != "Low").sum()))
        a[2].metric("Max 7d rain", f"{tw['Rain 7d (mm)'].max():.0f} mm")
        hi = tw.loc[tw["Flood risk (0-100)"].idxmax()]
        a[3].metric("Highest flood risk", hi["Town"], f"{hi['Flood risk (0-100)']:.0f}/100")

        heat = pd.DataFrame(list(tw["_rain"]), index=tw["Town"], columns=tw.iloc[0]["_dates"])
        st.plotly_chart(px.imshow(heat, aspect="auto", color_continuous_scale="Blues",
                                  labels=dict(color="mm"), title="Forecast daily rainfall by town (mm)"),
                        use_container_width=True)
        st.plotly_chart(px.bar(tw.sort_values("Flood risk (0-100)"), x="Flood risk (0-100)", y="Town",
                               orientation="h", color="Flood level", color_discrete_map=LEVEL_COLORS,
                               hover_data=["Region", "Rain 7d (mm)", "Exposure (1-5)"],
                               title="Flood risk by town (60% forecast hazard + 40% exposure)"),
                        use_container_width=True)
        st.dataframe(tw.drop(columns=["lat", "lon", "_rain", "_dates"]), hide_index=True,
                     use_container_width=True,
                     column_config={"Issues": st.column_config.TextColumn(width="large")})
        st.markdown("##### Exposure: mapped buildings within 1 km")
        if st.button("Estimate for all towns"):
            res = {}
            with st.spinner("Counting buildings from OpenStreetMap…"):
                for _, r in tw.iterrows():
                    try:
                        res[r["Town"]] = count_buildings(round(r["lat"], 3), round(r["lon"], 3))
                    except Exception:
                        res[r["Town"]] = None
                    time.sleep(0.5)
            st.session_state["bld"] = res
        if st.session_state.get("bld"):
            ex = tw[["Town", "Flood level", "Flood risk (0-100)"]].copy()
            ex["Buildings within 1 km"] = ex["Town"].map(st.session_state["bld"])
            st.plotly_chart(px.bar(ex.sort_values("Buildings within 1 km"), x="Buildings within 1 km", y="Town",
                                   orientation="h", color="Flood level", color_discrete_map=LEVEL_COLORS,
                                   title="Mapped buildings near each town, coloured by flood level"),
                            use_container_width=True)
            st.caption("OpenStreetMap coverage varies, so a low count can mean unmapped buildings. "
                       "This is an exposure proxy, not a population count.")
        pick = st.selectbox("Problems and issues in", tw["Town"])
        row = tw[tw["Town"] == pick].iloc[0]
        st.markdown(f"**{pick}** ({row['Region']}) · flood level **{row['Flood level']}**")
        st.markdown("\n".join(f"- {i}" for i in row["Issues"].split("; ")))
        st.caption("Hazard = max of 7-day rain, peak daily rain, and GloFAS river discharge vs normal. "
                   "Exposure and issue lists are indicative general assessments, not official data. "
                   "Tides, storm surge and street-level drainage are not modelled; confirm with NDMA / NEA / DWR.")

# ---------------------------------------------------------------- drought & coast
with tab_land:
    st.subheader("Drought indicators by region")
    if dr is None:
        st.info("Drought data is unavailable right now.")
    else:
        st.plotly_chart(px.bar(dr.sort_values("Drought index (0-100)"), x="Drought index (0-100)", y="Region",
                               orientation="h", color="Drought index (0-100)", color_continuous_scale="YlOrBr",
                               range_color=[0, 100], title="Drought index (dry days + soil moisture)"),
                        use_container_width=True)
        st.dataframe(dr, hide_index=True, use_container_width=True)
    st.subheader("Sea conditions (next 7 days)")
    if mar is None or not mar["Max wave (m)"].notna().any():
        st.info("Marine data is unavailable for these points right now.")
    else:
        st.dataframe(mar.drop(columns=["lat", "lon"]), hide_index=True, use_container_width=True)
    st.caption("Indicative only. Drought index = 50% dry days in the last 14 + 50% low soil moisture (0-7 cm). "
               "Sea status: watch from 2 m waves, alert from 3 m. Offshore model points, not tide-gauge readings.")

# ---------------------------------------------------------------- analysis
with tab_an:
    AN = ["Temp (°C)", "Humidity (%)", "Wind (km/h)", "Rain next 7d (mm)", "PM10 (µg/m³)", "PM2.5 (µg/m³)",
          "Dust (µg/m³)", "US AQI", "Drought index (0-100)", "Composite risk (0-100)"]
    short = df["Region"].str.split(" (", regex=False).str[0]
    raw = df[AN]
    norm = (raw - raw.min()) / (raw.max() - raw.min()).replace(0, 1)

    st.subheader("1. Which regions stand out?")
    fig = px.imshow(norm.values, x=AN, y=short, color_continuous_scale="YlOrRd", aspect="auto",
                    labels=dict(color="Relative level"), title="All indicators by region (0 = lowest region, 1 = highest)")
    fig.update_traces(customdata=raw.values, hovertemplate="%{y}<br>%{x}: %{customdata:.1f}<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        sel = st.multiselect("Compare regions (radar)", list(short), default=list(short[:3]), key="radar")
        fr = pgo.Figure()
        for nm in sel:
            vals = norm.loc[short[short == nm].index[0]].tolist()
            fr.add_trace(pgo.Scatterpolar(r=vals + vals[:1], theta=AN + AN[:1], fill="toself", name=nm, opacity=0.55))
        fr.update_layout(polar=dict(radialaxis=dict(range=[0, 1], showticklabels=False)), title="Region profile comparison")
        st.plotly_chart(fr, use_container_width=True)
    with c2:
        comp = pd.DataFrame({"Region": short,
                             "Heat": ((df["Temp (°C)"] - 30) / 10).clip(0, 1) * 100 / 3,
                             "Air (PM10)": (df["PM10 (µg/m³)"] / 150).clip(0, 1) * 100 / 3,
                             "Rain (flood)": (df["Rain next 7d (mm)"] / 80).clip(0, 1) * 100 / 3}
                            ).melt("Region", var_name="Driver", value_name="Points")
        st.plotly_chart(px.bar(comp, x="Points", y="Region", color="Driver", orientation="h",
                               title="What drives each region's composite risk (max 100)"), use_container_width=True)

    st.subheader("2. How is one town changing?")
    town_sel = st.selectbox("Town", list(TOWNS), key="an_town")
    try:
        d, h = load_timeline(TOWNS[town_sel]["lat"], TOWNS[town_sel]["lon"])
        ft = make_subplots(specs=[[{"secondary_y": True}]])
        ft.add_trace(pgo.Bar(x=d["time"], y=d["precipitation_sum"], name="Rain (mm)",
                             marker_color=["#9db7d5" if p == "Past" else "#1C6DD0" for p in d["Period"]]), secondary_y=False)
        ft.add_trace(pgo.Scatter(x=d["time"], y=d["temperature_2m_max"], name="Max temp (°C)", line=dict(color="#E08A00")), secondary_y=True)
        ft.add_trace(pgo.Scatter(x=d["time"], y=d["temperature_2m_min"], name="Min temp (°C)", line=dict(color="#7B5EA7")), secondary_y=True)
        ft.update_yaxes(title_text="Rain (mm)", secondary_y=False)
        ft.update_yaxes(title_text="Temperature (°C)", secondary_y=True)
        ft.update_layout(title=f"{town_sel}: last 7 days and next 7 days (pale bars = past rain)")
        st.plotly_chart(ft, use_container_width=True)
        fa_ = px.line(h, x="time", y=["pm10", "pm2_5", "dust"], title=f"{town_sel}: air quality and dust, hourly",
                      labels={"value": "µg/m³", "time": "", "variable": ""})
        st.plotly_chart(fa_, use_container_width=True)
        st.plotly_chart(px.bar(d, x="time", y="wind_speed_10m_max", color="Period",
                               title=f"{town_sel}: daily maximum wind (km/h)",
                               labels={"wind_speed_10m_max": "km/h", "time": ""}), use_container_width=True)
    except Exception as e:
        st.warning(f"Timeline unavailable: {e}")

    st.subheader("3. How do regions compare over the last 12 months?")
    regs = st.multiselect("Regions (up to 4)", list(REGIONS), default=list(REGIONS)[:3], key="cmp")
    frames = []
    for r in regs[:4]:
        try:
            h12 = load_history(*REGIONS[r])
            mth = h12.set_index("time").resample("MS").agg({"precipitation_sum": "sum", "temperature_2m_max": "mean"}).reset_index()
            mth["Region"] = r.split(" (")[0]
            frames.append(mth)
        except Exception:
            pass
    if frames:
        allm = pd.concat(frames)
        c3, c4 = st.columns(2)
        c3.plotly_chart(px.bar(allm, x="time", y="precipitation_sum", color="Region", barmode="group",
                               title="Monthly rainfall (mm)", labels={"precipitation_sum": "mm", "time": ""}),
                        use_container_width=True)
        c4.plotly_chart(px.line(allm, x="time", y="temperature_2m_max", color="Region", markers=True,
                                title="Average daily maximum temperature by month (°C)",
                                labels={"temperature_2m_max": "°C", "time": ""}), use_container_width=True)

    st.subheader("4. Towns: rain, exposure and flood level")
    if tw is not None:
        st.plotly_chart(px.scatter(tw, x="Rain 7d (mm)", y="Max daily rain (mm)", size="Exposure (1-5)", size_max=28,
                                   color="Flood level", color_discrete_map=LEVEL_COLORS, hover_name="Town", text="Town",
                                   title="Rain total vs heaviest day (bubble size = exposure)"), use_container_width=True)

    st.subheader("5. Forecast vs what was reported")
    if inc is not None and len(inc) and "created_at" in inc.columns:
        t = inc.copy()
        t["created_at"] = pd.to_datetime(t["created_at"], utc=True)
        wk = t.groupby([pd.Grouper(key="created_at", freq="W"), "severity"]).size().reset_index(name="Reports")
        c5, c6 = st.columns(2)
        c5.plotly_chart(px.bar(wk, x="created_at", y="Reports", color="severity", color_discrete_map=SEV_COLORS,
                               title="Incident reports per week", labels={"created_at": ""}), use_container_width=True)
        cnt = t["town"].value_counts().rename_axis("Town").reset_index(name="Reports")
        if tw is not None:
            mm = tw.merge(cnt, on="Town", how="left").fillna({"Reports": 0})
            c6.plotly_chart(px.scatter(mm, x="Flood risk (0-100)", y="Reports", text="Town", color="Flood level",
                                       color_discrete_map=LEVEL_COLORS, title="Forecast flood risk vs reports"),
                            use_container_width=True)
    else:
        st.info("Incident analysis appears here once reports are submitted (sign-in and Supabase required).")

# ---------------------------------------------------------------- compare over time
with tab_cmp:
    opts = {n: (t["lat"], t["lon"]) for n, t in TOWNS.items()}
    if farms is not None and len(farms):
        for _, r in farms.iterrows():
            opts[f"Farm: {r['name']}"] = (float(r["lat"]), float(r["lon"]))
    with st.expander("Add a custom point (optional)"):
        cn = st.text_input("Name", "My point", key="cmp_cn")
        cla = st.number_input("Latitude", value=13.45, format="%.4f", key="cmp_cla")
        clo = st.number_input("Longitude", value=-15.4, format="%.4f", key="cmp_clo")
        if st.checkbox("Include this point", key="cmp_cinc"):
            opts[cn] = (cla, clo)

    st.subheader("1. Compare places over time")
    m1, m2, m3 = st.columns([2, 1.5, 1])
    sel = m1.multiselect("Places (up to 4)", list(opts), default=["Banjul", "Basse"], key="cmp_sel")
    metric = m2.selectbox("What to compare", list(METRICS_TS) + [NDVI_LABEL], key="cmp_metric")
    yrs = m3.select_slider("Years back", [1, 2, 3, 5, 10], value=5, key="cmp_yrs")
    first_this = date.today().replace(day=1)
    end_d = first_this - timedelta(days=1)
    start_d = date(first_this.year - yrs, first_this.month, 1)

    if metric == NDVI_LABEL:
        st.caption("Reads a 1 km square around each place from up to 10 Sentinel-2 scenes (cloud under 40%). "
                   "This is slower, and the rainy season (about June to October) often has no clear scenes.")
        if sel and st.button("Load NDVI for these places", type="primary"):
            frames = []
            with st.spinner("Reading satellite scenes…"):
                for nm in sel[:3]:
                    la_, lo_ = opts[nm]
                    gj = json.dumps(square_geom(la_, lo_, 100.0), sort_keys=True)
                    try:
                        _, fs = s2_search(la_, lo_, 0.6, str(start_d), str(end_d), 40)
                    except Exception:
                        fs = []
                    for f_ in fs[::max(1, len(fs) // 10)][:10]:
                        try:
                            frames.append({**farm_ndvi(f_["id"], gj, f_), "Place": nm})
                        except Exception:
                            pass
            st.session_state["cmp_ndvi"] = pd.DataFrame(frames)
        nd = st.session_state.get("cmp_ndvi")
        if nd is not None and len(nd):
            nd = nd[nd["mean_ndvi"].notna() & (nd["valid_pct"] >= 30)].sort_values("date")
            st.plotly_chart(px.line(nd, x="date", y="mean_ndvi", color="Place", markers=True,
                                    title="Greenness over time (mean NDVI, clear pixels)", labels={"mean_ndvi": "NDVI", "date": ""}),
                            use_container_width=True)
        elif nd is not None:
            st.warning("No clear scenes found for these places and dates.")
    else:
        mode = st.radio("View", ["Places side by side", "One place, year over year", "One place, difference from normal"],
                        horizontal=True, key="cmp_mode")
        smooth = st.checkbox("Smooth with a 3-month average", key="cmp_smooth")
        how = METRICS_TS[metric][1]
        series = {}
        for nm in sel[:4]:
            try:
                series[nm] = load_monthly(opts[nm][0], opts[nm][1], str(start_d), str(end_d), metric)
            except Exception as e:
                st.warning(f"{nm}: could not load ({e})")
        if series:
            if mode == "Places side by side":
                allm = pd.concat([d_.assign(Place=n_) for n_, d_ in series.items()])
                if smooth:
                    allm["value"] = allm.groupby("Place")["value"].transform(lambda x: x.rolling(3, center=True, min_periods=1).mean())
                st.plotly_chart(px.line(allm, x="month", y="value", color="Place", markers=True, title=metric,
                                        labels={"value": metric, "month": ""}), use_container_width=True)
                rows_ = []
                for n_, d_ in series.items():
                    bc = block_change(d_, how)
                    row = {"Place": n_, "Latest 12 months": None, "Earlier years (average)": None, "Change (%)": None, "Trend per decade": None}
                    if bc:
                        row.update({"Latest 12 months": round(bc[0], 2), "Earlier years (average)": round(bc[1], 2),
                                    "Change (%)": None if bc[2] is None else round(bc[2], 1)})
                    dd = d_.dropna()
                    if how == "mean" and len(dd) >= 60:
                        yrs_ = dd["month"].dt.year + (dd["month"].dt.month - 1) / 12
                        row["Trend per decade"] = round(float(np.polyfit(yrs_, dd["value"], 1)[0] * 10), 2)
                    rows_.append(row)
                st.dataframe(pd.DataFrame(rows_), hide_index=True, use_container_width=True)
                st.caption("Latest 12 months vs the average of earlier 12-month periods (totals for rain and evapotranspiration, "
                           "averages for the rest). Trend per decade needs 5+ years and is only a rough guide: natural year-to-year "
                           "variation is large in The Gambia, so a short record can mislead.")
            else:
                nm1 = next(iter(series))
                d1 = series[nm1].dropna().copy()
                d1["Year"] = d1["month"].dt.year.astype(str)
                d1["Month"] = d1["month"].dt.month
                if mode == "One place, year over year":
                    st.plotly_chart(px.line(d1, x="Month", y="value", color="Year", markers=True,
                                            title=f"{nm1}: {metric}, each year", labels={"value": metric}), use_container_width=True)
                else:
                    clim = d1.groupby("Month")["value"].transform("mean")
                    d1["Difference from normal"] = d1["value"] - clim
                    d1["Direction"] = np.where(d1["Difference from normal"] >= 0, "Above normal", "Below normal")
                    st.plotly_chart(px.bar(d1, x="month", y="Difference from normal", color="Direction",
                                           color_discrete_map={"Above normal": "#1C6DD0", "Below normal": "#C8372D"},
                                           title=f"{nm1}: {metric}, difference from the {yrs}-year average for that month",
                                           labels={"month": ""}), use_container_width=True)
                st.caption("The first selected place is shown. Normal = the average for that calendar month over the period chosen.")
        elif sel:
            st.info("No data could be loaded. Try again in a minute.")

    st.subheader("2. See how one place changed between two dates (Sentinel-2)")
    try:
        import sentinel  # noqa: F401
        s2c = True
    except Exception as e:
        s2c = False
        st.info(f"Needs the rasterio package. Details: {e}")
    if s2c:
        b1, b2, b3 = st.columns([1.3, 1, 1])
        place = b1.selectbox("Place", list(opts), key="chg_place")
        halfc = b2.select_slider("Area half-width (km)", [1, 2, 5, 10], value=2, key="chg_half")
        cloudc = b3.slider("Max scene cloud (%)", 5, 80, 30, key="chg_cloud")
        d1_, d2_ = st.columns(2)
        before = d1_.date_input("Before (date range)", value=(date.today() - timedelta(days=425), date.today() - timedelta(days=365)), key="chg_before")
        after = d2_.date_input("After (date range)", value=(date.today() - timedelta(days=60), date.today()), key="chg_after")
        st.caption("Compare the same season in different years (for example dry season to dry season), "
                   "or the vegetation will differ just because of the time of year.")
        if st.button("Compare these two periods", type="primary"):
            if len(before) != 2 or len(after) != 2:
                st.warning("Pick a start and an end date for both ranges.")
            else:
                la_, lo_ = opts[place]
                try:
                    bb, fb = s2_search(la_, lo_, halfc, str(before[0]), str(before[1]), cloudc)
                    _, fa = s2_search(la_, lo_, halfc, str(after[0]), str(after[1]), cloudc)
                    if not fb or not fa:
                        st.warning("No clear scene in " + ("the before period." if not fb else "the after period.") +
                                   " Widen the dates or raise the cloud limit.")
                    else:
                        f1 = min(fb, key=lambda f: f["properties"].get("eo:cloud_cover", 100))
                        f2 = min(fa, key=lambda f: f["properties"].get("eo:cloud_cover", 100))
                        st.session_state["chg_res"] = (place, s2_change(f1["id"], f2["id"], tuple(round(x, 4) for x in bb), 500, f1, f2))
                except Exception as e:
                    st.error(f"Could not compare: {e}")
        cr = st.session_state.get("chg_res")
        if cr and cr[0] == place:
            r = cr[1]
            k = st.columns(5)
            k[0].metric("Before", r["before_date"], f"{r['before_cloud']:.0f}% cloud" if r["before_cloud"] is not None else None, delta_color="off")
            k[1].metric("After", r["after_date"], f"{r['after_cloud']:.0f}% cloud" if r["after_cloud"] is not None else None, delta_color="off")
            k[2].metric("Mean NDVI change", r["mean_change"] if r["mean_change"] is not None else "n/a",
                        f"{r['mean_before']} to {r['mean_after']}", delta_color="off")
            k[3].metric("Greener area", f"{r['gain_pct']}%" if r["gain_pct"] is not None else "n/a", help="Share of clear pixels where NDVI rose by more than 0.1")
            k[4].metric("Browner area", f"{r['loss_pct']}%" if r["loss_pct"] is not None else "n/a", help="Share of clear pixels where NDVI fell by more than 0.1")
            la_, lo_ = opts[place]
            mc = folium.Map(location=[la_, lo_], zoom_start={1: 13, 2: 12, 5: 11, 10: 10}[halfc], tiles="CartoDB positron")
            folium.raster_layers.ImageOverlay(image=r["diff_rgba"], bounds=r["bounds"], opacity=0.9, name="Change (after minus before)").add_to(mc)
            folium.raster_layers.ImageOverlay(image=r["before_rgba"], bounds=r["bounds"], opacity=0.85, name="Before NDVI", show=False).add_to(mc)
            folium.raster_layers.ImageOverlay(image=r["after_rgba"], bounds=r["bounds"], opacity=0.85, name="After NDVI", show=False).add_to(mc)
            folium.LayerControl(collapsed=False).add_to(mc)
            st_folium(mc, height=480, use_container_width=True, returned_objects=[], key="chg_map")
            st.caption("Green = vegetation increased, red = decreased, near white = little change. Transparent = cloud or no data. "
                       "Differences can also come from haze, sun angle, harvest, burning or flooding, so check on the ground. "
                       f"Read in {r['seconds']} s.")
            dv = r["diff"][~pd.isna(r["diff"])]
            if len(dv):
                st.plotly_chart(px.histogram(x=dv.ravel(), nbins=40, title="Distribution of NDVI change (after minus before)",
                                             labels={"x": "NDVI change"}), use_container_width=True)

# ---------------------------------------------------------------- sentinel-2
with tab_s2:
    try:
        import sentinel  # noqa: F401
        s2_ok = True
    except Exception as e:
        s2_ok = False
        st.info(f"Sentinel-2 needs the rasterio package (see requirements.txt). Details: {e}")
    if s2_ok:
        a, b, c, d = st.columns(4)
        tn = a.selectbox("Town", list(TOWNS), key="s2_town")
        half = b.select_slider("Area half-width (km)", [2, 5, 10, 20], value=5, key="s2_half")
        days = c.select_slider("Look back (days)", [30, 60, 120, 365], value=120, key="s2_days")
        cloud = d.slider("Max scene cloud cover (%)", 5, 80, 30, key="s2_cloud")
        detail = st.radio("Detail", ["Fast (about 100 m)", "Medium (about 40 m)", "Full (10 m)"], index=1, horizontal=True)
        max_px = {"Fast (about 100 m)": 250, "Medium (about 40 m)": 500, "Full (10 m)": 1200}[detail]
        tt = TOWNS[tn]
        try:
            t0 = time.perf_counter()
            bbox, feats = s2_search(tt["lat"], tt["lon"], half, str(date.today() - timedelta(days=days)),
                                    str(date.today()), cloud)
            t_search = time.perf_counter() - t0
        except Exception as e:
            bbox, feats, t_search = None, [], 0
            st.error(f"Scene search failed: {e}")
        if bbox and not feats:
            st.warning("No scenes under that cloud limit in this period. Raise the cloud limit or look back further. "
                       "Heavy cloud is normal in the rainy season (about June to October).")
        if feats:
            rows = [{"Date": f["properties"]["datetime"][:10], "Scene cloud (%)": round(f["properties"].get("eo:cloud_cover", 0), 1),
                     "Scene": f["id"]} for f in feats]
            sc = pd.DataFrame(rows)
            st.caption(f"{len(feats)} scene(s) found in {t_search:.1f} s. Sentinel-2 passes each place about every 5 days.")
            pick_i = st.selectbox("Scene", range(len(sc)), format_func=lambda i: f"{sc.Date[i]} ({sc['Scene cloud (%)'][i]:.0f}% cloud)")
            f_sel = feats[pick_i]
            bkey = tuple(round(x, 4) for x in bbox)
            if st.button("Load this scene", type="primary"):
                try:
                    st.session_state["s2_res"] = s2_scene(f_sel["id"], bkey, max_px, f_sel)
                except Exception as e:
                    st.error(f"Could not read this scene: {e}")
            res = st.session_state.get("s2_res")
            if res and res["id"] == f_sel["id"]:
                k = st.columns(5)
                k[0].metric("Mean NDVI", res["mean_ndvi"] if res["mean_ndvi"] is not None else "n/a")
                k[1].metric("Dense vegetation", f"{res['veg_pct']}%" if res["veg_pct"] is not None else "n/a", help="Share of clear pixels with NDVI above 0.3")
                k[2].metric("Cloud in view", f"{res['cloud_pct']}%")
                k[3].metric("Usable pixels", f"{res['usable_pct']}%")
                k[4].metric("Load time", f"{res['seconds']} s", f"{res['pixels']:,} pixels")
                m2 = folium.Map(location=[tt["lat"], tt["lon"]], zoom_start={2: 13, 5: 12, 10: 11, 20: 10}[half], tiles="CartoDB positron")
                folium.raster_layers.ImageOverlay(image=res["rgb"], bounds=res["bounds"], opacity=0.95, name="True colour").add_to(m2)
                folium.raster_layers.ImageOverlay(image=res["ndvi_rgba"], bounds=res["bounds"], opacity=0.85, name="NDVI").add_to(m2)
                folium.LayerControl(collapsed=False).add_to(m2)
                st_folium(m2, height=520, use_container_width=True, returned_objects=[])
                st.caption("NDVI colours: blue = water, brown = bare soil, yellow = sparse, green = dense vegetation. "
                           "Clouds, shadows and missing pixels are transparent. Overlay position is approximate.")
                vv = res["ndvi"][~pd.isna(res["ndvi"])]
                if len(vv):
                    st.plotly_chart(px.histogram(x=vv.ravel(), nbins=40, title="NDVI distribution (clear pixels)",
                                                 labels={"x": "NDVI"}), use_container_width=True)
            st.markdown("##### NDVI trend over the scenes found")
            if st.button("Compute trend (latest 8 scenes, fast mode)"):
                out = []
                with st.spinner("Reading scenes…"):
                    for f in feats[:8]:
                        try:
                            out.append(s2_stats(f["id"], bkey, 200, f))
                        except Exception:
                            pass
                st.session_state["s2_trend"] = pd.DataFrame(out)
            tr = st.session_state.get("s2_trend")
            if tr is not None and len(tr):
                tr = tr.sort_values("date")
                st.plotly_chart(px.line(tr, x="date", y="mean_ndvi", markers=True, hover_data=["cloud_pct", "usable_pct"],
                                        title=f"Mean NDVI around {tn}", labels={"mean_ndvi": "NDVI", "date": ""}),
                                use_container_width=True)
                st.dataframe(tr[["date", "mean_ndvi", "veg_pct", "cloud_pct", "usable_pct", "seconds"]], hide_index=True, use_container_width=True)
        st.caption("Source: Copernicus Sentinel-2 L2A via Earth Search (Element 84, AWS), free with no key. "
                   "Typically clearest from about November to May, but vegetation is also drier then. Verify the licence for commercial use.")

# ---------------------------------------------------------------- farm monitor
with tab_farm:
    st.subheader("1. Locate your farm")
    ctr = st.session_state.get("farm_center", (13.45, -15.4, 8))
    c1, c2 = st.columns([1, 1.7], gap="large")
    with c1:
        q = st.text_input("Search a village or town", key="farm_q", placeholder="e.g. Basse, Farafenni, Brikama")
        if q:
            try:
                hits = geocode(q)
            except Exception:
                hits = []
            if hits:
                hi = st.selectbox("Matches", range(len(hits)), format_func=lambda k: hits[k]["label"], key="farm_hit")
                if st.button("Go to this place"):
                    st.session_state["farm_center"] = (hits[hi]["lat"], hits[hi]["lon"], 14)
                    st.rerun()
            else:
                st.caption("No match. Try another spelling or enter coordinates.")
        la = st.number_input("Latitude", value=float(ctr[0]), format="%.5f", key=f"fl_{ctr[0]:.5f}")
        lo = st.number_input("Longitude", value=float(ctr[1]), format="%.5f", key=f"fo_{ctr[1]:.5f}")
        if st.button("Go to coordinates"):
            st.session_state["farm_center"] = (la, lo, 15)
            st.rerun()
        if st.session_state.get("picked") and st.button("Use the point clicked on the main map"):
            pk = st.session_state["picked"]
            st.session_state["farm_center"] = (pk[0], pk[1], 15)
            st.rerun()
        ha_m = st.number_input("Field size if you drop a marker (hectares)", 0.1, 100.0, 1.0)
        saved_choice = None
        if farms is not None and len(farms):
            names = ["(none)"] + [f"{r['name']} ({r['crop']})" for _, r in farms.iterrows()]
            k_ = st.selectbox("Or open a saved farm", range(len(names)), format_func=lambda i: names[i])
            saved_choice = None if k_ == 0 else farms.iloc[k_ - 1]
        st.caption("On the map, outline the field with the polygon or rectangle tool, or drop a marker. "
                   "Switch to Satellite photo (top right) to see field boundaries.")
    with c2:
        mf = folium.Map(location=[ctr[0], ctr[1]], zoom_start=ctr[2], tiles=None)
        folium.TileLayer("OpenStreetMap", name="Street map").add_to(mf)
        folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                         attr="Esri World Imagery", name="Satellite photo", max_zoom=19).add_to(mf)
        Draw(export=False, edit_options={"edit": False},
             draw_options={"polyline": False, "circle": False, "circlemarker": False, "polygon": True,
                           "rectangle": True, "marker": True}).add_to(mf)
        if farms is not None and len(farms) and "geojson" in farms.columns:
            for _, r in farms.iterrows():
                try:
                    folium.GeoJson(json.loads(r["geojson"]), tooltip=r["name"],
                                   style_function=lambda _x: {"color": "#1F8A5B", "weight": 3}).add_to(mf)
                except Exception:
                    pass
        folium.LayerControl().add_to(mf)
        fo_ = st_folium(mf, height=470, use_container_width=True, returned_objects=["last_active_drawing"], key="farm_map")
        dr_ = (fo_ or {}).get("last_active_drawing")
        if dr_ and dr_.get("geometry"):
            st.session_state["farm_draw"] = dr_["geometry"]

    active = None
    if saved_choice is not None:
        gg = json.loads(saved_choice["geojson"])
        active = {"name": saved_choice["name"], "crop": saved_choice["crop"], "geom": gg, "id": saved_choice["id"],
                  "planted": pd.to_datetime(saved_choice["planting_date"]).date() if saved_choice.get("planting_date") else date.today() - timedelta(days=30)}
    elif st.session_state.get("farm_draw"):
        g0 = st.session_state["farm_draw"]
        if g0["type"] == "Point":
            gg = square_geom(g0["coordinates"][1], g0["coordinates"][0], ha_m)
        elif g0["type"] == "Polygon":
            gg = g0
        else:
            gg = None
        if gg:
            f1, f2, f3 = st.columns(3)
            nm = f1.text_input("Farm name", "My farm", key="farm_name")
            cr = f2.selectbox("Crop", CROPS, key="farm_crop")
            pl = f3.date_input("Planting date", value=date.today() - timedelta(days=30), key="farm_plant")
            active = {"name": nm, "crop": cr, "geom": gg, "id": None, "planted": pl}
    if active is None:
        st.info("Draw your field or drop a marker on the map (or open a saved farm) to start monitoring.")
    else:
        flat, flon, fha = geom_info(active["geom"])
        gjson = json.dumps(active["geom"], sort_keys=True)
        sv1, sv2 = st.columns([1, 3])
        if SB_ON and TOKEN:
            if active["id"] is None and sv1.button("Save this farm", type="primary"):
                try:
                    sb_rest("POST", "farms", TOKEN, body={"name": active["name"], "crop": active["crop"],
                            "planting_date": str(active["planted"]), "lat": flat, "lon": flon, "area_ha": round(fha, 2),
                            "geojson": gjson})
                    load_farms.clear()
                    st.success("Saved. It now shows on the main map and in the saved farms list.")
                except ValueError as e:
                    st.error(f"Could not save: {e}. Run the farms SQL from the README.")
            if active["id"] is not None and sv1.button("Delete this farm"):
                try:
                    sb_rest("DELETE", "farms", TOKEN, params={"id": f"eq.{active['id']}"})
                    load_farms.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        else:
            sv2.caption("Sign in (with Supabase set up) to save farms. Unsaved farms last for this session only.")

        st.subheader(f"2. Monitoring: {active['name']} ({active['crop']})")
        days_since = max((date.today() - active["planted"]).days, 0)
        try:
            fw = load_farm_weather(flat, flon, int(min(max(days_since + 3, 14), 90)))
            today_ts = pd.Timestamp(date.today())
            past = fw[fw["time"] < today_ts]
            since = past[past["time"] >= pd.Timestamp(active["planted"])]
            dry = 0
            for v in reversed([x or 0 for x in past["precipitation_sum"].tolist()]):
                if v >= 1:
                    break
                dry += 1
            sm_now = fw.loc[fw["time"] == today_ts, "soil_moisture_0_to_7cm"]
            sm_now = float(sm_now.iloc[0]) if len(sm_now) and pd.notna(sm_now.iloc[0]) else None
            nxt = fw[(fw["time"] >= today_ts) & (fw["time"] < today_ts + pd.Timedelta(days=3))]
            k = st.columns(6)
            k[0].metric("Field area", f"{fha:.1f} ha")
            k[1].metric("Days since planting", days_since)
            k[2].metric("Rain since planting", f"{since['precipitation_sum'].fillna(0).sum():.0f} mm")
            k[3].metric("Days without rain", dry)
            k[4].metric("Soil moisture", f"{sm_now:.2f}" if sm_now is not None else "n/a", help="Top 7 cm, m³/m³ (model)")
            k[5].metric("Max temp, next 3 days", f"{nxt['temperature_2m_max'].max():.0f}°C")
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(pgo.Bar(x=fw["time"], y=fw["precipitation_sum"], name="Rain (mm)",
                                  marker_color=["#9db7d5" if t < today_ts else "#1C6DD0" for t in fw["time"]]), secondary_y=False)
            fig.add_trace(pgo.Scatter(x=fw["time"], y=fw["soil_moisture_0_to_7cm"], name="Soil moisture", line=dict(color="#1F8A5B")), secondary_y=True)
            fig.update_yaxes(title_text="Rain (mm)", secondary_y=False)
            fig.update_yaxes(title_text="Soil moisture (m³/m³)", secondary_y=True)
            fig.update_layout(title="Rain and soil moisture (pale bars = past, solid = forecast)")
            st.plotly_chart(fig, use_container_width=True)
            weather_ok = True
        except Exception as e:
            weather_ok = False
            st.warning(f"Weather unavailable: {e}")

        st.markdown("##### Crop greenness from Sentinel-2 (inside your field only)")
        try:
            import sentinel  # noqa: F401
            s2f = True
        except Exception as e:
            s2f = False
            st.info(f"Needs the rasterio package. Details: {e}")
        trend = None
        if s2f:
            fcloud = st.slider("Max scene cloud cover (%)", 10, 80, 40, key="farm_cloud")
            try:
                start_ = max(active["planted"] - timedelta(days=14), date.today() - timedelta(days=365))
                _, fscenes = s2_search(flat, flon, 0.5, str(start_), str(date.today()), fcloud)
            except Exception as e:
                fscenes = []
                st.error(f"Scene search failed: {e}")
            st.caption(f"{len(fscenes)} scene(s) since two weeks before planting. Sentinel-2 passes about every 5 days; "
                       "cloud is common from about June to October.")
            if fscenes and st.button("Compute field NDVI trend (up to 12 scenes)", type="primary"):
                rows_ = []
                with st.spinner("Reading your field from each scene…"):
                    for fsc in fscenes[:12]:
                        try:
                            rows_.append(farm_ndvi(fsc["id"], gjson, fsc))
                        except Exception:
                            pass
                st.session_state["farm_trend"] = (gjson, pd.DataFrame(rows_))
            ft_ = st.session_state.get("farm_trend")
            if ft_ and ft_[0] == gjson and len(ft_[1]):
                trend = ft_[1]
                trend = trend[trend["mean_ndvi"].notna() & (trend["valid_pct"] >= 30)].sort_values("date")
                if len(trend):
                    ftr = pgo.Figure()
                    ftr.add_trace(pgo.Scatter(x=trend["date"], y=trend["p90"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
                    ftr.add_trace(pgo.Scatter(x=trend["date"], y=trend["p10"], fill="tonexty", line=dict(width=0),
                                              fillcolor="rgba(31,138,91,.18)", name="Spread (10th to 90th percentile)"))
                    ftr.add_trace(pgo.Scatter(x=trend["date"], y=trend["mean_ndvi"], mode="lines+markers", name="Mean NDVI",
                                              line=dict(color="#1F8A5B")))
                    ftr.update_layout(title="Field NDVI over time (clear pixels only)", yaxis_title="NDVI")
                    st.plotly_chart(ftr, use_container_width=True)
                    st.dataframe(trend[["date", "mean_ndvi", "p10", "p90", "valid_pct", "cloud_pct"]], hide_index=True,
                                 use_container_width=True)
                else:
                    st.warning("No clear scenes with enough usable pixels over your field. Raise the cloud limit.")

        st.markdown("##### Alerts for this field")
        al = []
        if weather_ok:
            if dry >= 7:
                al.append(f"No meaningful rain (under 1 mm) for {dry} days.")
            if sm_now is not None and sm_now < 0.10:
                al.append(f"Topsoil is dry (moisture {sm_now:.2f}).")
            if nxt["temperature_2m_max"].max() >= T_HEAT:
                al.append(f"Heat: up to {nxt['temperature_2m_max'].max():.0f}°C in the next 3 days.")
            if nxt["precipitation_sum"].fillna(0).sum() >= 50:
                al.append(f"Heavy rain forecast: {nxt['precipitation_sum'].fillna(0).sum():.0f} mm in 3 days (waterlogging or flood risk).")
        if trend is not None and len(trend) >= 2:
            d_ = float(trend["mean_ndvi"].iloc[-1] - trend["mean_ndvi"].iloc[-2])
            if d_ <= -0.10:
                al.append(f"Greenness fell by {abs(d_):.2f} NDVI between {trend['date'].iloc[-2]} and {trend['date'].iloc[-1]}. "
                          "Possible stress, flooding, pests, harvest or cloud haze: check the field.")
        if al:
            for a_ in al:
                st.warning(a_)
        else:
            st.success("No alerts right now (based on the data available).")
        st.caption("Indicative thresholds only. NDVI depends on crop type and growth stage, so compare with earlier weeks and "
                   "with neighbouring fields, and confirm problems on the ground. Satellite photo: Esri World Imagery.")

# ---------------------------------------------------------------- data quality
with tab_dq:
    st.subheader("1. Are the data sources up and fresh?")
    hc = health_checks(firms_key or "")
    st.dataframe(hc, hide_index=True, use_container_width=True)
    st.caption("Freshness: Fresh = newest data up to 1 day old, Delayed = up to 3 days, Stale = older. "
               "FIRMS rows need your FIRMS key. Checked at most every 10 minutes.")

    st.subheader("2. NASA FIRMS fire detections: do independent sensors agree?")
    snap = {}
    if not firms_key:
        st.info("Add your FIRMS key (sidebar or secrets) to run the fire cross-checks.")
    else:
        dq_days = st.slider("Days to compare", 2, 10, 5, key="dq_days")
        try:
            snpp = load_firms_source(firms_key, "VIIRS_SNPP_NRT", dq_days)
            n20 = load_firms_source(firms_key, "VIIRS_NOAA20_NRT", dq_days)
            try:
                modis = load_firms_source(firms_key, "MODIS_NRT", dq_days)
            except Exception:
                modis = None
            a1, a2 = match_rate(snpp, n20, 2.0), match_rate(n20, snpp, 2.0)
            a3 = match_rate(modis, pd.concat([snpp, n20]), 3.0) if modis is not None else None
            k = st.columns(5)
            k[0].metric("VIIRS SNPP detections", len(snpp))
            k[1].metric("VIIRS NOAA-20 detections", len(n20))
            k[2].metric("SNPP confirmed by NOAA-20", f"{a1}%" if a1 is not None else "n/a")
            k[3].metric("NOAA-20 confirmed by SNPP", f"{a2}%" if a2 is not None else "n/a")
            k[4].metric("MODIS confirmed by VIIRS", f"{a3}%" if a3 is not None else "n/a")
            snap = {"snpp_to_noaa20_agreement_pct": a1, "noaa20_to_snpp_agreement_pct": a2, "modis_to_viirs_agreement_pct": a3}
            c1, c2 = st.columns(2)
            both = pd.concat([snpp.assign(Sensor="VIIRS SNPP"), n20.assign(Sensor="VIIRS NOAA-20")])
            if len(both):
                c1.plotly_chart(px.bar(both.groupby(["acq_date", "Sensor"]).size().reset_index(name="Detections"),
                                       x="acq_date", y="Detections", color="Sensor", barmode="group",
                                       title="Detections per day", labels={"acq_date": ""}), use_container_width=True)
                conf = snpp["confidence"].astype(str).map(CONF_MAP).fillna("Other").value_counts().reset_index()
                conf.columns = ["Confidence", "Detections"]
                c2.plotly_chart(px.bar(conf, x="Confidence", y="Detections", title="VIIRS SNPP confidence classes"),
                                use_container_width=True)
            st.caption("Agreement = share of one sensor's detections with another sensor's detection within 2 km "
                       "(3 km for MODIS) on the same date. Satellites pass at different times and fires can end between "
                       "passes, so 100% is not expected. This checks consistency, not absolute accuracy.")
        except Exception as e:
            st.warning(f"FIRMS cross-check unavailable: {e}")

    st.subheader("3. Checked against ground truth: fire incident reports")
    if firms_key and inc is not None and len(inc) and "type" in inc.columns:
        fr_ = inc[inc["type"] == "Fire"].copy()
        fr_["when"] = pd.to_datetime(fr_["created_at"], utc=True).dt.tz_localize(None)
        fr_ = fr_[fr_["when"] >= pd.Timestamp.now("UTC").tz_localize(None) - pd.Timedelta(days=10)]
        if len(fr_):
            try:
                hot = pd.concat([load_firms_source(firms_key, "VIIRS_SNPP_NRT", 10), load_firms_source(firms_key, "VIIRS_NOAA20_NRT", 10)])
                hot["d"] = pd.to_datetime(hot["acq_date"])
                res_rows = []
                for _, r in fr_.iterrows():
                    near = hot[(hot["d"] - r["when"].normalize()).abs() <= pd.Timedelta(days=2)]
                    dist = hav_km(r["lat"], r["lon"], near["latitude"].values, near["longitude"].values).min() if len(near) else None
                    res_rows.append({"Date": str(r["when"].date()), "Town": r.get("town", ""),
                                     "Nearest hotspot (km)": None if dist is None else round(float(dist), 1),
                                     "Detected (within 5 km, 2 days)": bool(dist is not None and dist <= 5)})
                rr = pd.DataFrame(res_rows)
                det = int(rr["Detected (within 5 km, 2 days)"].sum())
                st.metric("Reported fires seen by satellite", f"{det} of {len(rr)}", f"{100 * det / len(rr):.0f}%")
                st.dataframe(rr, hide_index=True, use_container_width=True)
                snap["fire_reports_detected_pct"] = round(100 * det / len(rr), 1)
                if len(rr) < 10:
                    st.caption("Fewer than 10 reports in the last 10 days: treat this percentage as indicative only.")
            except Exception as e:
                st.warning(f"Could not compare with reports: {e}")
        else:
            st.info("No fire incident reports in the last 10 days to compare against.")
    else:
        st.info("This check needs the FIRMS key and submitted incident reports of type Fire (sign-in and Supabase required).")
    st.caption("Report dates use the time the report was submitted. Satellites can miss small, short or cloud-covered fires, "
               "so a miss is not always a wrong report.")

    st.subheader("4. Quality over time")
    if SB_ON and TOKEN:
        if st.button("Save a snapshot now"):
            body = [{"source": "NASA FIRMS", "metric": m, "value": v, "note": ""} for m, v in snap.items() if v is not None]
            body += [{"source": r["Source"], "metric": f"latency_ms:{r['Check']}", "value": float(r["Latency (ms)"]), "note": r["Status"]}
                     for _, r in hc.iterrows()]
            try:
                sb_rest("POST", "data_quality_log", TOKEN, body=body)
                load_dq_log.clear()
                st.success(f"Saved {len(body)} measurements.")
            except ValueError as e:
                st.error(f"Could not save: {e}. Run the data_quality_log SQL from the README.")
        try:
            lg = load_dq_log(TOKEN)
            if len(lg):
                lg["created_at"] = pd.to_datetime(lg["created_at"])
                agree = lg[lg["metric"].str.contains("pct")]
                if len(agree):
                    st.plotly_chart(px.line(agree.sort_values("created_at"), x="created_at", y="value", color="metric", markers=True,
                                            title="Agreement and detection rates over time (%)", labels={"created_at": "", "value": "%"}),
                                    use_container_width=True)
                lat_ = lg[lg["metric"].str.startswith("latency")]
                if len(lat_):
                    st.plotly_chart(px.line(lat_.sort_values("created_at"), x="created_at", y="value", color="metric",
                                            title="Source response time (ms)", labels={"created_at": "", "value": "ms"}),
                                    use_container_width=True)
            else:
                st.info("No snapshots saved yet. Save one now, then again on other days to see trends.")
        except ValueError as e:
            st.info(f"Trend log not available yet: {e}")
    else:
        st.info("Sign in with Supabase configured to save snapshots and see trends.")

# ---------------------------------------------------------------- incidents
with tab_inc:
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
    if not SB_ON:
        st.info("Incident reporting needs Supabase. See the README for setup.")
    elif not TOKEN:
        st.info("Sign in to report and view incidents.")
    else:
        c1, c2 = st.columns([1, 1.25], gap="large")
        with c1:
            st.subheader("Report an incident")
            pk = st.session_state.get("picked")
            town = st.selectbox("Nearest town", list(TOWNS), key="inc_town")
            d_lat, d_lon = pk if pk else (TOWNS[town]["lat"], TOWNS[town]["lon"])
            st.caption(f"Using map point {pk[0]:.4f}, {pk[1]:.4f}" if pk else "Tip: click the map first to use an exact point.")
            with st.form("incident", clear_on_submit=True):
                typ = st.selectbox("Type", INCIDENT_TYPES)
                sev = st.select_slider("Severity", ["Minor", "Moderate", "Severe"])
                desc = st.text_area("What happened?", max_chars=500)
                a, b = st.columns(2)
                houses = a.number_input("Houses affected", 0, 100000, 0)
                ppl = b.number_input("People affected", 0, 1000000, 0)
                lat = a.number_input("Latitude", value=float(d_lat), format="%.5f", key=f"lat_{d_lat:.5f}")
                lon = b.number_input("Longitude", value=float(d_lon), format="%.5f", key=f"lon_{d_lon:.5f}")
                photo = st.file_uploader("Photo (optional, under 5 MB)", type=["jpg", "jpeg", "png"])
                go = st.form_submit_button("Submit report", type="primary", use_container_width=True)
            if go:
                try:
                    purl = upload_photo(TOKEN, photo) if photo else None
                    sb_rest("POST", "incidents", TOKEN, body={
                        "reporter_email": st.session_state["user"]["email"], "type": typ, "severity": sev,
                        "description": desc.strip(), "lat": lat, "lon": lon, "town": town,
                        "houses_affected": int(houses), "people_affected": int(ppl),
                        **({"photo_url": purl} if purl else {})})
                    load_incidents.clear()
                    st.session_state["flash"] = "Report submitted. It now shows on the map."
                    st.rerun()
                except ValueError as e:
                    st.error(f"Could not save: {e}. If your session expired, sign out and sign in again.")
        with c2:
            st.subheader("Reported damage")
            if inc_err:
                st.error(f"Could not load reports: {inc_err}")
            elif inc is None or not len(inc):
                st.info("No reports yet. Submit the first one.")
            else:
                k = st.columns(4)
                k[0].metric("Reports", len(inc))
                k[1].metric("Severe", int((inc["severity"] == "Severe").sum()))
                k[2].metric("Houses affected", int(inc["houses_affected"].fillna(0).sum()))
                k[3].metric("People affected", int(inc["people_affected"].fillna(0).sum()))
                st.plotly_chart(px.bar(inc["type"].value_counts().reset_index(), x="count", y="type", orientation="h",
                                       title="Reports by type"), use_container_width=True)
                show = inc[["created_at", "town", "type", "severity", "houses_affected", "people_affected", "description"] + (["photo_url"] if "photo_url" in inc.columns else [])].head(50)
                st.dataframe(show, hide_index=True, use_container_width=True)
                st.download_button("⬇️ Download reports (CSV)", inc.to_csv(index=False), "incidents.csv", "text/csv")

# ---------------------------------------------------------------- history
with tab_clim:
    reg = st.selectbox("Region", list(REGIONS))
    try:
        h = load_history(*REGIONS[reg])
        h["tmean"] = ((h["temperature_2m_max"] + h["temperature_2m_min"]) / 2).rolling(7, center=True).mean()
        st.plotly_chart(px.line(h, x="time", y=["temperature_2m_max", "tmean", "temperature_2m_min"],
                                title=f"{reg}: daily temperature (°C)"), use_container_width=True)
        mon = h.set_index("time")["precipitation_sum"].resample("MS").sum().reset_index()
        st.plotly_chart(px.bar(mon, x="time", y="precipitation_sum",
                               title=f"{reg}: monthly rainfall (mm)"), use_container_width=True)
        st.caption(f"Last 12 months total: {h['precipitation_sum'].sum():.0f} mm · "
                   f"hottest day: {h['temperature_2m_max'].max():.1f} °C")
    except Exception as e:
        st.error(f"History unavailable: {e}")

# ---------------------------------------------------------------- data
with tab_data:
    st.dataframe(df.drop(columns=["lat", "lon"]).round(1), use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), "gambia_env_live.csv", "text/csv")
    st.download_button("📄 Download report (HTML, print to PDF)", build_report(ORG, df, tw, alerts),
                       f"environmental_report_{date.today()}.html", "text/html")
    st.caption("Protected-area and wetland points are approximate and for orientation only. "
               "Replace with official shapefiles/GeoJSON (e.g. from DPWM or NEA) via the sidebar upload.")