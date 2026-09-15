"""Static configuration. Pure data, no logic."""
from pathlib import Path

BASE_URL = "https://applemac.pk"
USER_AGENT = (
    "applemac-price-tracker/1.0 "
    "(personal price tracker; contact via repository issues)"
)
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

NULL_PLACEHOLDER = "\u2022"  # the site's "no value" marker

FAMILIES = ("macbook_pro", "macbook_air", "iphone")

CATEGORIES = {
    "macbook-pro-14": "macbook_pro",
    "macbook-pro-16": "macbook_pro",
    "macbook-air-13": "macbook_air",
    "macbook-air-15": "macbook_air",
    "iphone-16": "iphone",
    "iphone-16-plus": "iphone",
    "iphone-16-pro": "iphone",
    "iphone-16-pro-max": "iphone",
    "iphone-16e": "iphone",
    "iphone-17": "iphone",
    "iphone-17-pro": "iphone",
    "iphone-17-pro-max": "iphone",
    "iphone-17e": "iphone",
    "iphone-18-pro": "iphone",
    "iphone-18-pro-max": "iphone",
    "iphone-air-series": "iphone",
    "iphone": "iphone",  # catch-all; contributes only slugs the leaves missed
}

# Deal-score weights. Must sum to 1.0.
WEIGHTS = {
    "vs_apple": 0.30,
    "vs_history": 0.25,
    "vs_peers": 0.20,
    "spec_value": 0.15,
    "site_discount": 0.10,
}

DUTY_PERCENT = 0.55  # tune until Est. Apple Landed matches observed reality
HISTORY_WINDOW_DAYS = 90
COUNT_DROP_ABORT_THRESHOLD = 0.20  # abort if a category shrinks >20%

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
BUILD_DIR = ROOT / "build"
FIXTURE_DIR = ROOT / "tests" / "fixtures"
