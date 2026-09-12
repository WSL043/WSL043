import copy
import json
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.search_race import ALGORITHMS, comparison, render_comparison, search
from scripts.svg_models import Calendar
from scripts.publish_arcade import validate_svg, publish, digest


def oracle(costs, start, unit=False):
    """Independent Bellman-Ford; no production neighbor/heap helper."""
    distance = {p: float('inf') for p in costs}
    distance[start] = 0
    edges = [(a, b) for a in costs for b in costs if abs(a[0]-b[0])+abs(a[1]-b[1]) == 1]
    for _ in range(len(costs)-1):
        changed = False
        for a, b in edges:
            candidate = distance[a]+(1 if unit else costs[b])
            if candidate < distance[b]:
                distance[b], changed = candidate, True
        if not changed:
            break
    return distance


class SearchTests(unittest.TestCase):
    def test_two_hundred_weighted_maps_match_independent_oracle(self):
        rng = random.Random(43)
        for _ in range(200):
            costs = {(x, y): rng.randint(1, 9) for x in range(6) for y in range(5) if rng.random() > .25}
            start, goal = (0, 2), (5, 2)
            costs[start] = costs[goal] = 1
            before = costs.copy()
            optimal, steps = oracle(costs, start)[goal], oracle(costs, start, True)[goal]
            for algorithm in ALGORITHMS:
                result = search(costs, start, goal, algorithm)
                self.assertEqual(result['reachable'], optimal < float('inf'))
                expected = (steps if algorithm == 'bfs' else optimal) if result['reachable'] else None
                self.assertEqual(result['steps' if algorithm == 'bfs' else 'cost'], expected)
                self.assertEqual(len(result['trace']), len(set(result['trace'])))
                if result['reachable']:
                    self.assertEqual((result['path'][0], result['path'][-1]), (start, goal))
                    self.assertEqual(result['cost'], sum(costs[p] for p in result['path'][1:]))
                    for a, b in zip(result['path'], result['path'][1:]):
                        self.assertEqual(abs(a[0]-b[0])+abs(a[1]-b[1]), 1)
                        self.assertIn(b, costs)
                self.assertEqual(search(costs, start, goal, algorithm), result)
            self.assertEqual(costs, before)

    def test_fewer_steps_can_cost_more(self):
        costs = {(x, y): 1 for x in range(7) for y in range(3)}
        costs.update({(x, 1): 9 for x in range(1, 6)})
        b, d, a = [search(costs, (0, 1), (6, 1), algo) for algo in ALGORITHMS]
        self.assertLess(b['steps'], d['steps'])
        self.assertGreater(b['cost'], d['cost'])
        self.assertEqual(a['cost'], d['cost'])

    def test_unreachable_equal_endpoints_and_invalid_input(self):
        costs = {(0, 0): 1, (2, 0): 5}
        for algo in ALGORITHMS:
            self.assertFalse(search(costs, (0, 0), (2, 0), algo)['reachable'])
            r = search(costs, (0, 0), (0, 0), algo)
            self.assertEqual((r['cost'], r['steps']), (0, 0))
            with self.assertRaises(ValueError): search(costs, (0, 0), (1, 0), algo)
            with self.assertRaises(ValueError): search({(0, 0): 0}, (0, 0), (0, 0), algo)

    def test_snapshot_output_is_reproducible_vector_and_theme_aware(self):
        snapshot = json.loads((Path(__file__).parent/'fixtures/heatmap.json').read_text(encoding='utf-8'))
        cal = Calendar.from_snapshot(snapshot)
        before = copy.deepcopy(cal)
        report = comparison(cal)
        self.assertEqual(report['results']['dijkstra']['cost'], report['results']['astar']['cost'])
        for result in report['results'].values():
            self.assertTrue(all(tuple(p) not in cal.missing for p in result['trace']))
        with tempfile.TemporaryDirectory() as temp:
            for theme in ('light', 'dark'):
                svg = render_comparison(cal, theme)
                self.assertEqual(svg, render_comparison(cal, theme))
                path = Path(temp)/'comparison.svg'
                path.write_text(svg, encoding='utf-8')
                validate_svg(path, 'search-comparison', snapshot)
                self.assertIn('@media(prefers-reduced-motion:reduce){.motion{display:none}}', svg)
                self.assertIn('cost '+str(report['results']['astar']['cost']), svg)
        self.assertNotEqual(render_comparison(cal, 'light'), render_comparison(cal, 'dark'))
        self.assertEqual(cal, before)

    def test_empty_contributions_are_never_filled_with_fake_activity(self):
        cal = Calendar(53, {(x, y): 0 for x in range(53) for y in range(7)}, set(), [], 'empty', '2026-09-12')
        report = comparison(cal)
        self.assertEqual(report['results']['astar']['cost'], 52)
        self.assertFalse(cal.active)
        meta = ET.fromstring(render_comparison(cal, 'light')).find('{http://www.w3.org/2000/svg}metadata')
        self.assertEqual(json.loads(meta.text)['active_days'], 0)

    def test_checked_in_comparison_matches_saved_snapshot(self):
        assets = Path(__file__).resolve().parents[1]/'assets/arcade'
        cal = Calendar.from_snapshot(json.loads((assets/'heatmap-snapshot.json').read_text(encoding='utf-8')))
        expected = comparison(cal)
        self.assertEqual(json.loads((assets/'search-comparison.json').read_text(encoding='utf-8')), expected)
        manifest = json.loads((assets/'heatmap-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(digest(assets/'heatmap-snapshot.json'), manifest['snapshot_sha256'])
        for name, sha in manifest['analysis'].items():
            self.assertEqual(digest(assets/name), sha)
        for theme in ('dark', 'light'):
            self.assertTrue((assets/f'search-comparison-{theme}.svg').read_text(encoding='utf-8') == render_comparison(cal, theme, expected), 'Checked-in SVG must reproduce exactly')


class SearchPublicationTests(unittest.TestCase):
    def prepare(self):
        # Reuse the existing integration fixture without inheriting its test suite.
        from test_heatmap_pipeline import PublicationTests
        return PublicationTests.prepare(self)

    def test_modified_report_with_updated_hash_cannot_publish(self):
        root, artifacts, _ = self.prepare()
        path = artifacts/'search-comparison.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report['results']['astar']['cost'] = 0
        path.write_text(json.dumps(report), encoding='utf-8')
        manifest_path = artifacts/'heatmap-manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['analysis'][path.name] = digest(path)
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'does not reproduce'): publish(root, root/'staging')
        self.assertFalse((root/'assets').exists())

    def test_modified_visual_statistics_with_updated_hash_cannot_publish(self):
        root, artifacts, _ = self.prepare()
        path = artifacts/'search-comparison-light.svg'
        path.write_text(path.read_text(encoding='utf-8').replace('expanded ', 'invented '), encoding='utf-8')
        manifest_path = artifacts/'heatmap-manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['analysis'][path.name] = digest(path)
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'does not reproduce'): publish(root, root/'staging')
        self.assertFalse((root/'assets').exists())

    def test_missing_comparison_changes_no_live_files(self):
        root, artifacts, _ = self.prepare()
        (artifacts/'search-comparison-dark.svg').unlink()
        with self.assertRaises(FileNotFoundError): publish(root, root/'staging')
        self.assertFalse((root/'assets').exists())
