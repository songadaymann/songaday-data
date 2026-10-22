"""Bandcamp track links: which track on Jonathan's Bandcamp is which Song A Day song.

Source: https://jonathanmann.bandcamp.com, read-only and without logging in.
1. The /music page lists every release. Its grid is half plain HTML links and half a
   data-client-items JSON attribute; both are read. The Song A Day year albums are the ones
   titled "Song A Day: Year One" (2009) to "Song A Day: Year Eighteen" (2026, still growing).
   Some slugs end in "-2" (e.g. /album/song-a-day-year-seventeen-2), so the slugs are taken
   from the page, never guessed.
2. Each album page carries a data-tralbum JSON attribute (HTML-escaped) whose trackinfo lists
   every track: track_num, title, title_link (/track/...) and duration in seconds.
Raw pages are cached in cache/bandcamp/ (music.html and albums/<slug>.html), so a rerun makes
no requests. Bandcamp doesn't publish play or download counts, so there are none here.

Matching a track to a song number. Year K's track T is most likely song
(first song of year K) + T - 1, but only a matching title confirms it. Years Nine to
Eighteen line up exactly; Years One to Eight have skipped songs, extra and duplicate
uploads, and a few tracks out of order, so the matching works in three passes:
  pass 1  inside each album's own year, the in-order pairing of tracks and songs that
          matches the most titles (a weighted longest common subsequence). A skipped or
          extra track shifts the rest without breaking anything.
  pass 2  tracks still unplaced look for their title among the songs still unplaced in
          their year and NEAR_DAYS either side, or anywhere in the catalog if the title is
          exactly the same (Year Three ends with #1144, a February 2012 song).
  pass 3  "position-only": between two placed tracks, the unplaced tracks and the unplaced
          songs between those two tracks' songs are paired in order when there are as many of
          each, or by length (within 3 s) when there aren't. Duplicate uploads (same title and
          length as a placed track) are skipped. These are tracks whose title differs from
          the catalog's ("Our House" for "2100 California St."), or was copied from the
          track before by mistake; all of them agree with the catalog's length within 2 s.
          A position guess whose lengths are more than POSITION_MAX_LENGTH_GAP seconds apart
          is refused and printed, not written.
Normalizing a title: lowercase, accents flattened, "(feat. ...)" dropped, "&" read as
"and", dashes and slashes read as spaces, other punctuation removed, spaces collapsed.
"exact" means the normalized titles are equal. Otherwise the score is the best difflib
ratio between readings of the two titles (also with bracketed asides dropped, only the part
after a colon or before " - ", number words as digits, spaces removed, words sorted), or a
containment score when one title sits whole inside the other; FUZZY_MIN or more is "fuzzy".
Lengths never confirm or reject a title match (pass 1 only uses them to choose between two
tracks with the same title): the catalog's Length is the video's, which often differs from
the audio's by a minute or more.

Output: dataset/bandcamp.csv, one row per song in the catalog (#1 to the newest song):
  number, bandcamp_url (absolute https://jonathanmann.bandcamp.com/track/...),
  bandcamp_album (the album title), track_num, bandcamp_title (as written on Bandcamp),
  match (exact | fuzzy | position-only | none), match_score (the title score above, 0 to
  1, three decimals; for position-only it is low by definition; blank when match is none)
Songs with no Bandcamp track get match "none" and blank Bandcamp columns. Tracks that fit no
song are listed on screen, not in the table.

Run:  .venv/bin/python sources/bandcamp.py                    (downloads only what isn't cached)
      .venv/bin/python sources/bandcamp.py --refresh-current  (/music and the two newest
                                                               years' albums again, for new
                                                               tracks)
      .venv/bin/python sources/bandcamp.py --refresh          (every page again)
      .venv/bin/python sources/bandcamp.py --offline          (cache only, no network)

Paths, all optional:
  SONGADAY_CATALOG_DIR  songaday-display publish/meta folder (index-*.json chunks)
                        default ~/Library/Caches/songaday-display/publish/meta
"""

import argparse
import csv
import datetime as dt
import difflib
import functools
import glob
import html
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "bandcamp"
MUSIC_PAGE_CACHE = CACHE_DIR / "music.html"
ALBUM_CACHE = CACHE_DIR / "albums"
OUT_CSV = ROOT / "dataset" / "bandcamp.csv"

CATALOG_DIR = Path(
    os.environ.get("SONGADAY_CATALOG_DIR")
    or Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta"
)

BANDCAMP = "https://jonathanmann.bandcamp.com"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
REQUEST_PAUSE = 1.0  # seconds between live requests; one request at a time

FIRST_DAY = dt.date(2009, 1, 1)  # song #1
FIRST_YEAR = 2009  # "Year One"

FUZZY_MIN = 0.80  # difflib ratio at or above this counts as a fuzzy title match
NEAR_DAYS = 7  # pass 2 also looks this many days into the neighbouring years
POSITION_MAX_LENGTH_GAP = 20  # seconds; a position-only guess this far off in length is refused
BAND = 40  # pass 1 compares a track only with songs within this many places of its own

YEAR_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}

COLUMNS = [
    "number",
    "bandcamp_url",
    "bandcamp_album",
    "track_num",
    "bandcamp_title",
    "match",
    "match_score",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def song_date(number):
    return FIRST_DAY + dt.timedelta(days=number - 1)


def song_number(date):
    return (date - FIRST_DAY).days + 1


def length_seconds(text):
    """The catalog writes lengths as "m:ss" (sometimes "h:mm:ss"); None if unreadable."""
    if not text or not isinstance(text, str):
        return None
    parts = text.strip().split(":")
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        return None
    seconds = 0.0
    for value in numbers:
        seconds = seconds * 60 + value
    return seconds


def get_page(url, attempts=6):
    """GET a page politely: descriptive User-Agent, backoff on 429 and 5xx errors."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=headers, timeout=60)
        except requests.RequestException as error:
            wait = 2**attempt
            print(f"  network error ({error.__class__.__name__}), retrying in {wait}s")
            time.sleep(wait)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            wait = int(response.headers.get("Retry-After") or 2 ** (attempt + 1))
            print(f"  HTTP {response.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} for {url}")
        return response.text
    raise RuntimeError(f"gave up on {url} after {attempts} attempts")


def cached_page(url, path, refresh, offline):
    """Return the page at url, from path if cached (unless refresh), saving what is fetched."""
    if path.exists() and not refresh:
        return path.read_text()
    if offline:
        sys.exit(f"--offline but {path.relative_to(ROOT)} isn't cached")
    print(f"  GET {url}")
    text = get_page(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(path)
    time.sleep(REQUEST_PAUSE)
    return text


# ---------------------------------------------------------------------------
# 1. The song catalog
# ---------------------------------------------------------------------------


def load_catalog():
    """Return {song number: {"title", "length"}} from the songaday-display index chunks.

    Some chunks exist in two hashed versions; the newest file wins for each song.
    """
    files = sorted(glob.glob(str(CATALOG_DIR / "index-*.json")), key=os.path.getmtime)
    if not files:
        sys.exit(f"No index-*.json catalog chunks in {CATALOG_DIR} (set SONGADAY_CATALOG_DIR)")
    songs = {}
    for path in files:
        for song in json.loads(Path(path).read_text())["songs"]:
            songs[song["n"]] = {
                "title": song.get("t") or "",
                "length": length_seconds((song.get("a") or {}).get("Length")),
            }
    return dict(sorted(songs.items()))


# ---------------------------------------------------------------------------
# 2. Bandcamp pages
# ---------------------------------------------------------------------------


def year_of_album_title(title):
    """ "Song A Day: Year Seventeen" -> 17; None for any other release."""
    match = re.fullmatch(r"\s*song a day\s*:?\s*year\s+([a-z]+)\s*", title.lower())
    if not match:
        return None
    return YEAR_WORDS.get(match.group(1))


def year_of_slug(slug):
    """ "song-a-day-year-seventeen-2" -> 17; None for any other slug."""
    match = re.fullmatch(r"song-a-day-year-([a-z]+)(?:-\d+)?", slug)
    if not match:
        return None
    return YEAR_WORDS.get(match.group(1))


def find_year_albums(music_html):
    """Return {year number: album path} for every Song A Day year album on /music.

    The grid's first items are plain <a href="/album/..."> links; the rest are in the
    data-client-items attribute as JSON with page_url and title. Both are read. A year whose
    slug looks right is checked against the album page's own title later.
    """
    paths = set(re.findall(r'href="(/album/[^"?#]+)"', music_html))
    titles = {}
    attribute = re.search(r'data-client-items="([^"]*)"', music_html)
    if attribute:
        for item in json.loads(html.unescape(attribute.group(1))):
            if item.get("type") == "album" and item.get("page_url"):
                paths.add(item["page_url"])
                titles[item["page_url"]] = item.get("title") or ""
    albums = {}
    for path in sorted(paths):
        slug = path.rsplit("/", 1)[-1]
        year = year_of_slug(slug) or year_of_album_title(titles.get(path, ""))
        if year is None:
            continue
        if year in albums:
            sys.exit(f"two albums for Year {year}: {albums[year]} and {path}")
        albums[year] = path
    return dict(sorted(albums.items()))


def parse_album(album_html):
    """Return (album title, [track dicts]) from an album page's data-tralbum attribute."""
    attribute = re.search(r'data-tralbum="([^"]*)"', album_html)
    if not attribute:
        raise ValueError("no data-tralbum attribute on the album page")
    tralbum = json.loads(html.unescape(attribute.group(1)))
    title = (tralbum.get("current") or {}).get("title") or ""
    tracks = []
    for info in tralbum.get("trackinfo") or []:
        if not info.get("title_link"):
            continue  # an unreleased placeholder has no page of its own
        tracks.append(
            {
                "track_num": info.get("track_num"),
                "title": (info.get("title") or "").strip(),
                "url": BANDCAMP + info["title_link"],
                "duration": info.get("duration"),
            }
        )
    return title, tracks


def load_albums(refresh, offline, refresh_current=False):
    """Return {year number: {"title", "path", "tracks"}} for every Song A Day year album.

    refresh downloads every page again; refresh_current only /music and the albums of the
    two newest years (the one still growing, and the one before it in case its last days
    were uploaded late).
    """
    music_html = cached_page(
        BANDCAMP + "/music", MUSIC_PAGE_CACHE, refresh or refresh_current, offline
    )
    found = find_year_albums(music_html)
    newest = sorted(found)[-2:]
    albums = {}
    for year, path in found.items():
        slug = path.rsplit("/", 1)[-1]
        again = refresh or (refresh_current and year in newest)
        album_html = cached_page(BANDCAMP + path, ALBUM_CACHE / f"{slug}.html", again, offline)
        title, tracks = parse_album(album_html)
        if year_of_album_title(title) not in (None, year):
            sys.exit(f"{path} is titled {title!r}, not Year {year}")
        albums[year] = {"title": title, "path": path, "tracks": tracks}
    return albums


# ---------------------------------------------------------------------------
# 3. Comparing titles
# ---------------------------------------------------------------------------

# Words too common in titles to say two titles are related.
STOP_WORDS = {"the", "and", "you", "for", "with", "song", "your", "are", "its", "from", "this"}
NUMBER_WORDS = {word: str(value) for word, value in YEAR_WORDS.items()}


@functools.lru_cache(maxsize=None)
def normalize(title):
    """Lowercase, flatten accents, drop "(feat. ...)", read "&" as "and", turn dashes and
    slashes into spaces, remove other punctuation, collapse spaces.
    "Hands (Oh No!)" -> "hands oh no". Letters of any script are kept (Hebrew and Yiddish
    titles exist); a title of emoji only is kept as written, lowercased."""
    text = unicodedata.normalize("NFKD", title)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    # "(feat. Brittain Ashford)", "[ft. ...]" and a trailing "feat. ..." or "featuring ..."
    text = re.sub(r"[(\[]\s*(feat\.?|ft\.|featuring)\s[^)\]]*[)\]]", " ", text)
    text = re.sub(r"\s(feat\.|ft\.|featuring)\s.*$", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[-‐-―/]", " ", text)
    text = re.sub(r"[^\w\s]", "", text).replace("_", " ")
    text = " ".join(text.split())
    return text or " ".join(title.casefold().split())


@functools.lru_cache(maxsize=None)
def variants(title):
    """The normalized title plus shorter readings of it that Bandcamp or the catalog
    sometimes use: without bracketed asides, only the part after the last colon (Year Two's
    "The Story of Wandering Fall, Act 2, Scene 3: Tiny Wings"), only the part before " - "
    (the catalog's "SpinTunes #10 - Sign Up Now!"), and each of those with number words as
    digits ("The Three Rules" -> "the 3 rules")."""
    forms = {normalize(title), normalize(re.sub(r"[(\[][^)\]]*[)\]]", " ", title))}
    if ":" in title:
        forms.add(normalize(title.rsplit(":", 1)[1]))
    for dash in (" - ", " – ", " — "):
        if dash in title:
            forms.add(normalize(title.split(dash, 1)[0]))
    forms |= {" ".join(NUMBER_WORDS.get(word, word) for word in form.split()) for form in forms}
    return tuple(sorted(form for form in forms if form))


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def similarity(track_title, song_title):
    """Return (score from 0 to 1, "exact" or "fuzzy" or None).

    exact: the normalized titles are equal (score 1).
    Otherwise the score is the best of these, over every pair of variants:
      - difflib's ratio;
      - the ratio with spaces removed ("FunFacts" / "Fun Facts", "4EVA" / "4 EVA");
      - the ratio with the words sorted ("Courtney and Sarah" / "Sarah and Courtney");
      - when one variant sits whole inside the other ("I Love Battlestar" in
        "I Love Battlestar Galactica") and is at least two words or eight letters long,
        0.8 + 0.2 * (shorter length / longer length).
    A score of FUZZY_MIN or more is "fuzzy".
    """
    a, b = normalize(track_title), normalize(song_title)
    if a == b:
        return 1.0, "exact"
    best = max(ratio(a, b), ratio(a.replace(" ", ""), b.replace(" ", "")))
    # Shortcut for the common case of two unrelated titles: if they share no telling word,
    # the shorter readings can't be related either, so stop here.
    shared = (set(a.split()) & set(b.split())) - STOP_WORDS
    if best < 0.5 and not any(len(word) >= 3 or word.isdigit() for word in shared):
        return round(best, 3), None
    for x in variants(track_title):
        for y in variants(song_title):
            if x == y:
                best = max(best, 1.0)
                continue
            best = max(
                best,
                ratio(x, y),
                ratio(x.replace(" ", ""), y.replace(" ", "")),
                ratio(" ".join(sorted(x.split())), " ".join(sorted(y.split()))),
            )
            short, long = sorted((x, y), key=len)
            if (len(short.split()) >= 2 or len(short) >= 8) and f" {short} " in f" {long} ":
                best = max(best, 0.8 + 0.2 * len(short) / len(long))
    return round(best, 3), ("fuzzy" if best >= FUZZY_MIN else None)


def lengths_agree(track, song, within):
    """True if both lengths are known and differ by at most `within` seconds, False if they
    differ by more, None if either is unknown (Bandcamp shows 0 for a track with no audio)."""
    if not track["duration"] or song["length"] is None:
        return None
    return abs(track["duration"] - song["length"]) <= within


# ---------------------------------------------------------------------------
# 4. Matching tracks to song numbers
# ---------------------------------------------------------------------------


def year_range(year, catalog):
    """First and last song number of Song A Day year `year` (1 = 2009) in the catalog."""
    first = song_number(dt.date(FIRST_YEAR + year - 1, 1, 1))
    last = min(song_number(dt.date(FIRST_YEAR + year - 1, 12, 31)), max(catalog))
    return first, last


def align(tracks, numbers, catalog):
    """Pass 1: the in-order pairing of tracks with songs that matches the most titles.

    A weighted longest-common-subsequence: a track and a song can pair only if their titles
    match (score >= FUZZY_MIN), and the pairing keeps both lists in order, so a skipped or
    extra track shifts everything after it without breaking the matches. Each pair is worth
    its title score, plus a little when the lengths agree within 3 s (to choose between two
    tracks with the same title). A track is only compared with songs within BAND places of
    its own place. Returns {track index: (song number, score, kind)}.
    """
    m, n = len(tracks), len(numbers)
    pair = {}  # (i, j) -> (weight, score, kind), only for title matches
    for i, track in enumerate(tracks):
        for j in range(max(0, i - BAND), min(n, i + BAND + 1)):
            song = catalog[numbers[j]]
            score, kind = similarity(track["title"], song["title"])
            if kind:
                bonus = 0.05 if lengths_agree(track, song, 3) else 0.0
                pair[(i, j)] = (score + bonus, score, kind)
    # best[i][j]: the best total for tracks[:i] against numbers[:j]
    best = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        row, above = best[i], best[i - 1]
        for j in range(1, n + 1):
            value = max(above[j], row[j - 1])
            if (i - 1, j - 1) in pair:
                value = max(value, above[j - 1] + pair[(i - 1, j - 1)][0])
            row[j] = value
    # Walk back from the end to read off the pairs.
    matched = {}
    i, j = m, n
    while i > 0 and j > 0:
        here = best[i][j]
        step = pair.get((i - 1, j - 1))
        if step and abs(here - best[i - 1][j - 1] - step[0]) < 1e-9:
            matched[i - 1] = (numbers[j - 1], step[1], step[2])
            i, j = i - 1, j - 1
        elif best[i - 1][j] == here:
            i -= 1
        else:
            j -= 1
    return matched


def match_all(albums, catalog):
    """Match every year album's tracks to song numbers (the three passes in the docstring).

    Returns (rows, notes): rows is {song number: CSV row}; notes lists the tracks that fit
    no song and the position guesses refused because the lengths are far apart.
    Every song gets at most one track and every track at most one song. Pass 1 only looks
    inside each album's own year, so a song uploaded to two albums goes to its own year's.
    """
    placed = {}  # song number -> (year, track index, score, kind)
    by_album = {year: {} for year in albums}  # year -> {track index: song number}

    def place(year, index, number, score, kind):
        placed[number] = (year, index, score, kind)
        by_album[year][index] = number

    # Pass 1: in-order title alignment inside each album's own year.
    for year, album in albums.items():
        first, last = year_range(year, catalog)
        numbers = list(range(first, last + 1))
        for index, (number, score, kind) in align(album["tracks"], numbers, catalog).items():
            place(year, index, number, score, kind)

    # Pass 2: tracks still unplaced look for their title among the unplaced songs of their
    # year and NEAR_DAYS either side (exact or fuzzy), or anywhere in the catalog (exact
    # titles only, and not when the lengths are more than 5 s apart). Best score first;
    # ties go to the song nearest the track's expected place.
    by_title = defaultdict(list)
    for number, song in catalog.items():
        by_title[normalize(song["title"])].append(number)
    candidates = []
    for year, album in albums.items():
        first, last = year_range(year, catalog)
        near = range(max(1, first - NEAR_DAYS), min(max(catalog), last + NEAR_DAYS) + 1)
        for index, track in enumerate(album["tracks"]):
            if index in by_album[year]:
                continue
            guess = expected_number(by_album[year], index, first)
            for number in near:
                if number not in placed:
                    score, kind = similarity(track["title"], catalog[number]["title"])
                    if kind:
                        candidates.append((-score, abs(number - guess), year, index, number, kind))
            for number in by_title.get(normalize(track["title"]), []):
                if number not in placed and number not in near:
                    if lengths_agree(track, catalog[number], 5) is not False:
                        candidates.append((-1.0, abs(number - guess), year, index, number, "exact"))
    for negative_score, _, year, index, number, kind in sorted(candidates):
        if number not in placed and index not in by_album[year]:
            place(year, index, number, -negative_score, kind)

    # Pass 3: position-only. Between two placed tracks of an album, the unplaced tracks and
    # the unplaced songs that fall between those two tracks' songs are paired up:
    #   - as many tracks as songs: paired in order, unless a pair's lengths are more than
    #     POSITION_MAX_LENGTH_GAP seconds apart (that pair is refused and reported);
    #   - otherwise: each track, in order, takes the next free song whose length is within
    #     3 s of its own (the closest if several), or stays unplaced.
    # The album's start counts as a placed track (the song before the year's first), and so
    # does its end (the song after the year's last, or after the newest song in the catalog).
    # A track with the same title as a placed track and the same length (within 3 s, or with
    # no audio to compare) is a duplicate upload and is never placed by position. Same title
    # with a different length is usually a track whose title was copied from the track
    # before it by mistake (Year Seven's two "Don't Soldier On Blindly"), so those stay in.
    twins = defaultdict(list)  # normalized title -> [(year, track index)] of placed tracks
    for y in albums:
        for i in by_album[y]:
            twins[normalize(albums[y]["tracks"][i]["title"])].append((y, i))

    def duplicate_of(year, index):
        """The song number of the placed track this one duplicates, or None."""
        track = albums[year]["tracks"][index]
        for y, i in twins.get(normalize(track["title"]), []):
            twin = albums[y]["tracks"][i]
            if (
                not track["duration"]
                or not twin["duration"]
                or abs(track["duration"] - twin["duration"]) <= 3
            ):
                return by_album[y][i]
        return None

    refused = []
    for year, album in albums.items():
        first, last = year_range(year, catalog)
        tracks = album["tracks"]
        anchors = dict(by_album[year])
        anchors[-1] = first - 1
        anchors[len(tracks)] = last + 1
        order = sorted(anchors)
        for before, after in zip(order, order[1:]):
            gap_tracks = [i for i in range(before + 1, after) if duplicate_of(year, i) is None]
            gap_songs = [
                n for n in range(anchors[before] + 1, anchors[after])
                if n not in placed and n in catalog
            ]
            if not gap_tracks or not gap_songs:
                continue
            if len(gap_tracks) == len(gap_songs):
                for index, number in zip(gap_tracks, gap_songs):
                    track, song = tracks[index], catalog[number]
                    if lengths_agree(track, song, POSITION_MAX_LENGTH_GAP) is False:
                        refused.append((year, index, number))
                        continue
                    score, _ = similarity(track["title"], song["title"])
                    place(year, index, number, score, "position-only")
            else:
                free = list(gap_songs)
                for index in gap_tracks:
                    duration = tracks[index]["duration"]
                    fits = [n for n in free if lengths_agree(tracks[index], catalog[n], 3)]
                    if not fits:
                        continue
                    number = min(fits, key=lambda n: abs(duration - catalog[n]["length"]))
                    free = [n for n in free if n > number]  # keep the pairing in order
                    score, _ = similarity(tracks[index]["title"], catalog[number]["title"])
                    place(year, index, number, score, "position-only")

    rows = {}
    for number in catalog:
        row = {"number": number, "match": "none"}
        if number in placed:
            year, index, score, kind = placed[number]
            track = albums[year]["tracks"][index]
            row.update(
                bandcamp_url=track["url"],
                bandcamp_album=albums[year]["title"],
                track_num=track["track_num"],
                bandcamp_title=track["title"],
                match=kind,
                match_score=f"{score:.3f}",
            )
        rows[number] = row

    # Explain every track left over.
    leftovers = []
    for year, album in albums.items():
        for index, track in enumerate(album["tracks"]):
            if index in by_album[year]:
                continue
            twin = duplicate_of(year, index)
            if twin is not None:
                same = "same title and length" if track["duration"] else "same title"
                why = f"duplicate of the track placed at #{twin} ({same})"
            else:
                # The closest title in the whole catalog, to say whether the song is already
                # linked to another upload (e.g. a re-release on a later year's album).
                score, number = max(
                    (similarity(track["title"], song["title"])[0], n) for n, song in catalog.items()
                )
                if score >= FUZZY_MIN and number in placed:
                    y, i, _, _ = placed[number]
                    why = (
                        f"title matches #{number} ({score:.3f}), which already has "
                        f"Year {y} track {albums[y]['tracks'][i]['track_num']}"
                    )
                elif score >= FUZZY_MIN:
                    why = (
                        f"title is close to #{number} ({score:.3f}), which has no track, but "
                        "that song is too far from this album's year to link without a check"
                    )
                else:
                    why = "no song with this title"
            if not track["duration"]:
                why += "; the track has no audio"
            leftovers.append((year, track, why))
    refused = [(year, albums[year]["tracks"][index], number) for year, index, number in refused]
    return rows, {"leftovers": leftovers, "refused": refused}


def expected_number(placed_in_album, index, first):
    """The song number track `index` would be, judging by the nearest placed track before it
    (or the album's start)."""
    before = [k for k in placed_in_album if k < index]
    if not before:
        return first + index
    k = max(before)
    return placed_in_album[k] + (index - k)


# ---------------------------------------------------------------------------
# 5. Output
# ---------------------------------------------------------------------------


def write_csv(rows):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CSV.with_suffix(".tmp")
    with tmp.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for number in sorted(rows):
            writer.writerow({column: rows[number].get(column, "") for column in COLUMNS})
    tmp.replace(OUT_CSV)


def report(rows, notes, albums, catalog):
    """Print coverage by year, the songs with no track, and the tracks with no song."""
    kinds = ["exact", "fuzzy", "position-only", "none"]
    counts = defaultdict(Counter)
    for number, row in rows.items():
        counts[song_date(number).year][row["match"]] += 1
    tracks_by_year = {FIRST_YEAR + year - 1: len(a["tracks"]) for year, a in albums.items()}
    print(f"\n{'year':<6}{'songs':>6}{'tracks':>7}" + "".join(f"{k:>15}" for k in kinds))
    total = Counter()
    for year in sorted(counts):
        songs = sum(counts[year].values())
        total.update(counts[year])
        print(
            f"{year:<6}{songs:>6}{tracks_by_year.get(year, 0):>7}"
            + "".join(f"{counts[year][k]:>15}" for k in kinds)
        )
    songs = sum(total.values())
    linked = songs - total["none"]
    print(
        f"{'all':<6}{songs:>6}{sum(tracks_by_year.values()):>7}"
        + "".join(f"{total[k]:>15}" for k in kinds)
    )
    print(f"\n{linked} of {songs} songs ({100 * linked / songs:.1f}%) have a Bandcamp track.")

    missing = [n for n, row in rows.items() if row["match"] == "none"]
    print(f"\nSongs with no Bandcamp track ({len(missing)}):")
    for number in missing:
        print(f"  #{number} {song_date(number)}  {catalog[number]['title']}")

    print(f"\nPosition guesses refused because the lengths differ ({len(notes['refused'])}):")
    for year, track, number in notes["refused"]:
        song = catalog[number]
        print(
            f"  #{number} {song['title']!r} ({song['length']:.0f} s) vs Year {year} track "
            f"{track['track_num']} {track['title']!r} ({track['duration']:.0f} s)"
        )

    print(f"\nTracks that fit no song ({len(notes['leftovers'])}):")
    for year, track, why in notes["leftovers"]:
        print(f"  Year {year} track {track['track_num']} {track['title']!r}: {why}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--refresh", action="store_true", help="download every page again")
    parser.add_argument(
        "--refresh-current",
        action="store_true",
        help="download /music and the two newest years' albums again",
    )
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    args = parser.parse_args()
    if args.offline and (args.refresh or args.refresh_current):
        parser.error("--offline can't be combined with --refresh or --refresh-current")

    catalog = load_catalog()
    print(f"Catalog: songs #{min(catalog)} to #{max(catalog)}")
    albums = load_albums(args.refresh, args.offline, args.refresh_current)
    print(f"Bandcamp: {len(albums)} Song A Day year albums, "
          f"{sum(len(a['tracks']) for a in albums.values())} tracks")
    missing_years = sorted(set(range(1, max(albums) + 1)) - set(albums))
    if missing_years:
        print(f"  no album found for Year(s) {missing_years}")

    rows, notes = match_all(albums, catalog)
    write_csv(rows)
    report(rows, notes, albums, catalog)
    print(f"\nWrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
