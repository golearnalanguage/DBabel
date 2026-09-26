/* Document uploads stay on the local authenticated Workbench server. */
window.installExchange = function({api,state,el,node,refreshGate}) {
  const t=window.dbabelI18n.t;
  function download(result){const url=URL.createObjectURL(new Blob([result.content],{type:result.content_type+';charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=result.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  window.exportReviewResults=async()=>{try{download(await api('/api/results',{method:'POST',body:JSON.stringify({format:el('resultFormat').value})}));}catch(e){window.workbenchNotice(e.message);}};
  async function filePayload(input){const f=input.files[0];if(!f)throw Error(t('Select a file first.'));if(f.size>16*1024*1024)throw Error(t('Maximum file size: 16 MiB.'));const bytes=new Uint8Array(await f.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return {name:f.name,content_base64:btoa(binary)};}
  const panel=el('exchangePanel');
  el('openIntake').addEventListener('click',()=>{panel.hidden=!panel.hidden;if(!panel.hidden)panel.scrollIntoView({block:'start'});});
  el('closeIntake').addEventListener('click',()=>panel.hidden=true);
  const status=el('intakeStatus');
  async function intake(create){
    const buttons=[el('inspectDocument'),el('createIntake')];buttons.forEach(b=>b.disabled=true);
    try{
      const source=await filePayload(el('sourceUpload'));
      const body={source,source_language:el('intakeSourceLanguage').value.trim(),target_languages:el('intakeTargetLanguages').value.split(',').map(x=>x.trim()),alignment_confirmed:el('confirmAlignment').checked};
      if(create&&el('targetUpload').files.length)body.target=await filePayload(el('targetUpload'));
      if(create&&!confirm(t('Open a new session? Save current edits first. The current session stays on disk.')))return;
      const result=await api(create?'/api/intake/create':'/api/intake/inspect',{method:'POST',body:JSON.stringify(body)});
      status.textContent=JSON.stringify(result,null,2);
      if(create){sessionStorage.setItem('dbabel-created-bundle',result.bundle);location.hash='token='+encodeURIComponent(result.token);location.reload();}
    }catch(e){status.textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}
  }
  el('inspectDocument').addEventListener('click',()=>intake(false));el('createIntake').addEventListener('click',()=>intake(true));
  el('downloadResults').addEventListener('click',window.exportReviewResults);
  window.renderGlossaryUpload=async(container)=>{
    const heading=node('h2',t('Upload project glossary'));
    const help=node('p',t('Choose the DBabel project glossary CSV or JSON. Approved entries apply only within their language and product scope.'));
    const input=node('input');input.type='file';input.accept='.csv,.json';input.id='glossaryUpload';input.setAttribute('aria-label',t('Project glossary file'));
    const button=node('button',t('Validate and use glossary'),'view-action');button.id='validateGlossary';
    const output=node('div');output.id='glossaryScore';output.setAttribute('role','status');
    function score(r){output.replaceChildren(node('p',r.score===null?t('No applicable approved terms; score unavailable.'):`${t('Terminology compliance')}: ${r.score}% · ${r.passed_checks}/${r.applicable_checks}`),node('p',t('Score = passed applicable term/unit checks ÷ all applicable checks. This measures glossary compliance.')));for(const c of r.checks||[]){if(!c.passed)output.append(node('p',`${c.unit_id} · ${c.source_term} → ${c.accepted.join(' / ')} · ${t('Check required')}`));}}
    button.addEventListener('click',async()=>{button.disabled=true;try{score(await api('/api/glossary',{method:'POST',body:JSON.stringify({file:await filePayload(input)})}));await refreshGate();}catch(e){output.textContent=e.message;}finally{button.disabled=false;}});
    container.append(heading,help,input,button,output);
    try{score(await api('/api/glossary'));}catch(e){output.textContent=e.message;}
  };
  const created=sessionStorage.getItem('dbabel-created-bundle');if(created){window.workbenchNotice(t('Session saved at: ')+created);sessionStorage.removeItem('dbabel-created-bundle');}
};
