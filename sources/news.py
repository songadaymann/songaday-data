"""What was in the news on each Song A Day date, and which songs mention it.

Source: English Wikipedia's "Portal:Current events" daily pages
("Portal:Current events/2009 January 1", ...), CC BY-SA 4.0. Each day page lists that day's
headlines under section names such as "Armed conflicts and attacks" or "Sports".

Steps:
1. Fetch the wikitext of every daily page from 2009-01-01 to the day before today's song,
   through the MediaWiki API, one request per month (up to 31 titles per request). Raw API
   responses are cached in cache/news/daily/YYYY-MM.json, so reruns never refetch.
2. Parse each day into headline items: the section each sits in, its plain text, and the
   Wikipedia article titles it links to.
3. Write dataset/news.csv: one row per day, with item counts per section and up to five
   short headlines.
4. Match each song (title, proper nouns, nouns, description) against the articles linked in
   that day's and the previous two days' items, and write dataset/news_matches.csv.

Run:  .venv/bin/python sources/news.py            (fetches what is missing, then builds)
      .venv/bin/python sources/news.py --offline  (cache only, no network)
      .venv/bin/python sources/news.py --refresh-recent  (refetch months that were still
                                                          being edited when cached)

The song catalog comes from the songaday-display publish/meta folder (index-*.json and
detail-*.json chunks); set SONGADAY_CATALOG_DIR to point somewhere else.
"""

import argparse
import bisect
import calendar
import csv
import datetime as dt
import glob
import html
import json
import math
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "news" / "daily"
DATASET_DIR = ROOT / "dataset"
NEWS_CSV = DATASET_DIR / "news.csv"
MATCHES_CSV = DATASET_DIR / "news_matches.csv"

CATALOG_DIR = Path(
    os.environ.get("SONGADAY_CATALOG_DIR")
    or Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta"
)

API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"

FIRST_DAY = dt.date(2009, 1, 1)  # song #1
LAST_DAY = dt.date(2026, 10, 20)  # the day before today's song (#6503 on 2026-10-21)

# Pause between live API requests, in seconds. The API is free; one request at a time.
REQUEST_PAUSE = 1.0


# ---------------------------------------------------------------------------
# 1. Fetching
# ---------------------------------------------------------------------------


def day_title(day):
    """The daily page title, e.g. "Portal:Current events/2009 January 1"."""
    return f"Portal:Current events/{day.year} {calendar.month_name[day.month]} {day.day}"


def month_days(year, month):
    """Every date in a month that falls inside FIRST_DAY..LAST_DAY."""
    n_days = calendar.monthrange(year, month)[1]
    days = [dt.date(year, month, d) for d in range(1, n_days + 1)]
    return [d for d in days if FIRST_DAY <= d <= LAST_DAY]


def all_months():
    """(year, month) pairs from FIRST_DAY's month to LAST_DAY's month."""
    year, month = FIRST_DAY.year, FIRST_DAY.month
    while (year, month) <= (LAST_DAY.year, LAST_DAY.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def api_get(session, params):
    """One API GET with retries: backs off on HTTP 429/5xx and on the API's maxlag error."""
    for attempt in range(8):
        try:
            response = session.get(API_URL, params=params, timeout=60)
        except requests.RequestException as error:
            wait = 2 ** attempt
            print(f"  network error ({error}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            wait = int(response.headers.get("Retry-After") or 2 ** (attempt + 1))
            print(f"  HTTP {response.status_code}; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        response.raise_for_status()
        data = response.json()
        if data.get("error", {}).get("code") == "maxlag":
            wait = int(response.headers.get("Retry-After") or 5)
            print(f"  server lagged; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if "error" in data:
            raise RuntimeError(f"API error: {data['error']}")
        return data
    raise RuntimeError(f"gave up after retries: {params.get('titles', '')[:80]}")


def fetch_month(session, year, month):
    """Fetch the wikitext of every daily page in one month (all titles in one query).

    Returns the list of raw API responses (more than one if the API asked to continue).
    """
    titles = [day_title(d) for d in month_days(year, month)]
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content|ids|timestamp",
        "rvslots": "main",
        "titles": "|".join(titles),
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
        "maxlag": 5,
    }
    responses = []
    cont = {}
    while True:
        data = api_get(session, {**params, **cont})
        responses.append(data)
        if "continue" not in data:
            break
        cont = data["continue"]
        time.sleep(REQUEST_PAUSE)
    return titles, responses


def cache_path(year, month):
    return CACHE_DIR / f"{year:04d}-{month:02d}.json"


def is_stale(cached, year, month):
    """A month cached before it had ended (plus a week of late edits) may be incomplete."""
    fetched = dt.datetime.fromisoformat(cached["fetched"]).date()
    last = dt.date(year, month, calendar.monthrange(year, month)[1])
    return fetched < last + dt.timedelta(days=7)


def fetch_all(offline=False, refresh_recent=False):
    """Make sure every month is in the cache. Returns {date: wikitext or None}."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    fetched_now = 0
    texts = {}
    for year, month in all_months():
        path = cache_path(year, month)
        cached = json.loads(path.read_text()) if path.exists() else None
        need = cached is None or (refresh_recent and is_stale(cached, year, month))
        # A cached month that was cut off by LAST_DAY may lack days we now want.
        if cached is not None and set(cached["titles"]) != {day_title(d) for d in month_days(year, month)}:
            need = True
        if need and not offline:
            if fetched_now:
                time.sleep(REQUEST_PAUSE)
            titles, responses = fetch_month(session, year, month)
            cached = {
                "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "titles": titles,
                "responses": responses,
            }
            path.write_text(json.dumps(cached, ensure_ascii=False))
            fetched_now += 1
            print(f"fetched {year}-{month:02d} ({len(titles)} days)")
        if cached is None:
            continue
        texts.update(texts_from_cache(cached))
    print(f"{fetched_now} months fetched from Wikipedia, the rest from cache")
    return texts


def texts_from_cache(cached):
    """{date: wikitext} for one cached month; None for pages that do not exist."""
    by_title = {}
    redirects = {}
    for data in cached["responses"]:
        query = data.get("query", {})
        for r in query.get("redirects", []):
            redirects[r["from"]] = r["to"]
        for norm in query.get("normalized", []):
            redirects.setdefault(norm["from"], norm["to"])
        for page in query.get("pages", []):
            revs = page.get("revisions")
            if revs:
                by_title[page["title"]] = revs[0]["slots"]["main"]["content"]
            else:
                by_title.setdefault(page["title"], None)
    out = {}
    for title in cached["titles"]:
        target = redirects.get(title, title)
        target = redirects.get(target, target)
        day = dt.datetime.strptime(title.split("/", 1)[1], "%Y %B %d").date()
        out[day] = by_title.get(target)
    return out




# ---------------------------------------------------------------------------
# 2. Parsing a day's wikitext into headline items
# ---------------------------------------------------------------------------

# Canonical sections. The portal's section names drifted over the years ("Disasters",
# "Sport", "Arts, culture and entertainment", "Health" ...); SECTION_RULES maps each raw name
# to one of these, first match wins. Anything else is "other".
SECTIONS = [
    "armed_conflicts",
    "arts_culture",
    "business_economy",
    "disasters_accidents",
    "health_environment",
    "international_relations",
    "law_crime",
    "politics_elections",
    "science_technology",
    "sports",
]
SECTION_RULES = [
    ("sports", r"sport"),
    ("armed_conflicts", r"conflict|attack|\bwar\b|terror"),
    ("disasters_accidents", r"disaster|accident|^weather$"),
    ("international_relations", r"international|diplomac|foreign"),
    ("politics_elections", r"politic|election|government"),
    ("law_crime", r"\blaws?\b|crime|justice|arrest|prosecut|detention"),
    ("business_economy", r"business|econom|financ"),
    ("science_technology", r"science|technolog|discover|\bspace\b|physics|exploration|"
                           r"internet|natural history"),
    ("health_environment", r"health|environment|ecolog|medic|climate"),
    ("arts_culture", r"\barts?\b|culture|entertainment|\bmedia\b|television|movie|film|"
                     r"literature|music"),
]
# Headings that say nothing about the topic; their items are treated as unsectioned.
GENERIC_HEADINGS = {"current events", "news", "general news", "other", "other current events"}


def section_slug(label):
    """Map a raw section heading to a canonical slug ("other" if nothing fits, None for a
    heading such as "Current events" that says nothing about the topic)."""
    label = label.lower().strip()
    if label in GENERIC_HEADINGS:
        return None
    for slug, pattern in SECTION_RULES:
        if re.search(pattern, label):
            return slug
    return "other"


# Link prefixes that are not articles: namespaces, sister projects, other languages.
NON_ARTICLE_PREFIXES = {
    "file", "image", "category", "template", "portal", "wikipedia", "wp", "help", "special",
    "media", "user", "talk", "wikt", "wiktionary", "w", "commons", "s", "n", "q", "b", "v",
    "d", "voy", "species", "meta", "m", "mw", "c", "wikinews", "wikisource", "wikiquote",
}

# Templates whose text we keep, as {name: how}. Everything else is dropped (citation and
# maintenance templates such as {{Dead link}} carry no headline text).
SHIP_PREFIXES = {"mv", "ms", "hms", "uss", "ss", "rv", "hmas", "hmcs", "ins", "usns", "sv",
                 "my", "hmnzs", "fv", "rms", "ns", "usc&gs", "ccgs", "jds", "js", "pns", "tcg"}
CURRENCY = {"us$": "US$", "usd": "US$", "gbp": "£", "£": "£", "eur": "€", "€": "€",
            "jpy": "¥", "inr": "₹", "a$": "A$", "aud": "A$", "ca$": "CA$", "cad": "CA$",
            "rmb": "CN¥", "cny": "CN¥", "nz$": "NZ$", "hk$": "HK$", "₹": "₹"}
LAST_PARAM_TEMPLATES = {"lang", "transl", "nowrap", "nobr", "small", "smaller", "big",
                        "nowrap begin", "noitalic", "abbr", "keep together", "linktext",
                        "lang-zh", "zh", "nihongo", "korean", "audio", "vs", "sup", "sub",
                        "sic"}
FIRST_PARAM_TEMPLATES = {"flag", "flagcountry", "flagu", "flaglink", "mlby", "nflyr",
                         "baseball year", "by", "sortname", "iast", "ipa", "abbrlink",
                         "math", "mvar", "frac", "as of", "nhl year", "nbay", "ill",
                         "interlanguage link", "interlanguage link multi", "illm", "le",
                         "wikt-lang", "ety", "proper name", "titlelink"}
SYMBOL_TEMPLATES = {"ndash": "–", "mdash": "—", "snd": " – ", "spaced ndash": " – ", "'": "'",
                    "-": "", "nbsp": " ", "colon": ":", "!": "|", "=": "=", "·": "·", "dot": "·",
                    "en dash": "–", "em dash": "—", "\\": " / ", "spnd": " – "}
# Templates that are links to an article (the first parameter is its title).
LINK_TEMPLATES = {"ill", "interlanguage link", "interlanguage link multi", "illm", "le"}


def expand_template(body, links):
    """Plain text for one innermost template body (the part between {{ and }})."""
    parts = [p.strip() for p in body.split("|")]
    name = parts[0].lower().replace("_", " ").strip()
    params = [p for p in parts[1:] if "=" not in p or p.startswith("http")]
    if name in SYMBOL_TEMPLATES:
        return SYMBOL_TEMPLATES[name]
    if name in ("convert", "cvt"):
        if len(params) >= 4 and params[1] in ("-", "to", "and", "–", "or", "by", "x", "×"):
            return f"{params[0]} {params[1]} {params[2]} {params[3]}"
        return " ".join(params[:2])
    if name in CURRENCY:
        return CURRENCY[name] + (params[0] if params else "")
    if name in SHIP_PREFIXES:
        # {{MV|Arctic Sea}} -> "MV Arctic Sea", and it links to that ship's article.
        ship = f"{parts[0].strip()} {params[0]}" if params else parts[0].strip()
        links.append(ship)
        return ship
    if name == "ship" and len(params) >= 2:
        # {{ship|HMS|Victory}} -> "HMS Victory"
        ship = f"{params[0]} {params[1]}"
        links.append(ship)
        return ship
    if name == "sclass" and len(params) >= 2:
        return f"{params[0]}-class {params[1]}"
    if name == "currency" and params:
        return " ".join(params[:2])
    if name == "val" and params:
        return " ± ".join(params[:2])
    if name in ("mpl", "mp") and params:
        return "".join(params[:2])  # minor planets: {{mpl|2018 GY|3}} -> "2018 GY3"
    if name in ("ov", "orbiter"):
        return f"OV-{params[0]}" if params else ""
    if name in LINK_TEMPLATES and params:
        links.append(params[0])
    if name in FIRST_PARAM_TEMPLATES:
        return params[0] if params else ""
    if name in LAST_PARAM_TEMPLATES or name.startswith("lang-"):
        return params[-1] if params else ""
    return ""


def clean_link_target(target):
    """An article title from a [[link]] target, or None if it is not an article."""
    target = target.strip().replace("_", " ")
    if target.startswith(":"):
        target = target[1:]
    if ":" in target:
        prefix = target.split(":", 1)[0].strip().lower()
        if prefix in NON_ARTICLE_PREFIXES or re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", prefix):
            return None
    target = target.split("#", 1)[0].strip()
    target = re.sub(r"\s+", " ", target)
    if not target:
        return None
    return target[0].upper() + target[1:]


LINK_RE = re.compile(r"\[\[([^\[\]|]*)(?:\|([^\[\]]*))?\]\]")


def wikitext_to_plain(text, links):
    """Strip wiki markup from one item line. Article titles of links are added to `links`."""
    text = re.sub(r"<ref[^>/]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    # Templates, innermost first.
    for _ in range(5):
        new = re.sub(r"\{\{([^{}]*)\}\}", lambda m: expand_template(m.group(1), links), text)
        if new == text:
            break
        text = new
    text = text.replace("{{", "").replace("}}", "")

    def link_text(m):
        target, label = m.group(1), m.group(2)
        title = clean_link_target(target)
        if title is None:
            return ""
        links.append(title)
        if label is None:
            return target.split("#", 1)[0].lstrip(":").replace("_", " ")
        return label

    text = LINK_RE.sub(link_text, text)
    # External links: citations like [http://... (BBC)] go; inline [http://... words] keep words.
    text = re.sub(r"\[(?:https?:)?//[^\s\]]+\s*\(?[^\]]*?\)?\]",
                  lambda m: "" if re.search(r"\(.*\)\s*\]$", m.group(0)) or " " not in m.group(0)
                  else m.group(0).split(" ", 1)[1][:-1], text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    return text


def parse_day(wikitext):
    """Headline items of one day: [{section, raw_section, text, links, context_links}].

    The portal nests items: a top bullet often just names an ongoing story
    ("* [[COVID-19 pandemic]]") and the bullets under it are the news. A headline is any
    bullet with no bullets under it, or one that cites a source itself. Its context_links
    are the links of the story bullets above it.
    """
    text = re.sub(r"<!--.*?-->", "", wikitext, flags=re.S)
    # Old pages wrap the news in {{Current events|...|content= ... }}; newer ones open with
    # {{Current events|...}} on its own line.
    text = re.sub(r"\{\{\s*Current events\s*\|[^{}\n]*?content\s*=", "\n", text, flags=re.I)
    text = re.sub(r"\{\{\s*Current events\s*\|[^{}\n]*\}\}", "\n", text, flags=re.I)

    nodes = []  # each: depth, raw_section, text, links, cites, parent, has_children
    section = None
    stack = []  # indexes of open nodes by depth
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line == "}}":
            continue
        heading = (re.match(r"^;\s*(.+)$", line) or re.match(r"^'''([^']+)'''\s*:?$", line)
                   or re.match(r"^==+\s*(.+?)\s*==+$", line))
        if heading:
            section = wikitext_to_plain(heading.group(1), []) or None
            stack = []
            continue
        bullet = re.match(r"^([:*#]+)\s*(.*)$", line)
        if bullet:
            depth = bullet.group(1).count("*") + bullet.group(1).count("#") + bullet.group(1).count(":")
            body = bullet.group(2)
        elif line.startswith("[") and nodes and not line.startswith("[["):
            # A source citation that wrapped onto its own line belongs to the item above.
            nodes[-1]["cites"] = True
            continue
        else:
            depth, body = 1, line
        links = []
        plain = wikitext_to_plain(body, links)
        if not re.search(r"[^\W_]", plain):  # nothing left but punctuation
            continue
        while stack and nodes[stack[-1]]["depth"] >= depth:
            stack.pop()
        parent = stack[-1] if stack else None
        if parent is not None:
            nodes[parent]["has_children"] = True
        nodes.append({
            "depth": depth,
            "raw_section": section,
            "text": plain,
            "links": links,
            "cites": bool(re.search(r"\[(?:https?:)?//", body)),
            "parent": parent,
            "has_children": False,
        })
        stack.append(len(nodes) - 1)

    items = []
    for node in nodes:
        if node["has_children"] and not node["cites"]:
            continue
        context = []
        parent = node["parent"]
        while parent is not None:
            context = nodes[parent]["links"] + context
            parent = nodes[parent]["parent"]
        raw_section = node["raw_section"]
        items.append({
            "raw_section": raw_section,
            "section": section_slug(raw_section) if raw_section else None,
            "text": node["text"],
            "links": list(dict.fromkeys(node["links"])),
            "context_links": [l for l in dict.fromkeys(context) if l not in node["links"]],
        })
    return items


# ---------------------------------------------------------------------------
# Text helpers shared by the classifier and the song matcher
# ---------------------------------------------------------------------------

# Common English function words, plus words that are everywhere in news headlines.
STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before
being below between both but by can could did do does doing down during each few for from
further had has have having he her here hers herself him himself his how i if in into is it
its itself just me more most my myself no nor not now of off on once only or other our ours
out over own same she should so some such than that the their theirs them then there these
they this those through to too under until up very was we were what when where which while
who whom why will with would you your yours yourself one two three four five six seven eight
nine ten first second third new old per via de la le el del des du der von van al bin st mr
mrs ms dr inc ltd co jr sr vs list history timeline wikipedia article
""".split())

# Words that identify the songwriter himself; descriptions mention him all the time.
SELF_WORDS = {"jonathan", "mann", "songaday", "song a day", "jonathan mann"}


def fold(text):
    """Lowercase, strip accents, and turn every non-alphanumeric run into one space."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokens(text):
    return fold(text).split()


# ---------------------------------------------------------------------------
# Sections for days the portal did not split into sections
# ---------------------------------------------------------------------------


def item_features(item):
    """Bag of features for the section classifier: words plus linked article titles."""
    feats = [w for w in tokens(item["text"]) if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]
    feats += ["L:" + fold(l) for l in item["links"] + item["context_links"]]
    return feats


class SectionClassifier:
    """Multinomial naive Bayes over item_features, trained on items that had a section."""

    def fit(self, items):
        self.class_counts = Counter()
        self.feat_counts = defaultdict(Counter)
        for item in items:
            self.class_counts[item["section"]] += 1
            self.feat_counts[item["section"]].update(item_features(item))
        self.vocab = set().union(*self.feat_counts.values())
        total = sum(self.class_counts.values())
        self.log_prior = {c: math.log(n / total) for c, n in self.class_counts.items()}
        self.class_total = {c: sum(f.values()) for c, f in self.feat_counts.items()}
        return self

    def predict(self, item):
        feats = [f for f in item_features(item) if f in self.vocab]
        v = len(self.vocab)
        best, best_score = None, -math.inf
        for c in self.class_counts:
            counts, denom = self.feat_counts[c], self.class_total[c] + v
            score = self.log_prior[c] + sum(math.log((counts[f] + 1) / denom) for f in feats)
            if score > best_score:
                best, best_score = c, score
        return best


def fill_missing_sections(days):
    """Give unsectioned items (mostly 2009 and early 2010) a predicted section.

    Trains on every item that sat under a recognised heading; reports accuracy on a held-out
    tenth of the sectioned days first. Sets item["inferred"] = True on predicted items.
    """
    labeled = [(d, it) for d, items in days.items() for it in items
               if it["section"] and it["section"] != "other"]
    test_days = {d for d in days if d.toordinal() % 10 == 0}
    train = [it for d, it in labeled if d not in test_days]
    test = [it for d, it in labeled if d in test_days]
    model = SectionClassifier().fit(train)
    correct = sum(model.predict(it) == it["section"] for it in test)
    print(f"section classifier: {correct / len(test):.1%} right on {len(test)} held-out items")
    model = SectionClassifier().fit([it for _, it in labeled])
    n = 0
    for items in days.values():
        for it in items:
            it["inferred"] = it["section"] is None
            if it["inferred"]:
                it["section"] = model.predict(it)
                n += 1
    print(f"section classifier: predicted a section for {n} unsectioned items")


# ---------------------------------------------------------------------------
# 3. dataset/news.csv
# ---------------------------------------------------------------------------


def short(text, limit=160):
    """One headline for a "|"-separated cell: no pipes, at most `limit` characters."""
    text = text.replace("|", "/").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "…"


def top_items(items, k=5):
    """Up to k headlines for the day, biggest stories first.

    The portal does not rank its items, so: an item's story is the ongoing-story bullet it
    sits under (its first context link), and a story's size is how many of the day's items
    mention it. Bigger stories come first, one headline per story; ties go round-robin
    across sections in page order, so the list is not all "Armed conflicts" (always first
    on the page). Fragments under six words are skipped.
    """
    candidates = [it for it in items if len(it["text"].split()) >= 6]
    size = Counter()
    for it in items:
        for link in set(it["links"]) | set(it["context_links"]):
            size[link] += 1
    seen_in_section = Counter()
    section_order = {}
    ranked = []
    for page_pos, it in enumerate(candidates):
        story = it["context_links"][0] if it["context_links"] else None
        section_order.setdefault(it["section"], len(section_order))
        turn = seen_in_section[it["section"]]
        seen_in_section[it["section"]] += 1
        ranked.append((-(size[story] if story else 1), turn, section_order[it["section"]],
                       page_pos, story, it))
    ranked.sort(key=lambda r: r[:4])
    picked, stories = [], set()
    for *_, story, it in ranked:
        if story is not None and story in stories:
            continue
        stories.add(story)
        picked.append(it)
        if len(picked) == k:
            break
    return [short(it["text"]) for it in picked]


def write_news_csv(days):
    DATASET_DIR.mkdir(exist_ok=True)
    columns = (["date", "n_items", "n_articles"] + [f"section_{s}" for s in SECTIONS]
               + ["section_other", "sections_inferred", "top_items"])
    with NEWS_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for day in sorted(days):
            items = days[day]
            counts = Counter(it["section"] for it in items)
            articles = {l for it in items for l in it["links"] + it["context_links"]}
            writer.writerow(
                [day.isoformat(), len(items), len(articles)]
                + [counts.get(s, 0) for s in SECTIONS]
                + [counts.get("other", 0), sum(it["inferred"] for it in items),
                   "|".join(top_items(items))]
            )
    print(f"wrote {NEWS_CSV.relative_to(ROOT)} ({len(days)} days)")


# ---------------------------------------------------------------------------
# 4. Songs vs. news: dataset/news_matches.csv
# ---------------------------------------------------------------------------

WINDOW = (0, 1, 2)  # the song's day and the two days before it
DAY_WEIGHT = {0: 1.0, 1: 1.0, 2: 0.8}  # news is often filed under the day before the song
FIELD_WEIGHT = {"title": 1.5, "proper": 1.5, "noun": 1.0, "description": 1.0}
CLASS_WEIGHT = {"name": 1.0, "word": 0.5, "concept": 0.5}
LOOKBACK = 60  # days before the window used to judge whether a story was new
CONTROL_SHIFTS = (-364, 364)  # the same song scored against news a year off, for a baseline
MAX_NGRAM = 8


def load_catalog():
    """{n: song} from the songaday-display chunks. Some chunks exist in two hashed versions;
    reading oldest first lets the newest file win for each song number."""
    songs = {}
    for path in sorted(glob.glob(str(CATALOG_DIR / "index-*.json")), key=os.path.getmtime):
        for s in json.loads(Path(path).read_text())["songs"]:
            songs[s["n"]] = s
    descriptions = {}
    for path in sorted(glob.glob(str(CATALOG_DIR / "detail-*.json")), key=os.path.getmtime):
        for s in json.loads(Path(path).read_text())["songs"]:
            descriptions[s["n"]] = s.get("description") or ""
    if not songs:
        sys.exit(f"no catalog found in {CATALOG_DIR} (set SONGADAY_CATALOG_DIR)")
    out = {}
    for n, s in sorted(songs.items()):
        attrs = s.get("a", {})
        out[n] = {
            "n": n,
            "date": FIRST_DAY + dt.timedelta(days=n - 1),
            "title": s.get("t") or "",
            "proper": attrs.get("Proper Noun") or [],
            "noun": attrs.get("Noun") or [],
            "description": descriptions.get(n, ""),
            "topic": attrs.get("Topic") or [],
        }
    return out


def ngrams(text):
    """Every run of 1..MAX_NGRAM folded words in `text`, as strings."""
    words = tokens(text)
    return {" ".join(words[i:i + k]) for k in range(1, MAX_NGRAM + 1)
            for i in range(len(words) - k + 1)}


def song_grams(song):
    """{field: n-gram set}. List fields are n-grammed entry by entry, so two proper nouns
    never run together into a false phrase."""
    return {
        "title": ngrams(song["title"]),
        "proper": set().union(set(), *(ngrams(p) for p in song["proper"])),
        "noun": set().union(set(), *(ngrams(p) for p in song["noun"])),
        "description": ngrams(song["description"]),
    }


def title_name(title):
    """An article title as people write it: "Kevin Barry (author)" -> "Kevin Barry",
    "Halle, Belgium" -> "Halle"."""
    name = re.sub(r"\s*\([^)]*\)", "", title)
    return name.split(",")[0].strip()


def case_stats(texts):
    """{word: share of its uses that are lowercase} over running prose. Proper names are
    almost always capitalised mid-sentence; ordinary words are not. Sentence-initial words
    are skipped, since they are capitalised either way."""
    lower, upper = Counter(), Counter()
    for text in texts:
        for m in re.finditer(r"[^\W\d_][\w'’-]*", text):
            before = text[: m.start()].rstrip()
            if not before or before[-1] in ".:!?\"“(":
                continue
            bucket = lower if m.group()[0].islower() else upper
            for w in tokens(m.group()):
                bucket[w] += 1
    return {w: lower[w] / (lower[w] + upper[w]) for w in set(lower) | set(upper)}


def is_proper(name, lower_share):
    """Does an article name look like a proper name ("Barack Obama", "2009 Guwahati
    bombings", "COVID-19 pandemic") rather than a common noun ("Natural gas", "Euro")?"""
    words = name.split()
    if not words:
        return False
    if any(w[:1].isupper() for w in words[1:]):
        return True
    if any(ch.isupper() for ch in words[0][1:]):  # COVID-19, iPhone, BBC
        return True
    if len(words) == 1:
        folded = fold(words[0])
        return bool(folded) and lower_share.get(folded, 0.0) < 0.5
    return False


def strip_article(phrase):
    """ "the sun" -> "sun": a leading article would match half the songs ever written."""
    return re.sub(r"^(the|a|an) ", "", phrase)


def build_terms(days, songs):
    """Turn every day's links into searchable terms, and decide which are too common.

    Returns (day_terms, term_days, names):
      day_terms[day] = [(item index, [(term, class, source name), ...]), ...]
      term_days[term] = sorted day ordinals on which the term was in the news
      names[phrase] = the article name a folded phrase came from, for display
    Classes: "name" = the full name of a proper-noun article; "concept" = a common-noun
    article ("Tornado"), only matched in a song's title, proper nouns or nouns; "word" = one
    distinctive word of a proper name ("Obama" from "Barack Obama").
    """
    # How often each word is written lowercase, in the headlines and in the song
    # descriptions together. The descriptions are everyday prose, so they catch words like
    # "nature" or "sun" that the news mostly capitalises (the journal, the tabloid).
    lower_share = case_stats([it["text"] for items in days.values() for it in items]
                             + [s["description"] for s in songs.values()])

    # Given names: words that open many different two- or three-word names
    # ("John Kerry", "John McCain", ...). On their own they would match every John.
    # Ambiguous words: words inside many different names ("Korean", "Super", "Island").
    first_of, anywhere = Counter(), Counter()
    distinct_names = {title_name(l) for items in days.values() for it in items
                      for l in it["links"] + it["context_links"]}
    for name in distinct_names:
        words = [fold(w) for w in name.split() if fold(w)]
        if 2 <= len(words) <= 3:
            first_of[words[0]] += 1
        for w in set(words):
            anywhere[w] += 1
    given_names = {w for w, k in first_of.items() if k >= 3 and k / anywhere[w] >= 0.7}
    ambiguous = {w for w, k in anywhere.items() if k >= 20} - given_names

    # Words that are common across the songs themselves (descriptions are prose).
    song_df = Counter()
    for song in songs.values():
        song_df.update(set(tokens(" ".join([song["title"], song["description"]]
                                           + song["proper"] + song["noun"]))))
    common_in_songs = {w for w, k in song_df.items() if k / len(songs) > 0.03}
    everyday_in_songs = {w for w, k in song_df.items() if k / len(songs) > 0.01}

    def word_ok(w):
        return (len(w) >= 3 and not w.replace(" ", "").isdigit() and w not in STOPWORDS
                and w not in SELF_WORDS and w not in given_names and w not in ambiguous
                and w not in common_in_songs and lower_share.get(w, 0.0) < 0.2)

    day_terms, names = {}, {}
    term_days = defaultdict(set)
    for day, items in days.items():
        entries = []
        for i, it in enumerate(items):
            terms = []
            for link in dict.fromkeys(it["links"] + it["context_links"]):
                name = title_name(link)
                phrase = strip_article(fold(name))
                if len(phrase) < 3 or phrase.replace(" ", "").isdigit() or phrase in STOPWORDS \
                        or phrase in SELF_WORDS:
                    continue
                proper = is_proper(name, lower_share)
                if not proper and phrase in everyday_in_songs:
                    continue  # an everyday word ("Tell", "Love") matches songs by chance
                terms.append((phrase, "name" if proper else "concept", phrase))
                names.setdefault(phrase, name)
                if proper and len(name.split()) > 1:
                    # One capitalised word of the name; "Ki-moon" stays "ki moon", never
                    # "moon", and lowercase words ("mid-air", "bombings") are skipped.
                    for w in dict.fromkeys(fold(w) for w in name.split() if w[:1].isupper()):
                        if w != phrase and word_ok(w):
                            terms.append((w, "word", phrase))
            terms = list(dict.fromkeys(terms))
            for term, _, _ in terms:
                term_days[term].add(day.toordinal())
            entries.append((i, terms))
        day_terms[day] = entries

    # Very common terms (in the news on more than a quarter of all days: "United States",
    # "Russia") match almost any song by chance, so they are dropped.
    n_days = len(days)
    too_common = {t for t, ds in term_days.items() if len(ds) / n_days > 0.25}
    for day, entries in day_terms.items():
        day_terms[day] = [(i, [term for term in terms if term[0] not in too_common])
                          for i, terms in entries]
    term_days = {t: sorted(ds) for t, ds in term_days.items() if t not in too_common}
    print(f"terms: {len(term_days)} kept, {len(too_common)} too common; as single words, "
          f"{len(given_names)} given names and {len(ambiguous)} ambiguous words skipped")
    return day_terms, term_days, names


def novelty(term, day, term_days, first_ord):
    """How new the story was: log of 61 over (1 + the number of the 60 days before the
    3-day window whose news linked the term). A story running all along ("Donald Trump"
    in 2018) scores 0; one that just broke scores log(61), about 4.1. Near the start of
    the data, where fewer than 60 earlier days exist, the count is scaled up to 60 days."""
    hi = day - len(WINDOW)
    lo = max(first_ord, hi - LOOKBACK + 1)
    span = hi - lo + 1
    if span <= 0:
        return math.log(LOOKBACK + 1)
    ds = term_days[term]
    prior = bisect.bisect_right(ds, hi) - bisect.bisect_left(ds, lo)
    return math.log((LOOKBACK + 1) / (prior * LOOKBACK / span + 1))


def score_song(grams, ordinal, days_by_ord, day_terms, term_days, first_ord):
    """Match one song's n-grams against the news on `ordinal` and the two days before it.

    Returns (score, {term: (value, class, source)}, {(ordinal, item index): value}).
    A term's value is
    field weight x class weight x day weight x (novelty + 0.25); a song's score is the sum
    over distinct terms (each counted once, at its best).
    """
    term_value, term_class, term_source, term_items = {}, {}, {}, defaultdict(set)
    for offset in WINDOW:
        o = ordinal - offset
        day = days_by_ord.get(o)
        if day is None:
            continue
        for i, terms in day_terms[day]:
            for term, cls, source in terms:
                fields = ("title", "proper", "noun") if cls == "concept" else FIELD_WEIGHT
                weight = max((FIELD_WEIGHT[f] for f in fields if term in grams[f]), default=0)
                if not weight:
                    continue
                value = (weight * CLASS_WEIGHT[cls] * DAY_WEIGHT[offset]
                         * (novelty(term, ordinal, term_days, first_ord) + 0.25))
                if value > term_value.get(term, 0):
                    term_value[term] = value
                    term_class[term] = cls
                    term_source[term] = source
                term_items[term].add((o, i))
    # A word already covered by a matched full name ("obama" in "barack obama") adds
    # nothing, and two words of one name ("Hillary", "Clinton") count once.
    full_names = [f" {t} " for t, c in term_class.items() if c != "word"]
    best_word = {}
    for t in sorted((t for t, c in term_class.items() if c == "word"), key=lambda t: -term_value[t]):
        if any(f" {t} " in n for n in full_names) or term_source[t] in best_word:
            del term_value[t]
        else:
            best_word[term_source[t]] = t
    item_value = Counter()
    for t, v in term_value.items():
        for key in term_items[t]:
            item_value[key] += v
    matched = {t: (v, term_class[t], term_source[t]) for t, v in term_value.items()}
    return sum(term_value.values()), matched, item_value


def match_songs(days, songs):
    day_terms, term_days, names = build_terms(days, songs)
    days_by_ord = {d.toordinal(): d for d in days}
    first_ord, last_ord = min(days_by_ord), max(days_by_ord)
    rows = []
    for n, song in songs.items():
        grams = song_grams(song)
        ordinal = song["date"].toordinal()
        score, matched, item_value = score_song(grams, ordinal, days_by_ord, day_terms,
                                                term_days, first_ord)
        controls = []
        for shift in CONTROL_SHIFTS:
            o = ordinal + shift
            if first_ord + 2 <= o <= last_ord:
                controls.append(score_song(grams, o, days_by_ord, day_terms, term_days,
                                           first_ord)[0])
        top = item_value.most_common(3)
        rows.append({
            "number": n,
            "date": song["date"].isoformat(),
            "title": song["title"],
            # A word shows the article it came from: "Webb [James Webb Space Telescope]".
            "matched_terms": "|".join(
                (f"{t.title()} [{names[source]}]" if cls == "word" else names[t]).replace("|", "/")
                for t, (_, cls, source) in sorted(matched.items(), key=lambda kv: -kv[1][0])),
            "matched_items": "|".join(
                f"{days_by_ord[o].isoformat()}: {short(days[days_by_ord[o]][i]['text'], 148)}"
                for (o, i), _ in top),
            "match_score": round(score, 2),
            "days_before": ordinal - top[0][0][0] if top else "",
            "control_score": round(sum(controls) / len(controls), 2) if controls else "",
            "_controls": controls,
            "_topic": song["topic"],
        })
    with MATCHES_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in rows[0] if not k.startswith("_")],
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {MATCHES_CSV.relative_to(ROOT)} ({len(rows)} songs)")
    return rows


def report(rows):
    """Print the headline numbers and the strongest matches.

    The control asks how many songs would "match" by chance: each song is scored again
    against the news a year earlier and a year later, and those scores are averaged.
    """
    matched = [r for r in rows if r["match_score"] > 0]
    print(f"\n{len(matched)} of {len(rows)} songs ({len(matched) / len(rows):.1%}) mention "
          f"something linked in that day's or the previous two days' news")
    compared = [r for r in rows if r["_controls"]]
    print(f"real vs chance, over the {len(compared)} songs with news a year either side:")
    for threshold in (0.01, 2, 4, 6):
        real = sum(r["match_score"] >= threshold for r in compared)
        chance = sum(sum(c >= threshold for c in r["_controls"]) / len(r["_controls"])
                     for r in compared)
        label = "any match" if threshold < 1 else f"score >= {threshold}"
        print(f"  {label:>11}: {real} songs, {chance:.0f} expected by chance "
              f"({real / max(chance, 1):.1f}x)")
    print("\nshare of songs scoring >= 4, by topic:")
    for topic in ("Politics", "Trump", "COVID", "Science", "Apple", "Poetic", "Life", "Animals"):
        group = [r for r in rows if topic in r["_topic"]]
        if group:
            hits = sum(r["match_score"] >= 4 for r in group)
            print(f"  {topic:>9}: {hits / len(group):5.1%} of {len(group)}")
    lag = Counter(r["days_before"] for r in rows if r["match_score"] >= 4)
    print("strong matches (score >= 4) by where the news sat: "
          + ", ".join(f"{k} day(s) before: {v}" for k, v in sorted(lag.items())))
    print("\nstrongest matches, ranked by score minus the chance (control) score:")
    excess = lambda r: r["match_score"] - (r["control_score"] or 0)
    for r in sorted(rows, key=lambda r: -excess(r))[:40]:
        print(f"#{r['number']} {r['date']} {r['title']!r} score {r['match_score']} "
              f"(control {r['control_score']}): {r['matched_terms'][:100]}\n"
              f"    {r['matched_items'].split('|')[0][:170]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    parser.add_argument("--refresh-recent", action="store_true",
                        help="refetch months cached before they were a week old")
    args = parser.parse_args()

    texts = fetch_all(offline=args.offline, refresh_recent=args.refresh_recent)
    missing = sorted(d for d, t in texts.items() if not t)
    if missing:
        print(f"{len(missing)} days have no page: {', '.join(map(str, missing[:20]))}")
    days = {d: parse_day(t) for d, t in sorted(texts.items()) if t}
    print(f"parsed {len(days)} days, {sum(map(len, days.values()))} headline items")
    fill_missing_sections(days)
    write_news_csv(days)

    songs = load_catalog()
    rows = match_songs(days, songs)
    report(rows)


if __name__ == "__main__":
    main()
