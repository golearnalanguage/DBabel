import ast,json,sys,unittest
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
SCHEMAS=ROOT/'schemas'

class ContractTests(unittest.TestCase):
    def test_all_review_schemas_are_valid_draft_2020_12(self):
        names=['review_session.schema.json','review_unit.schema.json','review_issue.schema.json','review_decision.schema.json','review_event.schema.json','export_receipt.schema.json','technique_annotation.schema.json']
        for name in names:
            with self.subTest(name=name):Draft202012Validator.check_schema(json.loads((SCHEMAS/name).read_text()))
    def test_frontend_never_uses_innerhtml_for_document_content(self):
        app=(ROOT/'review_workbench/static/app.js').read_text();portable=(ROOT/'review_workbench/portable_template.html').read_text()
        self.assertNotIn('.innerHTML',app);self.assertNotIn('.innerHTML',portable)
    def test_portable_has_no_runtime_network_dependency(self):
        t=(ROOT/'review_workbench/portable_template.html').read_text()
        self.assertIn("connect-src 'none'",t);self.assertNotIn('<script src=',t);self.assertNotIn('<link rel="stylesheet"',t)
    def test_python_sources_parse_as_python_3_9(self):
        paths=list((ROOT/'scripts').glob('*.py'))+list((ROOT/'tests').glob('test_*.py'))
        for p in paths:
            with self.subTest(path=p.name):ast.parse(p.read_text(encoding='utf-8'),filename=str(p),feature_version=9)

    def test_workbench_human_approval_is_runtime_contract(self):
        skill=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        agents=(ROOT/'AGENTS.md').read_text(encoding='utf-8')
        openai=(ROOT/'agents/openai.yaml').read_text(encoding='utf-8')
        server=(ROOT/'scripts/start_review_workbench.py').read_text(encoding='utf-8')
        app=(ROOT/'review_workbench/static/app.js').read_text(encoding='utf-8')

        self.assertIn('Review Workbench',skill)
        self.assertIn('scripts/create_review_session.py',skill)
        self.assertIn('--original',skill)
        self.assertIn('--output',skill)
        self.assertIn('never fabricate',skill.lower())

        self.assertIn('Review Workbench handoff',agents)
        self.assertIn('Review Session',openai)
        self.assertIn('Never',openai)

        self.assertIn('"output_name"',server)
        self.assertIn('Review-only mode.',app)


if __name__=='__main__':unittest.main()
