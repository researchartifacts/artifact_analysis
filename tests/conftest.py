"""Shared test fixtures for the artifact_analysis test suite."""

import json
import os
import pytest


@pytest.fixture
def tmp_website(tmp_path):
    """Create a minimal website-like directory tree for tests.

    Returns the root path (equivalent to the website repo root).
    Structure:
        assets/data/   — JSON outputs
        _data/         — YAML outputs
    """
    (tmp_path / "assets" / "data").mkdir(parents=True)
    (tmp_path / "_data").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_authors():
    """Minimal list of author dicts as produced by generate_author_stats."""
    return [
        {
            "name": "Alice Smith",
            "display_name": "Alice Smith",
            "affiliation": "MIT",
            "artifact_count": 5,
            "total_papers": 10,
            "category": "systems",
            "conferences": ["SOSP", "OSDI"],
            "years": [2020, 2021, 2022],
            "year_range": "2020-2022",
            "recent_count": 2,
            "artifact_citations": 30,
            "badges_available": 5,
            "badges_functional": 4,
            "badges_reproducible": 3,
            "artifact_rate": 50.0,
            "repro_rate": 60.0,
            "functional_rate": 80.0,
            "papers": [],
            "papers_without_artifacts": [],
        },
        {
            "name": "Bob Jones",
            "display_name": "Bob Jones",
            "affiliation": "",
            "artifact_count": 2,
            "total_papers": 8,
            "category": "security",
            "conferences": ["CCS"],
            "years": [2021],
            "year_range": "2021-2021",
            "recent_count": 1,
            "artifact_citations": 5,
            "badges_available": 2,
            "badges_functional": 1,
            "badges_reproducible": 0,
            "artifact_rate": 25.0,
            "repro_rate": 0.0,
            "functional_rate": 50.0,
            "papers": [],
            "papers_without_artifacts": [],
        },
        {
            "name": "Carol White",
            "display_name": "Carol White",
            "affiliation": "Stanford University",
            "artifact_count": 3,
            "total_papers": 6,
            "category": "systems",
            "conferences": ["SOSP"],
            "years": [2022, 2023],
            "year_range": "2022-2023",
            "recent_count": 2,
            "artifact_citations": 15,
            "badges_available": 3,
            "badges_functional": 3,
            "badges_reproducible": 2,
            "artifact_rate": 50.0,
            "repro_rate": 66.7,
            "functional_rate": 100.0,
            "papers": [],
            "papers_without_artifacts": [],
        },
    ]


@pytest.fixture
def sample_index():
    """A pre-existing author index with two entries."""
    return [
        {
            "id": 1,
            "name": "Alice Smith",
            "display_name": "Alice Smith",
            "affiliation": "MIT",
            "affiliation_source": "csrankings",
            "affiliation_updated": "2025-01-01",
            "affiliation_history": [],
            "external_ids": {},
            "category": "systems",
        },
        {
            "id": 2,
            "name": "Bob Jones",
            "display_name": "Bob Jones",
            "affiliation": "",
            "affiliation_source": "",
            "affiliation_updated": "",
            "affiliation_history": [],
            "external_ids": {},
            "category": "security",
        },
    ]


def write_json(path, data):
    """Helper to write a JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_json(path):
    """Helper to read a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
