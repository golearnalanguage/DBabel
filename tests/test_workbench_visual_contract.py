import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class VisualContractTests(unittest.TestCase):
    def test_desktop_brand_and_reference_layout_contract(self):
        html=(ROOT/'review_workbench'/'static'/'index.html').read_text(encoding='utf-8')
        css=(ROOT/'review_workbench'/'static'/'style.css').read_text(encoding='utf-8')
        for marker in [
            'dbabel-workbench-logo.png','class="sidebar"','class="document-bar"',
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
        logo=ROOT/'review_workbench'/'static'/'dbabel-workbench-logo.png'
        preview=ROOT/'assets'/'dbabel-review-workbench-preview.png'
        self.assertTrue(logo.is_file());self.assertTrue(preview.is_file())
        self.assertGreater(logo.stat().st_size,1000);self.assertGreater(preview.stat().st_size,10000)

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

    def test_brand_identity_is_clay_and_not_fake_window_chrome(self):
        desktop=(ROOT/'review_workbench'/'static'/'index.html').read_text(encoding='utf-8')
        portable=(ROOT/'review_workbench'/'portable_template.html').read_text(encoding='utf-8')
        for text in (desktop, portable):
            self.assertIn('<span class="avatar">CL</span><strong>clay</strong>', text)
            self.assertNotIn('Jane Doe', text)
            self.assertNotIn('Local Reviewer', text)
            self.assertNotIn('Portable Reviewer', text)
            self.assertNotIn('window-control', text)
            self.assertNotIn('maximize', text.lower())
            self.assertNotIn('minimize', text.lower())

    def test_logo_has_transparent_background_for_surface_blending(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed in minimal package runtime')
        logo=Image.open(ROOT/'review_workbench'/'static'/'dbabel-workbench-logo.png').convert('RGBA')
        alpha=list(logo.getchannel('A').getdata())
        self.assertIn(0, alpha)
        self.assertIn(255, alpha)

    def test_v6_visual_template_is_documented(self):
        doc=(ROOT/'docs'/'REVIEW_WORKBENCH.md').read_text(encoding='utf-8')
        self.assertIn('### V6 brand-shell refinement', doc)
        self.assertIn('transparent DBabel brand lockup', doc)
        self.assertIn('fake operating-system window chrome', doc)
        self.assertIn('`clay`', doc)


    def test_unimplemented_controls_are_explicitly_disabled(self):
        desktop=(ROOT/'review_workbench/static/index.html').read_text(encoding='utf-8')
        portable=(ROOT/'review_workbench/portable_template.html').read_text(encoding='utf-8')
        css=(ROOT/'review_workbench/static/style.css').read_text(encoding='utf-8')

        for content in (desktop,portable):
            self.assertEqual(
                content.count('title="Planned Workbench view"'),
                5,
            )
            self.assertEqual(
                content.count('class="nav-soon">Soon</small>'),
                5,
            )
            self.assertEqual(
                content.count('title="Planned filter"'),
                3,
            )
            self.assertIn(
                'title="Use Review Status above"',
                content,
            )
            self.assertIn(
                'disabled title="Compact view is planned"',
                content,
            )

        self.assertIn(
            'explicit capability-state controls',
            css,
        )
        self.assertIn(
            '.nav-item:disabled',
            css,
        )
        self.assertIn(
            '.filter-collapsed:disabled',
            css,
        )


if __name__=='__main__':
    unittest.main()
