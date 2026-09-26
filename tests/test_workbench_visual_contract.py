import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class VisualContractTests(unittest.TestCase):
    def test_desktop_brand_and_reference_layout_contract(self):
        html=(ROOT/'review_workbench'/'static'/'index.html').read_text(encoding='utf-8')
        css=(ROOT/'review_workbench'/'static'/'style.css').read_text(encoding='utf-8')
        for marker in [
            'dbabel-logo-light.svg','dbabel-logo-dark.svg','class="sidebar"','class="document-bar"',
            'class="metrics-strip"','id="segmentRows"','class="inspector"',
            'Suggested Translation','Evidence from Reference Documents','Accept Suggestion',
            'Keep Current','Quality Check','Project Settings','id="themeSelect"',
            'id="suggestionEvidenceList"'
        ]:
            self.assertIn(marker,html)
        for marker in [
            '--sidebar:240px','--inspector:clamp(460px,30vw,520px)',
            'grid-template-rows:104px 88px minmax(0,1fr)',
            '.brand-lockup{height:154px','.segment-table','.inspector',
            'grid-template-columns:minmax(0,1fr) var(--inspector)',
            '.inline-evidence'
        ]:
            self.assertIn(marker,css)
        self.assertNotIn('http://',html)
        self.assertNotIn('https://',html)

    def test_three_state_theme_contract(self):
        html=(ROOT/'review_workbench'/'static'/'index.html').read_text(encoding='utf-8')
        css=(ROOT/'review_workbench'/'static'/'style.css').read_text(encoding='utf-8')
        js=(ROOT/'review_workbench'/'static'/'app.js').read_text(encoding='utf-8')
        for value in ['value="system"','value="light"','value="dark"']:
            self.assertIn(value,html)
        self.assertIn('html[data-theme="dark"]',css)
        self.assertIn('prefers-color-scheme: dark',css)
        self.assertIn('dbabel-review-theme',js)
        self.assertIn('localStorage.setItem',js)
        self.assertIn("matchMedia('(prefers-color-scheme: dark)')",js)

    def test_human_readable_issue_aliases_are_visual_only(self):
        desktop=(ROOT/'review_workbench'/'static'/'app.js').read_text(encoding='utf-8')
        portable=(ROOT/'review_workbench'/'portable_app.js').read_text(encoding='utf-8')
        for text in [desktop,portable]:
            self.assertIn("NUMBER_UNIT_INTEGRITY:'NUMBER_UNIT'",text)
            self.assertIn("PLACEHOLDER_INTEGRITY:'PLACEHOLDER'",text)
            self.assertIn("ENV_VAR_INTEGRITY:'ENV_VAR'",text)
            self.assertIn('chip.title=raw',text)
        # underlying demo contract remains the full machine label
        issues=(ROOT/'examples'/'review_workbench_demo.dbreview'/'issues.json').read_text(encoding='utf-8')
        self.assertIn('NUMBER_UNIT_INTEGRITY',issues)

    def test_issue_filter_contract_includes_reference_groups(self):
        js=(ROOT/'review_workbench'/'static'/'app.js').read_text(encoding='utf-8')
        for marker in ["'TERM_GROUP','TERM'","'NUMBER_UNIT_INTEGRITY','NUMBER_UNIT'","'EVIDENCE_GROUP','EVIDENCE'","'ERROR','ERROR'","'WARNING','WARNING'"]:
            self.assertIn(marker,js)
        self.assertIn("key==='ERROR'||key==='WARNING'",js)

    def test_responsive_breakpoints_exist(self):
        css=(ROOT/'review_workbench'/'static'/'style.css').read_text(encoding='utf-8')
        self.assertIn('@media (max-width:1450px)',css)
        self.assertIn('@media (max-width:1160px)',css)
        self.assertIn('@media (max-width:980px)',css)
        self.assertIn('@media (max-width:680px)',css)

    def test_logo_and_readme_preview_assets_exist(self):
        from xml.etree import ElementTree as ET
        for theme in ['light','dark']:
            logo=ROOT/'review_workbench/static'/('dbabel-logo-'+theme+'.svg')
            root=ET.fromstring(logo.read_text())
            self.assertEqual(root.tag,'{http://www.w3.org/2000/svg}svg')
            self.assertEqual(logo.read_bytes(),(ROOT/'assets'/logo.name).read_bytes())
        self.assertGreater((ROOT/'assets/dbabel-review-workbench-preview.png').stat().st_size,10000)

    def test_portable_reuses_desktop_css_and_has_embedded_runtime(self):
        template=(ROOT/'review_workbench'/'portable_template.html').read_text(encoding='utf-8')
        builder=(ROOT/'scripts'/'build_portable_review.py').read_text(encoding='utf-8')
        portable_js=(ROOT/'review_workbench'/'portable_app.js').read_text(encoding='utf-8')
        for marker in ['__DBABEL_DATA__','__DBABEL_LOGO__','__DBABEL_CSS__','__DBABEL_PORTABLE_JS__']:
            self.assertEqual(template.count(marker),1)
        self.assertIn("connect-src 'none'",template)
        self.assertNotIn('<script src=',template)
        self.assertNotIn('<link rel="stylesheet"',template)
        self.assertIn('style.css',builder)
        self.assertIn('portable_app.js',builder)
        self.assertIn("value=\"system\"",template)
        self.assertIn('issueAliases',portable_js)
        self.assertIn('suggestionEvidenceList',portable_js)

    def test_example_bundle_is_large_and_varied(self):
        bundle=ROOT/'examples'/'review_workbench_demo.dbreview'
        units=(bundle/'units.jsonl').read_text(encoding='utf-8').strip().splitlines()
        issues=(bundle/'issues.json').read_text(encoding='utf-8')
        self.assertGreaterEqual(len(units),16)
        for marker in ['NUMBER_UNIT_INTEGRITY','PLACEHOLDER_INTEGRITY','PATH_INTEGRITY','VERSION_INTEGRITY','TECHNICAL_CLAIM','EVIDENCE_CONFLICT']:
            self.assertIn(marker,issues)

    def test_server_whitelists_logo_only(self):
        server=(ROOT/'scripts'/'start_review_workbench.py').read_text(encoding='utf-8')
        self.assertIn('"/dbabel-workbench-logo.png": "dbabel-workbench-logo.png"',server)
        self.assertIn('allowed = {',server)

    def test_logo_text_contrast_and_tower_colours(self):
        from xml.etree import ElementTree as ET
        ns={'s':'http://www.w3.org/2000/svg'}
        palettes=[]
        def luminance(hex_colour):
            rgb=[int(hex_colour[i:i+2],16)/255 for i in (1,3,5)]
            linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
            return sum(v*w for v,w in zip(linear,[0.2126,0.7152,0.0722]))
        for theme,background in [('light',1),('dark',0)]:
            root=ET.fromstring((ROOT/'review_workbench/static'/('dbabel-logo-'+theme+'.svg')).read_text())
            for text in root.findall('s:text',ns):
                lum=luminance(text.attrib['fill'])
                self.assertGreater((max(lum,background)+0.05)/(min(lum,background)+0.05),7)
            palettes.append([p.attrib['fill'] for p in root.findall('.//s:path',ns)])
        self.assertEqual(palettes[0],palettes[1]);self.assertGreaterEqual(len(set(palettes[0])),4)

    def test_bulk_selection_has_real_actions(self):
        desktop_html=(ROOT/'review_workbench/static/index.html').read_text(encoding='utf-8')
        portable_html=(ROOT/'review_workbench/portable_template.html').read_text(encoding='utf-8')
        desktop_js=(ROOT/'review_workbench/static/app.js').read_text(encoding='utf-8')
        portable_js=(ROOT/'review_workbench/portable_app.js').read_text(encoding='utf-8')
        css=(ROOT/'review_workbench/static/style.css').read_text(encoding='utf-8')

        for content in (desktop_html,portable_html):
            self.assertIn('id="bulkActions"',content)
            self.assertIn('id="bulkCount"',content)
            self.assertIn('id="bulkKeep"',content)
            self.assertIn('id="bulkDefer"',content)
            self.assertIn('id="bulkClear"',content)
            self.assertIn('id="selectPage"',content)

        for code in (desktop_js,portable_js):
            self.assertIn('selectedUnits:new Set()',code)
            self.assertIn('function bulkDecision(status)',code)
            self.assertIn("bulkDecision('KEEP_CURRENT')",code)
            self.assertIn("bulkDecision('DEFERRED')",code)
            self.assertIn("el('selectPage').addEventListener",code)
            self.assertIn('window.confirm',code)

        self.assertIn(
            'functional bulk-selection controls',
            css,
        )
        self.assertIn(
            'tr.batch-selected',
            css,
        )


    def test_technique_reasoning_is_visible_but_not_a_decision(self):
        desktop_html=(
            ROOT/'review_workbench/static/index.html'
        ).read_text(encoding='utf-8')

        portable_html=(
            ROOT/'review_workbench/portable_template.html'
        ).read_text(encoding='utf-8')

        desktop_js=(
            ROOT/'review_workbench/static/app.js'
        ).read_text(encoding='utf-8')

        portable_js=(
            ROOT/'review_workbench/portable_app.js'
        ).read_text(encoding='utf-8')

        css=(
            ROOT/'review_workbench/static/style.css'
        ).read_text(encoding='utf-8')

        for content in (
            desktop_html,
            portable_html,
        ):
            self.assertIn(
                'Technique reasoning',
                content,
            )
            self.assertIn(
                'Diagnostic · human decision unchanged',
                content,
            )
            self.assertIn(
                'id="techniqueList"',
                content,
            )

        for code in (
            desktop_js,
            portable_js,
        ):
            self.assertIn(
                'function renderTechniqueMetadata(u)',
                code,
            )
            self.assertIn(
                'technique.technique_id',
                code,
            )
            self.assertIn(
                'technique.trigger_reason',
                code,
            )
            self.assertIn(
                'technique.quality_dimensions',
                code,
            )
            self.assertIn(
                'technique.transformations',
                code,
            )

        self.assertIn(
            '.technique-card',
            css,
        )

        issues=(
            ROOT
            / 'examples'
            / 'review_workbench_demo.dbreview'
            / 'issues.json'
        ).read_text(
            encoding='utf-8'
        )

        self.assertIn(
            'PROPOSITION_PRESERVING_REORDERING',
            issues,
        )

        decision_schema=(
            ROOT
            / 'schemas'
            / 'review_decision.schema.json'
        ).read_text(
            encoding='utf-8'
        )

        self.assertNotIn(
            'TECHNIQUE_ACCEPTED',
            decision_schema,
        )



if __name__=='__main__':
    unittest.main()
