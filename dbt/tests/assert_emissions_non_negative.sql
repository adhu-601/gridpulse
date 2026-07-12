-- Singular data test: emissions must never be negative (physically impossible).
-- Returns offending rows; the test passes when zero rows are returned.
select obs_id, facility_id, interval_ts, emissions_tco2e
from {{ ref('fct_facility_interval') }}
where emissions_tco2e < 0
