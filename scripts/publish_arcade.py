#!/usr/bin/env python3
"""Validate every input before copying; the subsequent Git commit publishes atomically."""
from __future__ import annotations

import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from scripts.rotate_arcade import ARCADE_EXPERIENCES
    from scripts.original_arcade import ORIGINALS
except ModuleNotFoundError:
    from rotate_arcade import ARCADE_EXPERIENCES
    from original_arcade import ORIGINALS

ASSET_MAP = {
    "space-shooter": (("space-shooter.gif", "space-shooter.gif"),),
    "breakout": (("breakout-light.svg", "breakout-light.svg"), ("breakout-dark.svg", "breakout-dark.svg")),
    "snake": (("snake-light.svg", "snake-light.svg"), ("snake-dark.svg", "snake-dark.svg")),
    "maze-chase": (("maze-chase-light.svg", "maze-chase-light.svg"), ("maze-chase-dark.svg", "maze-chase-dark.svg")),
    "3d-city": (("3d-city.svg", "3d-city.svg"),),
}
ASSET_MAP.update({name: tuple((f"{name}-{theme}.svg", f"{name}-{theme}.svg") for theme in ("light","dark")) for name in ORIGINALS})


def validate_svg(path: Path) -> None:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    if root.tag.rsplit("}",1)[-1] != "svg":
        raise ValueError(f"Not an SVG: {path}")
    for element in root.iter():
        if element.tag.rsplit("}",1)[-1] in ("script", "foreignObject"):
            raise ValueError(f"Executable SVG content rejected: {path}")
        for key, value in element.attrib.items():
            name = key.rsplit("}",1)[-1].lower()
            if name.startswith("on") or (name == "href" and not value.startswith("#")):
                raise ValueError(f"External or executable SVG attribute rejected: {path}")


def publish(root: Path, staging: Path) -> None:
    metadata = staging / "rotation-metadata"
    selection = json.loads((metadata / "selection.json").read_text(encoding="utf-8"))
    selected, mode = selection["selected"], selection.get("mode","selected")
    if selected not in ARCADE_EXPERIENCES or mode not in ("selected","all"):
        raise ValueError("Unknown selected experience or generation mode")
    modules = ARCADE_EXPERIENCES if mode == "all" else (selected,)
    planned_copies = []
    for module in modules:
        directory = metadata / "originals" if module in ORIGINALS else staging / "generators"
        for source_name, destination_name in ASSET_MAP[module]:
            source = directory / source_name
            if not source.is_file() or source.stat().st_size == 0:
                raise FileNotFoundError(f"Missing generated asset for {module}: {source}")
            if module in ORIGINALS:
                validate_svg(source)
            planned_copies.append((source, root / "assets" / "arcade" / destination_name))
    next_readme, next_state = metadata / "README.next.md", metadata / "arcade-state.next.json"
    if not next_readme.is_file() or not next_state.is_file():
        raise FileNotFoundError("Rotation metadata is incomplete")
    state = json.loads(next_state.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Invalid next state")
    if state.get("schema") == 2 and (state.get("current") != selected or state.get("world",{}).get("last_date") != state.get("updated_on")):
        raise ValueError("Selection, expedition and next-state metadata disagree")
    if not next_readme.read_text(encoding="utf-8").strip():
        raise ValueError("Refusing to publish an empty profile")
    # No live files have been touched before all validation above passes.
    planned_copies += [(next_readme, root / "README.md"), (next_state, root / ".github" / "arcade-state.json")]
    for source, destination in planned_copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--staging", type=Path, default=Path("staging"))
    args = parser.parse_args()
    publish(args.root.resolve(), args.staging.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
