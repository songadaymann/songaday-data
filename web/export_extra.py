"""Write web/lab-extra.json, the data behind the tools on songaday.studio/data.

lab.json (web/export.py) holds what the "every day" field and the charts draw. This file adds
what the lookups, the things to press and the "over the years" charts need: a few more values
per song (length, tempo, topics, instrument, weather, home), which videos are gone, and a few
sums per year. It uses only the standard library,
so it runs without the project's environment.

    python3 web/export_extra.py

Everything here is a plain count or median. None of it has been through the shuffle tests or
the two reviews that the findings in analysis/findings.md went through.
"""

import collections
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "lab-extra.json"

# Open-Meteo's labels, folded into four kinds of day.
WEATHER = {"clear": 0, "mostly clear": 0, "partly cloudy": 0, "cloudy": 1, "drizzle": 2, "rain": 2, "snow": 3}
WEATHER_LABELS = ["Clear", "Cloudy", "Rain", "Snow"]
# The three crypto topics count as one, so the page needs one plain word for them.
MERGE = {"NFTs": "Crypto", "Ethereum": "Crypto"}
# Topics too broad to say what a year was about.
BROAD = {"Poetic", "Life"}
INSTRUMENTS = 6       # how many main instruments get their own line
TOPICS_PER_YEAR = 4
GEM_MIN_VOTES = 3     # songaday.fan votes needed before a rating counts
GEM_MIN_SCORE = 8.0
# The four homes, in order. A song belongs to the home he had then, even if written on a trip.
ERAS = ["berkeley", "brooklyn", "jersey_city", "hartford"]
ERA_LABELS = ["Berkeley", "Brooklyn", "Jersey City", "Hartford"]


def number(value):
    try:
        return float(value)
    except ValueError:
        return None


def topics_of(song):
    """A song's topics, merged and without repeats, in the sheet's order."""
    return list(dict.fromkeys(MERGE.get(t, t) for t in song["topics"].split("|") if t))


def main():
    with open(ROOT / "dataset" / "songaday.csv", newline="") as handle:
        songs = sorted(csv.DictReader(handle), key=lambda row: int(row["number"]))
    assert [int(s["number"]) for s in songs] == list(range(1, len(songs) + 1)), "songaday.csv must be #1..#N with no gaps"

    topic_counts = collections.Counter(t for s in songs for t in topics_of(s))
    topic_labels = [t for t, _ in topic_counts.most_common()]
    topic_index = {t: i for i, t in enumerate(topic_labels)}
    inst_counts = collections.Counter(s["main_instrument"] for s in songs if s["main_instrument"])
    inst_labels = [i for i, _ in inst_counts.most_common()]
    inst_index = {name: i for i, name in enumerate(inst_labels)}

    def whole(value):
        value = number(value)
        return None if value is None else int(round(value))

    rows = {
        "len": [whole(s["length_seconds"]) for s in songs],
        "bpm": [whole(s["tempo_bpm"]) for s in songs],
        "topics": [[topic_index[t] for t in topics_of(s)] for s in songs],
        "inst": [inst_index.get(s["main_instrument"]) for s in songs],
        "wx": [WEATHER.get(s["weather_label"]) for s in songs],
        "era": [ERAS.index(s["home_era"]) if s["home_era"] in ERAS else None for s in songs],
    }
    # Songs whose video YouTube no longer returns: the page skips them where it shows a picture.
    gone = [int(s["number"]) for s in songs if s["yt_video_status"] == "unavailable" or not s["youtube_id"]]

    years = sorted({int(s["year"]) for s in songs})
    by_year = {y: [s for s in songs if int(s["year"]) == y] for y in years}

    def median(year, column):
        values = [v for v in (number(s[column]) for s in by_year[year]) if v is not None]
        return round(statistics.median(values), 1) if values else None

    top_inst = inst_labels[:INSTRUMENTS]
    inst_share = [[round(sum(1 for s in by_year[y] if s["main_instrument"] == name) / len(by_year[y]), 4) for y in years]
                  for name in top_inst]

    def year_topics(year):
        counts = collections.Counter(t for s in by_year[year] for t in topics_of(s) if t not in BROAD)
        return [[t, n] for t, n in counts.most_common(TOPICS_PER_YEAR)]

    views = sorted(v for v in (number(s["yt_views"]) for s in songs) if v is not None)
    median_views = statistics.median(views)
    gems = []
    for s in songs:
        votes, score, seen = number(s["fan_votes"]), number(s["fan_score"]), number(s["yt_views"])
        if votes and votes >= GEM_MIN_VOTES and score is not None and score >= GEM_MIN_SCORE and seen is not None and seen < median_views:
            gems.append({"n": int(s["number"]), "score": score, "votes": int(votes), "views": int(seen)})
    gems.sort(key=lambda g: (-g["score"], -g["votes"], g["views"]))

    data = {
        "labels": {"topic": topic_labels, "inst": inst_labels, "wx": WEATHER_LABELS, "era": ERA_LABELS},
        "songs": rows,
        "gone": gone,
        "years": years,
        "length_median": [median(y, "length_seconds") for y in years],
        "tempo_median": [median(y, "tempo_bpm") for y in years],
        "inst_share": {"names": top_inst, "share": inst_share},
        "topics_by_year": [year_topics(y) for y in years],
        "gems": gems,
        "gems_rule": {"min_votes": GEM_MIN_VOTES, "min_score": GEM_MIN_SCORE, "median_views": int(median_views),
                      "rated_songs": sum(1 for s in songs if number(s["fan_score"]) is not None)},
    }
    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    print(f"Wrote {OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1024:.0f} KB, {len(songs)} songs, {len(gems)} gems")


if __name__ == "__main__":
    main()
