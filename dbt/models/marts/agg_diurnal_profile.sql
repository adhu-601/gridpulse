-- Average generation by local hour-of-day and fuel category (Australia/Sydney).
-- Powers the dashboard's diurnal stacked-area chart: the midday solar peak
-- (~09:00-15:00) displacing gas while coal holds a flat baseline.
with f as (
    select * from {{ ref('fct_facility_interval') }}
)
select
    local_hour,
    fuel_category,
    count(*)              as n_observations,
    avg(power_mw)         as avg_power_mw,
    sum(energy_mwh)       as energy_mwh,
    sum(emissions_tco2e)  as emissions_tco2e
from f
group by 1, 2
order by local_hour, fuel_category
