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
         'skyline': 'Isometric Skyline', 'neondrive': 'Neon Drive', 'tunnel': 'Warp Tunnel'}


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
    def __init__(self, cal, scene, theme, duration):
        self.cal, self.scene, self.theme, self.duration = cal, scene, theme, duration
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
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} 216" '
                f'width="{self.width}" height="216" role="img" aria-labelledby="title desc" data-scene="{self.scene}">'
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


def mix(colour, other, amount):
    a = [int(colour[i:i+2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i+2], 16) for i in (1, 3, 5)]
    return '#'+''.join(f'{round(x+(y-x)*amount):02x}' for x, y in zip(a, b))


def depth_samples(far, near, count):
    """Geometrically spaced depths: scale = 1/depth changes by a constant ratio between samples."""
    return [far*(near/far)**(k/count) for k in range(count+1)]


def month_starts(cal):
    names = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')
    result, last = {}, None
    for x, raw in enumerate(cal.weeks):
        month = date.fromisoformat(raw).month
        if month != last:
            result[x] = names[month-1]
            last = month
    return result


def skyline(cal, model, theme):
    dark = theme == 'dark'
    order, windows, n = model['order'], model['windows'], len(model['order'])
    sweep = min(14, 4+n*.1)
    rise0 = 1.5
    hold0 = rise0+sweep+1.3
    fall0 = hold0+10
    finish = fall0+sweep*.8+1.2
    draw = Drawing(cal, 'skyline', theme, finish+1.5)
    w = draw.width
    ground = {p: (24+16*p[0], 68+17*p[1]) for p in cal.grid if p not in cal.missing}
    # Sky: banded dusk, stars, and a moon (or sun by day).
    sky = ('#0b1330', '#101a3d', '#172250', '#22306a') if dark else ('#bfe3ff', '#d3ecff', '#e6f4ff', '#f5faff')
    for i, colour in enumerate(sky):
        draw.parts.append(f'<rect x="0" y="{i*17}" width="{w}" height="18" fill="{colour}"/>')
    draw.parts.append(f'<rect x="0" y="66" width="{w}" height="150" fill="{"#0f1626" if dark else "#dfe9f5"}"/>')
    for sx, sy, phase in model['stars']:
        star = f'<circle cx="{num(30+sx*(w-60))}" cy="{num(6+sy*40)}" r="1" fill="{"#e8ecff" if dark else "#ffffff"}"/>'
        draw.parts.append(draw.animated(star, [(phase+1, {'opacity': '.25'}), (phase+2, {'opacity': '1'}), (phase+3, {'opacity': '.25'})], {'opacity': '.6'}))
    moon = '#e8ecff' if dark else '#ffd166'
    draw.parts.append(f'<circle cx="{w-70}" cy="30" r="11" fill="{moon}"/><circle cx="{w-74}" cy="27" r="2.4" fill="{mix(moon, "#8b95c9", .35)}"/>'
                      f'<circle cx="{w-66}" cy="34" r="1.8" fill="{mix(moon, "#8b95c9", .35)}"/>')
    plate = ''.join(f'M{x-6} {y}h12l4 -4h-12z' for x, y in ground.values())
    draw.parts.append(f'<path d="{plate}" fill="{draw.empty}"/>')
    for i, (p, level, bits) in enumerate(zip(order, model['levels'], windows)):
        x, y = ground[p]
        height = level*9.5
        rise = rise0+i/max(1, n)*sweep
        fall = fall0+i/max(1, n)*sweep*.8
        front = draw.green[level]
        squash = lambda s: f'translate({num(x)}px,{num(y)}px) rotate(0deg) scale(1,{num(max(.001, s))})'
        base_scale = {'transform': squash(.001)}
        curve = [(rise, .001), (rise+.7, 1.14), (rise+1.05, 1), (fall, 1), (fall+.8, .001)]
        draw.parts.append(draw.animated(
            f'<rect x="-6" y="{num(-height)}" width="12" height="{num(height)}" fill="{front}" data-day="{p[0]},{p[1]}"/>',
            [(t, {'transform': squash(s)}) for t, s in curve], base_scale))
        draw.parts.append(draw.animated(
            f'<path d="M6 0L10 -4V{num(-height-4)}L6 {num(-height)}z" fill="{mix(front, "#000000", .38)}"/>',
            [(t, {'transform': squash(s)}) for t, s in curve], base_scale))
        top = f'<path d="M-6 0H6L10 -4H-2z" fill="{mix(front, "#ffffff", .32)}"/>'
        top_at = lambda s: f'translate({num(x)}px,{num(y-height*s)}px) rotate(0deg) scale(1)'
        draw.parts.append(draw.animated(top, [(t, {'transform': top_at(s)}) for t, s in curve], {'transform': top_at(0)}))
        panes, row = [], 0
        for yy in range(-4, int(-height+2), -5):
            for k, xx in enumerate((-4, 1)):
                if bits >> ((row*2+k) % 12) & 1:
                    panes.append(f'M{xx} {yy}h2.6v-2.6h-2.6z')
            row += 1
        if panes:
            lit = rise+1.4
            body = f'<path d="{"".join(panes)}" fill="#ffd166"/>'
            at = {'transform': f'translate({num(x)}px,{num(y)}px)'}
            draw.parts.append(draw.animated(body, [(lit, {**at, 'opacity': '0'}), (lit+.25, {**at, 'opacity': '1'}),
                                                   (lit+5+(bits % 5), {**at, 'opacity': '.45'}), (lit+5.6+(bits % 5), {**at, 'opacity': '1'}),
                                                   (fall, {**at, 'opacity': '1'}), (fall+.3, {**at, 'opacity': '0'})],
                                             {**at, 'opacity': '0'}))
    for k, phase in enumerate(model['beams']):
        bx = w*(.22+.56*k)
        beam = f'<path d="M0 0L-12 -120H12z" fill="#ffffff" opacity="{".13" if dark else ".35"}"/>'
        frames = [(hold0+j*.5, {'transform': f'translate({num(bx)}px,164px) rotate({num(30*math.sin(phase+j*.55*(1 if k else -1)))}deg)', 'opacity': '1'})
                  for j in range(int(9/.5)+1)]
        base = {'transform': f'translate({num(bx)}px,164px) rotate(0deg)', 'opacity': '0'}
        draw.parts.append(draw.animated(beam, [(hold0-.4, base)]+frames+[(fall0, {**frames[-1][1], 'opacity': '0'})], base))
    d = model['plane']
    start, end = (-20, w+20) if d == 1 else (w+20, -20)
    plane = ('<ellipse rx="8" ry="2.2" fill="#c9d1d9"/><path d="M-6 0L-11 -5L-8 0z" fill="#c9d1d9"/>'
             '<circle cx="9" cy="0" r="1.3" fill="#ff5c5c"/>')
    fly0 = hold0+1
    draw.parts.append(draw.animated(plane, [
        (fly0, {'transform': f'translate({start}px,26px) scale({d},1)', 'opacity': '1'}),
        (fly0+7, {'transform': f'translate({end}px,20px) scale({d},1)', 'opacity': '1'}),
        (fly0+7.1, {'transform': f'translate({end}px,20px) scale({d},1)', 'opacity': '0'})],
        {'transform': f'translate({start}px,26px) scale({d},1)', 'opacity': '0'}))
    draw.parts.append(caption('SKYLINE / BUILD THE YEAR'))
    return draw


def neondrive(cal, model, theme):
    cols, dark = cal.cols, theme == 'dark'
    v, dfar, dnear = model['speed'], 15., .8
    end = .05+(cols-1+dfar-dnear)/v
    draw = Drawing(cal, 'neondrive', theme, end+2)
    w = draw.width
    vpx, vpy, focal, cam_h = w/2, 90, 170., .62
    pink, cyan = ('#ff2e97', '#22d3ee') if dark else ('#c0166f', '#0a8fb0')
    p1, p2, p3, p4 = model['phases']

    def sway(t):
        return .38*math.sin(6.2832*t/9+p1)+.17*math.sin(6.2832*t/5.3+p2)

    sky = ('#090418', '#150a35', '#2a0f52', '#4a1268', '#7a1a78', '#b02a7d') if dark else ('#ffd6ec', '#ffddef', '#ffe4d6', '#ffecc7', '#fff3cf', '#fff8dd')
    band = vpy/len(sky)
    for i, colour in enumerate(sky):
        draw.parts.append(f'<rect x="0" y="{num(i*band)}" width="{w}" height="{num(band+1)}" fill="{colour}"/>')
    for sx, sy, phase in model['stars']:
        star = f'<circle cx="{num(sx*w)}" cy="{num(sy*44+6)}" r="1" fill="#ffffff"/>'
        draw.parts.append(draw.animated(star, [(phase+1, {'opacity': '.3'}), (phase+2, {'opacity': '1'}), (phase+3, {'opacity': '.3'})], {'opacity': '.7' if dark else '.0'}))
    sun_r, sun_y = 38, vpy-4
    draw.parts.append(f'<circle cx="{num(vpx)}" cy="{sun_y}" r="{sun_r}" fill="{"#ff9f45" if dark else "#ffb347"}"/>')
    for k in range(7):
        dy = 4+k*5
        half = math.sqrt(max(0, sun_r**2-dy**2))
        draw.parts.append(f'<rect x="{num(vpx-half)}" y="{sun_y+dy}" width="{num(2*half)}" height="{num(1+k*.55)}" fill="{sky[-1]}"/>')
    sums = [sum(cal.grid[c, r] for r in range(7)) for c in range(cols)]
    peak = max(max(sums), 1)
    ridge = ''.join(f'L{24+16*c} {num(vpy-4-24*sums[c]/peak)}' for c in range(cols))
    draw.parts.append(f'<path d="M0 {vpy}L0 {vpy-4}{ridge}L{w} {vpy-4}L{w} {vpy}z" fill="{"#1a0838" if dark else "#e9c9f7"}" stroke="{pink}" stroke-width="1.2" stroke-linejoin="round"/>')
    draw.parts.append(f'<rect x="0" y="{vpy}" width="{w}" height="{216-vpy}" fill="{"#0a0420" if dark else "#f7e9ff"}"/>')
    # Ground grid: lateral camera sway is an exact horizontal shear about the horizon.
    bottom = focal*cam_h/(216-vpy)
    lines = ''.join(f'M0 0L{num(focal*x/bottom)} {216-vpy}' for x in range(-9, 10))
    road = f'M{num(-3.5*focal/bottom)} {216-vpy}L0 0L{num(3.5*focal/bottom)} {216-vpy}z'
    times = [(i+1)*.5 for i in range(int((end+1.5)/.5))]
    shear = [math.degrees(math.atan2(-sway(t), cam_h)) for t in times]
    grid_body = (f'<path d="{road}" fill="{pink}" opacity=".07"/><path d="{lines}" stroke="{pink}" stroke-width="1" opacity=".55" fill="none"/>')
    frames = [(t, {'transform': f'translate({num(vpx)}px,{vpy}px) skewX({num(a)}deg)'}) for t, a in zip(times, shear)]
    rest = {'transform': f'translate({num(vpx)}px,{vpy}px) skewX({num(shear[0])}deg)'}
    draw.parts.append(draw.animated(grid_body, frames+[(draw.duration-.02, rest)], rest))
    ds = depth_samples(dfar, dnear, 22)
    for k in range(cols+int(dfar)+1):
        line = f'<rect x="{-w}" y="0" width="{3*w}" height="1" fill="{pink}"/>'
        frames = []
        for d in ds:
            t = .05+(k+dfar-d)/v
            frames.append((t, {'transform': f'translate(0px,{num(vpy+focal*cam_h/d)}px) rotate(0deg) scale(1,{num(min(2.6, max(.7, 2.4/d)))})',
                               'opacity': num(max(0, min(.9, (dfar-d)/4, (d-dnear)/.5)))}))
        if frames[-1][0] < 0 or frames[0][0] > end+1.9:
            continue
        frames = [(min(t, end+1.9), pr) for t, pr in frames]
        draw.parts.append(draw.animated(line, frames, {'transform': f'translate(0px,{vpy}px) rotate(0deg) scale(1,.7)', 'opacity': '0'}))
    signs = month_starts(cal)
    items = [('sign', c) for c in signs]+[('tile', p) for p in cal.active]
    for kind, item in sorted(items, key=lambda it: -(it[1] if it[0] == 'sign' else it[1][0])):
        c = item if kind == 'sign' else item[0]
        if kind == 'sign':
            x_world = -4.4
            body = (f'<path d="M0 0V{-.75*focal}" stroke="{cyan}" stroke-width="5"/>'
                    f'<text x="0" y="{-.82*focal}" font-family="{FONT}" font-size="{.42*focal}" font-weight="700" fill="{cyan}" text-anchor="middle" style="fill:{cyan}">{signs[c]}</text>')
        else:
            x_world = item[1]-3
            level = cal.grid[item]
            half, hgt = .36*focal, .46*focal
            colour = mix(draw.green[level], '#7dffb3', .3) if dark else draw.green[level]
            body = (f'<rect x="{num(-half-9)}" y="{num(-hgt-9)}" width="{num(2*half+18)}" height="{num(hgt+9)}" rx="10" fill="{cyan}" opacity=".22"/>'
                    f'<rect x="{num(-half)}" y="{num(-hgt)}" width="{num(2*half)}" height="{num(hgt)}" fill="{colour}" stroke="{cyan}" stroke-width="5" data-day="{item[0]},{item[1]}"/>'
                    f'<path d="M{num(-half)} {num(-hgt)}l7 -14h{num(2*half-14)}l7 14z" fill="{mix(colour, "#ffffff", .35)}"/>')
        frames = []
        for d in ds:
            t = .05+(c+dfar-d)/v
            cx = sway(t)
            appear = max(0, min(1, (dfar-d)/4))
            leave = max(0, min(1, (d-.8)/.35)) if d < 1.15 else 1
            frames.append((t, {'transform': f'translate({num(vpx+focal*(x_world-cx)/d)}px,{num(vpy+focal*cam_h/d)}px) rotate(0deg) scale({num(1/d)})',
                               'opacity': num(min(appear, leave))}))
        draw.parts.append(draw.animated(body, frames, {'transform': f'translate({vpx}px,{vpy}px) rotate(0deg) scale(.05)', 'opacity': '0'}))
    # Retro car, seen from behind; it leans into the sway.
    car = (f'<rect x="-30" y="-9" width="60" height="12" rx="4" fill="{pink}"/>'
           f'<path d="M-20 -9L-13 -20H13L20 -9z" fill="{mix(pink, "#000000", .35)}"/>'
           '<rect x="-27" y="-7" width="11" height="5" rx="2" fill="#ff3b3b"/><rect x="16" y="-7" width="11" height="5" rx="2" fill="#ff3b3b"/>'
           '<rect x="-27" y="3" width="10" height="5" rx="1.5" fill="#111"/><rect x="17" y="3" width="10" height="5" rx="1.5" fill="#111"/>')
    tilt = [(t, {'transform': f'translate({num(vpx+sway(t)*-3)}px,198px) rotate({num(-sway(t)*3)}deg)'}) for t in times]
    rest_car = dict(tilt[0][1])
    draw.parts.append(draw.animated(car, tilt+[(draw.duration-.02, rest_car)], rest_car))
    draw.parts.append(caption('NEON DRIVE / CRUISE THE YEAR'))
    return draw


def tunnel(cal, model, theme):
    cols, dark = cal.cols, theme == 'dark'
    v, dfar, dnear, steps = model['speed'], 18., .34, 18
    end = .05+(cols-1+dfar-dnear)/v
    draw = Drawing(cal, 'tunnel', theme, end+2)
    w = draw.width
    cxs, cys, radius, focal = w/2, 106, 62., 2.1
    a1, a2, a3, a4, a5, a6 = model['phases']
    if not dark:
        draw.parts.append(f'<rect x="0" y="0" width="{w}" height="216" fill="#0d1230"/>')
    else:
        draw.parts.append(f'<rect x="0" y="0" width="{w}" height="216" fill="#05070f"/>')

    def cam(t):
        return (26*math.sin(6.2832*t/11+a1)+12*math.sin(6.2832*t/4.7+a2),
                18*math.sin(6.2832*t/8.3+a3)+9*math.sin(6.2832*t/3.9+a4),
                7*math.sin(6.2832*t/13+a5)+3*math.sin(6.2832*t/5.1+a6))
    palette = (draw.cyan, draw.accent, '#b98cff', '#7dff9b', '#ff8fa3')
    signs = month_starts(cal)
    # Stars streak outward from the vanishing point in repeating cycles.
    for angle, r0, cycle, phase in model['stars']:
        ca, sa = math.cos(angle), math.sin(angle)
        frames, t = [], .1+phase*cycle
        while t+cycle < end+1.9:
            for u, op in ((0, 0), (.35, .55), (.75, .95), (1, 0)):
                r = r0+(360-r0)*u**2.4
                frames.append((t+u*cycle, {'transform': f'translate({num(cxs+ca*r)}px,{num(cys+sa*r*.62)}px) rotate({num(math.degrees(angle))}deg) scale({num(.4+u*1.6)})', 'opacity': num(op)}))
            t += cycle
        if frames:
            base = {'transform': f'translate({num(cxs)}px,{cys}px) rotate(0deg) scale(.4)', 'opacity': '0'}
            draw.parts.append(draw.animated(f'<rect x="-5" y="-.6" width="10" height="1.2" rx=".6" fill="{"#ffffff"}"/>', frames, base))
    ds = depth_samples(dfar, dnear, steps)
    colour_by_week, current = {}, -1
    for x in range(cols):
        if x in signs:
            current += 1
        colour_by_week[x] = palette[max(current, 0) % len(palette)]
    for c in range(cols-1, -1, -1):
        tint = colour_by_week[c]
        verts = [(radius*math.cos(math.radians(-90+r*360/7)), radius*math.sin(math.radians(-90+r*360/7))) for r in range(7)]
        frame = 'M'+'L'.join(f'{num(x)} {num(y)}' for x, y in verts)+'z'
        spokes = ''.join(f'M{num(x)} {num(y)}L{num(x*.8)} {num(y*.8)}' for x, y in verts)
        body = [f'<path d="{frame}" fill="none" stroke="{tint}" stroke-width="{4 if c in signs else 2.4}" stroke-linejoin="round" opacity=".85"/>',
                f'<path d="{spokes}" stroke="{tint}" stroke-width="1.6" opacity=".45" fill="none"/>']
        for r, (x, y) in enumerate(verts):
            if (c, r) in cal.missing:
                continue
            angle = -90+r*360/7+90
            level = cal.grid[c, r]
            if level:
                body.append(f'<g transform="translate({num(x)} {num(y)}) rotate({num(angle)})">'
                            f'<rect x="-13" y="-13" width="26" height="26" rx="5" fill="{tint}" opacity=".25"/>'
                            f'<rect x="-9" y="-9" width="18" height="18" rx="2.5" fill="{draw.green[level]}" stroke="{tint}" stroke-width="1.6" data-day="{c},{r}"/></g>')
            else:
                body.append(f'<rect x="{num(x-3)}" y="{num(y-3)}" width="6" height="6" rx="1" fill="{tint}" opacity=".4"/>')
        if c in signs:
            body.append(f'<text x="0" y="{-radius-14}" font-family="{FONT}" font-size="15" font-weight="700" fill="{tint}" text-anchor="middle" style="fill:{tint}">{signs[c]}</text>')
        frames = []
        for d in ds:
            t = .05+(c+dfar-d)/v
            camx, camy, roll = cam(t)
            s = focal/d
            rad = math.radians(roll)
            tx = cxs-s*(camx*math.cos(rad)-camy*math.sin(rad))
            ty = cys-s*(camx*math.sin(rad)+camy*math.cos(rad))
            appear = max(0, min(1, (dfar-d)/6))
            leave = max(0, min(1, (d-dnear)/.3)) if d < .65 else 1
            frames.append((t, {'transform': transform(tx, ty, s, roll), 'opacity': num(min(appear, leave))}))
        draw.parts.append(draw.animated(''.join(body), frames, {'transform': transform(cxs, cys, .05, 0), 'opacity': '0'}))
    draw.parts.append(caption('WARP / FLY THROUGH THE YEAR'))
    return draw


RENDERERS = {'bomber': bomber, 'miners': miners, 'link-match': links,
             'portal': portal, 'assembly': assembly, 'minecraft': minecraft, 'lego': lego,
             'fireworks': fireworks, 'domino': domino, 'dust': dust, 'sorter': sorter, 'synth': synth, 'claw': claw,
             'skyline': skyline, 'neondrive': neondrive, 'tunnel': tunnel}


def render(cal: Calendar, scene: str, seed: int, theme='dark', model=None) -> str:
    if theme not in THEMES or scene not in RENDERERS:
        raise ValueError('Unknown theme or SVG scene')
    if not cal.active:
        # A genuinely empty calendar stays empty, rather than inventing obstacles.
        return Drawing(cal, scene, theme, 6).document(seed)
    model = PLANNERS[scene](cal, seed) if model is None else model
    return RENDERERS[scene](cal, model, theme).document(seed)
