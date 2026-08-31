#!/usr/bin/env python3
"""Publish a validated rotation without exposing a partially updated profile."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from scripts.rotate_arcade import ARCADE_EXPERIENCES
except ModuleNotFoundError:  # Direct execution: python scripts/publish_arcade.py
    from rotate_arcade import ARCADE_EXPERIENCES


ASSET_MAP = {
    "space-shooter": (("space-shooter.gif", "space-shooter.gif"),),
    "breakout": (
        ("breakout-light.svg", "breakout-light.svg"),
        ("breakout-dark.svg", "breakout-dark.svg"),
    ),
    "snake": (
        ("snake-light.svg", "snake-light.svg"),
        ("snake-dark.svg", "snake-dark.svg"),
    ),
    "maze-chase": (
        ("maze-chase-light.svg", "maze-chase-light.svg"),
        ("maze-chase-dark.svg", "maze-chase-dark.svg"),
    ),
    "3d-city": (("3d-city.svg", "3d-city.svg"),),
}


def publish(root: Path, staging: Path) -> None:
    metadata = staging / "rotation-metadata"
    selection = json.loads((metadata / "selection.json").read_text(encoding="utf-8"))
    selected = selection["selected"]
    mode = selection.get("mode", "selected")
    if selected not in ARCADE_EXPERIENCES:
        raise ValueError(f"Unknown selected experience: {selected}")

    modules = ARCADE_EXPERIENCES if mode == "all" else (selected,)
    planned_copies: list[tuple[Path, Path]] = []
    for module in modules:
        artifact_dir = staging / "generators" / f"arcade-{module}"
        for source_name, destination_name in ASSET_MAP[module]:
            source = artifact_dir / source_name
            if not source.is_file() or source.stat().st_size == 0:
                raise FileNotFoundError(f"Missing generated asset for {module}: {source}")
            planned_copies.append((source, root / "assets" / "arcade" / destination_name))

    next_readme = metadata / "README.next.md"
    next_state = metadata / "arcade-state.next.json"
    if not next_readme.is_file() or not next_state.is_file():
        raise FileNotFoundError("Rotation metadata is incomplete")

    for source, destination in planned_copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(next_readme, root / "README.md")
    shutil.copyfile(next_state, root / ".github" / "arcade-state.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--staging", type=Path, default=Path("staging"))
    args = parser.parse_args()
    publish(args.root.resolve(), args.staging.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
