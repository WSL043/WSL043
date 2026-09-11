"""Solvable daily puzzles and an honest, publish-driven shared expedition."""
from __future__ import annotations

import copy
import itertools
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from functools import lru_cache
from typing import Any

try:
    from scripts.original_arcade import rng_for, scene_secret
except ModuleNotFoundError:
    from original_arcade import rng_for, scene_secret

KINDS = ("vault", "nim", "route", "lights", "twenty-four", "knight")
BIOMES = ("Moss Station", "Glass Desert", "Tidal Library", "Neon Orchard", "Lunar Market", "Cloud Railway", "Coral Archive", "Quiet Observatory")
RELICS = tuple(f"{a} {b}" for a in ("Moss", "Lunar", "Coral", "Neon", "Amber", "Clockwork")
               for b in ("Compass", "Key", "Lantern", "Seed", "Ticket", "Shell", "Feather", "Badge"))


@dataclass(frozen=True)
class Puzzle:
    kind: str
    title: str
    prompt: str
    hint: str
    answer: str
    data: dict[str, Any] = field(default_factory=dict)


def puzzle_kind(day: str) -> str:
    block, offset = divmod(date.fromisoformat(day).toordinal(), len(KINDS))
    def bag(n: int) -> list[str]:
        result = list(KINDS)
        rng_for("2000-01-01", f"puzzle-bag-{n}").shuffle(result)
        return result
    current, previous = bag(block), bag(block-1)
    # Only the first two positions can change, so the previous bag's last is stable.
    if current[0] == previous[-1]:
        current[0], current[1] = current[1], current[0]
    return current[offset]


def vault_score(guess: tuple[int, ...], secret: tuple[int, ...]) -> tuple[int, int]:
    exact = sum(a == b for a, b in zip(guess, secret))
    return exact, len(set(guess) & set(secret)) - exact


def vault(rng) -> Puzzle:
    pool = list(itertools.permutations(range(6), 3))
    secret = rng.choice(pool)
    remaining, guesses, clues = pool[:], [p for p in pool if p != secret], []
    rng.shuffle(guesses)
    while len(remaining) > 1:
        # Choose an informative clue; retain the target but never print it as a guess.
        guess = min(guesses, key=lambda g: sum(vault_score(g, s) == vault_score(g, secret) for s in remaining))
        score = vault_score(guess, secret)
        clues.append((guess, score))
        remaining = [s for s in remaining if vault_score(guess, s) == score]
        guesses.remove(guess)
    rows = "\n".join(f"| `{''.join(map(str,g))}` | {e} | {m} |" for g, (e,m) in clues)
    prompt = ("Crack a **three-digit code** using digits **0–5, without repeats**. A leading zero is allowed.\n\n"
              "Counts are exact; 'misplaced' excludes correctly placed digits.\n\n"
              "| Guess | Correct place | Correct digit, wrong place |\n| --- | --- | --- |\n" + rows)
    return Puzzle("vault", "The clockwork vault", prompt, "For each clue, add both counts to find how many of its digits belong in the code. Check the positions separately.",
                  f"The unique code is **{''.join(map(str,secret))}**. All 120 possible codes were checked.", {"secret": secret, "clues": clues})


def nim(rng) -> Puzzle:
    while True:
        piles = [rng.randrange(1, 13) for _ in range(3)]
        xor = piles[0] ^ piles[1] ^ piles[2]
        if xor:
            break
    moves = [(i, value-(value^xor)) for i, value in enumerate(piles) if (value^xor) < value]
    i, amount = moves[0]
    return Puzzle("nim", "Three piles, one good move",
                  f"Piles A, B, C contain **{piles[0]}, {piles[1]}, {piles[2]}** crystals. Two players alternate.\n\n"
                  "Remove one or more crystals from exactly one pile. Taking the last crystal wins. Find a move that forces a win with perfect play.",
                  "Aim to make the bitwise XOR of the three pile sizes equal to zero.",
                  f"One winning move: take **{amount}** from pile **{'ABC'[i]}**, leaving **{piles[i]-amount}** there. The new XOR is zero. Other winning moves may exist.",
                  {"piles": piles, "moves": moves})


def cheapest_path(grid: list[list[int]]) -> tuple[int, list[tuple[int, int]]]:
    h, w = len(grid), len(grid[0])
    costs, paths = {}, {}
    for y in range(h):
        for x in range(w):
            choices = [p for p in ((x-1,y),(x,y-1)) if p in costs]
            prev = min(choices, key=costs.get) if choices else None
            costs[x,y] = grid[y][x] + (costs[prev] if prev else 0)
            paths[x,y] = (paths[prev] if prev else []) + [(x,y)]
    return costs[w-1,h-1], paths[w-1,h-1]


def route(rng) -> Puzzle:
    grid = [[rng.randrange(1, 10) for _ in range(4)] for _ in range(4)]
    cost, path = cheapest_path(grid)
    table = "\n".join(" ".join(map(str,row)) for row in grid)
    directions = " → ".join("R" if x2>x1 else "D" for (x1,y1),(x2,y2) in zip(path,path[1:]))
    return Puzzle("route", "The cheapest delivery",
                  "Go from the top-left to the bottom-right, moving **only right or down**. Each cell costs its number, **including the start and destination**. What is the minimum total?\n\n```text\n"+table+"\n```",
                  "At each cell, keep its cost plus the cheaper of the totals immediately above and to the left.",
                  f"Minimum energy: **{cost}**. One optimal route: **{directions}**. Equal-cost alternatives are valid.", {"grid": grid, "cost": cost, "path": path})


def light_mask(index: int) -> int:
    x, y = index % 3, index // 3
    return sum(1 << (ny*3+nx) for nx, ny in ((x,y),(x-1,y),(x+1,y),(x,y-1),(x,y+1)) if 0<=nx<3 and 0<=ny<3)


def apply_lights(board: int, presses: int) -> int:
    for i in range(9):
        if presses & (1 << i):
            board ^= light_mask(i)
    return board


@lru_cache(maxsize=1)
def light_solutions() -> dict[int, int]:
    result = {}
    for presses in range(512):
        board = apply_lights(0, presses)
        if board not in result or presses.bit_count() < result[board].bit_count():
            result[board] = presses
    return result


def lights(rng) -> Puzzle:
    solutions = light_solutions()
    board = rng.choice(sorted(b for b in solutions if b and solutions[b].bit_count() >= 3))
    presses = solutions[board]
    rows = ["  ".join(f"{i+1}:{'●' if board&(1<<i) else '○'}" for i in range(y*3,y*3+3)) for y in range(3)]
    buttons = [i+1 for i in range(9) if presses&(1<<i)]
    return Puzzle("lights", "Lights out at the workshop",
                  "Turn every light off. Pressing a numbered cell toggles **itself and its orthogonal neighbors**, never diagonals. ● = on, ○ = off. No wrapping.\n\n```text\n"+"\n".join(rows)+"\n```",
                  "Pressing the same button twice cancels out. The order of different presses does not matter.",
                  f"Press **{', '.join(map(str,buttons))}**, in any order. This uses the minimum **{len(buttons)}** presses.", {"board": board, "presses": presses})


def solve_24(numbers: tuple[int, ...]) -> str | None:
    failed = set()
    def solve(items: list[tuple[Fraction, str]]) -> str | None:
        key = tuple(sorted(v for v, _ in items))
        if key in failed:
            return None
        if len(items) == 1:
            return items[0][1] if items[0][0] == 24 else None
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                a, sa = items[i]
                b, sb = items[j]
                rest = [item for k, item in enumerate(items) if k not in (i,j)]
                operations = [(a+b, f"({sa}+{sb})"), (a-b, f"({sa}-{sb})"), (b-a, f"({sb}-{sa})"), (a*b, f"({sa}*{sb})")]
                if b:
                    operations.append((a/b, f"({sa}/{sb})"))
                if a:
                    operations.append((b/a, f"({sb}/{sa})"))
                for value, expr in operations:
                    answer = solve(rest+[(value,expr)])
                    if answer is not None:
                        return answer
        failed.add(key)
        return None
    return solve([(Fraction(n), str(n)) for n in numbers])


def twenty_four(rng) -> Puzzle:
    for _ in range(40):
        numbers = tuple(rng.randrange(1, 10) for _ in range(4))
        answer = solve_24(numbers)
        if answer:
            break
    else:
        numbers, answer = (3,3,8,8), "(8/(3-(8/3)))"
    return Puzzle("twenty-four", "Four cards to twenty-four",
                  f"Today's cards: **{' · '.join(map(str,numbers))}**. Make exactly **24** using every card once.\n\nOnly `+`, `−`, `×`, `÷` and parentheses are allowed; no joining digits.",
                  "Intermediate fractions and negative numbers are allowed. Division can create a small denominator.",
                  f"One exact solution: `{answer} = 24`. This is checked with fractions, not rounded floating-point numbers.", {"numbers": numbers, "expression": answer})


def knight_paths(start: tuple[int,int]) -> dict[tuple[int,int], list[tuple[int,int]]]:
    paths, queue = {start:[start]}, deque([start])
    while queue:
        x,y = queue.popleft()
        for dx,dy in ((1,2),(2,1),(-1,2),(-2,1),(1,-2),(2,-1),(-1,-2),(-2,-1)):
            nxt = x+dx,y+dy
            if 0<=nxt[0]<4 and 0<=nxt[1]<4 and nxt not in paths:
                paths[nxt] = paths[x,y]+[nxt]
                queue.append(nxt)
    return paths


def knight(rng) -> Puzzle:
    start = rng.randrange(4),rng.randrange(4)
    paths = knight_paths(start)
    goal = rng.choice([p for p in paths if len(paths[p]) >= 4])
    path = paths[goal]
    def label(p):
        return f"{'ABCD'[p[0]]}{p[1]+1}"
    rows = ["    A B C D"]
    for y in range(4):
        rows.append(f"{y+1}   "+" ".join("S" if (x,y)==start else "T" if (x,y)==goal else "." for x in range(4)))
    return Puzzle("knight", "The tiny knight's detour",
                  f"On this **4×4 board**, get from S ({label(start)}) to T ({label(goal)}) in the fewest knight moves: two cells along one axis and one along the other. Stay on the board.\n\n```text\n"+"\n".join(rows)+"\n```",
                  "Explore all one-move destinations, then all two-move destinations. Going away from the target can help.",
                  f"Minimum: **{len(path)-1} moves**. One route: **{' → '.join(map(label,path))}**.", {"start":start,"goal":goal,"path":path})


BUILDERS = dict(zip(KINDS, (vault,nim,route,lights,twenty_four,knight)))


def make_puzzle(day: str, kind: str | None = None) -> Puzzle:
    kind = kind or puzzle_kind(day)
    if kind not in BUILDERS:
        raise ValueError(f"Unknown puzzle: {kind}")
    return BUILDERS[kind](rng_for(day, "puzzle:"+kind))


def advance_world(previous: dict[str, Any] | None, day: str, scene: str) -> dict[str, Any]:
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Date must use YYYY-MM-DD")
    world = copy.deepcopy(previous or {})
    if world.get("last_date") == day:
        return world
    if world.get("last_date", "") > day:
        raise ValueError("Refusing to rewind the expedition; use a separate preview state")
    days = world.get("days", 0)
    if type(days) is not int or days < 0:
        raise ValueError("Invalid expedition day count")
    days += 1
    rng = rng_for(day, "expedition")
    deck = list(RELICS)
    rng_for("2000-01-01", "relic-deck").shuffle(deck)
    item = deck[(days-1) % len(deck)]
    inventory = world.get("inventory", [])
    if not isinstance(inventory, list) or any(r not in RELICS for r in inventory):
        raise ValueError("Invalid expedition inventory")
    inventory = list(dict.fromkeys(inventory+[item]))
    biome = BIOMES[((days-1)//6) % len(BIOMES)]
    rare = days % 7 == 0 or rng.randrange(12) == 0
    if rare:
        event = rng.choice(("A glass comet rang like a wind chime.", "Moon jellies held a lantern parade.", "An upside-down rainbow opened a secret platform.", "The entire station floated one centimeter off the ground."))
    else:
        event = (rng.choice(("A shy robot", "The night conductor", "A wandering seed", "A clockwork snail", "An off-duty satellite", "The station keeper"))
                 + " " + rng.choice(("delivered", "borrowed", "carefully repaired", "discovered", "left a note beside", "traded a story for"))
                 + " " + rng.choice(("a humming teacup.", "an unfinished map.", "a very small moon.", "a pocket-sized lighthouse.", "an envelope full of rain.", "a ticket to nowhere in particular.")))
    entry = {"date":day,"biome":biome,"event":event,"relic":item,"rare":rare,"scene":scene}
    world.update({"version":1,"days":days,"last_date":day,"inventory":inventory,"history":(world.get("history",[])+[entry])[-7:]})
    return world


def render_extras(day: str, selected: str, world: dict[str, Any]) -> str:
    puzzle = make_puzzle(day)
    last = world["history"][-1]
    volume, stop = divmod(world["days"]-1, len(RELICS))
    journal = "\n".join(f"| {entry['date']} | {entry['biome']} | {'✦ ' if entry['rare'] else ''}{entry['event']} |" for entry in reversed(world["history"]))
    inventory = " · ".join(world["inventory"])
    return f'''{scene_secret(selected, day)}

<details>
<summary>🧩 Today's pocket quest: {puzzle.title} · open to play</summary>

{puzzle.prompt}

<details>
<summary>A small hint</summary>

{puzzle.hint}

</details>

<details>
<summary>Reveal the answer</summary>

{puzzle.answer}

</details>

</details>

**Postcard #{world['days']} · {last['biome']}** — {'✦ Rare encounter! ' if last['rare'] else ''}{last['event']}

<details>
<summary>🎒 Expedition journal · {len(world['inventory'])}/48 keepsakes · volume {volume+1}, stop {stop+1}/48</summary>

Today's keepsake: **{last['relic']}**.

| Published | Stop | Field note |
| --- | --- | --- |
{journal}

**Collection:** {inventory}

This is a shared fictional expedition. It advances once per successfully published calendar day (UTC), **not** per visitor, click, or solved puzzle. Missed days do not reset it or create catch-up chores. Every seventh expedition day guarantees a rare encounter. Collections remain after a new volume starts.

</details>

<sub>{day} · 6 puzzle families · generated locally, no trackers · <a href="./ARCADE.md">How this little world works</a></sub>'''
