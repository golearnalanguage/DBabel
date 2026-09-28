"""Long XLSX regression for adaptive literal review and visible progress."""
import json
import sys
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from runtime.models import GenerationResponse
from runtime.orchestrator import RuntimeOrchestrator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_reviewed_document import export_bundle  # noqa: E402
from review_model import load_bundle, normalize_decision, save_decisions  # noqa: E402


class LongDocumentProvider:
    def __init__(self):
        self.calls = Counter()

    def generate(self, request):
        payload = json.loads(request.user)
        semantic = payload.get("task") == "DBabel semantic risk adjudication"
        results = []
        for item in payload["units"]:
            unit_id = item["id"]
            self.calls[unit_id] += 1
            if semantic:
                results.append({
                    "id": unit_id, "outcome": "NO_FINDING",
                    "classification": None,
                    "reason": "No additional semantic concern identified.",
                    "next_action": "",
                })
                continue
            number = int(item["source"].split("：", 1)[0].split()[-1])
            if number == 110:
                target = "Step 110: Check --exec_mode and confirm the setting."
                if payload.get("retry_constraint"):
                    target = "Step 110: Check --exec_mode and confirm --exec_mode."
            elif number == 120:
                target = "Step 120: Check the database query result."
            else:
                target = f"Step {number:03d}: Check the configuration copy and record the owner."
            results.append({
                "id": unit_id, "suggested_target": target,
                "proposal_decision": "REPLACE",
                "reason": "Technical instruction translated for review.",
            })
        return GenerationResponse(
            text=json.dumps({"units": results}, ensure_ascii=False),
            model="fake-long-document", provider="local-test",
            response_id="local-test-response", usage={"total_tokens": 1},
        )


class LongDocumentTests(unittest.TestCase):
    def test_130_cell_xlsx_reaches_review_with_literal_issue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "long-sop.xlsx"
            rows = []
            for number in range(1, 131):
                text = f"步骤 {number:03d}：检查配置副本并登记负责人。"
                if number == 110:
                    text = (f"步骤 {number:03d}：" +
                            "核对变更记录、测试结果和回退负责人。" * 70 +
                            "先设置 --exec_mode，再核对 --exec_mode。")
                elif number == 120:
                    text = f"步骤 {number:03d}：检查 SELECT * FROM V$DATABASE 的查询结果。"
                rows.append(f'<row r="{number}"><c r="A{number}" t="inlineStr">'
                            f'<is><t>{escape(text)}</t></is></c></row>')
            worksheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/'
                         'spreadsheetml/2006/main"><sheetData>' +
                         ''.join(rows) + '</sheetData></worksheet>')
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('[Content_Types].xml', '<Types/>')
                archive.writestr('xl/workbook.xml', '<workbook/>')
                archive.writestr('xl/worksheets/sheet1.xml', worksheet)
            provider_path = root / "provider.json"
            provider_path.write_text(json.dumps({
                "provider": "openai-compatible",
                "base_url": "http://127.0.0.1:8000/v1",
                "api_key_env": "DBABEL_TEST_KEY",
                "model": "fake-long-document",
                "timeout_seconds": 120,
                "max_response_bytes": 2000000,
            }))
            events = []
            provider = LongDocumentProvider()
            manifest = RuntimeOrchestrator(workspace_root=root / "runs").run_translation_to_review(
                source=source, source_language="zh-CN", target_language="en",
                provider_config_path=provider_path, default_text_role="PROSE",
                provider=provider, on_progress=events.append,
            )
            self.assertEqual(manifest["status"], "READY_FOR_HUMAN_REVIEW")
            self.assertEqual(manifest["current_stage"], "DELIVERY_VALIDATION")
            self.assertTrue(any(event.get("state") == "SPLITTING_BATCH" for event in events))
            self.assertTrue(any(event.get("state") == "RETRYING_LITERAL" for event in events))
            self.assertTrue(any(event.get("state") == "REVIEW_REQUIRED" for event in events))
            self.assertTrue(any(event.get("completed_units") == 130 for event in events))
            post_path = Path(manifest["artifacts"]["post_translation"]["path"])
            post = json.loads(post_path.read_text(encoding="utf-8"))
            units = post["review_units"]
            self.assertEqual(len(units), 130)
            self.assertEqual(units[119]["proposal_decision"], "REVIEW")
            self.assertIn("V$DATABASE", units[119]["suggestion_reason"])
            self.assertGreaterEqual(post["deterministic_qa"]["summary"]["error_count"], 1)
            # These are explicit simulation decisions, never automatic approval.
            bundle = Path(manifest["artifacts"]["review_bundle"]["path"])
            data = load_bundle(bundle)
            draft_output = root / "long-sop.draft.xlsx"
            draft_receipt = export_bundle(bundle, ROOT, source, draft_output,
                                          export_mode="DRAFT")
            self.assertEqual(draft_receipt["status"], "DRAFT_EXPORTED",
                             draft_receipt.get("blockers"))
            self.assertEqual(len(draft_receipt["review_scope"]["unreviewed_unit_ids"]), 130)
            with zipfile.ZipFile(draft_output) as archive:
                sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("Step 001:", sheet)
            self.assertIn("Step 130:", sheet)
            self.assertNotIn("步骤 001", sheet)
            decisions = []
            for review_unit, previous in zip(data["units"], data["decisions"]):
                if "V$DATABASE" in review_unit["source"]:
                    action = {
                        "status": "USER_EDITED",
                        "approved_target": (
                            "Step 120: Check SELECT * FROM V$DATABASE "
                            "query result and record the observation time."
                        ),
                    }
                else:
                    action = {"status": "ACCEPT_SUGGESTION"}
                decisions.append(normalize_decision(review_unit, action, previous))
            save_decisions(bundle, decisions)
            output = root / "reviewed-long-sop.xlsx"
            receipt = export_bundle(bundle, ROOT, source, output)
            self.assertEqual(receipt["status"], "VERIFIED", receipt.get("blockers"))
            self.assertTrue(output.is_file())
