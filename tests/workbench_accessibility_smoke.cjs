// Disposable synthetic session only. Scan current UI states and exercise keyboard review.
const {chromium}=require('playwright');
const axe=require('axe-core');
const fs=require('fs'),path=require('path');
if(!process.env.DBABEL_TEST_URL||!process.env.DBABEL_TEST_OUTPUT)throw Error('Use tests/run_browser_smoke.py for isolated fixtures.');
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.DBABEL_CHROME?{executablePath:process.env.DBABEL_CHROME}:{})});
  const findings=[];
  try{
    // Axe is injected only in this test context; the app's production CSP stays intact.
    const page=await browser.newPage({viewport:{width:1440,height:1000},bypassCSP:true});
    // Exercise the candidate response contract even when the optional matcher
    // is absent. Candidate text must remain inert and must not approve a unit.
    await page.route('**/api/translation-memory/candidates?*',route=>route.fulfill({
      contentType:'application/json',body:JSON.stringify({available:true,authority:'SUGGESTION_ONLY',
        candidates:[{id:'SYNTHETIC_REFERENCE',score:92.5,source:'Source <img src=x onerror="window.unsafeMemory=true">',
          target:'Synthetic reference translation',authority:'SUGGESTION_ONLY',
          scope:{kind:'DOCUMENT',context:{product:'Synthetic Product'}},
          differences:[{operation:'replace',before:'old wording',after:'current wording'}]}]})
    }));
    await page.goto(process.env.DBABEL_TEST_URL);
    await page.waitForSelector('#segmentRows tr');
    await page.locator('#similarMemoryList [data-memory-id="SYNTHETIC_REFERENCE"]').waitFor();
    if(await page.locator('#similarMemoryList img').count()||await page.evaluate(()=>Boolean(window.unsafeMemory)))throw Error('Memory reference text executed as markup');
    if(await page.inputValue('#decisionSelect')!=='UNREVIEWED')throw Error('A memory reference changed the human decision');
    const firstId=await page.locator('#segmentRows tr').first().getAttribute('data-id');
    await page.locator('#segmentRows tr.active').focus();
    await page.keyboard.press('ArrowDown');
    await page.waitForFunction(id=>document.querySelector('#segmentRows tr.active').dataset.id!==id,firstId);
    await page.waitForFunction(()=>document.querySelector('#segmentRows tr.active')===document.activeElement);
    await page.keyboard.press('Enter');
    if(await page.locator('#editAction').evaluate(button=>button!==document.activeElement))throw Error('Review action not focused');
    await page.keyboard.press('Enter');
    await page.fill('#targetText','Synthetic keyboard edit');
    await page.keyboard.press('Escape');
    if(!await page.locator('#targetText').getAttribute('readonly')){
      if(!(await page.locator('#targetText').evaluate(input=>input.readOnly)))throw Error('Escape did not cancel the edit');
    }
    await page.locator('#editAction').press('Enter');
    await page.fill('#targetText','Synthetic keyboard approved edit');
    await page.keyboard.press('Control+Enter');
    await page.waitForFunction(()=>document.querySelector('#decisionSelect').value==='USER_EDITED');
    await page.locator('#suggestionTab').focus();
    await page.keyboard.press('ArrowRight');
    if(await page.locator('#evidenceTab').getAttribute('aria-selected')!=='true'||!await page.locator('#tabEvidence').isVisible())throw Error('Keyboard tab activation failed');
    await page.keyboard.press('End');
    if(await page.locator('#terminologyTab').getAttribute('aria-selected')!=='true')throw Error('End did not select the last tab');
    await page.keyboard.press('Home');
    for(const language of ['en','zh-CN']){
      if(await page.inputValue('#languageSelect')!==language){
        await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.selectOption('#languageSelect',language)]);
      }
      await page.waitForSelector(`html[lang="${language}"] #segmentRows tr`);
      for(const theme of ['light','dark']){
        await page.selectOption('#themeSelect',theme);
        await page.addScriptTag({content:axe.source});
        for(const tab of ['suggestion','evidence','terminology']){
          await page.locator(`[data-tab="${tab}"]`).click();
          const result=await page.evaluate(async()=>window.axe.run(document.querySelector('.app-shell'),{
            runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}
          }));
          findings.push({language,theme,tab,violations:result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});
        }
      }
    }
    fs.mkdirSync(process.env.DBABEL_TEST_OUTPUT,{recursive:true});
    fs.writeFileSync(path.join(process.env.DBABEL_TEST_OUTPUT,'accessibility.json'),JSON.stringify(findings,null,2));
    const failures=findings.filter(state=>state.violations.length);
    if(failures.length)throw Error('Accessibility violations: '+JSON.stringify(failures));
    console.log('PASS: inert memory references without approval, row navigation, keyboard edit/cancel, tab keyboard/state, 12 language/theme/tab accessibility scans.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
