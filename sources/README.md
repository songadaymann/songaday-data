# The pipeline

Each script in this folder fetches or computes one kind of data and writes one table to
`dataset/`. `merge.py` then joins them into `dataset/songaday.csv`, one row per song. The
columns are documented in [`dataset/README.md`](../dataset/README.md).

Run everything from the repo root with the project's Python (3.11 or newer):

```bash
.venv/bin/python sources/run_all.py
```

## Order

| # | Step | Script | Reads | Writes | Network on a cold cache | Rerun |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | songs | `songs.py` | the public song spreadsheet (CSV, .xlsx and htmlview exports), the songaday-display catalog, YouTube oEmbed for disputed IDs | `dataset/songs.csv`, `analysis/sheet-fixes.csv` | a few requests, plus about 40 oEmbed lookups | about 1-3 s |
| 2 | places | `places.py` | the catalog's Location strings, the Open-Meteo geocoder | `dataset/places.csv` | about 126 geocoder lookups | about 1 s |
| 3 | weather | `weather.py` | `places.py` (imported, so it runs after it), the Open-Meteo historical archive | `dataset/weather.csv` | 616 requests, about 10 minutes | about 1 s |
| 4 | sky | `sky.py` | nothing (computed with PyEphem); NASA's two eclipse catalog pages, only to check the eclipses | `dataset/sky.csv` | 2 requests | about 7-13 s |
| 5 | views | `views.py` | the songaday-toolkit's YouTube snapshot, the songaday.fan app's sheet export, songaday.fan's ratings API, and the YouTube Data API if a key is set | `dataset/views.csv` | 66 ratings requests, about 1 minute | about 1-3 s |
| 6 | news | `news.py` | Wikipedia's Portal:Current events through the MediaWiki API, the catalog | `dataset/news.csv`, `dataset/news_matches.csv` | 214 requests, about 19 minutes | about 50 s |
| 7 | merge | `merge.py` | every table above | `dataset/songaday.csv` | none | about 1 s |

Only two orderings matter: `weather.py` imports `places.py`, and `merge.py` comes last. Steps
1-6 don't read each other's output.

Every download is cached under `cache/<step>/` (ignored by Git), so nothing is fetched twice.
All requests are sequential, send the User-Agent
`songaday-data/0.1 (github.com/songadaymann/songaday-data)`, and back off on HTTP 429.

## run_all.py

```bash
.venv/bin/python sources/run_all.py                    # every step; offline where the cache exists
.venv/bin/python sources/run_all.py --fetch            # let each step fetch what's new or missing
.venv/bin/python sources/run_all.py --only weather,merge
.venv/bin/python sources/run_all.py --from views       # that step and every one after it
.venv/bin/python sources/run_all.py --allow-gaps       # passed on to merge.py
```

By default a step whose cache is already there runs with `--offline`, so a rerun makes no web
requests. With a full cache the whole pipeline takes about a minute (most of it `news.py`)
and reproduces the committed tables byte for byte. `places.py` and `sky.py` have no offline
switch; they only go online for something not yet cached (a new Location string, NASA's
eclipse pages). A step with no cache at all downloads what it needs. `run_all.py` stops at
the first step that fails and exits with its code.

## Each script on its own

```bash
.venv/bin/python sources/songs.py              # downloads only what isn't cached
.venv/bin/python sources/songs.py --refresh    # downloads the spreadsheet again
.venv/bin/python sources/songs.py --offline    # cache only

.venv/bin/python sources/places.py             # geocoder answers are cached

.venv/bin/python sources/weather.py            # fetches only missing or provisional months
.venv/bin/python sources/weather.py --offline

.venv/bin/python sources/sky.py                # prints 15 sanity checks; exits 1 if one fails

.venv/bin/python sources/views.py              # fetches only what isn't cached
.venv/bin/python sources/views.py --offline
.venv/bin/python sources/views.py --refresh-fan        # new songaday.fan ratings snapshot
.venv/bin/python sources/views.py --refresh-youtube    # new YouTube snapshot (needs YOUTUBE_API_KEY)

.venv/bin/python sources/news.py               # fetches missing months, then builds
.venv/bin/python sources/news.py --offline
.venv/bin/python sources/news.py --refresh-recent     # refetch months still being edited when cached

.venv/bin/python sources/merge.py              # checks everything, then writes songaday.csv
.venv/bin/python sources/merge.py --allow-gaps # write even if a table is behind the song list
```

`merge.py` fails loudly, and writes nothing, when the song numbers have gaps or repeats, a
date doesn't match its song number, a table has repeated keys or rows for songs that don't
exist, a Location string has no place, `weather.csv` and `places.csv` disagree on a place, a
home-era boundary doesn't land on a song at that home, or a table doesn't cover every song
(unless `--allow-gaps`). It then prints each table's coverage and the blank rate of every
column, and warns if `dataset/README.md` misses a column.

## Settings

All optional. Put them in `.env` (copy `.env.example`) or the environment.

| Variable | Used by | Default |
| --- | --- | --- |
| `SONGADAY_CATALOG_DIR` | songs, places, weather, views, news | `~/Library/Caches/songaday-display/publish/meta` |
| `SONGADAY_CATALOG_REPORT` | songs | `../songaday-display/output/catalog-report.json` |
| `SONGADAY_TOOLKIT_DIR` | views | `../songaday-toolkit` |
| `SONGADAY_FAN_APP_DIR` | views | `../song-a-day-rating-app` |
| `YOUTUBE_API_KEY` | views | none; without it the views come from the last snapshot |

## Running it without Jonathan's machine

The committed tables in `dataset/` are the result; you don't need to run anything to use
them. To rebuild, most steps need the songaday-display catalog, a local cache built from
Jonathan's working spreadsheet. Without it:

- `songs.py` falls back to the public spreadsheet alone, which stops at #5101 (2022-12-19).
- `places.py`, `weather.py`, `views.py` and `news.py` stop with a message asking for
  `SONGADAY_CATALOG_DIR`.
- `sky.py` and `merge.py` work as they are.

## Adding new songs

1. Refresh the songaday-display catalog (in that project), so it has the new songs.
2. In `news.py`, move `LAST_DAY` to the day before today's song. After 2026, move `LAST_DAY`
   in `sky.py` too (it stops at 2026-12-31).
3. Run `.venv/bin/python sources/run_all.py --fetch`. Weather fetches the new months, views
   and news the new days, and merge checks that every table covers every song.
4. For fresh YouTube counts, set `YOUTUBE_API_KEY` and run `views.py --refresh-youtube`.
