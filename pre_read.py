#!/usr/bin/env python3
"""
Scientific Pre-Reading Workflow.

Opens a PDF, identifies Abstract and Conclusion, and RSVPs them first.
While reading, any paragraph that references a figure or equation shows
a rendered preview of that figure/equation in the lower screen area.
After the pre-read the user can continue with the full paper.
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
    sys.exit("PyMuPDF is not installed.  Rebuild the Docker image.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsvp import words_from, show_title_screen


# ── section detection patterns ────────────────────────────────────────────────

_ABSTRACT_RE = re.compile(
    r"^\s*(abstract|summary|synopsis|overview|résumé)\s*$", re.I
)
_CONCLUSION_RE = re.compile(
    r"^\s*(conclusions?|concluding\s+remarks?|"
    r"summary\s+and\s+conclusions?|final\s+remarks?|"
    r"discussion\s+and\s+conclusions?|general\s+conclusions?)\s*$",
    re.I,
)
_MATH_SYMBOLS = re.compile(r"[=∫∂•→←↔≤≥≠≈∑∏√∞∇∈∉⊂⊃∪∩×÷±∮∝⟨⟩\|{}$]")

# reference patterns inside running text
_FIG_CAPTION_RE  = re.compile(r"\b[Ff]ig(?:ure)?\.?\s*(\d+[a-zA-Z]?)")
_EQ_NUMBER_RE    = re.compile(r"\(\s*(\d+(?:[.\-]\d+)?)\s*\)\s*$")
_EQ_REF_TEXT_RE  = re.compile(
    r"\b[Ee]q(?:uation)?s?\.?\s*\(?(\d+(?:[.\-]\d+)?)\)?"
)


# ── PDF low-level helpers ─────────────────────────────────────────────────────

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


def _is_header(block, body_size):
    if block["type"] != 0:
        return False
    spans = [sp for ln in block["lines"] for sp in ln["spans"]]
    if not spans:
        return False
    text = " ".join(sp["text"] for sp in spans).strip()
    if not text or len(text) > 90:
        return False
    clean = re.sub(r"^[\dIVXivx]+[.\s]+", "", text).strip()
    if not clean:
        return False
    if _MATH_SYMBOLS.search(text):
        return False
    letter_count = len(re.sub(r"[^a-zA-Z]", "", text))
    if letter_count < max(3, len(text) * 0.55):
        return False
    avg_size = sum(sp["size"] for sp in spans) / len(spans)
    is_large = avg_size > body_size * 1.05
    is_bold  = any(sp["flags"] & 16 for sp in spans)
    is_caps  = text.replace(" ", "").isupper() and len(text.replace(" ", "")) > 2
    return is_large or is_bold or is_caps


def _normalize(raw):
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
    Returns (title, sections_dict, doc, all_blocks, page_rects).
    Keeps doc open so callers can render pages for the reference panel.
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

    if not title:
        for is_hdr, text in segments[:15]:
            if is_hdr and len(text) > 5:
                title = text
                break

    sections: dict[str, list[str]] = {}
    cur = "preamble"
    sections[cur] = []
    for is_hdr, text in segments:
        if is_hdr:
            cur = _normalize(text)
            sections.setdefault(cur, [])
        else:
            sections[cur].append(text)

    # drop math-garbled section keys
    _KNOWN = {"abstract", "preamble", "introduction", "methods", "results",
              "discussion", "conclusion", "references", "acknowledgments", "appendix"}
    sections = {
        k: v for k, v in sections.items()
        if k in _KNOWN
        or len(re.sub(r"[^a-zA-Z]", "", k)) / max(1, len(k)) >= 0.70
    }

    # abstract recovery
    if "abstract" not in sections:
        pre = sections.pop("preamble", [])
        if pre:
            first = re.sub(r"^abstract\s*[:.\-]?\s*", "", pre[0], flags=re.I).strip()
            if first:
                pre[0] = first
            sections = {"abstract": pre, **sections}
        elif "introduction" in sections:
            pre_intro = [
                (k, "\n\n".join(v))
                for k, v in sections.items()
                if k not in ("preamble",) and k != "introduction"
                and list(sections.keys()).index(k)
                   < list(sections.keys()).index("introduction")
                and len("\n\n".join(v).split()) >= 30
            ]
            if pre_intro:
                best_key, _ = max(pre_intro, key=lambda kv: len(kv[1].split()))
                popped = sections.pop(best_key)
                sections = {"abstract": popped, **sections}
        else:
            early = "\n\n".join("\n\n".join(v) for v in list(sections.values())[:4])
            m = re.search(r"\babstract\b\s*[:.\-]?\s*(.{80,}?)(?=\n\n|\Z)",
                          early, re.I | re.DOTALL)
            if m:
                sections = {"abstract": [m.group(1).strip()], **sections}
    else:
        sections.pop("preamble", None)

    if "conclusion" not in sections and "discussion" in sections:
        sections["conclusion"] = sections["discussion"]

    return (
        title,
        {k: "\n\n".join(v) for k, v in sections.items() if v},
        doc,
        all_blocks,
        page_rects,
    )


# ── reference scanning ────────────────────────────────────────────────────────

def _math_density(text):
    math = len(re.findall(r"[=+*/^∫∂→←≤≥≠≈∑∏√∞∇·×±]", text))
    return math / max(1, len(text))


def _caption_for_region(blocks, img_rect):
    """Find figure caption text near img_rect. Returns (caption, 'figN') or ('', None)."""
    best = (float("inf"), "", None)
    for b in blocks:
        if b["type"] != 0:
            continue
        text = " ".join(
            sp["text"] for ln in b["lines"] for sp in ln["spans"]
        ).strip()
        m = _FIG_CAPTION_RE.search(text)
        if not m:
            continue
        bx0, by0, bx1, by1 = b["bbox"]
        horiz_overlap = max(
            0, min(bx1, img_rect.x1) - max(bx0, img_rect.x0)
        )
        vert_dist = min(
            abs(by0 - img_rect.y1), abs(by1 - img_rect.y0)
        )
        if horiz_overlap > img_rect.width * 0.25 and vert_dist < 100:
            if vert_dist < best[0]:
                best = (vert_dist, text, f"fig{m.group(1).lower()}")
    return best[1], best[2]


def scan_refs(doc, all_blocks, page_rects):
    """
    Scan for figures and numbered display equations.

    Returns dict:
        'fig1' → {'type':'fig', 'page':int, 'bbox':tuple4, 'label':str, 'caption':str}
        'eq5'  → {'type':'eq',  'page':int, 'bbox':tuple4, 'label':str, 'caption':str}
    """
    refs = {}

    # figures — images with nearby captions
    for page_num, (page, blocks) in enumerate(zip(doc, all_blocks)):
        try:
            img_infos = page.get_image_info(hashes=False)
        except Exception:
            img_infos = []
        for info in img_infos:
            r = fitz.Rect(info["bbox"])
            if r.width < 20 or r.height < 20:
                continue
            caption, fig_key = _caption_for_region(blocks, r)
            if fig_key and fig_key not in refs:
                refs[fig_key] = {
                    "type": "fig",
                    "page": page_num,
                    "bbox": (r.x0, r.y0, r.x1, r.y1),
                    "label": f"Figure {fig_key[3:].upper()}",
                    "caption": caption[:120],
                }

    # display equations — text blocks ending with (N) and containing math
    for page_num, blocks in enumerate(all_blocks):
        for b in blocks:
            if b["type"] != 0:
                continue
            text = " ".join(
                sp["text"] for ln in b["lines"] for sp in ln["spans"]
            )
            m = _EQ_NUMBER_RE.search(text)
            if m and _math_density(text) > 0.08:
                eq_key = f"eq{m.group(1)}"
                if eq_key not in refs:
                    refs[eq_key] = {
                        "type": "eq",
                        "page": page_num,
                        "bbox": b["bbox"],
                        "label": f"Eq. ({m.group(1)})",
                        "caption": text[:120].strip(),
                    }

    return refs


# ── reference rendering ───────────────────────────────────────────────────────

def render_ref_art(doc, ref_info, term_w, term_h):
    """
    Render a reference region to a list of strings (one per terminal row).

    Each character represents one pixel column; two PDF pixel rows are merged
    into one terminal row using Unicode half-block characters, giving
    term_w × (term_h * 2) effective pixel resolution.

    Grayscale mapping (dark PDF content on white background):
        255 (white) → space   0 (black) → █
    """
    bbox = fitz.Rect(ref_info["bbox"])
    if bbox.is_empty or bbox.width < 1 or bbox.height < 1:
        return [f"  [{ref_info['label']}]"]

    pixel_w = max(4, term_w)
    pixel_h = max(4, term_h * 2)

    sx = pixel_w / bbox.width
    sy = pixel_h / bbox.height
    scale = min(sx, sy, 6.0)

    mat = fitz.Matrix(scale, scale)
    try:
        page = doc[ref_info["page"]]
        pix = page.get_pixmap(matrix=mat, clip=bbox, colorspace=fitz.csGRAY)
    except Exception:
        return [f"  [{ref_info['label']}  — render failed]"]

    pw, ph = pix.width, pix.height
    data   = pix.samples     # bytes, 1 byte per pixel (gray)

    # Using ▀ (upper half-block): each terminal char covers 2 pixel rows.
    # We encode brightness by choosing from a block-char ramp.
    # Two rows → average → invert (PDF: white bg, dark text).
    TOP   = " ·:░▒▓█"   # 8 levels light→dark
    n     = len(TOP) - 1

    lines = []
    for py in range(0, ph, 2):
        row = []
        for px in range(min(pw, term_w)):
            t = int(data[py * pw + px])        if py * pw + px < len(data)         else 255
            b = int(data[(py + 1) * pw + px])  if (py+1) < ph else 255
            avg = (t + b) // 2
            inv = 255 - avg                    # invert so dark content = high value
            row.append(TOP[min(n, inv * (n + 1) // 256)])
        lines.append("".join(row))
        if len(lines) >= term_h:
            break

    return lines


# ── word tagging ──────────────────────────────────────────────────────────────

def _ref_in_paragraph(text, refs):
    """Return the first reference key mentioned in text, or None."""
    for m in _FIG_CAPTION_RE.finditer(text):
        key = f"fig{m.group(1).lower()}"
        if key in refs:
            return key
    for m in _EQ_REF_TEXT_RE.finditer(text):
        key = f"eq{m.group(1)}"
        if key in refs:
            return key
    return None


def tag_words(text, refs):
    """
    Split text into paragraphs, detect references, and return
    list of (word, ref_key_or_None) for the RSVP loop.
    """
    tagged = []
    for para in re.split(r"\n\n+", text.strip()):
        ref = _ref_in_paragraph(para, refs)
        for w in words_from(para):
            tagged.append((w, ref))
    return tagged


# ── curses display ────────────────────────────────────────────────────────────

def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE,   -1)
    curses.init_pair(2, curses.COLOR_RED,     -1)
    curses.init_pair(3, curses.COLOR_CYAN,    -1)
    curses.init_pair(4, curses.COLOR_GREEN,   -1)
    curses.init_pair(5, curses.COLOR_YELLOW,  -1)
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)


def _orp_index(word):
    n = max(1, len(re.sub(r"\W", "", word)))
    if n <= 1:  return 0
    if n <= 5:  return 1
    if n <= 9:  return 2
    if n <= 13: return 3
    return 4


def _span_highlight(word):
    n      = max(1, len(re.sub(r"\W", "", word)))
    center = _orp_index(word)
    if n <= 3:    width = n
    elif n <= 5:  width = 2
    elif n <= 8:  width = 3
    elif n <= 12: width = 4
    elif n <= 16: width = 5
    else:         width = 6
    half  = width // 2
    start = max(0, min(center - half, len(word) - width))
    return set(range(start, min(len(word), start + width)))


def _dist_highlight(word):
    n      = max(1, len(re.sub(r"\W", "", word)))
    center = _orp_index(word)
    wlen   = len(word)
    if n <= 3:    count = n
    elif n <= 5:  count = 2
    elif n <= 9:  count = 3
    elif n <= 13: count = 4
    else:         count = 5
    selected   = {center}
    candidates = set(range(wlen)) - selected
    while len(selected) < count and candidates:
        best = max(candidates,
                   key=lambda p: min(abs(p - s) for s in selected))
        selected.add(best)
        candidates.discard(best)
    return selected


def redraw_sci(scr, word, wpm, idx, total, paused, mode,
               art_lines, ref_label, ref_caption):
    """
    RSVP word in the upper third of the screen.
    If art_lines is not empty, the lower portion shows the reference art.
    """
    scr.erase()
    H, W = scr.getmaxyx()

    # word position: upper third when a ref is present, centre otherwise
    cy = H // 3 if art_lines else H // 2

    # highlight set
    orp = _orp_index(word)
    if mode == 1:
        lit = _span_highlight(word)
    elif mode == 2:
        lit = _dist_highlight(word)
    else:
        lit = {orp}

    x0 = max(0, min(W // 2 - orp, W - len(word) - 1))

    # guide rails
    rail = "─" * (W - 2)
    try:
        scr.addstr(cy - 2, 1, rail, curses.color_pair(3))
        scr.addstr(cy + 2, 1, rail, curses.color_pair(3))
    except curses.error:
        pass

    # ORP / span / dist tick marks
    if mode == 0:
        ox = x0 + orp
        if 0 <= ox < W - 1:
            try:
                scr.addstr(cy - 1, ox, "▼", curses.color_pair(2))
                scr.addstr(cy + 1, ox, "▲", curses.color_pair(2))
            except curses.error:
                pass
    elif mode == 1:
        sx0, sx1 = x0 + min(lit), x0 + max(lit)
        for sx in range(sx0, sx1 + 1):
            if 0 <= sx < W - 1:
                top = "┬" if sx in (sx0, sx1) else "─"
                bot = "┴" if sx in (sx0, sx1) else "─"
                try:
                    scr.addstr(cy - 1, sx, top, curses.color_pair(2))
                    scr.addstr(cy + 1, sx, bot, curses.color_pair(2))
                except curses.error:
                    pass
    else:
        for idx_lit in lit:
            sx = x0 + idx_lit
            if 0 <= sx < W - 1:
                try:
                    scr.addstr(cy - 1, sx, "·", curses.color_pair(2))
                    scr.addstr(cy + 1, sx, "·", curses.color_pair(2))
                except curses.error:
                    pass

    # word characters
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

    # reference panel ─────────────────────────────────────────────────────────
    ref_start_row = cy + 4

    if art_lines:
        # label line
        label_text = f"  ── {ref_label} ──"
        if ref_caption:
            cap_preview = ref_caption[:W - len(label_text) - 4]
            label_text += f"  {cap_preview}"
        try:
            scr.addstr(ref_start_row - 1, 0,
                       label_text[:W - 1], curses.color_pair(5))
        except curses.error:
            pass

        # art rows
        available = H - 2 - ref_start_row
        for i, line in enumerate(art_lines[:available]):
            row = ref_start_row + i
            if row >= H - 2:
                break
            art_x = max(0, (W - len(line)) // 2)
            try:
                scr.addstr(row, art_x, line[:W - 1], curses.color_pair(1))
            except curses.error:
                pass

    # status / progress ───────────────────────────────────────────────────────
    mode_tag = (" ORP  ", " SPAN ", " DIST ")[mode]
    pct = idx / total
    bw  = max(10, W - 32)
    bar = "█" * int(bw * pct) + "░" * (bw - int(bw * pct))
    try:
        scr.addstr(H - 2, 0,
            f"  {wpm} WPM  │  {idx}/{total}  ({pct*100:.0f} %)  │{mode_tag}│"[:W-1],
            curses.color_pair(3))
        scr.addstr(H - 1, 0, f" {bar} "[:W - 1], curses.color_pair(4))
    except curses.error:
        pass

    # hint bar
    hint = ("  —— PAUSED ——  SPC resume · +/- speed · m mode · q quit  "
            if paused else
            "  SPC pause · +/- speed · m mode · q quit  ")
    try:
        scr.addstr(0, max(0, (W - len(hint)) // 2),
                   hint[:W - 1], curses.color_pair(3))
    except curses.error:
        pass

    scr.refresh()


def run_sci(scr, tagged_words, wpm, mode, rendered_refs, refs_meta):
    """
    RSVP loop for the scientific reader.

    tagged_words  : list of (word, ref_key_or_None)
    rendered_refs : {ref_key: [art_line, ...]}   pre-rendered art
    refs_meta     : {ref_key: ref_info_dict}      for label/caption
    """
    curses.curs_set(0)
    scr.nodelay(True)
    _init_colors()

    total  = len(tagged_words)
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
            mode = (mode + 1) % 3

        now   = time.monotonic()
        delay = 60.0 / wpm

        word, ref_key = tagged_words[i] if i < total else ("", None)

        art     = rendered_refs.get(ref_key, []) if ref_key else []
        label   = refs_meta[ref_key]["label"]   if ref_key else ""
        caption = refs_meta[ref_key]["caption"] if ref_key else ""

        if not paused and now >= due:
            redraw_sci(scr, word, wpm, i + 1, total,
                       False, mode, art, label, caption)
            due = now + delay
            i  += 1
        elif paused:
            w, rk = tagged_words[max(0, i - 1)]
            a = rendered_refs.get(rk, []) if rk else []
            lb = refs_meta[rk]["label"]   if rk else ""
            cp = refs_meta[rk]["caption"] if rk else ""
            redraw_sci(scr, w, wpm, i, total,
                       True, mode, a, lb, cp)
            time.sleep(0.04)
        else:
            time.sleep(min(0.005, due - now))

    # done screen
    scr.clear()
    H, W = scr.getmaxyx()
    msg = "[ Done — press any key to return to menu ]"
    try:
        scr.addstr(H // 2, max(0, (W - len(msg)) // 2),
                   msg, curses.color_pair(4) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()
    scr.nodelay(False)
    scr.getch()


# ── section navigator menu ────────────────────────────────────────────────────

_DISPLAY_LABELS = {
    "abstract":       "Abstract",
    "introduction":   "Introduction",
    "methods":        "Methods",
    "results":        "Results",
    "discussion":     "Discussion",
    "conclusion":     "Conclusion",
    "references":     "References",
    "acknowledgments":"Acknowledgments",
    "preamble":       "Preamble",
}


def _menu_items(sections, refs_meta):
    items = []

    quick_keys = [k for k in ("abstract", "conclusion")
                  if k in sections and sections[k].strip()]
    if quick_keys:
        wc = sum(len(words_from(sections[k])) for k in quick_keys)
        rc = sum(
            sum(1 for _, r in tag_words(sections[k], refs_meta) if r)
            for k in quick_keys
        )
        items.append({
            "type": "quick", "keys": quick_keys,
            "label": "★  Quick Pre-read  (abstract + conclusion)",
            "words": wc, "refs": rc,
        })
        items.append({"type": "sep"})

    for key, text in sections.items():
        if not text.strip():
            continue
        tagged = tag_words(text, refs_meta)
        items.append({
            "type": "section", "key": key,
            "label": _DISPLAY_LABELS.get(key, key.title()),
            "words": len(tagged),
            "refs":  sum(1 for _, r in tagged if r),
        })

    items.append({"type": "sep"})

    all_tagged = tag_words("\n\n".join(sections.values()), refs_meta)
    items.append({
        "type": "full", "label": "Read full paper",
        "words": len(all_tagged),
        "refs":  sum(1 for _, r in all_tagged if r),
    })
    items.append({"type": "sep"})
    items.append({"type": "quit", "label": "Quit"})
    return items


def _draw_menu(scr, doc_title, items, cursor, selected_keys, wpm):
    scr.erase()
    H, W = scr.getmaxyx()
    _init_colors()

    header = f"  {doc_title}" if doc_title else "  Scientific Paper Navigator"
    try:
        scr.addstr(0, 0, header[:W - 1], curses.color_pair(5) | curses.A_BOLD)
        scr.addstr(1, 0, "─" * (W - 1), curses.color_pair(3))
    except curses.error:
        pass

    LIST_START = 2
    LIST_H     = H - 5

    scroll = max(0, min(cursor - LIST_H // 2, len(items) - LIST_H))
    scroll = max(0, scroll)

    col = max(20, W // 2)

    for disp, item_i in enumerate(range(scroll, min(len(items), scroll + LIST_H))):
        row = LIST_START + disp
        if row >= H - 3:
            break
        item = items[item_i]

        if item["type"] == "sep":
            try:
                scr.addstr(row, 2, "─" * min(W - 4, 70), curses.color_pair(3))
            except curses.error:
                pass
            continue

        is_cur    = item_i == cursor
        base_attr = (curses.color_pair(4) | curses.A_BOLD if is_cur
                     else curses.color_pair(1))

        if item["type"] == "quick":
            lbl  = f"  {item['label']}"
            stat = f"{item['words']} words  ·  ~{item['words']/wpm:.1f} min"
            if item["refs"]:
                stat += f"  ·  {item['refs']} ref{'s' if item['refs']!=1 else ''}"
        elif item["type"] == "section":
            tick = "✓" if item["key"] in selected_keys else " "
            lbl  = f"  [{tick}] {item['label']}"
            stat = f"{item['words']} words  ·  ~{item['words']/wpm:.1f} min"
            if item["refs"]:
                stat += f"  ·  {item['refs']} ref{'s' if item['refs']!=1 else ''}"
        elif item["type"] == "full":
            lbl  = f"      {item['label']}"
            stat = f"{item['words']} words  ·  ~{item['words']/wpm:.1f} min"
            if item["refs"]:
                stat += f"  ·  {item['refs']} ref{'s' if item['refs']!=1 else ''}"
        elif item["type"] == "quit":
            lbl  = f"      {item['label']}"
            stat = ""
        else:
            lbl = stat = ""

        line = f" {lbl:<{col}}{stat}"
        try:
            scr.addstr(row, 0, line[:W - 1], base_attr)
        except curses.error:
            pass

    hint = "  ↑↓ navigate  ·  SPC toggle  ·  A all  ·  Enter read  ·  Q quit"
    try:
        scr.addstr(H - 3, 0, "─" * (W - 1), curses.color_pair(3))
        scr.addstr(H - 2, 0, hint[:W - 1], curses.color_pair(3))
    except curses.error:
        pass

    if selected_keys:
        sel_words = sum(
            it["words"] for it in items
            if it["type"] == "section" and it["key"] in selected_keys
        )
        status = (
            f"  Selected: {len(selected_keys)} section"
            f"{'s' if len(selected_keys)!=1 else ''}"
            f"  ·  {sel_words} words  ·  ~{sel_words/wpm:.1f} min"
            f"  ·  Enter = read selected"
        )
        try:
            scr.addstr(H - 1, 0, status[:W - 1], curses.color_pair(6))
        except curses.error:
            pass

    scr.refresh()


def section_menu(scr, doc_title, items, wpm):
    """
    Interactive section navigator.
    Returns ('sections', [key, ...]) | ('full',) | ('quit',)
    """
    curses.curs_set(0)
    scr.nodelay(False)
    _init_colors()

    nav_idx = [i for i, it in enumerate(items) if it["type"] != "sep"]
    if not nav_idx:
        return ("quit",)
    cursor        = nav_idx[0]
    selected_keys = set()

    while True:
        _draw_menu(scr, doc_title, items, cursor, selected_keys, wpm)
        key = scr.getch()

        pos = nav_idx.index(cursor) if cursor in nav_idx else 0

        if key in (curses.KEY_UP, ord("k"), ord("K")):
            if pos > 0:
                cursor = nav_idx[pos - 1]
        elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
            if pos < len(nav_idx) - 1:
                cursor = nav_idx[pos + 1]
        elif key == ord(" "):
            item = items[cursor]
            if item["type"] == "section":
                k = item["key"]
                if k in selected_keys:
                    selected_keys.discard(k)
                else:
                    selected_keys.add(k)
        elif key in (ord("a"), ord("A")):
            all_sec = {it["key"] for it in items if it["type"] == "section"}
            selected_keys = set() if selected_keys == all_sec else all_sec.copy()
        elif key in (ord("q"), ord("Q")):
            return ("quit",)
        elif key in (10, 13, curses.KEY_ENTER):
            item = items[cursor]
            if item["type"] == "quit":
                return ("quit",)
            elif item["type"] == "full":
                return ("full",)
            elif item["type"] == "quick":
                return ("sections", item["keys"])
            elif item["type"] == "section":
                if selected_keys:
                    return ("sections", list(selected_keys))
                return ("sections", [item["key"]])


# ── banner / prompt helpers ───────────────────────────────────────────────────

def show_banner(scr, label, word_count, wpm, ref_count=0):
    scr.clear()
    _init_colors()
    curses.curs_set(0)
    H, W = scr.getmaxyx()

    bar  = "━" * min(52, W - 4)
    mins = word_count / wpm
    sub  = f"{word_count} words  ·  ~{mins:.1f} min at {wpm} WPM"
    if ref_count:
        sub += f"  ·  {ref_count} figure/equation reference{'s' if ref_count != 1 else ''}"
    cy   = H // 2

    for row, text, pair, bold in [
        (cy - 2, bar,   6, False),
        (cy,     label, 5, True),
        (cy + 2, sub,   3, False),
        (cy + 4, bar,   6, False),
    ]:
        attr = curses.color_pair(pair) | (curses.A_BOLD if bold else 0)
        try:
            scr.addstr(row, max(0, (W - len(text)) // 2), text[:W - 1], attr)
        except curses.error:
            pass

    scr.refresh()
    time.sleep(1.5)


def ask_continue(scr, prompt):
    scr.clear()
    _init_colors()
    curses.curs_set(0)
    scr.nodelay(False)
    H, W = scr.getmaxyx()
    hint = "[ Y / Enter = yes   ·   N or Q = no ]"
    try:
        scr.addstr(H // 2,     max(0, (W - len(prompt)) // 2),
                   prompt[:W - 1], curses.color_pair(5) | curses.A_BOLD)
        scr.addstr(H // 2 + 2, max(0, (W - len(hint)) // 2),
                   hint[:W - 1], curses.color_pair(3))
    except curses.error:
        pass
    scr.refresh()
    while True:
        k = scr.getch()
        if k in (ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
            return True
        if k in (ord("n"), ord("N"), ord("q"), ord("Q")):
            return False


# ── reading flow (menu hub → read → menu) ────────────────────────────────────

def reading_flow(scr, title, sections, wpm, mode, refs_meta, doc):
    _init_colors()
    curses.curs_set(0)

    if title:
        show_title_screen(scr, title)

    H, W = scr.getmaxyx()
    art_h = max(4, H - H // 3 - 9)
    art_w = max(20, W - 6)
    rendered_refs = {
        k: render_ref_art(doc, info, art_w, art_h)
        for k, info in refs_meta.items()
    }

    items = _menu_items(sections, refs_meta)

    while True:
        action = section_menu(scr, title, items, wpm)

        if action[0] == "quit":
            return

        elif action[0] == "sections":
            for key in action[1]:
                text = sections.get(key, "")
                if not text.strip():
                    continue
                tagged    = tag_words(text, refs_meta)
                ref_count = sum(1 for _, r in tagged if r)
                label     = _DISPLAY_LABELS.get(key, key).upper()
                show_banner(scr, label, len(tagged), wpm, ref_count)
                run_sci(scr, tagged, wpm, mode, rendered_refs, refs_meta)

        elif action[0] == "full":
            all_tagged = tag_words("\n\n".join(sections.values()), refs_meta)
            ref_count  = sum(1 for _, r in all_tagged if r)
            show_banner(scr, "FULL PAPER", len(all_tagged), wpm, ref_count)
            run_sci(scr, all_tagged, wpm, mode, rendered_refs, refs_meta)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Scientific pre-reading: abstract + conclusion first, "
                    "with inline figure/equation previews."
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
    title, sections, doc, all_blocks, page_rects = extract_sections(args.file)

    print("  Scanning figures and equations…", file=sys.stderr)
    refs_meta = scan_refs(doc, all_blocks, page_rects)

    quick_sections = [k for k in ("abstract", "conclusion") if k in sections]
    if title:
        print(f"  Title     : {title}", file=sys.stderr)
    print(f"  Sections  : {', '.join(sections.keys())}", file=sys.stderr)
    print(f"  Pre-read  : {', '.join(quick_sections) or 'none detected'}",
          file=sys.stderr)

    fig_count = sum(1 for v in refs_meta.values() if v["type"] == "fig")
    eq_count  = sum(1 for v in refs_meta.values() if v["type"] == "eq")
    print(f"  Refs found: {fig_count} figure(s), {eq_count} equation(s)",
          file=sys.stderr)

    time.sleep(0.8)

    mode = {"orp": 0, "span": 1, "dist": 2}[args.mode]
    curses.wrapper(
        lambda scr: reading_flow(
            scr, title, sections, args.wpm, mode, refs_meta, doc
        )
    )


if __name__ == "__main__":
    main()
