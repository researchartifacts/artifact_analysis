"""Tests for src/generators/committee_stats/{classification,charting} helpers.

Focus on pure helpers that do not require network downloads. We avoid
``_build_university_index`` because it downloads a large external JSON file.
"""

from src.generators.committee_stats import charting, classification

# ── classification ──────────────────────────────────────────────────────────


class TestCleanAffiliation:
    def test_strips_html_tags(self):
        # HTML tags are removed verbatim (no space substituted in their place).
        assert classification._clean_affiliation("MIT<br>USA") == "MITUSA"
        assert classification._clean_affiliation("MIT <br> USA") == "MIT USA"

    def test_strips_markdown_markers(self):
        assert classification._clean_affiliation("**MIT**") == "MIT"
        assert classification._clean_affiliation("_Stanford_") == "Stanford"

    def test_collapses_whitespace(self):
        assert classification._clean_affiliation("  MIT   CSAIL  ") == "MIT CSAIL"

    def test_empty_string(self):
        assert classification._clean_affiliation("") == ""


class TestClassifyMember:
    def _make_indexes(self):
        from pytrie import Trie

        name_index = {
            "mit": {"name": "MIT", "country": "United States"},
            "stanford university": {"name": "Stanford University", "country": "United States"},
            "eth zurich": {"name": "ETH Zurich", "country": "Switzerland"},
        }
        return Trie(**name_index), name_index

    def test_prefix_match(self):
        prefix_tree, name_index = self._make_indexes()
        # ``Trie.values(prefix=p)`` returns values whose KEY starts with p,
        # so the affiliation must be a (lowercase) prefix of an indexed key.
        country, inst = classification.classify_member("MIT", prefix_tree, name_index)
        assert country == "United States"
        assert inst == "MIT"

    def test_exact_match(self):
        prefix_tree, name_index = self._make_indexes()
        country, inst = classification.classify_member("Stanford University", prefix_tree, name_index)
        assert country == "United States"
        assert inst == "Stanford University"

    def test_fuzzy_match_threshold(self):
        # A near-identical string falls through prefix-tree but matches via
        # fuzz.ratio > 80.
        prefix_tree, name_index = self._make_indexes()
        country, inst = classification.classify_member(
            "stanford universty",
            prefix_tree,
            name_index,  # missing 'i'
        )
        assert country == "United States"
        assert inst == "Stanford University"

    def test_empty_returns_none(self):
        prefix_tree, name_index = self._make_indexes()
        country, inst = classification.classify_member("", prefix_tree, name_index)
        assert country is None
        assert inst is None

    def test_unknown_below_threshold(self):
        prefix_tree, name_index = self._make_indexes()
        country, inst = classification.classify_member("Totally Unknown Place That Is Long", prefix_tree, name_index)
        assert country is None
        assert inst is None


class TestAggregateAcrossConferences:
    def test_basic_split(self):
        per_conf = {
            "sosp2023": {"United States": 2, "Germany": 1},
            "ndss2023": {"United States": 3, "Switzerland": 1},
        }
        conf_to_area = {"sosp2023": "systems", "ndss2023": "security"}
        overall, sys_d, sec_d = classification._aggregate_across_conferences(per_conf, conf_to_area)
        assert overall == {"United States": 5, "Germany": 1, "Switzerland": 1}
        assert sys_d == {"United States": 2, "Germany": 1}
        assert sec_d == {"United States": 3, "Switzerland": 1}

    def test_unknown_area_in_overall_only(self):
        per_conf = {"foo2023": {"X": 4}}
        overall, sys_d, sec_d = classification._aggregate_across_conferences(per_conf, {"foo2023": "unknown"})
        assert overall == {"X": 4}
        assert sys_d == {}
        assert sec_d == {}

    def test_empty(self):
        overall, sys_d, sec_d = classification._aggregate_across_conferences({}, {})
        assert overall == {} and sys_d == {} and sec_d == {}


class TestTopN:
    def test_sorts_desc_and_truncates(self):
        d = {"A": 5, "B": 10, "C": 1, "D": 7}
        top = classification._top_n(d, n=2)
        assert top == [("B", 10), ("D", 7)]

    def test_returns_all_when_n_larger(self):
        d = {"A": 1, "B": 2}
        top = classification._top_n(d, n=10)
        assert sorted(top) == [("A", 1), ("B", 2)]

    def test_empty(self):
        assert classification._top_n({}, n=5) == []


class TestComputeMemberStats:
    def _basic_inputs(self):
        all_results = {
            "sosp2023": [
                {"name": "Alice Smith", "affiliation": "MIT", "role": "member"},
                {"name": "Bob Jones", "affiliation": "Stanford", "role": "chair"},
            ],
            "sosp2024": [
                {"name": "Alice Smith", "affiliation": "MIT", "role": "member"},
            ],
            "ndss2023": [
                {"name": "Alice Smith", "affiliation": "MIT CSAIL", "role": "member"},
            ],
        }
        conf_to_area = {
            "sosp2023": "systems",
            "sosp2024": "systems",
            "ndss2023": "security",
        }
        return all_results, conf_to_area

    def test_alice_appears_in_both_areas(self):
        all_results, conf_to_area = self._basic_inputs()
        members, sys_m, sec_m, _ = classification._compute_member_stats(all_results, conf_to_area, classified={})
        alice = next(m for m in members if m["name"].startswith("Alice"))
        # 2 systems + 1 security = 3 total memberships
        assert alice["total_memberships"] == 3
        assert alice["area"] == "both"

    def test_chair_count_tracked(self):
        all_results, conf_to_area = self._basic_inputs()
        members, sys_m, sec_m, _ = classification._compute_member_stats(all_results, conf_to_area, classified={})
        bob = next(m for m in members if m["name"].startswith("Bob"))
        assert bob["chair_count"] == 1
        assert bob["area"] == "systems"

    def test_systems_only_subset(self):
        all_results, conf_to_area = self._basic_inputs()
        _, sys_m, _, _ = classification._compute_member_stats(all_results, conf_to_area, classified={})
        names = {m["name"] for m in sys_m}
        # Both Alice and Bob have systems memberships
        assert any(n.startswith("Alice") for n in names)
        assert any(n.startswith("Bob") for n in names)

    def test_security_only_subset(self):
        all_results, conf_to_area = self._basic_inputs()
        _, _, sec_m, _ = classification._compute_member_stats(all_results, conf_to_area, classified={})
        names = {m["name"] for m in sec_m}
        # Only Alice has security membership
        assert any(n.startswith("Alice") for n in names)
        assert not any(n.startswith("Bob") for n in names)

    def test_skips_empty_names(self):
        all_results = {"sosp2023": [{"name": "", "affiliation": "MIT"}]}
        members, _, _, _ = classification._compute_member_stats(all_results, {"sosp2023": "systems"}, classified={})
        assert members == []

    def test_empty_input(self):
        members, sys_m, sec_m, summary = classification._compute_member_stats({}, {}, classified={})
        assert members == []
        assert sys_m == []
        assert sec_m == []


# ── charting ────────────────────────────────────────────────────────────────


class TestGenerateCommitteeCharts:
    """Smoke tests that exercise the matplotlib code paths and verify SVG output."""

    def _detail(self):
        return {
            "by_country": {
                "overall": [
                    {"name": "United States", "count": 10},
                    {"name": "Germany", "count": 5},
                    {"name": "China", "count": 4},
                ],
                "systems": [{"name": "United States", "count": 6}],
                "security": [{"name": "Germany", "count": 3}],
            },
            "by_continent": {
                "overall": [
                    {"name": "North America", "count": 10},
                    {"name": "Europe", "count": 7},
                ],
                "systems": [{"name": "North America", "count": 6}],
                "security": [{"name": "Europe", "count": 4}],
            },
            "by_institution": {
                "overall": [
                    {"name": "MIT", "count": 4},
                    {"name": "Stanford", "count": 3},
                ],
                "systems": [{"name": "MIT", "count": 4}],
                "security": [{"name": "Stanford", "count": 3}],
            },
            "by_year": {
                "continent": {
                    2022: {"North America": 5, "Europe": 3},
                    2023: {"North America": 6, "Europe": 4, "Asia": 2},
                }
            },
        }

    def _summary(self):
        return {
            "committee_sizes": [
                {"year": 2022, "area": "systems", "size": 25},
                {"year": 2022, "area": "security", "size": 18},
                {"year": 2023, "area": "systems", "size": 30},
                {"year": 2023, "area": "security", "size": 22},
            ]
        }

    def test_writes_expected_svgs(self, tmp_path):
        charting.generate_committee_charts(self._summary(), self._detail(), tmp_path)
        charts_dir = tmp_path / "assets" / "charts"
        # Spot-check a few of the expected outputs
        for name in [
            "committee_countries.svg",
            "committee_continents.svg",
            "committee_institutions.svg",
            "committee_sizes.svg",
            "committee_continent_timeline.svg",
        ]:
            assert (charts_dir / name).exists(), f"missing {name}"
            assert (charts_dir / name).stat().st_size > 0

    def test_handles_empty_detail(self, tmp_path):
        # Empty detail: no charts should be produced (functions return early),
        # but the call must not raise.
        empty_detail = {
            "by_country": {"overall": [], "systems": [], "security": []},
            "by_continent": {"overall": [], "systems": [], "security": []},
            "by_institution": {"overall": [], "systems": [], "security": []},
            "by_year": {"continent": {}},
        }
        empty_summary = {"committee_sizes": []}
        # Should not raise.
        charting.generate_committee_charts(empty_summary, empty_detail, tmp_path)
        # Charts dir is created but contains no files (or only ones that
        # happened to have non-empty data).
        charts_dir = tmp_path / "assets" / "charts"
        assert charts_dir.exists()
        assert list(charts_dir.iterdir()) == []
