#!/usr/bin/env python3
"""News-image entry for make.fun bounty news-image-20261120.

"Sum up 20 November's world news in one image" -- a newspaper front page
drawn entirely by this program. Python standard library only: the PNG is
encoded by hand (zlib + chunk CRCs) and every letter comes from an embedded
5x7 bitmap font. No network, no wall clock, no randomness, no timestamps --
running the program twice produces byte-identical output.

Usage:
    python3 main.py            # writes entry.png to $MAKEFUN_OUTPUT_DIR
                               # (default /output)

    >>> STORIES is the ONE place to edit: each entry is
    (headline, subline, accent colour, icon kind). Headlines are rendered
    in ALL CAPS; keep them <= ~48 chars, sublines <= ~80 chars. The layout
    engine asserts widths at build time and shrinks the font scale if a
    line is too wide, so a too-long line can never overflow the page.
"""

import binascii
import math
import os
import struct
import sys
import zlib

# ---------------------------------------------------------------------------
# STORIES -- the five stories of Friday 20 November 2026, researched
# ~04:45 UTC / 11:45 WIB on 20 Nov 2026 (see news-20261120-research.md).
# Each story: (HEADLINE, subline, accent colour (R, G, B), icon kind).
# Icon kinds: "globe", "ballot", "chart", "rocket", "trophy", "flag",
#             "coin", "bolt", "satellite".  Unknown kinds fall back to a
#             plain dot icon.  Headlines are drawn in ALL CAPS from the
#             embedded font (A-Z, 0-9 and basic punctuation only).
# ---------------------------------------------------------------------------
STORIES = [
    ("TRUMP, XI, PUTIN HOLD FIRST 3-WAY SUMMIT",
     "SHENZHEN TALKS ISSUE FOUR-POINT PEACE DECLARATION.",
     (46, 111, 115), "flag"),
    ("ANTHROPIC SOARS 17% IN RECORD IPO DEBUT",
     "SHARES CLOSE AT $97.17; $81BN RAISE IS LARGEST EVER.",
     (107, 124, 60), "rocket"),
    ("HOUTHI MISSILE HITS RIYADH'S TALLEST TOWER",
     "PIF TOWER DAMAGED IN SECOND KAFD STRIKE IN 2 WEEKS.",
     (166, 74, 60), "bolt"),
    ("WALL STREET SINKS 2% IN SIXTH STRAIGHT LOSS",
     "DOW DOWN 1,100 POINTS; NASDAQ FALLS 2.2%.",
     (72, 96, 145), "chart"),
    ("COP31 CLOSING DAY WITH FOSSIL FUELS ERASED",
     "DRAFT DROPS EVERY FOSSIL REFERENCE; NO DEAL YET.",
     (122, 79, 110), "globe"),
]

DATE_LINE = "FRIDAY, 20 NOVEMBER 2026"
KICKER = "THE WORLD IN BRIEF"
FOOTER = "DRAWN ENTIRELY BY CODE - NO PHOTOGRAPHS USED"

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
PAPER = (247, 243, 234)   # off-white paper
INK = (18, 32, 62)        # dark navy ink
INK_SOFT = (70, 80, 105)  # softer navy for sublines
RULE = (196, 188, 170)    # thin divider
ACCENT_RULE = (18, 32, 62)

# ---------------------------------------------------------------------------
# Embedded 5x7 bitmap font.  Each glyph is 7 rows of 5 characters;
# "#" is a set pixel.  Covers A-Z, 0-9, space and common punctuation.
# ---------------------------------------------------------------------------
FONT = {
    "A": ("..#..", ".#.#.", "#...#", "#...#", "#####", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": (".####", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "##..#", "#.#.#", "#..##", "#..##", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "...#.", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ",": (".....", ".....", ".....", ".....", ".....", ".##..", ".#..."),
    ".": (".....", ".....", ".....", ".....", ".....", ".....", ".##.."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ";": (".....", ".##..", ".##..", ".....", ".##..", ".##..", ".#..."),
    "'": ("..#..", "..#..", "..#..", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "/": ("....#", "....#", "...#.", "...#.", "..#..", ".#...", "#...."),
    "(": ("...##", "..#..", ".#...", ".#...", ".#...", "..#..", "...##"),
    ")": ("##...", "..#..", "...#.", "...#.", "...#.", "..#..", "##..."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "%": ("##..#", "##.#.", "...#.", "..#..", ".#...", "#.##.", "#..##"),
    "&": (".##..", "#..#.", "#..#.", ".#...", "#.#.#", "#..#.", ".##.#"),
    "$": ("..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "=": (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    '"': (".#.#.", ".#.#.", ".....", ".....", ".....", ".....", "....."),
    "*": (".....", ".#.#.", "..#..", "#####", "..#..", ".#.#.", "....."),
}
BLANK_GLYPH = (".....",) * 7

for _g in FONT.values():
    assert len(_g) == 7 and all(len(_r) == 5 for _r in _g)

# ---------------------------------------------------------------------------
# Canvas: an RGB pixel buffer with tiny drawing primitives.
# ---------------------------------------------------------------------------
W, H = 1024, 1024


class Canvas:
    def __init__(self, width=W, height=H, bg=PAPER):
        self.w = width
        self.h = height
        self.px = bytearray(width * height * 3)
        self.fill_rect(0, 0, width, height, bg)

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = color

    def fill_rect(self, x, y, w, h, color):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        r, g, b = color
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                i = base + (xx - x0) * 3
                self.px[i], self.px[i + 1], self.px[i + 2] = r, g, b

    def hline(self, x, y, w, color, thick=1):
        self.fill_rect(x, y, w, thick, color)

    def vline(self, x, y, h, color, thick=1):
        self.fill_rect(x, y, thick, h, color)

    def rect(self, x, y, w, h, color, thick=1):
        self.hline(x, y, w, color, thick)
        self.hline(x, y + h - thick, w, color, thick)
        self.vline(x, y, h, color, thick)
        self.vline(x + w - thick, y, h, color, thick)

    def line(self, x0, y0, x1, y1, color, thick=1):
        """Bresenham line (thick = square brush)."""
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self.fill_rect(x0 - thick // 2, y0 - thick // 2, thick, thick, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def fill_circle(self, cx, cy, r, color):
        for yy in range(cy - r, cy + r + 1):
            dx = int((r * r - (yy - cy) ** 2) ** 0.5) if abs(yy - cy) <= r else 0
            self.fill_rect(cx - dx, yy, 2 * dx + 1, 1, color)

    def circle(self, cx, cy, r, color, thick=2):
        # Outline circle: draw concentric rings.
        for rr in range(r - thick + 1, r + 1):
            if rr < 1:
                continue
            for deg in range(0, 360):
                a = math.radians(deg)
                self.set(cx + int(rr * math.cos(a) + 0.5),
                         cy + int(rr * math.sin(a) + 0.5), color)

    def fill_triangle(self, p1, p2, p3, color):
        xs = [p1[0], p2[0], p3[0]]
        ys = [p1[1], p2[1], p3[1]]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)

        def sign(ax, ay, bx, by, cx, cy):
            return (ax - cx) * (by - cy) - (bx - cx) * (ay - cy)

        d = sign(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
        if d == 0:
            return
        for yy in range(y0, y1 + 1):
            for xx in range(x0, x1 + 1):
                d1 = sign(xx, yy, p1[0], p1[1], p2[0], p2[1])
                d2 = sign(xx, yy, p2[0], p2[1], p3[0], p3[1])
                d3 = sign(xx, yy, p3[0], p3[1], p1[0], p1[1])
                neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
                pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
                if not (neg and pos):
                    self.set(xx, yy, color)


# ---------------------------------------------------------------------------
# Text: widths and drawing from the bitmap font.
# ---------------------------------------------------------------------------
def char_advance(scale, gap=None):
    return 5 * scale + (scale if gap is None else gap)


def text_width(text, scale, gap=None):
    if not text:
        return 0
    return len(text) * char_advance(scale, gap) - (scale if gap is None else gap)


def draw_text(cv, x, y, text, scale, color, gap=None):
    adv = char_advance(scale, gap)
    cx = x
    for ch in text:
        glyph = FONT.get(ch, BLANK_GLYPH)
        for r, row in enumerate(glyph):
            for c, bit in enumerate(row):
                if bit == "#":
                    cv.fill_rect(cx + c * scale, y + r * scale, scale, scale, color)
        cx += adv


def draw_text_centred(cv, cx, y, text, scale, color, gap=None):
    draw_text(cv, cx - text_width(text, scale, gap) // 2, y, text, scale, color, gap)


def draw_text_right(cv, x_right, y, text, scale, color, gap=None):
    draw_text(cv, x_right - text_width(text, scale, gap), y, text, scale, color, gap)


def fit_text(text, max_width, scale, gap=None):
    """Return (text, scale) that fits max_width: shrink scale, then trim.

    Prints a warning to stderr when shrinking/trimming so a too-long line
    is caught at build time instead of overflowing the page.
    """
    s = scale
    while s > 1 and text_width(text, s, gap) > max_width:
        s -= 1
    if text_width(text, s, gap) > max_width:
        ell = "..."
        while text and text_width(text + ell, s, gap) > max_width:
            text = text[:-1]
        text = text + ell
        print(f"warning: trimmed line to fit: {text!r}", file=sys.stderr)
    elif s != scale:
        print(f"warning: shrank scale {scale} -> {s} for: {text!r}", file=sys.stderr)
    return text, s

# ---------------------------------------------------------------------------
# Icons: small flat pictograms drawn with rects / circles / lines.
# (bx, by) is the top-left of the icon square, s is its side length.
# ---------------------------------------------------------------------------
def tint(color, frac=0.22):
    return tuple(int(c * frac + p * (1 - frac)) for c, p in zip(color, PAPER))


def draw_icon(cv, kind, bx, by, s, color):
    """Icon background panel + pictogram. All icons use flat shapes only."""
    cv.fill_rect(bx, by, s, s, tint(color))
    cv.rect(bx, by, s, s, color, 2)
    cx, cy = bx + s // 2, by + s // 2
    u = s // 10  # unit
    if kind == "globe":
        r = 3 * u
        cv.circle(cx, cy, r, color, 3)
        cv.vline(cx, cy - r, 2 * r + 1, color, 2)
        cv.hline(cx - r, cy, 2 * r + 1, color, 2)
        cv.line(cx - r + 4, cy - r + 8, cx + r - 4, cy + r - 8, color, 2)
    elif kind == "ballot":
        cv.rect(bx + 2 * u, by + 5 * u, 6 * u, 4 * u, color, 3)       # box
        cv.hline(bx + 3 * u, by + 5 * u, 4 * u, color, 3)             # slot
        cv.line(bx + 3 * u, by + 3 * u, bx + 4 * u, by + 4 * u, color, 3)
        cv.line(bx + 4 * u, by + 4 * u, bx + 7 * u, by + 1 * u, color, 3)
    elif kind == "chart":
        cv.vline(bx + 2 * u, by + 2 * u, 6 * u, color, 3)             # y axis
        cv.hline(bx + 2 * u, by + 8 * u, 6 * u, color, 3)             # x axis
        pts = [(2, 7), (4, 5), (5, 6), (7, 3), (8, 2)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            cv.line(bx + x0 * u, by + y0 * u, bx + x1 * u, by + y1 * u, color, 3)
        for x, y in pts:
            cv.fill_circle(bx + x * u, by + y * u, 3, color)
    elif kind == "rocket":
        cv.fill_triangle((cx, by + u), (cx - 2 * u, by + 4 * u),
                         (cx + 2 * u, by + 4 * u), color)             # nose
        cv.fill_rect(cx - 2 * u, by + 4 * u, 4 * u, 3 * u, color)     # body
        cv.fill_triangle((cx - 2 * u, by + 5 * u), (cx - 4 * u, by + 8 * u),
                         (cx - 2 * u, by + 7 * u), color)             # fin L
        cv.fill_triangle((cx + 2 * u, by + 5 * u), (cx + 4 * u, by + 8 * u),
                         (cx + 2 * u, by + 7 * u), color)             # fin R
        cv.fill_circle(cx, by + 5 * u, u, PAPER)                      # window
        cv.fill_triangle((cx, by + 9 * u), (cx - u, by + 7 * u),
                         (cx + u, by + 7 * u), (214, 120, 40))        # flame
    elif kind == "trophy":
        cv.fill_rect(bx + 3 * u, by + 2 * u, 4 * u, 3 * u, color)     # cup
        cv.fill_rect(bx + 2 * u, by + 2 * u, u, 2 * u, color)         # handle L
        cv.fill_rect(bx + 7 * u, by + 2 * u, u, 2 * u, color)         # handle R
        cv.fill_rect(cx - u // 2, by + 5 * u, u, 2 * u, color)        # stem
        cv.fill_rect(bx + 3 * u, by + 7 * u, 4 * u, u, color)         # base
        cv.fill_circle(cx, by + 3 * u, u // 2, PAPER)                 # shine
    elif kind == "flag":
        cv.vline(bx + 3 * u, by + u, 8 * u, color, 3)                 # pole
        cv.fill_rect(bx + 3 * u, by + u, 5 * u, 3 * u, color)         # flag
        cv.fill_circle(bx + 3 * u, by + u, 3, color)
    elif kind == "coin":
        cv.circle(cx, cy, 3 * u, color, 3)
        draw_text_centred(cv, cx, cy - 7, "$", 2, color)
    elif kind == "bolt":
        cv.fill_triangle((cx + u, by + u), (cx - 2 * u, by + 6 * u),
                         (cx + u, by + 6 * u), color)
        cv.fill_triangle((cx - u, by + 9 * u), (cx + 2 * u, by + 4 * u),
                         (cx - u, by + 4 * u), color)
    elif kind == "satellite":
        cv.fill_rect(cx - u, cy - u, 2 * u, 2 * u, color)             # body
        cv.fill_rect(bx + u, cy - u // 2, 2 * u, u, color)            # panel L
        cv.fill_rect(bx + 7 * u, cy - u // 2, 2 * u, u, color)        # panel R
        cv.line(cx, cy - u, cx + 2 * u, cy - 3 * u, color, 2)         # antenna
        cv.fill_circle(cx + 2 * u, cy - 3 * u, 2, color)
    else:  # fallback: plain dot
        cv.fill_circle(cx, cy, 2 * u, color)


# ---------------------------------------------------------------------------
# Layout (fixed geometry, 1024 x 1024)
# ---------------------------------------------------------------------------
MARGIN = 40
CONTENT_W = W - 2 * MARGIN          # 944
TEXT_X = MARGIN + 100 + 16          # icon (100) + gap, from left margin
TEXT_W = W - MARGIN - TEXT_X        # 828
ICON_S = 100
ROW_H = 158
STORIES_TOP = 160


def render():
    cv = Canvas()

    # --- Masthead -------------------------------------------------------
    draw_text_centred(cv, W // 2, 30, KICKER, 2, INK_SOFT)
    # Date: scale 6, tight gap so the 26-char line fits with margins.
    date_scale, date_gap = 6, 3
    assert text_width(DATE_LINE, date_scale, date_gap) <= CONTENT_W, \
        f"date too wide: {text_width(DATE_LINE, date_scale, date_gap)}"
    draw_text_centred(cv, W // 2, 58, DATE_LINE, date_scale, INK, gap=date_gap)
    cv.hline(MARGIN, 116, CONTENT_W, ACCENT_RULE, 3)
    cv.hline(MARGIN, 122, CONTENT_W, RULE, 1)
    draw_text_centred(cv, W // 2, 134, "FIVE STORIES FROM AROUND THE WORLD",
                      2, INK_SOFT)

    # --- Story rows -----------------------------------------------------
    for i, (headline, subline, accent, icon) in enumerate(STORIES):
        top = STORIES_TOP + i * ROW_H
        draw_icon(cv, icon, MARGIN, top + 29, ICON_S, accent)

        hl, hl_scale = fit_text(headline.upper(), TEXT_W, 3)
        draw_text(cv, TEXT_X, top + 40, hl, hl_scale, INK)

        sl, sl_scale = fit_text(subline.upper(), TEXT_W, 2, gap=1)
        draw_text(cv, TEXT_X, top + 78, sl, sl_scale, INK_SOFT, gap=1)

        draw_text_right(cv, W - MARGIN, top + 40, f"{i + 1:02d}", 2, accent)

        if i < len(STORIES) - 1:
            cv.hline(MARGIN, top + ROW_H - 1, CONTENT_W, RULE, 1)

    # --- Footer ---------------------------------------------------------
    foot_top = STORIES_TOP + len(STORIES) * ROW_H + 12
    cv.hline(MARGIN, foot_top, CONTENT_W, ACCENT_RULE, 2)
    draw_text_centred(cv, W // 2, foot_top + 12, FOOTER, 2, INK_SOFT)

    return cv


# ---------------------------------------------------------------------------
# PNG encoder (stdlib only): IHDR / IDAT (zlib) / IEND, correct CRCs.
# No ancillary chunks, so no timestamps -- output is fully deterministic.
# ---------------------------------------------------------------------------
def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF))


def encode_png(cv):
    raw = bytearray()
    stride = cv.w * 3
    for y in range(cv.h):
        raw.append(0)  # filter: None
        raw += cv.px[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")
    png = encode_png(render())
    with open(out_path, "wb") as f:
        f.write(png)
    print(f"Wrote {out_path} ({len(png)} bytes, {W}x{H})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
