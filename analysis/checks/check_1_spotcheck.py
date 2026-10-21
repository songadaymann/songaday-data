"""Skeptic check 1: spot-check 20 random rows of dataset/songaday.csv against the raw sources.

For each sampled song this compares:
  - the public sheet (cache/sheet/sheet-gid0.csv, songs #1-#5101): date, title, location,
    mood, beard, genre, first topic, length, tempo, key, video ID
  - the songaday-display catalog (newest index-*.json per chunk, deduped by song number):
    the same fields
  - the Open-Meteo cache (cache/weather/<place>/<month>.json): daily mean temperature,
    precipitation, weather code, and that the cached request used the row's coordinates
  - the YouTube snapshot (cache/views/youtube/toolkit-2026-10-18.json): views
  - PyEphem, recomputed here: moon illumination at 17:00 New York time
It also re-checks a few whole-table invariants (no repeated numbers, date = number, no
repeated video IDs, sheet date column agrees with the number).

Run from the repo root:
  .venv/bin/python analysis/checks/check_1_spotcheck.py
"""

import csv
import glob
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import ephem
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CATALOG = Path(os.environ.get("SONGADAY_CATALOG_DIR",
                              Path.home() / "Library/Caches/songaday-display/publish/meta"))
N_SAMPLE = 20
SEED = 20261021


def slug(text):
    """Same rule as sources/places.py, only to find the cache file."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def norm(v):
    """Loose comparison: case, spaces and punctuation ignored."""
    return re.sub(r"[^a-z0-9#]+", "", str(v).lower())


def mmss_to_s(v):
    m = re.match(r"^\s*(\d+):(\d{1,2})", str(v))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def video_id(v):
    m = re.search(r"(?:youtu\.be/|v=|shorts/)([A-Za-z0-9_-]{11})", str(v))
    return m.group(1) if m else str(v).strip()


def load_catalog():
    """Newest file per chunk wins; songs deduped by number."""
    by_chunk = {}
    for f in glob.glob(str(CATALOG / "index-*.json")):
        chunk = Path(f).name.split("-")[1]
        if chunk not in by_chunk or os.path.getmtime(f) > os.path.getmtime(by_chunk[chunk]):
            by_chunk[chunk] = f
    songs = {}
    for f in by_chunk.values():
        for s in json.load(open(f))["songs"]:
            songs[s["n"]] = s
    return songs


def load_sheet():
    rows = {}
    with open(ROOT / "cache/sheet/sheet-gid0.csv", newline="", encoding="utf-8") as fh:
        r = csv.reader(fh)
        next(r)                      # the note row
        header = next(r)
        for row in r:
            if row and row[0].strip().isdigit():
                rows[int(row[0])] = dict(zip(header, row))
    return rows


def weather_from_cache(place, date):
    month = date[:7]
    path = ROOT / "cache/weather" / slug(place) / f"{month}.json"
    if not path.exists():
        return None
    blob = json.load(open(path))
    daily = blob["response"]["daily"]
    if date not in daily["time"]:
        return None
    i = daily["time"].index(date)
    return dict(lat=blob["params"]["latitude"], lon=blob["params"]["longitude"],
                tz=blob["response"].get("timezone"),
                temp_mean=daily["temperature_2m_mean"][i],
                precip=daily["precipitation_sum"][i], code=daily["weather_code"][i])


def moon_illum(date):
    local = datetime.fromisoformat(date).replace(hour=17, tzinfo=ZoneInfo("America/New_York"))
    m = ephem.Moon(ephem.Date(local.astimezone(timezone.utc).replace(tzinfo=None)))
    return m.moon_phase


def main():
    df = pd.read_csv(ROOT / "dataset/songaday.csv", keep_default_na=False, dtype=str)
    n = df["number"].astype(int)
    print("== whole-table invariants ==")
    print("rows", len(df), "| repeated numbers", int(n.duplicated().sum()),
          "| gaps", int(n.max() - n.min() + 1 - n.nunique()))
    d = pd.to_datetime(df["date"])
    print("date != 2009-01-01 + (n-1):", int(((d - pd.Timestamp("2009-01-01")).dt.days + 1
                                            != n).sum()))
    yt = df["youtube_id"][df["youtube_id"] != ""]
    print("repeated youtube ids:", int(yt.duplicated().sum()))

    sheet = load_sheet()
    catalog = load_catalog()
    # The sheet's own date column against the number rule.
    bad_dates = []
    for k, row in sheet.items():
        try:
            sd = datetime.strptime(row["date"].strip(), "%m/%d/%Y").date()
        except ValueError:
            bad_dates.append((k, row["date"]))
            continue
        if sd != (datetime(2009, 1, 1) + timedelta(days=k - 1)).date():
            bad_dates.append((k, row["date"]))
    print(f"sheet rows {len(sheet)}; sheet date column disagrees with number on "
          f"{len(bad_dates)} rows; first few: {bad_dates[:8]}")
    cat_bad = [k for k, s in catalog.items()
               if s.get("d") != str((datetime(2009, 1, 1) + timedelta(days=k - 1)).date())]
    print(f"catalog songs {len(catalog)}; catalog date disagrees with number on {len(cat_bad)}")

    # Mood/beard sheet vs catalog disagreement rate over every song both have, since the
    # dataset uses one of them.
    dis = {"Mood": 0, "Beard": 0, "Genre": 0}
    both = [k for k in sheet if k in catalog]
    for k in both:
        for fld, col in (("Mood", "mood"), ("Beard", "beard"), ("Genre", "genre")):
            if norm(sheet[k][col]) != norm(catalog[k]["a"].get(fld, "")):
                dis[fld] += 1
    print(f"sheet vs catalog disagreements over {len(both)} songs: {dis}")

    print(f"\n== {N_SAMPLE} random rows (seed {SEED}) ==")
    rng = np.random.default_rng(SEED)
    picks = sorted(rng.choice(len(df), N_SAMPLE, replace=False))
    snap = json.load(open(ROOT / "cache/views/youtube/toolkit-2026-10-18.json"))["videos"]
    mismatches = []
    for i in picks:
        r = df.iloc[i]
        k = int(r["number"])
        cat = catalog.get(k, {})
        a = cat.get("a", {})
        sh = sheet.get(k)
        checks = []
        # Fields: (name, dataset value, raw value, comparison)
        def add(name, ours, raw, same):
            checks.append((name, ours, raw, same))
        add("date/cat", r["date"], cat.get("d"), r["date"] == cat.get("d"))
        add("title/cat", r["title"], cat.get("t"), norm(r["title"]) == norm(cat.get("t", "")))
        add("loc/cat", r["location_raw"], a.get("Location"),
            norm(r["location_raw"]) == norm(a.get("Location", "")))
        add("mood/cat", r["mood"], a.get("Mood"), norm(r["mood"]) == norm(a.get("Mood", "")))
        add("beard/cat", r["beard"], a.get("Beard"), norm(r["beard"]) == norm(a.get("Beard", "")))
        add("genre/cat", r["genre"], a.get("Genre"), norm(r["genre"]) == norm(a.get("Genre", "")))
        L = mmss_to_s(a.get("Length", ""))
        add("length/cat", r["length_seconds"], a.get("Length"),
            (r["length_seconds"] == "" and L is None) or
            (L is not None and r["length_seconds"] != "" and abs(float(r["length_seconds"]) - L) < 1))
        add("yt/cat", r["youtube_id"], cat.get("yt"), r["youtube_id"] == cat.get("yt"))
        if sh:
            add("title/sheet", r["title"], sh["title"], norm(r["title"]) == norm(sh["title"]))
            add("loc/sheet", r["location_raw"], sh["location"],
                r["location_raw"].strip() == sh["location"].strip())
            add("mood/sheet", r["mood"], sh["mood"], norm(r["mood"]) == norm(sh["mood"]))
            add("beard/sheet", r["beard"], sh["beard"], norm(r["beard"]) == norm(sh["beard"]))
            add("genre/sheet", r["genre"], sh["genre"], norm(r["genre"]) == norm(sh["genre"]))
            t0 = r["topics"].split("|")[0] if r["topics"] else ""
            add("topic/sheet", t0, sh["topic"], norm(t0) in norm(sh["topic"]) or
                norm(sh["topic"]).startswith(norm(t0)[:4]))
            L = mmss_to_s(sh["length"])
            add("length/sheet", r["length_seconds"], sh["length"],
                L is not None and r["length_seconds"] != "" and
                abs(float(r["length_seconds"]) - L) < 1)
            add("tempo/sheet", r["tempo_bpm"], sh["tempo"],
                r["tempo_bpm"] != "" and str(sh["tempo"]).strip().startswith(
                    str(int(float(r["tempo_bpm"])))))
            add("key/sheet", r["key_raw"], sh["inKey"], norm(r["key_raw"]) == norm(sh["inKey"]))
            add("yt/sheet", r["youtube_id"], video_id(sh["videoID"]),
                r["youtube_id"] == video_id(sh["videoID"]))
        w = weather_from_cache(r["place"], r["date"])
        if w:
            add("weather coords", f"{r['place_lat']},{r['place_lon']}", f"{w['lat']},{w['lon']}",
                abs(float(r["place_lat"]) - w["lat"]) < 1e-3
                and abs(float(r["place_lon"]) - w["lon"]) < 1e-3)
            add("temp mean", r["weather_temperature_2m_mean"], w["temp_mean"],
                r["weather_temperature_2m_mean"] != "" and w["temp_mean"] is not None and
                abs(float(r["weather_temperature_2m_mean"]) - w["temp_mean"]) < 0.05)
            add("precip", r["weather_precipitation_sum"], w["precip"],
                r["weather_precipitation_sum"] != "" and w["precip"] is not None and
                abs(float(r["weather_precipitation_sum"]) - w["precip"]) < 0.05)
            add("wcode", r["weather_code"], w["code"],
                r["weather_code"] != "" and int(float(r["weather_code"])) == w["code"])
        else:
            add("weather cache", r["place"], None, False)
        v = snap.get(r["youtube_id"])
        if v is not None and r["yt_source"] == "youtube_api_via_toolkit":
            add("views/snapshot", r["yt_views"], v.get("views"),
                r["yt_views"] != "" and int(float(r["yt_views"])) == v.get("views"))
        ill = moon_illum(r["date"])
        add("moon illum", r["sky_moon_illumination"], round(ill, 4),
            abs(float(r["sky_moon_illumination"]) - ill) < 0.005)
        bad = [c for c in checks if not c[3]]
        print(f"#{k} {r['date']} {r['title'][:38]!r} place={r['place']!r} "
              f"home={r['is_home']} era={r['home_era']}: {len(checks) - len(bad)}/{len(checks)} ok")
        for c in bad:
            print(f"     MISMATCH {c[0]}: dataset={c[1]!r} raw={c[2]!r}")
            mismatches.append((k,) + c[:3])
    print(f"\n{len(mismatches)} mismatching fields across {N_SAMPLE} rows")


if __name__ == "__main__":
    main()
