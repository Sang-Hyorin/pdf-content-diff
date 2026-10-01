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

RECIPE = 'pdf-content-diff-0.6.0-full-pages'


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
    fingerprint = digest(Path(__file__)) + digest(Path(__file__).with_name('backend.py'))
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
    if not result['hasText']:
        raise ValueError('Both PDFs must contain extractable text')
    old, new = fitz.open(old_file), fitz.open(new_file)
    docs = {'left': old, 'right': new}
    for side, doc in docs.items():
        colour = (1, .60, .64) if side == 'left' else (1, .84, .20)
        for page, marks in result[side]['marks'].items():
            for mark in marks:
                r = fitz.Rect(mark['rect']); r.x0 -= .6; r.x1 += .6
                doc[page].draw_rect(r, color=None, fill=colour, fill_opacity=.42, overlay=True)
    review = fitz.open()
    # One document-wide scale, independent of changed-region size and page count.
    scale = min(min(540 / page.rect.width, 728 / page.rect.height)
                for doc in docs.values() for page in doc)
    for index, nodes in enumerate(groups(result)):
        originals = {side: sorted(p for s, p in nodes if s == side)
                     for side in ('left', 'right')}
        # Never squeeze multiple original pages into a single review sheet.
        for part in range(max(map(len, originals.values()))):
            page = review.new_page(width=1190, height=842)
            page.insert_text((30,26), f'Content revision {index+1}: before and after', fontname='hebo', fontsize=16)
            page.insert_text((30,45), 'Red: removed or replaced text. Yellow: added or replacement text.', fontsize=10)
            for side, x, label in [('left',30,'Before'), ('right',620,'After')]:
                if part >= len(originals[side]):
                    page.insert_text((x,71), f'{label} - no corresponding changed page', fontname='hebo', fontsize=13)
                    continue
                p = originals[side][part]
                source = docs[side][p]
                page.insert_text((x,71), f'{label} - original page {p+1}', fontname='hebo', fontsize=13)
                width, height = source.rect.width*scale, source.rect.height*scale
                left = x + (540-width)/2
                destination = fitz.Rect(left,84,left+width,84+height)
                if source.get_contents():
                    page.show_pdf_page(destination, docs[side], p)
            page.draw_line((595,61),(595,812),color=(.8,.8,.8),width=.5)
    if not len(review):
        page = review.new_page(width=1190,height=842)
        page.insert_text((30,40),'No text changes detected.',fontsize=16)
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
            'pages':page_count,'hunks':len(result['hunks']),
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
