/* LexGuard — progressive, multi-page UI. No client-side routing or synthetic response substitution. */
'use strict';
const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const clean = x => x == null ? '' : String(x);
const el = (tag, cls='', text) => { const node = document.createElement(tag); if (cls) node.className=cls; if (text!==undefined) node.textContent=clean(text); return node; };
const add = (parent,...nodes) => { nodes.filter(Boolean).forEach(n=>parent.append(n));return parent;};
const currencyFree = n => Number.isFinite(Number(n)) ? Number(n).toLocaleString(undefined,{maximumFractionDigits:1}) : '—';
const safeState = s => ['complete','success','ready'].includes(s) ? 'complete' : 'partial';
const SUMMARY_KEY='lexguard-latest-report-v1';
const exampleContract = `MASTER SERVICES AGREEMENT — SYNTHETIC EXAMPLE\n\nThis example agreement is entered into by Alpha Corp (Customer) and Vendor Four GmbH (Supplier). It contains fictional entities for interface testing.\n\n1. Services. Supplier shall implement the inventory platform and deliver agreed milestones, subject to acceptance testing within ten business days.\n\n2. Term. The agreement runs for two years and renews automatically for one year unless a party gives sixty days written notice.\n\n3. Fees. Customer shall pay undisputed invoices within thirty days of receipt. Extra work requires written approval.\n\n4. Confidentiality. Each party must protect confidential information and restrict access. The test notices contact is qa-notices@example.org.\n\n5. Liability. The supplier indemnifies the customer against third-party intellectual property claims. Total liability is limited to the preceding twelve months of fees, except for fraud or deliberate misconduct.\n\n6. Governing law. Indian law governs this agreement. The courts at Bengaluru have exclusive jurisdiction.`;

function themeInit(){
  $$('[data-theme-toggle]').forEach(btn=>btn.addEventListener('click',()=>{
    const next=document.documentElement.dataset.theme==='dark'?'light':'dark';
    document.documentElement.dataset.theme=next;
    try{localStorage.setItem('lexguard-theme',next)}catch{}
  }));
  const m=$('[data-menu-toggle]'),nav=$('#mobile-nav');
  if(m&&nav){m.addEventListener('click',()=>{const open=m.getAttribute('aria-expanded')==='true';m.setAttribute('aria-expanded',String(!open));nav.hidden=open;});nav.addEventListener('click',e=>{if(e.target.closest('a')){nav.hidden=true;m.setAttribute('aria-expanded','false')}});}
}
function notify(msg){const toast=$('#toast');if(!toast)return;toast.textContent=msg;toast.hidden=false;clearTimeout(notify.timer);notify.timer=setTimeout(()=>toast.hidden=true,3800)}
function showError(selector,message){const node=typeof selector==='string'?$(selector):selector;if(!node)return;node.textContent=message;node.hidden=false;node.scrollIntoView({behavior:'smooth',block:'center'});}
function clearError(selector){const node=typeof selector==='string'?$(selector):selector;if(node){node.hidden=true;node.textContent=''}}
function parsedError(data,status){
  if(Array.isArray(data?.detail)){return data.detail.map(d=>`${(d.loc||[]).slice(1).join(' → ') || 'Input'}: ${d.msg}`).join(' · ')}
  if(typeof data?.detail==='string')return data.detail;
  return `Request failed (${status}). Check API readiness and try again.`;
}
async function postJson(url,body){
  let response;
  try{response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
  catch{throw new Error('Could not contact the LexGuard server. Make sure the backend is running.');}
  const text=await response.text();let data;
  try{data=JSON.parse(text)}catch{data={detail:text||'Invalid server response'}}
  if(!response.ok)throw new Error(parsedError(data,response.status));
  return data;
}
async function systemStatus(){
  try{
    const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('offline');const d=await r.json();
    const ready=['coi','cr','cl','le'].filter(k=>d[k]==='ready').length;
    $$('.live-chip').forEach(n=>{n.classList.toggle('is-ready',ready===4);n.classList.toggle('is-partial',ready<4);});
    $$('[data-system-label]').forEach(n=>n.textContent=ready===4?'All systems ready':`${ready} of 4 agents ready`);
    const labels={ready:'Ready',unavailable:'Unavailable',missing_model:'Model missing',degraded:'Degraded',groq_fallback:'Fallback'};
    $$('[data-agent-status]').forEach(n=>{let s=d[n.dataset.agentStatus];n.textContent=labels[s]||clean(s||'Unknown').replace(/_/g,' ');n.style.color=s==='ready'?'var(--mint)':'var(--amber)';});
  }catch{
    $$('.live-chip').forEach(n=>n.classList.add('is-partial'));
    $$('[data-system-label]').forEach(n=>n.textContent='API unavailable');
    $$('[data-agent-status]').forEach(n=>n.textContent='Not connected');
  }
}
function filesFromText(input){return clean(input||'').split(',').map(s=>s.trim()).filter(Boolean)}
function fieldValue(form,name){return form.elements.namedItem(name)?.value?.trim()||''}
function numeric(form,name){return Number(fieldValue(form,name))}
function modelFeatures(form){return {
  deal_size:numeric(form,'deal_size'),liability_cap:numeric(form,'liability_cap'),auto_renewal:numeric(form,'auto_renewal'),
  jurisdiction_risk:numeric(form,'jurisdiction_risk'),indemnification_clause:numeric(form,'indemnification_clause'),
  dispute_history:numeric(form,'dispute_history'),governing_law_clarity:numeric(form,'governing_law_clarity')
};}
function validateFields(node){
  for(const control of $$('input,textarea,select',node)){
    if(control.type==='file'||control.type==='checkbox'&&control.id!=='acknowledge')continue;
    if(control.required && !clean(control.value).trim())return `${control.closest('.field')?.querySelector('span')?.textContent?.replace('*','').trim()||'A required field'} is required.`;
    if(!control.checkValidity())return control.validationMessage || 'Please check the highlighted field.';
  }
  const entities=$('[name="contract_entities"]',node);
  if(entities&&filesFromText(entities.value).length>13)return 'Please enter no more than 13 additional entities.';
  return '';
}
let fileLoading=false;
function setupExtraction(fileId,textareaSelector){
  const file=$(fileId),area=$(textareaSelector),drop=$('#dropzone'),status=$('#upload-status');
  if(!file||!area)return;
  async function extract(f){
    if(!f)return;
    if(!/\.(txt|pdf|docx)$/i.test(f.name)){status.textContent='Use a TXT, PDF, or DOCX file.';return}
    if(f.size>5*1024*1024){status.textContent='This file exceeds the 5 MB limit.';return}
    fileLoading=true;status.textContent=`Extracting ${f.name}…`;
    try{
      const form=new FormData();form.append('file',f);
      const r=await fetch('/api/extract',{method:'POST',body:form});let data=await r.json();
      if(!r.ok)throw Error(parsedError(data,r.status));
      area.value=data.text||'';area.dispatchEvent(new Event('input',{bubbles:true}));
      status.textContent=`${f.name} extracted. Review and verify the text below before analysis.`;
      notify('Document extracted. Please review the text.');
    }catch(e){status.textContent=e.message||'Unable to extract this file.';}
    finally{fileLoading=false;file.value='';}
  }
  file.addEventListener('change',()=>extract(file.files[0]));
  if(drop){['dragenter','dragover'].forEach(k=>drop.addEventListener(k,e=>{e.preventDefault();drop.classList.add('dragover')}));
    ['dragleave','drop'].forEach(k=>drop.addEventListener(k,e=>{e.preventDefault();drop.classList.remove('dragover')}));
    drop.addEventListener('drop',e=>extract(e.dataTransfer?.files?.[0]));}
}
function setExample(form,fillContext=false){
  const t=$('[name="contract_text"]',form);if(t){t.value=exampleContract;t.dispatchEvent(new Event('input',{bubbles:true}))}
  if(fillContext){
    const values={client_entity:'Alpha Corp',counterparty_entity:'Vendor Four GmbH',deal_size:750000,liability_cap:1,auto_renewal:1,jurisdiction_risk:5,indemnification_clause:1,dispute_history:0,governing_law_clarity:3,deviation:35};
    Object.entries(values).forEach(([k,v])=>{const c=form.elements.namedItem(k);if(c)c.value=v});
  }
  notify('Synthetic example loaded. No real-client facts are implied.');
}
function setLoading(btn,busy,normal){if(!btn)return;btn.disabled=busy;btn.textContent=busy?'Analyzing…':normal;}
function miniKpi(label,value){const d=el('div');add(d,el('small','',label),el('strong','',value));return d;}
function renderStepRecap(form){const target=$('#review-recap');target.replaceChildren();
  const t=fieldValue(form,'contract_text'),client=fieldValue(form,'client_entity'),counterparty=fieldValue(form,'counterparty_entity'),deviation=fieldValue(form,'deviation');
  add(target,miniKpi('REPRESENTED ENTITY',client),miniKpi('COUNTERPARTY',counterparty),miniKpi('DOCUMENT SIZE',`${t.length.toLocaleString()} characters`),miniKpi('EXPOSURE MODEL',deviation===''?'Will be skipped if COI completes':'Deviation provided · '+deviation+'%'));
}
function reviewInit(){
  const form=$('#review-form');if(!form)return;
  const t=$('#contract-text');t.addEventListener('input',()=>$('#char-count').textContent=`${t.value.length.toLocaleString()} characters`);
  $('#load-example').addEventListener('click',()=>setExample(form,true));setupExtraction('#review-file','#contract-text');
  let step=1,sending=false;const panels=$$('.step-panel'),back=$('#prev-step'),next=$('#next-step'),submit=$('#review-submit');
  function move(to){step=to;panels.forEach(p=>p.hidden=Number(p.dataset.step)!==step);$$('[data-progress-label]').forEach(n=>{const val=Number(n.dataset.progressLabel);n.classList.toggle('current',val===step);n.classList.toggle('done',val<step)});$('#progress-fill').style.width=`${step/3*100}%`;back.hidden=step===1;next.hidden=step===3;submit.hidden=step!==3;clearError('#review-error');if(step===3)renderStepRecap(form);window.scrollTo({top:180,behavior:'smooth'});}
  back.addEventListener('click',()=>move(Math.max(1,step-1)));
  next.addEventListener('click',()=>{
    if(fileLoading){showError('#review-error','Document extraction is still in progress.');return}
    const invalid=validateFields(panels[step-1]);if(invalid){showError('#review-error',invalid);return}
    if(step===1&&t.value.trim().length<40){showError('#review-error','Enter at least 40 characters of contract text.');return}
    move(Math.min(3,step+1));
  });
  form.addEventListener('submit',async e=>{
    e.preventDefault();if(sending||fileLoading)return;clearError('#review-error');
    if(!$('#acknowledge').checked){showError('#review-error','Please acknowledge the data handling and human review requirements.');return}
    for(const panel of panels.slice(0,2)){const invalid=validateFields(panel);if(invalid){showError('#review-error',invalid);return}}
    const d=fieldValue(form,'deviation');const payload={doc_id:`review-${Date.now()}`,client_entity:fieldValue(form,'client_entity'),counterparty_entity:fieldValue(form,'counterparty_entity'),contract_entities:filesFromText(fieldValue(form,'contract_entities')),contract_text:fieldValue(form,'contract_text'),features:modelFeatures(form)};
    if(d!=='')payload.clause_deviation_override=Number(d)/100;
    sending=true;setLoading(submit,true,'Run analysis →');
    try{
      const result=await postJson('/api/analyze',payload);
      try{sessionStorage.setItem(SUMMARY_KEY,JSON.stringify({receivedAt:new Date().toISOString(),result}))}
      catch{throw Error('This browser cannot retain the report between pages. Enable session storage or use the developer console to run the API directly.')}
      window.location.assign('/results');
    }catch(err){showError('#review-error',err.message||'Review could not complete.');}
    finally{sending=false;setLoading(submit,false,'Run analysis →')}
  });
}
function downloadableJson(data,name){const b=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download=name;a.style.display='none';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function labelStatus(obj){return clean(obj?.status||'not run').split(':')[0].replaceAll('_',' ')}
function cardHead(title,index,status){const head=el('div','agent-report-head');const left=el('div','agent-report-title');add(left,el('span','agent-num',index),el('h3','',title));const pill=el('span',`status-pill ${safeState(status)}`,status||'not run');add(head,left,pill);return head}
function metric(label,value){const d=el('div','submetric');add(d,el('small','',label),el('strong','',value));return d}
function itemList(items,format,max=40){const list=el('div','finding-list');items.slice(0,max).forEach((f,i)=>{const n=el('div','finding-row');const [a,b,c]=format(f,i);add(n,el('strong','',a));const right=el('span');right.textContent=b||'';if(c)right.className=`risk-tag ${c}`;n.append(right);list.append(n)});if(items.length>max)list.append(el('p','',`${items.length-max} more entries are in the exported report.`));return list}
function detailsBlock(title,content){const d=el('details'),s=el('summary','',title);d.append(s,content);return d}
function explain(card,text){if(text)card.append(el('p','',text));}
const asArray=value=>Array.isArray(value)?value:[];
const present=value=>value!==null&&value!==undefined&&value!=='';
const riskLabel=value=>value==='Seed'?'Baseline (Seed)':clean(value||'Unavailable');
function renderCoi(data){const d=data&&typeof data==='object'?data:{},c=el('article','agent-report');c.append(cardHead('Conflict of interest','01 / COI',labelStatus(d)));
  const sub=el('div','submetric-row');add(sub,metric('VERIFIED CONFLICT',d.status==='complete'?(d.conflict_detected===true?'Detected':d.conflict_detected===false?'Not found in graph':'Undetermined'):'Undetermined'),metric('SEVERITY',d.severity||'Not available'));c.append(sub);
  if(d.status==='complete'&&d.conflict_detected===false)explain(c,'No verified conflict path was returned within the configured graph. This is not universal clearance.');
  if(d.skipped_reason||d.reason||d.graph_error)explain(c,d.skipped_reason||d.reason||d.graph_error);
  const path=asArray(d.conflict_path);if(path.length)c.append(detailsBlock('View relationship path',el('p','',path.join(' -> '))));
  const unresolved=asArray(d.unresolved_entities);if(unresolved.length)c.append(detailsBlock(`Unresolved entities (${unresolved.length})`,itemList(unresolved,x=>[clean(x),'Needs verification'])));
  const findings=asArray(d.findings);if(findings.length)c.append(detailsBlock(`Graph findings (${findings.length})`,itemList(findings,x=>[asArray(x?.path).join(' -> ')||x?.description||x?.type||'Graph finding',[`Severity: ${x?.severity||'unknown'}`,x?.verified===true?'Verified':'Unverified'].join(' | ')])));
  const clauseFindings=asArray(d.clause_findings);if(clauseFindings.length)c.append(detailsBlock(`Clause text findings (${clauseFindings.length})`,itemList(clauseFindings,x=>[x?.type||'Potential conflict',[x?.person,x?.relationship||x?.evidence,x?.verified===false?'Unverified':''].filter(Boolean).join(' | ')])));
  if(d.party_roles&&Object.keys(d.party_roles).length)c.append(detailsBlock('Party roles',itemList(Object.entries(d.party_roles),([role,value])=>[role.replaceAll('_',' '),Array.isArray(value)?value.join(', '):clean(value)])));
  return c;}
function renderCr(data){const d=data&&typeof data==='object'?data:{},c=el('article','agent-report'),clauses=asArray(d.clauses),attempted=clauses.length,classified=clauses.filter(x=>['Seed','Low','Medium','High'].includes(x?.model?.prediction)).length;
  c.append(cardHead('Clause risk','02 / CR',labelStatus(d)));
  const sub=el('div','submetric-row');add(sub,metric('CLASSIFIED',Array.isArray(d.clauses)?`${classified} / ${attempted}`:'Unavailable'),metric('OMITTED CLAUSES',present(d.omitted_clause_count)?clean(d.omitted_clause_count):'Unavailable'));c.append(sub);
  if(d.reason)explain(c,d.reason);
  explain(c,d.model_note||'LegalBERT labels are model risk signals, not calibrated probabilities. ?Seed? means Baseline, not Low risk.');
  if(!clauses.length)explain(c,d.status==='complete'?'No eligible clauses were returned for classification.':'No clause results were returned.');
  if(clauses.length){
    const list=el('div','finding-list');clauses.forEach(x=>{
      const row=el('div','finding-row'),left=el('div');add(left,el('strong','',`Clause ${x?.clause_id??'?'}`));if(Number.isFinite(x?.model?.model_score))left.append(el('div','',`Raw model score: ${(100*x.model.model_score).toFixed(1)}% (uncalibrated)`));
      row.append(left);const v=x?.model?.prediction;row.append(el('span',`risk-tag ${clean(v).toLowerCase()}`,riskLabel(v)));list.append(row);
      if(x?.reason)list.append(el('p','',x.reason));
    });c.append(detailsBlock(`Inspect ${clauses.length} attempted clauses`,list));
  }
  return c;}
function renderCl(data){const d=data&&typeof data==='object'?data:{},c=el('article','agent-report'),findings=asArray(d.findings);
  c.append(cardHead('Confidentiality leakage','03 / CL',labelStatus(d)));
  const sub=el('div','submetric-row');add(sub,metric('SENSITIVE SIGNALS',d.sensitive_data_detected===true?'Detected':d.sensitive_data_detected===false?'Not detected':'Unknown'),metric('FINDINGS',present(d.total_findings)?clean(d.total_findings):Array.isArray(d.findings)?clean(findings.length):'Unavailable'));c.append(sub);
  if(present(d.risk_score)||d.risk_level)explain(c,`Reported risk: ${d.risk_level||'unknown'}${present(d.risk_score)?` | score ${d.risk_score}/100`:''}. Finding values are redacted in the API response.`);
  else explain(c,'No confidentiality risk score was returned.');
  if(d.reason)explain(c,d.reason);
  const counts=[['High sensitivity',d.high_sensitivity_count],['Medium sensitivity',d.medium_sensitivity_count],['Context dependent',d.context_dependent_count]].filter(([,value])=>present(value));
  if(counts.length)c.append(detailsBlock('Sensitivity counts',itemList(counts,([name,value])=>[name,clean(value)])));
  if(d.summary&&typeof d.summary==='object')c.append(detailsBlock('Finding categories',itemList(Object.entries(d.summary),([name,value])=>[name.replaceAll('_',' '),clean(value)])));
  if(findings.length)c.append(detailsBlock(`View ${findings.length} reported findings`,itemList(findings,f=>[f?.type||'Sensitive finding',[f?.value,f?.sensitivity,f?.clause_id?`Clause ${f.clause_id}`:'',f?.section].filter(Boolean).join(' | ')])));
  return c;}
function renderLe(data,status){const d=data&&typeof data==='object'?data:null,c=el('article','agent-report'),probability=d?.litigation_probability;
  c.append(cardHead('Litigation exposure','04 / LE',status||d?.status||(present(probability)?'complete':'not run')));
  const score=Number(probability);
  if(present(probability)&&Number.isFinite(score)){
    const gauge=el('div','exposure-gauge'),ring=el('div','gauge-ring'),pct=Math.max(0,Math.min(100,score*100));ring.style.setProperty('--score',`${pct}%`);ring.append(el('strong','',`${pct.toFixed(1)}%`));const copy=el('div','gauge-copy');add(copy,el('strong','',`Model band: ${d.risk_level||'not supplied'}`),el('p','','Synthetic-trained model output, not a calibrated estimate of actual litigation likelihood.'));gauge.append(ring,copy);c.append(gauge);
    if(d.features_used&&typeof d.features_used==='object')c.append(detailsBlock('Features used',itemList(Object.entries(d.features_used),([name,value])=>[name.replaceAll('_',' '),clean(value)])));
    if(d.shap_explanation&&typeof d.shap_explanation==='object'){
      const entries=Object.entries(d.shap_explanation).filter(([,v])=>v!==null&&Number.isFinite(Number(v))).sort((a,b)=>Math.abs(Number(b[1]))-Math.abs(Number(a[1])));
      if(entries.length)c.append(detailsBlock('Model contribution values',itemList(entries,([k,v])=>[k.replaceAll('_',' '),Number(v).toFixed(4)])));
    }
    if(d.model_fingerprint)explain(c,`Model fingerprint: ${d.model_fingerprint}`);
  }else explain(c,`${clean(status||d?.reason||'Not run')}. A completed COI check and supplied template deviation are required for the coordinated review.`);
  return c;}
function createChart(cr){const root=el('div'),clauses=asArray(cr?.clauses),valid=clauses.map(x=>x?.model?.prediction).filter(x=>['Seed','Low','Medium','High'].includes(x));if(!valid.length){root.append(el('p','chart-empty','No clause classifications available for a distribution chart.'));return root;}
  ['High','Medium','Low','Seed'].forEach(name=>{const count=valid.filter(x=>x===name).length,row=el('div','chart-row'),track=el('div','chart-track'),fill=el('div',`chart-fill ${name.toLowerCase()}`);fill.style.width=`${100*count/valid.length}%`;track.append(fill);add(row,el('span','',name==='Seed'?'Baseline':name),track,el('b','',count));root.append(row);});return root;}
function summaryCell(code,value,desc){const c=el('div','summary-cell');add(c,el('span','small-index',code),el('strong','',value),el('span','',desc));return c;}
function resultsInit(){const root=$('#result-content');if(!root)return;const empty=$('#empty-results');let bundle=null;
  try{bundle=JSON.parse(sessionStorage.getItem(SUMMARY_KEY)||'null')}catch{}
  const d=bundle?.result;
  if(!d||typeof d!=='object'||!['coi','cr','cl','decision'].some(key=>key in d)){empty.hidden=false;root.hidden=true;$('#download-result').disabled=true;return;}
  root.hidden=false;empty.hidden=true;
  $('#report-id').textContent=`REVIEW / ${d.doc_id||'UNTITLED'}`;
  const complete=d.status==='complete'&&d.coi?.status==='complete'&&d.cr?.status==='complete'&&d.cl?.status==='complete'&&present(d.le?.litigation_probability);
  $('#report-subtitle').textContent=complete?'All four agent steps returned completed results. Findings still require human interpretation.':'One or more checks did not complete. Review unavailable signals below before making a decision.';
  $('#report-state').textContent=complete?'All four agents completed':'Partial or incomplete coverage';
  const summary=$('#result-summary-grid');summary.replaceChildren();
  const cr=d.cr||{},cl=d.cl||{},coi=d.coi||{},le=d.le;
  const classifications=asArray(cr.clauses).filter(x=>['Seed','Low','Medium','High'].includes(x?.model?.prediction));
  add(summary,summaryCell('01 / COI',coi.status==='complete'?(coi.conflict_detected===true?'Conflict found':coi.conflict_detected===false?'No path found':'Undetermined'):'Incomplete','Within configured graph only'),summaryCell('02 / CR',Array.isArray(cr.clauses)?String(classifications.length):'Unavailable','Classified clauses'),summaryCell('03 / CL',present(cl.total_findings)?String(cl.total_findings):Array.isArray(cl.findings)?String(cl.findings.length):'Unavailable','Sensitive findings'),summaryCell('04 / LE',present(le?.litigation_probability)&&Number.isFinite(Number(le.litigation_probability))?`${(Number(le.litigation_probability)*100).toFixed(1)}%`:'Not run','Synthetic model signal | uncalibrated'));
  const details=$('#report-details');details.replaceChildren(renderCoi(coi),renderCr(cr),renderCl(cl),renderLe(le,d.le_status));
  $('#classification-chart').replaceChildren(createChart(cr));
  const reasons=$('#review-reasons');reasons.replaceChildren();const decision=d.decision||{},list=asArray(decision.reasons);
  [...(list.length?list:['Every result requires human assessment.']),...asArray(decision.limitations)].forEach(reason=>reasons.append(el('li','',reason)));
  if(d.graph_update){const update=$('#graph-update');update.hidden=false;update.textContent=`Knowledge graph update: ${JSON.stringify(d.graph_update)}`;}
  $('#raw-result').textContent=JSON.stringify(d,null,2);
  $('#download-result').addEventListener('click',()=>downloadableJson(d,`${d.doc_id||'lexguard'}-report.json`));
  $('#clear-report').addEventListener('click',()=>{sessionStorage.removeItem(SUMMARY_KEY);window.location.reload()});
}
function renderToolResult(kind,d){const target=$('#tool-output-content');target.replaceChildren();
  if(kind==='conflicts')target.append(renderCoi(d));
  if(kind==='clauses'){target.append(renderCr(d));const viz=el('div','mini-panel');add(viz,el('h3','','Classification distribution'),createChart(d));target.append(viz);}
  if(kind==='confidentiality')target.append(renderCl(d));
  if(kind==='litigation'){target.append(renderCoi(d.coi));target.append(renderLe(d.litigation,d.litigation?'complete':d.status));}
  const pre=el('pre','raw-output',JSON.stringify(d,null,2));target.append(detailsBlock('View raw agent response',pre));
}
function toolInit(){const form=$('#tool-form');if(!form)return;const kind=$('[data-tool]')?.dataset.tool;let last=null,busy=false;
  if(['clauses','confidentiality'].includes(kind)){setupExtraction('#tool-file','[name="contract_text"]');$('#load-example')?.addEventListener('click',()=>setExample(form));}
  form.addEventListener('submit',async e=>{
    e.preventDefault();if(busy||fileLoading)return;clearError('#tool-error');
    const invalid=validateFields(form);if(invalid){showError('#tool-error',invalid);return}
    const entitySet={doc_id:`specialist-${Date.now()}`,client_entity:fieldValue(form,'client_entity'),counterparty_entity:fieldValue(form,'counterparty_entity'),contract_entities:filesFromText(fieldValue(form,'contract_entities')),additional_entities:[]};
    let path,body;
    if(kind==='conflicts'){path='/api/coi/check';body=entitySet;}
    if(kind==='clauses'){path='/api/cr/analyze';body={contract_text:fieldValue(form,'contract_text')};}
    if(kind==='confidentiality'){path='/api/cl/analyze';body={doc_id:`privacy-${Date.now()}`,contract_text:fieldValue(form,'contract_text')};}
    if(kind==='litigation'){path='/api/risk/assess';body={...entitySet,litigation_entities:modelFeatures(form),clause_deviation_score:Number(fieldValue(form,'deviation'))/100};}
    const submit=$('#tool-submit');busy=true;setLoading(submit,true,`Run ${kind} analysis`);
    try{const data=await postJson(path,body);last=data;renderToolResult(kind,data);$('#tool-output').hidden=false;$('#tool-output').scrollIntoView({behavior:'smooth',block:'start'});}
    catch(err){showError('#tool-error',err.message||'The request failed.');}
    finally{busy=false;setLoading(submit,false,`Run ${kind} analysis →`)}
  });
  $('#tool-export')?.addEventListener('click',()=>{if(last)downloadableJson(last,`lexguard-${kind}-response.json`)});
}
document.addEventListener('DOMContentLoaded',()=>{
  themeInit();reviewInit();toolInit();resultsInit();
  fetch('/initialize',{method:'POST'}).catch(()=>{}).finally(systemStatus);
  systemStatus();setInterval(systemStatus,5000);
});
