"""Generate a fully synthetic preview; no manuscript files are required."""
import sys
from pathlib import Path
import fitz

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build_comparison import build

OUT=ROOT/'build'/'demo';OUT.mkdir(parents=True,exist_ok=True)
old='''Abstract
This fictional study evaluates a compact measurement workflow. The initial method uses twenty observations and reports a validation score of 0.84. The model is assessed on the same collection used during development. The results provide an early description of the measurement response.

Introduction
This unchanged paragraph is included to demonstrate that the review only
shows the edited section, even when surrounding pages move.'''
new='''Abstract
This fictional study evaluates an adaptive measurement workflow. The revised method uses twelve observations and reports a validation score of 0.91. The model is assessed on a separate collection held out from development. The results provide a more reliable description of the measurement response.

Introduction
This unchanged paragraph is included to demonstrate that the review only
shows the edited section, even when surrounding pages move.'''
for name,text in [('older.pdf',old),('newer.pdf',new)]:
    doc=fitz.open();page=doc.new_page()
    page.insert_textbox(fitz.Rect(90,80,510,690),text,fontsize=15,fontname='tiro')
    page.insert_text((290,810),'1',fontsize=10)
    doc.save(OUT/name);doc.close()
info=build(OUT/'older.pdf',OUT/'newer.pdf',OUT/'comparison.pdf')
with fitz.open(info['output']) as doc:
    (ROOT/'docs').mkdir(exist_ok=True)
    doc[0].get_pixmap(matrix=fitz.Matrix(1.2,1.2),clip=doc[0].rect,alpha=False).save(ROOT/'docs'/'preview.png')
print(info)
