# What the Song A Day data says

67 questions about 6,502 songs (#1, 2009-01-01, to #6502, 2026-10-20), each tested against chance with the confounds held fixed. Made by `analysis/analyze.py` from `dataset/songaday.csv`; every number here is in `findings.json`.

**How to read it.** Each answer compares like with like: songs from the same year and home (and season, or month, when the question needs it), because his tagging, his home, the weather and YouTube all changed over 17 years. *p* is how often shuffled data looks as striking as the real data. *q* is *p* corrected for running 124 tests (Benjamini-Hochberg): with this many tests a few p-values under 0.05 turn up by luck alone, and *q* accounts for that. Verdicts: **real** q < 0.01, **probably real** q < 0.05, **confounded** (the raw pattern exists but is explained by something else), **fun null** (a famous superstition that shows nothing) and **noise**.

## In short

- **Do songs about the day's news get more views?** Real: +124% views against same-month songs (q = 0.0017).
- **Does what a song is about predict its views?** Real: block adds 8.10% of within-month variance; biggest: Apple x4.70 (CI x3.15-x7.01, n=80) (q < 0.0001).
- **Are weekend songs mellower?** Real: 34.2% vs 44.5%, -10.4 points like-for-like (q = 0.0017).
- **Are songs on the road longer or shorter?** Real: 152.2 vs 137.4 s, +17.3 s like-for-like (q = 0.0017).
- **Does the beard get more views?** Real: views against same-month songs (controlled): Beard -3%, Shadow -13%, Clean +24% (q = 0.0017).
- **Does a song's length predict its views?** Real: doubling the length: x1.20 views (95% CI x1.16 to x1.25) at the typical length (q < 0.0001).
- **Does a song's mood predict its views?** Real: block adds 2.61% of within-month variance; biggest: Silly x1.61 (CI x1.46-x1.77, n=970) (q < 0.0001).
- **Are the moods getting darker over time?** Real: +8.4 points per decade (95% CI +4.2 to +12.7) (q = 0.0036).
- **Does the beard change the mood?** Real: biggest departure Clean x Tired: 65 songs vs 106 expected (-38%) (q = 0.0017).
- **Do songs from the road get more views?** Real: -28% views against same-month songs (q = 0.0017).
- **Do full moons make wilder songs?** No: 42.7% vs 41.5%, +1.3 points like-for-like (q = 0.8814).
- **Does Mercury retrograde bring confused, anxious, angry songs?** No: 11.6% vs 10.5%, +0.5 points like-for-like (q = 0.7594).
- **Is Friday the 13th unlucky (darker songs)?** No: 15.6% vs 17.1%, -1.4 points like-for-like (q = 1.0000).
- **Do songs made during Mercury retrograde get fewer views?** No: -6% views against same-month songs (q = 0.6492).
- **Does the phase of the moon change the mood mix?** No: biggest departure waxing gibbous x Happy: 41 songs vs 30 expected (+37%) (q = 0.8814).
- **Is he more often in a minor key when Mercury is retrograde?** No: 20.5% vs 20.8%, +0.3 points like-for-like (q = 0.8966).
- **Do songs from some weekdays get more views?** Confounded: views against same-month songs (controlled): Monday +11%, Tuesday +9%, Wednesday +8%, Thursday +2%, Friday -0%, Saturday -11%, Sunday -16%. Real within the month (q = 0.0017), but it fades once the views model holds topic, mood, length and the rest fixed (q = 0.3192): it is mostly what the songs are about.
- **Does the day's weather (clear, cloudy, rain, snow...) change the mood mix?** Confounded. Without controls: snow x Other: 33 songs vs 18 expected (+79%) (q = 0.0310); compared like with like: snow x Other: 33 songs vs 24 expected (+39%) (q = 0.7741).
- **Are songs faster when the planets are aligned?** Confounded. Without controls: +1.11 bpm per 30 degrees tighter planet bunching (q = 0.0223); compared like with like: -0.40 bpm per 30 degrees tighter planet bunching (q = 0.7610).
- **Busy news days, more minor keys?** Confounded. Without controls: +1.86 points per 10 more headlines (q = 0.0363); compared like with like: +1.18 points per 10 more headlines (q = 0.5105).

## The patterns that are real

### Do songs about the day's news get more views?

**real** · q = 0.0017 · p = 0.0002 · n = 6,451

Median views 947 for 318 songs that clearly name that day's news (match excess >= 1) vs 384 for 6,133 other songs; against songs of the same month that's +124% views (95% CI +95% to +154%).

*q = 0.0017: very unlikely to be chance, even after correcting for every test run.*

- Effect: +124% views (95% CI +95% to +154%), controlled
- Controls: same month of the same year (views grow with a video's age and YouTube era)
- Without controls: +127% views (95% CI +95% to +161%), no controls (raw p = 0.0005, q = 0.0030)
- In the full views model, which also holds topic, mood, length, instrument, genre and the rest fixed: news_song x1.42 (95% CI x1.22 to x1.67) (block p < 0.0001, q = 0.0002).
- Note: A news song names that day's headlines more than it would a year earlier or later. Matching is plain string matching, so it misses songs that allude to the news without naming it.
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: news_matched_by_year: songs and median_rel_views (bar)

### Does what a song is about predict its views?

**real** · q < 0.0001 · p < 0.0001 · n = 6,450

Compared with songs on rarer topics (none of the 30 most common) from the same month (other features held fixed), the biggest differences are Apple x4.70 (CI x3.15-x7.01, n=80); Conference x0.54 (CI x0.43-x0.67, n=88); Object x0.55 (CI x0.44-x0.68, n=52); Commission x0.57 (CI x0.47-x0.70, n=175). Together the topic terms explain 8.10% of the variation in views within a month.

*q < 0.0001: very unlikely to be chance, even after correcting for every test run.*

- Effect: block adds 8.10% of within-month variance; biggest: Apple x4.70 (CI x3.15-x7.01, n=80); Conference x0.54 (CI x0.43-x0.67, n=88); Object x0.55 (CI x0.44-x0.68, n=52); Commission x0.57 (CI x0.47-x0.70, n=175)
- Controls: month of upload (age and YouTube era) and every other feature in the model: topic, mood, length, instrument, genre, traveling, weekday, news song, beard
- Test: OLS on log10 views with month dummies; robust (HC1) Wald chi-square, 30 df
- Chart: views_model: block partial R^2 (bar) and term multipliers with CIs (dot plot)

### Are weekend songs mellower?

**real** · q = 0.0017 · p = 0.0002 · n = 6,502

High-energy moods: 34.2% of 1,858 songs on weekends vs 44.5% of 4,644 on weekdays; compared like with like, -10.4 points (95% CI -13.0 to -7.7).

*q = 0.0017: very unlikely to be chance, even after correcting for every test run.*

- Effect: -10.4 percentage points (95% CI -13.0 to -7.7), controlled
- Controls: same year and home era
- Without controls: -10.4 percentage points (95% CI -13.1 to -7.8), no controls (raw p = 0.0005, q = 0.0030)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: weekday: wild_share by weekday (bar)

### Are songs on the road longer or shorter?

**real** · q = 0.0017 · p = 0.0002 · n = 6,500

Songs while traveling averaged 152.2 s (1,328 songs) vs 137.4 s at home; compared like with like, +17.3 s (95% CI +11.9 to +22.6).

*q = 0.0017: very unlikely to be chance, even after correcting for every test run.*

- Effect: +17.3 s (95% CI +11.9 to +22.6), controlled
- Controls: same year and home era; circular-shift null; length clipped to 30-480 s
- Without controls: +14.8 s (95% CI +9.0 to +20.9), no controls (raw p = 0.0005, q = 0.0030)
- Note: Trips include gigs, conferences and collaborations, which may run long.
- Test: circular-shift test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: travel_summary: median_length (paired bars)

### Does the beard get more views?

**real** · q = 0.0017 · p = 0.0002 · n = 6,406

Beard explains 1.75% of the variation in views (chance alone: about 0.02%). Views against same-month songs (controlled): Beard -3%, Shadow -13%, Clean +24%.

*q = 0.0017: very unlikely to be chance, even after correcting for every test run.*

- Effect: eta^2 = 0.0175 (chance alone gives about 0.0002); views against same-month songs (controlled): Beard -3%, Shadow -13%, Clean +24%
- Controls: same month of the same year (views grow with a video's age and YouTube era); circular-shift null
- Without controls: eta^2 = 0.1425 (chance alone gives about 0.0309); views against the overall mean: Beard -44%, Shadow +6%, Clean +98% (raw p = 0.0005, q = 0.0030)
- In the full views model, which also holds topic, mood, length, instrument, genre and the rest fixed: Shadow x1.14 (95% CI x0.99 to x1.32); Clean x1.44 (95% CI x1.24 to x1.67); Other x0.98 (95% CI x0.69 to x1.40) (block p < 0.0001, q < 0.0001).
- Note: He may shave for special videos (gigs, shoots, commissions), so the beard could be a marker of the occasion rather than a cause. The model check holds topic and mood fixed, but not the occasion.
- Test: circular-shift test of between-group variance, 4999 shuffles
- Chart: beard_summary: median_rel_views by beard (bar)

### Does a song's length predict its views?

**real** · q < 0.0001 · p < 0.0001 · n = 6,450

Against songs of the same month and with topic, mood, instrument and genre held fixed, a song twice as long gets x1.20 the views (95% CI x1.16 to x1.25).

*q < 0.0001: very unlikely to be chance, even after correcting for every test run.*

- Effect: doubling the length: x1.20 views (95% CI x1.16 to x1.25) at the typical length; block adds 1.56% of within-month variance
- Controls: month of upload (age and YouTube era) and every other feature in the model: topic, mood, length, instrument, genre, traveling, weekday, news song, beard
- Note: Longer songs may be the ones with more effort or production, so length may stand in for that.
- Test: OLS on log10 views with month dummies; robust (HC1) Wald chi-square, 2 df
- Chart: views_model: block partial R^2 (bar) and term multipliers with CIs (dot plot)

### Does a song's mood predict its views?

**real** · q < 0.0001 · p < 0.0001 · n = 6,450

Compared with Pensive songs from the same month (other features held fixed), the biggest differences are Silly x1.61 (CI x1.46-x1.77, n=970); Excited x1.44 (CI x1.27-x1.62, n=566); Angry x1.41 (CI x1.23-x1.61, n=374); Happy x1.40 (CI x1.12-x1.74, n=137). Together the mood terms explain 2.61% of the variation in views within a month.

*q < 0.0001: very unlikely to be chance, even after correcting for every test run.*

- Effect: block adds 2.61% of within-month variance; biggest: Silly x1.61 (CI x1.46-x1.77, n=970); Excited x1.44 (CI x1.27-x1.62, n=566); Angry x1.41 (CI x1.23-x1.61, n=374); Happy x1.40 (CI x1.12-x1.74, n=137)
- Controls: month of upload (age and YouTube era) and every other feature in the model: topic, mood, length, instrument, genre, traveling, weekday, news song, beard
- Note: Mood is his own tag; silly songs are often the topical, shareable ones.
- Test: OLS on log10 views with month dummies; robust (HC1) Wald chi-square, 11 df
- Chart: views_model: block partial R^2 (bar) and term multipliers with CIs (dot plot)

### Are the moods getting darker over time?

**real** · q = 0.0036 · p = 0.0006 · n = 6,502

Yearly mean: 12.1% in 2009, 19.5% in 2026; the fitted trend is +8.4 points per decade (95% CI +4.2 to +12.7).

*q = 0.0036: very unlikely to be chance, even after correcting for every test run.*

- Effect: +8.4 points per decade (95% CI +4.2 to +12.7); Kendall tau = +0.57
- Controls: one value per year, so day-to-day autocorrelation can't inflate it; nothing else (this is the raw time trend)
- Note: Moods are his own tags and the vocabulary shifted (Angry and Anxious grew), so part of this may be tagging. Only 18 yearly values.
- Test: Kendall rank test on 18 yearly means; OLS slope with t-based CI
- Chart: mood_by_year: unhappy moods' share (stacked area)

### Does the beard change the mood?

**real** · q = 0.0017 · p = 0.0002 · n = 6,456

Beard vs mood: association V = 0.084, against about 0.036 from chance alone. Biggest departure: Clean x Tired: 65 songs vs 106 expected (-38%).

*q = 0.0017: very unlikely to be chance, even after correcting for every test run.*

- Effect: Cramer's V = 0.084 (chance alone gives about 0.036); biggest cell Clean x Tired: 65 songs vs 106 expected (-38%)
- Controls: same year and home era; circular-shift null (beards last months)
- Without controls: Cramer's V = 0.144 (chance alone gives about 0.089); biggest cell Clean x Silly: 355 songs vs 262 expected (+35%) (raw p = 0.0045, q = 0.0223)
- Note: Beard and mood are both his own tags, usually entered together, so a tagging habit could produce part of this.
- Test: circular-shift chi-square (expected counts within strata), 4999 shuffles
- Chart: beard_summary: mood shares by beard (stacked bars); beard_by_month (timeline)

### Do songs from the road get more views?

**real** · q = 0.0017 · p = 0.0002 · n = 6,451

Median views 406 for 1,318 songs from the road vs 392 for 5,133 from home; against songs of the same month that's -28% views (95% CI -34% to -21%).

*q = 0.0017: very unlikely to be chance, even after correcting for every test run.*

- Effect: -28% views (95% CI -34% to -21%), controlled
- Controls: same month of the same year (views grow with a video's age and YouTube era); circular-shift null
- Without controls: -11% views (95% CI -29% to +28%), no controls (raw p = 0.4765, q = 0.7610)
- In the full views model, which also holds topic, mood, length, instrument, genre and the rest fixed: traveling x0.86 (95% CI x0.80 to x0.93) (block p < 0.0001, q = 0.0009).
- Note: Trips include conferences and events whose songs have their own audience, so this is not 'travel makes better songs'.
- Test: circular-shift test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: travel_summary: median_rel_views (paired bars)

### Did the mood mix change between homes?

**real** · q = 0.0075 · p = 0.0014 · n = 6,502

Home era vs mood: association V = 0.146, against about 0.129 from chance alone. Biggest departure: Berkeley x Happy: 63 songs vs 22 expected (+185%).

*q = 0.0075: very unlikely to be chance, even after correcting for every test run.*

- Effect: Cramer's V = 0.146 (chance alone gives about 0.129); biggest cell Berkeley x Happy: 63 songs vs 22 expected (+185%)
- Controls: none (era is time itself); circular shift of at least a year
- Note: Mood tags drifted over the years (Happy was common in 2009 and rare after 2017), so some of this is tagging, not feeling.
- Test: circular-shift chi-square (expected counts within strata), 4999 shuffles
- Chart: era_summary: mood shares (stacked bars); mood_by_year (stacked area)

### Does the day of the week change the mood mix?

**real** · q = 0.0017 · p = 0.0002 · n = 6,502

Weekday vs mood: association V = 0.058, against about 0.041 from chance alone. Biggest departure: Saturday x Excited: 51 songs vs 82 expected (-38%).

*q = 0.0017: very unlikely to be chance, even after correcting for every test run.*

- Effect: Cramer's V = 0.058 (chance alone gives about 0.041); biggest cell Saturday x Excited: 51 songs vs 82 expected (-38%)
- Controls: same year and home era
- Without controls: Cramer's V = 0.058 (chance alone gives about 0.041); biggest cell Saturday x Excited: 51 songs vs 82 expected (-37%) (raw p = 0.0005, q = 0.0030)
- Note: Seven days by twelve moods spreads the pattern thin; the single biggest cell is shown.
- Test: stratified permutation chi-square (expected counts within strata), 4999 shuffles
- Chart: weekday: mood shares (heatmap)

### When politics fills the news, does he write about politics?

**probably real** · q = 0.0229 · p = 0.0048 · n = 6,502

Per 3 more politics headlines, the share of songs tagged Politics or Trump changes by +1.80 points (95% CI +0.55 to +3.03; overall 9.8%).

*q = 0.0229: unlikely to be chance after correcting for every test run.*

- Effect: +1.80 points per 3 more politics headlines (95% CI +0.55 to +3.03); partial r = +0.036
- Controls: same month of the same year
- Without controls: +1.47 points per 3 more politics headlines (95% CI +0.31 to +2.61); partial r = +0.032 (raw p = 0.0105, q = 0.0434)
- Note: Wikipedia's politics section and his Politics songs both peak on election days, so this is mostly elections.
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: news_by_month: politics_elections vs politics songs (dual line)

### Does the season change the mood mix?

**probably real** · q = 0.0496 · p = 0.0124 · n = 6,502

Season vs mood: association V = 0.064, against about 0.050 from chance alone. Biggest departure: winter x Tired: 80 songs vs 115 expected (-30%).

*q = 0.0496: unlikely to be chance after correcting for every test run.*

- Effect: Cramer's V = 0.064 (chance alone gives about 0.050); biggest cell winter x Tired: 80 songs vs 115 expected (-30%)
- Controls: same year; whole months shuffled within the year
- Without controls: Cramer's V = 0.064 (chance alone gives about 0.050); biggest cell winter x Tired: 80 songs vs 117 expected (-31%) (raw p = 0.0150, q = 0.0581)
- Test: block permutation chi-square (expected counts within strata), 4999 shuffles
- Chart: month_of_year: mood shares by month (stacked area)

### Does traveling change the mood mix?

**probably real** · q = 0.0285 · p = 0.0062 · n = 6,502

Traveling vs mood: association V = 0.068, against about 0.044 from chance alone. Biggest departure: Traveling x Anxious: 33 songs vs 48 expected (-31%).

*q = 0.0285: unlikely to be chance after correcting for every test run.*

- Effect: Cramer's V = 0.068 (chance alone gives about 0.044); biggest cell Traveling x Anxious: 33 songs vs 48 expected (-31%)
- Controls: same year and home era; circular-shift null
- Without controls: Cramer's V = 0.075 (chance alone gives about 0.055); biggest cell Traveling x Angry: 55 songs vs 78 expected (-29%) (raw p = 0.0505, q = 0.1622)
- Test: circular-shift chi-square (expected counts within strata), 4999 shuffles
- Chart: travel_summary: mood shares home vs away (paired bars)

### Does the genre predict views?

**real** · q < 0.0001 · p < 0.0001 · n = 6,450

Compared with Folk songs from the same month (other features held fixed), the biggest differences are Acapella x1.38 (CI x0.71-x2.70, n=51); Rock x1.34 (CI x1.22-x1.47, n=1278); Electro x1.26 (CI x1.12-x1.42, n=1023); Folk Rock x1.21 (CI x1.01-x1.45, n=52). Together the genre terms explain 0.59% of the variation in views within a month.

*q < 0.0001: very unlikely to be chance, even after correcting for every test run.*

- Effect: block adds 0.59% of within-month variance; biggest: Acapella x1.38 (CI x0.71-x2.70, n=51); Rock x1.34 (CI x1.22-x1.47, n=1278); Electro x1.26 (CI x1.12-x1.42, n=1023); Folk Rock x1.21 (CI x1.01-x1.45, n=52)
- Controls: month of upload (age and YouTube era) and every other feature in the model: topic, mood, length, instrument, genre, traveling, weekday, news song, beard
- Test: OLS on log10 views with month dummies; robust (HC1) Wald chi-square, 7 df
- Chart: views_model: block partial R^2 (bar) and term multipliers with CIs (dot plot)

## The funniest nulls

Famous superstitions, tested exactly like everything else. 1 more only look like something until songs are compared like with like, and are under Confounded. The 95% CI says how big an effect could still be hiding.

### Do full moons make wilder songs?

**fun null** · q = 0.8814 · p = 0.7312 · n = 6,502

High-energy moods (Silly, Excited, Intense, Angry, Anxious...): 42.7% of 220 songs on full-moon days vs 41.5% of 6,282 on other days; compared like with like, +1.3 points (95% CI -5.2 to +8.0).

*q = 0.8814: a superstition that shows nothing here.*

- Effect: +1.3 percentage points (95% CI -5.2 to +8.0), controlled
- Controls: same year, season and home era
- Without controls: +1.2 percentage points (95% CI -5.2 to +7.5), no controls (raw p = 0.7255, q = 0.8814)
- Note: The 'lunacy' claim: full moons make people wilder. High-energy moods are the test.
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: moon_phase_summary: wild_share by phase (bar)

### Does Mercury retrograde bring confused, anxious, angry songs?

**fun null** · q = 0.7594 · p = 0.4530 · n = 6,502

Anxious, Confused, Angry or Annoyed moods: 11.6% of 1,243 songs during Mercury retrograde vs 10.5% of 5,259 otherwise; compared like with like, +0.5 points (95% CI -0.8 to +1.9).

*q = 0.7594: a superstition that shows nothing here.*

- Effect: +0.5 percentage points (95% CI -0.8 to +1.9), controlled
- Controls: same year, season and home era; circular-shift null
- Without controls: +1.1 percentage points (95% CI -0.5 to +2.6), no controls (raw p = 0.1975, q = 0.4222)
- Note: Mercury retrograde is said to scramble communication; confused, anxious, angry and annoyed moods are the test.
- Test: circular-shift test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: mercury_summary: chaos_share (paired bars)

### Is Friday the 13th unlucky (darker songs)?

**fun null** · q = 1.0000 · p = 1.0000 · n = 6,502

Unhappy moods: 15.6% of 32 songs on Friday the 13th vs 17.1% of 6,470 on other days; compared like with like, -1.4 points (95% CI -15.7 to +9.4).

*q = 1.0000: a superstition that shows nothing here.*

- Effect: -1.4 percentage points (95% CI -15.7 to +9.4), controlled
- Controls: same year and home era
- Without controls: -1.5 percentage points (95% CI -15.7 to +9.4), no controls (raw p = 1.0000, q = 1.0000)
- Note: Only 32 Friday-the-13ths since 2009, so the CI is wide.
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: friday13: the songs (list)

### Do songs made during Mercury retrograde get fewer views?

**fun null** · q = 0.6492 · p = 0.3560 · n = 6,451

Median views 405 for 1,241 songs made during Mercury retrograde vs 393 for 5,210 otherwise; against songs of the same month that's -6% views (95% CI -17% to +7%).

*q = 0.6492: a superstition that shows nothing here.*

- Effect: -6% views (95% CI -17% to +7%), controlled
- Controls: same month of the same year (views grow with a video's age and YouTube era); circular-shift null
- Without controls: -4% views (95% CI -16% to +8%), no controls (raw p = 0.5485, q = 0.7850)
- Note: Mercury's retrograde periods recur every ~116 days, so a time shift of one cycle partly recreates them; the circular-shift null is cautious.
- Test: circular-shift test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: mercury_summary: median_rel_views (paired bars)

### Does the phase of the moon change the mood mix?

**fun null** · q = 0.8814 · p = 0.7392 · n = 6,502

Moon phase vs mood: association V = 0.038, against about 0.041 from chance alone. Biggest departure: waxing gibbous x Happy: 41 songs vs 30 expected (+37%).

*q = 0.8814: a superstition that shows nothing here.*

- Effect: Cramer's V = 0.038 (chance alone gives about 0.041); biggest cell waxing gibbous x Happy: 41 songs vs 30 expected (+37%)
- Controls: same year, season and home era
- Without controls: Cramer's V = 0.038 (chance alone gives about 0.041); biggest cell waxing gibbous x Happy: 41 songs vs 30 expected (+37%) (raw p = 0.8040, q = 0.8966)
- Test: stratified permutation chi-square (expected counts within strata), 4999 shuffles
- Chart: moon_phase_mood: counts (heatmap, row-normalised)

### Is he more often in a minor key when Mercury is retrograde?

**fun null** · q = 0.8966 · p = 0.7964 · n = 6,059

Minor-key songs: 20.5% of 1,133 songs during Mercury retrograde vs 20.8% of 4,926 otherwise; compared like with like, +0.3 points (95% CI -2.0 to +2.7).

*q = 0.8966: a superstition that shows nothing here.*

- Effect: +0.3 percentage points (95% CI -2.0 to +2.7), controlled
- Controls: same year, season and home era; circular-shift null
- Without controls: -0.3 percentage points (95% CI -2.6 to +2.0), no controls (raw p = 0.8325, q = 0.8966)
- Test: circular-shift test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: mercury_summary: minor_share (paired bars)

### Do supermoons make wilder songs?

**fun null** · q = 0.8966 · p = 0.8152 · n = 6,502

High-energy moods: 44.9% of 69 songs on supermoon days vs 41.5% of 6,433 on other days; compared like with like, +1.9 points (95% CI -10.4 to +13.4).

*q = 0.8966: a superstition that shows nothing here.*

- Effect: +1.9 percentage points (95% CI -10.4 to +13.4), controlled
- Controls: same year, season and home era
- Without controls: +3.4 percentage points (95% CI -7.3 to +14.6), no controls (raw p = 0.6250, q = 0.8333)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: moon_phase_summary (supermoon row)

### Does the Sun's zodiac sign change the mood mix (beyond the season)?

**fun null** · q = 0.1677 · p = 0.0568 · n = 6,502

Sun sign vs mood: association V = 0.044, against about 0.040 from chance alone. Biggest departure: Capricorn x Silly: 52 songs vs 78 expected (-33%).

*q = 0.1677: a superstition that shows nothing here.*

- Effect: Cramer's V = 0.044 (chance alone gives about 0.040); biggest cell Capricorn x Silly: 52 songs vs 78 expected (-33%)
- Controls: same year and astronomical season (each sign only against the other two signs of its season); whole sign periods shuffled
- Without controls: Cramer's V = 0.057 (chance alone gives about 0.054); biggest cell Leo x Intense: 69 songs vs 43 expected (+59%) (raw p = 0.0765, q = 0.2108)
- Note: Sun signs are calendar dates, so the season is held fixed: each sign is compared only with the other two signs of its season.
- Test: block permutation chi-square (expected counts within strata), 4999 shuffles
- Chart: sun_sign_mood: counts (heatmap, row-normalised)

### When the planets bunch up in the sky (a 'planet parade'), are songs wilder?

**fun null** · q = 0.6870 · p = 0.3878 · n = 6,502

Per 30 degrees tighter planet bunching, the share of high-energy moods changes by +0.84 points (95% CI -0.96 to +2.76; overall 41.6%).

*q = 0.6870: a superstition that shows nothing here.*

- Effect: +0.84 points per 30 degrees tighter planet bunching (95% CI -0.96 to +2.76); partial r = +0.010
- Controls: same year, season and home era; circular-shift null
- Without controls: +1.05 points per 30 degrees tighter planet bunching (95% CI -0.25 to +2.48); partial r = +0.034 (raw p = 0.1655, q = 0.3837)
- Test: circular-shift test of a within-stratum slope, 4999 shuffles
- Chart: planet_arc_binned: wild_share by arc bin (line)

### Are eclipse days darker?

**fun null** · q = 0.3405 · p = 0.1318 · n = 6,502

Unhappy moods (Sad, Angry, Anxious, Scared...): 11.1% of 81 songs on eclipse days vs 17.1% of 6,421 on other days; compared like with like, -6.6 points (95% CI -15.2 to +1.3).

*q = 0.3405: a superstition that shows nothing here.*

- Effect: -6.6 percentage points (95% CI -15.2 to +1.3), controlled
- Controls: same year, season and home era
- Without controls: -6.0 percentage points (95% CI -13.8 to +1.3), no controls (raw p = 0.1830, q = 0.3981)
- Note: Eclipse days are when an eclipse was visible somewhere on Earth, not necessarily where he was.
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: eclipses: the eclipse-day songs (list or strip)

### Monday blues: more tired or sad songs on Mondays?

**fun null** · q = 0.8881 · p = 0.7592 · n = 6,502

Tired or Sad moods: 13.9% of 929 songs on Mondays vs 14.3% of 5,573 on other days; compared like with like, -0.4 points (95% CI -2.8 to +2.0).

*q = 0.8881: a superstition that shows nothing here.*

- Effect: -0.4 percentage points (95% CI -2.8 to +2.0), controlled
- Controls: same year and home era
- Without controls: -0.4 percentage points (95% CI -2.8 to +2.1), no controls (raw p = 0.7505, q = 0.8863)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: weekday: tired_or_sad_share by weekday (bar)

### Are full-moon songs more often in a minor key?

**fun null** · q = 0.8623 · p = 0.6606 · n = 6,059

Minor-key songs: 22.0% of 205 songs on full-moon days vs 20.7% of 5,854 on other days; compared like with like, +1.4 points (95% CI -4.5 to +6.6).

*q = 0.8623: a superstition that shows nothing here.*

- Effect: +1.4 percentage points (95% CI -4.5 to +6.6), controlled
- Controls: same year, season and home era; songs with a known mode
- Without controls: +1.3 percentage points (95% CI -4.5 to +6.6), no controls (raw p = 0.6765, q = 0.8629)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: moon_phase_summary: minor_share by phase (bar)

### Does Mercury retrograde change the mood mix?

**fun null** · q = 0.9859 · p = 0.9382 · n = 6,502

Mercury retrograde vs mood: association V = 0.030, against about 0.044 from chance alone. Biggest departure: Retrograde x Other: 40 songs vs 48 expected (-16%).

*q = 0.9859: a superstition that shows nothing here.*

- Effect: Cramer's V = 0.030 (chance alone gives about 0.044); biggest cell Retrograde x Other: 40 songs vs 48 expected (-16%)
- Controls: same year, season and home era; circular-shift null
- Without controls: Cramer's V = 0.036 (chance alone gives about 0.045); biggest cell Retrograde x Other: 40 songs vs 50 expected (-20%) (raw p = 0.8275, q = 0.8966)
- Test: circular-shift chi-square (expected counts within strata), 4999 shuffles
- Chart: mercury_summary: mood shares, retrograde vs direct (paired bars)

### Does the Moon's zodiac sign change the mood mix?

**fun null** · q = 0.1622 · p = 0.0490 · n = 6,502

Moon sign vs mood: association V = 0.045, against about 0.041 from chance alone. Biggest departure: Virgo x Intense: 59 songs vs 41 expected (+46%).

*q = 0.1622: a superstition that shows nothing here.*

- Effect: Cramer's V = 0.045 (chance alone gives about 0.041); biggest cell Virgo x Intense: 59 songs vs 41 expected (+46%)
- Controls: same year, season and home era
- Without controls: Cramer's V = 0.045 (chance alone gives about 0.041); biggest cell Virgo x Intense: 59 songs vs 42 expected (+42%) (raw p = 0.0685, q = 0.1930)
- Test: stratified permutation chi-square (expected counts within strata), 4999 shuffles
- Chart: moon_sign_mood: counts (heatmap)

### Do planetary conjunctions change the mood mix?

**fun null** · q = 0.6116 · p = 0.3206 · n = 6,502

Any planet pair within 5 degrees vs mood: association V = 0.042, against about 0.039 from chance alone. Biggest departure: No conjunction x Chill: 523 songs vs 548 expected (-5%).

*q = 0.6116: a superstition that shows nothing here.*

- Effect: Cramer's V = 0.042 (chance alone gives about 0.039); biggest cell No conjunction x Chill: 523 songs vs 548 expected (-5%)
- Controls: same year, season and home era; circular-shift null
- Without controls: Cramer's V = 0.054 (chance alone gives about 0.063); biggest cell No conjunction x Intense: 211 songs vs 240 expected (-12%) (raw p = 0.6895, q = 0.8636)
- Test: circular-shift chi-square (expected counts within strata), 4999 shuffles
- Chart: conjunction_summary: mood shares by number of pairs (stacked bars)

### Are songs faster when more planets are in conjunction?

**fun null** · q = 0.7610 · p = 0.4718 · n = 6,466

Per 1 more conjunction pair, tempo changes by +0.32 bpm (95% CI -0.53 to +1.14; overall mean 105.8 bpm).

*q = 0.7610: a superstition that shows nothing here.*

- Effect: +0.32 bpm per 1 more conjunction pair (95% CI -0.53 to +1.14); partial r = +0.009
- Controls: same year, season and home era; circular-shift null
- Without controls: +1.31 bpm per 1 more conjunction pair (95% CI -0.09 to +2.66); partial r = +0.046 (raw p = 0.0650, q = 0.1874)
- Test: circular-shift test of a within-stratum slope, 4999 shuffles
- Chart: conjunction_summary: median_tempo by pairs (dot plot)

### The more planets retrograde, the darker the song?

**fun null** · q = 1.0000 · p = 0.9872 · n = 6,502

Per 1 more retrograde planet, the share of unhappy moods changes by -0.02 points (95% CI -2.17 to +2.12; overall 17.1%).

*q = 1.0000: a superstition that shows nothing here.*

- Effect: -0.02 points per 1 more retrograde planet (95% CI -2.17 to +2.12); partial r = -0.000
- Controls: same year, season and home era; circular-shift null
- Without controls: +0.16 points per 1 more retrograde planet (95% CI -1.72 to +1.82); partial r = +0.004 (raw p = 0.8835, q = 0.9364)
- Test: circular-shift test of a within-stratum slope, 4999 shuffles
- Chart: retrograde_summary: dark_share by count (bar)

### Are full-moon songs faster?

**fun null** · q = 0.8966 · p = 0.8388 · n = 6,466

Songs on full-moon days averaged 105.5 bpm (220 songs) vs 105.8 bpm on other days; compared like with like, -0.3 bpm (95% CI -3.5 to +2.8).

*q = 0.8966: a superstition that shows nothing here.*

- Effect: -0.3 bpm (95% CI -3.5 to +2.8), controlled
- Controls: same year, season and home era
- Without controls: -0.3 bpm (95% CI -3.7 to +2.8), no controls (raw p = 0.8350, q = 0.8966)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: moon_phase_summary: median_tempo by phase (dot plot)

### Are full-moon songs longer?

**fun null** · q = 1.0000 · p = 0.9958 · n = 6,500

Songs on full-moon days averaged 140.4 s (220 songs) vs 140.4 s on other days; compared like with like, +0.0 s (95% CI -8.8 to +8.6).

*q = 1.0000: a superstition that shows nothing here.*

- Effect: +0.0 s (95% CI -8.8 to +8.6), controlled
- Controls: same year, season and home era; length clipped to 30-480 s
- Without controls: -0.0 s (95% CI -9.3 to +9.2), no controls (raw p = 0.9980, q = 1.0000)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: moon_phase_summary: median_length by phase (dot plot)

## Confounded: real-looking, but something else explains it

### Do songs from some weekdays get more views?

**confounded** · q = 0.0017 · p = 0.0002 · n = 6,451

Weekday explains 0.82% of the variation in views (chance alone: about 0.10%). Views against same-month songs (controlled): Monday +11%, Tuesday +9%, Wednesday +8%, Thursday +2%, Friday -0%, Saturday -11%, Sunday -16%.

*Real within the month (q = 0.0017), but it fades once the views model holds topic, mood, length and the rest fixed (q = 0.3192): it is mostly what the songs are about.*

- Effect: eta^2 = 0.0082 (chance alone gives about 0.0010); views against same-month songs (controlled): Monday +11%, Tuesday +9%, Wednesday +8%, Thursday +2%, Friday -0%, Saturday -11%, Sunday -16%
- Controls: same month of the same year (views grow with a video's age and YouTube era)
- Without controls: eta^2 = 0.0055 (chance alone gives about 0.0009); views against the overall mean: Monday +11%, Tuesday +9%, Wednesday +8%, Thursday +3%, Friday -0%, Saturday -11%, Sunday -16% (raw p = 0.0005, q = 0.0030)
- In the full views model, which also holds topic, mood, length, instrument, genre and the rest fixed: Tuesday x0.96 (95% CI x0.88 to x1.05); Wednesday x0.94 (95% CI x0.85 to x1.03); Thursday x0.93 (95% CI x0.84 to x1.02); Friday x0.94 (95% CI x0.86 to x1.03); Saturday x0.94 (95% CI x0.87 to x1.03); Sunday x0.88 (95% CI x0.81 to x0.96) (block p = 0.1210, q = 0.3192).
- Note: Views are compared within the month, so this is about the day a song came out, not the era. Weekend songs are also quieter (fewer news songs and high-energy moods, more Poetic and Life), which the model check holds fixed.
- Test: stratified permutation test of between-group variance, 4999 shuffles
- Chart: weekday: median_rel_views by weekday (bar)

### Does the day's weather (clear, cloudy, rain, snow...) change the mood mix?

**confounded** · q = 0.7741 · p = 0.4994 · n = 6,502

Weather vs mood: association V = 0.035, against about 0.035 from chance alone. Biggest departure: snow x Other: 33 songs vs 24 expected (+39%).

*Looks real without controls (q = 0.0310), but not once songs are compared like with like (q = 0.7741).*

- Effect: Cramer's V = 0.035 (chance alone gives about 0.035); biggest cell snow x Other: 33 songs vs 24 expected (+39%)
- Controls: same month of the same year, at home or away separately
- Without controls: Cramer's V = 0.047 (chance alone gives about 0.038); biggest cell snow x Other: 33 songs vs 18 expected (+79%) (raw p = 0.0070, q = 0.0310)
- Test: stratified permutation chi-square (expected counts within strata), 4999 shuffles
- Chart: weather_mood: counts (heatmap, row-normalised)

### Are songs faster when the planets are aligned?

**confounded** · q = 0.7610 · p = 0.4848 · n = 6,466

Per 30 degrees tighter planet bunching, tempo changes by -0.40 bpm (95% CI -1.42 to +0.46; overall mean 105.8 bpm).

*Looks real without controls (q = 0.0223), but not once songs are compared like with like (q = 0.7610).*

- Effect: -0.40 bpm per 30 degrees tighter planet bunching (95% CI -1.42 to +0.46); partial r = -0.010
- Controls: same year, season and home era; circular-shift null
- Without controls: +1.11 bpm per 30 degrees tighter planet bunching (95% CI +0.14 to +2.10); partial r = +0.073 (raw p = 0.0045, q = 0.0223)
- Test: circular-shift test of a within-stratum slope, 4999 shuffles
- Chart: planet_arc_binned: median_tempo by arc bin (line)

### Busy news days, more minor keys?

**confounded** · q = 0.5105 · p = 0.2628 · n = 6,059

Per 10 more headlines, the share of minor-key songs changes by +1.18 points (95% CI -0.87 to +3.28; overall 20.7%).

*Looks real without controls (q = 0.0363), but not once songs are compared like with like (q = 0.5105).*

- Effect: +1.18 points per 10 more headlines (95% CI -0.87 to +3.28); partial r = +0.015
- Controls: same month of the same year
- Without controls: +1.86 points per 10 more headlines (95% CI +0.39 to +3.14); partial r = +0.034 (raw p = 0.0085, q = 0.0363)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: news_intensity_mood (bar)

## Noise

Reasonable questions with no detectable answer.

### Do rainy days make sad songs?

**noise** · q = 0.8966 · p = 0.8082 · n = 6,502

Sad songs: 6.5% of 2,016 songs on days with at least 1 mm of rain or snow vs 7.0% of 4,486 on drier days; compared like with like, -0.2 points (95% CI -1.6 to +1.2).

*q = 0.8966: no detectable effect.*

- Effect: -0.2 percentage points (95% CI -1.6 to +1.2), controlled
- Controls: same month of the same year, at home or away separately
- Without controls: -0.5 percentage points (95% CI -1.9 to +0.8), no controls (raw p = 0.4795, q = 0.7610)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: precip_binned: sad_share by precipitation bin (bar)

### Are songs faster on warm days?

**noise** · q = 0.8416 · p = 0.6380 · n = 6,466

Per 10 C warmer (daily mean), tempo changes by +0.36 bpm (95% CI -1.17 to +1.90; overall mean 105.8 bpm).

*q = 0.8416: no detectable effect.*

- Effect: +0.36 bpm per 10 C warmer (daily mean) (95% CI -1.17 to +1.90); partial r = +0.006
- Controls: same month of the same year, at home or away separately
- Without controls: +0.48 bpm per 10 C warmer (daily mean) (95% CI -0.19 to +1.16); partial r = +0.018 (raw p = 0.1490, q = 0.3771)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: temperature_binned: median_tempo by 5 C bin (line)

### Do sunny days make fewer sad songs?

**noise** · q = 0.7756 · p = 0.5248 · n = 6,502

Per 4 hours more sunshine, the share of Sad songs changes by +0.23 points (95% CI -0.46 to +0.93; overall 6.9%).

*q = 0.7756: no detectable effect.*

- Effect: +0.23 points per 4 hours more sunshine (95% CI -0.46 to +0.93); partial r = +0.008
- Controls: same month of the same year, at home or away separately
- Without controls: -0.10 points per 4 hours more sunshine (95% CI -0.67 to +0.47); partial r = -0.004 (raw p = 0.7275, q = 0.8814)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: weather_mood: sad share by label (bar)

### Busy news days, darker songs?

**noise** · q = 0.8100 · p = 0.5958 · n = 6,502

Per 10 more headlines on Wikipedia's current-events page, the share of unhappy moods changes by +0.48 points (95% CI -1.28 to +2.16; overall 17.1%).

*q = 0.8100: no detectable effect.*

- Effect: +0.48 points per 10 more headlines on Wikipedia's current-events page (95% CI -1.28 to +2.16); partial r = +0.007
- Controls: same month of the same year (the page's coverage changes by year)
- Without controls: -0.25 points per 10 more headlines on Wikipedia's current-events page (95% CI -1.37 to +0.93); partial r = -0.005 (raw p = 0.6770, q = 0.8629)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: news_intensity_mood: dark_share by within-month headline quintile (bar)

### Days with more war and attack headlines, darker songs?

**noise** · q = 0.7610 · p = 0.4800 · n = 6,502

Per 5 more armed-conflict headlines, the share of unhappy moods changes by +0.69 points (95% CI -1.24 to +2.52; overall 17.1%).

*q = 0.7610: no detectable effect.*

- Effect: +0.69 points per 5 more armed-conflict headlines (95% CI -1.24 to +2.52); partial r = +0.009
- Controls: same month of the same year
- Without controls: +0.90 points per 5 more armed-conflict headlines (95% CI -0.59 to +2.31); partial r = +0.015 (raw p = 0.2210, q = 0.4492)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: news_by_month: armed_conflicts vs dark share (dual line)

### Did the minor-key share change between homes?

**noise** · q = 0.1364 · p = 0.0374 · n = 6,059

Home era explains 1.45% of the variation in minor-key songs (chance alone: about 0.58%). Share of minor-key songs: Berkeley 21.5%, Brooklyn 28.7%, Jersey City 14.9%, Hartford 21.7%.

*q = 0.1364: no detectable effect.*

- Effect: eta^2 = 0.0145 (chance alone gives about 0.0058); share of minor-key songs: Berkeley 21.5%, Brooklyn 28.7%, Jersey City 14.9%, Hartford 21.7%
- Controls: none (era is time itself); null cuts the timeline at random points (circular shift of at least a year)
- Note: The era is a stretch of time, so this can't say the move caused it; it says the change is bigger than random cuts of the timeline produce.
- Test: circular-shift test of between-group variance, 4999 shuffles
- Chart: era_summary: minor_share by era (bar); mode_by_year (line)

### Is he writing more minor-key songs over time?

**noise** · q = 0.8100 · p = 0.6009 · n = 6,059

Yearly mean: 19.9% in 2009, 27.7% in 2026; the fitted trend is -3.1 points per decade (95% CI -9.8 to +3.6).

*q = 0.8100: no detectable effect.*

- Effect: -3.1 points per decade (95% CI -9.8 to +3.6); Kendall tau = -0.10
- Controls: one value per year, so day-to-day autocorrelation can't inflate it; nothing else (this is the raw time trend)
- Test: Kendall rank test on 18 yearly means; OLS slope with t-based CI
- Chart: mode_by_year: minor_share (line)

### Has his tempo drifted over the years?

**noise** · q = 0.7006 · p = 0.4012 · n = 6,466

Yearly median: 105 bpm in 2009, 120 bpm in 2026; the fitted trend is +3.7 bpm per decade (95% CI -1.8 to +9.2).

*q = 0.7006: no detectable effect.*

- Effect: +3.7 bpm per decade (95% CI -1.8 to +9.2); Kendall tau = +0.15
- Controls: one value per year, so day-to-day autocorrelation can't inflate it; nothing else (this is the raw time trend)
- Test: Kendall rank test on 18 yearly medians; OLS slope with t-based CI
- Chart: tempo_by_year: median with q1-q3 band (line)

### Are the songs getting longer or shorter?

**noise** · q = 0.8814 · p = 0.7328 · n = 6,500

Yearly median: 111 s in 2009, 135 s in 2026; the fitted trend is +0.8 s per decade (95% CI -11.0 to +12.6).

*q = 0.8814: no detectable effect.*

- Effect: +0.8 s per decade (95% CI -11.0 to +12.6); Kendall tau = +0.06
- Controls: one value per year, so day-to-day autocorrelation can't inflate it; nothing else (this is the raw time trend)
- Test: Kendall rank test on 18 yearly medians; OLS slope with t-based CI
- Chart: length_by_year: median with q1-q3 band (line)

### Seasonal blues: do short days make more sad songs?

**noise** · q = 0.1637 · p = 0.0528 · n = 6,502

Per 3 hours less daylight (monthly mean), the share of Sad songs changes by +1.02 points (95% CI -0.01 to +2.04; overall 6.9%).

*q = 0.1637: no detectable effect.*

- Effect: +1.02 points per 3 hours less daylight (monthly mean) (95% CI -0.01 to +2.04); partial r = +0.026
- Controls: same year; whole months shuffled within the year
- Without controls: +1.00 points per 3 hours less daylight (monthly mean) (95% CI -0.01 to +2.05); partial r = +0.026 (raw p = 0.0560, q = 0.1677)
- Note: Daylight is the season, so even a clear pattern couldn't be told apart from holidays, the school year or the cold.
- Test: month-block permutation test of a within-year slope, 4999 shuffles
- Chart: month_of_year: sad_share vs daylight_h (dual line)

### Do snow days change the mood mix?

**noise** · q = 0.7756 · p = 0.5254 · n = 6,502

Snow day (1 cm or more) vs mood: association V = 0.036, against about 0.038 from chance alone. Biggest departure: Snow day x Sad: 7 songs vs 11 expected (-34%).

*q = 0.7756: no detectable effect.*

- Effect: Cramer's V = 0.036 (chance alone gives about 0.038); biggest cell Snow day x Sad: 7 songs vs 11 expected (-34%)
- Controls: same month of the same year, at home or away separately
- Without controls: Cramer's V = 0.057 (chance alone gives about 0.041); biggest cell Snow day x Intense: 6 songs vs 14 expected (-56%) (raw p = 0.0355, q = 0.1334)
- Test: stratified permutation chi-square (expected counts within strata), 4999 shuffles
- Chart: weather_mood: snow row vs the rest (bars)

### Are weekend songs longer?

**noise** · q = 0.1516 · p = 0.0428 · n = 6,500

Songs on weekends averaged 143.0 s (1,858 songs) vs 139.3 s on weekdays; compared like with like, +3.7 s (95% CI +0.1 to +7.3).

*q = 0.1516: no detectable effect.*

- Effect: +3.7 s (95% CI +0.1 to +7.3), controlled
- Controls: same year and home era; length clipped to 30-480 s
- Without controls: +3.7 s (95% CI +0.0 to +7.3), no controls (raw p = 0.0445, q = 0.1533)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: weekday: median_length by weekday (bar)

### Is he more often minor at home or away?

**noise** · q = 0.3837 · p = 0.1612 · n = 6,059

Minor-key songs: 18.7% of 1,244 songs while traveling vs 21.2% of 4,815 at home; compared like with like, -2.1 points (95% CI -5.1 to +0.8).

*q = 0.3837: no detectable effect.*

- Effect: -2.1 percentage points (95% CI -5.1 to +0.8), controlled
- Controls: same year and home era; circular-shift null (trips last days)
- Without controls: -2.5 percentage points (95% CI -6.6 to +1.1), no controls (raw p = 0.2050, q = 0.4249)
- Test: circular-shift test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: travel_summary: minor_share home vs away by era (paired bars)

### Did his tempo change between homes?

**noise** · q = 0.3837 · p = 0.1702 · n = 6,466

Home era explains 1.81% of the variation in tempo (chance alone: about 1.16%). Tempo (bpm): Berkeley 104.8, Brooklyn 99.5, Jersey City 106.4, Hartford 108.9.

*q = 0.3837: no detectable effect.*

- Effect: eta^2 = 0.0181 (chance alone gives about 0.0116); tempo (bpm): Berkeley 104.8, Brooklyn 99.5, Jersey City 106.4, Hartford 108.9
- Controls: none (era is time itself); circular shift of at least a year
- Test: circular-shift test of between-group variance, 4999 shuffles
- Chart: era_summary: median_tempo (bar); tempo_by_year (line with IQR band)

### Is the bearded Jonathan more minor-key?

**noise** · q = 0.3837 · p = 0.1640 · n = 6,033

Beard explains 0.05% of the variation in minor-key songs (chance alone: about 0.02%). Share of minor-key songs (controlled): Beard 20.6%, Shadow 21.6%, Clean 19.4%.

*q = 0.3837: no detectable effect.*

- Effect: eta^2 = 0.0005 (chance alone gives about 0.0002); share of minor-key songs (controlled): Beard 20.6%, Shadow 21.6%, Clean 19.4%
- Controls: same year and home era; circular-shift null
- Without controls: eta^2 = 0.0020 (chance alone gives about 0.0022); share of minor-key songs: Beard 18.8%, Shadow 22.9%, Clean 20.3% (raw p = 0.3440, q = 0.6376)
- Test: circular-shift test of between-group variance, 4999 shuffles
- Chart: beard_summary: minor_share by beard (bar)

### Does the main instrument predict views?

**noise** · q = 0.3981 · p = 0.1818 · n = 6,450

Compared with Acoustic Guitar songs from the same month (other features held fixed), the biggest differences are Vocals x0.51 (CI x0.25-x1.02, n=46); 4-String Acoustic Guitar x1.13 (CI x0.98-x1.30, n=71); Baritone Ukulele x0.91 (CI x0.82-x1.00, n=691); Ukulele x0.91 (CI x0.80-x1.05, n=156). Together the instrument terms explain 0.17% of the variation in views within a month.

*q = 0.3981: no detectable effect.*

- Effect: block adds 0.17% of within-month variance; biggest: Vocals x0.51 (CI x0.25-x1.02, n=46); 4-String Acoustic Guitar x1.13 (CI x0.98-x1.30, n=71); Baritone Ukulele x0.91 (CI x0.82-x1.00, n=691); Ukulele x0.91 (CI x0.80-x1.05, n=156)
- Controls: month of upload (age and YouTube era) and every other feature in the model: topic, mood, length, instrument, genre, traveling, weekday, news song, beard
- Test: OLS on log10 views with month dummies; robust (HC1) Wald chi-square, 12 df
- Chart: views_model: block partial R^2 (bar) and term multipliers with CIs (dot plot)

### Is he faster in some seasons?

**noise** · q = 0.4249 · p = 0.2056 · n = 6,466

Season explains 0.10% of the variation in tempo (chance alone: about 0.07%). Tempo (bpm) (controlled): winter 104.8, spring 106.9, summer 105.5, fall 106.1.

*q = 0.4249: no detectable effect.*

- Effect: eta^2 = 0.0010 (chance alone gives about 0.0007); tempo (bpm) (controlled): winter 104.8, spring 106.9, summer 105.5, fall 106.1
- Controls: same year; whole months shuffled within the year
- Without controls: eta^2 = 0.0012 (chance alone gives about 0.0007); tempo (bpm): winter 104.7, spring 107.1, summer 105.7, fall 105.8 (raw p = 0.1525, q = 0.3782)
- Test: month-block permutation test of between-group variance, 4999 shuffles
- Chart: month_of_year: median_tempo (line)

### Are rainy-day songs more often minor?

**noise** · q = 0.5105 · p = 0.2586 · n = 6,059

Minor-key songs: 19.5% of 1,932 songs on wet days vs 21.3% of 4,127 on drier days; compared like with like, -1.3 points (95% CI -3.5 to +0.9).

*q = 0.5105: no detectable effect.*

- Effect: -1.3 percentage points (95% CI -3.5 to +0.9), controlled
- Controls: same month of the same year, at home or away separately
- Without controls: -1.8 percentage points (95% CI -4.0 to +0.5), no controls (raw p = 0.1165, q = 0.3140)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: precip_binned: minor_share by bin (bar)

### Are cold days more minor-key?

**noise** · q = 0.7594 · p = 0.4532 · n = 6,059

Per 10 C warmer (daily mean), the share of minor-key songs changes by -1.03 points (95% CI -3.70 to +1.64; overall 20.7%).

*q = 0.7594: no detectable effect.*

- Effect: -1.03 points per 10 C warmer (daily mean) (95% CI -3.70 to +1.64); partial r = -0.010
- Controls: same month of the same year, at home or away separately
- Without controls: -0.63 points per 10 C warmer (daily mean) (95% CI -1.71 to +0.41); partial r = -0.014 (raw p = 0.2635, q = 0.5105)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: temperature_binned: minor_share by bin (line)

### Do short days make more minor-key songs?

**noise** · q = 0.7594 · p = 0.4416 · n = 6,059

Per 3 hours less daylight (monthly mean), the share of minor-key songs changes by -0.70 points (95% CI -2.51 to +1.12; overall 20.7%).

*q = 0.7594: no detectable effect.*

- Effect: -0.70 points per 3 hours less daylight (monthly mean) (95% CI -2.51 to +1.12); partial r = -0.012
- Controls: same year; whole months shuffled within the year
- Without controls: -0.83 points per 3 hours less daylight (monthly mean) (95% CI -2.60 to +1.08); partial r = -0.014 (raw p = 0.3785, q = 0.6802)
- Note: Daylight is the season, so even a clear pattern couldn't be told apart from holidays, the school year or the cold.
- Test: month-block permutation test of a within-year slope, 4999 shuffles
- Chart: month_of_year: minor_share vs daylight_h (dual line)

### Are weekend songs faster or slower?

**noise** · q = 0.7756 · p = 0.5176 · n = 6,466

Songs on weekends averaged 106.1 bpm (1,847 songs) vs 105.7 bpm on weekdays; compared like with like, +0.4 bpm (95% CI -0.8 to +1.7).

*q = 0.7756: no detectable effect.*

- Effect: +0.4 bpm (95% CI -0.8 to +1.7), controlled
- Controls: same year and home era
- Without controls: +0.4 bpm (95% CI -0.9 to +1.7), no controls (raw p = 0.5160, q = 0.7756)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: weekday: median_tempo by weekday (bar)

### Are songs longer on warm (or cold) days?

**noise** · q = 0.7850 · p = 0.5508 · n = 6,500

Per 10 C warmer (daily mean), length changes by +1.32 s (95% CI -3.12 to +5.59; overall mean 140.4 s).

*q = 0.7850: no detectable effect.*

- Effect: +1.32 s per 10 C warmer (daily mean) (95% CI -3.12 to +5.59); partial r = +0.008
- Controls: same month of the same year, at home or away separately; length clipped to 30-480 s
- Without controls: -0.38 s per 10 C warmer (daily mean) (95% CI -2.06 to +1.50); partial r = -0.005 (raw p = 0.6820, q = 0.8629)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: temperature_binned: median_length by 5 C bin (line)

### Are the moods getting wilder over time?

**noise** · q = 0.7850 · p = 0.5498 · n = 6,502

Yearly mean: 46.0% in 2009, 28.7% in 2026; the fitted trend is -1.8 points per decade (95% CI -7.2 to +3.6).

*q = 0.7850: no detectable effect.*

- Effect: -1.8 points per decade (95% CI -7.2 to +3.6); Kendall tau = -0.11
- Controls: one value per year, so day-to-day autocorrelation can't inflate it; nothing else (this is the raw time trend)
- Test: Kendall rank test on 18 yearly means; OLS slope with t-based CI
- Chart: mood_by_year: high-energy moods' share (stacked area)

### Do warm days bring high-energy moods?

**noise** · q = 0.8100 · p = 0.5948 · n = 6,502

Per 10 C warmer (daily mean), the share of high-energy moods changes by -0.89 points (95% CI -4.15 to +2.30; overall 41.6%).

*q = 0.8100: no detectable effect.*

- Effect: -0.89 points per 10 C warmer (daily mean) (95% CI -4.15 to +2.30); partial r = -0.007
- Controls: same month of the same year, at home or away separately
- Without controls: -1.30 points per 10 C warmer (daily mean) (95% CI -2.60 to -0.00); partial r = -0.024 (raw p = 0.0510, q = 0.1622)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: temperature_binned: wild_share by bin (line)

### Are cloudy days more minor-key?

**noise** · q = 0.8100 · p = 0.5968 · n = 6,059

Per 50 percentage points more cloud cover, the share of minor-key songs changes by -0.48 points (95% CI -2.30 to +1.21; overall 20.7%).

*q = 0.8100: no detectable effect.*

- Effect: -0.48 points per 50 percentage points more cloud cover (95% CI -2.30 to +1.21); partial r = -0.007
- Controls: same month of the same year, at home or away separately
- Without controls: -0.84 points per 50 percentage points more cloud cover (95% CI -2.52 to +0.84); partial r = -0.012 (raw p = 0.3445, q = 0.6376)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: weather_mood (bars)

### Days with disasters in the news, sadder songs?

**noise** · q = 0.8100 · p = 0.5802 · n = 6,502

Per 3 more disaster headlines, the share of Sad songs changes by -0.34 points (95% CI -1.56 to +0.85; overall 6.9%).

*q = 0.8100: no detectable effect.*

- Effect: -0.34 points per 3 more disaster headlines (95% CI -1.56 to +0.85); partial r = -0.007
- Controls: same month of the same year
- Without controls: -0.15 points per 3 more disaster headlines (95% CI -1.24 to +0.93); partial r = -0.003 (raw p = 0.7960, q = 0.8966)
- Test: stratified permutation test of a within-stratum slope, 4999 shuffles
- Chart: news_intensity_mood (bar)

### Did his song length change between homes?

**noise** · q = 0.8966 · p = 0.7788 · n = 6,500

Home era explains 0.14% of the variation in length (chance alone: about 0.31%). Length (s): Berkeley 136.1, Brooklyn 144.6, Jersey City 141.1, Hartford 139.6.

*q = 0.8966: no detectable effect.*

- Effect: eta^2 = 0.0014 (chance alone gives about 0.0031); length (s): Berkeley 136.1, Brooklyn 144.6, Jersey City 141.1, Hartford 139.6
- Controls: none (era is time itself); circular shift of at least a year
- Test: circular-shift test of between-group variance, 4999 shuffles
- Chart: era_summary: median_length (bar); length_by_year (line with IQR band)

### Are rainy-day songs slower?

**noise** · q = 1.0000 · p = 0.9788 · n = 6,466

Songs on wet days averaged 106.4 bpm (2,003 songs) vs 105.5 bpm on drier days; compared like with like, +0.0 bpm (95% CI -1.3 to +1.3).

*q = 1.0000: no detectable effect.*

- Effect: +0.0 bpm (95% CI -1.3 to +1.3), controlled
- Controls: same month of the same year, at home or away separately
- Without controls: +0.9 bpm (95% CI -0.5 to +2.1), no controls (raw p = 0.1700, q = 0.3837)
- Test: stratified permutation test of a Mantel-Haenszel-weighted difference, 4999 shuffles
- Chart: precip_binned: median_tempo by bin (dot plot)

## What predicts views

A regression of log views on every feature at once, with a dummy for each month so songs only compete with songs of the same age (6,450 songs with a normal upload). The month alone explains 34.8% of the variation in log views (29.8% out of sample); adding topic, mood, length, instrument, genre, travel, weekday, news and beard brings it to 51.2% (45.9% out of sample). Home era alone explains 22.3% and calendar year alone 28.3%: the era differences in views are mostly the age of the video and YouTube's own history, so era isn't tested separately.

| Block | Adds (share of within-month variance) | Wald p | q |
| --- | --- | --- | --- |
| topic | 8.10% | <0.0001 | <0.0001 |
| mood | 2.61% | <0.0001 | <0.0001 |
| length | 1.56% | <0.0001 | <0.0001 |
| beard | 0.75% | <0.0001 | <0.0001 |
| genre | 0.59% | <0.0001 | <0.0001 |
| news_song | 0.44% | <0.0001 | 0.0002 |
| instrument | 0.17% | 0.1818 | 0.3981 |
| traveling | 0.17% | <0.0001 | 0.0009 |
| weekday | 0.10% | 0.1210 | 0.3192 |

Topics, as a views multiplier against same-month songs on rarer topics (none of these 30), with mood, length, instrument and the rest held fixed (95% CI):

| Topic | Songs | Multiplier | 95% CI |
| --- | --- | --- | --- |
| Apple | 80 | x4.70 | x3.15 to x7.01 |
| Pop Culture | 53 | x1.49 | x1.06 to x2.11 |
| TV | 70 | x1.44 | x1.00 to x2.09 |
| Trump | 100 | x1.42 | x1.08 to x1.88 |
| Politics | 530 | x1.26 | x1.10 to x1.45 |
| Internet | 148 | x1.12 | x0.92 to x1.36 |
| Podcast | 58 | x1.08 | x0.75 to x1.56 |
| Science | 58 | x1.07 | x0.76 to x1.50 |
| Video Games | 110 | x1.04 | x0.82 to x1.32 |
| Contest | 48 | x1.00 | x0.71 to x1.43 |
| Food | 55 | x1.00 | x0.70 to x1.43 |
| Twitter | 57 | x0.95 | x0.71 to x1.28 |
| Animals | 251 | x0.91 | x0.75 to x1.10 |
| Epiphany | 42 | x0.86 | x0.63 to x1.18 |
| Sick | 101 | x0.84 | x0.70 to x0.99 |
| Nerd | 120 | x0.76 | x0.62 to x0.92 |
| Ethereum | 130 | x0.76 | x0.64 to x0.89 |
| Crypto | 100 | x0.76 | x0.62 to x0.91 |
| Song A Day | 183 | x0.71 | x0.60 to x0.83 |
| Friend | 88 | x0.68 | x0.56 to x0.83 |
| Life | 727 | x0.68 | x0.61 to x0.76 |
| Apocalypse | 54 | x0.67 | x0.55 to x0.81 |
| NFTs | 145 | x0.66 | x0.56 to x0.78 |
| Jupiter | 88 | x0.62 | x0.52 to x0.73 |
| Love | 101 | x0.60 | x0.50 to x0.72 |
| Weather | 65 | x0.58 | x0.48 to x0.72 |
| Poetic | 1791 | x0.58 | x0.53 to x0.64 |
| Commission | 175 | x0.57 | x0.47 to x0.70 |
| Object | 52 | x0.55 | x0.44 to x0.68 |
| Conference | 88 | x0.54 | x0.43 to x0.67 |

## Every test

| Verdict | Question | Effect | n | p | q |
| --- | --- | --- | --- | --- | --- |
| real | Does what a song is about predict its views? | block adds 8.10% of within-month variance | 6,450 | <0.0001 | <0.0001 |
| real | Does a song's mood predict its views? | block adds 2.61% of within-month variance | 6,450 | <0.0001 | <0.0001 |
| real | Does a song's length predict its views? | doubling the length: x1.20 views (95% CI x1.16 to x1.25) at the typical length | 6,450 | <0.0001 | <0.0001 |
| real | Does the genre predict views? | block adds 0.59% of within-month variance | 6,450 | <0.0001 | <0.0001 |
| real | Are weekend songs mellower? | -10.4 percentage points (95% CI -13.0 to -7.7), controlled | 6,502 | 0.0002 | 0.0017 |
| real | Does the day of the week change the mood mix? | Cramer's V = 0.058 (chance alone gives about 0.041) | 6,502 | 0.0002 | 0.0017 |
| real | Are songs on the road longer or shorter? | +17.3 s (95% CI +11.9 to +22.6), controlled | 6,500 | 0.0002 | 0.0017 |
| real | Do songs from the road get more views? | -28% views (95% CI -34% to -21%), controlled | 6,451 | 0.0002 | 0.0017 |
| real | Does the beard change the mood? | Cramer's V = 0.084 (chance alone gives about 0.036) | 6,456 | 0.0002 | 0.0017 |
| real | Does the beard get more views? | eta^2 = 0.0175 (chance alone gives about 0.0002) | 6,406 | 0.0002 | 0.0017 |
| real | Do songs about the day's news get more views? | +124% views (95% CI +95% to +154%), controlled | 6,451 | 0.0002 | 0.0017 |
| real | Are the moods getting darker over time? | +8.4 points per decade (95% CI +4.2 to +12.7) | 6,502 | 0.0006 | 0.0036 |
| real | Did the mood mix change between homes? | Cramer's V = 0.146 (chance alone gives about 0.129) | 6,502 | 0.0014 | 0.0075 |
| probably real | When politics fills the news, does he write about politics? | +1.80 points per 3 more politics headlines (95% CI +0.55 to +3.03) | 6,502 | 0.0048 | 0.0229 |
| probably real | Does traveling change the mood mix? | Cramer's V = 0.068 (chance alone gives about 0.044) | 6,502 | 0.0062 | 0.0285 |
| probably real | Does the season change the mood mix? | Cramer's V = 0.064 (chance alone gives about 0.050) | 6,502 | 0.0124 | 0.0496 |
| confounded | Do songs from some weekdays get more views? | eta^2 = 0.0082 (chance alone gives about 0.0010) | 6,451 | 0.0002 | 0.0017 |
| confounded | Busy news days, more minor keys? | +1.18 points per 10 more headlines (95% CI -0.87 to +3.28) | 6,059 | 0.2628 | 0.5105 |
| confounded | Are songs faster when the planets are aligned? | -0.40 bpm per 30 degrees tighter planet bunching (95% CI -1.42 to +0.46) | 6,466 | 0.4848 | 0.7610 |
| confounded | Does the day's weather (clear, cloudy, rain, snow...) change the mood mix? | Cramer's V = 0.035 (chance alone gives about 0.035) | 6,502 | 0.4994 | 0.7741 |
| fun null | Does the Moon's zodiac sign change the mood mix? | Cramer's V = 0.045 (chance alone gives about 0.041) | 6,502 | 0.0490 | 0.1622 |
| fun null | Does the Sun's zodiac sign change the mood mix (beyond the season)? | Cramer's V = 0.044 (chance alone gives about 0.040) | 6,502 | 0.0568 | 0.1677 |
| fun null | Are eclipse days darker? | -6.6 percentage points (95% CI -15.2 to +1.3), controlled | 6,502 | 0.1318 | 0.3405 |
| fun null | Do planetary conjunctions change the mood mix? | Cramer's V = 0.042 (chance alone gives about 0.039) | 6,502 | 0.3206 | 0.6116 |
| fun null | Do songs made during Mercury retrograde get fewer views? | -6% views (95% CI -17% to +7%), controlled | 6,451 | 0.3560 | 0.6492 |
| fun null | When the planets bunch up in the sky (a 'planet parade'), are songs wilder? | +0.84 points per 30 degrees tighter planet bunching (95% CI -0.96 to +2.76) | 6,502 | 0.3878 | 0.6870 |
| fun null | Does Mercury retrograde bring confused, anxious, angry songs? | +0.5 percentage points (95% CI -0.8 to +1.9), controlled | 6,502 | 0.4530 | 0.7594 |
| fun null | Are songs faster when more planets are in conjunction? | +0.32 bpm per 1 more conjunction pair (95% CI -0.53 to +1.14) | 6,466 | 0.4718 | 0.7610 |
| fun null | Are full-moon songs more often in a minor key? | +1.4 percentage points (95% CI -4.5 to +6.6), controlled | 6,059 | 0.6606 | 0.8623 |
| fun null | Do full moons make wilder songs? | +1.3 percentage points (95% CI -5.2 to +8.0), controlled | 6,502 | 0.7312 | 0.8814 |
| fun null | Does the phase of the moon change the mood mix? | Cramer's V = 0.038 (chance alone gives about 0.041) | 6,502 | 0.7392 | 0.8814 |
| fun null | Monday blues: more tired or sad songs on Mondays? | -0.4 percentage points (95% CI -2.8 to +2.0), controlled | 6,502 | 0.7592 | 0.8881 |
| fun null | Are full-moon songs faster? | -0.3 bpm (95% CI -3.5 to +2.8), controlled | 6,466 | 0.8388 | 0.8966 |
| fun null | Do supermoons make wilder songs? | +1.9 percentage points (95% CI -10.4 to +13.4), controlled | 6,502 | 0.8152 | 0.8966 |
| fun null | Is he more often in a minor key when Mercury is retrograde? | +0.3 percentage points (95% CI -2.0 to +2.7), controlled | 6,059 | 0.7964 | 0.8966 |
| fun null | Does Mercury retrograde change the mood mix? | Cramer's V = 0.030 (chance alone gives about 0.044) | 6,502 | 0.9382 | 0.9859 |
| fun null | Are full-moon songs longer? | +0.0 s (95% CI -8.8 to +8.6), controlled | 6,500 | 0.9958 | 1.0000 |
| fun null | The more planets retrograde, the darker the song? | -0.02 points per 1 more retrograde planet (95% CI -2.17 to +2.12) | 6,502 | 0.9872 | 1.0000 |
| fun null | Is Friday the 13th unlucky (darker songs)? | -1.4 percentage points (95% CI -15.7 to +9.4), controlled | 6,502 | 1.0000 | 1.0000 |
| noise | Did the minor-key share change between homes? | eta^2 = 0.0145 (chance alone gives about 0.0058) | 6,059 | 0.0374 | 0.1364 |
| noise | Are weekend songs longer? | +3.7 s (95% CI +0.1 to +7.3), controlled | 6,500 | 0.0428 | 0.1516 |
| noise | Seasonal blues: do short days make more sad songs? | +1.02 points per 3 hours less daylight (monthly mean) (95% CI -0.01 to +2.04) | 6,502 | 0.0528 | 0.1637 |
| noise | Is he more often minor at home or away? | -2.1 percentage points (95% CI -5.1 to +0.8), controlled | 6,059 | 0.1612 | 0.3837 |
| noise | Did his tempo change between homes? | eta^2 = 0.0181 (chance alone gives about 0.0116) | 6,466 | 0.1702 | 0.3837 |
| noise | Is the bearded Jonathan more minor-key? | eta^2 = 0.0005 (chance alone gives about 0.0002) | 6,033 | 0.1640 | 0.3837 |
| noise | Does the main instrument predict views? | block adds 0.17% of within-month variance | 6,450 | 0.1818 | 0.3981 |
| noise | Is he faster in some seasons? | eta^2 = 0.0010 (chance alone gives about 0.0007) | 6,466 | 0.2056 | 0.4249 |
| noise | Are rainy-day songs more often minor? | -1.3 percentage points (95% CI -3.5 to +0.9), controlled | 6,059 | 0.2586 | 0.5105 |
| noise | Has his tempo drifted over the years? | +3.7 bpm per decade (95% CI -1.8 to +9.2) | 6,466 | 0.4012 | 0.7006 |
| noise | Are cold days more minor-key? | -1.03 points per 10 C warmer (daily mean) (95% CI -3.70 to +1.64) | 6,059 | 0.4532 | 0.7594 |
| noise | Do short days make more minor-key songs? | -0.70 points per 3 hours less daylight (monthly mean) (95% CI -2.51 to +1.12) | 6,059 | 0.4416 | 0.7594 |
| noise | Days with more war and attack headlines, darker songs? | +0.69 points per 5 more armed-conflict headlines (95% CI -1.24 to +2.52) | 6,502 | 0.4800 | 0.7610 |
| noise | Do snow days change the mood mix? | Cramer's V = 0.036 (chance alone gives about 0.038) | 6,502 | 0.5254 | 0.7756 |
| noise | Do sunny days make fewer sad songs? | +0.23 points per 4 hours more sunshine (95% CI -0.46 to +0.93) | 6,502 | 0.5248 | 0.7756 |
| noise | Are weekend songs faster or slower? | +0.4 bpm (95% CI -0.8 to +1.7), controlled | 6,466 | 0.5176 | 0.7756 |
| noise | Are songs longer on warm (or cold) days? | +1.32 s per 10 C warmer (daily mean) (95% CI -3.12 to +5.59) | 6,500 | 0.5508 | 0.7850 |
| noise | Are the moods getting wilder over time? | -1.8 points per decade (95% CI -7.2 to +3.6) | 6,502 | 0.5498 | 0.7850 |
| noise | Do warm days bring high-energy moods? | -0.89 points per 10 C warmer (daily mean) (95% CI -4.15 to +2.30) | 6,502 | 0.5948 | 0.8100 |
| noise | Are cloudy days more minor-key? | -0.48 points per 50 percentage points more cloud cover (95% CI -2.30 to +1.21) | 6,059 | 0.5968 | 0.8100 |
| noise | Busy news days, darker songs? | +0.48 points per 10 more headlines on Wikipedia's current-events page (95% CI -1.28 to +2.16) | 6,502 | 0.5958 | 0.8100 |
| noise | Days with disasters in the news, sadder songs? | -0.34 points per 3 more disaster headlines (95% CI -1.56 to +0.85) | 6,502 | 0.5802 | 0.8100 |
| noise | Is he writing more minor-key songs over time? | -3.1 points per decade (95% CI -9.8 to +3.6) | 6,059 | 0.6009 | 0.8100 |
| noise | Are songs faster on warm days? | +0.36 bpm per 10 C warmer (daily mean) (95% CI -1.17 to +1.90) | 6,466 | 0.6380 | 0.8416 |
| noise | Are the songs getting longer or shorter? | +0.8 s per decade (95% CI -11.0 to +12.6) | 6,500 | 0.7328 | 0.8814 |
| noise | Do rainy days make sad songs? | -0.2 percentage points (95% CI -1.6 to +1.2), controlled | 6,502 | 0.8082 | 0.8966 |
| noise | Did his song length change between homes? | eta^2 = 0.0014 (chance alone gives about 0.0031) | 6,500 | 0.7788 | 0.8966 |
| noise | Are rainy-day songs slower? | +0.0 bpm (95% CI -1.3 to +1.3), controlled | 6,466 | 0.9788 | 1.0000 |

## Method

- **Shuffling.** Each controlled test shuffles the exposure 4,999 times within strata (songs of the same year and home era, plus season for the sky, or the same month of the same year for weather, views and news). For exposures that come in long runs (Mercury retrograde, planet positions, trips, beard, home era) the exposure is instead rotated in time by a random offset (a circular shift), which keeps the runs and any day-to-day resemblance between songs. Seasons, daylight and sun signs are shuffled as whole months or whole sign periods within a year.
- **Effects.** Differences are Mantel-Haenszel-weighted averages of within-stratum differences; slopes are fitted after removing each stratum's mean; mood mixes use a chi-square against within-stratum expected counts, summarised as Cramer's V next to the V that chance alone produces. 95% CIs invert the shuffle test: the estimate minus the 97.5th and 2.5th percentiles of the shuffled statistics.
- **Moods.** The 11 moods with 100+ songs are kept and the rest pooled as Other. High-energy: Amazed, Angry, Anxious, Dizzy, Drunk, Excited, Funky, Horny, Intense, Motivational, Scared, Scary, Silly, Wild. Unhappy: Angry, Annoyed, Anxious, Disgusted, Embarrassed, In Pain, Sad, Scared, Scary, Sick, Upset.
- **Views.** log10(views + 1), only for videos that are up, were uploaded within 30 days of the song and have been online 30+ days, compared within the month of upload.
- **Lengths** are clipped to 30 s - 8 min in tests so a few very long songs don't swing the means. Minor-key tests use only songs with a known mode.
- **Views model check.** The weekday, travel, news-song and beard views tests are run again as blocks of the views regression, which also holds topic, mood, length, instrument and genre fixed. A views pattern that fades there (q >= 0.05) is labelled confounded: it is mostly what the songs are about.
- **Multiple testing.** q-values are Benjamini-Hochberg over all 124 p-values the script computes: the controlled tests, their uncontrolled versions, the trends and the views model's blocks.
- **Trends** use one value per year (Kendall's test), because 6,500 neighbouring songs are not independent. Home-era tests treat the era as a stretch of time and compare it with eras cut at random points.
- **Caveats.** Mood, beard, key and tempo are Jonathan's own tags and the way he tagged drifted. Sky values are a 17:00 New York snapshot wherever he was. Weather is a reanalysis grid cell, not the room. News coverage on Wikipedia's Portal changes by year. Tests that find nothing don't prove there's nothing; the CI says how big an effect could hide.

