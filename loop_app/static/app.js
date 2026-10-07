import {createCircleController} from './circle.js';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state, owner = 'all', query = '', running = false, toastTimer, edit;
const isDemo = () => state.fixture.provenance === 'synthetic_test';
const lenses = {music_only:'Music', music_movies:'Music + films', music_brands:'Music + brands'};
const covers = ['#718272','#b69060','#843f39','#d9ceb0','#d4b29c','#6e7956','#9eafb4','#b88c56','#66848b','#a34e42','#948758','#7e8075','#c6aa91','#6b8f81','#6d6f52','#ac9f7d'];
const people = () => state.fixture.participants;
const books = () => state.fixture.candidates;
const person = id => people().find(p => p.id === id);
const book = id => books().find(b => b.id === id);
const avatar = p => `<span class="avatar" style="--avatar:${escape(p.color)}">${escape(p.initials)}</span>`;
function rank(pid, cid) {
  let before = 0;
  for (const values of state.ranking_info[pid]?.groups || []) {
    const group = values.filter(id => state.pool.includes(id));
    if (group.includes(cid)) return before + (group.length + 1) / 2;
    before += group.length;
  }
  return null;
}
const rankLabel = n => n === null ? 'unranked' : `#${Number(n.toFixed(1))}`;
function toast(text) {
  clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5500);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Loop-Token':state.csrf_token}, body:JSON.stringify(body)});
  if(response.status===401){location.assign('/');throw new Error('Sign in to the organizer workspace.');}
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The request could not finish.');
  return data;
}
async function reload() { state = await api('/api/state'); render(); }
async function showInvites(rotate=false){
  try{
    const data=await api('/api/invites',{rotate});
    dialog(`<div class="eyebrow muted">THE PEOPLE BEHIND THE PAGES</div><h2>Let everyone choose their next chapter.</h2><p class="dialog-subtitle">Send each reader their own private link. They can review their incoming book, change their favorites, or withdraw their own offered copies.</p><div class="invite-list">${data.readers.map(p=>{const link=location.origin+'/join#token='+p.token;return `<section class="invite-card"><div class="invite-heading"><strong>${escape(p.name)}</strong><span>${p.approval?.accepted===true?(p.approval.source==='participant_link'?'Accepted via reader link':'Recorded by organizer'):p.joined_at?'Link opened · awaiting review':'Not opened yet'}</span></div><div class="invite-copy"><input aria-label="${escape(p.name)}’s private link" value="${escape(link)}" readonly><button class="button ghost" data-copy-invite>Copy link ↗</button></div><a class="invite-open" href="${escape(link)}" target="_blank" rel="noopener noreferrer">Preview ${escape(p.name)}’s page ↗</a></section>`;}).join('')}</div><p class="explanation-note">${isDemo()?'This example uses fictional readers and offers; reviews are demo interactions. ':''}Anyone with a link can act as that reader. Replacing links revokes the old ones. ${location.hostname==='127.0.0.1'||location.hostname==='localhost'?'Local links work on this computer; use the hosted app to invite friends.':''}</p><div class="dialog-actions"><button class="button ghost" id="rotate-invites">Replace private links</button><button class="button primary" data-close>Back to the circle</button></div>`);
    $('rotate-invites').onclick=()=>showInvites(true);
    $('dialog-content').querySelectorAll('[data-copy-invite]').forEach(button=>button.onclick=async()=>{const input=button.previousElementSibling;try{await navigator.clipboard.writeText(input.value);button.textContent='Copied ✓';}catch(_){input.focus();input.select();toast('Select and copy the highlighted link.');}});
  }catch(e){toast(e.message);}
}
function controls(busy) {
  document.querySelectorAll('button[data-mutation], #plan-button, #disruption-button, #reset-button, #chat-send, #new-circle-hero, #create-circle-button, #taste-tabs button').forEach(b => { b.disabled = busy; });
  $('chat-input').disabled = busy;
  const temporary=state.capabilities.hosted&&!state.capabilities.persistent_storage;
  $('new-circle-hero').disabled=busy||temporary;$('create-circle-button').disabled=busy||temporary;
  $('agent-status').textContent = busy ? 'Working on the shared shelf…' : 'Ready when you are';
  $('plan-button').innerHTML = busy ? 'Finding a way…' : 'Find a loop <span>↗</span>';
}
async function run(action, data = {}, message = '') {
  if (running || state.busy) return toast('A plan is already running.');
  running = true; controls(true); $('agent-progress').hidden = false;
  $('agent-progress').className = 'agent-trace busy-mark';
  $('agent-progress').textContent = 'Reading the workspace…';
  try {
    const result = await api('/api/agent', {revision:state.revision,...data,...(action ? {action} : {message})});
    if (message) { $('chat-input').value = ''; $('chat-messages').insertAdjacentHTML('beforeend', `<div class="chat-message user">${escape(message)}</div>`); }
    let job;
    do {
      await new Promise(resolve => setTimeout(resolve, 600));
      job = await api('/api/jobs/' + result.job_id);
      $('agent-progress').innerHTML = (job.trace || []).slice(-4).map(t => `<div>✓ ${escape(t.message)}</div>`).join('') || 'Reading the workspace…';
    } while (job.status === 'running');
    if(action==='create_circle'||action==='update_circle'||action==='open_circle'){owner='all';query='';$('shelf-search').value='';}
    await reload();
    if (job.status === 'error') throw new Error(job.error);
    toast(state.proposal.status === 'no_exchange' ? 'No exchange fits the current restrictions.' : 'The updated proposal is saved.');
    return true;
  } catch (error) {
    toast(error.message); $('agent-progress').textContent = error.message;
    $('agent-progress').classList.remove('busy-mark');
    try { await reload(); } catch (_) { /* Keep the last readable workspace. */ }
    return false;
  } finally {
    running = false; controls(state.busy); $('agent-progress').classList.remove('busy-mark');
    if (state.timeline?.at(-1)?.revision === state.revision) $('agent-progress').hidden = true;
  }
}
function render() {
  $('logout-button').hidden=!state.organizer_login;
  $('storage-notice').hidden=!(state.capabilities.hosted&&!state.capabilities.persistent_storage);
  $('connection-error').hidden = true;
  $('avatar-stack').innerHTML = people().map(avatar).join('');
  $('circle-name').textContent=state.fixture.name || 'Our little reading circle';
  $('workspace-mode').textContent=isDemo()?'A demo among friends':'Your reading circle';
  $('workspace-avatar').textContent=people()[0].initials;
  $('reset-button').textContent=isDemo()?'Reset the demo':'Return to demo';
  document.querySelector('.hero-cta a').textContent=isDemo()?'Explore the example ↓':'Explore the circle ↓';
  document.querySelector('.shelf-footnote').textContent=isDemo()?'Real book titles. Fictional owners and offered copies. Cover designs are illustrative.':'Books and ownership declared by your circle. Cover designs are illustrative.';
  $('offered-count').textContent = books().filter(b => b.available && b.offered).length;
  $('source-label').textContent = Object.values(state.ranking_info).some(r => r.provenance === 'live_api_response') ? 'Qloo · saved live results' : 'Saved Qloo rankings';
  renderGraph(); renderHandoffs(); renderShelf(); renderReaders(); renderChat();
  controls(running || state.busy);
}
function renderGraph() {
  const moves = state.proposal.moves || [], count = Object.keys(state.proposal.fit || {}).length;
  $('exchange-title').textContent = count === 4 ? 'A new chapter for everyone.' : count ? 'A few shelves, connected.' : 'A little room to reconsider.';
  $('match-badge').textContent = count ? `${count} readers · ${state.proposal.cycles.length} ${state.proposal.cycles.length === 1 ? 'loop' : 'loops'}` : 'No feasible exchange';
  $('match-badge').classList.toggle('empty', !count);
  const ordered = [...new Set((state.proposal.cycles || []).flat().map(m => m.from).concat(people().map(p => p.id)))];
  const small = window.matchMedia('(max-width:700px)').matches;
  const width=small?420:640, height=small?410:455, centerX=width/2, centerY=small?190:220;
  const points = small ? [[100,90],[320,90],[320,295],[100,295]] : [[155,105],[485,105],[485,335],[155,335]];
  const pos = Object.fromEntries(ordered.map((pid, i) => [pid,points[i]]));
  function path(from, to, previous = false) {
    const a = pos[from], b = pos[to];
    if (!a || !b) return '';
    const dx = b[0]-a[0], dy = b[1]-a[1], length = Math.hypot(dx,dy);
    const ax = a[0]+dx/length*38, ay = a[1]+dy/length*38;
    const bx = b[0]-dx/length*42, by = b[1]-dy/length*42;
    const mx = (a[0]+b[0])/2, my = (a[1]+b[1])/2;
    const cx = mx+(mx-centerX)*.32, cy = my+(my-centerY)*.4;
    return `<path class="graph-path${previous ? ' previous' : ''}" d="M${ax},${ay} Q${cx},${cy} ${bx},${by}" marker-end="url(#${previous ? 'old-arrow' : 'arrow'})"/>`;
  }
  const previous = state.changes?.removed || [];
  $('exchange-graph').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${count ? 'Proposed book handoffs between '+count+' readers' : 'No closed book exchange is feasible'}"><title>Each arrow sends an offered book to another reader. Click a reader to edit their taste.</title><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10" fill="#5e846e"/></marker><marker id="old-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10" fill="#b3aa98"/></marker></defs>${previous.map(m=>path(m[0],m[1],true)).join('')}${moves.map(m=>path(m.from,m.to)).join('')}<text x="${centerX}" y="${centerY-12}" text-anchor="middle" class="graph-center-mark">✳</text><text x="${centerX}" y="${centerY+26}" text-anchor="middle" class="graph-center-title">${count ? 'Stories in motion.' : 'Room for a new plan.'}</text><text x="${centerX}" y="${centerY+50}" text-anchor="middle" class="graph-center-small">${count ? 'ONE BOOK OUT. ONE BOOK IN.' : 'TRY RESTORING A COPY OR A RESTRICTION.'}</text>${ordered.map(pid=>{
    const p=person(pid), [x,y]=pos[pid], incoming=moves.find(m=>m.to===pid), b=incoming&&book(incoming.candidate_id);
    const title=b ? b.name : 'Waiting for a match';
    const limit=small?23:29;
    return `<g class="graph-node" data-reader="${pid}" tabindex="0" role="button" aria-label="Edit ${escape(p.name)}’s cultural references"><circle cx="${x}" cy="${y}" r="31" fill="${incoming ? escape(p.color) : '#d9dbcf'}" stroke="#fffdf7" stroke-width="4"/><text x="${x}" y="${y+5}" text-anchor="middle" class="graph-initials">${escape(p.initials)}</text><text x="${x}" y="${y+53}" text-anchor="middle" class="graph-name">${escape(p.name)}</text><text x="${x}" y="${y+70}" text-anchor="middle" class="graph-caption">${incoming ? 'A NEW CHAPTER' : 'NO HANDOFF YET'}</text><text x="${x}" y="${y+88}" text-anchor="middle" class="graph-book">${escape(title.length>limit ? title.slice(0,limit-2)+'…' : title)}${incoming ? ' · '+rankLabel(rank(pid,b.id)) : ''}</text></g>`;
  }).join('')}</svg>`;
  $('exchange-note').innerHTML = `<span class="legend"><i></i> ${count ? 'Proposed handoffs' : 'No books assigned'}</span>${previous.length ? '<span class="legend old"><i></i> Previous handoffs</span>' : '<span>Everyone involved still gets a say.</span>'}`;
  const withdrawn = books().find(b=>!b.available);
  const target = moves[0] && book(moves[0].candidate_id);
  $('disruption-button').innerHTML = target ? `Withdraw ${escape(target.name)} <span>↗</span>` : withdrawn ? `Restore ${escape(withdrawn.name)} <span>↗</span>` : 'Explore the restrictions <span>↗</span>';
  $('disruption-button').onclick = () => target ? run('withdraw',{copy_id:target.id}) : withdrawn ? run('restore',{copy_id:withdrawn.id}) : showEvidence();
}
function renderHandoffs() {
  const moves = state.proposal.moves || [];
  let html = moves.map(m=>{
    const p=person(m.to), sender=person(m.from), b=book(m.candidate_id), approval=state.approvals[p.id];
    return `<article class="handoff">${avatar(p)}<div class="handoff-content"><div class="handoff-name">${escape(p.name)} receives <small>${rankLabel(rank(p.id,b.id))} / ${state.pool.length}</small></div><div class="handoff-book"><button data-book="${b.id}">${escape(b.name)}</button></div><div class="handoff-sender">from ${escape(sender.name)}’s shelf</div>${approval ? approval.accepted ? `<div class="accepted-tag">✓ ${isDemo()?'Demo review':approval.source==='participant_link'?'Reader accepted':'Organizer recorded'}</div>` : '<div class="declined-tag">Declined · find another loop</div>' : `<div class="accept-actions"><button class="accept" data-accept="${p.id}" data-mutation>Record acceptance</button><button data-decline="${p.id}" data-mutation>Pass</button></div>`}</div></article>`;
  }).join('');
  if (!moves.length) html='<p class="handoff-empty">No closed exchange meets the current offers and restrictions. Try restoring a copy, changing a reading restriction, or lowering the minimum fit in the evidence panel.</p>';
  const unmatched = state.proposal.unmatched || [];
  if (unmatched.length && moves.length) html += `<div class="handoff-empty">Still looking for ${unmatched.map(pid=>escape(person(pid).name)).join(' and ')}. Their books stay on their shelves.</div>`;
  if (moves.length && moves.every(m=>state.approvals[m.to]?.accepted)) html += `<div class="all-accepted"><span>✓ All ${isDemo()?'demo ':''}acceptances recorded. Arrange handoffs with everyone involved.</span><a href="/api/export" download>Download proposal ↗</a></div>`;
  $('handoffs').innerHTML=html;
}
function cover(b) {
  const i = books().findIndex(x=>x.id===b.id), color=covers[i%covers.length];
  const ink = [3,4,8,12,15].includes(i) ? '#303d31' : '#faf1d9';
  const patterns = [
    '<circle cx="72" cy="145" r="47" fill="none" stroke="currentColor" stroke-width="1"/><circle cx="72" cy="145" r="30" fill="none" stroke="currentColor" stroke-width="1"/><path d="M26 190L118 98M26 99L118 190" stroke="currentColor" stroke-width="1"/>',
    '<circle cx="104" cy="110" r="23" fill="currentColor" opacity=".65"/><path d="M0 205Q40 126 88 176T160 173L160 230H0Z" fill="currentColor" opacity=".4"/><path d="M0 210Q60 158 160 197" fill="none" stroke="currentColor"/>',
    '<path d="M24 193C24 128 126 121 126 193M40 193C40 145 110 145 110 193M56 193C56 161 94 161 94 193" fill="none" stroke="currentColor" stroke-width="1.5"/>',
    '<path d="M35 115V190H115V115ZM35 152H115M75 115V190" fill="none" stroke="currentColor"/><path d="M20 195H130M20 201H130" stroke="currentColor"/>'
  ];
  return `<div class="book-cover" style="--cover:${color};--cover-ink:${ink}"><span class="book-cover-title">${escape(b.name)}</span><svg class="cover-art" viewBox="0 0 150 230" preserveAspectRatio="xMidYMid slice" aria-hidden="true">${patterns[i%4]}</svg><span class="book-cover-author">${escape(b.author)}</span></div>`;
}
function renderShelf() {
  $('owner-filters').innerHTML = [{id:'all',name:'All shelves'},...people()].map(p=>`<button class="${owner===p.id ? 'selected' : ''}" data-owner="${p.id}" aria-pressed="${owner===p.id}">${escape(p.name)} <small>${books().filter(b=>b.available&&(p.id==='all'||b.owner===p.id)).length}</small></button>`).join('');
  const selected = new Set(state.proposal.moves.map(m=>m.candidate_id));
  const filtered = books().filter(b=>(owner==='all'||b.owner===owner) && (b.name+' '+b.author).toLowerCase().includes(query.toLowerCase()));
  $('shelf-grid').innerHTML = filtered.map(b=>{
    const p=person(b.owner);
    return `<article class="book-card ${selected.has(b.id)?'in-loop':''} ${!b.available?'withdrawn':''}"><button class="book-open" data-book="${b.id}" aria-label="Explore ${escape(b.name)}">${cover(b)}<div class="book-title">${escape(b.name)}</div><div class="book-author">${escape(b.author)}</div></button><div class="book-owner-row"><span><i class="owner-dot" style="--avatar:${escape(p.color)}"></i>${escape(p.name)}’s shelf</span>${!b.available?'<span class="withdrawn-label">Withdrawn</span>':selected.has(b.id)?'<span class="in-loop-label">In the loop ↗</span>':''}</div><button class="book-action" data-${b.available?'withdraw':'restore'}="${b.id}" data-mutation aria-label="${b.available?'Withdraw':'Restore'} ${escape(b.name)}" title="${b.available?'Withdraw':'Restore'} this copy">${b.available?'−':'+'}</button></article>`;
  }).join('') || '<p class="handoff-empty">No books match that search.</p>';
}
function renderReaders() {
  $('taste-tabs').innerHTML=isDemo()?Object.entries(lenses).map(([key,label])=>`<button data-variant="${key}" class="${state.variant===key?'selected':''}" aria-pressed="${state.variant===key}">${label}</button>`).join(''):'<span class="personal-taste-label">References chosen by your readers</span>';
  $('reader-list').innerHTML=people().map(p=>`<button class="reader" data-reader="${p.id}">${avatar(p)}<div class="reader-body"><div class="reader-name">${escape(p.name)}<span>↗</span></div><p class="reader-bio">${escape(p.bio)}</p><div class="taste-chips">${state.taste[p.id].slice(0,3).map(r=>`<span class="taste-chip">${escape(r.name)}</span>`).join('')}${state.taste[p.id].length>3?`<span class="taste-chip">+${state.taste[p.id].length-3}</span>`:''}</div></div></button>`).join('');
}
function renderChat() {
  $('chat-messages').innerHTML=state.messages.map(m=>`<div class="chat-message ${m.role==='user'?'user':''}">${m.engine?`<small>${escape(m.engine)}</small>`:''}${escape(m.text.replace(/\bP[1-4]\b/g,pid=>person(pid)?.name||pid))}${m.trace?.length?`<details class="agent-trace"><summary>${m.trace.length} completed tool steps</summary>${m.trace.map(t=>`<div>✓ ${escape(t.message)}</div>`).join('')}</details>`:''}</div>`).join('');
  $('chat-messages').scrollTop=$('chat-messages').scrollHeight;
  $('chat-starters').innerHTML='<button data-prompt="Find a loop">Find a loop ↗</button><button data-prompt="Explain this exchange">Why these books?</button>';
  $('agent-mode').textContent=state.capabilities.gemini ? `Gemini agent · Qloo taste · validated handoffs` : 'Guided mode · saved Qloo taste · validated handoffs';
}
function dialog(html) { const root=$('dialog-content');root.onclick=null;root.oninput=null;root.onchange=null;root.innerHTML=html; if (!$('detail-dialog').open) $('detail-dialog').showModal(); }
function closeDialog() { $('detail-dialog').close(); edit=null; }
function showBook(cid) {
  const b=book(cid), p=person(b.owner);
  dialog(`<div class="eyebrow muted">FROM ${escape(p.name.toUpperCase())}’S SHELF</div><div class="detail-book">${cover(b)}<div><h2>${escape(b.name)}</h2><p class="dialog-subtitle">${escape(b.author)}</p><p class="detail-owner">${b.available?'Offered':'Withdrawn'} · ${escape({en:'English',fr:'French',hi:'Hindi',es:'Spanish'}[b.language]||b.language)} · ${isDemo()?'one fictional copy':'one offered copy'}</p><div class="dialog-actions"><button class="button ${b.available?'clay':'primary'}" data-${b.available?'withdraw':'restore'}="${b.id}" data-mutation>${b.available?'Withdraw this copy':'Restore this copy'}</button></div></div></div><table class="rank-table"><thead><tr><th>Reader</th><th>Qloo rank / ${state.pool.length}</th><th>Declared references</th></tr></thead><tbody>${people().map(p=>`<tr><td>${escape(p.name)}</td><td>${rankLabel(rank(p.id,cid))}</td><td><small>${state.taste[p.id].map(r=>escape(r.name)).join(', ')}</small></td></tr>`).join('')}</tbody></table><p class="explanation-note">These ranks come from Qloo’s ordering of the same book pool for each set of references. They don’t explain why a particular person would enjoy the book. Readers decide whether to accept.</p>`);
}
function showReader(pid) {
  if (running||state.busy) return toast('Wait for the current plan before editing taste.');
  const p=person(pid);
  const excluded=books().filter(b=>p.acceptable_ids&&!p.acceptable_ids.includes(b.id)).map(b=>b.id);
  const pending=state.approvals[pid]?.accepted===false&&state.proposal.moves.find(m=>m.to===pid)?.candidate_id;
  if(pending&&!excluded.includes(pending))excluded.push(pending);
  edit={pid,references:structuredClone(state.taste[pid]),languages:[...(p.languages||[])],read:[...(p.already_read_ids||[])],declined:excluded};
  dialog(`<div class="dialog-heading">${avatar(p)}<div><div class="eyebrow muted">A READER, A WHOLE WORLD OF TASTE</div><h2>${escape(p.name)}’s references.</h2></div></div><p class="dialog-subtitle">${isDemo()?'Try your own public favorites in this fictional reader’s place.':'Choose the public favorites this reader wants to use.'} Choose a specific search result so Qloo uses the right artist, film, book, or brand.</p><label class="field-label">What do you love?</label><div id="editable-chips" class="editable-chips"></div><div class="profile-presets">${Object.entries(lenses).map(([k,v])=>`<button data-preset="${k}">${v}</button>`).join('')}</div><label class="field-label" for="reference-query">Add a public cultural reference</label><form id="reference-form" class="input-row"><select id="reference-type" aria-label="Reference type"><option value="artist">Artist</option><option value="movie">Film</option><option value="brand">Brand</option><option value="book">Book</option></select><input id="reference-query" placeholder="e.g. Radiohead" maxlength="100" required minlength="2"><button class="button ghost" id="reference-search">Search</button></form><div id="reference-results" class="search-results"></div><div id="profile-error" class="inline-error" role="status"></div><label class="field-label" for="reader-language">Reading language</label><select class="dialog-select" id="reader-language"><option value="en">English</option><option value="fr">French</option><option value="hi">Hindi</option><option value="es">Spanish</option><option value="">No language restriction</option></select><label class="field-label">Already read? Exclude these books.</label><div class="reading-checklist">${books().map(b=>`<label><input type="checkbox" name="already-read" value="${b.id}" ${edit.read.includes(b.id)?'checked':''}>${escape(b.name)}</label>`).join('')}</div>${edit.declined.length?`<label class="field-label">Previously passed on · uncheck to reconsider</label><div class="reading-checklist">${edit.declined.map(cid=>`<label><input type="checkbox" name="declined-book" value="${cid}" checked>${escape(book(cid).name)}</label>`).join('')}</div>`:''}<div class="dialog-actions"><button class="button primary" id="save-profile" data-mutation>Save taste & find a loop ↗</button><button class="button ghost" data-close>Keep current profile</button></div><p class="explanation-note">Demo presets use genuine saved rankings. New combinations query Qloo on the server; no names, emails, or raw chat are sent to Qloo.</p>`);
  $('reader-language').value=edit.languages[0]||'';
  renderEditChips();
  $('reference-form').onsubmit=searchReference;
  $('save-profile').onclick=()=>{
    if (!edit.references.length) return $('profile-error').textContent='Choose at least one public reference.';
    const value=$('reader-language').value;
    const payload={participant_id:edit.pid,references:edit.references,languages:value?[value]:[],already_read_ids:[...document.querySelectorAll('[name="already-read"]:checked')].map(e=>e.value),declined_ids:[...document.querySelectorAll('[name="declined-book"]:checked')].map(e=>e.value)};
    closeDialog(); run('profile',payload);
  };
}
function renderEditChips() { $('editable-chips').innerHTML=edit.references.map((r,i)=>`<span class="taste-chip">${escape(r.name)}<button data-remove-reference="${i}" aria-label="Remove ${escape(r.name)}">×</button></span>`).join('')||'<span class="dialog-subtitle">Add a favorite or choose a preset.</span>'; }
async function searchReference(event) {
  event.preventDefault(); const currentEdit=edit;
  const input=$('reference-query').value, kind=$('reference-type').value;
  $('reference-search').disabled=true; $('profile-error').textContent=''; $('reference-results').textContent='Searching public cultural entities…';
  try {
    const data=await api('/api/search',{query:input,type:kind});
    if (edit!==currentEdit) return;
    currentEdit.results=data.results;
    $('reference-results').innerHTML=data.results.map((r,i)=>`<button class="search-result" data-add-reference="${i}">${escape(r.name)}<small>${escape(r.disambiguation||r.type)} · ${escape(r.qloo_id.slice(0,8))}</small></button>`).join('')||'<p class="dialog-subtitle">No match. Try a different title or spelling.</p>';
  } catch(error) { if (edit===currentEdit) { $('reference-results').textContent=''; $('profile-error').textContent=error.message; } }
  finally { if (edit===currentEdit) $('reference-search').disabled=false; }
}
function showEvidence() {
  dialog(`<div class="eyebrow muted">THE EVIDENCE BEHIND THE EXCHANGE</div><h2>Taste, with the workings visible.</h2><p class="dialog-subtitle">Qloo ranks the same ${books().length} titles using each reader’s declared cultural references. The solver first serves as many readers as possible, then improves the weakest relative fit and total fit.</p><div class="evidence-info"><span class="badge">${state.pool.length} commonly ranked books</span><span class="badge">${state.validation.valid?'Constraints checked':'Validation failed'}</span><span class="badge">${escape(state.variant==='custom'?'Custom references':lenses[state.variant]||'Reader references')}</span></div><label class="field-label" for="evidence-reader">Inspect a reader’s ordering</label><select id="evidence-reader" class="dialog-select">${people().map(p=>`<option value="${p.id}">${escape(p.name)}</option>`).join('')}</select><div id="evidence-table"></div><p class="explanation-note">Latest recorded ordering: ${escape(new Date(state.captured_at).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'}))}. Gemini uses the same candidate information and references. Ties use midranks. This view reports orderings, not a measured preference win. ${isDemo()?'Fictional ownership and offers have not been validated with real readers.':'Ownership and favorites are declared by the circle. The ordering is not an independently measured preference win.'}</p><label class="field-label" for="fit-floor">Minimum relative rank fit</label><div class="range-row"><span>Open</span><input id="fit-floor" type="range" min="0" max="1" step="0.05" value="${state.fixture.constraints.fit_floor}"><output id="floor-value">${state.fixture.constraints.fit_floor.toFixed(2)}</output></div><p class="dialog-subtitle">A fit of 1 requires a top-ranked book. A fit of 0 permits any ranked book. This is a rank index within the fixed pool, not a satisfaction probability.</p><div class="dialog-actions"><button id="apply-floor" class="button primary" data-mutation>Apply & replan</button><button id="refresh-rankings" class="button ghost" data-mutation ${state.capabilities.live_qloo?'':'disabled'}>Refresh Qloo rankings</button></div><p class="dialog-subtitle">${state.capabilities.live_qloo?'Refreshing makes four live Insights requests.':'Configure QLOO_API_KEY on the server to enable live searches and fresh rankings.'} The current proposal and evidence can be downloaded from the footer.</p>`);
  const renderTable=()=>{
    const pid=$('evidence-reader').value, baseline=state.baseline[pid];
    $('evidence-table').innerHTML=`<table class="rank-table"><thead><tr><th>Book</th><th>Qloo</th><th>Gemini${baseline?'':' · pending'}</th></tr></thead><tbody>${[...books()].sort((a,b)=>(rank(pid,a.id)??99)-(rank(pid,b.id)??99)).map(b=>`<tr><td>${escape(b.name)}${!b.available?' <small>withdrawn</small>':''}</td><td>${rankLabel(rank(pid,b.id))}</td><td>${baseline?rankLabel(baseline.ranks[b.id]??null):'—'}</td></tr>`).join('')}</tbody></table><p class="dialog-subtitle">${baseline?escape(baseline.model):'No saved Gemini comparison for these custom references.'} · ranks relative to ${state.pool.length} books.</p>`;
  };
  $('evidence-reader').onchange=renderTable; renderTable();
  $('fit-floor').oninput=()=>{ $('floor-value').textContent=Number($('fit-floor').value).toFixed(2); };
  $('apply-floor').onclick=()=>{ const value=Number($('fit-floor').value); closeDialog(); run('constraints',{fit_floor:value}); };
  $('refresh-rankings').onclick=()=>{ closeDialog(); run('refresh'); };
  controls(running||state.busy);
  if (!state.capabilities.live_qloo) $('refresh-rankings').disabled=true;
}
function showHow() {
  dialog('<div class="eyebrow muted">A SMALL LOOP, A NEW POSSIBILITY</div><h2>Keep the stories moving.</h2><div class="steps-list"><div class="how-step"><div><h3>Start with what is offered.</h3><p>Each copy belongs to one reader. They choose whether to offer it, which languages they read, and which books they have already read.</p></div></div><div class="how-step"><div><h3>Let taste open a door.</h3><p>Qloo uses public music, film, book, and brand references to rank the shared titles. It offers a cultural signal; the reader makes the personal decision.</p></div></div><div class="how-step"><div><h3>Find an exchange that closes.</h3><p>The agent proposes handoffs where everyone gives one book and receives one. Offers, reading restrictions, and the minimum fit are checked before saving.</p></div></div><div class="how-step"><div><h3>Make room for a change of plans.</h3><p>Withdraw a copy or decline an incoming title, then find another loop. The revised graph shows the previous handoffs alongside the new proposal.</p></div></div></div><p class="explanation-note">Start your own circle to add offered books and readers’ chosen references, or explore the fictional example shelf. Acceptances are recorded in this shared workspace. Arrange physical exchanges with the actual participants.</p><div class="dialog-actions"><button class="button primary" data-close>Explore the shelf ↗</button></div>');
}
document.addEventListener('click', async event=>{
  const target=event.target.closest('button, [data-reader]'); if (!target || !state || target.disabled) return;
  if (target.hasAttribute('data-reader')) { target.focus({preventScroll:true}); showReader(target.dataset.reader); }
  else if (target.hasAttribute('data-book')) showBook(target.dataset.book);
  else if (target.hasAttribute('data-owner')) { owner=target.dataset.owner; renderShelf(); }
  else if (target.hasAttribute('data-variant')) run('variant',{variant:target.dataset.variant});
  else if (target.hasAttribute('data-prompt')) run(null,{},target.dataset.prompt);
  else if (target.hasAttribute('data-withdraw') || target.hasAttribute('data-restore')) { const action=target.hasAttribute('data-withdraw')?'withdraw':'restore', cid=target.dataset[action]; closeDialog(); run(action,{copy_id:cid}); }
  else if (target.hasAttribute('data-accept') || target.hasAttribute('data-decline')) {
    try { await api('/api/accept',{participant_id:target.dataset.accept||target.dataset.decline,accepted:target.hasAttribute('data-accept'),proposal_id:state.proposal_id}); await reload(); toast(target.hasAttribute('data-accept')?isDemo()?'Demo acceptance saved.':'Acceptance saved in this shared workspace.':'Preference saved. Find a loop to exclude that incoming book.'); }
    catch(error) { toast(error.message); }
  }
  else if (target.hasAttribute('data-remove-reference') && edit) { edit.references.splice(Number(target.dataset.removeReference),1); renderEditChips(); }
  else if (target.hasAttribute('data-add-reference') && edit) {
    const r=edit.results[Number(target.dataset.addReference)];
    if (edit.references.length>=8) return $('profile-error').textContent='Choose at most eight references.';
    if (!edit.references.some(x=>x.qloo_id===r.qloo_id)) edit.references.push(r);
    renderEditChips(); $('reference-results').innerHTML=''; $('reference-query').value='';
  }
  else if (target.hasAttribute('data-preset') && edit) {
    const profile=state.fixture.profiles.find(p=>p.id===person(edit.pid).profile_id);
    edit.references=profile.variants[target.dataset.preset].map(id=>structuredClone(state.fixture.references.find(r=>r.id===id))); renderEditChips();
  }
  else if (target.hasAttribute('data-close')) closeDialog();
});
document.addEventListener('keydown', event=>{
  if ((event.key==='Enter'||event.key===' ') && event.target.matches('.graph-node')) { event.preventDefault(); showReader(event.target.dataset.reader); }
});
$('detail-dialog').querySelector('.dialog-close').onclick=closeDialog;
$('detail-dialog').addEventListener('click', e=>{ if(e.target===$('detail-dialog')) { const r=e.target.getBoundingClientRect(); if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom) closeDialog(); } });
$('detail-dialog').addEventListener('cancel', ()=>{ edit=null; });
$('shelf-search').oninput=e=>{ query=e.target.value; renderShelf(); };
$('plan-button').onclick=()=>run('plan');
$('reset-button').onclick=()=>{ owner='all';query='';$('shelf-search').value='';closeDialog();run('reset'); };
$('evidence-button').onclick=showEvidence;
$('invite-button').onclick=()=>showInvites();
$('logout-button').onclick=async()=>{await api('/api/logout',{});location.assign('/');};
$('footer-evidence').onclick=showEvidence;
$('how-button').onclick=showHow;
const circleUI=createCircleController({getState:()=>state,api,run,dialog,closeDialog,escape,toast});
$('create-circle-button').onclick=circleUI.start;
$('new-circle-hero').onclick=circleUI.start;
$('circle-menu').onclick=circleUI.menu;
$('chat-form').onsubmit=event=>{ event.preventDefault();const text=$('chat-input').value.trim();if(text)run(null,{},text); };
$('chat-input').addEventListener('keydown', event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('chat-form').requestSubmit();}});
reload().catch(error=>{ $('connection-error').hidden=false; $('connection-error').textContent='The workspace is unavailable. Start the Loop server and reload this page. '+error.message; });
window.matchMedia('(max-width:700px)').addEventListener('change',()=>{ if(state)renderGraph(); });
setInterval(()=>{if(state&&!running&&!edit&&!$('detail-dialog').open)reload().catch(()=>{});},8000);
