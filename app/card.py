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
TRACK = _oklch(0.28, 0, 0)      # bar / ring track
GREEN = _oklch(0.72, 0.17, 150)  # won
RED = _oklch(0.60, 0.13, 25)     # lost

# Progress stages get a cool→bright violet ramp (further along = brighter); Won green, Lost red.
_RAMP = {"TO_CONTACT": 0.0, "CONTACTED": 0.25, "REPLIED": 0.5,
         "QUALIFIED": 0.75, "PROPOSAL": 1.0}


def _stage_color(stage: str) -> tuple[int, int, int]:
    if stage == "WON":
        return GREEN
    if stage == "LOST":
        return RED
    t = _RAMP.get(stage, 0.5)
    return _oklch(0.60 + 0.16 * t, 0.10 + 0.09 * t, 285)

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
    total = max(data["total"], 1)
    n = len(active)

    W, M, PAD = 860, 24, 44
    ROW, HEADER_H, KPI_H, FOOTER_H = 48, 72, 116, 60
    H = 2 * (M + PAD) + HEADER_H + KPI_H + ROW * n + FOOTER_H
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([M, M, W - M, H - M], radius=30, fill=PANEL)
    x0, x1 = M + PAD, W - M - PAD

    f_title, f_big, f_body = _font(40, True), _font(28, True), _font(23)
    f_small, f_ring, f_cap = _font(19), _font(27, True), _font(16)

    # --- header ---
    y = M + PAD
    d.text((x0, y), "Today", font=f_title, fill=FG)
    dt = data["date"]
    d.text((x1 - d.textlength(dt, font=f_body), y + 12), dt, font=f_body, fill=MUTED)
    d.rounded_rectangle([x0, y + 52, x0 + 46, y + 57], radius=3, fill=BRAND)  # brand underline
    y += HEADER_H

    # --- KPI: label on the left, progress ring on the right ---
    value, goal, label = data["kpi_value"], data["goal"], data["kpi_label"]
    d.text((x0, y + 26), "KPI", font=f_cap, fill=MUTED)
    d.text((x0, y + 48), label, font=f_big, fill=FG)
    r, rw = 46, 13
    cx, cy = x1 - r, y + KPI_H // 2 - 6
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, 0, 360, fill=TRACK, width=rw)
    ratio = min(1.0, value / goal) if goal > 0 else 0.0
    if value > 0:
        d.arc(box, -90, -90 + 360 * ratio, fill=BRAND, width=rw)
    vt = f"{value}/{goal}"
    d.text((cx - d.textlength(vt, font=f_ring) / 2, cy - 16), vt, font=f_ring, fill=FG)
    y += KPI_H

    # --- pipeline: one coloured bar per stage (width = share of the total) ---
    label_w, num_w = 134, 44
    track_x, track_x1 = x0 + label_w, x1 - num_w
    for s, cnt in active:
        d.text((x0, y + 1), STAGE_LABEL[s], font=f_body, fill=MUTED)
        d.rounded_rectangle([track_x, y + 5, track_x1, y + 29], radius=9, fill=TRACK)
        w = max(14, round((track_x1 - track_x) * cnt / total))
        d.rounded_rectangle([track_x, y + 5, track_x + w, y + 29], radius=9, fill=_stage_color(s))
        d.text((x1 - d.textlength(str(cnt), font=f_body), y + 1), str(cnt), font=f_body, fill=FG)
        y += ROW

    # --- footer: stat row (· separators) + wordmark ---
    y += 8
    conv = f"{round(data['conv'] * 100)}%" if data["conv"] is not None else "—"
    stats = f"Conv {conv}   ·   +{data['created']} today   ·   {data['total']} total"
    if data.get("due"):
        stats += f"   ·   {len(data['due'])} due"
    d.text((x0, y), stats, font=f_small, fill=MUTED)
    mark = "suslicketeam"
    d.text((x1 - d.textlength(mark, font=f_small), y), mark, font=f_small, fill=BRAND)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
