-- 5-minute facility observations, cast to Australia/Sydney local time for the
-- diurnal analysis while retaining the canonical UTC timestamp.
with source as (
    select * from {{ source('gridpulse', 'FACILITY_POWER_EMISSIONS') }}
)
select
    obs_id,
    facility_id,
    interval_ts,
    interval_ts at time zone 'Australia/Sydney'  as interval_local,
    cast(interval_ts as date)                    as interval_date,
    extract(hour from interval_ts at time zone 'Australia/Sydney') as local_hour,
    power_mw,
    emissions_tco2e,
    -- energy for a 5-minute interval, MWh = MW * (5/60)
    power_mw * (5.0 / 60.0)                       as energy_mwh
from source
