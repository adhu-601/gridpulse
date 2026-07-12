-- Facility dimension for the marts layer (one row per facility).
select
    facility_id,
    facility_code,
    facility_name,
    state,
    network_region,
    fueltech_id,
    fuel_category,
    is_renewable,
    capacity_registered_mw,
    lat,
    lon
from {{ ref('stg_facilities') }}
