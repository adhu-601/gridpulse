"""Stage 2 — Cleaning, unit-aggregation and consolidation.

Turns the long-format observations into the analysis-ready wide table
(``consolidated_facility_5min.csv``): timestamps normalised to UTC and trimmed
to the window, metrics standardised, generating units summed to facility level,
metrics pivoted wide, and facility metadata joined on.
"""

from __future__ import annotations

import logging

import pandas as pd

from . import config

log = logging.getLogger("gridpulse.transform")

_METRIC_MAP = {
    "power": "power_mw", "power_mw": "power_mw",
    "emissions": "emissions_tco2e", "emissions_tco2e": "emissions_tco2e",
    "co2_emissions": "emissions_tco2e",
}


def _mode_or_none(s: pd.Series):
    s = s.dropna()
    return s.mode().iat[0] if not s.empty else None


def consolidate(long_df: pd.DataFrame, facilities_df: pd.DataFrame) -> pd.DataFrame:
    """Clean + aggregate + pivot + enrich into the wide consolidated table."""
    if long_df.empty:
        log.warning("long_df is empty — returning empty consolidated frame")
        return pd.DataFrame(columns=config.CONSOLIDATED_COLUMNS)

    df = long_df.copy()

    # 1. timestamps → UTC, strict trim to the window
    df["interval_ts"] = pd.to_datetime(df["interval_ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["interval_ts"])
    df = df[(df["interval_ts"] >= pd.Timestamp(config.DATE_START)) &
            (df["interval_ts"] < pd.Timestamp(config.DATE_END))]

    # 2. numeric coercion, drop blanks
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value", "metric", "facility_code"])

    # 3. standardise metric names
    df["metric_std"] = df["metric"].str.lower().map(_METRIC_MAP).fillna(df["metric"])
    df = df[df["metric_std"].isin(["power_mw", "emissions_tco2e"])]

    # 4. sum units → facility level (power and emissions are both additive)
    agg = (df.groupby(["interval_ts", "facility_code", "metric_std"], as_index=False)
             ["value"].sum(min_count=1))

    # 5. pivot metrics wide
    wide = agg.pivot_table(index=["interval_ts", "facility_code"],
                           columns="metric_std", values="value", aggfunc="sum").reset_index()
    wide.columns.name = None
    for col in ("power_mw", "emissions_tco2e"):
        if col not in wide.columns:
            wide[col] = pd.NA
    wide = wide.dropna(subset=["power_mw", "emissions_tco2e"], how="all")

    # 6. enrich with facility metadata (units rolled up)
    fac_meta = (facilities_df.groupby("facility_code", as_index=False).agg(
        facility_name=("facility_name", "first"),
        network_region=("network_region", "first"),
        lat=("lat", "first"),
        lon=("lon", "first"),
        fueltech_id=("fueltech_id", _mode_or_none),
        capacity_registered_mw=("capacity_registered_mw", "sum"),
    ))
    consolidated = (wide.merge(fac_meta, on="facility_code", how="left")
                    [config.CONSOLIDATED_COLUMNS]
                    .sort_values(["interval_ts", "facility_code"])
                    .reset_index(drop=True))

    log.info("Consolidated %s rows | %d facilities | %s → %s",
             f"{len(consolidated):,}", consolidated["facility_code"].nunique(),
             consolidated["interval_ts"].min(), consolidated["interval_ts"].max())
    return consolidated


def write_consolidated(consolidated: pd.DataFrame) -> None:
    config.ensure_dirs()
    consolidated.to_csv(config.CONSOLIDATED_CSV, index=False)
    log.info("Wrote %s (%.2f MB, %s rows)", config.CONSOLIDATED_CSV,
             config.CONSOLIDATED_CSV.stat().st_size / 1e6, f"{len(consolidated):,}")
