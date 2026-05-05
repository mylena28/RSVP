# RSVP Reader

Terminal-based Rapid Serial Visual Presentation reader. Words flash one at a time at the same screen position so your eyes never move — only the text does.

Supports plain text files, piped input, interactive paste, and **PDF files** with automatic text extraction.

Runs entirely inside Docker — no Python installation or extra libraries needed on the host.

---

## Quick start

```bash
# build once
docker build -t rsvp .

# convenience wrapper (auto-builds, mounts CWD as /data)
chmod +x run.sh
```

## Usage

```bash
./run.sh                            # paste mode — type/paste text, Ctrl+D to begin
./run.sh article.txt                # plain text file
./run.sh paper.pdf                  # PDF — title + body extracted automatically
./run.sh paper.pdf --wpm 350        # custom speed
cat article.txt | ./run.sh          # pipe mode
```

Without `run.sh`:

```bash
docker run --rm -it \
  -v "$(pwd):/data:ro" -w /data \
  rsvp paper.pdf --wpm 300
```

---

## PDF extraction

When a `.pdf` file is given, the reader automatically:

| Step | What happens |
|------|-------------|
| Title | Read from PDF metadata; if absent, inferred from the largest text on the first page |
| Title screen | Shown for 2 seconds in the terminal before RSVP begins |
| Running headers/footers | Detected by position (top/bottom 8 % of page) and repetition across pages — removed |
| Footnotes | Filtered by font size (anything smaller than 75 % of the body font) |
| Page numbers | Bare digit-only blocks stripped |
| Soft hyphens | Words split across lines are rejoined (`con-\ntext` → `context`) |

The extracted body text is then fed into the normal RSVP display.

---

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

The red letter is the **Optimal Recognition Point (ORP)** — roughly 30 % into each word. It stays pinned to the same horizontal position on every flash, eliminating the saccadic eye movements that slow ordinary reading.

---

## Controls

| Key | Action |
|-----|--------|
| `Space` | pause / resume |
| `+` or `=` | +25 WPM |
| `-` | −25 WPM |
| `q` | quit |

All controls are live — adjust speed mid-session without interrupting flow.

---

## Options

```
usage: rsvp.py [-h] [--wpm WPM] [file]

positional arguments:
  file        text or PDF file (omit to paste via stdin)

options:
  --wpm WPM   words per minute (default: 250, range: 50–1000)
```

---

## Speed guide

| WPM | Feel |
|-----|------|
| 150–200 | Slow, very comfortable |
| 250 | Default — good for first sessions |
| 300–350 | Moderate — most people's sweet spot |
| 400–500 | Fast — works well for familiar material |
| 600+ | Challenging — comprehension drops for dense text |

Start at 250 and raise by 25–50 WPM per session. The adaptation is real.

---

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| `python:3.12-slim` | Base image |
| `curses` | Terminal display (Python stdlib — no install needed) |
| `PyMuPDF 1.25.5` | PDF parsing (installed inside the image) |

Nothing needs to be installed on the host beyond Docker.
