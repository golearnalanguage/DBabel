#!/usr/bin/env python3
"""Check Skill metadata, schemas, examples, local links, and package checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml
from jsonschema import Draft202012Validator
from validate_report import ROOT, validate_report


def package_paths(root=ROOT):
    # A checkout uses Git's ignore rules. An extracted package uses its file tree.
    if (root / '.git').exists():
        names = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
            cwd=root).decode().split('\0')
        return sorted({name for name in names if name and name != 'MANIFEST.sha256'
                       and (root / name).is_file()})
    ignored = {'.git', '.venv', '__pycache__', '.pytest_cache', 'output', 'cache',
               'source_cache', 'private', 'customer_data', 'project_glossary_private',
               'translation_memory_private'}
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                  if p.is_file() and not (set(p.relative_to(root).parts) & ignored)
                  and p.name not in {'MANIFEST.sha256', '.DS_Store'}
                  and not p.name.startswith('.env'))


def manifest(paths, root=ROOT):
    return ''.join(f'{hashlib.sha256((root / name).read_bytes()).hexdigest()}  ./{name}\n'
                   for name in paths)


def check_package(write_manifest=False):
    errors = []
    paths = package_paths()
    skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
    match = re.match(r'^---\n(.*?)\n---\n', skill, re.S)
    if not match:
        return ['SKILL.md: missing YAML frontmatter']
    metadata = yaml.safe_load(match[1])
    allowed = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
    if not isinstance(metadata, dict):
        return ['SKILL.md: frontmatter must be an object']
    if set(metadata) - allowed:
        errors.append('SKILL.md: unsupported frontmatter field')
    name = metadata.get('name', '')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64:
        errors.append('SKILL.md: invalid skill name')
    desc = metadata.get('description', '')
    if not isinstance(desc, str) or not 1 <= len(desc) <= 1024:
        errors.append('SKILL.md: invalid description')
    version = metadata.get('metadata', {}).get('version')
    if version != '1.3.0':
        errors.append('SKILL.md: unexpected package version')
    for name in paths:
        p = ROOT / name
        try:
            if p.suffix in {'.yaml', '.yml'}:
                data = yaml.safe_load(p.read_text(encoding='utf-8'))
                if name.startswith('config/') and data.get('version') != version:
                    errors.append(f'{name}: inconsistent version')
            if name.startswith('schemas/') and p.suffix == '.json':
                schema = json.loads(p.read_text(encoding='utf-8'))
                Draft202012Validator.check_schema(schema)
                def refs(value):
                    if isinstance(value, dict):
                        if '$ref' in value and not value['$ref'].startswith('#'):
                            yield value['$ref']
                        for v in value.values():
                            yield from refs(v)
                    elif isinstance(value, list):
                        for v in value:
                            yield from refs(v)
                for ref in refs(schema):
                    if not (p.parent / ref).is_file():
                        errors.append(f'{name}: unresolved schema reference {ref}')
            if p.suffix == '.md':
                for link in re.findall(r'\[[^\]\n]*\]\(([^)\s]+)\)', p.read_text(encoding='utf-8')):
                    if re.match(r'^[a-zA-Z]+:|^#', link):
                        continue
                    target = link.split('#')[0]
                    if target and not (p.parent / target).exists():
                        errors.append(f'{name}: broken local link {link}')
        except (ValueError, yaml.YAMLError) as exc:
            errors.append(f'{name}: {exc}')
    for p in (ROOT / 'examples').glob('*report.json'):
        errors.extend(f'{p.name}: {e}' for e in validate_report(json.loads(p.read_text(encoding='utf-8'))))
    wanted = manifest(paths)
    target = ROOT / 'MANIFEST.sha256'
    if write_manifest and not errors:
        target.write_text(wanted, encoding='utf-8')
    if not target.exists() or target.read_text(encoding='utf-8') != wanted:
        errors.append('MANIFEST.sha256: stale or incomplete; regenerate after intentional edits')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-manifest', action='store_true')
    args = parser.parse_args()
    errors = check_package(args.write_manifest)
    if errors:
        parser.exit(1, '\n'.join(errors) + '\n')
    print('Package checks passed.')


if __name__ == '__main__':
    main()
