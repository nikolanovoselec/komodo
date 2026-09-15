const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require('jsdom');
async function fixture(t){
 const w=new JSDOM('<div class="header"><a class="nav-item" href="/media">Media</a><a class="nav-item" href="/hardware-workloads">Hardware</a><a target="_blank" href="/endpoints-services">New tab</a><select class="cc-page-select"><option value="/media">Media</option><option value="/hardware-workloads">Hardware</option><option value="/endpoints-services">Endpoints</option></select></div><main id="page" class="content-ready"><h1>Media</h1><div id="page-content"><div id="initial">Media content</div></div></main><section id="plex-radio"><audio></audio></section>',{url:'https://test/media',runScripts:'outside-only'}).window;
 w.scrollTo=()=>{};let calls=[],activations=[];
 w.fetch=async url=>{calls.push(url);return {ok:true,headers:{get:()=>null},text:async()=>'<div class="page-columns"><div class="page-column">'+url+'</div></div>'};};
 const text=fs.readFileSync(__dirname+'/dashboard-navigation.js','utf8').replace('export function installNavigation','function installNavigation');w.eval(text+';window.installNavigation=installNavigation;');
 w.installNavigation({pageData:{slug:'media'},activate:first=>activations.push(first)});
 t.after(()=>w.close());return {w,calls,activations};
}
test('internal click swaps content without replacing audio; back restores cached native DOM',async t=>{
 const {w,calls,activations}=await fixture(t);const audio=w.document.querySelector('audio'),initial=w.document.querySelector('#initial');
 w.document.querySelector('a[href="/hardware-workloads"]').click();await new Promise(setImmediate);
 assert.equal(w.location.pathname,'/hardware-workloads');assert.equal(w.document.querySelector('audio'),audio);assert.equal(w.document.title,'Hardware & Workloads');assert.equal(calls.length,1);
 await w.constructNavigate('/media');assert.equal(w.document.querySelector('#initial'),initial);assert.deepEqual(activations,[true,false]);
 w.history.back();await new Promise(r=>setTimeout(r,30));assert.equal(w.location.pathname,'/hardware-workloads');assert.equal(calls.length,1);
});
test('mobile select uses same lifecycle; repeated route does not fetch or activate twice',async t=>{
 const {w,calls,activations}=await fixture(t);const s=w.document.querySelector('select');s.value='/endpoints-services';s.dispatchEvent(new w.Event('change',{bubbles:true}));await new Promise(setImmediate);
 assert.equal(w.location.pathname,'/endpoints-services');await w.constructNavigate('/endpoints-services');assert.equal(calls.length,1);assert.deepEqual(activations,[true]);
});
test('returning to current route cancels a slow navigation and clears busy state',async t=>{
 const {w}=await fixture(t);let resolve;w.fetch=()=>new Promise(r=>resolve=r);
 const pending=w.constructNavigate('/hardware-workloads');await w.constructNavigate('/media');
 assert.equal(w.document.querySelector('#page').getAttribute('aria-busy'),'false');
 resolve({ok:true,headers:{get:()=>null},text:async()=>'<div class="page-columns"></div>'});await pending;
 assert.equal(w.location.pathname,'/media');assert.ok(w.document.querySelector('#initial'));
});
test('failed page fetch retains current content and playback and exposes a retryable error',async t=>{
 const {w}=await fixture(t);w.fetch=async()=>({ok:false,status:503});const audio=w.document.querySelector('audio');
 await w.constructNavigate('/hardware-workloads');assert.equal(w.location.pathname,'/media');assert.ok(w.document.querySelector('#initial'));assert.equal(w.document.querySelector('audio'),audio);assert.match(w.document.querySelector('[role=alert]').textContent,/could not/i);
});
