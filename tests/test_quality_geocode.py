"""Unit tests for the data-quality gate and geocoding enrichment."""

import pandas as pd
import pytest

from gridpulse import geocode, quality


def _good_frame():
    return pd.DataFrame([
        {"interval_ts": "2026-05-12T00:00:00+00:00", "facility_code": "AAA",
         "facility_name": "Alpha", "network_region": "NSW1", "fueltech_id": "coal_black",
         "capacity_registered_mw": 500.0, "lat": -33.0, "lon": 151.0,
         "power_mw": 250.0, "emissions_tco2e": 200.0},
        {"interval_ts": "2026-05-12T00:00:00+00:00", "facility_code": "BBB",
         "facility_name": "Beta", "network_region": "SA1", "fueltech_id": "wind",
         "capacity_registered_mw": 200.0, "lat": -34.9, "lon": 138.6,
         "power_mw": -5.0, "emissions_tco2e": 0.0},   # negative power = battery, OK
    ])


def test_gate_passes_on_clean_frame():
    report = quality.run_checks(_good_frame())
    assert report.ok
    assert all(r.passed for r in report.results)


def test_gate_fails_on_negative_emissions():
    df = _good_frame()
    df.loc[0, "emissions_tco2e"] = -10.0
    report = quality.run_checks(df)
    assert not report.ok
    with pytest.raises(ValueError):
        quality.assert_all(df)


def test_gate_fails_on_bad_region():
    df = _good_frame()
    df.loc[0, "network_region"] = "WEM"        # not a NEM region
    report = quality.run_checks(df)
    assert not report.ok


def test_gate_flags_duplicate_grain():
    df = pd.concat([_good_frame(), _good_frame().iloc[[0]]], ignore_index=True)
    report = quality.run_checks(df)
    names = {r.name: r.passed for r in report.results}
    assert names["unique_grain"] is False


def test_geocode_backfills_invalid_coords():
    df = _good_frame()
    df.loc[0, "lat"] = None          # missing coordinate
    df.loc[0, "lon"] = None
    out = geocode.enrich(df)
    assert out.loc[0, "lat"] is not None and out.loc[0, "lon"] is not None
    assert out.loc[0, "geocode_source"] == "region_centroid"
    assert out.loc[0, "state"] == "NSW"
    assert out.loc[1, "geocode_source"] == "api"
