"""Tests for src/generators/generate_repo_stats helpers.

Network calls (GitHub/Zenodo/Figshare) are NOT exercised; we test only the
pure aggregation function ``aggregate_stats`` which takes pre-collected stat
dicts and rolls them up into the final structure.
"""

from src.generators.generate_repo_stats import aggregate_stats


def _gh(conference="SOSP", year=2023, *, stars=10, forks=2, title="Repo", url="https://github.com/x/y"):
    return {
        "conference": conference,
        "year": year,
        "title": title,
        "url": url,
        "source": "github",
        "github_stars": stars,
        "github_forks": forks,
        "description": "A test repo",
        "language": "Python",
        "name": "y",
        "pushed_at": "2023-01-01",
    }


def _zen(conference="SOSP", year=2023, *, views=100, downloads=5):
    return {
        "conference": conference,
        "year": year,
        "title": "Z",
        "url": "https://zenodo.org/record/123",
        "source": "zenodo",
        "zenodo_views": views,
        "zenodo_downloads": downloads,
    }


class TestAggregateStats:
    def test_empty_input(self):
        agg = aggregate_stats([])
        assert agg["overall"]["github_repos"] == 0
        assert agg["overall"]["total_stars"] == 0
        assert agg["by_conference"] == []
        assert agg["by_year"] == []
        assert agg["all_github_repos"] == []

    def test_single_github_repo(self):
        agg = aggregate_stats([_gh(stars=15, forks=3)])
        assert agg["overall"]["github_repos"] == 1
        assert agg["overall"]["total_stars"] == 15
        assert agg["overall"]["total_forks"] == 3
        assert agg["overall"]["max_stars"] == 15
        assert agg["overall"]["avg_stars"] == 15.0
        assert agg["overall"]["avg_forks"] == 3.0

    def test_aggregates_by_conference(self):
        stats = [
            _gh(conference="SOSP", year=2023, stars=10, url="u1"),
            _gh(conference="SOSP", year=2023, stars=20, url="u2"),
            _gh(conference="OSDI", year=2024, stars=5, url="u3"),
        ]
        agg = aggregate_stats(stats)
        by_conf = {c["name"]: c for c in agg["by_conference"]}
        assert by_conf["SOSP"]["github_repos"] == 2
        assert by_conf["SOSP"]["total_stars"] == 30
        assert by_conf["SOSP"]["max_stars"] == 20
        assert by_conf["SOSP"]["avg_stars"] == 15.0
        assert by_conf["OSDI"]["github_repos"] == 1
        assert by_conf["OSDI"]["total_stars"] == 5

    def test_aggregates_by_year(self):
        stats = [
            _gh(year=2022, stars=4, url="u1"),
            _gh(year=2023, stars=8, url="u2"),
            _gh(year=2023, stars=12, url="u3"),
        ]
        agg = aggregate_stats(stats)
        by_year = {y["year"]: y for y in agg["by_year"]}
        assert by_year[2022]["github_repos"] == 1
        assert by_year[2022]["total_stars"] == 4
        assert by_year[2023]["github_repos"] == 2
        assert by_year[2023]["total_stars"] == 20
        assert by_year[2023]["avg_stars"] == 10.0

    def test_zenodo_tracked_separately(self):
        stats = [
            _gh(stars=5, url="u1"),
            _zen(views=200, downloads=10),
        ]
        agg = aggregate_stats(stats)
        assert agg["overall"]["github_repos"] == 1
        assert agg["overall"]["zenodo_repos"] == 1
        assert agg["overall"]["total_views"] == 200
        assert agg["overall"]["total_downloads"] == 10

    def test_all_github_repos_listed(self):
        stats = [
            _gh(stars=1, url="u1", title="A"),
            _gh(stars=2, url="u2", title="B"),
        ]
        agg = aggregate_stats(stats)
        titles = {e["title"] for e in agg["all_github_repos"]}
        assert titles == {"A", "B"}

    def test_top_repos_capped_at_5(self):
        stats = [_gh(stars=i, url=f"u{i}", title=f"R{i}") for i in range(1, 11)]
        agg = aggregate_stats(stats)
        sosp = agg["by_conference"][0]
        assert len(sosp["top_repos"]) == 5
        # Sorted by stars descending → R10 is first
        assert sosp["top_repos"][0]["title"] == "R10"

    def test_handles_none_stars_forks(self):
        # github_stats may return None for stars/forks.
        s = _gh(stars=None, forks=None)
        agg = aggregate_stats([s])
        assert agg["overall"]["github_repos"] == 1
        assert agg["overall"]["total_stars"] == 0
        assert agg["overall"]["total_forks"] == 0
