import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
import backend
from build_comparison import build, groups


def synthetic(values):
    return ([{'text':x,'page':0,'rects':[[i*5,0,i*5+4,10]],'rectPages':[0]}
             for i,x in enumerate(values)], [{'width':600,'height':840}], {})


def pdf(file, text, offset=0, numbers=False):
    doc=fitz.open();page=doc.new_page()
    page.insert_textbox(fitz.Rect(95,70+offset,510,650),text,fontsize=12,fontname='tiro')
    if numbers:
        for i in range(16):
            page.insert_text((65,80+i*16),str(i+1+offset),fontsize=7)
    page.insert_text((290,810),'1',fontsize=10)
    doc.save(file);doc.close()


class TokenChecks(unittest.TestCase):
    def compare(self,a,b):
        with patch.object(backend,'extract',side_effect=[synthetic(a),synthetic(b)]):
            return backend.compare('old','new')

    def test_numeric_edit(self):
        context='A long unchanged context describing the measured score for this fictional example as'.split()
        result=self.compare(context+['0.84'],context+['0.91'])
        self.assertEqual(result['removedTokens'],1)
        self.assertEqual(result['addedTokens'],1)

    def test_identical(self):
        self.assertFalse(self.compare(['same'],['same'])['hunks'])

    def test_movement_and_duplicate(self):
        a='The first paragraph records the unchanged evidence for several devices'.split()
        b='The second paragraph describes independent results from a fictional platform'.split()
        self.assertFalse(self.compare(a+b,b+a)['hunks'])
        self.assertEqual(self.compare(a,a+a)['addedTokens'],len(a))

    def test_all_cross_page_rectangles_are_grouped(self):
        result={'hunks':[{'leftPages':[0,1],'rightPages':[2]}]}
        self.assertEqual(groups(result),[{('left',0),('left',1),('right',2)}])


class PDFChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.old=self.root/'old.pdf';self.new=self.root/'new.pdf';self.out=self.root/'review.pdf'
    def tearDown(self):
        self.temp.cleanup()

    def test_margin_numbers_and_reflow(self):
        text='Abstract\nThis fictional report measures a stable response. The experiment uses sixteen observations.'
        pdf(self.old,text,numbers=True);pdf(self.new,text,offset=10,numbers=True)
        result=backend.compare(self.old,self.new)
        self.assertFalse(result['hunks'])
        self.assertEqual(result['left']['excluded']['lineNumbers'],16)

    def test_vector_output_cache_and_source_preservation(self):
        pdf(self.old,'Abstract\nThe fictional score is 0.84.\nIntroduction\nUnchanged prose.')
        pdf(self.new,'Abstract\nThe fictional score is 0.91.\nIntroduction\nUnchanged prose.')
        before=(self.old.read_bytes(),self.new.read_bytes())
        info=build(self.old,self.new,self.out)
        self.assertFalse(info['cached']);self.assertTrue(build(self.old,self.new,self.out)['cached'])
        with fitz.open(self.out) as doc:
            self.assertEqual(len(doc),1)
            self.assertIn('0.84',doc[0].get_text());self.assertIn('0.91',doc[0].get_text())
            self.assertFalse(doc[0].get_images());self.assertGreater(len(doc[0].get_fonts()),0)
        self.assertEqual(before,(self.old.read_bytes(),self.new.read_bytes()))
        pdf(self.new,'Abstract\nThe fictional score is 0.93.\nIntroduction\nUnchanged prose.')
        self.assertFalse(build(self.old,self.new,self.out)['cached'])

    def test_protect_input_and_unrelated_output(self):
        pdf(self.old,'Old text');pdf(self.new,'New text');pdf(self.out,'Unrelated document')
        contents=self.out.read_bytes()
        with self.assertRaises(ValueError):build(self.old,self.new,self.old)
        with self.assertRaises(ValueError):build(self.old,self.new,self.out)
        self.assertEqual(contents,self.out.read_bytes())

    def test_no_changes_and_no_text(self):
        pdf(self.old,'Same text');pdf(self.new,'Same text')
        build(self.old,self.new,self.out)
        with fitz.open(self.out) as doc:self.assertIn('No text changes',doc[0].get_text())
        blank=self.root/'blank.pdf';pdf(blank,'')
        with self.assertRaises(ValueError):build(self.old,blank,self.root/'blank-review.pdf')

    def test_full_pages_keep_one_scale_and_do_not_stack(self):
        for file, values in [(self.old, ['old alpha', 'old beta', 'old gamma']),
                             (self.new, ['new alpha', 'new beta', 'new gamma'])]:
            doc=fitz.open()
            for text in values:
                page=doc.new_page()
                page.insert_text((100,100),text,fontsize=12)
                page.insert_text((100,700),'Unchanged bottom context',fontsize=12)
            doc.save(file);doc.close()
        build(self.old,self.new,self.out)
        with fitz.open(self.out) as doc:
            self.assertEqual(len(doc),3)
            sizes=[]
            for page in doc:
                self.assertIn('Unchanged bottom context',page.get_text())
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        sizes.extend(s['size'] for s in line['spans'] if 'bottom context' in s['text'])
            self.assertEqual(len(sizes),6)
            self.assertLess(max(sizes)-min(sizes),0.001)
            self.assertLess(max(sizes),12)


if __name__=='__main__':unittest.main()
