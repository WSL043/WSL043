import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scripts import showcase

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def fake_fetch(path, token=None):
    if path.endswith('/releases/latest'):
        return {'tag_name': 'v1.2.3'} if 'loudease' not in path else None
    if path.startswith('/users/WSL043/repos'):
        return [{'name': 'WSL043', 'fork': False, 'private': False, 'pushed_at': '2026-09-29T11:59:00Z'},
                {'name': 'forked', 'fork': True, 'private': False, 'pushed_at': '2026-09-29T11:00:00Z'},
                {'name': 'DSH-Portable', 'fork': False, 'private': False, 'pushed_at': '2026-09-29T09:00:00Z'}]
    if path == '/users/WSL043':
        return {'public_repos': 16}
    return {'stargazers_count': 7, 'language': 'Python', 'pushed_at': '2026-09-28T20:00:00Z', 'html_url': 'x'}


class ShowcaseTests(unittest.TestCase):
    def test_relative_time(self):
        self.assertEqual(showcase.ago('2026-09-29T11:59:40Z', NOW), 'just now')
        self.assertEqual(showcase.ago('2026-09-29T09:00:00Z', NOW), '3h ago')
        self.assertEqual(showcase.ago('2026-09-26T12:00:00Z', NOW), '3d ago')
        self.assertEqual(showcase.ago('2026-07-20T12:00:00Z', NOW), '2mo ago')

    def test_latest_ignores_profile_repo_and_forks(self):
        data = showcase.collect(fake_fetch)
        self.assertEqual(data['latest']['name'], 'DSH-Portable')
        self.assertEqual(len(data['projects']), len(showcase.PROJECTS))
        self.assertIsNone(next(p for p in data['projects'] if p['slug'] == 'loudease')['release'])

    def test_missing_repository_fails_loudly(self):
        with self.assertRaises(RuntimeError):
            showcase.collect(lambda path, token=None: None)

    def test_every_svg_is_well_formed_and_escapes_text(self):
        data = showcase.collect(fake_fetch)
        data['projects'][0]['title'] = '<script>&"'
        data['latest']['name'] = '<b>x</b>'
        for theme in showcase.THEMES:
            svgs = [showcase.render_now_playing(data, theme, NOW), showcase.render_more_card(data, theme)]
            svgs += [showcase.render_card(p, i, theme, NOW) for i, p in enumerate(data['projects'])]
            for raw in svgs:
                ET.fromstring(raw)
                self.assertNotIn('<script', raw)
                self.assertNotIn('href', raw)

    def test_long_descriptions_are_clamped(self):
        rows = showcase.wrap('word ' * 100)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[-1].endswith('…'))

    def test_no_recent_repo_still_renders(self):
        data = showcase.collect(fake_fetch)
        data['latest'] = None
        ET.fromstring(showcase.render_now_playing(data, 'dark', NOW))


if __name__ == '__main__':
    unittest.main()
