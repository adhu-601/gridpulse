# GridPulse — Data Dictionary

## Consolidated contract — `consolidated_facility_5min.csv`
The single source of truth downstream stages read.

| Column | Type | Description |
|---|---|---|
| `interval_ts` | timestamptz (UTC) | 5-minute dispatch interval |
| `facility_code` | varchar | OpenElectricity facility code |
| `facility_name` | varchar | Facility display name |
| `network_region` | varchar | NEM region: NSW1 / QLD1 / VIC1 / SA1 / TAS1 |
| `fueltech_id` | varchar | Dominant fuel technology (e.g. `coal_black`, `wind`) |
| `capacity_registered_mw` | double | Registered capacity, summed across units |
| `lat`, `lon` | double | Facility coordinates (validated / backfilled) |
| `power_mw` | double | Facility power output (negative = battery charging) |
| `emissions_tco2e` | double | Facility emissions (tonnes CO₂-equivalent, ≥ 0) |

## DuckDB warehouse (dbt sources) — `electricity_a2.duckdb`

### `FUEL_TYPE` (dimension)
| Column | Type | Notes |
|---|---|---|
| `fuel_id` | int | PK |
| `fuel_name` | varchar | unique fuel technology |
| `is_renewable` | boolean | renewable flag |
| `category` | varchar | Fossil / Renewable / Storage / Other |

### `FACILITY` (dimension)
| Column | Type | Notes |
|---|---|---|
| `facility_id` | int | PK |
| `facility_code` | varchar | unique |
| `facility_name` | varchar | |
| `state`, `network_region` | varchar | |
| `grid_connected` | boolean | |
| `lat`, `lon` | double | |
| `geom` | GEOMETRY | `ST_Point(lon,lat)` when spatial extension present |
| `fuel_id` | int | → FUEL_TYPE |
| `capacity_registered_mw` | double | |

### `FACILITY_POWER_EMISSIONS` (fact)
| Column | Type | Notes |
|---|---|---|
| `obs_id` | bigint | PK |
| `facility_id` | int | → FACILITY |
| `interval_ts` | timestamptz | unique with facility_id |
| `power_mw`, `emissions_tco2e` | double | |

### `MARKET_PRICE_DEMAND` (fact)
| Column | Type | Notes |
|---|---|---|
| `interval_ts` | timestamptz | |
| `network_region` | varchar | `NEM` for network-level |
| `price` | double | $/MWh |
| `demand` | double | MW |

_Reference tables `NGER_REPORT`, `LSRE_STATION`, `ABS_REGION`, `ABS_INDICATOR`,
`CORPORATION` carry the Assignment-1 schema and are created for completeness._

## dbt marts (`main_marts.*`)

| Model | Grain | Key columns |
|---|---|---|
| `dim_facility` | 1 / facility | facility attributes + fuel category |
| `fct_facility_interval` | 1 / facility / 5-min | `power_mw`, `energy_mwh`, `emissions_tco2e`, `intensity_tco2e_mwh`, `local_hour` |
| `agg_fuel_mix_daily` | day × fuel | `energy_mwh`, `emissions_tco2e`, `intensity_tco2e_mwh` |
| `agg_region_intensity` | region | `energy_twh`, `intensity_tco2e_mwh`, `renewable_share` |
| `agg_diurnal_profile` | local hour × fuel category | `avg_power_mw`, `energy_mwh` |

## Staging derivations of note
- `energy_mwh = power_mw × (5/60)` — energy for a 5-minute interval.
- `interval_local = interval_ts AT TIME ZONE 'Australia/Sydney'`; `local_hour`
  drives the diurnal analysis.
- `intensity_tco2e_mwh = emissions_tco2e / energy_mwh` (guarded against divide-by-zero).
