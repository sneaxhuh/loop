export function createCircleController({getState, api, run, dialog, closeDialog, escape, toast}) {
  const $=id=>document.getElementById(id);
  const storageKey='loop-circle-draft-v1';
  let draft, step=1, error='', matches={}, searchBusy=false, shelfOpen=true;
  const aliases=()=>draft.participants.map((p,i)=>p.name.trim()||`Reader ${i+1}`);
  function save() { try { sessionStorage.setItem(storageKey,JSON.stringify(draft)); } catch (_) { /* The in-memory draft remains usable. */ } }
  function start(mode='new') {
    if(getState().busy) return toast('Wait for the current plan to finish.');
    if(!draft) {try {draft=JSON.parse(sessionStorage.getItem(storageKey));} catch (_) {draft=null;}}
    if(mode==='edit') {
      const state=getState();
      draft={name:state.fixture.name,editing_id:state.fixture.id,attested:false,
        participants:state.fixture.participants.map(p=>({name:p.name,references:structuredClone(state.taste[p.id]),languages:[...p.languages]})),
        books:state.fixture.candidates.map(b=>({qloo_id:b.qloo_id,name:b.name,author:b.author,owner:b.owner,language:b.language}))};
      save();
    } else if(draft?.editing_id) {draft=null;sessionStorage.removeItem(storageKey);}
    if(!draft) {
      if(!draft?.participants || draft.participants.length!==4) draft={name:'',participants:Array.from({length:4},()=>({name:'',references:[],languages:['en']})),books:[],attested:false};
    }
    step=1; error=''; render();
  }
  function header() {
    return `<div class="eyebrow muted">YOUR PEOPLE. YOUR NEXT CHAPTERS.</div><h2>${draft.editing_id?'Make room for a new chapter.':'Make a circle of your own.'}</h2><div class="setup-steps">${['The readers','Their shelves','The exchange'].map((label,i)=>`<span class="${step===i+1?'current':step>i+1?'complete':''}"><i>${step>i+1?'✓':i+1}</i>${label}</span>`).join('')}</div>`;
  }
  function refsFor(profile) { const state=getState();return profile.variants.music_only.map(id=>state.fixture.references.find(r=>r.id===id)).filter(Boolean); }
  function render() {
    matches={};
    let content;
    if(step===1) {
      content=`<p class="dialog-subtitle">Start with four readers. Choose the things each person already loves. Names stay in this shared workspace; Qloo receives public cultural references.</p><label class="field-label" for="new-circle-name">Name your reading circle</label><input class="setup-input" id="new-circle-name" maxlength="60" placeholder="e.g. Sunday reading club" value="${escape(draft.name)}"><div class="setup-readers">${draft.participants.map((reader,i)=>`<section class="setup-reader"><div class="setup-reader-heading"><span class="setup-number">0${i+1}</span><input class="setup-input" data-reader-name="${i}" maxlength="40" placeholder="Reader ${i+1}’s name or nickname" value="${escape(reader.name)}"><select class="dialog-select" data-reader-language="${i}" aria-label="Reader ${i+1} language"><option value="en" ${reader.languages[0]==='en'?'selected':''}>English</option><option value="fr" ${reader.languages[0]==='fr'?'selected':''}>French</option><option value="hi" ${reader.languages[0]==='hi'?'selected':''}>Hindi</option><option value="es" ${reader.languages[0]==='es'?'selected':''}>Spanish</option><option value="" ${!reader.languages.length?'selected':''}>Any language</option></select></div><div class="editable-chips">${reader.references.map((r,j)=>`<span class="taste-chip">${escape(r.name)}<button data-circle-remove-ref="${i}:${j}" aria-label="Remove ${escape(r.name)}">×</button></span>`).join('')||'<span class="setup-hint">Choose one to eight favorites.</span>'}</div><select class="dialog-select setup-example" data-reader-example="${i}" aria-label="Example favorites for reader ${i+1}"><option value="">Choose example favorites, or search below…</option>${getState().fixture.profiles.map((p,j)=>`<option value="${j}">${refsFor(p).map(r=>escape(r.name)).join(' + ')}</option>`).join('')}</select><div class="input-row setup-search"><select id="circle-ref-type-${i}" aria-label="Cultural reference type"><option value="artist">Artist</option><option value="movie">Film</option><option value="brand">Brand</option><option value="book">Book</option></select><input id="circle-ref-query-${i}" maxlength="100" placeholder="Search a public favorite…" aria-label="Reader ${i+1} favorite"><button class="button ghost" data-circle-search-ref="${i}">Search</button></div><div id="circle-ref-results-${i}" class="search-results"></div></section>`).join('')}</div>`;
    } else if(step===2) {
      content=`<p class="dialog-subtitle">Add 8–20 distinct titles your readers can offer. Select the intended book and author, then choose who owns the copy. Start with at least one offered copy per reader.</p><div class="setup-inventory-count"><strong>${draft.books.length} books on the shelf</strong><span>${draft.books.length<8?`${8-draft.books.length} more to get started`:'Ready to plan'}</span></div><form id="circle-book-search" class="input-row"><input id="circle-book-query" type="search" maxlength="100" placeholder="Search your book title…" required minlength="2" aria-label="Search an owned book"><button class="button primary" id="circle-book-search-button">Find book ↗</button></form><div id="circle-book-results" class="search-results"></div><div class="setup-book-list">${draft.books.map((b,i)=>`<article class="setup-book"><div class="setup-book-title"><strong>${escape(b.name)}</strong><button data-circle-remove-book="${i}" aria-label="Remove ${escape(b.name)}">×</button></div><div class="setup-book-fields"><input class="setup-input" data-circle-author="${i}" value="${escape(b.author)}" placeholder="Confirm the author" maxlength="160" aria-label="Author of ${escape(b.name)}"><select class="dialog-select" data-circle-owner="${i}" aria-label="Owner of ${escape(b.name)}"><option value="">Who owns this copy?</option>${aliases().map((name,j)=>`<option value="P${j+1}" ${b.owner===`P${j+1}`?'selected':''}>${escape(name)}</option>`).join('')}</select><select class="dialog-select" data-circle-book-language="${i}" aria-label="Language of ${escape(b.name)}">${[['en','English'],['fr','French'],['hi','Hindi'],['es','Spanish']].map(([k,v])=>`<option value="${k}" ${b.language===k?'selected':''}>${v}</option>`).join('')}</select></div></article>`).join('')}</div><details class="setup-known-books" ${shelfOpen?'open':''}><summary>Already own one of the books on the current shelf?</summary><p class="setup-hint">Add the matching title, then declare its actual owner.</p><div class="known-title-grid">${getState().fixture.candidates.map((b,i)=>`<button data-circle-shelf-book="${i}" ${draft.books.some(x=>x.qloo_id===b.qloo_id)?'disabled':''}>${escape(b.name)}<small>${escape(b.author)}</small></button>`).join('')}</div></details>`;
    } else {
      content=`<p class="dialog-subtitle">${escape(draft.name)} is ready. Qloo will rank your offered titles for each reader’s references. Loop will save a valid exchange, or explain when no exchange fits.</p><div class="setup-review">${draft.participants.map((p,i)=>`<section><div><span class="setup-number">0${i+1}</span><h3>${escape(p.name)}</h3></div><p>${p.references.map(r=>escape(r.name)).join(' · ')}</p><ul>${draft.books.filter(b=>b.owner===`P${i+1}`).map(b=>`<li>${escape(b.name)}</li>`).join('')}</ul></section>`).join('')}</div><label class="setup-attestation"><input type="checkbox" id="circle-attested" ${draft.attested?'checked':''}><span>These readers chose the references shown and own the copies listed. They are willing to offer those copies for an exchange.</span></label><p class="explanation-note">Creating a circle proposes handoffs. Each reader still reviews their incoming book before you arrange a physical exchange. ${getState().capabilities.live_qloo?'New book pools and references use live Qloo queries.':'New book pools or references need QLOO_API_KEY configured on the server.'}</p>`;
    }
    dialog(header()+content+`<div id="circle-setup-error" class="inline-error" role="status">${escape(error)}</div><div class="dialog-actions setup-actions">${step>1?'<button class="button ghost" data-circle-back>← Back</button>':'<button class="button ghost" data-close>Keep exploring</button>'}<button class="button primary" data-circle-next>${step===3?'Create circle & find a loop ↗':step===1?'Add their books →':'Review the circle →'}</button></div>`);
    const root=$('dialog-content');
    root.oninput=event=>{
      const t=event.target;
      if(t.id==='new-circle-name') draft.name=t.value;
      if(t.dataset.readerName!==undefined) draft.participants[Number(t.dataset.readerName)].name=t.value;
      if(t.dataset.readerLanguage!==undefined) draft.participants[Number(t.dataset.readerLanguage)].languages=t.value?[t.value]:[];
      if(t.dataset.circleAuthor!==undefined) draft.books[Number(t.dataset.circleAuthor)].author=t.value;
      if(t.dataset.circleOwner!==undefined) draft.books[Number(t.dataset.circleOwner)].owner=t.value;
      if(t.dataset.circleBookLanguage!==undefined) draft.books[Number(t.dataset.circleBookLanguage)].language=t.value;
      if(t.id==='circle-attested') draft.attested=t.checked;
      save();
    };
    root.onchange=event=>{
      const t=event.target;
      if(t.dataset.readerExample!==undefined && t.value!=='') {
        draft.participants[Number(t.dataset.readerExample)].references=structuredClone(refsFor(getState().fixture.profiles[Number(t.value)])); save();render();
      }
    };
    root.onclick=handleClick;
    if(step===2) {
      $('circle-book-search').onsubmit=e=>{e.preventDefault();search('book',$('circle-book-query').value,'books');};
      const panel=root.querySelector('.setup-known-books');panel.ontoggle=()=>{shelfOpen=panel.open;};
    }
  }
  function invalid(message) { error=message;$('circle-setup-error').textContent=message;return false; }
  function validate() {
    if(step===1) {
      if(!draft.name.trim()) return invalid('Name your reading circle.');
      for(let i=0;i<4;i++) {
        if(!draft.participants[i].name.trim()) return invalid(`Add a name or nickname for reader ${i+1}.`);
        if(!draft.participants[i].references.length) return invalid(`Choose at least one favorite for ${aliases()[i]}.`);
      }
    }
    if(step===2) {
      if(draft.books.length<8) return invalid('Add at least eight distinct book titles so Qloo can rank the shelf.');
      if(draft.books.some(b=>!b.author.trim()||!b.owner)) return invalid('Confirm every author and choose the owner of each offered copy.');
      for(let i=0;i<4;i++) if(!draft.books.some(b=>b.owner===`P${i+1}`)) return invalid(`${aliases()[i]} needs at least one offered copy.`);
    }
    if(step===3&&!draft.attested) return invalid('Confirm the chosen references and ownership before creating this circle.');
    error='';return true;
  }
  function addBook(match) {
    if(draft.books.length>=20) return toast('This pilot supports up to twenty distinct titles.');
    if(draft.books.some(b=>b.qloo_id===match.qloo_id)) return toast('That book is already on this shelf.');
    draft.books.push({qloo_id:match.qloo_id,name:match.name,author:match.author||'',owner:'',language:'en'});
    save();render();
  }
  async function search(type, query, key) {
    if(searchBusy) return;
    if(query.trim().length<2) return invalid('Enter at least two characters to search.');
    searchBusy=true;
    const container=key==='books'?$('circle-book-results'):$('circle-ref-results-'+key);
    container.textContent='Finding public matches…';
    try {
      const data=await api('/api/search',{type,query});
      if(!container.isConnected) return;
      matches[key]=data.results;
      container.innerHTML=data.results.map((r,i)=>`<button class="search-result" data-circle-match="${key}:${i}">${escape(r.name)}<small>${escape(r.disambiguation||r.author||r.type)}</small></button>`).join('')||'<p class="setup-hint">No matching title. Try another spelling.</p>';
    } catch(e) { if(container.isConnected)container.textContent=e.message; }
    finally { searchBusy=false; }
  }
  async function handleClick(event) {
    const t=event.target.closest('button');if(!t||t.disabled)return;
    if(t.dataset.circleSearchRef!==undefined) {
      const i=t.dataset.circleSearchRef;search($('circle-ref-type-'+i).value,$('circle-ref-query-'+i).value,i);
    } else if(t.dataset.circleRemoveRef!==undefined) {
      const [i,j]=t.dataset.circleRemoveRef.split(':').map(Number);draft.participants[i].references.splice(j,1);save();render();
    } else if(t.dataset.circleMatch!==undefined) {
      const [key,index]=t.dataset.circleMatch.split(':');const match=matches[key]?.[Number(index)];if(!match)return;
      if(key==='books')addBook(match);
      else {
        const refs=draft.participants[Number(key)].references;
        if(refs.length>=8)return toast('Choose at most eight favorites per reader.');
        if(!refs.some(r=>r.qloo_id===match.qloo_id))refs.push(match);
        save();render();
      }
    } else if(t.dataset.circleShelfBook!==undefined) addBook(getState().fixture.candidates[Number(t.dataset.circleShelfBook)]);
    else if(t.dataset.circleRemoveBook!==undefined) {draft.books.splice(Number(t.dataset.circleRemoveBook),1);save();render();}
    else if(t.hasAttribute('data-circle-back')) {step--;error='';render();}
    else if(t.hasAttribute('data-circle-next')) {
      if(!validate())return;
      if(step<3){step++;render();return;}
      const payload=structuredClone(draft);closeDialog();
      const success=await run(draft.editing_id?'update_circle':'create_circle',{...payload,circle_id:draft.editing_id});
      if(success) {draft=null;sessionStorage.removeItem(storageKey);toast('Your reading circle and first proposal are saved.');}
      else {error='The circle could not be created. Your draft is still here; review the request message and try again.';step=3;render();}
    }
  }
  async function menu() {
    if(getState().busy)return toast('Wait for the current plan to finish.');
    dialog('<div class="eyebrow muted">A PLACE FOR EVERY READING CIRCLE</div><h2>Your circles.</h2><p class="dialog-subtitle">Loading your saved shelves…</p>');
    try {
      const data=await api('/api/circles');
      dialog(`<div class="eyebrow muted">A PLACE FOR EVERY READING CIRCLE</div><h2>Your circles.</h2><p class="dialog-subtitle">Each circle keeps its own shelf, references, proposals, and review decisions in this workspace.</p><div class="saved-circles">${data.circles.map(c=>`<button data-open-saved-circle="${escape(c.id)}" ${c.active?'disabled':''}><span><strong>${escape(c.name)}</strong><small>${c.readers} readers · ${c.books} books${c.demo?' · example shelf':''}</small></span><span>${c.active?'Open':'↗'}</span></button>`).join('')}</div><div class="dialog-actions"><button class="button primary" id="menu-create-circle">Create a reading circle ↗</button>${getState().fixture.provenance!=='synthetic_test'?'<button class="button ghost" id="menu-edit-circle">Edit this circle</button>':''}<button class="button ghost" data-close>Return to the shelf</button></div>`);
      $('menu-create-circle').onclick=start;
      if($('menu-edit-circle'))$('menu-edit-circle').onclick=()=>start('edit');
      $('dialog-content').onclick=async e=>{
        const button=e.target.closest('[data-open-saved-circle]');if(!button||button.disabled)return;
        closeDialog();await run('open_circle',{circle_id:button.dataset.openSavedCircle});
      };
    } catch(e) {toast(e.message);closeDialog();}
  }
  return {start,menu};
}
