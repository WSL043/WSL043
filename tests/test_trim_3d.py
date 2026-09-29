import unittest
import xml.etree.ElementTree as ET

from scripts.trim_3d import trim

NS = '{http://www.w3.org/2000/svg}'


def sample(extra=''):
    tower = ''.join(f'<g transform="translate({100+i*20} {200+i*10})"><rect x="0" y="0" width="18" height="18" class="cont-top-1"/></g>'
                    for i in range(8))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="850" viewBox="0 0 1280 850">'
            '<style>.fill-bg{fill:#fff}</style><defs><g id="brick"><rect width="4" height="4"/></g></defs>'
            '<rect x="0" y="0" width="1280" height="850" class="fill-bg"/>'
            f'<g>{tower}{extra}</g>'
            '<g transform="translate(980, 284.5)"><path d="M0 0L5 5"/></g>'
            '<g transform="translate(40, 520)"><circle r="20"/></g>'
            '<g><text x="1" y="1">921 contributions</text></g>'
            '</svg>')


class TrimTests(unittest.TestCase):
    def test_removes_charts_and_keeps_calendar_style_defs_and_background(self):
        root = ET.fromstring(trim(sample()))
        tags = [child.tag.replace(NS, '') for child in root]
        self.assertEqual(tags, ['style', 'defs', 'rect', 'g'])
        self.assertEqual(sum(1 for _ in root.iter(NS+'rect')), 8+1+1)
        self.assertIsNone(root.find('.//' + NS + 'circle'))
        self.assertIsNone(root.find('.//' + NS + 'text'))

    def test_viewbox_is_cropped_to_the_calendar_inside_the_original_canvas(self):
        root = ET.fromstring(trim(sample()))
        left, top, width, height = map(float, root.get('viewBox').split())
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertLess(width, 1280)
        self.assertLess(height, 850)
        self.assertEqual((root.get('width'), root.get('height')), (f'{width:g}', f'{height:g}'))

    def test_rejects_scripts_and_external_references(self):
        for extra in ('<script>alert(1)</script>', '<image href="https://example.com/x.png"/>',
                      '<g onclick="x()"/>', '<use href="https://example.com/a.svg#b"/>'):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    trim(sample(extra))

    def test_allows_internal_use_references(self):
        self.assertIn('href="#brick"', trim(sample('<use href="#brick"/>')))

    def test_removed_chart_content_is_never_inspected_or_kept(self):
        svg = sample().replace('<circle r="20"/>', '<script>alert(1)</script>')
        self.assertNotIn('script', trim(svg))

    def test_rejects_documents_without_a_calendar(self):
        with self.assertRaises(ValueError):
            trim('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')


if __name__ == '__main__':
    unittest.main()
