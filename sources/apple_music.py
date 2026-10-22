"""Apple Music links for each Song A Day song.

Source: Apple's free, keyless iTunes Lookup API (country=US).
  1. https://itunes.apple.com/lookup?id=188742143&entity=album&limit=200
     lists every release by the artist "Jonathan Mann" (id 188742143).
  2. https://itunes.apple.com/lookup?id=<collectionId>&entity=song&limit=200
     lists each release's tracks (trackNumber, discNumber, trackName, trackViewUrl, ...).
The API doesn't return ISRCs, so tracks are tied to songs by date and title.

How a track becomes a song number:
- Period albums ("Winter, 2009", "September, 2026", ...) cover a known stretch of days, so
  track k should be the song written on day k of that stretch. Each album's tracks are
  aligned, in order, against the catalog songs of that stretch (plus MARGIN_DAYS either
  side) by title similarity, the way a diff lines up two lists. A track whose title
  matches is "exact" (same normalized title) or "fuzzy" (close enough). Then:
    * a strong title match the in-order pass skipped (two swapped tracks, or a song filed
      on the next month's album) is picked up in a second, unordered pass;
    * a track whose title names exactly one song anywhere in the catalog takes that song,
      whatever its date ("Summer, 2014" has the 2009 song "The Robots Don't Love You
      Anymore" where the catalog has "Every Movie Robot SUPERCUT");
    * a track whose title doesn't match, but which sits between two matched tracks with
      the same day offset (or before or after a run that starts on the album's first
      day), takes its song by position: "position-only".
- Singles, EPs and compilations have no date range, so each track is matched by title
  against the whole catalog, keeping the song closest to (and preferably before) the
  release date. A single may also take a song from the week before its release with a
  looser title match, since singles often come out the day the song is written under a
  different name ("The Wind of God" is "Kenneth Copeland On COVID-19 (Wind of God...)").
- "The Mario Opera: Act One" (2003) and "Songonauts" (a band project) aren't Song A Day
  albums. Their tracks only count when the titles match closely and the matched songs
  cluster together in time; that picks up the Songonauts songs Jonathan wrote as his
  songs of the day in June 2017 (#3082-#3094), which Apple has only on that album.
- Apple's track length is a check: matches the title doesn't vouch for (position-only,
  or fuzzy below LOOSE_CHECK) are dropped when the length clearly disagrees with the
  catalog's Length. duration_diff_s in the output is Apple's length minus the catalog's.
- When a song is on more than one release (an album track plus a single, say), the period
  album track whose dates contain the song is the primary link and the others go in
  other_releases, as "Album: URL" pairs separated by " | ".

Output: dataset/apple_music.csv, one row per song in the catalog (#1 to the last song in
the songaday-display catalog). Songs with no Apple Music track have match = "none".
For checking by hand (both gitignored, rewritten on every run):
  cache/apple/unmatched-tracks.csv  Song A Day tracks that couldn't be tied to any song
  cache/apple/duration-checks.csv   linked songs whose Apple length is far off the
                                     catalog's; "fits_neighbour" means the audio matches
                                     the previous or next song's length instead, so Apple's
                                     titles may be shifted against the audio there

Run:  .venv/bin/python sources/apple_music.py            (fetches only what isn't cached)
      .venv/bin/python sources/apple_music.py --offline  (cache only, no network)
      .venv/bin/python sources/apple_music.py --refresh  (fetch the album list again, to
                                                          pick up new releases; albums
                                                          already cached aren't refetched)

Network on a cold cache: 188 requests (one album list plus one per release), about 10
minutes at Apple's limit of roughly 20 requests a minute. A rerun makes no requests.

Paths, all optional:
  SONGADAY_CATALOG_DIR  songaday-display publish/meta folder (index-*.json chunks)
                        default ~/Library/Caches/songaday-display/publish/meta
"""

import argparse
import csv
import datetime as dt
import difflib
import glob
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "apple"
ALBUM_CACHE = CACHE_DIR / "albums"
OUT_CSV = ROOT / "dataset" / "apple_music.csv"
UNMATCHED_CSV = CACHE_DIR / "unmatched-tracks.csv"
DURATION_CSV = CACHE_DIR / "duration-checks.csv"

CATALOG_DIR = Path(
    os.environ.get("SONGADAY_CATALOG_DIR")
    or Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta"
)

LOOKUP_URL = "https://itunes.apple.com/lookup"
ARTIST_ID = 188742143  # "Jonathan Mann" on Apple Music
COUNTRY = "US"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
REQUEST_PAUSE = 3.2  # seconds between live requests; Apple allows about 20 per minute

FIRST_DAY = dt.date(2009, 1, 1)  # song #1

# Releases by this artist that aren't Song A Day.
NOT_SONG_A_DAY = {"The Mario Opera: Act One", "Songonauts"}

# Title-matching thresholds (similarity runs from 0 to 1; see title_similarity).
ALIGN_MIN = 0.60  # a period-album track and a song may be paired by title at this or above
LOOSE_CHECK = 0.75  # pairs below this must also sit at the same day offset as a neighbour
SINGLE_MIN = 0.85  # singles, EPs and compilations need at least this
MARGIN_DAYS = 10  # period albums may start or end a few days off their nominal range
UNIQUE_TITLE_MIN = 10  # a unique title this long may match a song from any date
CLUSTER_DAYS = 30  # for albums that aren't Song A Day: how close matched songs must sit
# Apple's track length and the catalog's Length agree to within a second for most songs.
# Matches the title doesn't vouch for (position-only, or fuzzy below LOOSE_CHECK) are
# dropped when the two lengths are both known and further apart than 10 seconds or 15%
# of the song, whichever is more.
DURATION_TOLERANCE = 10  # seconds
DURATION_SHARE = 0.15

SEASON_MONTHS = {"Winter": 1, "Spring": 4, "Summer": 7, "Fall": 10}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
PERIOD_RE = re.compile(r"^(Winter|Spring|Summer|Fall|" + "|".join(MONTHS) + r"),? (\d{4})")

COLUMNS = [
    "number",
    "apple_music_url",
    "apple_track_id",
    "apple_album",
    "track_number",
    "apple_title",
    "match",
    "match_score",
    "duration_diff_s",
    "other_releases",
]
MATCH_RANK = {"exact": 0, "fuzzy": 1, "position-only": 2}


# ---------------------------------------------------------------------------
# 1. The song catalog
# ---------------------------------------------------------------------------


def parse_length(text):
    """Seconds in a catalog Length like "2:36" or "1:02:03"; None if there isn't one."""
    try:
        parts = [int(p) for p in str(text).split(":")]
    except ValueError:
        return None
    if len(parts) < 2:
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def load_catalog():
    """Return {song number: (date, title, length in seconds or None)} from the
    songaday-display index chunks.

    Some chunks exist in two hashed versions; the newest file wins for each song.
    """
    files = sorted(glob.glob(str(CATALOG_DIR / "index-*.json")), key=os.path.getmtime)
    if not files:
        sys.exit(f"No index-*.json catalog chunks in {CATALOG_DIR} (set SONGADAY_CATALOG_DIR)")
    songs = {}
    for path in files:
        for song in json.loads(Path(path).read_text())["songs"]:
            length = parse_length((song.get("a") or {}).get("Length"))
            songs[song["n"]] = (dt.date.fromisoformat(song["d"]), song.get("t") or "", length)
    return dict(sorted(songs.items()))


def song_number(day):
    """Song A Day number of a calendar day (2009-01-01 is #1)."""
    return (day - FIRST_DAY).days + 1


# ---------------------------------------------------------------------------
# 2. Fetching, with a cache
# ---------------------------------------------------------------------------

_last_request = 0.0


def fetch_json(params, cache_path, offline, refresh=False):
    """GET the Lookup API with these params, caching the JSON at cache_path."""
    global _last_request
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text())
    if offline:
        sys.exit(f"{cache_path.relative_to(ROOT)} isn't cached and --offline was given")
    for attempt in range(6):
        wait = REQUEST_PAUSE - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        response = requests.get(LOOKUP_URL, params=params, timeout=30,
                                headers={"User-Agent": USER_AGENT})
        if response.status_code in (403, 429) or response.status_code >= 500:
            # Apple answers 403 or 429 when it wants us to slow down.
            backoff = 30 * (attempt + 1)
            print(f"  HTTP {response.status_code}, waiting {backoff} s", file=sys.stderr)
            time.sleep(backoff)
            continue
        response.raise_for_status()
        data = response.json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        return data
    sys.exit(f"Gave up on {params} after repeated errors")


def fetch_releases(offline, refresh):
    """Return the artist's releases, each with its tracks, sorted by release date."""
    listing = fetch_json(
        {"id": ARTIST_ID, "entity": "album", "limit": 200, "country": COUNTRY},
        CACHE_DIR / f"artist-{ARTIST_ID}-albums.json", offline, refresh)
    albums = [r for r in listing["results"] if r.get("wrapperType") == "collection"]
    if len(albums) >= 200:
        print("Warning: the album list hit the API's 200-result cap; some may be missing",
              file=sys.stderr)
    releases = []
    for number, album in enumerate(albums, 1):
        cache_path = ALBUM_CACHE / f"{album['collectionId']}.json"
        if not cache_path.exists() and not offline:
            print(f"  [{number}/{len(albums)}] {album['collectionName']}", file=sys.stderr)
        data = fetch_json(
            {"id": album["collectionId"], "entity": "song", "limit": 200, "country": COUNTRY},
            cache_path, offline)
        tracks = [r for r in data["results"]
                  if r.get("wrapperType") == "track" and r.get("kind") == "song"]
        # Album order: disc first, then track number.
        tracks.sort(key=lambda t: (t.get("discNumber") or 1, t.get("trackNumber") or 0))
        releases.append({
            "id": album["collectionId"],
            "name": album["collectionName"],
            "released": dt.date.fromisoformat(album["releaseDate"][:10]),
            "track_count": album.get("trackCount"),
            "tracks": tracks,
        })
    releases.sort(key=lambda r: (r["released"], r["name"]))
    return releases


def duration_diff(track, catalog, song):
    """Apple's track length minus the catalog's Length, in seconds; None if either is missing."""
    millis, length = track.get("trackTimeMillis"), catalog[song][2]
    if not millis or length is None:
        return None
    return millis / 1000 - length


def duration_ok(track, catalog, song):
    """False only when both lengths are known and clearly disagree (see DURATION_SHARE)."""
    diff = duration_diff(track, catalog, song)
    if diff is None:
        return True
    return abs(diff) <= max(DURATION_TOLERANCE, DURATION_SHARE * catalog[song][2])


def clean_url(url):
    """Drop tracking parameters (uo=4 and friends) but keep ?i=<track id>."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k == "i"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


# ---------------------------------------------------------------------------
# 3. Titles
# ---------------------------------------------------------------------------

# "(feat. X)" anywhere, and an unbracketed " feat. X" running to the end or the next bracket.
FEAT_RE = re.compile(r"[\(\[]\s*(feat|ft|featuring|with)\b[^\)\]]*[\)\]]"
                     r"|\s(feat\.?|ft\.|featuring)\s[^\(\[]*", re.I)
BRACKETS_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")
STOPWORDS = {"the", "and", "song", "remix", "version", "with", "that", "this", "your",
             "from", "have", "what", "feat", "featuring", "redux", "again", "theme"}


def normalize(title):
    """Lowercase words: accents, apostrophes, punctuation and "(feat. X)" go.

    Letters of any script survive (Hebrew and Yiddish titles), and so do asterisks inside
    words, because Apple censors some titles ("F**k ICE") and censored_equal() needs them.
    """
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = FEAT_RE.sub(" ", text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"['‘’`]", "", text)  # don't -> dont
    # Split into words of letters, digits and asterisks; stars only count inside a word.
    words = [w.strip("*") for w in re.split(r"[^\w*]+", text.replace("_", " "))]
    return " ".join(w for w in words if w)


def title_forms(title):
    """Precomputed forms of a title, for title_similarity():
    (normalized, normalized without bracketed asides, and the two as sorted word sets)."""
    full = normalize(title)
    bare = normalize(BRACKETS_RE.sub(" ", title)) or full
    return (full, bare, " ".join(sorted(set(full.split()))), " ".join(sorted(set(bare.split()))))


def content_words(forms):
    """Distinctive words of a title (four letters or more, not filler), for date matches."""
    return {w for w in forms[0].split() if len(w) >= 4 and w not in STOPWORDS}


def censored_equal(a, b):
    """True when one title is the other with letters starred out ("f**k" vs "fuck")."""
    for censored, plain in ((a, b), (b, a)):
        if "*" in censored and len(censored) == len(plain):
            pattern = "".join(r"\S" if c == "*" else re.escape(c) for c in censored)
            if re.fullmatch(pattern, plain):
                return True
    return False


def _ratio(a, b, floor):
    """difflib's similarity ratio, or 0 when cheap upper bounds show it is below floor."""
    matcher = difflib.SequenceMatcher(None, a, b)
    if matcher.real_quick_ratio() < floor or matcher.quick_ratio() < floor:
        return 0.0
    return matcher.ratio()


def title_similarity(forms_a, forms_b, floor=0.0):
    """Similarity of two titles from 0 to 1 (1.0 only when the normalized titles agree).

    Scores below floor may come back as 0; callers that only care about strong matches
    pass a floor so most pairs are rejected without a full comparison.
    """
    full_a, bare_a, sorted_a, sorted_bare_a = forms_a
    full_b, bare_b, sorted_b, sorted_bare_b = forms_b
    if not full_a or not full_b:
        return 0.0
    if full_a == full_b:
        return 1.0
    if censored_equal(full_a, full_b):
        return 0.97  # the same title, starred out on Apple Music
    if bare_a == bare_b or censored_equal(bare_a, bare_b):
        return 0.95  # same title once an aside like "(Live)" or "(Oh No!)" is dropped
    best = 0.0
    # One title inside the other ("Baby Yoda" in "Baby Yoda Baby Baby Yoda") is a decent sign.
    shorter, longer = sorted((bare_a, bare_b), key=len)
    if len(shorter) >= 8 and re.search(rf"(?<!\w){re.escape(shorter)}(?!\w)", longer):
        best = 0.86
    best = max(best, _ratio(full_a, full_b, max(floor, best)))
    if bare_a != full_a or bare_b != full_b:
        best = max(best, _ratio(bare_a, bare_b, max(floor, best)))
    # Word order and repeated words shouldn't matter much either.
    for (a, b), (sa, sb) in (((full_a, full_b), (sorted_a, sorted_b)),
                             ((bare_a, bare_b), (sorted_bare_a, sorted_bare_b))):
        if sa != a or sb != b:
            best = max(best, _ratio(sa, sb, max(floor, best) + 0.05) - 0.05)
    return min(best, 0.94)


# ---------------------------------------------------------------------------
# 4. Matching
# ---------------------------------------------------------------------------


def period_range(name):
    """(first day, last day) for "Winter, 2009" or "September, 2026"; None otherwise."""
    match = PERIOD_RE.match(name)
    if not match:
        return None
    label, year = match.group(1), int(match.group(2))
    if label in SEASON_MONTHS:
        first_month, months = SEASON_MONTHS[label], 3
    else:
        first_month, months = MONTHS.index(label) + 1, 1
    first = dt.date(year, first_month, 1)
    after_month = first_month + months
    after = dt.date(year + (after_month - 1) // 12, (after_month - 1) % 12 + 1, 1)
    return first, after - dt.timedelta(days=1)


def align_period_album(release, catalog, forms, title_index):
    """Pair a period album's tracks with songs. Returns {track index: (song, kind, score)}."""
    first, last = period_range(release["name"])
    first_song = song_number(first)
    nominal_last = song_number(last)
    low = max(1, first_song - MARGIN_DAYS)
    high = min(max(catalog), nominal_last + MARGIN_DAYS)
    candidates = [n for n in range(low, high + 1) if n in catalog]
    tracks = release["tracks"]
    track_forms = [title_forms(t["trackName"]) for t in tracks]
    m, n = len(tracks), len(candidates)

    # Similarity of every track to every candidate song.
    sim = [[title_similarity(track_forms[i], forms[candidates[j]], ALIGN_MIN)
            for j in range(n)] for i in range(m)]

    # Weighted longest-common-subsequence: pick an in-order set of (track, song) pairs with
    # the largest total similarity. A tiny penalty for straying from the nominal position
    # breaks ties between songs that share a title.
    def weight(i, j):
        if sim[i][j] < ALIGN_MIN:
            return None
        return sim[i][j] - 0.0005 * abs((candidates[j] - first_song) - i)

    best = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            score = max(best[i - 1][j], best[i][j - 1])
            w = weight(i - 1, j - 1)
            if w is not None:
                score = max(score, best[i - 1][j - 1] + w)
            best[i][j] = score
    pairs = {}
    i, j = m, n
    while i > 0 and j > 0:
        w = weight(i - 1, j - 1)
        if w is not None and abs(best[i][j] - (best[i - 1][j - 1] + w)) < 1e-9:
            pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif best[i][j] == best[i - 1][j]:
            i -= 1
        else:
            j -= 1

    # Weak title pairs only count if a neighbouring pair agrees on the day offset.
    def offset(i):
        return candidates[pairs[i]] - i

    for i in sorted(pairs):
        if sim[i][pairs[i]] >= LOOSE_CHECK:
            continue
        neighbours = [k for k in sorted(pairs) if k != i and sim[k][pairs[k]] >= LOOSE_CHECK]
        before = [k for k in neighbours if k < i][-1:]
        after = [k for k in neighbours if k > i][:1]
        if (not any(offset(k) == offset(i) for k in before + after)
                or not duration_ok(tracks[i], catalog, candidates[pairs[i]])):
            del pairs[i]

    result = {}
    for i, j in pairs.items():
        kind = "exact" if sim[i][j] == 1.0 else "fuzzy"
        result[i] = (candidates[j], kind, sim[i][j])
    anchors = sorted(result)  # the in-order pairs; position-only filling leans on these
    taken = {song for song, _, _ in result.values()}

    # Second pass: strong title matches the in-order alignment had to skip, such as two
    # swapped tracks ("May, 2019" tracks 27 and 28) or a song filed on the next month's album.
    for i in range(m):
        if i in result:
            continue
        options = [(sim[i][j], -abs((candidates[j] - first_song) - i), j) for j in range(n)
                   if sim[i][j] >= SINGLE_MIN and candidates[j] not in taken]
        if options:
            score, _, j = max(options)
            result[i] = (candidates[j], "exact" if score == 1.0 else "fuzzy", score)
            taken.add(candidates[j])

    # A title that names exactly one song in the whole catalog, whatever its date: "Fall,
    # 2010" also carries the 2012 song "Bury Me Beneath the Ocean (Redux)", and "Summer,
    # 2014" has the 2009 "The Robots Don't Love You Anymore" in place of a supercut.
    for i in range(m):
        if i in result or len(track_forms[i][0]) < UNIQUE_TITLE_MIN:
            continue
        hits = title_index.get(track_forms[i][0], [])
        if len(hits) == 1 and hits[0] not in taken:
            result[i] = (hits[0], "exact", 1.0)
            taken.add(hits[0])

    # Position-only: fill unmatched tracks between (or beyond) anchors whose offsets agree,
    # as long as the track's length doesn't contradict the song's.
    nominal_offset = first_song  # song = first_song + track index when nothing is off
    for i in range(m):
        if i in result:
            continue
        before = [k for k in anchors if k < i][-1:]
        after = [k for k in anchors if k > i][:1]
        offsets = {result[k][0] - k for k in before + after}
        if not anchors or len(offsets) != 1:
            continue
        guess = offsets.pop()
        if not (before and after) and guess != nominal_offset:
            continue  # edge tracks are only filled when the album starts on its first day
        song = guess + i
        if (song in catalog and song not in taken and first_song <= song <= nominal_last
                and duration_ok(tracks[i], catalog, song)):
            result[i] = (song, "position-only", title_similarity(track_forms[i], forms[song]))
            taken.add(song)

    return result


def match_loose_release(release, catalog, forms, single=False, cluster_only=False):
    """Match a single, EP or compilation by title. Returns {track index: (song, kind, score)}.

    Every track needs a strong title match (SINGLE_MIN), and the best title wins, then a
    song whose length fits the track, then one written before the release, then the song
    closest in time to the release.
    single: singles usually come out within days of the song, often under a different
    title ("The Wind of God" is the song "Kenneth Copeland On COVID-19 (Wind of God chill
    remix)"), so a song from the week before the release (or the day after) also counts
    when the titles are roughly alike or share a distinctive word, and it ranks first.
    cluster_only: for albums that aren't Song A Day; a match only counts when at least
    two other tracks of the album match songs within CLUSTER_DAYS of it.
    """
    result = {}
    for i, track in enumerate(release["tracks"]):
        tf = title_forms(track["trackName"])
        words = content_words(tf)
        scored = []
        for n, (day, _, _) in catalog.items():
            days_after = (release["released"] - day).days  # how long after the song it came out
            near = single and -1 <= days_after <= 7
            score = title_similarity(tf, forms[n], 0.0 if near else SINGLE_MIN)
            if near and (score >= 0.5 or words & content_words(forms[n])):
                rank = score + 0.3
            elif score >= SINGLE_MIN:
                rank = score
            else:
                continue
            # Best title first; then a song whose length fits, a song written before the
            # release, and the song closest in time to the release.
            fits = duration_ok(track, catalog, n) and duration_diff(track, catalog, n) is not None
            scored.append((-rank, not fits, days_after < -7, abs(days_after), n, score))
        if scored:
            *_, n, score = min(scored)
            result[i] = (n, "exact" if score == 1.0 else "fuzzy", score)
    if cluster_only:
        # Keep a match only if two or more other matches from this album sit close by.
        days = {i: catalog[n][0] for i, (n, _, _) in result.items()}
        kept = {}
        for i, value in result.items():
            close = sum(abs((days[k] - days[i]).days) <= CLUSTER_DAYS for k in days if k != i)
            if close >= 2:
                kept[i] = value
        result = kept
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    parser.add_argument("--refresh", action="store_true",
                        help="fetch the artist's album list again (new releases)")
    args = parser.parse_args()

    catalog = load_catalog()
    forms = {n: title_forms(title) for n, (_, title, _) in catalog.items()}
    title_index = {}  # normalized title -> song numbers with that title
    for n, f in forms.items():
        title_index.setdefault(f[0], []).append(n)
    releases = fetch_releases(args.offline, args.refresh)

    # Every (song, track) pairing found, with what kind of release it came from.
    found = []  # (song, release kind, match kind, score, release, track, in date range)
    unmatched = []
    for release in releases:
        if period_range(release["name"]):
            kind = "period"
            matches = align_period_album(release, catalog, forms, title_index)
        elif release["name"] in NOT_SONG_A_DAY:
            kind = "other"
            matches = match_loose_release(release, catalog, forms, cluster_only=True)
        else:
            kind = "single" if len(release["tracks"]) == 1 else "ep"
            matches = match_loose_release(release, catalog, forms, single=kind == "single")
        for i, track in enumerate(release["tracks"]):
            if i in matches:
                song, match_kind, score = matches[i]
                span = period_range(release["name"])
                in_range = bool(span) and span[0] <= catalog[song][0] <= span[1]
                found.append((song, kind, match_kind, score, release, track, in_range))
            elif kind != "other":
                unmatched.append((release, track))

    # Pick one primary track per song: period albums first, then the album whose dates
    # contain the song, then the better title match, then the earlier release.
    release_rank = {"period": 0, "ep": 1, "single": 2, "other": 3}
    by_song = {}
    for item in found:
        by_song.setdefault(item[0], []).append(item)
    rows = []
    for n in catalog:
        options = sorted(by_song.get(n, []),
                         key=lambda x: (release_rank[x[1]], not x[6], MATCH_RANK[x[2]],
                                        -x[3], x[4]["released"]))
        if not options:
            rows.append({"number": n, "match": "none"})
            continue
        _, _, match_kind, score, release, track, _ = options[0]
        diff = duration_diff(track, catalog, n)
        others = [f"{o[4]['name']}: {clean_url(o[5]['trackViewUrl'])}" for o in options[1:]]
        rows.append({
            "number": n,
            "apple_music_url": clean_url(track["trackViewUrl"]),
            "apple_track_id": track["trackId"],
            "apple_album": release["name"],
            "track_number": track.get("trackNumber"),
            "apple_title": track["trackName"],
            "match": match_kind,
            "match_score": f"{score:.3f}",
            "duration_diff_s": "" if diff is None else f"{diff:.1f}",
            "other_releases": " | ".join(others),
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    with UNMATCHED_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["album", "released", "disc", "track", "title", "url"])
        for release, track in unmatched:
            writer.writerow([release["name"], release["released"], track.get("discNumber"),
                             track.get("trackNumber"), track["trackName"],
                             clean_url(track["trackViewUrl"])])

    write_duration_checks(rows, catalog, found)
    report(rows, catalog, releases, found, unmatched)


def write_duration_checks(rows, catalog, found):
    """List linked songs whose Apple track is far longer or shorter than the catalog Length.

    Most are the same song in a different edit, or a wrong Length in the sheet. When the
    track's length fits the previous or next song instead, Apple's titles may be shifted
    against the audio ("Summer, 2009" tracks 84-86), which is worth a listen.
    """
    tracks = {str(item[5]["trackId"]): item[5] for item in found}
    with DURATION_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["number", "title", "catalog_length_s", "apple_length_s", "apple_album",
                         "track_number", "apple_title", "fits_neighbour"])
        for row in rows:
            n, diff = row["number"], row.get("duration_diff_s")
            if not diff or abs(float(diff)) <= max(30, 0.3 * catalog[n][2]):
                continue
            seconds = tracks[str(row["apple_track_id"])]["trackTimeMillis"] / 1000
            fits = [str(k) for k in (n - 1, n + 1)
                    if k in catalog and catalog[k][2] is not None and abs(catalog[k][2] - seconds) <= 2]
            writer.writerow([n, catalog[n][1], catalog[n][2], f"{seconds:.0f}", row["apple_album"],
                             row["track_number"], row["apple_title"], " ".join(f"#{k}" for k in fits)])


def report(rows, catalog, releases, found, unmatched):
    """Print coverage by year and by match kind."""
    total_tracks = sum(len(r["tracks"]) for r in releases)
    print(f"{len(releases)} releases, {total_tracks} tracks; "
          f"{len(found)} track-song pairs, {len(unmatched)} Song A Day tracks unmatched")
    counts = {}
    for row in rows:
        counts[row["match"]] = counts.get(row["match"], 0) + 1
    linked = len(rows) - counts.get("none", 0)
    print(f"{linked} of {len(rows)} songs linked ({linked / len(rows):.1%}): "
          + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print("year  songs  linked  missing")
    by_year = {}
    for row in rows:
        year = catalog[row["number"]][0].year
        stats = by_year.setdefault(year, [0, 0])
        stats[0] += 1
        stats[1] += row["match"] != "none"
    for year, (songs, linked) in sorted(by_year.items()):
        print(f"{year}  {songs:5d}  {linked:6d}  {songs - linked:7d}")
    multi = sum(1 for row in rows if row.get("other_releases"))
    print(f"{multi} songs are on more than one release (see other_releases)")
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}; checks in {UNMATCHED_CSV.relative_to(ROOT)} "
          f"and {DURATION_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
