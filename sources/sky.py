#!/usr/bin/env python3
"""The sky on every Song A Day day: the moon, the planets, retrogrades, alignments, eclipses.

Writes dataset/sky.csv with one row per calendar date from 2009-01-01 (song #1) to
2026-12-31. Each row is a snapshot at 17:00 New York time, roughly when the day's song goes
up. Everything is computed offline with PyEphem. The one download is NASA's eclipse catalog,
used only to check the eclipses, and it is cached in cache/sky/.

Run it from the repo root:

    .venv/bin/python sources/sky.py

It prints a set of sanity checks against known events at the end.

Definitions:

- Positions are geocentric (seen from the Earth's center) and apparent, on the ecliptic of
  date. That is the frame of the tropical zodiac, so 0 degrees is the March equinox point.
- Phase days (is_new_moon_day, is_full_moon_day and the four principal phase names) mark the
  New York calendar day that contains the exact moment of that phase. On the days between,
  the name comes from the Moon's angle from the Sun at 17:00: under 90 degrees is a waxing
  crescent, 90-180 waxing gibbous, 180-270 waning gibbous, 270-360 waning crescent.
- A supermoon is a full moon whose distance is within the closest 10% of the range between
  the nearest apogee and the nearest perigee (Richard Nolle's "within 90% of perigee"):
  (apogee - distance) / (apogee - perigee) >= 0.9, with the distance taken at the exact full
  moon. It is flagged on the full moon's New York day. New-moon supermoons are not flagged.
- Retrograde means the planet's geocentric ecliptic longitude is decreasing at 17:00.
- Conjunctions and the alignment arc use ecliptic longitude only (latitude is ignored) and
  no Pluto, Sun or Moon. Seen from Earth there are seven other planets, Mercury, Venus, Mars,
  Jupiter, Saturn, Uranus and Neptune, so planets_in_smallest_arc and the conjunctions use
  those seven (21 pairs): the "planet parade" sense, planets bunched in our sky. All eight
  planets including Earth only line up as seen from the Sun, so
  planets_in_smallest_arc_helio does that version with heliocentric longitudes.
- Eclipses are computed from the Sun-Moon-Earth geometry at each new and full moon and
  flagged on the New York day that contains greatest eclipse. A solar eclipse counts if the
  Moon's penumbra touches the Earth anywhere; a lunar eclipse counts if the Moon enters the
  Earth's penumbra at all (so faint penumbral eclipses count, as in NASA's catalogs). The
  script checks the result against NASA's catalogs for 2009-2026 (the only download, cached
  in cache/sky/ and used only for that check).

Columns:

    date                     calendar date, YYYY-MM-DD
    computed_at_utc          the 17:00 New York snapshot in UTC (21:00 or 22:00 Z)
    moon_illumination        fraction of the Moon's disk lit, 0-1
    moon_age_days            days since the most recent new moon
    moon_phase               new, waxing crescent, first quarter, waxing gibbous, full,
                             waning gibbous, last quarter, waning crescent
    is_new_moon_day          the exact new moon falls on this New York day
    is_full_moon_day         the exact full moon falls on this New York day
    moon_distance_km         Earth center to Moon center at 17:00
    is_supermoon             this day's full moon is a supermoon (definition above)
    mercury_retrograde       Mercury's longitude is decreasing at 17:00
    mercury_station          "retrograde" or "direct" on the day Mercury turns, else blank
    retrograde_count         how many of Mercury, Venus, Mars, Jupiter, Saturn are retrograde
    retrograde_planets       which ones, separated by ";"
    sun_lon ... neptune_lon  ecliptic longitude in degrees, 0-360
    planets_in_smallest_arc  degrees of the smallest arc of the ecliptic holding the seven
                             other planets as seen from Earth (smaller = more bunched up)
    planets_in_smallest_arc_helio
                             the same for all eight planets as seen from the Sun
    conjunction_pairs        number of planet pairs within 5 degrees of longitude, seen
                             from Earth
    conjunctions             those pairs, like "jupiter-saturn", separated by ";"
    sun_sign, moon_sign      tropical zodiac sign at 17:00
    is_eclipse_day           a solar or lunar eclipse peaks on this New York day
    eclipse_kind             "solar total", "solar annular", "solar hybrid", "solar
                             partial", "lunar total", "lunar partial", "lunar penumbral"
"""

import math
import re
from datetime import date, datetime, time, timedelta, timezone
from itertools import combinations
from pathlib import Path
from time import sleep
from zoneinfo import ZoneInfo

import ephem
import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize_scalar

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "dataset" / "sky.csv"

FIRST_DAY = date(2009, 1, 1)
LAST_DAY = date(2026, 12, 31)
NEW_YORK = ZoneInfo("America/New_York")
SNAPSHOT_TIME = time(17, 0)  # about when the daily song goes up

# Physical constants, in kilometers.
AU_KM = 149_597_870.7
EARTH_RADIUS_KM = 6378.137  # equatorial
EARTH_E2 = 0.00669438  # squared eccentricity of the Earth's ellipsoid (WGS84)
MOON_RADIUS_KM = 1737.4
SUN_RADIUS_KM = 696_000.0  # the value NASA's eclipse tables use

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# The planets other than Earth, in order from the Sun. Seen from Earth there are seven of the
# eight; the heliocentric alignment column adds Earth back as the eighth.
PLANETS = {
    "mercury": ephem.Mercury(),
    "venus": ephem.Venus(),
    "mars": ephem.Mars(),
    "jupiter": ephem.Jupiter(),
    "saturn": ephem.Saturn(),
    "uranus": ephem.Uranus(),
    "neptune": ephem.Neptune(),
}
SUN = ephem.Sun()
MOON = ephem.Moon()

RETROGRADE_PLANETS = ["mercury", "venus", "mars", "jupiter", "saturn"]
CONJUNCTION_DEGREES = 5.0
SUPERMOON_FRACTION = 0.9

# Half-width, in days, of the finite difference used to measure a planet's motion.
RATE_STEP_DAYS = 0.05


# --- time helpers -----------------------------------------------------------------------

def snapshot_utc(day):
    """17:00 New York time on this day, as a UTC datetime (handles daylight saving)."""
    local = datetime.combine(day, SNAPSHOT_TIME, tzinfo=NEW_YORK)
    return local.astimezone(timezone.utc)


def to_ephem(utc_dt):
    """A UTC datetime as a PyEphem date (PyEphem treats naive datetimes as UTC)."""
    return ephem.Date(utc_dt.replace(tzinfo=None))


def utc_datetime(when):
    """A PyEphem date as an aware UTC datetime."""
    return ephem.Date(when).datetime().replace(tzinfo=timezone.utc)


def new_york_day(when):
    """The New York calendar date that contains this moment."""
    return utc_datetime(when).astimezone(NEW_YORK).date()


# --- positions --------------------------------------------------------------------------

def ecliptic_longitude(body, when):
    """Geocentric apparent ecliptic longitude of date, in degrees 0-360."""
    body.compute(when, epoch=when)
    equatorial = ephem.Equatorial(body.ra, body.dec, epoch=when)
    return math.degrees(ephem.Ecliptic(equatorial, epoch=when).lon) % 360.0


def heliocentric_longitude(body, when):
    """Ecliptic longitude seen from the Sun, in degrees 0-360. For the Sun object PyEphem
    gives the Earth's heliocentric position, so heliocentric_longitude(SUN, t) is Earth's."""
    body.compute(when, epoch=when)
    return math.degrees(body.hlon) % 360.0


def wrap180(degrees):
    """An angle difference folded into -180..180."""
    return (degrees + 180.0) % 360.0 - 180.0


def longitude_rate(body, when):
    """How fast the body's longitude is changing, in degrees per day (negative = retrograde)."""
    ahead = ecliptic_longitude(body, when + RATE_STEP_DAYS)
    behind = ecliptic_longitude(body, when - RATE_STEP_DAYS)
    return wrap180(ahead - behind) / (2 * RATE_STEP_DAYS)


def smallest_arc(longitudes):
    """Width of the smallest arc of the circle that contains every longitude."""
    points = sorted(longitudes)
    gaps = [points[i + 1] - points[i] for i in range(len(points) - 1)]
    gaps.append(points[0] + 360.0 - points[-1])  # the gap that wraps past 0 degrees
    return 360.0 - max(gaps)


def zodiac_sign(longitude):
    return SIGNS[int(longitude // 30) % 12]


# --- moon phases, perigees, apogees -----------------------------------------------------

def phase_events(start, end):
    """Every exact new, first quarter, full and last quarter moon between two ephem dates."""
    finders = {
        "new": ephem.next_new_moon,
        "first quarter": ephem.next_first_quarter_moon,
        "full": ephem.next_full_moon,
        "last quarter": ephem.next_last_quarter_moon,
    }
    events = []
    for name, find_next in finders.items():
        when = find_next(start)
        while when < end:
            events.append((ephem.Date(when), name))
            when = find_next(when + 1)
    return sorted(events)


def moon_distance_km(when):
    MOON.compute(when)
    return MOON.earth_distance * AU_KM


def moon_extremes(start, end):
    """Times and distances of every lunar perigee and apogee, found on an hourly grid and
    then refined to the minute."""
    hours = np.arange(float(start), float(end), 1 / 24)
    distances = [moon_distance_km(t) for t in hours]
    perigees, apogees = [], []
    for i in range(1, len(hours) - 1):
        before, here, after = distances[i - 1], distances[i], distances[i + 1]
        window = (hours[i] - 1 / 24, hours[i] + 1 / 24)
        if here < before and here <= after:
            best = minimize_scalar(moon_distance_km, bounds=window, method="bounded")
            perigees.append((best.x, best.fun))
        elif here > before and here >= after:
            best = minimize_scalar(lambda t: -moon_distance_km(t), bounds=window, method="bounded")
            apogees.append((best.x, -best.fun))
    return perigees, apogees


def nearest(extremes, when):
    """The (time, distance) in a list of extremes closest in time to `when`."""
    return min(extremes, key=lambda item: abs(item[0] - when))


# --- eclipses ---------------------------------------------------------------------------
#
# Both kinds of eclipse use apparent geocentric positions, the convention of NASA's eclipse
# catalogs: with them the eclipse gammas and magnitudes here agree with NASA's to about an
# arcsecond (see the checks at the bottom).

def apparent_vector_km(body):
    """Geocentric apparent position of a computed body as an x, y, z vector in km, in the
    equator-of-date frame (so the z axis is the Earth's rotation axis)."""
    ra, dec = float(body.ra), float(body.dec)
    distance = body.earth_distance * AU_KM
    return distance * np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


def lunar_eclipse(full_moon):
    """The eclipse at this full moon, if there is one: a dict with its time of greatest
    eclipse, kind, gamma and magnitudes, or None.

    The Earth's shadow radii follow Danjon's rule (the Earth's radius enlarged by 1% for the
    atmosphere), the method of NASA's Five Millennium Canon of Lunar Eclipses."""

    def distance_from_shadow(when):
        # Angle between the Moon's center and the center of the Earth's shadow, in radians.
        MOON.compute(when)
        SUN.compute(when)
        shadow = (float(SUN.ra) + math.pi, -float(SUN.dec))
        return float(ephem.separation((MOON.ra, MOON.dec), shadow))

    best = minimize_scalar(
        distance_from_shadow, bounds=(full_moon - 0.25, full_moon + 0.25),
        method="bounded", options={"xatol": 1e-6},
    )
    when, gap = best.x, best.fun
    MOON.compute(when)
    SUN.compute(when)
    moon_km, sun_km = MOON.earth_distance * AU_KM, SUN.earth_distance * AU_KM
    moon_parallax = math.asin(EARTH_RADIUS_KM / moon_km)
    sun_parallax = math.asin(EARTH_RADIUS_KM / sun_km)
    sun_radius = math.asin(SUN_RADIUS_KM / sun_km)
    moon_radius = math.asin(MOON_RADIUS_KM / moon_km)
    penumbra = 1.01 * moon_parallax + sun_parallax + sun_radius
    umbra = 1.01 * moon_parallax + sun_parallax - sun_radius

    # Eclipse magnitudes: how far into each shadow the Moon reaches, in Moon diameters.
    penumbral_magnitude = (penumbra + moon_radius - gap) / (2 * moon_radius)
    umbral_magnitude = (umbra + moon_radius - gap) / (2 * moon_radius)
    if umbral_magnitude >= 1:
        kind = "lunar total"
    elif umbral_magnitude > 0:
        kind = "lunar partial"
    elif penumbral_magnitude > 0:
        kind = "lunar penumbral"
    else:
        return None
    return {
        "time": ephem.Date(when),
        "kind": kind,
        "gamma": math.sin(gap) * moon_km / EARTH_RADIUS_KM,
        "penumbral_magnitude": penumbral_magnitude,
        "umbral_magnitude": umbral_magnitude,
    }


def solar_geometry(when):
    """The Moon's shadow against the Earth at one moment.

    Works in the "fundamental plane", the plane through the Earth's center at right angles
    to the shadow's axis (the line from the Sun's center through the Moon's center).
    Returns a dict with:
      gamma        the axis's distance from the Earth's center in Earth radii, with the
                   Earth's flattening taken out, so the Earth is a circle of radius 1
      nasa_gamma   the same without the flattening correction, as NASA's catalogs give it
      penumbra     the penumbra's radius on the plane, in Earth radii
      umbra_on_plane, umbra_at_surface
                   the umbra's radius in km on the plane and at the surface point under the
                   Moon along the axis: positive means the umbra reaches there (total),
                   negative means only the antumbra does (annular)"""
    MOON.compute(when)
    SUN.compute(when)
    moon = apparent_vector_km(MOON)
    sun = apparent_vector_km(SUN)
    sun_to_moon = moon - sun
    sun_moon_km = np.linalg.norm(sun_to_moon)
    axis = sun_to_moon / sun_moon_km  # points from the Sun, through the Moon, toward Earth

    # Where the axis crosses the fundamental plane, and how far the Moon is above that plane.
    crossing = moon - np.dot(moon, axis) * axis
    moon_height = -np.dot(moon, axis)

    # Measure the crossing point in north/east plane coordinates, and stretch the north one
    # so the flattened Earth becomes a circle of radius 1 (the Besselian rho1 correction).
    north = np.array([0.0, 0.0, 1.0]) - axis[2] * axis
    north /= np.linalg.norm(north)
    east = np.cross(north, axis)
    x, y = np.dot(crossing, east), np.dot(crossing, north)
    rho1 = math.sqrt(1 - EARTH_E2 * (1 - axis[2] ** 2))
    gamma = math.hypot(x, y / rho1) / EARTH_RADIUS_KM

    # The two shadow cones and their radii at a given height below the Moon's center.
    outer = math.asin((SUN_RADIUS_KM + MOON_RADIUS_KM) / sun_moon_km)
    inner = math.asin((SUN_RADIUS_KM - MOON_RADIUS_KM) / sun_moon_km)
    penumbra_km = MOON_RADIUS_KM / math.cos(outer) + moon_height * math.tan(outer)

    def umbra_km(height):
        return MOON_RADIUS_KM / math.cos(inner) - height * math.tan(inner)

    surface_height = moon_height - EARTH_RADIUS_KM * math.sqrt(max(0.0, 1 - gamma ** 2))
    return {
        "gamma": gamma,
        "nasa_gamma": math.hypot(x, y) / EARTH_RADIUS_KM,
        "penumbra": penumbra_km / EARTH_RADIUS_KM,
        "umbra_on_plane": umbra_km(moon_height),
        "umbra_at_surface": umbra_km(surface_height),
    }


def solar_eclipse(new_moon):
    """The eclipse at this new moon, if there is one: a dict with its time of greatest
    eclipse, kind and gamma, or None."""
    best = minimize_scalar(
        lambda t: solar_geometry(t)["gamma"], bounds=(new_moon - 0.25, new_moon + 0.25),
        method="bounded", options={"xatol": 1e-6},
    )
    when = best.x
    shadow = solar_geometry(when)
    gamma, umbra_on_plane = shadow["gamma"], shadow["umbra_on_plane"]
    if gamma >= 1 + shadow["penumbra"]:
        return None  # the penumbra misses the Earth
    if gamma < 1:
        # Central eclipse: the axis hits the Earth. It is total at the point under the Moon
        # if the umbra reaches there; if the umbra then falls short of the plane (where the
        # path's sunrise and sunset ends are), the eclipse is hybrid.
        if shadow["umbra_at_surface"] > 0:
            kind = "solar hybrid" if umbra_on_plane < 0 else "solar total"
        else:
            kind = "solar annular"
    elif gamma < 1 + abs(umbra_on_plane) / EARTH_RADIUS_KM:
        # Non-central: the axis misses, but the edge of the umbra or antumbra grazes Earth.
        kind = "solar total" if umbra_on_plane > 0 else "solar annular"
    else:
        kind = "solar partial"
    return {"time": ephem.Date(when), "kind": kind, "gamma": shadow["nasa_gamma"]}


# --- Mercury stations -------------------------------------------------------------------

def mercury_stations(snapshots, rates):
    """The moments Mercury turns retrograde or direct, from the sign changes in its daily
    17:00 rates, each refined to the exact moment the rate crosses zero."""
    mercury = PLANETS["mercury"]
    stations = []
    for i in range(len(snapshots) - 1):
        if (rates[i] < 0) != (rates[i + 1] < 0):
            when = brentq(lambda t: longitude_rate(mercury, t), snapshots[i], snapshots[i + 1], xtol=1e-6)
            stations.append((ephem.Date(when), "retrograde" if rates[i] >= 0 else "direct"))
    return stations


# --- the table --------------------------------------------------------------------------

def every_day():
    day = FIRST_DAY
    while day <= LAST_DAY:
        yield day
        day += timedelta(days=1)


def build_table():
    days = list(every_day())
    snapshots = [to_ephem(snapshot_utc(day)) for day in days]

    # Lunar phase moments, with a margin so the first and last days have neighbors.
    margin_start = to_ephem(datetime(2008, 11, 1, tzinfo=timezone.utc))
    margin_end = to_ephem(datetime(2027, 2, 1, tzinfo=timezone.utc))
    events = phase_events(margin_start, margin_end)
    phase_on_day = {new_york_day(when): name for when, name in events}
    new_moons = [when for when, name in events if name == "new"]
    full_moons = [when for when, name in events if name == "full"]

    # Supermoons: compare each full moon's distance with the nearest perigee and apogee.
    print("Finding perigees and apogees...")
    perigees, apogees = moon_extremes(margin_start, margin_end)
    supermoon_days = set()
    for full in full_moons:
        distance = moon_distance_km(full)
        _, perigee = nearest(perigees, full)
        _, apogee = nearest(apogees, full)
        if (apogee - distance) / (apogee - perigee) >= SUPERMOON_FRACTION:
            supermoon_days.add(new_york_day(full))

    # Eclipses at every new and full moon.
    print("Checking every new and full moon for eclipses...")
    eclipses = [e for e in (solar_eclipse(t) for t in new_moons) if e]
    eclipses += [e for e in (lunar_eclipse(t) for t in full_moons) if e]
    eclipses.sort(key=lambda e: e["time"])
    eclipse_on_day = {new_york_day(e["time"]): e["kind"] for e in eclipses}

    print(f"Computing {len(days)} daily snapshots...")
    rows, mercury_rates = [], []
    for day, when in zip(days, snapshots):
        # Positions.
        sun_lon = ecliptic_longitude(SUN, when)
        moon_lon = ecliptic_longitude(MOON, when)  # leaves MOON computed for `when`
        illumination = MOON.moon_phase
        distance = MOON.earth_distance * AU_KM
        longitudes = {name: ecliptic_longitude(body, when) for name, body in PLANETS.items()}
        helio = [heliocentric_longitude(body, when) for body in [SUN, *PLANETS.values()]]

        # Phase: the principal phase if its exact moment is today, otherwise by elongation.
        elongation = (moon_lon - sun_lon) % 360.0
        phase = phase_on_day.get(day) or (
            "waxing crescent" if elongation < 90 else
            "waxing gibbous" if elongation < 180 else
            "waning gibbous" if elongation < 270 else
            "waning crescent"
        )

        # Retrogrades.
        rates = {name: longitude_rate(PLANETS[name], when) for name in RETROGRADE_PLANETS}
        mercury_rates.append(rates["mercury"])
        retrograde = [name for name in RETROGRADE_PLANETS if rates[name] < 0]

        # Conjunctions among the seven planets seen from Earth (21 possible pairs).
        conjunctions = [
            f"{a}-{b}" for a, b in combinations(longitudes, 2)
            if abs(wrap180(longitudes[a] - longitudes[b])) <= CONJUNCTION_DEGREES
        ]

        row = {
            "date": day.isoformat(),
            "computed_at_utc": utc_datetime(when).strftime("%Y-%m-%dT%H:%MZ"),
            "moon_illumination": round(illumination, 4),
            "moon_age_days": round(when - ephem.previous_new_moon(when), 3),
            "moon_phase": phase,
            "is_new_moon_day": phase_on_day.get(day) == "new",
            "is_full_moon_day": phase_on_day.get(day) == "full",
            "moon_distance_km": round(distance),
            "is_supermoon": day in supermoon_days,
            "mercury_retrograde": "mercury" in retrograde,
            "mercury_station": "",  # filled in below
            "retrograde_count": len(retrograde),
            "retrograde_planets": ";".join(retrograde),
            "sun_lon": round(sun_lon, 3),
            "moon_lon": round(moon_lon, 3),
        }
        for name, lon in longitudes.items():
            row[f"{name}_lon"] = round(lon, 3)
        row.update({
            "planets_in_smallest_arc": round(smallest_arc(longitudes.values()), 2),
            "planets_in_smallest_arc_helio": round(smallest_arc(helio), 2),
            "conjunction_pairs": len(conjunctions),
            "conjunctions": ";".join(conjunctions),
            "sun_sign": zodiac_sign(sun_lon),
            "moon_sign": zodiac_sign(moon_lon),
            "is_eclipse_day": day in eclipse_on_day,
            "eclipse_kind": eclipse_on_day.get(day, ""),
        })
        rows.append(row)

    # Mark the day each Mercury station happens on.
    stations = mercury_stations(snapshots, mercury_rates)
    index_of = {row["date"]: i for i, row in enumerate(rows)}
    for when, direction in stations:
        i = index_of.get(new_york_day(when).isoformat())
        if i is not None:
            rows[i]["mercury_station"] = direction

    table = pd.DataFrame(rows)
    return table, eclipses, stations


# --- sanity checks ----------------------------------------------------------------------

# NASA's Five Millennium eclipse catalogs (Fred Espenak, eclipse.gsfc.nasa.gov), used only to
# check the computed eclipses. They are downloaded once into cache/sky/.
NASA_CATALOGS = {
    "solar": "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
    "lunar": "https://eclipse.gsfc.nasa.gov/LEcat5/LE2001-2100.html",
}
CACHE_DIR = ROOT / "cache" / "sky"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
NASA_KINDS = {
    "solar": {"P": "solar partial", "A": "solar annular", "T": "solar total", "H": "solar hybrid"},
    "lunar": {"N": "lunar penumbral", "P": "lunar partial", "T": "lunar total"},
}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def cached_download(url):
    """The text at a URL, fetched once and kept in cache/sky/. Retries politely on 429s and
    server errors. Returns None if it can't be fetched (the check is then skipped)."""
    import requests  # only needed for this check

    path = CACHE_DIR / url.rsplit("/", 1)[-1]
    if path.exists():
        return path.read_text()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        except requests.RequestException as error:
            print(f"  could not fetch {url}: {error}")
            return None
        if response.status_code == 200:
            path.write_text(response.text)
            return response.text
        if response.status_code == 429 or response.status_code >= 500:
            sleep(2 ** attempt * 5)
            continue
        print(f"  could not fetch {url}: HTTP {response.status_code}")
        return None
    return None


def nasa_eclipses():
    """NASA's eclipses from 2009 to 2026, keyed by the UTC date of greatest eclipse:
    {date: {"kind", "time" (UTC, as an ephem date), "gamma"}}. None if not available."""
    row = re.compile(
        r"^\s*\d{5}\s+(\d{4}) (\w{3}) (\d\d)\s+(\d\d:\d\d:\d\d)\s+(-?\d+)\s+"
        r"-?\d+\s+\d+\s+(\S+)\s+\S+\s+(-?\d\.\d+)"
    )
    eclipses = {}
    for family, url in NASA_CATALOGS.items():
        page = cached_download(url)
        if page is None:
            return None
        for line in re.sub(r"<[^>]*>", "", page).splitlines():
            match = row.match(line)
            if not match:
                continue
            year, month, day, clock, delta_t, kind_code, gamma = match.groups()
            if not FIRST_DAY.year <= int(year) <= LAST_DAY.year:
                continue
            # The catalogs give Terrestrial Time; Universal Time is that minus Delta T.
            moment = ephem.Date(f"{year}/{MONTHS.index(month) + 1}/{day} {clock}") - int(delta_t) / 86400
            eclipses[utc_datetime(moment).date().isoformat()] = {
                "kind": NASA_KINDS[family][kind_code[0]],
                "time": ephem.Date(moment),
                "gamma": float(gamma),
            }
    return eclipses


def sanity_checks(table, eclipses, stations):
    """Compare the table with well-known events. Prints one line per check."""
    by_date = table.set_index("date")
    results = []

    def check(label, passed, detail=""):
        results.append(passed)
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}{': ' + detail if detail else ''}")

    print("\nSanity checks")

    # The Sun sits at 0 and 90 degrees at the 2024 March equinox and June solstice.
    for label, finder, target in [
        ("Sun at 0 deg at the 2024 March equinox", ephem.next_equinox, 0.0),
        ("Sun at 90 deg at the 2024 June solstice", ephem.next_solstice, 90.0),
    ]:
        moment = finder("2024/1/1")
        error = abs(wrap180(ecliptic_longitude(SUN, moment) - target))
        check(label, error < 0.001, f"{moment} UTC, off by {error * 3600:.2f} arcsec")

    # Full moon 2024-01-25 (17:54 UTC, 12:54 New York).
    day = by_date.loc["2024-01-25"]
    check("Full moon on 2024-01-25", bool(day.is_full_moon_day) and day.moon_phase == "full",
          f"illumination {day.moon_illumination} at 17:00")
    full_days = table[table.is_full_moon_day].date
    neighbors = full_days[(full_days >= "2024-01-01") & (full_days <= "2024-03-31")].tolist()
    check("Only one full moon day per lunation around it", neighbors == ["2024-01-25", "2024-02-24", "2024-03-25"],
          ", ".join(neighbors))

    # December 2009 had a blue moon (two full moons), the second with a partial lunar eclipse.
    december = full_days[full_days.str.startswith("2009-12")].tolist()
    check("Blue moon in December 2009", december == ["2009-12-02", "2009-12-31"], ", ".join(december))

    # Mercury retrograde, spring 2024: stations retrograde 2024-04-01 22:14 UTC (18:14 New York,
    # after the 17:00 snapshot) and direct 2024-04-25 12:54 UTC (08:54 New York).
    april = [(w, d) for w, d in stations if str(w).startswith("2024/4")]
    detail = "; ".join(f"{d} at {utc_datetime(w):%Y-%m-%d %H:%M} UTC" for w, d in april)
    check("Mercury stations on 2024-04-01 and 2024-04-25",
          [new_york_day(w).isoformat() for w, _ in april] == ["2024-04-01", "2024-04-25"], detail)
    retro = table[table.mercury_retrograde & (table.date >= "2024-03-15") & (table.date <= "2024-05-15")].date
    check("Mercury retrograde at 17:00 from 2024-04-02 to 2024-04-24",
          retro.tolist() == [f"2024-04-{d:02d}" for d in range(2, 25)],
          f"{retro.min()} to {retro.max()}, {len(retro)} days")

    # Solar eclipse 2024-04-08, total across North America.
    day = by_date.loc["2024-04-08"]
    check("Total solar eclipse on 2024-04-08", day.eclipse_kind == "solar total",
          f"is_eclipse_day={day.is_eclipse_day}, kind={day.eclipse_kind!r}, new moon day={day.is_new_moon_day}")

    # The great conjunction of Jupiter and Saturn, 2020-12-21.
    december = table[table.date.str.startswith("2020-12")].copy()
    december["gap"] = (december.jupiter_lon - december.saturn_lon).map(lambda d: abs(wrap180(d)))
    closest = december.loc[december.gap.idxmin()]
    check("Jupiter-Saturn great conjunction on 2020-12-21",
          closest.date == "2020-12-21" and closest.gap < 0.2 and "jupiter-saturn" in closest.conjunctions,
          f"closest at 17:00 on {closest.date}, {closest.gap * 60:.1f} arcmin apart in longitude")

    # Supermoons: 2016-11-14 was the closest full moon since 1948; 2024 had four in a row.
    check("Supermoon on 2016-11-14", bool(by_date.loc["2016-11-14"].is_supermoon))
    super_2024 = table[table.is_supermoon & table.date.str.startswith("2024")].date.tolist()
    check("Four supermoons in 2024, Aug-Nov",
          super_2024 == ["2024-08-19", "2024-09-17", "2024-10-17", "2024-11-15"], ", ".join(super_2024))

    # Every eclipse against NASA's catalogs: dates, kinds, times of greatest eclipse, gammas.
    nasa = nasa_eclipses()
    if nasa is None:
        print("  [SKIP] NASA eclipse catalogs not available")
    else:
        computed = {utc_datetime(e["time"]).date().isoformat(): e for e in eclipses
                    if FIRST_DAY <= utc_datetime(e["time"]).date() <= LAST_DAY}
        missing = sorted(set(nasa) - set(computed))
        extra = sorted(set(computed) - set(nasa))
        both = sorted(set(nasa) & set(computed))
        wrong = [(d, computed[d]["kind"], nasa[d]["kind"]) for d in both if computed[d]["kind"] != nasa[d]["kind"]]
        minutes = [abs(computed[d]["time"] - nasa[d]["time"]) * 1440 for d in both]
        gammas = [abs(computed[d]["gamma"] - abs(nasa[d]["gamma"])) for d in both]
        solar = sum(1 for d in nasa if nasa[d]["kind"].startswith("solar"))
        detail = (f"{len(computed)} computed, {len(nasa)} in NASA's catalogs ({solar} solar, "
                  f"{len(nasa) - solar} lunar); greatest eclipse within {max(minutes):.1f} min, "
                  f"gamma within {max(gammas):.4f}")
        if missing or extra or wrong:
            detail += f"; missing {missing}, extra {extra}, wrong kind {wrong}"
        check("All 2009-2026 eclipses match NASA (date and kind)", not (missing or extra or wrong), detail)
        check("One eclipse day per eclipse", int(table.is_eclipse_day.sum()) == len(nasa),
              f"{int(table.is_eclipse_day.sum())} eclipse days (New York dates)")

    # 2015-04-04 was the century's shortest total lunar eclipse (umbral magnitude 1.0008) and
    # 2011-07-01 a tiny partial solar eclipse (magnitude 0.097): edge cases for the geometry.
    tight = {utc_datetime(e["time"]).date().isoformat(): e for e in eclipses}
    april = tight.get("2015-04-04", {})
    check("2015-04-04 lunar eclipse is (barely) total", april.get("kind") == "lunar total",
          f"umbral magnitude {april.get('umbral_magnitude', float('nan')):.4f} (NASA 1.0008)")

    # Some lists include a penumbral lunar eclipse on 2016-08-18 (the end of Saros 109). With
    # Danjon's shadow, as NASA uses, the Moon just misses the penumbra.
    missed = lunar_eclipse(ephem.next_full_moon("2016/8/15"))
    check("No eclipse on 2016-08-18 (as in NASA's catalog)", missed is None)

    print(f"  {sum(results)} of {len(results)} checks passed")
    return all(results)


def summary(table):
    """A few headline numbers, for the report."""
    print("\nSummary")
    print(f"  rows: {len(table)} ({table.date.iloc[0]} to {table.date.iloc[-1]})")
    print(f"  full moon days: {int(table.is_full_moon_day.sum())}, new moon days: {int(table.is_new_moon_day.sum())}, "
          f"supermoons: {int(table.is_supermoon.sum())}")
    print(f"  Mercury retrograde on {int(table.mercury_retrograde.sum())} days "
          f"({table.mercury_retrograde.mean():.1%}), {int((table.mercury_station == 'retrograde').sum())} retrograde periods")
    print(f"  retrograde_count distribution: {table.retrograde_count.value_counts().sort_index().to_dict()}")
    tight = table.loc[table.planets_in_smallest_arc.idxmin()]
    loose = table.loc[table.planets_in_smallest_arc.idxmax()]
    print(f"  tightest planet arc: {tight.planets_in_smallest_arc} deg on {tight.date}; "
          f"widest: {loose.planets_in_smallest_arc} deg on {loose.date}")
    print(f"  most conjunctions in one day: {table.conjunction_pairs.max()} "
          f"(first on {table.loc[table.conjunction_pairs.idxmax()].date})")
    print(f"  eclipse days: {table.eclipse_kind[table.is_eclipse_day].value_counts().to_dict()}")


def main():
    table, eclipses, stations = build_table()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH.relative_to(ROOT)} ({len(table)} rows, {len(table.columns)} columns)")
    summary(table)
    ok = sanity_checks(table, eclipses, stations)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
