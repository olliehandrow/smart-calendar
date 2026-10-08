#!/usr/bin/env python3
"""
Builds site/data.json for the smart calendar display.

  - Events:  Planning Center Calendar API (event_instances + their parent event)
  - Weather: Open-Meteo (free, no API key)
  - Facts:   uselessfacts.jsph.pl (free, no API key)
  - Quotes:  zenquotes.io (free, no API key)
             Both fall back to content/facts.txt / content/quotes.txt if the API call fails.
             Fetched once per local day: later builds that day reuse the facts/quotes
             from the currently deployed data.json (PAGES_URL) so they don't change.

Standard library only, so the GitHub Action needs no pip install.

Environment variables (set as GitHub Secrets / Variables):
  PCO_APP_ID, PCO_SECRET   Planning Center personal access token (required)
  TIMEZONE                 e.g. America/Denver            (default America/Denver)
  LATITUDE, LONGITUDE      for the weather card           (optional; weather is skipped if unset)
  PCO_ONLY_PUBLIC          "true" to show only events visible in Church Center (default false)
  PCO_APPROVED_ONLY        "true" to hide pending/rejected events (default true)
  PAGES_URL                deployed site URL, set by the workflow (optional)
"""
import base64, json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data.json"
TZ_NAME = os.environ.get("TIMEZONE", "America/Denver")
TZ = ZoneInfo(TZ_NAME)
PCO = "https://api.planningcenteronline.com/calendar/v2"


def env_bool(name, default):
    v = os.environ.get(name)
    return default if v is None or v == "" else v.strip().lower() in ("1", "true", "yes")


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "smart-calendar-signage", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---------------------------------------------------------------- events
def fetch_events(start_local, end_local):
    app_id, secret = os.environ.get("PCO_APP_ID"), os.environ.get("PCO_SECRET")
    if not app_id or not secret:
        sys.exit("PCO_APP_ID and PCO_SECRET must be set")
    auth = {"Authorization": "Basic " + base64.b64encode(f"{app_id}:{secret}".encode()).decode()}

    utc = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Grab anything that ends after the window opens and starts before it closes,
    # so multi-day events that began earlier are included.
    qs = urllib.parse.urlencode({
        "where[ends_at][gte]": utc(start_local),
        "where[starts_at][lte]": utc(end_local),
        "include": "event",
        "order": "starts_at",
        "per_page": 100,
    })
    url = f"{PCO}/event_instances?{qs}"

    only_public = env_bool("PCO_ONLY_PUBLIC", False)
    approved_only = env_bool("PCO_APPROVED_ONLY", True)
    out, seen = [], set()
    while url:
        page = get_json(url, auth)
        parents = {i["id"]: i["attributes"] for i in page.get("included", []) if i["type"] == "Event"}
        for inst in page.get("data", []):
            a = inst["attributes"]
            ev_id = (inst.get("relationships", {}).get("event", {}).get("data") or {}).get("id")
            ev = parents.get(ev_id, {})
            if only_public and ev.get("visible_in_church_center") is False:
                continue
            if approved_only and ev.get("approval_status") not in (None, "A"):
                continue
            title = (ev.get("name") or a.get("name") or "Untitled").strip()
            item = to_item(title, a)
            if item and (k := json.dumps(item, sort_keys=True)) not in seen:
                seen.add(k)
                out.append(item)
        url = (page.get("links") or {}).get("next")
    return out


def to_item(title, a):
    if not a.get("starts_at"):
        return None
    s = datetime.fromisoformat(a["starts_at"].replace("Z", "+00:00")).astimezone(TZ)
    e = datetime.fromisoformat((a.get("ends_at") or a["starts_at"]).replace("Z", "+00:00")).astimezone(TZ)
    long_span = (e - s) >= timedelta(hours=20) and s.date() != e.date()
    if a.get("all_day_event") or long_span:
        # end date inclusive; an end exactly at midnight belongs to the previous day
        end_day = (e - timedelta(seconds=1)).date() if e.time() == datetime.min.time() and e > s else e.date()
        return {"title": title, "all_day": True, "start": s.date().isoformat(), "end": max(end_day, s.date()).isoformat()}
    fmt = "%Y-%m-%dT%H:%M"
    return {"title": title, "start": s.strftime(fmt), "end": e.strftime(fmt)}


# ---------------------------------------------------------------- weather
def fetch_weather():
    lat, lon = os.environ.get("LATITUDE"), os.environ.get("LONGITUDE")
    if not lat or not lon:
        print("LATITUDE/LONGITUDE not set, skipping weather")
        return {}
    qs = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": TZ_NAME, "forecast_days": 7,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
    })
    try:
        d = get_json(f"https://api.open-meteo.com/v1/forecast?{qs}")["daily"]
    except Exception as ex:  # weather is nice-to-have; never fail the build over it
        print("weather fetch failed:", ex)
        return {}
    return {
        day: {"code": code, "high": round(hi), "low": round(lo)}
        for day, code, hi, lo in zip(d["time"], d["weather_code"], d["temperature_2m_max"], d["temperature_2m_min"])
        if code is not None and hi is not None and lo is not None
    }


# ---------------------------------------------------------------- content
def read_lines(name):
    p = ROOT / "content" / name
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def read_quotes():
    out = []
    for line in read_lines("quotes.txt"):
        text, _, author = line.partition("|")
        out.append({"text": text.strip().strip('"“”'), "author": author.strip()})
    return out


def fetch_facts(n=10):
    out = []
    try:
        for _ in range(n):
            text = get_json("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en").get("text", "").strip()
            if text and text not in out:
                out.append(text)
    except Exception as ex:  # nice-to-have; fall back to the local list rather than fail the build
        print("facts fetch failed:", ex)
    return out or read_lines("facts.txt")


def fetch_quotes(n=10):
    try:
        quotes = [
            {"text": q["q"].strip(), "author": (q.get("a") or "").strip()}
            for q in get_json("https://zenquotes.io/api/quotes")
            if q.get("q")
        ]
        if quotes:
            return quotes[:n]
    except Exception as ex:  # nice-to-have; fall back to the local list rather than fail the build
        print("quotes fetch failed:", ex)
    return read_quotes()


def previous_content(today):
    """Facts/quotes from the deployed data.json if it was built earlier today, else None."""
    base = os.environ.get("PAGES_URL", "").strip()
    if not base:
        return None
    try:
        prev = get_json(base.rstrip("/") + "/data.json")
    except Exception as ex:
        print("previous data.json fetch failed:", ex)
        return None
    if prev.get("content_date") == today.isoformat() and prev.get("facts") and prev.get("quotes"):
        return prev["facts"], prev["quotes"]
    return None


# ---------------------------------------------------------------- main
def main():
    today = datetime.now(TZ).date()
    week_start = today - timedelta(days=(today.weekday() + 1) % 7)  # Sunday
    start = datetime.combine(week_start, datetime.min.time(), TZ)
    end = start + timedelta(days=36)                                 # 4-week month view + margin

    events = fetch_events(start, end)
    facts, quotes = previous_content(today) or (fetch_facts(), fetch_quotes())
    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timezone": TZ_NAME,
        "events": events,
        "weather": fetch_weather(),
        "content_date": today.isoformat(),
        "facts": facts,
        "quotes": quotes,
    }
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} with {len(events)} events, {len(data['weather'])} weather days")


if __name__ == "__main__":
    main()
