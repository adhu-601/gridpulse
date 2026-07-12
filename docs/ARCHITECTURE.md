# GridPulse — Architecture

## 1. Overview

GridPulse is a batch-plus-stream pipeline over Australian NEM electricity data.
It is organised as **five stages** wrapped in an orchestration layer, with a
**layered storage** model so the upstream API is expensive to hit but cheap to
replay.

```
API ──► Ingest ──► Transform ──► Load (DuckDB) ──► dbt marts ──► Serving
                     (+ geocode, quality gate)
        └──────────────── Dagster asset graph ────────────────┘
```

## 2. Stages

### 2.1 Ingest (`gridpulse/ingest.py`, `api_client.py`)
- `OpenElectricityClient` wraps the v4 REST API: bearer auth, ISO-8601 UTC
  formatting, retries **only** on transient 429/5xx (honouring `Retry-After`),
  fail-fast on 4xx, and a `requests_made` budget counter.
- Facility codes are **batched** (~25/call) so ~430 facilities cost ~18 data
  requests, staying well under the 500/day free-tier budget.
- Every raw response is written to `data/raw_openelectricity/` **before** parsing.
  A cache check makes re-runs a no-op — this is the *materialisation* that lets
  every downstream stage replay without touching the API.

### 2.2 Transform (`transform.py`)
Long-format observations → analysis-ready wide table:
1. timestamps → UTC, strictly trimmed to the 7-day window;
2. values coerced numeric, blanks dropped;
3. metric labels standardised (`power`→`power_mw`, `emissions`→`emissions_tco2e`);
4. **generating units summed to facility level** (power and emissions are both
   additive across parallel units, e.g. Bayswater's four coal turbines);
5. metrics pivoted wide; rows missing *both* metrics dropped;
6. enriched with facility metadata (region, fuel, capacity, lat/lon).

Output: `consolidated_facility_5min.csv` — the single source of truth.

### 2.3 Geocode (`geocode.py`)
- Derives `state` from NEM `network_region`.
- Validates every coordinate against an Australian bounding box; invalid/missing
  coordinates are **backfilled from the NEM-region centroid** (deterministic,
  offline) and tagged `geocode_source`.
- These coordinates seed the DuckDB `GEOMETRY` (`ST_Point`) column.

### 2.4 Quality gate (`quality.py`)
A dependency-free "expectations" layer run **before** load — 9 checks including
row count, schema contract, non-null keys, unique `(interval, facility)` grain,
region domain, in-window timestamps, non-negative emissions, and coordinates in
range. Negative *power* is retained (batteries charging) but reported. Hard
failures raise and stop the pipeline.

### 2.5 Load (`load.py`)
Builds the normalised schema shared with Assignment 1 and populates the core
dimensions/facts. The DuckDB **spatial** extension is loaded opportunistically
(graceful fallback without it). These tables are dbt's **sources**.

### 2.6 Transform layer — dbt (`dbt/`)
- **staging** (views): typed, NEM-scoped cleanups of each source.
- **marts** (tables): `dim_facility`, `fct_facility_interval` (one row per
  facility per 5-min interval, with local-time and energy/intensity
  derivations), and aggregate marts `agg_fuel_mix_daily`,
  `agg_region_intensity`, `agg_diurnal_profile`.
- **tests**: 39 nodes — generic (`unique`, `not_null`, `relationships`,
  `accepted_values`, `dbt_utils.accepted_range`) plus two custom singular tests
  (`assert_emissions_non_negative`, `assert_intervals_within_window`).

### 2.7 Serving
- **Streamlit** (`dashboard/app_streamlit.py`) reads only the marts. Four
  views: *Overview* (KPIs, mix donuts, weekly generation stack, price &
  demand), *Facility explorer* (all 541 facilities mapped with full-value
  hover, click drill-down to a facility's 5-minute week, sortable table),
  *Analysis* (regional intensity, diurnal profile, leaderboards), and
  *How it's built* (the embedded case study: `docs/architecture.svg` + a
  stage-by-stage narrative).
- **Live map** (`Assignment2_Dashboard_Group156.ipynb`): the original MQTT
  subscriber + Plotly Dash map that replays the stream in real time.

The canonical architecture diagram is `docs/architecture.svg` (hand-crafted);
`docs/make_architecture_diagram.py` rasterises it to `architecture.png` via
cairosvg for contexts that can't render SVG.

## 3. Orchestration (`orchestration/`)
The pipeline is a Dagster **asset graph**:

```
facility_catalogue → raw_timeseries → consolidated_dataset
      → warehouse/{FACILITY, FUEL_TYPE, FACILITY_POWER_EMISSIONS, MARKET_PRICE_DEMAND}
      → staging/{stg_*} → marts/{dim,fct,agg_*}
```

The four warehouse tables are emitted by a single `@multi_asset` and mapped 1:1
onto the dbt **sources** (via a custom `DagsterDbtTranslator`), so dbt models
always run *after* the warehouse is loaded. A `full_refresh` job materialises
everything and a `daily_full_refresh` schedule runs it at 06:00. Each asset
emits `MaterializeResult` metadata (row counts, quality pass-rate) for
observability in the Dagster UI.

## 4. Storage layers
| Layer | Location | Purpose |
|---|---|---|
| Raw (immutable) | `data/raw_openelectricity/*.json` | exact API responses; enables offline replay |
| Consolidated (contract) | `data/consolidated_facility_5min.csv` | cleaned wide table; single source of truth |
| Warehouse | `data/electricity_a2.duckdb` | normalised analytical schema (dbt sources) |
| Marts | DuckDB `main_marts.*` | tested, modelled tables the dashboards read |

## 5. Design decisions & trade-offs
- **DuckDB** over a server DB: zero-ops, embeddable, fast analytical scans, and
  first-class in dbt/Dagster — ideal for a single-node reproducible portfolio.
- **Cache-first ingestion**: correctness and reproducibility beat freshness for
  this workload; a real key + `--fetch` pulls new windows on demand.
- **NEM scoping in staging**: the catalogue carries one stray WEM (Western
  Australia) facility; staging filters to the five NEM regions so marts and
  `accepted_values` tests are clean.
- **Two dashboards**: the live Dash map answers "what's happening now?"; the
  Streamlit marts dashboard answers "what did the week look like?".
