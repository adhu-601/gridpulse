-- Facility dimension, cleaned and typed. Excludes the raw geom column so the
-- staging layer stays free of the DuckDB spatial extension (lat/lon are kept).
with source as (
    select * from {{ source('gridpulse', 'FACILITY') }}
),
fuel as (
    select fuel_id, fuel_name, is_renewable, category
    from {{ source('gridpulse', 'FUEL_TYPE') }}
)
select
    f.facility_id,
    f.facility_code,
    f.facility_name,
    f.state,
    f.network_region,
    f.grid_connected,
    f.lat,
    f.lon,
    f.capacity_registered_mw,
    f.fuel_id,
    fuel.fuel_name        as fueltech_id,
    fuel.category         as fuel_category,
    fuel.is_renewable
from source f
left join fuel on f.fuel_id = fuel.fuel_id
-- Scope to the NEM: the catalogue carries a stray WEM (Western Australia)
-- facility that is out of scope for this east-coast pipeline.
where f.network_region in ('NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1')
