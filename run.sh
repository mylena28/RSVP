#!/usr/bin/env bash
# Usage:
#   ./run.sh                          # interactive paste mode (Ctrl+D to start)
#   ./run.sh mytext.txt               # read from file
#   ./run.sh mytext.txt --wpm 350     # custom speed
#   cat mytext.txt | ./run.sh         # pipe text in
#   cat mytext.txt | ./run.sh --wpm 400

set -euo pipefail

IMAGE="rsvp"

if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Building Docker image '$IMAGE'..."
    docker build -t "$IMAGE" "$(dirname "$0")"
fi

exec docker run --rm -it \
    -e TERM="${TERM:-xterm-256color}" \
    -v "$(pwd):/data:ro" \
    -w /data \
    "$IMAGE" "$@"
