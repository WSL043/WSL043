"""Small, scriptless animated SVGs: a full heatmap, not a dashboard or GIF wrapper."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from html import escape
import hashlib
import json
from pathlib import Path
from scripts.svg_models import Calendar, PLANNERS, DIRS

THEMES = {
    'dark': ('#0d1117', '#161b22', '#30363d', '#8b949e',
             ('#161b22', '#0e4429', '#006d32', '#26a641', '#39d353')),
    'light': ('#ffffff', '#ebedf0', '#d0d7de', '#57606a',
              ('#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39')),
}
NAMES = {'bomber': 'Heatmap Bomber', 'miners': 'Commit Miners',
         'link-match': 'Contribution Link', 'portal': 'Portal Courier',
         'assembly': 'Magnetic Assembly', 'minecraft': 'Minecraft Block Miner', 'lego': 'LEGO Brick Workshop'}


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


RENDERERS = {'bomber': bomber, 'miners': miners, 'link-match': links,
             'portal': portal, 'assembly': assembly, 'minecraft': minecraft, 'lego': lego}


def render(cal: Calendar, scene: str, seed: int, theme='dark', model=None) -> str:
    if theme not in THEMES or scene not in RENDERERS:
        raise ValueError('Unknown theme or SVG scene')
    if not cal.active:
        # A genuinely empty calendar stays empty, rather than inventing obstacles.
        return Drawing(cal, scene, theme, 6).document(seed)
    model = PLANNERS[scene](cal, seed) if model is None else model
    return RENDERERS[scene](cal, model, theme).document(seed)
