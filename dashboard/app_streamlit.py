"""GridPulse - NEM analytics dashboard & project case study (Streamlit + Plotly).

Design language modelled on openelectricity.org.au: warm off-white canvas,
chunky grotesque headlines, white chart cards with thin borders and
"Title UNIT ... Av. X" headers, the domain-canonical fuel-tech palette,
and an OpenElectricity-style facility detail card (units, registered-capacity
reference line, weekly generation trace).

Reads the tested dbt marts in DuckDB (never raw data), plus the Assignment 1
all-Australia station layer. Run with:

    streamlit run dashboard/app_streamlit.py

Sections: Overview | Facilities | Analysis | How it's built
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# --------------------------------------------------------------------------- #
# Config & design tokens
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Data source resolution: the full pipeline warehouse when it exists (local dev),
# otherwise the committed slim warehouse that holds just the four tables this
# dashboard reads — which is what ships to Streamlit Community Cloud, where the
# 106 MB pipeline warehouse cannot be rebuilt.
_FULL_DB = PROJECT_ROOT / "data" / "electricity_a2.duckdb"
_SLIM_DB = PROJECT_ROOT / "data" / "gridpulse_dashboard.duckdb"
DUCKDB_PATH = os.environ.get("GRIDPULSE_DUCKDB") or str(
    _FULL_DB if _FULL_DB.exists() else _SLIM_DB)
ARCH_SVG = PROJECT_ROOT / "docs" / "architecture.svg"
AU_STATIONS_CSV = PROJECT_ROOT / "data" / "au_power_stations.csv"

BG = "#FAF9F6"          # warm off-white page canvas
SURFACE = "#FFFFFF"     # chart / card surface
BORDER = "#E6E3DB"      # hairline card borders
INK = "#1C1C1A"         # primary text
INK_2 = "#57554F"       # secondary text
MUTED = "#8F8C84"       # captions, axis labels
GRID = "#ECEAE3"        # dotted chart gridlines
BLACK = "#141414"       # buttons, active nav, emphasis
RED = "#E34A33"         # price / intensity / capacity reference
GREEN = "#417505"       # renewables accent
FONT = "'DM Sans', 'Segoe UI', system-ui, sans-serif"

# Pipeline-stage accents (kept in sync with docs/architecture.svg).
STAGE = {
    "source":    "#4582B4",
    "ingest":    "#3145CE",
    "transform": "#1D7A7A",
    "warehouse": "#B46813",
    "model":     "#7C3AED",
    "serve":     "#417505",
}

# Domain-canonical fuel palette (OpenElectricity's own colour language).
# CVD-validated for stack adjacency (worst adjacent pair dE 50.7); the low
# contrast of Solar/Gas on white is relieved by the legend, the summary
# table and full hover tooltips on every mark.
FUEL_GROUP_ORDER = ["Coal", "Gas", "Distillate", "Bioenergy", "Hydro",
                    "Wind", "Solar", "Storage"]
FUEL_GROUP_COLOURS = {
    "Coal": "#131313", "Gas": "#F48E1B", "Hydro": "#4582B4", "Wind": "#417505",
    "Solar": "#FED500", "Bioenergy": "#1D7A7A", "Distillate": "#F35020",
    "Storage": "#3145CE", "Other": "#A8A69E",
}
RENEWABLE_GROUPS = ["Hydro", "Wind", "Solar", "Bioenergy"]
FOSSIL_GROUPS = ["Coal", "Gas", "Distillate"]

# Assignment 1 layer: NGER primary-fuel labels, mapped onto the same language.
AU_FUEL_COLOURS = {
    "Black Coal": "#131313", "Brown Coal": "#8B572A", "Natural Gas": "#F48E1B",
    "Coal Seam Methane": "#C98500", "Waste Coal Mine Gas": "#B46813",
    "Diesel": "#F35020", "Liquid Fuel": "#F35020", "Wind": "#417505",
    "Solar": "#FED500", "Hydro": "#4582B4", "Landfill Gas": "#7FA02F",
    "Wood": "#1D7A7A", "Bagasse": "#1D7A7A", "Multiple Sources": "#6B7280",
    "Unknown": "#A8A69E",
}

FUEL_GROUP_SQL = """
    case
        when fueltech_id like 'coal%'      then 'Coal'
        when fueltech_id like 'gas%'       then 'Gas'
        when fueltech_id like 'solar%'     then 'Solar'
        when fueltech_id like 'wind%'      then 'Wind'
        when fueltech_id =    'hydro'      then 'Hydro'
        when fueltech_id like 'battery%'   then 'Storage'
        when fueltech_id =    'pumps'      then 'Storage'
        when fueltech_id like 'bioenergy%' then 'Bioenergy'
        when fueltech_id =    'distillate' then 'Distillate'
        else 'Other'
    end
"""

try:
    from gridpulse.geocode import REGION_CENTROID
except Exception:  # pragma: no cover
    REGION_CENTROID = {"NSW1": (-32.16, 147.02), "QLD1": (-22.58, 144.43),
                       "VIC1": (-36.85, 144.28), "SA1": (-34.29, 135.71),
                       "TAS1": (-42.02, 146.60)}

st.set_page_config(page_title="GridPulse - NEM Analytics", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&display=swap');

  /* hide Streamlit chrome so it reads as a website */
  header[data-testid="stHeader"] { display:none; }
  #MainMenu, footer { visibility:hidden; }
  [data-testid="stSidebarCollapsedControl"] { display:none; }

  .stApp { background:#FAF9F6; }
  .block-container { padding-top:1.2rem; padding-bottom:2.5rem;
      max-width:100%; padding-left:3rem; padding-right:3rem; }
  html, body, [class*="css"], .stMarkdown, button, input, select {
      font-family:'DM Sans','Segoe UI',system-ui,sans-serif !important; }

  /* ---- top bar ---------------------------------------------------------- */
  .oe-topbar { display:flex; align-items:center; justify-content:space-between;
      padding:10px 2px 14px 2px; border-bottom:1px solid #E6E3DB; }
  .oe-wordmark { font-size:1.45rem; font-weight:800; letter-spacing:-0.03em;
      color:#141414; display:flex; align-items:center; gap:2px; }
  .oe-wordmark svg { margin:3px 3px 0 3px; }
  .oe-topmeta { font-size:11px; font-weight:600; letter-spacing:.14em;
      text-transform:uppercase; color:#8F8C84; }
  .oe-topmeta b { color:#1C1C1A; }

  /* ---- dotted-grid backdrop (OpenElectricity "About" hero signature) ----- */
  .oe-grid { position:relative;
      background-image:radial-gradient(#D7D3C8 1.15px, transparent 1.2px);
      background-size:46px 46px; background-position:center;
      border-top:1px solid #E6E3DB; border-bottom:1px solid #E6E3DB;
      margin:0 -3rem; padding:0 3rem; }
  .oe-gridword { text-align:center; font-size:5.4rem; font-weight:800;
      letter-spacing:-0.045em; color:#141414; margin:0; padding:52px 0; }

  /* ---- hero -------------------------------------------------------------- */
  .oe-hero { position:relative; display:flex; flex-wrap:wrap; gap:40px;
      align-items:flex-end; padding:40px 2px 34px 2px;
      border-bottom:1px solid #E6E3DB; }
  .oe-hero::before { content:""; position:absolute; inset:0 -3rem;
      background-image:radial-gradient(#DCD8CE 1.1px, transparent 1.15px);
      background-size:44px 44px;
      -webkit-mask-image:linear-gradient(90deg, transparent 62%, #000 100%);
      mask-image:linear-gradient(90deg, transparent 62%, #000 100%);
      pointer-events:none; z-index:0; }
  .oe-hero > * { position:relative; z-index:1; }
  .oe-hero .left { flex:1 1 560px; }
  .oe-kicker { font-size:11px; font-weight:700; letter-spacing:.22em;
      text-transform:uppercase; color:#8F8C84; margin:0 0 18px 0; }
  .oe-big { font-size:3.5rem; font-weight:800; letter-spacing:-0.045em;
      line-height:1.03; color:#141414; margin:0; }
  .oe-lede { font-size:15.5px; line-height:1.65; color:#57554F;
      margin:20px 0 0 0; max-width:760px; }
  .oe-lede b { color:#1C1C1A; font-weight:700; }
  .oe-split { flex:0 0 auto; display:flex; flex-direction:column; gap:22px;
      padding-bottom:6px; }
  .oe-split .row { display:flex; align-items:baseline; gap:10px; }
  .oe-split .sq { width:13px; height:13px; border-radius:2px; flex:0 0 auto;
      align-self:center; }
  .oe-split .lab { font-size:11px; font-weight:700; letter-spacing:.16em;
      color:#57554F; }
  .oe-split .num { font-size:2.5rem; font-weight:800; letter-spacing:-0.03em;
      color:#141414; line-height:1; }
  .oe-split .num small { font-size:1.3rem; font-weight:700; color:#8F8C84; }
  .oe-herochips { margin-top:20px; }
  .oe-herochips span { display:inline-block; border:1px solid #E0DDD4;
      color:#57554F; border-radius:999px; padding:3px 12px; font-size:11.5px;
      font-weight:600; margin:0 6px 6px 0; background:#fff; }

  /* ---- nav tabs: top-right of the header bar, like openelectricity ------- */
  .block-container { position:relative; }
  .stTabs [data-baseweb="tab-list"] { position:absolute; top:44px; right:6px;
      z-index:50; justify-content:flex-end; flex-wrap:nowrap; gap:26px;
      background:transparent; border-bottom:none; padding:0; margin:0;
      white-space:nowrap; }
  .stTabs [data-baseweb="tab"] p { white-space:nowrap; }
  .stTabs [data-baseweb="tab"] { font-size:15px; font-weight:600;
      color:#8F8C84; padding:8px 2px; background:transparent; }
  .stTabs [data-baseweb="tab-panel"] { padding-top:6px; }
  .stTabs [data-baseweb="tab"]:hover { color:#1C1C1A; background:transparent; }
  .stTabs [aria-selected="true"] { color:#141414; font-weight:700;
      background:transparent; box-shadow:none; }
  .stTabs [data-baseweb="tab-highlight"] { background-color:#141414;
      height:2.5px; }
  .stTabs [data-baseweb="tab-border"] { display:none; }

  /* ---- white cards (bordered containers) --------------------------------- */
  [data-testid="stVerticalBlockBorderWrapper"] {
      background:#FFFFFF; border:1px solid #E6E3DB !important;
      border-radius:6px; padding:0.55rem 0.9rem 0.35rem 0.9rem; }
  [data-testid="stVerticalBlockBorderWrapper"] > div { border:none !important; }

  /* ---- chart-card header:  Title UNIT ......... Av. X -------------------- */
  .oe-chead { display:flex; align-items:baseline; gap:7px;
      border-bottom:1px solid #F0EEE7; padding:4px 2px 9px 2px; margin-bottom:2px; }
  .oe-chead .t { font-size:13.5px; font-weight:700; color:#1C1C1A; }
  .oe-chead .u { font-size:12px; font-weight:500; color:#8F8C84; }
  .oe-chead .r { margin-left:auto; font-size:12px; color:#8F8C84; }
  .oe-chead .r b { color:#1C1C1A; font-weight:700; }

  /* ---- section blocks: kicker + statement + body -------------------------- */
  .oe-sect { margin:30px 0 14px 0; max-width:940px; }
  .oe-sect .k { font-size:10.5px; font-weight:700; letter-spacing:.2em;
      text-transform:uppercase; color:#8F8C84; margin-bottom:8px; }
  .oe-sect .s { font-size:1.5rem; font-weight:700; letter-spacing:-0.025em;
      line-height:1.25; color:#141414; }
  .oe-sect .b { font-size:14px; line-height:1.6; color:#57554F; margin-top:8px; }
  .oe-sect .b b { color:#1C1C1A; }

  /* ---- About mission statement + prose blocks ---------------------------- */
  .oe-mission { font-size:2.15rem; font-weight:800; letter-spacing:-0.03em;
      line-height:1.18; color:#141414; max-width:960px; margin:34px 0 6px 0; }
  .oe-mission .accent { color:#417505; }
  .oe-prose { display:grid; grid-template-columns:210px 1fr; gap:10px 40px;
      max-width:1000px; padding:22px 0; border-top:1px solid #E6E3DB;
      margin-top:22px; }
  .oe-prose .h { font-size:1.2rem; font-weight:700; letter-spacing:-0.01em;
      color:#141414; }
  .oe-prose .h .n { display:block; font-size:11px; font-weight:700;
      letter-spacing:.16em; color:#8F8C84; margin-bottom:6px; }
  .oe-prose p { font-size:14.5px; line-height:1.7; color:#57554F; margin:0 0 10px 0; }
  .oe-prose p:last-child { margin-bottom:0; }
  .oe-prose p b { color:#1C1C1A; }
  @media (max-width:820px){ .oe-prose { grid-template-columns:1fr; gap:6px; } }

  /* ---- insight note under a chart ---------------------------------------- */
  .oe-ins { display:flex; gap:12px; align-items:flex-start; max-width:940px;
      margin:10px 2px 6px 2px; padding:12px 0 14px 0;
      border-bottom:1px solid #E6E3DB; }
  .oe-ins .sq { width:9px; height:9px; border-radius:2px; background:#E34A33;
      flex:0 0 auto; margin-top:5px; }
  .oe-ins .tx { font-size:13.5px; line-height:1.6; color:#57554F; }
  .oe-ins .tx b { color:#1C1C1A; }

  /* ---- stat tiles --------------------------------------------------------- */
  .oe-stat { background:#FFFFFF; border:1px solid #E6E3DB; border-radius:6px;
      padding:14px 16px 12px 16px; height:100%; }
  .oe-stat .l { font-size:10.5px; font-weight:700; letter-spacing:.14em;
      text-transform:uppercase; color:#8F8C84; }
  .oe-stat .v { font-size:1.72rem; font-weight:800; letter-spacing:-0.03em;
      color:#141414; line-height:1.15; margin:7px 0 2px 0; }
  .oe-stat .v small { font-size:0.95rem; font-weight:700; color:#8F8C84; }
  .oe-stat .s { font-size:11.5px; color:#8F8C84; }

  /* ---- energy-mix summary table ------------------------------------------ */
  table.oe-mix { width:100%; border-collapse:collapse; font-size:13px; }
  table.oe-mix th { text-align:right; font-size:11px; font-weight:700;
      color:#1C1C1A; padding:6px 4px 8px 4px; border-bottom:1px solid #E6E3DB; }
  table.oe-mix th small { display:block; font-weight:500; color:#8F8C84;
      font-size:10px; }
  table.oe-mix th.src { text-align:left; }
  table.oe-mix td { padding:6.5px 4px; border-bottom:1px solid #F3F1EA;
      text-align:right; color:#1C1C1A; font-weight:500;
      font-variant-numeric:tabular-nums; }
  table.oe-mix td.src { text-align:left; color:#57554F; }
  table.oe-mix td.src .sq { display:inline-block; width:11px; height:11px;
      border-radius:2px; margin:0 9px -1px 0; }
  table.oe-mix tr.tot td { border-top:1.5px solid #1C1C1A; border-bottom:none;
      font-weight:700; padding-top:9px; }
  table.oe-mix tr.tot td.src { color:#1C1C1A; }

  /* ---- facilities dark footer strip --------------------------------------- */
  .oe-facfoot { display:flex; justify-content:space-between; align-items:center;
      background:#141414; color:#fff; border-radius:4px; padding:8px 16px;
      font-size:12.5px; margin:6px 0 4px 0; }
  .oe-facfoot b { font-size:14.5px; font-weight:700; }
  .oe-facfoot .u { color:#8F8C84; font-size:11px; margin-left:4px; }

  /* ---- facility detail card ----------------------------------------------- */
  .oe-dhead { display:flex; align-items:flex-start; justify-content:space-between;
      gap:20px; padding:8px 2px 12px 2px; border-bottom:1px solid #E6E3DB; }
  .oe-dhead .name { font-size:1.65rem; font-weight:800; letter-spacing:-0.03em;
      color:#141414; line-height:1.1; }
  .oe-dhead .sub { font-size:13px; color:#57554F; margin-top:5px; }
  .oe-dhead .sub .sq { display:inline-block; width:10px; height:10px;
      border-radius:2px; margin:0 7px -1px 0; }
  .oe-dhead .cap { text-align:right; flex:0 0 auto; }
  .oe-dhead .cap .l { font-size:10px; font-weight:700; letter-spacing:.14em;
      text-transform:uppercase; color:#8F8C84; }
  .oe-dhead .cap .v { font-size:1.65rem; font-weight:800;
      letter-spacing:-0.02em; color:#141414; }
  .oe-dhead .cap .v small { font-size:0.95rem; color:#8F8C84; font-weight:700; }
  .oe-dstats { display:flex; flex-wrap:wrap; padding:12px 2px 6px 2px; }
  .oe-dstats .d { padding:0 26px 8px 0; margin-right:26px;
      border-right:1px solid #F0EEE7; }
  .oe-dstats .d:last-child { border-right:none; }
  .oe-dstats .l { font-size:10px; font-weight:700; letter-spacing:.13em;
      text-transform:uppercase; color:#8F8C84; }
  .oe-dstats .v { font-size:1.18rem; font-weight:700; color:#141414;
      margin-top:3px; font-variant-numeric:tabular-nums; }

  /* ---- pipeline strip ------------------------------------------------------ */
  .oe-flow { display:flex; align-items:stretch; gap:0; overflow-x:auto;
      padding:4px 0 8px 0; }
  .oe-node { flex:1 1 0; min-width:150px; background:#FFFFFF;
      border:1px solid #E6E3DB; border-radius:6px; padding:13px 15px; }
  .oe-node .nn { display:flex; align-items:center; gap:8px; }
  .oe-node .nn .num { width:20px; height:20px; border-radius:50%;
      background:#141414; color:#fff; font-size:10.5px; font-weight:700;
      display:flex; align-items:center; justify-content:center; }
  .oe-node .nn .sq { width:9px; height:9px; border-radius:2px; }
  .oe-node .nt { font-size:16.5px; font-weight:700; color:#141414;
      margin:9px 0 5px 0; letter-spacing:-0.01em; }
  .oe-node .nd { font-size:12.5px; line-height:1.5; color:#8F8C84; }
  .oe-arrow { display:flex; align-items:center; justify-content:center;
      color:#141414; font-size:20px; font-weight:700; padding:0 6px;
      flex:0 0 auto; }

  /* ---- chips, stage cards, run block --------------------------------------- */
  .oe-chip { display:inline-block; background:#fff; color:#57554F;
      border:1px solid #E0DDD4; border-radius:999px; padding:4px 13px;
      font-size:12px; font-weight:600; margin:0 6px 6px 0; }
  .oe-stage { background:#FFFFFF; border:1px solid #E6E3DB; border-radius:6px;
      padding:16px 18px; height:100%; }
  .oe-stage .num { display:flex; align-items:center; gap:9px; }
  .oe-stage .num .c { width:27px; height:27px; border-radius:50%;
      background:#141414; color:#fff; font-size:13px; font-weight:700;
      display:flex; align-items:center; justify-content:center; }
  .oe-stage .num .k { font-size:12px; font-weight:700; letter-spacing:.16em;
      text-transform:uppercase; }
  .oe-stage h4 { margin:10px 0 6px 0; font-size:17.5px; font-weight:700;
      color:#141414; letter-spacing:-0.01em; }
  .oe-stage p { font-size:13.5px; line-height:1.55; color:#57554F; margin:0; }

  .oe-run { background:#141414; border-radius:6px; padding:20px 24px;
      margin-top:4px; }
  .oe-run .step { display:flex; align-items:flex-start; gap:14px; padding:7px 0; }
  .oe-run .sn { flex:0 0 auto; width:22px; height:22px; border-radius:50%;
      background:rgba(255,255,255,.14); color:#D8D5CC; font-size:11px;
      font-weight:700; display:flex; align-items:center; justify-content:center;
      margin-top:2px; }
  .oe-run .sc code { color:#F3F1EA; font-size:12.5px;
      font-family:Consolas, monospace !important; background:none; }
  .oe-run .sc .sd { color:#8F8C84; font-size:11.5px; margin-top:2px; }

  /* ---- Streamlit widget polish ---------------------------------------------- */
  [data-testid="stWidgetLabel"] p { font-size:11px; font-weight:700;
      letter-spacing:.1em; text-transform:uppercase; color:#8F8C84; }
  .stMultiSelect [data-baseweb="tag"] { background:#141414; }
  .stRadio [role="radiogroup"] label p, .stSelectbox div { font-size:13.5px; }

  .oe-footer { display:flex; justify-content:space-between; flex-wrap:wrap;
      gap:8px; color:#8F8C84; font-size:12.5px; border-top:1px solid #E6E3DB;
      padding-top:18px; margin-top:36px; }
  .oe-footer a { color:#1C1C1A; font-weight:600; text-decoration:none;
      border-bottom:1px solid #C9C6BD; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=600, show_spinner=False)
def q(sql: str) -> pd.DataFrame:
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


@st.cache_data(ttl=600, show_spinner=False)
def au_stations() -> pd.DataFrame:
    if not AU_STATIONS_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(AU_STATIONS_CSV)


def marts_available() -> bool:
    try:
        got = q("select count(*) n from information_schema.tables "
                "where table_name = 'fct_facility_interval'")
        return int(got["n"].iloc[0]) > 0
    except Exception:
        return False


PLOT_CONFIG = {"displayModeBar": False}


def oe_fig(fig, height=380, legend=True):
    """OpenElectricity chart chrome: white surface, dotted grid, quiet axes."""
    fig.update_layout(
        height=height, margin=dict(l=4, r=8, t=12, b=8),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="DM Sans, Segoe UI, sans-serif", color=INK_2, size=12),
        hoverlabel=dict(bgcolor="white", bordercolor=BORDER,
                        font_family="DM Sans, Segoe UI, sans-serif",
                        font_size=12.5, font_color=INK),
        legend=dict(orientation="h", yanchor="top", y=-0.14, x=0,
                    font=dict(size=11.5, color=INK_2), title=None,
                    traceorder="normal", itemsizing="constant") if legend else None,
        showlegend=legend,
    )
    fig.update_xaxes(gridcolor=GRID, griddash="dot", zeroline=False,
                     linecolor=BORDER, tickfont=dict(size=11, color=MUTED),
                     title_font=dict(size=11.5, color=MUTED))
    fig.update_yaxes(gridcolor=GRID, griddash="dot", zerolinecolor=BORDER,
                     zerolinewidth=1, linecolor=BORDER, showline=False,
                     tickfont=dict(size=11, color=MUTED),
                     title_font=dict(size=11.5, color=MUTED))
    return fig


def add_night_bands(fig, t0, t1) -> None:
    """Subtle grey night shading (19:00-06:30 local), like the OE tracker."""
    day = pd.Timestamp(t0).normalize() - pd.Timedelta(days=1)
    end = pd.Timestamp(t1)
    while day <= end:
        x0 = max(day + pd.Timedelta(hours=19), pd.Timestamp(t0))
        x1 = min(day + pd.Timedelta(hours=30.5), end)
        if x1 > x0:
            fig.add_vrect(x0=x0, x1=x1, fillcolor="rgba(20,20,20,0.035)",
                          line_width=0, layer="below")
        day += pd.Timedelta(days=1)


def rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def fmt(v, spec=",.0f", suffix="", dash="—"):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return dash
    return format(v, spec) + suffix


def chead(title: str, unit: str = "", right: str = "") -> None:
    """OE chart-card header row:  **Title** unit ............ right."""
    st.markdown(f'<div class="oe-chead"><span class="t">{title}</span>'
                f'<span class="u">{unit}</span><span class="r">{right}</span></div>',
                unsafe_allow_html=True)


def sect(kicker: str, statement: str, body: str | None = None) -> None:
    b = f'<div class="b">{body}</div>' if body else ""
    st.markdown(f'<div class="oe-sect"><div class="k">{kicker}</div>'
                f'<div class="s">{statement}</div>{b}</div>',
                unsafe_allow_html=True)


def insight(text: str) -> None:
    st.markdown(f'<div class="oe-ins"><span class="sq"></span>'
                f'<span class="tx">{text}</span></div>', unsafe_allow_html=True)


def stat_tile(col, label, value, sub, unit=""):
    u = f" <small>{unit}</small>" if unit else ""
    col.markdown(f'<div class="oe-stat"><div class="l">{label}</div>'
                 f'<div class="v">{value}{u}</div><div class="s">{sub}</div></div>',
                 unsafe_allow_html=True)


def pipeline_strip() -> None:
    """Horizontal, minimal view of how the data pipeline runs end-to-end."""
    nodes = [
        ("1", "Source", "source",
         "OpenElectricity v4 REST API — 5-min facility power & CO2e + market data"),
        ("2", "Ingest", "ingest",
         "Batched, retried, budgeted client writing an immutable JSON cache"),
        ("3", "Transform & gate", "transform",
         "pandas cleans, aggregates & geocodes; a 9-check quality gate blocks bad data"),
        ("4", "Warehouse", "warehouse",
         "Normalised DuckDB schema with spatial geometry points"),
        ("5", "Model & test", "model",
         "dbt builds a tested star schema — 47 nodes, 39 data tests"),
        ("6", "Serve", "serve",
         "This dashboard + an MQTT live map, reading only tested marts"),
    ]
    html = ['<div class="oe-flow">']
    for i, (n, title, key, desc) in enumerate(nodes):
        c = STAGE[key]
        html.append(
            f'<div class="oe-node">'
            f'<div class="nn"><span class="num">{n}</span>'
            f'<span class="sq" style="background:{c}"></span></div>'
            f'<div class="nt">{title}</div><div class="nd">{desc}</div></div>')
        if i < len(nodes) - 1:
            html.append('<div class="oe-arrow">&#8594;</div>')
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)


# Minimal stroke icons for the stage walkthrough (24x24, currentColor).
STAGE_ICONS = {
    "cloud": '<path d="M7 18a4.5 4.5 0 0 1-.36-8.99A6 6 0 0 1 18.3 10.6 4 4 0 0 1 17.5 18Z"/>',
    "download": ('<path d="M12 3v10m0 0 4-4m-4 4-4-4"/>'
                 '<path d="M4 17v2.2A1.8 1.8 0 0 0 5.8 21h12.4a1.8 1.8 0 0 0 '
                 '1.8-1.8V17"/>'),
    "funnel": '<path d="M3 5h18l-7 8.5V19l-4 2v-7.5L3 5Z"/>',
    "pin": ('<path d="M12 21s-7-5.6-7-11a7 7 0 0 1 14 0c0 5.4-7 11-7 11Z"/>'
            '<circle cx="12" cy="10" r="2.6"/>'),
    "db": ('<ellipse cx="12" cy="5" rx="8" ry="3"/>'
           '<path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/>'
           '<path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>'),
    "flask": ('<path d="M10 2v6.5L4.6 18a2.4 2.4 0 0 0 2.1 3.5h10.6a2.4 2.4 0 '
              '0 0 2.1-3.5L14 8.5V2"/><path d="M8.5 2h7"/><path d="M7 15h10"/>'),
    "chart": ('<rect x="3" y="4" width="18" height="13" rx="2"/>'
              '<path d="M8 13v-3M12 13V8M16 13v-5"/><path d="M9 21h6M12 17v4"/>'),
}


def stage_scrolly() -> None:
    """Scroll-driven stage walkthrough: each stage lights up (1 -> 6) as it
    crosses the middle of the viewport, like openelectricity's storytelling
    sections. Runs in a components iframe so the IntersectionObserver works."""
    stages = [
        ("#4582B4", "Ingest", "download", "Respect the API, cache everything",
         "Batched requests, retries only on 429/5xx, a hard daily budget, and "
         "an immutable raw JSON cache — the API is hit at most once per window."),
        ("#1D7A7A", "Transform", "funnel", "668k rows, analysis-ready",
         "Strict UTC windowing, metric standardisation and unit-to-facility "
         "aggregation produce one consolidated CSV — the data contract."),
        ("#B46813", "Geocode & gate", "pin", "Trust, but verify",
         "Coordinates validated against an AU bounding box, backfilled from "
         "region centroids; 9 hard checks refuse bad data before load."),
        ("#3145CE", "Warehouse", "db", "A real schema, not a CSV dump",
         "A normalised DuckDB schema with spatial points — zero-ops, embedded "
         "and columnar-fast."),
        ("#7C3AED", "Model & test", "flask", "Marts with 39 data tests",
         "Staging views feed a star schema of marts; 47 dbt nodes pass. The "
         "dashboard reads only tested marts."),
        ("#417505", "Orchestrate & serve", "chart", "One graph, two surfaces",
         "15 Dagster assets on a daily schedule; served by this app and an "
         "MQTT-to-Dash live map."),
    ]
    rows = []
    for i, (c, label, icon, title, body) in enumerate(stages, start=1):
        last = ' style="visibility:hidden"' if i == len(stages) else ""
        rows.append(f"""
        <div class="row">
          <div class="rail">
            <div class="num">{i}</div>
            <div class="line"{last}></div>
          </div>
          <div class="ic" style="color:{c}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.7" stroke-linecap="round"
                 stroke-linejoin="round">{STAGE_ICONS[icon]}</svg>
          </div>
          <div class="tx">
            <div class="k" style="color:{c}">Stage {i} &middot; {label}</div>
            <h3>{title}</h3>
            <p>{body}</p>
          </div>
        </div>""")
    html = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700;9..40,800&display=swap');
      body { margin:0; background:#FAF9F6;
             font-family:'DM Sans','Segoe UI',system-ui,sans-serif; }
      .row { display:flex; gap:24px; align-items:flex-start;
             padding:16px 8px 0 8px; opacity:.32; transform:translateY(10px);
             transition:opacity .45s ease, transform .45s ease; }
      .row.on { opacity:1; transform:none; }
      .rail { display:flex; flex-direction:column; align-items:center;
              flex:0 0 46px; }
      .num { width:44px; height:44px; border-radius:50%; background:#fff;
             border:2px solid #C9C6BD; color:#8F8C84; font-size:19px;
             font-weight:800; display:flex; align-items:center;
             justify-content:center; transition:all .4s ease; }
      .row.on .num { background:#141414; border-color:#141414; color:#fff;
             transform:scale(1.08); }
      .line { width:2px; flex:1 1 auto; min-height:48px; background:#E0DDD4;
             margin-top:8px; }
      .ic { flex:0 0 42px; margin-top:3px; opacity:.55; transition:opacity .4s; }
      .row.on .ic { opacity:1; }
      .ic svg { width:38px; height:38px; }
      .tx { padding-bottom:20px; }
      .tx .k { font-size:11px; font-weight:700; letter-spacing:.18em;
             text-transform:uppercase; }
      .tx h3 { font-size:1.3rem; font-weight:800; letter-spacing:-0.02em;
             color:#141414; margin:5px 0 6px 0; }
      .tx p { font-size:13.5px; line-height:1.6; color:#57554F; margin:0;
             max-width:640px; }
    </style>
    """ + "".join(rows) + """
    <script>
      const rows = Array.from(document.querySelectorAll('.row'));
      rows[0].classList.add('on');
      if ('IntersectionObserver' in window) {
        const io = new IntersectionObserver((entries) => {
          entries.forEach(e => e.target.classList.toggle('on', e.isIntersecting));
        }, { root: null, rootMargin: '-30% 0px -30% 0px', threshold: 0 });
        rows.forEach(r => io.observe(r));
      } else {
        rows.forEach(r => r.classList.add('on'));
      }
    </script>"""
    components.html(html, height=800, scrolling=False)


# --------------------------------------------------------------------------- #
# Guard + shared data
# --------------------------------------------------------------------------- #
if not marts_available():
    st.error("dbt marts not found. Run:\n\n```\npython -m gridpulse.pipeline\n"
             "dbt build --project-dir dbt --profiles-dir dbt\n```")
    st.stop()

region = q("select * from main_marts.agg_region_intensity order by energy_mwh desc")
window = q("select min(interval_ts) t0, max(interval_ts) t1, count(*) n "
           "from main_marts.fct_facility_interval")
N_ROWS = int(window["n"].iloc[0])
T0, T1 = window["t0"].iloc[0], window["t1"].iloc[0]

facilities = q(f"""
    select
        d.facility_code, d.facility_name, d.network_region, d.state,
        d.fueltech_id, {FUEL_GROUP_SQL.replace('fueltech_id', 'd.fueltech_id')} as fuel_group,
        d.fuel_category, d.capacity_registered_mw, d.lat, d.lon,
        count(f.obs_id)        as n_obs,
        avg(f.power_mw)        as avg_power_mw,
        max(f.power_mw)        as peak_power_mw,
        sum(f.energy_mwh)      as energy_mwh,
        sum(f.emissions_tco2e) as emissions_tco2e,
        case when sum(f.energy_mwh) > 0
             then sum(f.emissions_tco2e) / sum(f.energy_mwh) end as intensity
    from main_marts.dim_facility d
    left join main_marts.fct_facility_interval f using (facility_id)
    group by all
""")
_missing = facilities["lat"].isna() | facilities["lon"].isna()
facilities["geocode_source"] = _missing.map({True: "region centroid",
                                             False: "API catalogue"})
facilities.loc[_missing, "lat"] = facilities.loc[_missing, "network_region"].map(
    lambda r: REGION_CENTROID.get(r, (None, None))[0])
facilities.loc[_missing, "lon"] = facilities.loc[_missing, "network_region"].map(
    lambda r: REGION_CENTROID.get(r, (None, None))[1])
_hours = max((T1 - T0).total_seconds() / 3600.0, 1.0)
facilities["capacity_factor"] = (
    facilities["energy_mwh"]
    / (facilities["capacity_registered_mw"].where(facilities["capacity_registered_mw"] > 0)
       * _hours))

mix = q(f"""
    select {FUEL_GROUP_SQL} as fuel_group,
           sum(energy_mwh)      as energy_mwh,
           sum(emissions_tco2e) as emissions_tco2e
    from main_marts.fct_facility_interval
    group by 1 order by energy_mwh desc
""")

tot_energy = region["energy_mwh"].sum()
tot_emis = region["emissions_tco2e"].sum()
overall_int = tot_emis / tot_energy if tot_energy else 0
renew_e = mix.loc[mix.fuel_group.isin(RENEWABLE_GROUPS), "energy_mwh"].sum()
fossil_e = mix.loc[mix.fuel_group.isin(FOSSIL_GROUPS), "energy_mwh"].sum()
renew_share = renew_e / tot_energy if tot_energy else 0
fossil_share = fossil_e / tot_energy if tot_energy else 0
n_generating = int((facilities["n_obs"] > 0).sum())
WIN_DAYS = max(1, round((T1 - T0).total_seconds() / 86400))
_t0, _t1 = pd.Timestamp(T0), pd.Timestamp(T1)
if _t0.strftime("%b %Y") == _t1.strftime("%b %Y"):
    _win = f'{_t0.strftime("%d")}&ndash;{_t1.strftime("%d %b %Y")}'
else:
    _win = f'{_t0.strftime("%d %b %Y")} &ndash; {_t1.strftime("%d %b %Y")}'
_span = "One week" if WIN_DAYS <= 8 else f"{WIN_DAYS} days"

# --------------------------------------------------------------------------- #
# Top bar + hero
# --------------------------------------------------------------------------- #
PULSE = ("<svg width='22' height='14' viewBox='0 0 22 14' fill='none'>"
         "<path d='M1 7h4l3-6 4 12 3-6h6' stroke='#41A21A' stroke-width='2.4' "
         "stroke-linecap='round' stroke-linejoin='round'/></svg>")

st.markdown(
    f'<div class="oe-topbar">'
    f'<div class="oe-wordmark">Grid{PULSE}Pulse</div></div>',
    unsafe_allow_html=True)

_tech = ["Python", "pandas", "DuckDB", "dbt", "Dagster", "Streamlit",
         "Plotly", "MQTT", "pytest"]


def hero() -> None:
    """The headline hero — shown only on the Overview tab."""
    st.markdown(
        f'<div class="oe-hero">'
        f'<div class="left">'
        f'<div class="oe-kicker">End-to-end data engineering &middot; data '
        f'OpenElectricity API (CC-BY 4.0) &middot; window {_win} '
        f'({WIN_DAYS} days)</div>'
        f'<h1 class="oe-big">{_span} of Australia&rsquo;s electricity,<br>'
        f'traced from API to insight.</h1>'
        f'<p class="oe-lede">GridPulse ingests <b>{N_ROWS:,} five-minute '
        f'readings</b> from all <b>{len(facilities):,} generators</b> on the '
        f'National Electricity Market, cleans and geocodes them, refuses bad '
        f'data at a 9-check quality gate, warehouses them in DuckDB and models '
        f'them into <b>dbt marts with 39 automated tests</b>. Everything on '
        f'this page is read from those tested marts &mdash; never from raw '
        f'data.</p>'
        f'<div class="oe-herochips">'
        + "".join(f"<span>{t}</span>" for t in _tech)
        + f'</div></div>'
        f'<div class="oe-split">'
        f'<div><div class="row"><span class="sq" style="background:#131313">'
        f'</span><span class="lab">FOSSILS</span></div>'
        f'<div class="num">{fossil_share*100:.1f}<small>%</small></div></div>'
        f'<div><div class="row"><span class="sq" style="background:#417505">'
        f'</span><span class="lab">RENEWABLES</span></div>'
        f'<div class="num">{renew_share*100:.1f}<small>%</small></div></div>'
        f'<div style="font-size:10.5px;color:#8F8C84;letter-spacing:.08em;">'
        f'SHARE OF ENERGY &middot; {WIN_DAYS}-DAY WINDOW</div>'
        f'</div></div>',
        unsafe_allow_html=True)


tab_overview, tab_map, tab_analysis, tab_story = st.tabs(
    ["Overview", "Facilities", "Analysis", "About"])

# =========================================================================== #
# OVERVIEW
# =========================================================================== #
with tab_overview:
    hero()
    sect("The grid at a glance",
         f"{tot_energy/1e6:,.1f} terawatt-hours in {WIN_DAYS} days — "
         f"and where the carbon sits.",
         "Six headline measures for the loaded window, aggregated from the "
         "5-minute facility readings in the tested marts.")
    k = st.columns(6)
    stat_tile(k[0], "Total energy", f"{tot_energy/1e6:,.2f}",
              "generated in the window", "TWh")
    stat_tile(k[1], "Emissions", f"{tot_emis/1e6:,.2f}",
              "CO2-equivalent", "Mt")
    stat_tile(k[2], "Grid intensity", f"{overall_int:.3f}",
              "tonnes CO2e per MWh", "t/MWh")
    stat_tile(k[3], "Renewables", f"{renew_share*100:,.1f}",
              "share of energy", "%")
    stat_tile(k[4], "NEM regions", f"{len(region)}", "QLD NSW VIC SA TAS")
    stat_tile(k[5], "Generating sites", f"{n_generating:,}",
              f"of {len(facilities):,} facilities")

    # ---- generation over the week ------------------------------------- #
    sect("Generation",
         "Solar carves a midday wave; coal never leaves the floor.",
         "Hourly average output by fuel technology, stacked. Shaded bands are "
         "night-time (19:00&ndash;06:30 local) &mdash; watch solar switch off "
         "and gas, hydro and storage pick up the evening.")
    hourly = q(f"""
        select date_trunc('hour', interval_local) as ts,
               {FUEL_GROUP_SQL} as fuel_group,
               sum(energy_mwh) / 1000.0 as gwh
        from main_marts.fct_facility_interval
        group by 1, 2 order by 1
    """)
    wide = (hourly.pivot(index="ts", columns="fuel_group", values="gwh")
                  .fillna(0.0).sort_index())
    av_gw = wide.clip(lower=0).sum(axis=1).mean()
    with st.container(border=True):
        chead("Generation", "GW", f"Av. <b>{av_gw:,.1f} GW</b>")
        fig = go.Figure()
        for grp in [g for g in FUEL_GROUP_ORDER if g in wide.columns]:
            fig.add_trace(go.Scatter(
                x=wide.index, y=wide[grp].clip(lower=0), name=grp, mode="lines",
                stackgroup="gen", line=dict(width=0),
                fillcolor=FUEL_GROUP_COLOURS[grp],
                hovertemplate="%{y:,.2f} GW"))
        add_night_bands(fig, wide.index.min(), wide.index.max())
        fig.update_layout(hovermode="x unified",
                          xaxis=dict(dtick=86400000, tickformat="%a %d"))
        st.plotly_chart(oe_fig(fig, 400), use_container_width=True,
                        config=PLOT_CONFIG)
    solar_peak = wide["Solar"].max() if "Solar" in wide.columns else 0
    coal_min = wide["Coal"].min() if "Coal" in wide.columns else 0
    wind_max = wide["Wind"].max() if "Wind" in wide.columns else 0
    insight(f"Solar peaks near <b>{solar_peak:,.1f} GW</b> every midday while "
            f"coal never drops below <b>{coal_min:,.1f} GW</b> — an inflexible "
            f"baseload floor under a variable renewable wave. Wind swings "
            f"independently of the sun (up to <b>{wind_max:,.1f} GW</b>), which "
            f"is exactly why storage and flexible gas matter for balancing "
            f"the grid.")

    # ---- energy mix: summary table + donuts ---------------------------- #
    sect("Energy mix",
         "Energy is shared across eight fuels — the carbon is not.",
         "The table breaks the loaded window down by source, exactly as "
         "OpenElectricity reports it: energy contributed, share of total, and "
         "each source's share of the CO2e.")
    mixed = mix.set_index("fuel_group")
    rows_html = []
    for g in [g for g in FUEL_GROUP_ORDER if g in mixed.index]:
        e = mixed.loc[g, "energy_mwh"]
        em = mixed.loc[g, "emissions_tco2e"]
        rows_html.append(
            f'<tr><td class="src"><span class="sq" '
            f'style="background:{FUEL_GROUP_COLOURS[g]}"></span>{g}</td>'
            f'<td>{e/1000:,.0f}</td><td>{e/tot_energy*100:,.1f}%</td>'
            f'<td>{em/1000:,.1f}</td><td>{(em/tot_emis*100 if tot_emis else 0):,.1f}%</td></tr>')
    renew_em = mixed.loc[mixed.index.isin(RENEWABLE_GROUPS), "emissions_tco2e"].sum()
    fossil_em = mixed.loc[mixed.index.isin(FOSSIL_GROUPS), "emissions_tco2e"].sum()
    for label, e, em in [("Renewables", renew_e, renew_em),
                         ("Fossils", fossil_e, fossil_em)]:
        rows_html.append(
            f'<tr class="tot"><td class="src">{label}</td>'
            f'<td>{e/1000:,.0f}</td><td>{e/tot_energy*100:,.1f}%</td>'
            f'<td>{em/1000:,.1f}</td><td>{(em/tot_emis*100 if tot_emis else 0):,.1f}%</td></tr>')
    mix_table = (
        '<table class="oe-mix">'
        '<tr><th class="src">Sources</th>'
        '<th>Energy<small>GWh</small></th><th>Contribution<small>to energy</small></th>'
        '<th>Emissions<small>ktCO2e</small></th><th>Contribution<small>to CO2e</small></th></tr>'
        + "".join(rows_html) + "</table>")

    c1, c2 = st.columns([1.15, 1])
    with c1:
        with st.container(border=True):
            chead("Sources", f"{WIN_DAYS}-day window",
                  f"<b>{tot_energy/1e6:,.2f} TWh</b> · <b>{tot_emis/1e6:,.2f} Mt</b>")
            st.markdown(mix_table, unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            chead("Share of energy vs share of emissions", "",
                  "outer ring energy · inner emissions")
            de = mix[mix["energy_mwh"] > 0]
            dm = mix[mix["emissions_tco2e"] > 0]
            fig = go.Figure()
            fig.add_trace(go.Pie(
                labels=de["fuel_group"], values=de["energy_mwh"],
                hole=0.62, sort=False, direction="clockwise",
                marker=dict(colors=[FUEL_GROUP_COLOURS.get(g, "#A8A69E")
                                    for g in de["fuel_group"]],
                            line=dict(color="#fff", width=2)),
                textinfo="none", domain=dict(x=[0, 1], y=[0, 1]),
                hovertemplate="<b>%{label}</b><br>Energy: %{value:,.0f} MWh"
                              "<br>Share: %{percent}<extra>energy</extra>"))
            fig.add_trace(go.Pie(
                labels=dm["fuel_group"], values=dm["emissions_tco2e"],
                hole=0.55, sort=False, direction="clockwise", showlegend=False,
                marker=dict(colors=[FUEL_GROUP_COLOURS.get(g, "#A8A69E")
                                    for g in dm["fuel_group"]],
                            line=dict(color="#fff", width=2)),
                textinfo="none", domain=dict(x=[0.24, 0.76], y=[0.24, 0.76]),
                hovertemplate="<b>%{label}</b><br>Emissions: %{value:,.0f} tCO2e"
                              "<br>Share: %{percent}<extra>emissions</extra>"))
            # The colour key is the summary table alongside; the ring labels
            # below disambiguate outer (energy) from inner (emissions).
            fig.update_layout(
                showlegend=False, margin=dict(l=4, r=8, t=6, b=8),
                annotations=[dict(text="ENERGY", x=0.5, y=0.545, showarrow=False,
                                  font=dict(size=9.5, color=MUTED, weight=700)),
                             dict(text="CO₂e", x=0.5, y=0.455, showarrow=False,
                                  font=dict(size=9.5, color=MUTED))])
            st.plotly_chart(oe_fig(fig, 392, legend=False),
                            use_container_width=True, config=PLOT_CONFIG)
            st.markdown(
                '<div style="display:flex;gap:16px;justify-content:center;'
                'flex-wrap:wrap;padding:2px 0 6px 0;font-size:11px;'
                'color:#57554F;">'
                + "".join(
                    f'<span style="white-space:nowrap"><span style="display:'
                    f'inline-block;width:9px;height:9px;border-radius:2px;'
                    f'background:{FUEL_GROUP_COLOURS[g]};margin-right:5px"></span>'
                    f'{g}</span>'
                    for g in FUEL_GROUP_ORDER if g in set(de["fuel_group"]))
                + '</div>', unsafe_allow_html=True)
    coal_e = mixed.loc["Coal", "energy_mwh"] if "Coal" in mixed.index else 0
    coal_c = mixed.loc["Coal", "emissions_tco2e"] if "Coal" in mixed.index else 0
    insight(f"Coal supplies <b>{coal_e/tot_energy*100:,.0f}%</b> of the energy "
            f"but <b>{coal_c/tot_emis*100:,.0f}%</b> of the emissions, while "
            f"renewables ({renew_share*100:,.1f}% of energy) emit almost "
            f"nothing — hover the rings: the outer (energy) is diverse, the "
            f"inner (emissions) is nearly all black. Cutting carbon is about "
            f"displacing one fuel.")

    # ---- wholesale market ---------------------------------------------- #
    sect("The market",
         "Demand sets the rhythm; price rides the evening ramp.",
         "NEM-wide operational demand and volume-weighted spot price at "
         "5-minute resolution — two single-axis charts, deliberately never a "
         "dual axis.")
    market = q("select interval_ts, price_aud_mwh, demand_mw "
               "from main_staging.stg_market order by interval_ts")
    if market.empty:
        st.info("No market series loaded.")
    else:
        cma, cmb = st.columns(2)
        with cma:
            with st.container(border=True):
                chead("Demand", "MW",
                      f"Av. <b>{market['demand_mw'].mean():,.0f} MW</b>")
                fig = go.Figure(go.Scatter(
                    x=market["interval_ts"], y=market["demand_mw"], mode="lines",
                    line=dict(color=BLACK, width=1.3),
                    hovertemplate="%{x|%a %d %b %H:%M}<br>Demand: "
                                  "<b>%{y:,.0f} MW</b><extra></extra>"))
                add_night_bands(fig, market["interval_ts"].min(),
                                market["interval_ts"].max())
                fig.update_layout(xaxis=dict(dtick=86400000, tickformat="%a %d"))
                st.plotly_chart(oe_fig(fig, 280, legend=False),
                                use_container_width=True, config=PLOT_CONFIG)
        with cmb:
            with st.container(border=True):
                chead("Price", "$/MWh",
                      f"Av. <b>${market['price_aud_mwh'].mean():,.2f}</b>")
                fig = go.Figure(go.Scatter(
                    x=market["interval_ts"], y=market["price_aud_mwh"],
                    mode="lines", line=dict(color=RED, width=1.2),
                    line_shape="hv",
                    hovertemplate="%{x|%a %d %b %H:%M}<br>Price: "
                                  "<b>$%{y:,.2f}/MWh</b><extra></extra>"))
                add_night_bands(fig, market["interval_ts"].min(),
                                market["interval_ts"].max())
                fig.update_layout(xaxis=dict(dtick=86400000, tickformat="%a %d"))
                st.plotly_chart(oe_fig(fig, 280, legend=False),
                                use_container_width=True, config=PLOT_CONFIG)
        pk = market.loc[market["demand_mw"].idxmax()]
        lo = market.loc[market["demand_mw"].idxmin()]
        ph = market.loc[market["price_aud_mwh"].idxmax()]
        stats_tbl = (
            '<table class="oe-mix">'
            '<tr><th class="src">Stats</th><th>Min.</th><th>Max.</th></tr>'
            f'<tr><td class="src">Demand <span style="color:#8F8C84">MW</span></td>'
            f'<td>{lo["demand_mw"]:,.0f}<br><small style="color:#8F8C84">'
            f'{pd.Timestamp(lo["interval_ts"]).strftime("%a %d %b, %H:%M")}</small></td>'
            f'<td>{pk["demand_mw"]:,.0f}<br><small style="color:#8F8C84">'
            f'{pd.Timestamp(pk["interval_ts"]).strftime("%a %d %b, %H:%M")}</small></td></tr>'
            f'<tr><td class="src">Price <span style="color:#8F8C84">$/MWh</span></td>'
            f'<td>{market["price_aud_mwh"].min():,.2f}</td>'
            f'<td>{market["price_aud_mwh"].max():,.2f}<br>'
            f'<small style="color:#8F8C84">'
            f'{pd.Timestamp(ph["interval_ts"]).strftime("%a %d %b, %H:%M")}</small></td></tr>'
            '</table>')
        sc1, _ = st.columns([1, 1])
        with sc1:
            with st.container(border=True):
                st.markdown(stats_tbl, unsafe_allow_html=True)
        insight(f"Demand swings from <b>{lo['demand_mw']:,.0f}</b> to "
                f"<b>{pk['demand_mw']:,.0f} MW</b> inside the window and peaks on "
                f"{pd.Timestamp(pk['interval_ts']).strftime('%A at %H:%M')}. "
                f"Price is far spikier than demand — it averages "
                f"<b>${market['price_aud_mwh'].mean():,.0f}/MWh</b> but tops out "
                f"at <b>${market['price_aud_mwh'].max():,.0f}/MWh</b> during the "
                f"evening ramp, when solar has left and gas sets the price.")

# =========================================================================== #
# FACILITIES
# =========================================================================== #
with tab_map:
    sect("Facilities",
         "Every registered NEM generator — click one to open it.",
         "All facilities in the market, including the "
         f"{len(facilities)-n_generating} that sat idle in the window. Click "
         "a dot on the map or a row in the table to open the "
         "OpenElectricity-style facility card below: capacity, output "
         "against its registered limit, and emissions.")

    au = au_stations()
    layer = st.radio(
        "Data layer",
        [f"NEM facilities — live week ({len(facilities):,})",
         f"All Australian stations ({len(au):,})" if not au.empty
         else "All Australian stations (unavailable)"],
        horizontal=True, label_visibility="collapsed")

    # ------------------------------------------------------------------ #
    # Layer 1 — NEM facilities, OpenElectricity explorer layout
    # ------------------------------------------------------------------ #
    if layer.startswith("NEM"):
        f0, f1, f2, f3, f4 = st.columns([1.4, 1.3, 1.5, 1.3, 0.9])
        search = f0.text_input("Filter by name", placeholder="Filter by name…")
        sel_regions = f1.multiselect(
            "Region", sorted(facilities["network_region"].unique()),
            placeholder="All regions")
        sel_fuels = f2.multiselect(
            "Technology", [g for g in FUEL_GROUP_ORDER
                           if g in set(facilities["fuel_group"])],
            placeholder="All technologies")
        size_by = f3.selectbox(
            "Size markers by",
            ["Capacity (MW)", "Avg power (MW)", "Energy (MWh)",
             "Emissions (tCO2e)"])
        show_idle = f4.toggle("Include idle", value=True)

        fmap = facilities.copy()
        if search:
            fmap = fmap[fmap["facility_name"].str.contains(search, case=False,
                                                           na=False)]
        if sel_regions:
            fmap = fmap[fmap["network_region"].isin(sel_regions)]
        if sel_fuels:
            fmap = fmap[fmap["fuel_group"].isin(sel_fuels)]
        if not show_idle:
            fmap = fmap[fmap["n_obs"] > 0]

        size_col = {"Capacity (MW)": "capacity_registered_mw",
                    "Avg power (MW)": "avg_power_mw",
                    "Energy (MWh)": "energy_mwh",
                    "Emissions (tCO2e)": "emissions_tco2e"}[size_by]
        raw = pd.to_numeric(fmap[size_col], errors="coerce").abs().fillna(0.0)
        s = raw ** 0.5
        floor = (s.max() * 0.30) if s.max() > 0 else 1.0
        fmap["_size"] = s.clip(lower=floor) + 2.0

        fmap["_h_cap"] = fmap["capacity_registered_mw"].map(lambda v: fmt(v, ",.1f", " MW"))
        fmap["_h_avg"] = fmap["avg_power_mw"].map(lambda v: fmt(v, ",.1f", " MW"))
        fmap["_h_en"] = fmap["energy_mwh"].map(lambda v: fmt(v, ",.0f", " MWh"))
        fmap["_h_em"] = fmap["emissions_tco2e"].map(lambda v: fmt(v, ",.0f", " tCO2e"))
        fmap["_h_obs"] = fmap["n_obs"].map(
            lambda v: f"{int(v):,} obs" if v else "no data in window")

        col_tbl, col_map = st.columns([1, 1.25])
        with col_tbl:
            tview = (fmap[["facility_name", "network_region", "fueltech_id",
                           "capacity_registered_mw", "facility_code"]]
                     .sort_values("capacity_registered_mw", ascending=False)
                     .reset_index(drop=True))
            tbl_event = st.dataframe(
                tview.drop(columns=["facility_code"]),
                hide_index=True, use_container_width=True, height=560,
                on_select="rerun", selection_mode="single-row",
                key="fac_table",
                column_config={
                    "facility_name": "Name",
                    "network_region": st.column_config.TextColumn(
                        "Region", width="small"),
                    "fueltech_id": st.column_config.TextColumn(
                        "Tech", width="small"),
                    "capacity_registered_mw": st.column_config.NumberColumn(
                        "Capacity (MW)", format="%.0f"),
                })
        with col_map:
            fig = px.scatter_map(
                fmap, lat="lat", lon="lon", color="fuel_group", size="_size",
                size_max=20, zoom=3.55, center={"lat": -32.8, "lon": 145.5},
                map_style="carto-positron", height=560, opacity=0.92,
                color_discrete_map=FUEL_GROUP_COLOURS,
                category_orders={"fuel_group": FUEL_GROUP_ORDER + ["Other"]},
                custom_data=["facility_name", "facility_code", "fueltech_id",
                             "network_region", "_h_cap", "_h_avg", "_h_en",
                             "_h_em", "_h_obs", "geocode_source"],
            )
            fig.update_traces(hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "<span style='color:#8F8C84'>%{customdata[2]} · "
                "%{customdata[3]} · %{customdata[9]}</span><br>"
                "Capacity <b>%{customdata[4]}</b> · "
                "Avg <b>%{customdata[5]}</b><br>"
                "Window: <b>%{customdata[6]}</b> · <b>%{customdata[7]}</b> · "
                "%{customdata[8]}"
                "<extra></extra>"))
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                font=dict(family="DM Sans, Segoe UI, sans-serif"),
                legend=dict(orientation="h", yanchor="bottom", y=0.004, x=0.01,
                            bgcolor="rgba(255,255,255,0.9)",
                            font=dict(size=11, color=INK_2),
                            title=None, itemsizing="constant"),
                hoverlabel=dict(bgcolor="white", bordercolor=BORDER,
                                font_family="DM Sans, Segoe UI, sans-serif",
                                font_size=12.5, font_color=INK))
            map_event = st.plotly_chart(fig, use_container_width=True,
                                        on_select="rerun",
                                        selection_mode="points",
                                        key="facility_map", config=PLOT_CONFIG)
        st.markdown(
            f'<div class="oe-facfoot"><span>Facilities <b>{len(fmap):,}</b></span>'
            f'<span>Generated in window <b>{int((fmap["n_obs"] > 0).sum()):,}</b>'
            f'<span class="u">of {len(fmap):,}</span></span>'
            f'<span>Capacity <b>{fmap["capacity_registered_mw"].sum():,.0f}</b>'
            f'<span class="u">MW</span></span></div>',
            unsafe_allow_html=True)

        # ---- selection: map click or table row, most recent wins -------- #
        map_code = None
        try:
            pts = map_event.selection.points  # type: ignore[union-attr]
            if pts:
                map_code = pts[0]["customdata"][1]
        except Exception:
            map_code = None
        tbl_code = None
        try:
            rows = tbl_event.selection.rows  # type: ignore[union-attr]
            if rows:
                tbl_code = tview.iloc[rows[0]]["facility_code"]
        except Exception:
            tbl_code = None

        prev_map = st.session_state.get("_prev_map_code")
        prev_tbl = st.session_state.get("_prev_tbl_code")
        if map_code is not None and map_code != prev_map:
            st.session_state["sel_code"] = map_code
        elif tbl_code is not None and tbl_code != prev_tbl:
            st.session_state["sel_code"] = tbl_code
        st.session_state["_prev_map_code"] = map_code
        st.session_state["_prev_tbl_code"] = tbl_code

        sel_code = st.session_state.get("sel_code")
        if sel_code not in set(facilities["facility_code"]):
            sel_code = (facilities.sort_values("energy_mwh", ascending=False)
                        ["facility_code"].iloc[0])

        # ---- facility detail card (OpenElectricity style) ---------------- #
        frow = facilities.loc[facilities["facility_code"] == sel_code].iloc[0]
        fcolour = FUEL_GROUP_COLOURS.get(frow["fuel_group"], "#A8A69E")
        cap_mw = frow["capacity_registered_mw"]
        with st.container(border=True):
            st.markdown(
                f'<div class="oe-dhead">'
                f'<div><div class="name">{frow["facility_name"]}</div>'
                f'<div class="sub"><span class="sq" style="background:{fcolour}">'
                f'</span>{frow["fueltech_id"]} &middot; {frow["network_region"]} '
                f'({frow["state"]}) &middot; {frow["facility_code"]}</div></div>'
                f'<div class="cap"><div class="l">Registered capacity</div>'
                f'<div class="v">{fmt(cap_mw, ",.0f")}<small> MW</small></div>'
                f'</div></div>',
                unsafe_allow_html=True)
            cf = frow["capacity_factor"]
            st.markdown(
                '<div class="oe-dstats">'
                + "".join(
                    f'<div class="d"><div class="l">{l}</div>'
                    f'<div class="v">{v}</div></div>'
                    for l, v in [
                        ("Avg power", fmt(frow["avg_power_mw"], ",.1f", " MW")),
                        ("Peak power", fmt(frow["peak_power_mw"], ",.1f", " MW")),
                        ("Energy · window", fmt(frow["energy_mwh"], ",.0f", " MWh")),
                        ("Emissions · window", fmt(frow["emissions_tco2e"], ",.0f", " t")),
                        ("Intensity", fmt(frow["intensity"], ",.3f", " t/MWh")),
                        ("Capacity factor",
                         fmt(cf * 100 if pd.notna(cf) else None, ",.1f", "%")),
                    ])
                + '</div>', unsafe_allow_html=True)

            series = q(f"""
                select interval_local, power_mw, emissions_tco2e
                from main_marts.fct_facility_interval
                where facility_code = '{sel_code}'
                order by interval_local
            """)
            if series.empty:
                st.info("No generation recorded for this facility in the "
                        "sample window — it sat idle all week.")
            else:
                chead("Generation", "MW",
                      f"Av. <b>{series['power_mw'].mean():,.0f} MW</b>")
                fig = go.Figure(go.Scatter(
                    x=series["interval_local"], y=series["power_mw"],
                    mode="lines", line=dict(color=fcolour, width=1.1),
                    fill="tozeroy", fillcolor=rgba(fcolour, 0.22),
                    hovertemplate="%{x|%a %d %b %H:%M}<br>Power: "
                                  "<b>%{y:,.2f} MW</b><extra></extra>"))
                add_night_bands(fig, series["interval_local"].min(),
                                series["interval_local"].max())
                if pd.notna(cap_mw) and cap_mw > 0:
                    fig.add_hline(
                        y=cap_mw, line_dash="dash", line_color=RED,
                        line_width=1.1,
                        annotation_text="Registered capacity",
                        annotation_position="top right",
                        annotation_font=dict(size=10.5, color=RED))
                fig.update_layout(
                    xaxis=dict(dtick=86400000, tickformat="%a %d"))
                st.plotly_chart(oe_fig(fig, 300, legend=False),
                                use_container_width=True, config=PLOT_CONFIG)
                if series["emissions_tco2e"].abs().sum() > 0:
                    chead("Emissions", "tCO2e / 5 min",
                          f"Window total <b>{series['emissions_tco2e'].sum():,.0f} t</b>")
                    fig = go.Figure(go.Scatter(
                        x=series["interval_local"],
                        y=series["emissions_tco2e"], mode="lines",
                        line=dict(color=RED, width=1.1),
                        hovertemplate="%{x|%a %d %b %H:%M}<br>Emissions: "
                                      "<b>%{y:,.3f} tCO2e</b><extra></extra>"))
                    add_night_bands(fig, series["interval_local"].min(),
                                    series["interval_local"].max())
                    fig.update_layout(
                        xaxis=dict(dtick=86400000, tickformat="%a %d"))
                    st.plotly_chart(oe_fig(fig, 240, legend=False),
                                    use_container_width=True,
                                    config=PLOT_CONFIG)
        if pd.notna(cap_mw) and cap_mw > 0 and not series.empty:
            insight(f"<b>{frow['facility_name']}</b> ran at a "
                    f"<b>{fmt(frow['capacity_factor']*100 if pd.notna(frow['capacity_factor']) else None, ',.0f', '%')}</b> "
                    f"capacity factor over the window — the dashed line is its "
                    f"{cap_mw:,.0f} MW registered limit. The gap between the "
                    f"trace and that line is how OpenElectricity shows "
                    f"headroom (or, for solar and wind, the weather).")

        with st.expander("All facilities — every value behind the map"):
            table = fmap[["facility_name", "facility_code", "network_region",
                          "state", "fueltech_id", "fuel_group",
                          "capacity_registered_mw", "avg_power_mw",
                          "peak_power_mw", "energy_mwh", "emissions_tco2e",
                          "intensity", "capacity_factor", "n_obs"]
                         ].sort_values("energy_mwh", ascending=False)
            st.dataframe(
                table, hide_index=True, use_container_width=True, height=420,
                column_config={
                    "facility_name": "Facility", "facility_code": "Code",
                    "network_region": "Region", "state": "State",
                    "fueltech_id": "Fuel tech", "fuel_group": "Group",
                    "capacity_registered_mw": st.column_config.NumberColumn(
                        "Capacity (MW)", format="%.1f"),
                    "avg_power_mw": st.column_config.NumberColumn(
                        "Avg MW", format="%.1f"),
                    "peak_power_mw": st.column_config.NumberColumn(
                        "Peak MW", format="%.1f"),
                    "energy_mwh": st.column_config.NumberColumn(
                        "Energy (MWh)", format="%.0f"),
                    "emissions_tco2e": st.column_config.NumberColumn(
                        "Emissions (t)", format="%.0f"),
                    "intensity": st.column_config.NumberColumn(
                        "t/MWh", format="%.3f"),
                    "capacity_factor": st.column_config.ProgressColumn(
                        "Capacity factor", format="percent",
                        min_value=0, max_value=1),
                    "n_obs": st.column_config.NumberColumn("Obs"),
                })

    # ------------------------------------------------------------------ #
    # Layer 2 — all-Australia census (Assignment 1 dataset)
    # ------------------------------------------------------------------ #
    else:
        if au.empty:
            st.info("data/au_power_stations.csv not found.")
        else:
            g1, g2 = st.columns([1.5, 2.5])
            sel_states = g1.multiselect(
                "State", sorted(au["state"].dropna().unique()),
                placeholder="All states")
            sel_fuel = g2.multiselect(
                "Primary fuel", sorted(au["primary_fuel"].dropna().unique()),
                placeholder="All fuels")
            amap = au.copy()
            if sel_states:
                amap = amap[amap["state"].isin(sel_states)]
            if sel_fuel:
                amap = amap[amap["primary_fuel"].isin(sel_fuel)]

            amap["_size"] = (pd.to_numeric(amap["production_mwh"],
                                           errors="coerce")
                             .clip(lower=0).fillna(0) ** 0.5 / 18 + 4)
            amap["_h_prod"] = amap["production_mwh"].map(
                lambda v: fmt(v, ",.0f", " MWh"))
            amap["_h_em"] = amap["emissions_tco2e"].map(
                lambda v: fmt(v, ",.0f", " tCO2e"))
            amap["_h_int"] = amap["intensity_tco2e_mwh"].map(
                lambda v: fmt(v, ",.3f", " t/MWh"))
            amap["_h_year"] = amap["reporting_year"].fillna("—")
            amap["_h_grid"] = amap["grid"].fillna("—")

            fig = px.scatter_map(
                amap, lat="lat", lon="lon", color="primary_fuel", size="_size",
                size_max=24, zoom=3.4, center={"lat": -28.5, "lon": 134.0},
                map_style="carto-positron", height=620,
                color_discrete_map=AU_FUEL_COLOURS,
                custom_data=["station_name", "state", "primary_fuel",
                             "_h_prod", "_h_em", "_h_int", "_h_year",
                             "_h_grid"],
            )
            fig.update_traces(hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "<span style='color:#8F8C84'>%{customdata[1]} · "
                "%{customdata[2]} · grid: %{customdata[7]}</span><br>"
                "Production (yr) <b>%{customdata[3]}</b><br>"
                "Emissions (yr) <b>%{customdata[4]}</b> · "
                "Intensity <b>%{customdata[5]}</b><br>"
                "Reporting year %{customdata[6]}"
                "<extra></extra>"))
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                font=dict(family="DM Sans, Segoe UI, sans-serif"),
                legend=dict(orientation="h", yanchor="bottom", y=0.005, x=0.01,
                            bgcolor="rgba(255,255,255,0.9)",
                            font=dict(size=11, color=INK_2), title=None),
                hoverlabel=dict(bgcolor="white", bordercolor=BORDER,
                                font_family="DM Sans, Segoe UI, sans-serif",
                                font_size=12.5, font_color=INK))
            st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
            insight(f"<b>{len(amap):,}</b> stations across every state and "
                    f"territory (NGER census, geocoded in Assignment 1) — "
                    f"size is annual production. Diesel dots blanket the "
                    f"remote NT and WA off-grid, while the east-coast NEM "
                    f"carries the giants.")

            with st.expander("All stations — latest reporting year"):
                st.dataframe(
                    amap[["station_name", "state", "primary_fuel", "grid",
                          "reporting_year", "production_mwh",
                          "emissions_tco2e", "intensity_tco2e_mwh"]]
                    .sort_values("production_mwh", ascending=False),
                    hide_index=True, use_container_width=True, height=420,
                    column_config={
                        "station_name": "Station", "state": "State",
                        "primary_fuel": "Fuel", "grid": "Grid",
                        "reporting_year": "Year",
                        "production_mwh": st.column_config.NumberColumn(
                            "Production (MWh)", format="%.0f"),
                        "emissions_tco2e": st.column_config.NumberColumn(
                            "Emissions (t)", format="%.0f"),
                        "intensity_tco2e_mwh": st.column_config.NumberColumn(
                            "t/MWh", format="%.3f"),
                    })

# =========================================================================== #
# ANALYSIS
# =========================================================================== #
with tab_analysis:
    sect("Regions",
         "Five grids, one market — and a 60x gap in carbon intensity.",
         "The loaded window, split by NEM region: how much energy each "
         "produced, how dirty each megawatt-hour was, and how renewable each "
         "grid ran.")
    reg = region.sort_values("energy_twh", ascending=True)
    with st.container(border=True):
        chead("Energy · intensity · renewable share", "by region",
              f"{_win}")
        m1, m2, m3 = st.columns(3)
        with m1:
            fig = go.Figure(go.Bar(
                x=reg["energy_twh"], y=reg["network_region"],
                orientation="h", marker_color=BLACK,
                hovertemplate="<b>%{y}</b><br>Energy: "
                              "<b>%{x:,.2f} TWh</b><extra></extra>"))
            fig.update_layout(xaxis_title="Energy (TWh)")
            st.plotly_chart(oe_fig(fig, 270, legend=False),
                            use_container_width=True, config=PLOT_CONFIG)
        with m2:
            fig = go.Figure(go.Bar(
                x=reg["intensity_tco2e_mwh"], y=reg["network_region"],
                orientation="h", marker_color=RED,
                hovertemplate="<b>%{y}</b><br>Intensity: "
                              "<b>%{x:,.3f} t/MWh</b><extra></extra>"))
            fig.update_layout(xaxis_title="Intensity (tCO2e/MWh)",
                              yaxis=dict(showticklabels=False))
            st.plotly_chart(oe_fig(fig, 270, legend=False),
                            use_container_width=True, config=PLOT_CONFIG)
        with m3:
            fig = go.Figure(go.Bar(
                x=reg["renewable_share"] * 100, y=reg["network_region"],
                orientation="h", marker_color=GREEN,
                hovertemplate="<b>%{y}</b><br>Renewable share: "
                              "<b>%{x:,.1f}%</b><extra></extra>"))
            fig.update_layout(xaxis_title="Renewable share (%)",
                              yaxis=dict(showticklabels=False))
            st.plotly_chart(oe_fig(fig, 270, legend=False),
                            use_container_width=True, config=PLOT_CONFIG)
    vic = region.loc[region["network_region"] == "VIC1", "intensity_tco2e_mwh"]
    tas = region.loc[region["network_region"] == "TAS1", "intensity_tco2e_mwh"]
    ratio = (vic.iloc[0] / tas.iloc[0]) if len(vic) and len(tas) and tas.iloc[0] else 0
    top_region = region.iloc[0]
    insight(f"VIC1 (brown coal) is the dirtiest grid at "
            f"<b>{vic.iloc[0]:.3f} t/MWh</b>; hydro-powered TAS1 is "
            f"<b>{ratio:,.0f}x cleaner</b> at {tas.iloc[0]:.3f} — the widest "
            f"gap inside one market. {top_region['network_region']} is the "
            f"largest producer at <b>{top_region['energy_twh']:.2f} TWh</b>, "
            f"so where the energy is made matters as much as how much.")

    sect("The average day",
         "The duck curve, drawn by 353 power stations.",
         "Average energy delivered in each hour of the day (local time), "
         f"stacked by fuel — {WIN_DAYS} days folded into one.")
    diurnal = q(f"""
        select local_hour, {FUEL_GROUP_SQL} as fuel_group,
               sum(energy_mwh) / count(distinct interval_date) as mwh_per_hour
        from main_marts.fct_facility_interval
        group by 1, 2 order by 1
    """)
    dw = (diurnal.pivot(index="local_hour", columns="fuel_group",
                        values="mwh_per_hour").fillna(0.0).sort_index())
    with st.container(border=True):
        chead("Average generation by hour of day", "MWh/h",
              f"Av. <b>{dw.clip(lower=0).sum(axis=1).mean():,.0f} MWh/h</b>")
        fig = go.Figure()
        for grp in [g for g in FUEL_GROUP_ORDER if g in dw.columns]:
            fig.add_trace(go.Scatter(
                x=dw.index, y=dw[grp].clip(lower=0), name=grp, mode="lines",
                stackgroup="d", line=dict(width=0),
                fillcolor=FUEL_GROUP_COLOURS[grp],
                hovertemplate="%{y:,.0f} MWh"))
        fig.update_layout(hovermode="x unified",
                          xaxis_title="Hour of day (local)",
                          xaxis=dict(dtick=2))
        st.plotly_chart(oe_fig(fig, 390), use_container_width=True,
                        config=PLOT_CONFIG)
    sp_hour = int(dw["Solar"].idxmax()) if "Solar" in dw.columns else 12
    insight(f"Solar output peaks around <b>{sp_hour}:00</b>, carving the "
            f"midday duck curve; gas and storage fill the evening ramp when "
            f"the sun drops but demand doesn't. This daily shape is the core "
            f"operational challenge of a decarbonising grid — and the reason "
            f"batteries are being built out fast.")

    sect("Leaderboard",
         "A handful of giants carry the grid.",
         "The 15 largest facilities by energy or emissions over the window "
         "— colour is fuel technology.")
    metric_choice = st.radio("Rank by", ["Energy (MWh)", "Emissions (tCO2e)"],
                             horizontal=True, label_visibility="collapsed")
    mcol = "energy_mwh" if metric_choice.startswith("Energy") else "emissions_tco2e"
    top = (facilities[facilities[mcol] > 0].nlargest(15, mcol).sort_values(mcol))
    with st.container(border=True):
        chead("Top 15 facilities", metric_choice.lower(),
              f"of {n_generating:,} generating sites")
        fig = px.bar(
            top, x=mcol, y="facility_name", orientation="h",
            color="fuel_group", color_discrete_map=FUEL_GROUP_COLOURS,
            category_orders={"fuel_group": FUEL_GROUP_ORDER},
            labels={mcol: "", "facility_name": ""},
            custom_data=["fueltech_id", "network_region", "energy_mwh",
                         "emissions_tco2e", "intensity"])
        fig.update_traces(hovertemplate=(
            "<b>%{y}</b><br>"
            "<span style='color:#8F8C84'>%{customdata[0]} · %{customdata[1]}"
            "</span><br>"
            "Energy: <b>%{customdata[2]:,.0f} MWh</b><br>"
            "Emissions: <b>%{customdata[3]:,.0f} tCO2e</b><br>"
            "Intensity: <b>%{customdata[4]:,.3f} t/MWh</b><extra></extra>"))
        st.plotly_chart(oe_fig(fig, 470), use_container_width=True,
                        config=PLOT_CONFIG)
    top5_share = facilities.nlargest(5, mcol)[mcol].sum() / facilities[mcol].sum() * 100
    unit = "energy" if mcol == "energy_mwh" else "emissions"
    insight(f"The top 5 facilities alone account for "
            f"<b>{top5_share:,.0f}%</b> of all {unit} — the NEM is a story "
            f"of a few giant coal stations and hundreds of small renewables. "
            f"That concentration is why a handful of retirement decisions can "
            f"move the whole grid's carbon footprint.")

    sect("Fuel technology",
         "Fuel choice is the whole carbon story.",
         "Total emissions divided by total energy, per technology — only "
         "technologies that generated more than 1 GWh are shown.")
    by_tech = q(f"""
        select fueltech_id, {FUEL_GROUP_SQL} as fuel_group,
               sum(energy_mwh) as energy_mwh,
               sum(emissions_tco2e) / nullif(sum(energy_mwh), 0) as intensity
        from main_marts.fct_facility_interval
        group by 1, 2 having sum(energy_mwh) > 1000
        order by intensity desc
    """)
    with st.container(border=True):
        chead("Emissions intensity", "tCO2e/MWh",
              f"grid average <b>{overall_int:.3f}</b>")
        fig = px.bar(by_tech, x="intensity", y="fueltech_id", orientation="h",
                     color="fuel_group", color_discrete_map=FUEL_GROUP_COLOURS,
                     category_orders={"fuel_group": FUEL_GROUP_ORDER},
                     labels={"intensity": "", "fueltech_id": ""},
                     custom_data=["energy_mwh"])
        fig.update_traces(hovertemplate=(
            "<b>%{y}</b><br>Intensity: <b>%{x:,.3f} t/MWh</b><br>"
            "Energy: %{customdata[0]:,.0f} MWh<extra></extra>"))
        fig.add_vline(x=overall_int, line_dash="dash", line_color=RED,
                      line_width=1.1, annotation_text="grid average",
                      annotation_position="top",
                      annotation_font=dict(size=10.5, color=RED))
        st.plotly_chart(oe_fig(fig, 410), use_container_width=True,
                        config=PLOT_CONFIG)
    bc = by_tech.loc[by_tech["fueltech_id"] == "coal_brown", "intensity"]
    bc_ratio = (bc.iloc[0] / overall_int) if len(bc) and overall_int else 0
    insight(f"Brown coal emits <b>{bc.iloc[0]:.2f} t/MWh</b> — about "
            f"<b>{bc_ratio:,.1f}x</b> the grid average (dashed line) — while "
            f"hydro, wind and solar sit at zero. Cutting emissions is about "
            f"which technologies run, not how efficiently any one of them "
            f"does.")

# =========================================================================== #
# HOW IT'S BUILT
# =========================================================================== #
with tab_story:
    # ---- OpenElectricity-style "About" hero: big word over a dotted grid --- #
    st.markdown('<div class="oe-grid"><div class="oe-gridword">About</div></div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="oe-mission">GridPulse &mdash; a production-shaped data '
        'platform that turns Australia&rsquo;s <span class="accent">public '
        'grid data</span> into governed, tested, reproducible analytics.</div>',
        unsafe_allow_html=True)

    st.markdown(
        f'<div class="oe-prose">'
        f'<div class="h"><span class="n">01 &middot; WHY</span>Why I built it</div>'
        f'<div><p>Most &ldquo;data projects&rdquo; are a single chart sitting on '
        f'top of a CSV. Real analytics teams own far more than that: reliable '
        f'ingestion, a data contract, layered storage, automated testing and '
        f'orchestration. GridPulse exists to <b>demonstrate that entire '
        f'lifecycle end-to-end</b> on a genuinely messy, rate-limited public '
        f'data source &mdash; not a toy dataset.</p>'
        f'<p>It began as a University of Sydney data-engineering assignment '
        f'(COMP5339) and was rebuilt into a portfolio project: the kind of '
        f'work a data engineer actually ships.</p></div>'

        f'<div class="h"><span class="n">02 &middot; WHAT IT SOLVES</span>'
        f'The problem</div>'
        f'<div><p>The OpenElectricity API is capped at <b>500 requests a '
        f'day</b>, returns data <b>per generating unit</b> rather than per '
        f'station, ships many facilities <b>without coordinates</b>, and &mdash; '
        f'like any live feed &mdash; can silently serve bad or missing values. '
        f'Naively querying it is slow, fragile and easy to corrupt.</p>'
        f'<p>GridPulse fixes each of those: it <b>caches every raw response '
        f'immutably</b> (the API is hit at most once per window), aggregates '
        f'units up to facility level, backfills coordinates from region '
        f'centroids, and refuses bad data at a <b>9-check quality gate</b> '
        f'before anything is loaded.</p></div>'

        f'<div class="h"><span class="n">03 &middot; HOW IT HELPS</span>'
        f'Trustworthy by construction</div>'
        f'<div><p>Everything downstream reads only <b>dbt marts protected by '
        f'39 automated tests</b> &mdash; never raw data. Three independent test '
        f'layers (a pre-load gate, warehouse tests and unit tests) mean nothing '
        f'ships unverified, and the whole pipeline rebuilds from the raw cache '
        f'with <b>one command</b>, fully offline. Numbers you see here are '
        f'reproducible, not hand-picked.</p></div>'

        f'<div class="h"><span class="n">04 &middot; WHO IT&rsquo;S FOR</span>'
        f'Use cases</div>'
        f'<div><p>The tested marts support <b>emissions and renewable-share '
        f'reporting</b>, <b>wholesale market and price analysis</b>, '
        f'<b>per-facility monitoring</b>, and <b>grid-decarbonisation '
        f'research</b> &mdash; anything that needs clean, located, '
        f'quality-assured 5-minute NEM data it can query with confidence.</p>'
        f'</div>'
        f'</div>', unsafe_allow_html=True)

    sect("Architecture",
         "From a rate-limited public API to tested marts, in six stages.",
         "Every number on this site is reproducible offline: raw API "
         "responses are cached immutably, a 9-check gate refuses bad data "
         "before load, and dbt rebuilds and re-tests the marts from the "
         "warehouse. Dagster orchestrates the whole graph.")
    pipeline_strip()
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    if ARCH_SVG.exists():
        with st.container(border=True):
            st.image(str(ARCH_SVG), use_container_width=True)

    sect("Stage by stage", "What each step actually does.",
         "Scroll — each stage lights up as it reaches the middle of the "
         "screen.")
    stage_scrolly()

    sect("Testing", "Defence in depth — nothing ships untested.")
    t1, t2, t3 = st.columns(3)
    t1.markdown('<div class="oe-stage">'
                '<div class="num"><span class="c">9</span>'
                '<span class="k" style="color:#E34A33">Pipeline gate</span></div>'
                '<h4>Before load</h4><p><b>9 expectations</b> — schema, nulls, '
                'unique grain, domains, bounds. A failure stops the run.</p>'
                '</div>', unsafe_allow_html=True)
    t2.markdown('<div class="oe-stage">'
                '<div class="num"><span class="c">39</span>'
                '<span class="k" style="color:#7C3AED">Warehouse tests</span></div>'
                '<h4>After modelling</h4><p><b>39 dbt data tests</b> — '
                'uniqueness, referential integrity, accepted values, ranges. '
                '47/47 nodes PASS.</p></div>', unsafe_allow_html=True)
    t3.markdown('<div class="oe-stage">'
                '<div class="num"><span class="c">10</span>'
                '<span class="k" style="color:#417505">Unit tests</span></div>'
                '<h4>On the transforms</h4><p><b>10 pytest cases</b> on the '
                'pure functions — aggregation, windowing, geocoding, gate '
                'failures.</p></div>', unsafe_allow_html=True)

    sect("Layered storage", "Each layer rebuilds from the one before it.")
    st.markdown("""
| Layer | Artefact | Role |
|---|---|---|
| Raw | `data/raw_openelectricity/*.json` | immutable API responses |
| Contract | `consolidated_facility_5min.csv` | single source of truth |
| Warehouse | `electricity_a2.duckdb` | normalised schema (dbt sources) |
| Marts | `main_marts.*` | tested star schema, read by this app |
""")

    sect("Run it yourself", "The whole pipeline is one reproducible workflow.")
    st.markdown(
        '<div class="oe-run">'
        '<div class="step"><div class="sn">1</div><div class="sc">'
        '<code>python -m gridpulse.pipeline</code>'
        '<div class="sd">Ingest &#8594; transform &#8594; geocode &#8594; '
        '9-check gate &#8594; load DuckDB (replays offline from the JSON '
        'cache)</div></div></div>'
        '<div class="step"><div class="sn">2</div><div class="sc">'
        '<code>dbt build --project-dir dbt --profiles-dir dbt</code>'
        '<div class="sd">Build staging views + mart tables and run 39 data '
        'tests (47/47 nodes)</div></div></div>'
        '<div class="step"><div class="sn">3</div><div class="sc">'
        '<code>python -m pytest</code>'
        '<div class="sd">10 unit tests on the pure transform / quality / '
        'geocode functions</div></div></div>'
        '<div class="step"><div class="sn">4</div><div class="sc">'
        '<code>dagster dev -m orchestration.definitions</code>'
        '<div class="sd">Launch the 15-asset lineage graph + daily schedule '
        'at :3000</div></div></div>'
        '<div class="step"><div class="sn">5</div><div class="sc">'
        '<code>streamlit run dashboard/app_streamlit.py</code>'
        '<div class="sd">Serve this dashboard from the tested marts</div>'
        '</div></div>'
        '</div>', unsafe_allow_html=True)

    sect("Verified results", "Every number below is from the latest full run.")
    r = st.columns(4)
    stat_tile(r[0], "Fact rows", f"{N_ROWS:,}", "facility x 5-min interval")
    stat_tile(r[1], "dbt nodes passing", "47 / 47", "39 data tests")
    stat_tile(r[2], "Quality checks", "9 / 9", "hard gate before load")
    stat_tile(r[3], "Unit tests", "10 / 10", "pure transforms")
    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
    st.markdown(
        "".join(f'<span class="oe-chip">{t}</span>' for t in
                ["Python 3.12", "pandas", "DuckDB", "dbt", "Dagster",
                 "Streamlit", "Plotly", "MQTT", "Dash", "pytest"]),
        unsafe_allow_html=True)

st.markdown(
    '<div class="oe-footer">'
    '<span>GridPulse &middot; built by Aditya Moon &amp; Pranjal Desai</span>'
    '<span>Data: <a href="https://openelectricity.org.au">OpenElectricity</a> '
    '(CC-BY 4.0) and NGER &middot; design language after '
    'openelectricity.org.au</span>'
    '<span>Rebuild: <code>python -m gridpulse.pipeline</code> + '
    '<code>dbt build</code></span></div>',
    unsafe_allow_html=True)
