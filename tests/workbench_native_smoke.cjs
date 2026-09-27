// Disposable sessions only: exercises layout hit targets and native ZIP delivery.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path');
if(!process.env.DBABEL_TEST_URL||!process.env.DBABEL_TEST_OUTPUT)throw Error('Set disposable DBABEL_TEST_URL and DBABEL_TEST_OUTPUT.');
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.DBABEL_CHROME?{executablePath:process.env.DBABEL_CHROME}:{})});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
    fs.mkdirSync(process.env.DBABEL_TEST_OUTPUT,{recursive:true});
    await page.goto(process.env.DBABEL_TEST_URL);await page.waitForSelector('#segmentRows tr');
    for(const language of ['en','zh-CN']){
      await page.selectOption('#languageSelect',language);await page.waitForSelector(`html[lang="${language}"] #segmentRows tr`);
      await page.waitForLoadState('networkidle');
      for(const theme of ['light','dark']){
        await page.selectOption('#themeSelect',theme);
        for(const width of [1920,1440,1280,1100,980,680,390]){
          await page.setViewportSize({width,height:1000});
          await page.evaluate(()=>document.querySelector('#segmentRows .comment-col').scrollIntoView({block:'center'}));
          const failures=await page.evaluate(()=>{
            const fails=[];
            if(document.documentElement.scrollWidth>innerWidth+1)fails.push('page overflow');
            const wrap=document.querySelector('.table-wrap');wrap.scrollTop=0;wrap.scrollLeft=0;
            const cell=document.querySelector('#segmentRows .comment-col'),icon=cell.querySelector('svg');
            const r=icon.getBoundingClientRect(),c=cell.getBoundingClientRect();
            if(r.left<c.left-1||r.right>c.right+1)fails.push('comment clipped inside cell');
            const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
            if(!hit||!cell.contains(hit))fails.push('comment covered');
            const counter=document.querySelector('#segmentCounter').getBoundingClientRect();
            const buttons=document.querySelector('.inspector-head>div').getBoundingClientRect();
            if(counter.left<buttons.right&&counter.right>buttons.left&&counter.top<buttons.bottom&&counter.bottom>buttons.top)fails.push('counter overlaps navigation');
            const image=document.querySelector('.brand-lockup img');
            if(!image.complete||!image.naturalWidth||!image.src.endsWith('dbabel-workbench-logo.png'))fails.push('original logo missing');
            return fails;
          });
          if(failures.length){await page.screenshot({path:path.join(process.env.DBABEL_TEST_OUTPUT,'layout-failure.png'),fullPage:true});throw Error(`${language}/${theme}/${width}: ${failures.join(', ')}`);}
        }
      }
    }
    await page.setViewportSize({width:1440,height:1000});await page.selectOption('#themeSelect','dark');
    await page.screenshot({path:path.join(process.env.DBABEL_TEST_OUTPUT,'restored-logo-layout.png'),fullPage:true});
    await page.click('#openIntake');
    await page.locator('#sourceUpload').setInputFiles({name:'manual.TXT',mimeType:'text/plain',buffer:Buffer.from('\ufeff你好。\r\n\r\n第二行。\r\n')});
    await page.fill('#intakeTargetLanguages','en');await page.click('#createIntake');
    await page.waitForFunction(()=>document.querySelectorAll('#segmentRows tr').length===2);
    await page.locator('#segmentRows tr').first().click();await page.click('#editAction');
    await page.fill('#targetText','Hello.');await page.click('#editAction');
    await page.waitForFunction(()=>document.querySelector('#decisionSelect').value==='USER_EDITED');
    await page.selectOption('#exportMode','CHECKPOINT');
    await page.waitForFunction(()=>!document.querySelector('#exportButton').disabled);
    let download=page.waitForEvent('download');await page.click('#exportButton');download=await download;
    if(!download.suggestedFilename().endsWith('.delivery.zip'))throw Error('Native delivery ZIP missing');
    await download.saveAs(path.join(process.env.DBABEL_TEST_OUTPUT,'native.delivery.zip'));
    if(!fs.statSync(path.join(process.env.DBABEL_TEST_OUTPUT,'native.delivery.zip')).size)throw Error('Empty ZIP');
    await page.reload();await page.waitForSelector('#segmentRows tr');
    await page.selectOption('#exportMode','CHECKPOINT');
    await page.waitForFunction(()=>!document.querySelector('#exportButton').disabled);
    download=page.waitForEvent('download');await page.click('#exportButton');download=await download;
    await download.saveAs(path.join(process.env.DBABEL_TEST_OUTPUT,'repeat.delivery.zip'));
    await page.selectOption('#resultFormat','html');download=page.waitForEvent('download');await page.click('#downloadResults');download=await download;
    await download.saveAs(path.join(process.env.DBABEL_TEST_OUTPUT,'bilingual.html'));
    if(errors.length)throw Error(errors.join('\n'));
    console.log('PASS: 28 language/theme/width combinations; comment hit targets; original logo; source-only uppercase extension intake; native ZIP; repeat export; bilingual download.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
