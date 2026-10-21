"""Join the per-source tables in dataset/ into dataset/songaday.csv: one row per Song A Day
song, with what is known about the song and about the day it was made.

Inputs (whichever exist; dataset/songs.csv is required):
  songs.csv         the cleaned song table, from sources/songs.py             key: number
  places.csv        each Location string mapped to a place (places.py)        key: location_raw
  weather.csv       the day's weather where the song was made (weather.py)    key: number
  sky.csv           moon, planets and eclipses for every date (sky.py)        key: date
  views.csv         YouTube views and songaday.fan ratings (views.py)         key: number
  news.csv          Wikipedia's Portal:Current events, per day (news.py)      key: date
  news_matches.csv  how strongly each song names that day's news (news.py)    key: number

Each column keeps its source's name, with a prefix that says where it came from: place_,
weather_, sky_, yt_ (YouTube), fan_ (songaday.fan) or news_. Song columns have no prefix
(except song_sources and song_flags). Derived columns are added for analysis: calendar
fields, season, home era, at home or traveling, major or minor. dataset/README.md documents
every column.

Left out on purpose, because they are long text that already lives in its own file:
songs.csv's generated_summary (machine-written, not Jonathan's words), news.csv's top_items
and news_matches.csv's matched_items (Wikipedia headline text, CC BY-SA 4.0). Keeping the
headline text out keeps songaday.csv under a single license, CC BY 4.0.

Checks. Any failure prints what's wrong, exits 1 and writes nothing:
  - songs.csv numbers run 1..N with no gaps or repeats, each date is 2009-01-01 + (number - 1)
    days, and its weekday and year agree with the date
  - every other table has unique keys, no keys outside the song list, and (where it has a
    date column) the same date for each song number
  - every song is covered by every table (--allow-gaps writes anyway, with blanks)
  - every Location string has a row in places.csv, and weather.csv's place agrees with it
  - the home-era boundaries below land on songs recorded at those homes
  - the output has one row per song, and the columns that should always be filled are
Then it prints the row count, each table's coverage and the blank rate of every column.

Run:  .venv/bin/python sources/merge.py
      .venv/bin/python sources/merge.py --allow-gaps   (when a source is behind the song list)
"""

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"
OUTPUT = DATASET / "songaday.csv"
DATA_DICTIONARY = DATASET / "README.md"

FIRST_DAY = dt.date(2009, 1, 1)  # song #1
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Northern-hemisphere meteorological seasons, by month. Every place in the data is north of
# the equator.
SEASONS = {12: "winter", 1: "winter", 2: "winter",
           3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer",
           9: "fall", 10: "fall", 11: "fall"}

# His homes. Each era starts the day after his last song at the previous home, so a move
# belongs to the era it leads into. Songs from the start of an era up to his first song at
# the new home are "between homes". Each row: era, number of its first song, number of the
# first song recorded at the new home, and the home town(s) as (city, region) pairs from
# places.csv. "Home" means anywhere in that town: his apartment, his studio, a cafe.
ERAS = [
    # January 2009 he was on the road (Los Angeles, NYC, Baltimore, Jupiter FL). #39
    # "Changing the Color of My Walls" (2009-02-08) is the first song from Berkeley.
    ("berkeley", 1, 39, {("Berkeley", "California")}),
    # #1040 "The Last Song I'll Ever Write in This Apartment" (2011-11-06), then the drive
    # east and four months with family in Canton, CT. #1161 "Super Tuesday Song" (2012-03-06,
    # Brooklyn Studio) is the first from Brooklyn. All of New York City counts as home in
    # these years: he lived in the city, and the sheet's "NYC" sometimes means Brooklyn.
    ("brooklyn", 1041, 1161, {("Brooklyn", "New York"), ("New York", "New York")}),
    # #2179 "2014 Song in Review" is the last from Windsor Terrace. #2180 "My Back is
    # Hurting" (2014-12-20) is the first from Jersey City.
    ("jersey_city", 2180, 2180, {("Jersey City", "New Jersey")}),
    # From May 2020 he was mostly with family (Severna Park, MD, then Avon, CT); #4214
    # (2020-07-15) is the last song from Jersey City. #4231 (2020-08-01, Hartford, CT Studio)
    # is the first from Hartford.
    ("hartford", 4215, 4231, {("Hartford", "Connecticut"), ("West Hartford", "Connecticut")}),
]

# Location strings that mean he was in transit. Their songs borrow a nearby song's place
# (see sources/places.py), which can be his home town, but he wasn't at home. "In The Car" is
# not here: most of those songs are local drives.
IN_TRANSIT = {"in the air", "airport"}

# Columns copied from each table, in output order: {source column: output column}.
WEATHER_COLUMNS = {
    "place": "place", "lat": "place_lat", "lon": "place_lon",
    "place_confidence": "place_confidence",
    "weather_code": "weather_code", "weather_label": "weather_label",
    "temperature_2m_max": "weather_temperature_2m_max",
    "temperature_2m_min": "weather_temperature_2m_min",
    "temperature_2m_mean": "weather_temperature_2m_mean",
    "precipitation_sum": "weather_precipitation_sum",
    "rain_sum": "weather_rain_sum",
    "snowfall_sum": "weather_snowfall_sum",
    "sunshine_duration": "weather_sunshine_duration",
    "daylight_duration": "weather_daylight_duration",
    "cloud_cover_mean": "weather_cloud_cover_mean",
    "wind_speed_10m_max": "weather_wind_speed_10m_max",
}
VIEWS_COLUMNS = {
    "views": "yt_views", "likes": "yt_likes", "comments": "yt_comments",
    "views_as_of": "yt_views_as_of", "source": "yt_source", "video_status": "yt_video_status",
    "youtube_channel": "yt_channel", "published_at": "yt_published_at", "note": "yt_note",
    "fan_good": "fan_good", "fan_okay": "fan_okay", "fan_bad": "fan_bad",
    "fan_votes": "fan_votes", "fan_score": "fan_score", "fan_as_of": "fan_as_of",
}
# The YouTube columns that describe one particular video (blanked if it's the wrong video).
VIDEO_COLUMNS = ["yt_views", "yt_likes", "yt_comments", "yt_views_as_of", "yt_source",
                 "yt_channel", "yt_published_at"]
NEWS_MATCH_COLUMNS = {
    "matched_terms": "news_matched_terms", "match_score": "news_match_score",
    "control_score": "news_control_score", "days_before": "news_match_days_before",
}
# Song columns renamed so they can't be mistaken for another table's.
SONG_RENAMES = {"sources": "song_sources", "flags": "song_flags"}
SONG_DROPPED = ["generated_summary"]   # long machine-written text; stays in songs.csv
NEWS_DROPPED = ["top_items"]           # Wikipedia headline text; stays in news.csv

# Columns that should never be blank when every table covers every song. Missing columns
# (a table that doesn't exist) are skipped.
ALWAYS_FILLED = [
    "number", "date", "year", "month", "day_of_year", "weekday", "is_weekend", "season",
    "days_since_start", "title", "location_raw", "mode", "song_sources",
    "home_era", "is_between_homes",
    "place", "place_lat", "place_lon", "place_region", "place_country",
    "place_kind", "place_confidence", "is_home", "is_traveling",
    "weather_code", "weather_label", "weather_temperature_2m_max", "weather_temperature_2m_min",
    "sky_moon_phase", "sky_moon_illumination", "sky_mercury_retrograde", "sky_sun_sign",
    "yt_video_status", "fan_votes", "fan_as_of",
    "news_n_items", "news_n_articles", "news_match_score", "news_control_score",
    "news_match_excess",
]
SONG_ONLY = {"number", "date", "year", "month", "day_of_year", "weekday", "is_weekend",
             "season", "days_since_start", "title", "location_raw", "mode", "song_sources",
             "home_era", "is_between_homes"}
# Columns that only weather.csv fills for context strings ("In The Car"), so they can be
# blank when weather.csv is missing.
PER_SONG_PLACE = {"place", "place_lat", "place_lon", "place_region", "place_country",
                  "place_confidence", "is_home", "is_traveling"}


def song_date(number):
    """Song #N's date: 2009-01-01 + (N - 1) days."""
    return FIRST_DAY + dt.timedelta(days=int(number) - 1)


def normalize(text):
    """A Location string compared loosely: outer and doubled spaces dropped, case folded."""
    return " ".join(text.split()).casefold()


def flag(value):
    """True/False as text, the way the other tables write booleans."""
    return "True" if value else "False"


def read_table(name):
    """A dataset CSV as text, exactly as written (no number or NaN parsing), or None."""
    path = DATASET / name
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def numbers_of(name, table, problems):
    """The table's song numbers as ints, or None if any is not a whole number."""
    numbers = pd.to_numeric(table["number"], errors="coerce")
    bad = table.loc[numbers.isna() | (numbers % 1 != 0), "number"]
    if len(bad):
        problems.append(f"{name}: {len(bad)} non-integer song numbers, e.g. {bad.iloc[0]!r}")
        return None
    return numbers.astype(int)


def check_songs(songs, problems):
    """songs.csv is the spine: numbers 1..N, the date formula, weekday and year."""
    numbers = numbers_of("songs.csv", songs, problems)
    if numbers is None:
        return
    if numbers.duplicated().any():
        problems.append(f"songs.csv: repeated numbers {sorted(numbers[numbers.duplicated()])[:10]}")
    expected = list(range(1, len(songs) + 1))
    if sorted(numbers) != expected:
        missing = sorted(set(expected) - set(numbers))
        problems.append(f"songs.csv: numbers are not 1..{len(songs)}; missing {missing[:10]}")
    dates = numbers.map(lambda n: song_date(n).isoformat())
    wrong = songs[songs["date"] != dates]
    if len(wrong):
        problems.append(f"songs.csv: {len(wrong)} dates are not 2009-01-01 + (number - 1), "
                        f"e.g. #{wrong.iloc[0]['number']} {wrong.iloc[0]['date']}")
    weekdays = numbers.map(lambda n: WEEKDAYS[song_date(n).weekday()])
    if (songs["weekday"] != weekdays).any():
        problems.append(f"songs.csv: {(songs['weekday'] != weekdays).sum()} weekdays disagree with the date")
    years = numbers.map(lambda n: str(song_date(n).year))
    if (songs["year"] != years).any():
        problems.append(f"songs.csv: {(songs['year'] != years).sum()} years disagree with the date")


def check_by_number(name, table, song_numbers, problems, gaps):
    """A table keyed by song number: unique, inside the song list, same dates, full coverage."""
    numbers = numbers_of(name, table, problems)
    if numbers is None:
        return
    if numbers.duplicated().any():
        problems.append(f"{name}: repeated numbers {sorted(numbers[numbers.duplicated()])[:10]}")
    extra = sorted(set(numbers) - song_numbers)
    if extra:
        problems.append(f"{name}: {len(extra)} numbers not in songs.csv, e.g. {extra[:10]}")
    missing = sorted(song_numbers - set(numbers))
    if missing:
        gaps.append(f"{name}: no row for {len(missing)} songs, e.g. {missing[:10]}")
    if "date" in table.columns:
        dates = numbers.map(lambda n: song_date(n).isoformat())
        wrong = table[table["date"] != dates]
        if len(wrong):
            problems.append(f"{name}: {len(wrong)} dates disagree with the song number, "
                            f"e.g. #{wrong.iloc[0]['number']} {wrong.iloc[0]['date']}")


def check_by_date(name, table, song_dates, problems, gaps):
    """A table keyed by calendar date: unique, valid ISO dates, covering every song's date."""
    parsed = pd.to_datetime(table["date"], format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        problems.append(f"{name}: {parsed.isna().sum()} rows have a date that isn't YYYY-MM-DD")
    if table["date"].duplicated().any():
        problems.append(f"{name}: repeated dates, e.g. {table.loc[table['date'].duplicated(), 'date'].iloc[0]}")
    missing = sorted(song_dates - set(table["date"]))
    if missing:
        gaps.append(f"{name}: no row for {len(missing)} song dates, e.g. {missing[:5]}")


def place_lookup(places, songs, problems):
    """Map each song's Location string to its places.csv row (by exact string, then loosely).

    songs.csv keeps the sheet's own spelling for #1-#5101 and places.csv the catalog's, so a
    few differ only in spacing or case ("Prague " and "Prague", "nyc" and "NYC")."""
    if places["location_raw"].duplicated().any():
        problems.append("places.csv: repeated location_raw values")
    exact = set(places["location_raw"])
    loose = {}
    for raw in places["location_raw"]:
        loose.setdefault(normalize(raw), []).append(raw)
    matched, loose_matches = {}, 0
    for raw in songs["location_raw"].unique():
        if raw in exact:
            matched[raw] = raw
        elif len(loose.get(normalize(raw), [])) == 1:
            matched[raw] = loose[normalize(raw)][0]
            loose_matches += (songs["location_raw"] == raw).sum()
        else:
            problems.append(f"places.csv: no single row for Location {raw!r} "
                            f"(songs {songs.loc[songs['location_raw'] == raw, 'number'].tolist()[:5]})")
    return matched, loose_matches


def check_eras(home_town, problems):
    """Each era boundary must sit where the data says the move happened."""
    for i, (era, first, arrival, towns) in enumerate(ERAS):
        if arrival in home_town.index and home_town[arrival] not in towns:
            problems.append(f"home era {era}: song #{arrival}, its first song at home, was "
                            f"recorded in {home_town[arrival]}")
        if i > 0 and first - 1 in home_town.index and home_town[first - 1] not in ERAS[i - 1][3]:
            problems.append(f"home era {ERAS[i - 1][0]}: song #{first - 1}, its last song at "
                            f"home, was recorded in {home_town[first - 1]}")
    starts = [first for _, first, _, _ in ERAS]
    if starts != sorted(starts) or starts[0] != 1:
        problems.append("ERAS must start at song #1 and be in order")


def documented_columns():
    """Column names listed in dataset/README.md's tables (rows that start with | `name`)."""
    if not DATA_DICTIONARY.exists():
        return set()
    text = DATA_DICTIONARY.read_text(encoding="utf-8")
    return set(re.findall(r"^\|\s*`([a-z0-9_]+)`", text, flags=re.M))


def fail(problems):
    print("\nMERGE FAILED; dataset/songaday.csv was not written:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--allow-gaps", action="store_true",
                        help="write the table even if some source doesn't cover every song yet")
    args = parser.parse_args()

    problems = []  # anything in here stops the merge
    gaps = []      # songs a table doesn't cover yet; these stop it too, unless --allow-gaps

    # ---- Read and check every input ------------------------------------------------------
    songs = read_table("songs.csv")
    if songs is None:
        fail(["dataset/songs.csv is missing; run sources/songs.py first"])
    check_songs(songs, problems)
    if problems:
        fail(problems)
    songs["number"] = songs["number"].astype(int)
    songs = songs.sort_values("number").reset_index(drop=True)
    song_numbers = set(songs["number"])
    song_dates = set(songs["date"])

    names = ["places.csv", "weather.csv", "sky.csv", "views.csv", "news.csv", "news_matches.csv"]
    tables = {name: read_table(name) for name in names}
    print(f"songs.csv: {len(songs):,} songs, #1-#{len(songs)}, "
          f"{songs['date'].iloc[0]} to {songs['date'].iloc[-1]}")
    for name in names:
        table = tables[name]
        if table is None:
            print(f"{name}: MISSING, so its columns are left out (run its script in sources/)")
        else:
            print(f"{name}: {len(table):,} rows, {len(table.columns)} columns")

    for name in ["weather.csv", "views.csv", "news_matches.csv"]:
        if tables[name] is not None:
            check_by_number(name, tables[name], song_numbers, problems, gaps)
    for name in ["sky.csv", "news.csv"]:
        if tables[name] is not None:
            check_by_date(name, tables[name], song_dates, problems, gaps)
    places = tables["places.csv"]
    if places is not None:
        location_key, loose_matches = place_lookup(places, songs, problems)
    if problems:
        fail(problems)
    if gaps and not args.allow_gaps:
        fail(gaps + ["(rerun the source's script, or pass --allow-gaps to write with blanks)"])

    # ---- Song columns and the calendar ---------------------------------------------------
    days = songs["number"].map(song_date)
    out = pd.DataFrame({
        "number": songs["number"].astype(str),
        "date": songs["date"],
        "year": days.map(lambda d: str(d.year)),
        "month": days.map(lambda d: str(d.month)),
        "day_of_year": days.map(lambda d: str(d.timetuple().tm_yday)),
        "weekday": days.map(lambda d: WEEKDAYS[d.weekday()]),
        "is_weekend": days.map(lambda d: flag(d.weekday() >= 5)),
        "season": days.map(lambda d: SEASONS[d.month]),
        "days_since_start": (songs["number"] - 1).astype(str),
    })
    song_columns = [c for c in songs.columns
                    if c not in ("number", "date", "weekday", "year") and c not in SONG_DROPPED]
    for column in song_columns:
        out[SONG_RENAMES.get(column, column)] = songs[column]
        if column == "mode":
            # Blank, not False, when the key's mode is unknown, so the share of major songs
            # isn't diluted by songs with no recorded mode.
            out["is_major"] = songs["mode"].map({"major": "True", "minor": "False"}).fillna("")
            out["is_minor"] = songs["mode"].map({"major": "False", "minor": "True"}).fillna("")

    # ---- Place, home era, at home or away ------------------------------------------------
    era_of = pd.Series("", index=songs.index)
    between = pd.Series(False, index=songs.index)
    for era, first, arrival, _ in ERAS:
        in_era = songs["number"] >= first
        era_of[in_era] = era
        between[in_era] = songs.loc[in_era, "number"] < arrival
    out["home_era"] = era_of
    out["is_between_homes"] = between.map(flag)

    weather = tables["weather.csv"]
    if weather is not None:
        weather = weather.assign(number=weather["number"].astype(int)).set_index("number")
        weather = weather.reindex(songs["number"]).fillna("")
        for source, target in WEATHER_COLUMNS.items():
            if source in ("place", "lat", "lon", "place_confidence"):
                out[target] = weather[source].to_numpy()
    if places is not None:
        by_string = places.set_index("location_raw")
        keys = songs["location_raw"].map(location_key)
        string_place = keys.map(by_string["place"]).to_numpy()
        if weather is not None:
            # weather.csv's per-song place must agree with places.csv wherever the string has
            # a single place.
            given = out["place"].to_numpy()
            wrong = (string_place != "") & (given != "") & (string_place != given)
            if wrong.any():
                problems.append(f"weather.csv and places.csv disagree on the place of "
                                f"{wrong.sum()} songs, e.g. #{out.loc[wrong, 'number'].iloc[0]}")
        # Without weather.csv, or for a song it doesn't cover yet, the place comes straight
        # from places.csv. Context strings ("In The Car") then have no place, because theirs
        # depends on the song.
        fill = (out["place"] == "") if "place" in out.columns else pd.Series(True, index=out.index)
        for source, target in [("place", "place"), ("lat", "place_lat"), ("lon", "place_lon"),
                               ("confidence", "place_confidence")]:
            if target not in out.columns:
                out[target] = ""
            out.loc[fill, target] = keys[fill].map(by_string[source]).to_numpy()
        # City, region and country belong to the place, so context songs get them too.
        named = places[places["place"] != ""].drop_duplicates("place").set_index("place")
        unknown = set(out["place"]) - set(named.index) - {""}
        if unknown:
            problems.append(f"places in weather.csv that places.csv doesn't list: {sorted(unknown)[:5]}")
        out["place_city"] = out["place"].map(named["city"]).fillna("")
        out["place_region"] = out["place"].map(named["region"]).fillna("")
        out["place_country"] = out["place"].map(named["country"]).fillna("")
        out["place_kind"] = keys.map(by_string["kind"]).to_numpy()
        out["place_note"] = keys.map(by_string["note"]).to_numpy()

        # At home: in the era's home town, settled there, and not on a plane or at an airport.
        town = pd.Series(list(zip(out["place_city"], out["place_region"])), index=songs["number"])
        check_eras(town, problems)
        homes = {era: towns for era, _, _, towns in ERAS}
        in_town = [pair in homes[era] for pair, era in zip(town, out["home_era"])]
        transit = songs["location_raw"].map(normalize).isin(IN_TRANSIT).to_numpy()
        at_home = pd.Series(in_town, index=out.index) & ~between & ~transit
        known = out["place"] != ""
        out["is_home"] = [flag(h) if k else "" for h, k in zip(at_home, known)]
        out["is_traveling"] = [flag(not h) if k else "" for h, k in zip(at_home, known)]
        # Keep place columns together, in a fixed order.
        place_order = ["place", "place_city", "place_region", "place_country", "place_lat",
                       "place_lon", "place_kind", "place_confidence", "place_note",
                       "home_era", "is_home", "is_traveling", "is_between_homes"]
        out = out[[c for c in out.columns if c not in place_order] + place_order]

    # ---- Weather -------------------------------------------------------------------------
    if weather is not None:
        for source, target in WEATHER_COLUMNS.items():
            if source not in ("place", "lat", "lon", "place_confidence"):
                out[target] = weather[source].to_numpy()

    # ---- Sky (by date) -------------------------------------------------------------------
    sky = tables["sky.csv"]
    if sky is not None:
        sky = sky.set_index("date").reindex(out["date"]).fillna("")
        for column in sky.columns:
            out[f"sky_{column}"] = sky[column].to_numpy()

    # ---- YouTube views and songaday.fan ratings ------------------------------------------
    views = tables["views.csv"]
    wrong_video = []
    if views is not None:
        views = views.assign(number=views["number"].astype(int)).set_index("number")
        views = views.reindex(songs["number"]).fillna("")
        for source, target in VIEWS_COLUMNS.items():
            out[target] = views[source].to_numpy()
        # The counts belong to views.csv's video. Where songs.csv settled on a different
        # video (or none), they describe the wrong video, so blank them and say why.
        for i in out.index[(views["youtube_id"].to_numpy() != out["youtube_id"].to_numpy())]:
            theirs, ours = views["youtube_id"].iloc[i], out.at[i, "youtube_id"]
            wrong_video.append(int(out.at[i, "number"]))
            for column in VIDEO_COLUMNS:
                out.at[i, column] = ""
            out.at[i, "yt_video_status"] = "no_video" if ours == "" else "not_checked"
            out.at[i, "yt_note"] = (f"views.csv counted video {theirs or '(none)'}, but "
                                    f"songs.csv gives this song {ours or 'no video'}")
        # Days the video had been up when it was counted, to compare views fairly.
        published = pd.to_datetime(out["yt_published_at"], format="%Y-%m-%d", errors="coerce")
        as_of = pd.to_datetime(out["yt_views_as_of"], format="%Y-%m-%d", errors="coerce")
        days_online = (as_of - published).dt.days
        out["yt_days_online"] = days_online.map(lambda d: "" if pd.isna(d) else str(int(d)))
        if (days_online < 0).any():
            problems.append(f"{(days_online < 0).sum()} videos were counted before they were published")
        yt_order = ["yt_views", "yt_likes", "yt_comments", "yt_views_as_of", "yt_days_online",
                    "yt_source", "yt_video_status", "yt_channel", "yt_published_at", "yt_note"]
        rest = [c for c in out.columns if c not in yt_order and not c.startswith("fan_")]
        fan = [c for c in out.columns if c.startswith("fan_")]
        out = out[rest + yt_order + fan]

    # ---- News of the day (by date) -------------------------------------------------------
    news = tables["news.csv"]
    if news is not None:
        news = news.set_index("date").reindex(out["date"]).fillna("")
        for column in news.columns:
            if column not in NEWS_DROPPED:
                out[f"news_{column}"] = news[column].to_numpy()

    # ---- How strongly each song names that news ------------------------------------------
    matches = tables["news_matches.csv"]
    if matches is not None:
        matches = matches.assign(number=matches["number"].astype(int)).set_index("number")
        matches = matches.reindex(songs["number"]).fillna("")
        for source, target in NEWS_MATCH_COLUMNS.items():
            out[target] = matches[source].to_numpy()
        score = pd.to_numeric(out["news_match_score"], errors="coerce")
        control = pd.to_numeric(out["news_control_score"], errors="coerce")
        out["news_match_excess"] = (score - control).map(lambda x: "" if pd.isna(x) else f"{x:.2f}")
        out = out[[c for c in out.columns if c != "news_match_days_before"] + ["news_match_days_before"]]
        title_diffs = (matches["title"].to_numpy() != out["title"].to_numpy()).sum()

    # ---- Check the result ----------------------------------------------------------------
    if len(out) != len(songs) or out["number"].duplicated().any():
        problems.append(f"the merge made {len(out)} rows for {len(songs)} songs")
    if out.columns.duplicated().any():
        problems.append(f"repeated columns: {list(out.columns[out.columns.duplicated()])}")
    if (out["date"] != out["number"].map(lambda n: song_date(n).isoformat())).any():
        problems.append("dates no longer match song numbers after the merge")
    must_fill = [c for c in ALWAYS_FILLED if c in out.columns and (c in SONG_ONLY or not gaps)
                 and not (weather is None and c in PER_SONG_PLACE)]
    for column in must_fill:
        blank = out[column] == ""
        if blank.any():
            problems.append(f"{column} is blank for {blank.sum()} songs, e.g. "
                            f"#{out.loc[blank, 'number'].iloc[0]}")
    if problems:
        fail(problems)

    OUTPUT.write_text(out.to_csv(index=False, lineterminator="\n"), encoding="utf-8")

    # ---- Summary -------------------------------------------------------------------------
    print(f"\nWrote {OUTPUT.relative_to(ROOT)}: {len(out):,} rows x {len(out.columns)} columns, "
          f"{OUTPUT.stat().st_size / 1e6:.2f} MB")
    for gap in gaps:
        print(f"  GAP (allowed): {gap}")
    if places is not None:
        print(f"  Location strings matched loosely (spacing or case): {loose_matches} songs")
    if views is not None:
        print(f"  YouTube counts blanked because views.csv counted another video: "
              f"{len(wrong_video)} {wrong_video[:10]}")
    if matches is not None:
        print(f"  news_matches.csv titles that differ from songs.csv (songs.csv kept): {title_diffs}")

    if "is_home" in out.columns:
        print("\n  Home eras:")
        for era, first, arrival, _ in ERAS:
            rows = out[out["home_era"] == era]
            home = (rows["is_home"] == "True").sum()
            print(f"    {era:<12} #{rows['number'].iloc[0]:>4}-#{rows['number'].iloc[-1]:<5}"
                  f" {rows['date'].iloc[0]} to {rows['date'].iloc[-1]}  {len(rows):>5} songs, "
                  f"{home:>5} at home ({home / len(rows):.0%}), "
                  f"{(rows['is_between_homes'] == 'True').sum()} between homes")

    print("\n  Blank cells per column (columns not listed are always filled):")
    blanks = (out == "").sum()
    for column, count in blanks[blanks > 0].items():
        print(f"    {column:<36} {count:>5} blank  ({count / len(out):6.1%})")
    print(f"  {int((blanks == 0).sum())} of {len(out.columns)} columns have no blanks.")

    documented = documented_columns()
    undocumented = [c for c in out.columns if c not in documented]
    stale = sorted(documented - set(out.columns))
    if undocumented:
        print(f"\nWARNING: dataset/README.md doesn't document {undocumented}", file=sys.stderr)
    if stale:
        print(f"\nWARNING: dataset/README.md documents columns that aren't in the table: {stale}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
