# Bandcamp, Apple Music and Spotify links

Made by `sources/links.py` from `dataset/bandcamp.csv`, `dataset/apple_music.csv`. It covers songs #1 to #6502 (2026-10-20). The full table is `dataset/links.csv`; `analysis/sheet-backfill-links.csv` has only the links rated **high**.

## In short

- **Bandcamp:** 6,469 of 6,502 songs have a link (99.5%); 6,447 are rated high and go in the sheet, 22 are left for you to check, and 33 have no track.
- **Apple Music:** 6,289 of 6,502 songs have a link (96.7%); 6,270 are rated high and go in the sheet, 19 are left for you to check, and 213 have no track.
- **Spotify:** not fetched yet, so this column is blank. See [Spotify](#spotify) below.
- 6,498 songs have at least one high link; 6,219 have a high link on every service fetched (Bandcamp and Apple Music).
- **Downloads and plays:** none of the three services publishes them. Bandcamp's album data has no play or download count (play_count is 0 or empty), Apple's iTunes API has none, and Spotify's Web API gives no stream counts. See [Downloads](#downloads-and-plays).

## The spreadsheet file

`analysis/sheet-backfill-links.csv` has one row per song, #1 to #6502, with the columns number, date (M/D/YYYY, like the sheet), title, bandcamp, apple_music, spotify. A cell is filled only when the link is rated high; blank means no track was found or the match isn't sure enough (those are listed below). The public sheet currently ends at #5113 (2022-12-31). Its songs run #1, #2, ... in order with no gaps (#1 is on row 3, under the note and the header row), so the file's first 5,113 rows line up with it row for row: copy the bandcamp, apple_music and spotify cells of #1 to #5113 and paste them into new columns starting at row 3. Rows #5114 to #6502 are for wherever you keep the later years.

For #1 to #5113: Bandcamp 5,061 links, Apple Music 4,906 links. For #5114 to #6502: Bandcamp 1,386, Apple Music 1,364.

## How sure a link is

Each fetch step matched its own tracks to songs by title and by position on the year, season or month album (match = exact, fuzzy or position-only). This step checks the services against each other:

- **high**: an exact title match, or a fuzzy one scoring 0.85 or more. A weaker match (position-only, or fuzzy below that) is high too when its audio backs it up: the same length, within 1.5 s, as another service's sure link for the same song, or, for a track on a year, season or month album, the catalog's Length to within 1.5 s. Bandcamp and Apple usually carry the same master: for songs on both, the median length gap is well under a second. A single or compilation track also needs a title only one song has, or audio that backs it up.
- **check**: linked, but left out of the sheet: a weak match nothing backs up; a file whose length is far from the other service's and the catalog's but within a second of a neighbouring song's (so it may play that song); a title that another service, or the catalog, gives a different song whose audio this track has; or a single whose title several songs share.
- A file that is far off the other service and the catalog, but doesn't look like any neighbouring song, keeps its rating: it is usually another take, an edit or padding. Those are listed below to listen to.

## Coverage by year

Each cell is linked / high (high is what the sheet gets).

| Year | Songs | Bandcamp | Apple Music | Spotify | Any high | All high |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2009 | 365 | 364 / 364 | 364 / 364 | not fetched | 365 | 363 |
| 2010 | 365 | 356 / 356 | 364 / 364 | not fetched | 365 | 355 |
| 2011 | 365 | 355 / 355 | 364 / 362 | not fetched | 365 | 352 |
| 2012 | 366 | 360 / 360 | 366 / 364 | not fetched | 366 | 358 |
| 2013 | 365 | 365 / 365 | 364 / 362 | not fetched | 365 | 362 |
| 2014 | 365 | 362 / 361 | 271 / 269 | not fetched | 362 | 268 |
| 2015 | 365 | 365 / 365 | 277 / 276 | not fetched | 365 | 276 |
| 2016 | 366 | 363 / 363 | 366 / 366 | not fetched | 366 | 363 |
| 2017 | 365 | 365 / 364 | 364 / 364 | not fetched | 365 | 363 |
| 2018 | 365 | 365 / 365 | 365 / 365 | not fetched | 365 | 365 |
| 2019 | 365 | 365 / 361 | 365 / 364 | not fetched | 365 | 360 |
| 2020 | 366 | 366 / 366 | 361 / 359 | not fetched | 366 | 359 |
| 2021 | 365 | 365 / 362 | 365 / 363 | not fetched | 365 | 360 |
| 2022 | 365 | 365 / 354 | 365 / 364 | not fetched | 364 | 354 |
| 2023 | 365 | 364 / 364 | 365 / 365 | not fetched | 365 | 364 |
| 2024 | 366 | 366 / 365 | 366 / 365 | not fetched | 366 | 364 |
| 2025 | 365 | 365 / 364 | 364 / 361 | not fetched | 365 | 360 |
| 2026 | 293 | 293 / 293 | 273 / 273 | not fetched | 293 | 273 |
| **all** | 6,502 | 6,469 / 6,447 | 6,289 / 6,270 | not fetched | 6,498 | 6,219 |

Match types: Bandcamp exact 6,232, fuzzy 214, none 33, position-only 23; Apple Music exact 5,916, fuzzy 357, none 213, position-only 16.

## What's missing and why

### Bandcamp: 33 songs with no track

- #355 'I'm Weak' (2009-12-21): 'Song A Day: Year One' goes straight from track 355 (#354) to track 356 (#356)
- #396 'Patience' (2010-01-31): 'Song A Day: Year Two' goes straight from track 30 (#395) to track 31 (#397)
- #401 'Link Mann Acoustic Style.' (2010-02-05): 'Song A Day: Year Two' goes straight from track 34 (#400) to track 35 (#402)
- #413 'The Whiskey Android' (2010-02-17): 'Song A Day: Year Two' goes straight from track 46 (#412) to track 47 (#414)
- #447 '42Below' (2010-03-23): 'Song A Day: Year Two' goes straight from track 79 (#446) to track 80 (#448)
- #509-#510 (2 songs): 'Song A Day: Year Two' goes straight from track 142 (#508) to track 143 (#511)
- #613 'Storefronts' (2010-09-05): 'Song A Day: Year Two' goes straight from track 244 (#612) to track 245 (#614)
- #622 'Questions For Coco' (2010-09-14): 'Song A Day: Year Two' goes straight from track 252 (#621) to track 253 (#623)
- #689 'Girl, You're In My Heart' (2010-11-20): 'Song A Day: Year Two' goes straight from track 327 (#688) to track 328 (#690)
- #776 'Happy Birthday Thomas Hughes!!!' (2011-02-15): not on 'Song A Day: Year Three'; the tracks around it are out of order (track 46 is #775, track 41 is #777) and none is left over
- #851 'And Them I am Gone' (2011-05-01): 'Song A Day: Year Three' goes straight from track 119 (#850) to track 120 (#852)
- #857-#858 (2 songs): 'Song A Day: Year Three' goes straight from track 124 (#856) to track 125 (#859)
- #897 'Fold into Yourself' (2011-06-16): 'Song A Day: Year Three' goes straight from track 162 (#896) to track 163 (#898)
- #903 'Heart of An Autoharp' (2011-06-22): 'Song A Day: Year Three' goes straight from track 167 (#902) to track 168 (#904)
- #911 'Smoke Signals' (2011-06-30): 'Song A Day: Year Three' goes straight from track 174 (#910) to track 175 (#912)
- #950 'Blame Yourself!' (2011-08-08): 'Song A Day: Year Three' goes straight from track 212 (#949) to track 213 (#951)
- #991 'This Ain't Over' (2011-09-18): 'Song A Day: Year Three' goes straight from track 252 (#990) to track 253 (#992)
- #1035 'Neither Do You' (2011-11-01): 'Song A Day: Year Three' goes straight from track 295 (#1034) to track 296 (#1036)
- #1107 'Win a FREE Song REQUEST!!!' (2012-01-12): 'Song A Day: Year Four' has an unmatched track in its slot: track 12 'Turtles' (148 s)
- #1157-#1159 (3 songs): 'Song A Day: Year Four' goes straight from track 60 (#1156) to track 61 (#1160)
- #1162 'Joseph Kony' (2012-03-07): 'Song A Day: Year Four' goes straight from track 62 (#1161) to track 63 (#1163)
- #1418 'What a Shame' (2012-11-18): 'Song A Day: Year Four' goes straight from track 318 (#1417) to track 319 (#1419)
- #2058 'Every Movie Robot SUPERCUT' (2014-08-20): 'Song A Day: Year Six' has an unmatched track in its slot: track 232 'The Robots Don't Love You Anymore' (112 s)
- #2106 'You And I' (2014-10-07): 'Song A Day: Year Six' has an unmatched track in its slot: track 280 'I Can Get Everything I Need To Get Done By 10am' (72 s)
- #2128 'It's About Ethics in Journalism!' (2014-10-29): 'Song A Day: Year Six' goes straight from track 301 (#2127) to track 302 (#2129)
- #2615 'Randos Friending Me' (2016-02-28): 'Song A Day: Year Eight' goes straight from track 58 (#2614) to track 59 (#2616)
- #2650 'I Feel Sorry for Young People Who Don't Do Their Own Research' (2016-04-03): 'Song A Day: Year Eight' goes straight from track 94 (#2649) to track 95 (#2651)
- #2758 'Now I'm Home Won't You Kiss Me' (2016-07-20): 'Song A Day: Year Eight' goes straight from track 201 (#2757) to track 202 (#2759)
- #5172 'Say Pizza To Drugs, Say No To Yes (Redux)' (2023-02-28): 'Song A Day: Year Fifteen' has an unmatched track in its slot: track 59 'No Squeezy Baby' (71 s)

An unmatched track in a song's slot is usually a duplicate upload or a track whose length is too far from the song's to be paired by position (the Bandcamp step refused those rather than guess).

### Apple Music: 213 songs with no track

- #265 'Quantum Decoupling Transition in a One-Dimensional Feschbach Resonant Super Fluid' (2009-09-22): not on 'Summer, 2009' (93 tracks)
- #526 'Jew Wario At E3' (2010-06-10): not on 'Spring, 2010' (93 tracks)
- #750 'Hank Goes for a Walk' (2011-01-20): not on 'Winter, 2011' (90 tracks)
- #1792 'Some Thanksgiving Thoughts' (2013-11-27): not on 'Fall, 2013' (92 tracks)
- #1917-#2007 (91 songs): no 'Spring, 2014' album on Apple Music (US)
- #2008, #2058 (2 songs): not on 'Summer, 2014' (91 tracks)
- #2106 'You And I' (2014-10-07): not on 'Fall, 2014' (92 tracks)
- #2373-#2382, #2384-#2389, #2391-#2453, #2455-#2459, #2461-#2464 (88 songs): no 'Summer, 2015' album on Apple Music (US)
- #3087 'Jeff Sessions Supercut Song' (2017-06-14): not on 'Spring, 2017' (77 tracks)
- #4111, #4130 (2 songs): not on 'April, 2020' (27 tracks)
- #4140 'I Wonder What's Inside Your Butthole' (2020-05-02): not on 'May, 2020' (29 tracks)
- #4221 'Moms Are The Best!' (2020-07-22): not on 'July, 2020' (30 tracks)
- #4241 'Wet Ass P-Word (the Ben Shapiro Remix)' (2020-08-11): not on 'August, 2020' (29 tracks)
- #6180 'I Drink The Fire' (2025-12-02): not on 'December, 2025' (30 tracks)
- #6483-#6502 (20 songs): no 'October, 2026' album on Apple Music (US)

Spring 2014 and Summer 2015 have no album on Apple Music US (the fetch step also searched the iTunes Search API for them and found nothing); 4 Summer 2015 songs are linked from compilations instead. The newest month's album isn't out yet. A single song missing from an album that exists is usually a track left off when the album was distributed.

### Spotify

Not fetched. `sources/spotify.py` is written and tested against a fake API, but Spotify needs an app's client ID and secret even for read-only lookups, and there are none in `.env`. To fill the column:

1. Make a free app at https://developer.spotify.com/dashboard (any name, redirect URI `http://127.0.0.1:8888/callback`, tick Web API).
2. Put `SPOTIFY_CLIENT_ID=...` and `SPOTIFY_CLIENT_SECRET=...` in `.env` (it is gitignored).
3. Run `.venv/bin/python sources/spotify.py`, then `.venv/bin/python sources/links.py` again. The Spotify column and its checks fill in by themselves.

Spotify gets its releases from the same distributor as Apple, so expect roughly Apple's coverage, gaps included, but that is a guess until it runs.

## Where the services disagree

These links are rated **check** and left out of the sheet.

### Audio that looks like a neighbouring song (34)

The titles match, but this file's length is far from the other service's and the catalog's, and within a second of a song one or two days away. The service's titles are probably shifted against its audio, or two tracks are swapped, so the link may play the wrong song. Worth a listen, and possibly a fix with the distributor or on Bandcamp.

| # | Date | Title | Service | Their title | What doesn't fit |
| ---: | --- | --- | --- | --- | --- |
| 749 | 2011-01-19 | Hank is Paranoid | [Apple Music](https://music.apple.com/us/album/hank-is-paranoid/1137664327?i=1137664438) | Hank Is Paranoid | Apple Music: audio is 105 s against Bandcamp 66 s, catalog 64 s; it matches #750's length, so it may play that song |
| 755 | 2011-01-25 | The Mac vs. PC Conciliatory Song | [Apple Music](https://music.apple.com/us/album/the-mac-vs-pc-conciliatory-song/1137664327?i=1137664444) | The Mac Vs. PC Conciliatory Song | Apple Music: audio is 75 s against Bandcamp 122 s, catalog 174 s; it matches #756's length, so it may play that song |
| 1193 | 2012-04-07 | Your Day | [Apple Music](https://music.apple.com/us/album/your-day/1140021075?i=1140021087) | Your Day | Apple Music: audio is 70 s against Bandcamp 126 s, catalog 126 s; it matches #1192's length, so it may play that song |
| 1371 | 2012-10-02 | MItt Romney Flip Flop Autotune | [Apple Music](https://music.apple.com/us/album/mitt-romney-flip-flop-autotune/1140538127?i=1140538149) | Mitt Romney Flip Flop Autotune | Apple Music: audio is 68 s against Bandcamp 183 s, catalog 183 s; it matches #1370's length, so it may play that song |
| 1501 | 2013-02-09 | George W. Bush's Self Portraits | [Apple Music](https://music.apple.com/us/album/george-w-bushs-self-portraits/1141770796?i=1141770890) | George W. Bush's Self Portraits | Apple Music: audio is 149 s against Bandcamp 63 s, catalog 62 s; it matches #1500's length, so it may play that song |
| 1579 | 2013-04-28 | When It Rains You Feel It in Your Bones | [Apple Music](https://music.apple.com/us/album/when-it-rains-you-feel-it-in-your-bones/1144152073?i=1144152351) | When It Rains You Feel It in Your Bones | Apple Music: audio is 127 s against Bandcamp 233 s, catalog 233 s; it matches #1577's length, so it may play that song |
| 1975 | 2014-05-29 | Patreon Shoutout Song | [Bandcamp](https://jonathanmann.bandcamp.com/track/patreon-shoutout-song) | Patreon Shoutout Song | Bandcamp: audio is 212 s against catalog 151 s; it matches #1976's length, so it may play that song |
| 2182 | 2014-12-22 | All Signs Point | [Apple Music](https://music.apple.com/us/album/all-signs-point/1144217296?i=1144217708) | All Signs Point | Apple Music: audio is 144 s against Bandcamp 230 s, catalog 231 s; it matches #2183's length, so it may play that song; this song's audio may be under Apple Music's #2183 track |
| 2183 | 2014-12-23 | KEDQ! | [Apple Music](https://music.apple.com/us/album/kedq/1144217296?i=1144217709) | Kedq! | Apple Music: audio is 230 s against Bandcamp 144 s, catalog 145 s; it matches #2182's length, so it may play that song; this song's audio may be under Apple Music's #2182 track |
| 2966 | 2017-02-13 | Who's Gonna Take the Fall? | [Bandcamp](https://jonathanmann.bandcamp.com/track/whos-gonna-take-the-fall) | Who's Gonna Take the Fall? | Bandcamp: audio is 60 s against Apple Music 48 s, catalog 48 s; it matches #2967's length, so it may play that song |
| 3818 | 2019-06-15 | That Is Not A Heart Warming Story | [Apple Music](https://music.apple.com/us/album/that-is-not-a-heart-warming-story/1471706666?i=1471706686) | That Is Not a Heart Warming Story | Apple Music: audio is 164 s against Bandcamp 146 s, catalog 146 s; it matches #3819's length, so it may play that song |
| 3828 | 2019-06-25 | A Commissioner's Work Is Never Done | [Bandcamp](https://jonathanmann.bandcamp.com/track/a-commissioners-work-is-never-done) | A Commissioner's Work Is Never Done | Bandcamp: audio is 123 s against Apple Music 298 s, catalog 297 s; it matches #3829's length, so it may play that song |
| 3829 | 2019-06-26 | I'm With You | [Bandcamp](https://jonathanmann.bandcamp.com/track/im-with-you) | I'm With You | Bandcamp: audio is 148 s against Apple Music 123 s, catalog 124 s; it matches #3830's length, so it may play that song; this song's audio may be under Bandcamp's #3828 track |
| 3831 | 2019-06-28 | Marianne Williamson's Closing Remarks (Love Will Win) | [Bandcamp](https://jonathanmann.bandcamp.com/track/marianne-williamsons-closing-remarks-love-will-win) | Marianne Williamson's Closing Remarks (Love Will Win) | Bandcamp: audio is 167 s against Apple Music 65 s, catalog 70 s; it matches #3832's length, so it may play that song; this song's audio may be under Bandcamp's #3830 track |
| 3833 | 2019-06-30 | My LifeIs A Pile of Food Made Out Of Wood | [Bandcamp](https://jonathanmann.bandcamp.com/track/my-lifeis-a-pile-of-food-made-out-of-wood) | My LifeIs A Pile of Food Made Out Of Wood | Bandcamp: audio is 289 s against Apple Music 186 s, catalog 175 s; it matches #3834's length, so it may play that song; this song's audio may be under Bandcamp's #3832 track |
| 4678 | 2021-10-22 | What The Fuck? (worldcoin) | [Bandcamp](https://jonathanmann.bandcamp.com/track/what-the-fuck-worldcoin) | What The Fuck? (worldcoin) | Bandcamp: audio is 168 s against Apple Music 110 s, catalog 108 s; it matches #4679's length, so it may play that song; this song's audio may be under Bandcamp's #4676 track |
| 4679 | 2021-10-23 | What's The Floor Price of Your Heart | [Bandcamp](https://jonathanmann.bandcamp.com/track/whats-the-floor-price-of-your-heart) | What's The Floor Price of Your Heart | Bandcamp: audio is 68 s against Apple Music 168 s, catalog 167 s; it matches #4680's length, so it may play that song; this song's audio may be under Bandcamp's #4678 track |
| 4680 | 2021-10-24 | It's Halloween Again | [Bandcamp](https://jonathanmann.bandcamp.com/track/its-halloween-again) | It's Halloween Again | Bandcamp: audio is 127 s against Apple Music 68 s, catalog 67 s; it matches #4681's length, so it may play that song; this song's audio may be under Bandcamp's #4679 track |
| 4892 | 2022-05-24 | The Great King Snail | [Bandcamp](https://jonathanmann.bandcamp.com/track/the-great-king-snail) | The Great King Snail | Bandcamp: audio is 131 s against Apple Music 106 s, catalog 106 s; it matches #4893's length, so it may play that song; this song's audio may be under Bandcamp's #4891 track |
| 4893 | 2022-05-25 | And Now I'm Gone | [Bandcamp](https://jonathanmann.bandcamp.com/track/and-now-im-gone) | And Now I'm Gone | Bandcamp: audio is 181 s against Apple Music 131 s, catalog 130 s; it matches #4894's length, so it may play that song; this song's audio may be under Bandcamp's #4892 track |
| 4894 | 2022-05-26 | Don't Think About The Price of Eth, Watch My Driveway Get Paved Instead | [Bandcamp](https://jonathanmann.bandcamp.com/track/dont-think-about-the-price-of-eth-watch-my-driveway-get-paved-instead) | Don't Think About The Price of Eth, Watch My Driveway Get Paved Instead | Bandcamp: audio is 73 s against Apple Music 181 s, catalog 174 s; it matches #4895's length, so it may play that song; this song's audio may be under Bandcamp's #4893 track |
| 4895 | 2022-05-27 | Ropsten Trolls | [Bandcamp](https://jonathanmann.bandcamp.com/track/ropsten-trolls) | Ropsten Trolls | Bandcamp: audio is 155 s against Apple Music 73 s, catalog 66 s; it matches #4896's length, so it may play that song; this song's audio may be under Bandcamp's #4894 track |
| 4896 | 2022-05-28 | Saturday Morning Banjo Song | [Bandcamp](https://jonathanmann.bandcamp.com/track/saturday-morning-banjo-song) | Saturday Morning Banjo Song | Bandcamp: audio is 136 s against Apple Music 155 s, catalog 155 s; it matches #4897's length, so it may play that song; this song's audio may be under Bandcamp's #4895 track |
| 4897 | 2022-05-29 | Imposter Syndrome | [Bandcamp](https://jonathanmann.bandcamp.com/track/imposter-syndrome) | Imposter Syndrome | Bandcamp: audio is 152 s against Apple Music 136 s, catalog 132 s; it matches #4898's length, so it may play that song; this song's audio may be under Bandcamp's #4896 track |
| 4920 | 2022-06-21 | Jonathan's 2094th Dream | [Bandcamp](https://jonathanmann.bandcamp.com/track/jonathans-2094th-dream) | Jonathan's 2094th Dream | Bandcamp: audio is 200 s against Apple Music 257 s, catalog 257 s; it matches #4921's length, so it may play that song; this song's audio may be under Bandcamp's #4921 track |
| 4921 | 2022-06-22 | Creeps and Weirdos | [Bandcamp](https://jonathanmann.bandcamp.com/track/creeps-and-weirdos) | Creeps and Weirdos | Bandcamp: audio is 257 s against Apple Music 200 s, catalog 156 s; it matches #4920's length, so it may play that song; this song's audio may be under Bandcamp's #4920 track |
| 4921 | 2022-06-22 | Creeps and Weirdos | [Apple Music](https://music.apple.com/us/album/creeps-and-weirdos/1639460604?i=1639460687) | Creeps and Weirdos | Apple Music: audio is 200 s against Bandcamp 257 s, catalog 156 s; it matches #4920's length, so it may play that song; this song's audio may be under Apple Music's #4920 track |
| 4983 | 2022-08-23 | We Are Not Meant To Be Machines | [Bandcamp](https://jonathanmann.bandcamp.com/track/we-are-not-meant-to-be-machines) | We Are Not Meant To Be Machines | Bandcamp: audio is 146 s against Apple Music 122 s, catalog 122 s; it matches #4984's length, so it may play that song; this song's audio may be under Bandcamp's #4984 track |
| 4984 | 2022-08-24 | I'm Lost In The Machine | [Bandcamp](https://jonathanmann.bandcamp.com/track/im-lost-in-the-machine) | I'm Lost In The Machine | Bandcamp: audio is 122 s against Apple Music 146 s, catalog 145 s; it matches #4983's length, so it may play that song; this song's audio may be under Bandcamp's #4983 track |
| 4995 | 2022-09-04 | Sometimes I Don't Feel Like Writing Another Song | [Bandcamp](https://jonathanmann.bandcamp.com/track/sometimes-i-dont-feel-like-writing-another-song) | Sometimes I Don't Feel Like Writing Another Song | Bandcamp: audio is 44 s against Apple Music 107 s, catalog 107 s; it matches #4996's length, so it may play that song |
| 5487 | 2024-01-09 | We Are Alone | [Bandcamp](https://jonathanmann.bandcamp.com/track/we-are-alone) | We Are Alone | Bandcamp: audio is 248 s against Apple Music 180 s, catalog 178 s; it matches #5486's length, so it may play that song |
| 5870 | 2025-01-26 | Are You A Barnyard Animal? | [Apple Music](https://music.apple.com/us/album/are-you-a-barnyard-animal/1794537538?i=1794537714) | Are You a Barnyard Animal? | Apple Music: audio is 198 s against Bandcamp 177 s, catalog 177 s; it matches #5871's length, so it may play that song |
| 5883 | 2025-02-08 | Saturday Morning Cartoons | [Apple Music](https://music.apple.com/us/album/saturday-morning-cartoons/1800845523?i=1800845531) | Saturday Morning Cartoons | Apple Music: audio is 128 s against Bandcamp 102 s, catalog 102 s; it matches #5885's length, so it may play that song; this song's audio may be under Apple Music's #5884 track |
| 5994 | 2025-05-30 | How Long Before They Drop A Bomb On Us? | [Bandcamp](https://jonathanmann.bandcamp.com/track/how-long-before-they-drop-a-bomb-on-us) | How Long Before They Drop A Bomb On Us? | Bandcamp: audio is 152 s against Apple Music 175 s, catalog 175 s; it matches #5993's length, so it may play that song |

### A title that belongs to a different song (0)

The service links a track here whose title is another song's, and either its audio is that other song's, or nothing about its audio says it is this one.

None.

### A single whose title several songs share (2)

Nothing about a single's position says which of the same-named songs it is, and its audio doesn't settle it.

| # | Date | Title | Service | Their title | What doesn't fit |
| ---: | --- | --- | --- | --- | --- |
| 2390 | 2015-07-18 | Infinite Ways to Die | [Apple Music](https://music.apple.com/us/album/infinite-ways-to-die/1081585543?i=1081585552) | Infinite Ways to Die | Apple Music: 'Infinite Ways to Die' is on 'The Arctic Mountains in Your Heart', not a dated album, and #1126 has the same title; Apple Music 'Infinite Ways to Die' vs Bandcamp 'Don't Soldier On Blindly', and their audio doesn't match either; Apple Music: exact match (score 1.00) to 'Infinite Ways to Die' with nothing else to back it up |
| 4131 | 2020-04-23 | There Are No People In The Future | [Apple Music](https://music.apple.com/us/album/there-are-no-people-in-the-future/1510388326?i=1510388327) | There Are No People in the Future | Apple Music: 'There Are No People in the Future' is on 'There Are No People in the Future - Single', not a dated album, and #1178, #6215 have the same title; Apple Music: exact match (score 1.00) to 'There Are No People in the Future' with nothing else to back it up |

### One track linked to two songs (0)

None.

## In the sheet, but the file's length is far off (68)

The title matches (and, on a dated album, so does the place), so the link is the service's track for this song, but its length is far from what the other service and the catalog agree on. Usually another take, an edit, or padding; a few may be the wrong file. Worth a listen.

- #4476-#4485 on Apple Music ('April, 2021'): every one of these 10 files is 47-66 s longer than the other service's, so something was added to the whole run, not a different song each time.

| # | Date | Title | Service | Their title | What doesn't fit |
| ---: | --- | --- | --- | --- | --- |
| 122 | 2009-05-02 | Happy Birthday Shaista | [Bandcamp](https://jonathanmann.bandcamp.com/track/happy-birthday-shaista) | Happy Birthday Shaista | Bandcamp: audio is 189 s against Apple Music 144 s, catalog 143 s (a different take, an edit, padding, or the wrong file) |
| 525 | 2010-06-09 | We're Jews That Don't Care About Money | [Bandcamp](https://jonathanmann.bandcamp.com/track/were-jews-that-dont-care-about-money) | We're Jews That Don't Care About Money | Bandcamp: audio is 169 s against Apple Music 40 s, catalog 40 s (a different take, an edit, padding, or the wrong file) |
| 559 | 2010-07-13 | Who You Gonna Be Today? | [Bandcamp](https://jonathanmann.bandcamp.com/track/who-you-gonna-be-today) | Who You Gonna Be Today? | Bandcamp: audio is 104 s against Apple Music 185 s, catalog 185 s (a different take, an edit, padding, or the wrong file) |
| 747 | 2011-01-17 | Who the Hell is Arcade Fire? | [Bandcamp](https://jonathanmann.bandcamp.com/track/who-the-hell-is-arcade-fire) | Who The Hell Is Arcade Fire? | Bandcamp: audio is 132 s against Apple Music 147 s, catalog 147 s (a different take, an edit, padding, or the wrong file) |
| 2454 | 2015-09-20 | Time Only Moves in One Direction | [Apple Music](https://music.apple.com/us/album/time-only-moves-in-one-direction/1448803720?i=1448804480) | Time Only Moves in One Direction | Apple Music: audio is 248 s against Bandcamp 277 s, catalog 277 s (a different take, an edit, padding, or the wrong file) |
| 3089 | 2017-06-16 | I'm Not Them and They're Not Me | [Apple Music](https://music.apple.com/us/album/im-not-them-and-theyre-not-me/1240885793?i=1240885805) | I'm Not Them and They're Not Me | Apple Music: audio is 170 s against Bandcamp 146 s, catalog 147 s (a different take, an edit, padding, or the wrong file) |
| 3712 | 2019-03-01 | Why Am I Sitting In The Closet? | [Apple Music](https://music.apple.com/us/album/why-am-i-sitting-in-the-closet/1458367834?i=1458367835) | Why Am I Sitting in the Closet? | Apple Music: audio is 89 s against Bandcamp 114 s, catalog 115 s (a different take, an edit, padding, or the wrong file) |
| 3741 | 2019-03-30 | With No Bullshit | [Apple Music](https://music.apple.com/us/album/with-no-b-t/1458367834?i=1458367930) | With No B******t | Apple Music: audio is 394 s against Bandcamp 325 s, catalog 326 s (a different take, an edit, padding, or the wrong file) |
| 3830 | 2019-06-27 | Nothing To Worry About | [Bandcamp](https://jonathanmann.bandcamp.com/track/nothing-to-worry-about) | Nothing To Worry About | Bandcamp: audio is 69 s against Apple Music 148 s, catalog 148 s (a different take, an edit, padding, or the wrong file) |
| 3886 | 2019-08-22 | It's Not Your Fault (Improvised) | [Apple Music](https://music.apple.com/us/album/its-not-your-fault/1480588345?i=1480588638) | It's Not Your Fault | Apple Music: audio is 225 s against Bandcamp 168 s, catalog 169 s (a different take, an edit, padding, or the wrong file) |
| 3932 | 2019-10-07 | Marching Orders | [Apple Music](https://music.apple.com/us/album/marching-orders/1486443989?i=1486444596) | Marching Orders | Apple Music: audio is 143 s against Bandcamp 82 s, catalog 82 s (a different take, an edit, padding, or the wrong file) |
| 3933 | 2019-10-08 | Hark The Angel, His name Is Harold | [Apple Music](https://music.apple.com/us/album/hark-the-angel-his-name-is-harold/1486443989?i=1486444597) | Hark the Angel, His Name Is Harold | Apple Music: audio is 287 s against Bandcamp 226 s, catalog 226 s (a different take, an edit, padding, or the wrong file) |
| 3943 | 2019-10-18 | An Accident of Time | [Apple Music](https://music.apple.com/us/album/an-accident-of-time/1486443989?i=1486444607) | An Accident of Time | Apple Music: audio is 482 s against Bandcamp 384 s, catalog 385 s (a different take, an edit, padding, or the wrong file) |
| 3944 | 2019-10-19 | The Walls Are Closing In | [Apple Music](https://music.apple.com/us/album/the-walls-are-closing-in/1486443989?i=1486444608) | The Walls Are Closing In | Apple Music: audio is 452 s against Bandcamp 401 s, catalog 401 s (a different take, an edit, padding, or the wrong file) |
| 3979 | 2019-11-23 | Goldfish With A Grudge | [Apple Music](https://music.apple.com/us/album/goldfish-with-a-grudge/1492184607?i=1492184870) | Goldfish With a Grudge | Apple Music: audio is 144 s against Bandcamp 166 s, catalog 167 s (a different take, an edit, padding, or the wrong file) |
| 4000 | 2019-12-14 | A Song Made Up of Previous Song A DayTitles | [Apple Music](https://music.apple.com/us/album/a-song-made-up-of-previous-song-a-day-titles/1500482492?i=1500482775) | A Song Made Up of Previous Song a Day Titles | Apple Music: audio is 177 s against Bandcamp 325 s, catalog 325 s (a different take, an edit, padding, or the wrong file) |
| 4168 | 2020-05-30 | Please Don't Disappoint Picard | [Apple Music](https://music.apple.com/us/album/please-dont-disappoint-picard/1518159832?i=1518159896) | Please Don't Disappoint Picard | Apple Music: audio is 51 s against Bandcamp 91 s, catalog 90 s (a different take, an edit, padding, or the wrong file) |
| 4183 | 2020-06-14 | Change Just Like The River | [Apple Music](https://music.apple.com/us/album/change-just-like-the-river/1521739234?i=1521739339) | Change Just Like the River | Apple Music: audio is 108 s against Bandcamp 93 s, catalog 93 s (a different take, an edit, padding, or the wrong file) |
| 4233 | 2020-08-03 | Since You're Here | [Apple Music](https://music.apple.com/us/album/since-youre-here/1529929545?i=1529929548) | Since You're Here | Apple Music: audio is 156 s against Bandcamp 132 s, catalog 131 s (a different take, an edit, padding, or the wrong file) |
| 4300 | 2020-10-09 | I've Never Seen Beetlejuice | [Apple Music](https://music.apple.com/us/album/ive-never-seen-beetlejuice/1541050302?i=1541050312) | I've Never Seen Beetlejuice | Apple Music: audio is 122 s against Bandcamp 108 s, catalog 108 s (a different take, an edit, padding, or the wrong file) |
| 4314 | 2020-10-23 | Baby Yoda, Baby Baby Yoda feat Brittain Ashford (2020 Remix) | [Apple Music](https://music.apple.com/us/album/baby-yoda-baby-baby-yoda-feat-brittain-ashford-remix/1533316040?i=1533316042) | Baby Yoda Baby Baby Yoda (feat. Brittain Ashford) [Remix] | Apple Music: audio is 192 s against Bandcamp 288 s, catalog 288 s (a different take, an edit, padding, or the wrong file) |
| 4343 | 2020-11-21 | Talkin' American Fascism Blues | [Bandcamp](https://jonathanmann.bandcamp.com/track/talkin-american-fascism-blues) | Talkin' American Fascism Blues | Bandcamp: audio is 203 s against Apple Music 141 s, catalog 139 s (a different take, an edit, padding, or the wrong file) |
| 4366 | 2020-12-14 | North Pole Elves Unite! Unionize! | [Bandcamp](https://jonathanmann.bandcamp.com/track/north-pole-elves-unite-unionize) | North Pole Elves Unite! Unionize! | Bandcamp: audio is 133 s against Apple Music 175 s, catalog 174 s (a different take, an edit, padding, or the wrong file) |
| 4367 | 2020-12-15 | Thanksgiving Day Parade Recap | [Bandcamp](https://jonathanmann.bandcamp.com/track/thanksgiving-day-parade-recap) | Thanksgiving Day Parade Recap | Bandcamp: audio is 285 s against Apple Music 135 s, catalog 132 s (a different take, an edit, padding, or the wrong file) |
| 4384 | 2021-01-01 | Songs, The Hat | [Apple Music](https://music.apple.com/us/album/songs-the-hat/1551913007?i=1551913008) | Songs, The Hat | Apple Music: audio is 86 s against Bandcamp 535 s, catalog 535 s (a different take, an edit, padding, or the wrong file) |
| 4425 | 2021-02-11 | So Many Matts | [Apple Music](https://music.apple.com/us/album/so-many-matts/1557138970?i=1557138981) | So Many Matts | Apple Music: audio is 40 s against Bandcamp 58 s, catalog 57 s (a different take, an edit, padding, or the wrong file) |
| 4437 | 2021-02-23 | On The Boulevard of the Gymnast Dropout | [Apple Music](https://music.apple.com/us/album/on-the-boulevard-of-the-gymnast-dropout/1557138970?i=1557138995) | On the Boulevard of the Gymnast Dropout | Apple Music: audio is 119 s against Bandcamp 106 s, catalog 105 s (a different take, an edit, padding, or the wrong file) |
| 4476 | 2021-04-03 | Nobody Knows What Is To Come | [Apple Music](https://music.apple.com/us/album/nobody-knows-what-is-to-come/1571820321?i=1571820325) | Nobody Knows What Is To Come | Apple Music: audio is 270 s against Bandcamp 212 s, catalog 212 s (a different take, an edit, padding, or the wrong file) |
| 4477 | 2021-04-04 | Let Go of The Mannequin, Thomas (Bold & Beautiful remix) | [Apple Music](https://music.apple.com/us/album/let-go-of-the-mannequin-thomas-bold-the-beautiful/1571820321?i=1571820326) | Let Go of the Mannequin, Thomas (Bold & the Beautiful) | Apple Music: audio is 125 s against Bandcamp 60 s, catalog 60 s (a different take, an edit, padding, or the wrong file) |
| 4478 | 2021-04-05 | At The End of The Rainbow | [Apple Music](https://music.apple.com/us/album/at-the-end-of-the-rainbow/1571820321?i=1571820327) | At the End of the Rainbow | Apple Music: audio is 215 s against Bandcamp 150 s, catalog 149 s (a different take, an edit, padding, or the wrong file) |
| 4479 | 2021-04-06 | What You Wanna Do and What You Gotta Do | [Apple Music](https://music.apple.com/us/album/what-you-wanna-do-and-what-you-gotta-do/1571820321?i=1571820328) | What You Wanna Do and What You Gotta Do | Apple Music: audio is 199 s against Bandcamp 134 s, catalog 134 s (a different take, an edit, padding, or the wrong file) |
| 4480 | 2021-04-07 | Rearrange The Studio Day | [Apple Music](https://music.apple.com/us/album/rearrange-the-studio-day/1571820321?i=1571820329) | Rearrange the Studio Day | Apple Music: audio is 156 s against Bandcamp 109 s, catalog 108 s (a different take, an edit, padding, or the wrong file) |
| 4481 | 2021-04-08 | Doctor Who: Worlds Apart | [Apple Music](https://music.apple.com/us/album/doctor-who-worlds-apart/1571820321?i=1571820330) | Doctor Who: Worlds Apart | Apple Music: audio is 114 s against Bandcamp 53 s, catalog 52 s (a different take, an edit, padding, or the wrong file) |
| 4482 | 2021-04-09 | I'm 39 Today | [Apple Music](https://music.apple.com/us/album/im-39-today/1571820321?i=1571820331) | I'm 39 Today | Apple Music: audio is 190 s against Bandcamp 129 s, catalog 128 s (a different take, an edit, padding, or the wrong file) |
| 4483 | 2021-04-10 | I Gotta Write My song | [Apple Music](https://music.apple.com/us/album/i-gotta-write-my-song/1571820321?i=1571820332) | I Gotta Write My song | Apple Music: audio is 243 s against Bandcamp 183 s, catalog 182 s (a different take, an edit, padding, or the wrong file) |
| 4484 | 2021-04-11 | Hammertime Says EulerBeats It's Time To Rock And Roll | [Apple Music](https://music.apple.com/us/album/hammertime-says-eulerbeats-its-time-to-rock-and-roll/1571820321?i=1571820333) | Hammertime Says EulerBeats It's Time To Rock and Roll | Apple Music: audio is 278 s against Bandcamp 212 s, catalog 212 s (a different take, an edit, padding, or the wrong file) |
| 4485 | 2021-04-12 | It Ain't Enough | [Apple Music](https://music.apple.com/us/album/it-aint-enough/1571820321?i=1571820334) | It Ain't Enough | Apple Music: audio is 241 s against Bandcamp 179 s, catalog 179 s (a different take, an edit, padding, or the wrong file) |
| 4491 | 2021-04-18 | Oh Little Choo Choo Train | [Apple Music](https://music.apple.com/us/album/oh-little-choo-choo-train/1571820321?i=1571820520) | Oh Little Choo Choo Train | Apple Music: audio is 99 s against Bandcamp 86 s, catalog 86 s (a different take, an edit, padding, or the wrong file) |
| 4500 | 2021-04-27 | Song A DayRMXD | [Apple Music](https://music.apple.com/us/album/song-a-day-rmxd/1571820321?i=1571820529) | Song a Day RMXD | Apple Music: audio is 150 s against Bandcamp 604 s, catalog 603 s (a different take, an edit, padding, or the wrong file) |
| 4523 | 2021-05-20 | It's Raining Whale (The Pineapple Song) | [Apple Music](https://music.apple.com/us/album/its-raining-whale-the-pineapple-song/1571753976?i=1571753998) | It's Raining Whale (The Pineapple Song) | Apple Music: audio is 30 s against Bandcamp 396 s, catalog 395 s (a different take, an edit, padding, or the wrong file) |
| 4530 | 2021-05-27 | Right Click, Save As | [Apple Music](https://music.apple.com/us/album/right-click-save-as-nfts/1571753976?i=1571754006) | Right Click, Save As (NFTs) | Apple Music: audio is 82 s against Bandcamp 140 s, catalog 139 s (a different take, an edit, padding, or the wrong file) |
| 4539 | 2021-06-05 | Short And Sweet | [Apple Music](https://music.apple.com/us/album/short-and-sweet/1575580039?i=1575580044) | Short and Sweet | Apple Music: audio is 107 s against Bandcamp 121 s, catalog 120 s (a different take, an edit, padding, or the wrong file) |
| 4629 | 2021-09-03 | Shl0ms, Duchamp and The Toilet Shards | [Apple Music](https://music.apple.com/us/album/shl0ms-duchamp-and-the-toilet-shards/1599350225?i=1599350618) | Shl0ms, Duchamp and the Toilet Shards | Apple Music: audio is 168 s against Bandcamp 139 s, catalog 138 s (a different take, an edit, padding, or the wrong file) |
| 4662 | 2021-10-06 | Where Is The MacBook Pro? | [Apple Music](https://music.apple.com/us/album/where-is-the-macbook-pro/1599338200?i=1599338208) | Where Is the MacBook Pro? | Apple Music: audio is 112 s against Bandcamp 100 s, catalog 100 s (a different take, an edit, padding, or the wrong file) |
| 4681 | 2021-10-25 | Large Flying Bat Eating A Banana | [Bandcamp](https://jonathanmann.bandcamp.com/track/large-flying-bat-eating-a-banana) | Large Flying Bat Eating A Banana | Bandcamp: audio is 108 s against Apple Music 127 s, catalog 127 s (a different take, an edit, padding, or the wrong file) |
| 4733 | 2021-12-16 | The Worm | [Apple Music](https://music.apple.com/us/album/the-worm/1610239366?i=1610239384) | The Worm | Apple Music: audio is 111 s against Bandcamp 89 s, catalog 89 s (a different take, an edit, padding, or the wrong file) |
| 4738 | 2021-12-21 | Taiwan Is A Country | [Apple Music](https://music.apple.com/us/album/taiwan-is-a-country/1610239366?i=1610239479) | Taiwan Is a Country | Apple Music: audio is 89 s against Bandcamp 130 s, catalog 130 s (a different take, an edit, padding, or the wrong file) |
| 5153 | 2023-02-09 | RunwayML | [Apple Music](https://music.apple.com/us/album/runwayml/1676496656?i=1676496665) | RunwayML | Apple Music: audio is 97 s against Bandcamp 109 s, catalog 109 s (a different take, an edit, padding, or the wrong file) |
| 5297 | 2023-07-03 | NFTs are Dead part 420 | [Bandcamp](https://jonathanmann.bandcamp.com/track/nfts-are-dead-part-420) | NFTs are Dead part 420 | Bandcamp: audio is 99 s against Apple Music 166 s, catalog 163 s (a different take, an edit, padding, or the wrong file) |
| 5575 | 2024-04-06 | Dancing Eddie | [Apple Music](https://music.apple.com/us/album/dancing-eddie/1744426979?i=1744426985) | Dancing Eddie | Apple Music: audio is 107 s against Bandcamp 129 s, catalog 126 s (a different take, an edit, padding, or the wrong file) |
| 5747 | 2024-09-25 | Tolly | [Apple Music](https://music.apple.com/us/album/tolly/1772211828?i=1772212333) | Tolly | Apple Music: audio is 254 s against Bandcamp 187 s, catalog 187 s (a different take, an edit, padding, or the wrong file) |
| 5867 | 2025-01-23 | Yapster | [Apple Music](https://music.apple.com/us/album/yapster/1794537538?i=1794537711) | Yapster | Apple Music: audio is 79 s against Bandcamp 68 s, catalog 68 s (a different take, an edit, padding, or the wrong file) |
| 5905 | 2025-03-02 | Danny Ryan Is Back | [Apple Music](https://music.apple.com/us/album/danny-ryan-is-back/1808428223?i=1808428225) | Danny Ryan Is Back | Apple Music: audio is 296 s against Bandcamp 266 s, catalog 266 s (a different take, an edit, padding, or the wrong file) |
| 5914 | 2025-03-11 | Everything On Zora Is A Coin | [Apple Music](https://music.apple.com/us/album/everything-on-zora-is-a-coin/1808428223?i=1808428234) | Everything On Zora Is A Coin | Apple Music: audio is 112 s against Bandcamp 125 s, catalog 125 s (a different take, an edit, padding, or the wrong file) |
| 5915 | 2025-03-12 | IN PUBLIC | [Apple Music](https://music.apple.com/us/album/in-public/1808428223?i=1808428235) | IN PUBLIC | Apple Music: audio is 114 s against Bandcamp 102 s, catalog 101 s (a different take, an edit, padding, or the wrong file) |
| 5959 | 2025-04-25 | This Is not Real | [Apple Music](https://music.apple.com/us/album/this-is-not-real/1812315422?i=1812315600) | This Is not Real | Apple Music: audio is 241 s against Bandcamp 203 s, catalog 203 s (a different take, an edit, padding, or the wrong file) |
| 5968 | 2025-05-04 | May The Fourth Be With You Against Fascism | [Apple Music](https://music.apple.com/us/album/may-the-fourth-be-with-you-against-fascism/1820789527?i=1820789531) | May The Fourth Be With You Against Fascism | Apple Music: audio is 109 s against Bandcamp 87 s, catalog 87 s (a different take, an edit, padding, or the wrong file) |
| 6034 | 2025-07-09 | Grok Is MechaHitler | [Apple Music](https://music.apple.com/us/album/grok-is-mechahitler/1831900543?i=1831900552) | Grok Is MechaHitler | Apple Music: audio is 79 s against Bandcamp 112 s, catalog 112 s (a different take, an edit, padding, or the wrong file) |
| 6199 | 2025-12-21 | Ohhhhh Yeah | [Apple Music](https://music.apple.com/us/album/ohhhhh-yeah/1874109497?i=1874109907) | Ohhhhh Yeah | Apple Music: audio is 288 s against Bandcamp 225 s, catalog 225 s (a different take, an edit, padding, or the wrong file) |
| 6200 | 2025-12-22 | Don't Mean Nothin' | [Apple Music](https://music.apple.com/us/album/dont-mean-nothin/1874109497?i=1874109908) | Don't Mean Nothin' | Apple Music: audio is 261 s against Bandcamp 201 s, catalog 201 s (a different take, an edit, padding, or the wrong file) |
| 6202 | 2025-12-24 | Neon Signs | [Apple Music](https://music.apple.com/us/album/neon-signs/1874109497?i=1874109910) | Neon Signs | Apple Music: audio is 266 s against Bandcamp 208 s, catalog 208 s (a different take, an edit, padding, or the wrong file) |
| 6209 | 2025-12-31 | Seventeen Years | [Bandcamp](https://jonathanmann.bandcamp.com/track/seventeen-years) | Seventeen Years | Bandcamp: audio is 133 s against Apple Music 263 s, catalog 258 s (a different take, an edit, padding, or the wrong file) |
| 6322 | 2026-04-23 | The Nouns Are Dead | [Apple Music](https://music.apple.com/us/album/the-nouns-are-dead/6766473020?i=6766473343) | The Nouns Are Dead | Apple Music: audio is 167 s against Bandcamp 148 s, catalog 148 s (a different take, an edit, padding, or the wrong file) |
| 6333 | 2026-05-04 | Mister Photography | [Apple Music](https://music.apple.com/us/album/mister-photography/6775651323?i=6775651327) | Mister Photography | Apple Music: audio is 161 s against Bandcamp 136 s, catalog 135 s (a different take, an edit, padding, or the wrong file) |
| 6403 | 2026-07-13 | Lindsay Graham In Hell | [Apple Music](https://music.apple.com/us/album/lindsay-graham-in-hell/6798020297?i=6798020310) | Lindsay Graham In Hell | Apple Music: audio is 384 s against Bandcamp 157 s, catalog 156 s (a different take, an edit, padding, or the wrong file) |
| 6406 | 2026-07-16 | Diarrheapocalypse | [Apple Music](https://music.apple.com/us/album/diarrheapocalypse/6798020297?i=6798020313) | Diarrheapocalypse | Apple Music: audio is 138 s against Bandcamp 195 s, catalog 194 s (a different take, an edit, padding, or the wrong file) |
| 6454 | 2026-09-02 | A Humble Letter To The Ladders In The Basement | [Apple Music](https://music.apple.com/us/album/a-humble-letter-to-the-ladders-in-the-basement/6818570154?i=6818570156) | A Humble Letter To The Ladders In The Basement | Apple Music: audio is 416 s against Bandcamp 521 s, catalog 520 s (a different take, an edit, padding, or the wrong file) |
| 6477 | 2026-09-25 | Until The Darkness Falls | [Apple Music](https://music.apple.com/us/album/until-the-darkness-falls/6818570154?i=6818570302) | Until The Darkness Falls | Apple Music: audio is 230 s against Bandcamp 200 s, catalog 199 s (a different take, an edit, padding, or the wrong file) |

## Weak matches nothing backs up (5)

Position-only or low-scoring fuzzy title matches with no second service whose audio agrees and no exact fit with the catalog's Length. They may well be right (several are singles released the day of the song under another name); they are left out of the sheet until you've looked.

| # | Date | Catalog title | Service | Their title | Match | Score | Length vs catalog |
| ---: | --- | --- | --- | --- | --- | ---: | --- |
| 4154 | 2020-05-16 | Kenneth Copeland On COVID-19 (Wind of God chill remix) | [Apple Music](https://music.apple.com/us/album/the-wind-of-god/1513780309?i=1513780310) | The Wind of God | fuzzy | 0.465 | 107 s vs 104 s |
| 4571 | 2021-07-07 | Woodcock Luring Worms | [Apple Music](https://music.apple.com/us/album/the-american-woodcock-dance/1575730437?i=1575730438) | The American Woodcock Dance | fuzzy | 0.45 | 113 s vs 109 s |
| 4705 | 2021-11-18 | Please Trade Back | [Apple Music](https://music.apple.com/us/album/please-trade-my-ape-back/1599328027?i=1599328047) | Please Trade My Ape Back | fuzzy | 0.829 | 115 s vs 107 s |
| 5830 | 2024-12-17 | Pudgy Pengu Remix | [Apple Music](https://music.apple.com/us/album/pudgy-pengu-two/1788606135?i=1788606482) | Pudgy Pengu Two | fuzzy | 0.75 | 154 s vs 152 s |
| 5858 | 2025-01-14 | TikTok Refugee | [Apple Music](https://music.apple.com/us/album/tt-refugee/1794537538?i=1794537552) | TT Refugee | fuzzy | 0.833 | 113 s vs 115 s |

## Weak titles that something else backs up (71)

Position-only or low-scoring fuzzy title matches rated high because something else backs them up: another service's sure link for the same song is the same length; or the track sits in this song's place on a dated album and is the catalog's Length to the second; or, for a track with no length to compare, another service's high link in the same place has exactly the same title. These are in the sheet, so they are the ones to glance at first. Most are songs titled differently on the service than in the catalog ("Our House" for "2100 California St."), or Bandcamp tracks that carry the previous track's title by mistake.

| # | Catalog title | Service | Their title | Match | Score | Backed by |
| ---: | --- | --- | --- | --- | ---: | --- |
| 60 | 2100 California St. | [Bandcamp](https://jonathanmann.bandcamp.com/track/our-house) | Our House | position-only | 0.296 | the other service's audio |
| 98 | Ringtone for Shelly | [Apple Music](https://music.apple.com/us/album/shelly/1133048770?i=1133048951) | Shelly | position-only | 0.48 | the other service's audio |
| 102 | Ringtone for Casey | [Apple Music](https://music.apple.com/us/album/casey/1133048770?i=1133048955) | Casey | position-only | 0.435 | the other service's audio |
| 104 | Ringtone for Jackie | [Apple Music](https://music.apple.com/us/album/jackie/1133048770?i=1133048957) | Jackie | position-only | 0.48 | the other service's audio |
| 189 | Hunchback With a Dirty Mind | [Apple Music](https://music.apple.com/us/album/hunchbacks-dirty-mind/1133055443?i=1133055470) | Hunchback's Dirty Mind | fuzzy | 0.833 | the other service's audio |
| 214 | LifeWith Cha Cha is in Sonic Technicolor | [Apple Music](https://music.apple.com/us/album/cha-cha-is-sonic-technicolor/1133055443?i=1133055495) | Cha Cha Is Sonic Technicolor | fuzzy | 0.824 | the other service's audio |
| 238 | GPS With Bob Dylan | [Apple Music](https://music.apple.com/us/album/gps-voiced-by-bob-dylan/1133055443?i=1133055519) | GPS Voiced by Bob Dylan | fuzzy | 0.732 | the other service's audio |
| 270 | Popcorn | [Bandcamp](https://jonathanmann.bandcamp.com/track/throw-a-cob-of-corn-into-the-sun-popcorn) | Throw A Cob of Corn Into The Sun-Popcorn | position-only | 0.359 | the other service's audio |
| 324 | And With a name... | [Apple Music](https://music.apple.com/us/album/a-name/1133062645?i=1133062920) | A Name... | position-only | 0.571 | the other service's audio |
| 417 | I Kind Of Want An Ipad | [Bandcamp](https://jonathanmann.bandcamp.com/track/ipad) | iPad | position-only | 0.381 | the other service's audio |
| 506 | Skinit.com | [Apple Music](https://music.apple.com/us/album/skinit/1135250985?i=1135251048) | Skinit | fuzzy | 0.75 | the other service's audio |
| 539 | Jonathan's New Ringtone | [Apple Music](https://music.apple.com/us/album/jonathans-phone-rings/1135250985?i=1135251080) | Jonathan's Phone Rings | fuzzy | 0.791 | the other service's audio |
| 775 | Deep Thoughts With a Capybara | [Apple Music](https://music.apple.com/us/album/capybara-deep-thoughts/1137664327?i=1137664494) | Capybara Deep Thoughts | fuzzy | 0.813 | the other service's audio |
| 778 | Apart on Valentines Day | [Bandcamp](https://jonathanmann.bandcamp.com/track/why-is-love-hard) | Why Is Love Hard? | position-only | 0.256 | the other service's audio |
| 779 | Go! With Zach Anner! | [Apple Music](https://music.apple.com/us/album/go-zach-anner/1137664327?i=1137664498) | Go! Zach Anner! | fuzzy | 0.839 | the other service's audio |
| 806 | Embrace the Monkey | [Bandcamp](https://jonathanmann.bandcamp.com/track/were-all-just-monkeys) | We're All Just Monkeys | position-only | 0.615 | the other service's audio |
| 1017 | 10000 SUBSCRIBERS OMG!!! | [Bandcamp](https://jonathanmann.bandcamp.com/track/10000) | 10000 | position-only | 0.417 | the other service's audio |
| 1045 | Time Zones | [Bandcamp](https://jonathanmann.bandcamp.com/track/cross-the-state-line) | Cross The State Line | position-only | 0.333 | the other service's audio |
| 1213 | A Song About a Frog Sitting on a Bench Like a Human | [Bandcamp](https://jonathanmann.bandcamp.com/track/froggy-on-the-bench-song) | Froggy On The Bench Song | position-only | 0.48 | the other service's audio |
| 1230 | A Partial List of the Things That Make Me Feel Loneliness | [Bandcamp](https://jonathanmann.bandcamp.com/track/a-partial-list-of-the-things-im-not-2) | A Partial List of the Things I'm Not | position-only | 0.674 | the other service's audio |
| 1241 | Joy the Baker and Shutterbean | [Bandcamp](https://jonathanmann.bandcamp.com/track/joy-and-shutterbean) | Joy And Shutterbean | fuzzy | 0.81 | the other service's audio |
| 1256 | Anidea | [Bandcamp](https://jonathanmann.bandcamp.com/track/ive-got-an-idea-2) | I've Got An Idea | position-only | 0.667 | the other service's audio |
| 1282 | Helmet Safety Song | [Bandcamp](https://jonathanmann.bandcamp.com/track/put-your-helmet-on) | Put Your Helmet On | position-only | 0.516 | the other service's audio |
| 1301 | Be My Friend Again (Philipp is Sorry) | [Bandcamp](https://jonathanmann.bandcamp.com/track/phillipp-is-sorry) | Phillipp Is Sorry | position-only | 0.636 | the other service's audio |
| 1379 | Brooklyn Beta Day 1 | [Bandcamp](https://jonathanmann.bandcamp.com/track/brooklyn-beta-whisper-dont-yell-at-farmer-john) | Brooklyn Beta Whisper Don't Yell At Farmer John | position-only | 0.554 | the other service's audio |
| 1436 | We Have to Breakup | [Bandcamp](https://jonathanmann.bandcamp.com/track/weve-got-to-break-up) | We've Got To Break Up | fuzzy | 0.839 | the other service's audio |
| 1586 | Brief History of Cinco de Mayo in Song | [Bandcamp](https://jonathanmann.bandcamp.com/track/a-brief-history-of-cindeo-de-mayo-2) | A Brief History of Cindeo de Mayo | fuzzy | 0.828 | the other service's audio |
| 1775 | I'm Cooking Dinner Tonight | [Apple Music](https://music.apple.com/us/album/im-cooking-dinner-tonightim-cooking-dinner-tonight/1143182550?i=1143182800) | I'm Cooking Dinner Tonighti'm Cooking Dinner Tonight | fuzzy | 0.783 | the other service's audio |
| 1816 | A Cringing Look Back at 2013 | [Bandcamp](https://jonathanmann.bandcamp.com/track/a-cringeworthy-look-back-at-2013) | A Cringeworthy Look Back At 2013 | fuzzy | 0.833 | the other service's audio |
| 1855 | Everything is Going to Be All Right From Now On | [Bandcamp](https://jonathanmann.bandcamp.com/track/dip-your-toe) | Dip Your Toe | position-only | 0.237 | the other service's audio |
| 2136 | When Things Go Wrong | [Bandcamp](https://jonathanmann.bandcamp.com/track/i-am-here-for-you-2) | I Am Here For You | position-only | 0.267 | the other service's audio |
| 2390 | Infinite Ways to Die | [Bandcamp](https://jonathanmann.bandcamp.com/track/dont-soldier-on-blindly-2) | Don't Soldier On Blindly | position-only | 0.233 | the catalog's Length |
| 2402 | You Conquered the Lion | [Bandcamp](https://jonathanmann.bandcamp.com/track/and-i-make-no-sense-2) | And I Make No Sense | position-only | 0.293 | the catalog's Length |
| 2566 | Just Say Anything at All | [Bandcamp](https://jonathanmann.bandcamp.com/track/what-have-you-got-to-say) | What Have You Got To Say | position-only | 0.292 | the catalog's Length |
| 2566 | Just Say Anything at All | [Apple Music](https://music.apple.com/us/album/what-have-you-got-to-say/1146681138?i=1146681157) | What Have You Got to Say | position-only | 0.242 | the catalog's Length |
| 2569 | PCMA Twitter Song 2016 | [Bandcamp](https://jonathanmann.bandcamp.com/track/pcma-tweets-2016) | PCMA Tweets 2016 | position-only | 0.737 | the other service's audio |
| 2570 | 4 Myths of the Profile Picture | [Bandcamp](https://jonathanmann.bandcamp.com/track/okcupid-song) | OKCupid Song | position-only | 0.167 | the other service's audio |
| 2586 | Questions for Folks Supporting Hillary in the Primary | [Bandcamp](https://jonathanmann.bandcamp.com/track/hillary-clinton-questions) | Hillary Clinton Questions | position-only | 0.513 | the other service's audio |
| 2611 | Lay Your Head Down Low Low Low | [Bandcamp](https://jonathanmann.bandcamp.com/track/lay-me-down-low-2) | Lay Me Down Low | position-only | 0.622 | the other service's audio |
| 2688 | I Gotta Do This | [Bandcamp](https://jonathanmann.bandcamp.com/track/gotta-do-that) | Gotta Do That | position-only | 0.786 | the other service's audio |
| 3005 | 👶🏼 🐘 | [Apple Music](https://music.apple.com/us/album/baby-elephant/1222325359?i=1222325628) | Baby Elephant | position-only | 0.0 | the other service's audio |
| 3118 | ✌️ out | [Apple Music](https://music.apple.com/us/album/peace-out/1291740779?i=1291741066) | Peace Out | position-only | 0.5 | the other service's audio |
| 3205 | SHIT ROAD | [Apple Music](https://music.apple.com/us/album/bad-road/1342822079?i=1342822094) | Bad Road | position-only | 0.588 | the other service's audio |
| 3292 | JupiterIs Feeling Sick Sick Sick | [Apple Music](https://music.apple.com/us/album/jupiter-is-feeling-sick/1438522740?i=1438522745) | Jupiter Is Feeling Sick | fuzzy | 0.839 | the other service's audio |
| 3307 | Oobie Doobie Doooooo | [Apple Music](https://music.apple.com/us/album/baby-knocks-it-over/1438522740?i=1438522940) | Baby Knocks It Over | position-only | 0.258 | the other service's audio |
| 3311 | Apple, Google, Amazon and FaceBook Need To Be Broken Up | [Apple Music](https://music.apple.com/us/album/amazon-should-be-broken-up/1438522740?i=1438522944) | Amazon Should Be Broken Up | position-only | 0.557 | the other service's audio |
| 3313 | Stormy Daniels Didn't Like The Last Jedi | [Apple Music](https://music.apple.com/us/album/she-didnt-like-the-last-jedi/1438522740?i=1438522946) | She Didn't Like the Last Jedi | fuzzy | 0.806 | the other service's audio |
| 3336 | DADA Dot NYC | [Apple Music](https://music.apple.com/us/album/dada-nyc/1438480827?i=1438480966) | Dada NYC | fuzzy | 0.8 | the other service's audio |
| 3337 | Wanna Play With You On The Bed | [Apple Music](https://music.apple.com/us/album/wanna-play-on-the-bed/1438480827?i=1438480967) | Wanna Play on the Bed | fuzzy | 0.824 | the other service's audio |
| 3348 | Anuee Pahnuee | [Apple Music](https://music.apple.com/us/album/japanese-potato-mash/1438482874?i=1438482876) | Japanese Potato Mash | position-only | 0.485 | the other service's audio |
| 3368 | Who Wants To Go To War (John Bolton That's Who) | [Apple Music](https://music.apple.com/us/album/john-bolton-wants-to-go-to-war/1438482874?i=1438483196) | John Bolton Wants to Go to War | fuzzy | 0.794 | the other service's audio |
| 3396 | XDP day 1 2018 | [Apple Music](https://music.apple.com/us/album/experience-design/1439605100?i=1439605181) | Experience Design | position-only | 0.258 | the other service's audio |
| 3401 | Weathering The Storm redux | [Apple Music](https://music.apple.com/us/album/weathering-the-storm-again/1439605100?i=1439605186) | Weathering the Storm Again | fuzzy | 0.808 | the other service's audio |
| 3424 | PRSA Tweet Song | [Apple Music](https://music.apple.com/us/album/public-relations-tweet-song/1438586667?i=1438586804) | Public Relations Tweet Song | fuzzy | 0.667 | the other service's audio |
| 3426 | It’s Been A Long Time Since I Did An Acapella Song | [Apple Music](https://music.apple.com/us/album/no-music-just-lyrics/1438586667?i=1438586806) | No Music Just Lyrics | position-only | 0.261 | the other service's audio |
| 3428 | PRSA Theme Song | [Apple Music](https://music.apple.com/us/album/public-relations-theme-song/1438586667?i=1438586808) | Public Relations Theme Song | fuzzy | 0.667 | the other service's audio |
| 3486 | ALI Internal Comms Boston 2018 Tweet Song | [Apple Music](https://music.apple.com/us/album/internal-communications-boston-tweet-song/1438600327?i=1438600405) | Internal Communications Boston Tweet Song | fuzzy | 0.78 | the other service's audio |
| 3541 | Fireside Theme Song 2018 | [Apple Music](https://music.apple.com/us/album/fireside-theme-again/1439613392?i=1439613523) | Fireside Theme Again | fuzzy | 0.727 | the other service's audio |
| 3624 | Banjo Song #14941 | [Apple Music](https://music.apple.com/us/album/banjo-song-number14941/1454646816?i=1454646820) | Banjo Song Number14941 | fuzzy | 0.842 | the other service's audio |
| 3655 | Medicare For Allllll | [Apple Music](https://music.apple.com/us/album/medicare-mother-forking-care-for-all/1454713100?i=1454713103) | Medicare Mother Forking Care for All | position-only | 0.571 | the other service's audio |
| 3747 | Boopy Do Boo | [Apple Music](https://music.apple.com/us/album/boopy-do-boolong-ago/1462113869?i=1462113875) | Boopy Do BooLong Ago | fuzzy | 0.75 | the other service's audio |
| 3750 | AutoGlyph #215 | [Apple Music](https://music.apple.com/us/album/autoglyph-number-two-hundred-fifteen/1462113869?i=1462113878) | AutoGlyph Number Two Hundred Fifteen | position-only | 0.408 | the other service's audio |
| 3902 | I’m So Tie Erd (improvised) | [Apple Music](https://music.apple.com/us/album/im-so-tired/1482201561?i=1482202316) | I'm So Tired | fuzzy | 0.833 | the other service's audio |
| 4044 | MeaningConf2019 | [Apple Music](https://music.apple.com/us/album/meaningconf/1498929888?i=1498930037) | MeaningConf | fuzzy | 0.846 | the other service's audio |
| 4391 | Bernie Is The Incoming Chairman of the Budget Committee | [Apple Music](https://music.apple.com/us/album/incoming-chairman-of-the-senate-budget-committee/1549067753?i=1549067754) | Incoming Chairman of the Senate Budget Committee | fuzzy | 0.796 | the other service's audio |
| 4541 | WWDC2021 Remix: OKAY | [Apple Music](https://music.apple.com/us/album/wwdc2021-okay/1575580039?i=1575580046) | Wwdc2021: Okay | fuzzy | 0.812 | the other service's audio |
| 4799 | Touch The Orb 2022 feat. Dadabots | [Apple Music](https://music.apple.com/us/album/touch-the-orb-again/1631202689?i=1631203279) | Touch the Orb Again | fuzzy | 0.757 | the other service's audio |
| 4801 | 2/22/22 (feat. LogicBeach) | [Apple Music](https://music.apple.com/us/album/two-twenty-two-twenty-two/1631202689?i=1631203281) | Two Twenty Two Twenty Two | position-only | 0.125 | the other service's audio |
| 5042 | Bitboy Remix | [Apple Music](https://music.apple.com/us/album/bitboy/1654021217?i=1654021242) | Bitboy | fuzzy | 0.667 | the other service's audio |
| 5686 | Everyday Is The Hottest Day | [Apple Music](https://music.apple.com/us/album/its-the-hottest-day-on-record/1762296729?i=1762296844) | It's The Hottest Day On Record | fuzzy | 0.643 | the other service's audio |
| 6216 | Kevin (redux) | [Apple Music](https://music.apple.com/us/album/kevin-again/1873919333?i=1873919700) | Kevin Again | fuzzy | 0.625 | the other service's audio |

## Notes that don't change a rating

- **The services agree with each other, but not with the catalog's Length (147):** every service has the same file length, far from the video's. The links stand; it's the video (or the catalog's Length) that differs. This covers the Apple step's worry about Summer 2009 tracks 84-86: Bandcamp's files there have the same lengths as Apple's. #13, #14, #15, #144, #260, #266, #267, #738, #748, #751, #752, #753, #754, #757, #760, #762, #765, #767, #779, #785, #788, #803, #808, #819, #820, #880, #886, #901, #956, #960, #967, #973, #1002, #1025, #1050, #1066, #1082, #1089, #1092, #1093, #1095, #1111, #1132, #1141, #1148, #1150, #1155, #1202, #1470, #1827, #1828, #1832, #1833, #1834, #1835, #1836, #1838, #1857, #1862, #1864, #1866, #1870, #1873, #1891, #1892, #1895, #1905, #1912, #2009, #2022, #2036, #2075, #2076, #2097, #2104, #2143, #2157, #2192, #2211, #2715, #3507, #4617, #4749, #4770, #4776, #4786, #4791, #4796, #4797, #4801, #4853, #4908, #4929, #4938, #4955, #4958, #4985, #4991, #5007, #5042, #5050, #5061, #5064, #5154, #5166, #5174, #5175, #5241, #5242, #5245, #5250, #5259, #5267, #5278, #5294, #5310, #5331, #5334, #5348, #5354, #5434, #5464, #5466, #5478, #5496, #5497, #5508, #5539, #5555, #5583, #5589, #5594, #5608, #5629, #5636, #5707, #5713, #5714, #5715, #5718, #5719, #5723, #5729, #5755, #5770, #5795, #6249.
- **Right link, wrong title on the service (6):** the track's title is another song's, but its audio matches the other service's track for this song. Fixing the title on the service would tidy these: #1230, #1256, #2136, #2390, #2402, #2611.
- **Bandcamp track pages with no audio (2):** the link is right but there's nothing to play: #970, #2217.
- **Audio lengths that differ with no clear odd one out (6):** neither matches the catalog's Length, which is the video's: #755, #1830, #1845, #4097, #5578, #6208.
- **Titles that differ between services and aren't backed by audio (3):** #2390, #4154, #4571. The notes column of `dataset/links.csv` has both titles.

## Downloads and plays

No public source has them. Bandcamp's album pages carry a play_count field, but it is 0 or empty for every one of the 6,496 tracks; Apple's iTunes Lookup API and Spotify's Web API have no play, stream or download counts for an artist's tracks either. The numbers exist only in each service's artist dashboard, behind your login: Bandcamp's stats and sales reports, Spotify for Artists, and Apple Music for Artists. If you export one of those to a CSV and drop it in `cache/` (gitignored), a later step could join it to `dataset/links.csv` by track URL or title. This step didn't log in anywhere.

## Columns of dataset/links.csv

- `number`, `date`, `title`: the song (title from the songaday-display catalog).
- `catalog_seconds`: the catalog's Length, which is the video's length.
- For each of `bandcamp`, `apple_music`, `spotify`: `_url`, `_title` (the track's title on that service), `_album`, `_match` (exact, fuzzy, position-only or none), `_score` (title similarity from the fetch step, 0-1), `_seconds` (the track's audio length on that service), `_confidence` (high, check or none). All of a service's columns are blank when its step hasn't been run.
- `flags`: `|`-separated codes: `<service>_weak_match`, `<service>_audio_shifted`, `<service>_audio_mismatch`, `<service>_title_elsewhere`, `<service>_mislabelled`, `<service>_ambiguous_title`, `<service>_url_reused`, `bandcamp_no_audio`, `audio_differs`, `titles_differ`.
- `notes`: the same in words, `; `-separated.
