-- Grain: one row per (facility, 5-minute interval). The analytical fact table
-- joining observations to facility/fuel/region attributes. Downstream aggregate
-- marts and the dashboard read from here.
with obs as (
    select * from {{ ref('stg_power_emissions') }}
),
fac as (
    select * from {{ ref('dim_facility') }}
)
select
    obs.obs_id,
    obs.interval_ts,
    obs.interval_local,
    obs.interval_date,
    obs.local_hour,
    fac.facility_id,
    fac.facility_code,
    fac.facility_name,
    fac.network_region,
    fac.state,
    fac.fueltech_id,
    fac.fuel_category,
    fac.is_renewable,
    fac.capacity_registered_mw,
    fac.lat,
    fac.lon,
    obs.power_mw,
    obs.energy_mwh,
    obs.emissions_tco2e,
    -- interval emissions intensity (guard divide-by-zero)
    case when obs.energy_mwh > 0
         then obs.emissions_tco2e / obs.energy_mwh end as intensity_tco2e_mwh
from obs
inner join fac on obs.facility_id = fac.facility_id
