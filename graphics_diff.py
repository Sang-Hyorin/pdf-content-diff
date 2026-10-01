"""Translation-invariant comparison of connected vector drawing groups."""
import collections
import hashlib
import json
import fitz


def drawings(doc):
    records = []
    for number, page in enumerate(doc):
        paths = page.get_drawings()
        # Dense scientific plots may contain tens of thousands of overlapping
        # paths. Compare their page-level vector group in linear time instead
        # of running a quadratic connectivity sweep. A whole-page translation
        # remains invariant; independent figure movements can be reported.
        dense = len(paths) > 2000
        parents = list(range(len(paths)))
        if dense: parents = [0] * len(paths)
        def root(i):
            while parents[i] != i:
                parents[i] = parents[parents[i]]; i = parents[i]
            return i
        # Sweep by x to avoid comparing distant objects on the same page.
        active = []
        for i in ([] if dense else sorted(range(len(paths)), key=lambda i: paths[i]['rect'].x0)):
            box = paths[i]['rect'] + (-3,-3,3,3)
            active = [j for j in active if paths[j]['rect'].x1+3 >= box.x0]
            for j in active:
                if box.intersects(paths[j]['rect'] + (-3,-3,3,3)):
                    a, b = root(i), root(j)
                    parents[a] = b
            active.append(i)
        clusters = collections.defaultdict(list)
        for i, item in enumerate(paths): clusters[root(i)].append(item)
        for cluster in clusters.values():
            box = fitz.Rect(cluster[0]['rect'])
            for item in cluster[1:]: box |= item['rect']
            def normalize(value):
                if isinstance(value, fitz.Point): return [round(value.x-box.x0,2),round(value.y-box.y0,2)]
                if isinstance(value, fitz.Rect): return [round(value.x0-box.x0,2),round(value.y0-box.y0,2),round(value.x1-box.x0,2),round(value.y1-box.y0,2)]
                if isinstance(value, fitz.Quad): return normalize([value.ul,value.ur,value.ll,value.lr])
                if isinstance(value, (list,tuple)): return [normalize(v) for v in value]
                if isinstance(value,float): return round(value,2)
                return value
            signatures = []
            for item in cluster:
                fields = {k:normalize(item.get(k)) for k in ('items','type','color','fill','width','dashes','lineCap','lineJoin','closePath','even_odd','fill_opacity','stroke_opacity')}
                signatures.append(json.dumps(fields,sort_keys=True))
            signature = hashlib.sha256(json.dumps(sorted(signatures)).encode()).hexdigest()
            records.append({'page':number,'rect':list(box),'signature':signature})
    return records


def compare_graphics(old, new):
    left, right = drawings(old), drawings(new)
    common = collections.Counter(r['signature'] for r in left) & collections.Counter(r['signature'] for r in right)
    def remaining(records):
        available = common.copy(); result = []
        for record in records:
            key = record['signature']
            if available[key]: available[key] -= 1
            else: result.append(record)
        return result
    return remaining(left), remaining(right)
