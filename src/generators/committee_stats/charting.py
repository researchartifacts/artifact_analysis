"""Committee chart generation (matplotlib SVG outputs)."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np

logger = logging.getLogger(__name__)
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_CONTINENT_COLORS = {
    "Europe": "#4363D8",
    "North America": "#E6194B",
    "Asia": "#3CB44B",
    "South America": "#F58231",
    "Oceania": "#42D4F4",
    "Africa": "#F032E6",
    "Unknown": "#AAAAAA",
}


def generate_committee_charts(summary: dict, detail: dict, output_dir, inst_timeline=None) -> None:
    """Generate SVG charts for committee statistics."""
    charts_dir = Path(output_dir) / "assets/charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    _chart_top_countries(detail, charts_dir / "committee_countries.svg")
    _chart_top_countries(detail, charts_dir / "committee_countries_systems.svg", area="systems")
    _chart_top_countries(detail, charts_dir / "committee_countries_security.svg", area="security")
    _chart_continents(detail, charts_dir / "committee_continents.svg")
    _chart_continents(detail, charts_dir / "committee_continents_systems.svg", area="systems")
    _chart_continents(detail, charts_dir / "committee_continents_security.svg", area="security")
    _chart_top_institutions(detail, charts_dir / "committee_institutions.svg")
    _chart_top_institutions(detail, charts_dir / "committee_institutions_systems.svg", area="systems")
    _chart_top_institutions(detail, charts_dir / "committee_institutions_security.svg", area="security")
    _chart_committee_sizes(summary, charts_dir / "committee_sizes.svg")
    _chart_continent_timeline(detail, charts_dir / "committee_continent_timeline.svg")

    logger.info(f"  Committee charts generated in {charts_dir}")


def _chart_top_countries(detail, path, area=None, top_n=15):
    """Horizontal bar chart of top countries."""
    if area:
        data = detail["by_country"].get(area, [])
        title = f"Top Countries — {'Systems' if area == 'systems' else 'Security'}"
    else:
        data = detail["by_country"]["overall"]
        title = "Top Countries — All AE Committees"

    data = data[:top_n]
    if not data:
        return

    names = [d["name"] for d in reversed(data)]
    counts = [d["count"] for d in reversed(data)]

    fig, ax = plt.subplots(figsize=(8, max(4, len(names) * 0.4)))
    colors = plt.cm.viridis(np.linspace(0.3, 0.9, len(names)))
    ax.barh(names, counts, color=colors)
    ax.set_xlabel("Committee Members")
    ax.set_title(title, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    for i, v in enumerate(counts):
        ax.text(v + max(counts) * 0.01, i, str(v), va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _chart_continents(detail, path, area=None):
    """Pie chart of continent distribution."""
    if area:
        data = detail["by_continent"].get(area, [])
        title = f"AE Members by Continent — {'Systems' if area == 'systems' else 'Security'}"
    else:
        data = detail["by_continent"]["overall"]
        title = "AE Members by Continent"

    if not data:
        return

    names = [d["name"] for d in data]
    counts = [d["count"] for d in data]
    colors = [_CONTINENT_COLORS.get(n, "#999999") for n in names]

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        counts,
        labels=names,
        colors=colors,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.85,
    )
    for t in autotexts:
        t.set_fontsize(8)
    ax.set_title(title, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _chart_top_institutions(detail, path, area=None, top_n=20):
    """Horizontal bar chart of top institutions."""
    if area:
        data = detail["by_institution"].get(area, [])
        title = f"Top Institutions — {'Systems' if area == 'systems' else 'Security'}"
    else:
        data = detail["by_institution"]["overall"]
        title = "Top Institutions — All AE Committees"

    data = data[:top_n]
    if not data:
        return

    names = [d["name"][:40] for d in reversed(data)]  # truncate long names
    counts = [d["count"] for d in reversed(data)]

    fig, ax = plt.subplots(figsize=(10, max(5, len(names) * 0.35)))
    colors = plt.cm.plasma(np.linspace(0.2, 0.8, len(names)))
    ax.barh(names, counts, color=colors)
    ax.set_xlabel("Committee Members")
    ax.set_title(title, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    for i, v in enumerate(counts):
        ax.text(v + max(counts) * 0.01, i, str(v), va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _chart_committee_sizes(summary, path):
    """Line chart of committee sizes over time, split by area."""
    sizes = summary.get("committee_sizes", [])
    if not sizes:
        return

    sys_by_year: dict = defaultdict(int)
    sec_by_year: dict = defaultdict(int)
    for s in sizes:
        if s["year"] is None:
            continue
        if s["area"] == "systems":
            sys_by_year[s["year"]] += s["size"]
        elif s["area"] == "security":
            sec_by_year[s["year"]] += s["size"]

    all_y = sorted(set(sys_by_year.keys()) | set(sec_by_year.keys()))
    sys_vals = [sys_by_year.get(y, 0) for y in all_y]
    sec_vals = [sec_by_year.get(y, 0) for y in all_y]
    tot_vals = [s + c for s, c in zip(sys_vals, sec_vals)]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(all_y, tot_vals, marker="o", label="Total", color="#333", linewidth=2.5)
    ax.plot(all_y, sys_vals, marker="s", label="Systems", color="#2E86AB", linewidth=2)
    ax.plot(all_y, sec_vals, marker="^", label="Security", color="#A23B72", linewidth=2)
    ax.set_xlabel("Year")
    ax.set_ylabel("Committee Members")
    ax.set_title("AE Committee Sizes Over Time", fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(all_y)
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _chart_continent_timeline(detail, path):
    """Stacked area chart of continent distribution over time."""
    year_data = detail.get("by_year", {}).get("continent", {})
    if not year_data:
        return

    years = sorted(year_data.keys())
    all_continents: set = set()
    for yd in year_data.values():
        all_continents.update(yd.keys())

    continent_order = [
        "North America",
        "Europe",
        "Asia",
        "South America",
        "Oceania",
        "Africa",
        "Unknown",
    ]
    continents = [c for c in continent_order if c in all_continents]
    continents += sorted(all_continents - set(continent_order))

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = np.zeros(len(years))
    for continent in continents:
        vals = np.array([year_data.get(y, {}).get(continent, 0) for y in years], dtype=float)
        color = _CONTINENT_COLORS.get(continent, "#999999")
        ax.bar(years, vals, bottom=bottom, label=continent, color=color, width=0.7)
        bottom += vals

    ax.set_xlabel("Year")
    ax.set_ylabel("Committee Members")
    ax.set_title("AE Committee Members by Continent Over Time", fontweight="bold")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _chart_institution_timeline(inst_timeline, path):
    """Line chart showing unique institutions participating over years."""
    data = inst_timeline.get("unique_by_year", [])
    if not data:
        return

    years = [d["year"] for d in data]
    totals = [d["total"] for d in data]
    sys_vals = [d["systems"] for d in data]
    sec_vals = [d["security"] for d in data]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(years, totals, marker="o", label="Total", color="#333", linewidth=2.5)
    ax.plot(years, sys_vals, marker="s", label="Systems", color="#2E86AB", linewidth=2)
    ax.plot(years, sec_vals, marker="^", label="Security", color="#A23B72", linewidth=2)
    ax.set_xlabel("Year")
    ax.set_ylabel("Unique Institutions")
    ax.set_title("Unique Institutions on AE Committees Over Time", fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(years)
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _chart_top_institutions_over_time(inst_timeline, path, top_n=10):
    """Stacked bar chart showing top institutions' participation over years."""
    all_data = inst_timeline.get("all", {})
    if not all_data:
        return

    years = sorted(all_data.keys())

    total_by_inst: dict = defaultdict(int)
    for yr_data in all_data.values():
        for inst, count in yr_data.items():
            total_by_inst[inst] += count
    top_insts = [inst for inst, _ in sorted(total_by_inst.items(), key=lambda x: -x[1])[:top_n]]

    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = np.zeros(len(years))
    colors = plt.cm.tab10(np.linspace(0, 1, len(top_insts)))

    for i, inst in enumerate(top_insts):
        vals = np.array([all_data.get(y, {}).get(inst, 0) for y in years], dtype=float)
        label = inst[:35] if len(inst) > 35 else inst
        ax.bar(years, vals, bottom=bottom, label=label, color=colors[i], width=0.7)
        bottom += vals

    ax.set_xlabel("Year")
    ax.set_ylabel("Committee Members")
    ax.set_title("Top Institutions on AE Committees Over Time", fontweight="bold")
    ax.legend(loc="upper left", fontsize=7, bbox_to_anchor=(1.02, 1))
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)
