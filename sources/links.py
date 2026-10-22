"""One table of streaming and store links per Song A Day song: Bandcamp, Apple Music, Spotify.

Reads (all made by other steps; this script makes no web requests):
  dataset/bandcamp.csv     from sources/bandcamp.py
  dataset/apple_music.csv  from sources/apple_music.py
  dataset/spotify.csv      from sources/spotify.py, if it has been run (it needs Spotify
                           app credentials; without it the Spotify columns stay blank)
  their raw caches, only for each track's audio length:
    cache/bandcamp/albums/*.html   (trackinfo duration)
    cache/apple/albums/*.json      (trackTimeMillis)
    cache/spotify/albums/*.json    (duration_ms)
  and the songaday-display catalog (index-*.json chunks) for the titles and the video
  Length, falling back to dataset/songs.csv.

Writes:
  dataset/links.csv                  one row per song, #1 to the newest song in the catalog
  analysis/sheet-backfill-links.csv  number, date, title, bandcamp, apple_music, spotify,
                                     with only the links rated "high" (see below); a blank
                                     cell means "not found" or "not sure", never a guess
  analysis/links-report.md           coverage by year, what's missing and why, conflicts
                                     between the services, and the links to eyeball

How sure is each link? Each fetch step matched its own tracks to songs by title and
position (match = exact | fuzzy | position-only, with a 0-1 match_score). This step
checks the services against each other and against the catalog:
  - Title. A link is sure on its title alone when match is "exact", or "fuzzy" with
    match_score >= TITLE_SURE. For a single, EP or compilation (not a year, season or
    month album) the title must also name only one song in the catalog, because nothing
    about its position says which of two same-named songs it is.
  - Audio. The services usually carry the same master, so the same song has the same
    length on each (the median gap between Bandcamp and Apple is 0.04 s). Two lengths
    within SAME_AUDIO of each other are taken to be the same recording.
    A weak title match (position-only, low fuzzy) is accepted when another service's
    title-sure link for the same song has the same audio, or when the track sits on a
    dated album and its audio is the catalog's Length to within SHIFT_MATCH_CATALOG.
    A file is the odd one out when its length is far (FAR) from every other service's
    audio for that song and from the catalog's Length, while another service agrees with
    the catalog. If it is also within SHIFT_MATCH of a neighbouring song's audio, it
    probably plays that song (the service's titles are shifted against its audio, or two
    tracks are swapped): "audio_shifted", and the link is not trusted. Otherwise it is
    "audio_mismatch" (usually another take, an edit or padding) and keeps its rating.
  - Titles across services. If a service's track title is the title another service (or
    the catalog) gives a different song, the two disagree about which song that title is.
    When the track's audio is that other song's, it is a conflict and the link is not
    trusted. When the title also fits this song (two songs share a title), nothing is
    flagged. When the audio vouches for this song (as above), the link is right and only
    the service's title is wrong ("mislabelled"). Otherwise it is a conflict.
  - A track URL used for two songs is a conflict for both.
confidence per service: "high" (goes in the sheet), "check" (linked, but left out of the
sheet and listed in the report), "none" (no track found), blank (that service's step
hasn't been run).

Run from the repo root:
  .venv/bin/python sources/links.py
  .venv/bin/python sources/links.py --spotify-csv some/other/spotify.csv   (testing)

Paths, all optional:
  SONGADAY_CATALOG_DIR  songaday-display publish/meta folder (index-*.json chunks)
                        default ~/Library/Caches/songaday-display/publish/meta
"""

import argparse
import csv
import datetime as dt
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sources"))

# The title helpers of the two fetch steps, so "same title" means what it meant there.
import apple_music  # noqa: E402  normalize, title_forms, title_similarity, period_range
import bandcamp  # noqa: E402  parse_album, similarity

CATALOG_DIR = Path(
    os.environ.get(
        "SONGADAY_CATALOG_DIR",
        Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta",
    )
)
SONGS_CSV = ROOT / "dataset" / "songs.csv"
OUT_CSV = ROOT / "dataset" / "links.csv"
SHEET_CSV = ROOT / "analysis" / "sheet-backfill-links.csv"
REPORT_MD = ROOT / "analysis" / "links-report.md"

FIRST_DAY = dt.date(2009, 1, 1)  # song #1
SHEET_LAST = 5113  # the public spreadsheet currently ends at #5113 (2022-12-31)
SEASONS_UNTIL = dt.date(2017, 9, 30)  # Apple/Spotify: season albums until here, then months

TITLE_SURE = 0.85  # a fuzzy title match this good is trusted on its own
TITLES_AGREE = 0.80  # two services' titles this similar name the same song
SAME_AUDIO = (1.5, 0.01)  # same recording: within 1.5 s or 1%, whichever is larger
NEAR_CATALOG = (3.0, 0.03)  # agrees with the catalog's whole-second video Length
FAR = (10.0, 0.10)  # clearly different: more than 10 s and more than 10% apart
SHIFT_MATCH = 1.0  # seconds; audio this close to a neighbouring song's audio "is" that song
SHIFT_MATCH_CATALOG = 1.5  # the same against the catalog's whole-second Length
NEIGHBOURS = (-2, -1, 1, 2)  # how far a shifted or swapped track can be from its song

# Each service: where its table is, which columns hold what, and where its audio lengths are.
SERVICES = [
    {
        "key": "bandcamp",
        "label": "Bandcamp",
        "csv": ROOT / "dataset" / "bandcamp.csv",
        "url": "bandcamp_url",
        "title": "bandcamp_title",
        "album": "bandcamp_album",
        "track": "track_num",
        "id": "bandcamp_url",  # Bandcamp's lengths are looked up by track URL
    },
    {
        "key": "apple_music",
        "label": "Apple Music",
        "csv": ROOT / "dataset" / "apple_music.csv",
        "url": "apple_music_url",
        "title": "apple_title",
        "album": "apple_album",
        "track": "track_number",
        "id": "apple_track_id",
    },
    {
        "key": "spotify",
        "label": "Spotify",
        "csv": ROOT / "dataset" / "spotify.csv",
        "url": "spotify_url",
        "title": "spotify_title",
        "album": "spotify_album",
        "track": "track_number",
        "id": "spotify_track_id",
    },
]
LABEL = {s["key"]: s["label"] for s in SERVICES}

COLUMNS = ["number", "date", "title", "catalog_seconds"]
for _s in SERVICES:
    COLUMNS += [f"{_s['key']}_{field}" for field in
                ("url", "title", "album", "match", "score", "seconds", "confidence")]
COLUMNS += ["flags", "notes"]


# ---------------------------------------------------------------------------
# 1. Inputs
# ---------------------------------------------------------------------------


def song_date(number):
    return FIRST_DAY + dt.timedelta(days=number - 1)


def length_seconds(text):
    """ "2:36" -> 156; None when blank or unreadable."""
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
    """Return {number: {"title", "seconds"}}, from the catalog chunks or else songs.csv.

    Some catalog chunks exist in two hashed versions; the newest file wins for each song.
    """
    files = sorted(glob.glob(str(CATALOG_DIR / "index-*.json")), key=os.path.getmtime)
    songs = {}
    if files:
        for path in files:
            for song in json.loads(Path(path).read_text())["songs"]:
                songs[song["n"]] = {
                    "title": song.get("t") or "",
                    "seconds": length_seconds((song.get("a") or {}).get("Length")),
                    "date": song.get("d"),
                }
        source = f"catalog ({CATALOG_DIR})"
    elif SONGS_CSV.exists():
        with SONGS_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                seconds = row.get("length_seconds") or ""
                songs[int(row["number"])] = {
                    "title": row["title"],
                    "seconds": int(float(seconds)) if seconds else None,
                    "date": row["date"],
                }
        source = str(SONGS_CSV.relative_to(ROOT))
    else:
        sys.exit(f"No catalog in {CATALOG_DIR} and no {SONGS_CSV}")
    numbers = sorted(songs)
    if numbers != list(range(1, numbers[-1] + 1)):
        sys.exit("the song list has gaps or repeats")
    for n in numbers:
        if songs[n]["date"] and songs[n]["date"] != song_date(n).isoformat():
            sys.exit(f"#{n} is dated {songs[n]['date']}, not {song_date(n)}")
    print(f"Songs: #1 to #{numbers[-1]} from {source}")
    return songs


def show(path):
    """A path for messages: relative to the repo when it is inside it."""
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def load_service(service, path):
    """Return {number: row} from a service's table, or None if the table doesn't exist."""
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = {int(r["number"]): r for r in csv.DictReader(f)}
    print(f"{service['label']}: {len(rows)} rows from {show(path)}")
    return rows


def bandcamp_tracks():
    """Return {track URL: {"seconds", "year", "track", "title"}} from the cached album pages."""
    tracks = {}
    for path in sorted((ROOT / "cache" / "bandcamp" / "albums").glob("*.html")):
        album, items = bandcamp.parse_album(path.read_text(encoding="utf-8"))
        for item in items:
            tracks[item["url"]] = {
                "seconds": item["duration"],
                "album": album,
                "track": item["track_num"],
                "title": item["title"],
            }
    return tracks


def apple_lengths():
    """Return {trackId as text: seconds} from the cached Apple album lookups."""
    lengths = {}
    for path in sorted((ROOT / "cache" / "apple" / "albums").glob("*.json")):
        for item in json.loads(path.read_text())["results"]:
            if item.get("wrapperType") == "track" and item.get("trackTimeMillis"):
                lengths[str(item["trackId"])] = item["trackTimeMillis"] / 1000
    return lengths


def spotify_lengths():
    """Return {track id: seconds} from the cached Spotify album track lists, if any."""
    lengths = {}
    for path in sorted((ROOT / "cache" / "spotify" / "albums").glob("*.json")):
        for item in json.loads(path.read_text()).get("tracks") or []:
            if item.get("id") and item.get("duration_ms"):
                lengths[item["id"]] = item["duration_ms"] / 1000
    return lengths


def release_lists():
    """Return {service key: [(release name, track count)]} from the cached release lists,
    used to explain why a song has no link (no album for its season or month, or the
    album is there but the song isn't on it)."""
    lists = {}
    apple_list = ROOT / "cache" / "apple" / "artist-188742143-albums.json"
    if apple_list.exists():
        lists["apple_music"] = [
            (r.get("collectionName") or "", r.get("trackCount"))
            for r in json.loads(apple_list.read_text())["results"]
            if r.get("wrapperType") == "collection"
        ]
    for path in (ROOT / "cache" / "spotify").glob("artist-*-albums.json"):
        lists["spotify"] = [(a.get("name") or "", a.get("total_tracks"))
                            for a in json.loads(path.read_text()).get("albums") or []]
    return lists


# ---------------------------------------------------------------------------
# 2. Comparing titles and lengths
# ---------------------------------------------------------------------------


def within(a, b, tolerance):
    """True when a and b are both known and within (seconds, share) of each other."""
    if a is None or b is None:
        return False
    seconds, share = tolerance
    return abs(a - b) <= max(seconds, share * max(a, b))


def far(a, b):
    """True when a and b are both known and clearly different lengths."""
    if a is None or b is None:
        return False
    seconds, share = FAR
    return abs(a - b) > max(seconds, share * max(a, b))


def title_score(a, b):
    """How alike two titles are, 0 to 1: the better of the Apple and Bandcamp scorers
    (Apple's handles censoring and asides; Bandcamp's keeps emoji titles)."""
    if not a or not b:
        return 0.0
    apple = apple_music.title_similarity(apple_music.title_forms(a), apple_music.title_forms(b))
    return max(apple, bandcamp.similarity(a, b)[0])


def norm(title):
    """The normalized title used as a dictionary key (emoji titles kept as they are)."""
    return apple_music.normalize(title) or bandcamp.normalize(title) or title.strip()


def fmt_seconds(value):
    return "" if value is None else f"{value:.1f}"


# ---------------------------------------------------------------------------
# 3. Checking each song
# ---------------------------------------------------------------------------


def build_links(songs, tables, lengths):
    """Return (links, flags, notes): links[number][service] is a dict for each linked track."""
    links = defaultdict(dict)
    for service in SERVICES:
        key = service["key"]
        table = tables.get(key)
        if table is None:
            continue
        for number, row in table.items():
            if number not in songs or row.get("match", "none") in ("", "none"):
                continue
            album = row.get(service["album"]) or ""
            seconds = lengths[key].get(row.get(service["id"]) or "")
            if seconds is not None and seconds <= 0:
                seconds = None  # a Bandcamp track with no audio
            links[number][key] = {
                "url": row[service["url"]],
                "title": row.get(service["title"]) or "",
                "album": album,
                "match": row["match"],
                "score": float(row["match_score"]) if row.get("match_score") else None,
                "seconds": seconds,
                "no_audio": key == "bandcamp" and lengths[key].get(row[service["id"]]) == 0,
                # A year, season or month album says by position which song a track is.
                "positional": key == "bandcamp" or apple_music.period_range(album) is not None,
            }
    return links


def check_songs(songs, tables, links):
    """Rate every link. Returns {number: {service: confidence}}, flags and notes per song."""
    confidence = defaultdict(dict)
    flags = defaultdict(list)
    notes = defaultdict(list)
    backed_by = defaultdict(dict)  # why a weak title match was still rated high

    # Which songs each service's titles point at, and which the catalog's do, so a title
    # one service gives song N can be found on a different song elsewhere.
    by_title = {key: defaultdict(set) for key in LABEL}
    for number, by_service in links.items():
        for key, link in by_service.items():
            by_title[key][norm(link["title"])].add(number)
    catalog_by_title = defaultdict(set)
    for number, song in songs.items():
        catalog_by_title[norm(song["title"])].add(number)

    # Track URLs used for more than one song.
    url_songs = defaultdict(set)
    for number, by_service in links.items():
        for key, link in by_service.items():
            url_songs[(key, link["url"])].add(number)

    def audio_at(key, number):
        link = links.get(number, {}).get(key)
        return link["seconds"] if link else None

    for number in sorted(songs):
        catalog_seconds = songs[number]["seconds"]
        here = links.get(number, {})
        for key in LABEL:
            if tables.get(key) is not None:
                confidence[number][key] = "none"

        # 3a. Is each link sure on its title alone?
        title_sure = {}
        for key, link in here.items():
            sure = link["match"] == "exact" or (
                link["match"] == "fuzzy" and (link["score"] or 0) >= TITLE_SURE)
            if sure and not link["positional"]:
                # A single or compilation: the title must name only one song.
                same_named = catalog_by_title.get(norm(link["title"]), set()) | {number}
                if len(same_named) > 1:
                    sure = False
                    flags[number].append(f"{key}_ambiguous_title")
                    others = sorted(same_named - {number})
                    notes[number].append(
                        f"{LABEL[key]}: '{link['title']}' is on '{link['album']}', not a "
                        f"dated album, and " + ", ".join(f"#{n}" for n in others)
                        + (" has" if len(others) == 1 else " have") + " the same title")
            title_sure[key] = sure

        # 3b. Which links share audio with another service's link for this song?
        same_audio_as = defaultdict(set)
        for a in here:
            for b in here:
                if a != b and within(here[a]["seconds"], here[b]["seconds"], SAME_AUDIO):
                    same_audio_as[a].add(b)

        # 3c. Audio that is the odd one out: far from every other service's audio for this
        # song and from the catalog's Length. Only "shifted" (it matches a neighbouring
        # song) makes a link untrusted; other mismatches are listed but keep their rating,
        # because nothing says the track is a different song (it is usually another take,
        # an edit or padding).
        shifted = set()
        for key, link in here.items():
            mine = link["seconds"]
            if mine is None:
                continue
            others = {o: here[o]["seconds"] for o in here if o != key and here[o]["seconds"]}
            if within(mine, catalog_seconds, NEAR_CATALOG) or same_audio_as[key]:
                continue
            if others and not all(far(mine, s) for s in others.values()):
                continue  # a few seconds off another service: a different master, fine
            if catalog_seconds is not None and not far(mine, catalog_seconds):
                continue
            # Someone else must agree with the catalog (or with each other) for this link
            # to be the odd one, or its audio must clearly be a neighbouring song's.
            backed = any(within(s, catalog_seconds, NEAR_CATALOG) for s in others.values()) \
                or any(same_audio_as[o] - {key} for o in others)
            neighbour = None
            for step in NEIGHBOURS:
                other_number = number + step
                if other_number not in songs:
                    continue
                refs = [audio_at(o, other_number) for o in LABEL if o != key]
                if any(r is not None and abs(mine - r) <= SHIFT_MATCH for r in refs) or (
                        all(r is None for r in refs)
                        and songs[other_number]["seconds"] is not None
                        and abs(mine - songs[other_number]["seconds"]) <= SHIFT_MATCH_CATALOG):
                    neighbour = other_number
                    break
            if not backed and neighbour is None:
                if others and "audio_differs" not in flags[number]:
                    flags[number].append("audio_differs")
                    notes[number].append(
                        "audio lengths differ and none matches the catalog's "
                        f"{catalog_seconds} s: "
                        + ", ".join(f"{LABEL[k]} {here[k]['seconds']:.0f} s"
                                    for k in here if here[k]["seconds"]))
                continue
            reference = ", ".join(f"{LABEL[o]} {s:.0f} s" for o, s in others.items())
            reference = (reference + ", " if reference else "") + f"catalog {catalog_seconds} s"
            text = f"{LABEL[key]}: audio is {mine:.0f} s against {reference}"
            if neighbour is not None:
                shifted.add(key)
                flags[number].append(f"{key}_audio_shifted")
                text += f"; it matches #{neighbour}'s length, so it may play that song"
                # Where this song's own audio may be on this service instead.
                target = list(others.values()) + (
                    [catalog_seconds] if catalog_seconds is not None else [])
                for step in (-3, -2, -1, 1, 2, 3):
                    elsewhere = audio_at(key, number + step)
                    if elsewhere is not None and any(abs(elsewhere - t) <= SHIFT_MATCH_CATALOG
                                                     for t in target):
                        text += f"; this song's audio may be under {LABEL[key]}'s " \
                                f"#{number + step} track"
                        break
            else:
                flags[number].append(f"{key}_audio_mismatch")
                text += " (a different take, an edit, padding, or the wrong file)"
            notes[number].append(text)

        # Audio that vouches for a link whose title doesn't: the same length as another
        # service's title-sure link for this song, or, for a track on a dated album, the
        # catalog's Length to within SHIFT_MATCH_CATALOG (the Bandcamp step's position-only
        # tracks all fit this; their slot already says which song they should be).
        def audio_vouch(key):
            link = here[key]
            for other in sorted(same_audio_as[key], key=list(LABEL).index):
                if title_sure.get(other) and other not in shifted:
                    return f"its audio matches {LABEL[other]}'s track for this song"
            if (link["positional"] and link["seconds"] is not None
                    and catalog_seconds is not None
                    and abs(link["seconds"] - catalog_seconds) <= SHIFT_MATCH_CATALOG):
                return f"its audio is this song's length ({catalog_seconds} s) and it sits " \
                       "in this song's place on the album"
            return None

        # 3d. A title that another service, or the catalog, gives a different song.
        conflicted = set()
        for key, link in here.items():
            if link["match"] == "exact":
                continue  # it is this song's catalog title
            mine = norm(link["title"])
            homes = set()
            for other in LABEL:
                if other == key:
                    continue
                other_here = here.get(other)
                if other_here and norm(other_here["title"]) == mine:
                    continue  # the other service calls this song the same thing
                homes |= {(LABEL[other], n) for n in by_title[other].get(mine, ()) if n != number}
            homes |= {("the catalog", n) for n in catalog_by_title.get(mine, ()) if n != number}
            if not homes:
                continue
            where = ", ".join(f"{who} #{n}" for who, n in sorted(homes, key=lambda h: (h[1], h[0])))
            # Is this track the other song's recording? Its audio would match that song's.
            mine_seconds = link["seconds"]
            audio_home = sorted({
                n for _, n in homes if mine_seconds is not None and (
                    any(within(mine_seconds, audio_at(o, n), SAME_AUDIO) for o in LABEL)
                    or (songs[n]["seconds"] is not None
                        and abs(mine_seconds - songs[n]["seconds"]) <= SHIFT_MATCH_CATALOG))})
            vouch = audio_vouch(key)
            if audio_home and not (same_audio_as[key] & {o for o in here if title_sure.get(o)}):
                conflicted.add(key)
                flags[number].append(f"{key}_title_elsewhere")
                notes[number].append(
                    f"{LABEL[key]} links its track '{link['title']}' here, but that is the "
                    f"title of {where}, and its audio matches "
                    + ", ".join(f"#{n}" for n in audio_home))
            elif title_score(link["title"], songs[number]["title"]) >= TITLES_AGREE:
                continue  # two songs share a title; this one's own title fits too
            elif vouch:
                flags[number].append(f"{key}_mislabelled")
                notes[number].append(
                    f"{LABEL[key]} titles this track '{link['title']}', which is the title of "
                    f"{where}; {vouch}, so the link is right and {LABEL[key]}'s title is wrong")
            else:
                conflicted.add(key)
                flags[number].append(f"{key}_title_elsewhere")
                notes[number].append(
                    f"{LABEL[key]} links its track '{link['title']}' here, but that is the "
                    f"title of {where}")

        # 3e. One URL used for two songs.
        for key, link in here.items():
            shared = url_songs[(key, link["url"])] - {number}
            if shared:
                conflicted.add(key)
                flags[number].append(f"{key}_url_reused")
                notes[number].append(f"{LABEL[key]}: the same track is linked to "
                                     + ", ".join(f"#{n}" for n in sorted(shared)))

        # 3f. Titles of two services that don't look alike and aren't the same audio
        # (often a retitle on one service; information only).
        keys = sorted(here)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                if (title_score(here[a]["title"], here[b]["title"]) < TITLES_AGREE
                        and not (same_audio_as[a] & {b})):
                    flags[number].append("titles_differ")
                    notes[number].append(
                        f"{LABEL[a]} '{here[a]['title']}' vs {LABEL[b]} '{here[b]['title']}', "
                        "and their audio doesn't match either")

        # 3g. The verdict for each link.
        for key, link in here.items():
            if key in shifted or key in conflicted:
                confidence[number][key] = "check"
            elif title_sure[key]:
                confidence[number][key] = "high"
            elif audio_vouch(key):
                confidence[number][key] = "high"
                backed_by[number][key] = audio_vouch(key)
                notes[number].append(f"{LABEL[key]}: {link['match']} title match, rated high "
                                     f"because {audio_vouch(key)}")
            else:
                confidence[number][key] = "check"
                flags[number].append(f"{key}_weak_match")
                score = f"{link['score']:.2f}" if link["score"] is not None else "?"
                notes[number].append(
                    f"{LABEL[key]}: {link['match']} match (score {score}) to "
                    f"'{link['title']}' with nothing else to back it up")
            if link["no_audio"]:
                flags[number].append("bandcamp_no_audio")
                notes[number].append("Bandcamp's track page has no audio")

        # 3h. A weak match on a dated album with no audio to check (Spotify, when its cache
        # has no lengths) is still backed up when another service's high link for this
        # song, also on a dated album, has exactly the same title: Apple and Spotify get
        # their releases from the same distributor, so the same odd title in the same
        # place is the same track. (Not for singles: there the shared title is the doubt.)
        for key, link in here.items():
            if (f"{key}_weak_match" not in flags[number] or link["seconds"] is not None
                    or not link["positional"]):
                continue
            twins = [o for o in here if o != key and confidence[number][o] == "high"
                     and here[o]["positional"]
                     and norm(here[o]["title"]) == norm(link["title"])]
            if twins:
                confidence[number][key] = "high"
                backed_by[number][key] = f"the same title as {LABEL[twins[0]]}'s high link"
                flags[number].remove(f"{key}_weak_match")
                notes[number] = [t for t in notes[number]
                                 if not (t.startswith(LABEL[key]) and "nothing else" in t)]
                notes[number].append(f"{LABEL[key]}: {link['match']} title match, rated high "
                                     f"because it has the same title as {LABEL[twins[0]]}'s "
                                     "high link for this song")
    return confidence, flags, notes, backed_by


# ---------------------------------------------------------------------------
# 4. Why a song has no link
# ---------------------------------------------------------------------------


def period_name(day):
    """The release a song's date belongs on: "Spring, 2014" or "October, 2026"."""
    if day <= SEASONS_UNTIL:
        season = ["Winter", "Spring", "Summer", "Fall"][(day.month - 1) // 3]
        return f"{season}, {day.year}"
    return f"{apple_music.MONTHS[day.month - 1]}, {day.year}"


def missing_reasons(songs, tables, links, bc_tracks, releases):
    """Return {service: {number: reason}} for each song a service has no link for."""
    reasons = defaultdict(dict)

    # Bandcamp: what sits in the song's slot on its year album.
    if tables.get("bandcamp") is not None:
        used = {link["url"] for by_service in links.values()
                for k, link in by_service.items() if k == "bandcamp"}
        album_tracks = defaultdict(dict)  # album title -> {track number: track}
        for url, track in bc_tracks.items():
            album_tracks[track["album"]][track["track"]] = dict(track, url=url)
        for number in songs:
            if "bandcamp" in links.get(number, {}):
                continue
            before = next((n for n in range(number - 1, 0, -1)
                           if "bandcamp" in links.get(n, {})), None)
            after = next((n for n in range(number + 1, max(songs) + 1)
                          if "bandcamp" in links.get(n, {})), None)
            b = links[before]["bandcamp"] if before else None
            a = links[after]["bandcamp"] if after else None
            if not b or not a or b["album"] != a["album"]:
                reasons["bandcamp"][number] = "not on Bandcamp (no year album track around it)"
                continue
            first = int(tables["bandcamp"][before]["track_num"])
            last = int(tables["bandcamp"][after]["track_num"])
            low, high = sorted((first, last))
            spare = [t for t_num, t in sorted(album_tracks[b["album"]].items())
                     if low < t_num < high and t["url"] not in used]
            if not spare and first < last:
                reasons["bandcamp"][number] = (
                    f"'{b['album']}' goes straight from track {first} (#{before}) to "
                    f"track {last} (#{after})")
            elif not spare:
                reasons["bandcamp"][number] = (
                    f"not on '{b['album']}'; the tracks around it are out of order "
                    f"(track {first} is #{before}, track {last} is #{after}) and none is left over")
            else:
                reasons["bandcamp"][number] = (
                    f"'{b['album']}' has an unmatched track in its slot: "
                    + "; ".join(f"track {t['track']} '{t['title']}' ({t['seconds'] or 0:.0f} s)"
                                for t in spare))

    # Apple and Spotify: is there a season or month album for the song's date at all?
    for key in ("apple_music", "spotify"):
        if tables.get(key) is None:
            continue
        ranges = []
        for name, count in releases.get(key, []):
            span = apple_music.period_range(name)
            if span:
                ranges.append((span, name, count))
        for number in songs:
            if key in links.get(number, {}):
                continue
            day = song_date(number)
            homes = [(name, count) for (first, last), name, count in ranges
                     if first <= day <= last]
            if not homes:
                reasons[key][number] = f"no '{period_name(day)}' album on {LABEL[key]} (US)"
            else:
                name, count = homes[0]
                reasons[key][number] = f"not on '{name}' ({count} tracks)"
    return reasons


# ---------------------------------------------------------------------------
# 5. Output
# ---------------------------------------------------------------------------


def write_tables(songs, tables, links, confidence, flags, notes):
    """Write dataset/links.csv and analysis/sheet-backfill-links.csv."""
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    SHEET_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as out, \
            SHEET_CSV.open("w", newline="", encoding="utf-8") as sheet:
        table = csv.writer(out, lineterminator="\n")
        paste = csv.writer(sheet, lineterminator="\n")
        table.writerow(COLUMNS)
        paste.writerow(["number", "date", "title", "bandcamp", "apple_music", "spotify"])
        for number in sorted(songs):
            day = song_date(number)
            row = [number, day.isoformat(), songs[number]["title"],
                   songs[number]["seconds"] if songs[number]["seconds"] is not None else ""]
            sure = {}
            for service in SERVICES:
                key = service["key"]
                link = links.get(number, {}).get(key)
                fetched = tables.get(key) is not None
                if link:
                    row += [link["url"], link["title"], link["album"], link["match"],
                            f"{link['score']:.3f}" if link["score"] is not None else "",
                            fmt_seconds(link["seconds"]), confidence[number][key]]
                else:
                    row += ["", "", "", "none" if fetched else "", "", "",
                            "none" if fetched else ""]
                sure[key] = link["url"] if link and confidence[number][key] == "high" else ""
            # Flags can repeat (two services, same kind); keep the first of each.
            row += ["|".join(dict.fromkeys(flags[number])), "; ".join(notes[number])]
            table.writerow(row)
            # The spreadsheet writes dates as M/D/YYYY.
            paste.writerow([number, f"{day.month}/{day.day}/{day.year}", songs[number]["title"],
                            sure["bandcamp"], sure["apple_music"], sure["spotify"]])


def coverage_rows(songs, tables, links, confidence):
    """Per year: songs, and for each service linked and high counts."""
    years = sorted({song_date(n).year for n in songs})
    rows = []
    for year in years + ["all"]:
        numbers = [n for n in songs if year == "all" or song_date(n).year == year]
        row = {"year": year, "songs": len(numbers)}
        for key in LABEL:
            if tables.get(key) is None:
                row[key] = None
                continue
            row[key] = (sum(key in links.get(n, {}) for n in numbers),
                        sum(confidence[n].get(key) == "high" for n in numbers))
        row["any"] = sum(any(v == "high" for v in confidence[n].values()) for n in numbers)
        row["every"] = sum(
            all(confidence[n].get(k) == "high" for k in LABEL if tables.get(k) is not None)
            for n in numbers)
        rows.append(row)
    return rows


def runs(numbers):
    """[(first, last)] runs of consecutive numbers."""
    out = []
    for n in sorted(numbers):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return [tuple(r) for r in out]


def md_escape(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def write_report(songs, tables, links, confidence, flags, notes, reasons, backed_by):
    """Write analysis/links-report.md."""
    fetched = [k for k in LABEL if tables.get(k) is not None]
    last = max(songs)
    cov = coverage_rows(songs, tables, links, confidence)
    total = cov[-1]
    lines = []
    w = lines.append

    w("# Bandcamp, Apple Music and Spotify links")
    w("")
    w("Made by `sources/links.py` from "
      + ", ".join(f"`{show(s['csv'])}`" for s in SERVICES if tables.get(s['key']) is not None)
      + ". It covers songs #1 to "
      f"#{last} ({song_date(last).isoformat()}). The full table is `dataset/links.csv`; "
      "`analysis/sheet-backfill-links.csv` has only the links rated **high**.")
    w("")
    w("## In short")
    w("")
    for key in LABEL:
        if tables.get(key) is None:
            w(f"- **{LABEL[key]}:** not fetched yet, so this column is blank. See "
              "[Spotify](#spotify) below.")
            continue
        linked, high = total[key]
        w(f"- **{LABEL[key]}:** {linked:,} of {total['songs']:,} songs have a link "
          f"({linked / total['songs']:.1%}); {high:,} are rated high and go in the sheet, "
          f"{linked - high:,} are left for you to check, and {total['songs'] - linked:,} "
          "have no track.")
    w(f"- {total['any']:,} songs have at least one high link; {total['every']:,} have a high "
      "link on every service fetched ("
      + ", ".join(LABEL[k] for k in fetched[:-1]) + " and " + LABEL[fetched[-1]] + ").")
    w("- **Downloads and plays:** none of the three services publishes them. Bandcamp's "
      "album data has no play or download count (play_count is 0 or empty), Apple's iTunes "
      "API has none, and Spotify's Web API gives no stream counts. See "
      "[Downloads](#downloads-and-plays).")
    w("")

    w("## The spreadsheet file")
    w("")
    w("`analysis/sheet-backfill-links.csv` has one row per song, #1 to "
      f"#{last}, with the columns number, date (M/D/YYYY, like the sheet), title, "
      "bandcamp, apple_music, spotify. A cell is filled only when the link is rated high; "
      "blank means no track was found or the match isn't sure enough (those are listed "
      "below). The public sheet currently ends at "
      f"#{SHEET_LAST} ({song_date(SHEET_LAST).isoformat()}). Its songs run #1, #2, ... in "
      "order with no gaps (#1 is on row 3, under the note and the header row), so the "
      f"file's first {SHEET_LAST:,} rows line up with it row for row: copy the bandcamp, "
      "apple_music and spotify cells of #1 to "
      f"#{SHEET_LAST} and paste them into new columns starting at row 3. Rows "
      f"#{SHEET_LAST + 1} to #{last} are for wherever you keep the later years.")
    sheet_high = {k: sum(confidence[n].get(k) == "high" for n in songs if n <= SHEET_LAST)
                  for k in fetched}
    w("")
    w(f"For #1 to #{SHEET_LAST}: "
      + ", ".join(f"{LABEL[k]} {sheet_high[k]:,} links" for k in fetched)
      + f". For #{SHEET_LAST + 1} to #{last}: "
      + ", ".join(f"{LABEL[k]} {total[k][1] - sheet_high[k]:,}" for k in fetched) + ".")
    w("")

    w("## How sure a link is")
    w("")
    w("Each fetch step matched its own tracks to songs by title and by position on the "
      "year, season or month album (match = exact, fuzzy or position-only). This step "
      "checks the services against each other:")
    w("")
    w(f"- **high**: an exact title match, or a fuzzy one scoring {TITLE_SURE} or more. A "
      "weaker match (position-only, or fuzzy below that) is high too when its audio backs it "
      f"up: the same length, within {SAME_AUDIO[0]} s, as another service's sure link for the "
      "same song, or, for a track on a year, season or month album, the catalog's Length "
      f"to within {SHIFT_MATCH_CATALOG} s. Bandcamp and Apple usually carry the same master: "
      "for songs on both, the median length gap is well under a second. A single or "
      "compilation track also needs a title only one song has, or audio that backs it up.")
    w("- **check**: linked, but left out of the sheet: a weak match nothing backs up; a file "
      "whose length is far from the other service's and the catalog's but within a second of "
      "a neighbouring song's (so it may play that song); a title that another service, or the "
      "catalog, gives a different song whose audio this track has; or a single whose title "
      "several songs share.")
    w("- A file that is far off the other service and the catalog, but doesn't look like any "
      "neighbouring song, keeps its rating: it is usually another take, an edit or padding. "
      "Those are listed below to listen to.")
    w("")

    # Coverage table.
    w("## Coverage by year")
    w("")
    w("Each cell is linked / high (high is what the sheet gets).")
    w("")
    header = ["Year", "Songs"] + [LABEL[k] for k in LABEL] + ["Any high", "All high"]
    w("| " + " | ".join(header) + " |")
    w("| " + " | ".join(["---"] + ["---:"] * (len(header) - 1)) + " |")
    for row in cov:
        cells = [f"**{row['year']}**" if row["year"] == "all" else str(row["year"]),
                 f"{row['songs']:,}"]
        for key in LABEL:
            cells.append("not fetched" if row[key] is None else f"{row[key][0]:,} / {row[key][1]:,}")
        cells += [f"{row['any']:,}", f"{row['every']:,}"]
        w("| " + " | ".join(cells) + " |")
    w("")
    w("Match types: " + "; ".join(
        f"{LABEL[k]} " + ", ".join(f"{m} {c:,}" for m, c in Counter(
            (tables[k][n]["match"] if n in tables[k] else "none") for n in songs).most_common())
        for k in fetched) + ".")
    w("")

    # Missing.
    w("## What's missing and why")
    w("")
    for key in fetched:
        missing = sorted(reasons[key])
        w(f"### {LABEL[key]}: {len(missing)} songs with no track")
        w("")
        if not missing:
            w("None.")
            w("")
            continue
        # Long runs first (a whole album missing), then single songs.
        by_reason = defaultdict(list)
        for n in missing:
            by_reason[reasons[key][n]].append(n)
        grouped = sorted(by_reason.items(), key=lambda item: item[1][0])
        for reason, numbers in grouped:
            spans = ", ".join(f"#{a}" if a == b else f"#{a}-#{b}" for a, b in runs(numbers))
            if len(numbers) == 1:
                n = numbers[0]
                w(f"- #{n} '{md_escape(songs[n]['title'])}' ({song_date(n).isoformat()}): "
                  f"{md_escape(reason)}")
            else:
                w(f"- {spans} ({len(numbers)} songs): {md_escape(reason)}")
        w("")
        if key == "apple_music":
            w("Spring 2014 and Summer 2015 have no album on Apple Music US (the fetch step "
              "also searched the iTunes Search API for them and found nothing); 4 Summer "
              "2015 songs are linked from compilations instead. The newest month's album "
              "isn't out yet. A single song missing from an album that exists is usually a "
              "track left off when the album was distributed.")
            w("")
        if key == "bandcamp":
            w("An unmatched track in a song's slot is usually a duplicate upload or a "
              "track whose length is too far from the song's to be paired by position "
              "(the Bandcamp step refused those rather than guess).")
            w("")
    if "spotify" not in fetched:
        w("### Spotify")
        w("")
        w("Not fetched. `sources/spotify.py` is written and tested against a fake API, but "
          "Spotify needs an app's client ID and secret even for read-only lookups, and "
          "there are none in `.env`. To fill the column:")
        w("")
        w("1. Make a free app at https://developer.spotify.com/dashboard (any name, redirect "
          "URI `http://127.0.0.1:8888/callback`, tick Web API).")
        w("2. Put `SPOTIFY_CLIENT_ID=...` and `SPOTIFY_CLIENT_SECRET=...` in `.env` (it is "
          "gitignored).")
        w("3. Run `.venv/bin/python sources/spotify.py`, then `.venv/bin/python "
          "sources/links.py` again. The Spotify column and its checks fill in by "
          "themselves.")
        w("")
        w("Spotify gets its releases from the same distributor as Apple, so expect roughly "
          "Apple's coverage, gaps included, but that is a guess until it runs.")
        w("")

    # Conflicts between services.
    w("## Where the services disagree")
    w("")
    w("These links are rated **check** and left out of the sheet.")
    w("")
    sections = [
        ("_audio_shifted", "Audio that looks like a neighbouring song",
         "The titles match, but this file's length is far from the other service's and the "
         "catalog's, and within a second of a song one or two days away. The service's "
         "titles are probably shifted against its audio, or two tracks are swapped, so the "
         "link may play the wrong song. Worth a listen, and possibly a fix with the "
         "distributor or on Bandcamp."),
        ("_title_elsewhere", "A title that belongs to a different song",
         "The service links a track here whose title is another song's, and either its audio "
         "is that other song's, or nothing about its audio says it is this one."),
        ("_ambiguous_title", "A single whose title several songs share",
         "Nothing about a single's position says which of the same-named songs it is, and its "
         "audio doesn't settle it."),
        ("_url_reused", "One track linked to two songs", ""),
    ]

    def note_table(hits):
        w("| # | Date | Title | Service | Their title | What doesn't fit |")
        w("| ---: | --- | --- | --- | --- | --- |")
        for n, k in hits:
            link = links[n][k]
            mine = [t for t in notes[n] if t.startswith(LABEL[k])]
            w(f"| {n} | {song_date(n).isoformat()} | {md_escape(songs[n]['title'])} | "
              f"[{LABEL[k]}]({link['url']}) | {md_escape(link['title'])} | "
              f"{md_escape('; '.join(mine) or '; '.join(notes[n]))} |")
        w("")

    for suffix, heading, blurb in sections:
        hits = [(n, k) for n in sorted(songs) for k in fetched
                if f"{k}{suffix}" in flags[n] and confidence[n][k] == "check"]
        w(f"### {heading} ({len(hits)})")
        w("")
        if blurb:
            w(blurb)
            w("")
        if not hits:
            w("None.")
            w("")
            continue
        note_table(hits)

    # Kept in the sheet, but the file's length is far off.
    hits = [(n, k) for n in sorted(songs) for k in fetched
            if f"{k}_audio_mismatch" in flags[n]]
    w(f"## In the sheet, but the file's length is far off ({len(hits)})")
    w("")
    w("The title matches (and, on a dated album, so does the place), so the link is the "
      "service's track for this song, but its length is far from what the other service and the catalog agree on. "
      "Usually another take, an edit, or padding; a few may be the wrong file. Worth a "
      "listen.")
    w("")
    # Runs of neighbouring songs whose file is off by about the same amount: padding.
    for k in fetched:
        offsets = {}
        for n, kk in hits:
            if kk != k:
                continue
            others = [links[n][o]["seconds"] for o in links[n]
                      if o != k and links[n][o]["seconds"] is not None]
            ref = others[0] if others else songs[n]["seconds"]
            if ref is not None:
                offsets[n] = links[n][k]["seconds"] - ref
        for a, b in runs(offsets):
            span = [offsets[n] for n in range(a, b + 1)]
            same_sign = all(x > 0 for x in span) or all(x < 0 for x in span)
            if b - a >= 3 and same_sign and max(span) - min(span) <= 20:
                low, high = sorted((abs(min(span)), abs(max(span))))
                w(f"- #{a}-#{b} on {LABEL[k]} ('{links[a][k]['album']}'): every one of these "
                  f"{b - a + 1} files is {low:.0f}-{high:.0f} s "
                  f"{'longer' if span[0] > 0 else 'shorter'} than the other service's, so "
                  f"something was {'added to' if span[0] > 0 else 'cut from'} the whole run, "
                  "not a different song each time.")
                w("")
    if hits:
        note_table(hits)

    # Weak matches.
    # (Singles with a shared title are listed above already.)
    hits = [(n, k) for n in sorted(songs) for k in fetched if f"{k}_weak_match" in flags[n]
            and f"{k}_ambiguous_title" not in flags[n]]
    w(f"## Weak matches nothing backs up ({len(hits)})")
    w("")
    w("Position-only or low-scoring fuzzy title matches with no second service whose audio "
      "agrees and no exact fit with the catalog's Length. They may well be right (several "
      "are singles released the day of the song under another name); they are left out of "
      "the sheet until you've looked.")
    w("")
    if hits:
        w("| # | Date | Catalog title | Service | Their title | Match | Score | Length vs catalog |")
        w("| ---: | --- | --- | --- | --- | --- | ---: | --- |")
        for n, k in hits:
            link = links[n][k]
            gap = (f"{link['seconds']:.0f} s vs {songs[n]['seconds']} s"
                   if link["seconds"] is not None and songs[n]["seconds"] is not None else "")
            w(f"| {n} | {song_date(n).isoformat()} | {md_escape(songs[n]['title'])} | "
              f"[{LABEL[k]}]({link['url']}) | {md_escape(link['title'])} | {link['match']} | "
              f"{link['score'] if link['score'] is not None else ''} | {gap} |")
    else:
        w("None.")
    w("")

    # Accepted, but worth a glance.
    accepted = []
    for n in sorted(songs):
        for k in fetched:
            link = links.get(n, {}).get(k)
            if (link and confidence[n][k] == "high"
                    and not (link["match"] == "exact"
                             or (link["match"] == "fuzzy" and (link["score"] or 0) >= TITLE_SURE))):
                accepted.append((n, k))
    w(f"## Weak titles that something else backs up ({len(accepted)})")
    w("")
    w("Position-only or low-scoring fuzzy title matches rated high because something else "
      "backs them up: another service's sure link for the same song is the same length; or "
      "the track sits in this song's place on a dated album and is the catalog's Length to "
      "the second; or, for a track with no length to compare, another service's high link "
      "in the same place has exactly the same title. These are in the sheet, so they are the ones to glance at first. Most are "
      "songs titled differently on the service than in the catalog (\"Our House\" for "
      "\"2100 California St.\"), or Bandcamp tracks that carry the previous track's title by "
      "mistake.")
    w("")
    if accepted:
        w("| # | Catalog title | Service | Their title | Match | Score | Backed by |")
        w("| ---: | --- | --- | --- | --- | ---: | --- |")
        for n, k in accepted:
            link = links[n][k]
            why = backed_by[n].get(k, "")
            if why.startswith("its audio matches"):
                why = "the other service's audio"
            elif why.startswith("its audio is"):
                why = "the catalog's Length"
            w(f"| {n} | {md_escape(songs[n]['title'])} | [{LABEL[k]}]({link['url']}) | "
              f"{md_escape(link['title'])} | {link['match']} | "
              f"{link['score'] if link['score'] is not None else ''} | {why} |")
        w("")

    # Information only.
    mislabelled = [n for n in sorted(songs) if any(f.endswith("_mislabelled") for f in flags[n])]
    no_audio = [n for n in sorted(songs) if "bandcamp_no_audio" in flags[n]]
    differs = [n for n in sorted(songs) if "audio_differs" in flags[n]]
    titles = [n for n in sorted(songs) if "titles_differ" in flags[n]]
    agree_off = [n for n in sorted(songs) if len(links.get(n, {})) > 1
                 and songs[n]["seconds"] is not None
                 and all(l["seconds"] is not None for l in links[n].values())
                 and all(within(a["seconds"], b["seconds"], SAME_AUDIO)
                         for a in links[n].values() for b in links[n].values())
                 and all(far(l["seconds"], songs[n]["seconds"]) for l in links[n].values())]
    w("## Notes that don't change a rating")
    w("")
    w(f"- **The services agree with each other, but not with the catalog's Length "
      f"({len(agree_off)}):** every service has the same file length, far from the "
      "video's. The links stand; it's the video (or the catalog's Length) that differs. "
      "This covers the Apple step's worry about Summer 2009 tracks 84-86: Bandcamp's files "
      "there have the same lengths as Apple's. "
      + (", ".join(f"#{n}" for n in agree_off) or "none") + ".")
    w(f"- **Right link, wrong title on the service ({len(mislabelled)}):** the track's title "
      "is another song's, but its audio matches the other service's track for this song. "
      "Fixing the title on the service would tidy these: "
      + (", ".join(f"#{n}" for n in mislabelled) or "none") + ".")
    w(f"- **Bandcamp track pages with no audio ({len(no_audio)}):** the link is right but "
      "there's nothing to play: " + (", ".join(f"#{n}" for n in no_audio) or "none") + ".")
    w(f"- **Audio lengths that differ with no clear odd one out ({len(differs)}):** neither "
      "matches the catalog's Length, which is the video's: "
      + (", ".join(f"#{n}" for n in differs) or "none") + ".")
    w(f"- **Titles that differ between services and aren't backed by audio ({len(titles)}):** "
      + (", ".join(f"#{n}" for n in titles) or "none") + ". The notes column of "
      "`dataset/links.csv` has both titles.")
    w("")

    w("## Downloads and plays")
    w("")
    w("No public source has them. Bandcamp's album pages carry a play_count field, but it "
      "is 0 or empty for every one of the 6,496 tracks; Apple's iTunes Lookup API and Spotify's Web API have no "
      "play, stream or download counts for an artist's tracks either. The numbers exist "
      "only in each service's artist dashboard, behind your login: Bandcamp's stats and "
      "sales reports, Spotify for Artists, and Apple Music for Artists. If you export one "
      "of those to a CSV and drop it in `cache/` (gitignored), a later step could join it "
      "to `dataset/links.csv` by track URL or title. This step didn't log in anywhere.")
    w("")

    w("## Columns of dataset/links.csv")
    w("")
    w("- `number`, `date`, `title`: the song (title from the songaday-display catalog).")
    w("- `catalog_seconds`: the catalog's Length, which is the video's length.")
    w("- For each of `bandcamp`, `apple_music`, `spotify`: `_url`, `_title` (the track's "
      "title on that service), `_album`, `_match` (exact, fuzzy, position-only or none), "
      "`_score` (title similarity from the fetch step, 0-1), `_seconds` (the track's audio "
      "length on that service), `_confidence` (high, check or none). All of a service's "
      "columns are blank when its step hasn't been run.")
    w("- `flags`: `|`-separated codes: `<service>_weak_match`, `<service>_audio_shifted`, "
      "`<service>_audio_mismatch`, `<service>_title_elsewhere`, `<service>_mislabelled`, "
      "`<service>_ambiguous_title`, `<service>_url_reused`, `bandcamp_no_audio`, "
      "`audio_differs`, `titles_differ`.")
    w("- `notes`: the same in words, `; `-separated.")
    w("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--spotify-csv", type=Path, default=None,
                        help="read Spotify links from this file instead (for testing)")
    args = parser.parse_args()

    songs = load_catalog()
    tables = {}
    for service in SERVICES:
        path = service["csv"]
        if service["key"] == "spotify" and args.spotify_csv:
            path = args.spotify_csv.resolve()
        tables[service["key"]] = load_service(service, path)
        if tables[service["key"]] is None:
            print(f"{service['label']}: {show(path)} not found; its columns stay blank")
    if tables["bandcamp"] is None and tables["apple_music"] is None:
        sys.exit("neither dataset/bandcamp.csv nor dataset/apple_music.csv exists")

    bc_tracks = bandcamp_tracks()
    lengths = {
        "bandcamp": {url: t["seconds"] for url, t in bc_tracks.items()},
        "apple_music": apple_lengths(),
        "spotify": spotify_lengths(),
    }
    for key, found in lengths.items():
        if tables.get(key) is not None and not found:
            print(f"  no cached {LABEL[key]} track lengths; its audio isn't checked")

    links = build_links(songs, tables, lengths)
    confidence, flags, notes, backed_by = check_songs(songs, tables, links)
    reasons = missing_reasons(songs, tables, links, bc_tracks, release_lists())
    write_tables(songs, tables, links, confidence, flags, notes)
    write_report(songs, tables, links, confidence, flags, notes, reasons, backed_by)

    # A short summary on screen.
    for row in coverage_rows(songs, tables, links, confidence)[-1:]:
        for key in LABEL:
            if row[key] is None:
                print(f"{LABEL[key]}: not fetched")
            else:
                print(f"{LABEL[key]}: {row[key][0]} linked, {row[key][1]} high, "
                      f"{row['songs'] - row[key][0]} missing")
        print(f"Any high link: {row['any']} of {row['songs']}")
    kinds = Counter(f for n in songs for f in dict.fromkeys(flags[n]))
    print("Flags: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    for path in (OUT_CSV, SHEET_CSV, REPORT_MD):
        print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
