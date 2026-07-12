"""Unit tests for the cleaning/consolidation logic.

These run on tiny synthetic frames (no network, no cache), so they are fast and
deterministic — the kind of tests that guard the transform contract in CI.
"""

import pandas as pd
import pytest

from gridpulse import config, transform


@pytest.fixture
def facilities():
    return pd.DataFrame([
        {"facility_code": "AAA", "facility_name": "Alpha", "network_region": "NSW1",
         "lat": -33.0, "lon": 151.0, "unit_code": "AAA1", "fueltech_id": "coal_black",
         "status_id": "operating", "capacity_registered_mw": 500.0},
        {"facility_code": "AAA", "facility_name": "Alpha", "network_region": "NSW1",
         "lat": -33.0, "lon": 151.0, "unit_code": "AAA2", "fueltech_id": "coal_black",
         "status_id": "operating", "capacity_registered_mw": 500.0},
        {"facility_code": "BBB", "facility_name": "Beta", "network_region": "SA1",
         "lat": -34.9, "lon": 138.6, "unit_code": "BBB1", "fueltech_id": "wind",
         "status_id": "operating", "capacity_registered_mw": 200.0},
    ])


def _obs(ts, facility, unit, metric, value):
    return {"interval_ts": ts, "facility_code": facility, "unit_code": unit,
            "metric": metric, "value": value}


def test_units_sum_to_facility(facilities):
    """Two coal units at one facility must sum to one facility-level row."""
    ts = "2026-05-12T00:00:00+00:00"
    long_df = pd.DataFrame([
        _obs(ts, "AAA", "AAA1", "power", 100.0),
        _obs(ts, "AAA", "AAA2", "power", 150.0),
        _obs(ts, "AAA", "AAA1", "emissions", 80.0),
        _obs(ts, "AAA", "AAA2", "emissions", 120.0),
    ])
    out = transform.consolidate(long_df, facilities)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["power_mw"] == pytest.approx(250.0)
    assert row["emissions_tco2e"] == pytest.approx(200.0)
    assert row["capacity_registered_mw"] == pytest.approx(1000.0)  # both units


def test_out_of_window_rows_dropped(facilities):
    """Timestamps outside the analysis window are trimmed."""
    long_df = pd.DataFrame([
        _obs("2026-05-12T00:00:00+00:00", "BBB", "BBB1", "power", 10.0),
        _obs("2026-05-12T00:00:00+00:00", "BBB", "BBB1", "emissions", 0.0),
        _obs("2020-01-01T00:00:00+00:00", "BBB", "BBB1", "power", 999.0),  # too old
        _obs("2020-01-01T00:00:00+00:00", "BBB", "BBB1", "emissions", 0.0),
    ])
    out = transform.consolidate(long_df, facilities)
    assert len(out) == 1
    assert out.iloc[0]["power_mw"] == pytest.approx(10.0)


def test_metric_names_standardised(facilities):
    long_df = pd.DataFrame([
        _obs("2026-05-12T00:05:00+00:00", "BBB", "BBB1", "power", 5.0),
        _obs("2026-05-12T00:05:00+00:00", "BBB", "BBB1", "emissions", 0.0),
    ])
    out = transform.consolidate(long_df, facilities)
    assert {"power_mw", "emissions_tco2e"}.issubset(out.columns)


def test_output_schema_contract(facilities):
    long_df = pd.DataFrame([
        _obs("2026-05-12T00:00:00+00:00", "AAA", "AAA1", "power", 1.0),
        _obs("2026-05-12T00:00:00+00:00", "AAA", "AAA1", "emissions", 1.0),
    ])
    out = transform.consolidate(long_df, facilities)
    assert list(out.columns) == config.CONSOLIDATED_COLUMNS


def test_empty_input_returns_empty_contract(facilities):
    out = transform.consolidate(pd.DataFrame(), facilities)
    assert out.empty
    assert list(out.columns) == config.CONSOLIDATED_COLUMNS
