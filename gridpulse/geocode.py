"""Stage 2b — Geocoding & spatial enrichment.

The OpenElectricity catalogue ships a lat/lon for most facilities, but not all,
and the coordinates are not validated. This stage:

1. Derives each facility's ``state`` from its NEM ``network_region``.
2. Validates coordinates fall inside the Australian bounding box; coordinates
   outside it are treated as missing.
3. Backfills any missing coordinate with its NEM-region centroid so every
   facility is mappable (a deterministic, offline fallback — no network call).

The region centroids double as the ``geom`` seed for the DuckDB spatial column.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger("gridpulse.geocode")

# NEM region → (state code, representative centroid lat/lon).
REGION_TO_STATE = {
    "NSW1": "NSW", "QLD1": "QLD", "VIC1": "VIC", "SA1": "SA", "TAS1": "TAS",
}
REGION_CENTROID = {
    "NSW1": (-32.16, 147.02), "QLD1": (-22.58, 144.43), "VIC1": (-36.85, 144.28),
    "SA1": (-34.29, 135.71), "TAS1": (-42.02, 146.60),
}

# Generous mainland + Tasmania bounding box.
AUS_LAT_MIN, AUS_LAT_MAX = -44.0, -9.0
AUS_LON_MIN, AUS_LON_MAX = 112.0, 154.5


def _in_australia(lat, lon) -> bool:
    try:
        return (AUS_LAT_MIN <= float(lat) <= AUS_LAT_MAX
                and AUS_LON_MIN <= float(lon) <= AUS_LON_MAX)
    except (TypeError, ValueError):
        return False


def enrich(consolidated: pd.DataFrame) -> pd.DataFrame:
    """Add ``state`` and backfill invalid/missing coordinates. Returns a copy."""
    if consolidated.empty:
        out = consolidated.copy()
        out["state"] = pd.Series(dtype="object")
        out["geocode_source"] = pd.Series(dtype="object")
        return out

    df = consolidated.copy()
    df["state"] = df["network_region"].map(REGION_TO_STATE)

    valid = df.apply(lambda r: _in_australia(r["lat"], r["lon"]), axis=1)
    df["geocode_source"] = valid.map({True: "api", False: "region_centroid"})

    n_backfilled = int((~valid).sum())
    if n_backfilled:
        cent = df.loc[~valid, "network_region"].map(REGION_CENTROID)
        df.loc[~valid, "lat"] = [c[0] if isinstance(c, tuple) else None for c in cent]
        df.loc[~valid, "lon"] = [c[1] if isinstance(c, tuple) else None for c in cent]
        log.info("Backfilled %d facility-interval coordinates from region centroids",
                 n_backfilled)

    n_facilities = df.loc[df["geocode_source"] == "region_centroid", "facility_code"].nunique()
    log.info("Geocoding: %d facilities mapped from API coords, %d backfilled",
             df.loc[df["geocode_source"] == "api", "facility_code"].nunique(), n_facilities)
    return df
