# applemac.pk Price Tracker

Tracks MacBook Pro 14"/16", MacBook Air 13"/15" and current iPhone prices
from applemac.pk. Produces a ranked Excel workbook and a dashboard.

Runs daily via GitHub Actions; results publish to GitHub Pages.

## Local use

    pip install -r requirements.txt
    python -m scraper.cli run      # scrape, update history, rebuild outputs
    python -m scraper.cli serve    # dashboard at http://127.0.0.1:8000

Windows: double-click `run.bat`.

## Data

- `data/history.csv` — append-only price snapshots (canonical)
- `data/products.csv` — product identity and specs
- `data/apple_msrp.json` — Apple US MSRPs you maintain by hand

The SQLite database and Excel workbook under `web/downloads/` are
regenerated every run. Full history lives in git.

## Caveats

`Est. Apple Landed` is an estimate (US MSRP x live FX x duty %), not an
official or actual landed cost. Listed price does not guarantee stock.

## License

MIT. See `LICENSE`.
