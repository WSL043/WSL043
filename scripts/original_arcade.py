"""Eight original, deterministic SVG toys. Standard library only; no scripts or APIs."""
from __future__ import annotations

import hashlib
import math
import random
from collections import deque
from datetime import date
from html import escape
from pathlib import Path

ORIGINALS = {
    "neon-race": ("Neon Relay", "🏁", "Pick a courier, then watch an 18-second race. Tomorrow brings new overtakes."),
    "dungeon-crawl": ("Clockwork Dungeon", "🗝️", "A little robot explores a freshly carved maze. Every map has a route home."),
    "pocket-garden": ("Pocket Garden", "🌱", "A procedural terrarium: new trees, fireflies, and imaginary weather."),
    "orbital-rescue": ("Orbital Post Office", "🪐", "Tiny satellites carry the mail around a different miniature planet."),
    "life-lab": ("Life Laboratory", "🧬", "A real Conway simulation, born from today's seed. Watch order emerge."),
    "sorting-race": ("Sorting Grand Prix", "📊", "Bubble sort and insertion sort tackle the same shuffled deck. No fake bar dancing."),
    "midnight-metro": ("Midnight Metro", "🚃", "A miniature railway with a new route, station names, and patiently stopping trains."),
    "deep-sea": ("Deep Sea Dispatch", "🪼", "A tiny submarine drifts past glowing jellyfish and a forgotten seafloor."),
}
PALETTES = {
    "dark": ("#0b1020", "#151f35", "#dce8fa", "#7f97b9", "#65e3d3", "#ac98ff", "#ffbd69"),
    "light": ("#f5f7fc", "#e3e9f4", "#19283f", "#576b87", "#087e83", "#7751c5", "#ab6100"),
}


def rng_for(day: str, namespace: str) -> random.Random:
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Date must use YYYY-MM-DD")
    digest = hashlib.sha256(f"wsl043-arcade-v1|{day}|{namespace}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


class Canvas:
    def __init__(self, title: str, day: str, theme: str):
        self.bg, self.panel, self.ink, self.muted, self.a, self.b, self.gold = PALETTES[theme]
        self.parts: list[str] = []
        self.rules: list[str] = []
        self.title, self.day = title, day

    def add(self, svg: str) -> None:
        self.parts.append(svg)

    def text(self, x: float, y: float, label: str, size: int = 12, color: str | None = None) -> None:
        self.add(f'<text x="{x:g}" y="{y:g}" fill="{color or self.muted}" font-size="{size}">{escape(label)}</text>')

    def animate(self, values: list[str], prop: str, seconds: float, timing: str = "linear") -> str:
        name = f"m{len(self.rules)}"
        # Keep the first pose readable when animation is disabled.
        frames = "".join(f"{100*i/max(1,len(values)-1):.4f}%{{{prop}:{v}}}" for i, v in enumerate(values))
        self.rules.append(f".{name}{{{prop}:{values[0]};animation:{name} {seconds:g}s {timing} infinite}}@keyframes {name}{{{frames}}}")
        return f"anim {name}"

    def follow(self, points: list[tuple[float, float]], glyph: str, seconds: float = 18) -> None:
        cls = self.animate([f"translate({x:.2f}px,{y:.2f}px)" for x, y in points], "transform", seconds)
        self.add(f'<g class="{cls}">{glyph}</g>')

    def finish(self, footer: str, chip: tuple[int, int]) -> str:
        x, y = chip
        self.add(f'<g transform="translate({x},{y})"><path d="M-3,-5 v-3 M3,-5 v-3" stroke="{self.gold}"/><rect x="-5" y="-5" width="10" height="8" rx="2" fill="{self.gold}"/><path d="M-2,-2 h1 M1,-2 h1" stroke="{self.bg}" stroke-width="2"/></g>')
        style = """text{font-family:ui-monospace,SFMono-Regular,Consolas,monospace} .anim{transform-origin:0 0}
@media(prefers-reduced-motion:reduce){.anim{animation:none!important}}""" + "".join(self.rules)
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="400" viewBox="0 0 900 400" role="img" aria-labelledby="title desc">
<title id="title">{escape(self.title)} · {self.day}</title><desc id="desc">Seeded autoplay scene, not a keyboard game. {escape(footer)} A tiny gold robot is hidden in the scene.</desc>
<defs><clipPath id="scene"><rect x="20" y="70" width="860" height="282" rx="12"/></clipPath></defs>
<style>{style}</style><rect width="900" height="400" rx="20" fill="{self.bg}"/>
<rect x="1" y="1" width="898" height="398" rx="19" fill="none" stroke="{self.panel}" stroke-width="2"/>
<text x="28" y="30" fill="{self.a}" font-size="10" letter-spacing="3">WSL043 / POCKET WORLDS</text>
<text x="28" y="56" fill="{self.ink}" font-size="20" font-weight="700">{escape(self.title)}</text>
<text x="766" y="38" fill="{self.muted}" font-size="12">{self.day}</text>
<g clip-path="url(#scene)">{''.join(self.parts)}</g>
<text x="28" y="379" fill="{self.muted}" font-size="11">{escape(footer)}</text>
</svg>\n'''


def race_model(rng: random.Random) -> tuple[list[int], list[list[float]]]:
    finishes = rng.sample(range(22, 30), 4)
    tracks = []
    for finish in finishes:
        weights = [rng.uniform(.2, 2.4) for _ in range(finish)]
        total, progress = sum(weights), [0.0]
        for weight in weights:
            progress.append(progress[-1] + weight / total)
        tracks.append([min(1.0, progress[min(i, finish)]) for i in range(33)])
    return finishes, tracks


def neon_race(c: Canvas, rng: random.Random) -> str:
    _, tracks = race_model(rng)
    names = ("NOVA", "BYTE", "ECHO", "FLUX")
    for i, track in enumerate(tracks):
        y, color = 117 + i * 60, (c.a, c.b, c.gold, c.ink)[i]
        c.add(f'<rect x="28" y="{y-22}" width="844" height="46" rx="10" fill="{c.panel}"/>')
        c.text(44, y + 4, names[i], 13, color)
        c.add(f'<path d="M135,{y} H836" stroke="{c.muted}" stroke-dasharray="3 11" opacity=".35"/>')
        glyph = f'<path d="M-16,-8 H8 L18,0 8,8 H-16 L-11,0Z" fill="{color}"/><rect x="-6" y="-4" width="9" height="8" rx="2" fill="{c.bg}"/>'
        c.follow([(146 + 678 * p, y) for p in track], glyph)
    for i in range(16):
        c.add(f'<rect x="836" y="{84+i*16}" width="7" height="16" fill="{c.ink if i%2 else c.bg}"/>')
    return "18s race / choose a courier before the finish / daily seed, real overtakes"


def maze_model(rng: random.Random, width: int = 21, height: int = 9) -> tuple[set[tuple[int, int]], list[tuple[int, int]]]:
    opened, stack = {(1, 1)}, [(1, 1)]
    while stack:
        x, y = stack[-1]
        neighbors = [(x+dx, y+dy) for dx, dy in ((2,0),(-2,0),(0,2),(0,-2))
                     if 0 < x+dx < width-1 and 0 < y+dy < height-1 and (x+dx,y+dy) not in opened]
        if not neighbors:
            stack.pop()
            continue
        nx, ny = rng.choice(neighbors)
        opened.update({(nx, ny), ((nx+x)//2, (ny+y)//2)})
        stack.append((nx, ny))
    goal = (width-2, height-2)
    queue, parent = deque([(1, 1)]), {(1, 1): None}
    while queue:
        x, y = queue.popleft()
        for nxt in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if nxt in opened and nxt not in parent:
                parent[nxt] = (x, y)
                queue.append(nxt)
    path, node = [], goal
    while node is not None:
        path.append(node)
        node = parent[node]
    return opened, list(reversed(path))


def dungeon(c: Canvas, rng: random.Random) -> str:
    opened, route = maze_model(rng)
    for y in range(9):
        for x in range(21):
            if (x, y) not in opened:
                c.add(f'<rect x="{135+x*30}" y="{77+y*30}" width="28" height="28" rx="4" fill="{c.panel}"/>')
    points = [(150+x*30, 92+y*30) for x, y in route]
    for x, y in points[3:-1:6]:
        c.add(f'<path d="M{x},{y-4} l4,4 -4,4 -4,-4Z" fill="{c.b}" opacity=".7"/>')
    x, y = points[-1]
    c.add(f'<rect x="{x-9}" y="{y-8}" width="18" height="16" rx="3" fill="{c.gold}"/><path d="M{x},{y-5} v8" stroke="{c.bg}" stroke-width="3"/>')
    robot = f'<rect x="-10" y="-10" width="20" height="20" rx="6" fill="{c.a}"/><path d="M-5,-2 h3 M2,-2 h3" stroke="{c.bg}" stroke-width="3"/>'
    c.follow(points + [points[-1]] * 5, robot, 20)
    return f"Perfect maze / {len(route)-1} steps from start to chest / a new map every day"


def garden(c: Canvas, rng: random.Random) -> str:
    weather = rng.choice(("clear", "rain", "mist", "snow"))
    c.add(f'<circle cx="760" cy="125" r="31" fill="{c.gold}" opacity=".45"/><path d="M20,303 Q220,250 440,305 T880,285 V352 H20Z" fill="{c.panel}"/>')
    for i in range(7):
        x, y, height = 100+i*115, rng.randrange(295, 321), rng.randrange(60, 125)
        c.add(f'<ellipse cx="{x}" cy="{y+4}" rx="40" ry="9" fill="{c.bg}" opacity=".35"/>')
        tree = f'<rect x="-4" y="{-height}" width="8" height="{height}" rx="4" fill="{c.muted}"/>'
        for dx, dy, radius in ((0, -height, 30), (-20, -height+22, 26), (22, -height+18, 27)):
            tree += f'<circle cx="{dx}" cy="{dy}" r="{radius}" fill="{rng.choice((c.a,c.b))}" opacity=".8"/>'
        cls = c.animate(["rotate(-2deg)", "rotate(2deg)", "rotate(-2deg)"], "transform", rng.randrange(5, 10))
        c.add(f'<g transform="translate({x},{y})"><g class="{cls}">{tree}</g></g>')
        for _ in range(3):
            fx = x + rng.randrange(-40, 41)
            c.add(f'<path d="M{fx},{y+7} v-14" stroke="{c.a}"/><circle cx="{fx}" cy="{y-8}" r="4" fill="{c.gold}"/>')
    for _ in range(9):
        x, y = rng.randrange(70, 840), rng.randrange(120, 285)
        points = [(x+math.sin(t/6*math.tau)*15, y+math.cos(t/6*math.tau)*9) for t in range(7)]
        c.follow(points, f'<circle r="2.5" fill="{c.gold}"/>', rng.randrange(4, 10))
    if weather in ("rain", "snow"):
        for _ in range(24):
            x, y = rng.randrange(30, 870), rng.randrange(80, 330)
            glyph = f'<circle r="2" fill="{c.ink}" opacity=".55"/>' if weather == "snow" else f'<path d="M0,0 l-3,9" stroke="{c.muted}" opacity=".5"/>'
            c.follow([(x,y), (x-18,y+70)], glyph, 5 if weather == "snow" else 2)
    return f"Imaginary weather: {weather} / no watering streaks / everything grows at its own pace"


def orbit(c: Canvas, rng: random.Random) -> str:
    for _ in range(65):
        x, y = rng.randrange(30, 870), rng.randrange(80, 347)
        c.add(f'<circle cx="{x}" cy="{y}" r="{rng.choice((1,1,2))}" fill="{c.muted}" opacity=".55"/>')
    c.add(f'<circle cx="325" cy="213" r="36" fill="{c.a}"/><path d="M301,192 Q336,200 311,216 T335,241" fill="none" stroke="{c.bg}" stroke-width="8" opacity=".35"/>')
    for i, radius in enumerate((62, 97, 132)):
        c.add(f'<circle cx="325" cy="213" r="{radius}" fill="none" stroke="{c.muted}" opacity=".35"/>')
        phase = rng.random() * math.tau
        points = [(325+radius*math.cos(t/48*math.tau+phase), 213+radius*math.sin(t/48*math.tau+phase)) for t in range(49)]
        glyph = f'<path d="M-14,-4 h8 v8 h-8Z M6,-4 h8 v8 h-8Z" fill="{c.b}"/><rect x="-5" y="-6" width="10" height="12" rx="2" fill="{c.gold}"/>'
        c.follow(points, glyph, 12+i*7)
    c.text(570, 140, "INTERPLANETARY MAIL", 16, c.ink)
    for i, line in enumerate(("03 carriers in orbit", "01 tiny world to explore", "00 unread emergencies", "Delivery: eventually.")):
        c.text(570, 178+i*31, line)
    return "Orbital post office / different phases each day / no actual telemetry or tracking"


def life_step(cells: set[tuple[int, int]], w: int, h: int) -> set[tuple[int, int]]:
    result = set()
    for y in range(h):
        for x in range(w):
            count = sum((x+dx, y+dy) in cells for dx in (-1,0,1) for dy in (-1,0,1) if dx or dy)
            if count == 3 or (count == 2 and (x,y) in cells):
                result.add((x,y))
    return result


def life(c: Canvas, rng: random.Random) -> str:
    w, h = 28, 9
    cells = {(x,y) for y in range(h) for x in range(w) if rng.random() < .29}
    frames = [cells]
    for _ in range(23):
        frames.append(life_step(frames[-1], w, h))
    patterns = {}
    for y in range(h):
        for x in range(w):
            pattern = tuple("1" if (x,y) in frame else "0" for frame in frames)
            if pattern not in patterns:
                patterns[pattern] = c.animate(list(pattern), "opacity", 16, "steps(1,end)")
            px, py = 60+x*28, 87+y*28
            c.add(f'<rect x="{px}" y="{py}" width="24" height="24" rx="4" fill="{c.panel}"/><rect x="{px}" y="{py}" width="24" height="24" rx="4" fill="{c.a}" class="{patterns[pattern]}"/>')
    return "Conway B3/S23 / finite edges / 24 generations in 16s / the experiment then restarts"


def sort_traces(values: list[int]) -> tuple[list[list[int]], list[list[int]]]:
    a, bubble = values[:], [values[:]]
    for end in range(len(a)-1, 0, -1):
        changed = False
        for j in range(end):
            if a[j] > a[j+1]:
                a[j], a[j+1], changed = a[j+1], a[j], True
            bubble.append(a[:])
        if not changed:
            break
    a, insertion = values[:], [values[:]]
    for i in range(1, len(a)):
        j = i
        while j > 0:
            if a[j-1] <= a[j]:
                insertion.append(a[:])
                break
            a[j-1], a[j] = a[j], a[j-1]
            insertion.append(a[:])
            j -= 1
    return bubble, insertion


def sorting(c: Canvas, rng: random.Random) -> str:
    deck = list(range(1, 13))
    rng.shuffle(deck)
    traces = sort_traces(deck)
    length = max(map(len, traces)) + 12
    for row, (name, trace) in enumerate(zip(("BUBBLE", "INSERTION"), traces)):
        bottom = 194 + row*143
        c.text(42, bottom-80, f"{name} / {len(trace)-1} comparisons", 12, c.ink)
        c.add(f'<path d="M42,{bottom+1} H858" stroke="{c.muted}" opacity=".4"/>')
        for j in range(12):
            cls = c.animate([f"scaleY({trace[min(i,len(trace)-1)][j]/12:.4f})" for i in range(length)], "transform", 18, "steps(1,end)")
            c.add(f'<g transform="translate({64+j*66},{bottom})"><rect x="0" y="-70" width="45" height="70" rx="3" fill="{c.a if row==0 else c.b}" class="{cls}"/></g>')
    return "Same shuffled deck / one comparison per tick / completed rows wait at the finish"


def metro(c: Canvas, rng: random.Random) -> str:
    points = [(125, 170+rng.randrange(-20,21)), (265,102+rng.randrange(-12,13)), (590,106+rng.randrange(-15,16)),
              (788,170+rng.randrange(-15,16)), (698,291+rng.randrange(-18,19)), (390,317+rng.randrange(-12,12)), (160,270)]
    route = points + [points[0]]
    coords = " ".join(f"{x},{y}" for x,y in route)
    c.add(f'<polyline points="{coords}" fill="none" stroke="{c.panel}" stroke-width="24" stroke-linejoin="round"/><polyline points="{coords}" fill="none" stroke="{c.muted}" stroke-width="3" stroke-dasharray="4 8" stroke-linejoin="round"/>')
    names = rng.sample(("MOSS", "BYTE", "LUNA", "QUIET", "ROOT", "CACHE", "NOVA", "HOME", "ECHO", "FERN", "PORT", "LOOP"), 7)
    for (x,y), name in zip(points, names):
        c.add(f'<circle cx="{x}" cy="{y}" r="9" fill="{c.bg}" stroke="{c.a}" stroke-width="3"/>')
        c.text(x-20, y-17, name, 11, c.ink)
    for i in range(8):
        x, height = 280+i*42, rng.randrange(24, 65)
        c.add(f'<rect x="{x}" y="{255-height}" width="27" height="{height}" rx="3" fill="{c.panel}"/>')
        for j in range(2):
            c.add(f'<rect x="{x+6+j*11}" y="{262-height}" width="4" height="5" fill="{c.gold}"/>')
    for offset, color in ((0,c.a),(2,c.b),(4,c.gold)):
        shifted = points[offset:] + points[:offset]
        dwell = [p for p in shifted for _ in range(2)] + [shifted[0]]
        c.follow(dwell, f'<rect x="-12" y="-6" width="24" height="12" rx="5" fill="{color}"/><path d="M-5,-3 v6 M2,-3 v6" stroke="{c.bg}" stroke-width="3"/>', 28)
    return "7 imaginary stations / 3 trains / stop, breathe, move on / a new route tomorrow"


def deep_sea(c: Canvas, rng: random.Random) -> str:
    for i in range(5):
        y = 110+i*45
        c.add(f'<path d="M20,{y} Q220,{y-25} 450,{y} T880,{y}" stroke="{c.panel}" fill="none" stroke-width="16" opacity=".45"/>')
    c.add(f'<path d="M20,337 Q130,306 220,340 T480,325 T700,340 T880,312 V352 H20Z" fill="{c.panel}"/>')
    for _ in range(9):
        x, y = rng.randrange(45, 850), rng.randrange(125, 300)
        jelly = f'<path d="M-13,0 A13,13 0 0 1 13,0Z" fill="{c.b}" opacity=".7"/><path d="M-8,0 q-5,10 0,17 M0,0 q5,13 0,22 M8,0 q-4,9 0,17" stroke="{c.b}" fill="none"/>'
        c.follow([(x,y),(x+10,y-12),(x,y)], jelly, rng.randrange(5, 10))
    for _ in range(18):
        x, y = rng.randrange(35, 865), rng.randrange(100, 338)
        c.follow([(x,y),(x+12,y-70)], f'<circle r="2" stroke="{c.a}" fill="none" opacity=".4"/>', rng.randrange(5, 12))
    sub = f'<path d="M-24,-12 H15 A15,15 0 0 1 15,18 H-24Z" fill="{c.gold}"/><path d="M-8,-12 v-12 h14" stroke="{c.gold}" stroke-width="7" fill="none"/><circle cx="12" cy="3" r="8" fill="{c.bg}"/><circle cx="12" cy="3" r="4" fill="{c.a}"/><path d="M-28,-8 v23" stroke="{c.muted}" stroke-width="4"/>'
    c.follow([(160,220),(330,181),(610,222),(750,190),(610,222),(330,181),(160,220)], sub, 30)
    return "Bioluminescent drift / jellyfish, bubbles, one small submarine / no score to chase"


RENDERERS = dict(zip(ORIGINALS, (neon_race, dungeon, garden, orbit, life, sorting, metro, deep_sea)))


def hidden_chip(day: str, selected: str) -> tuple[int, int]:
    rng = rng_for(day, selected + ":stowaway")
    return rng.randrange(65, 836), rng.randrange(92, 333)


def render_scene(selected: str, day: str, theme: str = "dark") -> str:
    if selected not in ORIGINALS or theme not in PALETTES:
        raise ValueError("Unknown original scene or theme")
    canvas = Canvas(ORIGINALS[selected][0], day, theme)
    footer = RENDERERS[selected](canvas, rng_for(day, selected))
    return canvas.finish(footer, hidden_chip(day, selected))


def generate_originals(output: Path, selected: str, day: str, all_scenes: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name in ORIGINALS if all_scenes else ([selected] if selected in ORIGINALS else []):
        for theme in PALETTES:
            (output / f"{name}-{theme}.svg").write_text(render_scene(name, day, theme), encoding="utf-8")


def scene_secret(selected: str, day: str) -> str:
    if selected not in ORIGINALS:
        return ""
    x, y = hidden_chip(day, selected)
    extra = ""
    if selected == "neon-race":
        finishes, _ = race_model(rng_for(day, selected))
        extra = f"Race winner: **{('NOVA','BYTE','ECHO','FLUX')[finishes.index(min(finishes))]}**. "
    return ("<details>\n<summary>Bonus hunt: find the tiny gold robot · reveal location</summary>\n\n"
            f"{extra}The stowaway is approximately **{round(x/9)}% from the left, {round(y/4)}% from the top** of the image.\n\n</details>")
