"""Spotify links for each Song A Day song.

Source: the Spotify Web API, read-only, with an app's own Client Credentials (no user login).
  0. POST https://accounts.spotify.com/api/token (grant_type=client_credentials) trades the
     app's client ID and secret for a one-hour access token. It changes nothing on Spotify;
     it is the only non-GET request, and the token is never printed or cached.
  1. GET /v1/artists/4O4Rkb6K3ppeXyVvD6zBJA/albums?include_groups=album,single&market=US
     lists every album, EP and single by the artist Spotify calls "Song a Day" (Jonathan's
     own profile: Baby Yoda, Babu Frik, HASAN PIKER THIRST TRAP...). Features on other
     people's releases ("appears_on") are left out.
  2. GET /v1/albums/{id}/tracks?market=US lists each release's tracks (name, track_number,
     disc_number, duration_ms, id). Both lists are paged; the "next" links are followed.
The batch endpoint GET /v1/albums?ids= isn't needed: the album list already carries each
release date (and Spotify has been withdrawing batch endpoints from Development Mode apps).
If Spotify refuses PAGE_LIMIT items per page for this app, the script drops to
SMALL_PAGE_LIMIT and carries on.
Raw responses are cached in cache/spotify/ (artist-<id>-albums.json and
albums/<album id>.json), so a rerun makes no requests. Spotify's API doesn't give play
counts for an artist's tracks, so there are none here.

How a track becomes a song number. This is the same method, thresholds and tie-breaks as
sources/apple_music.py, and the title functions below are copied from it so both tables
agree; change them in both places. Apple's catalog shows the release pattern: seasonal
albums "Winter, 2009" to "Summer, 2017" (Winter = January-March, Spring = April-June,
Summer = July-September, Fall = October-December), then one album per month from
"October, 2017" on, plus singles and a few EPs.
- Period albums cover a known stretch of days, so track k should be the song written on
  day k of that stretch. Each album's tracks are aligned, in order, against the catalog
  songs of that stretch (plus MARGIN_DAYS either side) by title similarity, the way a diff
  lines up two lists. A track whose title matches is "exact" (same normalized title) or
  "fuzzy" (close enough). A track whose title doesn't match, but which sits between two
  matched tracks with the same day offset (or before or after a run that starts on the
  album's first day), takes its song by position: "position-only".
- Singles, EPs and other albums have no date range, so each track is matched by title
  against the whole catalog, keeping the song closest to (and preferably before) the
  release date. Only strong title matches count (SINGLE_MIN).
- When a song is on more than one release (an album track plus a single, say), the period
  album track is the primary link and the others go in other_releases.
Spotify writes versions as a dash suffix ("Song - Remastered 2020", "Song - Remix") where
Apple uses brackets ("Song [Remix]"); such a suffix is turned into a bracketed aside before
the titles are compared, so it is treated exactly like Apple's.

Output: dataset/spotify.csv, one row per song in the catalog (#1 to the last song):
  number, spotify_url (https://open.spotify.com/track/<id>), spotify_track_id,
  spotify_album (the release's name on Spotify), track_number, spotify_title (as written on
  Spotify), match (exact | fuzzy | position-only | none), match_score (title similarity,
  0 to 1, three decimals; blank when match is none), other_releases (any other releases of
  the same song, "album: url | album: url", like apple_music.csv)
Tracks that couldn't be tied to any song go to cache/spotify/unmatched-tracks.csv.

Credentials: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in this repo's .env (see
.env.example) or the environment. Without them the script says how to get them and exits 0
without writing anything. --offline needs no credentials once the cache is filled.

Run:  .venv/bin/python sources/spotify.py             (fetches only what isn't cached)
      .venv/bin/python sources/spotify.py --offline   (cache only, no network)
      .venv/bin/python sources/spotify.py --refresh   (fetch the album list again, to pick
                                                       up new releases)
      .venv/bin/python sources/spotify.py --selftest  (checks the title matcher; no network,
                                                       no credentials, no catalog needed)

Paths, all optional:
  SONGADAY_CATALOG_DIR  songaday-display publish/meta folder (index-*.json chunks)
                        default ~/Library/Caches/songaday-display/publish/meta
                        Without it, dataset/songs.csv is used for the titles.
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

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "spotify"
ALBUM_CACHE = CACHE_DIR / "albums"
OUT_CSV = ROOT / "dataset" / "spotify.csv"
UNMATCHED_CSV = CACHE_DIR / "unmatched-tracks.csv"
SONGS_CSV = ROOT / "dataset" / "songs.csv"

CATALOG_DIR = Path(
    os.environ.get("SONGADAY_CATALOG_DIR")
    or Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta"
)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
ARTIST_ID = "4O4Rkb6K3ppeXyVvD6zBJA"  # "Song a Day" on Spotify
MARKET = "US"  # same storefront as apple_music.py; also stops regional duplicates
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
REQUEST_PAUSE = 0.5  # seconds between live requests; one request at a time
PAGE_LIMIT = 50  # items per page for both lists (Spotify's documented maximum)
SMALL_PAGE_LIMIT = 10  # used instead if Spotify says the limit is too big for this app
MAX_RETRY_AFTER = 900  # seconds; a longer Retry-After stops the run instead of sleeping

FIRST_DAY = dt.date(2009, 1, 1)  # song #1

# Releases by this artist that aren't Song A Day (same list as apple_music.py).
NOT_SONG_A_DAY = {"The Mario Opera: Act One", "Songonauts"}

# Title-matching thresholds (similarity runs from 0 to 1; see title_similarity). These are
# apple_music.py's values; keep them in step.
ALIGN_MIN = 0.60  # a period-album track and a song may be paired by title at this or above
LOOSE_CHECK = 0.75  # pairs below this must also sit at the same day offset as a neighbour
SINGLE_MIN = 0.85  # singles, EPs and compilations need at least this
MARGIN_DAYS = 10  # period albums may start or end a few days off their nominal range

SEASON_MONTHS = {"Winter": 1, "Spring": 4, "Summer": 7, "Fall": 10}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
# Matches the start of the name, so Apple's odd "July, 2023Driving, Driving..." still reads
# as July 2023. Case-insensitive here, in case Spotify's capitalization differs.
PERIOD_RE = re.compile(r"^(Winter|Spring|Summer|Fall|" + "|".join(MONTHS) + r"),? (\d{4})",
                       re.I)

COLUMNS = [
    "number",
    "spotify_url",
    "spotify_track_id",
    "spotify_album",
    "track_number",
    "spotify_title",
    "match",
    "match_score",
    "other_releases",
]
MATCH_RANK = {"exact": 0, "fuzzy": 1, "position-only": 2}
RELEASE_RANK = {"period": 0, "ep": 1, "single": 2, "other": 3}

HOW_TO_ADD_CREDENTIALS = """\
No Spotify credentials, so dataset/spotify.csv was not written.

To add them (free, about two minutes):
  1. Go to https://developer.spotify.com/dashboard, log in, and choose "Create app".
  2. Any name and description. Redirect URI: http://127.0.0.1:8888/callback
     (it isn't used; the form just needs one). Tick "Web API".
  3. Open the app's Settings and copy the Client ID and the Client secret.
  4. Put them in this repo's .env (it is ignored by Git; see .env.example):
       SPOTIFY_CLIENT_ID=...
       SPOTIFY_CLIENT_SECRET=...
  5. Run .venv/bin/python sources/spotify.py again.
"""


# ---------------------------------------------------------------------------
# 0. Small helpers
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
    """Write JSON atomically (a half-written cache file would poison later runs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(path)


def song_number(day):
    """Song A Day number of a calendar day (2009-01-01 is #1)."""
    return (day - FIRST_DAY).days + 1


def release_day(album):
    """A Spotify release_date ("2019-11-18", "2019-11" or "2019") as a date."""
    text = album.get("release_date") or "1900"
    parts = [int(p) for p in text.split("-")] + [1, 1]
    return dt.date(parts[0], parts[1], parts[2])


# ---------------------------------------------------------------------------
# 1. The song catalog
# ---------------------------------------------------------------------------


def load_catalog():
    """Return {song number: (date, title)}.

    From the songaday-display index chunks (some exist in two hashed versions; the newest
    file wins for each song), or else from dataset/songs.csv.
    """
    files = sorted(glob.glob(str(CATALOG_DIR / "index-*.json")), key=os.path.getmtime)
    songs = {}
    for path in files:
        for song in json.loads(Path(path).read_text())["songs"]:
            songs[song["n"]] = (dt.date.fromisoformat(song["d"]), song.get("t") or "")
    if not songs and SONGS_CSV.exists():
        with SONGS_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                songs[int(row["number"])] = (dt.date.fromisoformat(row["date"]), row["title"])
    if not songs:
        sys.exit(f"No index-*.json catalog chunks in {CATALOG_DIR} (set SONGADAY_CATALOG_DIR) "
                 f"and no {SONGS_CSV.relative_to(ROOT)}")
    return dict(sorted(songs.items()))


# ---------------------------------------------------------------------------
# 2. Talking to Spotify
# ---------------------------------------------------------------------------


class SpotifyError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class Spotify:
    """A tiny Web API client: Client Credentials token, one request at a time, a pause
    between requests, Retry-After on 429, backoff on 5xx and network errors."""

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.token = None
        self.token_expires = 0.0
        self.last_request = 0.0
        self.page_limit = PAGE_LIMIT  # drops to SMALL_PAGE_LIMIT once if Spotify asks

    def _pause(self):
        wait = REQUEST_PAUSE - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()

    def _fetch_token(self):
        self._pause()
        response = self.session.post(
            TOKEN_URL, data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret), timeout=30)
        if response.status_code != 200:
            # The body is e.g. {"error": "invalid_client", ...}; it never echoes the secret.
            raise SpotifyError(
                f"Spotify refused the client ID/secret (HTTP {response.status_code}: "
                f"{response.text[:200]}). Check SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET "
                "in .env.", response.status_code)
        data = response.json()
        self.token = data["access_token"]
        # Renew a minute early rather than have a request fail halfway through a page.
        self.token_expires = time.monotonic() + int(data.get("expires_in", 3600)) - 60

    def get(self, url, params=None, attempts=8):
        """GET an API URL (absolute, e.g. a page's "next" link) and return its JSON."""
        renewed = False
        for attempt in range(attempts):
            if not self.token or time.monotonic() > self.token_expires:
                self._fetch_token()
            self._pause()
            try:
                response = self.session.get(
                    url, params=params, timeout=30,
                    headers={"Authorization": f"Bearer {self.token}"})
            except requests.RequestException as error:
                wait = 2**attempt
                print(f"  network error ({error.__class__.__name__}), retrying in {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code == 401 and not renewed:
                self.token = None  # expired or revoked token: get a new one, once
                renewed = True
                continue
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After") or 2**attempt)
                if wait > MAX_RETRY_AFTER:
                    raise SpotifyError(
                        f"Spotify asked us to wait {wait} s (rate limit). What was fetched "
                        "so far is cached; run again later.", 429)
                print(f"  HTTP 429, waiting {wait + 1}s as Spotify asks", file=sys.stderr)
                time.sleep(wait + 1)
                continue
            if response.status_code >= 500:
                wait = 2**attempt
                print(f"  HTTP {response.status_code}, retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            try:
                message = response.json().get("error", {}).get("message", "")
            except ValueError:
                message = response.text[:200]
            hint = ""
            if response.status_code == 403:
                hint = (" Spotify limits Development Mode apps; check the app's dashboard "
                        "page (the account that owns the app may need Premium).")
            raise SpotifyError(f"HTTP {response.status_code} for {url}: {message}.{hint}",
                               response.status_code)
        raise SpotifyError(f"gave up on {url} after {attempts} attempts")


def get_all_items(client, url, params):
    """Every item of a paged list, following the "next" links. If Spotify says the page
    size is too big for this app, start again with SMALL_PAGE_LIMIT (and keep using it)."""
    while True:
        try:
            items = []
            page = client.get(url, {**params, "limit": client.page_limit})
            while True:
                items.extend(page.get("items") or [])
                if not page.get("next"):
                    return items
                page = client.get(page["next"])  # the link already carries the query
        except SpotifyError as error:
            too_big = error.status == 400 and "limit" in str(error).lower()
            if too_big and client.page_limit > SMALL_PAGE_LIMIT:
                print(f"  Spotify won't take limit={client.page_limit}; using "
                      f"{SMALL_PAGE_LIMIT}", file=sys.stderr)
                client.page_limit = SMALL_PAGE_LIMIT
                continue
            raise


def fetch_releases(client, offline, refresh):
    """Return the artist's releases, each with its tracks in album order, oldest first.

    client is None when running offline. The album list is fetched again only with
    --refresh; a release's tracks are fetched when they aren't cached, or when the cached
    count no longer matches the album's total_tracks.
    """
    list_path = CACHE_DIR / f"artist-{ARTIST_ID}-albums.json"
    if list_path.exists() and not refresh:
        albums = json.loads(list_path.read_text())["albums"]
    elif offline:
        sys.exit(f"{list_path.relative_to(ROOT)} isn't cached and --offline was given")
    else:
        print("Listing the artist's albums and singles...", file=sys.stderr)
        albums = get_all_items(client, f"{API}/artists/{ARTIST_ID}/albums",
                               {"include_groups": "album,single", "market": MARKET})
        write_json(list_path, {"fetched_at": dt.date.today().isoformat(),
                               "artist_id": ARTIST_ID, "market": MARKET, "albums": albums})

    # The same release can be listed twice (a re-upload, or a regional copy); keep the
    # first of each name + date + track count.
    seen, unique = set(), []
    for album in albums:
        key = (album["name"].strip().lower(), album.get("release_date"), album.get("total_tracks"))
        if key in seen:
            print(f"  skipping a duplicate listing of {album['name']!r} ({album['id']})",
                  file=sys.stderr)
            continue
        seen.add(key)
        unique.append(album)

    releases = []
    for number, album in enumerate(unique, 1):
        path = ALBUM_CACHE / f"{album['id']}.json"
        cached = json.loads(path.read_text()) if path.exists() else None
        stale = cached is not None and len(cached["tracks"]) != album.get("total_tracks")
        if cached is None or (stale and not offline):
            if offline:
                sys.exit(f"{path.relative_to(ROOT)} isn't cached and --offline was given")
            print(f"  [{number}/{len(unique)}] {album['name']}", file=sys.stderr)
            items = get_all_items(client, f"{API}/albums/{album['id']}/tracks",
                                  {"market": MARKET})
            cached = {"fetched_at": dt.date.today().isoformat(), "album_id": album["id"],
                      "name": album["name"], "tracks": items}
            write_json(path, cached)
        tracks = [
            {
                "id": t["id"],
                "title": spotify_title_for_matching(t.get("name") or ""),
                "name": t.get("name") or "",
                "track_number": t.get("track_number"),
                "disc_number": t.get("disc_number") or 1,
            }
            for t in cached["tracks"]
            if t.get("id") and not t.get("is_local")
        ]
        # Album order: disc first, then track number.
        tracks.sort(key=lambda t: (t["disc_number"], t["track_number"] or 0))
        releases.append({
            "id": album["id"],
            "name": album["name"],
            "released": release_day(album),
            "track_count": album.get("total_tracks"),
            "tracks": tracks,
        })
    releases.sort(key=lambda r: (r["released"], r["name"]))
    return releases


def track_url(track_id):
    return f"https://open.spotify.com/track/{track_id}"


# ---------------------------------------------------------------------------
# 3. Titles (copied from apple_music.py, plus spotify_title_for_matching)
# ---------------------------------------------------------------------------

FEAT_RE = re.compile(r"[\(\[]\s*(feat|ft|featuring|with)\b[^\)\]]*[\)\]]", re.I)
BRACKETS_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")
# A trailing " - Remastered 2011", " - Live", " - Single Version", " - feat. X"...
DASH_SUFFIX_RE = re.compile(
    r"\s+[-–—]\s+((?:[^-–—]*\b)?(?:remaster(?:ed)?|remix|mix|live|version|edit|demo|acoustic|"
    r"instrumental|mono|stereo|feat\.?|ft\.|featuring)\b[^-–—]*)$", re.I)


def spotify_title_for_matching(name):
    """Turn Spotify's dash-suffix versions into the bracketed asides Apple uses, so
    "Baby Yoda Baby Baby Yoda - Remix" compares like "... [Remix]". Other dashes stay."""
    return DASH_SUFFIX_RE.sub(lambda m: f" ({m.group(1)})", name).strip()


def normalize(title):
    """Lowercase ASCII words only: accents, apostrophes, punctuation and "(feat. X)" go."""
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = FEAT_RE.sub(" ", text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"['‘’`]", "", text)  # don't -> dont
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def title_forms(title):
    """The normalized title, and the same with every bracketed aside removed."""
    full = normalize(title)
    bare = normalize(BRACKETS_RE.sub(" ", title)) or full
    return full, bare


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
    full_a, bare_a = forms_a
    full_b, bare_b = forms_b
    if not full_a or not full_b:
        return 0.0
    if full_a == full_b:
        return 1.0
    if bare_a == bare_b:
        return 0.95  # same title once an aside like "(Live)" or "(Oh No!)" is dropped
    best = 0.0
    # One title inside the other ("Baby Yoda" in "Baby Yoda Baby Baby Yoda") is a decent sign.
    shorter, longer = sorted((bare_a, bare_b), key=len)
    if len(shorter) >= 8 and re.search(rf"\b{re.escape(shorter)}\b", longer):
        best = 0.86
    for a, b in ((full_a, full_b), (bare_a, bare_b)):
        best = max(best, _ratio(a, b, max(floor, best)))
        # Word order and repeated words shouldn't matter much either.
        sorted_a, sorted_b = " ".join(sorted(set(a.split()))), " ".join(sorted(set(b.split())))
        if sorted_a != a or sorted_b != b:
            best = max(best, _ratio(sorted_a, sorted_b, max(floor, best) + 0.05) - 0.05)
    return min(best, 0.94)


# ---------------------------------------------------------------------------
# 4. Matching (the same steps as apple_music.py; tracks carry "title" here)
# ---------------------------------------------------------------------------


def period_range(name):
    """(first day, last day) for "Winter, 2009" or "September, 2026"; None otherwise."""
    match = PERIOD_RE.match(name.strip())
    if not match:
        return None
    label, year = match.group(1).title(), int(match.group(2))
    if label in SEASON_MONTHS:
        first_month, months = SEASON_MONTHS[label], 3
    else:
        first_month, months = MONTHS.index(label) + 1, 1
    first = dt.date(year, first_month, 1)
    after_month = first_month + months
    after = dt.date(year + (after_month - 1) // 12, (after_month - 1) % 12 + 1, 1)
    return first, after - dt.timedelta(days=1)


def align_period_album(release, catalog, forms):
    """Pair a period album's tracks with songs. Returns {track index: (song, kind, score)}."""
    first, last = period_range(release["name"])
    first_song = song_number(first)
    nominal_last = song_number(last)
    low = max(1, first_song - MARGIN_DAYS)
    high = min(max(catalog), nominal_last + MARGIN_DAYS)
    candidates = [n for n in range(low, high + 1) if n in catalog]
    tracks = release["tracks"]
    track_forms = [title_forms(t["title"]) for t in tracks]
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
        if not any(offset(k) == offset(i) for k in before + after):
            del pairs[i]

    result = {}
    for i, j in pairs.items():
        kind = "exact" if sim[i][j] == 1.0 else "fuzzy"
        result[i] = (candidates[j], kind, sim[i][j])

    # Position-only: fill unmatched tracks between (or beyond) anchors whose offsets agree.
    taken = {song for song, _, _ in result.values()}
    anchors = sorted(result)
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
        if song in catalog and song not in taken and first_song <= song <= nominal_last:
            result[i] = (song, "position-only", title_similarity(track_forms[i], forms[song]))
            taken.add(song)
    return result


def match_loose_release(release, catalog, forms, exact_only=False):
    """Match a single, EP or compilation by title. Returns {track index: (song, kind, score)}."""
    result = {}
    for i, track in enumerate(release["tracks"]):
        tf = title_forms(track["title"])
        scored = []
        for n, (day, _) in catalog.items():
            floor = 1.0 if exact_only else SINGLE_MIN
            score = title_similarity(tf, forms[n], floor)
            if score >= floor:
                # Prefer the best title, then songs written before the release, then the
                # one closest in time to the release.
                days_after = (release["released"] - day).days
                scored.append((-score, days_after < -7, abs(days_after), n))
        if scored:
            score, _, _, n = min(scored)
            result[i] = (n, "exact" if -score == 1.0 else "fuzzy", -score)
    return result


def release_kind(release):
    """period, other (not Song A Day), single (one track) or ep (anything else)."""
    if period_range(release["name"]):
        return "period"
    if release["name"] in NOT_SONG_A_DAY:
        return "other"
    return "single" if len(release["tracks"]) == 1 else "ep"


def match_all(releases, catalog):
    """Return (rows for the CSV, every pairing found, unmatched (release, track) pairs)."""
    forms = {n: title_forms(title) for n, (_, title) in catalog.items()}
    found = []  # (song, release kind, match kind, score, release, track)
    unmatched = []
    for release in releases:
        kind = release_kind(release)
        if kind == "period":
            matches = align_period_album(release, catalog, forms)
        else:
            matches = match_loose_release(release, catalog, forms, exact_only=kind == "other")
        for i, track in enumerate(release["tracks"]):
            if i in matches:
                song, match_kind, score = matches[i]
                found.append((song, kind, match_kind, score, release, track))
            elif kind != "other":
                unmatched.append((release, track))

    # Pick one primary track per song: period albums first, then the better title match.
    by_song = {}
    for item in found:
        by_song.setdefault(item[0], []).append(item)
    rows = []
    for n in catalog:
        options = sorted(by_song.get(n, []),
                         key=lambda x: (RELEASE_RANK[x[1]], MATCH_RANK[x[2]], -x[3],
                                        x[4]["released"]))
        if not options:
            rows.append({"number": n, "match": "none"})
            continue
        _, _, match_kind, score, release, track = options[0]
        others = [f"{o[4]['name']}: {track_url(o[5]['id'])}" for o in options[1:]]
        rows.append({
            "number": n,
            "spotify_url": track_url(track["id"]),
            "spotify_track_id": track["id"],
            "spotify_album": release["name"],
            "track_number": track["track_number"],
            "spotify_title": track["name"],
            "match": match_kind,
            "match_score": f"{score:.3f}",
            "other_releases": " | ".join(others),
        })
    return rows, found, unmatched


# ---------------------------------------------------------------------------
# 5. Output
# ---------------------------------------------------------------------------


def write_outputs(rows, unmatched):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CSV.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(OUT_CSV)

    UNMATCHED_CSV.parent.mkdir(parents=True, exist_ok=True)
    with UNMATCHED_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["album", "released", "disc", "track", "title", "url"])
        for release, track in unmatched:
            writer.writerow([release["name"], release["released"], track["disc_number"],
                             track["track_number"], track["name"], track_url(track["id"])])


def report(rows, catalog, releases, found, unmatched):
    """Print coverage by year and by match kind."""
    total_tracks = sum(len(r["tracks"]) for r in releases)
    periods = sum(1 for r in releases if release_kind(r) == "period")
    print(f"{len(releases)} releases ({periods} period albums), {total_tracks} tracks; "
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
    print(f"Wrote {OUT_CSV.relative_to(ROOT)} and {UNMATCHED_CSV.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# 6. Self-test of the matcher (no network, no credentials, no catalog)
# ---------------------------------------------------------------------------


def selftest():
    """Run small, made-up cases through the title and album matchers."""
    checks = 0

    def check(got, want, what):
        nonlocal checks
        assert got == want, f"{what}: got {got!r}, want {want!r}"
        checks += 1

    # Normalizing: case, accents, curly apostrophes, "&", "(feat. ...)", punctuation.
    check(normalize("Don’t Stop (feat. Brittain Ashford)"), "dont stop", "feat + apostrophe")
    check(normalize("Rock & Roll!!"), "rock and roll", "ampersand")
    check(normalize("Café Olé"), "cafe ole", "accents")
    check(normalize("Hands (Oh No!)"), "hands oh no", "aside kept in the full form")
    check(title_forms("Hands (Oh No!)"), ("hands oh no", "hands"), "bare form drops asides")
    check(spotify_title_for_matching("Baby Yoda Baby Baby Yoda - Remix"),
          "Baby Yoda Baby Baby Yoda (Remix)", "Spotify dash version")
    check(spotify_title_for_matching("Song Title - Remastered 2020"),
          "Song Title (Remastered 2020)", "Spotify remaster suffix")
    check(spotify_title_for_matching("Hustle & Grind - feat. Lackhoney"),
          "Hustle & Grind (feat. Lackhoney)", "Spotify dash feat")
    check(spotify_title_for_matching("SpinTunes #10 - Sign Up Now!"),
          "SpinTunes #10 - Sign Up Now!", "ordinary dash is kept")

    # Similarity.
    def sim(a, b):
        return title_similarity(title_forms(a), title_forms(b))

    check(sim("Hustle & Grind (feat. Lackhoney, Domino)", "Hustle and Grind"), 1.0, "feat")
    check(sim("Loki Is Genderfluid", "Loki Is Genderfluid (Blame the Norse)"), 0.95, "aside")
    check(sim("Baby Yoda Baby Baby Yoda (Remix)", "Baby Yoda Baby Baby Yoda"), 0.95, "remix")
    check(sim("The Final Onee", "The Final One") >= ALIGN_MIN, True, "typo is close")
    check(sim("Cat Song", "Election Night") < ALIGN_MIN, True, "different songs are far")

    # Period names.
    d = dt.date
    check(period_range("Winter, 2009"), (d(2009, 1, 1), d(2009, 3, 31)), "winter")
    check(period_range("Fall, 2016"), (d(2016, 10, 1), d(2016, 12, 31)), "fall")
    check(period_range("October 2024"), (d(2024, 10, 1), d(2024, 10, 31)), "no comma")
    check(period_range("February, 2024"), (d(2024, 2, 1), d(2024, 2, 29)), "leap year")
    check(period_range("December, 2025"), (d(2025, 12, 1), d(2025, 12, 31)), "December")
    check(period_range("July, 2023Driving, Driving"), (d(2023, 7, 1), d(2023, 7, 31)), "glued")
    check(period_range("Baby Yoda"), None, "a single")
    check(release_day({"release_date": "2019-11"}), d(2019, 11, 1), "month precision")

    # A period album with a missing song (#3), a retitled track (#6), a typo (#8) and a
    # Spotify-style version suffix (#9), then two singles.
    titles = ["In the Time of the Gods", "Hands (Oh No!)", "Who Do You Think You Are",
              "Cat Song", "Dog's Song", "Mystery Title", "Another One", "The Final One",
              "Ninth Song", "Tenth Song"]
    catalog = {n: (FIRST_DAY + dt.timedelta(days=n - 1), t) for n, t in enumerate(titles, 1)}

    def release(name, released, names):
        tracks = [{"id": f"{name[:4]}{k}", "name": t, "title": spotify_title_for_matching(t),
                   "track_number": k, "disc_number": 1} for k, t in enumerate(names, 1)]
        return {"id": name, "name": name, "released": released, "tracks": tracks}

    winter = release("Winter, 2009", d(2009, 1, 1), [
        "In The Time Of The Gods", "Hands", "Cat Song (feat. Someone)", "Dogs Song",
        "Something Completely Different", "Another One", "The Final Onee",
        "Ninth Song - Remastered 2020"])
    single = release("Who Do You Think You Are?", d(2009, 2, 1), ["Who Do You Think You Are?"])
    hands = release("Hands", d(2009, 1, 10), ["Hands"])
    stray = release("Totally Unrelated", d(2009, 3, 1), ["Totally Unrelated"])
    rows, found, unmatched = match_all([winter, single, hands, stray], catalog)
    by_number = {row["number"]: row for row in rows}
    want = {1: ("exact", 1), 2: ("fuzzy", 2), 3: ("exact", 1), 4: ("exact", 3),
            5: ("exact", 4), 6: ("position-only", 5), 7: ("exact", 6), 8: ("fuzzy", 7),
            9: ("fuzzy", 8), 10: ("none", None)}
    for n, (kind, track_number) in want.items():
        row = by_number[n]
        check((row["match"], row.get("track_number")), (kind, track_number), f"song #{n}")
    check(by_number[3]["spotify_album"], "Who Do You Think You Are?", "#3 from the single")
    check(by_number[2]["spotify_album"], "Winter, 2009", "period album beats the single")
    check(by_number[2]["other_releases"], "Hands: https://open.spotify.com/track/Hand1",
          "the single is listed as another release")
    check(by_number[6]["spotify_url"], "https://open.spotify.com/track/Wint5", "track URL")
    check([t["name"] for _, t in unmatched], ["Totally Unrelated"], "unmatched tracks")

    # A track two days off its nominal position still lands on its own title.
    shifted = release("Winter, 2009", d(2009, 1, 1), ["Cat Song", "Dog's Song"])
    result = align_period_album(shifted, catalog, {n: title_forms(t) for n, (_, t) in
                                                   catalog.items()})
    check(result, {0: (4, "exact", 1.0), 1: (5, "exact", 1.0)}, "shifted album")

    print(f"selftest: {checks} checks passed")


# ---------------------------------------------------------------------------
# 7. Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true",
                        help="use the cache only (no network, no credentials needed)")
    parser.add_argument("--refresh", action="store_true",
                        help="fetch the artist's album list again (new releases)")
    parser.add_argument("--selftest", action="store_true",
                        help="check the title matcher on made-up cases and exit")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    client = None
    if not args.offline:
        load_dotenv()
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            print(HOW_TO_ADD_CREDENTIALS)
            return  # exit 0: a missing optional source isn't an error
        client = Spotify(client_id, client_secret)

    catalog = load_catalog()
    try:
        releases = fetch_releases(client, args.offline, args.refresh)
    except SpotifyError as error:
        sys.exit(f"Spotify: {error}\nNothing was written; whatever was fetched is cached.")
    if not releases:
        sys.exit(f"Spotify listed no releases for artist {ARTIST_ID}; nothing was written.")

    rows, found, unmatched = match_all(releases, catalog)
    write_outputs(rows, unmatched)
    report(rows, catalog, releases, found, unmatched)


if __name__ == "__main__":
    main()
