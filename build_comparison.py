"""Lightweight vector PDF review. Source PDFs are always opened read-only."""
import hashlib
import json
import sys
import time
import os
import tempfile
from pathlib import Path

import fitz
from backend import compare
from graphics_diff import compare_graphics

RECIPE = 'pdf-content-diff-0.7.0-vector-pages'


def digest(file):
    h = hashlib.sha256()
    with open(file, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def groups(result):
    # Link pages that participate in the same replacement. A paragraph spanning
    # two old pages and one new page stays in one side-by-side comparison.
    components = []
    for h in result['hunks']:
        nodes = {(side, p) for side, key in [('left', 'leftPages'), ('right', 'rightPages')]
                 for p in h[key]}
        touched = [c for c in components if c & nodes]
        for c in touched:
            nodes |= c
            components.remove(c)
        components.append(nodes)
    return sorted(components, key=lambda c: min(p for _, p in c))


def build(old_file, new_file, output):
    started = time.perf_counter()
    old_file, new_file, output = map(Path, (old_file, new_file, output))
    if output.resolve() in (old_file.resolve(), new_file.resolve()):
        raise ValueError('Output must differ from both source PDFs')
    fingerprint = digest(Path(__file__)) + digest(Path(__file__).with_name('backend.py')) + digest(Path(__file__).with_name('graphics_diff.py'))
    signature = RECIPE + ':' + digest(old_file) + ':' + digest(new_file) + ':' + fingerprint
    if output.exists():
        cached = fitz.open(output)
        metadata = cached.metadata
        cached.close()
        if not metadata.get('subject', '').startswith(('pdf-content-diff-', 'vector-content-review-1:')):
            raise ValueError('Output already exists and is not a generated PDF Content Diff review')
        if metadata.get('subject') == signature:
            return {'output': str(output), 'cached': True, 'bytes': output.stat().st_size,
                    'seconds': round(time.perf_counter()-started, 3)}
    result = compare(str(old_file), str(new_file))
    old, new = fitz.open(old_file), fitz.open(new_file)
    docs = {'left': old, 'right': new}
    left_graphics, right_graphics = compare_graphics(old, new)
    if not result['hasText'] and not (left_graphics or right_graphics) and not all(
            any(p.get_drawings() for p in doc) for doc in docs.values()):
        raise ValueError('Both PDFs must contain extractable text or changed vector graphics')
    components = groups(result)
    for side, records in [('left',left_graphics),('right',right_graphics)]:
        for record in records:
            p = record['page']
            nodes = {(side,p)}
            if p < len(docs['right' if side == 'left' else 'left']):
                nodes.add(('right' if side == 'left' else 'left',p))
            touched = [c for c in components if c & nodes]
            for c in touched: nodes |= c; components.remove(c)
            components.append(nodes)
            box = (fitz.Rect(record['rect']) + (-2,-2,2,2)) & docs[side][p].rect
            docs[side][p].draw_rect(box,color=(.10,.40,.95),width=1.3,overlay=True)
    components.sort(key=lambda c: min(p for _,p in c))
    # Remove only the common outer margin, using one union across BOTH documents.
    # The crop is independent of edits, so body text has one size on every sheet.
    content = None
    for doc in docs.values():
        for source in doc:
            boxes = [fitz.Rect(block[:4]) for block in source.get_text('blocks')]
            boxes += [d['rect'] for d in source.get_drawings()]
            for box in boxes:
                if content is None: content = fitz.Rect(box)
                else: content |= box
    clips = {side: [(content + (-8,-8,8,8)) & p.rect if content else p.rect for p in doc]
             for side,doc in docs.items()}
    panel_width = max(c.width for values in clips.values() for c in values)
    panel_height = max(c.height for values in clips.values() for c in values)
    sheet_width, sheet_height = 2*panel_width+44, panel_height+68
    for side, doc in docs.items():
        colour = (1, .60, .64) if side == 'left' else (1, .84, .20)
        for page, marks in result[side]['marks'].items():
            for mark in marks:
                r = fitz.Rect(mark['rect']); r.x0 -= .6; r.x1 += .6
                doc[page].draw_rect(r, color=None, fill=colour, fill_opacity=.42, overlay=True)
    review = fitz.open()
    # One document-wide scale, independent of changed-region size and page count.
    scale = 1.0
    for index, nodes in enumerate(components):
        originals = {side: sorted(p for s, p in nodes if s == side)
                     for side in ('left', 'right')}
        # Never squeeze multiple original pages into a single review sheet.
        for part in range(max(map(len, originals.values()))):
            page = review.new_page(width=sheet_width, height=sheet_height)
            page.insert_text((12,18), f'Content revision {index+1}: before and after', fontname='hebo', fontsize=12)
            page.insert_text((12,32), 'Red: removed text. Yellow: added text. Blue outline: changed vector graphics.', fontsize=9)
            for side, x, label in [('left',12,'Before'), ('right',panel_width+32,'After')]:
                if part >= len(originals[side]):
                    page.insert_text((x,48), f'{label} - no corresponding changed page', fontname='hebo', fontsize=10)
                    continue
                p = originals[side][part]
                source = docs[side][p]
                page.insert_text((x,48), f'{label} - original page {p+1}', fontname='hebo', fontsize=10)
                clip = clips[side][p]
                width, height = clip.width*scale, clip.height*scale
                left = x + (panel_width-width)/2
                destination = fitz.Rect(left,56,left+width,56+height)
                if source.get_contents():
                    page.show_pdf_page(destination, docs[side], p,clip=clip)
            page.draw_line((panel_width+22,40),(panel_width+22,sheet_height-8),color=(.8,.8,.8),width=.5)
    if not len(review):
        page = review.new_page(width=1190,height=842)
        page.insert_text((30,40),'No text or vector graphics changes detected.',fontsize=16)
    review.set_metadata({'title':'PDF content comparison','subject':signature,
                         'keywords':'Ignore margin line numbers, page numbers and text reflow'})
    # Subset original fonts and keep vector text, with no page rasterization.
    review.subset_fonts()
    output.parent.mkdir(parents=True, exist_ok=True)
    data = review.tobytes(garbage=4,deflate=True)
    current_signature = RECIPE + ':' + digest(old_file) + ':' + digest(new_file) + ':' + fingerprint
    if current_signature != signature:
        review.close(); old.close(); new.close()
        raise RuntimeError('Source PDF changed during comparison; retry after compilation finishes')
    # Readers see a complete PDF even while the previous review is open.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            stream.write(data)
        os.replace(temporary, output)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    page_count = len(review)
    review.close(); old.close(); new.close()
    return {'output':str(output),'cached':False,'bytes':output.stat().st_size,
            'pages':page_count,'hunks':len(result['hunks']),'graphicsChanges':len(left_graphics)+len(right_graphics),
            'seconds':round(time.perf_counter()-started,3)}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Create a side-by-side vector PDF of actual text changes.')
    parser.add_argument('old', help='Older text-based PDF')
    parser.add_argument('new', help='Newer text-based PDF')
    parser.add_argument('output', help='Generated comparison PDF; must differ from both inputs')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.old, args.new, args.output)))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f'PDF Content Diff: {error}\n')
