# Song A Day Data

Every Song A Day song as data. Jonathan Mann has written a song every day since January 1,
2009. This project cleans his song spreadsheet, adds what was happening around each song (the
weather where it was recorded, the moon, the planets, the news, how many people watched it),
and looks for patterns, including the weird ones.

**Live:** not yet. The plan is a data page on [songaday.studio](https://songaday.studio).

## What's here

- `sources/` — scripts that fetch or compute each kind of data
- `dataset/` — the cleaned, merged result, one row per song (generated, committed)
- `analysis/` — the correlation tests and their results
- `cache/` — raw downloads, so nothing is fetched twice (ignored by Git)

## Run it locally

Needs Python 3.11 or newer.

```bash
python3.12 -m venv .venv   # any Python 3.11 or newer
.venv/bin/pip install -e .
cp .env.example .env   # optional; see the comments in it
```

The pipeline's steps and their order are in `sources/README.md` once they exist.

## License

Code: [MIT](LICENSE). The song data is Jonathan Mann's, CC BY 4.0. Outside data keeps its own
license; see [ASSETS.md](ASSETS.md).

Made by [Jonathan Mann](https://jonathanmann.net) (Song A Day).
