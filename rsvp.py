#!/usr/bin/env python3
"""RSVP — Rapid Serial Visual Presentation reader."""

import argparse
import curses
import os
import re
import sys
import time
from collections import Counter, defaultdict


# ── text helpers ──────────────────────────────────────────────────────────────

def words_from(text):
    return [w for w in re.split(r"\s+", text.strip()) if w]


def orp_index(word):
    """Optimal Recognition Point: focal letter at ~30 % into the word."""
    n = max(1, len(re.sub(r"\W", "", word)))
    if n <= 1:  return 0
    if n <= 5:  return 1
    if n <= 9:  return 2
    if n <= 13: return 3
    return 4


def span_highlight(word):
    """
    Indices to highlight in span mode: a cluster around the ORP.
    Width grows with word length so longer words get more shape context.
    """
    n      = max(1, len(re.sub(r"\W", "", word)))
    center = orp_index(word)

    if n <= 3:    width = n   # whole short word
    elif n <= 5:  width = 2
    elif n <= 8:  width = 3
    elif n <= 12: width = 4
    elif n <= 16: width = 5
    else:         width = 6

    half  = width // 2
    start = max(0, min(center - half, len(word) - width))
    return set(range(start, min(len(word), start + width)))


# ── PDF extraction ────────────────────────────────────────────────────────────

def _body_font_size(all_blocks):
    """Return the most common font size across the document (= body text size)."""
    sizes = []
    for blocks in all_blocks:
        for b in blocks:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes.append(round(span["size"]))
    if not sizes:
        return 10
    return Counter(sizes).most_common(1)[0][0]


def _repeated_strings(all_blocks, page_rects, threshold=3):
    """Collect text strings that appear in header/footer zones on 3+ pages."""
    counts = defaultdict(int)
    for blocks, rect in zip(all_blocks, page_rects):
        h_zone = rect.y0 + rect.height * 0.08
        f_zone = rect.y1 - rect.height * 0.08
        for b in blocks:
            if b["type"] != 0:
                continue
            by0, by1 = b["bbox"][1], b["bbox"][3]
            if by0 < h_zone or by1 > f_zone:
                txt = " ".join(
                    sp["text"] for ln in b["lines"] for sp in ln["spans"]
                ).strip()
                if txt:
                    counts[txt] += 1
    return {t for t, c in counts.items() if c >= threshold}


def load_pdf(path):
    """
    Extract (title, body_text) from a PDF.

    Filters out:
    - PDF annotation objects
    - Running headers/footers (detected by position + repetition)
    - Footnotes (font size < 75 % of body size)
    - Bare page numbers
    - Soft hyphens at line breaks are rejoined
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit("PyMuPDF is not installed. Rebuild the Docker image.")

    doc = fitz.open(path)

    # metadata title
    title = (doc.metadata.get("title") or "").strip()

    # gather per-page block data
    all_blocks = []
    page_rects = []
    for page in doc:
        all_blocks.append(page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"])
        page_rects.append(page.rect)

    body_size  = _body_font_size(all_blocks)
    min_size   = body_size * 0.75          # smaller → footnote
    repeated   = _repeated_strings(all_blocks, page_rects)

    # infer title from first-page largest text if metadata is empty
    if not title and all_blocks:
        best_size, best_text = 0, ""
        for b in all_blocks[0]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                for sp in ln["spans"]:
                    t = sp["text"].strip()
                    if t and sp["size"] > best_size:
                        best_size, best_text = sp["size"], t
        # only use it as title if it's larger than body text
        if best_size > body_size * 1.1:
            title = best_text

    paragraphs = []
    for blocks, rect in zip(all_blocks, page_rects):
        h_zone = rect.y0 + rect.height * 0.08
        f_zone = rect.y1 - rect.height * 0.08

        for b in blocks:
            if b["type"] != 0:
                continue

            by0, by1 = b["bbox"][1], b["bbox"][3]

            # skip header / footer zones
            if by0 < h_zone or by1 > f_zone:
                continue

            # build block text, handling hyphenation and footnote spans
            block_buf = ""
            for ln in b["lines"]:
                line_buf = ""
                for sp in ln["spans"]:
                    if sp["size"] < min_size:
                        continue                    # footnote-sized span
                    # strip inline footnote markers: digits/symbols directly
                    # attached to a word with no surrounding space
                    text = re.sub(r"(?<=[a-zA-Z])\d+(?=\s|$)", "", sp["text"])
                    line_buf += text

                line_buf = line_buf.rstrip()
                if line_buf.endswith("-"):
                    block_buf += line_buf[:-1]     # rejoin soft hyphen
                else:
                    block_buf += line_buf + " "

            block_buf = block_buf.strip()

            if not block_buf:
                continue
            if block_buf in repeated:
                continue
            if re.fullmatch(r"\d+", block_buf):   # bare page number
                continue

            paragraphs.append(block_buf)

    return title, "\n\n".join(paragraphs)


# ── curses display ────────────────────────────────────────────────────────────

def show_title_screen(scr, title):
    """Flash the document title for 2 seconds before RSVP begins."""
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE,  -1)
    curses.init_pair(3, curses.COLOR_CYAN,   -1)
    curses.init_pair(5, curses.COLOR_YELLOW, -1)

    scr.clear()
    H, W = scr.getmaxyx()

    label = "[ document title ]"
    try:
        scr.addstr(H // 2 - 2, max(0, (W - len(label)) // 2),
                   label, curses.color_pair(3))
    except curses.error:
        pass

    # wrap title if wider than terminal
    words = title.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= W - 4:
            cur = (cur + " " + w).lstrip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    for offset, line in enumerate(lines[:4]):
        try:
            scr.addstr(H // 2 + offset, max(0, (W - len(line)) // 2),
                       line, curses.color_pair(5) | curses.A_BOLD)
        except curses.error:
            pass

    scr.refresh()
    time.sleep(2)


def redraw(scr, word, wpm, idx, total, paused, span_mode=False):
    scr.erase()
    H, W = scr.getmaxyx()
    cy = H // 2

    orp       = orp_index(word)
    lit       = span_highlight(word) if span_mode else {orp}
    # anchor the word so the ORP sits at the screen centre
    x0        = max(0, min(W // 2 - orp, W - len(word) - 1))

    rail = "─" * (W - 2)
    try:
        scr.addstr(cy - 2, 1, rail, curses.color_pair(3))
        scr.addstr(cy + 2, 1, rail, curses.color_pair(3))
    except curses.error:
        pass

    # tick marks: single point in ORP mode; bracket the span in span mode
    if span_mode:
        span_start = x0 + min(lit)
        span_end   = x0 + max(lit)
        for sx in range(span_start, span_end + 1):
            if 0 <= sx < W - 1:
                ch_top = "┬" if sx in (span_start, span_end) else "─"
                ch_bot = "┴" if sx in (span_start, span_end) else "─"
                try:
                    scr.addstr(cy - 1, sx, ch_top, curses.color_pair(2))
                    scr.addstr(cy + 1, sx, ch_bot, curses.color_pair(2))
                except curses.error:
                    pass
    else:
        orp_x = x0 + orp
        if 0 <= orp_x < W - 1:
            try:
                scr.addstr(cy - 1, orp_x, "▼", curses.color_pair(2))
                scr.addstr(cy + 1, orp_x, "▲", curses.color_pair(2))
            except curses.error:
                pass

    for i, ch in enumerate(word):
        x = x0 + i
        if x >= W - 1:
            break
        attr = (curses.color_pair(2) | curses.A_BOLD
                if i in lit else curses.color_pair(1) | curses.A_BOLD)
        try:
            scr.addch(cy, x, ch, attr)
        except curses.error:
            pass

    mode_tag = " SPAN " if span_mode else " ORP  "
    pct = idx / total
    bw  = max(10, W - 32)
    bar = "█" * int(bw * pct) + "░" * (bw - int(bw * pct))
    try:
        scr.addstr(H - 2, 0,
            f"  {wpm} WPM  │  {idx}/{total}  ({pct * 100:.0f} %)  │{mode_tag}│"[: W - 1],
            curses.color_pair(3))
        scr.addstr(H - 1, 0, f" {bar} "[: W - 1], curses.color_pair(4))
    except curses.error:
        pass

    hint = ("  —— PAUSED ——  SPC resume · +/- speed · m mode · q quit  "
            if paused else
            "  SPC pause · +/- speed · m mode · q quit  ")
    try:
        scr.addstr(0, max(0, (W - len(hint)) // 2), hint[: W - 1], curses.color_pair(3))
    except curses.error:
        pass

    scr.refresh()


def run(scr, words, wpm, title="", span_mode=False):
    curses.curs_set(0)
    scr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE,  -1)
    curses.init_pair(2, curses.COLOR_RED,    -1)
    curses.init_pair(3, curses.COLOR_CYAN,   -1)
    curses.init_pair(4, curses.COLOR_GREEN,  -1)
    curses.init_pair(5, curses.COLOR_YELLOW, -1)

    if title:
        show_title_screen(scr, title)

    total  = len(words)
    i      = 0
    paused = False
    due    = time.monotonic()

    while i < total:
        key = scr.getch()
        if key in (ord("q"), ord("Q")):
            return
        elif key == ord(" "):
            paused = not paused
            if not paused:
                due = time.monotonic()
        elif key in (ord("+"), ord("=")):
            wpm = min(1000, wpm + 25)
        elif key == ord("-"):
            wpm = max(50, wpm - 25)
        elif key in (ord("m"), ord("M")):
            span_mode = not span_mode

        now   = time.monotonic()
        delay = 60.0 / wpm

        if not paused and now >= due:
            redraw(scr, words[i], wpm, i + 1, total, False, span_mode)
            due = now + delay
            i  += 1
        elif paused:
            redraw(scr, words[max(0, i - 1)], wpm, i, total, True, span_mode)
            time.sleep(0.04)
        else:
            time.sleep(min(0.005, due - now))

    scr.clear()
    H, W = scr.getmaxyx()
    msg = "[ Done! Press any key to exit. ]"
    try:
        scr.addstr(H // 2, max(0, (W - len(msg)) // 2),
                   msg, curses.color_pair(4) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()
    scr.nodelay(False)
    scr.getch()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="RSVP reader — display text word-by-word at speed."
    )
    ap.add_argument("file", nargs="?",
                    help="text or PDF file to read (omit to paste via stdin)")
    ap.add_argument("--wpm", type=int, default=250,
                    help="words per minute (default: 250)")
    ap.add_argument("--mode", choices=["orp", "span"], default="orp",
                    help="highlight mode: single ORP letter (default) or multi-letter span")
    args = ap.parse_args()

    title = ""

    if args.file and args.file.lower().endswith(".pdf"):
        print("  Extracting PDF…", file=sys.stderr)
        title, text = load_pdf(args.file)
        if title:
            print(f"  Title: {title}", file=sys.stderr)
    elif args.file:
        with open(args.file) as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
        tty = open("/dev/tty", "r")
        os.dup2(tty.fileno(), sys.stdin.fileno())
        tty.close()
    else:
        print("Paste your text below, then press Ctrl+D:\n")
        text = sys.stdin.read()

    words = words_from(text)
    if not words:
        sys.exit("No words found in input.")

    minutes = len(words) / args.wpm
    print(
        f"  {len(words)} words  ·  {args.wpm} WPM  ·  ~{minutes:.1f} min"
        f"  —  starting in 1 s…\n",
        file=sys.stderr,
    )
    time.sleep(1)

    curses.wrapper(lambda scr: run(scr, words, args.wpm, title,
                                   span_mode=(args.mode == "span")))


if __name__ == "__main__":
    main()
