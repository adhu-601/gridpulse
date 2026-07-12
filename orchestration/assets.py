"""Software-defined assets for the GridPulse ingestion → warehouse pipeline.

Each asset wraps a stage of the ``gridpulse`` package so the exact same code
runs from the CLI, from pytest, and from the Dagster daemon. Rich
``MaterializeResult`` metadata (row counts, quality-check pass rate) shows up in
the Dagster UI, giving observability into every run.
"""

import pandas as pd
from dagster import (
    AssetExecutionContext,
    AssetSpec,
    MaterializeResult,
    MetadataValue,
    asset,
    multi_asset,
)

from gridpulse import config, geocode, ingest, load, quality, transform
from .dbt_assets import SOURCE_TABLES, warehouse_key


@asset(group_name="ingest", compute_kind="python")
def facility_catalogue(context: AssetExecutionContext) -> pd.DataFrame:
    """Unit-level NEM facility metadata (from the cached API catalogue)."""
    df = ingest.load_facility_catalogue()
    context.add_output_metadata({
        "facilities": int(df["facility_code"].nunique()),
        "unit_rows": len(df),
    })
    return df


@asset(group_name="ingest", compute_kind="python")
def raw_timeseries(context: AssetExecutionContext,
                   facility_catalogue: pd.DataFrame) -> MaterializeResult:
    """Ensure the batched 5-minute payloads are present in the raw cache.

    Fetches from the API only when ``GRIDPULSE_FETCH=1`` and a key is set;
    otherwise it is a no-op that validates the cache exists.
    """
    import os
    fetched = 0
    if os.environ.get("GRIDPULSE_FETCH") == "1":
        fetched = ingest.fetch_timeseries(facility_catalogue)
    batch_files = list(config.RAW_CACHE_DIR.glob(
        f"batch_*__{config.DATE_START:%Y%m%d}_{config.DATE_END:%Y%m%d}.json"))
    return MaterializeResult(metadata={
        "batches_cached": len(batch_files),
        "batches_fetched_this_run": fetched,
    })


@asset(group_name="ingest", compute_kind="pandas", deps=[raw_timeseries])
def consolidated_dataset(context: AssetExecutionContext,
                         facility_catalogue: pd.DataFrame) -> MaterializeResult:
    """Clean, aggregate, geocode and quality-gate the wide consolidated table."""
    long_df = ingest.parse_raw_to_long(facility_catalogue)
    consolidated = transform.consolidate(long_df, facility_catalogue)
    consolidated = geocode.enrich(consolidated)

    report = quality.run_checks(consolidated)
    passed = sum(r.passed for r in report.results)
    if not report.ok:
        failed = [r.name for r in report.results if not r.passed and r.severity == "error"]
        raise ValueError(f"Data-quality gate failed: {failed}")

    transform.write_consolidated(consolidated[config.CONSOLIDATED_COLUMNS])
    return MaterializeResult(metadata={
        "rows": len(consolidated),
        "facilities": int(consolidated["facility_code"].nunique()),
        "quality_checks_passed": f"{passed}/{len(report.results)}",
        "window": f"{config.DATE_START.date()} → {config.DATE_END.date()}",
        "quality_report": MetadataValue.md(report.as_table().to_markdown(index=False)),
    })


@multi_asset(
    specs=[
        AssetSpec(key=warehouse_key(t), deps=[consolidated_dataset, facility_catalogue],
                  group_name="warehouse", kinds={"duckdb"},
                  description=f"{t} table in the DuckDB analytical schema.")
        for t in SOURCE_TABLES
    ],
)
def duckdb_warehouse(context: AssetExecutionContext, facility_catalogue: pd.DataFrame):
    """Load the normalised analytical schema into DuckDB.

    Emits one Dagster asset per source table so the dbt models that read these
    tables run strictly after the warehouse is loaded.
    """
    consolidated = pd.read_csv(config.CONSOLIDATED_CSV)
    market_df = pd.read_csv(config.MARKET_CSV) if config.MARKET_CSV.exists() else None
    summary = load.load_duckdb(consolidated, facility_catalogue, market_df)
    row_map = {
        "FACILITY": summary["facility"],
        "FUEL_TYPE": summary["fuel_type"],
        "FACILITY_POWER_EMISSIONS": summary["facility_power_emissions"],
        "MARKET_PRICE_DEMAND": summary["market_price_demand"],
    }
    for t in SOURCE_TABLES:
        yield MaterializeResult(asset_key=warehouse_key(t), metadata={
            "rows": row_map[t],
            "duckdb_path": str(config.DUCKDB_PATH),
            "spatial_enabled": summary["spatial"],
        })
