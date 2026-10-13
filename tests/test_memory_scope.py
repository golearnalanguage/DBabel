import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from runtime.memory_scope import canonical_scope, record_applies
from runtime.translation_memory import remember, match, similar_candidates, export_entries
from runtime.translation import rejected_for_unit


class MemoryScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'memory.sqlite3'
        self.override = patch.dict(os.environ, {'DBABEL_TRANSLATION_MEMORY': str(self.path)})
        self.override.start()
    def tearDown(self):
        self.override.stop()
        self.temp.cleanup()
    def unit(self, product='A', version='1'):
        return {'id':'U1','source':'配置主库','source_language':'zh-CN','target_language':'en',
                'context':{'project_id':'project','product':product,'version':version,'text_role':'PROSE'}}
    def test_product_and_version_isolate_exact_and_rejected_memory(self):
        unit = self.unit()
        remember(unit, {'status':'USER_EDITED','approved_target':'Configure primary database'})
        self.assertEqual(match(unit,'zh-CN','en'),'Configure primary database')
        self.assertIsNone(match(self.unit('B'),'zh-CN','en'))
        self.assertIsNone(match(self.unit(version='2'),'zh-CN','en'))
        record={'source':unit['source'],'source_language':'zh-CN','target_language':'en',
                'rejected_target':'bad','memory_scope':canonical_scope(unit)}
        self.assertEqual(rejected_for_unit(unit,'zh-CN','en',[record]),['bad'])
        self.assertEqual(rejected_for_unit(self.unit('B'),'zh-CN','en',[record]),[])
    def test_legacy_migration_preserves_data_without_automatic_reuse(self):
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute('CREATE TABLE memories(source_language TEXT,target_language TEXT,text_role TEXT,source_hash TEXT,source TEXT,kind TEXT,target TEXT,decision TEXT,updated_at TEXT)')
                import hashlib
                db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)',('zh-CN','en','PROSE',hashlib.sha256('配置主库'.encode()).hexdigest(),'配置主库','PREFERRED','old target','USER_EDITED','2026-01-01'))
        self.assertIsNone(match(self.unit(),'zh-CN','en'))
        rows=export_entries()
        self.assertEqual(rows[0]['target'],'old target')
        self.assertEqual(rows[0]['scope']['kind'],'LEGACY_UNSCOPED')
        self.assertTrue(self.path.with_name('memory.pre-scope-v1.sqlite3').exists())
    def test_fuzzy_candidates_are_scoped_and_never_approved(self):
        unit=self.unit()
        remember(unit,{'status':'USER_EDITED','approved_target':'Configure primary database'})
        query=dict(unit,source='配置主库服务')
        result=similar_candidates(query,'zh-CN','en',score_cutoff=50)
        if not result['available']:
            self.skipTest('optional RapidFuzz not installed')
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['candidates'][0]['authority'],'SUGGESTION_ONLY')
        self.assertTrue(result['candidates'][0]['differences'])
        self.assertIsNone(match(query,'zh-CN','en'))
        self.assertEqual(similar_candidates(self.unit('B'),'zh-CN','en')['candidates'],[])
    def test_legacy_rejection_cannot_become_global_constraint(self):
        record={'source':'配置主库','source_language':'zh-CN','target_language':'en','rejected_target':'bad'}
        self.assertFalse(record_applies(record,self.unit()))
