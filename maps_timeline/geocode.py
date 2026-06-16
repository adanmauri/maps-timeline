"""Optional geocoding of addresses using Nominatim (OpenStreetMap).

Turns the address text we extract from the UI into lat/lon. It is a
post-processing step (it does not affect scraping). It honors Nominatim's usage
policy: at most 1 request per second, an identifiable User-Agent, and it caches
results to avoid repeating queries for the same address.

Limitation: it returns the place/address location, not the actual recorded trip
path, and addresses without a street number may be approximate.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class NominatimGeocoder:
    """Geocoder with on-disk caching and rate limiting per Nominatim's policy."""

    def __init__(
        self,
        cache_path: Path,
        user_agent: str,
        min_interval: float = 1.0,
        country_hint: str | None = "Argentina",
    ):
        """Configure cache path, User-Agent, rate limit, and optional country hint."""
        self.cache_path = Path(cache_path)
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.country_hint = country_hint
        self._cache: dict[str, dict] = self._load_cache()
        self._last_request = 0.0

    @property
    def cache_entries(self) -> int:
        """Number of addresses currently stored in the on-disk cache."""
        return len(self._cache)

    def _load_cache(self) -> dict[str, dict]:
        """Load the geocode cache from disk, or return an empty dict."""
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        return {}

    def _save_cache(self) -> None:
        """Persist the in-memory geocode cache to disk."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _request(self, query: str) -> dict:
        """Call Nominatim for one address query and return lat/lon (or nulls)."""
        params: dict[str, str | int] = {"q": query, "format": "json", "limit": 1}
        resp = requests.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": self.user_agent},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return {"lat": None, "lon": None}
        return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}

    def geocode(self, address: str | None) -> tuple[float | None, float | None]:
        """Resolve an address to (lat, lon), using the cache and honoring the rate limit."""
        if not address:
            return (None, None)
        query = f"{address}, {self.country_hint}" if self.country_hint else address
        if query in self._cache:
            cached = self._cache[query]
            return (cached.get("lat"), cached.get("lon"))

        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        try:
            result = self._request(query)
        except requests.RequestException:
            return (None, None)  # no network: degrade without breaking normalization
        self._last_request = time.monotonic()
        self._cache[query] = result
        self._save_cache()
        return (result.get("lat"), result.get("lon"))
