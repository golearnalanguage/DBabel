import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from build_portable_review import build
from review_model import default_decision,write_json,write_jsonl

def make_bundle(root):
    b=root/'x.dbreview';b.mkdir();session={'format_version':'1.0','session_id':'RS_x','created_at':'2026-01-01T00:00:00Z','dbabel_version':'1.5.0-dev','mode':'BILINGUAL_REVIEW','title':'XSS test','bundle_files':{'units':'units.jsonl','issues':'issues.json','evidence':'evidence.json','decisions':'decisions.json','events':'events.jsonl','anchors':'anchors.json'},'original':{'filename':'x.docx','format':'docx','sha256':'0'*64},'counts':{'units':1,'issues':0,'evidence':0},'export_policy':{'require_all_confirmed':True,'block_unwaived_errors':True,'require_user_edit_recheck':True,'never_overwrite_original':True}}
    write_json(b/'session.json',session);write_jsonl(b/'units.jsonl',[{'id':'U1','location':'u','source':'<script>alert(1)</script>','current_target':'safe','labels':[],'finding_refs':[],'qa_issue_refs':[],'evidence_refs':[],'requires_confirmation':True}]);write_json(b/'issues.json',[]);write_json(b/'evidence.json',[]);write_json(b/'decisions.json',[default_decision('U1')]);write_json(b/'anchors.json',{});(b/'events.jsonl').write_text('');return b

class PortableTests(unittest.TestCase):
    def test_self_contained_and_xss_not_literal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);b=make_bundle(root);out=root/'review.html';build(b,out);text=out.read_text()
            self.assertNotIn('<script>alert(1)</script>',text)
            self.assertIn("connect-src 'none'",text)
            network_text=text.replace('http://www.w3.org/2000/svg','')
            self.assertNotIn('https://',network_text)
            self.assertNotIn('http://',network_text)
            self.assertIn('Export decisions.json',text)

if __name__=='__main__':unittest.main()
