"""Small, scriptless animated SVGs: a full heatmap, not a dashboard or GIF wrapper."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from html import escape
import hashlib
import json
import math
import random
from pathlib import Path
from scripts.svg_models import Calendar, PLANNERS

THEMES = {
    'dark': ('#0d1117', '#161b22', '#30363d', '#8b949e',
             ('#161b22', '#0e4429', '#006d32', '#26a641', '#39d353')),
    'light': ('#ffffff', '#ebedf0', '#d0d7de', '#57606a',
              ('#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39')),
}
NAMES = {'minecraft': 'Minecraft Block Miner', 'lego': 'LEGO Brick Workshop',
         'fireworks': 'Firework Show', 'domino': 'Domino Run', 'dust': 'Pixel Dust',
         'sorter': 'Level Sorter', 'synth': 'Heatmap Synth', 'claw': 'Claw Machine'}


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
        self.css, self.parts, self.tracks, self.backdrop = [], [], [], []

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
                ''.join(self.backdrop)+self.static_grid()+''.join(self.parts)+'</g></svg>')


def mc_block(colour):
    """A 12x12 grass block: coloured grass cap, dirt body with pebbles."""
    return (f'<rect x="-6" y="-6" width="12" height="12" fill="#7d5233"/>'
            '<rect x="-4" y="1" width="3" height="2" fill="#a06e42"/><rect x="1" y="3" width="3" height="2" fill="#a06e42"/>'
            '<rect x="2" y="-1" width="2" height="2" fill="#65401f"/><rect x="-5" y="4" width="2" height="2" fill="#65401f"/>'
            f'<rect x="-6" y="-6" width="12" height="4" fill="{colour}"/><rect x="-6" y="-2" width="2" height="2" fill="{colour}"/>'
            f'<rect x="2" y="-2" width="3" height="2" fill="{colour}"/><rect x="-6" y="-6" width="12" height="1" fill="#ffffff" opacity=".22"/>')


def minecraft(cal, model, theme):
    order, n = model['order'], len(model['order'])
    step = min(.7, 64/max(1, n))
    finish = 2+n*step
    draw = Drawing(cal, 'minecraft', theme, finish+6)
    draw.css.append('svg{shape-rendering:crispEdges}')
    w = draw.width
    dark = theme == 'dark'
    # Sky details in the free strip above the calendar: stars and a square moon by night, pixel clouds by day.
    if dark:
        rng = random.Random(n+7)
        sky = ''.join(f'<rect x="{rng.randint(20, w-20)}" y="{rng.randint(20, 32)}" width="2" height="2"/>' for _ in range(14))
        draw.backdrop.append(f'<g fill="#e8ecff" opacity=".7">{sky}</g><rect x="{w-70}" y="20" width="10" height="10" fill="#e8ecff"/>'
                             f'<rect x="{w-67}" y="23" width="3" height="3" fill="#b7c0e6"/>')
    else:
        clouds = ''.join(f'<rect x="{x}" y="{y}" width="18" height="4"/><rect x="{x+4}" y="{y-3}" width="10" height="3"/>'
                         for x, y in ((90, 26), (380, 30), (640, 25)))
        draw.backdrop.append(f'<g fill="#e6eefc">{clouds}</g><rect x="{w-70}" y="20" width="10" height="10" fill="#ffd166"/>')
    # Grass and dirt strip along the bottom.
    rng = random.Random(n*3+1)
    specks = ''.join(f'<rect x="{x}" y="{rng.randint(211, 214)}" width="{rng.choice((2, 3))}" height="2" fill="{rng.choice(("#65401f", "#a06e42", "#8a8a8a"))}"/>' for x in range(6, w, rng.randint(9, 15)))
    tufts = ''.join(f'<rect x="{x}" y="203" width="2" height="1" fill="#86cf5a"/>' for x in range(4, w, 11))
    draw.parts.append(f'<rect x="0" y="206" width="{w}" height="10" fill="#7d5233"/>{specks}<rect x="0" y="204" width="{w}" height="4" fill="#5fa03c"/>{tufts}')
    # Hotbar: one slot per level with a live stack count, in the familiar bevelled grey.
    counts = [sum(1 for p in cal.active if cal.grid[p] == level) for level in (1, 2, 3, 4)]
    slot, gap = 22, 2
    hx0 = round(w/2-(4*slot+3*gap)/2)
    hy = 172
    draw.parts.append(f'<rect x="{hx0-3}" y="{hy-3}" width="{4*slot+3*gap+6}" height="{slot+6}" fill="#c6c6c6"/>')
    icons = []
    for b in range(4):
        sx = hx0+b*(slot+gap)
        draw.parts.append(f'<rect x="{sx}" y="{hy}" width="{slot}" height="{slot}" fill="#8b8b8b"/><rect x="{sx}" y="{hy}" width="{slot}" height="2" fill="#373737"/>'
                          f'<rect x="{sx}" y="{hy}" width="2" height="{slot}" fill="#373737"/><rect x="{sx}" y="{hy+slot-2}" width="{slot}" height="2" fill="#ffffff"/>'
                          f'<rect x="{sx+slot-2}" y="{hy}" width="2" height="{slot}" fill="#ffffff"/>')
        icons.append((sx+slot/2, hy+slot/2-1))
        draw.parts.append(f'<g transform="translate({num(sx+slot/2)} {num(hy+slot/2-1)}) scale(.95)">{mc_block(draw.green[b+1])}</g>')
    sprite = ('<path d="M-5-17h10v9H-5z" fill="#bc865b"/>'
              '<path d="M-5-19h10v4H-5zM-5-19h3v7H-5z" fill="#513a29"/>'
              '<path d="M-5-8H5V1H-5z" fill="#29b6ad"/>'
              '<path d="M-5 1H-1V8H-5zM1 1H5V8H1z" fill="#6465b5"/>'
              '<path d="M6-5L13-12" stroke="#895e38" stroke-width="2"/>'
              '<path d="M9-14h7v5" stroke="#64eee2" stroke-width="3" fill="none"/>')
    start = xy(order[0])
    base = {'transform': transform(start[0]-12, start[1]+4), 'opacity': '0'}
    moves, changes = [], [[] for _ in range(4)]
    seen = [0, 0, 0, 0]
    for i, p in enumerate(order):
        x, y = int(xy(p)[0]), int(xy(p)[1])
        level = cal.grid[p]
        at = 1.5+i*step
        arrive = at+step+.3
        back = finish+.6+i/max(1, n)*2
        moves += [(at, {'transform': transform(x-12, y+4), 'opacity': '1'}),
                  (at+step*.35, {'transform': transform(x-11, y+3, 1, -12)}),
                  (at+step*.7, {'transform': transform(x-12, y+4)})]
        slot_at = icons[level-1]
        home = {'transform': transform(x, y), 'opacity': '1'}
        body = mc_block(draw.green[level]).replace('<rect x="-6" y="-6" width="12" height="12" fill="#7d5233"/>', f'<rect x="-6" y="-6" width="12" height="12" fill="#7d5233" data-day="{p[0]},{p[1]}"/>', 1)
        draw.parts.append(draw.animated(body, [
            (at, home), (at+step*.55, {'transform': transform(x, y, 1)}), (at+step*.7, {'transform': transform(x, y, 1.1)}),
            (arrive, {'transform': transform(*slot_at, .55), 'opacity': '1'}), (arrive+.06, {'transform': transform(*slot_at, .55), 'opacity': '0'}),
            (back-.06, {'transform': transform(*slot_at, .55), 'opacity': '0'}), (back, {'transform': transform(*slot_at, .55), 'opacity': '1'}),
            (back+.7, home)], home))
        crack = ('<path d="M-1 -5v3h2v3h-3v3h3v3M2 -3h3M-5 2h3" stroke="#0d1117" stroke-width="1" fill="none"/>')
        draw.parts.append(draw.animated(crack, stepped([(at+step*.2, {'transform': transform(x, y), 'opacity': '.4'}), (at+step*.45, {'transform': transform(x, y), 'opacity': '.75'}),
                                                        (at+step*.68, {'transform': transform(x, y), 'opacity': '1'}), (at+step*.72, {'transform': transform(x, y), 'opacity': '0'})]),
                                          {'transform': transform(x, y), 'opacity': '0'}))
        pixel_puff(draw, x, y, at+step*.7, '#a06e42')
        seen[level-1] += 1
        changes[level-1].append((arrive, seen[level-1]))
    # Stack counts follow every pick-up and every re-placement.
    rebuild = [[] for _ in range(4)]
    for i, p in enumerate(order):
        level = cal.grid[p]
        rebuild[level-1].append(finish+.6+i/max(1, n)*2)
    for b in range(4):
        sx, sy = icons[b]
        timeline = changes[b]+[(t, counts[b]-k-1) for k, t in enumerate(rebuild[b])]
        for j, (t, value) in enumerate(timeline):
            end = timeline[j+1][0] if j+1 < len(timeline) else draw.duration-.2
            if value <= 0:
                continue
            label = (f'<text x="{num(sx+slot/2-2)}" y="{num(sy+slot/2+8)}" text-anchor="end" style="fill:#3f3f3f;font-weight:700;font-size:9px">{value}</text>'
                     f'<text x="{num(sx+slot/2-3)}" y="{num(sy+slot/2+7)}" text-anchor="end" style="fill:#ffffff;font-weight:700;font-size:9px">{value}</text>')
            draw.parts.append(draw.animated(label, stepped([(t+.06, {'opacity': '1'}), (end+.06, {'opacity': '0'})]), {'opacity': '0'}))
    moves += [(finish, {'opacity': '0'}), (draw.duration-.1, base)]
    draw.parts.append(draw.animated(sprite, moves, base))
    draw.parts.append('<text x="24" y="197">MINE / COLLECT / REBUILD</text>')
    return draw


def lego(cal, model, theme):
    pieces = model['pieces']
    n = len(pieces)
    step = min(.55, 55/max(1, n))
    back = 3+n*step
    draw = Drawing(cal, 'lego', theme, back+5)
    draw.css.append('svg{shape-rendering:crispEdges}')
    w = draw.width
    dark = theme == 'dark'
    plate, plate_edge = ('#1a2740', '#2c3d5e') if dark else ('#d9e4f4', '#b7c8e2')
    # A studded baseplate under the calendar.
    studs = ''.join(f'<rect x="{x}" y="{y}" width="6" height="2"/>' for x in range(20, w-20, 16) for y in (33, 148))
    draw.backdrop.append(f'<rect x="12" y="30" width="{w-24}" height="124" fill="{plate}"/><rect x="12" y="30" width="{w-24}" height="2" fill="{plate_edge}"/>'
                         f'<rect x="12" y="152" width="{w-24}" height="2" fill="{plate_edge}"/><g fill="{plate_edge}">{studs}</g>')
    # Overhead rail for the hoists and a conveyor belt with scrolling ribs.
    draw.parts.append(f'<rect x="12" y="4" width="{w-24}" height="4" fill="{draw.line}"/><rect x="12" y="4" width="{w-24}" height="1" fill="{draw.muted}" opacity=".6"/>')
    draw.parts.append(f'<rect x="12" y="170" width="{w-24}" height="4" fill="{draw.line}"/><rect x="12" y="192" width="{w-24}" height="4" fill="{draw.line}"/>'
                      f'<rect x="12" y="174" width="{w-24}" height="18" fill="{tint(draw.line, .25, "#000000")}"/>')
    ribs = ''.join(f'<rect x="{x}" y="176" width="3" height="14"/>' for x in range(-16, w+16, 16))
    cycles = int(draw.duration)
    rib_frames = []
    for k in range(cycles):
        rib_frames += [(k+.02, {'transform': 'translate(0px,0px)'}), (k+1.0, {'transform': 'translate(16px,0px)'})]
    draw.parts.append(draw.animated(f'<g fill="{draw.muted}" opacity=".45">{ribs}</g>', rib_frames, {'transform': 'translate(0px,0px)'}))
    for x in (16, w-16):
        draw.parts.append(f'<rect x="{x-5}" y="172" width="10" height="22" fill="{draw.muted}"/><rect x="{x-3}" y="176" width="6" height="14" fill="{draw.line}"/>')
    for i, piece in enumerate(pieces):
        x, y = int(xy(piece[0])[0]), int(xy(piece[0])[1])
        width = (len(piece)-1)*16+12
        colour = draw.green[cal.grid[piece[0]]]
        high, low = tint(colour, .35), tint(colour, .35, '#000000')
        body = (f'<rect x="-6" y="-6" width="{width}" height="12" fill="{colour}"/><rect x="-6" y="-6" width="{width}" height="2" fill="{high}"/>'
                f'<rect x="-6" y="4" width="{width}" height="2" fill="{low}"/><rect x="-6" y="-6" width="1" height="12" fill="{high}"/>')
        for j, p in enumerate(piece):
            body += (f'<rect x="{j*16-6}" y="-6" width="12" height="12" fill="none" data-day="{p[0]},{p[1]}"/>'
                     f'<rect x="{j*16-3}" y="-9" width="6" height="3" fill="{colour}"/><rect x="{j*16-3}" y="-9" width="6" height="1" fill="{high}"/>'
                     f'<rect x="{j*16+2}" y="-8" width="1" height="2" fill="{low}"/>')
        home = {'transform': transform(x, y), 'opacity': '1'}
        at = 1.5+i*step
        dock_x = 28+(i % max(1, (cal.cols//4)))*64
        lift = y-13
        frames = [(at, home), (at+.3, {'transform': transform(x, lift)}),
                  (at+.85, {'transform': transform(dock_x, 178)}),
                  (at+1.15, {'transform': transform(dock_x+18, 178)}),
                  (at+1.65, {'transform': transform(x, y-14)}),
                  (at+1.85, home), (at+1.93, {'transform': transform(x, y, 1.08)}),
                  (at+2.05, home)]
        draw.parts.append(draw.animated(body, frames, home))
        # A hoist: trolley on the rail, cable and clamp follow the brick on both trips.
        cx = x+width/2-6
        cx2 = dock_x+width/2-6
        hx = lambda px, py: (f'translate({num(px)}px,{num(py)}px) rotate(0deg) scale(1)',
                             f'translate({num(px)}px,8px) rotate(0deg) scale(1,{num(max(1, py-8))})')
        pts = [(at+.02, cx, lift-9, '1'), (at+.3, cx, lift-9, '1'), (at+.85, cx2, 169, '1'), (at+1.0, cx2+0, 169, '0'),
               (at+1.5, cx2+18, 160, '0'), (at+1.66, cx, y-23, '1'), (at+1.85, cx, y-9, '1'), (at+1.95, cx, y-30, '0')]
        clamp = f'<rect x="-4" y="0" width="8" height="3" fill="{draw.muted}"/><rect x="-1" y="-3" width="2" height="3" fill="{draw.muted}"/>'
        wire = f'<rect x="0" y="0" width="1" height="1" fill="{draw.muted}"/>'
        first = hx(cx, 20)
        draw.parts.append(draw.animated(clamp, [(t, {'transform': hx(px, py)[0], 'opacity': op}) for t, px, py, op in pts], {'transform': first[0], 'opacity': '0'}))
        draw.parts.append(draw.animated(wire, [(t, {'transform': hx(px, py)[1], 'opacity': op}) for t, px, py, op in pts], {'transform': first[1], 'opacity': '0'}))
        pixel_puff(draw, x+width/2-6, y-9, at+1.85, draw.cyan)
    draw.parts.append('<text x="24" y="211">BRICK WORKSHOP / SNAP FIT</text>')
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


def budget(n, total, low, high):
    """Particles per tile so a full 54-week calendar stays well inside the file-size limit."""
    return max(low, min(high, total//max(1, n)))


def stepped(frames):
    """Hard steps for pixel motion: every state holds until just before the next keyframe."""
    out = []
    for i, (t, props) in enumerate(frames):
        if i:
            out.append((t-.002, frames[i-1][1]))
        out.append((t, props))
    return out


def tint(colour, amount, other='#ffffff'):
    a = [int(colour[i:i+2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i+2], 16) for i in (1, 3, 5)]
    return '#'+''.join(f'{round(x+(y-x)*amount):02x}' for x, y in zip(a, b))


def palette2(theme):
    if theme == 'dark':
        return dict(building='#151d33', building_dim='#1d2742', window='#ffd166', rail='#1b2438', rail_edge='#28334d',
                    ivory='#f3efe4', ivory_side='#cbc5b2', pip='#20242c', outline='#0d1117',
                    fire=('#ff9d3d', '#4cc9f0', '#ff6b8b', '#b48cff', '#ffe066'),
                    led=('#3fb950', '#f2cc60', '#ff6b6b'), steel=('#aeb8c6', '#5c6675', '#ffffff', '#7b8696'))
    return dict(building='#c5d1e6', building_dim='#b3c1da', window='#f2a900', rail='#e3e9f3', rail_edge='#cfd8e8',
                ivory='#fbf9f2', ivory_side='#d0cab6', pip='#20242c', outline='#4c4a40',
                fire=('#e8590c', '#0b7285', '#c2255c', '#7048e8', '#e67700'),
                led=('#2da44e', '#bf8700', '#cf222e'), steel=('#8c96a5', '#4b5565', '#ffffff', '#6b7686'))


def pixel_puff(draw, x, y, t, colour, span=.36):
    """A four-square puff that expands in hard steps and vanishes."""
    body = ''.join(f'<rect x="{dx-1}" y="{dy-1}" width="2" height="2" fill="{colour}"/>' for dx, dy in ((-2, -2), (2, -2), (-2, 2), (2, 2)))
    at = lambda s: f'translate({int(x)}px,{int(y)}px) rotate(0deg) scale({s})'
    draw.parts.append(draw.animated(body, stepped([(t, {'transform': at(1), 'opacity': '1'}), (t+span/3, {'transform': at(1.8), 'opacity': '.8'}),
                                                   (t+2*span/3, {'transform': at(2.6), 'opacity': '.45'}), (t+span, {'transform': at(2.6), 'opacity': '0'})]),
                                    {'transform': at(1), 'opacity': '0'}))


def fireworks(cal, model, theme):
    order, n = model['order'], len(model['order'])
    p2 = palette2(theme)
    step = min(.3, 50/max(1, n))
    first, fly, hop = 2.4, .56, .09
    finish = first+n*step+fly+1.6
    draw = Drawing(cal, 'fireworks', theme, finish+4)
    draw.css.append('svg{shape-rendering:crispEdges}')
    # A pixel skyline: buildings on a 4px grid with 2x2 windows, a few of them lit.
    rng = random.Random(n*31+len(model['pads']))
    dim, lit, x = '', '', 4
    roofs = ''
    while x < draw.width-8:
        w = 4*rng.randint(3, 6)
        h = 4*rng.randint(3, 9)
        roofs += f'M{x} {216-h}h{w}V216H{x}z'
        for wy in range(216-h+4, 212, 6):
            for wx in range(x+3, x+w-3, 5):
                if rng.random() < .16:
                    lit += f'M{wx} {wy}h2v2h-2z'
                else:
                    dim += f'M{wx} {wy}h2v2h-2z'
        x += w+4*rng.randint(0, 1)
    skyline = (f'<path d="{roofs}" fill="{p2["building"]}"/><path d="{dim}" fill="{p2["building_dim"]}"/>')
    twinkle = f'<path d="{lit}" fill="{p2["window"]}"/>'
    fire = p2['fire']
    pieces = 16 if n <= 50 else (8 if n <= 110 else (4 if n <= 200 else 0))
    hops = 8 if n <= 200 else 4
    rings = ((4, 9, 14, 18), (7, 13, 19, 24))
    drop = (0, 0, 2, 5)
    fade = ('1', '1', '.85', '.45')
    grow = (1.3, 1.2, 1, .75)
    for i, p in enumerate(order):
        x, y = int(xy(p)[0]), int(xy(p)[1])
        at = first+i*step
        boom = at+fly
        colour = fire[i % 5]
        blackout = .9+x/draw.width*.7
        base_dark = {'opacity': '0', 'transform': transform(x, y, .7)}
        lone_tile(draw, p, stepped([(blackout, {}), (blackout+.1, base_dark),
                                    (boom, {'opacity': '1', 'fill': '#ffffff', 'transform': transform(x, y, 1.3)}),
                                    (boom+hop, {'fill': tint(draw.green[cal.grid[p]], .5), 'transform': transform(x, y, 1.15)}),
                                    (boom+2*hop, {})]))
        rocket = ''.join(f'<rect x="-1" y="{k*2+1}" width="2" height="2" fill="{colour}" opacity="{o}"/>' for k, o in enumerate(('.9', '.6', '.35', '.15')))
        rocket += '<rect x="-1" y="-1" width="2" height="2" fill="#ffffff"/>'
        ys = [round(196+(y-196)*(1-(1-(k+1)/hops)**2)) for k in range(hops)]
        frames = [(at, {'transform': transform(x, 196), 'opacity': '1'})]+[(at+fly*(k+1)/hops, {'transform': transform(x, ys[k]), 'opacity': '1'}) for k in range(hops)]
        frames.append((boom+.02, {'transform': transform(x, y), 'opacity': '0'}))
        draw.parts.append(draw.animated(rocket, stepped(frames), {'transform': transform(x, 196), 'opacity': '0'}))
        flash = '<rect x="-2" y="-2" width="4" height="4" fill="#ffffff"/>'
        draw.parts.append(draw.animated(flash, stepped([(boom, {'transform': transform(x, y, 1), 'opacity': '1'}), (boom+hop, {'transform': transform(x, y, 1.6), 'opacity': '.8'}),
                                                        (boom+2*hop, {'transform': transform(x, y, 1.6), 'opacity': '0'})]),
                                          {'transform': transform(x, y, 1), 'opacity': '0'}))
        for ring, radii in enumerate(rings[:(1 if pieces < 16 else 2) if pieces else 0]):
            count = 8 if pieces >= 8 else 4
            for k in range(count):
                angle = math.tau*(k+.5*ring)/count
                own = colour if ring == 0 else tint(colour, .5)
                bit = '<rect x="-1.5" y="-1.5" width="3" height="3"/>'
                shades = ('#ffffff', tint(own, .45), own, tint(own, .25, '#000000'))
                frames = []
                for j in range(4):
                    px = x+round(math.cos(angle)*radii[j])
                    py = y+round(math.sin(angle)*radii[j])+drop[j]
                    frames.append((boom+j*hop, {'transform': transform(px, py, grow[j]), 'opacity': fade[j], 'fill': shades[j]}))
                frames.append((boom+4*hop, {'transform': transform(x+round(math.cos(angle)*radii[3]), y+round(math.sin(angle)*radii[3])+6), 'opacity': '0'}))
                draw.parts.append(draw.animated(bit, stepped(frames), {'transform': transform(x, y), 'opacity': '0', 'fill': '#ffffff'}))
    draw.parts.append(skyline)
    beat = [(t, {'opacity': '1' if int(t) % 2 else '.35'}) for t in [k*1.3+1 for k in range(int(finish/1.3))]]
    if beat:
        draw.parts.append(draw.animated(twinkle, stepped(beat), {'opacity': '.35'}))
    draw.parts.append('<text x="24" y="170">FIREWORKS / RELIGHT THE YEAR</text>')
    return draw


PIPS = {1: ((0, 0),), 2: ((-2.2, -1.8), (2.2, 1.8)), 3: ((-2.4, -1.8), (0, 0), (2.4, 1.8)),
        4: ((-2.2, -1.8), (2.2, -1.8), (-2.2, 1.8), (2.2, 1.8))}


def domino_body(p2, accent, level, side, identity=''):
    """An ivory double-N domino with a coloured base stripe, drawn relative to the bottom corner it pivots on."""
    x0 = -9 if side == 1 else 0
    pips = ''
    for cy in (-11.25, -3.75):
        for dx, dy in PIPS[level]:
            pips += f'M{num(x0+4.5+dx+1.05)} {num(cy+dy)}a1.05 1.05 0 1 0 -2.1 0a1.05 1.05 0 1 0 2.1 0z'
    return (f'<path d="M{x0+9} -15l2.2 -2.2V-2.2L{x0+9} 0z" fill="{p2["ivory_side"]}" stroke="{p2["outline"]}" stroke-opacity=".5" stroke-width=".6"/>'
            f'<path d="M{x0} -15l2.2 -2.2h9L{x0+9} -15z" fill="#ffffff" stroke="{p2["outline"]}" stroke-opacity=".5" stroke-width=".6"/>'
            f'<rect x="{x0}" y="-15" width="9" height="15" rx="1.6" fill="{p2["ivory"]}" stroke="{p2["outline"]}" stroke-opacity=".7" stroke-width=".8" {identity}/>'
            f'<path d="M{x0+.9} -7.5H{x0+8.1}" stroke="{p2["pip"]}" stroke-opacity=".45" stroke-width=".7"/>'
            f'<path d="{pips}" fill="{p2["pip"]}"/>'
            f'<rect x="{x0+1}" y="-2.6" width="7" height="1.7" rx=".8" fill="{accent}"/>')


def pixel_ball(p2):
    steel = p2['steel']
    cells = ((-2, -4, 4, 2), (-4, -2, 8, 4), (-2, 2, 4, 2))
    body = ''.join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{steel[0]}"/>' for x, y, w, h in cells)
    return (body+f'<rect x="-2" y="-4" width="4" height="2" fill="{steel[2]}" opacity=".5"/>'
            f'<rect x="-4" y="-2" width="2" height="2" fill="{steel[2]}"/><rect x="0" y="0" width="4" height="2" fill="{steel[3]}"/>'
            f'<rect x="-2" y="2" width="4" height="2" fill="{steel[1]}"/>')


def domino(cal, model, theme):
    order, n, side = model['order'], len(model['order']), model['dir']
    p2 = palette2(theme)
    step = min(.12, 26/max(1, n))
    first = 2.6
    down_end = first+n*step+.7
    rise0 = down_end+3
    finish = rise0+n*step*.55+1.2
    draw = Drawing(cal, 'domino', theme, finish+2)
    rails = ''.join(f'M16 {xy((0, r))[1]-8}h{draw.width-32}v16h-{draw.width-32}z' for r in range(7))
    edges = ''.join(f'M16 {xy((0, r))[1]+7}h{draw.width-32}v1h-{draw.width-32}z' for r in range(7))
    draw.backdrop.append(f'<path d="{rails}" fill="{p2["rail"]}"/><path d="{edges}" fill="{p2["rail_edge"]}"/>')
    shadows = ''.join(f'M{num(xy(p)[0]-5)} {xy(p)[1]+7.6}a5 1.4 0 1 0 10 0a5 1.4 0 1 0 -10 0z' for p in order)
    draw.parts.append(f'<path d="{shadows}" fill="#000000" opacity="{".38" if theme == "dark" else ".2"}"/>')
    puffs = n <= 160
    for i, p in enumerate(order):
        x, y = xy(p)
        pivot = (x+4.5*side, y+7.5)
        at = lambda angle: transform(pivot[0], pivot[1], 1, angle*side)
        fall = first+i*step
        rise = rise0+(n-1-i)*step*.55
        flat = 84
        body = domino_body(p2, draw.green[cal.grid[p]] if theme == 'light' else draw.green[max(2, cal.grid[p])], cal.grid[p], side, f'data-day="{p[0]},{p[1]}"')
        frames = [(fall, {'transform': at(0)}), (fall+.16, {'transform': at(20)}), (fall+.3, {'transform': at(58)}),
                  (fall+.4, {'transform': at(flat)}), (fall+.47, {'transform': at(flat-5)}), (fall+.55, {'transform': at(flat)}),
                  (rise, {'transform': at(flat)}), (rise+.25, {'transform': at(28)}), (rise+.42, {'transform': at(-5)}), (rise+.55, {'transform': at(0)})]
        draw.parts.append(draw.animated(body, frames, {'transform': at(0)}))
        if puffs and i % 2 == 0:
            pixel_puff(draw, pivot[0]+4*side, pivot[1]-1, fall+.4, tint(p2['ivory'], .0, '#ffffff') if theme == 'dark' else '#8f8a78')
    x0, y0 = xy(order[0])
    edge = -14 if side == 1 else draw.width+14
    hit_x = int(x0-11*side)
    draw.parts.append(draw.animated(pixel_ball(p2), [
        (first-1.6, {'transform': transform(edge, y0+3), 'opacity': '1'}),
        (first-.05, {'transform': transform(hit_x, y0+3), 'opacity': '1'}),
        (first+.02, {'transform': transform(hit_x+2*side, y0+3), 'opacity': '1'}),
        (first+.4, {'transform': transform(hit_x+5*side, y0+3), 'opacity': '0'})],
        {'transform': transform(edge, y0+3), 'opacity': '0'}))
    draw.parts.append(caption('DOMINO / CHAIN REACTION'))
    return draw


def dust(cal, model, theme):
    order, n = model['order'], len(model['order'])
    sweep = min(22, max(6, n*.12))
    snap0 = 2
    back0 = snap0+sweep+3.5
    finish = back0+sweep+1.8
    draw = Drawing(cal, 'dust', theme, finish+3)
    draw.css.append('svg{shape-rendering:crispEdges}')
    quads = ((-3, -3), (3, -3), (-3, 3), (3, 3)) if n <= 160 else ((-3, 0), (3, 0))
    size = 6 if n <= 160 else 6
    hop = .17
    fade = ('1', '1', '1', '.8', '.55', '.25', '0')
    for i, p in enumerate(order):
        x, y = int(xy(p)[0]), int(xy(p)[1])
        gone = snap0+i/max(1, n)*sweep
        back = back0+i/max(1, n)*sweep
        colour = draw.green[cal.grid[p]]
        lone_tile(draw, p, stepped([(gone, {}), (gone+.05, {'opacity': '0'}), (back+.3, {'opacity': '1', 'fill': '#ffffff'}), (back+.3+hop, {})]))
        rng = random.Random(i*977+13)
        for q, (ox, oy) in enumerate(quads):
            wind, lift, sag = rng.uniform(4, 8), rng.uniform(3, 6), rng.uniform(.5, 1.0)
            shade = tint(colour, .16 if (q % 2) else .0, '#ffffff') if q != 2 else tint(colour, .18, '#000000')
            bit = f'<rect x="{-size//2}" y="{-size//2}" width="{size}" height="{size}" fill="{shade}"/>'
            t0 = gone+.03+q*.06+rng.uniform(0, .12)
            path = [(x+ox+round(wind*j*(1+.12*j)), y+oy+round(-lift*j+sag*j*j)) for j in range(7)]
            frames = [(t0+j*hop, {'transform': transform(px, py), 'opacity': fade[j]}) for j, (px, py) in enumerate(path)]
            frames += [(back-.34, {'transform': transform(path[3][0], path[3][1]), 'opacity': '0'}),
                       (back-.17, {'transform': transform(path[1][0], path[1][1]), 'opacity': '.7'}),
                       (back, {'transform': transform(x+ox, y+oy), 'opacity': '1'}),
                       (back+.3, {'transform': transform(x+ox, y+oy), 'opacity': '0'})]
            draw.parts.append(draw.animated(bit, stepped(frames), {'transform': transform(x+ox, y+oy), 'opacity': '0'}))
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
    draw.css.append('svg{shape-rendering:crispEdges}')
    gap = 14
    binw = (draw.width-48-3*gap)/4
    peak = max(counts)
    pitch = next((m for m in (8, 7, 6, 5, 4.4) if int((binw-10)/m)*int(34/m) >= peak), 4.4)
    per_row = max(1, int((binw-10)/pitch))
    mini = (pitch-.9)/12
    accents = ('#3fae6a', '#37c26f', '#4ade80', '#86efac') if theme == 'dark' else ('#3a9d5d', '#22863a', '#1a7f37', '#116329')
    for b in range(4):
        x0 = round(24+b*(binw+gap))
        accent = accents[b]
        w = round(binw)
        draw.parts.append(f'<rect x="{x0}" y="156" width="{w}" height="46" fill="{accent}" opacity=".10"/>')
        draw.parts.append(f'<path d="M{x0} 156h{w}v46h-{w}zM{x0+2} 158v42h{w-4}v-42z" fill="{accent}" fill-rule="evenodd"/>')
        draw.parts.append(f'<rect x="{x0+w//2-18}" y="152" width="36" height="6" fill="{accent}"/>')
        draw.parts.append(f'<text x="{x0+2}" y="214" style="fill:{accent};font-weight:700">LEVEL {b+1}</text>')
        draw.parts.append(f'<text x="{x0+w-2}" y="214" text-anchor="end" style="fill:{draw.muted};font-weight:700">{counts[b]} DAYS</text>')
    for i, (p, (b, k)) in enumerate(zip(order, slots)):
        home = (int(xy(p)[0]), int(xy(p)[1]))
        slot = (round(24+b*(binw+gap)+8+pitch/2+(k % per_row)*pitch), round(198-pitch/2-(k//per_row)*pitch))
        out, back = out0+i*step, back0+(n-1-i)*step
        frames = [(out, {})]
        for j in range(1, 7):
            t = ease(j/6)
            pt = bezier(home, (home[0], 150), (slot[0], 148), slot, t)
            frames.append((out+j/6*.9, {'transform': transform(round(pt[0]), round(pt[1]), 1+(mini-1)*t)}))
        frames.append((back, {'transform': transform(*slot, mini)}))
        for j in range(1, 7):
            t = ease(j/6)
            pt = bezier(slot, (slot[0], 150), (home[0], 150), home, t)
            frames.append((back+j/6*.9, {'transform': transform(round(pt[0]), round(pt[1]), mini+(1-mini)*t)}))
        lone_tile(draw, p, frames+[(back+1.0, {'transform': transform(*home, 1.08)}), (back+1.15, {})])
        pixel_puff(draw, slot[0], slot[1]-2, out+.9, accents[b])
    return draw


def synth(cal, model, theme):
    cols = cal.cols
    p2 = palette2(theme)
    sweeps, clock = [], 1.5
    for ps in model['passes']:
        sweeps.append((clock, ps['dir'], ps['tempo']))
        clock += cols*ps['tempo']+1.2
    finish = clock+.6
    draw = Drawing(cal, 'synth', theme, finish+2)
    draw.css.append('svg{shape-rendering:crispEdges}')
    xs = [int(xy((c, 0))[0]) for c in range(cols)]
    frames = []
    for start, direction, tempo in sweeps:
        a, b = (xs[0], xs[-1]) if direction == 1 else (xs[-1], xs[0])
        mk = lambda x, op: {'transform': transform(x, 38), 'opacity': op}
        frames += [(start-.05, mk(a, '0')), (start, mk(a, '1')), (start+cols*tempo, mk(b, '1')), (start+cols*tempo+.2, mk(b, '0'))]
    tip = ''.join(f'<rect x="{-3+k}" y="{k*1-2}" width="{6-2*k}" height="1" fill="{draw.cyan}"/>' for k in range(3))
    tip_b = ''.join(f'<rect x="{-3+k}" y="{118+1-k}" width="{6-2*k}" height="1" fill="{draw.cyan}"/>' for k in range(3))
    head = f'<rect x="-8" y="0" width="16" height="118" fill="{draw.cyan}" opacity=".10"/><rect x="-1" y="0" width="2" height="118" fill="{draw.cyan}"/>{tip}{tip_b}'
    draw.parts.append(draw.animated(head, frames, {'transform': transform(xs[0], 38), 'opacity': '0'}))
    sums = [sum(cal.grid[c, r] for r in range(7)) for c in range(cols)]
    peak = max(max(sums), 1)
    seg_colours = [p2['led'][0]]*5+[p2['led'][1]]*2+[p2['led'][2]]*2
    draw.parts.append(f'<rect x="20" y="201" width="{draw.width-40}" height="1" fill="{draw.line}"/>')
    for c in range(cols):
        count = max(1, round(9*sums[c]/peak)) if sums[c] else 0
        if not count:
            draw.parts.append(f'<rect x="{xs[c]-3}" y="199" width="6" height="2" fill="{draw.line}"/>')
            continue
        segs = ''.join(f'<rect x="-3" y="{-3*(k+1)}" width="6" height="2" fill="{seg_colours[k]}"/>' for k in range(count))
        base = {'transform': transform(xs[c], 200), 'opacity': '.45'}
        pulses = []
        for start, direction, tempo in sweeps:
            hit = start+(c if direction == 1 else cols-1-c)*tempo
            pulses += [(hit-.02, base), (hit, {'transform': base['transform'], 'opacity': '1'}), (hit+.28, base)]
        draw.parts.append(draw.animated(segs, stepped(pulses), base))
    for p in cal.active:
        x, y = int(xy(p)[0]), int(xy(p)[1])
        pulses, ping = [], []
        for start, direction, tempo in sweeps:
            hit = start+(p[0] if direction == 1 else cols-1-p[0])*tempo
            pulses += [(hit-.02, {}), (hit, {'transform': transform(x, y, 1.3), 'fill': tint(draw.green[cal.grid[p]], .55)}), (hit+.14, {})]
            ping += [(hit, {'transform': transform(x, y, 1), 'opacity': '.9'}), (hit+.1, {'transform': transform(x, y, 1.35), 'opacity': '.7'}),
                     (hit+.2, {'transform': transform(x, y, 1.7), 'opacity': '.4'}), (hit+.3, {'transform': transform(x, y, 1.7), 'opacity': '0'})]
        lone_tile(draw, p, stepped(pulses))
        ring = f'<rect x="-6" y="-6" width="12" height="12" fill="none" stroke="{draw.cyan}" stroke-width="1"/>'
        draw.parts.append(draw.animated(ring, stepped(ping), {'transform': transform(x, y, 1), 'opacity': '0'}))
    draw.parts.append(caption('SYNTH / PLAY THE YEAR'))
    return draw


def claw(cal, model, theme):
    order, n = model['order'], len(model['order'])
    s = min(.9, 60/max(1, n))
    first = 1.5
    finish = first+n*s+.8
    draw = Drawing(cal, 'claw', theme, finish+5)
    draw.css.append('svg{shape-rendering:crispEdges}')
    w = draw.width
    binw, bin_x = 150, w-24-150
    chute = bin_x+binw//2
    pitch = 5.6
    per_row = int((binw-10)/pitch)
    mini = (pitch-.9)/12
    draw.parts.append(f'<rect x="12" y="3" width="{w-24}" height="4" fill="{draw.line}"/><rect x="12" y="3" width="{w-24}" height="1" fill="{draw.muted}" opacity=".5"/>'
                      f'<rect x="12" y="1" width="3" height="8" fill="{draw.muted}"/><rect x="{w-15}" y="1" width="3" height="8" fill="{draw.muted}"/>')
    draw.parts.append(f'<rect x="{bin_x}" y="168" width="{binw}" height="38" fill="{draw.accent}" opacity=".10"/>')
    draw.parts.append(f'<path d="M{bin_x} 168h{binw}v38h-{binw}zM{bin_x+2} 170v34h{binw-4}v-34z" fill="{draw.accent}" fill-rule="evenodd"/>')
    draw.parts.append(''.join(f'<rect x="{bin_x+k*binw//5}" y="170" width="1" height="34" fill="{draw.accent}" opacity=".25"/>' for k in range(1, 5)))
    draw.parts.append(f'<rect x="{chute-16}" y="164" width="32" height="5" fill="{draw.accent}"/>')
    draw.parts.append(f'<text x="{bin_x}" y="215" style="fill:{draw.accent};font-weight:700">PRIZES</text>')
    head_frames, cable_frames, prong_frames, car_frames = [], [], [], []

    def place(t, x, yh, closed):
        x = round(x)
        head_frames.append((t, {'transform': transform(x, yh), 'opacity': '1'}))
        cable_frames.append((t, {'transform': f'translate({x}px,7px) rotate(0deg) scale(1,{num(max(1, yh-7))})', 'opacity': '1'}))
        prong_frames.append((t, {'transform': f'translate({x}px,{yh}px) rotate(0deg) scale({.5 if closed else 1},1)', 'opacity': '1'}))
        car_frames.append((t, {'transform': transform(x, 5), 'opacity': '1'}))

    for i, p in enumerate(order):
        x, y = int(xy(p)[0]), int(xy(p)[1])
        t = first+i*s
        slot = (round(bin_x+8+pitch/2+(i % per_row)*pitch), round(202-pitch/2-(i//per_row)*pitch))
        place(t, chute, 22, False)
        place(t+.3*s, x, 22, False)
        place(t+.5*s, x, y-9, False)
        place(t+.56*s, x, y-9, True)
        place(t+.78*s, x, 22, True)
        place(t+s, chute, 22, True)
        back = finish+.8+(n-1-i)/max(1, n)*3
        frames = [(t+.5*s, {}), (t+.56*s, {'transform': transform(x, y)}), (t+.78*s, {'transform': transform(x, 31)}),
                  (t+s, {'transform': transform(chute, 31)}), (t+s+.22, {'transform': transform(chute, 150, .8)}),
                  (t+s+.5, {'transform': transform(*slot, mini)}), (back, {'transform': transform(*slot, mini)})]
        for j in range(1, 7):
            u = ease(j/6)
            pt = bezier(slot, (slot[0], 150), (x, 150), (x, y), u)
            frames.append((back+j/6*.9, {'transform': transform(round(pt[0]), round(pt[1]), mini+(1-mini)*u)}))
        lone_tile(draw, p, frames+[(back+1.0, {'transform': transform(x, y, 1.08)}), (back+1.15, {})])
        pixel_puff(draw, x, y-8, t+.56*s, draw.accent)
    place(finish, chute, 22, False)
    for frames in (head_frames, cable_frames, prong_frames, car_frames):
        frames.append((finish+.5, {**frames[-1][1], 'opacity': '0'}))
    draw.parts.append(draw.animated(f'<rect x="-8" y="-3" width="16" height="7" fill="{draw.muted}"/><rect x="-8" y="2" width="16" height="2" fill="{draw.line}"/>', car_frames,
                                    {'transform': transform(chute, 5), 'opacity': '0'}))
    draw.parts.append(draw.animated(f'<rect x="0" y="0" width="1" height="1" fill="{draw.muted}"/>', cable_frames,
                                    {'transform': f'translate({chute}px,7px) rotate(0deg) scale(1,15)', 'opacity': '0'}))
    hub = f'<rect x="-6" y="-4" width="12" height="7" fill="{draw.accent}"/><rect x="-6" y="1" width="12" height="2" fill="{tint(draw.accent, .35, "#000000")}"/>'
    draw.parts.append(draw.animated(hub, head_frames, {'transform': transform(chute, 22), 'opacity': '0'}))
    prongs = (''.join(f'<rect x="{x0}" y="3" width="2" height="9" fill="{draw.accent}"/><rect x="{x1}" y="10" width="4" height="2" fill="{draw.accent}"/>'
                      for x0, x1 in ((-7, -7), (5, 3)))
              + f'<rect x="-1" y="3" width="2" height="8" fill="{draw.accent}"/>')
    draw.parts.append(draw.animated(prongs, prong_frames, {'transform': f'translate({chute}px,22px) rotate(0deg) scale(1,1)', 'opacity': '0'}))
    draw.parts.append(caption('CLAW MACHINE / GRAB EVERY DAY'))
    return draw


RENDERERS = {'minecraft': minecraft, 'lego': lego, 'fireworks': fireworks, 'domino': domino, 'dust': dust,
             'sorter': sorter, 'synth': synth, 'claw': claw}


def render(cal: Calendar, scene: str, seed: int, theme='dark', model=None) -> str:
    if theme not in THEMES or scene not in RENDERERS:
        raise ValueError('Unknown theme or SVG scene')
    if not cal.active:
        # A genuinely empty calendar stays empty, rather than inventing obstacles.
        return Drawing(cal, scene, theme, 6).document(seed)
    model = PLANNERS[scene](cal, seed) if model is None else model
    return RENDERERS[scene](cal, model, theme).document(seed)
