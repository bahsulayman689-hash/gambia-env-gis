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
from datetime import date, datetime, timedelta
from pathlib import Path

import branca.colormap as cm
import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from folium.plugins import Fullscreen, HeatMap, MiniMap
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
section[data-testid="stSidebar"] { background: #fff; border-right: 1px solid #dbe5e8; }
.brand { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.3rem; font-weight: 700; color: #0B3C49; }
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
@media (max-width: 700px) { .hero { padding: 22px 20px; } .hero-status { font-size: 1.5rem; } .hero-row img { display: none; } }
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


def get(url, params):
    r = requests.get(url, params=params, timeout=30)
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


def secret(k):
    try:
        return st.secrets[k]
    except Exception:
        return None


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
                               "Authorization": f"Bearer {secret('SUPABASE_KEY')}",
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
if _pw and not st.session_state.get("auth"):
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

# ---------------------------------------------------------------- sidebar
st.sidebar.markdown("<div class='brand'>Gambia Env GIS</div>", unsafe_allow_html=True)
LAYERS = ["Temp (°C)", "PM10 (µg/m³)", "PM2.5 (µg/m³)", "Dust (µg/m³)", "US AQI",
          "Rain next 7d (mm)", "Humidity (%)", "Wind (km/h)", "Composite risk (0-100)"]
layer = st.sidebar.selectbox("Map layer", LAYERS, index=len(LAYERS) - 1)
show_sites = st.sidebar.checkbox("Protected areas & wetlands", True)
show_heat = st.sidebar.checkbox("Heatmap surface", True)
show_towns = st.sidebar.checkbox("Towns: flood level & issues", True)
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

# ---------------------------------------------------------------- header / KPIs
def _logo():
    try:
        return base64.b64encode((Path(__file__).parent / "assets" / "logo.svg").read_bytes()).decode()
    except Exception:
        return ""


lv = tw["Flood level"].value_counts() if tw is not None else {}
n_hi = int(lv.get("Warning", 0) + lv.get("Severe", 0))
n_w = int(lv.get("Watch", 0))
if tw is None:
    status, dot = "Flood outlook unavailable", "#9fb3b9"
elif n_hi:
    status, dot = f"Flood warning in {n_hi} town{'s' if n_hi > 1 else ''}", "#ff6b5e"
elif n_w:
    status, dot = f"Flood watch in {n_w} town{'s' if n_w > 1 else ''}", "#ffc233"
else:
    status, dot = "No flood alerts for the next 7 days", "#5be3a1"
_lg = _logo()
_img = f'<img src="data:image/svg+xml;base64,{_lg}" alt="">' if _lg else ""
st.markdown(
    f'<div class="hero"><div class="hero-row">{_img}<div>'
    f'<div class="hero-org">{html.escape(ORG)}: Environmental Monitor</div>'
    f'<div class="hero-status"><span class="dot" style="background:{dot}"></span>{status}</div>'
    f'<div class="hero-sub">Updated {datetime.now():%H:%M} from Open-Meteo and NASA for 15 towns in 8 regions. '
    f'Flood levels are forecast indicators, not official warnings.</div></div></div></div>',
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

tab_map, tab_flood, tab_clim, tab_data = st.tabs(["🗺️ Map", "🌊 Flooding & town issues", "📈 Climate history", "📋 Data & export"])

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
            x = flood_metrics([(clk["lat"], clk["lng"])])[0]
            st.info(f"📍 {clk['lat']:.4f}, {clk['lng']:.4f}: rain next 7d {x['rain7']:.0f} mm "
                    f"(max {x['rain_max']:.0f} mm/day) · river discharge {x['discharge']:.1f} m³/s "
                    f"({x['ratio']:.1f}× normal) · flood hazard {x['hazard'] * 100:.0f}/100")
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
        pick = st.selectbox("Problems and issues in", tw["Town"])
        row = tw[tw["Town"] == pick].iloc[0]
        st.markdown(f"**{pick}** ({row['Region']}) · flood level **{row['Flood level']}**")
        st.markdown("\n".join(f"- {i}" for i in row["Issues"].split("; ")))
        st.caption("Hazard = max of 7-day rain, peak daily rain, and GloFAS river discharge vs normal. "
                   "Exposure and issue lists are indicative general assessments, not official data. "
                   "Tides, storm surge and street-level drainage are not modelled; confirm with NDMA / NEA / DWR.")

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