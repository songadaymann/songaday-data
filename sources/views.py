"""How popular each Song A Day song is: YouTube views, likes and comments, plus the Good /
Okay / Bad votes listeners give it on songaday.fan. Every number says where it came from and
when it was counted.

Sources for the YouTube numbers, best first:
1. YouTube Data API v3 videos.list (part=snippet,statistics, 50 ids per call), only when a
   YOUTUBE_API_KEY is set in this repo's .env or the environment. Raw responses are cached in
   cache/views/youtube/api-YYYY-MM-DD/, so a rerun never refetches.
2. The snapshot the songaday-toolkit made through the same public API (its
   output/youtube-description-audit-*/youtube-api-cache.json, fetched 2026-10-18). A slim copy
   goes to cache/views/youtube/toolkit-YYYY-MM-DD.json, so later runs work without the toolkit.
3. The "views" column of Jonathan's master spreadsheet, as exported into the songaday.fan app
   (song-a-day-rating-app/src/data/songs.json, exported 2026-08-04, counted on or before that
   day). Used only for videos the public API no longer returns, such as removed or private
   ones. A slim copy goes to cache/views/sheet-views-YYYY-MM-DD.json.
When a video appears in more than one snapshot, the newest count wins.

Listener ratings come from songaday.fan's public, no-login endpoint
GET https://songaday.fan/api/ratings?songIds=1,2,... (100 ids per call). The site scores
Good as 10, Okay as 5 and Bad as 0; fan_score is the average, from 0 to 10. Responses are
cached in cache/views/fan-ratings/YYYY-MM-DD/. songaday.fan doesn't publish per-song play
counts, so there are none here.

Output: dataset/views.csv, one row per song in the catalog.

Run:  .venv/bin/python sources/views.py                  (fetches only what isn't cached)
      .venv/bin/python sources/views.py --offline        (cache only, no network)
      .venv/bin/python sources/views.py --refresh-fan    (new songaday.fan ratings snapshot)
      .venv/bin/python sources/views.py --refresh-youtube  (new API snapshot; needs a key)

Paths, all optional:
  SONGADAY_CATALOG_DIR  songaday-display publish/meta folder (index-*.json chunks)
                        default ~/Library/Caches/songaday-display/publish/meta
  SONGADAY_TOOLKIT_DIR  songaday-toolkit checkout, default ../songaday-toolkit
  SONGADAY_FAN_APP_DIR  song-a-day-rating-app checkout, default ../song-a-day-rating-app
  YOUTUBE_API_KEY       YouTube Data API v3 key (never printed or cached)
"""

import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "views"
YOUTUBE_CACHE = CACHE_DIR / "youtube"
FAN_CACHE = CACHE_DIR / "fan-ratings"
OUT_CSV = ROOT / "dataset" / "views.csv"

CATALOG_DIR = Path(
    os.environ.get("SONGADAY_CATALOG_DIR")
    or Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta"
)
TOOLKIT_DIR = Path(os.environ.get("SONGADAY_TOOLKIT_DIR") or ROOT.parent / "songaday-toolkit")
FAN_APP_DIR = Path(os.environ.get("SONGADAY_FAN_APP_DIR") or ROOT.parent / "song-a-day-rating-app")

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
FAN_RATINGS_URL = "https://songaday.fan/api/ratings"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"

YOUTUBE_BATCH = 50  # videos.list takes at most 50 ids
FAN_BATCH = 100  # songaday.fan's /api/ratings takes at most 100 ids
REQUEST_PAUSE = 0.5  # seconds between live requests; one request at a time

# The source labels written to the "source" column.
SOURCE_API = "youtube_api"
SOURCE_TOOLKIT = "youtube_api_via_toolkit"
SOURCE_SHEET = "sheet_views_column"

COLUMNS = [
    "number",
    "youtube_id",
    "views",
    "likes",
    "comments",
    "views_as_of",
    "source",
    "video_status",
    "youtube_channel",
    "published_at",
    "fan_good",
    "fan_okay",
    "fan_bad",
    "fan_votes",
    "fan_score",
    "fan_as_of",
    "note",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def load_dotenv():
    """Read KEY=VALUE lines from this repo's .env into os.environ (without overriding)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    tmp.replace(path)


def to_int(value):
    """YouTube sends counts as strings; missing means hidden or turned off."""
    if value is None or value == "":
        return None
    return int(value)


def get_json(url, params, attempts=6):
    """GET a JSON URL politely: descriptive User-Agent, backoff on 429 and 5xx errors."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
        except requests.RequestException as error:
            wait = 2**attempt
            print(f"  network error ({error.__class__.__name__}), retrying in {wait}s")
            time.sleep(wait)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            wait = int(response.headers.get("Retry-After") or 2**attempt)
            print(f"  HTTP {response.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            # Show the API's own reason (e.g. quotaExceeded) but never the request URL,
            # which would contain the API key.
            reason = response.text[:300].replace("\n", " ")
            raise RuntimeError(f"HTTP {response.status_code}: {reason}")
        return response.json()
    raise RuntimeError(f"gave up after {attempts} attempts")


# ---------------------------------------------------------------------------
# 1. The song catalog
# ---------------------------------------------------------------------------


def load_catalog():
    """Return {song number: youtube id or None} from the songaday-display index chunks.

    Some chunks exist in two hashed versions; the newest file wins for each song.
    """
    files = sorted(glob.glob(str(CATALOG_DIR / "index-*.json")), key=os.path.getmtime)
    if not files:
        sys.exit(f"No index-*.json catalog chunks in {CATALOG_DIR} (set SONGADAY_CATALOG_DIR)")
    songs = {}
    for path in files:
        for song in json.loads(Path(path).read_text())["songs"]:
            songs[song["n"]] = song.get("yt") or None
    return dict(sorted(songs.items()))


# ---------------------------------------------------------------------------
# 2. YouTube snapshots
#
# Every snapshot is saved in the same slim shape:
#   {"source": label, "videos": {video id: {fetched_at, status, views, likes, comments,
#                                            channel, published_at}}}
# status is "returned" (the public API gave statistics) or "unavailable" (it didn't).
# ---------------------------------------------------------------------------


def slim_video(fetched_at, item, channel_titles):
    """Turn one videos.list item (or None for a missing id) into the slim shape."""
    if not item:
        return {"fetched_at": fetched_at, "status": "unavailable"}
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    return {
        "fetched_at": fetched_at,
        "status": "returned",
        "views": to_int(stats.get("viewCount")),
        "likes": to_int(stats.get("likeCount")),
        "comments": to_int(stats.get("commentCount")),
        "channel": snippet.get("channelTitle") or channel_titles.get(snippet.get("channelId")),
        "published_at": (snippet.get("publishedAt") or "")[:10] or None,
    }


def import_toolkit_snapshots():
    """Copy each songaday-toolkit YouTube audit into cache/views/youtube/ in the slim shape."""
    pattern = str(TOOLKIT_DIR / "output" / "youtube-description-audit-*" / "youtube-api-cache.json")
    for path in sorted(glob.glob(pattern)):
        audit_date = re.search(r"audit-(\d{4}-\d{2}-\d{2})", path).group(1)
        target = YOUTUBE_CACHE / f"toolkit-{audit_date}.json"
        if target.exists() and target.stat().st_mtime >= os.path.getmtime(path):
            continue
        print(f"Importing the toolkit's YouTube snapshot from {audit_date} ...")
        raw = json.loads(Path(path).read_text())
        channel_titles = {
            channel_id: (entry.get("result") or {}).get("snippet", {}).get("title")
            for channel_id, entry in raw.get("channels", {}).items()
        }
        videos = {}
        for video_id, entry in raw["videos"].items():
            videos[video_id] = slim_video(entry["fetchedAt"], entry.get("result"), channel_titles)
        write_json(target, {"source": SOURCE_TOOLKIT, "imported_from": "songaday-toolkit " + Path(path).parent.name, "videos": videos})


def fetch_youtube_api(video_ids, refresh, offline):
    """Fetch current statistics for every catalog video, if a YOUTUBE_API_KEY is set."""
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("No YOUTUBE_API_KEY in .env or the environment: using the saved snapshots only.")
        return
    existing = sorted(YOUTUBE_CACHE.glob("api-*.json"))
    if offline or (existing and not refresh):
        return
    today = dt.date.today().isoformat()
    batch_dir = YOUTUBE_CACHE / f"api-{today}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    ids = sorted(set(video_ids))
    batches = [ids[i : i + YOUTUBE_BATCH] for i in range(0, len(ids), YOUTUBE_BATCH)]
    print(f"Fetching YouTube statistics for {len(ids)} videos in {len(batches)} calls ...")
    for number, batch in enumerate(batches, start=1):
        path = batch_dir / f"batch-{number:04d}.json"
        if path.exists():
            continue
        params = {"part": "snippet,statistics", "id": ",".join(batch), "key": key, "maxResults": 50}
        try:
            data = get_json(YOUTUBE_API_URL, params)
        except RuntimeError as error:
            print(f"  stopped at call {number}: {error}")
            break
        write_json(path, {"fetched_at": dt.datetime.now(dt.UTC).isoformat(), "requested": batch, "items": data.get("items", [])})
        time.sleep(REQUEST_PAUSE)
    # Collapse the raw batches into one slim snapshot.
    videos = {}
    for path in sorted(batch_dir.glob("batch-*.json")):
        batch = json.loads(path.read_text())
        returned = {item["id"]: item for item in batch["items"]}
        for video_id in batch["requested"]:
            videos[video_id] = slim_video(batch["fetched_at"], returned.get(video_id), {})
    write_json(YOUTUBE_CACHE / f"api-{today}.json", {"source": SOURCE_API, "videos": videos})


def load_youtube_snapshots():
    """Merge all slim snapshots. Per video: the newest count, and the newest status."""
    entries = []
    for path in YOUTUBE_CACHE.glob("*.json"):
        snapshot = json.loads(path.read_text())
        for video_id, video in snapshot["videos"].items():
            entries.append((video["fetched_at"], video_id, video, snapshot["source"]))
    entries.sort(key=lambda entry: entry[0])
    counts, status = {}, {}
    for fetched_at, video_id, video, source in entries:
        status[video_id] = video["status"]
        if video["status"] == "returned" and video.get("views") is not None:
            counts[video_id] = dict(video, source=source)
    return counts, status


# ---------------------------------------------------------------------------
# 3. The spreadsheet's old views column (fallback for videos YouTube no longer returns)
# ---------------------------------------------------------------------------


def load_sheet_views():
    """Return ({song number: (youtube id, views)}, export date) from the songaday.fan app."""
    songs_path = FAN_APP_DIR / "src" / "data" / "songs.json"
    manifest_path = FAN_APP_DIR / "src" / "data" / "source-manifest.json"
    if songs_path.exists() and manifest_path.exists():
        exported = json.loads(manifest_path.read_text())["generatedAt"][:10]
        target = CACHE_DIR / f"sheet-views-{exported}.json"
        if not target.exists():
            print(f"Importing the sheet's views column (exported {exported}) ...")
            views = {
                str(song["id"]): [song.get("youtubeId"), song.get("views")]
                for song in json.loads(songs_path.read_text())
            }
            write_json(target, {"exported": exported, "songs": views})
    cached = sorted(CACHE_DIR.glob("sheet-views-*.json"))
    if not cached:
        return {}, None
    data = json.loads(cached[-1].read_text())
    return {int(n): tuple(value) for n, value in data["songs"].items()}, data["exported"]


# ---------------------------------------------------------------------------
# 4. songaday.fan listener ratings
# ---------------------------------------------------------------------------


def fetch_fan_ratings(last_number, refresh, offline):
    """Return ({song number: aggregate}, as-of date) from songaday.fan's public ratings API.

    Song numbers are asked for in fixed blocks of 100 (1-100, 101-200, ...), one file each.
    The newest dated folder is reused, and any blocks it is missing are filled in.
    """
    folders = sorted(path for path in FAN_CACHE.glob("*") if path.is_dir())
    if refresh or not folders:
        folder = FAN_CACHE / dt.date.today().isoformat()
    else:
        folder = folders[-1]
    blocks = [(start, min(start + FAN_BATCH - 1, last_number)) for start in range(1, last_number + 1, FAN_BATCH)]
    missing = [block for block in blocks if not (folder / f"songs-{block[0]:05d}-{block[1]:05d}.json").exists()]
    if missing and not offline:
        folder.mkdir(parents=True, exist_ok=True)
        print(f"Fetching songaday.fan ratings: {len(missing)} calls ...")
        for start, end in missing:
            data = get_json(FAN_RATINGS_URL, {"songIds": ",".join(str(n) for n in range(start, end + 1))})
            if not data.get("persisted"):
                # The site answered without its database; zeros here would be fake.
                print(f"  songs {start}-{end}: site returned no stored ratings, skipping")
                continue
            data["fetched_at"] = dt.datetime.now(dt.UTC).isoformat()
            write_json(folder / f"songs-{start:05d}-{end:05d}.json", data)
            time.sleep(REQUEST_PAUSE)
    ratings = {}
    for path in folder.glob("songs-*.json") if folder.exists() else []:
        for aggregate in json.loads(path.read_text())["aggregates"]:
            ratings[aggregate["songId"]] = aggregate
    return ratings, folder.name if ratings else None


# ---------------------------------------------------------------------------
# 5. Put it together
# ---------------------------------------------------------------------------


def build_rows(catalog, counts, status, sheet_views, sheet_date, ratings, fan_as_of):
    # Videos that more than one song points to.
    users = {}
    for number, video_id in catalog.items():
        if video_id:
            users.setdefault(video_id, []).append(number)

    rows = []
    for number, video_id in catalog.items():
        row = {"number": number, "youtube_id": video_id or ""}
        notes = []

        if not video_id:
            row["video_status"] = "no_video"
        else:
            row["video_status"] = {"returned": "available", "unavailable": "unavailable"}.get(
                status.get(video_id), "not_checked"
            )
            shared = [n for n in users[video_id] if n != number]
            if shared:
                notes.append("same video as song " + ", ".join(str(n) for n in shared))

        count = counts.get(video_id) if video_id else None
        sheet = sheet_views.get(number)
        if count:
            row.update(
                views=count["views"],
                likes=count["likes"],
                comments=count["comments"],
                views_as_of=count["fetched_at"][:10],
                source=count["source"],
                youtube_channel=count.get("channel") or "",
                published_at=count.get("published_at") or "",
            )
        elif sheet and sheet[0] == video_id and sheet[1]:
            # Only trust the sheet's number if it was for this same video, and it isn't a
            # blank-meaning zero.
            row.update(views=sheet[1], views_as_of=sheet_date, source=SOURCE_SHEET)
            notes.append(f"views counted on or before {sheet_date}")

        rating = ratings.get(number)
        if rating:
            row.update(
                fan_good=rating["good"],
                fan_okay=rating["okay"],
                fan_bad=rating["bad"],
                fan_votes=rating["total"],
                fan_score=rating["average"] if rating["total"] else "",
                fan_as_of=fan_as_of,
            )
        row["note"] = "; ".join(notes)
        rows.append(row)
    return rows


def write_csv(rows):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: "" if row.get(column) is None else row.get(column, "") for column in COLUMNS})


def report(rows, counts, sheet_views):
    total = len(rows)
    with_views = [row for row in rows if row.get("views") is not None]
    print(f"\nWrote {OUT_CSV.relative_to(ROOT)}: {total} songs")
    print(f"  with a YouTube id      {sum(1 for row in rows if row['youtube_id'])}")
    print(f"  with views             {len(with_views)} ({len(with_views) / total:.1%})")
    for source in (SOURCE_API, SOURCE_TOOLKIT, SOURCE_SHEET):
        rows_from = [row for row in with_views if row["source"] == source]
        if rows_from:
            dates = sorted({row["views_as_of"] for row in rows_from})
            print(f"    from {source:24s} {len(rows_from):5d}  as of {', '.join(dates)}")
    print(f"  with likes             {sum(1 for row in rows if row.get('likes') is not None)}")
    print(f"  with comment counts    {sum(1 for row in rows if row.get('comments') is not None)}")
    for status in ("available", "unavailable", "not_checked", "no_video"):
        print(f"  video_status={status:12s} {sum(1 for row in rows if row['video_status'] == status)}")
    print(f"  total views            {sum(row['views'] for row in with_views):,}")
    views = sorted(row["views"] for row in with_views)
    print(f"  median views           {statistics.median(views):,.0f}")

    rated = [row for row in rows if row.get("fan_votes")]
    print(f"  fan ratings fetched    {sum(1 for row in rows if row.get('fan_votes') is not None)}")
    print(f"  with at least one vote {len(rated)}, {sum(row['fan_votes'] for row in rated):,} votes in all")

    # How stale is the sheet's views column? Compare it with the API for the same videos.
    ratios = []
    for row in rows:
        sheet = sheet_views.get(row["number"])
        count = counts.get(row["youtube_id"])
        if sheet and count and sheet[0] == row["youtube_id"] and sheet[1] and sheet[1] >= 100:
            ratios.append(count["views"] / sheet[1])
    if ratios:
        print(f"  sheet column vs API    median {statistics.median(ratios):.3f}x over {len(ratios)} videos")

    print("\nTop 20 by views:")
    for rank, row in enumerate(sorted(with_views, key=lambda row: -row["views"])[:20], start=1):
        extra = "" if row["source"] != SOURCE_SHEET else f"  [{row['video_status']}, {row['source']}]"
        print(f"  {rank:2d}. #{row['number']:<5d} {row['views']:>10,}  {row['youtube_id']}{extra}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="use cached data only")
    parser.add_argument("--refresh-fan", action="store_true", help="take a new songaday.fan ratings snapshot")
    parser.add_argument("--refresh-youtube", action="store_true", help="take a new YouTube API snapshot")
    args = parser.parse_args()

    load_dotenv()
    catalog = load_catalog()
    print(f"Catalog: {len(catalog)} songs, #{min(catalog)} to #{max(catalog)}")

    import_toolkit_snapshots()
    fetch_youtube_api([v for v in catalog.values() if v], args.refresh_youtube, args.offline)
    counts, status = load_youtube_snapshots()
    sheet_views, sheet_date = load_sheet_views()
    ratings, fan_as_of = fetch_fan_ratings(max(catalog), args.refresh_fan, args.offline)

    rows = build_rows(catalog, counts, status, sheet_views, sheet_date, ratings, fan_as_of)
    write_csv(rows)
    report(rows, counts, sheet_views)


if __name__ == "__main__":
    main()
