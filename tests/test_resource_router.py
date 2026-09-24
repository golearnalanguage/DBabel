import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from route_resources import (
    RoutingError,
    build_plan,
    load_router_config,
    validate_resource_plan,
    validate_task_context,
)


def make_context(mode="LOOKUP", fmt="none"):
    return {
        "format_version": "1.0",
        "mode": mode,
        "format": fmt,
        "signals": {
            "has_project_glossary": False,
            "aligned_bilingual_units": False,
            "structured_output": False,
            "needs_external_evidence": False,
            "external_research_requested": False,
            "public_research_permitted": False,
            "approved_resource_resolves_scope": False,
            "repair_requested": False,
            "repair_authorized": False,
        },
        "risk_tags": [],
    }


class ResourceRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_router_config()

    def plan(self, context):
        return build_plan(context, config=self.config, check_package_paths=False)

    def test_router_config_schema_is_enforced(self):
        broken = copy.deepcopy(self.config)
        broken["policy"]["max_example_sections"] = 4
        schema = json.loads(
            (ROOT / "schemas" / "resource_router.schema.json").read_text(encoding="utf-8")
        )
        errors = list(Draft202012Validator(schema).iter_errors(broken))
        self.assertTrue(errors)

    def test_task_context_schema_is_valid(self):
        self.assertEqual(validate_task_context(make_context()), [])

    def test_resource_plan_schema_is_valid(self):
        plan = self.plan(make_context())
        self.assertEqual(validate_resource_plan(plan), [])

    def test_lookup_is_minimal(self):
        plan = self.plan(make_context())
        self.assertEqual(
            plan["load_now"],
            ["references/03_TERMINOLOGY_CLASSIFICATION.md"],
        )
        self.assertNotIn(
            "references/08_QA_AND_RELEASE_GATES.md",
            plan["load_now"],
        )
        self.assertNotIn(
            "references/15_DETERMINISTIC_BILINGUAL_QA.md",
            plan["load_now"],
        )

    def test_pdf_audit_loads_format_policy_only_for_format_layer(self):
        context = make_context("AUDIT", "pdf")
        plan = self.plan(context)
        self.assertIn(
            "references/06_FILE_STRUCTURE_AND_FORMAT_POLICY.md",
            plan["load_now"],
        )
        self.assertNotIn(
            "references/07_TRANSLATION_AND_MT_POLICY.md",
            plan["load_now"],
        )

    def test_bilingual_review_with_alignment_routes_deterministic_qa(self):
        context = make_context("BILINGUAL_REVIEW", "docx")
        context["signals"]["aligned_bilingual_units"] = True
        plan = self.plan(context)
        self.assertIn(
            "references/07_TRANSLATION_AND_MT_POLICY.md",
            plan["load_now"],
        )
        self.assertIn(
            "references/15_DETERMINISTIC_BILINGUAL_QA.md",
            plan["load_now"],
        )

    def test_no_alignment_defers_deterministic_qa(self):
        context = make_context("BILINGUAL_REVIEW", "docx")
        plan = self.plan(context)
        self.assertNotIn(
            "references/15_DETERMINISTIC_BILINGUAL_QA.md",
            plan["load_now"],
        )
        self.assertTrue(
            any("aligned bilingual units are unavailable" in note for note in plan["notes"])
        )

    def test_project_glossary_routes_only_project_terminology_policy(self):
        context = make_context("TRANSLATE", "md")
        context["signals"]["has_project_glossary"] = True
        plan = self.plan(context)
        self.assertIn(
            "references/14_PROJECT_TERMINOLOGY_RESOLUTION.md",
            plan["load_now"],
        )

    def test_structured_output_routes_output_contract(self):
        context = make_context("AUDIT", "txt")
        context["signals"]["structured_output"] = True
        plan = self.plan(context)
        self.assertIn(
            "references/11_OUTPUT_AND_DATA_CONTRACTS.md",
            plan["load_now"],
        )

    def test_repair_rules_require_authorization(self):
        context = make_context("AUDIT", "docx")
        context["signals"]["repair_requested"] = True
        plan = self.plan(context)
        self.assertNotIn(
            "references/08_QA_AND_RELEASE_GATES.md",
            plan["load_now"],
        )
        self.assertTrue(any("not authorized" in note for note in plan["notes"]))

        context["signals"]["repair_authorized"] = True
        plan = self.plan(context)
        self.assertIn(
            "references/08_QA_AND_RELEASE_GATES.md",
            plan["load_now"],
        )

    def test_repair_authorized_without_request_is_invalid(self):
        context = make_context()
        context["signals"]["repair_authorized"] = True
        self.assertTrue(validate_task_context(context))

    def test_repair_mode_requires_request_signal(self):
        context = make_context("REPAIR", "docx")
        self.assertTrue(validate_task_context(context))

    def test_source_research_with_permission_loads_search_strategy(self):
        context = make_context("SOURCE_RESEARCH")
        context["signals"]["public_research_permitted"] = True
        plan = self.plan(context)
        self.assertIn(
            "references/04_SOURCE_AND_EVIDENCE_POLICY.md",
            plan["load_now"],
        )
        self.assertIn(
            "references/13_SEARCH_AND_RETRIEVAL_STRATEGY.md",
            plan["load_now"],
        )

    def test_public_search_strategy_not_loaded_without_permission(self):
        context = make_context("SOURCE_RESEARCH")
        plan = self.plan(context)
        self.assertNotIn(
            "references/13_SEARCH_AND_RETRIEVAL_STRATEGY.md",
            plan["load_now"],
        )
        self.assertTrue(
            any("Public research is not permitted" in note for note in plan["notes"])
        )

    def test_approved_resource_suppresses_unrequested_external_research(self):
        context = make_context("TRANSLATE")
        context["signals"]["needs_external_evidence"] = True
        context["signals"]["approved_resource_resolves_scope"] = True
        context["signals"]["public_research_permitted"] = True
        plan = self.plan(context)
        self.assertNotIn(
            "references/13_SEARCH_AND_RETRIEVAL_STRATEGY.md",
            plan["load_now"],
        )
        self.assertTrue(
            any("approved scoped resource" in note for note in plan["notes"])
        )

    def test_explicit_research_overrides_approved_resource_suppression(self):
        context = make_context("TRANSLATE")
        context["signals"]["approved_resource_resolves_scope"] = True
        context["signals"]["external_research_requested"] = True
        context["signals"]["public_research_permitted"] = True
        plan = self.plan(context)
        self.assertIn(
            "references/04_SOURCE_AND_EVIDENCE_POLICY.md",
            plan["load_now"],
        )
        self.assertIn(
            "references/13_SEARCH_AND_RETRIEVAL_STRATEGY.md",
            plan["load_now"],
        )

    def test_technical_claim_routes_claim_boundary(self):
        context = make_context("AUDIT")
        context["risk_tags"] = ["technical_claim"]
        plan = self.plan(context)
        self.assertIn(
            "references/10_TECHNICAL_CLAIM_BOUNDARY.md",
            plan["load_now"],
        )

    def test_cross_product_routes_concept_mapping_and_example(self):
        context = make_context("AUDIT")
        context["risk_tags"] = ["cross_product_mapping"]
        plan = self.plan(context)
        self.assertIn(
            "references/05_PRODUCT_SCOPE_AND_CONCEPT_MAPPING.md",
            plan["load_now"],
        )
        self.assertEqual(plan["example_sections"], ["C1"])

    def test_execution_scope_routes_only_a2_example(self):
        context = make_context("BILINGUAL_REVIEW")
        context["risk_tags"] = ["execution_scope"]
        plan = self.plan(context)
        self.assertEqual(plan["example_sections"], ["A2"])

    def test_example_loading_is_capped_and_ordered_by_risk_relevance(self):
        context = make_context("BILINGUAL_REVIEW")
        context["risk_tags"] = [
            "execution_scope",
            "number_unit_scope",
            "placeholder_position",
            "ocr_ambiguity",
        ]
        plan = self.plan(context)
        self.assertEqual(plan["example_sections"], ["A2", "B3", "D3"])
        self.assertTrue(
            any("capped at 3 sections" in note for note in plan["notes"])
        )

    def test_no_example_match_loads_no_example_sections(self):
        context = make_context("AUDIT")
        context["risk_tags"] = ["technical_claim"]
        plan = self.plan(context)
        self.assertEqual(plan["example_sections"], [])

    def test_load_order_is_stable_and_deduplicated(self):
        context = make_context("SOURCE_RESEARCH")
        context["signals"]["needs_external_evidence"] = True
        context["signals"]["external_research_requested"] = True
        context["signals"]["public_research_permitted"] = True
        context["risk_tags"] = ["version_sensitive"]
        plan = self.plan(context)
        self.assertEqual(
            len(plan["load_now"]),
            len(set(plan["load_now"])),
        )
        self.assertEqual(
            plan["load_now"].count("references/04_SOURCE_AND_EVIDENCE_POLICY.md"),
            1,
        )

    def test_full_reference_sweep_is_never_routed_for_lookup(self):
        plan = self.plan(make_context("LOOKUP"))
        self.assertLess(len(plan["load_now"]), len(plan["not_loaded"]))
        self.assertTrue(
            any("Full reference sweep is prohibited" in note for note in plan["notes"])
        )

    def test_fixture_contexts_validate_and_route(self):
        path = ROOT / "tests" / "fixtures" / "task_contexts.jsonl"
        count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            context = json.loads(line)
            self.assertEqual(validate_task_context(context), [])
            plan = self.plan(context)
            self.assertEqual(validate_resource_plan(plan), [])
            count += 1
        self.assertGreaterEqual(count, 6)

    def test_live_package_paths_and_example_ids_resolve(self):
        # This is the integration test: all routed package resources must exist,
        # and every configured worked-example route must exist in example_router.yaml.
        plan = build_plan(
            make_context("LOOKUP"),
            config=self.config,
            check_package_paths=True,
        )
        self.assertEqual(validate_resource_plan(plan), [])


if __name__ == "__main__":
    unittest.main()
