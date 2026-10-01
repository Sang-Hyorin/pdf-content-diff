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

RECIPE = 'pdf-content-diff-0.5.0'


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


def abstract_clips(doc):
    clips = {}; active = False
    for p, page in enumerate(doc):
        words = page.get_text('words', sort=True)
        heading = next((w for w in words if w[4] == 'Abstract'), None)
        intro = next((w for w in words if w[4] == 'Introduction'), None)
        if heading:
            active = True
        if not active:
            continue
        lower = heading[1]-4 if heading else 0
        upper = intro[1]-3 if intro else page.rect.height-75
        selected = [w for w in words if .14*page.rect.width < w[0] and
                    w[2] < .9*page.rect.width and w[1] >= lower and w[3] <= upper]
        if selected:
            clips[p] = fitz.Rect(.115*page.rect.width,
                lower if heading else min(w[1] for w in selected)-4,
                .875*page.rect.width, max(w[3] for w in selected)+5)
        if intro:
            break
    return clips


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
    abstracts = {side: abstract_clips(doc) for side, doc in docs.items()}
    for side, doc in docs.items():
        colour = (1, .60, .64) if side == 'left' else (1, .84, .20)
        for page, marks in result[side]['marks'].items():
            for mark in marks:
                r = fitz.Rect(mark['rect']); r.x0 -= .6; r.x1 += .6
                doc[page].draw_rect(r, color=None, fill=colour, fill_opacity=.42, overlay=True)
    review = fitz.open()
    for index, nodes in enumerate(groups(result)):
        is_abstract = all(p in abstracts[side] and
            all(abstracts[side][p].contains(fitz.Rect(m['rect'])) for m in result[side]['marks'][p])
            for side, p in nodes)
        clips = {}
        for side in ('left', 'right'):
            clips[side] = []
            for p in sorted(p for s, p in nodes if s == side):
                page = docs[side][p]
                if is_abstract:
                    clip = abstracts[side][p]
                else:
                    rects = [fitz.Rect(m['rect']) for m in result[side]['marks'][p]]
                    clip = fitz.Rect(min(r.x0 for r in rects)-20, min(r.y0 for r in rects)-24,
                                     max(r.x1 for r in rects)+20, max(r.y1 for r in rects)+20) & page.rect
                clips[side].append((p, clip))
        scale = min([540/c.width for values in clips.values() for _, c in values] +
                    [(728-12*(len(values)-1))/sum(c.height for _, c in values)
                     for values in clips.values() if values])
        page = review.new_page(width=1190, height=842)
        title = 'Abstract revision: before and after' if is_abstract else f'Content revision {index+1}: before and after'
        page.insert_text((30,26), title, fontname='hebo', fontsize=16)
        page.insert_text((30,45), 'Red: removed or replaced text. Yellow: added or replacement text.', fontsize=10)
        for side, x, label in [('left',30,'Before'), ('right',620,'After')]:
            originals = ', '.join(str(p+1) for p, _ in clips[side]) or 'none'
            page.insert_text((x,71), f'{label} - original page {originals}', fontname='hebo', fontsize=13)
            y = 84
            for p, clip in clips[side]:
                destination = fitz.Rect(x, y, x+clip.width*scale, y+clip.height*scale)
                page.show_pdf_page(destination, docs[side], p, clip=clip)
                y = destination.y1+12
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
