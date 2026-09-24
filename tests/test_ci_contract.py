"""Regression tests for the supported CI runtime matrix and validation gates."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/validate.yml'


class CIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf-8')
        cls.data = yaml.safe_load(cls.text)
        cls.job = cls.data['jobs']['validate']
        cls.steps = cls.job['steps']

    def test_os_matrix(self):
        self.assertEqual(
            set(self.job['strategy']['matrix']['os']),
            {
                'ubuntu-latest',
                'macos-latest',
                'windows-latest',
            },
        )

    def test_python_matrix_includes_minimum_and_reference_versions(self):
        versions = {str(value) for value in self.job['strategy']['matrix']['python-version']}
        self.assertEqual(versions, {'3.9', '3.11'})

    def test_matrix_does_not_fail_fast(self):
        self.assertIs(self.job['strategy']['fail-fast'], False)

    def test_required_validation_commands_are_present(self):
        runs = '\n'.join(str(step.get('run', '')) for step in self.steps)
        required = [
            'python scripts/check_package.py',
            'python scripts/validate_glossary.py tests/fixtures/project_glossary.json',
            'python scripts/validate_glossary.py tests/fixtures/project_glossary.csv',
            'python scripts/check_bilingual_integrity.py',
            'python scripts/prepare_runtime.py',
            'python -m unittest discover -s tests -v',
            'python scripts/validate_report.py examples/audit_report.json',
            'python scripts/check_package.py --write-manifest',
            'git diff --check',
        ]
        for command in required:
            with self.subTest(command=command):
                self.assertIn(command, runs)

    def test_ci_installs_only_core_validation_requirements(self):
        runs = '\n'.join(str(step.get('run', '')) for step in self.steps)
        self.assertIn('python -m pip install -r requirements-dev.txt', runs)
        for optional in ('markitdown', 'docling', 'python-magic', 'filetype', 'python-docx',
                         'python-pptx', 'openpyxl', 'pypdf', 'tika'):
            with self.subTest(optional=optional):
                self.assertNotIn('pip install ' + optional, runs)


if __name__ == '__main__':
    unittest.main()
