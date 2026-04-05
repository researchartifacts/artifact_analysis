"""Tests for enricher integration with the author index.

These tests verify that each enricher correctly reads/writes the canonical
author index when given a --data_dir.  We mock the actual network calls and
only test the index plumbing.
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import write_json, read_json
from src.utils.author_index import load_author_index, update_author_affiliation


class TestCSRankingsIndexIntegration:
    """Verify enrich_affiliations_csrankings updates author_index.json."""

    def test_enrichment_updates_index(self, tmp_website, sample_authors, sample_index):
        from src.enrichers.enrich_affiliations_csrankings import enrich_affiliations
        from pathlib import Path

        # Write authors.json and author_index.json
        authors_path = tmp_website / "assets" / "data" / "authors.json"
        write_json(str(authors_path), sample_authors[:2])  # Alice + Bob
        write_json(
            str(tmp_website / "assets" / "data" / "author_index.json"),
            sample_index,
        )

        # Build a fake CSRankings name index that matches Bob
        # Keys must match the normalize_name format or lastname: format
        name_index = {
            "bob jones": [{"name": "Bob Jones", "affiliation": "UC Berkeley"}],
            "lastname:jones": [{"name": "Bob Jones", "affiliation": "UC Berkeley"}],
        }

        output_path = tmp_website / "assets" / "data" / "authors_out.json"
        stats = enrich_affiliations(
            authors_file=Path(str(authors_path)),
            output_file=Path(str(output_path)),
            name_index=name_index,
            data_dir=str(tmp_website),
            verbose=False,
        )

        # Check that author_index.json was updated
        updated_index = read_json(
            str(tmp_website / "assets" / "data" / "author_index.json")
        )
        bob = next(e for e in updated_index if e["name"] == "Bob Jones")
        assert bob["affiliation"] == "UC Berkeley"
        assert bob["affiliation_source"] == "csrankings"

    def test_enrichment_without_data_dir_still_works(self, tmp_website, sample_authors):
        """When data_dir is None, enrichment works but doesn't touch the index."""
        from src.enrichers.enrich_affiliations_csrankings import enrich_affiliations
        from pathlib import Path

        authors_path = tmp_website / "assets" / "data" / "authors.json"
        write_json(str(authors_path), sample_authors[:1])
        output_path = tmp_website / "assets" / "data" / "authors_out.json"

        stats = enrich_affiliations(
            authors_file=Path(str(authors_path)),
            output_file=Path(str(output_path)),
            name_index={},
            data_dir=None,
        )
        assert stats["total"] == 1
        # No index file should be created
        assert not os.path.exists(
            str(tmp_website / "assets" / "data" / "author_index.json")
        )


class TestDblpIndexIntegration:
    """Verify enrich_affiliations_dblp_incremental updates author_index.json."""

    @patch("src.enrichers.enrich_affiliations_dblp_incremental.save_search_history")
    @patch("src.enrichers.enrich_affiliations_dblp_incremental.load_search_history", return_value={})
    @patch("src.enrichers.enrich_affiliations_dblp_incremental.requests")
    @patch("src.enrichers.enrich_affiliations_dblp_incremental.search_dblp_author")
    @patch("src.enrichers.enrich_affiliations_dblp_incremental.fetch_affiliation_from_dblp_page")
    def test_found_affiliation_updates_index(
        self, mock_fetch, mock_search, mock_requests, mock_load_hist, mock_save_hist,
        tmp_website, sample_authors, sample_index
    ):
        from src.enrichers.enrich_affiliations_dblp_incremental import enrich_affiliations

        # Mock session
        mock_requests.Session.return_value = MagicMock()

        # Write author_index.json
        write_json(
            str(tmp_website / "assets" / "data" / "author_index.json"),
            sample_index,
        )

        # Bob has no affiliation — will be searched
        mock_search.return_value = "j/BJones"
        mock_fetch.return_value = "Georgia Tech"

        authors_path = tmp_website / "assets" / "data" / "authors.json"
        enriched, stats = enrich_affiliations(
            [sample_authors[1]],  # Bob only
            output_path=str(authors_path),
            max_searches=1,
            data_dir=str(tmp_website),
        )

        updated_index = read_json(
            str(tmp_website / "assets" / "data" / "author_index.json")
        )
        bob = next(e for e in updated_index if e["name"] == "Bob Jones")
        assert bob["affiliation"] == "Georgia Tech"
        assert bob["affiliation_source"] == "dblp"
        assert bob["external_ids"]["dblp_pid"] == "j/BJones"


class TestOpenAlexIndexIntegration:
    """Verify enrich_affiliations_openalex updates author_index.json."""

    @patch("src.enrichers.enrich_affiliations_openalex.find_affiliation_for_author")
    @patch("src.enrichers.enrich_affiliations_openalex._build_author_papers_index")
    @patch("src.enrichers.enrich_affiliations_openalex._parse_authors_yml_fast")
    @patch("src.enrichers.enrich_affiliations_openalex._update_authors_yml")
    def test_found_affiliation_updates_index(
        self,
        mock_update_yml,
        mock_parse,
        mock_build_papers,
        mock_find,
        tmp_website,
        sample_index,
    ):
        from src.enrichers.enrich_affiliations_openalex import enrich

        write_json(
            str(tmp_website / "assets" / "data" / "author_index.json"),
            sample_index,
        )

        # Mock the paper-based lookup
        mock_build_papers.return_value = {"Bob Jones": [{"title": "Some Paper"}]}
        mock_parse.return_value = [
            {"name": "Bob Jones", "affiliation": ""},
        ]
        mock_find.return_value = ("Carnegie Mellon University", "openalex")
        mock_update_yml.return_value = 1

        # Create dummy authors.yml
        yml_path = tmp_website / "_data" / "authors.yml"
        yml_path.write_text("- affiliation: ''\n  name: 'Bob Jones'\n")

        stats = enrich(
            authors_file=str(yml_path),
            papers_file=str(tmp_website / "assets" / "data" / "papers.json"),
            data_dir=str(tmp_website),
        )

        updated_index = read_json(
            str(tmp_website / "assets" / "data" / "author_index.json")
        )
        bob = next(e for e in updated_index if e["name"] == "Bob Jones")
        assert bob["affiliation"] == "Carnegie Mellon University"
        assert bob["affiliation_source"] == "openalex"
