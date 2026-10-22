"""Skeptic's spot-check of dataset/links.csv against the live Bandcamp and Apple Music data.

The question: when links.csv says song #N's Bandcamp or Apple Music link is a given track,
is that track really the song from #N's day? This script answers it for a sample of songs
by opening each linked Bandcamp track page and Apple's lookup API for each linked track,
then comparing what they say now with the catalog's title and date for that day.

The sample (picked by pick_sample below):
  - 40 "spread" songs: leap days (Feb 29 2012/2016/2020/2024), Jan 1 and Dec 31 of several
    years, the first and last days of Apple's seasonal albums (Mar 31/Apr 1, Jun 30/Jul 1,
    Sep 30/Oct 1, the gaps around the missing Spring 2014 and Summer 2015 albums, and the
    switch to monthly albums in October 2017), then seeded-random days so every year from
    2009 to 2026 has at least one song.
  - every song that links.csv rates "check" on any service (there are exactly 40).
  - "follow-ups": high-rated links that the whole-table checks below point at (a title
    that fits a neighbour, an album outside the date, links.py's "mislabelled" flag, a
    file whose length is another day's). Opened live, but kept out of the error rates.
  - for spread songs with no Apple link, one Apple Search API query for the title, to
    test the claim that the song isn't on Apple Music.

For each sampled link it records, from the live page:
  - the track title, album and track number (Bandcamp page data, Apple lookup);
  - the audio length;
  - Bandcamp's upload date for the track (publish_date), an independent date signal;
and judges:
  - title: is it the catalog's title for #N (allowing case, punctuation, "(feat. ...)" and
    Apple's censored words), and is no neighbouring song (#N-3..#N+3) a better fit?
  - album/date: does Apple's album period ("Winter, 2009" = Jan-Mar, "May, 2020" = May)
    contain #N's date, and is Bandcamp's year album ("Year Four" = 2012) #N's year?
  - audio: does the live length match the catalog's video Length or the other service's
    file, or is it another day's song's file (see audio_judgement)? Lengths only: no audio
    is downloaded.

The title matching here is written from scratch on purpose (difflib, not the helpers in
sources/), so it is a second opinion rather than the same code checking itself.
Anything the automatic rules can't settle gets a hand verdict in MANUAL, with the reason.

It also runs whole-table checks that need no web requests:
  - every stored service title against the catalog titles of #N-3..#N+3 (off-by-one runs);
  - every link whose album period or year album doesn't contain the song's date;
  - every stored file length (audio_judgement): one file under two titles, and files that
    look like a song 1-3 days away, alone or in runs;
  - the links accepted on a weak title: is their length evidence discriminating?
  - track URLs used for more than one song;
  - analysis/sheet-backfill-links.csv against the cached public sheet, row by row, and
    against links.csv (high links only, nothing else).

Web: GET only, one request at a time, a descriptive User-Agent, a pause between requests
and backoff on 403/429/5xx. Raw responses are cached in cache/links-verify/ so a rerun
makes no requests. No logins, no keys.

Run from the repo root:
  .venv/bin/python analysis/checks/links_check.py            # fetch what isn't cached
  .venv/bin/python analysis/checks/links_check.py --offline  # cache only

Writes analysis/links-verify.md and prints a short summary.
"""

import argparse
import csv
import datetime as dt
import difflib
import glob
import html
import json
import os
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import requests
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
LINKS_CSV = ROOT / "dataset" / "links.csv"
BACKFILL_CSV = ROOT / "analysis" / "sheet-backfill-links.csv"
SHEET_CSV = ROOT / "cache" / "sheet" / "sheet-gid0.csv"
REPORT = ROOT / "analysis" / "links-verify.md"
CACHE = ROOT / "cache" / "links-verify"
CATALOG_DIR = Path(os.environ.get(
    "SONGADAY_CATALOG_DIR",
    Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta"))

USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
BANDCAMP_PAUSE = 1.5   # seconds between Bandcamp page requests
APPLE_PAUSE = 3.2      # Apple's lookup API allows about 20 requests a minute

FIRST_DAY = dt.date(2009, 1, 1)  # song #1
SEED = 20261021                  # the random fill days are the same on every run

TITLE_SAME = 0.85      # similarity at or above this: the same title
TITLE_NEAR = 0.60      # between NEAR and SAME: "partial", needs a look
NEIGHBOUR_GAIN = 0.05  # a neighbour must beat the song's own title by this much
NEIGHBOURS = 3         # look this many songs either side
LENGTH_NEAR = (3.0, 0.03)   # within 3 s or 3% of the catalog's whole-second video Length
LENGTH_SHIFT = 1.5          # within this of a neighbour's Length: "looks like #N+k"
LENGTH_FAR = (10.0, 0.10)   # ...but only when it is this far from its own song (10 s and 10%)

SEASONS = {"Winter": 1, "Spring": 4, "Summer": 7, "Fall": 10}  # first month of each
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
YEAR_WORDS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
              "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
              "Seventeen", "Eighteen", "Nineteen", "Twenty"]

# Hand verdicts for links the rules leave "unclear" (or get wrong), filled in after reading
# the live pages. Key: (song number, "bandcamp" | "apple"). Value: (verdict, reason).
# verdict: "right" (the track is this day's song), "wrong" (it is another song).
MANUAL = {
    (3495, "apple"): (
        "right", "'Powerful Sea' is the end of the catalog title; it is track 27 of "
                 "'July, 2018' (the 27th) and the file is 172.1 s, the same as Bandcamp's "
                 "'Yo Ho Ho Powerful Sea'"),
    (4154, "apple"): (
        "right", "the single 'The Wind of God' is the only Apple track for the catalog's "
                 "only 'Wind of God' song (this one, a 'Wind of God chill remix'); 107.3 s "
                 "against Bandcamp's 104.0 s"),
    (4571, "apple"): (
        "right", "probably: the single 'The American Woodcock Dance' and this day's "
                 "'Woodcock Luring Worms' are the catalog's only woodcock song; 113.5 s "
                 "against Bandcamp's 109.6 s, a few seconds longer as Apple's singles often are"),
    (4705, "apple"): (
        "right", "track 18 of 'November, 2021' (the 18th), and the title is the catalog's "
                 "with 'My Ape' added; the file is 7 s longer than Bandcamp's (114.5 s vs 107.4 s)"),
    (5830, "apple"): (
        "right", "track 17 of 'December, 2024' (the 17th); 'Pudgy Pengu Two' for "
                 "'Pudgy Pengu Remix', 153.6 s against Bandcamp's 151.7 s"),
    (5858, "apple"): (
        "right", "track 14 of 'January, 2025' (the 14th); Apple writes TikTok as 'TT' here and "
                 "on #5863 ('TT's Gone, BiliBili'); 113.2 s against Bandcamp's 115.3 s"),
}


# ----------------------------------------------------------------------------- basics

def song_date(number):
    return FIRST_DAY + dt.timedelta(days=number - 1)


def song_number(day):
    return (day - FIRST_DAY).days + 1


def length_seconds(text):
    """'2:36' -> 156; None if missing or unreadable."""
    if not text:
        return None
    try:
        seconds = 0
        for part in str(text).strip().split(":"):
            seconds = seconds * 60 + int(part)
        return seconds
    except ValueError:
        return None


def load_catalog():
    """{number: {title, date, seconds}} from the songaday-display index chunks.

    Some chunks exist in two hashed copies. Like sources/links.py, the newest file wins;
    copies that disagree on a title are counted so the report can say so.
    """
    files = sorted(glob.glob(str(CATALOG_DIR / "index-*.json")), key=os.path.getmtime)
    if not files:
        sys.exit(f"no catalog chunks in {CATALOG_DIR}")
    songs, seen_titles = {}, defaultdict(set)
    for path in files:
        for song in json.loads(Path(path).read_text())["songs"]:
            songs[song["n"]] = {
                "title": song.get("t") or "",
                "date": song.get("d") or "",
                "seconds": length_seconds((song.get("a") or {}).get("Length")),
            }
            seen_titles[song["n"]].add(song.get("t") or "")
    disagree = sorted(n for n, titles in seen_titles.items() if len(titles) > 1)
    return songs, disagree


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ----------------------------------------------------------------------------- titles

def title_forms(title):
    """Normalised versions of a title to compare: the whole thing, and without
    bracketed parts or a trailing "feat. ..." (catalog titles often carry those)."""
    text = unicodedata.normalize("NFKC", title or "").lower()
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("&", " and ")
    variants = {text,
                re.sub(r"[\(\[].*?[\)\]]", " ", text),
                re.sub(r"\s(feat\.?|ft\.?|featuring)\s.*$", " ", text)}
    forms = set()
    for v in variants:
        v = v.replace("'", "")                # don't -> dont
        v = re.sub(r"[^\w\s*]", " ", v)       # punctuation to spaces, keep letters and *
        v = re.sub(r"\s+", " ", v).strip()
        if v:
            forms.add(v)
    if not forms and title:                   # emoji-only titles: compare them raw
        forms.add(title.strip())
    return forms


def censored_match(service_form, catalog_form):
    """Apple writes 'With No B******t' for 'With No Bullshit': each * is one letter."""
    if "*" not in service_form:
        return False
    pattern = "".join(r"\w" if ch == "*" else re.escape(ch) for ch in service_form)
    return re.fullmatch(pattern, catalog_form) is not None


def similarity(a, b):
    """0..1: the best difflib ratio between any normalised forms of the two titles."""
    best = 0.0
    for x in title_forms(a):
        for y in title_forms(b):
            if x == y or censored_match(x, y) or censored_match(y, x):
                return 1.0
            best = max(best, difflib.SequenceMatcher(None, x, y).ratio())
    return best


def title_judgement(service_title, number, catalog):
    """How a service's title fits song #N, and whether a neighbour fits better.

    Returns (own similarity, best neighbour number or None, its similarity, kind) where
    kind is "same", "partial", "different" or "neighbour" (a nearby song fits clearly
    better, which is what an off-by-one link looks like).
    """
    own = similarity(service_title, catalog[number]["title"])
    best_n, best_sim = None, 0.0
    for k in range(-NEIGHBOURS, NEIGHBOURS + 1):
        other = number + k
        if k == 0 or other not in catalog:
            continue
        sim = similarity(service_title, catalog[other]["title"])
        if sim > best_sim:
            best_n, best_sim = other, sim
    if best_sim >= TITLE_SAME and best_sim > own + NEIGHBOUR_GAIN:
        kind = "neighbour"
    elif own >= TITLE_SAME:
        kind = "same"
    elif own >= TITLE_NEAR:
        kind = "partial"
    else:
        kind = "different"
    return own, best_n, best_sim, kind


# ----------------------------------------------------------------------------- albums

PERIOD_RE = re.compile(r"^(Winter|Spring|Summer|Fall|" + "|".join(MONTHS) + r"),?\s+(\d{4})$")
YEAR_ALBUM_RE = re.compile(r"^Song A Day: Year (\w+)$")


def apple_period(album):
    """(first day, last day) of a dated Apple album such as 'Winter, 2009' or
    'October 2024'; None for singles, EPs and compilations."""
    match = PERIOD_RE.match((album or "").strip())
    if not match:
        return None
    label, year = match.group(1), int(match.group(2))
    first_month, months = (SEASONS[label], 3) if label in SEASONS else (MONTHS.index(label) + 1, 1)
    first = dt.date(year, first_month, 1)
    after = first_month + months
    last = dt.date(year + (after - 1) // 12, (after - 1) % 12 + 1, 1) - dt.timedelta(days=1)
    return first, last


def bandcamp_year(album):
    """2012 for 'Song A Day: Year Four'; None for anything else."""
    match = YEAR_ALBUM_RE.match((album or "").strip())
    if not match or match.group(1) not in YEAR_WORDS:
        return None
    return 2009 + YEAR_WORDS.index(match.group(1))


def date_fit(service, album, number):
    """('ok' | 'outside' | 'undated', note) for whether the album fits #N's date."""
    day = song_date(number)
    if service == "bandcamp":
        year = bandcamp_year(album)
        if year is None:
            return "undated", f"'{album}' is not a year album"
        if year == day.year:
            return "ok", ""
        return "outside", f"'{album}' is {year}, the song is {day.year}"
    period = apple_period(album)
    if period is None:
        return "undated", f"'{album}' is not a dated album"
    first, last = period
    if first <= day <= last:
        return "ok", ""
    gap = (first - day).days if day < first else (day - last).days
    side = "before" if day < first else "after"
    return "outside", f"'{album}' runs {first}..{last}; the song is {gap} day(s) {side} it"


# ----------------------------------------------------------------------------- web

SESSION = requests.Session()
SESSION.headers["User-Agent"] = USER_AGENT
_last_request = {"bandcamp": 0.0, "apple": 0.0}


def polite_get(kind, url, pause):
    """One GET, spaced at least `pause` seconds after the last one of this kind, with
    backoff on 403/429/5xx. Returns the response (any status) or None after 6 tries."""
    for attempt in range(6):
        wait = pause - (time.time() - _last_request[kind])
        if wait > 0:
            time.sleep(wait)
        _last_request[kind] = time.time()
        try:
            response = SESSION.get(url, timeout=30)
        except requests.RequestException as error:
            print(f"  {url}: {error}; retrying", file=sys.stderr)
            time.sleep(5 * 2 ** attempt)
            continue
        if response.status_code in (403, 429) or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After", "")
            backoff = int(retry_after) if retry_after.isdigit() else min(300, 10 * 2 ** attempt)
            print(f"  {url}: HTTP {response.status_code}; waiting {backoff} s", file=sys.stderr)
            time.sleep(backoff)
            continue
        return response
    return None


def bandcamp_page(url, offline):
    """The live track page as (meta dict, html text or ''), cached in cache/links-verify/."""
    slug = re.sub(r"[^\w-]", "_", url.rstrip("/").rsplit("/", 1)[-1])
    page_path = CACHE / "bandcamp" / f"{slug}.html"
    meta_path = CACHE / "bandcamp" / f"{slug}.meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return meta, page_path.read_text(encoding="utf-8") if page_path.exists() else ""
    if offline:
        return {"status": None, "url": url}, ""
    response = polite_get("bandcamp", url, BANDCAMP_PAUSE)
    if response is None:
        return {"status": None, "url": url}, ""
    meta = {"status": response.status_code, "url": url, "final_url": response.url,
            "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    page_path.parent.mkdir(parents=True, exist_ok=True)
    if response.status_code == 200:
        page_path.write_text(response.text, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=1))
    return meta, response.text if response.status_code == 200 else ""


def parse_bandcamp(page):
    """Title, album, track number, length, upload date and has-audio from a track page."""
    out = {}
    match = re.search(r'data-tralbum="([^"]*)"', page)
    if match:
        data = json.loads(html.unescape(match.group(1)))
        current = data.get("current") or {}
        info = (data.get("trackinfo") or [{}])[0]
        out["title"] = current.get("title") or info.get("title") or ""
        out["track_number"] = current.get("track_number") or info.get("track_num")
        out["seconds"] = info.get("duration")
        out["has_audio"] = bool(info.get("file"))
        published = current.get("publish_date") or current.get("new_date")
        if published:
            out["published"] = dt.datetime.strptime(published, "%d %b %Y %H:%M:%S %Z").date()
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    if match:
        ld = json.loads(match.group(1))
        out["album"] = (ld.get("inAlbum") or {}).get("name", "")
        out.setdefault("title", ld.get("name", ""))
    return out


def apple_lookup(track_id, offline):
    """Apple's lookup result for one track id (US store), cached; None if not found."""
    path = CACHE / "apple" / f"{track_id}.json"
    if path.exists():
        data = json.loads(path.read_text())
    elif offline:
        return {"_status": None}
    else:
        response = polite_get("apple", f"https://itunes.apple.com/lookup?id={track_id}", APPLE_PAUSE)
        if response is None or response.status_code != 200:
            return {"_status": None if response is None else response.status_code}
        data = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1))
    tracks = [r for r in data.get("results", []) if r.get("wrapperType") == "track"]
    if not tracks:
        return {"_status": "no result"}
    return tracks[0]


APPLE_ARTIST_ID = 188742143  # Jonathan Mann on Apple Music


def apple_search(number, title, offline, catalog):
    """Search Apple's US store for a song title; return Jonathan Mann tracks that fit it.

    Used only for sampled songs that links.csv has no Apple link for, to test the claim
    that the song isn't on Apple Music. Returns (status, [(track name, album, id, sim)]).
    """
    path = CACHE / "apple-search" / f"{number}-jonathan-mann.json"
    if path.exists():
        data = json.loads(path.read_text())
    elif offline:
        return "not fetched", []
    else:
        url = ("https://itunes.apple.com/search?" +
               requests.compat.urlencode({"term": f"jonathan mann {title}", "entity": "song",
                                          "limit": 200, "country": "us"}))
        response = polite_get("apple", url, APPLE_PAUSE)
        if response is None or response.status_code != 200:
            return f"HTTP {None if response is None else response.status_code}", []
        data = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1))
    hits = []
    for r in data.get("results", []):
        if r.get("artistId") != APPLE_ARTIST_ID:
            continue
        sim = similarity(r.get("trackName", ""), title)
        if sim >= TITLE_NEAR:
            hits.append((r.get("trackName"), r.get("collectionName"), r.get("trackId"), sim))
    return f"{data.get('resultCount', 0)} results", hits


# ----------------------------------------------------------------------------- sample

BOUNDARY_DAYS = [
    ("2012-02-29", "leap day"), ("2016-02-29", "leap day"),
    ("2020-02-29", "leap day"), ("2024-02-29", "leap day"),
    ("2009-01-01", "Jan 1, song #1"), ("2010-01-01", "Jan 1"), ("2014-01-01", "Jan 1"),
    ("2018-01-01", "Jan 1"), ("2021-01-01", "Jan 1"), ("2026-01-01", "Jan 1"),
    ("2009-12-31", "Dec 31"), ("2013-12-31", "Dec 31"), ("2017-12-31", "Dec 31"),
    ("2020-12-31", "Dec 31"), ("2022-12-31", "Dec 31, last row of the public sheet"),
    ("2025-12-31", "Dec 31"),
    ("2009-09-30", "last day of Summer 2009"), ("2009-10-01", "first day of Fall 2009"),
    ("2010-06-30", "last day of Spring 2010"), ("2010-07-01", "first day of Summer 2010"),
    ("2011-03-31", "last day of Winter 2011"), ("2011-04-01", "first day of Spring 2011"),
    ("2014-03-31", "last day of Winter 2014 (no Spring 2014 album follows)"),
    ("2014-07-01", "first day of Summer 2014"),
    ("2015-06-30", "last day of Spring 2015 (no Summer 2015 album follows)"),
    ("2015-10-01", "first day of Fall 2015"),
    ("2017-06-30", "last day of Spring 2017"),
    ("2017-09-30", "last day of Summer 2017, the last seasonal album"),
    ("2017-10-01", "first monthly album (October, 2017)"),
]
SPREAD_SIZE = 40


def pick_sample(links_by_n, last_number, follow_ups):
    """[(number, group, why)] for the spread songs, every 'check' row, then follow-ups."""
    picks = {}
    for day, why in BOUNDARY_DAYS:
        picks[song_number(dt.date.fromisoformat(day))] = why
    # Fill to SPREAD_SIZE with seeded-random days, always in the year with fewest picks.
    rng = random.Random(SEED)
    years = range(2009, song_date(last_number).year + 1)
    while len(picks) < SPREAD_SIZE:
        count = Counter(song_date(n).year for n in picks)
        year = min(years, key=lambda y: (count[y], y))
        first = song_number(dt.date(year, 1, 1))
        last = min(song_number(dt.date(year, 12, 31)), last_number)
        n = rng.randint(first, last)
        if n not in picks:
            picks[n] = f"random day in {year}"
    sample = [(n, "spread", why) for n, why in sorted(picks.items())]
    checks = [int(r["number"]) for r in links_by_n.values()
              if "check" in (r["bandcamp_confidence"], r["apple_music_confidence"])]
    for n in sorted(checks)[:40]:
        flags = links_by_n[n]["flags"]
        if n in picks:     # already in the spread sample: say so, don't fetch twice
            continue
        sample.append((n, "check", flags))
    # Follow-ups: high-rated links that the whole-table scans (or links.py's own
    # "mislabelled" flag) say carry another song's title or sit outside their album's
    # period. Not part of either error rate; opened to see what the live page says.
    taken = {n for n, _, _ in sample}
    for n, why in sorted(follow_ups.items()):
        if n not in taken:
            sample.append((n, "follow-up", why))
    return sample


# ----------------------------------------------------------------------------- judging

def near_length(a, b):
    return a is not None and b is not None and abs(a - b) <= max(LENGTH_NEAR[0], LENGTH_NEAR[1] * b)


SAME_FILE = 0.05   # two tracks this close in length (seconds) are taken to be one file


def file_owner(seconds, n, m, service, catalog, lengths):
    """Songs #N and #M have one file of this length on `service`: whose song is it?

    First by the other service (it usually carries the same master): the song whose
    other-service file is this length, if only one is. Then by the catalog's video
    Length, if only one fits. None when neither settles it."""
    other = "apple" if service == "bandcamp" else "bandcamp"
    on = [x for x in (n, m)
          if lengths[other].get(x) is not None and abs(lengths[other][x] - seconds) <= 0.5]
    if len(on) == 1:
        return on[0]
    fits = [x for x in (n, m) if near_length(seconds, catalog[x]["seconds"])]
    if len(fits) == 1:
        return fits[0]
    return None


def audio_judgement(seconds, number, service, catalog, lengths, labels=None):
    """How a file's length fits song #N. Returns (label, the other song's number or None).

    'same file as #M'  this service has a file of the same length (within 0.05 s) on a
                       song 1-3 days away whose catalog Length differs by more than 5 s,
                       and the file is #M's (see file_owner), or nobody can tell whose
                       ('same file as #M, whose is unclear')
    'agrees'           within 3 s / 3% of the catalog's video Length
    'agrees with X'    within 3 s / 3% of the other service's file, not the video's
    'looks like #M'    more than 10 s and 10% from its own song (video and other service)
                       but within 1.5 s of song #M's video Length or other-service file
                       (1-3 days away), or,
                       next to a run of such files, within 1.5 s of the song the run's
                       shift points to ('in a run')
    'differs'          none of those (another take, an edit, padding, or a wrong file)
    """
    if seconds is None:
        return "no length", None
    other = "apple" if service == "bandcamp" else "bandcamp"
    video = catalog[number]["seconds"]
    theirs = lengths[other].get(number)
    # One file under two titles is checked first: the other service may carry it too.
    for k in (-1, 1, -2, 2, -3, 3):
        m = number + k
        twin = lengths[service].get(m)
        if (twin is None or abs(seconds - twin) > SAME_FILE or m not in catalog
                or video is None or catalog[m]["seconds"] is None
                or abs(video - catalog[m]["seconds"]) <= 5):
            continue
        owner = file_owner(seconds, number, m, service, catalog, lengths)
        if owner == m:
            return f"same file as #{m}", m
        if owner is None:
            return f"same file as #{m}, whose is unclear", m
    if near_length(seconds, video):
        return "agrees", None
    if near_length(seconds, theirs):
        return f"agrees with {other}, not the video", None
    # A file far from its own song but within 1.5 s of a neighbour's probably plays that
    # neighbour. "Far" keeps a few seconds of padding from looking like a neighbour.
    own = [x for x in (video, theirs) if x is not None]
    if all(far_length(seconds, x) for x in own):
        for k in (-1, 1, -2, 2, -3, 3):
            m = number + k
            if m in catalog and near_neighbour(seconds, m, other, catalog, lengths):
                return f"looks like #{m}", m
    # Inside a run of shifted files (labels from scan_audio), a smaller gap is enough.
    if labels:
        for side in (-1, 1):
            label, target = labels.get((service, number + side), ("", None))
            if target is None or not label.startswith(("looks like", "same file")):
                continue
            k = target - (number + side)
            m = number + k
            if m in catalog and near_neighbour(seconds, m, other, catalog, lengths):
                return f"looks like #{m} (in a run)", m
    return "differs", None


def near_neighbour(seconds, m, other, catalog, lengths):
    """Within LENGTH_SHIFT of song #M's video Length or of its file on the other service."""
    refs = [catalog[m]["seconds"], lengths[other].get(m)]
    return any(r is not None and abs(seconds - r) <= LENGTH_SHIFT for r in refs)


def far_length(a, b):
    return abs(a - b) > LENGTH_FAR[0] and abs(a - b) > LENGTH_FAR[1] * b


def scan_audio(links, catalog, lengths):
    """The audio label of every stored link, in two passes so that a file inside a run
    of shifted files can be read in the light of its neighbours."""
    labels = {}
    for _ in range(2):
        new = {}
        for row in links:
            n = int(row["number"])
            for service in SERVICE_COLUMNS:
                link = stored_link(row, service)
                if link["url"]:
                    new[(service, n)] = audio_judgement(link["seconds"], n, service, catalog,
                                                        lengths, labels)
        labels = new
    return labels


_FORM_INDEX = {}


def title_owners(title, catalog):
    """Song numbers whose catalog title has a normalised form in common with this title."""
    if not _FORM_INDEX:
        for n, song in catalog.items():
            for form in title_forms(song["title"]):
                _FORM_INDEX.setdefault(form, set()).add(n)
    owners = set()
    for form in title_forms(title):
        owners |= _FORM_INDEX.get(form, set())
    return sorted(owners)


def judge_link(service, number, live, stored, catalog, lengths, labels):
    """One sampled link: everything the report shows about it, plus the verdict."""
    row = {"service": service, "number": number}
    row["live_title"] = live.get("title", "")
    row["album"] = live.get("album", "")
    row["track_number"] = live.get("track_number")
    row["seconds"] = live.get("seconds")
    row["stored_title"] = stored["title"]
    row["stored_album"] = stored["album"]
    row["confidence"] = stored["confidence"]
    row["stale"] = []
    if row["live_title"] != stored["title"]:
        row["stale"].append(f"title now '{row['live_title']}', stored '{stored['title']}'")
    if row["album"] != stored["album"]:
        row["stale"].append(f"album now '{row['album']}', stored '{stored['album']}'")
    own, nb, nb_sim, kind = title_judgement(row["live_title"], number, catalog)
    row.update(title_sim=own, neighbour=nb, neighbour_sim=nb_sim, title_kind=kind)
    row["date_fit"], row["date_note"] = date_fit(service, row["album"], number)
    row["audio"], row["audio_points_to"] = audio_judgement(row["seconds"], number, service,
                                                           catalog, lengths, labels)
    if row["seconds"] is not None and stored["seconds"] is not None \
            and abs(row["seconds"] - stored["seconds"]) > 1.0:
        row["stale"].append(f"length now {row['seconds']:.1f} s, stored {stored['seconds']:.1f} s")
    if service == "bandcamp" and live.get("published"):
        row["upload_lag"] = (live["published"] - song_date(number)).days
    else:
        row["upload_lag"] = None
    row["has_audio"] = live.get("has_audio", True)

    # A title that belongs to another song, on a file whose length is this day's song and
    # not that other song's, is a mislabelled upload: the link plays the right song.
    owners = [] if kind == "same" else [m for m in title_owners(row["live_title"], catalog)
                                       if m != number]
    owners_far = owners and all(not near_length(row["seconds"], catalog[m]["seconds"])
                                for m in owners)

    # The verdict is about which song the track is: by its own label, is it #N's song?
    if (number, service) in MANUAL:
        row["verdict"], row["why"] = MANUAL[(number, service)]
        row["verdict_by"] = "hand"
    elif kind == "same":
        row["verdict"], row["why"], row["verdict_by"] = "right", "title is the catalog's", "rule"
    elif owners and row["audio"].startswith("agrees") and owners_far:
        row["verdict"], row["verdict_by"] = "mislabelled", "rule"
        row["why"] = (f"title is {', '.join(f'#{m}' for m in owners)}'s "
                      f"('{catalog[owners[0]]['title']}', {fmt_s(catalog[owners[0]]['seconds'])}), "
                      f"but the file is this day's length")
    elif kind == "neighbour":
        row["verdict"], row["verdict_by"] = "wrong", "rule"
        row["why"] = f"title is #{nb}'s ('{catalog[nb]['title']}')"
    else:
        row["verdict"], row["why"], row["verdict_by"] = "unclear", f"title similarity {own:.2f}", "rule"
    return row


def clopper_pearson(errors, n, level=0.95):
    """Exact two-sided confidence interval for an error rate."""
    if n == 0:
        return (0.0, 1.0)
    alpha = 1 - level
    low = 0.0 if errors == 0 else beta.ppf(alpha / 2, errors, n - errors + 1)
    high = 1.0 if errors == n else beta.ppf(1 - alpha / 2, errors + 1, n - errors)
    return low, high


# ----------------------------------------------------------------------------- whole table

SERVICE_COLUMNS = {
    "bandcamp": ("bandcamp_url", "bandcamp_title", "bandcamp_album", "bandcamp_confidence",
                 "bandcamp_seconds"),
    "apple": ("apple_music_url", "apple_music_title", "apple_music_album",
              "apple_music_confidence", "apple_music_seconds"),
}


def stored_link(row, service):
    url, title, album, confidence, seconds = SERVICE_COLUMNS[service]
    return {"url": row[url], "title": row[title], "album": row[album],
            "confidence": row[confidence],
            "seconds": float(row[seconds]) if row[seconds] else None}


def scan_neighbours(links, catalog):
    """Every stored service title whose best fit is a nearby song, grouped into runs."""
    hits = []
    for row in links:
        n = int(row["number"])
        for service in SERVICE_COLUMNS:
            link = stored_link(row, service)
            if not link["url"]:
                continue
            own, nb, nb_sim, kind = title_judgement(link["title"], n, catalog)
            if kind == "neighbour":
                hits.append({"number": n, "service": service, "title": link["title"],
                             "confidence": link["confidence"], "own": own,
                             "neighbour": nb, "neighbour_sim": nb_sim})
    # Runs: consecutive songs on one service whose titles all point the same way.
    runs, by_service = [], defaultdict(list)
    for hit in hits:
        by_service[hit["service"]].append(hit)
    for service, items in by_service.items():
        current = []
        for hit in sorted(items, key=lambda h: h["number"]):
            offset = hit["neighbour"] - hit["number"]
            if current and hit["number"] == current[-1]["number"] + 1 \
                    and offset == current[-1]["neighbour"] - current[-1]["number"]:
                current.append(hit)
            else:
                if len(current) >= 2:
                    runs.append((service, current))
                current = [hit]
        if len(current) >= 2:
            runs.append((service, current))
    return hits, runs


def scan_dates(links):
    """Every link whose album is dated but doesn't contain the song's date."""
    out = []
    for row in links:
        n = int(row["number"])
        for service in SERVICE_COLUMNS:
            link = stored_link(row, service)
            if not link["url"]:
                continue
            fit, note = date_fit(service, link["album"], n)
            if fit == "outside":
                out.append({"number": n, "service": service, "title": link["title"],
                            "album": link["album"], "confidence": link["confidence"],
                            "note": note})
    return out


def scan_weak(links, catalog):
    """High links accepted on a weak title (position-only, or fuzzy under 0.85).

    links.py accepts these because their length matches another service's sure link or
    the catalog. That evidence only means something if no nearby song has the same
    length, so for each one: the gap to this song's other-service length and catalog
    Length, and the smallest gap to the catalog Length of a song within 3 days.
    """
    out = []
    for row in links:
        n = int(row["number"])
        for service, prefix, other in (("bandcamp", "bandcamp", "apple_music"),
                                       ("apple", "apple_music", "bandcamp")):
            match, score = row[f"{prefix}_match"], row[f"{prefix}_score"]
            if row[f"{prefix}_confidence"] != "high":
                continue
            if not (match == "position-only" or (match == "fuzzy" and float(score) < 0.85)):
                continue
            mine = float(row[f"{prefix}_seconds"]) if row[f"{prefix}_seconds"] else None
            theirs = float(row[f"{other}_seconds"]) if row[f"{other}_seconds"] else None
            gap_other = abs(mine - theirs) if mine is not None and theirs is not None else None
            gap_catalog = (abs(mine - catalog[n]["seconds"])
                           if mine is not None and catalog[n]["seconds"] is not None else None)
            near = []
            for k in range(-NEIGHBOURS, NEIGHBOURS + 1):
                m = n + k
                if k and m in catalog and catalog[m]["seconds"] is not None and mine is not None:
                    near.append((abs(mine - catalog[m]["seconds"]), m))
            nearest_gap, nearest = min(near) if near else (None, None)
            gaps = [g for g in (gap_other, gap_catalog) if g is not None]
            best_own = min(gaps) if gaps else None
            # Discriminating: the file is the same master (within 0.5 s) as the other
            # service's title-sure link for this song, or it is within 3 s of this song
            # and every neighbour's video Length is at least a second further away.
            other_sure = row[f"{other}_confidence"] == "high" and (
                row[f"{other}_match"] == "exact"
                or (row[f"{other}_match"] == "fuzzy" and float(row[f"{other}_score"]) >= 0.85))
            same_master = other_sure and gap_other is not None and gap_other <= 0.5
            ok = same_master or (best_own is not None and best_own <= LENGTH_NEAR[0] and
                                 (nearest_gap is None or nearest_gap > best_own + 1.0))
            out.append({"number": n, "service": service, "title": row[f"{prefix}_title"],
                        "match": match, "score": score,
                        "title_sim": similarity(row[f"{prefix}_title"], catalog[n]["title"]),
                        "gap_other": gap_other, "gap_catalog": gap_catalog,
                        "nearest_gap": nearest_gap, "nearest": nearest,
                        "discriminating": ok})
    return out


def scan_same_file(links, catalog, lengths):
    """Two songs 1-3 days apart whose files on one service have the same length (within
    SAME_FILE) while their catalog Lengths differ by more than 5 s: one file under two
    titles. For each pair, which title the file's length belongs to, if either."""
    by_n = {int(r["number"]): r for r in links}
    out = []
    for service in SERVICE_COLUMNS:
        for n, seconds in sorted(lengths[service].items()):
            for k in (1, 2, 3):
                m = n + k
                twin = lengths[service].get(m)
                if twin is None or abs(seconds - twin) > SAME_FILE:
                    continue
                a, b = catalog[n]["seconds"], catalog[m]["seconds"]
                if a is None or b is None or abs(a - b) <= 5:
                    continue
                owner = file_owner(seconds, n, m, service, catalog, lengths)
                out.append({"service": service, "pair": (n, m), "seconds": seconds,
                            "catalog": (a, b), "owner": owner,
                            "confidence": (stored_link(by_n[n], service)["confidence"],
                                           stored_link(by_n[m], service)["confidence"])})
    return out


def scan_duplicate_urls(links):
    seen = defaultdict(list)
    for row in links:
        for service in SERVICE_COLUMNS:
            url = stored_link(row, service)["url"]
            if url:
                seen[(service, url)].append(int(row["number"]))
    return {key: numbers for key, numbers in seen.items() if len(numbers) > 1}


def check_backfill(links, catalog):
    """The paste file against links.csv and against the cached public sheet."""
    problems = []
    backfill = read_csv(BACKFILL_CSV)
    by_n = {int(r["number"]): r for r in links}
    if [int(r["number"]) for r in backfill] != sorted(by_n):
        problems.append("backfill numbers are not #1..#N in order")
    for r in backfill:
        n = int(r["number"])
        day = song_date(n)
        if r["date"] != f"{day.month}/{day.day}/{day.year}":
            problems.append(f"#{n}: backfill date {r['date']} is not {day}")
        if r["title"] != catalog[n]["title"]:
            problems.append(f"#{n}: backfill title differs from the catalog")
        link_row = by_n[n]
        for service, column in (("bandcamp", "bandcamp"), ("apple", "apple_music")):
            link = stored_link(link_row, service)
            expected = link["url"] if link["confidence"] == "high" else ""
            if r[column] != expected:
                problems.append(f"#{n} {service}: backfill cell '{r[column]}' "
                                f"but links.csv says '{expected}'")
    sheet_rows = 0
    if SHEET_CSV.exists():
        with open(SHEET_CSV, newline="", encoding="utf-8") as f:
            sheet = list(csv.reader(f))
        # Row 1 is a note, row 2 the header; songs start on row 3.
        for index, cells in enumerate(sheet[2:], start=3):
            if not cells or not cells[0].strip():
                continue
            sheet_rows += 1
            number = int(cells[0])
            target = backfill[index - 3] if index - 3 < len(backfill) else None
            if target is None or int(target["number"]) != number or target["date"] != cells[1]:
                problems.append(f"sheet row {index} is #{number} {cells[1]}, the paste file's "
                                f"row there is {target and (target['number'], target['date'])}")
    return problems, sheet_rows, len(backfill)


# ----------------------------------------------------------------------------- report

def fmt_s(value):
    return "" if value is None else f"{value:.0f} s"


def md(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def link_cell(row):
    """'Title' (album #track) with the stored→live note if anything changed."""
    if row is None:
        return "no link"
    if row.get("missing"):
        return row["missing"]
    text = f"{md(row['live_title'])} ({md(row['album'])} #{row['track_number']}, {fmt_s(row['seconds'])})"
    return text


def verdict_cell(row):
    if row is None:
        return ""
    if row.get("missing"):
        return "**unreachable**"
    parts = [f"**{row['verdict']}**"]
    if row["verdict"] != "right" or row["verdict_by"] == "hand":
        parts.append(md(row["why"]))
    if row["date_fit"] == "outside":
        parts.append("album: " + md(row["date_note"]))
    elif row["date_fit"] == "undated":
        parts.append(md(row["date_note"]))
    if row["audio"] not in ("agrees", "no catalog length"):
        parts.append(f"audio {row['audio']}")
    if not row["has_audio"]:
        parts.append("page has no audio")
    if row["stale"]:
        parts.append("changed: " + md("; ".join(row["stale"])))
    if row["confidence"] != "high":
        parts.append(f"rated {row['confidence']}")
    return "; ".join(parts)


def audio_problem(row):
    """True when the file looks like another day's song (see audio_judgement)."""
    return row["audio"].startswith(("same file", "looks like"))


def rate_rows(rows, label):
    """Table rows, one per service: among links rated high (the ones in the sheet), how
    many are titled as another song, how many carry another song's title on this day's
    audio, and how many have a file that looks like another day's."""
    out = []
    for service, name in (("bandcamp", "Bandcamp"), ("apple", "Apple Music")):
        mine = [r for r in rows if r and r["service"] == service and not r.get("missing")]
        high = [r for r in mine if r["confidence"] == "high"]
        wrong = [r for r in high if r["verdict"] == "wrong"]
        mislabelled = [r for r in high if r["verdict"] == "mislabelled"]
        audio = [r for r in high if audio_problem(r) and r["verdict"] != "wrong"]
        unclear = [r for r in high if r["verdict"] == "unclear"]
        any_problem = {r["number"] for r in wrong + mislabelled + audio}
        lo1, up1 = clopper_pearson(len(wrong), len(high))
        lo2, up2 = clopper_pearson(len(any_problem), len(high))
        listing = lambda rs: ", ".join(f"#{r['number']}" for r in rs) or "0"
        out.append(f"| {label} | {name} | {len(high)} | {listing(wrong)} | {listing(mislabelled)} "
                   f"| {listing(audio)} | {listing(unclear)} "
                   f"| {100 * len(wrong) / max(1, len(high)):.1f}% ({100 * lo1:.1f}-{100 * up1:.1f}%) "
                   f"| {100 * len(any_problem) / max(1, len(high)):.1f}% ({100 * lo2:.1f}-{100 * up2:.1f}%) |")
    return out


def write_report(sample, judged, catalog, catalog_disagree, scans, fetch_notes, backfill,
                 searches):
    neighbour_hits, runs, outside, duplicates, weak, same_file, labels, links_by_n = scans
    backfill_problems, sheet_rows, backfill_rows = backfill
    spread = [(n, why) for n, group, why in sample if group == "spread"]
    checks = [(n, why) for n, group, why in sample if group == "check"]
    follow = [(n, why) for n, group, why in sample if group == "follow-up"]
    check_in_spread = [n for n, _ in spread
                       if judged[n]["links"]["bandcamp_confidence"] == "check"
                       or judged[n]["links"]["apple_music_confidence"] == "check"]

    def rows_of(numbers):
        out = []
        for n in numbers:
            out.extend(r for r in (judged[n]["bandcamp"], judged[n]["apple"]) if r)
        return out

    def live_note(n, service):
        """What the live page said about this link, if it was opened."""
        r = judged.get(n, {}).get(service)
        if not r or r.get("missing"):
            return "not opened"
        return f"{r['verdict']}: '{md(r['live_title'])}', {fmt_s(r['seconds'])}, audio {r['audio']}"

    spread_rows = rows_of(n for n, _ in spread)
    check_rows = rows_of([n for n, _ in checks] + check_in_spread)
    random_rows = rows_of(n for n, why in spread if why.startswith("random day"))
    all_rows = rows_of(n for n, _ in spread + checks)
    follow_rows = rows_of(n for n, _ in follow)

    L = ["# Links spot-check against the live pages", ""]
    L.append("Made by `analysis/checks/links_check.py`. It opens the live Bandcamp track page "
             "and Apple's lookup API (`https://itunes.apple.com/lookup?id=<trackId>`) for each "
             "sampled link in `dataset/links.csv` and asks whether the track is the song from "
             "that day, comparing with the songaday-display catalog's title and date. The title "
             "matching is written separately from `sources/` so it is a second opinion. Raw "
             "responses are in `cache/links-verify/`.")
    L.append("")
    L.append("## In short")
    L.append("")
    opened = rows_of(judged)
    L.append(f"- Sampled {len(spread) + len(checks)} songs: {len(spread)} spread across "
             f"2009-2026 (leap days, Jan 1 / Dec 31, season and year album boundaries, "
             f"{sum(1 for _, w in spread if w.startswith('random day'))} random days), and "
             f"every song links.csv rates **check** on some service "
             f"({len(checks) + len(check_in_spread)}; {len(check_in_spread)} of them were "
             f"already in the spread). With the follow-ups that is "
             f"{sum(1 for r in opened if r['service'] == 'bandcamp')} Bandcamp track pages and "
             f"{sum(1 for r in opened if r['service'] == 'apple')} Apple lookups opened, "
             f"{len(fetch_notes)} fetch problems.")
    L.append(f"- Follow-ups: {len(follow)} more songs whose high-rated links the whole-table "
             f"scans below point at (another song's title, an album outside the date, a file "
             f"that looks like another day's). They are opened live too, but kept out of the "
             f"rates, which would otherwise be inflated by picking suspects.")
    L.append("")
    L.append("Links rated **high** (the ones the paste file uses) among the opened links. "
             "'Titled as another song' is the error the title check looks for; "
             "'mislabelled' is a track with another song's title but this day's audio; "
             "'file looks like another day' is a right title on a file whose length is "
             "another song's (see [How a link is judged](#how-a-link-is-judged)). Rates are "
             "per link with exact 95% intervals.")
    L.append("")
    L.append("| Sample | Service | High links opened | Titled as another song | Mislabelled "
             "| File looks like another day | Unclear | Title error rate | Any problem |")
    L.append("| --- | --- | ---: | --- | --- | --- | --- | ---: | ---: |")
    n_random = sum(1 for _, w in spread if w.startswith("random day"))
    L.extend(rate_rows(random_rows, f"{n_random} random days"))
    L.extend(rate_rows(spread_rows, "40 spread songs"))
    L.extend(rate_rows(rows_of(n for n, _ in checks), f"{len(checks)} check songs"))
    L.extend(rate_rows(all_rows, f"spread + check ({len(spread) + len(checks)})"))
    L.extend(rate_rows(follow_rows, f"{len(follow)} follow-ups"))
    L.append("")
    L.append(f"- Off-by-one (whole table, {len(neighbour_hits)} stored titles that fit a "
             f"neighbouring song better than their own): see [Off-by-one](#off-by-one-scan-whole-table).")
    L.append(f"- Album period vs date (whole table): {len(outside)} links sit on a dated album "
             f"whose period doesn't contain the song's date; see [Boundaries](#year-and-season-boundaries-whole-table).")
    L.append(f"- Paste file: {len(backfill_problems)} problems in {backfill_rows} rows "
             f"(checked against links.csv and the {sheet_rows} song rows of the cached public sheet).")
    if catalog_disagree:
        L.append(f"- The two copies of some catalog chunks disagree on {len(catalog_disagree)} titles "
                 f"(the newest copy is used, as links.py does).")
    L.append("")

    # ---- What it shows: the findings, each computed from the tables below.
    L.append("## What it shows")
    L.append("")
    high_opened = [r for r in all_rows if not r.get("missing") and r["confidence"] == "high"]
    every = [r for r in rows_of(judged) if not r.get("missing")]
    counts = {name: (sum(1 for r in high_opened if r["service"] == service and r["verdict"] == "wrong"),
                     sum(1 for r in high_opened if r["service"] == service))
              for service, name in (("bandcamp", "Bandcamp"), ("apple", "Apple Music"))}
    verdicts = Counter((r["service"], r["verdict"]) for r in every)
    L.append("- **Titles: " + ", ".join(f"{name} {w} wrong of {n}" for name, (w, n) in counts.items())
             + "** high links opened in the spread and check samples. Across all "
             f"{len(every)} opened links (check-rated and follow-ups included): "
             f"{sum(v for (s_, k), v in verdicts.items() if k == 'wrong')} titled as another song, "
             f"{sum(v for (s_, k), v in verdicts.items() if k == 'unclear')} unsettled, and "
             f"{verdicts[('bandcamp', 'mislabelled')]} Bandcamp and "
             f"{verdicts[('apple', 'mislabelled')]} Apple tracks carrying another song's title "
             f"over this day's audio.")
    hand = [r for r in rows_of(judged) if not r.get("missing") and r["verdict_by"] == "hand"]
    hand_right = sum(1 for r in hand if r["verdict"] == "right")
    L.append(f"- {len(hand)} titles needed a hand verdict ("
             + ", ".join(f"#{r['number']} {r['service']}" for r in hand) + f"); {hand_right} "
             "of them are the day's song under a shortened or reworded title (reasons in the "
             "tables).")
    mis = [r for r in rows_of(judged) if not r.get("missing") and r["verdict"] == "mislabelled"]
    hit_verdicts = Counter(live_note(h["number"], h["service"]).split(":")[0]
                           for h in neighbour_hits)
    L.append(f"- **Off-by-one in titles:** the whole-table scan finds {len(neighbour_hits)} "
             f"stored titles that fit a neighbour better than their own song and "
             f"{len(runs)} runs of them; opened live, their verdicts are "
             + ", ".join(f"{k} {v}" for k, v in sorted(hit_verdicts.items())) + ". In all, "
             f"{len(mis)} Bandcamp pages show another song's title over this day's file: "
             + ", ".join(f"#{r['number']} ('{md(r['live_title'])}')" for r in mis)
             + ". They are rated high, so the paste file links them; by length the link plays "
             "the right song, but the page shows the wrong name.")
    outside_verdicts = Counter(live_note(o["number"], o["service"]).split(":")[0] for o in outside)
    boundary_rows = rows_of(n for n, why in spread if not why.startswith("random day"))
    boundary_verdicts = Counter(r["verdict"] for r in boundary_rows if not r.get("missing"))
    L.append(f"- **Year and season boundaries:** {len(outside)} links sit on an album whose "
             f"period doesn't contain the date, each by one day or by one year album; opened "
             f"live, their verdicts are " + ", ".join(f"{k} {v}" for k, v in
                                                       sorted(outside_verdicts.items()))
             + ". A right title there means the album was sequenced across the boundary, not "
             f"that the link is wrong. The {len(spread) - n_random} boundary songs in the spread "
             f"sample (leap days, Jan 1, Dec 31, season edges) have "
             f"{sum(boundary_verdicts.values())} links opened, with title verdicts "
             + ", ".join(f"{k} {v}" for k, v in sorted(boundary_verdicts.items())) + ".")

    # Clusters of high or check links whose file looks like another day's.
    flagged_all = sorted(((service, n, target) for (service, n), (label, target) in labels.items()
                          if label.startswith(("same file", "looks like"))),
                         key=lambda x: (x[0], x[1]))
    clusters, current = [], []
    for item in flagged_all:
        if current and item[0] == current[-1][0] and item[1] <= current[-1][1] + 1:
            current.append(item)
        else:
            if current:
                clusters.append(current)
            current = [item]
    if current:
        clusters.append(current)
    high_flagged = [c for c in clusters
                    if any(stored_link(links_by_n[n], s)["confidence"] == "high" for s, n, _ in c)]
    def describe(cluster):
        parts = []
        for s, n, target in cluster:
            rating = stored_link(links_by_n[n], s)["confidence"]
            arrow = "=" if "unclear" in labels[(s, n)][0] else "->"
            parts.append(f"#{n}{'*' if rating == 'high' else ''}{arrow}#{target}")
        return f"{cluster[0][0]} " + ", ".join(parts)
    n_high_audio = sum(1 for c in clusters for s, n, _ in c
                       if stored_link(links_by_n[n], s)["confidence"] == "high")
    listed = [(s_, n) for c in high_flagged for s_, n, _ in c]
    live_same = [(s_, n) for s_, n in listed
                 if judged.get(n, {}).get(s_) and not judged[n][s_].get("missing")
                 and not judged[n][s_]["stale"]]
    L.append(f"- **The real problem is audio, not titles.** Across the whole table, "
             f"{len(flagged_all)} files look like another day's song by length; {n_high_audio} "
             f"of them are rated high and in the paste file. The groups that hold a high one "
             f"(#N->#M: the file on #N's link is #M's; #N=#M: one file on both, whose is "
             f"unclear; * = rated high): "
             + "; ".join(describe(c) for c in high_flagged) + f". {len(live_same)} of these "
             f"{len(listed)} links were opened live, and each page still has the stored title, "
             f"album and length.")
    bc_flagged = [judged[n]["bandcamp"] for s_, n in live_same if s_ == "bandcamp"
                  and judged[n]["bandcamp"]["upload_lag"] is not None]
    late = [r for r in bc_flagged if song_date(r["number"]).year >= 2017]
    if late:
        uploads = sorted(song_date(r["number"]) + dt.timedelta(days=r["upload_lag"]) for r in late)
        L.append(f"- On Bandcamp, {len(late)} of the {len(bc_flagged)} opened pages in those "
                 f"groups are songs from 2017 on, and all {len(late)} were created between "
                 f"{uploads[0]} and {uploads[-1]}: the June 2026 upload of the Year Nine to "
                 f"Seventeen albums (see [Bandcamp upload dates](#bandcamp-upload-dates)). The "
                 f"earlier ones (#738, #1092, #1093) have the same file on Apple Music too, so "
                 f"the mix-up is in the masters, not the upload." if all(
                     n in (738, 1092, 1093) for n in (r["number"] for r in bc_flagged
                                                     if song_date(r["number"]).year < 2017))
                 else f"- On Bandcamp, {len(late)} of the {len(bc_flagged)} opened pages in those "
                      f"groups are songs from 2017 on, created between {uploads[0]} and "
                      f"{uploads[-1]}.")
    L.append("- Lengths are the only audio evidence here (nothing was downloaded), so a lone "
             "'looks like' may be a coincidence; 'same file' (two titles, one file to 0.05 s) "
             "and runs are strong.")
    L.append(f"- **Paste file:** {len(backfill_problems)} problems; every row lines up with "
             f"the public sheet's row for the same song.")
    L.append("")

    L.append("## How a link is judged")
    L.append("")
    L.append(f"- **Title** (the verdict): the live title is compared with the catalog title of "
             f"the song and of the {NEIGHBOURS} songs either side, after lower-casing, dropping "
             f"punctuation, bracketed parts and \"feat. ...\", and reading Apple's `*` as any "
             f"letter. Similarity {TITLE_SAME} or more is the same title (**right**); a "
             f"neighbour that is the same title and beats the song's own by {NEIGHBOUR_GAIN} is "
             f"**wrong**; anything else is **unclear** and gets a hand verdict from the evidence "
             f"below, with the reason written out.")
    L.append("- **Album and date**: Apple's seasonal albums are calendar quarters (Winter = "
             "Jan-Mar, Spring = Apr-Jun, Summer = Jul-Sep, Fall = Oct-Dec; the albums' first "
             "tracks confirm this) and its monthly albums are months. Bandcamp's year albums are "
             "calendar years (Year One = 2009). Bandcamp pages also give the upload date.")
    L.append(f"- **Audio** (lengths only; no audio was downloaded): the live length is "
             f"**agrees** when within {LENGTH_NEAR[0]:.0f} s or {100 * LENGTH_NEAR[1]:.0f}% of "
             f"the catalog's video Length, or of the other service's file ('agrees with ..., "
             f"not the video'). It is **same file as #M** when this service has a file of the "
             f"same length (within {SAME_FILE} s) on a song 1-3 days away whose video Length "
             f"differs by more than 5 s, and the file is #M's: the other service's file for #M "
             f"is that length and its file for this song isn't (or, failing that, only #M's "
             f"video fits). It is **looks like #M** when it is more than "
             f"{LENGTH_FAR[0]:.0f} s and {100 * LENGTH_FAR[1]:.0f}% from both the video and the "
             f"other service, but within {LENGTH_SHIFT} s of #M's video or other-service file "
             f"(1-3 days away), or when it sits next to such a file and fits the same shift "
             f"('in a run'). 'Same file' is strong evidence; a lone 'looks like' can be a "
             f"coincidence. Anything else off is **differs**.")
    L.append("- A **title error** is a link rated **high** (so it goes in the sheet) whose track "
             "is titled as another song. **Any problem** also counts a mislabelled track and a "
             "file that looks like another day's. Rates come with exact 95% (Clopper-Pearson) "
             "intervals; with no errors in n links the upper bound is about 3.7/n.")
    L.append("")

    if fetch_notes:
        L.append("## Fetch problems")
        L.append("")
        L.extend(f"- {note}" for note in fetch_notes)
        L.append("")

    def sample_table(numbers_with_why, title):
        L.append(f"## {title}")
        L.append("")
        L.append("| # | Date | Why picked | Catalog title | Bandcamp now | Bandcamp verdict | "
                 "Apple Music now | Apple verdict |")
        L.append("| ---: | --- | --- | --- | --- | --- | --- | --- |")
        for n, why in numbers_with_why:
            j = judged[n]
            bc_missing = None if j["bandcamp"] else "no link in links.csv"
            ap_missing = None if j["apple"] else "no link in links.csv"
            lag = j["bandcamp"].get("upload_lag") if j["bandcamp"] else None
            date_text = song_date(n).isoformat()
            if lag is not None:
                date_text += f" (BC upload {lag:+d} d)"
            L.append(f"| {n} | {date_text} | {md(why)} | {md(catalog[n]['title'])} "
                     f"({fmt_s(catalog[n]['seconds'])}) | "
                     f"{link_cell(j['bandcamp']) if j['bandcamp'] else bc_missing} | "
                     f"{verdict_cell(j['bandcamp'])} | "
                     f"{link_cell(j['apple']) if j['apple'] else ap_missing} | "
                     f"{verdict_cell(j['apple'])} |")
        L.append("")

    sample_table(spread, "Spread sample (40 songs)")
    if searches:
        L.append("### Spread songs with no Apple link: searched on Apple")
        L.append("")
        L.append("For each, Apple's Search API (US store) was asked for 'jonathan mann' plus "
                 "the catalog title; "
                 "any Jonathan Mann track whose title fits (similarity "
                 f"{TITLE_NEAR}+) is listed.")
        L.append("")
        for n, (status, hits) in sorted(searches.items()):
            found = "; ".join(f"'{md(t)}' on '{md(a)}' (id {i}, similarity {sim:.2f})"
                              for t, a, i, sim in hits) or "no Jonathan Mann track with that title"
            L.append(f"- #{n} {song_date(n)} '{md(catalog[n]['title'])}': {status}; {found}")
        L.append("")
    sample_table(checks, "Songs rated check (all 40)")

    # What the check rows turn out to be.
    L.append("### What the check ratings hold up to")
    L.append("")
    L.append("Each of the links rated check, by what the live page shows. A check rating is "
             "borne out when the file looks like another day's or differs from its song; it "
             "is over-cautious when the title is the day's song and the file agrees.")
    L.append("")
    tally = Counter()
    for r in check_rows:
        if r.get("missing") or r["confidence"] != "check":
            continue
        audio = ("looks like another day" if audio_problem(r) else
                 "agrees" if r["audio"].startswith("agrees") else r["audio"])
        tally[(r["service"], r["verdict"], audio)] += 1
    L.append("| Service | Title | File | Links |")
    L.append("| --- | --- | --- | ---: |")
    for (service, verdict, audio), count in sorted(tally.items()):
        L.append(f"| {service} | {verdict} | {audio} | {count} |")
    L.append("")
    L.append("Titles of check links that only a hand verdict could settle: " +
             ", ".join(f"#{r['number']} {r['service']}" for r in check_rows
                       if not r.get("missing") and r["verdict_by"] == "hand") + ".")
    L.append("")

    # Bandcamp's upload dates for the opened pages, by the song's year.
    L.append("### Bandcamp upload dates")
    L.append("")
    L.append("Each Bandcamp track page carries the date the track was created. Days from the "
             "song's date to that upload, for the pages opened, by the song's year:")
    L.append("")
    by_year, by_upload = defaultdict(list), defaultdict(list)
    for r in rows_of(judged):
        if r["service"] == "bandcamp" and not r.get("missing") and r["upload_lag"] is not None:
            year = song_date(r["number"]).year
            by_year[year].append(r["upload_lag"])
            by_upload[year].append(song_date(r["number"]) + dt.timedelta(days=r["upload_lag"]))
    L.append("| Year | Pages | Earliest | Median | Latest | Uploaded between |")
    L.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for year in sorted(by_year):
        lags = sorted(by_year[year])
        dates = sorted(by_upload[year])
        L.append(f"| {year} | {len(lags)} | {lags[0]:+d} | {lags[len(lags) // 2]:+d} | "
                 f"{lags[-1]:+d} | {dates[0]} .. {dates[-1]} |")
    L.append("")
    early = [r for r in rows_of(judged) if r["service"] == "bandcamp" and not r.get("missing")
             and r["upload_lag"] is not None and r["upload_lag"] < -2]
    L.append("A number below -2 is a track created before its song was written (a day "
             "either way is the GMT clock): "
             + (", ".join(f"#{r['number']} ({r['upload_lag']:+d} d, {r['verdict']})" for r in early)
                or "none") + ". Such a page was first made for something else and later "
             "given this file or title.")
    L.append("")

    if follow:
        sample_table(follow, "Follow-ups from the whole-table scans")
    L.append("## Off-by-one scan (whole table)")
    L.append("")
    L.append(f"Every stored service title in links.csv, compared with the catalog titles of "
             f"#N-{NEIGHBOURS}..#N+{NEIGHBOURS}. A hit is a title that fits a neighbour (similarity "
             f"{TITLE_SAME}+) better than its own song.")
    L.append("")
    if neighbour_hits:
        L.append("| # | Service | Their title | Rated | Own similarity | Fits | Similarity "
                 "| Live check |")
        L.append("| ---: | --- | --- | --- | ---: | --- | ---: | --- |")
        for h in neighbour_hits:
            L.append(f"| {h['number']} | {h['service']} | {md(h['title'])} | {h['confidence']} | "
                     f"{h['own']:.2f} | #{h['neighbour']} '{md(catalog[h['neighbour']]['title'])}' | "
                     f"{h['neighbour_sim']:.2f} | {live_note(h['number'], h['service'])} |")
        L.append("")
    if runs:
        L.append("Runs of two or more consecutive songs shifted the same way:")
        L.append("")
        for service, items in runs:
            L.append(f"- {service} #{items[0]['number']}-#{items[-1]['number']}: each title is "
                     f"song {items[0]['neighbour'] - items[0]['number']:+d}'s")
        L.append("")
    else:
        L.append("No runs of consecutive shifted titles on either service.")
        L.append("")

    L.append("## Year and season boundaries (whole table)")
    L.append("")
    L.append("Links whose dated album doesn't contain the song's date. A title that is the "
             "day's song on the neighbouring period's album means the album itself was "
             "sequenced across the boundary; that is not a matching error.")
    L.append("")
    if outside:
        L.append("| # | Date | Service | Their title | Album | Rated | Note | Live check |")
        L.append("| ---: | --- | --- | --- | --- | --- | --- | --- |")
        for o in outside:
            L.append(f"| {o['number']} | {song_date(o['number'])} | {o['service']} | {md(o['title'])} | "
                     f"{md(o['album'])} | {o['confidence']} | {md(o['note'])} | "
                     f"{live_note(o['number'], o['service'])} |")
        L.append("")
    odd = sorted({stored_link(r, "apple")["album"] for r in links_by_n.values()
                  if re.match(r"^(Winter|Spring|Summer|Fall|" + "|".join(MONTHS) + r")\b",
                              stored_link(r, "apple")["album"])
                  and apple_period(stored_link(r, "apple")["album"]) is None})
    for album in odd:
        numbers = [n for n, r in links_by_n.items() if stored_link(r, "apple")["album"] == album]
        L.append(f"Apple's album '{md(album)}' (#{min(numbers)}-#{max(numbers)}, {len(numbers)} "
                 f"links) has a song title stuck to its name, so its period can't be read and "
                 f"its {len(numbers)} links were left out of this check.")
        L.append("")

    L.append("## Files that sound like another day (whole table)")
    L.append("")
    L.append("Every stored file length in links.csv, judged the same way as the sampled links: "
             "'same file as #M' (one file under two titles, and it is #M's), 'looks like #M' "
             f"(more than {LENGTH_FAR[0]:.0f} s and {100 * LENGTH_FAR[1]:.0f}% from its own "
             f"song, within {LENGTH_SHIFT} s of #M's), or 'in a run' (next to such a file, "
             f"shifted the same way, within {LENGTH_SHIFT} s). Counts by rating:")
    L.append("")
    tally = Counter()
    for (service, n), (label, target) in labels.items():
        kind = label.split(" #")[0] + (" (in a run)" if "in a run" in label else "")
        tally[(service, stored_link(links_by_n[n], service)["confidence"], kind)] += 1
    L.append("| Service | Rated | Audio | Links |")
    L.append("| --- | --- | --- | ---: |")
    for (service, confidence, kind), count in sorted(tally.items()):
        L.append(f"| {service} | {confidence} | {kind} | {count:,} |")
    L.append("")
    flagged = sorted(((n, service, label) for (service, n), (label, target) in labels.items()
                      if label.startswith(("same file", "looks like"))
                      and stored_link(links_by_n[n], service)["confidence"] == "high"),
                     key=lambda x: (x[1], x[0]))
    L.append(f"The {len(flagged)} links rated **high** (so in the sheet) whose file looks like "
             f"another day's; each is opened live under Follow-ups:")
    L.append("")
    for n, service, label in flagged:
        link = stored_link(links_by_n[n], service)
        L.append(f"- {service} #{n} '{md(catalog[n]['title'])}': {fmt_s(link['seconds'])} file, "
                 f"video {fmt_s(catalog[n]['seconds'])}; {label}")
    L.append("")

    L.append("## One file under two titles (whole table)")
    L.append("")
    L.append(f"Songs 1-3 days apart whose files on the same service are the same length "
             f"(within {SAME_FILE} s) although their catalog Lengths differ by more than 5 s. "
             f"One of the two titles is playing the other's audio (or both are playing a third "
             f"file). 'Belongs to' is the song whose file on the other service is that length "
             f"(when only one is), else the song whose video Length fits (when only one does).")
    L.append("")
    if same_file:
        L.append("| Service | Songs | File | Catalog Lengths | Belongs to | Rated |")
        L.append("| --- | --- | ---: | --- | --- | --- |")
        for h in same_file:
            n, m = h["pair"]
            L.append(f"| {h['service']} | #{n} '{md(catalog[n]['title'])}', #{m} "
                     f"'{md(catalog[m]['title'])}' | {h['seconds']:.1f} s | "
                     f"{h['catalog'][0]} s, {h['catalog'][1]} s | "
                     f"{'#' + str(h['owner']) if h['owner'] else 'neither'} | "
                     f"#{n} {h['confidence'][0]}, #{m} {h['confidence'][1]} |")
        L.append("")
    else:
        L.append("None.")
        L.append("")

    L.append("## Weak titles accepted on length (whole table)")
    L.append("")
    weak_bad = [w for w in weak if not w["discriminating"]]
    L.append(f"{len(weak)} links are rated high on a weak title (position-only, or fuzzy under "
             f"0.85), so they are in the sheet because of their length. That evidence holds "
             f"when the file is the same master (within 0.5 s) as the other service's "
             f"title-sure link for the song, or is within {LENGTH_NEAR[0]:.0f} s of the song "
             f"and every song within {NEIGHBOURS} days has a video Length at least 1 s further "
             f"away. {len(weak) - len(weak_bad)} pass; {len(weak_bad)} "
             f"{'does' if len(weak_bad) == 1 else 'do'} not"
             + (":" if weak_bad else "."))
    L.append("")
    if weak_bad:
        L.append("| # | Service | Their title | Catalog title | Match | Gap to other service | "
                 "Gap to catalog | Closest neighbour |")
        L.append("| ---: | --- | --- | --- | --- | ---: | ---: | --- |")
        for w in weak_bad:
            gap = lambda g: "" if g is None else f"{g:.1f} s"
            L.append(f"| {w['number']} | {w['service']} | {md(w['title'])} | "
                     f"{md(catalog[w['number']]['title'])} | {w['match']} {w['score']} | "
                     f"{gap(w['gap_other'])} | {gap(w['gap_catalog'])} | "
                     f"#{w['nearest']} at {gap(w['nearest_gap'])} |")
        L.append("")

    L.append("## Track URLs used for more than one song (whole table)")
    L.append("")
    if duplicates:
        for (service, url), numbers in sorted(duplicates.items()):
            L.append(f"- {service}: {url} for " + ", ".join(f"#{n}" for n in numbers))
    else:
        L.append("None.")
    L.append("")

    L.append("## The paste file")
    L.append("")
    L.append(f"`analysis/sheet-backfill-links.csv` has {backfill_rows} rows. Each row's date "
             f"was checked against #1 = 2009-01-01, its title against the catalog, each cell "
             f"against links.csv (filled only when rated high, and then with that URL), and "
             f"rows 3 onward of the cached public sheet (`cache/sheet/sheet-gid0.csv`, "
             f"{sheet_rows} song rows) against the paste file's row in the same place.")
    L.append("")
    if backfill_problems:
        L.extend(f"- {p}" for p in backfill_problems[:60])
        if len(backfill_problems) > 60:
            L.append(f"- ... and {len(backfill_problems) - 60} more")
    else:
        L.append("No problems: pasting from row 3 puts every link on its own song's row.")
    L.append("")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="use only cache/links-verify/")
    args = parser.parse_args()

    catalog, catalog_disagree = load_catalog()
    links = read_csv(LINKS_CSV)
    links_by_n = {int(r["number"]): r for r in links}
    last_number = max(links_by_n)
    for n in links_by_n:
        if catalog[n]["date"] and catalog[n]["date"] != song_date(n).isoformat():
            sys.exit(f"catalog dates #{n} {catalog[n]['date']}, expected {song_date(n)}")

    # Each service's stored file lengths, the references for the audio judgement.
    lengths = {service: {} for service in SERVICE_COLUMNS}
    for row in links:
        for service in SERVICE_COLUMNS:
            link = stored_link(row, service)
            if link["url"] and link["seconds"] is not None:
                lengths[service][int(row["number"])] = link["seconds"]

    # The whole-table scans first: their high-rated hits become follow-ups in the sample.
    neighbour_hits, runs = scan_neighbours(links, catalog)
    outside = scan_dates(links)
    duplicates = scan_duplicate_urls(links)
    weak = scan_weak(links, catalog)
    same_file = scan_same_file(links, catalog, lengths)
    labels = scan_audio(links, catalog, lengths)
    backfill = check_backfill(links, catalog)
    follow_ups = {}
    for (service, n), (label, target) in sorted(labels.items(), key=lambda x: x[0][1]):
        # High links whose file looks like another song's: in the sheet, maybe wrong audio.
        if label.startswith(("same file", "looks like")) \
                and stored_link(links_by_n[n], service)["confidence"] == "high":
            follow_ups.setdefault(n, f"{service} file: {label}")
    for hit in neighbour_hits:
        if hit["confidence"] == "high":
            follow_ups[hit["number"]] = f"{hit['service']} title fits #{hit['neighbour']}"
    for hit in outside:
        if hit["confidence"] == "high":
            follow_ups.setdefault(hit["number"], f"{hit['service']} album is outside the date")
    for n, row in links_by_n.items():
        if "bandcamp_mislabelled" in row["flags"] and row["bandcamp_confidence"] == "high":
            follow_ups.setdefault(n, "links.py flags Bandcamp's title as another song's")

    sample = pick_sample(links_by_n, last_number, follow_ups)
    print("sample: " + ", ".join(f"{g} {sum(x == g for _, x, _ in sample)}"
                                 for g in ("spread", "check", "follow-up")))

    judged, fetch_notes = {}, []
    for n, group, why in sample:
        row = links_by_n[n]
        judged[n] = {"links": row, "bandcamp": None, "apple": None}
        bc = stored_link(row, "bandcamp")
        if bc["url"]:
            meta, page = bandcamp_page(bc["url"], args.offline)
            if meta.get("status") != 200:
                fetch_notes.append(f"#{n} Bandcamp {bc['url']}: HTTP {meta.get('status')}")
                judged[n]["bandcamp"] = {"service": "bandcamp", "missing": f"HTTP {meta.get('status')}",
                                         "confidence": bc["confidence"]}
            else:
                if meta.get("final_url", bc["url"]).rstrip("/") != bc["url"].rstrip("/"):
                    fetch_notes.append(f"#{n} Bandcamp {bc['url']} redirects to {meta['final_url']}")
                live = parse_bandcamp(page)
                judged[n]["bandcamp"] = judge_link("bandcamp", n, live, bc, catalog, lengths, labels)
        ap = stored_link(row, "apple")
        if ap["url"]:
            track_id = re.search(r"[?&]i=(\d+)", ap["url"]).group(1)
            result = apple_lookup(track_id, args.offline)
            if "_status" in result:
                fetch_notes.append(f"#{n} Apple lookup id={track_id}: {result['_status']}")
                judged[n]["apple"] = {"service": "apple", "missing": str(result["_status"]),
                                      "confidence": ap["confidence"]}
            else:
                live = {"title": result.get("trackName", ""),
                        "album": result.get("collectionName", ""),
                        "track_number": result.get("trackNumber"),
                        "seconds": (result["trackTimeMillis"] / 1000
                                    if result.get("trackTimeMillis") else None)}
                if result.get("artistName") != "Jonathan Mann":
                    fetch_notes.append(f"#{n} Apple id={track_id} is by {result.get('artistName')}")
                judged[n]["apple"] = judge_link("apple", n, live, ap, catalog, lengths, labels)

    # Songs in the spread sample with no Apple link: is the song really not on Apple?
    searches = {}
    for n, group, why in sample:
        if group == "spread" and not stored_link(links_by_n[n], "apple")["url"]:
            searches[n] = apple_search(n, catalog[n]["title"], args.offline, catalog)

    write_report(sample, judged, catalog, catalog_disagree,
                 (neighbour_hits, runs, outside, duplicates, weak, same_file, labels, links_by_n),
                 fetch_notes,
                 backfill,
                 searches)

    # Console summary: anything not plainly right, so MANUAL can be filled in.
    for n, group, why in sample:
        for service in ("bandcamp", "apple"):
            r = judged[n][service]
            if not r or r.get("missing"):
                continue
            if r["verdict"] != "right" or r["stale"] or r["date_fit"] != "ok" or r["audio"] != "agrees":
                print(f"#{n} {service} [{group}] {r['verdict']} ({r['verdict_by']}): "
                      f"live '{r['live_title']}' vs catalog '{catalog[n]['title']}' "
                      f"sim {r['title_sim']:.2f}; nb #{r['neighbour']} {r['neighbour_sim']:.2f}; "
                      f"{r['date_fit']} {r['date_note']}; audio {r['audio']} "
                      f"({fmt_s(r['seconds'])} vs {fmt_s(catalog[n]['seconds'])}); "
                      f"lag {r['upload_lag']}; stale {r['stale']}")
    print(f"neighbour hits {len(neighbour_hits)}, runs {len(runs)}, outside {len(outside)}, "
          f"duplicate urls {len(duplicates)}, backfill problems {len(backfill[0])}")
    for note in fetch_notes:
        print("fetch:", note)
    print(f"wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
