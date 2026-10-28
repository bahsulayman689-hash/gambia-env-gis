"""Scheduled alert job (no Streamlit). Sends SMS (Twilio) and/or a webhook (Slack/Teams) when
towns breach flood / heat / dust thresholds. Run daily via GitHub Actions (see .github/workflows/alerts.yml).

Env vars: TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, ALERT_RECIPIENTS (comma-separated +220...),
          WEBHOOK_URL (optional), T_HEAT=38, T_PM10=150, ORG_NAME
If no sender is configured the alerts are only printed.
"""
import os
import requests

TOWNS = [("Banjul", 13.4549, -16.5790, 5), ("Serrekunda", 13.4383, -16.6781, 5), ("Bakau", 13.4781, -16.6819, 4),
         ("Sukuta", 13.3833, -16.7000, 4), ("Brikama", 13.2714, -16.6494, 4), ("Gunjur", 13.2000, -16.7500, 3),
         ("Kartong", 13.0833, -16.7667, 3), ("Essau", 13.4833, -16.5333, 3), ("Kerewan", 13.4903, -16.0894, 3),
         ("Farafenni", 13.5667, -15.6000, 2), ("Mansa Konko", 13.4667, -15.5333, 3), ("Bansang", 13.4333, -14.6500, 3),
         ("Janjanbureh", 13.5333, -14.7667, 4), ("Kuntaur", 13.6667, -14.8833, 3), ("Basse", 13.3081, -14.2167, 3)]
T_HEAT = float(os.getenv("T_HEAT", 38))
T_PM10 = float(os.getenv("T_PM10", 150))
ORG = os.getenv("ORG_NAME", "Gambia Environmental Monitor")


def get(url, params):
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j if isinstance(j, list) else [j]


def main():
    base = {"latitude": ",".join(str(t[1]) for t in TOWNS), "longitude": ",".join(str(t[2]) for t in TOWNS),
            "timezone": "Africa/Banjul"}
    w = get("https://api.open-meteo.com/v1/forecast",
            {**base, "daily": "precipitation_sum,temperature_2m_max", "forecast_days": 7})
    a = get("https://air-quality-api.open-meteo.com/v1/air-quality", {**base, "current": "pm10"})
    try:
        f = get("https://flood-api.open-meteo.com/v1/flood",
                {**base, "daily": "river_discharge,river_discharge_mean", "forecast_days": 7})
    except Exception:
        f = [{}] * len(TOWNS)
    msgs = []
    for t, wi, ai, fi in zip(TOWNS, w, a, f):
        rain = [x or 0 for x in wi["daily"]["precipitation_sum"]]
        q = [x for x in fi.get("daily", {}).get("river_discharge", []) if x is not None]
        qm = [x for x in fi.get("daily", {}).get("river_discharge_mean", []) if x is not None]
        ratio = max(q) / (sum(qm) / len(qm)) if q and qm and sum(qm) > 0 else 0
        hazard = max(min(sum(rain) / 80, 1), min(max(rain) / 50, 1), min(max(ratio - 1, 0) / 2, 1))
        if hazard >= 0.5:
            msgs.append(f"FLOOD {'SEVERE' if hazard >= .75 else 'WARNING'} {t[0]}: {sum(rain):.0f} mm in 7d "
                        f"(max {max(rain):.0f} mm/day)")
        tmax = max(x or 0 for x in wi["daily"]["temperature_2m_max"][:3])
        if tmax >= T_HEAT:
            msgs.append(f"HEAT {t[0]}: up to {tmax:.0f}C in next 3 days")
        pm = ai["current"].get("pm10") or 0
        if pm >= T_PM10:
            msgs.append(f"DUST {t[0]}: PM10 {pm:.0f} ug/m3")
    if not msgs:
        print("No alerts.")
        return
    text = f"{ORG} alerts:\n" + "\n".join(msgs)
    print(text)
    sid, tok = os.getenv("TWILIO_SID"), os.getenv("TWILIO_TOKEN")
    for to in filter(None, os.getenv("ALERT_RECIPIENTS", "").split(",")):
        if sid and tok:
            requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, tok),
                          data={"From": os.getenv("TWILIO_FROM"), "To": to.strip(), "Body": text[:1500]}, timeout=30)
    if os.getenv("WEBHOOK_URL"):
        requests.post(os.getenv("WEBHOOK_URL"), json={"text": text}, timeout=30)


if __name__ == "__main__":
    main()
