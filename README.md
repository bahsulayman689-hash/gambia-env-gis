<p align="center">
  <img src="logo.svg" alt="Gambia Env GIS" width="120">
</p>

<h1 align="center">Gambia Environmental GIS Dashboard</h1>

<p align="center">
  Live flood outlook, air quality, heat, fire and vegetation monitoring for The Gambia 🇬🇲
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-blue">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-app-ff4b4b">
  <img alt="Data" src="https://img.shields.io/badge/Data-Open--Meteo%20%7C%20NASA-1b4f72">
</p>

<!-- Add a screenshot: save it as docs/screenshot.png, then uncomment -->
<!-- <p align="center"><img src="docs/screenshot.png" width="800"></p> -->

## Features

- **Flood outlook:** 7-day flood level for 15 towns (Low / Watch / Warning / Severe), plus click-anywhere flood hazard on the map.
- **Live conditions:** temperature, humidity, wind, rainfall, PM2.5, PM10, Saharan dust and AQI for 8 regions.
- **Satellite layers:** NASA MODIS NDVI vegetation and true-colour imagery (GIBS), fire hotspots (FIRMS).
- **Town issue profiles:** the main environmental problems of each town (indicative; verify with NEA / NDMA / DWR).
- **Alerts:** on-screen thresholds, optional Supabase logging, daily SMS / webhook alerts.
- **Reports:** CSV export and a printable HTML report.
- **White-label:** client name, logo, colour and optional access code.
- **Custom layers:** upload GeoJSON, or CSV with `lat`, `lon`, `name`.

## Workflow

```mermaid
flowchart LR
    A["Open-Meteo<br/>weather, air quality, GloFAS flood"] --> D["Streamlit app<br/>app.py"]
    B["NASA GIBS<br/>NDVI, true colour"] --> D
    C["NASA FIRMS<br/>fire hotspots"] --> D
    U["Uploaded GeoJSON / CSV"] --> D
    D --> M["Interactive map"]
    D --> F["Flooding and town issues"]
    D --> R["CSV and HTML report"]
    D --> AL["Threshold alerts"]
    AL --> S[("Supabase<br/>alerts table")]
    G["GitHub Actions<br/>daily 06:00 UTC"] --> J["alerts_job.py"]
    A --> J
    J --> T["Twilio SMS / Slack or Teams webhook"]
```

### How flood risk is calculated

```mermaid
flowchart LR
    R1["7-day rain total"] --> H["Hazard 0-1<br/>(highest of the three)"]
    R2["Peak daily rain"] --> H
    R3["River discharge vs normal"] --> H
    H --> K["Flood risk 0-100<br/>60% hazard + 40% exposure"]
    E["Town exposure 1-5"] --> K
    H --> L["Level: Low, Watch, Warning, Severe"]
```

## Quick start

```bash
git clone https://github.com/<your-username>/gambia-env-gis.git
cd gambia-env-gis
pip install -r requirements.txt
streamlit run app.py
```

## Configuration (all optional)

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, or paste the values into Streamlit Cloud under Settings > Secrets. **Never commit `secrets.toml`.**

| Key | Purpose |
|---|---|
| `ORG_NAME`, `ORG_LOGO_URL`, `PRIMARY_COLOR` | White-label branding |
| `APP_PASSWORD` | Access code (remove for a public app) |
| `FIRMS_KEY` | Fire hotspots. Free at https://firms.modaps.eosdis.nasa.gov/api/map_key |
| `SUPABASE_URL`, `SUPABASE_KEY` | Log alerts to Supabase (anon key) |

### Accounts (sign in / create account)

With `SUPABASE_URL` and `SUPABASE_KEY` set, the app shows a **Sign in / Create account** page (Supabase Auth). Set `REQUIRE_LOGIN = "false"` to keep the app public. Without Supabase, `APP_PASSWORD` is used as a simple access code.

In Supabase: **Authentication > Providers > Email** must be enabled. Under **Authentication > URL Configuration**, set **Site URL** to your Streamlit app URL so confirmation and reset links come back to the app. To restrict access to invited users only, turn off new sign-ups and use **Authentication > Users > Invite user**.

### Incident reports table

Signed-in users can report real damage (type, severity, houses and people affected, location). Run this once in the Supabase SQL Editor:

```sql
create table incidents (
  id bigint generated always as identity primary key,
  created_at timestamptz default now(),
  reporter_email text, type text, severity text, description text,
  lat float8, lon float8, town text,
  houses_affected int default 0, people_affected int default 0
);
alter table incidents enable row level security;
create policy "read incidents" on incidents for select to authenticated using (true);
create policy "insert incidents" on incidents for insert to authenticated with check (true);
```

Reports appear as coloured dots on the map (yellow minor, orange moderate, red severe). Sessions last about an hour; if saving fails, sign out and in again.

### Supabase table

```sql
create table alerts (
  id bigint generated always as identity primary key,
  created_at timestamptz default now(),
  region text, type text, value float8, threshold float8
);
alter table alerts enable row level security;
create policy "insert alerts" on alerts for insert with check (true);
```

### Daily alerts

`alerts_job.py` runs on a schedule through `.github/workflows/alerts.yml`. Add these as GitHub repository secrets: `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`, `ALERT_RECIPIENTS` (comma-separated, e.g. `+220...`), `WEBHOOK_URL`, `ORG_NAME`. The job has no memory between runs, so a long-lasting problem is re-sent each day.

## Project structure

```
app.py                      Streamlit dashboard
alerts_job.py               Scheduled alert sender
requirements.txt
assets/logo.svg             Logo
.github/workflows/alerts.yml
.streamlit/secrets.toml.example
PROPOSAL_AND_HANDOVER.md    Client proposal and handover checklist
```

## Data sources and limits

- **Open-Meteo** (weather, CAMS air quality, GloFAS flood): the free API is for **non-commercial** use. Commercial deployments need a paid plan.
- **NASA GIBS and FIRMS:** free; FIRMS needs a MAP_KEY.
- **OpenStreetMap tiles:** fair-use policy applies.
- Flood levels are forecast-based indicators, **not official warnings**. Tides, storm surge and street drainage are not modelled.
- Town exposure scores and issue lists are indicative assessments, not official data.

## Author

**Sulayman Bah**, ML / software developer, The Gambia
GitHub: [bahsulayman689-hash](https://github.com/bahsulayman689-hash) · LinkedIn: [sulayman-bah-8a7096423](https://linkedin.com/in/sulayman-bah-8a7096423)
