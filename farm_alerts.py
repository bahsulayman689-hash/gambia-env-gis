"""Daily SMS alerts for saved farms (no Streamlit). Run by .github/workflows/farm_alerts.yml.
Only farms whose owner turned alerts on and gave a phone number are used. One SMS per farm per 2 days at most.

Env: SUPABASE_URL (https://<project>.supabase.co), SUPABASE_SERVICE_KEY (server-side secret; never put it in the app),
     TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, T_HEAT=38, ORG_NAME. Without Twilio the messages are only printed."""
import json
import os
import time
from datetime import date, timedelta
from urllib.parse import urlparse

import requests

import farm_rules

_u = urlparse(os.environ["SUPABASE_URL"].strip())
BASE = f"{_u.scheme}://{_u.netloc}"
KEY = os.environ["SUPABASE_SERVICE_KEY"]
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
T_HEAT = float(os.getenv("T_HEAT", 38))
ORG = os.getenv("ORG_NAME", "Farm monitor")
FORECAST = "https://api.open-meteo.com/v1/forecast"


def get_json(url, params=None, headers=None):
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=40)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 3:
                time.sleep(1.5 * 2 ** attempt)
                continue
            raise
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(1.5 * 2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()


def weather(lat, lon):
    j = get_json(FORECAST, {"latitude": round(lat, 4), "longitude": round(lon, 4), "past_days": 14, "forecast_days": 3,
                            "timezone": "Africa/Banjul", "daily": "precipitation_sum,temperature_2m_max",
                            "hourly": "soil_moisture_0_to_7cm"})
    days = j["daily"]["time"]
    rain = [x or 0 for x in j["daily"]["precipitation_sum"]]
    today = date.today().isoformat()
    ti = days.index(today) if today in days else len(days) - 3
    dry = 0
    for v in reversed(rain[:ti]):
        if v >= 1:
            break
        dry += 1
    sm = [v for t, v in zip(j["hourly"]["time"], j["hourly"]["soil_moisture_0_to_7cm"]) if t.startswith(today) and v is not None]
    tmax3 = max(x or 0 for x in j["daily"]["temperature_2m_max"][ti:ti + 3])
    return dry, (sum(sm) / len(sm) if sm else None), tmax3, sum(rain[ti:ti + 3])


def main():
    cal = farm_rules.load_calendar()
    farms = get_json(f"{BASE}/rest/v1/farms", {"select": "id,name,crop,planting_date,lat,lon,phone,alerts_on",
                                                 "alerts_on": "eq.true", "phone": "not.is.null"}, H)
    sid, tok = os.getenv("TWILIO_SID"), os.getenv("TWILIO_TOKEN")
    for f in farms:
        try:
            since = (date.today() - date.fromisoformat(f["planting_date"])).days if f.get("planting_date") else 0
            stg = farm_rules.current_stage(f["crop"], since, cal)
            msgs = farm_rules.weather_alerts(*weather(f["lat"], f["lon"]), stage=stg, t_heat=T_HEAT)
            if not msgs:
                continue
            recent = get_json(f"{BASE}/rest/v1/farm_alert_log", {"select": "id", "farm_id": f"eq.{f['id']}",
                                                                  "sent_on": f"gte.{(date.today() - timedelta(days=1)).isoformat()}"}, H)
            if recent:
                continue
            stage_txt = f", {stg['stage'].lower()}" if stg else ""
            text = f"{ORG}: {f['name']} ({f['crop']}, day {since}{stage_txt}). " + " ".join(msgs)
            print(text)
            if sid and tok:
                r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, tok), timeout=30,
                                  data={"From": os.getenv("TWILIO_FROM"), "To": str(f["phone"]).strip(), "Body": text[:600]})
                r.raise_for_status()
                requests.post(f"{BASE}/rest/v1/farm_alert_log", headers={**H, "Prefer": "return=minimal"}, timeout=30,
                              data=json.dumps({"farm_id": f["id"], "message": text[:500]}))
        except Exception as e:   # one farm failing must not stop the others
            print(f"Farm {f.get('id')}: {e}")


if __name__ == "__main__":
    main()
