#!/usr/bin/env bash
# Scientific Pre-Reading Workflow.
#
# Usage:
#   ./pre_read.sh paper.pdf
#   ./pre_read.sh paper.pdf --wpm 300
#   ./pre_read.sh paper.pdf --wpm 300 --mode dist
#
# Equation detection (one-time, requires ANTHROPIC_API_KEY):
#   export ANTHROPIC_API_KEY=sk-ant-...
#   ./pre_read.sh paper.pdf          # auto-detects if key is set + no sidecar
#   ./pre_read.sh paper.pdf --detect-equations   # force re-detection

set -euo pipefail

IMAGE="rsvp"
PDF=""
DETECT=false
PASS_ARGS=()

for arg in "$@"; do
    if [[ "$arg" == "--detect-equations" ]]; then
        DETECT=true
    elif [[ -z "$PDF" && "$arg" == *.pdf ]]; then
        PDF="$arg"
        PASS_ARGS+=("$arg")
    else
        PASS_ARGS+=("$arg")
    fi
done

if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Building Docker image '$IMAGE'..."
    docker build -t "$IMAGE" "$(dirname "$0")"
fi

# Auto-detect equations if API key is set and sidecar is missing
SIDECAR="${PDF%.pdf}.equations.json"
if [[ -n "$PDF" && -n "${ANTHROPIC_API_KEY:-}" && ! -f "$SIDECAR" ]]; then
    DETECT=true
fi

if [[ "$DETECT" == true && -n "$PDF" ]]; then
    echo "  Detecting equations via Claude vision (one-time)…"
    docker run --rm \
        --entrypoint python \
        -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
        -e TERM="${TERM:-xterm-256color}" \
        -v "$(pwd):/data" \
        -w /data \
        "$IMAGE" /app/detect_equations.py "$PDF"
fi

SIGNAL="$(pwd)/.rsvp_open_signal"
HTML="$(pwd)/rsvp_reading.html"

# Remove any leftover signal from a previous run
rm -f "$SIGNAL"

# Background watcher: open browser whenever the signal file appears
(
    while true; do
        if [[ -f "$SIGNAL" ]]; then
            rm -f "$SIGNAL"
            # Try Linux, then macOS
            if command -v xdg-open &>/dev/null; then
                xdg-open "$HTML" 2>/dev/null &
            elif command -v open &>/dev/null; then
                open "$HTML" 2>/dev/null &
            else
                echo ""
                echo "  Open this file in your browser: $HTML"
            fi
        fi
        sleep 0.3
    done
) &
WATCHER=$!

# Cleanup watcher and temp files on exit
cleanup() {
    kill "$WATCHER" 2>/dev/null || true
    wait "$WATCHER" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Run the reader
docker run --rm -it \
    --entrypoint python \
    -e TERM="${TERM:-xterm-256color}" \
    -v "$(pwd):/data" \
    -w /data \
    "$IMAGE" /app/pre_read.py "${PASS_ARGS[@]}"
