"""Tests for Zenodo URL parsing in cached_zenodo_stats."""

from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.sys_sec_scrape import cached_zenodo_stats

_FAKE_RECORD = {
    "stats": {"unique_views": 42, "unique_downloads": 7},
    "updated": "2025-01-01",
    "created": "2024-06-01",
}


def _mock_get(expected_api_url):
    """Return a side_effect that asserts the correct API URL is called."""

    def _side_effect(url, timeout=None):
        assert url == expected_api_url, f"Expected {expected_api_url}, got {url}"
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = _FAKE_RECORD
        return resp

    return _side_effect


@pytest.mark.parametrize(
    "input_url,expected_rec",
    [
        # New plural format
        ("https://zenodo.org/records/8062035", "8062035"),
        # Old singular format (the bug)
        ("https://zenodo.org/record/8062035", "8062035"),
        # With fragment
        ("https://zenodo.org/record/6534753#.YnpJtoxBz31", "6534753"),
        # New format with fragment
        ("https://zenodo.org/records/6544915#.Yn3UZhPMJhE", "6544915"),
        # Trailing slash
        ("https://zenodo.org/records/1234567/", "1234567"),
        ("https://zenodo.org/record/1234567/", "1234567"),
    ],
)
@patch("src.scrapers.sys_sec_scrape._read_cache", return_value=type("", (), {})())
@patch("src.scrapers.sys_sec_scrape._write_cache")
def test_zenodo_url_parsing(mock_write, mock_read, input_url, expected_rec):
    """Verify both /record/ and /records/ URLs are parsed to the correct record ID."""
    # Make _read_cache return _MISSING so we go through the HTTP path
    from src.scrapers.sys_sec_scrape import _MISSING

    mock_read.return_value = _MISSING

    expected_api = f"https://zenodo.org/api/records/{expected_rec}"
    with patch("src.scrapers.sys_sec_scrape._session") as mock_session:
        mock_session.get.side_effect = _mock_get(expected_api)
        mock_session.default_timeout = 30
        result = cached_zenodo_stats(input_url)

    assert result is not None
    assert result["zenodo_views"] == 42
    assert result["zenodo_downloads"] == 7
