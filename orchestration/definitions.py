"""Dagster entrypoint — `dagster dev -m orchestration.definitions`.

Wires the ingestion assets and the dbt asset graph together, exposes a
full-refresh job, and schedules it daily. The DuckDB path is pinned to an
absolute location so the Dagster daemon, dbt, and the dashboard all read and
write the same warehouse regardless of the working directory.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from dagster import (
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource

# Pin the warehouse path before anything imports gridpulse.config / dbt.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("GRIDPULSE_DUCKDB", str(_PROJECT_ROOT / "data" / "electricity_a2.duckdb"))

from . import assets as gp_assets                     # noqa: E402
from .dbt_assets import dbt_project, gridpulse_dbt_models  # noqa: E402


def _dbt_executable() -> str:
    """Locate dbt: prefer the same venv as the running interpreter, else PATH."""
    candidate = Path(sys.executable).parent / "dbt.exe"
    if candidate.exists():
        return str(candidate)
    return shutil.which("dbt") or "dbt"

# Full pipeline: ingest → warehouse → dbt models + tests.
full_refresh_job = define_asset_job(
    name="full_refresh",
    selection=AssetSelection.all(),
    description="Rebuild the NEM warehouse and all dbt marts end-to-end.",
)

daily_schedule = ScheduleDefinition(
    job=full_refresh_job,
    cron_schedule="0 6 * * *",          # 06:00 daily
    name="daily_full_refresh",
)

defs = Definitions(
    assets=[
        gp_assets.facility_catalogue,
        gp_assets.raw_timeseries,
        gp_assets.consolidated_dataset,
        gp_assets.duckdb_warehouse,
        gridpulse_dbt_models,
    ],
    jobs=[full_refresh_job],
    schedules=[daily_schedule],
    resources={
        "dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=_dbt_executable()),
    },
)
