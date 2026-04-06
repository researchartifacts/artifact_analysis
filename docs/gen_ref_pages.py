"""Auto-generate API reference pages for all Python modules.

This script runs at MkDocs build time via mkdocs-gen-files.
It discovers all .py files under src/ and generates mkdocstrings pages.
"""

from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()
src = Path("src")

for path in sorted(src.rglob("*.py")):
    # Skip __pycache__, __init__ unless it has content
    if "__pycache__" in str(path):
        continue

    module_path = path.with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = Path("reference") / doc_path

    parts = tuple(module_path.parts)

    # Skip __init__.py — they're usually empty
    if parts[-1] == "__init__":
        continue

    # Build the Python import path
    python_path = ".".join(parts)

    nav[parts[1:]] = doc_path.as_posix()

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        fd.write(f"# {parts[-1]}\n\n")
        fd.write(f"::: {python_path}\n")

    mkdocs_gen_files.set_edit_path(full_doc_path, path.as_posix())

# Write navigation summary
with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())

# Write index page for the reference section
with mkdocs_gen_files.open("reference/index.md", "w") as fd:
    fd.write("# API Reference\n\n")
    fd.write("Auto-generated documentation for all Python modules in the pipeline.\n\n")
    fd.write("Browse by category:\n\n")
    fd.write("- **[Generators](generators/)** — Statistics, visualizations, and output generation\n")
    fd.write("- **[Scrapers](scrapers/)** — Data collection from conference sites\n")
    fd.write("- **[Enrichers](enrichers/)** — Affiliation and data enhancement\n")
    fd.write("- **[Models](models/)** — Pydantic data models for output schemas\n")
    fd.write("- **[Utils](utils/)** — Shared utilities and helpers\n")
