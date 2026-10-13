# /// script
# requires-python = ">=3.11"
# dependencies = ["uharfbuzz>=0.56", "fonttools>=4.55"]
# ///
"""Generate the shiruviaa profile artwork.

Run with `uv run tools/build.py`. Writes SVG sources and resvg-rendered PNGs
into `assets/`. Text is converted to outlines because GitHub serves README
SVGs as images, which cannot load web fonts.

Requires `resvg` on PATH plus Adwaita Sans and JetBrains Mono (both OFL).
"""

from __future__ import annotations

import random
import re
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

FONT_SANS = Path("/usr/share/fonts/Adwaita/AdwaitaSans-Regular.ttf")
FONT_MONO = Path("/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf")

# palette
NIGHT = "#0E0B1A"
NIGHT_HI = "#171230"
INK = "#FBF8FF"
PINK = "#FF6FB5"
VIOL = "#8B6CFF"
DEEP = "#5A45D6"
BLUSH = "#FFE0F1"
LILAC = "#E6DEFF"
GOLD = "#FFD58A"


# ---------------------------------------------------------------- text ----

@dataclass
class Font:
    path: Path
    weight: int = 400

    def __post_init__(self) -> None:
        blob = hb.Blob.from_file_path(str(self.path))
        self.face = hb.Face(blob)
        self.font = hb.Font(self.face)
        self.upem = self.face.upem
        axes = {a.tag for a in self.face.axis_infos}
        if "wght" in axes:
            self.font.set_variations({"wght": self.weight})

    def path_d(self, text: str, size: float, x: float, y: float,
               anchor: str = "start", tracking: float = 0.0) -> tuple[str, float]:
        """Outline `text` at baseline (x, y). Returns (path data, advance)."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf, {"kern": True, "liga": False, "calt": False})
        s = size / self.upem
        track = tracking * size
        total = sum(p.x_advance for p in buf.glyph_positions) * s + track * (len(buf.glyph_infos) - 1)
        if anchor == "middle":
            x -= total / 2
        elif anchor == "end":
            x -= total
        parts: list[str] = []
        pen_x = 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            pen = SVGPathPen(None, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
            self.font.draw_glyph_with_pen(info.codepoint, pen)
            d = pen.getCommands()
            if d:
                gx = x + (pen_x + pos.x_offset) * s
                gy = y - pos.y_offset * s
                parts.append(_transform_path(d, s, gx, gy))
            pen_x += pos.x_advance + track / s
        return " ".join(parts), total


def _transform_path(d: str, s: float, tx: float, ty: float) -> str:
    """Scale (y flipped) and translate an absolute-coordinate SVGPathPen path."""
    out: list[str] = []
    tokens = d.replace("M", " M ").replace("L", " L ").replace("Q", " Q ").replace(
        "C", " C ").replace("Z", " Z ").replace("H", " H ").replace("V", " V ").split()
    cmd = ""
    nums: list[float] = []

    def flush() -> None:
        if not cmd:
            return
        if cmd == "Z":
            out.append("Z")
            return
        if cmd == "H":
            out.append("H" + " ".join(f"{tx + n * s:.2f}" for n in nums))
            return
        if cmd == "V":
            out.append("V" + " ".join(f"{ty - n * s:.2f}" for n in nums))
            return
        pts = []
        for i in range(0, len(nums), 2):
            pts.append(f"{tx + nums[i] * s:.2f} {ty - nums[i + 1] * s:.2f}")
        out.append(cmd + " ".join(pts))

    for t in tokens:
        if t in "MLQCZHV":
            flush()
            cmd, nums = t, []
        else:
            nums.append(float(t))
    flush()
    return "".join(out)


SANS = Font(FONT_SANS, 400)
SANS_MED = Font(FONT_SANS, 560)
SANS_SEMI = Font(FONT_SANS, 640)
MONO = Font(FONT_MONO)


def text(font: Font, s: str, size: float, x: float, y: float, fill: str,
         opacity: float = 1.0, anchor: str = "start", tracking: float = 0.0) -> str:
    d, _ = font.path_d(s, size, x, y, anchor, tracking)
    op = f' fill-opacity="{opacity}"' if opacity != 1.0 else ""
    return f'<path aria-hidden="true" d="{d}" fill="{fill}"{op}/>'


def text_width(font: Font, s: str, size: float, tracking: float = 0.0) -> float:
    return font.path_d(s, size, 0, 0, tracking=tracking)[1]


# ---------------------------------------------------- monoline wordmark ----
# Rounded geometric lowercase drawn as strokes (x-height 84..155,
# ascender 56); every glyph starts at its own x = 0.

GLYPHS: dict[str, tuple[str, float]] = {
    "s": ("M59 91 C51 84 40 81 29 81 C14 81 3 90 3 102 C3 112 10 118 23 121 L43 126 "
          "C55 129 61 134 61 143 C61 153 50 159 35 159 C21 159 9 154 0 145", 61),
    "h": ("M0 56 V154 M0 113 C0 92 12 81 30 81 C48 81 60 92 60 113 V154", 60),
    "i": ("M0 84 V154", 0),
    "r": ("M0 154 V84 M0 118 C0 96 13 81 33 81 C40 81 46 83 51 86", 51),
    "u": ("M0 84 V126 C0 145 12 155 29 155 C47 155 60 145 60 126 V84", 60),
    "v": ("M0 84 L37 153 L72 84", 72),
    "a": ("M64 92 C56 85 46 81 34 81 C14 81 0 96 0 118 C0 140 14 155 34 155 "
          "C46 155 57 149 64 140 M64 84 V154", 64),
    "o": ("M37 81 C15 81 0 95 0 118 C0 141 15 155 37 155 C59 155 74 141 74 118 "
          "C74 95 59 81 37 81 Z", 74),
    "l": ("M0 56 V140 C0 150 7 155 18 155 H26", 26),
    "y": ("M0 84 V124 C0 143 12 153 29 153 C47 153 60 143 60 124 V84 M60 124 V151 "
          "C60 171 48 181 30 181 C19 181 8 178 0 172", 60),
}
KERN = {"sh": 34, "hi": 32, "ir": 30, "ru": 32, "uv": 28, "vi": 28, "ia": 32, "aa": 34,
        "vo": 28, "os": 31, "su": 33, "ul": 32, "la": 26, "ay": 34}
WORD_TOP, WORD_BOTTOM = 44, 181  # stroke-inclusive vertical extent


def wordmark(word: str, color: str = INK, dot_colors: tuple[str, ...] = (PINK, VIOL),
             stroke: float = 15.5) -> tuple[str, float]:
    """Return (svg group, width) for the wordmark at scale 1, origin at x = 0."""
    x = 0.0
    prev = ""
    strokes: list[str] = []
    dots: list[str] = []
    for ch in word:
        if prev:
            x += KERN[prev + ch]
        d, w = GLYPHS[ch]
        strokes.append(f'<path d="{d}" transform="translate({x:g} 0)"/>')
        if ch == "i":
            dots.append(f'<circle cx="{x:g}" cy="55" r="10" fill="{dot_colors[len(dots) % len(dot_colors)]}"/>')
        x += w
        prev = ch
    g = (f'<g fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
         f'stroke-linejoin="round">{"".join(strokes)}</g>{"".join(dots)}')
    return g, x


# --------------------------------------------------------------- kitsune ----
# Drawn in a 256 space; artwork bounds are x -8..264, y 14..208.

HEAD = "M128 92 L154 84 L194 34 L206 116 L226 146 L128 222 L30 146 L50 116 L62 34 L102 84 Z"
TAIL = ("M0 0 C22 -26 36 -66 22 -104 C17 -118 8 -126 -4 -134 C2 -118 2 -102 -6 -88 "
        "C-24 -62 -24 -28 0 0Z")
TAIL_ANGLES = (-96, -72, -48, -24, 0, 24, 48, 72, 96)
KIT_BOX = (-8, 14, 272, 194)  # x, y, w, h
KIT_CENTER = (128, 111)
PIVOT = (128, 150)


def kitsune(uid: str, outline: str = NIGHT, sway: bool = False) -> str:
    tails = []
    for a in sorted(TAIL_ANGLES, key=lambda a: -abs(a)):
        sx = -1 if a < 0 else 1
        grad = f"{uid}-tb" if abs(a) in (24, 72) else f"{uid}-ta"
        tails.append(
            f'<path d="{TAIL}" transform="translate({PIVOT[0]} {PIVOT[1]}) rotate({a}) scale({sx} 1)" '
            f'fill="url(#{grad})" stroke="{outline}" stroke-width="3.2" stroke-linejoin="round" '
            f'paint-order="stroke"/>')
    sway_cls = f' class="sway" style="transform-origin:{PIVOT[0]}px {PIVOT[1]}px"' if sway else ""
    return f'''<defs>
  <linearGradient id="{uid}-ta" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{VIOL}"/><stop offset="0.66" stop-color="{PINK}"/><stop offset="1" stop-color="{BLUSH}"/></linearGradient>
  <linearGradient id="{uid}-tb" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{DEEP}"/><stop offset="0.68" stop-color="{VIOL}"/><stop offset="1" stop-color="{LILAC}"/></linearGradient>
  <linearGradient id="{uid}-ear" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{PINK}"/><stop offset="1" stop-color="{VIOL}"/></linearGradient>
</defs>
<g{sway_cls}>{"".join(tails)}</g>
<g transform="translate(128 150) scale(0.76) translate(-128 -150)">
  <path d="{HEAD}" fill="{outline}" stroke="{outline}" stroke-width="16" stroke-linejoin="round"/>
  <path d="{HEAD}" fill="{INK}" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/>
  <path d="M162 90 L192 48 L198 110 Z M94 90 L64 48 L58 110 Z" fill="url(#{uid}-ear)" stroke="url(#{uid}-ear)" stroke-width="4" stroke-linejoin="round"/>
  <path d="M80 124 C92 140 104 148 116 148 C108 136 96 128 80 124Z M176 124 C164 140 152 148 140 148 C148 136 160 128 176 124Z" fill="{NIGHT}" stroke="{NIGHT}" stroke-width="3" stroke-linejoin="round"/>
  <path d="M78 118 C92 124 104 132 112 142 M178 118 C164 124 152 132 144 142" fill="none" stroke="{PINK}" stroke-width="5" stroke-linecap="round"/>
  <path d="M128 98 C134 108 138 114 138 120 C138 126 133 130 128 130 C123 130 118 126 118 120 C118 114 122 108 128 98Z" fill="url(#{uid}-ear)"/>
  <path d="M62 162 L84 166 M66 176 L86 174 M194 162 L172 166 M190 176 L170 174" fill="none" stroke="{PINK}" stroke-width="4.5" stroke-linecap="round" stroke-opacity="0.85"/>
  <path d="M118 194 H138 C140 194 141 196 140 198 L130 209 C129 210 127 210 126 209 L116 198 C115 196 116 194 118 194Z" fill="{NIGHT}" stroke="{NIGHT}" stroke-width="3" stroke-linejoin="round"/>
</g>'''


def place_kitsune(uid: str, cx: float, cy: float, scale: float, **kw) -> str:
    return (f'<g transform="translate({cx:g} {cy:g}) scale({scale:g}) '
            f'translate({-KIT_CENTER[0]} {-KIT_CENTER[1]})">{kitsune(uid, **kw)}</g>')


# -------------------------------------------------------------- ornaments ----

def sparkle(x: float, y: float, r: float, color: str, opacity: float = 1.0, cls: str = "",
            delay: float | None = None) -> str:
    k = r * 0.22
    d = (f"M{x:g} {y - r:g} C{x + k * .4:.2f} {y - k:.2f} {x + k:.2f} {y - k * .4:.2f} {x + r:g} {y:g} "
         f"C{x + k:.2f} {y + k * .4:.2f} {x + k * .4:.2f} {y + k:.2f} {x:g} {y + r:g} "
         f"C{x - k * .4:.2f} {y + k:.2f} {x - k:.2f} {y + k * .4:.2f} {x - r:g} {y:g} "
         f"C{x - k:.2f} {y - k * .4:.2f} {x - k * .4:.2f} {y - k:.2f} {x:g} {y - r:g}Z")
    c = f' class="{cls}"' if cls else ""
    st = f' style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    return f'<path d="{d}" fill="{color}" fill-opacity="{opacity}"{c}{st}/>'


def starfield(w: float, h: float, n: int, seed: int, avoid: list[tuple[float, float, float]] = ()) -> str:
    rng = random.Random(seed)
    out = []
    placed = 0
    while placed < n:
        x, y = rng.uniform(12, w - 12), rng.uniform(12, h - 12)
        if any((x - ax) ** 2 + (y - ay) ** 2 < ar ** 2 for ax, ay, ar in avoid):
            continue
        r = rng.choice((0.9, 1.1, 1.3, 1.6, 2.0))
        op = rng.uniform(0.18, 0.6)
        tw = rng.random() < 0.45
        cls = ' class="tw"' if tw else ""
        st = f' style="animation-delay:{rng.uniform(0, 5):.2f}s"' if tw else ""
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{INK}" fill-opacity="{op:.2f}"{cls}{st}/>')
        placed += 1
    return "".join(out)


def pill(x: float, y: float, label: str, size: float = 19, color: str = LILAC,
         border: str = VIOL, fill_op: float = 0.12) -> tuple[str, float]:
    tw = text_width(MONO, label, size)
    pad = size * 0.8
    h = size * 1.9
    w = tw + pad * 2
    svg = (f'<rect x="{x:g}" y="{y:g}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" fill="{border}" '
           f'fill-opacity="{fill_op}" stroke="{border}" stroke-opacity="0.45" stroke-width="1.5"/>'
           + text(MONO, label, size, x + pad, y + h / 2 + size * 0.36, color, 0.92))
    return svg, w


ANIM_CSS = """
<style>
  .tw { animation: tw 4.8s ease-in-out infinite; }
  .spk { animation: spk 3.6s ease-in-out infinite; transform-box: fill-box; transform-origin: center; }
  .sway { animation: sway 7s ease-in-out infinite; transform-box: view-box; }
  .ap { animation: ap 2.6s cubic-bezier(.45,0,.75,1) infinite; transform-box: fill-box; transform-origin: center; }
  @keyframes tw { 0%,100% { opacity: 1 } 50% { opacity: .15 } }
  @keyframes spk { 0%,100% { opacity: 1; transform: scale(1) } 50% { opacity: .35; transform: scale(.6) } }
  @keyframes sway { 0%,100% { transform: rotate(-1.4deg) } 50% { transform: rotate(1.4deg) } }
  @keyframes ap { 0% { transform: scale(1.35); opacity: 0 } 20% { opacity: .7 } 88% { transform: scale(.68); opacity: .9 } 100% { transform: scale(.68); opacity: 0 } }
  @media (prefers-reduced-motion: reduce) { .tw, .spk, .sway, .ap { animation: none } }
</style>"""


def svg_doc(w: int, h: int, title: str, desc: str, body: str, style: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-labelledby="title desc" shape-rendering="geometricPrecision">\n'
            f'<title id="title">{title}</title>\n<desc id="desc">{desc}</desc>{style}\n{body}\n</svg>\n')


# ---------------------------------------------------------------- assets ----

def avatar() -> str:
    body = f'''<defs>
  <linearGradient id="av-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{NIGHT_HI}"/><stop offset="1" stop-color="{NIGHT}"/></linearGradient>
  <radialGradient id="av-glow" cx="512" cy="470" r="470" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{VIOL}" stop-opacity="0.42"/><stop offset="0.55" stop-color="{PINK}" stop-opacity="0.10"/><stop offset="1" stop-color="{PINK}" stop-opacity="0"/></radialGradient>
</defs>
<rect width="1024" height="1024" fill="url(#av-bg)"/>
<rect width="1024" height="1024" fill="url(#av-glow)"/>
{sparkle(150, 176, 30, GOLD, 0.95)}{sparkle(884, 214, 20, INK, 0.8)}{sparkle(852, 856, 24, PINK, 0.85)}{sparkle(178, 830, 15, LILAC, 0.7)}
{place_kitsune("av", 512, 520, 3.2)}'''
    return svg_doc(1024, 1024, "shiruviaa",
                   "A white kitsune mask with pink markings in front of nine pink and violet tails, on a night sky.",
                   body)


def mark() -> str:
    x, y, w, h = KIT_BOX
    pad = 10
    W, H = w + pad * 2, h + pad * 2
    s = 4
    body = (f'<g transform="scale({s})"><g transform="translate({pad - x} {pad - y})">'
            f'{kitsune("mk")}</g></g>')
    return svg_doc(W * s, H * s, "shiruviaa kitsune",
                   "A white kitsune mask with pink markings in front of nine pink and violet tails.", body)


def banner() -> str:
    W, H = 1600, 600
    kx, ky, ks = 395, 312, 1.9
    wm, wm_w = wordmark("shiruviaa")
    wm_s = 1.08
    tx = 720
    wm_y = 170
    tag1 = "osu! tooling, engineered for"
    tag2 = "performance and power users."
    chips_y = 466
    chips = []
    cx = tx
    for label in ("rust", "native", "linux + windows", "open source"):
        svg, w = pill(cx, chips_y, label)
        chips.append(svg)
        cx += w + 14
    stars = starfield(W, H, 90, 7, avoid=[(kx, ky - 10, 280), (tx + 380, 300, 0)])
    hit = [(1452, 132, 40, 0.0, "1"), (1508, 470, 30, 1.1, "2"), (96, 520, 26, 1.9, "3")]
    hits = []
    for hx, hy, r, dl, n in hit:
        hits.append(
            f'<circle cx="{hx}" cy="{hy}" r="{r}" fill="{PINK}" fill-opacity="0.07" stroke="{INK}" stroke-opacity="0.22" stroke-width="4"/>'
            + text(SANS_SEMI, n, r * 0.9, hx, hy + r * 0.32, INK, 0.28, anchor="middle")
            + f'<circle cx="{hx}" cy="{hy}" r="{r * 1.47:.1f}" fill="none" stroke="{PINK}" stroke-opacity="0.55" stroke-width="2.5" class="ap" style="animation-delay:{dl}s"/>')
    body = f'''<defs>
  <linearGradient id="bn-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{NIGHT_HI}"/><stop offset="1" stop-color="{NIGHT}"/></linearGradient>
  <radialGradient id="bn-a" cx="{kx}" cy="{ky - 20}" r="420" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{VIOL}" stop-opacity="0.45"/><stop offset="0.6" stop-color="{PINK}" stop-opacity="0.08"/><stop offset="1" stop-color="{PINK}" stop-opacity="0"/></radialGradient>
  <radialGradient id="bn-b" cx="1240" cy="40" r="520" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{PINK}" stop-opacity="0.20"/><stop offset="1" stop-color="{PINK}" stop-opacity="0"/></radialGradient>
  <radialGradient id="bn-c" cx="1120" cy="640" r="460" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{DEEP}" stop-opacity="0.30"/><stop offset="1" stop-color="{DEEP}" stop-opacity="0"/></radialGradient>
  <linearGradient id="bn-rule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{PINK}"/><stop offset="1" stop-color="{VIOL}" stop-opacity="0"/></linearGradient>
  <clipPath id="bn-clip"><rect width="{W}" height="{H}" rx="28"/></clipPath>
</defs>
<g clip-path="url(#bn-clip)">
  <rect width="{W}" height="{H}" fill="url(#bn-bg)"/>
  <rect width="{W}" height="{H}" fill="url(#bn-c)"/>
  <rect width="{W}" height="{H}" fill="url(#bn-b)"/>
  <rect width="{W}" height="{H}" fill="url(#bn-a)"/>
  <g>{stars}</g>
  {"".join(hits)}
  {sparkle(176, 118, 16, GOLD, 0.95, "spk", 0.0)}
  {sparkle(640, 96, 11, INK, 0.85, "spk", 1.2)}
  {sparkle(620, 516, 13, PINK, 0.9, "spk", 2.1)}
  {sparkle(1300, 404, 9, LILAC, 0.8, "spk", 0.6)}
  {sparkle(1390, 548, 12, GOLD, 0.8, "spk", 2.8)}
  {place_kitsune("bn", kx, ky, ks, sway=True)}
  <g transform="translate({tx} {wm_y}) scale({wm_s}) translate(0 {-WORD_TOP})">{wm}</g>
  <rect x="{tx + 2}" y="{wm_y + (WORD_BOTTOM - WORD_TOP) * wm_s + 6:.0f}" width="320" height="3" rx="1.5" fill="url(#bn-rule)"/>
  {text(SANS, tag1, 36, tx, 396, INK, 0.86)}
  {text(SANS, tag2, 36, tx, 442, INK, 0.86)}
  {"".join(chips)}
  <rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="27" fill="none" stroke="{INK}" stroke-opacity="0.08" stroke-width="2"/>
</g>'''
    return svg_doc(W, H, "shiruviaa",
                   "The shiruviaa kitsune beside the shiruviaa wordmark and the line: osu! tooling, engineered for performance and power users.",
                   body, ANIM_CSS)


@dataclass
class Project:
    slug: str
    kicker: str
    lines: tuple[str, str]
    chips: tuple[str, ...]
    icon: str  # inline SVG body in a 1024 space
    accent: str


def card(p: Project) -> str:
    W, H = 800, 360
    wm, wm_w = wordmark(p.slug, dot_colors=(p.accent,))
    s = 0.56
    chips = []
    cx = 48
    for label in p.chips:
        svg, w = pill(cx, 290, label, size=17)
        chips.append(svg)
        cx += w + 10
    uid = p.slug
    body = f'''<defs>
  <linearGradient id="{uid}-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{NIGHT_HI}"/><stop offset="1" stop-color="{NIGHT}"/></linearGradient>
  <radialGradient id="{uid}-glow" cx="760" cy="0" r="420" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{p.accent}" stop-opacity="0.30"/><stop offset="1" stop-color="{p.accent}" stop-opacity="0"/></radialGradient>
  <linearGradient id="{uid}-edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PINK}" stop-opacity="0.55"/><stop offset="0.5" stop-color="{INK}" stop-opacity="0.06"/><stop offset="1" stop-color="{VIOL}" stop-opacity="0.45"/></linearGradient>
  <clipPath id="{uid}-clip"><rect width="{W}" height="{H}" rx="26"/></clipPath>
  <clipPath id="{uid}-icon"><rect width="1024" height="1024" rx="200"/></clipPath>
</defs>
<g clip-path="url(#{uid}-clip)">
  <rect width="{W}" height="{H}" fill="url(#{uid}-bg)"/>
  <rect width="{W}" height="{H}" fill="url(#{uid}-glow)"/>
  {starfield(W, H, 26, zlib.crc32(p.slug.encode()), avoid=[(400, 200, 0)])}
  {sparkle(648, 70, 10, GOLD, 0.9, "spk", 0.4)}
  {sparkle(616, 116, 6, INK, 0.7, "spk", 1.6)}
</g>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="25" fill="none" stroke="url(#{uid}-edge)" stroke-width="2"/>
<g transform="translate(48 44) scale({96 / 1024})" clip-path="url(#{uid}-icon)">{p.icon}</g>
<g transform="translate(168 {44 + 48 - (WORD_TOP + 155) / 2 * s - 2:.1f}) scale({s})">{wm}</g>
{text(MONO, p.kicker, 17, 48, 196, p.accent, 0.95, tracking=0.06)}
{text(SANS, p.lines[0], 25, 48, 236, INK, 0.82)}
{text(SANS, p.lines[1], 25, 48, 270, INK, 0.82)}
{"".join(chips)}
<g transform="translate(724 44)" fill="none" stroke="{INK}" stroke-opacity="0.75" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="14" cy="14" r="24" stroke-opacity="0.18"/>
  <path d="M6 22 L22 6 M10 6 H22 V18"/>
</g>'''
    return svg_doc(W, H, p.slug, f"{p.slug}: {p.kicker}. {p.lines[0]} {p.lines[1]}", body, ANIM_CSS)


def pillars() -> str:
    W, H = 1600, 300
    cols = [
        ("native & measured", "Rust all the way down.", "Hot paths measured, not guessed.", "bolt"),
        ("linux first-class", "Wayland, X11 and Wine as home turf.", "Windows, too.", "term"),
        ("built for power users", "Local HTTP + WebSocket APIs,", "profiles, and every knob in reach.", "knobs"),
    ]
    gap = 24
    cw = (W - gap * 2) / 3
    parts = []
    for i, (title, l1, l2, icon) in enumerate(cols):
        x = i * (cw + gap)
        accent = (PINK, VIOL, GOLD)[i]
        ix, iy = x + 44, 52
        if icon == "bolt":
            ico = (f'<path d="M{ix + 36} {iy} L{ix + 8} {iy + 34} H{ix + 30} L{ix + 24} {iy + 60} L{ix + 54} {iy + 24} H{ix + 32} Z" '
                   f'fill="{accent}" fill-opacity="0.18" stroke="{accent}" stroke-width="5" stroke-linejoin="round"/>')
        elif icon == "term":
            ico = (f'<rect x="{ix}" y="{iy + 4}" width="62" height="50" rx="10" fill="none" stroke="{accent}" stroke-width="5"/>'
                   f'<path d="M{ix + 14} {iy + 20} L{ix + 24} {iy + 29} L{ix + 14} {iy + 38} M{ix + 32} {iy + 40} H{ix + 46}" '
                   f'fill="none" stroke="{accent}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
        else:
            ico = "".join(
                f'<path d="M{ix} {iy + 10 + k * 20} H{ix + 62}" stroke="{accent}" stroke-opacity="0.45" stroke-width="5" stroke-linecap="round"/>'
                f'<circle cx="{ix + kx}" cy="{iy + 10 + k * 20}" r="8" fill="{NIGHT}" stroke="{accent}" stroke-width="5"/>'
                for k, kx in enumerate((42, 16, 34)))
        parts.append(f'''<g>
  <rect x="{x + 1:.1f}" y="1" width="{cw - 2:.1f}" height="{H - 2}" rx="24" fill="url(#pl-bg)" stroke="{INK}" stroke-opacity="0.08" stroke-width="2"/>
  <rect x="{x + 1:.1f}" y="1" width="{cw - 2:.1f}" height="{H - 2}" rx="24" fill="url(#pl-g{i})"/>
  {ico}
  {text(SANS_SEMI, title, 36, x + 44, 176, INK)}
  {text(SANS, l1, 26, x + 44, 220, INK, 0.7)}
  {text(SANS, l2, 26, x + 44, 254, INK, 0.7)}
</g>''')
    glows = "".join(
        f'<radialGradient id="pl-g{i}" cx="{i * (cw + gap) + cw - 40:.0f}" cy="0" r="300" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c}" stop-opacity="0.16"/><stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>'
        for i, c in enumerate((PINK, VIOL, GOLD)))
    body = f'''<defs>
  <linearGradient id="pl-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{NIGHT_HI}"/><stop offset="1" stop-color="{NIGHT}"/></linearGradient>
  {glows}
</defs>
{"".join(parts)}'''
    return svg_doc(W, H, "What we care about",
                   "Native and measured: Rust all the way down, hot paths benchmarked. Linux first-class: Wayland, X11 and Wine, Windows too. Built for power users: local HTTP and WebSocket APIs, profiles, and every knob in reach.",
                   body)


def docs_card() -> str:
    W, H = 1600, 240
    ix, iy = 56, 64  # book icon origin, 112 x 112 box
    tx = 210
    # (label, text colour, border colour): vosu pages pink, the tutorial gold, vosulay violet
    chip_rows = ((("vosu guide", PINK, PINK), ("vosu API", PINK, PINK)),
                 (("build an overlay", GOLD, GOLD), ("vosulay docs", LILAC, VIOL)))
    chip_size, chip_gap, row_gap = 19, 12, 16
    pad = chip_size * 0.8
    chip_h = chip_size * 1.9
    gy = (H - (chip_h * 2 + row_gap)) / 2 + 14
    chips = []
    gx = W
    for r, row in enumerate(chip_rows):
        widths = [text_width(MONO, label, chip_size) + pad * 2 for label, _, _ in row]
        cx = W - 64 - (sum(widths) + chip_gap * (len(row) - 1))
        gx = min(gx, cx)
        for (label, color, border), w in zip(row, widths):
            svg, _ = pill(cx, gy + r * (chip_h + row_gap), label, size=chip_size, color=color, border=border)
            chips.append(svg)
            cx += w + chip_gap
    book = (f'<path d="M{ix + 56} {iy + 26} C{ix + 40} {iy + 14} {ix + 20} {iy + 12} {ix + 6} {iy + 16} V{iy + 92} '
            f'C{ix + 20} {iy + 88} {ix + 40} {iy + 90} {ix + 56} {iy + 102} Z" fill="{PINK}" fill-opacity="0.16" '
            f'stroke="{PINK}" stroke-width="5" stroke-linejoin="round"/>'
            f'<path d="M{ix + 56} {iy + 26} C{ix + 72} {iy + 14} {ix + 92} {iy + 12} {ix + 106} {iy + 16} V{iy + 92} '
            f'C{ix + 92} {iy + 88} {ix + 72} {iy + 90} {ix + 56} {iy + 102} Z" fill="{VIOL}" fill-opacity="0.16" '
            f'stroke="{VIOL}" stroke-width="5" stroke-linejoin="round"/>'
            f'<path d="M{ix + 20} {iy + 38} C{ix + 30} {iy + 36} {ix + 40} {iy + 38} {ix + 46} {iy + 42} '
            f'M{ix + 20} {iy + 56} C{ix + 30} {iy + 54} {ix + 40} {iy + 56} {ix + 46} {iy + 60} '
            f'M{ix + 92} {iy + 38} C{ix + 82} {iy + 36} {ix + 72} {iy + 38} {ix + 66} {iy + 42}" '
            f'fill="none" stroke="{INK}" stroke-opacity="0.55" stroke-width="4" stroke-linecap="round"/>')
    body = f'''<defs>
  <linearGradient id="dc-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{NIGHT_HI}"/><stop offset="1" stop-color="{NIGHT}"/></linearGradient>
  <radialGradient id="dc-a" cx="{ix + 56}" cy="{iy + 56}" r="420" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{PINK}" stop-opacity="0.22"/><stop offset="1" stop-color="{PINK}" stop-opacity="0"/></radialGradient>
  <radialGradient id="dc-b" cx="{W - 160}" cy="0" r="520" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{VIOL}" stop-opacity="0.26"/><stop offset="1" stop-color="{VIOL}" stop-opacity="0"/></radialGradient>
  <linearGradient id="dc-edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PINK}" stop-opacity="0.55"/><stop offset="0.5" stop-color="{INK}" stop-opacity="0.06"/><stop offset="1" stop-color="{VIOL}" stop-opacity="0.45"/></linearGradient>
  <linearGradient id="dc-rule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{PINK}"/><stop offset="1" stop-color="{VIOL}" stop-opacity="0"/></linearGradient>
  <clipPath id="dc-clip"><rect width="{W}" height="{H}" rx="26"/></clipPath>
</defs>
<g clip-path="url(#dc-clip)">
  <rect width="{W}" height="{H}" fill="url(#dc-bg)"/>
  <rect width="{W}" height="{H}" fill="url(#dc-b)"/>
  <rect width="{W}" height="{H}" fill="url(#dc-a)"/>
  {starfield(W, H, 40, 715, avoid=[(ix + 56, iy + 56, 90), (tx + 380, 120, 0)])}
  {sparkle(gx - 70, 62, 11, GOLD, 0.9, "spk", 0.3)}
  {sparkle(gx - 40, 196, 7, INK, 0.75, "spk", 1.5)}
</g>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="25" fill="none" stroke="url(#dc-edge)" stroke-width="2"/>
{book}
{text(MONO, "documentation", 19, tx, 82, PINK, 0.95, tracking=0.08)}
{text(SANS_SEMI, "shiruviaa.github.io", 46, tx, 136, INK)}
<rect x="{tx + 2}" y="150" width="260" height="3" rx="1.5" fill="url(#dc-rule)"/>
{text(SANS, "Guides, the API reference, and a step-by-step overlay tutorial.", 25, tx, 192, INK, 0.78)}
{"".join(chips)}'''
    return svg_doc(W, H, "shiruviaa documentation",
                   "shiruviaa.github.io: guides, the API reference, and a step-by-step overlay tutorial. Sections: vosu guide, vosu API, build an overlay, vosulay docs.",
                   body, ANIM_CSS)


def fetch_icon(path: Path) -> str:
    """Inner markup of a product's 1024x1024 app icon SVG."""
    src = path.read_text()
    start = src.index(">", src.index("<svg")) + 1
    end = src.rindex("</svg>")
    inner = src[start:end]
    # drop title/desc: the card carries its own accessible text
    inner = re.sub(r"<title[^>]*>.*?</title>|<desc[^>]*>.*?</desc>", "", inner, flags=re.S)
    return inner.strip()


def render(name: str, svg: str, width: int | None = None) -> None:
    svg_path = OUT / f"{name}.svg"
    svg_path.write_text(svg)
    # resvg renders the static frame; it skips @keyframes/@media by design
    cmd = ["resvg", "--quiet", str(svg_path), str(OUT / f"{name}.png")]
    if width:
        cmd += ["-w", str(width)]
    subprocess.run(cmd, check=True)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    icons = ROOT / "tools" / "product-icons"
    projects = [
        Project("vosu", "osu! telemetry daemon",
                ("Live osu! state, counters, and tosu-compatible APIs", "from one native daemon. No Node, no Electron."),
                ("rust", "stable + lazer", "linux", "windows"),
                fetch_icon(icons / "vosu-app-icon.svg"), PINK),
        Project("vosulay", "in-game overlay manager",
                ("Your counters, rendered inside osu! itself:", "Vulkan, OpenGL, Wayland, X11 and Windows."),
                ("rust", "cef", "linux", "windows"),
                fetch_icon(icons / "vosulay-app-icon.svg"), VIOL),
    ]
    render("shiruviaa-avatar", avatar())
    render("shiruviaa-mark", mark())
    render("shiruviaa-banner", banner())
    render("pillars", pillars())
    render("card-docs", docs_card(), width=1600)
    for p in projects:
        render(f"card-{p.slug}", card(p), width=1600)


if __name__ == "__main__":
    main()
