-- Network-level price & demand series.
with source as (
    select * from {{ source('gridpulse', 'MARKET_PRICE_DEMAND') }}
)
select
    interval_ts,
    network_region,
    price   as price_aud_mwh,
    demand  as demand_mw
from source
where price is not null or demand is not null
