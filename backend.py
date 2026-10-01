"""PDF content comparison with source-coordinate word annotations.

No source PDF is written. The JSON result is consumed by the VS Code viewer.
"""
import argparse
import collections
import difflib
import json
import re
import unicodedata

import fitz

TOKEN = re.compile(r"[^\W_]+(?:[-‐‑][^\W_]+)*|[^\s]", re.UNICODE)


def normalize(s):
    s = unicodedata.normalize('NFKC', s).replace('\u00ad', '')
    return re.sub(r'(?<=[A-Za-z])[-‐‑](?=[A-Za-z])', '', s)


def extract(path):
    doc = fitz.open(path)
    raw_channels = [[], []]
    pages = []
    excluded = {'lineNumbers': 0, 'pageNumbers': 0}
    all_words = [page.get_text('words', sort=True) for page in doc]
    global_numbered = sum(1 for pi, page in enumerate(doc) for w in all_words[pi]
                          if w[4].isdigit() and w[2] < page.rect.width * .15
                          and w[1] < page.rect.height * .96) >= 12
    for pi, page in enumerate(doc):
        pages.append({'width': page.rect.width, 'height': page.rect.height})
        words = all_words[pi]
        margin = [w for w in words if w[4].isdigit() and w[2] < page.rect.width * .15
                  and w[1] < page.rect.height * .96]
        values = [int(w[4]) for w in margin]
        numbered = global_numbered or (len(values) >= 6 and sum(a < b for a, b in zip(values, values[1:])) >= .8 * (len(values)-1))
        margin_set = {(w[0], w[1], w[4]) for w in margin} if numbered else set()
        spans = [(s['bbox'], s['size']) for block in page.get_text('dict')['blocks'] if 'lines' in block
                 for line in block['lines'] for s in line['spans']]
        sizes = collections.Counter(round(size) for rect, size in spans if size >= 9)
        body_size = sizes.most_common(1)[0][0] if sizes else 12
        captions = {block[5] for block in page.get_text('blocks')
                    if block[6] == 0 and re.match(r'\s*(?:Fig(?:ure)?\.?|Table)\s*\d', block[4])}
        number_y = [(w[1]+w[3])/2 for w in margin] if numbered else []
        for w in words:
            text = w[4]
            if (w[0], w[1], text) in margin_set:
                excluded['lineNumbers'] += 1
                continue
            if text.isdigit() and w[1] > page.rect.height * .9 and .35 * page.rect.width < w[0] < .65 * page.rect.width:
                excluded['pageNumbers'] += 1
                continue
            cx, cy = (w[0]+w[2])/2, (w[1]+w[3])/2
            large = any(r[0]-1 <= cx <= r[2]+1 and r[1]-1 <= cy <= r[3]+1 and size >= .85*body_size
                        for r,size in spans)
            narrative = w[5] not in captions and (large or any(abs(cy-y)<8 for y in number_y))
            raw_channels[0 if narrative else 1].append({'text': text, 'page': pi, 'rects': [list(w[:4])], 'line': (pi, w[5], w[6])})
    doc.close()

    # Join discretionary end-of-line hyphenation before tokenization. Also
    # normalize internal alphabetic hyphens so reflow cannot create a change.
    merged = []
    for raw in raw_channels:
        channel = []
        for word in raw:
            if (channel and len(channel[-1]['text']) > 1 and channel[-1]['text'][-2].isalpha()
                    and channel[-1]['text'].endswith(('-', '‐', '\u00ad'))
                    and word['text'][:1].isalpha() and word['line'] != channel[-1]['line']):
                last = channel[-1]
                last['text'] = last['text'].rstrip('-‐\u00ad') + word['text']
                last['rects'].extend(word['rects'])
                last.setdefault('rectPages', [last['page']]).append(word['page'])
                last['line'] = word['line']
            else:
                channel.append(word)
        merged.extend(channel)
    result = []
    for word in merged:
        text = normalize(word['text'])
        for match in TOKEN.finditer(text):
            value = normalize(match.group())
            if value:
                # Highlight original whole-word rectangles rather than pretend
                # that character widths are uniform in proportional fonts.
                result.append({'text': value, 'page': word['page'], 'rects': word['rects'],
                               'rectPages': word.get('rectPages', [word['page']] * len(word['rects']))})
    return result, pages, excluded


def compare(left, right):
    a, ap, ae = extract(left)
    b, bp, be = extract(right)
    av = [t['text'] for t in a]
    bv = [t['text'] for t in b]
    ops = difflib.SequenceMatcher(None, av, bv, autojunk=False).get_opcodes()
    deleted = set()
    inserted = set()
    for tag, i, j, k, l in ops:
        if tag != 'equal':
            deleted.update(range(i, j))
            inserted.update(range(k, l))

    # Figure floats and paragraphs can swap reading-order positions. Reconcile
    # exact substantial runs among unmatched text without similarity thresholds
    # that could swallow a real numeric or word change.
    di = sorted(deleted)
    ii = sorted(inserted)
    moved = 0
    reconcile = difflib.SequenceMatcher(None, [av[x] for x in di], [bv[x] for x in ii], autojunk=False)
    for block in reconcile.get_matching_blocks():
        if block.size < 8:
            continue
        old = di[block.a:block.a+block.size]
        new = ii[block.b:block.b+block.size]
        # Do not join unrelated isolated words across disjoint edit regions.
        if all(y == x+1 for x, y in zip(old, old[1:])) and all(y == x+1 for x, y in zip(new, new[1:])):
            deleted.difference_update(old)
            inserted.difference_update(new)
            moved += block.size

    def marks(tokens, indexes):
        by_page = collections.defaultdict(list)
        seen = set()
        for i in sorted(indexes):
            token = tokens[i]
            for page, rect in zip(token['rectPages'], token['rects']):
                key = (page, tuple(rect))
                if key not in seen:
                    seen.add(key)
                    by_page[page].append({'rect': rect, 'text': token['text']})
        return dict(by_page)

    hunks = []
    for tag, i, j, k, l in ops:
        ld = [x for x in range(i, j) if x in deleted]
        ri = [x for x in range(k, l) if x in inserted]
        if not ld and not ri:
            continue
        hunks.append({'leftPage': a[ld[0]]['page'] if ld else None,
                      'rightPage': b[ri[0]]['page'] if ri else None,
                      'leftPages': sorted({p for x in ld for p in a[x]['rectPages']}),
                      'rightPages': sorted({p for x in ri for p in b[x]['rectPages']}),
                      'leftRect': a[ld[0]]['rects'][0] if ld else None,
                      'rightRect': b[ri[0]]['rects'][0] if ri else None,
                      'old': ' '.join(av[x] for x in ld), 'new': ' '.join(bv[x] for x in ri)})
    return {'left': {'pages': ap, 'marks': marks(a, deleted), 'excluded': ae},
            'right': {'pages': bp, 'marks': marks(b, inserted), 'excluded': be},
            'hunks': hunks, 'removedTokens': len(deleted), 'addedTokens': len(inserted),
            'movedTokens': moved, 'hasText': bool(a and b)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('old')
    parser.add_argument('new')
    args = parser.parse_args()
    print(json.dumps(compare(args.old, args.new), ensure_ascii=False))
