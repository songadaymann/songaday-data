# Data and assets

The code in this repository is covered by [LICENSE](LICENSE). This file covers the data: where
each part comes from and what you may do with it.

## 1. Ours: included and open

| Path | What it is | Source | License |
| --- | --- | --- | --- |
| `dataset/` (song columns) | Song number, date, title, location, topic, instruments, mood, beard, genre, styles, nouns, length, key, tempo, video ID and description for every Song A Day song | Jonathan Mann's public song spreadsheet (https://docs.google.com/spreadsheets/d/15BqqJ1TY77jdb9IkLcGrmrBNIpyfbkSwgevtabzQgcA) and the songaday-display catalog | CC BY 4.0. Credit "Jonathan Mann (Song A Day)". |

## 2. Free third-party: included under their own licenses

| Path | Source | License |
| --- | --- | --- |
| `dataset/` (weather columns) | Open-Meteo historical weather API, https://open-meteo.com/ | CC BY 4.0. "Weather data by Open-Meteo.com" |
| `dataset/` (place coordinates) | Open-Meteo geocoding (GeoNames), https://open-meteo.com/en/docs/geocoding-api | CC BY 4.0 |
| `dataset/` (news columns) | Wikipedia, "Portal:Current events", https://en.wikipedia.org/wiki/Portal:Current_events | CC BY-SA 4.0. Derived files that include headline text are under CC BY-SA 4.0 too. |
| `dataset/` (moon and planet columns) | Computed here from astronomical formulas | Same as the code |

## 3. Licensed (paid or restricted): not included

None.

## 4. Not ours and not licensed: never in the repo

| What | Why it's excluded |
| --- | --- |
| Song audio, video and stills | They live in R2 and on YouTube; this repo only holds data about them |
| API keys | Kept in `.env` (see `.env.example`) |

## Never commit

Ripped songs or videos, press, stock, or Getty photos, photos or likenesses of real people, other NFT collections' art, screenshots of commercial software, the source files of paid asset packs, voice models with noncommercial terms, and personal data.
