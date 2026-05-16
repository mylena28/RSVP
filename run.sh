#!/usr/bin/env bash
# Terminal RSVP reader.
#
# Usage:
#   ./run.sh                              # paste mode — type/paste text, Ctrl+D to begin
#   ./run.sh sample.txt                   # plain text file
#   ./run.sh articles/paper.pdf           # PDF in articles/
#   ./run.sh paper.pdf                    # bare name auto-resolves to articles/
#   ./run.sh paper.pdf --wpm 350
#   cat text.txt | ./run.sh --wpm 400

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE="rsvp"

if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Building Docker image '$IMAGE'..."
    docker build -t "$IMAGE" "$SCRIPT_DIR"
fi

# Resolve bare PDF filename to articles/ if it exists there
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == *.pdf && "$arg" != */* && -f "$SCRIPT_DIR/articles/$arg" ]]; then
        ARGS+=("articles/$arg")
    else
        ARGS+=("$arg")
    fi
done

exec docker run --rm -it \
    -e TERM="${TERM:-xterm-256color}" \
    -v "$SCRIPT_DIR:/data:ro" \
    -w /data \
    "$IMAGE" "${ARGS[@]+"${ARGS[@]}"}"
