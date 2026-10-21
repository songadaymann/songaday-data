"""Where each Song A Day song was recorded: every Location string in the catalog, mapped to a
real place with coordinates.

The sheet's Location column is free text. It mixes cities ("Jersey City"), studio variants
("Hartford, CT Studio 3"), neighborhoods ("Windsor Terrace"), typos ("Tuscon, AC"), states
("Vermont") and things that are not places at all ("In The Car", "Norman's House"). This
script maps each string to a canonical place through the hand-checked tables below, looks up
coordinates with the free Open-Meteo geocoding API (no key; raw answers cached in
cache/places/geocode/), and writes dataset/places.csv with one row per distinct Location
string.

How a string becomes a place:
1. PLACES lists the canonical places. Each says how to find its coordinates: a geocoder
   query (filtered by country and state so "Canton" finds Canton, CT and not Canton, OH) or,
   for the few places the geocoder doesn't know, fixed coordinates read off a map.
2. LOCATIONS maps every Location string to one of those places, with its kind, a confidence
   and a note on any judgment call. Strings that aren't places map to CONTEXT instead.
3. A CONTEXT song takes the place of the nearest song (by song number, the earlier one on a
   tie) whose Location is a real place. "In The Car" on the drive from Berkeley to LA becomes
   Berkeley; "Airport" the day after three Denver songs becomes Denver. These are always
   confidence "low". SONG_OVERRIDES fixes the rare song where that rule picks wrong.
4. A Location string that is in neither table (a new one added to the sheet later) is sent
   to the geocoder as-is, gets confidence "low", and is reported so it can be added to
   LOCATIONS.

Columns of dataset/places.csv:
  location_raw  the Location string exactly as the catalog has it
  place         canonical place, e.g. "Hartford, CT", "Windsor Terrace, Brooklyn, NY",
                "Vienna, Austria". Blank for a CONTEXT string whose songs resolve to
                different places; their per-song places are in dataset/weather.csv.
  city          the city or town (Brooklyn for its neighborhoods); blank when the sheet only
                names a state or an island
  region        state, province or other first-level region, from the geocoder
  country       country, from the geocoder
  lat, lon      decimal degrees (WGS84)
  kind          home    his home town at the time (his place or anywhere in that town)
                studio  a named recording studio, his own or someone else's
                travel  anywhere else, including family homes and nearby towns
                unknown not a place (a car, a plane, a school), or the sheet's value can't be
                        where the song was made
  confidence    high    the string names the place outright (typos and wrong states fixed)
                medium  the place is inferred, e.g. "Williams, MA" -> Williamstown
                low     a guess: a state with no town, or resolved from neighboring songs
  note          why, for anything that isn't obvious
  songs, first_date, last_date
                how many songs use the string, and when it first and last appears

His homes, for reference: Berkeley, CA (Feb 2009 to early Nov 2011); his parents' area in
Canton/Avon, CT while between homes (Nov 2011 to Feb 2012); Brooklyn, NY (Mar 2012 to Dec 2014:
Williamsburg, Bushwick, Windsor Terrace); Jersey City, NJ (Dec 2014 to mid 2020; spring 2020
with family in Severna Park, MD); Hartford / West Hartford, CT (Aug 2020 to now). Family is in
Avon/Canton, CT and Severna Park, MD.

Run:  .venv/bin/python sources/places.py

Paths, all optional:
  SONGADAY_CATALOG_DIR  songaday-display publish/meta folder (index-*.json chunks)
                        default ~/Library/Caches/songaday-display/publish/meta

Geocoding data: Open-Meteo (open-meteo.com), built on GeoNames (geonames.org), CC BY 4.0.
"""

import csv
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "places"
GEOCODE_CACHE = CACHE_DIR / "geocode"
OUT_CSV = ROOT / "dataset" / "places.csv"

CATALOG_DIR = Path(
    os.environ.get("SONGADAY_CATALOG_DIR")
    or Path.home() / "Library" / "Caches" / "songaday-display" / "publish" / "meta"
)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
REQUEST_PAUSE = 0.5  # seconds between live requests; one request at a time
MAX_TRIES = 6  # per request, with exponential backoff on 429 and 5xx

COLUMNS = [
    "location_raw", "place", "city", "region", "country", "lat", "lon",
    "kind", "confidence", "note", "songs", "first_date", "last_date",
]
KINDS = {"home", "studio", "travel", "unknown"}
CONFIDENCES = {"high", "medium", "low"}

# Marks a Location string that isn't a place; each of its songs borrows a neighbor's place.
CONTEXT = "CONTEXT"


def geo(name, country, admin1=None, admin2=None, feature=None, city=None, country_name=None):
    """A place found by geocoder query. admin1/admin2 must appear in the result's state or
    county; feature limits the GeoNames feature class (e.g. "PRK" for a park); city replaces
    the result's name in the city column ("" leaves it blank); country_name fills in a
    country the geocoder leaves blank."""
    return {"query": name, "country": country, "admin1": admin1, "admin2": admin2,
            "feature": feature, "city": city, "country_name": country_name}


def fixed(lat, lon, city, region, country, why):
    """A place the geocoder doesn't know, with coordinates read off a map."""
    return {"lat": lat, "lon": lon, "city": city, "region": region, "country": country,
            "why": why}


# Canonical places. Labels are "Town, ST" in the US, "Neighborhood, Brooklyn, NY" for
# Brooklyn, and "City, Country" (or "City, Province") elsewhere.
PLACES = {
    # California
    "Berkeley, CA": geo("Berkeley", "US", "California"),
    "Oakland, CA": geo("Oakland", "US", "California"),
    "San Francisco, CA": geo("San Francisco", "US", "California"),
    "Los Angeles, CA": geo("Los Angeles", "US", "California"),
    "San Diego, CA": geo("San Diego", "US", "California"),
    "Santa Cruz, CA": geo("Santa Cruz", "US", "California"),
    "Ojai, CA": geo("Ojai", "US", "California"),
    "Stanford, CA": geo("Stanford", "US", "California"),
    "Palo Alto, CA": geo("Palo Alto", "US", "California"),
    "Burlingame, CA": geo("Burlingame", "US", "California"),
    "Palm Springs, CA": geo("Palm Springs", "US", "California"),
    "Yosemite Valley, CA": geo("Yosemite Valley", "US", "California"),
    # New York City
    "New York, NY": geo("New York", "US", "New York"),
    "Brooklyn, NY": geo("Brooklyn", "US", "New York", admin2="Kings"),
    "Williamsburg, Brooklyn, NY": geo("Williamsburg", "US", "New York", admin2="Kings",
                                      city="Brooklyn"),
    "Bushwick, Brooklyn, NY": geo("Bushwick", "US", "New York", admin2="Kings", city="Brooklyn"),
    "Park Slope, Brooklyn, NY": geo("Park Slope", "US", "New York", admin2="Kings",
                                    city="Brooklyn"),
    "Windsor Terrace, Brooklyn, NY": geo("Windsor Terrace", "US", "New York", admin2="Kings",
                                         city="Brooklyn"),
    "Cypress Hills, Brooklyn, NY": geo("Cypress Hills", "US", "New York", admin2="Kings",
                                       city="Brooklyn"),
    "Downtown Brooklyn, Brooklyn, NY": geo("Downtown Brooklyn", "US", "New York",
                                           admin2="Kings", city="Brooklyn"),
    "Prospect Park, Brooklyn, NY": geo("Prospect Park", "US", "New York", admin2="Kings",
                                       feature="PRK", city="Brooklyn"),
    "Brooklyn Navy Yard, Brooklyn, NY": fixed(40.7010, -73.9700, "Brooklyn", "New York",
                                              "United States", "not in the geocoder"),
    # New York State
    "Harrison, NY": geo("Harrison", "US", "New York", admin2="Westchester"),
    "Croton-on-Hudson, NY": geo("Croton-on-Hudson", "US", "New York"),
    "Olivebridge, NY": geo("Olivebridge", "US", "New York"),
    "Tillson, NY": geo("Tillson", "US", "New York"),
    "Storm King, NY": geo("Mountainville", "US", "New York", admin2="Orange",
                          city="Mountainville"),
    "Nyack, NY": geo("Nyack", "US", "New York"),
    "Nanuet, NY": geo("Nanuet", "US", "New York"),
    "Lake Welch, NY": fixed(41.226, -74.045, "", "New York", "United States",
                            "not in the geocoder; Lake Welch in Harriman State Park, read off "
                            "a map"),
    "Saratoga Springs, NY": geo("Saratoga Springs", "US", "New York"),
    # New Jersey
    "Jersey City, NJ": geo("Jersey City", "US", "New Jersey"),
    "Newark, NJ": geo("Newark", "US", "New Jersey"),
    "Secaucus, NJ": geo("Secaucus", "US", "New Jersey"),
    "Hackensack, NJ": geo("Hackensack", "US", "New Jersey"),
    "Teaneck, NJ": geo("Teaneck", "US", "New Jersey"),
    "Paramus, NJ": geo("Paramus", "US", "New Jersey"),
    "Bayonne, NJ": geo("Bayonne", "US", "New Jersey"),
    "Morristown, NJ": geo("Morristown", "US", "New Jersey"),
    "Chester, NJ": geo("Chester", "US", "New Jersey", admin2="Morris"),
    "East Hanover, NJ": geo("East Hanover", "US", "New Jersey"),
    # Connecticut
    "Hartford, CT": geo("Hartford", "US", "Connecticut"),
    "West Hartford, CT": geo("West Hartford", "US", "Connecticut"),
    "Avon, CT": geo("Avon", "US", "Connecticut"),
    "Canton, CT": geo("Canton", "US", "Connecticut"),
    "Simsbury, CT": geo("Simsbury", "US", "Connecticut"),
    "West Simsbury, CT": geo("West Simsbury", "US", "Connecticut"),
    "Weatogue, CT": geo("Weatogue", "US", "Connecticut", admin2="Capitol"),
    "Farmington, CT": geo("Farmington", "US", "Connecticut"),
    "Barkhamsted, CT": geo("Barkhamsted", "US", "Connecticut"),
    "Southington, CT": geo("Southington", "US", "Connecticut"),
    "Windsor, CT": geo("Windsor", "US", "Connecticut"),
    "Manchester, CT": geo("Manchester", "US", "Connecticut"),
    "Milford, CT": geo("Milford", "US", "Connecticut"),
    # Rest of New England
    "Bennington, VT": geo("Bennington", "US", "Vermont"),
    "Burlington, VT": geo("Burlington", "US", "Vermont"),
    "Essex Junction, VT": geo("Essex Junction", "US", "Vermont"),
    "Westford, VT": geo("Westford", "US", "Vermont"),
    "Boston, MA": geo("Boston", "US", "Massachusetts"),
    "Ludlow, MA": geo("Ludlow", "US", "Massachusetts"),
    "Sturbridge, MA": geo("Sturbridge", "US", "Massachusetts"),
    "Williamstown, MA": geo("Williamstown", "US", "Massachusetts"),
    "Keene, NH": geo("Keene", "US", "New Hampshire"),
    "Misquamicut, RI": geo("Misquamicut", "US", "Rhode Island"),
    # Mid-Atlantic and South
    "Philadelphia, PA": geo("Philadelphia", "US", "Pennsylvania"),
    "Lancaster, PA": geo("Lancaster", "US", "Pennsylvania", admin2="Lancaster"),
    "Wilmington, DE": geo("Wilmington", "US", "Delaware"),
    "Baltimore, MD": geo("Baltimore", "US", "Maryland"),
    "Severna Park, MD": geo("Severna Park", "US", "Maryland"),
    "Oakland, MD": geo("Oakland", "US", "Maryland", admin2="Garrett"),
    "Washington, DC": geo("Washington", "US", "District of Columbia"),
    "Charlottesville, VA": geo("Charlottesville", "US", "Virginia"),
    "Bristol, VA": geo("Bristol", "US", "Virginia"),
    "Hot Springs, VA": geo("Hot Springs", "US", "Virginia"),
    "Nashville, TN": geo("Nashville", "US", "Tennessee"),
    "Atlanta, GA": geo("Atlanta", "US", "Georgia"),
    "Jupiter, FL": geo("Jupiter", "US", "Florida"),
    "Pensacola, FL": geo("Pensacola", "US", "Florida"),
    "Orlando, FL": geo("Orlando", "US", "Florida"),
    "New Orleans, LA": geo("New Orleans", "US", "Louisiana"),
    "San Juan, PR": geo("San Juan", "PR", country_name="Puerto Rico"),
    # Midwest, Texas and West
    "Chicago, IL": geo("Chicago", "US", "Illinois"),
    "St. Louis, MO": geo("St. Louis", "US", "Missouri"),
    "Minneapolis, MN": geo("Minneapolis", "US", "Minnesota"),
    "Eagan, MN": geo("Eagan", "US", "Minnesota"),
    "Alexandria, MN": geo("Alexandria", "US", "Minnesota"),
    "Austin, TX": geo("Austin", "US", "Texas"),
    "Plano, TX": geo("Plano", "US", "Texas"),
    "Midland, TX": geo("Midland", "US", "Texas"),
    "Ozona, TX": geo("Ozona", "US", "Texas"),
    "Tucson, AZ": geo("Tucson", "US", "Arizona"),
    "Patagonia, AZ": geo("Patagonia", "US", "Arizona"),
    "Denver, CO": geo("Denver", "US", "Colorado"),
    "Colorado Springs, CO": geo("Colorado Springs", "US", "Colorado"),
    "Manitou Springs, CO": geo("Manitou Springs", "US", "Colorado"),
    "Pueblo, CO": geo("Pueblo", "US", "Colorado"),
    "Salt Lake City, UT": geo("Salt Lake City", "US", "Utah"),
    "Portland, OR": geo("Portland", "US", "Oregon"),
    "Seattle, WA": geo("Seattle", "US", "Washington"),
    # Maui: the sheet names only the island. Kahului is its main town (and airport).
    "Maui, HI": geo("Kahului", "US", "Hawaii", city=""),
    # States with no town given. The geocoder has no state entries, so these use the state
    # capital as a stand-in point (city left blank).
    "Vermont": geo("Montpelier", "US", "Vermont", city=""),
    "Pennsylvania": geo("Harrisburg", "US", "Pennsylvania", admin2="Dauphin", city=""),
    "Minnesota": geo("Saint Paul", "US", "Minnesota", city=""),
    "New Jersey": geo("Trenton", "US", "New Jersey", city=""),
    # Canada
    "Montreal, QC": geo("Montreal", "CA", "Quebec"),
    "Toronto, ON": geo("Toronto", "CA", "Ontario"),
    "Palmer Rapids, ON": geo("Palmer Rapids", "CA", "Ontario"),
    "Vancouver, BC": geo("Vancouver", "CA", "British Columbia"),
    "Victoria, BC": geo("Victoria", "CA", "British Columbia"),
    # Rest of the world
    "London, UK": geo("London", "GB", "England"),
    "Vienna, Austria": geo("Vienna", "AT"),
    "Berlin, Germany": geo("Berlin", "DE"),
    # GeoNames files the city under its English name; "Hannover" finds a hamlet near Bremen.
    "Hanover, Germany": geo("Hanover", "DE", "Lower Saxony"),
    "Prague, Czechia": geo("Prague", "CZ"),
    "Copenhagen, Denmark": geo("Copenhagen", "DK"),
    "Barcelona, Spain": geo("Barcelona", "ES"),
    "Bogotá, Colombia": geo("Bogotá", "CO"),
    "Phuket, Thailand": geo("Phuket", "TH"),
}


# Every Location string in the catalog: (place or CONTEXT, kind, confidence, note).
# Grouped roughly by where his life was at the time.
LOCATIONS = {
    # Berkeley years, 2009-2011
    "Berkeley": ("Berkeley, CA", "home", "high",
                 "home Feb 2009 to Nov 2011; one later visit (#2138, 2014)"),
    "Berkeley Studio": ("Berkeley, CA", "studio", "high", ""),
    "Oakland": ("Oakland, CA", "travel", "high",
                "Oakland, CA: all six songs are from the Berkeley years (not Oakland, MD)"),
    "Norman's House": (CONTEXT, "unknown", "low",
                       "a friend's house during the Berkeley years; Berkeley Studio and "
                       "Berkeley songs on either side"),
    "New Zealand": (CONTEXT, "unknown", "low",
                    "#748 is a song about someone in New Zealand, and #747 and #749 are both "
                    "Berkeley Studio, so it was almost certainly made in Berkeley; the sheet "
                    "probably has the subject, not the place"),
    "Los Angeles": ("Los Angeles, CA", "travel", "high",
                    "includes the first five songs (Jan 1-5, 2009), before the move to "
                    "Berkeley"),
    "San Francisco": ("San Francisco, CA", "travel", "high", ""),
    "San Diego": ("San Diego, CA", "travel", "high", ""),
    "Santa Cruz": ("Santa Cruz, CA", "travel", "high", ""),
    "Ojai, CA": ("Ojai, CA", "travel", "high", ""),
    "Stanford, CA": ("Stanford, CA", "travel", "high", ""),
    "Yosemite": ("Yosemite Valley, CA", "travel", "medium",
                 "the sheet says only Yosemite; Yosemite Valley is where visitors stay"),
    "Portland, OR": ("Portland, OR", "travel", "high", ""),
    "Seattle, WA": ("Seattle, WA", "travel", "high", ""),
    "Maui, HI": ("Maui, HI", "travel", "medium",
                 "island only; coordinates are Kahului, the main town, and weather varies a "
                 "lot across Maui"),
    "Vienna": ("Vienna, Austria", "travel", "high",
               "Vienna, Austria, not Vienna, VA: #131-132 are about flying over the Atlantic "
               "to Vienna, #133 is 'Springtime in Vienna' (Austria) and #139 is about the "
               "University of Vienna's botanical gardens"),
    "Vermont": ("Vermont", "travel", "low",
                "state only (Aug 2009); coordinates are Montpelier, the capital"),
    "Jupiter, FL": ("Jupiter, FL", "travel", "high", ""),
    "Pensacola,FL": ("Pensacola, FL", "travel", "high", ""),
    "Baltimore": ("Baltimore, MD", "travel", "high", ""),
    "Southington, CT": ("Southington, CT", "travel", "high", ""),
    "NYC": ("New York, NY", "travel", "high",
            "he lived in Brooklyn from 2012 to 2014, so some of these are his home city"),
    "Bennington, VT": ("Bennington, VT", "travel", "high", ""),

    # The move east, Nov 2011, and the months in Connecticut before Brooklyn
    "In The Car": (CONTEXT, "unknown", "low",
                   "in a car; each song takes the place of the nearest song with a real place"),
    "Tuscon, AC": ("Tucson, AZ", "travel", "high", "typo for Tucson, AZ; cross-country drive"),
    "Utah": ("Patagonia, AZ", "travel", "low",
             "the sheet says Utah, but #1043 is Tucson and #1045 is Ozona, TX on the same "
             "cross-country drive, and Utah is far off that route. The song mentions ending "
             "up in Patagonia, which fits Patagonia, AZ, an hour south of Tucson. Needs a "
             "check"),
    "Ozona, TX": ("Ozona, TX", "travel", "high", ""),
    "Austin, TX": ("Austin, TX", "travel", "high", ""),
    "New Orleans": ("New Orleans, LA", "travel", "high", ""),
    "Bristol, VA": ("Bristol, VA", "travel", "high", ""),
    "Charlottesville, VA": ("Charlottesville, VA", "travel", "high", ""),
    "Canton, CT": ("Canton, CT", "travel", "high",
                   "family; his base from Nov 2011 to Feb 2012, between Berkeley and Brooklyn"),
    "Avon, CT": ("Avon, CT", "travel", "high", "family"),
    "Barkhamsted, CT": ("Barkhamsted, CT", "travel", "high", ""),
    "Phuket, Thailand": ("Phuket, Thailand", "travel", "high", ""),
    "Pennsylvania": ("Pennsylvania", "travel", "low",
                     "state only; coordinates are Harrisburg, the capital. Mostly the yearly "
                     "Go For Pro gaming weekend (2012-2016) and one healthcare conference "
                     "(#3044, 2017)"),
    "Chicago": ("Chicago, IL", "travel", "high", ""),

    # Brooklyn years, 2012-2014
    "Brooklyn": ("Brooklyn, NY", "travel", "high",
                 "only 4 of the 10 songs are from while he lived in Brooklyn (2012); the "
                 "rest are visits (2011, 2015, 2019)"),
    "Brooklyn Studio": ("Brooklyn, NY", "studio", "high", "neighborhood not given"),
    "Williamsburg": ("Williamsburg, Brooklyn, NY", "home", "high", "Brooklyn neighborhood"),
    "Bushwick": ("Bushwick, Brooklyn, NY", "home", "high", "Brooklyn neighborhood"),
    "Park Slope": ("Park Slope, Brooklyn, NY", "home", "high", "Brooklyn neighborhood"),
    "Windsor Terrace": ("Windsor Terrace, Brooklyn, NY", "home", "high", "Brooklyn neighborhood"),
    "Windsor Terrace Studio": ("Windsor Terrace, Brooklyn, NY", "studio", "high", ""),
    "Brooklyn navy Yard": ("Brooklyn Navy Yard, Brooklyn, NY", "home", "high", ""),
    "Ronen's Brooklyn Studio": ("Brooklyn, NY", "studio", "high", "neighborhood not given"),
    "Dan Romer's Studio": ("Brooklyn, NY", "studio", "low",
                           "assumed to be in Brooklyn, where producer Dan Romer works; the "
                           "sheet doesn't say"),
    "Hospital": (CONTEXT, "unknown", "low",
                 "a hospital, Mar 2012; Brooklyn Studio and NYC songs on either side"),
    "The Garden Center": ("Wilmington, DE", "travel", "low",
                          "unnamed garden center; three of its six songs come straight after "
                          "Wilmington, DE songs, and #1259 is 'Raining in Delaware'"),
    "Wilmington, DE": ("Wilmington, DE", "travel", "high", ""),
    "Ludlow, MA": ("Ludlow, MA", "travel", "high", ""),
    "London": ("London, UK", "travel", "high",
               "London, England: Healthbox London, 'Platform Nine and Three-Quarters', a "
               "red-eye to London"),
    "Harrison, NY": ("Harrison, NY", "travel", "high", "Westchester County"),
    "Severna Park": ("Severna Park, MD", "travel", "high", "family"),
    "Montreal": ("Montreal, QC", "travel", "high", ""),
    "Denver": ("Denver, CO", "travel", "high", ""),
    "Minnesota": ("Minnesota", "travel", "low",
                  "state only (one song, Oct 2013); coordinates are Saint Paul, the capital"),
    "Burlington, VT": ("Burlington, VT", "travel", "high", ""),
    "Williams, MA": ("Williamstown, MA", "travel", "medium",
                     "no town is called Williams, MA; read as Williamstown (Williams "
                     "College)"),
    "Manitou Springs, CO": ("Manitou Springs, CO", "travel", "high", ""),
    "Colorado Springs, CO": ("Colorado Springs, CO", "travel", "high", ""),
    "Pueblo, CO": ("Pueblo, CO", "travel", "high", ""),
    "Croton On Hudson": ("Croton-on-Hudson, NY", "travel", "high", ""),

    # Jersey City years, 2014-2020
    "Jersey City": ("Jersey City, NJ", "home", "high", ""),
    "Jersey City2": ("Jersey City, NJ", "home", "high", "his second Jersey City home"),
    "Jersey City Studio": ("Jersey City, NJ", "studio", "high", ""),
    "Jersey City Studio2": ("Jersey City, NJ", "studio", "high", ""),
    "Jersey City Studio3": ("Jersey City, NJ", "studio", "high", ""),
    "Jersey City(Oskar's House)": ("Jersey City, NJ", "home", "high",
                                   "a friend's house in Jersey City"),
    "Salt Lake City": ("Salt Lake City, UT", "travel", "high", ""),
    "Berlin": ("Berlin, Germany", "travel", "high", ""),
    "Hanover, Germany": ("Hanover, Germany", "travel", "high", "Hannover"),
    "Toronto": ("Toronto, ON", "travel", "high", ""),
    "Cypress Hill, Brooklyn": ("Cypress Hills, Brooklyn, NY", "travel", "high",
                               "Cypress Hills, Brooklyn neighborhood"),
    "Minneapolis": ("Minneapolis, MN", "travel", "high", ""),
    "Misquomicut, RI": ("Misquamicut, RI", "travel", "high", "Misquamicut, in Westerly"),
    "Newark Airport": ("Newark, NJ", "travel", "high", "Newark Liberty airport"),
    "Simsbury, CT": ("Simsbury, CT", "travel", "high", ""),
    "Olivebridge, NY": ("Olivebridge, NY", "travel", "high", ""),
    "Vancouver": ("Vancouver, BC", "travel", "medium",
                  "assumed Vancouver, BC rather than Vancouver, WA; the two songs don't say"),
    "Washington, DC": ("Washington, DC", "travel", "high", ""),
    "Chester, NJ": ("Chester, NJ", "travel", "high", "Morris County"),
    "Morristown, NJ": ("Morristown, NJ", "travel", "high", ""),
    "Tillson, NY": ("Tillson, NY", "travel", "high", "summer 2017"),
    "Tillson, NY Studio": ("Tillson, NY", "studio", "high", ""),
    "Storm King": ("Storm King, NY", "travel", "medium",
                   "taken as Storm King Art Center in Mountainville, NY, a short drive from "
                   "the Tillson songs on either side"),
    "Palmer Rapids, Ontario": ("Palmer Rapids, ON", "travel", "high", ""),
    "St. Louis": ("St. Louis, MO", "travel", "high", ""),
    "Boston": ("Boston, MA", "travel", "high", ""),
    "nashville, TN": ("Nashville, TN", "travel", "high", ""),
    "Hackensack Children's Hospital": ("Hackensack, NJ", "travel", "high",
                                       "the children's hospital at Hackensack University "
                                       "Medical Center"),
    "Plano, TX": ("Plano, TX", "travel", "high", ""),
    "Flamig Farm": ("West Simsbury, CT", "travel", "medium",
                    "Flamig Farm is in West Simsbury, CT; Avon songs on either side"),
    "Stanclift Cove": (CONTEXT, "travel", "low",
                       "couldn't find a Stanclift Cove; the song is about kayaking 'at sea', "
                       "so probably the Connecticut or Rhode Island shore. Avon songs on "
                       "either side"),
    "Windsor CT": ("Windsor, CT", "travel", "high", ""),
    "Atlanta": ("Atlanta, GA", "travel", "high", ""),
    "East Hanover, NJ": ("East Hanover, NJ", "travel", "high", ""),
    "In The Air": (CONTEXT, "unknown", "low",
                   "on a plane; each song takes the place of the nearest song with a real "
                   "place (usually where the flight left from)"),
    "Prague": ("Prague, Czechia", "travel", "high", ""),
    "Victoria, BC": ("Victoria, BC", "travel", "high", ""),
    "Orlando": ("Orlando, FL", "travel", "high", ""),
    "Teaneck, NJ": ("Teaneck, NJ", "travel", "high", ""),
    "Philly": ("Philadelphia, PA", "travel", "high", ""),
    "Hot Springs, VA": ("Hot Springs, VA", "travel", "high", ""),
    "Secaucus, NY": ("Secaucus, NJ", "travel", "high",
                     "Secaucus is in New Jersey; the sheet says NY"),
    "Alexandria, MN": ("Alexandria, MN", "travel", "high", ""),
    "Eagan, MN": ("Eagan, MN", "travel", "high", ""),
    "Midland, TX": ("Midland, TX", "travel", "high", ""),
    "Keene, NH": ("Keene, NH", "travel", "high", ""),
    "Severna Park Studio": ("Severna Park, MD", "studio", "high",
                            "spring 2020, with family"),

    # Hartford years, 2020 to now
    "Hartford, CT": ("Hartford, CT", "home", "high", ""),
    "Hartford, CT Studio": ("Hartford, CT", "studio", "high", ""),
    "Hartford, CT Studio 2": ("Hartford, CT", "studio", "high", ""),
    "Hartford, CT Studio 3": ("Hartford, CT", "studio", "high", ""),
    "Hartford, CT Studio 4": ("Hartford, CT", "studio", "high", ""),
    "Downtown Hartford": ("Hartford, CT", "home", "high", ""),
    "Connecticut Convention Center": ("Hartford, CT", "home", "high", "in downtown Hartford"),
    "West Hartford APT": ("West Hartford, CT", "home", "high", ""),
    "West Hartford Conference Room": ("West Hartford, CT", "home", "high", ""),
    "Nyack, NY": ("Nyack, NY", "travel", "high", ""),
    "Lancaster, PA": ("Lancaster, PA", "travel", "high", ""),
    "Dutch Wonderland": ("Lancaster, PA", "travel", "high",
                         "Dutch Wonderland amusement park, Lancaster, PA"),
    "Nanuet, NY": ("Nanuet, NY", "travel", "high", ""),
    "Lake Welch": ("Lake Welch, NY", "travel", "high",
                   "Lake Welch, Harriman State Park (coordinates approximate)"),
    "Uconn Hostpital": ("Farmington, CT", "travel", "high",
                        "UConn Health hospital, Farmington, CT"),
    "Times Square": ("New York, NY", "travel", "high", ""),
    "Airport": (CONTEXT, "unknown", "low",
                "an airport; each song takes the place of the nearest song with a real place"),
    "Milford, CT": ("Milford, CT", "travel", "high", ""),
    "Bogota, Columbia": ("Bogotá, Colombia", "travel", "high", "Devcon 6, Oct 2022"),
    "Sturbridge, MA": ("Sturbridge, MA", "travel", "high", ""),
    "Barcelona": ("Barcelona, Spain", "travel", "high", ""),
    "Copenhagen": ("Copenhagen, Denmark", "travel", "high", ""),
    "Weatogue, CT": ("Weatogue, CT", "travel", "high", "village in Simsbury"),
    "Weatauge, CT": ("Weatogue, CT", "travel", "high", "spelling of Weatogue, in Simsbury"),
    "School": (CONTEXT, "unknown", "low", "his daughter's school, near home"),
    "In The Woods": (CONTEXT, "unknown", "low", "somewhere outdoors, near home"),
    "Oakland, MD": ("Oakland, MD", "travel", "high", "Garrett County, family road trip"),
    "The Rock Maze": ("Oakland, MD", "travel", "medium",
                      "a rock formation on the Oakland, MD trip; Oakland songs on either side"),
    "Newark, NJ": ("Newark, NJ", "travel", "high", ""),
    "Saratoga Springs": ("Saratoga Springs, NY", "travel", "high",
                         "Saratoga Springs, NY (a lake week, Aug 2024), not the one in Utah"),
    "Essex Junction, VT": ("Essex Junction, VT", "travel", "high", ""),
    "Westford, VT": ("Westford, VT", "travel", "high", ""),
    "On A Tree Stump": (CONTEXT, "unknown", "low",
                        "a tree cut down 'last week', so probably at home"),
    "Puerto Rico": ("San Juan, PR", "travel", "low",
                    "island only; coordinates are San Juan. One song mentions El Yunque, in "
                    "the much wetter east"),
    "Studio ROAR": (CONTEXT, "studio", "low",
                    "a friend's new studio; Hartford songs on either side"),
    "Doctor's Office": (CONTEXT, "unknown", "low", "near home"),
    "Owen's House": (CONTEXT, "unknown", "low", "a friend's house; Hartford songs on either side"),
    "Prospect Park": ("Prospect Park, Brooklyn, NY", "travel", "high", ""),
    "Downtown Brooklyn": ("Downtown Brooklyn, Brooklyn, NY", "travel", "high", ""),
    "Roulette": ("Downtown Brooklyn, Brooklyn, NY", "travel", "high",
                 "Roulette Intermedium, 509 Atlantic Ave, Brooklyn (#6133, live at "
                 "Kinference 2025)"),
    "In The Park": (CONTEXT, "unknown", "low", "a park, near home"),
    "Manchester, CT": ("Manchester, CT", "travel", "high", ""),
    "Bayonne, NJ": ("Bayonne, NJ", "travel", "high", ""),
    "Maryland": ("Severna Park, MD", "travel", "medium",
                 "state only; Christmas 2025 and June 2026, taken to be family in Severna Park"),
    "New Jersey": ("New Jersey", "travel", "low",
                   "state only (#6211, on the way home from Maryland); coordinates are "
                   "Trenton, the capital, which is on that drive"),
    "Palo Alto, CA": ("Palo Alto, CA", "travel", "high", ""),
    "Burlingame, CA": ("Burlingame, CA", "travel", "high", ""),
    "Paramus, NJ": ("Paramus, NJ", "travel", "high", ""),
    "Charles' Studio": (CONTEXT, "studio", "low",
                        "a friend's studio; Hartford songs on either side"),
    "Palm Springs": ("Palm Springs, CA", "travel", "high", ""),
}

# The few songs where "nearest song with a real place" picks wrong: number -> (place, note).
SONG_OVERRIDES = {
    1761: ("Brooklyn, NY",
           "'Go Faster, Cab' is a cab ride home; the nearest songs are Minnesota (#1760) and "
           "Brooklyn Studio (#1762), and the earlier one would win the tie"),
}


# ---------------------------------------------------------------------------- catalog


def load_catalog(catalog_dir=CATALOG_DIR):
    """Every song in the songaday-display catalog, as {number: song}, oldest first.

    The folder can hold two hashed copies of a chunk (index-3-aaaa.json, index-3-bbbb.json)
    from different builds. Files are read oldest first, so a song in a newer file replaces
    the older copy.
    """
    files = sorted(Path(catalog_dir).expanduser().glob("index-*.json"),
                   key=lambda path: path.stat().st_mtime)
    if not files:
        sys.exit(f"No index-*.json chunks in {catalog_dir}. Set SONGADAY_CATALOG_DIR.")
    songs = {}
    for path in files:
        for song in json.loads(path.read_text())["songs"]:
            songs[song["n"]] = song
    return dict(sorted(songs.items()))


# ---------------------------------------------------------------------------- network


def fetch_json(url, params, what):
    """GET a JSON API politely: one request at a time, a pause after each, and exponential
    backoff on 429 (rate limited) and 5xx errors."""
    for attempt in range(MAX_TRIES):
        try:
            response = requests.get(url, params=params, timeout=60,
                                    headers={"User-Agent": USER_AGENT})
        except requests.RequestException as error:
            status, problem = None, str(error)
        else:
            if response.status_code == 200:
                time.sleep(REQUEST_PAUSE)
                return response.json()
            status, problem = response.status_code, response.text[:200]
            if status not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{what}: HTTP {status}: {problem}")
        wait = 2 ** attempt * (5 if status == 429 else 2)
        print(f"  {what}: {status or 'network error'}, retrying in {wait}s ({problem})")
        time.sleep(wait)
    raise RuntimeError(f"{what}: gave up after {MAX_TRIES} tries")


def slug(text):
    """A file-name-safe version of a string."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def plain(text):
    """Lowercase without accents, for comparing names ("Bogotá" == "bogota")."""
    return slug(text or "").replace("-", " ")


def geocode_search(name, country):
    """Up to 100 geocoder results for a name in one country, cached on disk."""
    path = GEOCODE_CACHE / f"{slug(name)}--{country.lower()}.json"
    if path.exists():
        return json.loads(path.read_text()).get("results", [])
    params = {"name": name, "count": 100, "language": "en", "format": "json",
              "countryCode": country}
    print(f"  geocoding {name!r} ({country})")
    answer = fetch_json(GEOCODE_URL, params, f"geocode {name}")
    GEOCODE_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(answer, ensure_ascii=False, indent=1))
    return answer.get("results", [])


def pick_result(results, spec):
    """The best geocoder result for a PLACES spec: it must be in the right state/county (and
    feature class, if given); then an exact name match beats a partial one, a populated
    place beats a park or a mountain, and a bigger population wins."""
    def matches(result):
        if spec.get("admin1") and plain(spec["admin1"]) not in plain(result.get("admin1")):
            return False
        if spec.get("admin2") and plain(spec["admin2"]) not in plain(result.get("admin2")):
            return False
        if spec.get("feature") and not str(result.get("feature_code", "")).startswith(
                spec["feature"]):
            return False
        return True

    def rank(item):
        order, result = item
        exact = plain(result.get("name")) == plain(spec["query"])
        populated = str(result.get("feature_code", "")).startswith("PPL")
        return (not exact, not populated, -(result.get("population") or 0), order)

    candidates = [(order, r) for order, r in enumerate(results) if matches(r)]
    if not candidates:
        return None
    return min(candidates, key=rank)[1]


def locate(label, spec):
    """Coordinates and names for one canonical place."""
    if "lat" in spec:
        return {"place": label, "city": spec["city"], "region": spec["region"],
                "country": spec["country"], "lat": spec["lat"], "lon": spec["lon"],
                "source": f"fixed: {spec['why']}"}
    result = pick_result(geocode_search(spec["query"], spec["country"]), spec)
    if result is None:
        sys.exit(f"Geocoder found nothing for {label!r} ({spec}). Fix PLACES.")
    city = result["name"] if spec.get("city") is None else spec["city"]
    return {"place": label, "city": city, "region": result.get("admin1", ""),
            "country": result.get("country") or spec.get("country_name") or "",
            "lat": result["latitude"], "lon": result["longitude"],
            "source": f"geocoder: {result['name']}, {result.get('admin1', '')} "
                      f"({result.get('feature_code', '')}, GeoNames {result.get('id')})"}


def geocode_unlisted(raw):
    """Best effort for a Location string missing from LOCATIONS: try the US, then anywhere."""
    for country in ("US", None):
        params = {"name": raw.split(",")[0].strip(), "count": 10, "language": "en",
                  "format": "json"}
        if country:
            params["countryCode"] = country
        path = GEOCODE_CACHE / f"unlisted--{slug(raw)}--{(country or 'any').lower()}.json"
        if path.exists():
            results = json.loads(path.read_text()).get("results", [])
        else:
            answer = fetch_json(GEOCODE_URL, params, f"geocode {raw}")
            GEOCODE_CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(answer, ensure_ascii=False, indent=1))
            results = answer.get("results", [])
        if results:
            result = results[0]
            return {"place": f"{result['name']}, {result.get('admin1', '')}".strip(", "),
                    "city": result["name"], "region": result.get("admin1", ""),
                    "country": result.get("country", ""), "lat": result["latitude"],
                    "lon": result["longitude"], "source": "geocoder, first hit"}
    return None


# ---------------------------------------------------------------------------- mapping


def build():
    """Map every song to a place.

    Returns (places, songs_out, unlisted):
      places     {place label: located place dict}
      songs_out  one dict per song: number, date, location_raw, place, lat, lon, confidence,
                 how (fixed | context | override)
      unlisted   Location strings that weren't in LOCATIONS
    """
    catalog = load_catalog()
    raw_by_song = {n: (song["a"].get("Location") or "").strip() for n, song in catalog.items()}

    # Check the tables against each other and against the catalog.
    for raw, (label, kind, confidence, _note) in LOCATIONS.items():
        assert label == CONTEXT or label in PLACES, f"{raw!r} -> unknown place {label!r}"
        assert kind in KINDS and confidence in CONFIDENCES, raw
    used = set(raw_by_song.values())
    for raw in sorted(set(LOCATIONS) - used):
        print(f"  note: LOCATIONS entry {raw!r} isn't in the catalog any more")

    # Locate every canonical place that's in use.
    needed = {LOCATIONS[raw][0] for raw in used if raw in LOCATIONS} - {CONTEXT}
    needed |= {place for place, _ in SONG_OVERRIDES.values()}
    places = {label: locate(label, PLACES[label]) for label in sorted(needed)}

    # Strings nobody has mapped yet: geocode them as-is, or treat them as context.
    unlisted = {}
    for raw in sorted(used - set(LOCATIONS)):
        found = geocode_unlisted(raw) if raw else None
        if found:
            places.setdefault(found["place"], found)
            unlisted[raw] = (found["place"], "unknown", "low",
                             "not in LOCATIONS yet; first geocoder hit, unchecked")
        else:
            unlisted[raw] = (CONTEXT, "unknown", "low",
                             "not in LOCATIONS yet and the geocoder found nothing")
    table = {**LOCATIONS, **unlisted}

    # Songs with a real place first, then context songs borrow from the nearest of those.
    fixed_place = {n: table[raw][0] for n, raw in raw_by_song.items()
                   if table[raw][0] != CONTEXT}
    numbers = sorted(catalog)
    songs_out = []
    for n in numbers:
        raw = raw_by_song[n]
        label, _kind, confidence, _note = table[raw]
        how = "fixed"
        if n in SONG_OVERRIDES:
            label, confidence, how = SONG_OVERRIDES[n][0], "medium", "override"
        elif label == CONTEXT:
            label, confidence, how = nearest_fixed(n, fixed_place, numbers), "low", "context"
        place = places[label]
        songs_out.append({"number": n, "date": catalog[n]["d"], "location_raw": raw,
                          "place": label, "lat": place["lat"], "lon": place["lon"],
                          "confidence": confidence, "how": how})
    return places, songs_out, table


def nearest_fixed(n, fixed_place, numbers):
    """The place of the nearest song with a real place; the earlier song wins a tie."""
    for distance in range(1, len(numbers)):
        for other in (n - distance, n + distance):
            if other in fixed_place:
                return fixed_place[other]
    raise RuntimeError(f"song {n}: no song anywhere has a real place")


def place_rows(places, songs_out, table):
    """One row per Location string, in order of first use."""
    by_raw = {}
    for song in songs_out:
        by_raw.setdefault(song["location_raw"], []).append(song)
    rows = []
    for raw, songs in sorted(by_raw.items(), key=lambda item: item[1][0]["number"]):
        label, kind, confidence, note = table[raw]
        resolved = Counter(song["place"] for song in songs)
        if label == CONTEXT:
            if len(resolved) == 1:
                label = next(iter(resolved))
                where = (f"its one song resolves to {label}" if len(songs) == 1
                         else f"all {len(songs)} songs resolve to {label}")
            else:
                label = ""
                where = "resolves per song: " + ", ".join(
                    f"{place} x{count}" for place, count in resolved.most_common())
            note = f"{note}. Not a fixed place, {where}" if note else where
        place = places.get(label, {})
        if place.get("source", "").startswith("fixed"):
            note = f"{note}; coordinates {place['source']}" if note else place["source"]
        rows.append({
            "location_raw": raw, "place": label, "city": place.get("city", ""),
            "region": place.get("region", ""), "country": place.get("country", ""),
            "lat": place.get("lat", ""), "lon": place.get("lon", ""),
            "kind": kind, "confidence": confidence, "note": note,
            "songs": len(songs), "first_date": songs[0]["date"], "last_date": songs[-1]["date"],
        })
    return rows


def main():
    places, songs_out, table = build()
    rows = place_rows(places, songs_out, table)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    # A short report.
    songs_by = Counter(song["confidence"] for song in songs_out)
    strings_by = Counter(row["confidence"] for row in rows)
    kinds = Counter()
    for row in rows:
        kinds[row["kind"]] += row["songs"]
    how = Counter(song["how"] for song in songs_out)
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}: {len(rows)} Location strings, "
          f"{len(places)} distinct places, {len(songs_out)} songs")
    print("  strings by confidence:", dict(strings_by))
    print("  songs by confidence:  ", dict(songs_by))
    print("  songs by kind:        ", dict(kinds))
    print("  songs placed by:      ", dict(how))
    unlisted = sorted(set(table) - set(LOCATIONS))
    if unlisted:
        print(f"  {len(unlisted)} Location strings aren't in LOCATIONS yet (add them):")
        for raw in unlisted:
            print(f"    {raw!r} -> {table[raw][0]}")


if __name__ == "__main__":
    main()
