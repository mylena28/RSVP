# RSVP Reader

Rapid Serial Visual Presentation reader for scientific papers. Words flash one at a time at the same screen position so your eyes never move — only the text does.

Two modes:

- **Browser reader** (`pre_read.sh`) — parses a PDF into sections, embeds figure/equation images, and opens a self-contained HTML file in your browser. Recommended for papers.
- **Terminal reader** (`run.sh`) — reads plain text or PDFs directly in the terminal with `curses`.

Runs entirely inside Docker — no Python installation needed on the host.

---

## Project layout

```
articles/          PDFs and their AI sidecar files (.clean.json, .equations.json)
pre_read.sh        browser reader launcher
run.sh             terminal reader launcher
rsvp_reading.html  generated output (git-ignored, recreated each run)
sample.txt         example plain-text file for the terminal reader
```

Drop any PDF into `articles/` and run it by name:

```bash
./pre_read.sh paper.pdf       # bare name auto-resolves to articles/
./pre_read.sh articles/paper.pdf      # explicit path also works
```

---

## Browser reader (recommended for papers)

```bash
./pre_read.sh articles/paper.pdf
./pre_read.sh articles/paper.pdf --wpm 300
./pre_read.sh articles/paper.pdf --mode span
```

The terminal shows a title screen while the HTML is generated, then opens the file in your browser automatically.

### What it does

1. **Parses the PDF** into named sections (Abstract, Introduction, Conclusion, etc.)
2. **Embeds referenced figures and equations** as inline images next to the word that cites them
3. **Generates a self-contained HTML file** (`rsvp_reading.html`) — no server needed, works offline
4. **Opens your browser** to a section menu where you choose what to read

### Section menu

Navigate with keyboard or mouse. You can read a single section, cherry-pick several at once, or read the full paper.

| Key | Action |
|-----|--------|
| `↑` / `↓` or `j` / `k` | move cursor |
| `Space` | toggle section selected |
| `A` | select / deselect all sections |
| `Enter` | read highlighted section (or all selected) |
| `ESC` | clear selection |

A `★ Quick Pre-read` shortcut at the top reads Abstract + Conclusion together.

### Reader controls

| Key / Button | Action |
|-------------|--------|
| `Space` | pause / resume |
| `+` or `=` | +25 WPM |
| `-` | −25 WPM |
| `m` or click mode button | cycle highlight mode: ORP → SPAN → DIST |
| `←` / `→` | step one word back / forward |
| `ESC` | return to section menu |

### AI preprocessing (optional, improves quality)

Two one-time steps use the Gemini vision API to fix common PDF extraction problems:

| Step | What it fixes |
|------|--------------|
| `--clean-text` | Garbled characters from bad PDF encoding |
| `--detect-equations` | Inline equations replaced with equation images |

Put your key in `.env`:
```bash
echo "GEMINI_API_KEY=AIza..." > .env
```

With a key present, both steps run automatically the first time you process a PDF. Sidecars (`.clean.json`, `.equations.json`) are saved next to the PDF in `articles/` so subsequent runs are instant.

```bash
./pre_read.sh articles/paper.pdf                    # auto-preprocesses if key set + no sidecar
./pre_read.sh articles/paper.pdf --detect-equations # force re-detect equations
./pre_read.sh articles/paper.pdf --clean-text       # force re-clean garbled text
```

---

## Terminal reader

```bash
./run.sh                                # paste mode — type/paste text, Ctrl+D to begin
./run.sh sample.txt                     # plain text file
./run.sh articles/paper.pdf             # PDF
./run.sh paper.pdf --wpm 350            # bare name auto-resolves to articles/
cat article.txt | ./run.sh              # pipe mode
```

Without `run.sh`:

```bash
docker run --rm -it \
  -v "$(pwd):/data:ro" -w /data \
  rsvp articles/paper.pdf --wpm 300
```

### Controls

| Key | Action |
|-----|--------|
| `Space` | pause / resume |
| `+` or `=` | +25 WPM |
| `-` | −25 WPM |
| `m` | cycle highlight mode |
| `q` | quit |

---

## Quick start

```bash
# build once
docker build -t rsvp .
chmod +x run.sh pre_read.sh

# drop a PDF in articles/ and read it
cp ~/Downloads/paper.pdf articles/
./pre_read.sh paper.pdf
```

---

## Highlight modes

Three modes, switchable live with `m`:

**ORP** (default) — one red letter marks the Optimal Recognition Point:
```
  ──────────────────────────────────────────
                  ▼
          presentation
                  ▲
  ──────────────────────────────────────────
  300 WPM · 47 / 312 (15%) · ORP
```

**SPAN** — a contiguous cluster of letters is highlighted; width grows with word length:
```
  ──────────────────────────────────────────
               ▼
          presentation
               ▲
  ──────────────────────────────────────────
  300 WPM · 47 / 312 (15%) · SPAN
```

**DIST** — letters are spread across the word at maximum mutual distance, anchored at the ORP:
```
  ──────────────────────────────────────────
                  ▼
          presentation
                  ▲
  ──────────────────────────────────────────
  300 WPM · 47 / 312 (15%) · DIST
```

### Letters highlighted per word length

| Word length | ORP | SPAN | DIST |
|-------------|-----|------|------|
| 1–3 | 1 | whole word | whole word |
| 4–5 | 1 | 2 | 2 |
| 6–8 | 1 | 3 | 3 |
| 9–12 | 1 | 4 | 4 |
| 13–16 | 1 | 5 | 5 |
| 17+ | 1 | 6 | 6 |

---

## PDF extraction

When a `.pdf` is given, the reader automatically:

| Step | What happens |
|------|-------------|
| Title | Read from PDF metadata; if absent, inferred from the largest text on the first page |
| Sections | Detected by heading patterns (Abstract, Introduction, …, Conclusion, References) and numbered headings (e.g. `1.  Introduction`) |
| Headers/footers | Removed by position (top/bottom 10% of page) and repetition across pages |
| Footnotes | Filtered by font size (< 75% of body font) |
| Page numbers | Bare digit-only blocks stripped |
| Soft hyphens | Words split across lines rejoined (`con-\ntext` → `context`) |
| Figures / equations | Bounding boxes scanned; images embedded in the HTML next to citing words |

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
| `curses` | Terminal display (Python stdlib) |
| `PyMuPDF` | PDF parsing |
| `google-generativeai` | Optional AI preprocessing (equation detection, text cleaning) |

Nothing needs to be installed on the host beyond Docker.
