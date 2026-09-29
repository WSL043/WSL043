"""Small, scriptless animated SVGs: a full heatmap, not a dashboard or GIF wrapper."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from html import escape
import hashlib
import json
import math
from pathlib import Path
from scripts.svg_models import Calendar, PLANNERS, DIRS
from scripts.svg_iso import CANVAS_H, DX, GAP, ROWS, SLAB, UNIT_FACE, Iso, layout, quarter_sizes, shades, streak_and_week

HEIGHTS = {'isocity': CANVAS_H, 'isodrop': CANVAS_H}

THEMES = {
    'dark': ('#0d1117', '#161b22', '#30363d', '#8b949e',
             ('#161b22', '#0e4429', '#006d32', '#26a641', '#39d353')),
    'light': ('#ffffff', '#ebedf0', '#d0d7de', '#57606a',
              ('#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39')),
}
FONT = 'ui-monospace,monospace'
NAMES = {'bomber': 'Heatmap Bomber', 'miners': 'Commit Miners',
         'link-match': 'Contribution Link', 'portal': 'Portal Courier',
         'assembly': 'Magnetic Assembly', 'minecraft': 'Minecraft Block Miner', 'lego': 'LEGO Brick Workshop',
         'fireworks': 'Firework Show', 'domino': 'Domino Ripple', 'dust': 'Pixel Dust',
         'sorter': 'Level Sorter', 'synth': 'Heatmap Synth', 'claw': 'Claw Machine',
         'isocity': 'Isometric City', 'isodrop': 'Block Rain'}


def num(value):
    return f'{value:.4f}'.rstrip('0').rstrip('.') or '0'


def xy(point):
    return 24 + point[0] * 16, 46 + point[1] * 16


def transform(x, y, scale=1, angle=0):
    return f'translate({num(x)}px,{num(y)}px) rotate({num(angle)}deg) scale({num(scale)})'


def ease(value):
    return value * value * (3 - 2 * value)


def bezier(a, b, c, d, t):
    u = 1 - t
    return tuple(u**3*a[k]+3*u*u*t*b[k]+3*u*t*t*c[k]+t**3*d[k] for k in (0, 1))


class Drawing:
    def __init__(self, cal, scene, theme, duration, height=216):
        self.cal, self.scene, self.theme, self.duration = cal, scene, theme, duration
        self.height = height
        self.bg, self.empty, self.line, self.muted, self.green = THEMES[theme]
        self.accent = '#f2cc60' if theme == 'dark' else '#9a6700'
        self.cyan = '#79e0f2' if theme == 'dark' else '#0969da'
        self.width = cal.cols * 16 + 48
        self.css, self.parts, self.tracks = [], [], []

    def animated(self, body, frames, base):
        # Each track explicitly returns to its first state; no cut on loop wrap.
        ident = f'a{len(self.tracks)}'
        values = {0.0: base.copy(), self.duration: base.copy()}
        if frames and min(t for t, _ in frames) > .001:
            values[min(t for t, _ in frames)-.001] = base.copy()
        for time, props in frames:
            if not 0 <= time <= self.duration:
                raise ValueError('Animation exceeds its declared loop')
            values.setdefault(float(time), {}).update(props)
        self.tracks.append(values)
        initial = ';'.join(f'{k}:{v}' for k, v in base.items())
        keys = ''.join(f'{num(100*t/self.duration)}%'+'{'+
                       ';'.join(f'{k}:{v}' for k, v in props.items())+'}'
                       for t, props in sorted(values.items()))
        self.css.append(f'.{ident}'+'{'+initial+f';animation:{ident} {num(self.duration)}s linear infinite;transform-origin:0 0'+'}')
        self.css.append(f'@keyframes {ident}'+'{'+keys+'}')
        return f'<g class="{ident}">{body}</g>'

    def active_tiles(self, changes, finish):
        for index, p in enumerate(self.cal.active):
            level = self.cal.grid[p]
            x, y = xy(p)
            normal = {'transform': transform(x, y), 'opacity': '1', 'fill': self.green[level]}
            frames, old = [], level
            for t, hp in changes.get(p, []):
                frames += [(max(.001, t-.025), {'fill': self.green[old], 'opacity': '1', 'transform': normal['transform']}),
                           (t, {'fill': self.green[hp], 'opacity': '1' if hp else '0', 'transform': normal['transform']})]
                old = hp
            if changes.get(p):
                restore = finish + 1 + 1.4 * index / max(1, len(self.cal.active))
                frames += [(restore, {'opacity': '0', 'transform': transform(x, y+5, .35)}),
                           (restore+.04, {'fill': self.green[level], 'opacity': '.45'}),
                           (restore+.4, normal), (self.duration-.2, normal)]
            tile = f'<rect x="-6" y="-6" width="12" height="12" rx="2" data-day="{p[0]},{p[1]}"/>'
            self.parts.append(self.animated(tile, frames, normal))

    def flash(self, body, start, end, opacity='1'):
        frames = [(max(0, start-.001), {'opacity': '0'}), (start, {'opacity': opacity}),
                  (end, {'opacity': '0'})]
        self.parts.append(self.animated(body, frames, {'opacity': '0'}))

    def spark(self, point, t, colour=None):
        x, y = xy(point)
        colour = colour or self.accent
        body = f'<path d="M-4 0H4M0-4V4" stroke="{colour}" stroke-width="1.3"/>'
        self.parts.append(self.animated(body, [(t, {'transform': transform(x, y), 'opacity': '1'}),
            (t+.32, {'transform': transform(x, y, 2, 90), 'opacity': '0'})],
            {'opacity': '0', 'transform': transform(x, y, .2)}))

    def robot(self, route_keys, start, end, colour):
        # One small sprite with distinct face, boots and antenna; no image embeds.
        body = (f'<path d="M-4 5v2M4 5v2M0-7v-2" stroke="{colour}" stroke-width="2"/>'
                f'<rect x="-6" y="-6" width="12" height="11" rx="3" fill="{colour}"/>'
                '<rect x="-4" y="-3" width="8" height="4" rx="1.5" fill="#0d1117"/>'
                '<path d="M-2-2v2M2-2v2" stroke="#ffffff" stroke-width="1.3"/>')
        first = transform(*xy(start))
        frames = [(max(0, route_keys[0][0]-.1), {'opacity': '0'}), (route_keys[0][0], {'opacity': '1'})]
        frames += [(t, {'transform': transform(*xy(p))}) for t, p in route_keys]
        frames += [(end+.15, {'opacity': '1'}), (end+.6, {'opacity': '0'}),
                   (self.duration-.1, {'transform': first, 'opacity': '0'})]
        self.parts.append(self.animated(body, frames, {'transform': first, 'opacity': '0'}))

    def static_grid(self, coloured=False):
        result = []
        for p, level in self.cal.grid.items():
            if p in self.cal.missing:
                continue
            x, y = xy(p)
            fill = self.green[level] if coloured else self.empty
            result.append(f'<rect x="{x-6}" y="{y-6}" width="12" height="12" rx="2" fill="{fill}"/>')
        return ''.join(result)

    def document(self, seed):
        months, last = [], None
        names = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
        for x, raw in enumerate(self.cal.weeks):
            month = date.fromisoformat(raw).month
            if month != last:
                months.append(f'<text x="{xy((x, 0))[0]-6}" y="15">{names[month-1]}</text>')
                last = month
        digest = hashlib.sha256(json.dumps(sorted(self.cal.grid.items())).encode()).hexdigest()
        meta = {'scene': self.scene, 'owner': self.cal.owner, 'date': self.cal.day,
                'active_days': len(self.cal.active), 'grid_sha256': digest, 'seed': seed,
                'duration_seconds': round(self.duration, 4), 'format': 'vector-css-svg'}
        styles = ('svg{font:10px ui-monospace,monospace}text{fill:'+self.muted+'}'
                  '.still{display:none}.motion{display:inline}@media print{.motion{display:none}.still{display:inline}}')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
                f'width="{self.width}" height="{self.height}" role="img" aria-labelledby="title desc" data-scene="{self.scene}">'
                f'<title id="title">{escape(self.cal.owner)} — {NAMES[self.scene]}</title>'
                f'<desc id="desc">Full contribution calendar, {escape(self.cal.day)}. '
                'Autoplay simulation; the source contributions are never modified. Printing shows the original calendar.</desc>'
                f'<metadata>{escape(json.dumps(meta, separators=(",", ":")))}</metadata>'
                '<style>'+styles+''.join(self.css)+'</style>'
                f'<rect width="100%" height="100%" fill="{self.bg}"/>'+''.join(months)+
                '<g class="still">'+self.static_grid(True)+'</g><g class="motion">'+
                self.static_grid()+''.join(self.parts)+'</g></svg>')


def bomber(cal, model, theme):
    events, now = [], 1.5
    for event in model['events']:
        plant = now + (len(event['route'])-1)*.07
        flee = plant+.16
        detonate = max(plant+.66, flee+(len(event['retreat'])-1)*.07+.12)
        events.append((event, now, plant, flee, detonate))
        now = detonate+.3
    factor = min(1, 100/max(1, now))
    finish = now*factor
    draw = Drawing(cal, 'bomber', theme, finish+5)
    changes, motion = defaultdict(list), [(1.3*factor, model['start'])]
    for e, start, plant, flee, hit in events:
        motion += [((start+i*.07)*factor, p) for i, p in enumerate(e['route'])]
        motion += [((flee+i*.07)*factor, p) for i, p in enumerate(e['retreat'])]
        for p, hp in zip(e['hits'], e['hp']):
            changes[p].append((hit*factor, hp-1))
    draw.active_tiles(changes, finish)
    for e, start, plant, flee, hit in events:
        x, y = xy(e['route'][-1])
        bomb = (f'<circle cx="{x}" cy="{y}" r="5" fill="{draw.accent}"/>'
                f'<circle cx="{x-1}" cy="{y-1}" r="3.1" fill="{draw.bg}"/>'
                f'<path d="M{x+2} {y-4}l2-3" stroke="{draw.accent}" stroke-width="1.4"/>')
        draw.flash(bomb, plant*factor, hit*factor)
        for dx, dy in DIRS:
            ray = [p for p in e['area'] if (p[0]-e['route'][-1][0])*dx+(p[1]-e['route'][-1][1])*dy > 0
                   and (p[0]-e['route'][-1][0])*dy == (p[1]-e['route'][-1][1])*dx]
            if ray:
                ex, ey = xy(ray[-1])
                body = f'<path d="M{x} {y}L{ex} {ey}" stroke="{draw.accent}" stroke-width="6" stroke-linecap="round"/>'
                draw.flash(body, hit*factor, hit*factor+.24*factor, '.8')
        for p in e['hits']:
            draw.spark(p, hit*factor)
    draw.robot(motion, model['start'], finish, draw.accent)
    return draw


def miners(cal, model, theme):
    jobs, now = [], 1.5
    for wave in model['waves']:
        ends = []
        for job in wave:
            drill = now + (len(job['route'])-1)*.085
            done = drill+.28+.14*job['level']
            jobs.append((job, now, drill, done))
            ends.append(done)
        now = max(ends)+.7
    factor = min(1, 90/max(1, now))
    finish = now*factor
    draw = Drawing(cal, 'miners', theme, finish+5)
    changes = defaultdict(list)
    motions = [[(1.3*factor, p)] for p in model['starts']]
    for job, start, drill, done in jobs:
        changes[job['target']].append((done*factor, 0))
        motions[job['bot']] += [((start+i*.085)*factor, p) for i, p in enumerate(job['route'])]
        motions[job['bot']].append((done*factor, job['route'][-1]))
    draw.active_tiles(changes, finish)
    # Two little carts travel below the calendar, not over fabricated days.
    for bot, colour in enumerate((draw.cyan, draw.accent)):
        body = (f'<path d="M-8-4h16l-2 9H-6z" fill="{colour}"/>'
                f'<circle cx="-4" cy="7" r="2" fill="{draw.muted}"/>'
                f'<circle cx="4" cy="7" r="2" fill="{draw.muted}"/>')
        positions = [(when*factor, {'transform': transform(xy(j['target'])[0], 191)})
                     for j, _, _, t in jobs if j['bot'] == bot for when in (t, t+.6)]
        frames = [(1.2*factor, {'opacity': '1'})]+positions+[(finish+.15, {'opacity': '1'}), (finish+.6, {'opacity': '0'})]
        draw.parts.append(draw.animated(body, frames,
                          {'transform': transform(xy(model['starts'][bot])[0], 191), 'opacity': '0'}))
    for job, start, drill, done in jobs:
        target, stand = xy(job['target']), xy(job['route'][-1])
        tool = f'<path d="M{stand[0]} {stand[1]}L{target[0]} {target[1]}" stroke="{draw.accent}" stroke-width="2" stroke-dasharray="2 2"/>'
        draw.flash(tool, drill*factor, done*factor)
        draw.spark(job['target'], done*factor)
        # The ore chip visibly falls from the actual removed day to its cart.
        x, y = target
        body = f'<rect x="-3" y="-3" width="6" height="6" rx="1" fill="{draw.green[job["level"]]}"/>'
        draw.parts.append(draw.animated(body,
            [(done*factor, {'transform': transform(x, y), 'opacity': '1'}),
             ((done+.2)*factor, {'transform': transform(x+5, y-9, 1, 40)}),
             ((done+.53)*factor, {'transform': transform(x, 184, .6, 150), 'opacity': '1'}),
             ((done+.59)*factor, {'opacity': '0'})], {'opacity': '0', 'transform': transform(x, y)}))
    for i in (0, 1):
        draw.robot(motions[i], model['starts'][i], finish, (draw.cyan, draw.accent)[i])
    return draw


def links(cal, model, theme):
    factor = min(1, 95/max(1, len(model['pairs'])*.92))
    finish = 1.5 + len(model['pairs'])*.92*factor
    draw = Drawing(cal, 'link-match', theme, finish+5)
    changes = defaultdict(list)
    for i, pair in enumerate(model['pairs']):
        at = 1.5 + i*.92*factor
        for p in (pair['a'], pair['b']):
            changes[p].append((at+.7*factor, 0))
    draw.active_tiles(changes, finish)
    for i, pair in enumerate(model['pairs']):
        at = 1.5 + i*.92*factor
        points = [xy(p) for p in pair['route']]
        d = 'M'+'L'.join(f'{x} {y}' for x, y in points)
        body = f'<path d="{d}" fill="none" stroke="{draw.cyan}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        draw.flash(body, at+.15*factor, at+.75*factor)
        for p in (pair['a'], pair['b']):
            x, y = xy(p)
            draw.flash(f'<rect x="{x-7}" y="{y-7}" width="14" height="14" rx="3" fill="none" stroke="{draw.accent}" stroke-width="1.4"/>',
                       at, at+.7*factor)
            draw.spark(p, at+.7*factor, draw.cyan)
        frames = [(at+.15*factor+j/max(1, len(points)-1)*.45*factor,
                   {'transform': transform(x, y), 'opacity': '1'}) for j, (x, y) in enumerate(points)]
        frames.append((at+.7*factor, {'opacity': '0'}))
        draw.parts.append(draw.animated('<circle r="2.8" fill="#ffffff"/>', frames, {'opacity': '0'}))
    return draw


def portal(cal, model, theme):
    n = len(model['order'])
    span = min(22, max(5, n*.16))
    back = 1.5+span+2.5
    finish = back+span+2
    draw = Drawing(cal, 'portal', theme, finish+2)
    left, right = (12, 187), (draw.width-12, 187)
    for p, colour in ((left, draw.accent), (right, draw.cyan)):
        body = (f'<ellipse rx="6" ry="13" fill="{draw.bg}" stroke="{colour}" stroke-width="2"/>'
                f'<ellipse rx="9" ry="16" fill="none" stroke="{colour}" stroke-width="1" opacity=".35"/>')
        draw.parts.append(draw.animated(body, [(1, {'opacity': '1'}), (finish+.5, {'opacity': '1'}),
                     (finish+1.2, {'opacity': '0'})], {'transform': transform(*p), 'opacity': '0'}))
    for i, p in enumerate(model['order']):
        home = xy(p)
        out = 1.5 + i/max(1, n)*span
        arrive = back + (n-1-i)/max(1, n)*span
        base = {'transform': transform(*home), 'opacity': '1'}
        frames = [(out, base)]
        for j in range(1, 9):
            t = j/8
            point = bezier(home, (home[0], 181), (left[0]+60, 187), left, ease(t))
            frames.append((out+t*1.55, {'transform': transform(*point, 1-.45*t, 180*t), 'opacity': '1'}))
        frames += [(out+1.57, {'opacity': '0'}),
                   (arrive-.01, {'transform': transform(*right, .55, 180), 'opacity': '0'}),
                   (arrive, {'opacity': '1'})]
        for j in range(1, 9):
            t = j/8
            point = bezier(right, (right[0]-65, 187), (home[0], 178), home, ease(t))
            frames.append((arrive+t*1.55, {'transform': transform(*point, .55+.45*t, 180*(1-t)), 'opacity': '1'}))
        frames.append((finish+.5, base))
        body = f'<rect x="-6" y="-6" width="12" height="12" rx="2" fill="{draw.green[cal.grid[p]]}" data-day="{p[0]},{p[1]}"/>'
        draw.parts.append(draw.animated(body, frames, base))
        draw.spark(p, arrive+1.55, draw.cyan)
    return draw


def assembly(cal, model, theme):
    n = len(model['pieces'])
    span = min(26, max(8, n*.48))
    back, finish = 1.5+span*.5+2.5, 1.5+span*1.5+4.5
    draw = Drawing(cal, 'assembly', theme, finish+2)
    spacing = (draw.width-40)/max(1, n)
    for i, piece in enumerate(model['pieces']):
        coords = [xy(p) for p in piece]
        centre = (round(sum(p[0] for p in coords)/len(coords)), round(sum(p[1] for p in coords)/len(coords)))
        dock = 20+(i+.5)*spacing, 184
        scale = min(.55, spacing/62)
        angle = (90 if i % 2 else -90)
        base = {'transform': transform(*centre), 'opacity': '1'}
        out = 1.5 + i/max(1, n)*span*.5
        back_at = back+(n-1-i)/max(1, n)*span
        frames = [(out, base)]
        for j in range(1, 9):
            t = j/8
            point = bezier(centre, (centre[0], 165), (dock[0], 165), dock, ease(t))
            frames.append((out+t*1.3, {'transform': transform(*point, 1+(scale-1)*ease(t), angle*ease(t))}))
        frames.append((back_at, {'transform': transform(*dock, scale, angle)}))
        for j in range(1, 9):
            t = j/8
            point = bezier(dock, (dock[0], 166), (centre[0], 166), centre, ease(t))
            frames.append((back_at+t*1.3, {'transform': transform(*point, scale+(1-scale)*ease(t), angle*(1-ease(t)))}))
        frames += [(back_at+1.39, {'transform': transform(*centre, 1.05)}), (back_at+1.55, base)]
        body = ''.join(f'<rect x="{num(x-centre[0]-6)}" y="{num(y-centre[1]-6)}" width="12" height="12" rx="2" '
                       f'fill="{draw.green[cal.grid[p]]}" data-day="{p[0]},{p[1]}"/>' for p, (x, y) in zip(piece, coords))
        draw.parts.append(draw.animated(body, frames, base))
        for p in piece:
            draw.spark(p, back_at+1.3, draw.cyan)
    return draw


def minecraft(cal, model, theme):
    order = model['order']
    step = min(.7, 64/max(1, len(order)))
    finish = 2+len(order)*step
    draw = Drawing(cal, 'minecraft', theme, finish+6)
    # Pixel explorer with turquoise shirt, square head and a diamond-coloured pick.
    sprite = ('<path d="M-5-17h10v9H-5z" fill="#bc865b"/>'
              '<path d="M-5-19h10v4H-5zM-5-19h3v7H-5z" fill="#513a29"/>'
              '<path d="M-5-8H5V1H-5z" fill="#29b6ad"/>'
              '<path d="M-5 1H-1V8H-5zM1 1H5V8H1z" fill="#6465b5"/>'
              '<path d="M6-5L13-12" stroke="#895e38" stroke-width="2"/>'
              '<path d="M9-14h7v5" stroke="#64eee2" stroke-width="3" fill="none"/>')
    start = xy(order[0])
    base = {'transform': transform(start[0]-12, start[1]+4), 'opacity': '0'}
    moves = []
    for i, p in enumerate(order):
        x, y = xy(p)
        at = 1.5+i*step
        moves += [(at, {'transform': transform(x-12, y+4), 'opacity': '1'}),
                  (at+step*.35, {'transform': transform(x-11, y+3, 1, -12)}),
                  (at+step*.7, {'transform': transform(x-12, y+4)})]
        body = (f'<rect x="-6" y="-6" width="12" height="12" fill="{draw.green[cal.grid[p]]}" data-day="{p[0]},{p[1]}"/>'
                '<path d="M-6-2H6V6H-6z" fill="#805432"/>'
                '<path d="M-4 0h3v2h-3zM1 3h3v2H1z" fill="#b98452"/>'
                f'<path d="M-6-6H6v4H-6zM-4-2h2v2h-2zM2-2h2v2H2z" fill="{draw.green[cal.grid[p]]}"/>')
        home = {'transform': transform(x, y), 'opacity': '1'}
        dock = (24+(i % cal.cols)*16, 173+(i//cal.cols)*5)
        back = finish+.6+i/max(1, len(order))*2
        draw.parts.append(draw.animated(body, [(at, home),
            (at+step*.4, {'transform': transform(x, y, .9, -8)}),
            (at+step*.7, {'transform': transform(x, y, .7, 12)}),
            (at+step+ .3, {'transform': transform(*dock, .55), 'opacity': '1'}),
            (back, {'transform': transform(*dock, .55)}), (back+.7, home)], home))
        draw.flash(f'<path d="M{x-4} {y-5}l4 4-2 3 5 3" stroke="#f0f6fc" fill="none"/>', at+step*.2, at+step*.7)
        draw.spark(p, at+step*.6)
    moves += [(finish, {'opacity': '0'}), (draw.duration-.1, base)]
    draw.parts.append(draw.animated(sprite, moves, base))
    draw.parts.append(f'<text x="24" y="210">MINE / COLLECT / REBUILD</text>')
    return draw


def lego(cal, model, theme):
    pieces = model['pieces']
    step = min(.55, 55/max(1, len(pieces)))
    back = 3+len(pieces)*step
    draw = Drawing(cal, 'lego', theme, back+5)
    draw.parts.append(f'<rect x="16" y="172" width="{draw.width-32}" height="22" rx="5" fill="{draw.line}"/>')
    for x in range(24, draw.width-16, 24):
        draw.parts.append(f'<circle cx="{x}" cy="188" r="3" fill="{draw.muted}"/>')
    for i, piece in enumerate(pieces):
        x, y = xy(piece[0])
        width = (len(piece)-1)*16+12
        colour = draw.green[cal.grid[piece[0]]]
        body = f'<rect x="-6" y="-6" width="{width}" height="12" rx="1" fill="{colour}"/>'
        body += f'<path d="M-6 3h{width}v3H-6z" fill="#000000" opacity=".25"/>'
        for j, p in enumerate(piece):
            # Invisible identity rect follows its own real date within the brick.
            body += (f'<rect x="{j*16-6}" y="-6" width="12" height="12" fill="none" data-day="{p[0]},{p[1]}"/>'
                     f'<ellipse cx="{j*16}" cy="-7" rx="4" ry="2" fill="{colour}" stroke="{draw.muted}" stroke-width=".7"/>')
        home = {'transform': transform(x, y), 'opacity': '1'}
        at = 1.5+i*step
        # The first pass feeds a brick to the belt; a small gantry returns it.
        dock_x = 28+(i % max(1, (cal.cols//4)))*64
        frames = [(at, home), (at+.3, {'transform': transform(x, y-13)}),
                  (at+.85, {'transform': transform(dock_x, 178)}),
                  (at+1.15, {'transform': transform(dock_x+18, 178)}),
                  (at+1.65, {'transform': transform(x, y-14)}),
                  (at+1.85, home), (at+1.93, {'transform': transform(x, y, 1.08)}),
                  (at+2.05, home)]
        draw.parts.append(draw.animated(body, frames, home))
        draw.spark(piece[-1], at+1.85, draw.cyan)
        draw.flash(f'<path d="M{x} 24V{y-16}m-7 0h14" stroke="{draw.cyan}" stroke-width="2" fill="none"/>', at+1.15, at+1.85)
    draw.parts.append('<text x="24" y="210">BRICK WORKSHOP / SNAP FIT</text>')
    return draw


def lone_tile(draw, p, frames):
    """One real active day as a single tile track; every frame states all animated properties."""
    x, y = xy(p)
    normal = {'transform': transform(x, y), 'opacity': '1', 'fill': draw.green[draw.cal.grid[p]]}
    tile = f'<rect x="-6" y="-6" width="12" height="12" rx="2" data-day="{p[0]},{p[1]}"/>'
    draw.parts.append(draw.animated(tile, [(t, {**normal, **props}) for t, props in frames], normal))
    return normal


def caption(text):
    return f'<text x="24" y="211">{text}</text>'


def fireworks(cal, model, theme):
    order, n = model['order'], len(model['order'])
    step = min(.3, 50/max(1, n))
    first, fly = 2.4, .55
    finish = first+n*step+fly+1.4
    draw = Drawing(cal, 'fireworks', theme, finish+4)
    colours = (draw.accent, draw.cyan, '#ff8fa3' if theme == 'dark' else '#cf222e')
    pads = [xy((c, 0))[0] for c in model['pads']]
    for x in pads:
        draw.parts.append(f'<rect x="{x-8}" y="198" width="16" height="5" rx="2" fill="{draw.line}"/>')
    for i, p in enumerate(order):
        x, y = xy(p)
        at = first+i*step
        boom = at+fly
        colour = colours[i % 3]
        dark = {'opacity': '0', 'transform': transform(x, y, .7)}
        lit = {'opacity': '1', 'transform': transform(x, y, 1.45)}
        blackout = .9+x/draw.width*.7
        lone_tile(draw, p, [(blackout, {}), (blackout+.35, dark), (boom-.02, dark), (boom, lit),
                            (boom+.4, {'transform': transform(x, y, 1)})])
        pad = min(pads, key=lambda v: abs(v-x))
        angle = math.degrees(math.atan2(x-pad, 198-y))
        rocket = (f'<circle r="2.4" fill="{colour}"/>'
                  f'<path d="M0 2v10" stroke="{colour}" stroke-width="1.6" stroke-linecap="round" opacity=".55"/>')
        draw.parts.append(draw.animated(rocket, [
            (at, {'transform': transform(pad, 196, 1, angle), 'opacity': '1'}),
            (boom, {'transform': transform(x, y, 1, angle), 'opacity': '1'}),
            (boom+.04, {'opacity': '0', 'transform': transform(x, y, 1, angle)})],
            {'transform': transform(pad, 196, 1, angle), 'opacity': '0'}))
        ring = f'<circle r="5" fill="none" stroke="{colour}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>'
        draw.parts.append(draw.animated(ring, [
            (boom, {'transform': transform(x, y, .3), 'opacity': '.95'}),
            (boom+.45, {'transform': transform(x, y, 2.4), 'opacity': '0'})],
            {'transform': transform(x, y, .3), 'opacity': '0'}))
        draw.spark(p, boom, colour)
    draw.parts.append(caption('FIREWORKS / RELIGHT THE YEAR'))
    return draw


def domino(cal, model, theme):
    order, origin, lean = model['order'], model['origin'], model['lean']
    speed, fall0 = .11, 1.8
    dist = {p: math.hypot(p[0]-origin[0], p[1]-origin[1]) for p in order}
    far = max(dist.values(), default=0)
    rise0 = fall0+far*speed+3
    finish = rise0+far*speed+1.2
    draw = Drawing(cal, 'domino', theme, finish+3)
    for p in order:
        x, y = xy(p)
        fall, rise = fall0+dist[p]*speed, rise0+dist[p]*speed
        down = {'transform': transform(x+4*lean, y+4, .92, 84*lean), 'opacity': '.45'}
        lone_tile(draw, p, [(fall, {}), (fall+.14, {'transform': transform(x+2*lean, y+2, 1, 38*lean)}),
                            (fall+.32, down), (rise, down),
                            (rise+.16, {'transform': transform(x+lean, y+1, 1.05, 30*lean), 'opacity': '.8'}),
                            (rise+.34, {'transform': transform(x, y, 1.12)}), (rise+.5, {})])
    ox, oy = xy(origin)
    for start, colour in ((fall0, draw.accent), (rise0, draw.cyan)):
        ring = f'<circle r="1" fill="none" stroke="{colour}" stroke-width="2" vector-effect="non-scaling-stroke"/>'
        draw.parts.append(draw.animated(ring, [
            (start, {'transform': transform(ox, oy, .5), 'opacity': '.9'}),
            (start+far*speed+.3, {'transform': transform(ox, oy, far*16+24), 'opacity': '0'})],
            {'transform': transform(ox, oy, .5), 'opacity': '0'}))
    draw.spark(origin, fall0, draw.accent)
    draw.parts.append(caption('DOMINO / RIPPLE EFFECT'))
    return draw


def dust(cal, model, theme):
    order, drift, n = model['order'], model['drift'], len(model['order'])
    sweep = min(22, max(6, n*.12))
    snap0 = 2
    back0 = snap0+sweep+3.5
    finish = back0+sweep+1.8
    draw = Drawing(cal, 'dust', theme, finish+3)
    for i, (p, (dx, dy, rot)) in enumerate(zip(order, drift)):
        x, y = xy(p)
        gone = snap0+i/max(1, n)*sweep
        back = back0+i/max(1, n)*sweep
        away = {'transform': transform(x+dx, y+dy, .25, rot), 'opacity': '0'}
        near = {'transform': transform(x-dx*.4, y-dy*.4+8, .25, -rot*.5), 'opacity': '0'}
        lone_tile(draw, p, [(gone, {}), (gone+.25, {'transform': transform(x+3, y-2, .95, 6), 'opacity': '.8'}),
                            (gone+1.2, away), (back, near),
                            (back+.9, {'transform': transform(x, y, 1.1)}), (back+1.05, {})])
        mote = f'<rect x="-1.5" y="-1.5" width="3" height="3" fill="{draw.green[cal.grid[p]]}"/>'
        draw.parts.append(draw.animated(mote, [
            (gone+.1, {'transform': transform(x, y), 'opacity': '.9'}),
            (gone+1.5, {'transform': transform(x+dx*1.9, y+dy*1.5, .6, rot*2), 'opacity': '0'})],
            {'transform': transform(x, y), 'opacity': '0'}))
        draw.spark(p, back+.9, draw.cyan)
    draw.parts.append(caption('PIXEL DUST / SNAP AND REFORM'))
    return draw


def sorter(cal, model, theme):
    order, slots, counts = model['order'], model['slots'], model['counts']
    n = len(order)
    step = min(.22, 45/max(1, n))
    out0 = 2
    back0 = out0+n*step+4
    finish = back0+n*step+1.6
    draw = Drawing(cal, 'sorter', theme, finish+3)
    gap = 12
    binw = (draw.width-48-3*gap)/4
    peak = max(counts)
    # Largest mini-tile pitch at which the fullest bin still fits in about five rows.
    pitch = next((m for m in (8, 7, 6, 5, 4.4) if int((binw-10)/m)*int(34/m) >= peak), 4.4)
    per_row = max(1, int((binw-10)/pitch))
    mini = (pitch-.9)/12
    for b in range(4):
        x0 = 24+b*(binw+gap)
        draw.parts.append(f'<rect x="{num(x0)}" y="160" width="{num(binw)}" height="42" rx="5" fill="{draw.empty}" stroke="{draw.line}" stroke-width="1.5"/>')
        draw.parts.append(f'<text x="{num(x0)}" y="213">LEVEL {b+1} · {counts[b]} days</text>')
    for i, (p, (b, k)) in enumerate(zip(order, slots)):
        home = xy(p)
        slot = (24+b*(binw+gap)+8+pitch/2+(k % per_row)*pitch, 197-pitch/2-(k//per_row)*pitch)
        out, back = out0+i*step, back0+(n-1-i)*step
        frames = [(out, {})]
        for j in range(1, 7):
            t = ease(j/6)
            pt = bezier(home, (home[0], 150), (slot[0], 150), slot, t)
            frames.append((out+j/6*.9, {'transform': transform(*pt, 1+(mini-1)*t, 180*t)}))
        frames.append((back, {'transform': transform(*slot, mini, 180)}))
        for j in range(1, 7):
            t = ease(j/6)
            pt = bezier(slot, (slot[0], 152), (home[0], 152), home, t)
            frames.append((back+j/6*.9, {'transform': transform(*pt, mini+(1-mini)*t, 180*(1-t))}))
        lone_tile(draw, p, frames+[(back+1.0, {'transform': transform(*home, 1.08)}), (back+1.15, {})])
        draw.spark(p, back+.95, draw.cyan)
    return draw


def synth(cal, model, theme):
    cols = cal.cols
    sweeps, clock = [], 1.5
    for ps in model['passes']:
        sweeps.append((clock, ps['dir'], ps['tempo']))
        clock += cols*ps['tempo']+1.2
    finish = clock+.6
    draw = Drawing(cal, 'synth', theme, finish+2)
    xs = [xy((c, 0))[0] for c in range(cols)]
    frames = []
    for start, direction, tempo in sweeps:
        a, b = (xs[0], xs[-1]) if direction == 1 else (xs[-1], xs[0])
        frames += [(start-.05, {'transform': transform(a, 38), 'opacity': '0'}), (start, {'transform': transform(a, 38), 'opacity': '1'}),
                   (start+cols*tempo, {'transform': transform(b, 38), 'opacity': '1'}),
                   (start+cols*tempo+.2, {'transform': transform(b, 38), 'opacity': '0'})]
    head = (f'<rect x="-6" y="0" width="12" height="118" fill="{draw.cyan}" opacity=".16"/>'
            f'<rect x="-1.2" y="0" width="2.4" height="118" rx="1" fill="{draw.cyan}"/>')
    draw.parts.append(draw.animated(head, frames, {'transform': transform(xs[0], 38), 'opacity': '0'}))
    sums = [sum(cal.grid[c, r] for r in range(7)) for c in range(cols)]
    peak = max(max(sums), 1)
    for c in range(cols):
        height = max(3, 24*sums[c]/peak)
        base = {'transform': f'translate({num(xs[c])}px,200px) rotate(0deg) scale(1,1)', 'opacity': '.35'}
        bar = f'<rect x="-3.5" y="{num(-height)}" width="7" height="{num(height)}" rx="2" fill="{draw.accent}"/>'
        bar_frames = []
        for start, direction, tempo in sweeps:
            hit = start+(c if direction == 1 else cols-1-c)*tempo
            pulse = {'transform': f'translate({num(xs[c])}px,200px) rotate(0deg) scale(1,1.5)', 'opacity': '1'}
            bar_frames += [(hit-.02, base), (hit+.05, pulse), (hit+.4, base)]
        draw.parts.append(draw.animated(bar, bar_frames, base))
    for p in cal.active:
        x, y = xy(p)
        pulses = []
        for start, direction, tempo in sweeps:
            hit = start+(p[0] if direction == 1 else cols-1-p[0])*tempo
            pulses += [(hit-.02, {}), (hit+.04, {'transform': transform(x, y, 1.55), 'fill': draw.cyan}), (hit+.3, {})]
        lone_tile(draw, p, pulses)
    draw.parts.append(caption('SYNTH / PLAY THE YEAR'))
    return draw


def claw(cal, model, theme):
    order, n = model['order'], len(model['order'])
    s = min(.9, 60/max(1, n))
    first = 1.5
    finish = first+n*s+.8
    draw = Drawing(cal, 'claw', theme, finish+5)
    chute = draw.width-30
    draw.parts.append(f'<rect x="16" y="14" width="{draw.width-32}" height="3" rx="1.5" fill="{draw.line}"/>')
    draw.parts.append(f'<rect x="{chute-20}" y="174" width="40" height="32" rx="5" fill="{draw.empty}" stroke="{draw.line}" stroke-width="1.5"/>')
    draw.parts.append(f'<text x="{chute-20}" y="213">PRIZES</text>')
    head_frames, cable_frames = [], []

    def place(t, x, yh):
        head_frames.append((t, {'transform': transform(x, yh), 'opacity': '1'}))
        cable_frames.append((t, {'transform': f'translate({num(x)}px,15px) rotate(0deg) scale(1,{num(max(1, yh-15))})', 'opacity': '1'}))

    for i, p in enumerate(order):
        x, y = xy(p)
        t = first+i*s
        place(t, chute, 22)
        place(t+.3*s, x, 22)
        place(t+.5*s, x, y-9)
        place(t+.56*s, x, y-9)
        place(t+.78*s, x, 22)
        place(t+s, chute, 22)
        restore = finish+.8+i/max(1, n)*1.4
        pop = {'opacity': '0', 'transform': transform(x, y+5, .35)}
        lone_tile(draw, p, [(t+.5*s, {}), (t+.56*s, {'transform': transform(x, y)}),
                            (t+.78*s, {'transform': transform(x, 31)}), (t+s, {'transform': transform(chute, 31)}),
                            (t+s+.18, {'transform': transform(chute, 190, .7)}), (t+s+.26, {'opacity': '0', 'transform': transform(chute, 190, .7)}),
                            (restore, pop), (restore+.04, {**pop, 'opacity': '.45'}), (restore+.4, {})])
        draw.spark(p, t+.53*s, draw.accent)
    place(finish, chute, 22)
    head_frames.append((finish+.4, {'transform': transform(chute, 22), 'opacity': '0'}))
    cable_frames.append((finish+.4, {'transform': f'translate({num(chute)}px,15px) rotate(0deg) scale(1,7)', 'opacity': '0'}))
    cable = f'<rect x="-.6" y="0" width="1.2" height="1" fill="{draw.muted}"/>'
    prongs = (f'<rect x="-6" y="-3" width="12" height="5" rx="2" fill="{draw.accent}"/>'
              f'<path d="M-6 2L-8 10M6 2L8 10" stroke="{draw.accent}" stroke-width="2" stroke-linecap="round" fill="none"/>')
    draw.parts.append(draw.animated(cable, cable_frames, {'transform': f'translate({num(chute)}px,15px) rotate(0deg) scale(1,7)', 'opacity': '0'}))
    draw.parts.append(draw.animated(prongs, head_frames, {'transform': transform(chute, 22), 'opacity': '0'}))
    draw.parts.append(caption('CLAW MACHINE / GRAB EVERY DAY'))
    return draw


HEIGHT_PX = {1: 10, 2: 20, 3: 30, 4: 44}
ISO_GREEN = {'dark': ('#1b7a49', '#22a75d', '#3fd07a', '#8dffb0'), 'light': ('#86dca0', '#45c172', '#1f9d4a', '#0d6b2f')}
ISO_GROUND = {
    'dark': dict(sky=('#070b1a', '#0a1128', '#0e1834', '#131f42', '#18274f', '#1d2f5c'), plate='#25314f', plot='#2e3c60',
                 street='#111828', side_l='#182038', side_r='#0f1628', text='#e8ecff', dim='#8b95c9', line='#c9d1f5',
                 tree=('#2f8f4e', '#3aa85c', '#236b3d'), cloud='.10'),
    'light': dict(sky=('#cfe8ff', '#dbeeff', '#e8f4ff', '#f2f8ff', '#f8fbff', '#ffffff'), plate='#c4d4ea', plot='#e3ecf8',
                  street='#9fb0c8', side_l='#9db0cc', side_r='#8496b4', text='#141b34', dim='#56608f', line='#ffffff',
                  tree=('#5cbf7a', '#43a862', '#348a4e'), cloud='.85'),
}
CAR_COLOURS = ('#ff7a59', '#59f3ff', '#ffd166', '#b98cff')


def itext(x, y, value, size, fill, weight='400', anchor='start', spacing=0):
    return (f'<text x="{num(x)}" y="{num(y)}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" letter-spacing="{spacing}" style="fill:{fill}">{escape(str(value))}</text>')


def cube_rel(iso, hx, hy, height, colours):
    """A shaded box centred on the origin of its own group: (top, left, right) path strings."""
    top, left, right = colours
    r = lambda gx, gy, z: iso.rel(gx, gy, z, 0, 0)
    return (f'<path d="{iso.poly([r(-hx, -hy, height), r(hx, -hy, height), r(hx, hy, height), r(-hx, hy, height)])}" fill="{top}"/>'
            f'<path d="{iso.poly([r(-hx, hy, 0), r(hx, hy, 0), r(hx, hy, height), r(-hx, hy, height)])}" fill="{left}"/>'
            f'<path d="{iso.poly([r(hx, hy, 0), r(hx, -hy, 0), r(hx, -hy, height), r(hx, hy, height)])}" fill="{right}"/>')


def mini_cube(x, y, size, height, colours):
    top, left, right = colours
    dx, dy = size*.866, size*.5
    return (f'<path d="M{num(x)} {num(y-height-dy)}L{num(x+dx)} {num(y-height)}L{num(x)} {num(y-height+dy)}L{num(x-dx)} {num(y-height)}z" fill="{top}"/>'
            f'<path d="M{num(x-dx)} {num(y-height)}L{num(x)} {num(y-height+dy)}V{num(y+dy)}L{num(x-dx)} {num(y)}z" fill="{left}"/>'
            f'<path d="M{num(x+dx)} {num(y-height)}L{num(x)} {num(y-height+dy)}V{num(y+dy)}L{num(x+dx)} {num(y)}z" fill="{right}"/>')


def iso_stage(draw, iso, cal, model, theme, cells):
    """Sky, clouds, celestial body, the four-district plate with streets, plots and trees."""
    g = ISO_GROUND[theme]
    dark = theme == 'dark'
    w, h = draw.width, CANVAS_H
    band = h/len(g['sky'])
    for i, colour in enumerate(g['sky']):
        draw.parts.append(f'<rect x="0" y="{num(i*band)}" width="{w}" height="{num(band+1)}" fill="{colour}"/>')
    if dark:
        for sx, sy, phase in model['stars']:
            star = f'<circle cx="{num(20+sx*(w-40))}" cy="{num(10+sy*130)}" r="1.1" fill="#e8ecff"/>'
            draw.parts.append(draw.animated(star, [(phase+1, {'opacity': '.25'}), (phase+2, {'opacity': '1'}), (phase+3, {'opacity': '.25'})], {'opacity': '.6'}))
        draw.parts.append(f'<circle cx="{w-230}" cy="44" r="17" fill="#e8ecff"/><circle cx="{w-236}" cy="39" r="3.2" fill="#b7c0e6"/>'
                          f'<circle cx="{w-224}" cy="50" r="2.4" fill="#b7c0e6"/><circle cx="{w-228}" cy="36" r="1.8" fill="#b7c0e6"/>')
    else:
        draw.parts.append(f'<circle cx="{w-230}" cy="44" r="18" fill="#ffc94d"/><circle cx="{w-230}" cy="44" r="26" fill="#ffc94d" opacity=".25"/>')
    span = draw.duration
    for k, (cx, cy) in enumerate(model['clouds']):
        y = 26+cy*110
        cloud = ('<ellipse cx="0" cy="0" rx="26" ry="9"/><ellipse cx="-14" cy="-6" rx="15" ry="9"/><ellipse cx="10" cy="-9" rx="17" ry="11"/>')
        cloud = f'<g fill="#ffffff" opacity="{g["cloud"]}">{cloud}</g>'
        start = cx*span*.5
        frames = [(start+.1, {'transform': f'translate(-90px,{num(y)}px)', 'opacity': '0'}), (start+2.5, {'transform': f'translate(-60px,{num(y)}px)', 'opacity': '1'}),
                  (min(span-.5, start+span*.55), {'transform': f'translate({w+60}px,{num(y)}px)', 'opacity': '1'}),
                  (min(span-.3, start+span*.55+2), {'transform': f'translate({w+90}px,{num(y)}px)', 'opacity': '0'})]
        draw.parts.append(draw.animated(cloud, frames, {'transform': f'translate(-90px,{num(y)}px)', 'opacity': '0'}))
    gx, gy, block = iso.gx, iso.gy, iso.block
    a, b, c, d = iso.p(0, 0), iso.p(gx, 0), iso.p(gx, gy), iso.p(0, gy)
    below = lambda pt: (pt[0], pt[1]+SLAB)
    draw.parts.append(f'<path d="{iso.poly([d, c, below(c), below(d)])}" fill="{g["side_l"]}"/>')
    draw.parts.append(f'<path d="{iso.poly([c, b, below(b), below(c)])}" fill="{g["side_r"]}"/>')
    draw.parts.append(f'<path d="{iso.diamond(0, 0, gx, gy)}" fill="{g["plate"]}"/>')
    draw.parts.append(f'<path d="{iso.diamond(block, 0, block+GAP, gy)}{iso.diamond(0, ROWS, gx, ROWS+GAP)}" fill="{g["street"]}"/>')
    plots = ''.join(iso.diamond(px+.05, py+.05, px+.95, py+.95) for px, py in cells.values())
    draw.parts.append(f'<path d="{plots}" fill="{g["plot"]}"/>')
    dashes = ''.join(f'M{num(iso.p(block+1, k+.2)[0])} {num(iso.p(block+1, k+.2)[1])}L{num(iso.p(block+1, k+.6)[0])} {num(iso.p(block+1, k+.6)[1])}'
                     for k in range(gy) if not ROWS <= k < ROWS+GAP)
    dashes += ''.join(f'M{num(iso.p(k+.2, ROWS+1)[0])} {num(iso.p(k+.2, ROWS+1)[1])}L{num(iso.p(k+.6, ROWS+1)[0])} {num(iso.p(k+.6, ROWS+1)[1])}'
                      for k in range(gx) if not block <= k < block+GAP)
    draw.parts.append(f'<path d="{dashes}" stroke="{g["line"]}" stroke-width="1.2" opacity=".55" fill="none"/>')
    return g


def iso_hud(draw, iso, cal, g, theme):
    w = draw.width
    colours = [shades(c) for c in ISO_GREEN[theme]]
    counts = [sum(1 for p in cal.active if cal.grid[p] == level) for level in (1, 2, 3, 4)]
    draw.parts.append(itext(20, 84, 'YEAR IN BLOCKS', 12, g['dim'], '700', spacing=2))
    for i, count in enumerate(counts):
        y = 116+i*32
        draw.parts.append(mini_cube(34, y, 11, HEIGHT_PX[i+1]*.55, colours[i]))
        draw.parts.append(itext(56, y+1, f'LEVEL {i+1}', 11, g['text'], '700'))
        draw.parts.append(itext(56, y+15, f'{count} days', 11, g['dim']))
    levels = [cal.grid[c, r] for c in range(cal.cols) for r in range(7) if (c, r) not in cal.missing]
    week_sums = [sum(cal.grid[c, r] for r in range(7)) for c in range(cal.cols)]
    busiest = max(range(cal.cols), key=lambda c: week_sums[c])
    facts = (('ACTIVE DAYS', len(cal.active)), ('LONGEST STREAK', streak_and_week(levels)), ('BUSIEST WEEK', f'#{busiest+1}'))
    draw.parts.append(itext(w-20, 84, 'CITY STATS', 12, g['dim'], '700', 'end', 2))
    for i, (label, value) in enumerate(facts):
        y = 116+i*38
        draw.parts.append(itext(w-20, y, value, 20, g['text'], '700', 'end'))
        draw.parts.append(itext(w-20, y+14, label, 10, g['dim'], '400', 'end', 1))
    names = ('DISTRICT 1', 'DISTRICT 2', 'DISTRICT 3', 'DISTRICT 4')
    starts, week = [], 0
    for size in quarter_sizes(cal.cols):
        starts.append(week)
        week += size
    for q, start in enumerate(starts):
        label = cal.weeks[start][:7] if cal.weeks else f'week {start+1}'
        draw.parts.append(itext(20, 262+q*17, f'{names[q]}  {label}', 10, g['dim']))


def iso_tree(iso, cell, variant, colours):
    cx, cy = cell[0]+.5, cell[1]+.5
    height = 17+variant*4
    apex = iso.rel(cx, cy, height, cx, cy)
    def base(sx, sy, z=5):
        return iso.rel(cx+sx*.27, cy+sy*.27, z, cx, cy)
    crown_l = iso.poly([base(-1, 1), base(1, 1), apex])
    crown_r = iso.poly([base(1, 1), base(1, -1), apex])
    crown_b = iso.poly([base(-1, -1), base(-1, 1), apex])
    trunk = iso.poly([iso.rel(cx-.06, cy+.06, 0, cx, cy), iso.rel(cx+.06, cy+.06, 0, cx, cy), iso.rel(cx+.06, cy+.06, 6, cx, cy), iso.rel(cx-.06, cy+.06, 6, cx, cy)])
    x, y = iso.p(cx, cy)
    return (f'<g transform="translate({num(x)} {num(y)})"><path d="{trunk}" fill="#6b4a2f"/>'
            f'<path d="{crown_b}" fill="{colours[2]}"/><path d="{crown_r}" fill="{colours[2]}"/><path d="{crown_l}" fill="{colours[0]}"/></g>')


def isocity(cal, model, theme):
    order, n = model['order'], len(model['order'])
    cells = layout(cal.cols)
    sweep = min(11, 3+n*.09)
    rise0 = 1.2
    hold0 = rise0+sweep+1.6
    fall0 = hold0+13
    finish = fall0+sweep*.8+1.2
    draw = Drawing(cal, 'isocity', theme, finish+1.5, CANVAS_H)
    iso = Iso(cal.cols, draw.width)
    g = iso_stage(draw, iso, cal, model, theme, cells)
    palette = ISO_GREEN[theme]
    for cell, variant in sorted(model['trees'], key=lambda t: sum(cells[t[0]])):
        draw.parts.append(iso_tree(iso, cells[cell], variant, g['tree']))
    # Traffic: cars patrol both streets, driving on the right-hand lane of each direction.
    for car in model['cars']:
        along_x = car['axis'] == 'x'
        length = (iso.gx+4) if along_x else (iso.gy+4)
        trip = length/car['speed']
        lane = .27*car['dir']
        cross = (ROWS+1+lane) if along_x else (iso.block+1+lane)
        def at(pos):
            gx, gy = (pos, cross) if along_x else (cross, pos)
            x, y = iso.p(gx, gy)
            return f'translate({num(x)}px,{num(y)}px) rotate(0deg) scale(1)'
        start_pos, end_pos = (-2, length-2) if car['dir'] == 1 else (length-2, -2)
        frames, t = [], car['phase']
        while t+trip < draw.duration-.5:
            frames += [(t, {'transform': at(start_pos), 'opacity': '0'}), (t+.5, {'transform': at(start_pos), 'opacity': '1'}),
                       (t+trip-.5, {'transform': at(end_pos), 'opacity': '1'}), (t+trip, {'transform': at(end_pos), 'opacity': '0'})]
            t += trip+1.5+car['phase']*.3
        if not frames:
            continue
        body = cube_rel(iso, .42 if along_x else .2, .2 if along_x else .42, 5, shades(CAR_COLOURS[car['colour']]))
        draw.parts.append(draw.animated(body, frames, {'transform': at(start_pos), 'opacity': '0'}))
    towers = {p: (cells[p], level, bits) for p, level, bits in zip(order, model['levels'], model['windows'])}
    rank = {p: i for i, p in enumerate(order)}
    hx = hy = .38
    for p in sorted(towers, key=lambda q: (sum(towers[q][0]), towers[q][0][0])):
        (gx, gy), level, bits = towers[p]
        cx, cy = gx+.5, gy+.5
        height = HEIGHT_PX[level]
        top_c, left_c, right_c = shades(palette[level-1])
        rise = rise0+rank[p]/max(1, n)*sweep
        fall = fall0+rank[p]/max(1, n)*sweep*.8
        curve = [(rise, .001), (rise+.6, 1.16), (rise+1.0, 1), (fall, 1), (fall+.8, .001)]
        left = (f'<path d="{UNIT_FACE}" fill="{left_c}"/><rect x="0" y="-1" width="1" height="1" fill="none" data-day="{p[0]},{p[1]}"/>')
        right = f'<path d="{UNIT_FACE}" fill="{right_c}"/>'
        top = f'<path d="{iso.top_local(cx, cy, hx, hy)}" fill="{top_c}"/>'
        draw.parts.append(draw.animated(left, [(t, {'transform': iso.left_xf(cx, cy, hx, hy, height*s)}) for t, s in curve],
                                        {'transform': iso.left_xf(cx, cy, hx, hy, .001)}))
        draw.parts.append(draw.animated(right, [(t, {'transform': iso.right_xf(cx, cy, hx, hy, height*s)}) for t, s in curve],
                                        {'transform': iso.right_xf(cx, cy, hx, hy, .001)}))
        draw.parts.append(draw.animated(top, [(t, {'transform': iso.top_xf(cx, cy, height*s)}) for t, s in curve],
                                        {'transform': iso.top_xf(cx, cy, 0)}))
        lit = rise+1.3
        for face, sign in (('L', 30), ('R', -30)):
            panes, row = [], 0
            for z in range(3, height-1, 5):
                for k, frac in enumerate((.22, .62)):
                    if bits >> ((row*2+k+(0 if face == 'L' else 8)) % 16) & 1:
                        panes.append(f'M{num(2*hx*DX*frac)} {-z}h2.4v-2.6h-2.4z')
                row += 1
            if not panes:
                continue
            origin = iso.p(cx-hx, cy+hy) if face == 'L' else iso.p(cx+hx, cy+hy)
            base = f'translate({num(origin[0])}px,{num(origin[1])}px) skewY({sign}deg)'
            glow = '#ffd166' if theme == 'dark' else '#fff3b0'
            draw.parts.append(draw.animated(f'<path d="{"".join(panes)}" fill="{glow}"/>', [
                (lit, {'transform': base, 'opacity': '0'}), (lit+.25, {'transform': base, 'opacity': '1'}),
                (lit+5+(bits % 5), {'transform': base, 'opacity': '.5'}), (lit+5.5+(bits % 5), {'transform': base, 'opacity': '1'}),
                (fall, {'transform': base, 'opacity': '1'}), (fall+.3, {'transform': base, 'opacity': '0'})],
                {'transform': base, 'opacity': '0'}))
        if level == 4:
            beacon = f'<circle r="1.8" fill="#ff5c5c"/>'
            bx, by = iso.p(cx, cy, height)
            frames = []
            for j in range(6):
                frames += [(lit+j*1.2, {'transform': f'translate({num(bx)}px,{num(by)}px)', 'opacity': '1'}),
                           (lit+j*1.2+.6, {'transform': f'translate({num(bx)}px,{num(by)}px)', 'opacity': '.15'})]
            frames.append((fall, {'transform': f'translate({num(bx)}px,{num(by)}px)', 'opacity': '0'}))
            draw.parts.append(draw.animated(beacon, frames, {'transform': f'translate({num(bx)}px,{num(by)}px)', 'opacity': '0'}))
    iso_hud(draw, iso, cal, g, theme)
    return draw


def isodrop(cal, model, theme):
    drops = model['drops']
    cells = layout(cal.cols)
    step = min(.12, 42/max(1, len(drops)))
    first = 1.4
    landed = first+len(drops)*step+.9
    pulse0 = landed+1.2
    fall0 = pulse0+6.5
    finish = fall0+3.4
    draw = Drawing(cal, 'isodrop', theme, finish+1.5, CANVAS_H)
    iso = Iso(cal.cols, draw.width)
    g = iso_stage(draw, iso, cal, model, theme, cells)
    palette = [shades(c) for c in ISO_GREEN[theme]]
    for cell, variant in sorted(model['trees'], key=lambda t: sum(cells[t[0]])):
        draw.parts.append(iso_tree(iso, cells[cell], variant, g['tree']))
    max_depth = iso.gx+iso.gy
    hx = hy = .4
    cube_h = 8
    order = sorted(range(len(drops)), key=lambda i: (sum(cells[drops[i][0]]), drops[i][1], i))
    for i in order:
        p, k = drops[i]
        gx, gy = cells[p]
        cx, cy = gx+.5, gy+.5
        x, y = iso.p(cx, cy, k*cube_h)
        rest = f'translate({num(x)}px,{num(y)}px) rotate(0deg) scale(1)'
        at = lambda dy, s=1: f'translate({num(x)}px,{num(y+dy)}px) rotate(0deg) scale({num(s)})'
        land = first+i*step
        depth = (gx+gy)/max_depth
        pulse = pulse0+depth*2.2
        lift = fall0+depth*3
        frames = [(land, {'transform': at(-230), 'opacity': '0'}), (land+.06, {'transform': at(-230), 'opacity': '1'}),
                  (land+.5, {'transform': at(0), 'opacity': '1'}), (land+.62, {'transform': at(-4), 'opacity': '1'}),
                  (land+.74, {'transform': rest, 'opacity': '1'}),
                  (pulse, {'transform': rest, 'opacity': '1'}), (pulse+.22, {'transform': at(-6), 'opacity': '1'}), (pulse+.44, {'transform': rest, 'opacity': '1'}),
                  (lift, {'transform': rest, 'opacity': '1'}), (lift+.7, {'transform': at(-230), 'opacity': '0'})]
        body = cube_rel(iso, hx, hy, cube_h, palette[k])
        if k == 0:
            body += f'<rect x="-1" y="-1" width="1" height="1" fill="none" data-day="{p[0]},{p[1]}"/>'
        draw.parts.append(draw.animated(body, frames, {'transform': at(-230), 'opacity': '0'}))
        if k == 0:
            gxp, gyp = iso.p(cx, cy)
            ring = f'<ellipse rx="1" ry=".5" fill="none" stroke="{g["line"]}" stroke-width="1.2" vector-effect="non-scaling-stroke"/>'
            flat = lambda s: f'translate({num(gxp)}px,{num(gyp)}px) rotate(0deg) scale({num(s)})'
            draw.parts.append(draw.animated(ring, [(land+.5, {'transform': flat(1), 'opacity': '.7'}), (land+1.0, {'transform': flat(15), 'opacity': '0'})],
                                            {'transform': flat(1), 'opacity': '0'}))
    iso_hud(draw, iso, cal, g, theme)
    return draw


RENDERERS = {'bomber': bomber, 'miners': miners, 'link-match': links,
             'portal': portal, 'assembly': assembly, 'minecraft': minecraft, 'lego': lego,
             'fireworks': fireworks, 'domino': domino, 'dust': dust, 'sorter': sorter, 'synth': synth, 'claw': claw,
             'isocity': isocity, 'isodrop': isodrop}


def render(cal: Calendar, scene: str, seed: int, theme='dark', model=None) -> str:
    if theme not in THEMES or scene not in RENDERERS:
        raise ValueError('Unknown theme or SVG scene')
    if not cal.active:
        # A genuinely empty calendar stays empty, rather than inventing obstacles.
        return Drawing(cal, scene, theme, 6, HEIGHTS.get(scene, 216)).document(seed)
    model = PLANNERS[scene](cal, seed) if model is None else model
    return RENDERERS[scene](cal, model, theme).document(seed)
