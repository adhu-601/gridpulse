# GridPulse — Project Context (feed this to a new chat)

> Purpose of this file: a complete, self-contained briefing on the project so a
> fresh AI chat (or a new collaborator) can continue work without re-discovering
> anything. Last updated: 12 Jul 2026.

## 1. What the project is

**GridPulse** — an end-to-end data-engineering pipeline over Australia's
National Electricity Market (NEM). It ingests 5-minute facility-level power and
CO₂e-emissions data from the **OpenElectricity v4 REST API**
(https://api.openelectricity.org.au/v4, free tier = 500 requests/day, CC-BY 4.0),
cleans/aggregates/geocodes it in Python, loads a normalised **DuckDB** schema,
models it with **dbt** into tested marts, orchestrates everything with
**Dagster**, and serves it through a **Streamlit** dashboard plus the original
**MQTT → Plotly Dash live map**.

Origin: COMP5339 (Data Engineering, University of Sydney) Assignment 2,
Group 156 — then levelled up into a portfolio/resume project by Aditya Moon
(adityamoon690@gmail.com). Goal: impress data-engineering recruiters; the repo
is intended for GitHub and the resume.

**Location on disk:** `E:\Resume\Projects and Jobs\Data Engineering Project`
(git repo, published to **github.com/adhu-601/gridpulse** — public — on 12 Jul 2026).
Python venv at `.venv` (Python 3.12 — dbt/Dagster are not stable on 3.14).

## 2a. Extending the data window (added 4 Jul 2026)

The warehouse currently holds only the committed 12–19 May 2026 week — that is
all the raw cache contains, and no `OPENELECTRICITY_API_KEY` is set on this
machine. The pipeline now supports longer histories: `gridpulse/config.py`
reads `GRIDPULSE_DATE_START` / `GRIDPULSE_DATE_END` (ISO dates) and
`config.fetch_windows()` splits the range into ≤7-day chunks (the API caps a
5-min request at 8 days); `ingest.py` fetches/caches/parses per (window,
batch) file, so interrupted runs resume. Cost: ~22 requests per week of data
→ the 480/day budget covers ~20 weeks per day. To load more data: get a free
key at platform.openelectricity.org.au, then e.g.
`OPENELECTRICITY_API_KEY=... GRIDPULSE_DATE_START=2026-03-01
GRIDPULSE_DATE_END=2026-05-19 python -m gridpulse.pipeline --fetch` +
`dbt build`. Note: `data/market_price_demand_5min.csv` (price/demand) came
from the original notebook and still covers only the sample week — extending
it needs a market fetch via `api_client.market_timeseries`. The dashboard is
window-agnostic: all labels derive from `WIN_DAYS`/`_win` computed from the
loaded facts ("N-day window", headline switches from "One week" to "N days").

## 2. Data facts (verified sample window)

- Window: **12–19 May 2026 UTC** (displayed local ≈ 12 May 10:00 → 18 May 23:55 +10).
- **668,134** facility-interval fact rows; **541** NEM facilities in the
  dimension (catalogue has 542 incl. one stray WEM facility filtered out in
  dbt staging); **353** facilities actually generated in the window; **188 idle**.
- 532 of 541 facilities have API coordinates; the rest are backfilled from NEM
  region centroids (see `gridpulse/geocode.py: REGION_CENTROID`).
- Market series: 2,016 rows of NEM-wide 5-min price (`price_aud_mwh`) & demand
  (`demand_mw`) in `data/market_price_demand_5min.csv`.
- Headline insights: fossil ≈ **64% of energy but ~100% of emissions**;
  totals ≈ **3.62 TWh**, **2.15 Mt CO₂e**, intensity **0.594 t/MWh**, renewable
  share **31.6%**; VIC1 dirtiest (0.767 t/MWh, brown coal), TAS1 cleanest
  (0.013, hydro); solar duck-curve 09:00–15:00.
- Test status (all verified passing on 3 Jul 2026): **pytest 10/10**,
  **pipeline quality gate 9/9**, **dbt build 47/47 nodes (39 data tests)**,
  Dagster definitions load with **15 assets**.

## 3. Repository layout

```
gridpulse/                 installable package (pyproject.toml, `pip install -e .`)
  config.py                paths, API config, window (DATE_START/END), contract columns
  api_client.py            OpenElectricityClient: batching, retry 429/5xx only,
                           Retry-After, budget ≤480/day, fail-fast 4xx
  ingest.py                raw JSON cache (data/raw_openelectricity/*.json) + parsing
  transform.py             UTC trim, unit→facility sum, metric standardisation,
                           long→wide pivot, writes consolidated_facility_5min.csv
  geocode.py               AU bbox validation, region-centroid backfill, state derivation
  quality.py               9-check expectations gate (hard fail stops run)
  load.py                  DuckDB loader: FACILITY, FUEL_TYPE,
                           FACILITY_POWER_EMISSIONS, MARKET_PRICE_DEMAND,
                           spatial GEOMETRY via ST_Point (graceful fallback)
  pipeline.py              CLI: python -m gridpulse.pipeline [--fetch]
dbt/                       dbt-duckdb project (profiles.yml inside dbt/)
  models/staging/          stg_facilities (NEM-scope filter!), stg_power_emissions,
                           stg_market  (views, schema main_staging)
  models/marts/            dim_facility, fct_facility_interval,
                           agg_fuel_mix_daily, agg_region_intensity,
                           agg_diurnal_profile  (tables, schema main_marts)
  tests/                   2 custom singular tests
orchestration/             Dagster: assets.py, dbt_assets.py (DagsterDbtTranslator
                           maps warehouse tables → dbt sources), definitions.py
                           (full_refresh job + daily_full_refresh schedule 06:00)
dashboard/app_streamlit.py THE dashboard (rebuilt — see §5)
.streamlit/config.toml     light theme (#f9f9f7 bg, #2a78d6 primary)
docs/
  architecture.svg         ★ canonical hand-crafted architecture diagram
  architecture.png         rasterised from the SVG (cairosvg, width 2340)
  make_architecture_diagram.py  svg→png converter (cairosvg)
  ARCHITECTURE.md          design doc; data_dictionary.md — schema
data/                      committed raw cache + electricity_a2.duckdb warehouse
tests/                     pytest suite (transform / quality / geocode)
Assignment2_Group156.ipynb            original publisher notebook (Tasks 1–4, 6:
                                      fetch, clean, DuckDB, EDA, MQTT publish)
Assignment2_Dashboard_Group156.ipynb  original MQTT subscriber + Dash live map
COMP5339_Assignment2_Group156_report.pdf  original report
Makefile, pyproject.toml, requirements.txt, README.md
```

DuckDB file: `data/electricity_a2.duckdb`. Schemas: `main` (warehouse sources),
`main_staging` (dbt views), `main_marts` (dbt tables).
`stg_market` columns: `interval_ts, network_region, price_aud_mwh, demand_mw`.
`fct_facility_interval` grain: (facility, 5-min interval); has `interval_ts`,
`interval_local`, `interval_date`, `local_hour`, facility attributes,
`power_mw`, `energy_mwh` (= power/12), `emissions_tco2e`, `intensity_tco2e_mwh`.

## 4. How to run (all commands from project root, Windows)

```bash
.venv/Scripts/python -m pytest                      # 10 unit tests
.venv/Scripts/python -m gridpulse.pipeline          # offline replay → DuckDB (add --fetch + OPENELECTRICITY_API_KEY for new data)
GRIDPULSE_DUCKDB="$PWD/data/electricity_a2.duckdb" \
  .venv/Scripts/dbt build --project-dir dbt --profiles-dir dbt
.venv/Scripts/streamlit run dashboard/app_streamlit.py
.venv/Scripts/dagster dev -m orchestration.definitions    # UI at :3000
python docs/make_architecture_diagram.py            # re-render architecture.png
```

The two assignment notebooks still work as the live-stream demo: run the
publisher notebook's Task 6 and the subscriber notebook in separate kernels;
they talk over `broker.hivemq.com`, topic `comp5339/group156/electricity`.

## 5. The Streamlit dashboard (rebuilt Jul 2026 round 5 — OpenElectricity design)

`dashboard/app_streamlit.py`, **full redesign modelled on openelectricity.org.au**
(user request 4 Jul 2026: "make it like openelectricity, minimal, explanatory
text + insights everywhere, facility click like their site"). Reads **only**
`main_marts.*` (+ `main_staging.stg_market`).

**Design language** (keep consistent):
- Warm off-white canvas `BG #FAF9F6`, white cards `#FFFFFF` with 1px `#E6E3DB`
  borders and 6px radius; ink `#1C1C1A`, secondary `#57554F`, muted `#8F8C84`;
  black `#141414` for buttons/active nav; red `#E34A33` for price/intensity
  lines and the dashed "Registered capacity" reference; font **DM Sans**
  (Google-Fonts @import in the CSS block).
- **OE fuel palette** (domain-canonical; CVD adjacency validated, worst
  adjacent ΔE 50.7; low contrast of Solar/Gas relieved by legend + summary
  table + tooltips): Coal #131313, Gas #F48E1B, Hydro #4582B4, Wind #417505,
  Solar #FED500, Bioenergy #1D7A7A, Distillate #F35020, Storage #3145CE,
  Other #A8A69E. Stack order = FUEL_GROUP_ORDER (Coal→Gas→Distillate→
  Bioenergy→Hydro→Wind→Solar→Storage), solid fills (no alpha).
- Recurring components: `chead(title, unit, right)` = OE chart-card header
  ("**Generation** MW …… Av. **22.9 GW**"); `sect(kicker, statement, body)` =
  section blocks (uppercase kicker + chunky statement + body); `insight(text)`
  = red-square note under each chart (values computed from data — keep
  accurate); `stat_tile()` KPI tiles; charts sit in `st.container(border=True)`
  restyled via CSS; `oe_fig()` = dotted-grid minimal Plotly chrome +
  `add_night_bands()` (19:00–06:30 grey vrects, like the OE tracker);
  `PLOT_CONFIG` hides the modebar.
- Top bar: "Grid~Pulse" wordmark (green SVG pulse squiggle); the **section
  nav (st.tabs) is CSS-repositioned to the top-right of the header bar**
  (`position:absolute; top:27px; right:6px` on the tab-list, needs
  `.block-container { position:relative }`), black underline on active —
  like the OE site header. Data-source meta lives in the hero kicker.
  **Layout is full-width** (`.block-container max-width:100%`, 3rem side
  padding); text blocks keep their own max-widths. Hero: big headline +
  lede + tech chips + the OE-homepage-style **FOSSILS x% / RENEWABLES y%
  split numbers** (computed from `mix` groups).

The **headline hero** (kicker + big "N days of Australia's electricity…" +
lede + tech chips + FOSSILS/RENEWABLES split) is a `hero()` function called
**only inside the Overview tab** — it must NOT appear on Facilities / Analysis /
About. The hero has a right-fading dotted-grid texture (`.oe-hero::before`).

Four tabs (labelled **Overview | Facilities | Analysis | About**):
1. **Overview** — `hero()` first, then 6 stat tiles; Generation stacked-area
   card (GW, night bands, day ticks, fuel legend); **fuel summary table**
   (`oe-mix`, colour squares + Energy GWh + contribution-to-energy % +
   Emissions kt + contribution-to-CO2e %, with Renewables/Fossils total rows)
   beside a **two-ring donut** (outer energy, inner emissions; ENERGY/CO₂e
   centre labels + an HTML fuel legend row rendered under it — the plotly pie
   legend was unreliable so a hand-built `<div>` legend is used); Demand
   (black line) + Price (red step line) cards plus an OE-style **Stats min/max
   table** with timestamps.
2. **Facilities** — OE explorer layout: filter row (name search, region,
   technology-group, size-by, include-idle) → **table (left, single-row
   select) + map (right)** → dark footer strip (facility count / generated
   count / total MW). Clicking a **map dot or a table row** (change-detection
   via `st.session_state` `_prev_map_code`/`_prev_tbl_code`; most recent event
   wins, default = largest facility) opens the **OE facility detail card**:
   name + fueltech + region header, REGISTERED CAPACITY big number top-right,
   divider stats row, Generation chart with **dashed red "Registered
   capacity" hline** + Av. MW header, Emissions chart if nonzero. Full
   all-values dataframe in an expander. Second radio layer = all-Australia
   NGER census map (Assignment 1 data), same styling.
3. **Analysis** — region small-multiples card (3 horizontal bars: Energy
   black / Intensity red / Renewable share green, shared region order);
   diurnal stacked area; top-15 leaderboard (fuel colours); intensity by
   fueltech with dashed red grid-average vline. No axis titles where the
   card header already carries the unit (they collided with legends).
4. **About** (renamed from "How it's built" — shorter label also fixes the
   top-right nav overflow) — opens with an **OpenElectricity-style About
   hero**: the giant word "About" (`.oe-gridword`, 5.4rem) centred over a
   full-bleed **dotted-grid band** (`.oe-grid`, radial-gradient dots), then a
   green-accented **mission statement** (`.oe-mission`), then a two-column
   **`.oe-prose`** block answering *why I built it / what it solves / how it
   helps / who it's for* (the "add more info — why/use/helps/solves" request).
   Then the technical case study: pipeline strip (minimal white nodes, black
   arrows, 16.5px titles), embedded architecture.svg in a card, then
   **`stage_scrolly()`**: a scroll-driven stage walkthrough rendered via
   `st.components.v1.html` (iframe, height 960) — six rows with big number
   circles, stroke icons (`STAGE_ICONS` dict) and 1.75rem titles; an
   IntersectionObserver (`rootMargin -30%/-30%`) lights each stage up
   (black filled number, full opacity) as it crosses the middle of the
   viewport, OE-storytelling style. Then 3 test-layer cards, storage table,
   black "Run it yourself" command card, verified-results tiles, tech chips.

`.streamlit/config.toml`: primary #141414, bg #FAF9F6.

## 6. Architecture diagram

`docs/architecture.svg` — **hand-written minimal SVG (1600×780), redesigned
Jul 2026 round 5** to match the OE dashboard: off-white `#FAF9F6` canvas, no
gradients/shadows/icons. Header = "GridPulse ~ architecture" wordmark + one-line
subtitle + hairline rule. **Six white stage cards in one left→right row**
(black number circle, coloured 10px square + uppercase stage label, a
**coloured stroke icon top-right** — cloud / download / funnel / db cylinder /
flask / monitor, matching the dashboard's `STAGE_ICONS` — bold title,
3 short lines + 1 muted footnote), joined by **bold 3.5px black arrows with
solid triangular heads** — the flow is the loudest element. The Dagster pill
carries a small clock icon. Below: dashed red
**Dagster control bus** (horizontal line + up-arrows into all six cards, pill
label "DAGSTER ORCHESTRATES EVERY STAGE"). Bottom: **LAYERED STORAGE strip**
(Raw → Contract → Warehouse → Marts white boxes with coloured left edges, mono
artefact paths, black arrows) and a footer rule with the three test layers.
Stage accents (sync with `STAGE` dict in the dashboard): source #4582B4,
ingest #3145CE, transform #1D7A7A, warehouse #B46813, model #7C3AED,
serve #417505; Dagster #E34A33. Use plain "CO2e" (subscript ₂ has no glyph in
cairosvg). Edit the SVG directly; then run
`python docs/make_architecture_diagram.py` (cairosvg) to refresh the PNG.
README embeds the SVG; the dashboard case-study tab embeds it.

## 7. Decisions & conventions (don't accidentally undo these)

- **Layered storage**: raw JSON (immutable) → consolidated CSV (contract) →
  DuckDB schema → dbt marts. Nothing downstream re-hits the API.
- **Quality gate before load, dbt tests after** — both are selling points.
- Negative `power_mw` is **valid** (batteries charging) and retained;
  emissions must be ≥ 0 (tested).
- dbt staging filters to the 5 NEM regions (drops 1 WEM facility) — that's why
  dim has 541 vs 542 in the warehouse FACILITY table.
- Dashboard reads marts only — keep it that way (it's part of the story).
- Charts: no dual axes; unified hover; explicit `hovertemplate`s everywhere;
  units in labels. Map hover fields are pre-formatted strings.
- `interval_local` is the display timestamp (Australia/Sydney); `interval_ts`
  is UTC-based.
- Env overrides: `GRIDPULSE_DUCKDB`, `GRIDPULSE_DATA_DIR`,
  `OPENELECTRICITY_API_KEY`, `GRIDPULSE_FETCH=1` (Dagster fetch mode).

## 8. Session history (what was done in the Jul 2026 chat)

8.0. **Design revision round 5 (4 Jul 2026) — OpenElectricity redesign:** user
   asked to "completely change the design and make it similar to
   openelectricity.org.au — minimal, explanatory text for visualisations,
   proper insights, facility click like their site, and a minimal architecture
   diagram with clearly visible flow arrows."
   - Studied openelectricity.org.au + explore.openelectricity.org.au in
     Chrome (homepage, tracker, facilities page, Gladstone detail overlay) and
     replicated the language: off-white canvas, DM Sans, chart-card headers
     with "Av. X" right slots, fuel summary table with colour squares and
     contribution columns, Stats min/max table, night shading, red price
     lines, black pill accents, OE's own fuel colours.
   - **Full rewrite of `dashboard/app_streamlit.py`** (see §5 for the current
     structure) and **full rewrite of `docs/architecture.svg`** (see §6).
     Palette CVD-validated with the dataviz skill validator (worst adjacent
     ΔE 50.7). PNG re-rendered.
   - Facility explorer now mirrors the OE explorer: table+map side by side,
     dark totals strip, and a click (map dot or table row) opens an OE-style
     detail card with registered capacity + dashed capacity line on the
     generation trace.
   - Verified in Chrome on :8511 — all four tabs, map-click and table-click
     drill-down both switch the card (tested Bouldercombe + Loy Yang A);
     fixed a legend/axis-title collision on the two horizontal-bar charts by
     dropping axis titles (unit lives in the card header).
   - Superseded from round 4: dark hero banner, About band + 4 value cards,
     blue insight boxes, tinted stage cards, the coloured-gradient SVG. The
     no-emoji rule, marts-only reads, no dual axes, categorical map colour +
     size floor all still hold.

7.0. **Design revision round 4 (4 Jul 2026):** full modern-professional
   restyle per user request ("completely redesign, more attractive, modern yet
   professional; add a project description at the start; show the pipeline
   workflow; add 1–2 more insight lines; clean architecture diagram with
   colour-coded stages, bolder arrows, bigger titles").
   - **Architecture SVG rebuilt** (see §6): navy header band, six colour-coded
     tinted stages with numbered badges + 18px titles, bold 3px arrows, dashed
     rose Dagster control bus. Re-rendered PNG. Verified visually.
   - **Dashboard**: new page bg #f4f6fb + refreshed tokens; hero adds a stronger
     value-prop subtitle + tech-chip row; NEW always-visible **About band**
     (intro paragraph + 4 value cards) and **pipeline workflow strip**
     (`pipeline_strip()`, colours from new `STAGE` dict = SVG palette); KPI cards
     replaced with custom HTML `kpi_card()` (coloured left accent); "How it's
     built" tab gained a workflow strip at top, recoloured stage cards, and a
     dark **"Run it yourself"** numbered command sequence (`.gp-run`); extended
     insight lines on the mix/generation/market/region/diurnal/leaderboard/tech
     charts. All data logic (queries, `FUEL_GROUP_SQL`, fuel palette, map
     size-floor, drill-down) unchanged. Verified all four tabs in Chrome.
   - Kept: no emojis, no dual axes, marts-only reads, categorical map colour +
     size floor, segmented pill tabs, banner + stat strip.


1. Verified the whole pipeline end-to-end: pytest 10/10, pipeline run
   (9/9 checks, 668,134 rows loaded), dbt build 47/47, Dagster 15 assets load.
2. Replaced the old single-page Streamlit dashboard with the four-tab app
   described in §5. Root cause of "only a few values on the map" in the old
   version: the map query had `having avg(power_mw) > 0` and only mapped
   facilities with observations — now all 541 render with an idle toggle.
3. Replaced the old matplotlib architecture PNG with the hand-crafted SVG
   (§6); `make_architecture_diagram.py` is now just the cairosvg rasteriser;
   added cairosvg to dev deps; README points at the SVG.
4. README: new Serving row, new "The dashboard" section; ARCHITECTURE.md §2.7
   updated to match.
5. Added `.streamlit/config.toml` theme. Added this `context.md`.
6. Visually verified every tab in Chrome (hover tooltip, map click drill-down,
   tables, case-study rendering) with the app on port 8511.
7z. **Design revision round 3 (3 Jul 2026):** user disliked the plain hero and
   still couldn't "see all the stations." Two fixes:
   - **Hero fully redesigned** into a dark gradient BANNER (`.gp-banner`,
     navy→blue radial+linear gradient, rounded, shadow) with an inline SVG
     bolt mark (`BOLT`, gold — NOT an emoji), big white "GridPulse" title, and
     a proper STAT STRIP (`.gp-stats`/`.gp-stat`) of 4 divider-separated
     stats (window / facilities / observations / tests) — replaces the
     run-together chip row the user complained about. Tabs restyled as a
     centred SEGMENTED PILL control (grey track, white active pill), not an
     underline nav.
   - **Map visibility root cause:** the NEM layer coloured markers by a
     CONTINUOUS scale (Viridis/Reds), so low-power stations rendered as tiny
     dark-purple dots that vanished on the basemap. Fixed: NEM map now colours
     by `fuel_group` (categorical, distinct FUEL_GROUP_COLOURS incl. "Other")
     and sizes by the selected metric with a **firm size floor**
     (`s.clip(lower=s.max()*0.32)+2`) so every one of the 541 is a clearly
     visible dot. carto-positron basemap, opacity 0.9, itemsizing constant.
   Keep these: categorical colour on the map (not continuous), the size floor,
   the banner + stat strip, segmented pill tabs.
7a. **Design revision round 2 (3 Jul 2026, later same day):** full website
   look — Streamlit header/menu/sidebar all hidden via CSS (`header
   [data-testid="stHeader"] display:none`), **no sidebar at all** (author/
   source/rebuild info moved to a centred footer); hero is centred (kicker,
   2.6rem "GridPulse" title, subtitle, pill chips); the 4 sections are big
   centred nav tabs (17px, `justify-content:center`). Every chart now has a
   one-line "INSIGHT" callout underneath (`insight()` helper, values computed
   from the data — keep them accurate). Architecture SVG text was cut ~40%
   (shorter card bullets, one-line footer).
   **Map rework:** two data layers via radio —
   (a) "NEM facilities — live week (541)": styled like the Assignment 2 Dash
   dashboard: metric radio Power/Emissions, continuous Viridis/Reds colour +
   size by metric, open-street-map basemap, full-value hover, drill-down,
   table; (b) "All Australian stations (626)": from
   `data/au_power_stations.csv`, built from Assignment 1 outputs at
   `E:\USYD\SEM 3\COMP 5339 - Data Engineering\DE Assignment 1\
   COMP5339_Assignment1_Group156\data1\output` (geocoded_power_stations.csv:
   3,718 station names but only 626 with coordinates; joined to
   consolidated_electricity_data.csv latest-year NGER fuel/production/
   emissions; 232 stations have no NGER match → fuel "Unknown", "—" values).
   Colour by primary fuel (AU_FUEL_COLOURS), size by annual production,
   carto-positron basemap — mirrors the A1 map. Note: user initially expected
   "668,134 locations" — that's fact rows (facility × 5-min interval), not
   stations; the two-layer map + insight line now explains this in-app.
7b. **Design revision round 1:** removed ALL emojis from the app (user
   requirement — keep it that way); hero header with blue uppercase kicker +
   2.4rem title; tabs restyled as a nav (plain labels, blue underline);
   `section()` helper renders every section heading as accent-bar + title +
   one-line caption (replaces st.subheader + long explanatory paragraphs —
   keep copy short); KPI cards have a blue top border and clamp() font so
   values never truncate; `.block-container` padding-top must stay ≥ ~3.4rem
   or content hides under Streamlit's fixed header. Diagram polish: title
   33px, zone labels 14px with coloured accent bars, larger footer text.

## 9. Known quirks / gotchas

- Windows + PowerShell 5.1; use `.venv/Scripts/...` executables. Bash (Git
  Bash) also available.
- `dbt build` needs env var `GRIDPULSE_DUCKDB` pointing at the warehouse
  (profiles.yml reads it) and the DuckDB file must not be locked by a running
  Streamlit/Dagster process (Streamlit connects read-only per query, so it's
  normally fine).
- cairosvg needs its cairo DLLs — it installed and works in this venv.
- Plotly ≥ 6 uses `px.scatter_map` (not the deprecated `scatter_mapbox`).
- Streamlit ≥ 1.35 required for `st.plotly_chart(on_select=...)`; venv has 1.58.
- The dashboard caches queries 10 min (`st.cache_data(ttl=600)`) — press "C"
  / rerun to clear after rebuilding the warehouse.

## 10. Remaining ideas (not done)

- GitHub publish DONE (12 Jul 2026): `git init` + first commit pushed to
  **github.com/adhu-601/gridpulse** (public, `gh repo create`). Data decision —
  the immutable `data/raw_openelectricity/` JSON cache (77 MB, the offline
  replay source) IS committed; the derived `electricity_a2.duckdb` (106 MB, over
  GitHub's 100 MB/file limit) and `consolidated_facility_5min.csv` (63 MB) are
  gitignored and rebuilt by `python -m gridpulse.pipeline`. The hardcoded free
  OpenElectricity key in `Assignment2_Group156.ipynb` was redacted to
  `REPLACE_ME` before the push (rotate it at platform.openelectricity.org.au if
  desired). Added `LICENSE` (MIT). README de-emojified + badges + TOC.
- GitHub Actions CI (pytest + dbt build), incremental dbt models, forecast
  mart (XGBoost/Prophet), Parquet partitioning.
- Optional: add dashboard screenshots to README (attempts to capture clean
  ones via automated Chrome were flaky; do manually).
