"""Stage 3 — Load the normalised analytical schema into DuckDB.

Implements the star-ish schema shared with Assignment 1 (dimensions
``FUEL_TYPE`` / ``FACILITY`` plus fact tables ``FACILITY_POWER_EMISSIONS`` and
``MARKET_PRICE_DEMAND``, alongside the NGER / LSRE / ABS reference tables). The
DuckDB **spatial** extension is loaded opportunistically so facilities carry a
real ``geom`` point when available, and the loader degrades gracefully without
it. These tables are the *sources* the dbt project builds its marts on top of.
"""

from __future__ import annotations

import logging

import duckdb
import pandas as pd

from . import config

log = logging.getLogger("gridpulse.load")

RENEWABLE = {"solar_utility", "solar_rooftop", "wind", "hydro", "pumps",
             "bioenergy_biomass", "bioenergy_biogas"}
REGION_STATE = {"NSW1": "NSW", "QLD1": "QLD", "VIC1": "VIC", "SA1": "SA", "TAS1": "TAS"}


def _category(ft: str | None) -> str:
    ft = (ft or "").lower()
    if ft.startswith(("coal", "gas", "distillate")):
        return "Fossil"
    if ft in RENEWABLE:
        return "Renewable"
    if ft.startswith("battery"):
        return "Storage"
    return "Other"


def _create_schema(con: duckdb.DuckDBPyConnection, has_spatial: bool) -> None:
    for t in ["FACILITY_POWER_EMISSIONS", "MARKET_PRICE_DEMAND", "NGER_REPORT",
              "ABS_INDICATOR", "ABS_REGION", "LSRE_STATION", "FACILITY",
              "FUEL_TYPE", "CORPORATION"]:
        con.execute(f"DROP TABLE IF EXISTS {t}")

    con.execute("""CREATE TABLE FUEL_TYPE (
        fuel_id INTEGER PRIMARY KEY, fuel_name VARCHAR NOT NULL UNIQUE,
        is_renewable BOOLEAN, category VARCHAR)""")
    con.execute("""CREATE TABLE CORPORATION (
        corporation_id INTEGER PRIMARY KEY, reporting_entity VARCHAR NOT NULL UNIQUE)""")

    geom_col = "geom GEOMETRY,\n" if has_spatial else ""
    con.execute(f"""CREATE TABLE FACILITY (
        facility_id INTEGER PRIMARY KEY, facility_code VARCHAR UNIQUE,
        facility_name VARCHAR NOT NULL, state VARCHAR(3), network_region VARCHAR,
        grid_connected BOOLEAN, lat DOUBLE, lon DOUBLE, {geom_col}
        fuel_id INTEGER REFERENCES FUEL_TYPE(fuel_id),
        capacity_registered_mw DOUBLE,
        corporation_id INTEGER REFERENCES CORPORATION(corporation_id))""")

    con.execute("""CREATE TABLE NGER_REPORT (
        report_id INTEGER PRIMARY KEY, facility_id INTEGER REFERENCES FACILITY(facility_id),
        fuel_id INTEGER REFERENCES FUEL_TYPE(fuel_id), reporting_year VARCHAR, fy_start INTEGER,
        electricity_prod_mwh DOUBLE, scope1_emissions_tco2e DOUBLE,
        scope2_emissions_tco2e DOUBLE, total_emissions_tco2e DOUBLE,
        emission_intensity_tco2e DOUBLE)""")
    con.execute("""CREATE TABLE LSRE_STATION (
        station_id INTEGER PRIMARY KEY, station_name VARCHAR NOT NULL, state VARCHAR(3),
        fuel_source VARCHAR, accredited_capacity_mw DOUBLE, status VARCHAR,
        accreditation_date DATE, registration_number VARCHAR)""")
    con.execute("""CREATE TABLE ABS_REGION (
        region_id INTEGER PRIMARY KEY, state VARCHAR(3), region_name VARCHAR)""")
    con.execute("""CREATE TABLE ABS_INDICATOR (
        indicator_id INTEGER PRIMARY KEY, region_id INTEGER REFERENCES ABS_REGION(region_id),
        data_item VARCHAR, year INTEGER, value DOUBLE)""")
    con.execute("""CREATE TABLE FACILITY_POWER_EMISSIONS (
        obs_id BIGINT PRIMARY KEY, facility_id INTEGER REFERENCES FACILITY(facility_id),
        interval_ts TIMESTAMPTZ NOT NULL, power_mw DOUBLE, emissions_tco2e DOUBLE,
        UNIQUE (facility_id, interval_ts))""")
    con.execute("""CREATE TABLE MARKET_PRICE_DEMAND (
        interval_ts TIMESTAMPTZ NOT NULL, network_region VARCHAR,
        price DOUBLE, demand DOUBLE)""")


def load_duckdb(consolidated: pd.DataFrame, facilities_df: pd.DataFrame,
                market_df: pd.DataFrame | None = None) -> dict:
    """Build the schema and populate the core dimensions and facts.

    Returns a small summary dict of row counts (handy for asset metadata).
    """
    config.ensure_dirs()
    con = duckdb.connect(str(config.DUCKDB_PATH))
    has_spatial = False
    try:
        con.execute("INSTALL spatial"); con.execute("LOAD spatial")
        has_spatial = True
    except Exception as e:                              # noqa: BLE001
        log.warning("Spatial extension unavailable, skipping geom column: %s", e)

    _create_schema(con, has_spatial)

    # -- FUEL_TYPE dimension ------------------------------------------------ #
    def _mode(s):
        s = s.dropna()
        return s.mode().iat[0] if not s.empty else None

    facility_dim = (facilities_df.groupby("facility_code", as_index=False).agg(
        facility_name=("facility_name", "first"), network_region=("network_region", "first"),
        lat=("lat", "first"), lon=("lon", "first"),
        fueltech_id=("fueltech_id", _mode),
        capacity_registered_mw=("capacity_registered_mw", "sum")))
    facility_dim["state"] = facility_dim["network_region"].map(REGION_STATE)

    fuels = sorted(facility_dim["fueltech_id"].dropna().unique().tolist())
    fuel_type_df = pd.DataFrame({
        "fuel_id": range(1, len(fuels) + 1), "fuel_name": fuels,
        "is_renewable": [f in RENEWABLE for f in fuels],
        "category": [_category(f) for f in fuels]})
    fuel_id_map = dict(zip(fuel_type_df["fuel_name"], fuel_type_df["fuel_id"]))

    facility_dim = facility_dim.reset_index(drop=True)
    facility_dim["facility_id"] = facility_dim.index + 1
    facility_dim["fuel_id"] = facility_dim["fueltech_id"].map(fuel_id_map).astype("Int64")
    facility_dim["grid_connected"] = True

    con.register("fuel_type_df", fuel_type_df)
    con.execute("INSERT INTO FUEL_TYPE SELECT fuel_id, fuel_name, is_renewable, category FROM fuel_type_df")

    fac_insert = facility_dim[["facility_id", "facility_code", "facility_name", "state",
                               "network_region", "grid_connected", "lat", "lon",
                               "fuel_id", "capacity_registered_mw"]].copy()
    con.register("fac_insert", fac_insert)
    if has_spatial:
        con.execute("""INSERT INTO FACILITY SELECT facility_id, facility_code, facility_name,
            state, network_region, grid_connected, lat, lon,
            CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN ST_Point(lon, lat) ELSE NULL END,
            fuel_id, capacity_registered_mw, NULL FROM fac_insert""")
    else:
        con.execute("""INSERT INTO FACILITY SELECT facility_id, facility_code, facility_name,
            state, network_region, grid_connected, lat, lon, fuel_id,
            capacity_registered_mw, NULL FROM fac_insert""")

    # -- FACILITY_POWER_EMISSIONS fact ------------------------------------- #
    stream = consolidated.copy()
    stream["interval_ts"] = pd.to_datetime(stream["interval_ts"], utc=True)
    code_to_id = dict(zip(facility_dim["facility_code"], facility_dim["facility_id"]))
    stream["facility_id"] = stream["facility_code"].map(code_to_id)
    stream = stream.dropna(subset=["facility_id"]).reset_index(drop=True)
    stream["facility_id"] = stream["facility_id"].astype(int)
    stream["obs_id"] = stream.index + 1
    fact = stream[["obs_id", "facility_id", "interval_ts", "power_mw", "emissions_tco2e"]]
    con.register("fact_df", fact)
    con.execute("INSERT INTO FACILITY_POWER_EMISSIONS SELECT * FROM fact_df")

    # -- MARKET_PRICE_DEMAND fact ------------------------------------------ #
    n_market = 0
    if market_df is not None and not market_df.empty:
        mk = market_df.copy()
        mk["interval_ts"] = pd.to_datetime(mk["interval_ts"], utc=True)
        for c in ("price", "demand"):
            if c not in mk.columns:
                mk[c] = pd.NA
        con.register("mk_df", mk[["interval_ts", "network_region", "price", "demand"]])
        con.execute("INSERT INTO MARKET_PRICE_DEMAND SELECT * FROM mk_df")
        n_market = len(mk)

    summary = {"fuel_type": len(fuel_type_df), "facility": len(facility_dim),
               "facility_power_emissions": len(fact), "market_price_demand": n_market,
               "spatial": has_spatial}
    con.close()
    log.info("Loaded DuckDB: %s", summary)
    return summary
