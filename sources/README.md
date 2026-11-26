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
| 7 | sales | `sales.py` | the sale contracts on Ethereum, Zora and Base through public nodes; Coinbase's daily ETH price | `dataset/sales.csv` | about 1,100 requests, about 15 minutes | about 2 s |
| 8 | merge | `merge.py` | every table above | `dataset/songaday.csv` | none | about 1 s |

Only two orderings matter: `weather.py` imports `places.py`, and `merge.py` comes last. Steps
1-7 don't read each other's output (`sales.py` reads `songs.csv` only for the last song number).

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

## Estimated modes (an extra step)

`modes.py` isn't in `run_all.py`: it needs Essentia, which is large and isn't in
`pyproject.toml`, and it downloads about 1.5 GB of audio on a cold cache. It reads
`dataset/songaday.csv` and `dataset/bandcamp.csv` and writes `dataset/mode_estimates.csv`,
major or minor for the 429 songs whose sheet entry gives only the root. `merge.py` doesn't
read it. The method and its accuracy are in the script's docstring.

```bash
uv run --no-project --with essentia --with requests python sources/modes.py           # cache only
uv run --no-project --with essentia --with requests python sources/modes.py --fetch   # download missing audio (one request a second)
uv run --no-project --with essentia --with requests python sources/modes.py --check   # also score it on songs whose mode is known
```

Audio is cached in `cache/modes/audio/`, measurements in `cache/modes/measured.json`.

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

.venv/bin/python sources/sales.py              # fetches only what isn't cached
.venv/bin/python sources/sales.py --offline
.venv/bin/python sources/sales.py --refresh    # also read sales newer than the cache
.venv/bin/python sources/sales.py --contracts  # print the list of contracts below

.venv/bin/python sources/merge.py              # checks everything, then writes songaday.csv
.venv/bin/python sources/merge.py --allow-gaps # write even if a table is behind the song list
```

`merge.py` fails loudly, and writes nothing, when the song numbers have gaps or repeats, a
date doesn't match its song number, a table has repeated keys or rows for songs that don't
exist, a Location string has no place, `weather.csv` and `places.csv` disagree on a place, a
home-era boundary doesn't land on a song at that home, or a table doesn't cover every song
(unless `--allow-gaps`). It then prints each table's coverage and the blank rate of every
column, and warns if `dataset/README.md` misses a column.

## The sale contracts

Song A Day songs have been sold as NFTs through a different contract every year or two.
`sales.py` reads each one; `chainlogs.py` holds the node addresses and the cache. No key or
account is needed. **This list was put together from the songaday.world code and the chains
themselves on 2026-11-26. Jonathan looked it over the same day and called it "more or less
right"; the rows marked "to confirm" are still open.**

| Venue | Chain | Contract | Years | Songs | How a sale shows up | Read? |
| --- | --- | --- | --- | --- | --- | --- |
| `opensea_2021` | Ethereum | OpenSea shared storefront `0x495f947276749Ce646f68AC8c248420045cb7b5e`, tokens made by `0x3d9456Ad6463a77bD77123Cb4836e463030bfAb4` | 2021 | 1-730 | `TransferSingle` out of that wallet, with `OrdersMatched` on OpenSea's exchange `0x7Be8076f4EA4A4AD08075C2508e481d6C946D12b` in the same transaction | yes |
| `mint_2021` | Ethereum | Song A Day collection `0x19b703f65aA7E1E775BD06c2aa0D0d08c80f1C45`, `publicMint` | 2021-12-31 | 731-4748 | `Transfer` from the zero address in a transaction that pays 0.2 ETH a song | yes |
| (upgrade) | Ethereum | same collection, `publicClaim` | 2021-12 to 2023 | 1-730 | the 2021 tokens swapped one for one; no payment, so not a sale | not a sale |
| `zora_2022` | Ethereum | Zora auction house `0xE468cE99444174Bd3bBBEd09209577d25D1ad673` | 2022 | 4749-5118 | `AuctionEnded` (winner, amount), `AuctionBid` | yes |
| `gbm_v1` | Ethereum | `0xd736d2c76fba2ba5a217fd4edfa1b231deeeb29d` | Jan-Mar 2023 | 5119-5202 | `Auction_Initialized`, `Auction_BidPlaced` (the last one wins), `Auction_Claimed` | yes |
| `gbm_v2` | Ethereum | `0x1c51Abab1160879e697733124da80e4072590BBD` | Apr-Dec 2023 | 5203-5478 | same events | yes |
| sound.xyz | Ethereum | one contract per song, not yet listed | Dec 2023 to Feb 2024 | 5479-5529 | edition mints; the original went to one edition buyer picked at random | **no** |
| `gbm_zora` | Zora | `0x2cc2D8256798b35a4c1D181284127BAaCa750014` | 2024 | 5530-5844 | same GBM events | yes |
| `gbm_base` | Base | `0xEaedaDe6A47b08f21C6c0B319024c6fedA3E6539` (69 songs, from #5845) then `0xd7829F0EFC16086a91Cf211CFbb0E4Ef29D16BEE` (581) | 2025 to Oct 2026 | 5845-6500 | stored values `getAuctionIDSongADao`, `getAuctionHighestBid`, `getAuctionHighestBidder`, `getAuctionEndTime` | yes |
| `auction_2026` | Base | SongADayAuction `0xFd8126142d2C6c4FA4c0DFe6694FF71413666D38` | from 2026-10-19 | 6501 on | stored `getAuction(song)`; events `BidPlaced`, `AuctionSettled` | yes |
| resales | Ethereum | Song A Day collection `0x19b7...1C45` | from 2021-12-31 | any | `Transfer` with a sale event in the same transaction: OpenSea `OrdersMatched` or Seaport `OrderFulfilled`, Blur `OrdersMatched` / `Execution721Packed`, LooksRare `TakerBid` / `TakerAsk` | yes |
| editions | Optimism | `0x9c17564ccaa0bae1d3883251cae70ca86ef3ec41` | to confirm | to confirm | `Mint_Initialized`, `TransferSingle` | **no** |
| editions | Zora, Base | on Base `0xb3bad5fe12268edc8a52ff786076c1d1fa92ef0d`; the Zora one is not yet listed | 2024 to 2026 | 5530-6500 | Zora-protocol `Purchased`, beside each GBM auction | **no** |
| patron editions | Ethereum | `0x3e290d6f5C66b1FAABd072Db9E0d223EDEfC7ab5` | from 2026-10-19 | 6501 on | `EditionMinted` (paid or supporter) | **no** |

Why Base is read differently: no free Base node keeps old event logs, so `sales.py` asks the
auction contracts what they store for each song. Every Base and Zora auction result was
compared once with the Goldsky indexes songaday.world used (962 auctions, all equal).

Checked by hand against Etherscan, BaseScan and the Zora explorer on 2026-11-26 (price and date; buyer where the explorer shows the address): #100
(opensea_2021), #2000 (mint_2021), #5000 (zora_2022), #5174 (gbm_v1), #5369 (gbm_v2), #5689
(gbm_zora), #6000 (gbm_base), #6538 (auction_2026), and the resales of #3182 (OpenSea old
exchange), #4523 (Seaport), #157 (Blur) and #1465 (LooksRare).

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
