#!/usr/bin/env python3
"""Keep only the 3D calendar from a github-profile-3d-contrib SVG.

The generator always adds a radar chart, a language pie and a stats footer around the calendar. This
removes everything except the style block, shared defs, the background and the calendar group, then
crops the viewBox to the calendar. The result is checked for scripts and external references before it is written.
"""
from __future__ import annotations
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)
PAD = 14
HEADROOM = 110


def local(tag):
    return tag.rsplit('}', 1)[-1]


def calendar_bounds(group):
    """Approximate bounds of the towers from their translate() positions and unskewed rectangle sizes."""
    xs, ys = [], []

    def walk(node, tx, ty):
        match = re.match(r'\s*translate\(\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s*\)', node.attrib.get('transform', ''))
        if match:
            tx, ty = tx+float(match.group(1)), ty+float(match.group(2))
        if local(node.tag) == 'rect' and 'width' in node.attrib:
            xs.extend([tx, tx+float(node.attrib['width'])])
            ys.append(ty)
        for child in node:
            walk(child, tx, ty)

    walk(group, 0, 0)
    if not xs:
        raise ValueError('No calendar tiles found')
    return min(xs), max(xs), min(ys), max(ys)


def trim(raw):
    root = ET.fromstring(raw)
    if local(root.tag) != 'svg':
        raise ValueError('Not an SVG document')
    groups = [child for child in root if local(child.tag) == 'g']
    if not groups:
        raise ValueError('No calendar group found')
    calendar = max(groups, key=lambda g: sum(1 for _ in g.iter()))
    full_h = float(root.attrib['height'])
    full_w = float(root.attrib['width'])
    for child in list(root):
        if child is calendar or local(child.tag) in ('style', 'title', 'desc', 'defs'):
            continue
        if local(child.tag) == 'rect' and float(child.attrib.get('width', 0)) >= full_w-1 and float(child.attrib.get('height', 0)) >= full_h-1:
            continue
        root.remove(child)
    x0, x1, y0, y1 = calendar_bounds(calendar)
    left, top = max(0, x0-PAD), max(0, y0-HEADROOM)
    right, bottom = min(full_w, x1+PAD+30), min(full_h, y1+60)
    width, height = right-left, bottom-top
    root.set('viewBox', f'{left:g} {top:g} {width:g} {height:g}')
    root.set('width', f'{width:g}')
    root.set('height', f'{height:g}')
    for node in root.iter():
        if local(node.tag) in ('script', 'foreignObject', 'image'):
            raise ValueError(f'Unexpected <{local(node.tag)}> in generated SVG')
        for name, value in node.attrib.items():
            internal = name.lower().endswith('href') and value.startswith('#')
            external_href = name.lower().endswith('href') and not internal
            if name.lower().startswith('on') or external_href or re.search(r'javascript:|data:|https?://', value, re.I):
                raise ValueError('Unexpected external reference in generated SVG')
    return ET.tostring(root, encoding='unicode')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args(argv)
    result = trim(args.source.read_text(encoding='utf-8'))
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(result, encoding='utf-8', newline='\n')
    print(f'{args.destination}: {len(result)//1024} KB')


if __name__ == '__main__':
    sys.exit(main())
