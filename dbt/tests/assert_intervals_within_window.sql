-- Singular data test: every observation must fall inside the declared 7-day
-- analysis window (2026-05-12 .. 2026-05-19 UTC). Guards against stray or
-- future-dated intervals leaking through cleaning.
select obs_id, interval_ts
from {{ ref('fct_facility_interval') }}
where interval_ts <  timestamptz '2026-05-12 00:00:00+00'
   or interval_ts >= timestamptz '2026-05-19 00:00:00+00'
