"""Regression tests for DBabel's cross-file package contracts."""
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_package import PACKAGE_VERSION, cross_contract_errors


class PackageContractTests(unittest.TestCase):
    def assert_rejected_after(self, relative_path, transform, fragment):
        with tempfile.TemporaryDirectory() as temp:
            copy_root = Path(temp) / 'repo'
            shutil.copytree(
                ROOT,
                copy_root,
                ignore=shutil.ignore_patterns(
                    '.git', '.venv', '__pycache__', '.pytest_cache',
                    'output', 'cache', 'source_cache', 'private',
                    'customer_data', 'project_glossary_private',
                    'translation_memory_private'))
            path = copy_root / relative_path
            transform(path)
            errors = cross_contract_errors(copy_root)
            self.assertTrue(any(fragment in error for error in errors), errors)

    def test_package_version_constant(self):
        self.assertEqual(PACKAGE_VERSION, '1.4.0')

    def test_cross_contracts_clean(self):
        self.assertEqual(cross_contract_errors(ROOT), [])

    def test_readme_version_drift_is_rejected(self):
        def mutate(path):
            text = path.read_text(encoding='utf-8')
            path.write_text(text.replace('Repository version: **1.4.0**',
                                         'Repository version: **9.9.9**'),
                            encoding='utf-8')
        self.assert_rejected_after(
            'README.md', mutate, 'repository version does not match package version')

    def test_example_router_drift_is_rejected(self):
        def mutate(path):
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            data['routes'] = data['routes'][:-1]
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
        self.assert_rejected_after(
            'config/example_router.yaml', mutate,
            'route IDs do not match worked-example sections')

    def test_glossary_header_drift_is_rejected(self):
        def mutate(path):
            text = path.read_text(encoding='utf-8')
            path.write_text(text.replace('entry_id,', 'id,'), encoding='utf-8')
        self.assert_rejected_after(
            'templates/project_glossary.csv', mutate,
            'header drifted from glossary loader contract')

    def test_unknown_format_backend_is_rejected(self):
        def mutate(path):
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            data['formats']['docx']['audit_backends'].insert(0, 'nonexistent_backend')
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
        self.assert_rejected_after(
            'config/format_registry.yaml', mutate, 'references unknown backend')

    def test_workflow_safety_drift_is_rejected(self):
        def mutate(path):
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            data['rules']['deterministic_qa_authorizes_repair'] = True
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
        self.assert_rejected_after(
            'config/workflow.yaml', mutate,
            'safety invariant deterministic_qa_authorizes_repair must be False')

    def test_resource_router_example_drift_is_rejected(self):
        def mutate(path):
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            data['example_routes']['execution_scope'] = 'Z9'
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
        self.assert_rejected_after(
            'config/resource_router.yaml', mutate,
            'example routes drifted from example_router.yaml')


if __name__ == '__main__':
    unittest.main()
