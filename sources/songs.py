"""The song table: one clean row per Song A Day song, plus a list of cells worth fixing in the
spreadsheet itself.

Sources:
1. Jonathan's public song spreadsheet,
   https://docs.google.com/spreadsheets/d/15BqqJ1TY77jdb9IkLcGrmrBNIpyfbkSwgevtabzQgcA
   Every tab is read from its CSV export (tabs and their gids come from the sheet's htmlview
   page; the .xlsx export is checked too, because it also lists hidden tabs). The sheet has
   one tab. Its rows stop at #5113 and the last filled row is #5101 (2022-12-19), so later
   songs come only from source 2.
2. The songaday-display catalog (its publish/meta folder of index-*.json and detail-*.json
   chunks). It is built from Jonathan's working spreadsheet, which carries on past 2022, and
   it is the more cleaned of the two, so its values win where it has them. The sheet adds the
   main instrument and main style (the first item of each list) and the descriptions.
3. YouTube's public oEmbed endpoint, asked only about the videos the two sources disagree on
   (a few dozen), to see which ID is a live video on Jonathan's channel and what it is titled.
   Answers are cached in cache/sheet/youtube-oembed.json.
4. Optional: songaday-display's output/catalog-report.json. It lists cells that are broken in
   the working spreadsheet (titles that export as URLs, a YouTube ID of "100") and YouTube IDs
   the catalog's own sources disagree on. They go into the fixes list.

Song #N is always dated 2009-01-01 + (N - 1) days. A sheet date that disagrees is reported.

Outputs:
  dataset/songs.csv          one row per song, #1 to the newest song in either source
  analysis/sheet-fixes.csv   number, column, current_value, proposed_value, reason
The sheet is never edited here.

Columns of songs.csv. Lists are "|"-separated, spelled one way (see the alias tables below),
main item first:
  number, date (ISO), weekday, year, title, youtube_id (11 characters, or blank)
  location_raw          the location exactly as written
  topics, instruments, styles, nouns, proper_nouns     lists
  main_instrument, main_style                          the first item of each list
  mood, beard, genre
  length_seconds, tempo_bpm (decimals kept where the sheet has them)
  key                   one spelling per key: C, Db, D, Eb, E, F, F#, G, Ab, A, Bb, B and Cm,
                        C#m, Dm, Ebm, Em, Fm, F#m, Gm, G#m, Am, Bbm, Bm; the first key when
                        several are written
  mode                  major, minor or unknown
  key_raw               the key text as written
  description           Jonathan's own words (songs #4749 on)
  generated_summary     the old gallery's machine-written summary (songs #1-#4748)
  sources               sheet, catalog or sheet+catalog
  flags                 "|"-separated notes on this row's data (see the code for each)

Run:  .venv/bin/python sources/songs.py              (downloads only what isn't cached)
      .venv/bin/python sources/songs.py --refresh    (downloads the spreadsheet again)
      .venv/bin/python sources/songs.py --offline    (cache only, no network)

Paths, all optional:
  SONGADAY_CATALOG_DIR     songaday-display publish/meta folder
                           default ~/Library/Caches/songaday-display/publish/meta
  SONGADAY_CATALOG_REPORT  songaday-display's catalog report
                           default ../songaday-display/output/catalog-report.json
Without the catalog, the table falls back to the sheet alone (songs #1-#5101).
"""

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "sheet"
OEMBED_CACHE = CACHE_DIR / "youtube-oembed.json"
SONGS_CSV = ROOT / "dataset" / "songs.csv"
FIXES_CSV = ROOT / "analysis" / "sheet-fixes.csv"

SHEET_ID = "15BqqJ1TY77jdb9IkLcGrmrBNIpyfbkSwgevtabzQgcA"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
OEMBED_URL = "https://www.youtube.com/oembed"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
REQUEST_PAUSE = 1.0  # seconds between live requests; one request at a time

FIRST_DAY = dt.date(2009, 1, 1)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Descriptions in Jonathan's own words start with song #4749 (2022-01-01), the first sheet row
# with a Description. For #1-#4748 the catalog's descriptions come from the old gallery and are
# machine-written summaries of the lyrics ("This song tells the story of..."), so they go in a
# column of their own, generated_summary, and never in description.
OWN_DESCRIPTIONS_FROM = 4749

# Song runs whose key was logged as the root note only. Songs #212-#271 and #358-#727 (most
# of 2010) have no minor key at all, against about 1 song in 5 everywhere else (a run of 370
# at that rate has odds near 1e-34), and their keys are bare roots written with sharps (A#,
# D#, G#). So the key there is the root, and the mode is "unknown", not "major".
ROOT_ONLY_KEYS = [(212, 271), (358, 727)]

# Jonathan's YouTube channels, as oEmbed reports them in author_url. Song A Day's
# auto-generated "Topic" channel is a different upload of the same audio.
OWN_CHANNELS = ("youtube.com/@jonathanmann", "youtube.com/@songadaymann")

COLUMNS = [
    "number", "date", "weekday", "year", "title", "youtube_id", "location_raw", "topics",
    "main_instrument", "instruments", "mood", "beard", "genre", "main_style", "styles", "nouns",
    "proper_nouns", "length_seconds", "tempo_bpm", "key", "mode", "key_raw", "description",
    "generated_summary", "sources", "flags",
]
FIX_COLUMNS = ["number", "column", "current_value", "proposed_value", "reason"]

# Cell text that means "nothing here": blanks, placeholders and spreadsheet error values.
BLANKS = {"", "-", "--", "?", "na", "n/a", "n//a", "none", "null", "undefined", "#value!",
          "#n/a", "#ref!", "[object object]"}

# ---- Spelling tables ----
# Each list-valued column has a small alias table: a misspelling or variant on the left, the
# spelling to use on the right. A list on the right splits a value that is missing a comma
# ("Bass Drums" is Bass and Drums); an empty list drops a value that is an export artifact.
# Lookups ignore case. After these, every value takes the casing most songs use for it.

TOPIC_ALIASES = {
    "Animal": "Animals", "Poeitc": "Poetic", "Politic": "Politics", "Dream": "Dreams",
    "Friends": "Friend", "Kiera's School": "Keira's School",
    "Internet/AI": ["Internet", "AI"], "Politics/Life": ["Politics", "Life"],
    "Epiphany and Jupiter": ["Epiphany", "Jupiter"], "Politics and Crypto": ["Politics", "Crypto"],
}

INSTRUMENT_ALIASES = {
    "12 String Acoustic Gutiar": "12 String Acoustic Guitar",
    "12-String Acoustic Guitar": "12 String Acoustic Guitar",
    "4 String Acoustic Guitar": "4-String Acoustic Guitar", "4 String Guitar": "4-String Guitar",
    "A capella": "Acapella", "A cappella": "Acapella",
    "Acoustic": "Acoustic Guitar", "Acoustic Guiitar": "Acoustic Guitar",
    "Acoustic Gutiar": "Acoustic Guitar", "Acoutsic Guitar": "Acoustic Guitar",
    "Acoustic Guitar Drums": ["Acoustic Guitar", "Drums"],
    "Acoustic Guitar Samples": ["Acoustic Guitar", "Samples"],
    "Electric Guitar Drums": ["Electric Guitar", "Drums"], "Piano Drums": ["Piano", "Drums"],
    "Drums Samples": ["Drums", "Samples"], "Bass Drums": ["Bass", "Drums"],
    "Bass Drum Machine": ["Bass", "Drum Machine"],
    "AI Generated": "AI", "AI Generated Music": "AI", "Generated With AI": "AI",
    "Baritone Uke": "Baritone Ukulele", "Baritone Ukelele": "Baritone Ukulele",
    "Baritone Ukuele": "Baritone Ukulele", "Bartione Guitar": "Baritone Guitar",
    "Beat Box": "Beatboxing", "Clapping": "Claps",
    "Drum Machin": "Drum Machine", "Drum Machines": "Drum Machine",
    "Drum Mahine": "Drum Machine", "Drums Mahcine": "Drum Machine", "Drusm": "Drums",
    "Elecrtic Guitar": "Electric Guitar", "Electic Guitar": "Electric Guitar",
    "Electr Guitar": "Electric Guitar", "Electrc Guitar": "Electric Guitar",
    "Electric Gutiar": "Electric Guitar",
    "Guialele": "Guitalele", "Guitalale": "Guitalele", "Guitilele": "Guitalele",
    "Guitlele": "Guitalele", "Gutialele": "Guitalele",
    "Keyboard": "Keyboards", "Novox The Robot": "Novox", "Omni Chord": "Omnichord",
    "Orchesrtal": "Orchestral", "Organs": "Organ", "Percuission": "Percussion",
    "Pink Gutiar": "Pink Guitar", "Sample": "Samples", "Saxaphone": "Saxophone",
    "Srtings": "Strings", "Synth": "Synths", "Sythns": "Synths", "Tamborine": "Tambourine",
    "ondes martenot": "Ondes Martenot", "Water bottle": "Water Bottle",
    "Jingle bells": "Jingle Bells",
}

MOOD_ALIASES = {"Excied": "Excited", "Exicted": "Excited"}

GENRE_ALIASES = {
    "A Cappella": "Acapella", "Elecro": "Electro", "Rok": "Rock", "Synthpop": "Synth Pop",
    "Carribean": "Caribbean", "Spoken word": "Spoken Word",
}

STYLE_ALIASES = {
    "8bit": "8Bit", "8-Bit": "8Bit", "A Scary": "Scary", "Anthe": "Anthem", "Broodng": "Brooding",
    "Deliate": "Delicate", "Dissonance": "Dissonant", "Dissonnant": "Dissonant",
    "Distorion": "Distortion", "Distorton": "Distortion", "Distrotion": "Distortion",
    "Distorted": "Distortion", "Dremay": "Dreamy", "Exhasuted": "Exhausted",
    "Foulful": "Soulful", "Soulul": "Soulful", "Frustarted": "Frustrated",
    "Frustrared": "Frustrated", "Funmy": "Funny", "Funn": "Funny", "Funnny": "Funny",
    "Heavt": "Heavy", "Hoepful": "Hopeful", "Hopefuly": "Hopeful", "Hopful": "Hopeful",
    "Impov": "Improv", "Improvised": "Improv", "Lighht": "Light", "Lookming": "Looming",
    "Narraitve": "Narrative", "Narratie": "Narrative", "Nattative": "Narrative",
    "Peronal": "Personal", "Rambliing": "Rambling", "Ramblin": "Rambling",
    "Ramblnig": "Rambling", "Roughl": "Rough", "Shot": "Short", "Wisful": "Wistful",
    "Wistul": "Wistful", "Wostfil": "Wistful", "Werid": "Weird", "Racuous": "Raucous",
    "Raucus": "Raucous", "Recylcing": "Recycling", "Meldoy": "Melody", "Firey": "Fiery",
    "Forboding": "Foreboding", "Sparce": "Sparse", "Full band": "Full Band",
    "Washed out": "Washed Out", "nature": "Nature",
    "Plea Frustrated": ["Plea", "Frustrated"], "Catchy Anthem": ["Catchy", "Anthem"],
    "#VALUE!": [],
}

NOUN_ALIASES = {
    "Commissison": "Commission", "Famous Peron": "Famous Person", "Impov": "Improv",
    "Improvised": "Improv", "Neice": "Niece", "Zomies": "Zombies",
    "My Appearence": "My Appearance", "Assisnation": "Assassination", "Aoology": "Apology",
    "Healthcare": "Health Care", "Furrys": "Furries", "Racoons": "Raccoons",
    "Prarie Dog": "Prairie Dog", "Narwal": "Narwhal", "Wildabeasts": "Wildebeests",
    "Leucochloridium Paradoxm": "Leucochloridium Paradoxum",
    "Presidential Electrion": "Presidential Election", "Food poisoning": "Food Poisoning",
    "Boom box": "Boom Box", "Bad day": "Bad Day", "Real name Policy": "Real Name Policy",
    "hoopsnake": "Hoop Snake",
    "[object Object]": [],
}

PROPER_NOUN_ALIASES = {
    "Alex Jone": "Alex Jones", "Boring Ape Yacht Club": "Bored Ape Yacht Club",
    "David Hoffmann": "David Hoffman", "ETH Denver": "ETHDenver", "EthDenver": "ETHDenver",
    "Friendtech": "friend.tech", "Hester Price": "Hester Peirce",
    "John Siracus": "John Siracusa", "Louie C. Rhymes": "Louie C Rhymes",
    "Seedclub": "Seed Club", "Tech Crunch": "TechCrunch", "Techcrunch": "TechCrunch",
    "Yugalabs": "Yuga Labs", "DeepFuckingValue": "Deep Fucking Value",
    "Frank DeGods": "FrankDeGods", "Meetbits": "Meebits", "Thomas Hughs": "Thomas Hughes",
    "Kiera Mann": "Keira Mann", "Keria Mann": "Keira Mann",  # his niece; "Keira" in most songs
    "FaceBook": "Facebook", "Iphone 4": "iPhone 4",
}

# Field name in this script -> (catalog trait name, public sheet column, alias table).
LIST_FIELDS = {
    "topics": ("Topic", "topic", TOPIC_ALIASES),
    "instruments": ("Instrument", "all instruments", INSTRUMENT_ALIASES),
    "styles": ("Style", "all styles", STYLE_ALIASES),
    "nouns": ("Noun", "noun", NOUN_ALIASES),
    "proper_nouns": ("Proper Noun", "proper noun", PROPER_NOUN_ALIASES),
    "mood": ("Mood", "mood", MOOD_ALIASES),
    "beard": ("Beard", "beard", {}),
    "genre": ("Genre", "genre", GENRE_ALIASES),
}
SINGLE_FIELDS = {"mood", "beard", "genre"}  # one value per song
BEARDS = {"Beard", "Clean", "Shadow", "Mustache", "Goatee"}

# Location typos, for the fixes list only: dataset/songs.csv keeps location_raw as written.
LOCATION_FIXES = {
    "nashville, TN": "Nashville, TN", "Pensacola,FL": "Pensacola, FL",
    "Tuscon, AC": "Tucson, AZ", "Bogota, Columbia": "Bogota, Colombia",
    "Uconn Hostpital": "UConn Hospital", "Weatauge, CT": "Weatogue, CT",
    "Secaucus, NY": "Secaucus, NJ", "Brooklyn navy Yard": "Brooklyn Navy Yard",
}

# ---- Keys ----
# One spelling per key, the usual choice on the circle of fifths: Db major but C# minor,
# Eb minor rather than D# minor, and so on.
NOTE_VALUES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
MAJOR_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]
MODE_WORDS = {"ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian", "locrian",
              "phrygian dominant", "blues", "harmonic minor", "melodic minor"}
KEY_WORDS = {"atonal", "circle of fifths"}  # written on purpose; no single key
CYRILLIC = str.maketrans({"А": "A", "В": "B", "С": "C", "Е": "E", "а": "a", "с": "c", "е": "e"})
KEY_RE = re.compile(r"^(?P<note>[A-Ga-g])\s*(?P<acc>#|b|♯|♭)?\s*"
                    r"(?P<quality>major|minor|maj|min|m)?(?![a-z])\s*(?P<rest>.*)$")

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


# ---- Small helpers ----

def load_dotenv():
    """Read KEY=value lines from this repo's .env, without overriding the real environment."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def clean(value):
    """Trimmed text with runs of whitespace collapsed; "" for blanks and placeholders."""
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text.lower() in BLANKS else text


def split_items(value):
    """A sheet cell ("Synths, Drum Machine") or a catalog list -> list of trimmed items."""
    if value is None:
        return []
    items = value if isinstance(value, list) else re.split(r"[,;|]", str(value))
    return [item for item in (clean(x) for x in items) if item]


def song_date(number):
    return FIRST_DAY + dt.timedelta(days=number - 1)


def fetch(url, path, refresh=False, offline=False, attempts=5):
    """Download url once into path; later runs read the cached copy."""
    if path.exists() and not refresh:
        return path.read_bytes()
    if offline:
        sys.exit(f"--offline, and {path.relative_to(ROOT)} isn't cached yet")
    for attempt in range(attempts):
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(5 * 2 ** attempt)  # back off: 5, 10, 20, 40 s
            continue
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        time.sleep(REQUEST_PAUSE)
        return response.content
    sys.exit(f"gave up on {url} after {attempts} tries")


# ---- The spreadsheet ----

def sheet_tabs(refresh, offline):
    """Every tab of the public sheet: [(name, gid or None, state)].

    The htmlview page names the visible tabs and their gids; the .xlsx export's workbook.xml
    names every tab, hidden ones included (they have no gid there)."""
    html = fetch(f"{SHEET_URL}/htmlview", CACHE_DIR / "htmlview.html", refresh, offline)
    html = html.decode("utf-8", "replace")
    gids = {}
    for name, gid in re.findall(r'items\.push\(\{name: "((?:[^"\\]|\\.)*)", pageUrl: "[^"]*", gid: "(\d+)"', html):
        name = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), name).replace("\\/", "/")
        gids[name] = gid
    xlsx = fetch(f"{SHEET_URL}/export?format=xlsx", CACHE_DIR / "sheet.xlsx", refresh, offline)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as book:
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    tabs = [(s.get("name"), gids.get(s.get("name")), s.get("state", "visible"))
            for s in workbook.find("x:sheets", ns)]
    for name, gid in gids.items():  # a tab the xlsx somehow left out
        if name not in [t[0] for t in tabs]:
            tabs.append((name, gid, "visible"))
    return tabs


def read_tab(gid, refresh, offline):
    """One tab's CSV export -> {song number: {column: cell}}, keyed on the first column.

    The header is the first row with both "date" and "title" (the first tab opens with a note
    row). Its unnamed first column is the song number."""
    data = fetch(f"{SHEET_URL}/export?format=csv&gid={gid}", CACHE_DIR / f"sheet-gid{gid}.csv", refresh, offline)
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    for i, row in enumerate(rows):
        cells = [c.strip().lower() for c in row]
        if "date" in cells and "title" in cells:
            header = [c.strip() for c in row]
            header[0] = header[0] or "number"
            break
    else:
        return {}, 0
    songs = {}
    for row in rows[i + 1:]:
        record = dict(zip(header, row))
        number = record.get("number", "").strip()
        if number.isdigit():
            songs[int(number)] = record
    return songs, len(rows)


def has_content(record):
    """True when a sheet row holds anything past its number and date."""
    return any(clean(v) for k, v in record.items() if k not in ("number", "date"))


def load_sheet(refresh, offline):
    tabs = sheet_tabs(refresh, offline)
    songs, notes = {}, []
    for name, gid, state in tabs:
        if gid is None:
            notes.append(f"tab {name!r} ({state}) has no gid on the htmlview page, so it wasn't read")
            continue
        tab, csv_rows = read_tab(gid, refresh, offline)
        filled = sorted(n for n, r in tab.items() if has_content(r))
        notes.append(f"tab {name!r} (gid {gid}, {state}): {csv_rows} CSV records, {len(tab)} numbered "
                     f"rows #{min(tab, default=0)}-#{max(tab, default=0)}, {len(filled)} filled, "
                     f"last filled #{filled[-1] if filled else '-'}")
        for number, record in tab.items():
            if number not in songs or (has_content(record) and not has_content(songs[number])):
                songs[number] = record
    return songs, notes


# ---- The catalog ----

def load_catalog():
    """songaday-display's index and detail chunks -> ({n: song}, {n: description}).

    Some chunks exist twice under different hashes; a song in more than one file takes its
    entry from the newest file."""
    folder = Path(os.environ.get("SONGADAY_CATALOG_DIR") or
                  Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta")
    if not folder.is_dir():
        return {}, {}, folder

    def chunks(kind):
        out = {}
        for path in sorted(folder.glob(f"{kind}-*.json"), key=lambda p: p.stat().st_mtime):
            for song in json.loads(path.read_text(encoding="utf-8"))["songs"]:
                out[int(song["n"])] = song
        return out

    index = chunks("index")
    details = {n: song.get("description") for n, song in chunks("detail").items()}
    return index, details, folder


def load_catalog_report():
    path = Path(os.environ.get("SONGADAY_CATALOG_REPORT") or
                ROOT.parent / "songaday-display" / "output" / "catalog-report.json")
    if not path.exists():
        return {}, path
    return json.loads(path.read_text(encoding="utf-8")), path


# ---- Normalizers ----

def youtube_candidate(value):
    """The video ID in a bare ID or a youtube.com / youtu.be link (not checked for length)."""
    text = clean(value)
    if YOUTUBE_ID_RE.match(text):
        return text
    match = re.search(r"(?:youtu\.be/|[?&]v=|/embed/|/shorts/|/live/)([^?&/#\s]+)", text)
    return match.group(1) if match else text


def is_junk_title(title):
    """A linked cell exports its URL; a cell read as a time exports an 1899 date."""
    return bool(re.match(r"(?i)https?://", title)) or bool(re.search(r"\b1899\b.*GMT", title))


def title_from_url(title):
    text = re.sub(r"(?i)^(https?://)?(www\.)?", "", title).rstrip("/")
    return text[:1].upper() + text[1:]


def parse_length(value, repair=False):
    """"2:36" or "1:02:03" -> seconds. repair=True also reads the sheet's slips ("1.21", ":50")."""
    text = clean(value)
    if repair:
        text = re.sub(r"[.;]", ":", text)
        text = re.sub(r"^:", "0:", text)
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", text)
    if not match or int(match.group(3)) >= 60:
        return None
    hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_length(seconds):
    if seconds is None:
        return ""
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_tempo(value):
    """"124" or "99.546" -> float; "105/125" (a tempo change) -> 105 plus a flag."""
    numbers = re.findall(r"\d+(?:\.\d+)?", clean(value))
    if not numbers:
        return None, ""
    return float(numbers[0]), ("tempo_multiple" if len(numbers) > 1 else "")


def format_number(x):
    if x is None:
        return ""
    return str(int(x)) if float(x).is_integer() else f"{x:.3f}".rstrip("0")


def fix_key_text(text):
    """Undo two kinds of damage seen in the key column: a Cyrillic С typed for C, and the same
    letter's UTF-8 bytes read as Mac Roman ("–°")."""
    try:
        text = text.encode("mac_roman").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text.translate(CYRILLIC)


def parse_key(value):
    """Key text as written -> (key, mode, flags).

    The first key wins when several are written ("Em/G" -> Em). Unreadable text gives no key;
    "Atonal" and "Circle of Fifths" are left as written in key_raw with no key."""
    text = fix_key_text(clean(value))
    if not text:
        return "", "unknown", []
    parts = [p for p in re.split(r"\s*(?:/|,|&|\band\b|\bor\b)\s*", text) if p]
    flags = ["key_multiple"] if len(parts) > 1 else []
    if text.lower() in KEY_WORDS:
        return "", "unknown", flags
    match = KEY_RE.match(parts[0]) if parts else None
    if not match:
        return "", "unknown", flags + ["key_unreadable"]
    rest = match.group("rest").strip().lower()
    mode_word = rest in MODE_WORDS
    if rest in ("?", "-ish", "ish"):
        flags.append("key_uncertain")
    elif rest and not mode_word:
        return "", "unknown", flags + ["key_unreadable"]
    pitch = NOTE_VALUES[match.group("note").upper()]
    pitch += {"#": 1, "♯": 1, "b": -1, "♭": -1}.get(match.group("acc") or "", 0)
    minor = (match.group("quality") or "").lower() in ("m", "min", "minor")
    key = (MINOR_NAMES if minor else MAJOR_NAMES)[pitch % 12]
    if mode_word:
        return key, "unknown", flags
    return key, ("minor" if minor else "major"), flags


# ---- Spelling ----

class Spelling:
    """Alias tables plus the casing most songs use, per field."""

    def __init__(self):
        self.aliases = {field: {k.lower(): v for k, v in table.items()}
                        for field, (_, _, table) in LIST_FIELDS.items()}
        self.casing = {}

    def alias(self, field, items):
        out = []
        for item in items:
            new = self.aliases[field].get(item.lower(), item)
            out.extend(new if isinstance(new, list) else [new])
        return out

    def learn(self, field_values):
        """field_values: {field: [list of items per song]} after aliases. For each value, the
        casing used by the most songs wins (ties: the one with more capitals, then A-Z)."""
        for field, lists in field_values.items():
            counts = Counter(item for items in lists for item in items)
            by_lower = defaultdict(list)
            for item, count in counts.items():
                by_lower[item.lower()].append((-count, -sum(ch.isupper() for ch in item), item))
            self.casing[field] = {low: sorted(options)[0][2] for low, options in by_lower.items()}

    def normalize(self, field, items):
        """Raw items -> aliased, consistently cased, de-duplicated (first one kept)."""
        out, seen = [], set()
        for item in self.alias(field, items):
            item = self.casing.get(field, {}).get(item.lower(), item)
            if item.lower() not in seen:
                seen.add(item.lower())
                out.append(item)
        return out

    def explain(self, field, items):
        """Why normalize() changes these items, as short notes for the fixes list."""
        notes, seen = [], set()
        for item in items:
            alias = self.aliases[field].get(item.lower())
            if alias is not None:
                target = " + ".join(f'"{a}"' for a in alias) if isinstance(alias, list) else f'"{alias}"'
                notes.append(f'"{item}" -> {target}' if alias != [] else f'drop "{item}" (export artifact)')
            elif item.lower() in seen:
                notes.append(f'"{item}" is listed twice')
            else:
                cased = self.casing.get(field, {}).get(item.lower(), item)
                if cased != item:
                    notes.append(f'"{item}" -> "{cased}" (the spelling most songs use)')
            seen.add(item.lower())
        return "; ".join(notes)


# ---- YouTube ----

def youtube_lookup(video_ids, offline):
    """oEmbed answers for these IDs: {id: {status, title, author, author_url}}, cached."""
    cache = json.loads(OEMBED_CACHE.read_text(encoding="utf-8")) if OEMBED_CACHE.exists() else {}
    todo = [v for v in dict.fromkeys(video_ids) if v not in cache]
    if todo and offline:
        print(f"  --offline: {len(todo)} YouTube IDs not checked")
        return cache
    for i, video_id in enumerate(todo):
        params = {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
        for attempt in range(5):
            response = requests.get(OEMBED_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(5 * 2 ** attempt)
                continue
            break
        entry = {"status": response.status_code, "checked": dt.date.today().isoformat()}
        if response.ok:
            info = response.json()
            entry.update(title=info.get("title"), author=info.get("author_name"), author_url=info.get("author_url"))
        cache[video_id] = entry
        OEMBED_CACHE.parent.mkdir(parents=True, exist_ok=True)
        OEMBED_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        if i < len(todo) - 1:
            time.sleep(REQUEST_PAUSE)
    return cache


def on_own_channel(answer):
    return bool(answer) and answer.get("status") == 200 and \
        any(c in (answer.get("author_url") or "").lower() for c in OWN_CHANNELS)


def describe_video(video_id, answers):
    answer = answers.get(video_id)
    if not answer:
        return f"{video_id} (not checked)"
    if answer.get("status") != 200:
        return f"{video_id} (YouTube answers {answer.get('status')}: private, removed or no such video)"
    return f'{video_id} ("{answer.get("title")}" on {answer.get("author")})'


def title_in(title, video_title):
    """True when the YouTube title contains this song title (case and spacing ignored)."""
    squash = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    return bool(title) and squash(title) in squash(video_title or "")


# ---- Building the table ----

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--refresh", action="store_true", help="download the spreadsheet again")
    parser.add_argument("--offline", action="store_true", help="use cached files only")
    args = parser.parse_args()
    load_dotenv()

    print("Spreadsheet")
    sheet, tab_notes = load_sheet(args.refresh, args.offline)
    for note in tab_notes:
        print("  " + note)
    sheet_filled = {n for n, r in sheet.items() if has_content(r)}

    catalog, details, catalog_dir = load_catalog()
    print(f"Catalog: {len(catalog)} songs from {catalog_dir}" if catalog else
          f"Catalog: not found at {catalog_dir}; using the sheet alone")
    report, report_path = load_catalog_report()
    print(f"Catalog report: {'read' if report else 'not found'} ({report_path})")

    numbers = sorted(sheet_filled | set(catalog))
    numbers = list(range(1, max(numbers) + 1))
    fixes = []

    def fix(number, column, current, proposed, reason):
        fixes.append({"number": number, "column": column, "current_value": current,
                      "proposed_value": proposed, "reason": reason})

    # Which YouTube IDs need a second opinion: the two sources disagree, the sheet's is
    # malformed, two songs share one, the titles disagree, or the catalog report names a
    # conflict between the working sheet and the catalog's other sources.
    report_alternatives = defaultdict(set)
    for item in (report.get("youtube") or {}).get("conflictSample", []):
        for video_id in item.get("ids", {}).values():
            if YOUTUBE_ID_RE.match(video_id or ""):
                report_alternatives[int(item["n"])].add(video_id)
    to_check, owners = [], defaultdict(list)
    for n in numbers:
        s, c = sheet.get(n, {}), catalog.get(n, {})
        options = [v for v in (c.get("yt"), youtube_candidate(s.get("videoID")) if n in sheet_filled else None)
                   if v and YOUTUBE_ID_RE.match(v)]
        options += sorted(report_alternatives.get(n, ()))
        if c.get("yt"):
            owners[c["yt"]].append(n)
        sheet_title, catalog_title = clean(s.get("title")), clean(c.get("t"))
        title_dispute = n in sheet_filled and catalog_title and sheet_title != catalog_title
        if len(set(options)) > 1 or title_dispute or \
                (n in sheet_filled and not YOUTUBE_ID_RE.match(youtube_candidate(s.get("videoID")))):
            to_check += options
    to_check += [v for v, ns in owners.items() if len(ns) > 1]
    print(f"YouTube: checking {len(set(to_check))} disputed IDs with oEmbed")
    answers = youtube_lookup(to_check, args.offline)

    # Pass 1: pick each field's raw value per song, best source first.
    drafts = []
    for n in numbers:
        s = sheet.get(n, {}) if n in sheet_filled else {}
        c = catalog.get(n, {})
        a = c.get("a", {})
        draft = {"number": n, "sheet": s, "catalog": c, "flags": []}

        # Title: the catalog's, unless it is an export artifact; YouTube settles disagreements.
        catalog_title, sheet_title = clean(c.get("t")), clean(s.get("title"))
        options = [t for t in (catalog_title, sheet_title) if t and not is_junk_title(t)]
        draft["title"] = options[0] if options else title_from_url(catalog_title or sheet_title)
        draft["title_evidence"] = ""
        if catalog_title and sheet_title and catalog_title != sheet_title:
            draft["flags"].append("title_conflict")

        # YouTube ID: prefer one that is live on Jonathan's channel.
        sheet_video = youtube_candidate(s.get("videoID")) if s else ""
        options = [v for v in dict.fromkeys([c.get("yt"), sheet_video, *sorted(report_alternatives.get(n, ()))])
                   if v and YOUTUBE_ID_RE.match(v)]
        chosen = next((v for v in options if on_own_channel(answers.get(v))), None) or \
            next((v for v in options if (answers.get(v) or {}).get("status") == 200), None) or \
            (options[0] if options else "")
        draft["youtube_id"] = chosen
        if len(options) > 1:
            draft["flags"].append("youtube_conflict")
        if not chosen:
            draft["flags"].append("youtube_missing")
        if s and clean(s.get("videoID")) and not YOUTUBE_ID_RE.match(sheet_video):
            draft["flags"].append("sheet_youtube_malformed")
        draft["sheet_video"] = sheet_video

        # A title dispute is settled by the chosen video's YouTube title when it matches a side;
        # when both match ("tsowf.tumblr.com" sits inside "www.tsowf.tumblr.com"), the longer.
        if "title_conflict" in draft["flags"]:
            video_title = (answers.get(chosen) or {}).get("title")
            matches = [t for t in (catalog_title, sheet_title)
                       if t and not is_junk_title(t) and title_in(t, video_title)]
            if matches:
                draft["title"] = max(matches, key=len)
                draft["title_evidence"] = f'YouTube title "{video_title}"'

        # Lists and single-valued traits, as raw items (the catalog first).
        for field, (trait, column, _) in LIST_FIELDS.items():
            items = split_items(a.get(trait))
            draft[field + "_raw"] = items if items else split_items(s.get(column))
            draft[field + "_sheet"] = split_items(s.get(column)) if s else None

        # Location exactly as written: the sheet's cell when the sheet has the song.
        draft["location_raw"] = s.get("location", "") if s else (a.get("Location") or "")

        # Length: the catalog's, else the sheet's with its slips repaired.
        draft["length"] = parse_length(a.get("Length"))
        if draft["length"] is None:
            draft["length"] = parse_length(s.get("length"), repair=True)
        length_text = clean(a.get("Length")) or clean(s.get("length"))
        if draft["length"] is None and length_text:
            draft["flags"].append("length_unreadable")

        # Tempo: the sheet's when it agrees with the catalog (it keeps the decimals).
        catalog_tempo, catalog_flag = parse_tempo(a.get("Tempo"))
        sheet_tempo, sheet_flag = parse_tempo(s.get("tempo"))
        if catalog_tempo is not None and sheet_tempo is not None and abs(catalog_tempo - sheet_tempo) >= 1:
            draft["flags"].append("tempo_conflict")
            draft["tempo"], tempo_flag = catalog_tempo, catalog_flag
        elif sheet_tempo is not None:
            draft["tempo"], tempo_flag = sheet_tempo, sheet_flag
        else:
            draft["tempo"], tempo_flag = catalog_tempo, catalog_flag
        if tempo_flag:
            draft["flags"].append(tempo_flag)

        # Key: the catalog's value parsed, else the sheet's; key_raw keeps the sheet's text.
        draft["key_raw"] = s.get("inKey", "").strip() if s else clean(a.get("Key"))
        key, mode, key_flags = parse_key(a.get("Key"))
        if not key and not clean(a.get("Key")):
            key, mode, key_flags = parse_key(s.get("inKey"))
        if mode == "major" and any(lo <= n <= hi for lo, hi in ROOT_ONLY_KEYS):
            mode = "unknown"
            key_flags.append("mode_not_recorded")
        draft["key"], draft["mode"] = key, mode
        draft["flags"] += key_flags

        # Descriptions: Jonathan's own words, and the old gallery's generated summaries apart.
        sheet_description = (s.get("Description") or "").strip()
        catalog_description = (details.get(n) or "").strip()
        if clean(sheet_description):
            draft["description"] = sheet_description
        elif n >= OWN_DESCRIPTIONS_FROM:
            draft["description"] = catalog_description
        else:
            draft["description"] = ""
        draft["generated_summary"] = catalog_description if n < OWN_DESCRIPTIONS_FROM else ""

        draft["sources"] = "+".join(name for name, ok in (("sheet", bool(s)), ("catalog", bool(c))) if ok)

        # The sheet's date column should be the song's date.
        if s and clean(s.get("date")):
            try:
                written = dt.datetime.strptime(clean(s["date"]), "%m/%d/%Y").date()
            except ValueError:
                written = None
            if written != song_date(n):
                draft["flags"].append("date_mismatch")
                fix(n, "date", s["date"], f"{song_date(n).month}/{song_date(n).day}/{song_date(n).year}",
                    f"song #{n} is {song_date(n).isoformat()} (2009-01-01 + {n - 1} days)")
        drafts.append(draft)

    # Pass 2: consistent spelling across all songs, then the final rows.
    spelling = Spelling()
    spelling.learn({field: [spelling.alias(field, d[field + "_raw"]) for d in drafts] for field in LIST_FIELDS})

    rows = []
    for d in drafts:
        n, s = d["number"], d["sheet"]
        values = {field: spelling.normalize(field, d[field + "_raw"]) for field in LIST_FIELDS}
        beard = values["beard"][0] if values["beard"] else ""
        if beard and beard not in BEARDS:
            d["flags"].append("beard_invalid")
            values["beard"] = []
        date = song_date(n)
        rows.append({
            "number": n,
            "date": date.isoformat(),
            "weekday": WEEKDAYS[date.weekday()],
            "year": date.year,
            "title": d["title"],
            "youtube_id": d["youtube_id"],
            "location_raw": d["location_raw"],
            "topics": "|".join(values["topics"]),
            "main_instrument": values["instruments"][0] if values["instruments"] else "",
            "instruments": "|".join(values["instruments"]),
            "mood": values["mood"][0] if values["mood"] else "",
            "beard": values["beard"][0] if values["beard"] else "",
            "genre": values["genre"][0] if values["genre"] else "",
            "main_style": values["styles"][0] if values["styles"] else "",
            "styles": "|".join(values["styles"]),
            "nouns": "|".join(values["nouns"]),
            "proper_nouns": "|".join(values["proper_nouns"]),
            "length_seconds": "" if d["length"] is None else d["length"],
            "tempo_bpm": format_number(d["tempo"]),
            "key": d["key"],
            "mode": d["mode"],
            "key_raw": d["key_raw"],
            "description": d["description"],
            "generated_summary": d["generated_summary"],
            "sources": d["sources"],
            "flags": "",  # filled in below, after the duplicate-video check
        })
        d["values"] = values

    # Two songs sharing one video: the one whose title the video carries keeps it.
    by_video = defaultdict(list)
    for row in rows:
        if row["youtube_id"]:
            by_video[row["youtube_id"]].append(row)
    for video_id, shared in by_video.items():
        if len(shared) < 2:
            continue
        video_title = (answers.get(video_id) or {}).get("title")
        keepers = [r for r in shared if title_in(r["title"], video_title)]
        for row in shared:
            d = drafts[row["number"] - 1]
            d["flags"].append("youtube_duplicate")
            if keepers and row not in keepers:
                row["youtube_id"] = ""
                d["flags"].append("youtube_wrong_video")
                fix(row["number"], "videoID", d["sheet_video"] or video_id, "(find this song's video)",
                    f"{describe_video(video_id, answers)} is song #{keepers[0]['number']}'s video")

    for row, d in zip(rows, drafts):
        row["flags"] = "|".join(dict.fromkeys(d["flags"]))

    # ---- The fixes list ----
    working = "not in the public sheet; value from the working spreadsheet via the catalog"
    for row, d in zip(rows, drafts):
        n, s, c, values = row["number"], d["sheet"], d["catalog"], d["values"]
        in_sheet = bool(s)
        note = "" if in_sheet else f" ({working})"

        # Title
        if in_sheet and clean(s.get("title")) != row["title"]:
            evidence = d["title_evidence"] or (f"the catalog has \"{clean(c.get('t'))}\"" if c else "")
            fix(n, "title", s.get("title"), row["title"], f"title doesn't match this song; {evidence}".rstrip("; "))
        elif not in_sheet and clean(c.get("t")) and clean(c.get("t")) != row["title"]:
            fix(n, "title", c.get("t"), row["title"], "cell exports as a URL or a date" + note)

        # YouTube ID
        current_video = d["sheet_video"] if in_sheet else (c.get("yt") or "")
        raw_video = s.get("videoID", "").strip() if in_sheet else current_video
        if row["youtube_id"] and current_video != row["youtube_id"] and "youtube_wrong_video" not in d["flags"]:
            if not YOUTUBE_ID_RE.match(current_video or ""):
                why = f'"{current_video}" isn\'t an 11-character video ID'
            else:
                why = f"{describe_video(current_video, answers)}"
            fix(n, "videoID", raw_video, row["youtube_id"],
                f"{why}; use {describe_video(row['youtube_id'], answers)}" + note)

        # Lists: typos, variants, duplicates, missing commas, export artifacts.
        for field, (_, column, _) in LIST_FIELDS.items():
            current = d[field + "_sheet"] if in_sheet else split_items((c.get("a") or {}).get(LIST_FIELDS[field][0]))
            if current is None:
                continue
            proposed = values[field]
            if field == "beard" and "beard_invalid" in d["flags"]:
                before = rows[n - 2]["beard"] if n > 1 else ""
                after = rows[n]["beard"] if n < len(rows) else ""
                guess = before if before and before == after else "(fill in)"
                fix(n, column, ", ".join(current), guess,
                    f"not a beard value (Beard, Clean, Shadow, Mustache or Goatee); songs #{n - 1} and #{n + 1} say {before or '?'} and {after or '?'}" + note)
                continue
            if current != proposed:
                why = spelling.explain(field, current) or "differs from the catalog"
                fix(n, column, ", ".join(current), ", ".join(proposed), why + note)

        # The sheet's main/other columns should split its all-instruments / all-styles list.
        if in_sheet:
            for field, main_col, other_col, all_col in (("instruments", "main instrument", "other instruments", "all instruments"),
                                                        ("styles", "main style", "other styles", "all styles")):
                items = values[field]
                main, other = (items[0] if items else ""), ", ".join(items[1:])
                current_main, current_other = split_items(s.get(main_col)), split_items(s.get(other_col))
                if [x.lower() for x in current_main] != ([main.lower()] if main else []):
                    fix(n, main_col, s.get(main_col, ""), main,
                        spelling.explain(field, current_main) or f"should be the first item of {all_col}")
                if [x.lower() for x in current_other] != [x.lower() for x in items[1:]]:
                    strays = [x for x in current_other if x.lower() not in [i.lower() for i in items]]
                    stray_note = f" ({', '.join(f'{x!r}' for x in strays)} isn't in {all_col})" if strays else ""
                    fix(n, other_col, s.get(other_col, ""), other,
                        spelling.explain(field, current_other) or f"should be {all_col} minus the main one{stray_note}")

        # Locations with a typo.
        location = clean(row["location_raw"])
        if location in LOCATION_FIXES:
            fix(n, "location", row["location_raw"], LOCATION_FIXES[location], "spelling" + note)

        # Length: malformed in the sheet, or different from the catalog.
        current_length = clean(s.get("length")) if in_sheet else clean((c.get("a") or {}).get("Length"))
        proposed_length = format_length(row["length_seconds"] if row["length_seconds"] != "" else None)
        if current_length and proposed_length and parse_length(current_length) != row["length_seconds"]:
            if parse_length(current_length) is not None:
                why = "differs from the catalog"
            elif parse_length(current_length, repair=True) == row["length_seconds"]:
                why = "not m:ss"
            else:
                why = f"not m:ss, and the catalog has {proposed_length}"
            fix(n, "length", s.get("length", "") if in_sheet else current_length, proposed_length, why + note)
        elif current_length and not proposed_length:
            fix(n, "length", current_length, "(fill in)", "not a readable m:ss length" + note)

        # Key: damaged letters, unreadable text.
        current_key = (s.get("inKey", "").strip() if in_sheet else clean((c.get("a") or {}).get("Key")))
        if current_key and clean(current_key) and fix_key_text(current_key) != current_key:
            fix(n, "inKey", current_key, fix_key_text(current_key), "the letter C is a look-alike character (Cyrillic С or its garbled bytes)" + note)
        elif "key_unreadable" in d["flags"]:
            fix(n, "inKey", current_key, "(fill in)", "not a readable key" + note)

        # Tempo: text that isn't a number.
        current_tempo = s.get("tempo", "").strip() if in_sheet else clean((c.get("a") or {}).get("Tempo"))
        if clean(current_tempo) and not re.fullmatch(r"\d+(\.\d+)?", clean(current_tempo)) and "tempo_multiple" not in d["flags"]:
            fix(n, "tempo", current_tempo, row["tempo_bpm"] or "(fill in)", "not a number" + note)

        # Empty core cells (including "na" placeholders).
        for column, value, current in (
                ("title", row["title"], s.get("title") if in_sheet else c.get("t")),
                ("videoID", row["youtube_id"], s.get("videoID") if in_sheet else c.get("yt")),
                ("location", clean(row["location_raw"]), row["location_raw"]),
                ("topic", row["topics"], s.get("topic") if in_sheet else ""),
                ("all instruments", row["instruments"], s.get("all instruments") if in_sheet else ""),
                ("mood", row["mood"], s.get("mood") if in_sheet else ""),
                ("beard", row["beard"] or ("x" if "beard_invalid" in d["flags"] else ""), s.get("beard") if in_sheet else ""),
                ("genre", row["genre"], s.get("genre") if in_sheet else ""),
                ("all styles", row["styles"], s.get("all styles") if in_sheet else ""),
                ("length", row["length_seconds"] if "length_unreadable" not in d["flags"] else "x", s.get("length") if in_sheet else ""),
                ("inKey", row["key_raw"] if clean(row["key_raw"]) else "", s.get("inKey") if in_sheet else ""),
                ("tempo", row["tempo_bpm"], s.get("tempo") if in_sheet else "")):
            if value in ("", None) and "youtube_wrong_video" not in d["flags"]:
                written = (current or "").strip()
                fix(n, column, written, "(fill in)",
                    (f'missing (written as "{written}")' if written else "missing") + note)

    # Cells that are broken only in the working spreadsheet, from songaday-display's report.
    already = {(f["number"], f["column"]) for f in fixes}
    for item in report.get("titleConflicts", []):
        d1 = item.get("d1") or ""
        if is_junk_title(d1) and (item["n"], "title") not in already and item["n"] <= len(rows):
            fix(item["n"], "title", d1, rows[item["n"] - 1]["title"],
                "working spreadsheet: the cell exports as a URL or an 1899 date (a hyperlinked or time-formatted cell)"
                + ("; the public sheet has the text" if item["n"] in sheet_filled else ""))
    for item in ((report.get("youtube") or {}).get("malformedBySource") or {}).get("d1", []):
        n = int(item["n"])
        if (n, "videoID") not in already and n <= len(rows):
            fix(n, "videoID", item.get("value"), rows[n - 1]["youtube_id"] or "(fill in)",
                "working spreadsheet: not a video ID"
                + ("; the public sheet has the right one" if n in sheet_filled else ""))

    # One note for the rows the public sheet doesn't have.
    last_filled = max(sheet_filled) if sheet_filled else 0
    if catalog and max(catalog) > last_filled:
        blank_rows = sorted(n for n in sheet if n not in sheet_filled)
        fix(last_filled + 1, "(whole row)", f"rows #{blank_rows[0]}-#{blank_rows[-1]} blank, no rows after" if blank_rows else "no rows",
            f"songs #{last_filled + 1}-#{max(catalog)}",
            f"the public sheet stops at #{last_filled} ({song_date(last_filled).isoformat()}); the later songs are only in the working spreadsheet")

    order = {c: i for i, c in enumerate(["(whole row)", "date", "title", "videoID", "location", "topic", "all instruments",
                                          "main instrument", "other instruments", "mood", "beard", "genre", "all styles",
                                          "main style", "other styles", "noun", "proper noun", "length", "inKey", "tempo"])}
    fixes.sort(key=lambda f: (f["number"], order.get(f["column"], 99)))

    # ---- Write ----
    SONGS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with SONGS_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    FIXES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with FIXES_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIX_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(fixes)

    # ---- Report ----
    print(f"\nWrote {SONGS_CSV.relative_to(ROOT)}: {len(rows)} songs, #1-#{rows[-1]['number']} "
          f"({rows[0]['date']} to {rows[-1]['date']})")
    print("  sources: " + ", ".join(f"{k} {v}" for k, v in Counter(r["sources"] for r in rows).most_common()))
    print("  filled: " + ", ".join(f"{col} {sum(1 for r in rows if r[col] != '')}" for col in COLUMNS[4:24]))
    flag_counts = Counter(f for r in rows for f in r["flags"].split("|") if f)
    print("  flags: " + (", ".join(f"{k} {v}" for k, v in flag_counts.most_common()) or "none"))
    print(f"Wrote {FIXES_CSV.relative_to(ROOT)}: {len(fixes)} cells")
    print("  by column: " + ", ".join(f"{k} {v}" for k, v in Counter(f["column"] for f in fixes).most_common()))


if __name__ == "__main__":
    main()
