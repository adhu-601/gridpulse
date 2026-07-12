"""Thin, well-behaved client for the OpenElectricity v4 REST API.

Design goals (the things an interviewer will ask about):

* **Bounded, selective retries** — retry only on transient 429/5xx responses,
  honour ``Retry-After`` on rate limits, and fail fast on permanent 4xx errors
  so a malformed request is never retried blindly.
* **Budget observability** — a ``requests_made`` counter makes free-tier usage
  (500/day) visible at a glance.
* **Batching** — facility codes are sent in batches so ~430 NEM facilities are
  covered in ~18 data requests instead of one-per-facility.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Iterable, Sequence

import requests

from . import config

log = logging.getLogger("gridpulse.api")


class OpenElectricityClient:
    """Minimal wrapper around the OpenElectricity v4 endpoints used here."""

    def __init__(self, api_key: str | None = None, base_url: str = config.API_BASE):
        api_key = api_key if api_key is not None else config.API_KEY
        if not api_key:
            log.warning(
                "No OpenElectricity API key set — live calls will 401. "
                "The pipeline still runs from the cached raw JSON."
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "GridPulse/1.0 (+data-engineering-pipeline)",
        })
        self.base = base_url.rstrip("/")
        self.requests_made = 0

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def _fmt(d: datetime) -> str:
        """ISO-8601 (no microseconds), normalised to UTC."""
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def _get(self, path: str, params=None, max_attempts: int = 4) -> dict:
        """GET with retry on 429/5xx only; raises immediately on 4xx."""
        url = f"{self.base}/{path.lstrip('/')}"
        last_err = None
        for attempt in range(max_attempts):
            try:
                r = self.session.get(url, params=params, timeout=120)
            except requests.RequestException as e:      # network/timeout
                last_err = str(e)
                time.sleep(2 * (attempt + 1))
                continue
            self.requests_made += 1
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "30"))
                log.warning("429 rate-limited on %s, sleeping %ss", path, wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                last_err = f"HTTP {r.status_code}"
                time.sleep(2 * (attempt + 1))
                continue
            if 400 <= r.status_code < 500:              # permanent — fail fast
                raise requests.HTTPError(
                    f"{r.status_code} on {url}: {r.text[:300]}", response=r,
                )
            return r.json()
        raise RuntimeError(f"Failed {url} after {max_attempts} attempts: {last_err}")

    # -- endpoints ---------------------------------------------------------- #
    def list_facilities(self, network_id: str = config.NETWORK_CODE) -> dict:
        """Facility + unit metadata catalogue for a network (one request)."""
        return self._get("facilities/", params={"network_id": network_id})

    def facilities_timeseries(
        self,
        network_code: str,
        facility_codes: Sequence[str],
        metrics: Iterable[str],
        interval: str,
        date_start: datetime,
        date_end: datetime,
    ) -> dict:
        """Bulk per-facility power/emissions time-series."""
        params = [
            ("interval", interval),
            ("date_start", self._fmt(date_start)),
            ("date_end", self._fmt(date_end)),
        ]
        params += [("metrics", m) for m in metrics]
        params += [("facility_code", fc) for fc in facility_codes]
        return self._get(f"data/facilities/{network_code}", params=params)

    def market_timeseries(
        self, network_code: str, metrics: Iterable[str], interval: str,
        date_start: datetime, date_end: datetime,
    ) -> dict:
        """Network-level price & demand series."""
        params = [
            ("interval", interval),
            ("date_start", self._fmt(date_start)),
            ("date_end", self._fmt(date_end)),
        ]
        params += [("metrics", m) for m in metrics]
        return self._get(f"market/network/{network_code}", params=params)
