"""Tests for optional Nominatim geocoding."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from maps_timeline.geocode import NominatimGeocoder


def test_geocode_empty_address(tmp_path):
    """Return null coordinates for empty addresses."""
    geocoder = NominatimGeocoder(tmp_path / "cache.json", user_agent="test/1.0")
    assert geocoder.geocode(None) == (None, None)
    assert geocoder.cache_entries == 0


def test_geocode_uses_disk_cache(tmp_path):
    """Read coordinates from an existing cache file without HTTP."""
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps({"Main 1, Argentina": {"lat": -34.6, "lon": -58.4}}),
        encoding="utf-8",
    )
    geocoder = NominatimGeocoder(cache, user_agent="test/1.0")
    assert geocoder.geocode("Main 1") == (-34.6, -58.4)


def test_geocode_fetches_and_persists(tmp_path):
    """Resolve a new address via HTTP and write the cache file."""
    geocoder = NominatimGeocoder(
        tmp_path / "cache.json",
        user_agent="test/1.0",
        min_interval=0.0,
        country_hint=None,
    )
    response = MagicMock()
    response.json.return_value = [{"lat": "-34.5", "lon": "-58.3"}]
    response.raise_for_status = MagicMock()

    with patch("maps_timeline.geocode.requests.get", return_value=response) as get:
        assert geocoder.geocode("Main 1") == (-34.5, -58.3)

    get.assert_called_once()
    saved = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert saved["Main 1"]["lat"] == -34.5


def test_geocode_empty_nominatim_response(tmp_path):
    """Store null coordinates when Nominatim returns no matches."""
    geocoder = NominatimGeocoder(
        tmp_path / "cache.json",
        user_agent="test/1.0",
        min_interval=0.0,
    )
    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status = MagicMock()

    with patch("maps_timeline.geocode.requests.get", return_value=response):
        assert geocoder.geocode("Nowhere") == (None, None)


def test_geocode_network_error_degrades(tmp_path):
    """Return null coordinates when HTTP fails after retries."""
    geocoder = NominatimGeocoder(
        tmp_path / "cache.json",
        user_agent="test/1.0",
        min_interval=0.0,
    )
    with patch(
        "maps_timeline.geocode.requests.get",
        side_effect=requests.RequestException("offline"),
    ):
        assert geocoder.geocode("Main 1") == (None, None)


def test_geocode_rate_limit_sleeps(tmp_path, monkeypatch):
    """Sleep when requests arrive faster than min_interval."""
    clock = {"t": 100.0}
    monkeypatch.setattr("maps_timeline.geocode.time.monotonic", lambda: clock["t"])
    slept: list[float] = []
    monkeypatch.setattr("maps_timeline.geocode.time.sleep", slept.append)

    geocoder = NominatimGeocoder(
        tmp_path / "cache.json",
        user_agent="test/1.0",
        min_interval=10.0,
    )
    response = MagicMock()
    response.json.return_value = [{"lat": "1.0", "lon": "2.0"}]
    response.raise_for_status = MagicMock()

    with patch("maps_timeline.geocode.requests.get", return_value=response):
        geocoder.geocode("First")

    clock["t"] = 100.5
    with patch("maps_timeline.geocode.requests.get", return_value=response):
        geocoder.geocode("Second")

    assert slept == [pytest.approx(9.5)]
