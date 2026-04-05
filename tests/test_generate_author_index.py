"""Tests for src.generators.generate_author_index — the index builder."""

import json
import os
import pytest
from tests.conftest import write_json, read_json
from src.generators.generate_author_index import (
    load_existing_index,
    load_authors_json,
    build_index,
)


class TestLoadExistingIndex:
    def test_missing_file(self, tmp_path):
        entries, by_name, max_id = load_existing_index(str(tmp_path / "nope.json"))
        assert entries == []
        assert by_name == {}
        assert max_id == 0

    def test_loads_and_indexes(self, tmp_path, sample_index):
        p = tmp_path / "index.json"
        write_json(str(p), sample_index)
        entries, by_name, max_id = load_existing_index(str(p))
        assert len(entries) == 2
        assert max_id == 2
        assert "Alice Smith" in by_name


class TestLoadAuthorsJson:
    def test_missing_file(self, tmp_path):
        result = load_authors_json(str(tmp_path / "nope.json"))
        assert result == []

    def test_loads_list(self, tmp_path, sample_authors):
        p = tmp_path / "authors.json"
        write_json(str(p), sample_authors)
        result = load_authors_json(str(p))
        assert len(result) == 3


class TestBuildIndex:
    def test_fresh_build_assigns_sequential_ids(self, sample_authors):
        index, stats = build_index(sample_authors, {}, 0)
        ids = [e["id"] for e in index]
        assert ids == [1, 2, 3]
        assert stats["new"] == 3
        assert stats["preserved"] == 0
        assert stats["total"] == 3

    def test_preserves_existing_ids(self, sample_authors, sample_index):
        by_name = {e["name"]: e for e in sample_index}
        index, stats = build_index(sample_authors, by_name, 2)
        id_map = {e["name"]: e["id"] for e in index}
        # Alice and Bob keep their existing IDs
        assert id_map["Alice Smith"] == 1
        assert id_map["Bob Jones"] == 2
        # Carol is new, gets next ID
        assert id_map["Carol White"] == 3
        assert stats["preserved"] == 2
        assert stats["new"] == 1

    def test_no_id_reuse(self, sample_authors, sample_index):
        """Even if some existing authors are missing from new data, IDs don't reuse."""
        # Only Alice in new data — Bob is gone
        new_authors = [a for a in sample_authors if a["name"] == "Alice Smith"]
        new_authors.append({"name": "New Person", "display_name": "New Person"})
        by_name = {e["name"]: e for e in sample_index}
        index, stats = build_index(new_authors, by_name, 2)
        ids = {e["name"]: e["id"] for e in index}
        assert ids["Alice Smith"] == 1
        assert ids["New Person"] == 3  # not 2 (Bob's old ID)

    def test_output_sorted_by_id(self, sample_authors, sample_index):
        by_name = {e["name"]: e for e in sample_index}
        index, _ = build_index(sample_authors, by_name, 2)
        ids = [e["id"] for e in index]
        assert ids == sorted(ids)

    def test_stats_consistency(self, sample_authors, sample_index):
        by_name = {e["name"]: e for e in sample_index}
        _, stats = build_index(sample_authors, by_name, 2)
        assert stats["total"] == stats["preserved"] + stats["new"]
        assert stats["with_affiliation"] <= stats["total"]
        assert stats["max_id"] >= stats["total"]

    def test_skips_empty_names(self, sample_authors):
        authors = sample_authors + [{"name": "", "display_name": "Ghost"}]
        index, stats = build_index(authors, {}, 0)
        assert stats["total"] == 3  # Ghost skipped

    def test_affiliation_change_detected(self, sample_index):
        """When authors.json has a new affiliation, index detects the change."""
        by_name = {e["name"]: e for e in sample_index}
        authors = [
            {"name": "Alice Smith", "display_name": "Alice Smith", "affiliation": "Google"},
        ]
        index, stats = build_index(authors, by_name, 2)
        alice = index[0]
        assert alice["affiliation"] == "Google"
        assert stats["affiliation_changed"] == 1
        assert len(alice["affiliation_history"]) == 1
        assert alice["affiliation_history"][0]["affiliation"] == "MIT"

    def test_no_spurious_history_on_same_affiliation(self, sample_index):
        by_name = {e["name"]: e for e in sample_index}
        authors = [
            {"name": "Alice Smith", "display_name": "Alice Smith", "affiliation": "MIT"},
        ]
        index, stats = build_index(authors, by_name, 2)
        assert stats["affiliation_changed"] == 0
        assert index[0]["affiliation_history"] == []

    def test_new_author_with_affiliation_gets_source(self):
        authors = [{"name": "New One", "display_name": "New One", "affiliation": "ETH Zurich"}]
        index, _ = build_index(authors, {}, 0)
        assert index[0]["affiliation_source"] == "dblp"
        assert index[0]["affiliation_updated"]  # non-empty

    def test_new_author_without_affiliation(self):
        authors = [{"name": "New One", "display_name": "New One", "affiliation": ""}]
        index, _ = build_index(authors, {}, 0)
        assert index[0]["affiliation_source"] == ""
        assert index[0]["affiliation_updated"] == ""

    def test_deep_copy_safety(self, sample_index):
        """Modifying returned entries doesn't mutate original existing_by_name."""
        by_name = {e["name"]: e for e in sample_index}
        original_history_id = id(sample_index[0]["affiliation_history"])
        index, _ = build_index(
            [{"name": "Alice Smith", "display_name": "Alice Smith", "affiliation": "MIT"}],
            by_name, 2,
        )
        # The index entry's history list should be a different object
        assert id(index[0]["affiliation_history"]) != original_history_id

    def test_required_fields_present(self, sample_authors):
        """Every index entry must have the full set of required fields."""
        required = {
            "id", "name", "display_name", "affiliation",
            "affiliation_source", "affiliation_updated",
            "affiliation_history", "external_ids", "category",
        }
        index, _ = build_index(sample_authors, {}, 0)
        for entry in index:
            missing = required - set(entry.keys())
            assert not missing, f"Entry {entry['name']} missing: {missing}"
