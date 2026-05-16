#!/usr/bin/env bash
# Scientific Pre-Reading Workflow.
#
# Usage:
#   ./pre_read.sh articles/paper.pdf
#   ./pre_read.sh Lighthill1975.pdf        # bare name auto-resolves to articles/
#   ./pre_read.sh articles/paper.pdf --wpm 300
#   ./pre_read.sh articles/paper.pdf --wpm 300 --mode dist
#
# AI preprocessing (one-time per PDF, requires GEMINI_API_KEY):
#   Put your key in a .env file:  echo "GEMINI_API_KEY=AIza..." > .env
#   Get a free key at: https://aistudio.google.com/apikey
#   ./pre_read.sh articles/paper.pdf              # auto-runs both if key set + no sidecar
#   ./pre_read.sh articles/paper.pdf --detect-equations   # force re-detect equations
#   ./pre_read.sh articles/paper.pdf --clean-text         # force re-clean garbled text

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env if present (never committed — see .gitignore)
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/.env"
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
        # Bare filename → look in articles/ first
        if [[ "$arg" != */* && -f "$SCRIPT_DIR/articles/$arg" ]]; then
            PDF="articles/$arg"
        else
            PDF="$arg"
        fi
        PASS_ARGS+=("$PDF")
    else
        PASS_ARGS+=("$arg")
    fi
done

if [[ -z "$PDF" ]]; then
    echo "Usage: $0 <paper.pdf> [--wpm N] [--mode orp|span|dist]"
    echo "       PDFs live in articles/  — bare name is resolved automatically."
    exit 1
fi

if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Building Docker image '$IMAGE'..."
    docker build -t "$IMAGE" "$SCRIPT_DIR"
fi

# Auto-run AI preprocessing if key is set and sidecars are missing
EQ_SIDECAR="${PDF%.pdf}.equations.json"
CLEAN_SIDECAR="${PDF%.pdf}.clean.json"
if [[ -n "${GEMINI_API_KEY:-}" && ! -f "$SCRIPT_DIR/$EQ_SIDECAR" ]]; then
    DETECT=true
fi
if [[ -n "${GEMINI_API_KEY:-}" && ! -f "$SCRIPT_DIR/$CLEAN_SIDECAR" ]]; then
    CLEAN=true
fi

if [[ "$DETECT" == true ]]; then
    echo "  Detecting equations via Gemini vision (one-time)…"
    docker run --rm \
        --entrypoint python \
        -e GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
        -e TERM="${TERM:-xterm-256color}" \
        -v "$SCRIPT_DIR:/data" \
        -w /data \
        "$IMAGE" /app/detect_equations.py "$PDF"
fi

if [[ "$CLEAN" == true ]]; then
    echo "  Cleaning garbled text via Gemini vision (one-time)…"
    docker run --rm \
        --entrypoint python \
        -e GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
        -e TERM="${TERM:-xterm-256color}" \
        -v "$SCRIPT_DIR:/data" \
        -w /data \
        "$IMAGE" /app/clean_text.py "$PDF"
fi

SIGNAL="$SCRIPT_DIR/.rsvp_open_signal"
HTML="$SCRIPT_DIR/rsvp_reading.html"

# Remove any leftover signal from a previous run
rm -f "$SIGNAL"

# Background watcher: open browser whenever the signal file appears
(
    while true; do
        if [[ -f "$SIGNAL" ]]; then
            rm -f "$SIGNAL"
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

cleanup() {
    kill "$WATCHER" 2>/dev/null || true
    wait "$WATCHER" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

docker run --rm -it \
    --entrypoint python \
    -e TERM="${TERM:-xterm-256color}" \
    -v "$SCRIPT_DIR:/data" \
    -w /data \
    "$IMAGE" /app/pre_read.py "${PASS_ARGS[@]}"
