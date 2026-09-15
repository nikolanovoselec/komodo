const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const {JSDOM}=require('jsdom');
const markup='<div class="nw-dashboard"><details data-nw-disclosure="clients"><summary>Clients</summary><input type="search" data-nw-search><select data-nw-kind><option value="all">All</option><option value="wired">Wired</option></select><span data-nw-results></span><div data-nw-client data-kind="wired">Example workstation</div><div data-nw-client data-kind="wireless">Example phone</div></details><details data-nw-disclosure="capabilities"><summary>Capabilities</summary></details></div>';
test('public refresh retains filter, independent disclosures, keyboard focus and middle caret',async t=>{
 const w=new JSDOM(markup,{runScripts:'outside-only'}).window;t.after(()=>w.close());w.eval(fs.readFileSync(__dirname+'/networking.js','utf8'));
 const q=w.document.querySelector('input');q.focus();q.value='Example';q.dispatchEvent(new w.Event('input',{bubbles:true}));q.setSelectionRange(2,4);q.dispatchEvent(new w.Event('select',{bubbles:true}));
 const d=w.document.querySelector('details');d.open=true;d.dispatchEvent(new w.Event('toggle'));
 w.document.body.innerHTML=markup;w.document.dispatchEvent(new w.CustomEvent('dynacat:widget-updated'));
 const replacement=w.document.querySelector('input');assert.equal(replacement.value,'Example');assert.equal(w.document.activeElement,replacement);assert.equal(replacement.selectionStart,2);assert.equal(replacement.selectionEnd,4);
 assert.equal(w.document.querySelector('details').open,true);assert.equal(w.document.querySelectorAll('details')[1].open,false);
 // Native SSE morph can keep the focused node but reset its value.
 replacement.value='';w.document.dispatchEvent(new w.CustomEvent('dynacat:widget-updated'));
 assert.equal(replacement.value,'Example');assert.equal(replacement.selectionStart,2);assert.equal(replacement.selectionEnd,4);
});
