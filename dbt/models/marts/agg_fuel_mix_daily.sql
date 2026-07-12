-- Daily generation and emissions by fuel technology + category.
-- Reproduces the report's "generation mix" and "emissions concentration"
-- findings (coal ≈ 58% of energy but ≈ 95% of emissions).
with f as (
    select * from {{ ref('fct_facility_interval') }}
)
select
    interval_date,
    fuel_category,
    fueltech_id,
    is_renewable,
    count(*)                          as n_observations,
    count(distinct facility_id)       as n_facilities,
    sum(energy_mwh)                   as energy_mwh,
    sum(emissions_tco2e)              as emissions_tco2e,
    case when sum(energy_mwh) > 0
         then sum(emissions_tco2e) / sum(energy_mwh) end as intensity_tco2e_mwh
from f
group by 1, 2, 3, 4
