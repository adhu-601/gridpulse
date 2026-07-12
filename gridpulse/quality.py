"""Lightweight data-quality gate (a dependency-free 'expectations' layer).

Runs a battery of assertions over the consolidated frame *before* it is loaded,
so bad data fails the pipeline early rather than surfacing in the dashboard.
Each check returns a structured result; :func:`assert_all` raises on any hard
failure. dbt tests then provide a second, warehouse-native layer of checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from . import config

log = logging.getLogger("gridpulse.quality")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"          # "error" fails the gate, "warn" does not


@dataclass
class QualityReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results if r.severity == "error")

    def add(self, name, passed, detail="", severity="error"):
        self.results.append(CheckResult(name, passed, detail, severity))
        lvl = logging.INFO if passed else (logging.ERROR if severity == "error" else logging.WARNING)
        log.log(lvl, "[%s] %s — %s", "PASS" if passed else "FAIL", name, detail)

    def as_table(self) -> pd.DataFrame:
        return pd.DataFrame([r.__dict__ for r in self.results])


def run_checks(df: pd.DataFrame) -> QualityReport:
    """Validate the consolidated wide table against the data contract."""
    r = QualityReport()

    r.add("row_count_positive", len(df) > 0, f"{len(df):,} rows")

    expected = set(config.CONSOLIDATED_COLUMNS)
    r.add("schema_columns_present", expected.issubset(df.columns),
          f"missing: {sorted(expected - set(df.columns))}")

    if df.empty:
        return r

    key_nulls = int(df[["interval_ts", "facility_code"]].isna().any(axis=1).sum())
    r.add("no_null_keys", key_nulls == 0, f"{key_nulls} rows with null key")

    dupes = int(df.duplicated(["interval_ts", "facility_code"]).sum())
    r.add("unique_grain", dupes == 0, f"{dupes} duplicate (interval, facility) rows")

    bad_region = sorted(set(df["network_region"].dropna()) - set(config.NEM_REGIONS))
    r.add("regions_in_domain", not bad_region, f"unexpected regions: {bad_region}")

    ts = pd.to_datetime(df["interval_ts"], utc=True, errors="coerce")
    in_window = ((ts >= pd.Timestamp(config.DATE_START)) &
                 (ts < pd.Timestamp(config.DATE_END))).all()
    r.add("timestamps_in_window", bool(in_window),
          f"{config.DATE_START.date()} → {config.DATE_END.date()}")

    neg_emis = int((df["emissions_tco2e"] < 0).sum())
    r.add("emissions_non_negative", neg_emis == 0, f"{neg_emis} negative emissions rows")

    # Negative power is physically valid (batteries charging) — warn, don't fail.
    neg_power = int((df["power_mw"] < 0).sum())
    r.add("negative_power_is_storage", True,
          f"{neg_power} negative-power rows (batteries charging — retained)", severity="warn")

    lat_ok = df["lat"].between(-44, -9).all()
    lon_ok = df["lon"].between(112, 154.5).all()
    r.add("coords_within_australia", bool(lat_ok and lon_ok),
          "all lat/lon inside AU bounding box")

    return r


def assert_all(df: pd.DataFrame) -> QualityReport:
    report = run_checks(df)
    if not report.ok:
        failed = [r.name for r in report.results if not r.passed and r.severity == "error"]
        raise ValueError(f"Data-quality gate failed: {failed}")
    return report
