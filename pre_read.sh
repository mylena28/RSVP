#!/usr/bin/env bash
# Scientific Pre-Reading Workflow.
#
# Usage:
#   ./pre_read.sh paper.pdf
#   ./pre_read.sh paper.pdf --wpm 300
#   ./pre_read.sh paper.pdf --wpm 300 --mode dist
#
# AI preprocessing (one-time per PDF, requires GEMINI_API_KEY):
#   Put your key in a .env file:  echo "GEMINI_API_KEY=AIza..." > .env
#   Get a free key at: https://aistudio.google.com/apikey
#   ./pre_read.sh paper.pdf              # auto-runs both if key set + no sidecar
#   ./pre_read.sh paper.pdf --detect-equations   # force re-detect equations
#   ./pre_read.sh paper.pdf --clean-text         # force re-clean garbled text

set -euo pipefail

# Load .env if present (never committed — see .gitignore)
if [[ -f "$(dirname "$0")/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$(dirname "$0")/.env"
    set +a
fi

IMAGE="rsvp"
PDF=""
DETECT=false
CLEAN=false
PASS_ARGS=()

for arg in "$@"; do
    if [[ "$arg" == "--detect-equations" ]]; then
        DETECT=true
    elif [[ "$arg" == "--clean-text" ]]; then
        CLEAN=true
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

# Auto-run AI preprocessing if key is set and sidecars are missing
EQ_SIDECAR="${PDF%.pdf}.equations.json"
CLEAN_SIDECAR="${PDF%.pdf}.clean.json"
if [[ -n "$PDF" && -n "${GEMINI_API_KEY:-}" && ! -f "$EQ_SIDECAR" ]]; then
    DETECT=true
fi
if [[ -n "$PDF" && -n "${GEMINI_API_KEY:-}" && ! -f "$CLEAN_SIDECAR" ]]; then
    CLEAN=true
fi

if [[ "$DETECT" == true && -n "$PDF" ]]; then
    echo "  Detecting equations via Gemini vision (one-time)…"
    docker run --rm \
        --entrypoint python \
        -e GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
        -e TERM="${TERM:-xterm-256color}" \
        -v "$(pwd):/data" \
        -w /data \
        "$IMAGE" /app/detect_equations.py "$PDF"
fi

if [[ "$CLEAN" == true && -n "$PDF" ]]; then
    echo "  Cleaning garbled text via Gemini vision (one-time)…"
    docker run --rm \
        --entrypoint python \
        -e GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
        -e TERM="${TERM:-xterm-256color}" \
        -v "$(pwd):/data" \
        -w /data \
        "$IMAGE" /app/clean_text.py "$PDF"
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
