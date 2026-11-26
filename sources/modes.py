"""Estimated major or minor for the songs whose mode was never written down.

For songs #212-#271 and #358-#727 the song spreadsheet gives only the root ("A", "D#"), so
`mode` is "unknown" there (flag mode_not_recorded). This step estimates major or minor from
the recordings and writes dataset/mode_estimates.csv. The estimates stay in their own table:
merge.py doesn't read it, so `mode`, `is_major`, `is_minor` and every test in analysis/
still count only modes Jonathan wrote down.

How
1. Audio: Bandcamp's 128 kbps streams of the matching tracks (dataset/bandcamp.csv), taken
   from the data-tralbum JSON on the Year One, Two and Three album pages. Cached in
   cache/modes/audio/<number>.mp3, one request at a time; nothing is redistributed.
2. Measure (Essentia): a 12-bin pitch-class profile over the whole recording (HPCP, 4096-sample
   frames, peaks 20-3500 Hz), plus Essentia's KeyExtractor with the "bgate" and "edma"
   profiles. Cached in cache/modes/measured.json.
3. Vote, knowing the root from the sheet, so each method only chooses root-major or root-minor:
     thirds     the minor third against the major third above the root
     temperley  correlation with Temperley's minor profile against his major profile
     bgate      Essentia's key, counted only when its root is the sheet's root
     edma       the same with the edma profile
   A song gets an estimate when at least MIN_VOTES methods answer and none disagree;
   otherwise it stays blank.
4. Check (--check): the same vote on CHECK_SONGS from 2009 and 2011 whose mode was written
   down, all the minor ones and 160 major ones. On 2026-11-25 it labeled 80% of the major
   songs (98% of them right) and 55% of the minor ones (95% right). At the catalog's mix
   (about 79% major) a "minor" estimate is then right about 92% of the time and a "major" one
   about 99%. Minor songs are left blank more often than major ones, so don't read the share
   of minor songs in 2010 from the estimates.

Needs Essentia, which isn't in pyproject.toml (it's large and only this step uses it):
    uv run --no-project --with essentia --with requests python sources/modes.py [--check] [--fetch]
Without --fetch it works only from the cache.
"""
import argparse
import csv
import html
import json
import math
import random
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"
CACHE = ROOT / "cache" / "modes"
AUDIO = CACHE / "audio"
MEASURED = CACHE / "measured.json"
OUT = DATASET / "mode_estimates.csv"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
REQUEST_PAUSE = 1.0
ALBUMS = {
    "Song A Day: Year One": "https://jonathanmann.bandcamp.com/album/song-a-day-year-one",
    "Song A Day: Year Two": "https://jonathanmann.bandcamp.com/album/song-a-day-year-two",
    "Song A Day: Year Three": "https://jonathanmann.bandcamp.com/album/song-a-day-year-three",
}
MIN_VOTES = 3
CHECK_SEED, CHECK_MAJORS = 2026, 160
PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
      "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
TEMPERLEY = ([0.748, 0.060, 0.488, 0.082, 0.670, 0.460, 0.096, 0.715, 0.104, 0.366, 0.057, 0.400],
             [0.712, 0.084, 0.474, 0.618, 0.049, 0.460, 0.105, 0.747, 0.404, 0.067, 0.133, 0.330])


def load_songs():
    with open(DATASET / "songaday.csv", encoding="utf-8") as f:
        return {int(r["number"]): r for r in csv.DictReader(f)}


def root_of(row):
    m = re.match(r"^([A-G][#b]?)", (row.get("key") or "").strip())
    return PC.get(m.group(1)) if m else None


def gap_songs(songs):
    return sorted(n for n, r in songs.items() if "mode_not_recorded" in r.get("song_flags", ""))


def check_songs(songs):
    ok = [n for n, r in songs.items() if r["mode"] in ("major", "minor") and (n <= 357 or 731 <= n <= 1095)
          and not {"key_multiple", "key_uncertain"} & set(r.get("song_flags", "").split("|"))]
    minors = [n for n in ok if songs[n]["mode"] == "minor"]
    majors = [n for n in ok if songs[n]["mode"] == "major"]
    return sorted(minors + random.Random(CHECK_SEED).sample(majors, CHECK_MAJORS))


def get(url, binary=False):
    for attempt in range(6):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(int(response.headers.get("Retry-After") or 2 ** (attempt + 1)))
            continue
        response.raise_for_status()
        return response.content if binary else response.text
    raise RuntimeError(f"gave up on {url}")


def fetch_audio(numbers):
    """Download the Bandcamp stream of every song in numbers that isn't cached yet."""
    missing = [n for n in numbers if not (AUDIO / f"{n}.mp3").exists()]
    if not missing:
        return
    with open(DATASET / "bandcamp.csv", encoding="utf-8") as f:
        tracks = {int(r["number"]): r["bandcamp_url"] for r in csv.DictReader(f) if r["bandcamp_url"]}
    streams = {}
    for url in ALBUMS.values():
        page = get(url)
        time.sleep(REQUEST_PAUSE)
        album = json.loads(html.unescape(re.search(r'data-tralbum="([^"]+)"', page).group(1)))
        for t in album["trackinfo"]:
            stream = (t.get("file") or {}).get("mp3-128")
            if stream and t.get("title_link"):
                streams[t["title_link"].split("/track/")[-1]] = stream
    AUDIO.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(missing, 1):
        stream = streams.get(tracks.get(n, "").split("/track/")[-1])
        if not stream:
            continue
        (AUDIO / f"{n}.mp3").write_bytes(get(stream, binary=True))
        time.sleep(REQUEST_PAUSE)
        if i % 50 == 0:
            print(f"  fetched {i} of {len(missing)}")


def measure_one(path):
    import numpy as np
    import essentia
    essentia.log.warningActive = False
    import essentia.standard as es
    audio = es.MonoLoader(filename=str(path), sampleRate=44100)()
    if len(audio) < 44100 * 5:
        return {"error": "shorter than 5 seconds"}
    window, spectrum = es.Windowing(type="blackmanharris62"), es.Spectrum()
    peaks = es.SpectralPeaks(orderBy="magnitude", magnitudeThreshold=1e-05, minFrequency=20,
                             maxFrequency=3500, maxPeaks=60, sampleRate=44100)
    hpcp = es.HPCP(size=12, referenceFrequency=440, harmonics=4, bandPreset=True, minFrequency=20,
                   maxFrequency=3500, weightType="cosine", nonLinear=False, windowSize=1.0, sampleRate=44100)
    total = np.zeros(12)
    for frame in es.FrameGenerator(audio, frameSize=4096, hopSize=2048, startFromZero=True):
        freqs, mags = peaks(spectrum(window(frame)))
        if len(freqs):
            total += hpcp(freqs, mags)
    if total.max() <= 0:
        return {"error": "no pitched sound"}
    total /= total.max()
    chroma = [float(total[(pc + 3) % 12]) for pc in range(12)]  # Essentia's bin 0 is A; make it C
    guesses = {}
    for profile in ("bgate", "edma"):
        key, scale, strength = es.KeyExtractor(profileType=profile, sampleRate=44100)(audio)
        guesses[profile] = [key, scale, float(strength)]
    return {"chroma": chroma, "essentia": guesses}


def measure(numbers):
    done = json.loads(MEASURED.read_text()) if MEASURED.exists() else {}
    todo = [n for n in numbers if str(n) not in done and (AUDIO / f"{n}.mp3").exists()]
    for i, n in enumerate(todo, 1):
        try:
            done[str(n)] = measure_one(AUDIO / f"{n}.mp3")
        except Exception as error:  # a broken download stays blank
            done[str(n)] = {"error": str(error)[:200]}
        if i % 50 == 0:
            MEASURED.write_text(json.dumps(done))
            print(f"  measured {i} of {len(todo)}")
    MEASURED.parent.mkdir(parents=True, exist_ok=True)
    MEASURED.write_text(json.dumps(done))
    return done


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return num / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def votes(m, root):
    """Each method's answer (major or minor), given the root from the sheet."""
    c = [m["chroma"][(root + i) % 12] for i in range(12)]
    out = {
        "thirds": "minor" if c[3] > c[4] else "major",
        "temperley": "minor" if corr(c, TEMPERLEY[1]) > corr(c, TEMPERLEY[0]) else "major",
    }
    for profile in ("bgate", "edma"):
        key, scale, _ = m["essentia"][profile]
        if PC.get(key) == root:
            out[profile] = scale
    return out


def estimate(m, root):
    if root is None or "chroma" not in m:
        return "", {}
    v = votes(m, root)
    answers = set(v.values())
    return (answers.pop() if len(v) >= MIN_VOTES and len(answers) == 1 else ""), v


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fetch", action="store_true", help="download audio that isn't cached")
    parser.add_argument("--check", action="store_true", help="also score the vote on songs whose mode is known")
    args = parser.parse_args()
    songs = load_songs()
    gap = gap_songs(songs)
    check = check_songs(songs) if args.check else []
    if args.fetch:
        fetch_audio(gap + check)
    measured = measure(gap + check)

    rows = []
    for n in gap:
        m = measured.get(str(n), {})
        guess, v = estimate(m, root_of(songs[n]))
        reason = ("no audio" if not m else "audio unreadable" if "chroma" not in m
                  else "" if guess else "methods disagree or too few answered")
        rows.append({"number": n, "key": songs[n]["key"], "mode_estimated": guess,
                     "votes": "|".join(f"{k}:{val}" for k, val in v.items()), "note": reason})
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["number", "key", "mode_estimated", "votes", "note"])
        writer.writeheader()
        writer.writerows(rows)
    labeled = [r for r in rows if r["mode_estimated"]]
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} songs, {len(labeled)} estimated "
          f"({sum(r['mode_estimated'] == 'minor' for r in labeled)} minor), {len(rows) - len(labeled)} left blank")

    if check:
        tally = {"major": [0, 0, 0], "minor": [0, 0, 0]}  # right, labeled, total
        for n in check:
            m = measured.get(str(n), {})
            if "chroma" not in m:
                continue
            guess, _ = estimate(m, root_of(songs[n]))
            t = tally[songs[n]["mode"]]
            t[2] += 1
            if guess:
                t[1] += 1
                t[0] += guess == songs[n]["mode"]
        for mode, (right, labeled_n, total) in tally.items():
            print(f"check, written down as {mode}: {labeled_n} of {total} estimated, {right} of those right")


if __name__ == "__main__":
    main()
