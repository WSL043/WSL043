import json
import random
import tempfile
import unittest
from pathlib import Path

from scripts.rotate_arcade import (
    ARCADE_EXPERIENCES,
    choose_next,
    render_arcade_block,
    replace_arcade_block,
)


class RotationTests(unittest.TestCase):
    def test_shuffle_bag_shows_every_experience_once_without_repeats(self):
        state = {"current": None, "remaining": [], "cycle": 0}
        seen = []

        for _ in ARCADE_EXPERIENCES:
            selected, state = choose_next(state, random.Random(20260831 + len(seen)))
            seen.append(selected)

        self.assertEqual(set(seen), set(ARCADE_EXPERIENCES))
        self.assertEqual(len(seen), len(set(seen)))

    def test_new_cycle_never_repeats_previous_day(self):
        current = ARCADE_EXPERIENCES[-1]
        selected, _ = choose_next(
            {"current": current, "remaining": [], "cycle": 3},
            random.Random(4),
        )

        self.assertNotEqual(selected, current)

    def test_arcade_block_uses_theme_aware_picture_when_available(self):
        block = render_arcade_block("breakout")

        self.assertIn("Today's Arcade: Breakout", block)
        self.assertIn("prefers-color-scheme: dark", block)
        self.assertIn("./assets/arcade/breakout-dark.svg", block)
        self.assertIn("./assets/arcade/breakout-light.svg", block)

    def test_replacement_preserves_everything_outside_markers(self):
        original = (
            "before\n"
            "<!-- ARCADE:START -->\nold\n<!-- ARCADE:END -->\n"
            "after\n"
        )

        updated = replace_arcade_block(original, render_arcade_block("snake"))

        self.assertTrue(updated.startswith("before\n<!-- ARCADE:START -->"))
        self.assertTrue(updated.endswith("<!-- ARCADE:END -->\nafter\n"))
        self.assertNotIn("\nold\n", updated)
        self.assertIn("Today's Arcade: Snake", updated)


class PublicationTests(unittest.TestCase):
    def test_flat_single_artifact_layout_publishes_selected_experience(self):
        from scripts.publish_arcade import publish

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("live profile\n", encoding="utf-8")
            staging = root / "staging"
            metadata = staging / "rotation-metadata"
            generators = staging / "generators"
            metadata.mkdir(parents=True)
            generators.mkdir(parents=True)
            (metadata / "selection.json").write_text(
                json.dumps({"selected": "maze-chase", "mode": "selected"}),
                encoding="utf-8",
            )
            (metadata / "README.next.md").write_text("next profile\n", encoding="utf-8")
            (metadata / "arcade-state.next.json").write_text("{}\n", encoding="utf-8")
            (generators / "maze-chase-light.svg").write_text("<svg/>\n", encoding="utf-8")
            (generators / "maze-chase-dark.svg").write_text("<svg/>\n", encoding="utf-8")

            publish(root, staging)

            self.assertEqual(
                (root / "README.md").read_text(encoding="utf-8"),
                "next profile\n",
            )
            self.assertTrue((root / "assets" / "arcade" / "maze-chase-light.svg").is_file())

    def test_missing_selected_asset_fails_before_profile_is_changed(self):
        from scripts.publish_arcade import publish

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("live profile\n", encoding="utf-8")
            staging = root / "staging"
            metadata = staging / "rotation-metadata"
            metadata.mkdir(parents=True)
            (metadata / "selection.json").write_text(
                json.dumps({"selected": "space-shooter"}), encoding="utf-8"
            )
            (metadata / "README.next.md").write_text("next profile\n", encoding="utf-8")
            (metadata / "arcade-state.next.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(FileNotFoundError, "space-shooter"):
                publish(root, staging)

            self.assertEqual(
                (root / "README.md").read_text(encoding="utf-8"),
                "live profile\n",
            )


if __name__ == "__main__":
    unittest.main()
