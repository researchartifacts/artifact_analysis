"""Integration test: end-to-end author index pipeline.

Simulates the full workflow:
  1. generate_author_stats writes authors.json
  2. generate_author_index creates the index
  3. enricher updates an affiliation in the index
  4. generate_author_index re-syncs (detects enricher changes)
  5. generators inject author_id into outputs

This test uses synthetic fixture data and doesn't require DBLP or the network.
"""

import pytest

from src.generators.generate_author_index import build_index, load_existing_index
from src.utils.author_index import (
    load_author_index,
    save_author_index,
    update_author_affiliation,
)
from tests.conftest import read_json, write_json


@pytest.mark.integration
class TestEndToEndPipeline:
    """Simulate the pipeline phases in sequence."""

    def test_full_lifecycle(self, tmp_website, sample_authors):
        data_dir = str(tmp_website)
        index_path = str(tmp_website / "assets" / "data" / "author_index.json")
        authors_path = str(tmp_website / "assets" / "data" / "authors.json")

        # ── Phase 1: Write initial authors.json (simulate generate_author_stats)
        write_json(authors_path, sample_authors)

        # ── Phase 2: First index build — no existing index
        from src.generators.generate_author_index import load_authors_json

        authors = load_authors_json(authors_path)
        index, stats = build_index(authors, {}, 0)
        save_author_index(data_dir, index)

        assert stats["total"] == 3
        assert stats["new"] == 3
        assert stats["preserved"] == 0

        # Verify IDs are stable: Alice=1, Bob=2, Carol=3
        entries, by_name = load_author_index(data_dir)
        assert by_name["Alice Smith"]["id"] == 1
        assert by_name["Bob Jones"]["id"] == 2
        assert by_name["Carol White"]["id"] == 3

        # ── Phase 3: Enricher discovers Bob's affiliation
        bob = by_name["Bob Jones"]
        changed = update_author_affiliation(bob, "UC Berkeley", "csrankings")
        assert changed is True
        save_author_index(data_dir, sorted(by_name.values(), key=lambda e: e["id"]))

        # Verify Bob's affiliation is recorded
        _, by_name2 = load_author_index(data_dir)
        assert by_name2["Bob Jones"]["affiliation"] == "UC Berkeley"
        assert by_name2["Bob Jones"]["affiliation_source"] == "csrankings"

        # ── Phase 4: Enricher updates Bob's affiliation (institution move)
        bob2 = by_name2["Bob Jones"]
        changed = update_author_affiliation(bob2, "Google Research", "openalex")
        assert changed is True
        save_author_index(data_dir, sorted(by_name2.values(), key=lambda e: e["id"]))

        _, by_name3 = load_author_index(data_dir)
        bob3 = by_name3["Bob Jones"]
        assert bob3["affiliation"] == "Google Research"
        assert bob3["affiliation_source"] == "openalex"
        assert len(bob3["affiliation_history"]) == 1
        assert bob3["affiliation_history"][0]["affiliation"] == "UC Berkeley"

        # ── Phase 5: Re-sync index from updated authors.json
        #   Simulate: enricher also wrote to authors.json
        updated_authors = sample_authors.copy()
        updated_authors[1] = {**sample_authors[1], "affiliation": "Google Research"}
        write_json(authors_path, updated_authors)

        # Load existing index and rebuild
        _, existing_by_name, max_id = load_existing_index(index_path)
        authors = load_authors_json(authors_path)
        index2, stats2 = build_index(authors, existing_by_name, max_id)
        save_author_index(data_dir, index2)

        assert stats2["preserved"] == 3
        assert stats2["new"] == 0
        # IDs are still the same
        _, final = load_author_index(data_dir)
        assert final["Alice Smith"]["id"] == 1
        assert final["Bob Jones"]["id"] == 2
        assert final["Carol White"]["id"] == 3
        # Bob's enriched affiliation was preserved
        assert final["Bob Jones"]["affiliation"] == "Google Research"

        # ── Phase 6: New author appears
        new_authors = updated_authors + [
            {
                "name": "Dave Lee",
                "display_name": "Dave Lee",
                "affiliation": "KAIST",
                "category": "security",
            }
        ]
        write_json(authors_path, new_authors)

        _, existing_by_name, max_id = load_existing_index(index_path)
        authors = load_authors_json(authors_path)
        index3, stats3 = build_index(authors, existing_by_name, max_id)
        save_author_index(data_dir, index3)

        assert stats3["new"] == 1
        _, final2 = load_author_index(data_dir)
        # Dave gets the next ID after max existing (3)
        assert final2["Dave Lee"]["id"] == 4
        # Existing IDs unchanged
        assert final2["Alice Smith"]["id"] == 1

    def test_author_id_flows_to_profiles(self, tmp_website, sample_authors, sample_index):
        """After index build, generate_author_profiles includes author_id."""
        data_dir = str(tmp_website)

        write_json(str(tmp_website / "assets" / "data" / "authors.json"), sample_authors)
        write_json(str(tmp_website / "assets" / "data" / "author_index.json"), sample_index)
        write_json(str(tmp_website / "assets" / "data" / "ae_members.json"), [])
        write_json(str(tmp_website / "assets" / "data" / "combined_rankings.json"), [])

        from src.generators.generate_author_profiles import generate_profiles

        generate_profiles(data_dir)

        profiles = read_json(str(tmp_website / "assets" / "data" / "author_profiles.json"))
        alice = next(p for p in profiles if p["name"] == "Alice Smith")
        bob = next(p for p in profiles if p["name"] == "Bob Jones")
        assert alice["author_id"] == 1
        assert bob["author_id"] == 2
