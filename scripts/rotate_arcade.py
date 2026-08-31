#!/usr/bin/env python3
"""Choose the next profile arcade experience and prepare publish metadata."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path
from typing import Any


ARCADE_EXPERIENCES = (
    "space-shooter",
    "breakout",
    "snake",
    "maze-chase",
    "3d-city",
)

EXPERIENCE_DETAILS = {
    "space-shooter": {
        "title": "Space Shooter",
        "icon": "🚀",
        "description": "Today's contribution grid has entered bullet-hell mode.",
        "light": "./assets/arcade/space-shooter.gif",
    },
    "breakout": {
        "title": "Breakout",
        "icon": "🧱",
        "description": "A tiny paddle is clearing the year's contribution bricks.",
        "light": "./assets/arcade/breakout-light.svg",
        "dark": "./assets/arcade/breakout-dark.svg",
    },
    "snake": {
        "title": "Snake",
        "icon": "🐍",
        "description": "The classic contribution snake is having lunch.",
        "light": "./assets/arcade/snake-light.svg",
        "dark": "./assets/arcade/snake-dark.svg",
    },
    "maze-chase": {
        "title": "Maze Chase",
        "icon": "👻",
        "description": "Dots, ghosts, and a full year of commits to chase.",
        "light": "./assets/arcade/maze-chase-light.svg",
        "dark": "./assets/arcade/maze-chase-dark.svg",
    },
    "3d-city": {
        "title": "3D Contribution City",
        "icon": "🏙️",
        "description": "Today's commits have been rebuilt as a tiny skyline.",
        "light": "./assets/arcade/3d-city.svg",
    },
}

START_MARKER = "<!-- ARCADE:START -->"
END_MARKER = "<!-- ARCADE:END -->"


def choose_next(state: dict[str, Any], rng: random.Random) -> tuple[str, dict[str, Any]]:
    """Draw from a shuffle bag, covering every experience before refilling it."""
    current = state.get("current")
    remaining = [name for name in state.get("remaining", []) if name in ARCADE_EXPERIENCES]
    cycle = int(state.get("cycle", 0))

    if not remaining:
        remaining = list(ARCADE_EXPERIENCES)
        rng.shuffle(remaining)
        if current and len(remaining) > 1 and remaining[0] == current:
            remaining[0], remaining[1] = remaining[1], remaining[0]
        cycle += 1

    selected = remaining.pop(0)
    return selected, {"current": selected, "remaining": remaining, "cycle": cycle}


def force_selection(state: dict[str, Any], selected: str) -> dict[str, Any]:
    if selected not in ARCADE_EXPERIENCES:
        raise ValueError(f"Unknown arcade experience: {selected}")
    remaining = [
        name
        for name in state.get("remaining", [])
        if name in ARCADE_EXPERIENCES and name != selected
    ]
    return {
        "current": selected,
        "remaining": remaining,
        "cycle": int(state.get("cycle", 0)),
    }


def render_arcade_block(selected: str) -> str:
    details = EXPERIENCE_DETAILS[selected]
    picture_lines = ["<p align=\"center\">", "  <picture>"]
    if details.get("dark"):
        picture_lines.extend(
            [
                '    <source media="(prefers-color-scheme: dark)"',
                f'            srcset="{details["dark"]}">',
            ]
        )
    picture_lines.extend(
        [
            f'    <img src="{details["light"]}"',
            f'         alt="{details["title"]}" width="100%">',
            "  </picture>",
            "</p>",
        ]
    )
    return "\n".join(
        [
            f"## Today's Arcade: {details['title']} {details['icon']}",
            "",
            details["description"],
            "",
            *picture_lines,
            "",
            "<p align=\"center\"><sub>🎲 A different experience is drawn every day · no back-to-back repeats</sub></p>",
        ]
    )


def replace_arcade_block(readme: str, block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL
    )
    if len(pattern.findall(readme)) != 1:
        raise ValueError("README must contain exactly one arcade marker block")
    return pattern.sub(f"{START_MARKER}\n{block}\n{END_MARKER}", readme)


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"current": None, "remaining": [], "cycle": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def write_github_output(path: str | None, values: dict[str, str]) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path(".github/arcade-state.json"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--output-dir", type=Path, default=Path(".rotation-output"))
    parser.add_argument("--seed", default=os.environ.get("GITHUB_RUN_ID", "local-preview"))
    parser.add_argument("--experience", default="random")
    parser.add_argument("--generation-mode", choices=("selected", "all"), default="selected")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()

    state = read_state(args.state)
    if args.experience == "random":
        selected, next_state = choose_next(state, random.Random(args.seed))
    else:
        selected = args.experience
        next_state = force_selection(state, selected)

    next_state["updated_on"] = os.environ.get("ARCADE_DATE", "automated")
    readme = args.readme.read_text(encoding="utf-8")
    next_readme = replace_arcade_block(readme, render_arcade_block(selected))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "README.next.md").write_text(next_readme, encoding="utf-8")
    (args.output_dir / "arcade-state.next.json").write_text(
        json.dumps(next_state, indent=2) + "\n", encoding="utf-8"
    )
    selection = {"selected": selected, "mode": args.generation_mode}
    (args.output_dir / "selection.json").write_text(
        json.dumps(selection, indent=2) + "\n", encoding="utf-8"
    )
    write_github_output(
        args.github_output,
        {"selected": selected, "mode": args.generation_mode},
    )
    print(f"Selected arcade experience: {selected} ({args.generation_mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
