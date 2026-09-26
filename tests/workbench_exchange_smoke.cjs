// Run against a disposable server; this creates a new session and saves a glossary.
const {chromium}=require('playwright');const fs=require('fs');const path=require('path');
if(!process.env.DBABEL_TEST_URL||!process.env.DBABEL_TEST_OUTPUT)throw Error('Set DBABEL_TEST_URL and DBABEL_TEST_OUTPUT for disposable smoke fixtures.');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.DBABEL_CHROME?{executablePath:process.env.DBABEL_CHROME}:{})});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('requestfailed',r=>errors.push(r.url().split('/').pop()+': '+r.failure().errorText));page.on('dialog',d=>d.accept());
 const out=process.env.DBABEL_TEST_OUTPUT;fs.mkdirSync(out,{recursive:true});
 await page.goto(process.env.DBABEL_TEST_URL);await page.waitForSelector('#segmentRows tr');
 const original=await page.locator('#sourceText').innerText();
 await page.selectOption('#languageSelect','zh-CN');await page.waitForSelector('html[lang="zh-CN"] #segmentRows tr');
 if(await page.locator('#sourceText').innerText()!==original)throw Error('Language switch changed source text');
 if(await page.locator('#acceptButton').innerText()!=='✓接受建议')throw Error('Primary action untranslated');
 await page.selectOption('#themeSelect','dark');
 for(const width of [1440,1100,768,390]){
  await page.setViewportSize({width,height:1000});await page.screenshot({path:path.join(out,`workbench-zh-dark-${width}.png`),fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Horizontal page overflow at '+width);
  const visible=await page.locator('#languageSelect').isVisible();if(!visible)throw Error('Language control hidden at '+width);
  if(width>980){const a=await page.locator('.table-wrap').boundingBox(),b=await page.locator('.inspector').boundingBox();if(a.x+a.width>b.x+1)throw Error('Inspector overlays table at '+width);}
 }
 await page.setViewportSize({width:1440,height:1000});await page.selectOption('#themeSelect','light');await page.screenshot({path:path.join(out,'workbench-zh-light.png'),fullPage:true});
 for(const fmt of ['json','csv','tsv','md','html','txt']){await page.selectOption('#resultFormat',fmt);const d=page.waitForEvent('download');await page.click('#exportButton');const download=await d;await download.saveAs(path.join(out,download.suggestedFilename()));if(!fs.statSync(path.join(out,download.suggestedFilename())).size)throw Error('Empty export');}
 const json=JSON.parse(fs.readFileSync(path.join(out,'dbabel-review.json')));if(!json.units.length||!json.decisions.length)throw Error('Snapshot missing review data');
 await page.locator('[data-view="Terminology"]').click();await page.locator('#glossaryUpload').setInputFiles(path.join(__dirname,'../templates/project_glossary.csv'));await page.click('#validateGlossary');await page.waitForFunction(()=>document.querySelector('#validateGlossary')&&!document.querySelector('#validateGlossary').disabled);if(!await page.locator('#glossaryScore').innerText())throw Error('No glossary report');
 await page.click('#openIntake');await page.locator('#sourceUpload').setInputFiles({name:'source.txt',mimeType:'text/plain',buffer:Buffer.from('主库发送归档日志。\n最大连接数为 1000。')});await page.fill('#intakeTargetLanguages','en,ja');await page.click('#inspectDocument');await page.waitForFunction(()=>document.querySelector('#intakeStatus').textContent.includes('segment_count'));
 await page.click('#createIntake');await page.waitForFunction(()=>document.querySelectorAll('#segmentRows tr').length===4).catch(async e=>{console.error(await page.locator('body').innerText(),errors);throw e;});
 for(let i=0;i<4;i++){await page.locator('#segmentRows tr').nth(i).click();if(!(await page.locator('#suggestionBox').innerText()).trim()||!(await page.locator('#reasonBox').innerText()).trim())throw Error('Empty suggestion guidance');if(!await page.locator('#acceptButton').isDisabled())throw Error('Instruction accepted as translation');}
 await page.selectOption('#resultFormat','json');let d=page.waitForEvent('download');await page.click('#exportButton');let download=await d;await download.saveAs(path.join(out,'multilingual-review.json'));let multilingual=JSON.parse(fs.readFileSync(path.join(out,'multilingual-review.json')));if(new Set(multilingual.units.map(x=>x.target_language)).size!==2)throw Error('Missing target language');
 await page.selectOption('#languageSelect','en');await page.waitForSelector('html[lang="en"] #segmentRows tr').catch(async e=>{console.error('Language reload:',await page.locator('body').innerText(),errors);throw e;});if(!(await page.locator('#suggestionBox').innerText()).includes('Draft the'))throw Error('English guidance missing');
 if(errors.length)throw Error(errors.join('\n'));await browser.close();console.log('PASS: UI languages, data preservation, themes, four widths, six downloads, glossary upload, preflight, multilingual intake and guidance.');
})().catch(e=>{console.error(e);process.exit(1)});
