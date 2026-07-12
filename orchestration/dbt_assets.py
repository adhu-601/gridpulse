"""dbt models exposed as Dagster assets via dagster-dbt.

The whole dbt DAG (staging views + mart tables + tests) becomes first-class
Dagster assets, so lineage runs continuously from the raw API cache through the
DuckDB warehouse into the marts the dashboard reads. All dbt *sources* are
mapped onto the single upstream ``duckdb_warehouse`` Python asset, so a full
run materialises ingest → warehouse → dbt in the correct order.
"""

from pathlib import Path

from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import (
    DagsterDbtTranslator,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)

DBT_PROJECT_DIR = Path(__file__).resolve().parent.parent / "dbt"

# The four DuckDB tables the pipeline loads and dbt reads as sources. Kept in
# one place so the Python warehouse asset and the dbt translator agree on keys.
SOURCE_TABLES = ["FACILITY", "FUEL_TYPE", "FACILITY_POWER_EMISSIONS", "MARKET_PRICE_DEMAND"]


def warehouse_key(table: str) -> AssetKey:
    return AssetKey(["warehouse", table])

dbt_project = DbtProject(
    project_dir=DBT_PROJECT_DIR,
    profiles_dir=DBT_PROJECT_DIR,
)
# Only (re)generate the manifest when it is missing. Regenerating on every
# `dagster dev` boot runs `dbt parse`, which can exceed the code-server load
# timeout; the manifest is already produced by `dbt build`/`dbt deps`.
if not dbt_project.manifest_path.exists():
    dbt_project.prepare_if_dev()


class GridpulseDbtTranslator(DagsterDbtTranslator):
    """Map each dbt source onto the matching ``warehouse/<TABLE>`` asset the
    Python pipeline materialises, so dbt models run after the warehouse load."""

    def get_asset_key(self, dbt_resource_props):
        if dbt_resource_props["resource_type"] == "source":
            return warehouse_key(dbt_resource_props["name"])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=GridpulseDbtTranslator(),
)
def gridpulse_dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
    """Run `dbt build` (models + tests) and stream results into Dagster."""
    yield from dbt.cli(["build"], context=context).stream()
