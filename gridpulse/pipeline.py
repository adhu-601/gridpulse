"""End-to-end pipeline entrypoint (also usable as a plain CLI).

    python -m gridpulse.pipeline            # full run from cache → DuckDB
    python -m gridpulse.pipeline --fetch    # also hit the API for new batches

The Dagster assets in ``orchestration/`` call these same functions, so the CLI
and the orchestrator never drift apart.
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from . import config, geocode, ingest, load, quality, transform
from .api_client import OpenElectricityClient


def run(fetch: bool = False) -> dict:
    log = logging.getLogger("gridpulse.pipeline")
    config.ensure_dirs()

    client = OpenElectricityClient() if fetch else None
    facilities_df = ingest.load_facility_catalogue(client)
    if fetch:
        ingest.fetch_timeseries(facilities_df, client)

    long_df = ingest.parse_raw_to_long(facilities_df)
    consolidated = transform.consolidate(long_df, facilities_df)
    consolidated = geocode.enrich(consolidated)

    report = quality.assert_all(consolidated)
    log.info("Data-quality gate passed (%d checks)", len(report.results))

    # Persist the consolidated contract (drop enrichment-only helper columns).
    transform.write_consolidated(consolidated[config.CONSOLIDATED_COLUMNS])

    market_df = None
    if config.MARKET_CSV.exists():
        market_df = pd.read_csv(config.MARKET_CSV)

    summary = load.load_duckdb(consolidated, facilities_df, market_df)
    log.info("Pipeline complete: %s", summary)
    return summary


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    ap = argparse.ArgumentParser(description="GridPulse NEM data pipeline")
    ap.add_argument("--fetch", action="store_true",
                    help="fetch new data from the API (needs OPENELECTRICITY_API_KEY)")
    args = ap.parse_args()
    run(fetch=args.fetch)


if __name__ == "__main__":
    main()
