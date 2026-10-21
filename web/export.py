"""Write web/lab.json, the data behind songaday.studio/data.

Reads dataset/songaday.csv, dataset/places.csv, dataset/news.csv and analysis/aggregates.json
(run the pipeline and analysis/analyze.py first) and keeps only what the page draws: one compact
row per song for the "every day" field, plus the few aggregates the charts need. The numbers
quoted in the page's text come from analysis/findings.md and analysis/second-opinions.md.

    .venv/bin/python web/export.py
"""

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "lab.json"

# Three mood families, so the field stays readable (a palette past three hues can't stay
# colorblind-safe when every colour sits next to every other). Anything else is "other".
BRIGHT = {"Silly", "Excited", "Happy", "Hopeful", "Funky"}
CALM = {"Pensive", "Chill", "Tired", "Bored", "Nostalgic"}
DARK = {"Sad", "Angry", "Anxious", "Intense", "Confused", "Pleading", "Scared", "Disgusted", "Annoyed"}


def family(mood):
    if mood in BRIGHT:
        return 0
    if mood in CALM:
        return 1
    if mood in DARK:
        return 2
    return None


def clean(value, digits=None):
    """JSON-safe number: NaN becomes None, optionally rounded."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), digits) if digits is not None else value


def main():
    songs = pd.read_csv(ROOT / "dataset" / "songaday.csv", low_memory=False).sort_values("number")
    places = pd.read_csv(ROOT / "dataset" / "places.csv")
    news = pd.read_csv(ROOT / "dataset" / "news.csv", usecols=["date", "n_items"])
    agg = json.loads((ROOT / "analysis" / "aggregates.json").read_text())

    assert list(songs["number"]) == list(range(1, len(songs) + 1)), "songaday.csv must be #1..#N with no gaps"

    # Place names for the readout: canonical place per song, as an index into a label list.
    place_col = "place" if "place" in songs.columns else "places_place"
    place_labels = sorted(songs[place_col].dropna().unique())
    place_index = {name: i for i, name in enumerate(place_labels)}
    mood_labels = sorted(songs["mood"].dropna().unique())
    mood_index = {name: i for i, name in enumerate(mood_labels)}

    def col(*names):
        for name in names:
            if name in songs.columns:
                return songs[name]
        raise KeyError(names)

    views = col("views", "yt_views")
    temp = col("weather_temperature_2m_mean", "temperature_2m_mean")
    moon = col("sky_moon_illumination", "moon_illumination")
    traveling = col("is_traveling")
    beard_map = {"Beard": 0, "Shadow": 1, "Clean": 2}

    rows = {
        "title": [str(t) for t in songs["title"].fillna("")],
        "yt": [str(y) if isinstance(y, str) else "" for y in songs["youtube_id"]],
        "mood": [mood_index.get(m) for m in songs["mood"]],
        "family": [family(m) for m in songs["mood"]],
        "minor": [None if m == "unknown" else int(m == "minor") for m in songs["mode"]],
        "key": [k if isinstance(k, str) else "" for k in songs["key"]],
        "temp": [clean(t, 1) for t in temp],
        "moon": [None if pd.isna(m) else int(round(m * 100)) for m in moon],
        "views": [None if pd.isna(v) else int(v) for v in views],
        "away": [None if pd.isna(t) else int(bool(t)) for t in traveling],
        "beard": [beard_map.get(b) for b in songs["beard"]],
        "place": [place_index.get(p) for p in songs[place_col]],
    }

    lengths = songs["length_seconds"].dropna()
    total_views = int(views.fillna(0).sum())
    ranked = views.fillna(0).sort_values(ascending=False)
    top_1pct = ranked.head(max(1, round(len(ranked) * 0.01))).sum()

    mood_by_year = agg["mood_by_year"]
    years = mood_by_year["years"]
    totals = [sum(column) for column in zip(*mood_by_year["counts"])]

    def share(mood):
        counts = mood_by_year["counts"][mood_by_year["moods"].index(mood)]
        return [round(c / t, 4) if t else None for c, t in zip(counts, totals)]

    terms = [t for t in agg["views_model"]["terms"]
             if (t["block"] == "topic" and t["n"] >= 40) or t["block"] == "mood"]

    data = {
        "meta": {
            "songs": len(songs),
            "first_date": str(songs["date"].iloc[0]),
            "last_date": str(songs["date"].iloc[-1]),
            "hours": round(lengths.sum() / 3600),
            "places": int(places["place"].nunique()),
            "views": total_views,
            "top_1pct_share": round(top_1pct / total_views, 3),
            "headlines": int(news["n_items"].sum()),
        },
        "labels": {"mood": mood_labels, "place": place_labels},
        "songs": rows,
        "weekday": [{"day": d["value"], "songs": d["songs"], "wild": d["wild_share"]} for d in agg["weekday"]],
        "angry_sad": {"years": years, "angry": share("Angry"), "sad": share("Sad")},
        "beard_months": {"months": agg["beard_by_month"]["months"], "states": agg["beard_by_month"]["states"],
                         "counts": agg["beard_by_month"]["counts"]},
        "views_terms": [{"block": t["block"], "term": t["term"].split(":", 1)[1], "n": t["n"],
                         "x": round(t["multiplier"], 3), "lo": round(t["ci_low"], 3), "hi": round(t["ci_high"], 3)}
                        for t in terms],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    print(f"Wrote {OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1024:.0f} KB, {len(songs)} songs")


if __name__ == "__main__":
    main()
