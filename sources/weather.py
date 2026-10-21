"""The weather on the day of each Song A Day song, where it was made, from Open-Meteo's
historical weather archive (https://open-meteo.com/en/docs/historical-weather-api; free, no
key).

Each song's place comes from sources/places.py (the same tables that write
dataset/places.csv; songs recorded "In The Car" and the like borrow the place of the nearest
song with a real one). For every place, the archive is asked for daily weather, one request
per calendar month the place was used, covering the first to the last song date there that
month. That fetches only the days that are needed: a single request per place over its whole
span would download about 100,000 days for 6,500 songs and use most of the free tier's daily
quota (Open-Meteo counts a request as more than one call when it covers over 14 days).

Raw responses are cached in cache/weather/<place>/<YYYY-MM>.json with the request and the
date fetched, so a rerun downloads nothing new except chunks that changed (a new song in the
current month) or that were fetched within a week of their last day. The newest days come from
a preliminary analysis, and ERA5 replaces them about five days later.

Output: dataset/weather.csv, one row per song.
  number, date          song number and its date (2009-01-01 is #1)
  place, lat, lon       where it was made, from dataset/places.csv
  weather_code          WMO weather code for the day: the most severe weather of the day
  temperature_2m_max    daily high, degrees C (2 m above ground)
  temperature_2m_min    daily low, degrees C
  temperature_2m_mean   daily mean, degrees C
  precipitation_sum     rain + showers + snow (as water), mm
  rain_sum              rain and showers, mm
  snowfall_sum          snowfall, cm
  sunshine_duration     seconds of direct sunshine
  daylight_duration     seconds from sunrise to sunset
  cloud_cover_mean      mean cloud cover, %
  wind_speed_10m_max    strongest wind of the day (10 m above ground), km/h
  weather_label         plain words for weather_code: clear, mostly clear, partly cloudy,
                        cloudy, fog, drizzle, rain, snow, storm
  place_confidence      high / medium / low, from places.csv; "low" means the place is a
                        guess (a state with no town, or borrowed from a neighboring song)
Days are local days at the place (timezone=auto). Values are for the reanalysis grid cell
(about 9-25 km across) that contains the place, so they describe the area, not a street.

Run:  .venv/bin/python sources/weather.py             (fetches only what isn't cached)
      .venv/bin/python sources/weather.py --offline   (cache only, no network)

Paths, all optional:
  SONGADAY_CATALOG_DIR  songaday-display publish/meta folder (see sources/places.py)

Weather data by Open-Meteo.com, CC BY 4.0. It is built on ERA5 and ERA5-Land reanalysis from
the Copernicus Climate Change Service (ECMWF).
"""

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import places  # sources/places.py

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "weather"
OUT_CSV = ROOT / "dataset" / "weather.csv"

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = [
    "weather_code", "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "precipitation_sum", "rain_sum", "snowfall_sum", "sunshine_duration",
    "daylight_duration", "cloud_cover_mean", "wind_speed_10m_max",
]
# Open-Meteo's defaults are already metric (degrees C, km/h, mm; snowfall in cm).
UNITS = {"temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm"}
FINAL_AFTER_DAYS = 7  # a chunk fetched this long after its last day won't change

COLUMNS = ["number", "date", "place", "lat", "lon", *DAILY, "weather_label",
           "place_confidence"]
WHOLE_SECONDS = {"sunshine_duration", "daylight_duration"}  # rounded to whole seconds

# WMO weather codes (the subset Open-Meteo uses) in plain words.
WMO_LABELS = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "drizzle", 57: "drizzle",
    61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
    80: "rain", 81: "rain", 82: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow", 85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}


def weather_label(code):
    if code is None:
        return ""
    return WMO_LABELS.get(int(code), f"code {int(code)}")


def plan_chunks(songs_out):
    """Group songs into requests: one per place per calendar month, from the first to the last
    song date there that month."""
    chunks = defaultdict(list)
    for song in songs_out:
        chunks[(song["place"], song["date"][:7])].append(song)
    plan = []
    for (place, month), songs in sorted(chunks.items()):
        dates = sorted(song["date"] for song in songs)
        plan.append({"place": place, "month": month, "lat": songs[0]["lat"],
                     "lon": songs[0]["lon"], "start": dates[0], "end": dates[-1],
                     "songs": songs})
    return plan


def request_params(chunk):
    return {"latitude": chunk["lat"], "longitude": chunk["lon"],
            "start_date": chunk["start"], "end_date": chunk["end"],
            "daily": ",".join(DAILY), "timezone": "auto", **UNITS}


def cached_response(chunk, params, today):
    """The cached answer for a chunk, if it was asked the same question and is still good."""
    path = CACHE_DIR / places.slug(chunk["place"]) / f"{chunk['month']}.json"
    if not path.exists():
        return None
    saved = json.loads(path.read_text())
    if saved.get("params") != params:
        return None  # new songs this month, or the place moved
    fetched = dt.date.fromisoformat(saved["fetched"])
    final = (fetched - dt.date.fromisoformat(chunk["end"])).days >= FINAL_AFTER_DAYS
    if final or fetched == today:
        return saved["response"]
    return None  # recent days that were preliminary when fetched; ask again


def fetch_chunk(chunk, params, today):
    response = places.fetch_json(ARCHIVE_URL, params,
                                 f"weather {chunk['place']} {chunk['month']}")
    path = CACHE_DIR / places.slug(chunk["place"]) / f"{chunk['month']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched": today.isoformat(), "params": params,
                                "response": response}))
    return response


def song_rows(chunk, response):
    """One output row per song in the chunk, filled from the API's daily arrays."""
    daily = (response or {}).get("daily", {})
    index = {day: i for i, day in enumerate(daily.get("time", []))}
    rows = []
    for song in chunk["songs"]:
        row = {"number": song["number"], "date": song["date"], "place": song["place"],
               "lat": song["lat"], "lon": song["lon"],
               "place_confidence": song["confidence"]}
        i = index.get(song["date"])
        for name in DAILY:
            value = daily.get(name, [])[i] if i is not None else None
            if value is not None and name in WHOLE_SECONDS:
                value = round(value)
            if value is not None and name == "weather_code":
                value = int(value)
            row[name] = value
        row["weather_label"] = weather_label(row["weather_code"])
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    args = parser.parse_args()

    _places, songs_out, _table = places.build()
    plan = plan_chunks(songs_out)
    today = dt.date.today()

    rows, fetched, missing_chunks = [], 0, []
    for number, chunk in enumerate(plan, 1):
        params = request_params(chunk)
        response = cached_response(chunk, params, today)
        if response is None and not args.offline:
            response = fetch_chunk(chunk, params, today)
            fetched += 1
            if fetched % 50 == 0:
                print(f"  fetched {fetched} chunks ({number} of {len(plan)} done)")
        if response is None:
            missing_chunks.append(f"{chunk['place']} {chunk['month']}")
        rows.extend(song_rows(chunk, response))

    rows.sort(key=lambda row: row["number"])
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    # Coverage report.
    complete = [row for row in rows if all(row[name] is not None for name in DAILY)]
    some = [row for row in rows if any(row[name] is not None for name in DAILY)]
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}: {len(rows)} songs, {len(plan)} place-month "
          f"requests ({fetched} fetched now, {len(plan) - fetched - len(missing_chunks)} "
          f"from cache)")
    print(f"  weather for {len(some)} of {len(rows)} songs; all {len(DAILY)} values for "
          f"{len(complete)}")
    for name in DAILY:
        gaps = sum(row[name] is None for row in rows)
        if gaps:
            print(f"  {name}: missing for {gaps} songs")
    if missing_chunks:
        print(f"  {len(missing_chunks)} chunks not cached (offline?): "
              + ", ".join(missing_chunks[:10]))
    with_weather = {row["number"] for row in some}
    without = [row["number"] for row in rows if row["number"] not in with_weather]
    if without:
        print(f"  songs with no weather: {without[:30]}{' ...' if len(without) > 30 else ''}")
    print("  labels:", dict(Counter(row["weather_label"] for row in rows).most_common()))


if __name__ == "__main__":
    sys.exit(main())
