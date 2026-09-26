"""Behavioral coverage for upload parsing, scoped scoring and snapshot delivery."""
import base64
import importlib.util
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from review_exchange import read_document, create_intake, upload_file, glossary_score, render_result
from review_model import load_bundle
from create_review_session import _load_units


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def file(self,name,text):
        p=self.root/name;p.write_text(text,encoding='utf-8');return p
    def test_text_grammars_locations_and_unicode(self):
        cases=[('source.txt','甲\n\n乙\n',['甲','乙']),('source.md','<p>intro</p>\n# 标题',['<p>intro</p>','# 标题']),
               ('source.tsv','a\tb\nc\td',['a','b','c','d']),('source.csv','"hello, world",test\n"multi\nline",值',['hello, world','test','multi\nline','值']),
               ('source.json','{"a/b":"值","number":3,"list":["二"]}',['值','二']),
               ('source.jsonl','{"a":"甲"}\n{"a":"乙"}\n',['甲','乙']),
               ('source.html','<!doctype html><html><p>Visible</p><script>hidden()</script><p>文字</p></html>',['Visible','文字'])]
        for name,text,expected in cases:
            with self.subTest(name=name):
                r=read_document(self.file(name,text));self.assertEqual([x['text'] for x in r['segments']],expected);self.assertTrue(r['limitations'])
                self.assertTrue(all('location' in x for x in r['segments']))
    def test_office_scopes_and_formula_exclusion(self):
        cases=[('docx','word/document.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>甲</w:t></w:r></w:p></w:body></w:document>'),
               ('pptx','ppt/slides/slide1.xml','application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml','<slide><a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>甲</a:t></a:r></a:p></slide>'),
               ('xlsx','xl/worksheets/sheet1.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>甲</t></is></c><c r="B1"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>')]
        for suffix,part,ctype,xml in cases:
            p=self.root/('a.'+suffix)
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('[Content_Types].xml','<Types><Override ContentType="'+ctype+'"/></Types>');z.writestr(part,xml)
                if suffix=='pptx':z.writestr('ppt/presentation.xml','<presentation/>')
                if suffix=='xlsx':z.writestr('xl/workbook.xml','<workbook/>')
            self.assertEqual([x['text'] for x in read_document(p)['segments']],['甲'])
    def test_binary_content_is_not_accepted_as_markdown(self):
        p=self.root/'binary.md';p.write_bytes(b'\x00\x00binary data')
        with self.assertRaisesRegex(ValueError, 'content does not confirm'):
            read_document(p)

    def test_multilingual_intake_does_not_invent_targets_or_approval(self):
        path=self.file('src.txt','甲\n乙\n');bundle=self.root/'multi.dbreview'
        create_intake(path,bundle,'zh-CN',['en','ja'])
        data=load_bundle(bundle);self.assertEqual(len(data['units']),4)
        self.assertEqual({x['target_language'] for x in data['units']},{'en','ja'})
        self.assertTrue(all(x['current_target']=='' and x['alignment']=='UNALIGNED' for x in data['units']))
        self.assertTrue(all(x['status']=='UNREVIEWED' for x in data['decisions']))
        self.assertTrue((bundle/'inputs/source.txt').exists());self.assertTrue((bundle/'intake.json').exists())
    def test_positional_pairing_requires_equal_counts_and_explicit_confirmation(self):
        src=self.file('src.txt','甲\n乙');tgt=self.file('tgt.txt','A')
        with self.assertRaises(ValueError):create_intake(src,self.root/'bad.dbreview','zh-CN',['en'],tgt,True)
        tgt.write_text('A\nB');out=self.root/'pair.dbreview';create_intake(src,out,'zh-CN',['en'],tgt)
        self.assertEqual(load_bundle(out)['units'][0]['alignment'],'UNALIGNED')
    def test_suggestions_survive_session_preparation(self):
        p=self.file('units.json',json.dumps([{'source':'甲','target':'A','suggested_target':'B','suggestion_reason':'Actor differs.'}]))
        row=_load_units(p)[0];self.assertEqual(row['suggested_target'],'B');self.assertEqual(row['suggestion_reason'],'Actor differs.')
    def data(self):
        unit={'id':'U1','location':'p:1','source':'主库','current_target':'=unsafe()','suggested_target':'never accepted','source_language':'zh-CN','target_language':'en'}
        d={'unit_id':'U1','status':'UNREVIEWED','revision':0,'recheck':{'status':'NOT_RUN'}}
        return {'session':{'session_id':'RS_test','original':{'filename':'test'}},'units':[unit],'decisions':[d],'decisions_by_id':{'U1':d},'issues':[],'evidence':[]}
    def test_results_preserve_pending_states_and_escape_content(self):
        data=self.data();snap=json.loads(render_result(data,'json'));self.assertEqual(snap['units'][0]['target'],'=unsafe()')
        self.assertEqual(snap['units'][0]['status'],'UNREVIEWED')
        for fmt in ['csv','tsv']:
            rows=list(csv.reader(io.StringIO(render_result(data,fmt)),delimiter='\t' if fmt=='tsv' else ','))
            self.assertEqual(rows[1][rows[0].index('target')],"'=unsafe()")
        data['units'][0]['source']='<script>alert(1)</script>'
        self.assertNotIn('<script>',render_result(data,'html'));self.assertIn('&lt;script&gt;',render_result(data,'html'))
        for fmt in ['md','txt']:self.assertIn('UNREVIEWED',render_result(data,fmt))
        data['decisions'][0].update(status='USER_EDITED',approved_target='Approved')
        self.assertEqual(json.loads(render_result(data,'json'))['units'][0]['target'],'Approved')
    def test_glossary_score_scope_denominator_and_absent_match(self):
        glossary=json.loads((ROOT/'templates/project_glossary.json').read_text())
        entry=glossary['entries'][0];entry['source']={'language':'zh-CN','term':'主库'};entry['targets']=[{'language':'en','term':'primary database','status':'PREFERRED'}];entry['scope']={};entry['approval']='PROJECT_APPROVED';entry['behavior']='TRANSLATE'
        path=self.file('glossary.json',json.dumps({'format_version':'1.0','entries':[entry]}))
        data=self.data();self.assertEqual(glossary_score(data,path)['score'],0)
        data['units'][0]['current_target']='primary database';self.assertEqual(glossary_score(data,path)['score'],100)
        entry['scope']={'product':'OTHER'};path.write_text(json.dumps({'format_version':'1.0','entries':[entry]}));self.assertIsNone(glossary_score(data,path)['score'])
    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'optional pypdf unavailable')
    def test_pdf_text_layer_and_scan_gap(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(width=300,height=200)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 100 Td (Hello database) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        p=self.root/'text.pdf'
        with p.open('wb') as f:writer.write(f)
        result=read_document(p);self.assertEqual(result['format'],'pdf');self.assertIn('Hello database',result['segments'][0]['text'])
        blank=PdfWriter();blank.add_blank_page(width=100,height=100)
        with p.open('wb') as f:blank.write(f)
        with self.assertRaisesRegex(ValueError,'No text extracted'):read_document(p)

    def test_upload_rejects_paths_empty_bytes_and_bad_encoding(self):
        for payload in [{'name':'../bad','content_base64':'YQ=='},{'name':'ok.txt','content_base64':''},{'name':'ok.txt','content_base64':'!!!'}]:
            with self.assertRaises(ValueError):upload_file(payload,self.root)
        self.assertEqual(upload_file({'name':'ok.txt','content_base64':base64.b64encode('甲'.encode()).decode()},self.root).read_text(),'甲')


if __name__=='__main__':unittest.main()
