"""Tests for the stage dependency graph."""

from src.stages import STAGES, Stage, parallel_groups, topological_order


class TestTopologicalOrder:
    def test_returns_all_stages(self):
        order = topological_order()
        assert len(order) == len(STAGES)

    def test_dependencies_precede_dependants(self):
        order = topological_order()
        positions = {s.name: i for i, s in enumerate(order)}
        for stage in order:
            for dep in stage.depends_on:
                if dep in positions:
                    assert positions[dep] < positions[stage.name], f"{dep} must come before {stage.name}"

    def test_statistics_before_author_stats(self):
        order = topological_order()
        names = [s.name for s in order]
        assert names.index("statistics") < names.index("author_stats")

    def test_combined_rankings_before_institution_rankings(self):
        order = topological_order()
        names = [s.name for s in order]
        assert names.index("combined_rankings") < names.index("institution_rankings")


class TestParallelGroups:
    def test_first_tier_has_no_deps(self):
        groups = parallel_groups()
        for stage in groups[0]:
            assert stage.depends_on == () or all(dep not in {s.name for s in STAGES} for dep in stage.depends_on)

    def test_all_stages_covered(self):
        groups = parallel_groups()
        all_names = {s.name for group in groups for s in group}
        assert all_names == {s.name for s in STAGES}

    def test_cycle_detection(self):
        import pytest

        cycle_stages = (
            Stage(name="a", module="a", description="a", depends_on=("b",)),
            Stage(name="b", module="b", description="b", depends_on=("a",)),
        )
        with pytest.raises(ValueError, match="Cycle"):
            topological_order(cycle_stages)
