#!/usr/bin/env python3
"""
Equation detection via Claude vision API.

Renders each PDF page as a PNG, sends it to Claude, and stores the
detected equation bounding boxes in a JSON sidecar file next to the PDF.

Usage:
    python detect_equations.py paper.pdf
    python detect_equations.py paper.pdf --api-key sk-ant-...

The sidecar is named  paper.equations.json  and is read automatically
by pre_read.py when present, replacing the fragile text-based detection.
"""

import argparse
import base64
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
    import anthropic
except ImportError:
    sys.exit(
        "anthropic SDK not installed.\n"
        "Add  anthropic  to the Dockerfile and rebuild, or install it with:\n"
        "    pip install anthropic"
    )


# ── prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a precise PDF equation detector. "
    "Given a page image from a scientific paper, you find every display equation "
    "(block-level, set apart from the prose). "
    "You return only valid JSON — no explanation, no markdown fences."
)

_USER_TMPL = """\
This is page {page_num} of a scientific PDF rendered at {dpi} DPI.
Image size: {px_w} × {px_h} pixels.

Find every display equation (not inline math — only block-level equations
that are visually separated from the prose).

For each equation return:
  "num"   : the equation number as a string (e.g. "1", "2.3"), or null if unlabelled
  "bbox"  : [x0, y0, x1, y1] in pixels  (top-left origin, same as image coordinates)
  "label" : a short human-readable label, e.g. "Eq. (1)" or "unlabelled eq"

Return a JSON object:  {{ "equations": [ ... ] }}
If there are no display equations on this page, return:  {{ "equations": [] }}
"""


# ── rendering ─────────────────────────────────────────────────────────────────

def _render_page(page, dpi=150):
    """Render a PDF page to a PNG bytes object at the given DPI."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
    return pix.tobytes("png"), pix.width, pix.height


# ── Claude call ───────────────────────────────────────────────────────────────

def _ask_claude(client, png_bytes, page_num, px_w, px_h, dpi, model):
    b64 = base64.standard_b64encode(png_bytes).decode()
    prompt = _USER_TMPL.format(
        page_num=page_num, dpi=dpi, px_w=px_w, px_h=px_h
    )
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown fences if Claude wrapped the JSON anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ── coordinate conversion ─────────────────────────────────────────────────────

def _pixel_to_pdf(bbox_px, dpi, page_rect):
    """Convert pixel bbox [x0,y0,x1,y1] → PDF coordinates."""
    scale = 72.0 / dpi
    x0, y0, x1, y1 = bbox_px
    return [x0 * scale, y0 * scale, x1 * scale, y1 * scale]


# ── main ──────────────────────────────────────────────────────────────────────

def detect(pdf_path, api_key=None, model="claude-opus-4-7", dpi=150,
           force=False, verbose=True):
    """
    Detect equations in pdf_path and write a sidecar JSON file.

    Returns the path to the sidecar file.
    """
    sidecar = pdf_path.rsplit(".", 1)[0] + ".equations.json"

    if os.path.exists(sidecar) and not force:
        if verbose:
            print(f"  Sidecar already exists: {sidecar}  (use --force to rerun)")
        return sidecar

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        sys.exit(
            "No API key found.\n"
            "Set ANTHROPIC_API_KEY in your environment or pass --api-key."
        )

    client = anthropic.Anthropic(api_key=key)
    doc    = fitz.open(pdf_path)
    result = {}   # page_num (str) → list of eq dicts in PDF coordinates

    for page_num, page in enumerate(doc):
        if verbose:
            print(f"  Page {page_num + 1}/{len(doc)} …", end=" ", flush=True)

        png_bytes, px_w, px_h = _render_page(page, dpi)

        try:
            resp = _ask_claude(client, png_bytes, page_num + 1,
                               px_w, px_h, dpi, model)
        except (json.JSONDecodeError, KeyError, Exception) as e:
            if verbose:
                print(f"WARN: {e}")
            result[str(page_num)] = []
            continue

        eqs = resp.get("equations", [])
        page_eqs = []
        for eq in eqs:
            bbox_px = eq.get("bbox")
            if not bbox_px or len(bbox_px) != 4:
                continue
            bbox_pdf = _pixel_to_pdf(bbox_px, dpi, page.rect)
            page_eqs.append({
                "num":   eq.get("num"),
                "label": eq.get("label", "equation"),
                "bbox":  bbox_pdf,
            })

        result[str(page_num)] = page_eqs
        total_eq = len(page_eqs)
        if verbose:
            print(f"{total_eq} equation{'s' if total_eq != 1 else ''} found")

        # Polite rate-limit pause
        time.sleep(0.3)

    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    if verbose:
        total = sum(len(v) for v in result.values())
        print(f"\n  Done — {total} equations detected, saved to {sidecar}")

    return sidecar


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="PDF file to process")
    ap.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    ap.add_argument("--model",   default="claude-opus-4-7",
                    help="Claude model to use (default: claude-opus-4-7)")
    ap.add_argument("--dpi",     type=int, default=150,
                    help="Rendering DPI (default: 150; higher = more accurate but slower)")
    ap.add_argument("--force",   action="store_true",
                    help="Re-run even if sidecar already exists")
    ap.add_argument("--quiet",   action="store_true")
    args = ap.parse_args()

    detect(args.file, api_key=args.api_key, model=args.model,
           dpi=args.dpi, force=args.force, verbose=not args.quiet)


if __name__ == "__main__":
    main()
