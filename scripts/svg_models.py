"""Deterministic full-calendar models. Coordinates are weeks x weekdays.

This module only plans movement. No browser code, image library, network access,
or mutation of contribution data. Cosmetic timings are applied by svg_arcade.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import math
import random

Point = tuple[int, int]
SCENES = ('fireworks', 'domino', 'dust', 'sorter', 'synth', 'claw', 'minecraft', 'lego')


@dataclass
class Calendar:
    cols: int
    grid: dict[Point, int]
    missing: set[Point]
    weeks: list[str]
    owner: str
    day: str

    @classmethod
    def from_snapshot(cls, data: dict) -> 'Calendar':
        cols = data.get('columns')
        if type(cols) is not int or not 52 <= cols <= 54 or data.get('rows') != 7:
            raise ValueError('Expected 52-54 weeks and 7 weekdays')
        grid = {(x, y): 0 for x in range(cols) for y in range(7)}
        missing = set()
        for key, levels in data.get('active_columns', {}).items():
            x = int(key)
            if not 0 <= x < cols or len(levels) != 7:
                raise ValueError('Invalid calendar column')
            for y, value in enumerate(levels):
                if value is None:
                    missing.add((x, y))
                elif type(value) is not int or not 0 <= value <= 4:
                    raise ValueError('Level must be 0-4 or null')
                else:
                    grid[x, y] = value
        weeks = data.get('week_starts', [])
        if weeks and len(weeks) != cols:
            raise ValueError('Week labels do not match the grid')
        for value in weeks:
            date.fromisoformat(value)
        return cls(cols, grid, missing, weeks, str(data.get('owner', '')),
                   str(data.get('as_of', 'saved snapshot')))

    @property
    def active(self) -> list[Point]:
        return sorted(p for p, level in self.grid.items() if level)


def minecraft(cal: Calendar, seed: int) -> dict:
    # Sweep real active days in alternating rows; no invented ore or terrain.
    rows = list(range(7))
    random.Random(seed).shuffle(rows)
    order = [p for y in rows for p in sorted((p for p in cal.active if p[1] == y),
             reverse=bool(y % 2))]
    return {'scene': 'minecraft', 'order': order, 'levels': [cal.grid[p] for p in order]}


def lego(cal: Calendar, seed: int) -> dict:
    # Each brick is a straight 1-4 stud run of identical contribution levels.
    rng = random.Random(seed)
    remaining, pieces = set(cal.active), []
    while remaining:
        first = min(remaining, key=lambda p: (p[1], p[0]))
        piece = [first]
        remaining.remove(first)
        for dx in range(1, rng.randint(1, 4)):
            p = first[0]+dx, first[1]
            if p not in remaining or cal.grid[p] != cal.grid[first]:
                break
            remaining.remove(p)
            piece.append(p)
        pieces.append(piece)
    rng.shuffle(pieces)
    return {'scene': 'lego', 'pieces': pieces}


def fireworks(cal: Calendar, seed: int) -> dict:
    # Rockets relight real active days in a shuffled order from five launch pads.
    rng = random.Random(seed)
    order = cal.active[:]
    rng.shuffle(order)
    pads = sorted(rng.sample(range(2, max(8, cal.cols - 2)), 5))
    return {'scene': 'fireworks', 'order': order, 'levels': [cal.grid[p] for p in order], 'pads': pads}


def domino(cal: Calendar, seed: int) -> dict:
    # A real domino run: every active day is a standing tile, and the chain topples across the calendar in
    # column order, left to right or right to left. Ties inside a column are shuffled by the seed.
    rng = random.Random(seed)
    direction = rng.choice((1, -1))
    jitter = {p: rng.random() for p in cal.active}
    order = sorted(cal.active, key=lambda p: (p[0] * direction, jitter[p]))
    return {'scene': 'domino', 'dir': direction, 'order': order, 'levels': [cal.grid[p] for p in order]}


def dust(cal: Calendar, seed: int) -> dict:
    # Left-to-right disintegration with per-tile drift; the same tiles re-form afterwards.
    rng = random.Random(seed)
    order = sorted(cal.active, key=lambda p: (p[0] + rng.random() * 6, p[1]))
    drift = [(rng.randint(18, 44), -rng.randint(8, 34), rng.choice((-1, 1)) * rng.randint(60, 200)) for _ in order]
    return {'scene': 'dust', 'order': order, 'drift': drift, 'levels': [cal.grid[p] for p in order]}


def sorter(cal: Calendar, seed: int) -> dict:
    # Each active day flies into the bin of its own level; bin counts are the real level histogram.
    rng = random.Random(seed)
    order = cal.active[:]
    rng.shuffle(order)
    counts, slots = [0, 0, 0, 0], []
    for p in order:
        level = cal.grid[p] - 1
        slots.append((level, counts[level]))
        counts[level] += 1
    return {'scene': 'sorter', 'order': order, 'slots': slots, 'counts': counts}


def synth(cal: Calendar, seed: int) -> dict:
    # A playhead sweeps the whole calendar three times at different tempos and directions.
    rng = random.Random(seed)
    direction = rng.choice((1, -1))
    passes = []
    for tempo in rng.sample((0.12, 0.16, 0.2, 0.24), 3):
        passes.append({'dir': direction, 'tempo': tempo})
        direction = -direction
    return {'scene': 'synth', 'passes': passes}


def claw(cal: Calendar, seed: int) -> dict:
    # Nearest-neighbour route over tiles that are the top of their column, so the claw never passes through one.
    rng = random.Random(seed)
    remaining = set(cal.active)
    order, current = [], None
    while remaining:
        free = sorted(p for p in remaining if not any((p[0], y) in remaining for y in range(p[1])))
        if current is None:
            nxt = rng.choice(free)
        else:
            nxt = min(free, key=lambda p: (abs(p[0] - current[0]) + .5 * abs(p[1] - current[1]), p))
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return {'scene': 'claw', 'order': order, 'levels': [cal.grid[p] for p in order]}


PLANNERS = {'minecraft': minecraft, 'lego': lego,
            'fireworks': fireworks, 'domino': domino, 'dust': dust, 'sorter': sorter, 'synth': synth, 'claw': claw}
