"""GridPulse — an end-to-end data-engineering pipeline for the Australian NEM.

Retrieves 5-minute facility-level power and emissions data from the
OpenElectricity v4 API, cleans and consolidates it, geocodes each facility,
loads a normalised analytical schema into DuckDB, and exposes dbt marts that
power a live dashboard.

The package is deliberately import-light at the top level so that individual
stages (ingest / transform / geocode / load / quality) can be invoked
independently by the Dagster orchestration layer or from the CLI.
"""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["config"]
