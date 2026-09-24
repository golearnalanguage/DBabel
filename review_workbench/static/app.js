(() => {
  'use strict';
  const state={token:'',session:null,units:[],issues:[],evidence:[],decisions:new Map(),selected:null,gate:null,exportAvailable:false,outputName:null,page:0,pageSize:50,reviewFilters:new Set(),issueFilters:new Set(),activeTab:'suggestion',editing:false,theme:'system',selectedUnits:new Set()};
  const el=id=>document.getElementById(id);
  const THEME_KEY='dbabel-review-theme';
  const systemTheme=()=>window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
  function applyTheme(pref){state.theme=['light','dark','system'].includes(pref)?pref:'system';let resolved=state.theme==='system'?systemTheme():state.theme;document.documentElement.dataset.theme=resolved;document.documentElement.dataset.themePref=state.theme;const control=el('themeSelect');if(control)control.value=state.theme;try{localStorage.setItem(THEME_KEY,state.theme);}catch(_){}}
  function initTheme(){let saved='system';try{saved=localStorage.getItem(THEME_KEY)||'system';}catch(_){}applyTheme(saved);if(window.matchMedia){const mq=window.matchMedia('(prefers-color-scheme: dark)');const sync=()=>{if(state.theme==='system')applyTheme('system');};if(mq.addEventListener)mq.addEventListener('change',sync);else if(mq.addListener)mq.addListener(sync);}}
  const completedStatuses=new Set(['ACCEPT_SUGGESTION','KEEP_CURRENT','USER_EDITED','WAIVED']);
  const statusOrder=['UNREVIEWED','ACCEPT_SUGGESTION','KEEP_CURRENT','USER_EDITED','DEFERRED','BLOCKED','WAIVED'];
  const statusLabel={UNREVIEWED:'To Review',ACCEPT_SUGGESTION:'Reviewed · Accepted',KEEP_CURRENT:'Reviewed · Kept',USER_EDITED:'Reviewed · Edited',DEFERRED:'Deferred',BLOCKED:'Blocked',WAIVED:'Reviewed · Waived'};
  const languageNames={zh:'Chinese','zh-CN':'Chinese',en:'English','en-US':'English',ja:'Japanese',ko:'Korean',de:'German',fr:'French',es:'Spanish'};
  function node(tag,text,cls){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n;}
  function svgUse(id){const s=document.createElementNS('http://www.w3.org/2000/svg','svg');const u=document.createElementNS('http://www.w3.org/2000/svg','use');u.setAttribute('href','#'+id);s.append(u);return s;}
  function tokenFromHash(){const m=location.hash.match(/(?:^|[&#])token=([^&]+)/);return m?decodeURIComponent(m[1]):'';}
  async function api(path,options={}){options.headers=Object.assign({'X-DBabel-Session':state.token},options.headers||{});if(options.body&&!options.headers['Content-Type'])options.headers['Content-Type']='application/json';const r=await fetch(path,options);let body=null;try{body=await r.json();}catch(_){body={error:await r.text()};}if(!r.ok)throw new Error(body.error||`HTTP ${r.status}`);return body;}
  function decisionFor(id){return state.decisions.get(id)||{status:'UNREVIEWED',revision:0,reviewer_note:'',waived_issue_fingerprints:[],recheck:{status:'NOT_RUN',error_count:0,warning_count:0,issue_fingerprints:[]}};}
  function issuesFor(id){return state.issues.filter(x=>x.unit_id===id);}
  function evidenceFor(u){const wanted=new Set(u.evidence_refs||[]);for(const i of issuesFor(u.id))for(const x of (i.evidence_refs||[]))wanted.add(x);return state.evidence.filter(x=>wanted.has(x.id));}
  function unitIndex(id){return Math.max(0,state.units.findIndex(x=>x.id===id));}
  function reviewBucket(u){return completedStatuses.has(decisionFor(u.id).status)?'REVIEWED':'TO_REVIEW';}
  function reviewMatches(u,key){if(key==='WITH_ISSUES')return issuesFor(u.id).length>0;if(key==='REVIEWED')return completedStatuses.has(decisionFor(u.id).status);if(key==='TO_REVIEW')return !completedStatuses.has(decisionFor(u.id).status);return true;}
  function friendlyStatus(u){const d=decisionFor(u.id);if(d.status==='BLOCKED')return ['Blocked','blocked'];if(d.status==='WAIVED')return ['Reviewed','waived'];return completedStatuses.has(d.status)?['Reviewed','reviewed']:['To Review','to-review'];}
  function issueClass(i){const l=(i.label||i.check_id||'').toLowerCase();if(i.severity==='ERROR')return 'error';if(l.includes('number_unit'))return 'number_unit';if(l.includes('evidence'))return 'evidence';if(i.severity==='WARNING')return 'warning';if(i.classification==='POTENTIAL_ISSUE')return 'default';return 'term';}
  const issueAliases={NUMBER_UNIT_INTEGRITY:'NUMBER_UNIT',PLACEHOLDER_INTEGRITY:'PLACEHOLDER',PATH_INTEGRITY:'PATH',VERSION_INTEGRITY:'VERSION',URL_INTEGRITY:'URL',CLI_OPTION_INTEGRITY:'CLI_OPTION',ENV_VAR_INTEGRITY:'ENV_VAR',NUMBER_INTEGRITY:'NUMBER',PROTECTED_LITERAL:'PROTECTED',PREFERRED_TERM:'PREFERRED_TERM',EVIDENCE_CONFLICT:'EVIDENCE_CONFLICT',TECHNICAL_CLAIM:'TECH_CLAIM'};
  function issueDisplay(raw){return issueAliases[raw]||raw;}
  const issueFilterDefs=[['TERM_GROUP','TERM','blue'],['NUMBER_UNIT_INTEGRITY','NUMBER_UNIT','orange'],['EVIDENCE_GROUP','EVIDENCE','purple'],['ERROR','ERROR','red'],['WARNING','WARNING','yellow'],['PATH_INTEGRITY','PATH','blue'],['PLACEHOLDER_INTEGRITY','PLACEHOLDER','blue'],['VERSION_INTEGRITY','VERSION','blue']];
  function issueFilterMatch(u,key){const iss=issuesFor(u.id);if(key==='ERROR'||key==='WARNING')return iss.some(i=>i.severity===key);if(key==='EVIDENCE_GROUP')return evidenceFor(u).length>0||iss.some(i=>(i.label||i.check_id||'').includes('EVIDENCE'));if(key==='TERM_GROUP')return iss.some(i=>['TERM','PREFERRED_TERM'].includes(i.label||i.check_id))||(u.labels||[]).some(x=>['TERM','PREFERRED_TERM'].includes(x));return iss.some(i=>(i.label||i.check_id||i.severity)===key);}
  function pct(n,total){return total?` (${(n*100/total).toFixed(1)}%)`:'';}
  function searchable(u){return [u.id,u.location,u.source,u.current_target,u.suggested_target||'',...(u.labels||[]),...issuesFor(u.id).flatMap(x=>[x.label||'',x.check_id||'',x.message||'',x.classification||''])].join('\n').toLowerCase();}
  function filterUnits(){const q=el('searchBox').value.trim().toLowerCase(),quick=el('quickFilter').value;let items=state.units.filter(u=>{if(q&&!searchable(u).includes(q))return false;if(quick!=='ALL'&&!reviewMatches(u,quick))return false;if(state.reviewFilters.size&&![...state.reviewFilters].some(k=>reviewMatches(u,k)))return false;if(state.issueFilters.size&&![...state.issueFilters].some(k=>issueFilterMatch(u,k)))return false;return true;});const sort=el('sortSelect').value;if(sort==='STATUS')items=items.slice().sort((a,b)=>decisionFor(a.id).status.localeCompare(decisionFor(b.id).status)||unitIndex(a.id)-unitIndex(b.id));if(sort==='ISSUES')items=items.slice().sort((a,b)=>issuesFor(b.id).length-issuesFor(a.id).length||unitIndex(a.id)-unitIndex(b.id));return items;}
  function metricValue(id,n,total,showPct=true){const root=el(id);root.replaceChildren(document.createTextNode(n.toLocaleString()));if(showPct&&total){const p=node('span',`(${(n*100/total).toFixed(1)}%)`,'metric-pct');root.append(p);}}
  function renderMetrics(){const total=state.units.length,reviewed=state.units.filter(u=>reviewMatches(u,'REVIEWED')).length,withIssues=state.units.filter(u=>reviewMatches(u,'WITH_ISSUES')).length,pending=state.units.filter(u=>reviewMatches(u,'TO_REVIEW')).length;metricValue('metricTotal',total,total,false);metricValue('metricReviewed',reviewed,total);metricValue('metricIssues',withIssues,total);metricValue('metricPending',pending,total);el('countToReview').textContent=pending;el('countReviewed').textContent=reviewed;el('countWithIssues').textContent=withIssues;}
  function renderIssueFilters(){const root=el('issueFilterList');root.replaceChildren();for(const [key,label,color] of issueFilterDefs){const count=state.units.filter(u=>issueFilterMatch(u,key)).length;if(!count)continue;const row=node('label',undefined,'filter-row'),input=node('input');input.type='checkbox';input.checked=state.issueFilters.has(key);input.addEventListener('change',()=>{input.checked?state.issueFilters.add(key):state.issueFilters.delete(key);state.selectedUnits.clear();state.page=0;renderTable();});const dot=node('span',undefined,'dot '+color),labelNode=node('span',label);labelNode.title=key.endsWith('_GROUP')?label:key;row.append(input,dot,labelNode,node('b',count));root.append(row);}}
  function currentPageUnits(){
    const items=filterUnits();
    const maxPage=Math.max(
      0,
      Math.ceil(items.length/state.pageSize)-1
    );
    state.page=Math.min(state.page,maxPage);
    const start=state.page*state.pageSize;
    const end=Math.min(
      items.length,
      start+state.pageSize
    );
    return items.slice(start,end);
  }

  function syncSelectionUi(pageUnits){
    const pageIds=pageUnits.map(u=>u.id);
    const selectedOnPage=pageIds.filter(
      id=>state.selectedUnits.has(id)
    ).length;

    const selectPage=el('selectPage');

    selectPage.checked=
      pageIds.length>0 &&
      selectedOnPage===pageIds.length;

    selectPage.indeterminate=
      selectedOnPage>0 &&
      selectedOnPage<pageIds.length;

    const count=state.selectedUnits.size;

    el('bulkActions').hidden=count===0;
    el('bulkCount').textContent=`${count} selected`;
  }

  function renderTable(){
    const items=filterUnits();
    const maxPage=Math.max(
      0,
      Math.ceil(items.length/state.pageSize)-1
    );

    state.page=Math.min(state.page,maxPage);

    const start=state.page*state.pageSize;
    const end=Math.min(
      items.length,
      start+state.pageSize
    );

    const pageUnits=items.slice(start,end);

    el('pageInfo').textContent=
      items.length
        ? `${start+1}–${end} of ${items.length.toLocaleString()}`
        : '0–0 of 0';

    el('pagePrev').disabled=state.page===0;
    el('pageNext').disabled=state.page>=maxPage;

    const body=el('segmentRows');
    body.replaceChildren();

    for(const u of pageUnits){
      const tr=node(
        'tr',
        undefined,
        u.id===state.selected?'active':''
      );

      tr.dataset.id=u.id;

      if(state.selectedUnits.has(u.id)){
        tr.classList.add('batch-selected');
      }

      const check=node(
        'td',
        undefined,
        'check-col'
      );

      const cb=node(
        'input',
        undefined,
        'row-checkbox'
      );

      cb.type='checkbox';
      cb.checked=state.selectedUnits.has(u.id);
      cb.setAttribute(
        'aria-label',
        `Select segment ${unitIndex(u.id)+1}`
      );

      cb.addEventListener(
        'click',
        e=>e.stopPropagation()
      );

      cb.addEventListener(
        'change',
        ()=>{
          if(cb.checked){
            state.selectedUnits.add(u.id);
          }else{
            state.selectedUnits.delete(u.id);
          }

          tr.classList.toggle(
            'batch-selected',
            cb.checked
          );

          syncSelectionUi(pageUnits);
        }
      );

      check.append(cb);

      const num=node(
        'td',
        String(unitIndex(u.id)+1),
        'num-col'
      );

      const src=node('td');
      src.append(
        node(
          'div',
          u.source,
          'cell-text'
        )
      );

      const tgt=node('td');
      tgt.append(
        node(
          'div',
          decisionFor(u.id).approved_target
            ??u.current_target,
          'cell-text'
        )
      );

      const [slabel,sclass]=friendlyStatus(u);

      const st=node('td');
      st.append(
        node(
          'span',
          slabel,
          'status-pill '+sclass
        )
      );

      const issues=node('td');

      for(const i of issuesFor(u.id).slice(0,3)){
        const raw=
          i.label||
          i.check_id||
          i.severity;

        const txt=issueDisplay(raw);

        const chip=node(
          'span',
          txt,
          'issue-chip '+issueClass(i)
        );

        chip.title=raw;
        issues.append(chip);
      }

      if(
        evidenceFor(u).length &&
        !issuesFor(u.id).some(
          i=>(i.label||i.check_id||'')
            .includes('EVIDENCE')
        )
      ){
        const ev=node(
          'span',
          'EVIDENCE',
          'issue-chip evidence'
        );

        ev.title='Linked evidence';
        issues.append(ev);
      }

      const comment=node(
        'td',
        undefined,
        'comment-col'
      );

      comment.append(
        svgUse('i-comment')
      );

      tr.append(
        check,
        num,
        src,
        tgt,
        st,
        issues,
        comment
      );

      tr.addEventListener(
        'click',
        ()=>selectUnit(u.id)
      );

      body.append(tr);
    }

    syncSelectionUi(pageUnits);
    renderMetrics();
  }

  function selectUnit(id){state.selected=id;state.editing=false;const u=state.units.find(x=>x.id===id);if(!u)return;const d=decisionFor(id),idx=unitIndex(id);el('segmentCounter').textContent=`Segment ${idx+1} of ${state.units.length.toLocaleString()}`;el('sourceText').textContent=u.source;el('targetText').value=d.approved_target!==undefined?d.approved_target:u.current_target;el('targetText').readOnly=true;el('targetText').classList.remove('editing');el('editToggle').replaceChildren();el('editToggle').append(svgUse('i-edit'),document.createTextNode('Edit'));el('reviewerNote').value=d.reviewer_note||'';el('waiverReason').value=d.waiver_reason||'';el('waiverField').classList.add('hidden');el('decisionSelect').value=d.status;const iss=issuesFor(id);const chips=el('issueChips');chips.replaceChildren();for(const i of iss.slice(0,5)){const raw=i.label||i.check_id||i.severity,txt=issueDisplay(raw);const chip=node('span',txt,'issue-chip '+issueClass(i));chip.title=raw;chips.append(chip);}if(evidenceFor(u).length&&!iss.some(i=>(i.label||i.check_id||'').includes('EVIDENCE'))){const ev=node('span','EVIDENCE','issue-chip evidence');ev.title='Linked evidence';chips.append(ev);}if(!iss.length&&!evidenceFor(u).length)chips.append(node('span','CLEAN','issue-chip default'));el('evidenceTabCount').textContent=`(${evidenceFor(u).length})`;const terms=[...(u.labels||[]),...iss.map(i=>i.label||i.check_id||'')].filter(Boolean);el('termTabCount').textContent=`(${new Set(terms).size})`;renderSuggestion(u);renderEvidence(u);renderTerminology(u);setTab('suggestion');renderTable();}
  function renderSuggestion(u){const iss=issuesFor(u.id);el('suggestionBox').textContent=u.suggested_target||'No replacement suggestion. Review the current target and supporting issues.';const reasons=iss.map(i=>i.message).filter(Boolean);el('reasonBox').textContent=reasons.length?reasons.slice(0,3).join(' · '):'No deterministic or semantic issue is attached to this unit.';renderSuggestionEvidence(u);}
  function renderSuggestionEvidence(u){const evs=evidenceFor(u),root=el('suggestionEvidenceList');root.replaceChildren();el('suggestionEvidenceCount').textContent=evs.length?`View all (${evs.length})`:'No linked evidence';for(const e of evs.slice(0,1)){const c=node('div',undefined,'evidence-card');c.append(node('div',e.source_title||e.id,'evidence-title'));c.append(node('div',e.support_note||'','evidence-note'));c.append(node('div',e.locator||'','evidence-locator'));root.append(c);}if(!evs.length)root.append(node('div','No evidence record is linked to this unit.','evidence-card'));}

  function renderEvidence(u){const evs=evidenceFor(u),root=el('evidenceList');root.replaceChildren();el('evidenceCountText').textContent=evs.length?`View all (${evs.length})`:'No linked evidence';for(const e of evs){const c=node('div',undefined,'evidence-card');c.append(node('div',e.source_title||e.id,'evidence-title'));c.append(node('div',e.support_note||'','evidence-note'));c.append(node('div',e.locator||'','evidence-locator'));root.append(c);}if(!evs.length)root.append(node('div','No evidence record is linked to this unit.','evidence-card'));}
  function renderTerminology(u){const root=el('terminologyList');root.replaceChildren();const labels=new Set([...(u.labels||[]),...issuesFor(u.id).map(i=>i.label||i.check_id||i.classification).filter(Boolean)]);for(const t of labels){const c=node('div',undefined,'term-card');const tc=node('span',issueDisplay(t),'issue-chip term');tc.title=t;c.append(tc);c.append(node('span','DBabel review label'));root.append(c);}if(!labels.size)root.append(node('div','No terminology labels for this unit.','evidence-card'));}
  function setTab(name){state.activeTab=name;for(const b of document.querySelectorAll('.tabs button'))b.classList.toggle('active',b.dataset.tab===name);for(const p of document.querySelectorAll('.tab-panel'))p.classList.remove('active');const map={suggestion:'tabSuggestion',evidence:'tabEvidence',terminology:'tabTerminology'};el(map[name]).classList.add('active');}
  function editTarget(){if(!state.selected)return;state.editing=!state.editing;el('targetText').readOnly=!state.editing;el('targetText').classList.toggle('editing',state.editing);if(state.editing){el('targetText').focus();el('editToggle').textContent='Editing';el('editAction').textContent='Use Edit';}else{el('editToggle').replaceChildren();el('editToggle').append(svgUse('i-edit'),document.createTextNode('Edit'));el('editAction').replaceChildren();el('editAction').append(svgUse('i-edit'),document.createTextNode('Edit'));}}
  async function setDecision(status){const u=state.units.find(x=>x.id===state.selected);if(!u)return;const body={status,reviewer_note:el('reviewerNote').value};if(status==='USER_EDITED'||status==='WAIVED')body.approved_target=el('targetText').value;if(status==='KEEP_CURRENT')body.approved_target=u.current_target;if(status==='ACCEPT_SUGGESTION')body.approved_target=u.suggested_target||el('targetText').value;if(status==='WAIVED'){body.waiver_reason=el('waiverReason').value.trim();if(!body.waiver_reason){el('waiverField').classList.remove('hidden');el('waiverReason').focus();return;}body.waived_issue_fingerprints=issuesFor(u.id).filter(x=>x.severity==='ERROR').map(x=>x.fingerprint);}try{const saved=await api(`/api/decisions/${encodeURIComponent(u.id)}`,{method:'PUT',body:JSON.stringify(body)});state.decisions.set(u.id,saved.decision);if(saved.recheck_issues){state.issues=state.issues.filter(x=>!(x.unit_id===u.id&&x.kind==='DETERMINISTIC'));state.issues.push(...saved.recheck_issues);}renderIssueFilters();selectUnit(u.id);await refreshGate();}catch(err){alert(err.message);}}
  async function bulkDecision(status){
    const ids=[...state.selectedUnits];

    if(!ids.length){
      return;
    }

    const action=
      status==='KEEP_CURRENT'
        ? 'Keep Current'
        : 'Defer';

    if(
      !window.confirm(
        `${action} for ${ids.length} selected segment(s)?`
      )
    ){
      return;
    }

    try{
      const response=await api(
        '/api/decisions/bulk',
        {
          method:'POST',
          body:JSON.stringify({
            status,
            unit_ids:ids
          })
        }
      );

      for(
        const result
        of (response.results||[])
      ){
        const saved=result.decision;

        state.decisions.set(
          saved.unit_id,
          saved
        );

        if(result.recheck_issues){
          state.issues=
            state.issues.filter(
              x=>!(
                x.unit_id===saved.unit_id &&
                x.kind==='DETERMINISTIC'
              )
            );

          state.issues.push(
            ...result.recheck_issues
          );
        }
      }

      state.selectedUnits.clear();

      renderIssueFilters();
      renderTable();

      if(state.selected){
        selectUnit(state.selected);
      }

      await refreshGate();

    }catch(err){
      alert(err.message);
    }
  }

  async function refreshGate(){try{state.gate=await api('/api/export-gate',{method:'POST',body:'{}'});const blockers=state.gate.blockers||[];el('gateStatus').textContent=state.gate.status+(blockers.length?'\n'+blockers.slice(0,5).join('\n'):'');if(!state.exportAvailable){el('exportButton').disabled=true;el('exportButton').querySelector('span').textContent='Review Only';el('exportHint').textContent='Review-only mode. Start the Workbench with --original and --output to enable native DOCX export.';return;}el('exportButton').disabled=state.gate.status!=='AUTHORIZED';if(state.gate.status==='AUTHORIZED'){el('exportHint').textContent='Review complete. Native export is ready'+(state.outputName?': '+state.outputName:'.');el('exportButton').querySelector('span').textContent='Export Translation...';}else{el('exportHint').textContent=(state.outputName?'Output: '+state.outputName+' · ':'')+'Complete all required reviews to enable export.';el('exportButton').querySelector('span').textContent='Export Translation...';}}catch(err){el('gateStatus').textContent=err.message;el('exportButton').disabled=true;}}
  async function doExport(){try{const result=await api('/api/export',{method:'POST',body:'{}'});el('gateStatus').textContent=JSON.stringify(result,null,2);if(result.status==='VERIFIED')alert('Export verified: '+result.output.path);}catch(err){alert(err.message);}}
  function moveUnit(delta){if(!state.units.length)return;const idx=unitIndex(state.selected);const next=Math.max(0,Math.min(state.units.length-1,idx+delta));selectUnit(state.units[next].id);}
  async function copyText(id){try{await navigator.clipboard.writeText(el(id).textContent||'');}catch(_){}}
  function setupControls(){el('themeSelect').addEventListener('change',()=>applyTheme(el('themeSelect').value));for(const s of statusOrder){const o=new Option(statusLabel[s],s);el('decisionSelect').append(o);}el('decisionSelect').addEventListener('change',()=>{const s=el('decisionSelect').value;if(s==='UNREVIEWED')return; if(s==='WAIVED'){el('waiverField').classList.remove('hidden');return;}setDecision(s);});el('searchBox').addEventListener('input',()=>{state.selectedUnits.clear();state.page=0;renderTable();});for(const id of ['quickFilter','sortSelect'])el(id).addEventListener('change',()=>{state.selectedUnits.clear();state.page=0;renderTable();});for(const cb of document.querySelectorAll('[data-review-filter]'))cb.addEventListener('change',()=>{const k=cb.dataset.reviewFilter;cb.checked?state.reviewFilters.add(k):state.reviewFilters.delete(k);state.selectedUnits.clear();state.page=0;renderTable();});el('clearFilters').addEventListener('click',()=>{state.reviewFilters.clear();state.issueFilters.clear();for(const cb of document.querySelectorAll('.filters-panel input[type=checkbox]'))cb.checked=false;el('quickFilter').value='ALL';el('searchBox').value='';state.page=0;renderIssueFilters();renderTable();});el('pagePrev').addEventListener('click',()=>{if(state.page>0){state.selectedUnits.clear();state.page--;renderTable();}});el('pageNext').addEventListener('click',()=>{state.selectedUnits.clear();state.page++;renderTable();});el('unitPrev').addEventListener('click',()=>moveUnit(-1));el('unitNext').addEventListener('click',()=>moveUnit(1));for(const b of document.querySelectorAll('.tabs button'))b.addEventListener('click',()=>setTab(b.dataset.tab));el('editToggle').addEventListener('click',editTarget);el('editAction').addEventListener('click',()=>{if(!state.editing){editTarget();return;}setDecision('USER_EDITED');});el('acceptButton').addEventListener('click',()=>setDecision('ACCEPT_SUGGESTION'));el('keepButton').addEventListener('click',()=>setDecision('KEEP_CURRENT'));el('deferButton').addEventListener('click',()=>setDecision('DEFERRED'));el('blockButton').addEventListener('click',()=>setDecision('BLOCKED'));el('waiveButton').addEventListener('click',()=>{el('waiverField').classList.remove('hidden');el('waiverReason').focus();});el('confirmWaiver').addEventListener('click',()=>setDecision('WAIVED'));for(const b of document.querySelectorAll('[data-copy]'))b.addEventListener('click',()=>copyText(b.dataset.copy));el('exportButton').addEventListener('click',doExport);el('selectPage').addEventListener('change',()=>{for(const u of currentPageUnits()){if(el('selectPage').checked){state.selectedUnits.add(u.id);}else{state.selectedUnits.delete(u.id);}}renderTable();});el('bulkKeep').addEventListener('click',()=>bulkDecision('KEEP_CURRENT'));el('bulkDefer').addEventListener('click',()=>bulkDecision('DEFERRED'));el('bulkClear').addEventListener('click',()=>{state.selectedUnits.clear();renderTable();});}
  function initHeader(){const u=state.units[0]||{},s=languageNames[u.source_language]||u.source_language||'Source',t=languageNames[u.target_language]||u.target_language||'Target';el('documentTitle').textContent=state.session.title||state.session.original.filename||'DBabel Review';el('documentMeta').textContent=`Technical Documentation   |   ${s} → ${t}   |   ${state.session.dbabel_version||'v1.5'}`;el('sourceLanguage').textContent=`(${s})`;el('targetLanguage').textContent=`(${t})`;el('sourceLabel').textContent=`Source (${s})`;el('targetLabel').textContent=`Target (${t})`;}
  async function boot(){initTheme();state.token=tokenFromHash();if(!state.token){document.body.textContent='Missing DBabel session token.';return;}const data=await api('/api/bootstrap');state.session=data.session;state.units=data.units;state.issues=data.issues;state.evidence=data.evidence;for(const d of data.decisions)state.decisions.set(d.unit_id,d);state.exportAvailable=Boolean(data.export_available);state.outputName=data.output_name||null;setupControls();initHeader();renderIssueFilters();renderMetrics();renderTable();if(state.units.length)selectUnit(state.units[0].id);await refreshGate();}
  boot().catch(err=>{document.body.textContent='DBabel Workbench failed: '+err.message;});
})();
