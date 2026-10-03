#!/usr/bin/env python3
"""Generate the ported record catalog: canonical Open-Meteo Archive
records for every complete ISO week (Mon-Sun) of the coverage era at the
catalog location, written to records/<start>_<end>.json + manifest.json.

The canonical form is EXACTLY what the contract expects (strip
generationtime_ms, integral floats -> ints, sorted-key JSON) — the same
bytes the sha256 pins commit to.
"""
import datetime
import json
import time
import urllib.request
from pathlib import Path

LAT, LON = "-6.2", "106.82"
OUT = Path(__file__).resolve().parents[1] / "records"
ERA_START = datetime.date(2025, 1, 6)   # first Monday of the era
TODAY = datetime.date.today()
LAST_COMPLETE_SUNDAY = TODAY - datetime.timedelta(days=TODAY.isoweekday())


def iso(d):
    return d.isoformat()


def fetch_window(start, end):
    url = ("https://archive-api.open-meteo.com/v1/archive?"
           "latitude=" + LAT + "&longitude=" + LON
           + "&start_date=" + iso(start) + "&end_date=" + iso(end)
           + "&daily=precipitation_sum&timezone=GMT")
    raw = urllib.request.urlopen(url, timeout=60).read()
    parsed = json.loads(raw.decode())
    parsed.pop("generationtime_ms", None)

    def norm(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, list):
            return [norm(i) for i in v]
        if isinstance(v, dict):
            return {k: norm(x) for k, x in v.items()}
        return v

    return json.dumps(norm(parsed), sort_keys=True, separators=(",", ":"))


def main():
    OUT.mkdir(exist_ok=True)
    manifest = []
    week = ERA_START
    while week + datetime.timedelta(days=6) <= LAST_COMPLETE_SUNDAY:
        start, end = week, week + datetime.timedelta(days=6)
        name = iso(start) + "_" + iso(end) + ".json"
        canon = fetch_window(start, end)
        total = round(sum(json.loads(canon)["daily"]["precipitation_sum"]), 1)
        (OUT / name).write_text(canon)
        manifest.append({"file": name, "start": iso(start),
                         "end": iso(end), "total_mm": total})
        print(name, total, "mm", flush=True)
        week += datetime.timedelta(days=7)
        time.sleep(0.3)
    (OUT / "manifest.json").write_text(json.dumps(
        {"location": "Jakarta (lat -6.2, lon 106.82)",
         "source": "Open-Meteo Archive (keyless), canonicalized",
         "window_days": 7,
         "windows": manifest}, indent=1))
    print("manifest:", len(manifest), "windows")


if __name__ == "__main__":
    main()
