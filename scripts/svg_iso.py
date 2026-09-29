"""Isometric (2.5D) helpers: projection, district layout and shaded cube geometry.

Pure functions only. The year is folded into four 'districts' (quarters) laid out as city blocks
separated by streets, so the picture is a compact diamond instead of a 53-week diagonal.
Every cell keeps its calendar identity (week, weekday); only its position on the plate changes.
"""
from __future__ import annotations
import math

U = 12.5
DX, DY = U*math.cos(math.radians(30)), U*.5
GAP = 2
ROWS = 7
CANVAS_H = 360
SLAB = 9
UNIT_FACE = 'M0 0H1V-1H0z'


def num(value):
    return f'{value:.3f}'.rstrip('0').rstrip('.') or '0'


def quarter_sizes(cols):
    return [cols//4+(1 if i < cols % 4 else 0) for i in range(4)]


def dims(cols):
    block = max(quarter_sizes(cols))
    return 2*block+GAP, 2*ROWS+GAP, block


def layout(cols):
    """Map every (week, weekday) to a (gx, gy) plot on the plate; quarters snake through 2 x 2 blocks."""
    _, _, block = dims(cols)
    cells, week = {}, 0
    for q, size in enumerate(quarter_sizes(cols)):
        qx, qy = q % 2, q//2
        for c in range(size):
            for r in range(ROWS):
                cells[week+c, r] = (qx*(block+GAP)+c, qy*(ROWS+GAP)+r)
        week += size
    return cells


class Iso:
    def __init__(self, cols, width):
        self.gx, self.gy, self.block = dims(cols)
        self.ox = width/2-(self.gx-self.gy)*DX/2
        self.oy = 58

    def p(self, gx, gy, z=0):
        return self.ox+(gx-gy)*DX, self.oy+(gx+gy)*DY-z

    def rel(self, gx, gy, z, cx, cy):
        a, b = self.p(gx, gy, z), self.p(cx, cy, 0)
        return a[0]-b[0], a[1]-b[1]

    def poly(self, points, close=True):
        return 'M'+'L'.join(f'{num(x)} {num(y)}' for x, y in points)+('z' if close else '')

    def diamond(self, x0, y0, x1, y1, z=0):
        return self.poly([self.p(x0, y0, z), self.p(x1, y0, z), self.p(x1, y1, z), self.p(x0, y1, z)])

    def top_local(self, cx, cy, hx, hy):
        """Top face relative to the footprint centre at z=0; place it with translate(centre.x, centre.y - height)."""
        return self.poly([self.rel(cx+sx*hx, cy+sy*hy, 0, cx, cy) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])

    def left_xf(self, cx, cy, hx, hy, k):
        x, y = self.p(cx-hx, cy+hy)
        return f'translate({num(x)}px,{num(y)}px) skewY(30deg) scale({num(2*hx*DX)},{num(k)})'

    def right_xf(self, cx, cy, hx, hy, k):
        x, y = self.p(cx+hx, cy+hy)
        return f'translate({num(x)}px,{num(y)}px) skewY(-30deg) scale({num(2*hy*DX)},{num(k)})'

    def top_xf(self, cx, cy, height):
        x, y = self.p(cx, cy)
        return f'translate({num(x)}px,{num(y-height)}px) rotate(0deg) scale(1)'


def mix(colour, other, amount):
    a = [int(colour[i:i+2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i+2], 16) for i in (1, 3, 5)]
    return '#'+''.join(f'{round(x+(y-x)*amount):02x}' for x, y in zip(a, b))


def shades(colour):
    """(top, left, right) for a light source at the upper left."""
    return mix(colour, '#ffffff', .3), colour, mix(colour, '#000000', .34)


def streak_and_week(levels):
    """Longest run of consecutive active days and the busiest week, from the real calendar levels."""
    best = run = 0
    for level in levels:
        run = run+1 if level else 0
        best = max(best, run)
    return best
