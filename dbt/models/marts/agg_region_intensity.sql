-- Per-region energy, emissions and emission intensity over the window.
-- Reproduces the report's regional finding (VIC highest intensity on brown coal;
-- SA/TAS far lower on wind/hydro).
with f as (
    select * from {{ ref('fct_facility_interval') }}
)
select
    network_region,
    state,
    count(distinct facility_id)   as n_facilities,
    sum(energy_mwh)               as energy_mwh,
    sum(energy_mwh) / 1e6         as energy_twh,
    sum(emissions_tco2e)          as emissions_tco2e,
    case when sum(energy_mwh) > 0
         then sum(emissions_tco2e) / sum(energy_mwh) end as intensity_tco2e_mwh,
    sum(case when is_renewable then energy_mwh else 0 end)
        / nullif(sum(energy_mwh), 0)                      as renewable_share
from f
group by 1, 2
order by energy_mwh desc
