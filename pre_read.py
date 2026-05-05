#!/usr/bin/env python3
"""
Scientific Pre-Reading Workflow.

Opens a PDF, identifies the Abstract and Conclusion sections, and RSVPs
them first — giving a fast structural overview before the full paper.

After both sections the user is asked whether to continue with the full text.
"""

import argparse
import curses
import os
import re
import sys
import time
from collections import Counter, defaultdict

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF is not installed. Rebuild the Docker image.")

# share display primitives with rsvp.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsvp import words_from, run as _rsvp_loop, show_title_screen


# ── section patterns ──────────────────────────────────────────────────────────

_ABSTRACT_RE = re.compile(
    r"^\s*(abstract|summary|synopsis|overview|résumé)\s*$", re.I
)
_CONCLUSION_RE = re.compile(
    r"^\s*(conclusions?|concluding\s+remarks?|"
    r"summary\s+and\s+conclusions?|final\s+remarks?|"
    r"discussion\s+and\s+conclusions?|general\s+conclusions?)\s*$",
    re.I,
)


# ── PDF helpers (self-contained so this module is independent) ────────────────

def _body_size(all_blocks):
    sizes = []
    for blocks in all_blocks:
        for b in blocks:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                for sp in ln["spans"]:
                    if sp["text"].strip():
                        sizes.append(round(sp["size"]))
    return Counter(sizes).most_common(1)[0][0] if sizes else 10


def _repeated(all_blocks, page_rects, threshold=3):
    counts = defaultdict(int)
    for blocks, rect in zip(all_blocks, page_rects):
        hz = rect.y0 + rect.height * 0.08
        fz = rect.y1 - rect.height * 0.08
        for b in blocks:
            if b["type"] != 0:
                continue
            if b["bbox"][1] < hz or b["bbox"][3] > fz:
                txt = " ".join(
                    sp["text"] for ln in b["lines"] for sp in ln["spans"]
                ).strip()
                if txt:
                    counts[txt] += 1
    return {t for t, c in counts.items() if c >= threshold}


def _block_text(block, min_size):
    buf = ""
    for ln in block["lines"]:
        line = "".join(
            sp["text"] for sp in ln["spans"] if sp["size"] >= min_size
        ).rstrip()
        buf += (line[:-1] if line.endswith("-") else line + " ")
    return buf.strip()


_MATH_SYMBOLS = re.compile(r"[=∫∂•→←↔≤≥≠≈∑∏√∞∇∈∉⊂⊃∪∩×÷±∮∝⟨⟩\|{}$]")


def _is_header(block, body_size):
    if block["type"] != 0:
        return False
    spans = [sp for ln in block["lines"] for sp in ln["spans"]]
    if not spans:
        return False
    text = " ".join(sp["text"] for sp in spans).strip()
    if not text or len(text) > 90:
        return False

    # strip leading section numbers: "1.", "2.3", "IV."
    clean = re.sub(r"^[\dIVXivx]+[.\s]+", "", text).strip()
    if not clean:
        return False

    # reject if math symbols are present
    if _MATH_SYMBOLS.search(text):
        return False

    # must be mostly letters — equations and garbled formula lines fail this
    letter_count = len(re.sub(r"[^a-zA-Z]", "", text))
    if letter_count < max(3, len(text) * 0.55):
        return False

    avg_size = sum(sp["size"] for sp in spans) / len(spans)
    is_large = avg_size > body_size * 1.05
    is_bold  = any(sp["flags"] & 16 for sp in spans)
    is_caps  = text.replace(" ", "").isupper() and len(text.replace(" ", "")) > 2
    return is_large or is_bold or is_caps


def _normalize(raw):
    """Map a raw header string to a canonical section key."""
    h = re.sub(r"^[\dIVXivx]+[.\s]+", "", raw).strip().lower()
    h = re.sub(r"\s+", " ", h)
    if _ABSTRACT_RE.match(h):   return "abstract"
    if _CONCLUSION_RE.match(h): return "conclusion"
    if re.search(r"\bintroduction\b", h): return "introduction"
    if re.search(r"\bdiscussion\b",   h): return "discussion"
    if re.search(r"\bmethod",         h): return "methods"
    if re.search(r"\bresult",         h): return "results"
    if re.search(r"\breference|\bbiblio", h): return "references"
    if re.search(r"\backnowledg",     h): return "acknowledgments"
    return h


# ── section extraction ────────────────────────────────────────────────────────

def extract_sections(path):
    """
    Parse a scientific PDF.

    Returns (title, sections) where sections is an ordered dict mapping
    canonical section names to their body text.

    Detection strategy:
    1. Use font size, bold flag, and ALL-CAPS to identify section headers.
    2. Group body paragraphs under each header.
    3. Promote 'preamble' (text before the first header) to 'abstract' if no
       explicit abstract header was found.
    4. Promote 'discussion' to 'conclusion' as a last resort.
    """
    doc = fitz.open(path)
    title = (doc.metadata.get("title") or "").strip()

    all_blocks, page_rects = [], []
    for page in doc:
        all_blocks.append(
            page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        )
        page_rects.append(page.rect)

    bs       = _body_size(all_blocks)
    min_size = bs * 0.75
    repeated = _repeated(all_blocks, page_rects)

    # ordered flat list of (is_header, text)
    segments = []
    for blocks, rect in zip(all_blocks, page_rects):
        hz = rect.y0 + rect.height * 0.08
        fz = rect.y1 - rect.height * 0.08
        for b in blocks:
            if b["type"] != 0:
                continue
            by0, by1 = b["bbox"][1], b["bbox"][3]
            if by0 < hz or by1 > fz:
                continue
            text = _block_text(b, min_size)
            if not text or text in repeated or re.fullmatch(r"\d+", text):
                continue
            segments.append((_is_header(b, bs), text))

    # infer title from first large-font block if metadata is empty
    if not title:
        for is_hdr, text in segments[:15]:
            if is_hdr and len(text) > 5:
                title = text
                break

    # group into sections
    sections: dict[str, list[str]] = {}
    cur = "preamble"
    sections[cur] = []
    for is_hdr, text in segments:
        if is_hdr:
            cur = _normalize(text)
            sections.setdefault(cur, [])
        else:
            sections[cur].append(text)

    # ── post-processing ───────────────────────────────────────────────────────

    # 1. Drop sections whose key looks like garbled math or a journal byline.
    #    Keep: known canonical names OR keys that are ≥70 % letters.
    _KNOWN = {"abstract", "preamble", "introduction", "methods", "results",
              "discussion", "conclusion", "references", "acknowledgments",
              "appendix"}
    clean_sections: dict[str, list[str]] = {}
    for key, paras in sections.items():
        letter_ratio = len(re.sub(r"[^a-zA-Z]", "", key)) / max(1, len(key))
        if key in _KNOWN or letter_ratio >= 0.70:
            clean_sections[key] = paras
    sections = clean_sections

    # 2. Abstract recovery — runs up to three strategies in order:
    if "abstract" not in sections:

        # 2a. Preamble (text before any header)
        pre = sections.pop("preamble", [])
        if pre:
            first = re.sub(r"^abstract\s*[:.\-]?\s*", "", pre[0], flags=re.I).strip()
            if first:
                pre[0] = first
            sections = {"abstract": pre, **sections}

        # 2b. Any substantial block sitting before 'introduction'
        elif "introduction" in sections:
            pre_intro = []
            for key in list(sections.keys()):
                if key == "introduction":
                    break
                candidate = "\n\n".join(sections[key])
                if len(candidate.split()) >= 30:
                    pre_intro.append((key, candidate))
            if pre_intro:
                # pick the block with the most words (most likely to be abstract)
                best_key, best_text = max(pre_intro, key=lambda kv: len(kv[1].split()))
                sections["abstract"] = sections.pop(best_key)
                sections = {"abstract": sections["abstract"],
                            **{k: v for k, v in sections.items() if k != "abstract"}}

        # 2c. Inline "Abstract" keyword anywhere in the first ~500 words of text
        else:
            early_text = "\n\n".join(
                "\n\n".join(v) for v in list(sections.values())[:4]
            )
            m = re.search(
                r"\babstract\b\s*[:.\-]?\s*(.{80,}?)(?=\n\n|\Z)",
                early_text, re.I | re.DOTALL,
            )
            if m:
                sections = {"abstract": [m.group(1).strip()], **sections}
    else:
        sections.pop("preamble", None)

    # 3. Promote discussion → conclusion as a last resort
    if "conclusion" not in sections and "discussion" in sections:
        sections["conclusion"] = sections["discussion"]

    return title, {k: "\n\n".join(v) for k, v in sections.items() if v}


# ── curses helpers ────────────────────────────────────────────────────────────

def _colors(scr):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE,   -1)
    curses.init_pair(2, curses.COLOR_RED,     -1)
    curses.init_pair(3, curses.COLOR_CYAN,    -1)
    curses.init_pair(4, curses.COLOR_GREEN,   -1)
    curses.init_pair(5, curses.COLOR_YELLOW,  -1)
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)


def show_banner(scr, label, word_count, wpm):
    """Full-screen section banner shown for 1.5 s before each RSVP block."""
    scr.clear()
    _colors(scr)
    curses.curs_set(0)
    H, W = scr.getmaxyx()

    bar  = "━" * min(52, W - 4)
    mins = word_count / wpm
    sub  = f"{word_count} words  ·  ~{mins:.1f} min at {wpm} WPM"
    cy   = H // 2

    rows = [
        (cy - 2, bar,   6, False),
        (cy,     label, 5, True),
        (cy + 2, sub,   3, False),
        (cy + 4, bar,   6, False),
    ]
    for row, text, pair, bold in rows:
        attr = curses.color_pair(pair) | (curses.A_BOLD if bold else 0)
        x    = max(0, (W - len(text)) // 2)
        try:
            scr.addstr(row, x, text[: W - 1], attr)
        except curses.error:
            pass

    scr.refresh()
    time.sleep(1.5)


def ask_continue(scr, prompt):
    """Blocking yes/no prompt. Returns True for Y / Enter, False for N / Q."""
    scr.clear()
    _colors(scr)
    curses.curs_set(0)
    scr.nodelay(False)
    H, W = scr.getmaxyx()

    hint = "[ Y / Enter = yes   ·   N or Q = no ]"
    try:
        scr.addstr(H // 2,     max(0, (W - len(prompt)) // 2),
                   prompt[: W - 1], curses.color_pair(5) | curses.A_BOLD)
        scr.addstr(H // 2 + 2, max(0, (W - len(hint)) // 2),
                   hint[: W - 1], curses.color_pair(3))
    except curses.error:
        pass

    scr.refresh()
    while True:
        k = scr.getch()
        if k in (ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
            return True
        if k in (ord("n"), ord("N"), ord("q"), ord("Q")):
            return False


# ── pre-reading flow ──────────────────────────────────────────────────────────

_TARGETS = ("abstract", "conclusion")
_LABELS  = {"abstract": "ABSTRACT", "conclusion": "CONCLUSION"}


def prereading_flow(scr, title, sections, wpm, mode):
    _colors(scr)
    curses.curs_set(0)

    if title:
        show_title_screen(scr, title)

    found = [k for k in _TARGETS if k in sections and sections[k].strip()]

    if not found:
        if ask_continue(scr,
                "No abstract or conclusion detected.  Read full paper?"):
            all_words = words_from("\n\n".join(sections.values()))
            show_banner(scr, "FULL PAPER", len(all_words), wpm)
            _rsvp_loop(scr, all_words, wpm, mode=mode, show_done=True)
        return

    for i, key in enumerate(found):
        words = words_from(sections[key])
        show_banner(scr, _LABELS[key], len(words), wpm)
        _rsvp_loop(scr, words, wpm, mode=mode, show_done=False)

    # offer full paper after the last pre-read section
    all_words = words_from("\n\n".join(sections.values()))
    if ask_continue(scr, "Pre-reading complete.  Continue with the full paper?"):
        show_banner(scr, "FULL PAPER", len(all_words), wpm)
        _rsvp_loop(scr, all_words, wpm, mode=mode, show_done=True)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Scientific pre-reading: RSVP abstract + conclusion first."
    )
    ap.add_argument("file", help="PDF file to pre-read")
    ap.add_argument("--wpm",  type=int, default=250,
                    help="words per minute (default: 250)")
    ap.add_argument("--mode", choices=["orp", "span", "dist"], default="orp",
                    help="highlight mode (default: orp)")
    args = ap.parse_args()

    if not args.file.lower().endswith(".pdf"):
        sys.exit("pre_read only accepts PDF files.")

    print("  Extracting sections…", file=sys.stderr)
    title, sections = extract_sections(args.file)

    found = [k for k in _TARGETS if k in sections]
    if title:
        print(f"  Title    : {title}", file=sys.stderr)
    print(f"  Sections : {', '.join(sections.keys())}", file=sys.stderr)
    print(f"  Pre-read : {', '.join(found) or 'none detected — will offer full paper'}",
          file=sys.stderr)
    time.sleep(0.8)

    mode = {"orp": 0, "span": 1, "dist": 2}[args.mode]
    curses.wrapper(
        lambda scr: prereading_flow(scr, title, sections, args.wpm, mode)
    )


if __name__ == "__main__":
    main()
