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
./run.sh article.txt --mode span    # start in span highlight mode
./run.sh article.txt --mode dist    # start in distributed highlight mode
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

Two highlight modes, switchable live with `m`:

**ORP mode** (default) — a single red letter marks the Optimal Recognition Point:
```
  SPC pause · +/- speed · m mode · q quit

  ──────────────────────────────────────────────
                    ▼
            presentation
                    ▲
  ──────────────────────────────────────────────

  300 WPM  │  47/312  (15 %)  │ ORP  │
  [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
```

**Span mode** (`--mode span`) — a contiguous cluster of letters is highlighted, with bracket markers showing its extent. Width grows with word length:
```
  SPC pause · +/- speed · m mode · q quit

  ──────────────────────────────────────────────
               ┬───┴
            presentation
               ┬───┴
  ──────────────────────────────────────────────

  300 WPM  │  47/312  (15 %)  │ SPAN │
  [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
```

**Dist mode** (`--mode dist`) — letters are spread across the word rather than clustered. A dot `·` appears above and below each highlighted position. Useful for long words where the shape outline matters more than the cluster:
```
  SPC pause · +/- speed · m mode · q quit

  ──────────────────────────────────────────────
       ·         ·       ·            ·
            presentation
       ·         ·       ·            ·
  ──────────────────────────────────────────────

  300 WPM  │  47/312  (15 %)  │ DIST │
  [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
```

The selection always anchors to the ORP, then greedily adds the position farthest from all already-chosen ones, spreading highlights to the structural extremes of the word.

### Highlight counts by word length (Span and Dist)

| Word length | Letters lit | Span example | Dist example |
|-------------|-------------|--------------|--------------|
| 1–3 | whole word | `THE` | `THE` |
| 4–5 | 2 | `FLash` | `wOrD` |
| 6–8 | 3 | `rEADing` | `ReAdinG` |
| 9–12 | 4 | `pRESEnation` | `PreSentAtioN` |
| 13–16 | 5 | `cOMPREhension` | `ComPrehEnsioN` |
| 17+ | 6 | `inCOMPREhensible` | `IncoMprehEnsIblE` |

---

## Controls

| Key | Action |
|-----|--------|
| `Space` | pause / resume |
| `+` or `=` | +25 WPM |
| `-` | −25 WPM |
| `m` | toggle ORP / Span highlight mode |
| `q` | quit |

All controls are live — adjust speed and switch modes mid-session without interrupting flow.

---

## Options

```
usage: rsvp.py [-h] [--wpm WPM] [--mode {orp,span,dist}] [file]

positional arguments:
  file                      text or PDF file (omit to paste via stdin)

options:
  --wpm WPM                 words per minute (default: 250, range: 50–1000)
  --mode {orp,span,dist}    starting highlight mode (default: orp)
                            can also be cycled live with m: ORP → SPAN → DIST → ORP
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
