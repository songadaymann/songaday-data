# Links spot-check against the live pages

Made by `analysis/checks/links_check.py`. It opens the live Bandcamp track page and Apple's lookup API (`https://itunes.apple.com/lookup?id=<trackId>`) for each sampled link in `dataset/links.csv` and asks whether the track is the song from that day, comparing with the songaday-display catalog's title and date. The title matching is written separately from `sources/` so it is a second opinion. Raw responses are in `cache/links-verify/`.

## In short

- Sampled 80 songs: 40 spread across 2009-2026 (leap days, Jan 1 / Dec 31, season and year album boundaries, 11 random days), and every song links.csv rates **check** on some service (40; 0 of them were already in the spread). With the follow-ups that is 102 Bandcamp track pages and 99 Apple lookups opened, 0 fetch problems.
- Follow-ups: 22 more songs whose high-rated links the whole-table scans below point at (another song's title, an album outside the date, a file that looks like another day's). They are opened live too, but kept out of the rates, which would otherwise be inflated by picking suspects.

Links rated **high** (the ones the paste file uses) among the opened links. 'Titled as another song' is the error the title check looks for; 'mislabelled' is a track with another song's title but this day's audio; 'file looks like another day' is a right title on a file whose length is another song's (see [How a link is judged](#how-a-link-is-judged)). Rates are per link with exact 95% intervals.

| Sample | Service | High links opened | Titled as another song | Mislabelled | File looks like another day | Unclear | Title error rate | Any problem |
| --- | --- | ---: | --- | --- | --- | --- | ---: | ---: |
| 11 random days | Bandcamp | 11 | 0 | 0 | 0 | 0 | 0.0% (0.0-28.5%) | 0.0% (0.0-28.5%) |
| 11 random days | Apple Music | 11 | 0 | 0 | 0 | 0 | 0.0% (0.0-28.5%) | 0.0% (0.0-28.5%) |
| 40 spread songs | Bandcamp | 40 | 0 | 0 | #6209 | 0 | 0.0% (0.0-8.8%) | 2.5% (0.1-13.2%) |
| 40 spread songs | Apple Music | 39 | 0 | 0 | 0 | 0 | 0.0% (0.0-9.0%) | 0.0% (0.0-9.0%) |
| 40 check songs | Bandcamp | 18 | 0 | #2390 | 0 | 0 | 0.0% (0.0-18.5%) | 5.6% (0.1-27.3%) |
| 40 check songs | Apple Music | 20 | 0 | 0 | 0 | 0 | 0.0% (0.0-16.8%) | 0.0% (0.0-16.8%) |
| spread + check (80) | Bandcamp | 58 | 0 | #2390 | #6209 | 0 | 0.0% (0.0-6.2%) | 3.4% (0.4-11.9%) |
| spread + check (80) | Apple Music | 59 | 0 | 0 | 0 | 0 | 0.0% (0.0-6.1%) | 0.0% (0.0-6.1%) |
| 22 follow-ups | Bandcamp | 22 | 0 | #1230, #1256, #2136, #2402, #2611 | #738, #1092, #1093, #3830, #3832, #4343, #4366, #4367, #4681, #4898, #5297, #6208 | 0 | 0.0% (0.0-15.4%) | 77.3% (54.6-92.2%) |
| 22 follow-ups | Apple Music | 21 | 0 | 0 | #738, #1092, #1093, #1845, #4276, #6089 | 0 | 0.0% (0.0-16.1%) | 28.6% (11.3-52.2%) |

- Off-by-one (whole table, 3 stored titles that fit a neighbouring song better than their own): see [Off-by-one](#off-by-one-scan-whole-table).
- Album period vs date (whole table): 7 links sit on a dated album whose period doesn't contain the song's date; see [Boundaries](#year-and-season-boundaries-whole-table).
- Paste file: 0 problems in 6502 rows (checked against links.csv and the 5113 song rows of the cached public sheet).

## What it shows

- **Titles: Bandcamp 0 wrong of 58, Apple Music 0 wrong of 59** high links opened in the spread and check samples. Across all 201 opened links (check-rated and follow-ups included): 0 titled as another song, 0 unsettled, and 6 Bandcamp and 0 Apple tracks carrying another song's title over this day's audio.
- 6 titles needed a hand verdict (#3495 apple, #4154 apple, #4571 apple, #4705 apple, #5830 apple, #5858 apple); 6 of them are the day's song under a shortened or reworded title (reasons in the tables).
- **Off-by-one in titles:** the whole-table scan finds 3 stored titles that fit a neighbour better than their own song and 0 runs of them; opened live, their verdicts are mislabelled 3. In all, 6 Bandcamp pages show another song's title over this day's file: #2390 ('Don't Soldier On Blindly'), #1230 ('A Partial List of the Things I'm Not'), #1256 ('I've Got An Idea'), #2136 ('I Am Here For You'), #2402 ('And I Make No Sense'), #2611 ('Lay Me Down Low'). They are rated high, so the paste file links them; by length the link plays the right song, but the page shows the wrong name.
- **Year and season boundaries:** 7 links sit on an album whose period doesn't contain the date, each by one day or by one year album; opened live, their verdicts are right 7. A right title there means the album was sequenced across the boundary, not that the link is wrong. The 29 boundary songs in the spread sample (leap days, Jan 1, Dec 31, season edges) have 57 links opened, with title verdicts right 57.
- **The real problem is audio, not titles.** Across the whole table, 53 files look like another day's song by length; 19 of them are rated high and in the paste file. The groups that hold a high one (#N->#M: the file on #N's link is #M's; #N=#M: one file on both, whose is unclear; * = rated high): apple #738*->#737; apple #1092*=#1093, #1093*=#1092; apple #1845*->#1842; apple #4276*->#4275; apple #6089*->#6088; bandcamp #738*->#737; bandcamp #1092*=#1093, #1093*=#1092; bandcamp #3828->#3829, #3829->#3830, #3830*->#3831, #3831->#3832, #3832*->#3833, #3833->#3834; bandcamp #4343*->#4344; bandcamp #4366*->#4367, #4367*->#4368; bandcamp #4678->#4679, #4679->#4680, #4680->#4681, #4681*->#4678; bandcamp #4892->#4893, #4893->#4894, #4894->#4895, #4895->#4896, #4896->#4897, #4897->#4898, #4898*->#4899; bandcamp #5297*->#5294; bandcamp #6208*=#6209, #6209*=#6208. 32 of these 32 links were opened live, and each page still has the stored title, album and length.
- On Bandcamp, 23 of the 26 opened pages in those groups are songs from 2017 on, and all 23 were created between 2026-06-17 and 2026-06-20: the June 2026 upload of the Year Nine to Seventeen albums (see [Bandcamp upload dates](#bandcamp-upload-dates)). The earlier ones (#738, #1092, #1093) have the same file on Apple Music too, so the mix-up is in the masters, not the upload.
- Lengths are the only audio evidence here (nothing was downloaded), so a lone 'looks like' may be a coincidence; 'same file' (two titles, one file to 0.05 s) and runs are strong.
- **Paste file:** 0 problems; every row lines up with the public sheet's row for the same song.

## How a link is judged

- **Title** (the verdict): the live title is compared with the catalog title of the song and of the 3 songs either side, after lower-casing, dropping punctuation, bracketed parts and "feat. ...", and reading Apple's `*` as any letter. Similarity 0.85 or more is the same title (**right**); a neighbour that is the same title and beats the song's own by 0.05 is **wrong**; anything else is **unclear** and gets a hand verdict from the evidence below, with the reason written out.
- **Album and date**: Apple's seasonal albums are calendar quarters (Winter = Jan-Mar, Spring = Apr-Jun, Summer = Jul-Sep, Fall = Oct-Dec; the albums' first tracks confirm this) and its monthly albums are months. Bandcamp's year albums are calendar years (Year One = 2009). Bandcamp pages also give the upload date.
- **Audio** (lengths only; no audio was downloaded): the live length is **agrees** when within 3 s or 3% of the catalog's video Length, or of the other service's file ('agrees with ..., not the video'). It is **same file as #M** when this service has a file of the same length (within 0.05 s) on a song 1-3 days away whose video Length differs by more than 5 s, and the file is #M's: the other service's file for #M is that length and its file for this song isn't (or, failing that, only #M's video fits). It is **looks like #M** when it is more than 10 s and 10% from both the video and the other service, but within 1.5 s of #M's video or other-service file (1-3 days away), or when it sits next to such a file and fits the same shift ('in a run'). 'Same file' is strong evidence; a lone 'looks like' can be a coincidence. Anything else off is **differs**.
- A **title error** is a link rated **high** (so it goes in the sheet) whose track is titled as another song. **Any problem** also counts a mislabelled track and a file that looks like another day's. Rates come with exact 95% (Clopper-Pearson) intervals; with no errors in n links the upper bound is about 3.7/n.

## Spread sample (40 songs)

| # | Date | Why picked | Catalog title | Bandcamp now | Bandcamp verdict | Apple Music now | Apple verdict |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2009-01-01 (BC upload +344 d) | Jan 1, song #1 | In the Time of the Gods (156 s) | In The Time of the Gods (Song A Day: Year One #1, 156 s) | **right** | In the Time of the Gods (Winter, 2009 #1, 156 s) | **right** |
| 273 | 2009-09-30 (BC upload +84 d) | last day of Summer 2009 | Vulcan Smile (24 s) | Vulcan Smile (Song A Day: Year One #273, 25 s) | **right** | Vulcan Smile (Summer, 2009 #92, 25 s) | **right** |
| 274 | 2009-10-01 (BC upload +83 d) | first day of Fall 2009 | Downstairs Bear (75 s) | Downstairs Bear (Song A Day: Year One #275, 76 s) | **right** | Downstairs Bear (Summer, 2009 #93, 76 s) | **right**; album: 'Summer, 2009' runs 2009-07-01..2009-09-30; the song is 1 day(s) after it |
| 365 | 2009-12-31 (BC upload -1 d) | Dec 31 | Me, I Write a Song a Day (188 s) | Me, I Write A Song A Day (Song A Day: Year One #365, 189 s) | **right** | Me, I Write a Song a Day (Fall, 2009 #91, 189 s) | **right** |
| 366 | 2010-01-01 (BC upload +2 d) | Jan 1 | Happy New Year Everyone From The Mann Family Players (47 s) | Happy New Year Everyone From The Mann Family Players (Song A Day: Year Two #1, 47 s) | **right** | Happy New Year Everyone from the Mann Family Players (Winter, 2010 #1, 47 s) | **right** |
| 546 | 2010-06-30 (BC upload +23 d) | last day of Spring 2010 | Let's All Take A Trip (127 s) | Let's All Take A Trip (Song A Day: Year Two #180, 126 s) | **right** | Let's All Take a Trip (Spring, 2010 #92, 127 s) | **right** |
| 547 | 2010-07-01 (BC upload +22 d) | first day of Summer 2010 | Bones Come To Life (158 s) | Bones Come To Life (Song A Day: Year Two #181, 158 s) | **right** | Bones Come to Life (Spring, 2010 #93, 158 s) | **right**; album: 'Spring, 2010' runs 2010-04-01..2010-06-30; the song is 1 day(s) after it |
| 820 | 2011-03-31 (BC upload +0 d) | last day of Winter 2011 | The Kickstarter Song (280 s) | The Kickstarter Song (Song A Day: Year Three #89, 220 s) | **right**; audio agrees with apple, not the video | The Kickstarter Song (Winter, 2011 #90, 220 s) | **right**; audio agrees with bandcamp, not the video |
| 821 | 2011-04-01 (BC upload +0 d) | first day of Spring 2011 | Alanis-aurus Rex (63 s) | Alanisaurus Rex (Song A Day: Year Three #90, 64 s) | **right** | Alanis-Aurus Rex (Winter, 2011 #23, 64 s) | **right**; album: 'Winter, 2011' runs 2011-01-01..2011-03-31; the song is 1 day(s) after it |
| 1155 | 2012-02-29 (BC upload +1 d) | leap day | FaceBook Timeline Song (68 s) | Facebook Timeline Song (Song A Day: Year Four #59, 28 s) | **right**; audio agrees with apple, not the video | Facebook Timeline Song (Winter, 2012 #60, 28 s) | **right**; audio agrees with bandcamp, not the video |
| 1393 | 2012-10-24 (BC upload +2 d) | random day in 2012 | Elves on the Other Side (199 s) | Elves On The Other Side (Song A Day: Year Four #294, 200 s) | **right** | Elves on the Other Side (Fall, 2012 #24, 200 s) | **right** |
| 1467 | 2013-01-06 (BC upload +5 d) | random day in 2013 | I'm in a Bubble State of Mind (121 s) | I'm In A Bubble State of Mind (Song A Day: Year Five #6, 121 s) | **right** | I'm in a Bubble State of Mind (Winter, 2013 #6, 121 s) | **right** |
| 1826 | 2013-12-31 (BC upload +3 d) | Dec 31 | I Will Write Another Song (359 s) | I Will Write Another Song (Song A Day: Year Five #367, 359 s) | **right** | I Will Write Another Song (Fall, 2013 #91, 359 s) | **right** |
| 1827 | 2014-01-01 (BC upload +22 d) | Jan 1 | Me and Tilley (299 s) | Me And Tilley (Song A Day: Year Six #1, 160 s) | **right**; audio agrees with apple, not the video | Me and Tilley (Fall, 2013 #92, 160 s) | **right**; album: 'Fall, 2013' runs 2013-10-01..2013-12-31; the song is 1 day(s) after it; audio agrees with bandcamp, not the video |
| 1916 | 2014-03-31 (BC upload +276 d) | last day of Winter 2014 (no Spring 2014 album follows) | I Don't Try (214 s) | I Don't Try (Song A Day: Year Six #90, 213 s) | **right** | I Don't Try (Winter, 2014 #89, 213 s) | **right** |
| 2008 | 2014-07-01 (BC upload +185 d) | first day of Summer 2014 | The Song of Impossible Rhymes (229 s) | The Song of Impossible Rhymes (Song A Day: Year Six #182, 226 s) | **right** | no link in links.csv |  |
| 2372 | 2015-06-30 (BC upload +140 d) | last day of Spring 2015 (no Summer 2015 album follows) | How to Choose a Password (190 s) | How To Choose A Password (Song A Day: Year Seven #183, 189 s) | **right** | How to Choose a Password (Spring, 2015 #91, 190 s) | **right** |
| 2465 | 2015-10-01 (BC upload +48 d) | first day of Fall 2015 | Whispering Gallery (109 s) | Whispering Gallery (Song A Day: Year Seven #276, 109 s) | **right** | Whispering Gallery (Fall, 2015 #1, 109 s) | **right** |
| 2616 | 2016-02-29 (BC upload +308 d) | leap day | Where Are You Elizabeth Warren? (147 s) | Where Are You Elizabeth Warren (Song A Day: Year Eight #59, 146 s) | **right** | Where Are You Elizabeth Warren? (Winter, 2016 #60, 146 s) | **right** |
| 2752 | 2016-07-14 (BC upload +175 d) | random day in 2016 | Something I'm Not (246 s) | Something I'm Not (Song A Day: Year Eight #196, 246 s) | **right** | Something I'm Not (Summer, 2016 #14, 246 s) | **right** |
| 3103 | 2017-06-30 (BC upload +3273 d) | last day of Spring 2017 | I Was on An Airplane Above the Clouds (89 s) | I Was on An Airplane Above the Clouds (Song A Day: Year Nine #181, 89 s) | **right** | I Was on an Airplane Above the Clouds (Summer, 2017 #1, 89 s) | **right**; album: 'Summer, 2017' runs 2017-07-01..2017-09-30; the song is 1 day(s) before it |
| 3195 | 2017-09-30 (BC upload +3181 d) | last day of Summer 2017, the last seasonal album | Mr So Called President (92 s) | Mr  So Called President (Song A Day: Year Nine #273, 91 s) | **right** | Mr So Called President (Summer, 2017 #93, 91 s) | **right** |
| 3196 | 2017-10-01 (BC upload +3180 d) | first monthly album (October, 2017) | Concern Troll (185 s) | Concern Troll (Song A Day: Year Nine #274, 184 s) | **right** | Concern Troll (October, 2017 #1, 184 s) | **right** |
| 3287 | 2017-12-31 (BC upload +3089 d) | Dec 31 | I Wrote My First Song On A PIzza Box (181 s) | I Wrote My First Song On A PIzza Box (Song A Day: Year Nine #365, 181 s) | **right** | I Wrote My First Song on a Pizza Box (December, 2017 #31, 181 s) | **right** |
| 3288 | 2018-01-01 (BC upload +3089 d) | Jan 1 | Eventually I'm Returning To Right Here (188 s) | Eventually I'm Returning To Right Here (Song A Day: Year Ten #1, 188 s) | **right** | Eventually I'm Returning to Right Here (January, 2018 #1, 188 s) | **right** |
| 3495 | 2018-07-27 (BC upload +2882 d) | random day in 2018 | Yo Ho Ho Powerful Sea (173 s) | Yo Ho Ho Powerful Sea (Song A Day: Year Ten #208, 172 s) | **right** | Powerful Sea (July, 2018 #27, 172 s) | **right**; 'Powerful Sea' is the end of the catalog title; it is track 27 of 'July, 2018' (the 27th) and the file is 172.1 s, the same as Bandcamp's 'Yo Ho Ho Powerful Sea' |
| 3813 | 2019-06-10 (BC upload +2564 d) | random day in 2019 | What Are You Waiting For (120 s) | What Are You Waiting For (Song A Day: Year Eleven #161, 119 s) | **right** | What Are You Waiting For (June, 2019 #10, 119 s) | **right** |
| 3932 | 2019-10-07 (BC upload +2445 d) | random day in 2019 | Marching Orders (82 s) | Marching Orders (Song A Day: Year Eleven #280, 82 s) | **right** | Marching Orders (October, 2019 #7, 143 s) | **right**; audio differs |
| 4077 | 2020-02-29 (BC upload +2301 d) | leap day | The Corona of The Sun (168 s) | The Corona of The Sun (Song A Day: Year Twelve #60, 169 s) | **right** | The Corona of the Sun (February, 2020 #29, 169 s) | **right** |
| 4383 | 2020-12-31 (BC upload +1995 d) | Dec 31 | Put Everything Bad About Last Year Into A Bucket And Blow It Up (103 s) | Put Everything Bad About Last Year Into A Bucket And Blow It Up (Song A Day: Year Twelve #366, 104 s) | **right** | Put Everything Bad About Last Year Into a Bucket and Blow It Up (December, 2020 #31, 106 s) | **right**; audio agrees with bandcamp, not the video |
| 4384 | 2021-01-01 (BC upload +1994 d) | Jan 1 | Songs, The Hat (535 s) | Songs, The Hat (Song A Day: Year Thirteen #1, 535 s) | **right** | Songs, The Hat (January, 2021 #1, 86 s) | **right**; audio differs |
| 4710 | 2021-11-23 (BC upload +1668 d) | random day in 2021 | Hedge Fund Guy (Ken Griffin) (98 s) | Hedge Fund Guy (Ken Griffin) (Song A Day: Year Thirteen #327, 99 s) | **right** | Hedge Fund Guy (Ken Griffin) (November, 2021 #23, 101 s) | **right**; audio agrees with bandcamp, not the video |
| 5078 | 2022-11-26 (BC upload +1300 d) | random day in 2022 | Jealous of Your Friends (97 s) | Jealous of Your Friends (Song A Day: Year Fourteen #330, 97 s) | **right** | Jealous of Your Friends (November, 2022 #26, 97 s) | **right** |
| 5113 | 2022-12-31 (BC upload +1265 d) | Dec 31, last row of the public sheet | The Last Song of 2022 (116 s) | The Last Song of 2022 (Song A Day: Year Fourteen #365, 116 s) | **right** | The Last Song Of 2022 (December, 2022 #31, 116 s) | **right** |
| 5233 | 2023-04-30 (BC upload +1146 d) | random day in 2023 | Epstien Was A CIA Plant (94 s) | Epstien Was A CIA Plant (Song A Day: Year Fifteen #120, 94 s) | **right** | Epstien Was a CIA Plant (April, 2023 #30, 94 s) | **right** |
| 5311 | 2023-07-17 (BC upload +1068 d) | random day in 2023 | PinkyDoll (It's All Pavlovian) (121 s) | PinkyDoll (It's All Pavlovian) (Song A Day: Year Fifteen #198, 129 s) | **right**; audio agrees with apple, not the video | PinkyDoll (It's All Pavlovian) (July, 2023Driving, Driving, Driving, Driving #17, 129 s) | **right**; 'July, 2023Driving, Driving, Driving, Driving' is not a dated album; audio agrees with bandcamp, not the video |
| 5538 | 2024-02-29 (BC upload +841 d) | leap day | Four Year Cycles (137 s) | Four Year Cycles (Song A Day: Year Sixteen #60, 137 s) | **right** | Four Year Cycles (February, 2024 #29, 137 s) | **right** |
| 5725 | 2024-09-03 (BC upload +654 d) | random day in 2024 | Death & Time (238 s) | Death & Time (Song A Day: Year Sixteen #247, 238 s) | **right** | Death & Time (September, 2024 #3, 238 s) | **right** |
| 6209 | 2025-12-31 (BC upload +171 d) | Dec 31 | Seventeen Years (258 s) | Seventeen Years (Song A Day: Year Seventeen #365, 133 s) | **right**; audio same file as #6208, whose is unclear | Seventeen Years (December, 2025 #30, 263 s) | **right** |
| 6210 | 2026-01-01 (BC upload +292 d) | Jan 1 | Game A Day (133 s) | Game A Day (Song A Day: Year Eighteen #1, 136 s) | **right** | Game A Day (January, 2026 #1, 136 s) | **right** |

### Spread songs with no Apple link: searched on Apple

For each, Apple's Search API (US store) was asked for 'jonathan mann' plus the catalog title; any Jonathan Mann track whose title fits (similarity 0.6+) is listed.

- #2008 2014-07-01 'The Song of Impossible Rhymes': 4 results; no Jonathan Mann track with that title

## Songs rated check (all 40)

| # | Date | Why picked | Catalog title | Bandcamp now | Bandcamp verdict | Apple Music now | Apple verdict |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 749 | 2011-01-19 (BC upload +33 d) | apple_music_audio_shifted | Hank is Paranoid (64 s) | Hank is Paranoid (Song A Day: Year Three #18, 66 s) | **right** | Hank Is Paranoid (Winter, 2011 #19, 105 s) | **right**; audio looks like #750; rated check |
| 755 | 2011-01-25 (BC upload +27 d) | audio_differs\|apple_music_audio_shifted | The Mac vs. PC Conciliatory Song (174 s) | The Mac vs. PC Conciliatory Song (Song A Day: Year Three #24, 122 s) | **right**; audio differs | The Mac Vs. PC Conciliatory Song (Winter, 2011 #25, 75 s) | **right**; audio same file as #756; rated check |
| 1193 | 2012-04-07 (BC upload -85 d) | apple_music_audio_shifted | Your Day (126 s) | Your Day (Song A Day: Year Four #94, 126 s) | **right** | Your Day (Spring, 2012 #7, 70 s) | **right**; audio same file as #1192; rated check |
| 1371 | 2012-10-02 (BC upload +24 d) | apple_music_audio_shifted | MItt Romney Flip Flop Autotune (183 s) | Mitt Romney Flip-Flop Autotune (Song A Day: Year Four #272, 183 s) | **right** | Mitt Romney Flip Flop Autotune (Fall, 2012 #2, 68 s) | **right**; audio looks like #1370; rated check |
| 1501 | 2013-02-09 (BC upload +0 d) | apple_music_audio_shifted | George W. Bush's Self Portraits (62 s) | George W. Bush's Self Portraits (Song A Day: Year Five #41, 63 s) | **right** | George W. Bush's Self Portraits (Winter, 2013 #40, 149 s) | **right**; audio same file as #1500; rated check |
| 1579 | 2013-04-28 (BC upload +234 d) | apple_music_audio_shifted | When It Rains You Feel It in Your Bones (233 s) | When It Rains You Feel It In Your Bones (Song A Day: Year Five #119, 233 s) | **right** | When It Rains You Feel It in Your Bones (Spring, 2013 #28, 127 s) | **right**; audio same file as #1577; rated check |
| 1975 | 2014-05-29 (BC upload +217 d) | bandcamp_audio_shifted | Patreon Shoutout Song (151 s) | Patreon Shoutout Song (Song A Day: Year Six #149, 212 s) | **right**; audio looks like #1976; rated check | no link in links.csv |  |
| 2182 | 2014-12-22 (BC upload +12 d) | apple_music_audio_shifted | All Signs Point (231 s) | All Signs Point (Song A Day: Year Six #356, 230 s) | **right** | All Signs Point (Fall, 2014 #83, 144 s) | **right**; audio looks like #2183; rated check |
| 2183 | 2014-12-23 (BC upload +11 d) | apple_music_audio_shifted | KEDQ! (145 s) | KEDQ! (Song A Day: Year Six #355, 144 s) | **right** | Kedq! (Fall, 2014 #84, 230 s) | **right**; audio looks like #2182; rated check |
| 2390 | 2015-07-18 (BC upload +122 d) | apple_music_ambiguous_title\|bandcamp_mislabelled\|titles_differ\|apple_music_weak_match | Infinite Ways to Die (321 s) | Don't Soldier On Blindly (Song A Day: Year Seven #201, 321 s) | **mislabelled**; title is #2389's ('Don't Soldier on Blindly', 214 s), but the file is this day's length | Infinite Ways to Die (The Arctic Mountains in Your Heart #4, 308 s) | **right**; 'The Arctic Mountains in Your Heart' is not a dated album; audio differs; rated check |
| 2966 | 2017-02-13 (BC upload +3410 d) | bandcamp_audio_shifted | Who's Gonna Take the Fall? (48 s) | Who's Gonna Take the Fall? (Song A Day: Year Nine #44, 60 s) | **right**; audio same file as #2967; rated check | Who's Gonna Take the Fall? (Winter, 2017 #44, 48 s) | **right** |
| 3818 | 2019-06-15 (BC upload +2559 d) | apple_music_audio_shifted | That Is Not A Heart Warming Story (146 s) | That Is Not A Heart Warming Story (Song A Day: Year Eleven #166, 146 s) | **right** | That Is Not a Heart Warming Story (June, 2019 #15, 164 s) | **right**; audio looks like #3819; rated check |
| 3828 | 2019-06-25 (BC upload +2549 d) | bandcamp_audio_shifted | A Commissioner's Work Is Never Done (297 s) | A Commissioner's Work Is Never Done (Song A Day: Year Eleven #176, 123 s) | **right**; audio looks like #3829; rated check | A Commissioner's Work Is Never Done (June, 2019 #25, 298 s) | **right** |
| 3829 | 2019-06-26 (BC upload +2548 d) | bandcamp_audio_shifted | I'm With You (124 s) | I'm With You (Song A Day: Year Eleven #177, 148 s) | **right**; audio looks like #3830; rated check | I'm With You (June, 2019 #26, 123 s) | **right** |
| 3831 | 2019-06-28 (BC upload +2546 d) | bandcamp_audio_shifted | Marianne Williamson's Closing Remarks (Love Will Win) (70 s) | Marianne Williamson's Closing Remarks (Love Will Win) (Song A Day: Year Eleven #179, 167 s) | **right**; audio looks like #3832; rated check | Marianne Williamson's Closing Remarks (Love Will Win) (June, 2019 #28, 65 s) | **right**; audio differs |
| 3833 | 2019-06-30 (BC upload +2544 d) | bandcamp_audio_shifted | My LifeIs A Pile of Food Made Out Of Wood (175 s) | My LifeIs A Pile of Food Made Out Of Wood (Song A Day: Year Eleven #181, 289 s) | **right**; audio same file as #3834; rated check | My Life Is a Pile of Food Made Out of Wood (June, 2019 #30, 186 s) | **right**; audio differs |
| 4131 | 2020-04-23 (BC upload +2247 d) | apple_music_ambiguous_title\|apple_music_weak_match | There Are No People In The Future (232 s) | There Are No People In The Future (Song A Day: Year Twelve #114, 233 s) | **right** | There Are No People in the Future (There Are No People in the Future - Single #1, 236 s) | **right**; 'There Are No People in the Future - Single' is not a dated album; rated check |
| 4154 | 2020-05-16 (BC upload +2224 d) | titles_differ\|apple_music_weak_match | Kenneth Copeland On COVID-19 (Wind of God chill remix) (104 s) | Kenneth Copeland On COVID-19 (Wind of God chill remix) (Song A Day: Year Twelve #137, 104 s) | **right** | The Wind of God (The Wind of God - Single #1, 107 s) | **right**; the single 'The Wind of God' is the only Apple track for the catalog's only 'Wind of God' song (this one, a 'Wind of God chill remix'); 107.3 s against Bandcamp's 104.0 s; 'The Wind of God - Single' is not a dated album; audio differs; rated check |
| 4571 | 2021-07-07 (BC upload +1807 d) | titles_differ\|apple_music_weak_match | Woodcock Luring Worms (109 s) | Woodcock Luring Worms (Song A Day: Year Thirteen #188, 110 s) | **right** | The American Woodcock Dance (The American Woodcock Dance - Single #1, 113 s) | **right**; probably: the single 'The American Woodcock Dance' and this day's 'Woodcock Luring Worms' are the catalog's only woodcock song; 113.5 s against Bandcamp's 109.6 s, a few seconds longer as Apple's singles often are; 'The American Woodcock Dance - Single' is not a dated album; audio differs; rated check |
| 4678 | 2021-10-22 (BC upload +1700 d) | bandcamp_audio_shifted | What The Fuck? (worldcoin) (108 s) | What The Fuck? (worldcoin) (Song A Day: Year Thirteen #295, 168 s) | **right**; audio looks like #4679; rated check | What the F**k? (worldcoin) (October, 2021 #22, 110 s) | **right** |
| 4679 | 2021-10-23 (BC upload +1699 d) | bandcamp_audio_shifted | What's The Floor Price of Your Heart (167 s) | What's The Floor Price of Your Heart (Song A Day: Year Thirteen #296, 68 s) | **right**; audio looks like #4680; rated check | What's the Floor Price of Your Heart (October, 2021 #23, 168 s) | **right** |
| 4680 | 2021-10-24 (BC upload +1698 d) | bandcamp_audio_shifted | It's Halloween Again (67 s) | It's Halloween Again (Song A Day: Year Thirteen #297, 127 s) | **right**; audio looks like #4681; rated check | It's Halloween Again (October, 2021 #24, 68 s) | **right** |
| 4705 | 2021-11-18 (BC upload +1673 d) | apple_music_weak_match | Please Trade Back (107 s) | Please Trade Back (Song A Day: Year Thirteen #322, 107 s) | **right** | Please Trade My Ape Back (November, 2021 #18, 115 s) | **right**; track 18 of 'November, 2021' (the 18th), and the title is the catalog's with 'My Ape' added; the file is 7 s longer than Bandcamp's (114.5 s vs 107.4 s); audio differs; rated check |
| 4892 | 2022-05-24 (BC upload +1486 d) | bandcamp_audio_shifted | The Great King Snail (106 s) | The Great King Snail (Song A Day: Year Fourteen #144, 131 s) | **right**; audio looks like #4893; rated check | The Great King Snail (May, 2022 #24, 106 s) | **right** |
| 4893 | 2022-05-25 (BC upload +1485 d) | bandcamp_audio_shifted | And Now I'm Gone (130 s) | And Now I'm Gone (Song A Day: Year Fourteen #145, 181 s) | **right**; audio looks like #4894; rated check | And Now I'm Gone (May, 2022 #25, 131 s) | **right** |
| 4894 | 2022-05-26 (BC upload +1484 d) | bandcamp_audio_shifted | Don't Think About The Price of Eth, Watch My Driveway Get Paved Instead (174 s) | Don't Think About The Price of Eth, Watch My Driveway Get Paved Instead (Song A Day: Year Fourteen #146, 73 s) | **right**; audio looks like #4895; rated check | Don't Think About the Price of Eth, Watch My Driveway Get Paved Instead (May, 2022 #26, 181 s) | **right**; audio differs |
| 4895 | 2022-05-27 (BC upload +1483 d) | bandcamp_audio_shifted | Ropsten Trolls (66 s) | Ropsten Trolls (Song A Day: Year Fourteen #147, 155 s) | **right**; audio looks like #4896; rated check | Ropsten Trolls (May, 2022 #27, 73 s) | **right**; audio differs |
| 4896 | 2022-05-28 (BC upload +1482 d) | bandcamp_audio_shifted | Saturday Morning Banjo Song (155 s) | Saturday Morning Banjo Song (Song A Day: Year Fourteen #148, 136 s) | **right**; audio looks like #4897; rated check | Saturday Morning Banjo Song (May, 2022 #28, 155 s) | **right** |
| 4897 | 2022-05-29 (BC upload +1481 d) | bandcamp_audio_shifted | Imposter Syndrome (132 s) | Imposter Syndrome (Song A Day: Year Fourteen #149, 152 s) | **right**; audio looks like #4898; rated check | Imposter Syndrome (May, 2022 #29, 136 s) | **right** |
| 4920 | 2022-06-21 (BC upload +1458 d) | bandcamp_audio_shifted | Jonathan's 2094th Dream (257 s) | Jonathan's 2094th Dream (Song A Day: Year Fourteen #172, 200 s) | **right**; audio looks like #4921; rated check | Jonathan's 2094th Dream (June, 2022 #21, 257 s) | **right** |
| 4921 | 2022-06-22 (BC upload +1457 d) | bandcamp_audio_shifted\|apple_music_audio_shifted | Creeps and Weirdos (156 s) | Creeps and Weirdos (Song A Day: Year Fourteen #173, 257 s) | **right**; audio looks like #4920; rated check | Creeps and Weirdos (June, 2022 #22, 200 s) | **right**; audio looks like #4920; rated check |
| 4983 | 2022-08-23 (BC upload +1395 d) | bandcamp_audio_shifted | We Are Not Meant To Be Machines (122 s) | We Are Not Meant To Be Machines (Song A Day: Year Fourteen #235, 146 s) | **right**; audio looks like #4984; rated check | We Are Not Meant To Be Machines (August, 2022 #23, 122 s) | **right** |
| 4984 | 2022-08-24 (BC upload +1394 d) | bandcamp_audio_shifted | I'm Lost In The Machine (145 s) | I'm Lost In The Machine (Song A Day: Year Fourteen #236, 122 s) | **right**; audio looks like #4983; rated check | I'm Lost In the Machine (August, 2022 #24, 146 s) | **right** |
| 4995 | 2022-09-04 (BC upload +1383 d) | bandcamp_audio_shifted | Sometimes I Don't Feel Like Writing Another Song (107 s) | Sometimes I Don't Feel Like Writing Another Song (Song A Day: Year Fourteen #247, 44 s) | **right**; audio same file as #4996; rated check | Sometimes I Don't Feel Like Writing Another Song (September, 2022 #4, 107 s) | **right** |
| 5487 | 2024-01-09 (BC upload +892 d) | bandcamp_audio_shifted | We Are Alone (178 s) | We Are Alone (Song A Day: Year Sixteen #9, 248 s) | **right**; audio same file as #5486; rated check | We Are Alone (January, 2024 #9, 180 s) | **right** |
| 5830 | 2024-12-17 (BC upload +549 d) | apple_music_weak_match | Pudgy Pengu Remix (152 s) | Pudgy Pengu Remix (Song A Day: Year Sixteen #352, 152 s) | **right** | Pudgy Pengu Two (December, 2024 #17, 154 s) | **right**; track 17 of 'December, 2024' (the 17th); 'Pudgy Pengu Two' for 'Pudgy Pengu Remix', 153.6 s against Bandcamp's 151.7 s; rated check |
| 5858 | 2025-01-14 (BC upload +522 d) | apple_music_weak_match | TikTok Refugee (115 s) | TikTok Refugee (Song A Day: Year Seventeen #14, 115 s) | **right** | TT Refugee (January, 2025 #14, 113 s) | **right**; track 14 of 'January, 2025' (the 14th); Apple writes TikTok as 'TT' here and on #5863 ('TT's Gone, BiliBili'); 113.2 s against Bandcamp's 115.3 s; rated check |
| 5870 | 2025-01-26 (BC upload +510 d) | apple_music_audio_shifted | Are You A Barnyard Animal? (177 s) | Are You A Barnyard Animal? (Song A Day: Year Seventeen #26, 177 s) | **right** | Are You a Barnyard Animal? (January, 2025 #26, 198 s) | **right**; audio looks like #5871; rated check |
| 5883 | 2025-02-08 (BC upload +497 d) | apple_music_audio_shifted | Saturday Morning Cartoons (102 s) | Saturday Morning Cartoons (Song A Day: Year Seventeen #39, 102 s) | **right** | Saturday Morning Cartoons (February, 2025 #8, 128 s) | **right**; audio looks like #5885; rated check |
| 5994 | 2025-05-30 (BC upload +386 d) | bandcamp_audio_shifted | How Long Before They Drop A Bomb On Us? (175 s) | How Long Before They Drop A Bomb On Us? (Song A Day: Year Seventeen #150, 152 s) | **right**; audio same file as #5993; rated check | How Long Before They Drop A Bomb On Us? (May, 2025 #30, 175 s) | **right** |

### What the check ratings hold up to

Each of the links rated check, by what the live page shows. A check rating is borne out when the file looks like another day's or differs from its song; it is over-cautious when the title is the day's song and the file agrees.

| Service | Title | File | Links |
| --- | --- | --- | ---: |
| apple | right | agrees | 3 |
| apple | right | differs | 4 |
| apple | right | looks like another day | 12 |
| bandcamp | right | looks like another day | 22 |

Titles of check links that only a hand verdict could settle: #4154 apple, #4571 apple, #4705 apple, #5830 apple, #5858 apple.

### Bandcamp upload dates

Each Bandcamp track page carries the date the track was created. Days from the song's date to that upload, for the pages opened, by the song's year:

| Year | Pages | Earliest | Median | Latest | Uploaded between |
| --- | ---: | ---: | ---: | ---: | --- |
| 2009 | 4 | -1 | +84 | +344 | 2009-12-11 .. 2009-12-30 |
| 2010 | 3 | +2 | +22 | +23 | 2010-01-03 .. 2010-07-23 |
| 2011 | 7 | +0 | +33 | +44 | 2011-02-21 .. 2012-02-06 |
| 2012 | 7 | -148 | +1 | +24 | 2012-01-13 .. 2012-10-26 |
| 2013 | 4 | +0 | +5 | +234 | 2013-01-11 .. 2014-01-03 |
| 2014 | 8 | +4 | +58 | +276 | 2014-01-23 .. 2015-01-03 |
| 2015 | 4 | +48 | +122 | +140 | 2015-11-17 .. 2015-11-18 |
| 2016 | 3 | +175 | +308 | +313 | 2017-01-02 .. 2017-01-05 |
| 2017 | 5 | +3089 | +3181 | +3410 | 2026-06-16 .. 2026-06-16 |
| 2018 | 2 | +2882 | +3089 | +3089 | 2026-06-17 .. 2026-06-17 |
| 2019 | 9 | +2445 | +2547 | +2564 | 2026-06-17 .. 2026-06-17 |
| 2020 | 8 | +1995 | +2102 | +2301 | 2026-06-18 .. 2026-06-18 |
| 2021 | 8 | +1668 | +1699 | +1994 | 2026-06-18 .. 2026-06-18 |
| 2022 | 14 | +1265 | +1480 | +1486 | 2026-06-18 .. 2026-06-18 |
| 2023 | 4 | +1023 | +1082 | +1146 | 2026-06-19 .. 2026-06-19 |
| 2024 | 4 | +549 | +841 | +892 | 2026-06-19 .. 2026-06-19 |
| 2025 | 7 | +171 | +386 | +522 | 2026-06-20 .. 2026-06-20 |
| 2026 | 1 | +292 | +292 | +292 | 2026-10-20 .. 2026-10-20 |

A number below -2 is a track created before its song was written (a day either way is the GMT clock): #1193 (-85 d, right), #1230 (-122 d, mislabelled), #1256 (-148 d, mislabelled). Such a page was first made for something else and later given this file or title.

## Follow-ups from the whole-table scans

| # | Date | Why picked | Catalog title | Bandcamp now | Bandcamp verdict | Apple Music now | Apple verdict |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 738 | 2011-01-08 (BC upload +44 d) | bandcamp file: same file as #737 | EagleShark Raids the Robot Xombies (49 s) | EagleShark Raids the Robot Xombies (Song A Day: Year Three #8, 65 s) | **right**; audio same file as #737 | EagleShark Raids the Robot Xombies (Winter, 2011 #8, 65 s) | **right**; audio same file as #737 |
| 1092 | 2011-12-28 (BC upload +40 d) | bandcamp file: same file as #1093, whose is unclear | Made for Another Life (295 s) | Made For Another Life (Song A Day: Year Three #353, 202 s) | **right**; audio same file as #1093, whose is unclear | Made for Another Life (Fall, 2011 #89, 202 s) | **right**; audio same file as #1093, whose is unclear |
| 1093 | 2011-12-29 (BC upload +39 d) | bandcamp file: same file as #1092, whose is unclear | Piss Like a Racehorse (106 s) | Piss Like A Racehorse (Song A Day: Year Three #354, 202 s) | **right**; audio same file as #1092, whose is unclear | Piss Like a Racehorse (Fall, 2011 #90, 202 s) | **right**; audio same file as #1092, whose is unclear |
| 1144 | 2012-02-18 (BC upload +1 d) | bandcamp album is outside the date | Go for Pro Anthem #2 (111 s) | Go For Pro Anthem 2 (Song A Day: Year Three #358, 114 s) | **right**; album: 'Song A Day: Year Three' is 2011, the song is 2012 | Go for Pro Anthem #2 (Winter, 2012 #49, 112 s) | **right** |
| 1230 | 2012-05-14 (BC upload -122 d) | links.py flags Bandcamp's title as another song's | A Partial List of the Things That Make Me Feel Loneliness (181 s) | A Partial List of the Things I'm Not (Song A Day: Year Four #131, 182 s) | **mislabelled**; title is #1071's ('A Partial List of the Things I'm Not', 120 s), but the file is this day's length | A Partial List of the Things That Make Me Feel Loneliness (Spring, 2012 #44, 182 s) | **right** |
| 1256 | 2012-06-09 (BC upload -148 d) | links.py flags Bandcamp's title as another song's | Anidea (130 s) | I've Got An Idea (Song A Day: Year Four #157, 130 s) | **mislabelled**; title is #651's ('I've Got An Idea', 209 s), but the file is this day's length | Anidea (Spring, 2012 #70, 130 s) | **right** |
| 1845 | 2014-01-19 (BC upload +4 d) | apple file: same file as #1842 | I Don't Wanna Go to New Jersey (122 s) | Don't Want To Go To New Jersey (Song A Day: Year Six #19, 133 s) | **right**; audio differs | I Don't Wanna Go to New Jersey (Winter, 2014 #18, 102 s) | **right**; audio same file as #1842 |
| 2136 | 2014-11-06 (BC upload +58 d) | bandcamp title fits #2135 | When Things Go Wrong (42 s) | I Am Here For You (Song A Day: Year Six #309, 41 s) | **mislabelled**; title is #2135's ('I am Here for You', 149 s), but the file is this day's length | When Things Go Wrong (Fall, 2014 #37, 41 s) | **right** |
| 2402 | 2015-07-30 (BC upload +110 d) | bandcamp title fits #2401 | You Conquered the Lion (203 s) | And I Make No Sense (Song A Day: Year Seven #213, 202 s) | **mislabelled**; title is #2401's ('And I Make No Sense', 182 s), but the file is this day's length | no link in links.csv |  |
| 2611 | 2016-02-24 (BC upload +313 d) | links.py flags Bandcamp's title as another song's | Lay Your Head Down Low Low Low (168 s) | Lay Me Down Low (Song A Day: Year Eight #55, 168 s) | **mislabelled**; title is #1401's ('Lay Me Down Low', 222 s), but the file is this day's length | Lay Your Head down Low Low Low (Winter, 2016 #55, 168 s) | **right** |
| 3830 | 2019-06-27 (BC upload +2547 d) | bandcamp file: looks like #3831 | Nothing To Worry About (148 s) | Nothing To Worry About (Song A Day: Year Eleven #178, 69 s) | **right**; audio looks like #3831 | Nothing to Worry About (June, 2019 #27, 148 s) | **right** |
| 3832 | 2019-06-29 (BC upload +2545 d) | bandcamp file: looks like #3833 (in a run) | The Action On This Guitar (168 s) | The Action On This Guitar (Song A Day: Year Eleven #180, 174 s) | **right**; audio looks like #3833 (in a run) | The Action on This Guitar (June, 2019 #29, 168 s) | **right** |
| 4276 | 2020-09-15 (BC upload +2102 d) | apple file: looks like #4275 | Anti Mask Rally In St. George Utah (120 s) | Anti Mask Rally In St. George Utah (Song A Day: Year Twelve #259, 121 s) | **right** | Anti Mask Rally in St. George Utah (September, 2020 #15, 134 s) | **right**; audio looks like #4275 |
| 4343 | 2020-11-21 (BC upload +2035 d) | bandcamp file: same file as #4344 | Talkin' American Fascism Blues (139 s) | Talkin' American Fascism Blues (Song A Day: Year Twelve #326, 203 s) | **right**; audio same file as #4344 | Talkin' American Fascism Blues (November, 2020 #20, 141 s) | **right** |
| 4366 | 2020-12-14 (BC upload +2012 d) | bandcamp file: looks like #4367 | North Pole Elves Unite! Unionize! (174 s) | North Pole Elves Unite! Unionize! (Song A Day: Year Twelve #349, 133 s) | **right**; audio looks like #4367 | North Pole Elves Unite! Unionize! (December, 2020 #14, 175 s) | **right** |
| 4367 | 2020-12-15 (BC upload +2011 d) | bandcamp file: same file as #4368 | Thanksgiving Day Parade Recap (132 s) | Thanksgiving Day Parade Recap (Song A Day: Year Twelve #350, 285 s) | **right**; audio same file as #4368 | Thanksgiving Day Parade Recap (December, 2020 #15, 135 s) | **right** |
| 4681 | 2021-10-25 (BC upload +1697 d) | bandcamp file: looks like #4678 | Large Flying Bat Eating A Banana (127 s) | Large Flying Bat Eating A Banana (Song A Day: Year Thirteen #298, 108 s) | **right**; audio looks like #4678 | Large Flying Bat Eating a Banana (October, 2021 #25, 127 s) | **right** |
| 4898 | 2022-05-30 (BC upload +1480 d) | bandcamp file: same file as #4899 | Falling Apart Like Lego Bricks (147 s) | Falling Apart Like Lego Bricks (Song A Day: Year Fourteen #150, 134 s) | **right**; audio same file as #4899 | Falling Apart Like Lego Bricks (May, 2022 #30, 152 s) | **right**; audio differs |
| 5297 | 2023-07-03 (BC upload +1082 d) | bandcamp file: same file as #5294 | NFTs are Dead part 420 (163 s) | NFTs are Dead part 420 (Song A Day: Year Fifteen #184, 99 s) | **right**; audio same file as #5294 | NFTs are Dead part 420 (July, 2023Driving, Driving, Driving, Driving #3, 166 s) | **right**; 'July, 2023Driving, Driving, Driving, Driving' is not a dated album |
| 5356 | 2023-08-31 (BC upload +1023 d) | apple album is outside the date | This Is All That I Got (156 s) | This Is All That I Got (Song A Day: Year Fifteen #243, 156 s) | **right** | This Is All That I Got (September, 2023 #31, 156 s) | **right**; album: 'September, 2023' runs 2023-09-01..2023-09-30; the song is 1 day(s) before it |
| 6089 | 2025-09-02 (BC upload +291 d) | apple file: looks like #6088 | Did My Great Great Great Great Great Great Great Grandfather Feel Like This? (126 s) | Did My Great Great Great Great Great Great Great Grandfather Feel Like This? (Song A Day: Year Seventeen #245, 126 s) | **right** | Did My Great Great Great Great Great Great Great Grandfather Feel Like This? (September, 2025 #2, 139 s) | **right**; audio looks like #6088 |
| 6208 | 2025-12-30 (BC upload +172 d) | bandcamp file: same file as #6209, whose is unclear | Don't Cry (210 s) | Don't Cry (Song A Day: Year Seventeen #364, 133 s) | **right**; audio same file as #6209, whose is unclear | Don't Cry (December, 2025 #29, 183 s) | **right**; audio differs |

## Off-by-one scan (whole table)

Every stored service title in links.csv, compared with the catalog titles of #N-3..#N+3. A hit is a title that fits a neighbour (similarity 0.85+) better than its own song.

| # | Service | Their title | Rated | Own similarity | Fits | Similarity | Live check |
| ---: | --- | --- | --- | ---: | --- | ---: | --- |
| 2136 | bandcamp | I Am Here For You | high | 0.22 | #2135 'I am Here for You' | 1.00 | mislabelled: 'I Am Here For You', 41 s, audio agrees |
| 2390 | bandcamp | Don't Soldier On Blindly | high | 0.23 | #2389 'Don't Soldier on Blindly' | 1.00 | mislabelled: 'Don't Soldier On Blindly', 321 s, audio agrees |
| 2402 | bandcamp | And I Make No Sense | high | 0.29 | #2401 'And I Make No Sense' | 1.00 | mislabelled: 'And I Make No Sense', 202 s, audio agrees |

No runs of consecutive shifted titles on either service.

## Year and season boundaries (whole table)

Links whose dated album doesn't contain the song's date. A title that is the day's song on the neighbouring period's album means the album itself was sequenced across the boundary; that is not a matching error.

| # | Date | Service | Their title | Album | Rated | Note | Live check |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 274 | 2009-10-01 | apple | Downstairs Bear | Summer, 2009 | high | 'Summer, 2009' runs 2009-07-01..2009-09-30; the song is 1 day(s) after it | right: 'Downstairs Bear', 76 s, audio agrees |
| 547 | 2010-07-01 | apple | Bones Come to Life | Spring, 2010 | high | 'Spring, 2010' runs 2010-04-01..2010-06-30; the song is 1 day(s) after it | right: 'Bones Come to Life', 158 s, audio agrees |
| 821 | 2011-04-01 | apple | Alanis-Aurus Rex | Winter, 2011 | high | 'Winter, 2011' runs 2011-01-01..2011-03-31; the song is 1 day(s) after it | right: 'Alanis-Aurus Rex', 64 s, audio agrees |
| 1144 | 2012-02-18 | bandcamp | Go For Pro Anthem 2 | Song A Day: Year Three | high | 'Song A Day: Year Three' is 2011, the song is 2012 | right: 'Go For Pro Anthem 2', 114 s, audio agrees |
| 1827 | 2014-01-01 | apple | Me and Tilley | Fall, 2013 | high | 'Fall, 2013' runs 2013-10-01..2013-12-31; the song is 1 day(s) after it | right: 'Me and Tilley', 160 s, audio agrees with bandcamp, not the video |
| 3103 | 2017-06-30 | apple | I Was on an Airplane Above the Clouds | Summer, 2017 | high | 'Summer, 2017' runs 2017-07-01..2017-09-30; the song is 1 day(s) before it | right: 'I Was on an Airplane Above the Clouds', 89 s, audio agrees |
| 5356 | 2023-08-31 | apple | This Is All That I Got | September, 2023 | high | 'September, 2023' runs 2023-09-01..2023-09-30; the song is 1 day(s) before it | right: 'This Is All That I Got', 156 s, audio agrees |

Apple's album 'July, 2023Driving, Driving, Driving, Driving' (#5295-#5325, 31 links) has a song title stuck to its name, so its period can't be read and its 31 links were left out of this check.

## Files that sound like another day (whole table)

Every stored file length in links.csv, judged the same way as the sampled links: 'same file as #M' (one file under two titles, and it is #M's), 'looks like #M' (more than 10 s and 10% from its own song, within 1.5 s of #M's), or 'in a run' (next to such a file, shifted the same way, within 1.5 s). Counts by rating:

| Service | Rated | Audio | Links |
| --- | --- | --- | ---: |
| apple | check | agrees | 3 |
| apple | check | differs | 4 |
| apple | check | looks like | 8 |
| apple | check | same file as | 4 |
| apple | high | agrees | 5,501 |
| apple | high | agrees with bandcamp, not the video | 461 |
| apple | high | differs | 302 |
| apple | high | looks like | 2 |
| apple | high | same file as | 4 |
| bandcamp | check | looks like | 17 |
| bandcamp | check | same file as | 5 |
| bandcamp | high | agrees | 5,971 |
| bandcamp | high | agrees with apple, not the video | 430 |
| bandcamp | high | differs | 31 |
| bandcamp | high | looks like | 3 |
| bandcamp | high | looks like (in a run) | 1 |
| bandcamp | high | no length | 2 |
| bandcamp | high | same file as | 9 |

The 19 links rated **high** (so in the sheet) whose file looks like another day's; each is opened live under Follow-ups:

- apple #738 'EagleShark Raids the Robot Xombies': 65 s file, video 49 s; same file as #737
- apple #1092 'Made for Another Life': 202 s file, video 295 s; same file as #1093, whose is unclear
- apple #1093 'Piss Like a Racehorse': 202 s file, video 106 s; same file as #1092, whose is unclear
- apple #1845 'I Don't Wanna Go to New Jersey': 102 s file, video 122 s; same file as #1842
- apple #4276 'Anti Mask Rally In St. George Utah': 134 s file, video 120 s; looks like #4275
- apple #6089 'Did My Great Great Great Great Great Great Great Grandfather Feel Like This?': 139 s file, video 126 s; looks like #6088
- bandcamp #738 'EagleShark Raids the Robot Xombies': 65 s file, video 49 s; same file as #737
- bandcamp #1092 'Made for Another Life': 202 s file, video 295 s; same file as #1093, whose is unclear
- bandcamp #1093 'Piss Like a Racehorse': 202 s file, video 106 s; same file as #1092, whose is unclear
- bandcamp #3830 'Nothing To Worry About': 69 s file, video 148 s; looks like #3831
- bandcamp #3832 'The Action On This Guitar': 174 s file, video 168 s; looks like #3833 (in a run)
- bandcamp #4343 'Talkin' American Fascism Blues': 203 s file, video 139 s; same file as #4344
- bandcamp #4366 'North Pole Elves Unite! Unionize!': 133 s file, video 174 s; looks like #4367
- bandcamp #4367 'Thanksgiving Day Parade Recap': 285 s file, video 132 s; same file as #4368
- bandcamp #4681 'Large Flying Bat Eating A Banana': 108 s file, video 127 s; looks like #4678
- bandcamp #4898 'Falling Apart Like Lego Bricks': 134 s file, video 147 s; same file as #4899
- bandcamp #5297 'NFTs are Dead part 420': 99 s file, video 163 s; same file as #5294
- bandcamp #6208 'Don't Cry': 133 s file, video 210 s; same file as #6209, whose is unclear
- bandcamp #6209 'Seventeen Years': 133 s file, video 258 s; same file as #6208, whose is unclear

## One file under two titles (whole table)

Songs 1-3 days apart whose files on the same service are the same length (within 0.05 s) although their catalog Lengths differ by more than 5 s. One of the two titles is playing the other's audio (or both are playing a third file). 'Belongs to' is the song whose file on the other service is that length (when only one is), else the song whose video Length fits (when only one does).

| Service | Songs | File | Catalog Lengths | Belongs to | Rated |
| --- | --- | ---: | --- | --- | --- |
| bandcamp | #737 'EagleShark Eats a Sandwich', #738 'EagleShark Raids the Robot Xombies' | 65.1 s | 65 s, 49 s | #737 | #737 high, #738 high |
| bandcamp | #1092 'Made for Another Life', #1093 'Piss Like a Racehorse' | 201.9 s | 295 s, 106 s | neither | #1092 high, #1093 high |
| bandcamp | #2966 'Who's Gonna Take the Fall?', #2967 'What Did He Know and When Did He Know It?' | 59.9 s | 48 s, 60 s | #2967 | #2966 check, #2967 high |
| bandcamp | #3833 'My LifeIs A Pile of Food Made Out Of Wood', #3834 'Screw The Joneses' | 288.9 s | 175 s, 289 s | #3834 | #3833 check, #3834 high |
| bandcamp | #4343 'Talkin' American Fascism Blues', #4344 'Matthew Brann's Ruling On The Trump Campaign's Effort To Overturn Pennsylvania's Election' | 202.8 s | 139 s, 202 s | #4344 | #4343 high, #4344 high |
| bandcamp | #4367 'Thanksgiving Day Parade Recap', #4368 'The Big Storm' | 284.6 s | 132 s, 284 s | #4368 | #4367 high, #4368 high |
| bandcamp | #4898 'Falling Apart Like Lego Bricks', #4899 'The Lost Dream Song' | 133.8 s | 147 s, 134 s | #4899 | #4898 high, #4899 high |
| bandcamp | #4995 'Sometimes I Don't Feel Like Writing Another Song', #4996 'When I Say I've Got No Time' | 43.6 s | 107 s, 40 s | #4996 | #4995 check, #4996 high |
| bandcamp | #5294 'Onchain vs On-Chain', #5297 'NFTs are Dead part 420' | 98.7 s | 63 s, 163 s | #5294 | #5294 high, #5297 high |
| bandcamp | #5486 'Surprise, Arizona', #5487 'We Are Alone' | 247.6 s | 241 s, 178 s | #5486 | #5486 high, #5487 check |
| bandcamp | #5993 'And Then Go Home', #5994 'How Long Before They Drop A Bomb On Us?' | 151.6 s | 152 s, 175 s | #5993 | #5993 high, #5994 check |
| bandcamp | #6208 'Don't Cry', #6209 'Seventeen Years' | 133.1 s | 210 s, 258 s | neither | #6208 high, #6209 high |
| apple | #737 'EagleShark Eats a Sandwich', #738 'EagleShark Raids the Robot Xombies' | 65.1 s | 65 s, 49 s | #737 | #737 high, #738 high |
| apple | #755 'The Mac vs. PC Conciliatory Song', #756 'Daring Fireball' | 75.2 s | 174 s, 74 s | #756 | #755 check, #756 high |
| apple | #1092 'Made for Another Life', #1093 'Piss Like a Racehorse' | 202.0 s | 295 s, 106 s | neither | #1092 high, #1093 high |
| apple | #1192 'SHOCKED!!!', #1193 'Your Day' | 69.6 s | 69 s, 126 s | #1192 | #1192 high, #1193 check |
| apple | #1500 'Non-Existent Cat', #1501 'George W. Bush's Self Portraits' | 148.6 s | 148 s, 62 s | #1500 | #1500 high, #1501 check |
| apple | #1577 '12 Facts About George Jones', #1579 'When It Rains You Feel It in Your Bones' | 126.6 s | 126 s, 233 s | #1577 | #1577 high, #1579 check |
| apple | #1842 'My Brain is the Blue Screen of Death', #1845 'I Don't Wanna Go to New Jersey' | 102.4 s | 102 s, 122 s | #1842 | #1842 high, #1845 high |

## Weak titles accepted on length (whole table)

71 links are rated high on a weak title (position-only, or fuzzy under 0.85), so they are in the sheet because of their length. That evidence holds when the file is the same master (within 0.5 s) as the other service's title-sure link for the song, or is within 3 s of the song and every song within 3 days has a video Length at least 1 s further away. 70 pass; 1 does not:

| # | Service | Their title | Catalog title | Match | Gap to other service | Gap to catalog | Closest neighbour |
| ---: | --- | --- | --- | --- | ---: | ---: | --- |
| 4541 | apple | Wwdc2021: Okay | WWDC2021 Remix: OKAY | fuzzy 0.812 | 1.5 s | 1.5 s | #4543 at 1.5 s |

## Track URLs used for more than one song (whole table)

None.

## The paste file

`analysis/sheet-backfill-links.csv` has 6502 rows. Each row's date was checked against #1 = 2009-01-01, its title against the catalog, each cell against links.csv (filled only when rated high, and then with that URL), and rows 3 onward of the cached public sheet (`cache/sheet/sheet-gid0.csv`, 5113 song rows) against the paste file's row in the same place.

No problems: pasting from row 3 puts every link on its own song's row.

