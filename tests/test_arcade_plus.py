import ast
import copy
import itertools
import json
import random
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import deque
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

from scripts.original_arcade import ORIGINALS, PALETTES, render_scene, maze_model, life_step, sort_traces, race_model, rng_for
from scripts.daily_quests import KINDS, RELICS, advance_world, make_puzzle, puzzle_kind, vault_score, apply_lights
from scripts.rotate_arcade import ARCADE_EXPERIENCES, choose_next, force_selection, prepare_rotation, render_arcade_block, replace_arcade_block
from scripts.publish_arcade import ASSET_MAP, publish

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026,9,11)


class RotationTests(unittest.TestCase):
    def test_three_hundred_full_bags(self):
        state, previous = {}, None
        rng = random.Random(43)
        for _ in range(300):
            seen = []
            for _ in ARCADE_EXPERIENCES:
                selected, state = choose_next(state,rng)
                self.assertNotEqual(selected,previous)
                seen.append(selected)
                previous = selected
            self.assertEqual(set(seen),set(ARCADE_EXPERIENCES))
            self.assertEqual(len(seen),len(set(seen)))

    def test_legacy_migration_prioritizes_new_scenes(self):
        state = {"current":"space-shooter","remaining":["3d-city","breakout"],"cycle":3,"custom":"keep"}
        before = copy.deepcopy(state)
        selected, after = choose_next(state,random.Random(7))
        self.assertIn(selected,ORIGINALS)
        self.assertEqual(set(after["remaining"])|{selected},set(ORIGINALS)|{"3d-city","breakout"})
        self.assertEqual(after["custom"],"keep")
        self.assertEqual(state,before)

    def test_dirty_bag_is_deduplicated_and_current_removed(self):
        state = {"current":"snake","remaining":["snake","unknown","breakout","breakout"],"catalog":list(ARCADE_EXPERIENCES)}
        selected,after = choose_next(state,random.Random(2))
        self.assertEqual(selected,"breakout")
        self.assertEqual(after["remaining"],[])

    def test_same_day_retry_is_idempotent_even_with_new_seed(self):
        selected,state = prepare_rotation({},DAY.isoformat(),seed="first")
        again,after = prepare_rotation(state,DAY.isoformat(),seed="retry")
        self.assertEqual((again,after),(selected,state))

    def test_manual_switch_does_not_double_award(self):
        _,state = prepare_rotation({},DAY.isoformat(),"dungeon-crawl")
        _,after = prepare_rotation(state,DAY.isoformat(),"neon-race")
        self.assertEqual(state["world"],after["world"])
        self.assertEqual(after["current"],"neon-race")

    def test_invalid_manual_selection(self):
        with self.assertRaises(ValueError):
            force_selection({},"../../oops")

    def test_strict_dates(self):
        for day in ("20260911","2026-02-30","automated"):
            with self.subTest(day=day),self.assertRaises(ValueError):
                prepare_rotation({},day)

    def test_readme_keeps_external_content_and_literal_backslashes(self):
        original = "HEADER\n<!-- ARCADE:START -->\nold\n<!-- ARCADE:END -->\nPROJECTS"
        new = replace_arcade_block(original,"literal \\1 and \\g<0>")
        self.assertTrue(new.startswith("HEADER\n"))
        self.assertTrue(new.endswith("\nPROJECTS"))
        self.assertIn("literal \\1 and \\g<0>",new)

    def test_rejects_missing_duplicate_reversed_markers(self):
        for text in ("nothing", "<!-- ARCADE:END --><!-- ARCADE:START -->", "<!-- ARCADE:START --><!-- ARCADE:START --><!-- ARCADE:END -->"):
            with self.subTest(text=text),self.assertRaises(ValueError):
                replace_arcade_block(text,"next")

    def test_catalog_publisher_and_workflow_stay_in_sync(self):
        self.assertEqual(set(ARCADE_EXPERIENCES),set(ASSET_MAP))
        workflow = (ROOT/".github/workflows/daily-arcade.yml").read_text()
        choices = re.findall(r"^          - ([\w-]+)$",workflow,re.M)
        self.assertEqual(set(choices),{"random",*ARCADE_EXPERIENCES})
        self.assertIn("needs.choose.outputs.native != 'true'",workflow)
        self.assertNotIn("--seed \"${GITHUB_RUN_ID}",workflow)
        self.assertIn("date -u +%F",workflow)


class SceneTests(unittest.TestCase):
    def test_all_themes_parse_are_scriptless_small_and_repeatable(self):
        for delta in (0,1,190):
            day = (DAY+timedelta(days=delta)).isoformat()
            for name in ORIGINALS:
                for theme in PALETTES:
                    with self.subTest(day=day,name=name,theme=theme):
                        svg = render_scene(name,day,theme)
                        xml = ET.fromstring(svg)
                        self.assertTrue(xml.tag.endswith("svg"))
                        self.assertEqual(svg,render_scene(name,day,theme))
                        self.assertLess(len(svg.encode()),250_000)
                        self.assertNotIn("<script",svg)
                        self.assertNotIn("foreignObject",svg)
                        self.assertIn("prefers-reduced-motion",svg)
                        self.assertIn("autoplay",svg)

    def test_scene_geometry_changes_not_only_date_label(self):
        for name in ORIGINALS:
            a = render_scene(name,"2026-09-11").split('<g clip-path="url(#scene)">')[1]
            b = render_scene(name,"2026-09-12").split('<g clip-path="url(#scene)">')[1]
            self.assertNotEqual(a,b)

    def test_perfect_mazes_and_walkable_routes(self):
        for seed in range(100):
            opened,path = maze_model(random.Random(seed))
            self.assertEqual(path[0],(1,1)); self.assertEqual(path[-1],(19,7))
            self.assertEqual(len(path),len(set(path)))
            self.assertTrue(set(path)<=opened)
            self.assertTrue(all(abs(a[0]-b[0])+abs(a[1]-b[1])==1 for a,b in zip(path,path[1:])))
            edges = sum((x+dx,y+dy) in opened for x,y in opened for dx,dy in ((1,0),(0,1)))
            self.assertEqual(edges,len(opened)-1)
            seen,queue = {(1,1)},deque([(1,1)])
            while queue:
                x,y=queue.popleft()
                for p in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if p in opened and p not in seen:
                        seen.add(p);queue.append(p)
            self.assertEqual(seen,opened)

    def test_life_blinker_and_still_life(self):
        horizontal={(1,2),(2,2),(3,2)}
        vertical={(2,1),(2,2),(2,3)}
        self.assertEqual(life_step(horizontal,5,5),vertical)
        self.assertEqual(life_step(vertical,5,5),horizontal)
        block={(1,1),(1,2),(2,1),(2,2)}
        self.assertEqual(life_step(block,5,5),block)
        self.assertEqual(life_step(set(),5,5),set())

    def test_real_sort_traces_preserve_cards_and_finish_sorted(self):
        for seed in range(100):
            values=list(range(1,13));random.Random(seed).shuffle(values)
            before=values[:]
            for trace in sort_traces(values):
                self.assertEqual(trace[0],values)
                self.assertEqual(trace[-1],sorted(values))
                for frame in trace:
                    self.assertEqual(sorted(frame),sorted(values))
                for a,b in zip(trace,trace[1:]):
                    self.assertLessEqual(sum(x!=y for x,y in zip(a,b)),2)
            self.assertEqual(values,before)

    def test_race_progress_never_reverses(self):
        for seed in range(100):
            finish,tracks=race_model(random.Random(seed))
            self.assertEqual(len(set(finish)),4)
            for end,track in zip(finish,tracks):
                self.assertEqual(track[0],0)
                self.assertAlmostEqual(track[end],1)
                self.assertTrue(all(a<=b for a,b in zip(track,track[1:])))


class PuzzleTests(unittest.TestCase):
    def test_six_family_bags_and_no_adjacent_repeat(self):
        start=DAY.toordinal()//6*6
        kinds=[puzzle_kind(date.fromordinal(start+i).isoformat()) for i in range(600)]
        for i in range(0,600,6):
            self.assertEqual(set(kinds[i:i+6]),set(KINDS))
        self.assertTrue(all(a!=b for a,b in zip(kinds,kinds[1:])))

    def test_all_puzzles_are_reproducible(self):
        for kind in KINDS:
            self.assertEqual(make_puzzle(DAY.isoformat(),kind),make_puzzle(DAY.isoformat(),kind))

    def test_vaults_have_exactly_one_solution(self):
        for delta in range(24):
            p=make_puzzle((DAY+timedelta(days=delta)).isoformat(),"vault")
            candidates=[s for s in itertools.permutations(range(6),3) if all(vault_score(g,s)==score for g,score in p.data["clues"])]
            self.assertEqual(candidates,[p.data["secret"]])
            self.assertTrue(all(g!=p.data["secret"] for g,_ in p.data["clues"]))

    def test_nim_moves_are_legal_and_zero_xor(self):
        for delta in range(24):
            data=make_puzzle((DAY+timedelta(days=delta)).isoformat(),"nim").data
            for i,amount in data["moves"]:
                piles=data["piles"][:]
                self.assertTrue(0<amount<=piles[i])
                piles[i]-=amount
                self.assertEqual(piles[0]^piles[1]^piles[2],0)

    def test_paths_match_independent_brute_force(self):
        for delta in range(24):
            data=make_puzzle((DAY+timedelta(days=delta)).isoformat(),"route").data
            grid=data["grid"];totals=[]
            for rights in itertools.combinations(range(6),3):
                x=y=0;total=grid[0][0]
                for step in range(6):
                    if step in rights:x+=1
                    else:y+=1
                    total+=grid[y][x]
                totals.append(total)
            self.assertEqual(min(totals),data["cost"])
            self.assertEqual(sum(grid[y][x] for x,y in data["path"]),data["cost"])

    def test_lights_solutions_are_valid_and_minimal(self):
        for delta in range(24):
            data=make_puzzle((DAY+timedelta(days=delta)).isoformat(),"lights").data
            self.assertEqual(apply_lights(data["board"],data["presses"]),0)
            count=data["presses"].bit_count()
            self.assertTrue(all(apply_lights(data["board"],p)!=0 for p in range(512) if p.bit_count()<count))

    def test_twenty_four_exact_arithmetic_and_each_card_once(self):
        def evaluate(node,leaves):
            if isinstance(node,ast.Constant) and type(node.value) is int:
                leaves.append(node.value);return Fraction(node.value)
            self.assertIsInstance(node,ast.BinOp)
            a,b=evaluate(node.left,leaves),evaluate(node.right,leaves)
            if isinstance(node.op,ast.Add):return a+b
            if isinstance(node.op,ast.Sub):return a-b
            if isinstance(node.op,ast.Mult):return a*b
            if isinstance(node.op,ast.Div):return a/b
            self.fail("Unexpected operation")
        for delta in range(24):
            data=make_puzzle((DAY+timedelta(days=delta)).isoformat(),"twenty-four").data
            leaves=[]
            self.assertEqual(evaluate(ast.parse(data["expression"],mode="eval").body,leaves),24)
            self.assertEqual(sorted(leaves),sorted(data["numbers"]))

    def test_knight_routes_use_only_legal_moves_and_are_shortest(self):
        for delta in range(24):
            data=make_puzzle((DAY+timedelta(days=delta)).isoformat(),"knight").data
            path=data["path"]
            self.assertEqual(path[0],data["start"]);self.assertEqual(path[-1],data["goal"])
            self.assertTrue(all(sorted((abs(a[0]-b[0]),abs(a[1]-b[1])))==[1,2] for a,b in zip(path,path[1:])))
            layer={data["start"]};seen=set(layer);distance=0
            while data["goal"] not in layer:
                layer={(x,y) for x in range(4) for y in range(4) if (x,y) not in seen and any(sorted((abs(x-a),abs(y-b)))==[1,2] for a,b in layer)}
                seen|=layer;distance+=1
            self.assertEqual(distance,len(path)-1)


class ExpeditionTests(unittest.TestCase):
    def test_forty_eight_unique_keepsakes_and_bounded_history(self):
        world={}
        for delta in range(365):
            day=(DAY+timedelta(days=delta)).isoformat()
            world=advance_world(world,day,"neon-race")
            self.assertEqual(world["days"],delta+1)
            self.assertEqual(len(world["inventory"]),min(delta+1,48))
            self.assertLessEqual(len(world["history"]),7)
            if (delta+1)%7==0:self.assertTrue(world["history"][-1]["rare"])
        self.assertEqual(set(world["inventory"]),set(RELICS))

    def test_retry_and_absence_do_not_reset_or_backfill(self):
        world=advance_world({},DAY.isoformat(),"dungeon-crawl")
        before=copy.deepcopy(world)
        self.assertEqual(advance_world(world,DAY.isoformat(),"neon-race"),world)
        after=advance_world(world,(DAY+timedelta(days=20)).isoformat(),"neon-race")
        self.assertEqual(after["days"],2)
        self.assertEqual(world,before)

    def test_rewind_is_rejected(self):
        world=advance_world({},DAY.isoformat(),"dungeon-crawl")
        with self.assertRaises(ValueError):
            advance_world(world,(DAY-timedelta(days=1)).isoformat(),"dungeon-crawl")


class PipelineTests(unittest.TestCase):
    def stage(self,root,extra=()):
        (root/"README.md").write_text("HEADER\n<!-- ARCADE:START -->\nold\n<!-- ARCADE:END -->\nPROJECTS")
        metadata=root/"staging/rotation-metadata"
        args=[sys.executable,str(ROOT/"scripts/rotate_arcade.py"),"--readme",str(root/"README.md"),"--state",str(root/".github/arcade-state.json"),"--output-dir",str(metadata),"--date",DAY.isoformat(),"--experience","dungeon-crawl",*extra]
        subprocess.run(args,check=True,capture_output=True,text=True,cwd=root)
        return metadata,args

    def test_native_selected_needs_no_external_generator_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);metadata,args=self.stage(root)
            self.assertIn("\nold\n",(root/"README.md").read_text())
            publish(root,root/"staging")
            self.assertTrue((root/"assets/arcade/dungeon-crawl-dark.svg").exists())
            text=(root/"README.md").read_text()
            self.assertTrue(text.startswith("HEADER\n"));self.assertTrue(text.endswith("\nPROJECTS"))
            self.assertIn("pocket quest",text)
            before={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file() and "staging" not in p.parts}
            args[-1]="random"
            subprocess.run(args,check=True,capture_output=True,text=True,cwd=root)
            publish(root,root/"staging")
            self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file() and "staging" not in p.parts})

    def test_missing_native_asset_keeps_live_readme_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);metadata,_=self.stage(root)
            (metadata/"originals/dungeon-crawl-dark.svg").unlink()
            with self.assertRaises(FileNotFoundError):publish(root,root/"staging")
            self.assertIn("\nold\n",(root/"README.md").read_text())
            self.assertFalse((root/"assets").exists())

    def test_executable_native_svg_is_rejected_before_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);metadata,_=self.stage(root)
            (metadata/"originals/dungeon-crawl-dark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
            with self.assertRaises(ValueError):publish(root,root/"staging")
            self.assertFalse((root/"assets").exists())

    def test_all_mode_stages_sixteen_original_assets_and_accepts_legacy_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);metadata,_=self.stage(root,("--generation-mode","all"))
            self.assertEqual(len(list((metadata/"originals").glob("*.svg"))),16)
            generators=root/"staging/generators";generators.mkdir()
            for name,pairs in ASSET_MAP.items():
                if name not in ORIGINALS:
                    for filename,_ in pairs:(generators/filename).write_text("fixture for legacy generator")
            publish(root,root/"staging")
            self.assertEqual(len(list((root/"assets/arcade").iterdir())),sum(map(len,ASSET_MAP.values())))

    def test_mismatched_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);metadata,_=self.stage(root)
            path=metadata/"arcade-state.next.json";state=json.loads(path.read_text());state["current"]="snake";path.write_text(json.dumps(state))
            with self.assertRaises(ValueError):publish(root,root/"staging")
            self.assertFalse((root/"assets").exists())


if __name__ == "__main__":
    unittest.main()
