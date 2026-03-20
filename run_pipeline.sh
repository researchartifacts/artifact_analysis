#!/bin/bash
# Run the full data-generation pipeline.
# Usage: ./run_pipeline.sh [--output_dir DIR] [--conf_regex REGEX]
#        [--http_proxy URL] [--https_proxy URL]
#        [--save-results [--results_dir DIR] [--push]]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"
DATA_DIR="$SCRIPT_DIR/data"
LOG_DIR="$SCRIPT_DIR/logs"
DBLP_FILE="$DATA_DIR/dblp/dblp.xml.gz"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"

OUTPUT_DIR="../researchartifacts.github.io"
CONF_REGEX=".*20[12][0-9]"
SAVE_RESULTS=false
RESULTS_DIR="../artifact_analysis_results"
DO_PUSH=false

while [ $# -gt 0 ]; do
    case "$1" in
        --output_dir)   OUTPUT_DIR="$2";   shift 2 ;;
        --conf_regex)   CONF_REGEX="$2";   shift 2 ;;
        --http_proxy)   export http_proxy="$2" HTTP_PROXY="$2"; shift 2 ;;
        --https_proxy)  export https_proxy="$2"; shift 2 ;;
        --save-results) SAVE_RESULTS=true; shift ;;
        --results_dir)  RESULTS_DIR="$2";  shift 2 ;;
        --push)         DO_PUSH=true;      shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[ -n "$http_proxy" ] && echo "http_proxy: $http_proxy"
[ -n "$https_proxy" ] && echo "https_proxy: $https_proxy"

# Record pipeline arguments for the results snapshot
{
    echo "conf_regex: $CONF_REGEX"
    echo "output_dir: $OUTPUT_DIR"
    echo "save_results: $SAVE_RESULTS"
    echo "results_dir: $RESULTS_DIR"
    echo "push: $DO_PUSH"
    echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S %Z')"
} > "$LOG_DIR/last_pipeline_args"

# Auto-detect HTTPS proxy from HTTP proxy if not set
if [ -z "$https_proxy" ] && [ -n "$http_proxy" ]; then
    export https_proxy="$http_proxy" HTTPS_PROXY="$http_proxy"
    echo "Auto-set https_proxy from http_proxy: $https_proxy"
fi

if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Error: Output directory not found: $OUTPUT_DIR"
    exit 1
fi

# Auto-detect GITHUB_TOKEN from gh CLI if not already set
if [ -z "$GITHUB_TOKEN" ] && [ -z "$GH_TOKEN" ]; then
    _gh="$(command -v gh 2>/dev/null || echo "$HOME/.local/bin/gh")"
    if [ -x "$_gh" ]; then
        _tok="$("$_gh" auth token 2>/dev/null)"
        if [ -n "$_tok" ]; then
            export GITHUB_TOKEN="$_tok"
            echo "Using GitHub token from gh CLI (5,000 req/hr)"
        fi
    fi
fi
[ -n "$GITHUB_TOKEN" ] || [ -n "$GH_TOKEN" ] || echo "⚠️  No GITHUB_TOKEN set — limited to 60 GitHub API requests/hr"

# Test connectivity
if ! curl -sL --max-time 10 https://api.github.com/repos/sysartifacts/sysartifacts.github.io > /dev/null 2>&1; then
    echo "❌ Cannot reach GitHub API"
    exit 1
fi

# Ensure venv
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -q --quiet pyyaml requests beautifulsoup4 matplotlib lxml pytrie thefuzz > /dev/null 2>&1
fi

PYTHON=".venv/bin/python"
export PYTHONUNBUFFERED=1

# Start capturing pipeline log
LOGFILE="$LOG_DIR/last_pipeline.log"
exec > >(tee "$LOGFILE") 2>&1

echo "[1/10] Checking DBLP freshness..."
"$SCRIPTS_DIR/download_dblp.sh" --auto

echo "[2/10] Generating statistics (sysartifacts + secartifacts + USENIX)..."
$PYTHON -m src.generators.generate_statistics --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "❌ Statistics failed"; exit 1; }

echo "[3/13] Generating repository statistics (stars, forks, etc.)..."
$PYTHON -m src.generators.generate_repo_stats --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Repository stats failed (may need API access)"; }

echo "[3b/13] Generating artifact availability (URL liveness)..."
$PYTHON -m src.generators.generate_artifact_availability --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Artifact availability check failed (may need network access)"; }

echo "[3c/13] Generating AE participation statistics (DBLP paper counts)..."
$PYTHON -m src.generators.generate_participation_stats --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Participation stats failed (may need DBLP access)"; }

echo "[4/13] Artifact citation stats — SKIPPED (disabled by default)."
echo "       OpenAlex citation counts for artifact DOIs are unreliable."
echo "       All reported citations were false positives or self-citations."
echo "       To re-enable: pass --enable-citations to generate_artifact_citations."
# $PYTHON -m src.generators.generate_artifact_citations --data_dir "$OUTPUT_DIR" --enable-citations \
#     || { echo "⚠️  Artifact citations failed (may need network access)"; }

echo "[5/12] Cited artifacts lists — SKIPPED (no citation data)."
# $PYTHON -m src.generators.generate_cited_artifacts_list --data_dir "$OUTPUT_DIR" \
#     || { echo "⚠️  Cited artifacts list generation failed"; }

echo "[6/12] Generating visualizations..."
$PYTHON -m src.generators.generate_visualizations --data_dir "$OUTPUT_DIR" \
    || { echo "❌ Visualizations failed"; exit 1; }

echo "[7/12] Generating author statistics..."
if [ -f "$DBLP_FILE" ]; then
    $PYTHON -m src.generators.generate_author_stats \
        --dblp_file "$DBLP_FILE" --data_dir "$OUTPUT_DIR" --output_dir "$OUTPUT_DIR" \
        || { echo "❌ Author statistics failed"; exit 1; }
else
    echo "⚠️  Skipped ($DBLP_FILE not found)"
fi

echo "[8/12] Generating per-area author data..."
$PYTHON -m src.generators.generate_area_authors --data_dir "$OUTPUT_DIR" \
    || { echo "❌ Area author generation failed"; exit 1; }

echo "[9/12] Generating committee statistics..."
$PYTHON -m src.generators.generate_committee_stats --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Committee statistics failed (may need network access)"; }

echo "[10/12] Generating combined rankings..."
$PYTHON -m src.generators.generate_combined_rankings --data_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Combined rankings failed"; }

echo "[11/12] Generating institution rankings..."
$PYTHON -m src.generators.generate_institution_rankings --data_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Institution rankings failed"; }

echo "[12/12] Generating author profiles..."
$PYTHON -m src.generators.generate_author_profiles --data_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Author profiles failed"; }

echo "[13/13] Generating search data..."
$PYTHON -m src.generators.generate_search_data --data_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Search data generation failed"; }

echo "[14/14] Updating ranking history snapshots..."
$PYTHON -m src.generators.generate_ranking_history --data_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Ranking history update failed"; }

echo "✅ Pipeline complete! Output in $OUTPUT_DIR"

# ── Save results snapshot ─────────────────────────────────────────────────────
if [ "$SAVE_RESULTS" = true ]; then
    echo ""
    echo "[12/12] Saving results snapshot..."
    SAVE_ARGS="--results_dir $RESULTS_DIR --output_dir $OUTPUT_DIR"
    if [ -n "$https_proxy" ]; then
        SAVE_ARGS="$SAVE_ARGS --https_proxy $https_proxy"
    fi
    if [ "$DO_PUSH" = true ]; then
        SAVE_ARGS="$SAVE_ARGS --push"
    fi
    "$SCRIPT_DIR/save_results.sh" $SAVE_ARGS
fi
