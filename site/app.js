(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const storeKey = 'framefinder-job-status-v2';
  let data = {last_run:null, jobs:[],signals:[],sources:[],summary:{matches:0,review:0,sources_ok:0,sources_total:0}};
  let view = 'all';
  let statuses = {};
  try { statuses = JSON.parse(localStorage.getItem(storeKey) || '{}') || {}; } catch { statuses = {}; }
  const safe = str => String(str == null ? '' : str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const validUrl = raw => { try { const u=new URL(raw); return ['https:','http:'].includes(u.protocol)?u.href:'#'; } catch {return '#';} };
  const dt = str => {if(!str)return 'Not run';const d=new Date(str);return Number.isNaN(d.getTime())?'Not run':d.toLocaleString('en-CA',{timeZone:'America/Vancouver',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});};
  const postedDate = str => {
    if(!str)return 'Date not published';
    const d=new Date(String(str).length===10?`${str}T12:00:00Z`:str);
    return Number.isNaN(d.getTime())?'Date not published':d.toLocaleDateString('en-CA',{timeZone:'UTC',month:'short',day:'numeric',year:'numeric'});
  };
  const save = () => {try{localStorage.setItem(storeKey,JSON.stringify(statuses));}catch(e){console.warn('Browser storage not available',e);}};
  function setStatus(id, status) { if(statuses[id] === status)delete statuses[id]; else statuses[id]=status; save();render(); }
  function summary() {
    $('count-matches').textContent=data.summary.matches||0;
    $('count-review').textContent=data.summary.review||0;
    $('count-sources').textContent=`${data.summary.sources_ok||0}/${data.summary.sources_total||0}`;
    $('last-scan').textContent=dt(data.last_run);
    $('nav-all').textContent=data.jobs.length;
    $('nav-signals').textContent=(data.signals||[]).length;
    $('top-status').textContent=data.last_run?'Cloud scans active':'Awaiting first scan';
  }
  function renderSources(){
    $('source-grid').innerHTML=(data.sources||[]).map(x=>`<div class="source-item"><span class="dot ${x.status==='ok'?'ok':''}"></span><a href="${safe(validUrl(x.url))}" target="_blank" rel="noopener noreferrer">${safe(x.name)}</a><span class="source-sub">${x.status==='ok'?`${x.count||0} source openings`:'Needs attention'} · ${safe(x.status==='ok'?'Checked '+dt(x.last_checked):x.message||'Unavailable')}</span></div>`).join('') || '<p>No scan has run yet.</p>';
  }
  function render(){
    summary(); renderSources();
    const titles={all:['Opportunities worth a look','Real openings from the companies you care about.'],saved:['Your saved opportunities','A short list of roles you want to revisit.'],applied:['Your applications','Keep track of positions you have applied for.'],signals:['Early hiring signals','Public production news and staffing clues. These are leads, not job openings.'],review:['Needs verification','Potential fits without confirmed project type or location eligibility.'],hidden:['Hidden jobs','Roles you dismissed. Restore them any time.']};
    $('view-title').textContent=titles[view][0];$('view-desc').textContent=titles[view][1];
    $('signals').classList.toggle('hidden',view!=='signals');
    $('jobs').classList.toggle('hidden',view==='signals');
    document.querySelector('.job-columns').classList.toggle('hidden',view==='signals');
    document.querySelector('.filters').classList.toggle('hidden',view==='signals');
    $('signals').innerHTML=(data.signals||[]).map(x=>`<article class="signal-card"><div class="signal-kicker">◉ POSSIBLE EARLY HIRING SIGNAL · ${safe(x.source||'Public news')}</div><h3>${safe(x.title)}</h3><p>${safe(x.summary||'Public production or staffing news; not a confirmed vacancy.')}</p><div class="signal-bottom"><span>${safe(dt(x.published_at||x.first_seen))}</span><a href="${safe(validUrl(x.url))}" target="_blank" rel="noopener noreferrer">Read evidence ↗</a></div></article>`).join('')||'<div class="empty-signal">No qualifying public hiring signals yet. The news feeds are checked at each scan.</div>';
    document.querySelectorAll('.nav-link').forEach(x=>x.classList.toggle('selected',x.dataset.view===view));
    const q=$('search').value.trim().toLowerCase();const tier=$('tier').value;const sort=$('sort').value;
    let jobs=(data.jobs||[]).filter(j=>{
      const status=statuses[j.id] || '';
      if(view==='signals')return false;
      if(view==='saved' && status!=='saved')return false;
      if(view==='applied' && status!=='applied')return false;
      if(view==='review' && j.tier!=='review')return false;
      if(view==='hidden' && status!=='hidden')return false;
      if(view==='all' && status==='hidden')return false;
      if(tier!=='all' && j.tier!==tier)return false;
      return !q || `${j.title} ${j.company} ${j.location} ${j.excerpt||''}`.toLowerCase().includes(q);
    });
    if(sort==='new')jobs.sort((a,b)=>new Date(b.first_seen)-new Date(a.first_seen));
    else if(sort==='company')jobs.sort((a,b)=>a.company.localeCompare(b.company));
    else jobs.sort((a,b)=>Number(b.tier==='match')-Number(a.tier==='match') || b.score-a.score);
    $('job-total').textContent=jobs.length;
    const sourceBadge=(x)=>{
      const lab=String(x.label||'Source');const l=lab.toLowerCase();
      const badge=l.includes('linkedin')?'in':l.includes('indeed')?'i':l==='official'?'◈':lab.slice(0,2).toUpperCase();
      const tooltip=lab==='Official'?'Official career site':`${lab}${x.verified_at?' · verified '+postedDate(x.verified_at):''}`;
      return `<a class="source-badge" target="_blank" rel="noopener noreferrer" href="${safe(validUrl(x.url))}" title="${safe(tooltip)}" aria-label="Advertised on ${safe(tooltip)}"><span class="source-symbol">${safe(badge)}</span>${safe(lab)}</a>`;
    };
    $('jobs').innerHTML=jobs.map(j=>{
      const status=statuses[j.id]||'';const initials=(j.company||'J').split(/\s+/).slice(0,2).map(w=>w.slice(0,1)).join('');
      const why=(j.reasons||[]).join(' · ');
      const sources=(j.sources&&j.sources.length?j.sources:[{label:'Official',url:j.url}]).map(sourceBadge).join('');
      const posting=j.posted_at?`Posted ${postedDate(j.posted_at)}`:'Posted date not provided';
      const postingSource=j.posted_source?` title="${safe(j.posted_source)}"`:'';
      return `<article class="job job-row"><div class="job-main"><div class="job-icon" aria-hidden="true">${safe(initials)}</div><div class="job-info"><div class="company">${safe(j.company)}</div><h3><a target="_blank" rel="noopener noreferrer" href="${safe(validUrl(j.url))}">${safe(j.title)}</a></h3><div class="job-meta"><span class="pill ${j.tier==='match'?'match':'review'}">${j.tier==='match'?'MATCH':'VERIFY'}</span>${status?`<span class="pill ${safe(status)}">${safe(status.toUpperCase())}</span>`:''}<span>${j.score}/100</span><span${postingSource}>· ${safe(posting)}</span><span>· Found ${safe(dt(j.first_seen))}</span></div></div></div><div class="job-pay"><small>PAY</small><strong>${safe(j.salary||'Not listed')}</strong></div><div class="job-place"><small>WORK ARRANGEMENT</small><strong>${safe(j.arrangement||'Not specified')}</strong><span>${safe(j.location||'Location not verified')}</span></div><div class="job-source"><small>ADVERTISED ON</small><div class="source-chips">${sources}</div></div><div class="job-note-row"><span>${safe(why)}</span><div class="job-actions"><button type="button" data-action="saved" data-id="${safe(j.id)}" class="${status==='saved'?'is-saved':''}">${status==='saved'?'★ Saved':'☆ Save'}</button><button type="button" data-action="applied" data-id="${safe(j.id)}" class="${status==='applied'?'is-applied':''}">✓ Applied</button><button type="button" data-action="hidden" data-id="${safe(j.id)}">${status==='hidden'?'Restore':'✕'}</button><a target="_blank" rel="noopener noreferrer" href="${safe(validUrl(j.url))}">Apply ↗</a></div></div></article>`;
    }).join('');
    const empty=jobs.length===0;$('empty').classList.toggle('hidden',!empty);
    $('empty-title').textContent=!data.last_run?'Your radar is warming up.':'No roles in this view.';
    $('empty-desc').textContent=!data.last_run?'Once the first cloud scan runs, matching opportunities will appear here. Check source health to see which boards are accessible.':'Try another filter, or check back after the next automatic scan.';
  }
  document.querySelectorAll('.nav-link').forEach(el=>el.addEventListener('click',()=>{view=el.dataset.view;render();}));
  ['search','tier','sort'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',render));
  $('sources-toggle').addEventListener('click',()=>{const closed=$('source-panel').classList.toggle('hidden');$('sources-toggle').setAttribute('aria-expanded',String(!closed));});
  $('jobs').addEventListener('click',e=>{const el=e.target.closest('button[data-action]');if(el)setStatus(el.dataset.id,el.dataset.action);});
  fetch('./data/jobs.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('Data unavailable');return r.json();}).then(d=>{data=d;render();}).catch(err=>{$('top-status').textContent='Cannot load job data';console.warn(err);render();});
  render();
})();
