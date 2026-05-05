#!/usr/bin/env bash
# Scientific Pre-Reading Workflow — RSVPs abstract + conclusion first.
#
# Usage:
#   ./pre_read.sh paper.pdf
#   ./pre_read.sh paper.pdf --wpm 300
#   ./pre_read.sh paper.pdf --wpm 300 --mode dist

set -euo pipefail

IMAGE="rsvp"

if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Building Docker image '$IMAGE'..."
    docker build -t "$IMAGE" "$(dirname "$0")"
fi

exec docker run --rm -it \
    --entrypoint python \
    -e TERM="${TERM:-xterm-256color}" \
    -v "$(pwd):/data:ro" \
    -w /data \
    "$IMAGE" /app/pre_read.py "$@"
