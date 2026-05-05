# RSVP Reader

Terminal-based Rapid Serial Visual Presentation reader. Words flash one at a time at the same screen position so your eyes never move — only the text does.

Runs entirely inside Docker. No Python installation or external libraries required on the host.

## Quick start

```bash
# build once
docker build -t rsvp .

# interactive paste mode — paste text, press Ctrl+D to begin
docker run --rm -it rsvp

# read a file (current directory is mounted as /data)
docker run --rm -it -v "$(pwd):/data:ro" rsvp /data/mytext.txt

# custom speed
docker run --rm -it -v "$(pwd):/data:ro" rsvp /data/mytext.txt --wpm 350
```

Or use the included helper script that auto-builds the image and mounts the current directory:

```bash
chmod +x run.sh

./run.sh                           # paste mode
./run.sh sample.txt                # file mode (path relative to CWD)
./run.sh sample.txt --wpm 400      # faster
cat mytext.txt | ./run.sh          # pipe mode
```

## Display

```
  SPC pause · +/- speed · q quit

  ──────────────────────────────────────────────
                    ▼
            presentation
                    ▲
  ──────────────────────────────────────────────

  300 WPM  │  47/312  (15 %)
  [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
```

The red letter is the **Optimal Recognition Point (ORP)** — roughly 30 % into each word. It stays pinned to the same horizontal position every flash, which eliminates the saccadic eye movements that slow conventional reading.

## Controls

| Key | Action |
|-----|--------|
| `Space` | pause / resume |
| `+` or `=` | +25 WPM |
| `-` | −25 WPM |
| `q` | quit |

All controls are live — adjust speed mid-session without interrupting flow.

## Options

```
usage: rsvp.py [-h] [--wpm WPM] [file]

positional arguments:
  file        text file to read (omit to paste via stdin)

options:
  --wpm WPM   words per minute (default: 250, range: 50–1000)
```

## Speed guide

| WPM | Feel |
|-----|------|
| 150–200 | Slow, very comfortable |
| 250 | Default — good for first sessions |
| 300–350 | Moderate — most people's sweet spot |
| 400–500 | Fast — works well for familiar material |
| 600+ | Challenging — comprehension drops for dense text |

Start at 250 and raise by 25–50 WPM per session. The adaptation is real.

## Notes

- **No external dependencies.** Uses only Python's `curses` module (stdlib) — the Docker image is a plain `python:3.12-slim` with no extra packages.
- **Pipe mode** works with `docker run -it` — the app reads the pipe for text, then hands the PTY to curses for display.
- Best enjoyed in a maximised terminal window.
# RSVP
