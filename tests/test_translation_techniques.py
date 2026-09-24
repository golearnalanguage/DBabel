"""Contracts for the DBabel technical translation technique registry."""
import json
from pathlib import Path
import unittest

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "translation_techniques.yaml"
SCHEMA = ROOT / "schemas" / "translation_techniques.schema.json"
ROUTER = ROOT / "config" / "resource_router.yaml"
QA = ROOT / "config" / "deterministic_qa.yaml"

EXPECTED_TECHNIQUES = {
    "TECHNICAL_TOKEN_SHIELDING",
    "TERM_BEFORE_SENTENCE",
    "CONCEPT_BEFORE_SURFACE_FORM",
    "PRODUCT_VERSION_SCOPING",
    "TEXT_ROLE_TRANSLATION",
    "UI_LABEL_ANCHORING",
    "MODAL_STRENGTH_PRESERVATION",
    "LONG_SENTENCE_DECOMPOSITION",
    "CONTROLLED_EXPLICITATION",
    "NO_INVENTED_CAUSALITY",
    "TERMINOLOGY_VARIANT_GOVERNANCE",
    "ABBREVIATION_LIFECYCLE",
    "SOURCE_DEFECT_ESCALATION",
    "UI_DOCS_CONSISTENCY",
    "TARGET_LANGUAGE_TECHNICAL_NATURALNESS",
}


class TranslationTechniqueContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.router = yaml.safe_load(ROUTER.read_text(encoding="utf-8"))
        cls.qa = yaml.safe_load(QA.read_text(encoding="utf-8"))

    def test_registry_matches_schema(self):
        errors = list(
            Draft202012Validator(self.schema).iter_errors(self.registry)
        )
        self.assertEqual(errors, [])

    def test_core_technique_set_is_exact(self):
        ids = [item["id"] for item in self.registry["techniques"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), EXPECTED_TECHNIQUES)

    def test_transformation_references_resolve(self):
        transform_ids = {
            item["id"]
            for item in self.registry["transformations"]
        }

        referenced = set()

        for item in self.registry["techniques"]:
            referenced.update(item["allowed_transformations"])
            referenced.update(item["restricted_transformations"])

        self.assertEqual(
            referenced - transform_ids,
            set(),
        )

    def test_deterministic_check_links_resolve(self):
        known = set(self.qa["checks"])

        referenced = {
            check
            for item in self.registry["techniques"]
            for check in item["qa_mapping"]["deterministic_checks"]
        }

        self.assertEqual(
            referenced - known,
            set(),
        )

    def test_translation_modes_route_playbook_and_registry(self):
        required = {
            "references/18_TECHNICAL_TRANSLATION_PLAYBOOK.md",
            "config/translation_techniques.yaml",
        }

        for mode in ("BILINGUAL_REVIEW", "TRANSLATE", "REPAIR"):
            with self.subTest(mode=mode):
                self.assertTrue(
                    required.issubset(
                        set(self.router["mode_resources"][mode])
                    )
                )

    def test_guardrail_policy_is_fail_closed(self):
        policy = self.registry["policy"]

        self.assertIs(policy["examples_are_evidence"], False)
        self.assertIs(policy["source_truth_over_fluency"], True)
        self.assertIs(
            policy["deterministic_qa_authorizes_change"],
            False,
        )
        self.assertEqual(
            policy["unresolved_context_action"],
            "REVIEW",
        )
        self.assertIs(
            policy[
                "protected_literal_change_requires_authorization"
            ],
            True,
        )
        self.assertIs(
            policy["ai_suggestion_is_approval"],
            False,
        )


if __name__ == "__main__":
    unittest.main()
