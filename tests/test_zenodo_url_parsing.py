"""Tests for Zenodo URL parsing in cached_zenodo_stats."""

from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.repo_utils import _resolve_zenodo_record_id, cached_zenodo_stats

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
        # Upload URLs (with token query string)
        ("https://zenodo.org/uploads/14732956?token=eyJhbG...", "14732956"),
        # /doi/ path format
        ("https://zenodo.org/doi/10.5281/zenodo.11181584", "11181584"),
        # doi.org DOI URLs
        ("https://doi.org/10.5281/zenodo.6544966", "6544966"),
    ],
)
@patch("src.scrapers.repo_utils._read_cache", return_value=type("", (), {})())
@patch("src.scrapers.repo_utils._write_cache")
def test_zenodo_url_parsing(mock_write, mock_read, input_url, expected_rec):
    """Verify both /record/ and /records/ URLs are parsed to the correct record ID."""
    # Make _read_cache return _MISSING so we go through the HTTP path
    from src.scrapers.repo_utils import _MISSING

    mock_read.return_value = _MISSING

    expected_api = f"https://zenodo.org/api/records/{expected_rec}"
    with patch("src.scrapers.repo_utils._session") as mock_session:
        mock_session.get.side_effect = _mock_get(expected_api)
        mock_session.default_timeout = 30
        result = cached_zenodo_stats(input_url)

    assert result is not None
    assert result["zenodo_views"] == 42
    assert result["zenodo_downloads"] == 7


class TestResolveZenodoRecordId:
    """Unit tests for _resolve_zenodo_record_id (no HTTP)."""

    def test_badge_returns_none(self):
        assert _resolve_zenodo_record_id("https://zenodo.org/badge/latestdoi/580583199") is None

    def test_unparseable_returns_none(self):
        assert _resolve_zenodo_record_id("https://example.com/foo") is None

    def test_uploads(self):
        assert _resolve_zenodo_record_id("https://zenodo.org/uploads/14732956?token=abc") == "14732956"

    def test_doi_path(self):
        assert _resolve_zenodo_record_id("https://zenodo.org/doi/10.5281/zenodo.11181584") == "11181584"

    def test_doi_org(self):
        assert _resolve_zenodo_record_id("https://doi.org/10.5281/zenodo.6544966") == "6544966"

    def test_records_with_subpath(self):
        assert _resolve_zenodo_record_id("https://zenodo.org/records/1234567/files/data.zip") == "1234567"


@patch("src.scrapers.repo_utils._read_cache")
@patch("src.scrapers.repo_utils._write_cache")
def test_zenodo_410_resolves_doi(mock_write, mock_read):
    """When the API returns 410, resolve the DOI redirect and retry."""
    from src.scrapers.repo_utils import _MISSING

    mock_read.return_value = _MISSING

    call_count = 0

    def _side_effect_get(url, timeout=None):
        nonlocal call_count
        resp = MagicMock()
        if call_count == 0:
            # First call: concept DOI record → 410
            assert "15530592" in url
            resp.status_code = 410
            resp.json.return_value = {}
        else:
            # Second call: resolved record → 200
            assert "15530593" in url
            resp.status_code = 200
            resp.json.return_value = _FAKE_RECORD
        call_count += 1
        return resp

    def _side_effect_head(url, allow_redirects=True, timeout=None):
        resp = MagicMock()
        resp.url = "https://zenodo.org/records/15530593"
        return resp

    with patch("src.scrapers.repo_utils._session") as mock_session:
        mock_session.get.side_effect = _side_effect_get
        mock_session.head.side_effect = _side_effect_head
        mock_session.default_timeout = 30
        result = cached_zenodo_stats("https://doi.org/10.5281/zenodo.15530592")

    assert result is not None
    assert result["zenodo_views"] == 42
