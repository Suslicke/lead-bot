"""Render the /today stats as a PNG card in the website's palette (dark + violet brand).

Pillow only (no browser) — light enough for the box. Colours are the real tokens from the
site's globals.css, converted oklch→sRGB here so the card matches suslicketeam.com. The
DejaVu font ships in the Docker image (fonts-dejavu-core); falls back to Pillow's default.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

from .timeutil import progress_bar  # noqa: F401  (kept importable; bars are drawn natively)
from .twenty import STAGE_LABEL, STAGE_ORDER


# --- palette: oklch (from globals.css :root.dark) -> sRGB -----------------------------------
def _oklch(L: float, C: float, h_deg: float) -> tuple[int, int, int]:
    h = math.radians(h_deg)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_

    def enc(c: float) -> int:
        c = max(0.0, min(1.0, c))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return round(max(0.0, min(1.0, c)) * 255)

    return enc(r), enc(g), enc(bl)


BG = _oklch(0.145, 0, 0)        # near-black background
PANEL = _oklch(0.205, 0, 0)     # card surface
FG = _oklch(0.985, 0, 0)        # foreground text
MUTED = _oklch(0.708, 0, 0)     # secondary text
BRAND = _oklch(0.70, 0.18, 285)  # violet accent
TRACK = _oklch(0.30, 0, 0)      # bar track

_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(_DEJAVU_BOLD if bold else _DEJAVU, size)
    except OSError:
        try:
            return ImageFont.load_default(size)  # Pillow ≥10.1 — sized default
        except TypeError:
            return ImageFont.load_default()


def render_today(data: dict) -> bytes:
    """data = StatsService.today_data() → PNG bytes for a branded stats card."""
    active = [(s, data["counts"][s]) for s in STAGE_ORDER if data["counts"].get(s)]
    peak = max((n for _, n in active), default=1)

    W, M, PAD = 860, 24, 40
    H = 250 + 46 * len(active)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([M, M, W - M, H - M], radius=28, fill=PANEL)
    x0, x1 = M + PAD, W - M - PAD
    y = M + PAD

    f_title, f_big, f_body, f_small = _font(40, True), _font(30, True), _font(23), _font(19)
    # header
    d.text((x0, y), "Today", font=f_title, fill=FG)
    dt = data["date"]
    d.text((x1 - d.textlength(dt, font=f_body), y + 12), dt, font=f_body, fill=MUTED)
    d.rounded_rectangle([x0, y + 52, x0 + 46, y + 57], radius=3, fill=BRAND)  # brand underline
    y += 78

    # KPI row + progress bar
    created, goal = data["created"], data["goal"]
    d.text((x0, y), f"KPI  {created}/{goal}", font=f_big, fill=FG)
    bw, bx = 300, x1 - 300
    d.rounded_rectangle([bx, y + 14, bx + bw, y + 30], radius=8, fill=TRACK)
    if goal > 0 and created > 0:
        fill_w = max(16, round(bw * min(1.0, created / goal)))
        d.rounded_rectangle([bx, y + 14, bx + fill_w, y + 30], radius=8, fill=BRAND)
    y += 60

    # pipeline funnel
    for s, n in active:
        d.text((x0, y), STAGE_LABEL[s], font=f_body, fill=MUTED)
        track_x = x0 + 130
        full = x1 - 40 - track_x
        d.rounded_rectangle([track_x, y + 4, x1 - 40, y + 26], radius=8, fill=TRACK)
        w = max(10, round(full * n / peak))
        d.rounded_rectangle([track_x, y + 4, track_x + w, y + 26], radius=8, fill=BRAND)
        d.text((x1 - d.textlength(str(n), font=f_body), y), str(n), font=f_body, fill=FG)
        y += 46

    # footer: conversion · today · sources, + wordmark
    y += 6
    conv = f"{round(data['conv'] * 100)}%" if data["conv"] is not None else "—"
    d.text((x0, y), f"Conv {conv}    +{created} today    {data['total']} total",
           font=f_small, fill=MUTED)
    mark = "suslicketeam"
    d.text((x1 - d.textlength(mark, font=f_small), y), mark, font=f_small, fill=BRAND)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
