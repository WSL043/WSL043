"""Three additional heatmap mechanisms: collision, reflection and falling sand."""
from __future__ import annotations
import math
import random
from scripts import heatmap_arcade as a


def plan_pinball(initial, seed):
    rng = random.Random(seed)
    grid = initial.copy()
    xs = [p[0] for p, hp in grid.items() if hp]
    left, right = max(-1, min(xs, default=0)-3), min(a.COLS, max(xs, default=a.COLS-1)+3)
    balls = [{'p': [left+1+i*.45, -.82], 'v': [rng.uniform(7, 10), rng.uniform(5, 8)]}
             for i in range(3)]
    events, states = [], []
    radius = .54  # Minkowski sum: a .37-half-width tile plus a .17-radius ball.
    for f in range(round(a.DURATION*a.FPS)):
        t = f/a.FPS
        if 1.8 <= t < 16.4:
            for _ in range(4):  # Bounded substeps prevent tunnelling through tiles.
                for i, b in enumerate(balls):
                    for axis, lo, hi in [(0, left-.3, right+.3), (1, -.85, 6.85)]:
                        b['p'][axis] += b['v'][axis]/(4*a.FPS)
                        if b['p'][axis] < lo or b['p'][axis] > hi:
                            b['p'][axis] = max(lo, min(hi, b['p'][axis]))
                            b['v'][axis] *= -1
                        px, py = b['p']
                        candidates = [(x, y) for x in range(round(px)-1, round(px)+2)
                                      for y in range(round(py)-1, round(py)+2)]
                        for cell in candidates:
                            if grid.get(cell, 0) and all(abs(b['p'][k]-cell[k]) < radius for k in (0, 1)):
                                sign = 1 if b['v'][axis] > 0 else -1
                                b['p'][axis] = cell[axis]-sign*(radius+.005)
                                b['v'][axis] *= -1
                                grid[cell] -= 1
                                events.append({'t': t, 'p': cell, 'ball': i, 'hp': grid[cell]})
                                break
        states.append({'grid': grid.copy(), 'balls': [tuple(b['p']) for b in balls]})
    return {'states': states, 'events': events, 'final': grid, 'bounds': (left, right)}


def draw_pinball(model, initial, missing, t, focus):
    index = min(len(model['states'])-1, int(t*a.FPS))
    st = model['states'][index]
    img, d, v = a.base(initial, st['grid'], missing, 'pinball', t, focus)
    x1, y1 = v.xy((model['bounds'][0]-.5, -1.1))
    x2, y2 = v.xy((model['bounds'][1]+.5, 7.1))
    a.rect(d, (x1, y1, x2, y2), None, a.LINE, r=9)
    for i, p in enumerate(st['balls']):
        color = (a.CYAN, a.GOLD, a.RED)[i]
        trail = [v.xy(model['states'][max(0, index-j)]['balls'][i]) for j in range(7)]
        d.line(trail, fill=color, width=2)
        x, y = v.xy(p); r = v.pitch*.17
        d.ellipse((x-r, y-r, x+r, y+r), fill=color, outline=a.TEXT)
    for e in model['events']:
        a.burst(d, v, e['p'], t-e['t'], a.GOLD, e['p'][0]*7+e['p'][1])
    count = sum(initial[p] > 0 and st['grid'][p] == 0 for p in initial)
    a.rect(d, (0, 383, a.W, a.H), a.BG)
    a.text(d, (28, 389), 'THREE BALLS / REAL COLLISIONS / LEVEL = DURABILITY', style='label', fill=a.MUTED)
    a.text(d, (1012, 389), f'TILES CLEARED {count:02d}', style='hud', anchor='ra')
    return a.finish_frame(img)


def reflect(direction, slash):
    dx, dy = direction
    return (-dy, -dx) if slash else (dy, dx)


def plan_laser(initial, seed):
    rng = random.Random(seed)
    grid = initial.copy()
    mirrors = {p: (p[0]+p[1]+hp+seed) % 2 == 0 for p, hp in grid.items() if hp}
    events, pulses = [], []
    for n in range(16):
        active = [p for p, hp in grid.items() if hp]
        if not active:
            break
        cell = rng.choice(active)
        dx, dy = rng.choice(a.DIRS)
        start = ((-1 if dx > 0 else a.COLS), cell[1]) if dx else (cell[0], (-1 if dy > 0 else a.ROWS))
        p, direction, vertices = start, (dx, dy), [start]
        hits, travel, seen = [], 0, set()
        before = grid.copy()
        while travel < (a.COLS+2)*16 and len(hits) < 12:
            p = (p[0]+direction[0], p[1]+direction[1])
            travel += 1
            if not a.inside(p):
                break
            if grid.get(p, 0):
                # Each impact consumes a unit of actual source-level durability.
                grid[p] -= 1
                events.append({'t': 1.8+n*.88+len(hits)*.045, 'p': p, 'hp': grid[p]})
                hits.append(p)
                vertices.append(p)
                direction = reflect(direction, mirrors[p])
            if (p, direction, len(hits)) in seen:
                break
            seen.add((p, direction, len(hits)))
        if vertices[-1] != p:
            vertices.append(p)
        pulses.append({'t': 1.8+n*.88, 'vertices': vertices, 'hits': hits, 'grid_before': before})
    return {'events': events, 'pulses': pulses, 'mirrors': mirrors, 'final': grid}


def draw_laser(model, initial, missing, t, focus):
    grid = initial.copy()
    for e in model['events']:
        if e['t'] <= t:
            grid[e['p']] -= 1
    img, d, v = a.base(initial, grid, missing, 'laser', t, focus)
    for p, slash in model['mirrors'].items():
        if not grid[p]:
            continue
        x, y = v.xy(p); r = v.pitch*.23
        d.line((x-r, y+(r if slash else -r), x+r, y+(-r if slash else r)), fill='#b1ffde', width=2)
    for pulse in model['pulses']:
        age = t-pulse['t']
        if not 0 <= age < .74:
            continue
        # Extend the visible ray in the same order as the simulated impacts.
        pts = pulse['vertices']
        amount = min(len(pts)-1, max(0, age/.045+1))
        whole = min(len(pts)-1, int(amount))
        shown = list(pts[:whole+1])
        if whole < len(pts)-1:
            shown.append(tuple(a.lerp(pts[whole][k], pts[whole+1][k], amount-whole) for k in (0, 1)))
        if len(shown) >= 2:
            screen = [v.xy(p) for p in shown]
            d.line(screen, fill='#31776f' if age > .53 else '#45b5aa', width=7)
            d.line(screen, fill='#ddfff1' if age < .53 else '#79cfb3', width=2)
        a.robot(d, v, pts[0], t, a.CYAN)
    for e in model['events']:
        a.burst(d, v, e['p'], t-e['t'], a.CYAN, e['p'][0]*7+e['p'][1], .3)
    impacts = sum(e['t'] <= t for e in model['events'])
    a.rect(d, (0, 383, a.W, a.H), a.BG)
    a.text(d, (28, 389), 'GREEN CELLS REFLECT THE BEAM / EACH HIT DRAINS ONE LEVEL', style='label', fill=a.MUTED)
    a.text(d, (1012, 389), f'IMPACTS {impacts:03d}', style='hud', anchor='ra')
    return a.finish_frame(img)


def plan_gravity(initial, seed):
    """Integer falling-sand lattice; no overlapping or disappearing particles."""
    rng = random.Random(seed)
    active = sorted((p for p, hp in initial.items() if hp), key=lambda p: (-p[1], rng.random()))
    events = [{'t': 1.8+10.5*i/max(1, len(active)), 'p': p, 'level': initial[p],
               'grains': 4+3*initial[p]} for i, p in enumerate(active)]
    grid = initial.copy()
    sand, states, cursor = {}, [], 0
    for f in range(round(a.DURATION*a.FPS)):
        t = f/a.FPS
        while cursor < len(events) and events[cursor]['t'] <= t:
            e = events[cursor]; cursor += 1
            x, y = e['p']; grid[x, y] = 0
            offsets = [(dx, dy) for dx in range(4) for dy in range(4)]
            rng.shuffle(offsets)
            for dx, dy in offsets[:e['grains']]:
                p = (x*4+dx, y*4+dy)
                if p in sand:
                    raise ValueError('Sand overlapped an unreleased source tile')
                sand[p] = e['level']
        for _ in range(2):
            order = sorted(sand, key=lambda p: (-p[1], rng.random()))
            for p in order:
                level = sand.pop(p)
                side = -1 if rng.random() < .5 else 1
                destination = p
                for dx in (0, side, -side):
                    q = (p[0]+dx, p[1]+1)
                    if (-4 <= q[0] < a.COLS*4+4 and q[1] < 30 and q not in sand
                            and not grid.get((q[0]//4, q[1]//4), 0)):
                        destination = q
                        break
                sand[destination] = level
        states.append({'grid': grid.copy(), 'sand': sand.copy(), 'released': cursor})
    return {'states': states, 'events': events, 'final': grid}


def draw_gravity(model, initial, missing, t, focus):
    st = model['states'][min(len(model['states'])-1, int(t*a.FPS))]
    img, d, v = a.base(initial, st['grid'], missing, 'gravity', t, focus)
    for (gx, gy), level in st['sand'].items():
        x, y = v.xy((gx/4-.375, gy/4-.375)); r = v.pitch*.105
        if -10 < x < a.W+10:
            a.rect(d, (x-r, y-r, x+r, y+r), a.GREEN[level], r=1)
    x1, y = v.xy((-1, 7.05)); x2, _ = v.xy((a.COLS, 7.05))
    d.line((x1, y, x2, y), fill=a.MUTED, width=2)
    a.rect(d, (0, 383, a.W, a.H), a.BG)
    a.text(d, (28, 389), 'YOUR GREEN DAYS TURN INTO SAND / PARTICLES KEEP THEIR COLOUR', style='label', fill=a.MUTED)
    a.text(d, (1012, 389), f'GRAINS {len(st["sand"]):04d}', style='hud', anchor='ra')
    return a.finish_frame(img)


def register():
    for key, num, title, subtitle, planner, drawer in [
        ('pinball', '04', 'HEATMAP PINBALL', 'Every ball collides with your real contribution tiles.', plan_pinball, draw_pinball),
        ('laser', '05', 'LASER REFLECTION', 'Your green days are mirrors. Reflect, drain, clear.', plan_laser, draw_laser),
        ('gravity', '06', 'CONTRIBUTION SAND', 'The calendar crumbles into a tiny falling-sand simulation.', plan_gravity, draw_gravity),
    ]:
        a.SCENES[key] = (num, title, subtitle, a.CYAN)
        a.PLANNERS[key] = planner
        a.DRAWERS[key] = drawer
