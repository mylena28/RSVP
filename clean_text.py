#!/usr/bin/env python3
"""
Clean garbled text in scientific PDFs via Gemini vision.

PyMuPDF emits U+FFFD (▯) for every glyph it cannot map to Unicode —
typically Greek letters and math operators in inline prose (e.g. "the
parameter ▯ controls…" should read "the parameter α controls…").

This script finds those garbled non-equation text blocks, sends each
page's image to Gemini, and saves the cleaned text to a JSON sidecar so
pre_read.py can use it without needing the API key at read time.

Usage:
    python clean_text.py paper.pdf
    python clean_text.py paper.pdf --api-key AIza...

Sidecar is named  paper.clean.json  and loaded automatically by pre_read.py.
Get a free API key at: https://aistudio.google.com/apikey
"""

import argparse
import io
import json
import os
import re
import sys
import time

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF not installed — rebuild the Docker image.")

try:
    import google.generativeai as genai
    from PIL import Image
except ImportError:
    sys.exit(
        "google-generativeai or Pillow not installed.\n"
        "Rebuild the Docker image, or install with:\n"
        "    pip install google-generativeai Pillow"
    )

_FDFD = chr(0xFFFD)


# ── helpers ───────────────────────────────────────────────────────────────────

def _garble_ratio(text):
    stripped = text.replace(" ", "")
    if not stripped:
        return 0.0
    return sum(c == _FDFD for c in stripped) / len(stripped)


def _math_density(text):
    math = len(re.findall(r"[=+*/^∫∂→←≤≥≠≈∑∏√∞∇·×±]", text))
    return math / max(1, len(text))


def _is_equation_block(text):
    """True if this block is a display equation (not prose to be cleaned)."""
    ratio = _garble_ratio(text)
    if ratio > 0.20:
        return True
    if _math_density(text) > 0.12:
        return True
    return False


def _render_page(page, dpi=150):
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
    return pix.tobytes("png")


# ── Gemini call ───────────────────────────────────────────────────────────────

_PROMPT = """\
This is page {page_num} of a scientific paper. The text was extracted by PDF \
software, but some characters could not be decoded and appear as ▯ \
(U+FFFD replacement character).

For each text block listed below, provide a cleaned version where ▯ characters \
are replaced with the most likely symbol — Greek letters (α β γ δ ε ζ η θ ι κ \
λ μ ν ξ π ρ σ τ υ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω), math operators (× ÷ ± ≤ ≥ ≠ \
≈ ∞ ∂ ∇ ∑ ∫ ∮ ∝ ⟨ ⟩), or other symbols — based on context and what you can \
see in the page image. Keep all correctly decoded text exactly as-is.

Return only valid JSON (no markdown):
{{"blocks": [{{"id": 0, "text": "cleaned text"}}, ...]}}

Blocks to clean:
{blocks_json}
"""


def _ask_gemini(model, png_bytes, page_num, blocks):
    img = Image.open(io.BytesIO(png_bytes))
    blocks_json = json.dumps(
        [{"id": i, "text": b["text"]} for i, b in enumerate(blocks)],
        ensure_ascii=False,
    )
    prompt = _PROMPT.format(page_num=page_num, blocks_json=blocks_json)
    response = model.generate_content([img, prompt])
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ── main ──────────────────────────────────────────────────────────────────────

def clean(pdf_path, api_key=None, model_name="gemini-2.0-flash", dpi=150,
          force=False, verbose=True):
    """
    Find garbled prose blocks, clean them via Gemini, save .clean.json sidecar.
    Returns the sidecar path.
    """
    sidecar = pdf_path.rsplit(".", 1)[0] + ".clean.json"

    if os.path.exists(sidecar) and not force:
        if verbose:
            print(f"  Sidecar already exists: {sidecar}  (use --force to rerun)")
        return sidecar

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        sys.exit(
            "No API key found.\n"
            "Set GEMINI_API_KEY in your environment or pass --api-key.\n"
            "Get a free key at: https://aistudio.google.com/apikey"
        )

    genai.configure(api_key=key)
    model  = genai.GenerativeModel(model_name)
    doc    = fitz.open(pdf_path)
    result = {}
    total_cleaned = 0

    for page_num, page in enumerate(doc):
        raw_blocks = page.get_text(
            "dict", flags=fitz.TEXT_PRESERVE_WHITESPACE
        )["blocks"]

        # Collect prose blocks that have garbled chars but are not equations
        garbled = []
        for b in raw_blocks:
            if b["type"] != 0:
                continue
            text = " ".join(
                sp["text"] for ln in b["lines"] for sp in ln["spans"]
            ).strip()
            if _garble_ratio(text) < 0.01:
                continue
            if _is_equation_block(text):
                continue
            garbled.append({"bbox": list(b["bbox"]), "text": text})

        if not garbled:
            continue

        if verbose:
            print(
                f"  Page {page_num + 1}/{len(doc)}: "
                f"{len(garbled)} block(s) to clean…",
                end=" ", flush=True,
            )

        png_bytes = _render_page(page, dpi)

        try:
            resp = _ask_gemini(model, png_bytes, page_num + 1, garbled)
            cleaned = resp.get("blocks", [])
        except (json.JSONDecodeError, KeyError, Exception) as e:
            if verbose:
                print(f"WARN: {e}")
            continue

        page_result = []
        for item in cleaned:
            idx  = item.get("id")
            text = item.get("text", "").strip()
            if idx is None or idx >= len(garbled) or not text:
                continue
            page_result.append({
                "bbox": garbled[idx]["bbox"],
                "text": text,
            })

        result[str(page_num)] = page_result
        total_cleaned += len(page_result)
        if verbose:
            print(f"{len(page_result)} cleaned")

        # Gemini free tier: 15 RPM → wait 4.5 s between pages
        time.sleep(4.5)

    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"\n  Done — {total_cleaned} blocks cleaned, saved to {sidecar}")

    return sidecar


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("file", help="PDF file to process")
    ap.add_argument("--api-key", help="Gemini API key (or set GEMINI_API_KEY)")
    ap.add_argument("--model",   default="gemini-2.0-flash",
                    help="Gemini model (default: gemini-2.0-flash)")
    ap.add_argument("--dpi",     type=int, default=150,
                    help="Rendering DPI (default: 150)")
    ap.add_argument("--force",   action="store_true",
                    help="Re-run even if sidecar already exists")
    ap.add_argument("--quiet",   action="store_true")
    args = ap.parse_args()

    clean(args.file, api_key=args.api_key, model_name=args.model,
          dpi=args.dpi, force=args.force, verbose=not args.quiet)


if __name__ == "__main__":
    main()
