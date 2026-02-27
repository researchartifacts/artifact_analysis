#!/bin/bash
# Run the full data-generation pipeline.
# Usage: ./run_pipeline.sh [--output_dir DIR] [--conf_regex REGEX]
#        [--http_proxy URL] [--https_proxy URL]
#        [--save-results [--results_dir DIR] [--push]]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
} > "$SCRIPT_DIR/.last_pipeline_args"

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
LOGFILE="$SCRIPT_DIR/.last_pipeline.log"
exec > >(tee "$LOGFILE") 2>&1

echo "[1/8] Checking DBLP freshness..."
"$SCRIPT_DIR/download_dblp.sh" --auto

echo "[2/8] Generating statistics (sysartifacts + secartifacts + USENIX)..."
$PYTHON generate_statistics.py --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "❌ Statistics failed"; exit 1; }

echo "[3/8] Generating repository statistics (stars, forks, etc.)..."
$PYTHON generate_repo_stats.py --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Repository stats failed (may need API access)"; }

echo "[4/8] Generating visualizations..."
$PYTHON generate_visualizations.py --data_dir "$OUTPUT_DIR" \
    || { echo "❌ Visualizations failed"; exit 1; }

echo "[5/8] Generating author statistics..."
if [ -f "dblp.xml.gz" ]; then
    $PYTHON generate_author_stats.py \
        --dblp_file dblp.xml.gz --data_dir "$OUTPUT_DIR" --output_dir "$OUTPUT_DIR" \
        || { echo "❌ Author statistics failed"; exit 1; }
else
    echo "⚠️  Skipped (dblp.xml.gz not found)"
fi

echo "[6/8] Generating per-area author data..."
$PYTHON generate_area_authors.py --data_dir "$OUTPUT_DIR" \
    || { echo "❌ Area author generation failed"; exit 1; }

echo "[7/8] Generating committee statistics..."
$PYTHON generate_committee_stats.py --conf_regex "$CONF_REGEX" --output_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Committee statistics failed (may need network access)"; }

echo "[8/8] Generating combined rankings..."
$PYTHON generate_combined_rankings.py --data_dir "$OUTPUT_DIR" \
    || { echo "⚠️  Combined rankings failed"; }

echo "✅ Pipeline complete! Output in $OUTPUT_DIR"

# ── Save results snapshot ─────────────────────────────────────────────────────
if [ "$SAVE_RESULTS" = true ]; then
    echo ""
    echo "[9/9] Saving results snapshot..."
    SAVE_ARGS="--results_dir $RESULTS_DIR --output_dir $OUTPUT_DIR"
    if [ -n "$https_proxy" ]; then
        SAVE_ARGS="$SAVE_ARGS --https_proxy $https_proxy"
    fi
    if [ "$DO_PUSH" = true ]; then
        SAVE_ARGS="$SAVE_ARGS --push"
    fi
    "$SCRIPT_DIR/save_results.sh" $SAVE_ARGS
fi
