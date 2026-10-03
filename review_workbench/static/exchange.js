/* Document uploads stay on the local authenticated Workbench server. */
window.installExchange = function({api,state,el,node,refreshGate}) {
  const t=window.dbabelI18n.t;
  function download(result){const url=URL.createObjectURL(new Blob([result.content],{type:result.content_type+';charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=result.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  window.exportReviewResults=async()=>{try{download(await api('/api/results',{method:'POST',body:JSON.stringify({format:el('resultFormat').value})}));}catch(e){window.workbenchNotice(e.message);}};
  async function filePayload(input){const f=input.files[0];if(!f)throw Error(t('Select a file first.'));if(f.size>16*1024*1024)throw Error(t('Maximum file size: 16 MiB.'));const bytes=new Uint8Array(await f.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return {name:f.name,content_base64:btoa(binary)};}
  const panel=el('exchangePanel');
  const selectedTargets=new Set();
  const chips=el('intakeSelectedTargets');
  function renderTargets(){chips.replaceChildren();for(const language of selectedTargets){const chip=document.createElement('button');chip.type='button';chip.className='intake-target-chip';chip.textContent=language+' ×';chip.setAttribute('aria-label',t('Remove target language')+' '+language);chip.addEventListener('click',()=>{selectedTargets.delete(language);renderTargets();});chips.append(chip);}}
  el('addIntakeTarget').addEventListener('click',()=>{selectedTargets.add(el('intakeTargetLanguages').value);renderTargets();});
  el('openIntake').addEventListener('click',()=>{panel.hidden=!panel.hidden;if(!panel.hidden)panel.scrollIntoView({block:'start'});});
  el('closeIntake').addEventListener('click',()=>panel.hidden=true);
  const status=el('intakeStatus');
  async function intake(create){
    const buttons=[el('inspectDocument'),el('createIntake')];buttons.forEach(b=>b.disabled=true);
    try{
      const source=await filePayload(el('sourceUpload'));
      const body={source,source_language:el('intakeSourceLanguage').value,target_languages:selectedTargets.size?[...selectedTargets]:[el('intakeTargetLanguages').value],alignment_confirmed:el('confirmAlignment').checked};
      if(create&&el('targetUpload').files.length)body.target=await filePayload(el('targetUpload'));
      if(create&&!confirm(t('Open a new session? Save current edits first. The current session stays on disk.')))return;
      const result=await api(create?'/api/intake/create':'/api/intake/inspect',{method:'POST',body:JSON.stringify(body)});
      status.textContent=JSON.stringify(result,null,2);
      if(create){sessionStorage.setItem('dbabel-created-bundle',result.bundle);location.hash='token='+encodeURIComponent(result.token);location.reload();}
    }catch(e){status.textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}
  }
  el('inspectDocument').addEventListener('click',()=>intake(false));el('createIntake').addEventListener('click',()=>intake(true));
  el('downloadResults').addEventListener('click',window.exportReviewResults);
  window.renderGeneralTerms=async(container)=>{
    container.append(node('p',t('Cross-vendor reference suggestions for future Chinese-to-English AI translations. Off by default; never project-approved.')));
    const label=node('label');
    const toggle=node('input');toggle.type='checkbox';toggle.id='generalTermsEnabled';toggle.disabled=true;
    label.append(toggle,document.createTextNode(' '+t('Use built-in terms as AI reference')));
    const status=node('p',t('Loading built-in terms…'));status.id='generalTermsStatus';status.setAttribute('role','status');
    const list=node('ul');list.id='generalTermsList';
    container.append(label,status,list);
    try{
      const data=await api('/api/general-terms');
      toggle.checked=data.enabled===true;
      status.textContent=t('Applies to future translations only. Project-approved terms take priority.');
      for(const item of data.entries||[])list.append(node('li',`${item.zh} → ${item.en}`));
      toggle.addEventListener('change',async()=>{
        const chosen=toggle.checked;toggle.disabled=true;
        try{
          const result=await api('/api/general-terms',{method:'POST',body:JSON.stringify({enabled:chosen})});
          toggle.checked=result.enabled===true;
          status.textContent=t(toggle.checked?'Built-in reference enabled for future translations.':'Built-in reference disabled for future translations.');
        }catch(error){toggle.checked=!chosen;status.textContent=error.message;}
        finally{toggle.disabled=false;}
      });
      toggle.disabled=false;
    }catch(error){toggle.disabled=true;status.textContent=error.message;}
  };
  window.renderTranslationMemory=async(container)=>{
    container.append(node('p',t('Human-approved exact matches are reused locally as review suggestions. Rejected wording is blocked. No API tokens are used for lookup.')));
    const status=node('p',t('Loading translation memory…'));status.setAttribute('role','status');
    const exportButton=node('button',t('Export translation memory'),'view-action');exportButton.type='button';
    exportButton.addEventListener('click',async()=>{
      exportButton.disabled=true;
      try{const data=await api('/api/translation-memory/export');download({filename:data.filename,content:JSON.stringify({format_version:'1.0',entries:data.entries},null,2)+'\n',content_type:'application/json'});}
      catch(error){status.textContent=error.message;}finally{exportButton.disabled=false;}
    });
    const list=node('ul');container.append(exportButton,status,list);
    async function refresh(){
      try{
        const data=await api('/api/translation-memory');
        status.textContent=`${t('Saved memory entries')}: ${data.count}`;
        list.replaceChildren();
        for(const item of data.entries||[]){
          const row=node('li');
          const label=item.kind==='REJECTED'?t('Rejected'):t('Preferred');
          row.append(node('span',`${label} · ${item.source_language} → ${item.target_language} · ${item.source} → ${item.target} `));
          const edit=node('button',t('Edit'),'view-action');edit.type='button';
          const remove=node('button',t('Delete'),'view-action');remove.type='button';
          edit.addEventListener('click',()=>{
            const input=node('input');input.type='text';input.value=item.target;input.maxLength=20000;
            input.setAttribute('aria-label',t('Translation memory target'));
            const save=node('button',t('Save'),'view-action');save.type='button';
            const cancel=node('button',t('Cancel'),'view-action');cancel.type='button';
            row.replaceChildren(node('span',`${label} · ${item.source} → `),input,save,cancel);
            cancel.addEventListener('click',refresh);
            save.addEventListener('click',async()=>{
              save.disabled=true;
              try{await api('/api/translation-memory/edit',{method:'POST',body:JSON.stringify({id:item.id,target:input.value})});await refresh();}
              catch(error){status.textContent=error.message;save.disabled=false;}
            });
            input.focus();
          });
          remove.addEventListener('click',async()=>{
            if(!confirm(t('Delete this translation memory entry?')))return;
            remove.disabled=true;
            try{await api('/api/translation-memory/delete',{method:'POST',body:JSON.stringify({id:item.id})});await refresh();}
            catch(error){status.textContent=error.message;remove.disabled=false;}
          });
          row.append(edit,remove);list.append(row);
        }
      }catch(error){status.textContent=error.message;}
    }
    await refresh();
  };
  window.renderGlossaryUpload=async(container)=>{
    const heading=node('h2',t('Upload project glossary'));
    const help=node('p',t('Choose the DBabel project glossary CSV or JSON. Approved entries apply only within their language and product scope.'));
    const input=node('input');input.type='file';input.accept='.csv,.json';input.id='glossaryUpload';input.setAttribute('aria-label',t('Project glossary file'));
    const button=node('button',t('Validate and use glossary'),'view-action');button.id='validateGlossary';
    const output=node('div');output.id='glossaryScore';output.setAttribute('role','status');
    function score(r){output.replaceChildren(node('p',r.score===null?t('No applicable approved terms; score unavailable.'):`${t('Terminology compliance')}: ${r.score}% · ${r.passed_checks}/${r.applicable_checks}`),node('p',t('Score = passed applicable term/unit checks ÷ all applicable checks. This measures glossary compliance.')));for(const c of r.checks||[]){if(!c.passed)output.append(node('p',`${c.unit_id} · ${c.source_term} → ${c.accepted.join(' / ')} · ${t('Check required')}`));}}
    button.addEventListener('click',async()=>{button.disabled=true;try{score(await api('/api/glossary',{method:'POST',body:JSON.stringify({file:await filePayload(input)})}));await refreshGate();}catch(e){output.textContent=e.message;}finally{button.disabled=false;}});
    const template=node('button',t('Download terminology recognition template'),'view-action');
    template.id='downloadGlossaryTemplate';template.type='button';
    template.addEventListener('click',async()=>{
      template.disabled=true;
      try{
        const result=await api('/api/glossary/template');
        download({filename:result.filename,content:'\ufeff'+result.content,content_type:'text/csv'});
      }catch(error){window.workbenchNotice(error.message);}
      finally{template.disabled=false;}
    });
    container.append(heading,help,node('p',t('Fill source and target terms, language pair, scope and approval. Template rows start as USER_REVIEW and do not enforce QA until you approve them.')),template,input,button,output);
    try{score(await api('/api/glossary'));}catch(e){output.textContent=e.message;}
  };
  const created=sessionStorage.getItem('dbabel-created-bundle');if(created){window.workbenchNotice(t('Session saved at: ')+created);sessionStorage.removeItem('dbabel-created-bundle');}
};
