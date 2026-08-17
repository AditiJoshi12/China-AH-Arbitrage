"""
Equity curve SVG for the README.

Three series:
  * Gross (before costs, full-sample-selected book)
  * Net after 100/60 bps round-trip (the same book)
  * Net after 100/60 bps, PIT-selected book, OOS window only

One y-axis (cumulative return). IS/OOS divider is a vertical hairline. Colors
and text ink come from the dataviz reference palette (slots 1-3, light/dark
values pre-validated all-pairs in both modes).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from engine import IS_END, net_returns                                       # noqa: E402

BASE = (100, 60)

# palette (light | dark) — from dataviz reference, slots 1..3
COLORS = {
    "gross":     ("#2a78d6", "#3987e5"),
    "net":       ("#eb6834", "#d95926"),
    "pit":       ("#1baf7a", "#199e70"),
}
INK = {
    "surface":   ("#fcfcfb", "#1a1a19"),
    "primary":   ("#0b0b0b", "#ffffff"),
    "secondary": ("#52514e", "#c3c2b7"),
    "muted":     ("#898781", "#898781"),
    "grid":      ("#e1e0d9", "#2c2c2a"),
    "axis":      ("#c3c2b7", "#383835"),
}


def load():
    book = pd.read_csv(os.path.join(ROOT, "results", "book_daily.csv"),
                       index_col=0, parse_dates=True)
    pit  = pd.read_csv(os.path.join(ROOT, "results", "pit_book_daily.csv"),
                       index_col=0, parse_dates=True)
    return book, pit


def cum(r):
    return (1 + r.fillna(0)).cumprod()


def path_d(xs, ys):
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in zip(xs, ys))


def render():
    book, pit = load()
    gross = cum(book["gross_ret"])
    net   = cum(net_returns(book, *BASE))
    pit_c = cum(net_returns(pit, *BASE))

    W, H = 880, 380
    ML, MR, MT, MB = 56, 130, 24, 40
    pw, ph = W - ML - MR, H - MT - MB

    all_x = book.index
    x0, x1 = all_x.min().value, all_x.max().value

    ymin = min(gross.min(), net.min(), pit_c.min(), 0.85)
    ymax = max(gross.max(), net.max(), pit_c.max(), 1.15)
    # pad
    pad = (ymax - ymin) * 0.05
    ymin, ymax = ymin - pad, ymax + pad

    def sx(ts): return ML + (ts.value - x0) / (x1 - x0) * pw
    def sy(v):  return MT + (1 - (v - ymin) / (ymax - ymin)) * ph

    def series_path(s):
        xs = [sx(t) for t in s.index]
        ys = [sy(v) for v in s.values]
        return path_d(xs, ys)

    is_end_x = sx(pd.Timestamp(IS_END))

    # y ticks, unit-return axis
    yticks = []
    step = 0.05
    lo = np.floor(ymin / step) * step
    hi = np.ceil(ymax / step) * step
    v = lo
    while v <= hi + 1e-9:
        if ymin <= v <= ymax:
            yticks.append(round(v, 2))
        v += step

    # x ticks -> Jan of each year
    years = sorted(set(all_x.year))
    xticks = []
    for y in years:
        ts = pd.Timestamp(year=y, month=1, day=1)
        if all_x.min() <= ts <= all_x.max():
            xticks.append((ts, str(y)))

    def render_mode(mode):
        i = 0 if mode == "light" else 1
        surface = INK["surface"][i]
        primary = INK["primary"][i]
        secondary = INK["secondary"][i]
        muted = INK["muted"][i]
        grid = INK["grid"][i]
        axis = INK["axis"][i]

        parts = []
        parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{surface}"/>')

        # gridlines + y labels
        for t in yticks:
            y = sy(t)
            parts.append(f'<line x1="{ML}" y1="{y:.2f}" x2="{ML+pw}" y2="{y:.2f}" '
                         f'stroke="{grid}" stroke-width="1"/>')
            parts.append(f'<text x="{ML-8}" y="{y+3.5:.2f}" text-anchor="end" '
                         f'fill="{secondary}" font-size="11" '
                         f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
                         f'font-variant-numeric="tabular-nums">'
                         f'{t*100:+.0f}%</text>')

        # baseline at 0% return (value = 1)
        y0 = sy(1.0)
        parts.append(f'<line x1="{ML}" y1="{y0:.2f}" x2="{ML+pw}" y2="{y0:.2f}" '
                     f'stroke="{axis}" stroke-width="1"/>')

        # x ticks
        for ts, lbl in xticks:
            x = sx(ts)
            parts.append(f'<line x1="{x:.2f}" y1="{MT+ph}" x2="{x:.2f}" y2="{MT+ph+4}" '
                         f'stroke="{axis}" stroke-width="1"/>')
            parts.append(f'<text x="{x:.2f}" y="{MT+ph+18}" text-anchor="middle" '
                         f'fill="{secondary}" font-size="11" '
                         f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" '
                         f'font-variant-numeric="tabular-nums">{lbl}</text>')

        # axis / baseline
        parts.append(f'<line x1="{ML}" y1="{MT}" x2="{ML}" y2="{MT+ph}" '
                     f'stroke="{axis}" stroke-width="1"/>')
        parts.append(f'<line x1="{ML}" y1="{MT+ph}" x2="{ML+pw}" y2="{MT+ph}" '
                     f'stroke="{axis}" stroke-width="1"/>')

        # IS/OOS divider
        parts.append(f'<line x1="{is_end_x:.2f}" y1="{MT}" x2="{is_end_x:.2f}" '
                     f'y2="{MT+ph}" stroke="{muted}" stroke-width="1" '
                     f'stroke-dasharray="4 4"/>')
        parts.append(f'<text x="{is_end_x-6:.2f}" y="{MT+12}" text-anchor="end" '
                     f'fill="{muted}" font-size="10" '
                     f'font-family="system-ui,-apple-system,Segoe UI,sans-serif">'
                     f'in-sample</text>')
        parts.append(f'<text x="{is_end_x+6:.2f}" y="{MT+12}" text-anchor="start" '
                     f'fill="{muted}" font-size="10" '
                     f'font-family="system-ui,-apple-system,Segoe UI,sans-serif">'
                     f'out-of-sample</text>')

        # series
        c_g, c_n, c_p = (COLORS["gross"][i], COLORS["net"][i], COLORS["pit"][i])
        parts.append(f'<path d="{series_path(gross)}" fill="none" stroke="{c_g}" '
                     f'stroke-width="2" stroke-linejoin="round"/>')
        parts.append(f'<path d="{series_path(net)}" fill="none" stroke="{c_n}" '
                     f'stroke-width="2" stroke-linejoin="round"/>')
        parts.append(f'<path d="{series_path(pit_c)}" fill="none" stroke="{c_p}" '
                     f'stroke-width="2" stroke-linejoin="round"/>')

        # rounded end caps (data-end anchors)
        def end_cap(s, color):
            x, y = sx(s.index[-1]), sy(s.values[-1])
            return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{color}" '
                    f'stroke="{surface}" stroke-width="2"/>')
        parts.append(end_cap(gross, c_g))
        parts.append(end_cap(net, c_n))
        parts.append(end_cap(pit_c, c_p))

        # direct labels beside each end (legend + label together, off-plot)
        end_x = ML + pw + 8
        labels = [
            (gross, c_g, "gross"),
            (net, c_n, "net (100/60 bps)"),
            (pit_c, c_p, "net, PIT-selected"),
        ]
        # anti-collision: stack labels with 14px min gap in y
        pts = [(sy(s.values[-1]), col, txt, s.values[-1]) for s, col, txt in labels]
        pts.sort()
        min_gap = 16
        for j in range(1, len(pts)):
            if pts[j][0] - pts[j - 1][0] < min_gap:
                pts[j] = (pts[j - 1][0] + min_gap, *pts[j][1:])
        for y, col, txt, v in pts:
            parts.append(f'<text x="{end_x}" y="{y+3.5:.2f}" fill="{primary}" '
                         f'font-size="11" '
                         f'font-family="system-ui,-apple-system,Segoe UI,sans-serif">'
                         f'<tspan fill="{col}" font-weight="600">■ </tspan>'
                         f'{txt} <tspan fill="{secondary}" '
                         f'font-variant-numeric="tabular-nums">'
                         f'{(v-1)*100:+.1f}%</tspan></text>')

        return "\n".join(parts)

    light = render_mode("light")
    dark = render_mode("dark")

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="Equity curves: gross, net after 100/60 bps costs, and PIT-selected out-of-sample book">
  <title>China A/H equity curves — gross, net (100/60 bps), PIT-selected OOS</title>
  <style>
    .theme-dark {{ display: none; }}
    @media (prefers-color-scheme: dark) {{
      .theme-light {{ display: none; }}
      .theme-dark  {{ display: inline; }}
    }}
  </style>
  <g class="theme-light">{light}</g>
  <g class="theme-dark">{dark}</g>
</svg>
'''

    out = os.path.join(ROOT, "results", "equity_curve.svg")
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out}")


if __name__ == "__main__":
    render()
