"""A reproducible, scriptless comparison of search on the contribution calendar."""
from collections import deque
from html import escape
import hashlib
import heapq
import json

ALGORITHMS = ('bfs', 'dijkstra', 'astar')
ANALYSIS_FILES = ('search-comparison-dark.svg', 'search-comparison-light.svg', 'search-comparison.json')


def search(costs, start, goal, algorithm):
    """Four-neighbor graph. Cost is paid on entry; the start costs nothing."""
    if algorithm not in ALGORITHMS or start not in costs or goal not in costs:
        raise ValueError('Invalid search algorithm or endpoints')
    if any(type(c) is not int or not 1 <= c <= 9 for c in costs.values()):
        raise ValueError('Search costs must be integers from 1 to 9')
    def h(p):
        return abs(p[0]-goal[0])+abs(p[1]-goal[1]) if algorithm == 'astar' else 0
    distance, parent, closed, trace = {start: 0}, {start: None}, set(), []
    queue, heap, order = deque([start]), [(h(start), 0, 0, start)], 1
    while queue if algorithm == 'bfs' else heap:
        if algorithm == 'bfs':
            p = queue.popleft()
        else:
            _, _, score, p = heapq.heappop(heap)
            if score != distance[p]:
                continue
        if p in closed:
            continue
        closed.add(p)
        trace.append(p)
        if p == goal:
            break
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            q = p[0]+dx, p[1]+dy
            if q not in costs or q in closed:
                continue
            candidate = distance[p]+(1 if algorithm == 'bfs' else costs[q])
            if candidate >= distance.get(q, float('inf')):
                continue
            distance[q], parent[q] = candidate, p
            if algorithm == 'bfs':
                queue.append(q)
            else:
                heapq.heappush(heap, (candidate+h(q), order, candidate, q))
                order += 1
    path = []
    if goal in closed:
        p = goal
        while p is not None:
            path.append(p)
            p = parent[p]
        path.reverse()
    return {'algorithm': algorithm, 'reachable': bool(path), 'path': path, 'trace': trace,
            'expanded': len(trace), 'steps': len(path)-1 if path else None,
            'cost': sum(costs[p] for p in path[1:]) if path else None}


def comparison(cal):
    costs = {p: level+1 for p, level in cal.grid.items() if p not in cal.missing}
    row = sorted(p for p in costs if p[1] == 3) or sorted(costs)
    start, goal = (row[0], row[-1]) if row else (None, None)
    results = {a: search(costs, start, goal, a) for a in ALGORITHMS} if row else {}
    # JSON-native values make exported traces and publication checks unambiguous.
    return json.loads(json.dumps({'schema': 'search-comparison-v1', 'owner': cal.owner, 'date': cal.day,
        'grid_sha256': hashlib.sha256(json.dumps(sorted(cal.grid.items())).encode()).hexdigest(),
        'rules': {'movement': 'right/down/left/up', 'cost': '1 + contribution level; start excluded',
                  'missing_days': 'not traversable', 'heuristic': 'Manhattan; minimum cost 1',
                  'tie_break': 'insertion order', 'endpoints': 'first and last valid Wednesday, otherwise first and last valid cell',
                  'expanded': 'unique popped nodes including the goal', 'timing': 'illustrative playback, not a runtime benchmark'},
        'start': start, 'goal': goal, 'results': results}))


def render_comparison(cal, theme, report=None):
    if theme not in ('light', 'dark'):
        raise ValueError('Unknown theme')
    report = comparison(cal) if report is None else report
    dark = theme == 'dark'
    bg, line, muted, ink = ('#0d1117', '#30363d', '#8b949e', '#e6edf3') if dark else ('#ffffff', '#d0d7de', '#57606a', '#24292f')
    greens = ('#161b22', '#0e4429', '#006d32', '#26a641', '#39d353') if dark else ('#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39')
    colors = ('#ffb86b', '#a5a0ff', '#79e0f2') if dark else ('#b65c00', '#8250df', '#0969da')
    width, duration = cal.cols*16+48, 27
    def xy(p): return 24+p[0]*16, 43+p[1]*16
    def text(x, y, value, size=10, fill=None):
        return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill or muted}">{escape(str(value))}</text>'
    css, layers = [], []
    grid = ''.join(f'<rect x="{xy(p)[0]-6}" y="{xy(p)[1]-6}" width="12" height="12" rx="2" fill="{greens[v]}"/>'
                   for p, v in cal.grid.items() if p not in cal.missing)
    def animate(body, frames):
        ident = f't{len(css)}'
        frames = {0: 'opacity:0', 100: 'opacity:0', **frames}
        css.append(f'.{ident}'+'{opacity:0;animation:'+ident+f' {duration}s linear infinite'+'}'+
            '@keyframes '+ident+'{'+''.join(f'{t:.5f}%{{{style}}}' for t, style in sorted(frames.items()))+'}')
        return f'<g class="{ident}">{body}</g>'
    scoreboard = []
    names = {'bfs': 'BFS', 'dijkstra': 'Dijkstra', 'astar': 'A* / Manhattan'}
    for index, algorithm in enumerate(ALGORITHMS):
        result = report['results'].get(algorithm)
        if not result:
            continue
        color, begin, end = colors[index], index*100/3, (index+1)*100/3
        for i, p in enumerate(result['trace']):
            x, y = xy(p)
            arrival = begin+2+12*i/max(1, len(result['trace']))
            tile = f'<rect x="{x-6}" y="{y-6}" width="12" height="12" rx="2" fill="{color}"/>'
            layers.append(animate(tile, {arrival-.01: 'opacity:0', arrival: 'opacity:.48', end-5: 'opacity:.48', end-1: 'opacity:0'}))
        if result['path']:
            points = [xy(p) for p in result['path']]
            route = 'M'+'L'.join(f'{x} {y}' for x, y in points)
            layers.append(animate(f'<path d="{route}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linejoin="round"/>',
                {begin+15: 'opacity:0', begin+16: 'opacity:1', end-5: 'opacity:1', end-1: 'opacity:0'}))
            # A small courier follows the actual returned route, never a scripted shortcut.
            frames = {begin+15.99: 'opacity:0', end-4: 'opacity:1', end-1: 'opacity:0'}
            for i, (x, y) in enumerate(points):
                frames[begin+16+10*i/max(1, len(points)-1)] = f'opacity:1;transform:translate({x}px,{y}px)'
            x, y = points[-1]
            frames[end-4] = f'opacity:1;transform:translate({x}px,{y}px)'
            frames[end-1] = f'opacity:0;transform:translate({x}px,{y}px)'
            courier = f'<rect x="-4" y="-4" width="8" height="8" rx="2" fill="{color}" stroke="{bg}" stroke-width="1.5"/>'
            layers.append(animate(courier, frames))
        x = 24+index*(width-48)/3
        scoreboard += [text(x, 173, names[algorithm], 12, color),
            text(x, 191, f'cost {result["cost"] if result["reachable"] else "unreachable"}  /  expanded {result["expanded"]}  /  steps {result["steps"] if result["reachable"] else "--"}')]
        layers.append(animate(f'<path d="M{x} 155h{(width-72)/3}" stroke="{color}" stroke-width="2"/>',
            {begin+.1: 'opacity:1', end-1: 'opacity:1', end-.1: 'opacity:0'}))
    labels = ''
    for key, marker in (('start', 'S'), ('goal', 'G')):
        p = report.get(key)
        if p is not None:
            x, y = xy(p)
            labels += f'<rect x="{x-7}" y="{y-7}" width="14" height="14" rx="3" fill="{bg}" stroke="{ink}"/>'+text(x-3, y+3.5, marker, 10, ink)
    meta = {'scene': 'search-comparison', 'owner': cal.owner, 'date': cal.day,
        'active_days': len(cal.active), 'grid_sha256': report['grid_sha256'], 'format': 'vector-css-svg',
        'duration_seconds': duration, 'report_sha256': hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()}
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 216" width="{width}" height="216" role="img" aria-labelledby="title desc" data-scene="search-comparison">'
        '<title id="title">One calendar, three search strategies</title>'
        '<desc id="desc">BFS minimizes steps; Dijkstra and A* minimize entry cost. Colored waves show actual expanded nodes; couriers follow returned paths. Animation timing is illustrative, not a speed benchmark. Reduced motion shows the original calendar and final statistics.</desc>'
        '<metadata>'+escape(json.dumps(meta, separators=(',', ':')))+'</metadata>'
        '<style>svg{font:10px ui-monospace,monospace}'+''.join(css)+
        '@media(prefers-reduced-motion:reduce){.motion{display:none}}</style>'
        f'<rect width="100%" height="100%" fill="{bg}"/>'+text(18, 16, 'ONE CALENDAR. THREE SEARCH STRATEGIES.', 10, ink)+
        text(width-208, 16, f'{cal.day} / saved snapshot')+grid+'<g class="motion">'+''.join(layers)+'</g>'+labels+
        f'<path d="M18 155H{width-18}" stroke="{line}"/>'+''.join(scoreboard)+
        text(18, 211, 'Entry cost = 1 + level  |  S / G fixed  |  Playback speed is illustrative, not a benchmark', 9)+'</svg>')
