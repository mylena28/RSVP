#!/usr/bin/env python3
"""RSVP — Rapid Serial Visual Presentation reader."""

import argparse
import curses
import os
import re
import sys
import time


def words_from(text):
    return [w for w in re.split(r"\s+", text.strip()) if w]


def orp_index(word):
    """Optimal Recognition Point: the focal letter at ~30 % into the word."""
    n = max(1, len(re.sub(r"\W", "", word)))
    if n <= 1:
        return 0
    if n <= 5:
        return 1
    if n <= 9:
        return 2
    if n <= 13:
        return 3
    return 4


def redraw(scr, word, wpm, idx, total, paused):
    scr.erase()
    H, W = scr.getmaxyx()
    cy = H // 2

    orp = orp_index(word)
    x0 = max(0, min(W // 2 - orp, W - len(word) - 1))

    # horizontal guide rails
    rail = "─" * (W - 2)
    try:
        scr.addstr(cy - 2, 1, rail, curses.color_pair(3))
        scr.addstr(cy + 2, 1, rail, curses.color_pair(3))
    except curses.error:
        pass

    # ORP tick marks
    orp_x = x0 + orp
    if 0 <= orp_x < W - 1:
        try:
            scr.addstr(cy - 1, orp_x, "▼", curses.color_pair(2))
            scr.addstr(cy + 1, orp_x, "▲", curses.color_pair(2))
        except curses.error:
            pass

    # word — ORP letter highlighted in red/bold
    for i, ch in enumerate(word):
        x = x0 + i
        if x >= W - 1:
            break
        attr = (
            curses.color_pair(2) | curses.A_BOLD
            if i == orp
            else curses.color_pair(1) | curses.A_BOLD
        )
        try:
            scr.addch(cy, x, ch, attr)
        except curses.error:
            pass

    # progress bar + stats
    pct = idx / total
    bw = max(10, W - 24)
    bar = "█" * int(bw * pct) + "░" * (bw - int(bw * pct))
    try:
        scr.addstr(
            H - 2,
            0,
            f"  {wpm} WPM  │  {idx}/{total}  ({pct * 100:.0f} %) "[: W - 1],
            curses.color_pair(3),
        )
        scr.addstr(H - 1, 0, f" {bar} "[: W - 1], curses.color_pair(4))
    except curses.error:
        pass

    # header hint
    hint = (
        "  —— PAUSED ——  SPC resume · +/- speed · q quit  "
        if paused
        else "  SPC pause · +/- speed · q quit  "
    )
    try:
        scr.addstr(0, max(0, (W - len(hint)) // 2), hint[: W - 1], curses.color_pair(3))
    except curses.error:
        pass

    scr.refresh()


def run(scr, words, wpm):
    curses.curs_set(0)
    scr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_CYAN, -1)
    curses.init_pair(4, curses.COLOR_GREEN, -1)

    total = len(words)
    i = 0
    paused = False
    due = time.monotonic()

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

        now = time.monotonic()
        delay = 60.0 / wpm

        if not paused and now >= due:
            redraw(scr, words[i], wpm, i + 1, total, False)
            due = now + delay
            i += 1
        elif paused:
            redraw(scr, words[max(0, i - 1)], wpm, i, total, True)
            time.sleep(0.04)
        else:
            time.sleep(min(0.005, due - now))

    scr.clear()
    H, W = scr.getmaxyx()
    msg = "[ Done! Press any key to exit. ]"
    try:
        scr.addstr(
            H // 2,
            max(0, (W - len(msg)) // 2),
            msg,
            curses.color_pair(4) | curses.A_BOLD,
        )
    except curses.error:
        pass
    scr.refresh()
    scr.nodelay(False)
    scr.getch()


def main():
    ap = argparse.ArgumentParser(
        description="RSVP reader — display text word-by-word at speed."
    )
    ap.add_argument("file", nargs="?", help="text file to read (omit to paste via stdin)")
    ap.add_argument("--wpm", type=int, default=250, help="words per minute (default: 250)")
    args = ap.parse_args()

    if args.file:
        with open(args.file) as f:
            text = f.read()
    elif not sys.stdin.isatty():
        # stdin is a pipe — read text then give the TTY back to curses
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
        f"\n  {len(words)} words  ·  {args.wpm} WPM  ·"
        f"  ~{minutes:.1f} min  —  starting in 1 s…\n",
        file=sys.stderr,
    )
    time.sleep(1)

    curses.wrapper(lambda scr: run(scr, words, args.wpm))


if __name__ == "__main__":
    main()
