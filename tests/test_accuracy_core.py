import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_bilingual_integrity as qa


def entry(entry_id="E1", source_term="sync point", behavior="TRANSLATE",
          approval="PROJECT_APPROVED", targets=None, scope=None,
          mode="token", case_sensitive=False):
    if targets is None:
        targets = [
            {"language": "zh-CN", "term": "同步点", "status": "PREFERRED"},
            {"language": "zh-CN", "term": "同步位置", "status": "ADMITTED"},
            {"language": "zh-CN", "term": "同步节点", "status": "FORBIDDEN"},
        ]
    return {
        "id": entry_id,
        "source": {"language": "en", "term": source_term},
        "behavior": behavior,
        "approval": approval,
        "targets": targets,
        "scope": scope or {},
        "match": {
            "mode": mode,
            "case_sensitive": case_sensitive,
            "unicode_normalization": "NFC",
        },
    }


def unit(source, target, unit_id="U1", **kwargs):
    value = {"id": unit_id, "source": source, "target": target}
    value.update(kwargs)
    return value


class AccuracyCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = qa.load_config(ROOT / "config" / "deterministic_qa.yaml")

    def issues(self, source, target, glossary=None, **kwargs):
        report = qa.run_qa([unit(source, target, **kwargs)], self.config, glossary)
        self.assertEqual(qa.validate_report(report), [])
        return report["issues"]

    def ids(self, *args, **kwargs):
        return [x["check_id"] for x in self.issues(*args, **kwargs)]

    def test_placeholder_reordering_is_not_false_positive(self):
        self.assertNotIn("PLACEHOLDER_INTEGRITY", self.ids(
            "Use {0} with {name}.", "使用 {name} 和 {0}。"))

    def test_placeholder_loss(self):
        self.assertIn("PLACEHOLDER_INTEGRITY", self.ids(
            "Use {0} with {name}.", "使用 {0}。"))

    def test_shell_environment_variable_not_double_counted_as_placeholder(self):
        ids = self.ids("Use ${HOME}.", "Use ${PATH}.")
        self.assertIn("ENV_VAR_INTEGRITY", ids)
        self.assertNotIn("PLACEHOLDER_INTEGRITY", ids)

    def test_url_sentence_punctuation(self):
        self.assertNotIn("URL_INTEGRITY", self.ids(
            "See https://example.com/a.", "请参见 https://example.com/a。"))

    def test_url_change(self):
        self.assertIn("URL_INTEGRITY", self.ids(
            "See https://example.com/a.", "See https://example.com/b."))

    def test_unix_path_change(self):
        self.assertIn("PATH_INTEGRITY", self.ids(
            "Open /etc/example/app.conf.", "Open /etc/example/app.ini."))

    def test_windows_path_preserved(self):
        self.assertNotIn("PATH_INTEGRITY", self.ids(
            r"Open C:\\ProgramData\\DBabel\\config.ini.",
            r"打开 C:\\ProgramData\\DBabel\\config.ini。"))

    def test_standalone_filename_change(self):
        self.assertIn("FILENAME_INTEGRITY", self.ids(
            "Edit dm.ini before startup.", "启动前编辑 dm.cfg。"))

    def test_cli_option_change(self):
        self.assertIn("CLI_OPTION_INTEGRITY", self.ids(
            "Run tool --force.", "Run tool --fast."))

    def test_environment_variable_change(self):
        self.assertIn("ENV_VAR_INTEGRITY", self.ids(
            "Set $DB_HOME first.", "Set $HOME first."))

    def test_version_sentence_final_period(self):
        self.assertIn("VERSION_INTEGRITY", self.ids(
            "Requires version 3.1.", "Requires version 3.2."))

    def test_version_same(self):
        self.assertNotIn("VERSION_INTEGRITY", self.ids(
            "Requires v3.1.", "需要 v3.1。"))

    def test_number_unit_change(self):
        self.assertIn("NUMBER_UNIT_INTEGRITY", self.ids(
            "Wait 500 ms.", "Wait 500 s."))

    def test_number_unit_no_duplicate_plain_number_issue(self):
        ids = self.ids("Wait 500 ms.", "Wait 500 s.")
        self.assertIn("NUMBER_UNIT_INTEGRITY", ids)
        self.assertNotIn("NUMBER_INTEGRITY", ids)

    def test_localized_number_format_is_equivalent(self):
        self.assertNotIn("NUMBER_INTEGRITY", self.ids(
            "Processed 1,000.50 rows.", "已处理 1 000,50 行。"))

    def test_plain_number_change(self):
        self.assertIn("NUMBER_INTEGRITY", self.ids(
            "Processed 1000 rows.", "Processed 999 rows."))

    def test_percentage_is_number_unit(self):
        self.assertIn("NUMBER_UNIT_INTEGRITY", self.ids(
            "Usage is 50%.", "Usage is 60%."))

    def test_project_approved_preferred_term(self):
        glossary = {"format_version": "1.0", "entries": [entry()]}
        self.assertNotIn("PREFERRED_TERM", self.ids(
            "The sync point is recorded.", "记录同步点。",
            glossary=glossary, source_language="en", target_language="zh-CN"))

    def test_admitted_term_is_accepted(self):
        glossary = {"format_version": "1.0", "entries": [entry()]}
        self.assertNotIn("PREFERRED_TERM", self.ids(
            "The sync point is recorded.", "记录同步位置。",
            glossary=glossary, source_language="en", target_language="zh-CN"))

    def test_forbidden_term(self):
        glossary = {"format_version": "1.0", "entries": [entry()]}
        ids = self.ids(
            "The sync point is recorded.", "记录同步节点。",
            glossary=glossary, source_language="en", target_language="zh-CN")
        self.assertIn("FORBIDDEN_TERM", ids)

    def test_missing_preferred_or_admitted(self):
        glossary = {"format_version": "1.0", "entries": [entry()]}
        self.assertIn("PREFERRED_TERM", self.ids(
            "The sync point is recorded.", "记录位置。",
            glossary=glossary, source_language="en", target_language="zh-CN"))

    def test_unapproved_glossary_entry_is_not_enforced(self):
        glossary = {"format_version": "1.0", "entries": [entry(approval="USER_REVIEW")]}
        ids = self.ids(
            "The sync point is recorded.", "记录同步节点。",
            glossary=glossary, source_language="en", target_language="zh-CN")
        self.assertNotIn("FORBIDDEN_TERM", ids)
        self.assertNotIn("PREFERRED_TERM", ids)

    def test_scope_match(self):
        scoped = entry(scope={"product": "Product A", "version": "3"})
        glossary = {"format_version": "1.0", "entries": [scoped]}
        ids = self.ids(
            "The sync point is recorded.", "记录同步节点。",
            glossary=glossary, source_language="en", target_language="zh-CN",
            context={"product": "Product A", "version": "3"})
        self.assertIn("FORBIDDEN_TERM", ids)

    def test_scope_mismatch_does_not_cross_product(self):
        scoped = entry(scope={"product": "Product A"})
        glossary = {"format_version": "1.0", "entries": [scoped]}
        ids = self.ids(
            "The sync point is recorded.", "记录同步节点。",
            glossary=glossary, source_language="en", target_language="zh-CN",
            context={"product": "Product B"})
        self.assertNotIn("FORBIDDEN_TERM", ids)

    def test_missing_scope_context_fails_closed(self):
        scoped = entry(scope={"product": "Product A"})
        glossary = {"format_version": "1.0", "entries": [scoped]}
        ids = self.ids(
            "The sync point is recorded.", "记录同步节点。",
            glossary=glossary, source_language="en", target_language="zh-CN")
        self.assertNotIn("FORBIDDEN_TERM", ids)

    def test_text_role_scope(self):
        scoped = entry(scope={"text_roles": ["ui_label"]})
        glossary = {"format_version": "1.0", "entries": [scoped]}
        ids = self.ids(
            "sync point", "同步节点", glossary=glossary,
            source_language="en", target_language="zh-CN",
            context={"text_role": "body"})
        self.assertNotIn("FORBIDDEN_TERM", ids)

    def test_protect_literal(self):
        protected = entry(
            entry_id="P1", source_term="EXAMPLE_MODE", behavior="PROTECT",
            targets=[], case_sensitive=True)
        glossary = {"format_version": "1.0", "entries": [protected]}
        self.assertIn("PROTECTED_LITERAL", self.ids(
            "Set EXAMPLE_MODE=1.", "Set example_mode=1.", glossary=glossary))

    def test_protect_literal_preserved(self):
        protected = entry(
            entry_id="P1", source_term="EXAMPLE_MODE", behavior="PROTECT",
            targets=[], case_sensitive=True)
        glossary = {"format_version": "1.0", "entries": [protected]}
        self.assertNotIn("PROTECTED_LITERAL", self.ids(
            "Set EXAMPLE_MODE=1.", "设置 EXAMPLE_MODE=1。", glossary=glossary))

    def test_cjk_token_matching_without_spaces(self):
        e = entry(
            source_term="同步点",
            targets=[{"language": "en", "term": "sync point", "status": "PREFERRED"}],
            case_sensitive=False)
        e["source"]["language"] = "zh-CN"
        glossary = {"format_version": "1.0", "entries": [e]}
        self.assertNotIn("PREFERRED_TERM", self.ids(
            "记录同步点位置。", "Record the sync point position.",
            glossary=glossary, source_language="zh-CN", target_language="en"))


    def test_source_language_mismatch_fails_closed(self):
        glossary = {"format_version": "1.0", "entries": [entry()]}
        ids = self.ids(
            "The sync point is recorded.", "记录同步节点。",
            glossary=glossary, source_language="fr", target_language="zh-CN")
        self.assertNotIn("FORBIDDEN_TERM", ids)

    def test_missing_target_language_fails_closed_for_translation_terms(self):
        glossary = {"format_version": "1.0", "entries": [entry()]}
        ids = self.ids(
            "The sync point is recorded.", "记录同步节点。",
            glossary=glossary, source_language="en")
        self.assertNotIn("FORBIDDEN_TERM", ids)
        self.assertNotIn("PREFERRED_TERM", ids)

    def test_pretty_printed_single_json_unit_loader(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "unit.json"
            p.write_text(
                json.dumps(unit("a", "b"), indent=2), encoding="utf-8")
            values = qa.load_units(p)
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]["id"], "U1")

    def test_ambiguous_alignment_rejected(self):
        errors = qa.validate_units([
            unit("a", "b", alignment="AMBIGUOUS")
        ])
        self.assertTrue(any("AMBIGUOUS" in x for x in errors), errors)

    def test_duplicate_unit_id_rejected(self):
        errors = qa.validate_units([unit("a", "b"), unit("c", "d")])
        self.assertTrue(any("duplicate unit id" in x for x in errors), errors)

    def test_jsonl_loader(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "units.jsonl"
            p.write_text(
                json.dumps(unit("a", "b")) + "\n" +
                json.dumps(unit("c", "d", unit_id="U2")) + "\n",
                encoding="utf-8")
            values = qa.load_units(p)
            self.assertEqual([x["id"] for x in values], ["U1", "U2"])

    def test_generated_issue_ids_are_stable_sequence(self):
        report = qa.run_qa([
            unit("Use {0} at version 3.1.", "Use {1} at version 3.2.")
        ], self.config)
        self.assertEqual([x["id"] for x in report["issues"]], ["Q0001", "Q0002"])

    def test_report_schema(self):
        report = qa.run_qa([unit("same", "same")], self.config)
        self.assertEqual(qa.validate_report(report), [])
        self.assertEqual(report["summary"]["units_checked"], 1)


if __name__ == "__main__":
    unittest.main()
