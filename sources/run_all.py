"""Run the whole pipeline in order: songs, places, weather, sky, views, news, then merge.

By default a step whose cache is already there runs offline, from the cache only, so a rerun
makes no web requests and gives the same tables. A step with nothing cached yet goes online
and downloads what it needs (see sources/README.md for what each one fetches and how long
that takes). places.py and sky.py have no offline switch: they only go online for what isn't
cached (a new Location string; NASA's eclipse pages).

Run from the repo root:
  .venv/bin/python sources/run_all.py                  every step, offline where cached
  .venv/bin/python sources/run_all.py --fetch          let every step fetch what's new or
                                                       missing (new songs, new days)
  .venv/bin/python sources/run_all.py --only weather,merge
  .venv/bin/python sources/run_all.py --from views     that step and the ones after it
  .venv/bin/python sources/run_all.py --allow-gaps     passed on to merge.py

It stops at the first step that fails and exits with that step's code.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"

# Each step: name, script, the cache files or folders it needs to run offline, and the flag
# that makes it run offline (None when the script has no such switch).
STEPS = [
    ("songs", "songs.py",
     ["cache/sheet/htmlview.html", "cache/sheet/sheet.xlsx", "cache/sheet/sheet-gid0.csv"],
     "--offline"),
    ("places", "places.py", ["cache/places/geocode"], None),
    ("weather", "weather.py", ["cache/weather"], "--offline"),
    ("sky", "sky.py", ["cache/sky/SE2001-2100.html", "cache/sky/LE2001-2100.html"], None),
    ("views", "views.py", ["cache/views/youtube", "cache/views/fan-ratings"], "--offline"),
    ("news", "news.py", ["cache/news/daily"], "--offline"),
    ("merge", "merge.py", [], None),
]
NAMES = [name for name, _, _, _ in STEPS]


def cached(paths):
    """True when every cache path exists, and every cache folder has something in it."""
    for relative in paths:
        path = ROOT / relative
        if not path.exists():
            return False
        if path.is_dir() and not any(path.iterdir()):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fetch", action="store_true",
                        help="don't force offline: let each step fetch what's new or missing")
    parser.add_argument("--only", help=f"comma-separated steps to run, from: {', '.join(NAMES)}")
    parser.add_argument("--from", dest="start", choices=NAMES, help="start at this step")
    parser.add_argument("--allow-gaps", action="store_true",
                        help="let merge.py write the table when a source is behind the song list")
    args = parser.parse_args()

    chosen = NAMES
    if args.only:
        chosen = [name.strip() for name in args.only.split(",") if name.strip()]
        unknown = [name for name in chosen if name not in NAMES]
        if unknown:
            parser.error(f"unknown step(s) {unknown}; choose from {NAMES}")
    if args.start:
        chosen = [name for name in chosen if NAMES.index(name) >= NAMES.index(args.start)]

    started = time.time()
    for name, script, cache, offline_flag in STEPS:
        if name not in chosen:
            continue
        command = [sys.executable, str(SOURCES / script)]
        if offline_flag and cached(cache) and not args.fetch:
            command.append(offline_flag)
            mode = "offline (cache found)"
        elif not cache:
            mode = "local"
        elif cached(cache):
            mode = "fetching only what's new" if args.fetch else "cache found; fetches only what's missing"
        else:
            mode = "ONLINE: nothing cached yet, downloading"
        if name == "merge" and args.allow_gaps:
            command.append("--allow-gaps")

        print(f"\n=== {name}: {' '.join([f'sources/{script}'] + command[2:])}  [{mode}]", flush=True)
        step_started = time.time()
        result = subprocess.run(command, cwd=ROOT)
        print(f"=== {name}: exit {result.returncode} after {time.time() - step_started:.0f} s", flush=True)
        if result.returncode != 0:
            print(f"\nStopped: {name} failed. Fix it, then rerun with --from {name}.", file=sys.stderr)
            sys.exit(result.returncode)

    print(f"\nAll done: {', '.join(chosen)} in {time.time() - started:.0f} s.")


if __name__ == "__main__":
    main()
