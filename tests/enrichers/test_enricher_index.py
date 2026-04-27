"""Tests for enricher integration with the author index.

These tests verify that each enricher correctly reads/writes the canonical
author index when given a --data_dir.  We mock the actual network calls and
only test the index plumbing.
"""

import os
from unittest.mock import patch

from tests.conftest import read_json, write_json


class TestCSRankingsIndexIntegration:
    """Verify enrich_affiliations_csrankings updates author_index.json."""

    def test_enrichment_updates_index(self, tmp_website, sample_authors, sample_index):
        from pathlib import Path

        from src.enrichers.enrich_affiliations_csrankings import enrich_affiliations

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
        enrich_affiliations(
            authors_file=Path(str(authors_path)),
            output_file=Path(str(output_path)),
            name_index=name_index,
            data_dir=str(tmp_website),
            verbose=False,
        )

        # Check that author_index.json was updated
        updated_index = read_json(str(tmp_website / "assets" / "data" / "author_index.json"))
        bob = next(e for e in updated_index if e["name"] == "Bob Jones")
        assert bob["affiliation"] == "UC Berkeley"
        assert bob["affiliation_source"] == "csrankings"

    def test_enrichment_without_data_dir_still_works(self, tmp_website, sample_authors):
        """When data_dir is None, enrichment works but doesn't touch the index."""
        from pathlib import Path

        from src.enrichers.enrich_affiliations_csrankings import enrich_affiliations

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
        assert not os.path.exists(str(tmp_website / "assets" / "data" / "author_index.json"))


class TestAEMemberIndexIntegration:
    """Verify enrich_affiliations_ae_members updates author_index.json."""

    def test_ae_member_fills_missing_affiliation(self, tmp_website, sample_authors, sample_index):
        from pathlib import Path

        from src.enrichers.enrich_affiliations_ae_members import enrich_affiliations

        # Write authors.json (Bob has no affiliation)
        authors_path = tmp_website / "assets" / "data" / "authors.json"
        write_json(str(authors_path), sample_authors[:2])  # Alice + Bob

        # Write author_index.json
        write_json(
            str(tmp_website / "assets" / "data" / "author_index.json"),
            sample_index,
        )

        # Write ae_members.json with Bob's affiliation
        ae_members = [
            {"name": "Bob Jones", "affiliation": "Georgia Tech", "conferences": [["ATC", 2024, "member"]]},
            {"name": "Eve Unknown", "affiliation": "CMU", "conferences": [["OSDI", 2024, "member"]]},
        ]
        write_json(str(tmp_website / "assets" / "data" / "ae_members.json"), ae_members)

        output_path = tmp_website / "assets" / "data" / "authors_out.json"
        stats = enrich_affiliations(
            authors_file=Path(str(authors_path)),
            output_file=Path(str(output_path)),
            data_dir=str(tmp_website),
        )

        assert stats["enriched"] == 1  # Bob filled in

        # Check authors.json output
        enriched = read_json(str(output_path))
        bob = next(a for a in enriched if a["name"] == "Bob Jones")
        assert bob["affiliation"] == "Georgia Tech"

        # Alice should keep her existing affiliation
        alice = next(a for a in enriched if a["name"] == "Alice Smith")
        assert alice["affiliation"] == "MIT"

        # Check author_index.json was updated
        updated_index = read_json(str(tmp_website / "assets" / "data" / "author_index.json"))
        bob_idx = next(e for e in updated_index if e["name"] == "Bob Jones")
        assert bob_idx["affiliation"] == "Georgia Tech"
        assert bob_idx["affiliation_source"] == "ae_committee"

    def test_ae_member_does_not_overwrite_existing(self, tmp_website, sample_authors):
        """AE member enrichment should NOT overwrite existing affiliations."""
        from pathlib import Path

        from src.enrichers.enrich_affiliations_ae_members import enrich_affiliations

        authors_path = tmp_website / "assets" / "data" / "authors.json"
        write_json(str(authors_path), sample_authors[:1])  # Alice only (has MIT)

        ae_members = [{"name": "Alice Smith", "affiliation": "Stanford", "conferences": []}]
        write_json(str(tmp_website / "assets" / "data" / "ae_members.json"), ae_members)

        output_path = tmp_website / "assets" / "data" / "authors_out.json"
        stats = enrich_affiliations(
            authors_file=Path(str(authors_path)),
            output_file=Path(str(output_path)),
            data_dir=str(tmp_website),
        )

        assert stats["enriched"] == 0
        enriched = read_json(str(output_path))
        assert enriched[0]["affiliation"] == "MIT"  # unchanged


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

        enrich(
            authors_file=str(yml_path),
            papers_file=str(tmp_website / "assets" / "data" / "papers.json"),
            data_dir=str(tmp_website),
        )

        updated_index = read_json(str(tmp_website / "assets" / "data" / "author_index.json"))
        bob = next(e for e in updated_index if e["name"] == "Bob Jones")
        assert bob["affiliation"] == "Carnegie Mellon University"
        assert bob["affiliation_source"] == "openalex"
