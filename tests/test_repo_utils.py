"""Tests for src.scrapers.repo_utils with mocked HTTP calls.

Every test patches the module-level ``_session`` so no real network
requests are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import src.scrapers.repo_utils as repo_utils

# ── helpers ──────────────────────────────────────────────────────────────────


def _fake_response(status_code: int = 200, json_data=None, text: str = "", headers=None):
    """Build a minimal mock response object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text or ""
    resp.headers = headers or {}
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch, tmp_path):
    """Point cache dir at a temp directory so tests are isolated."""
    monkeypatch.setattr(repo_utils, "CACHE_DIR", str(tmp_path / "cache"))


@pytest.fixture()
def mock_session(monkeypatch):
    """Replace the module-level _session with a MagicMock."""
    session = MagicMock()
    session.default_timeout = 30
    monkeypatch.setattr(repo_utils, "_session", session)
    return session


# ── check_url_cached ─────────────────────────────────────────────────────────


class TestCheckUrlCached:
    def test_non_http_returns_false(self):
        assert repo_utils.check_url_cached("ftp://example.com") is False

    def test_existing_url_returns_true(self, mock_session):
        mock_session.head.return_value = _fake_response(200)
        assert repo_utils.check_url_cached("https://example.com/file.tar.gz") is True

    def test_404_returns_false(self, mock_session):
        mock_session.head.return_value = _fake_response(404)
        assert repo_utils.check_url_cached("https://example.com/gone") is False

    def test_429_retries_then_succeeds(self, mock_session):
        mock_session.head.side_effect = [
            _fake_response(429),
            _fake_response(200),
        ]
        with patch("src.scrapers.repo_utils.time.sleep"):
            result = repo_utils.check_url_cached("https://example.com/file")
        assert result is True

    def test_connection_error_returns_false(self, mock_session):
        import requests

        mock_session.head.side_effect = requests.exceptions.ConnectionError("DNS")
        assert repo_utils.check_url_cached("https://gone.example.com/x") is False


# ── cached_github_stats ──────────────────────────────────────────────────────


class TestCachedGithubStats:
    def test_200_returns_stats(self, mock_session, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        mock_session.get.return_value = _fake_response(
            200,
            json_data={
                "stargazers_count": 42,
                "forks_count": 7,
                "open_issues_count": 3,
                "subscribers_count": 5,
                "updated_at": "2024-01-01T00:00:00Z",
                "created_at": "2020-06-01T00:00:00Z",
                "license": {"spdx_id": "MIT"},
                "language": "Python",
                "archived": False,
                "size": 12345,
            },
            headers={"ETag": '"abc"'},
        )
        stats = repo_utils.cached_github_stats("https://github.com/owner/repo")
        assert stats["github_stars"] == 42
        assert stats["github_forks"] == 7
        assert stats["license"] == "MIT"

    def test_404_returns_none(self, mock_session, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        mock_session.get.return_value = _fake_response(404)
        result = repo_utils.cached_github_stats("https://github.com/owner/missing")
        assert result is None

    def test_strips_subpath(self, mock_session, monkeypatch):
        """URL like github.com/owner/repo/tree/main should resolve to owner/repo."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        mock_session.get.return_value = _fake_response(
            200,
            json_data={
                "stargazers_count": 1,
                "forks_count": 0,
                "open_issues_count": 0,
                "subscribers_count": 0,
                "updated_at": "2024-01-01",
                "created_at": "2024-01-01",
                "license": None,
                "language": "Rust",
                "archived": False,
                "size": 100,
            },
            headers={},
        )
        repo_utils.cached_github_stats("https://github.com/owner/repo/tree/main/src")
        call_url = mock_session.get.call_args[0][0]
        assert call_url == "https://api.github.com/repos/owner/repo"


# ── cached_zenodo_stats ──────────────────────────────────────────────────────


class TestCachedZenodoStats:
    def test_200_returns_stats(self, mock_session):
        mock_session.get.return_value = _fake_response(
            200,
            json_data={
                "stats": {"unique_views": 100, "unique_downloads": 50},
                "updated": "2024-06-01",
                "created": "2024-01-01",
            },
        )
        stats = repo_utils.cached_zenodo_stats("https://zenodo.org/records/12345")
        assert stats["zenodo_views"] == 100
        assert stats["zenodo_downloads"] == 50

    def test_unparseable_url_returns_none(self, mock_session):
        result = repo_utils.cached_zenodo_stats("https://zenodo.org/badge/latestdoi/123")
        assert result is None
        mock_session.get.assert_not_called()


# ── cached_figshare_stats ────────────────────────────────────────────────────


class TestCachedFigshareStats:
    def test_200_returns_stats(self, mock_session):
        mock_session.get.side_effect = [
            _fake_response(200, json_data={"totals": 200}),  # views
            _fake_response(200, json_data={"totals": 80}),  # downloads
            _fake_response(200, json_data={"modified_date": "2024-06-01", "created_date": "2024-01-01"}),  # meta
        ]
        stats = repo_utils.cached_figshare_stats("https://figshare.com/articles/dataset/foo/999999")
        assert stats["figshare_views"] == 200
        assert stats["figshare_downloads"] == 80

    def test_failure_returns_defaults(self, mock_session):
        import requests

        mock_session.get.side_effect = requests.RequestException("timeout")
        stats = repo_utils.cached_figshare_stats("https://figshare.com/articles/dataset/foo/999999")
        assert stats["figshare_views"] == -1
        assert stats["figshare_downloads"] == -1


# ── download_file / _cached_get ──────────────────────────────────────────────


class TestDownloadFile:
    def test_returns_body(self, mock_session, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        mock_session.get.return_value = _fake_response(200, text="hello world", headers={})
        mock_session.get.return_value.raise_for_status = MagicMock()
        body = repo_utils.download_file("https://example.com/data.csv")
        assert body == "hello world"
