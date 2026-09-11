#!/usr/bin/env python3
"""Choose a daily scene, generate originals, and stage a complete profile update."""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.original_arcade import ORIGINALS, generate_originals
    from scripts.daily_quests import advance_world, render_extras
except ModuleNotFoundError:  # Direct execution from the repository root.
    from original_arcade import ORIGINALS, generate_originals
    from daily_quests import advance_world, render_extras

LEGACY_EXPERIENCES = ("space-shooter", "breakout", "snake", "maze-chase", "3d-city")
ARCADE_EXPERIENCES = LEGACY_EXPERIENCES + tuple(ORIGINALS)
EXPERIENCE_DETAILS = {
    "space-shooter": {"title":"Space Shooter", "icon":"🚀", "description":"Today's contribution grid has entered bullet-hell mode.", "light":"./assets/arcade/space-shooter.gif"},
    "breakout": {"title":"Breakout", "icon":"🧱", "description":"A tiny paddle is clearing the year's contribution bricks.", "light":"./assets/arcade/breakout-light.svg", "dark":"./assets/arcade/breakout-dark.svg"},
    "snake": {"title":"Snake", "icon":"🐍", "description":"The classic contribution snake is having lunch.", "light":"./assets/arcade/snake-light.svg", "dark":"./assets/arcade/snake-dark.svg"},
    "maze-chase": {"title":"Maze Chase", "icon":"👻", "description":"Dots, ghosts, and a full year of commits to chase.", "light":"./assets/arcade/maze-chase-light.svg", "dark":"./assets/arcade/maze-chase-dark.svg"},
    "3d-city": {"title":"3D Contribution City", "icon":"🏙️", "description":"Today's commits have been rebuilt as a tiny skyline.", "light":"./assets/arcade/3d-city.svg"},
}
EXPERIENCE_DETAILS.update({name: {"title":title,"icon":icon,"description":description,
    "light":f"./assets/arcade/{name}-light.svg", "dark":f"./assets/arcade/{name}-dark.svg"}
    for name,(title,icon,description) in ORIGINALS.items()})
START_MARKER, END_MARKER = "<!-- ARCADE:START -->", "<!-- ARCADE:END -->"


def normalized_bag(state: dict[str, Any], rng: random.Random) -> list[str]:
    remaining = state.get("remaining", [])
    known = state.get("catalog", list(LEGACY_EXPERIENCES if state.get("current") else ARCADE_EXPERIENCES))
    if not isinstance(remaining, list) or not isinstance(known, list):
        raise ValueError("Invalid shuffle-bag state")
    if any(not isinstance(name, str) for name in remaining + known):
        raise ValueError("Shuffle-bag names must be strings")
    bag = list(dict.fromkeys(name for name in remaining if name in ARCADE_EXPERIENCES and name != state.get("current")))
    additions = [name for name in ARCADE_EXPERIENCES if name not in known and name not in bag and name != state.get("current")]
    rng.shuffle(additions)
    return additions + bag


def choose_next(state: dict[str, Any], rng: random.Random) -> tuple[str, dict[str, Any]]:
    """Migrate old bags, then cover each cartridge before refilling. Never mutate input."""
    remaining = normalized_bag(state, rng)
    cycle = int(state.get("cycle", 0))
    if not remaining:
        remaining = list(ARCADE_EXPERIENCES)
        rng.shuffle(remaining)
        if remaining[0] == state.get("current") and len(remaining) > 1:
            remaining[0], remaining[1] = remaining[1], remaining[0]
        cycle += 1
    selected = remaining.pop(0)
    next_state = copy.deepcopy(state)
    next_state.update(current=selected, remaining=remaining, cycle=cycle, catalog=list(ARCADE_EXPERIENCES))
    return selected, next_state


def force_selection(state: dict[str, Any], selected: str) -> dict[str, Any]:
    if selected not in ARCADE_EXPERIENCES:
        raise ValueError(f"Unknown arcade experience: {selected}")
    remaining = [name for name in normalized_bag(state, random.Random("manual-migration")) if name != selected]
    result = copy.deepcopy(state)
    result.update(current=selected, remaining=remaining, cycle=int(state.get("cycle",0)), catalog=list(ARCADE_EXPERIENCES))
    return result


def prepare_rotation(state: dict[str, Any], day: str, requested: str = "random", seed: str | None = None) -> tuple[str, dict[str, Any]]:
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Date must use YYYY-MM-DD")
    same_day = (state.get("schema") == 2 and state.get("updated_on") == day
                and state.get("world", {}).get("last_date") == day
                and state.get("catalog") == list(ARCADE_EXPERIENCES)
                and state.get("current") in ARCADE_EXPERIENCES)
    if requested == "random" and same_day:
        return state["current"], copy.deepcopy(state)
    if requested == "random":
        selected, next_state = choose_next(state, random.Random(seed or f"{day}|WSL043|rotation"))
    else:
        selected, next_state = requested, force_selection(state, requested)
    next_state.update(schema=2, updated_on=day)
    next_state["world"] = advance_world(state.get("world"), day, selected)
    return selected, next_state


def render_arcade_block(selected: str, extras: str = "", day: str | None = None) -> str:
    details = EXPERIENCE_DETAILS[selected]
    suffix = f"?v={day}" if day else ""
    picture = ['<p align="center">', '  <picture>']
    if details.get("dark"):
        picture += ['    <source media="(prefers-color-scheme: dark)"', f'            srcset="{details["dark"]}{suffix}">']
    picture += [f'    <img src="{details["light"]}{suffix}"', f'         alt="{details["title"]} — autoplay scene" width="100%">', '  </picture>', '</p>']
    return "\n".join([f"## Today's Arcade: {details['title']} {details['icon']}", "", details["description"], "", *picture, "",
        '<p align="center"><sub>🎲 13 cartridges · a full shuffle-bag rotation · no back-to-back daily repeats</sub></p>', "", extras]).rstrip()


def replace_arcade_block(readme: str, block: str) -> str:
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError("README must contain exactly one arcade marker block")
    pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)
    if len(pattern.findall(readme)) != 1:
        raise ValueError("README arcade markers are out of order")
    # A callable replacement preserves literal backslashes in generated puzzle text.
    return pattern.sub(lambda _: f"{START_MARKER}\n{block}\n{END_MARKER}", readme)


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"current":None, "remaining":[], "cycle":0}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Arcade state must be a JSON object")
    return state


def write_github_output(path: str | None, values: dict[str, str]) -> None:
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path(".github/arcade-state.json"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--output-dir", type=Path, default=Path("rotation-output"))
    parser.add_argument("--date", default=os.environ.get("ARCADE_DATE"))
    parser.add_argument("--seed", default=None, help="Optional rotation seed; same-day retries still keep the published draw")
    parser.add_argument("--experience", choices=("random",)+ARCADE_EXPERIENCES, default="random")
    parser.add_argument("--generation-mode", choices=("selected","all"), default="selected")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    day = args.date or datetime.now(timezone.utc).date().isoformat()
    selected, state = prepare_rotation(read_state(args.state), day, args.experience, args.seed)
    extras = render_extras(day, selected, state["world"])
    next_readme = replace_arcade_block(args.readme.read_text(encoding="utf-8"), render_arcade_block(selected, extras, day))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generate_originals(args.output_dir / "originals", selected, day, args.generation_mode == "all")
    (args.output_dir / "README.next.md").write_text(next_readme, encoding="utf-8")
    (args.output_dir / "arcade-state.next.json").write_text(json.dumps(state, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    selection = {"selected":selected,"mode":args.generation_mode,"native":str(selected in ORIGINALS).lower()}
    (args.output_dir / "selection.json").write_text(json.dumps(selection, indent=2)+"\n", encoding="utf-8")
    write_github_output(args.github_output, selection)
    print(f"Selected {selected} for {day}; staged {args.generation_mode} assets. Live files are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
