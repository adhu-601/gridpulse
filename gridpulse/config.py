"""Central configuration: paths, API settings, and the ingest window.

Every value can be overridden with an environment variable so the same code
runs unchanged locally, in CI, and inside the Dagster daemon. Nothing here
performs I/O beyond resolving paths, so importing this module is always cheap
and side-effect free.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
# Project root = parent of this package directory. Anchoring on the file (rather
# than the CWD) means the pipeline works regardless of where it is launched.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GRIDPULSE_DATA_DIR", PROJECT_ROOT / "data"))
RAW_CACHE_DIR = DATA_DIR / "raw_openelectricity"
OUTPUT_DIR = DATA_DIR / "output"

CONSOLIDATED_CSV = DATA_DIR / "consolidated_facility_5min.csv"
MARKET_CSV = DATA_DIR / "market_price_demand_5min.csv"
FACILITIES_JSON = RAW_CACHE_DIR / "facilities.json"
DUCKDB_PATH = Path(os.environ.get("GRIDPULSE_DUCKDB", DATA_DIR / "electricity_a2.duckdb"))

# --------------------------------------------------------------------------- #
# OpenElectricity API
# --------------------------------------------------------------------------- #
# The pipeline runs fully offline from the cached raw JSON in RAW_CACHE_DIR, so
# a real key is only needed to pull a *new* window of data.
API_KEY = os.environ.get("OPENELECTRICITY_API_KEY", "")
API_BASE = os.environ.get("OPENELECTRICITY_API_BASE", "https://api.openelectricity.org.au/v4")

NETWORK_CODE = "NEM"          # NEM covers QLD, NSW, VIC, SA, TAS
INTERVAL = "5m"              # 5-minute dispatch interval
METRICS = ["power", "emissions"]
BATCH_SIZE = 25              # ~25 facility codes per request keeps us < 30/call
DAILY_BUDGET = 480          # free-tier allowance is 500 requests/day

# Analysis window. Defaults to the committed 7-day sample, but both ends can
# be overridden (ISO dates, e.g. GRIDPULSE_DATE_START=2026-01-01) to ingest a
# longer history — the fetcher splits long ranges into API-sized chunks.
def _env_date(name: str, default: datetime) -> datetime:
    raw = os.environ.get(name)
    if not raw:
        return default
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


DATE_END = _env_date("GRIDPULSE_DATE_END", datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc))
DATE_START = _env_date("GRIDPULSE_DATE_START", DATE_END - timedelta(days=7))

# The API caps a 5-minute request at 8 days, so long ranges are fetched in
# 7-day windows. Each window costs ~22 requests (541 facilities / 25 per
# batch), so the 480/day budget covers roughly 20 weeks of history per day.
MAX_WINDOW_DAYS = 7


def fetch_windows() -> list[tuple[datetime, datetime]]:
    """Split [DATE_START, DATE_END) into API-sized windows (<= 7 days each)."""
    windows, start = [], DATE_START
    while start < DATE_END:
        end = min(start + timedelta(days=MAX_WINDOW_DAYS), DATE_END)
        windows.append((start, end))
        start = end
    return windows

# --------------------------------------------------------------------------- #
# MQTT streaming layer (Task 3 / dashboard replay)
# --------------------------------------------------------------------------- #
MQTT_HOST = os.environ.get("GRIDPULSE_MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.environ.get("GRIDPULSE_MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("GRIDPULSE_MQTT_TOPIC", "comp5339/group156/electricity")

# --------------------------------------------------------------------------- #
# Consolidated wide-table contract (single source of truth for downstream)
# --------------------------------------------------------------------------- #
CONSOLIDATED_COLUMNS = [
    "interval_ts", "facility_code", "facility_name", "network_region",
    "fueltech_id", "capacity_registered_mw", "lat", "lon",
    "power_mw", "emissions_tco2e",
]

# NEM regions used for validation / accepted-values tests.
NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]


def ensure_dirs() -> None:
    """Create the on-disk cache layout. Safe to call repeatedly."""
    for d in (DATA_DIR, RAW_CACHE_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
