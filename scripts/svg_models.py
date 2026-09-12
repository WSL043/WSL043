"""Deterministic full-calendar models. Coordinates are weeks x weekdays.

This module only plans movement. No browser code, image library, network access,
or mutation of contribution data. Cosmetic timings are applied by svg_arcade.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from datetime import date
import random

Point = tuple[int, int]
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
SCENES = ('bomber', 'miners', 'link-match', 'portal', 'assembly')


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


def inside(p: Point, cols: int) -> bool:
    # The perimeter is a game aisle, never an extra contribution date.
    return -1 <= p[0] <= cols and -1 <= p[1] <= 7


def flood(start: Point, grid: dict, cols: int) -> dict:
    parent = {start: None}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRS:
            q = x + dx, y + dy
            if inside(q, cols) and q not in parent and not grid.get(q, 0):
                parent[q] = (x, y)
                queue.append(q)
    return parent


def path(parent: dict, end: Point) -> list[Point]:
    result = [end]
    while parent[result[-1]] is not None:
        result.append(parent[result[-1]])
    return result[::-1]


def blast(center: Point, grid: dict, cols: int, radius: int = 3) -> tuple[list, list]:
    area, hits = [center], []
    for dx, dy in DIRS:
        for distance in range(1, radius + 1):
            q = center[0] + dx * distance, center[1] + dy * distance
            if not inside(q, cols):
                break
            area.append(q)
            if grid.get(q, 0):
                hits.append(q)
                break  # Walls shield everything behind them, even on their last hit.
    return area, hits


def bomber(cal: Calendar, seed: int) -> dict:
    rng = random.Random(seed)
    grid = cal.grid.copy()
    x0 = min((p[0] for p in cal.active), default=1) - 1
    pos = (max(-1, x0), -1)
    start = pos
    events = []
    while any(grid.values()):
        reachable = flood(pos, grid, cal.cols)
        candidates = []
        for p in reachable:
            area, hits = blast(p, grid, cal.cols)
            if not hits:
                continue
            route = path(reachable, p)
            score = (sum(1 + 2 * (grid[h] == 1) for h in hits) /
                     (1 + .17 * (len(route) - 1)) + rng.random() * .18)
            candidates.append((score, p, route, area, hits))
        for _, p, route, area, hits in sorted(candidates, reverse=True):
            escape = flood(p, grid, cal.cols)
            safe = [q for q in escape if q not in area]
            if safe:
                retreat = min((path(escape, q) for q in safe), key=len)
                break
        else:
            raise RuntimeError('No safely reachable bomb site; refusing a fake clear')
        events.append({'route': route, 'retreat': retreat, 'area': area, 'hits': hits,
                       'hp': [grid[q] for q in hits]})
        for q in hits:
            grid[q] -= 1
        pos = retreat[-1]
        if len(events) > sum(cal.grid.values()):
            raise RuntimeError('Bomber made no progress')
    return {'scene': 'bomber', 'start': start, 'events': events, 'final': grid}


def miners(cal: Calendar, seed: int) -> dict:
    rng = random.Random(seed)
    grid = cal.grid.copy()
    active = cal.active
    left = min((p[0] for p in active), default=0)
    right = max((p[0] for p in active), default=cal.cols - 1)
    positions = [(left, -1), (right, 7)]
    starts, waves = positions[:], []
    while any(grid.values()):
        wave, reserved = [], set()
        # Both routes in a wave are planned against the same pre-mining state.
        for bot in (0, 1):
            reach = flood(positions[bot], grid, cal.cols)
            candidates = []
            for stand in reach:
                route = path(reach, stand)
                for dx, dy in DIRS:
                    target = stand[0] + dx, stand[1] + dy
                    if grid.get(target, 0) and target not in reserved:
                        score = len(route) + grid[target] * .1 + rng.random() * .9
                        candidates.append((score, target, route))
            if not candidates:
                continue
            _, target, route = min(candidates)
            wave.append({'bot': bot, 'route': route, 'target': target, 'level': grid[target]})
            reserved.add(target)
            positions[bot] = route[-1]
        if not wave:
            raise RuntimeError('No accessible ore; refusing to walk through walls')
        for job in wave:
            grid[job['target']] = 0
        waves.append(wave)
    return {'scene': 'miners', 'starts': starts, 'waves': waves, 'final': grid}


def link_path(a: Point, b: Point, grid: dict, cols: int) -> list[Point] | None:
    """Connect equal occupied endpoints through empty cells with <=2 turns.

    Enumerate straight, L and Z/U routes. This bounded, auditable search is faster
    than exploring all direction states for each candidate pair on a full board.
    """
    if a == b or not grid.get(a) or grid.get(a) != grid.get(b):
        return None
    routes = [[a, (a[0], b[1]), b], [a, (b[0], a[1]), b]]
    routes += [[a, (x, a[1]), (x, b[1]), b] for x in range(-1, cols + 1)]
    routes += [[a, (a[0], y), (b[0], y), b] for y in range(-1, 8)]
    for corners in routes:
        route = [a]
        for p, q in zip(corners, corners[1:]):
            dx = (q[0] > p[0]) - (q[0] < p[0])
            dy = (q[1] > p[1]) - (q[1] < p[1])
            while p != q:
                p = p[0] + dx, p[1] + dy
                route.append(p)
        if (route[-1] == b and len(route) == len(set(route)) and
                all(inside(q, cols) and not grid.get(q, 0) for q in route[1:-1])):
            return route
    return None


def links(cal: Calendar, seed: int) -> dict:
    rng = random.Random(seed)
    grid, pairs = cal.grid.copy(), []
    while True:
        active = [p for p in cal.active if grid[p]]
        rng.shuffle(active)
        match = None
        for i, a in enumerate(active):
            # Nearby pairs keep the full-calendar animation readable.
            others = sorted(active[i + 1:], key=lambda b: abs(a[0]-b[0])+abs(a[1]-b[1]))
            for b in others:
                route = link_path(a, b, grid, cal.cols)
                if route:
                    match = {'a': a, 'b': b, 'route': route, 'level': grid[a]}
                    break
            if match:
                break
        if not match:
            break
        pairs.append(match)
        grid[match['a']] = grid[match['b']] = 0
    # Odd counts or blocked layouts can leave tiles. Never invent matching days.
    return {'scene': 'link-match', 'pairs': pairs, 'final': grid}


def portal(cal: Calendar, seed: int) -> dict:
    rng = random.Random(seed)
    order = cal.active[:]
    rng.shuffle(order)
    return {'scene': 'portal', 'order': order, 'levels': [cal.grid[p] for p in order]}


def assembly(cal: Calendar, seed: int) -> dict:
    rng = random.Random(seed)
    remaining, pieces = set(cal.active), []
    while remaining:
        piece = [rng.choice(sorted(remaining))]
        remaining.remove(piece[0])
        limit = rng.choice((3, 4, 4))
        while len(piece) < limit:
            choices = sorted({(p[0]+dx, p[1]+dy) for p in piece for dx, dy in DIRS} & remaining)
            if not choices:
                break
            q = rng.choice(choices)
            piece.append(q)
            remaining.remove(q)
        pieces.append(piece)
    rng.shuffle(pieces)
    return {'scene': 'assembly', 'pieces': pieces}


PLANNERS = {'bomber': bomber, 'miners': miners, 'link-match': links,
            'portal': portal, 'assembly': assembly}
