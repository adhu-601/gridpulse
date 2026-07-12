"""Stage 1 — Ingestion.

Materialises the OpenElectricity API into an immutable on-disk cache:

* ``facilities.json``  — the facility/unit metadata catalogue.
* ``batch_NNN__*.json`` — batched 5-minute power/emissions payloads.

Every raw response is written to disk *before* parsing, and a cache check at
the top of each batch makes re-runs a no-op. Downstream stages read only from
this cache, so the upstream API is touched at most once per data window no
matter how often the pipeline is replayed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from . import config
from .api_client import OpenElectricityClient

log = logging.getLogger("gridpulse.ingest")


# --------------------------------------------------------------------------- #
# Facility metadata catalogue
# --------------------------------------------------------------------------- #
def load_facility_catalogue(client: OpenElectricityClient | None = None) -> pd.DataFrame:
    """Return a *unit-level* facility catalogue, fetching only if uncached.

    One row per generating unit, carrying the parent facility attributes
    (name, region, lat/lon) plus unit attributes (fueltech, status, capacity).
    """
    config.ensure_dirs()
    if config.FACILITIES_JSON.exists():
        log.info("Loading facility catalogue from cache: %s", config.FACILITIES_JSON.name)
        raw = json.loads(config.FACILITIES_JSON.read_text(encoding="utf-8"))
    else:
        client = client or OpenElectricityClient()
        log.info("Fetching NEM facility catalogue from API…")
        raw = client.list_facilities(network_id=config.NETWORK_CODE)
        config.FACILITIES_JSON.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    records = []
    for fac in raw.get("data", []):
        fcode = fac.get("code") or fac.get("facility_code")
        if not fcode:
            continue
        loc = fac.get("location") or {}
        base = {
            "facility_code": fcode,
            "facility_name": fac.get("name"),
            "network_id": fac.get("network_id") or config.NETWORK_CODE,
            "network_region": fac.get("network_region"),
            "lat": loc.get("lat") or loc.get("latitude"),
            "lon": loc.get("lng") or loc.get("longitude") or loc.get("lon"),
        }
        for u in (fac.get("units") or [{}]):
            records.append({
                **base,
                "unit_code": u.get("code"),
                "fueltech_id": u.get("fueltech_id"),
                "status_id": u.get("status_id"),
                "capacity_registered_mw": u.get("capacity_registered"),
                "dispatch_type": u.get("dispatch_type"),
            })

    df = pd.DataFrame.from_records(records)
    log.info("Facility catalogue: %d facilities (%d unit rows)",
             df["facility_code"].nunique(), len(df))
    return df


def operating_facility_codes(facilities_df: pd.DataFrame) -> list[str]:
    """Facility codes worth requesting a stream for (operating / unknown)."""
    operating = facilities_df.loc[
        facilities_df["status_id"].fillna("").str.lower().isin({"operating", ""})
    ]
    return sorted(operating["facility_code"].dropna().unique().tolist())


# --------------------------------------------------------------------------- #
# Batched time-series retrieval (writes raw cache)
# --------------------------------------------------------------------------- #
def _batch_cache_path(batch_idx: int, w_start=None, w_end=None) -> Path:
    w_start = w_start or config.DATE_START
    w_end = w_end or config.DATE_END
    return config.RAW_CACHE_DIR / (
        f"batch_{batch_idx:03d}__{w_start:%Y%m%d}_{w_end:%Y%m%d}.json"
    )


def fetch_timeseries(facilities_df: pd.DataFrame,
                     client: OpenElectricityClient | None = None) -> int:
    """Fetch any missing batches into the raw cache. Returns #batches fetched.

    Long date ranges (see ``config.fetch_windows``) are fetched one API-sized
    window at a time; each (window, batch) pair is cached under its own file,
    so interrupted runs — e.g. when the daily request budget runs out —
    resume exactly where they stopped.
    """
    config.ensure_dirs()
    codes = operating_facility_codes(facilities_df)
    plan = [(i // config.BATCH_SIZE, codes[i:i + config.BATCH_SIZE])
            for i in range(0, len(codes), config.BATCH_SIZE)]
    windows = config.fetch_windows()
    to_fetch = [(ws, we, i, b)
                for ws, we in windows for (i, b) in plan
                if not _batch_cache_path(i, ws, we).exists()]

    log.info("Windows: %d | batches: %d total | %d cached | %d to fetch",
             len(windows), len(windows) * len(plan),
             len(windows) * len(plan) - len(to_fetch), len(to_fetch))
    if not to_fetch:
        return 0

    client = client or OpenElectricityClient()
    fetched = 0
    for w_start, w_end, batch_idx, batch in to_fetch:
        try:
            payload = client.facilities_timeseries(
                config.NETWORK_CODE, batch, config.METRICS,
                config.INTERVAL, w_start, w_end,
            )
            _batch_cache_path(batch_idx, w_start, w_end).write_text(
                json.dumps(payload), encoding="utf-8")
            fetched += 1
        except Exception as e:                          # noqa: BLE001
            log.error("window %s batch %d failed: %s",
                      f"{w_start:%Y%m%d}", batch_idx, e)
    log.info("Fetched %d batches this run (requests used: %s)",
             fetched, getattr(client, "requests_made", "?"))
    return fetched


# --------------------------------------------------------------------------- #
# Parse cached batches → long format
# --------------------------------------------------------------------------- #
def _yield_rows(payload: dict):
    """Yield (ts, unit_code, metric, value) tuples from one batch payload."""
    for block in payload.get("data", []) or []:
        metric = block.get("metric")
        for res in block.get("results", []) or []:
            cols = res.get("columns") or {}
            ucode = cols.get("unit_code") or cols.get("unit")
            if not ucode:                               # fall back to name, e.g. "power_BW01"
                nm = res.get("name", "") or ""
                if "_" in nm:
                    ucode = nm.split("_", 1)[1]
            for point in res.get("data", []) or []:
                if not point or len(point) < 2 or point[1] is None:
                    continue
                yield point[0], ucode, metric, point[1]


def parse_raw_to_long(facilities_df: pd.DataFrame) -> pd.DataFrame:
    """Walk the cached batch files into a long-format observation table."""
    unit_to_facility = (
        facilities_df.dropna(subset=["unit_code", "facility_code"])
                     .drop_duplicates("unit_code")
                     .set_index("unit_code")["facility_code"].to_dict()
    )
    batch_files = []
    for w_start, w_end in config.fetch_windows():
        batch_files.extend(sorted(config.RAW_CACHE_DIR.glob(
            f"batch_*__{w_start:%Y%m%d}_{w_end:%Y%m%d}.json")))
    log.info("Parsing %d batch files", len(batch_files))

    rows, unmapped = [], set()
    for cp in batch_files:
        payload = json.loads(cp.read_text(encoding="utf-8"))
        for ts, ucode, metric, val in _yield_rows(payload):
            if not ucode:
                continue
            fcode = unit_to_facility.get(ucode)
            if not fcode:
                unmapped.add(ucode)
                continue
            rows.append({"interval_ts": ts, "facility_code": fcode,
                         "unit_code": ucode, "metric": metric, "value": val})

    long_df = pd.DataFrame.from_records(rows)
    log.info("Parsed %s raw observations across %s facilities",
             f"{len(long_df):,}",
             long_df["facility_code"].nunique() if not long_df.empty else 0)
    if unmapped:
        log.warning("%d unit codes had no facility match (e.g. %s)",
                    len(unmapped), sorted(unmapped)[:5])
    return long_df
