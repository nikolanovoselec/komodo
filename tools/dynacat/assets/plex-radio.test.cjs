// Run: npm install --prefix /tmp/plex-radio-test jsdom --no-audit --no-fund
// NODE_PATH=/tmp/plex-radio-test/node_modules node --test assets/plex-radio.test.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = `${__dirname}/plex-radio.js`;
function make(options={}) {
  const {createRadio} = require(source);
  const audio = new EventTarget();
  Object.assign(audio, {paused:true, src:'', plays:0, pause(){this.paused=true;}, load(){}, removeAttribute(){this.src='';}, async play(){this.plays++; this.paused=false;}});
  const tracks = [1,2,3].map(id => ({id:String(id), title:`Track ${id}`, artist:'Artist', album:'Album',stream:`/radio/stream/${id}`}));
  let calls=0;
  const radio = createRadio({audio, fetch:async()=>{calls++;return {ok:true,json:async()=>({tracks})};}, random:()=>0, ...options});
  return {radio,audio,tracks,calls:()=>calls};
}
test('explicit Play starts a local stream; pause and resume reuse it',async()=>{
  const {radio,audio,calls}=make();
  await radio.play();
  assert.equal(calls(),1);assert.equal(audio.src,'/radio/stream/1');assert.equal(radio.state.playing,true);
  radio.pause();assert.equal(audio.paused,true);
  await radio.play();assert.equal(calls(),1);assert.equal(audio.plays,2);
});
test('next follows shuffle, previous uses history, paused skips never start audio',async()=>{
  const {radio,audio}=make();await radio.play();
  await radio.next();assert.equal(audio.src,'/radio/stream/2');
  await radio.previous();assert.equal(audio.src,'/radio/stream/1');
  assert.equal(radio.state.shuffle,true);
  radio.pause();await radio.next();assert.equal(audio.src,'/radio/stream/2');assert.equal(audio.paused,true);
  const idle=make();await idle.radio.next();assert.equal(idle.audio.plays,0);assert.equal(idle.calls(),0);
});
test('Shuffle immediately plays a different random track, including from paused and idle',async()=>{
  const {radio,audio}=make();await radio.play();radio.pause();
  const first=audio.src;await radio.shuffle();
  assert.notEqual(audio.src,first);assert.equal(audio.paused,false);assert.equal(radio.state.shuffle,true);
  await radio.previous();assert.equal(audio.src,first);
  const idle=make();await idle.radio.shuffle();assert.equal(idle.audio.plays,1);
});
test('pending queue is single flight and stop cancels even a late response',async()=>{
  let resolve,signal,calls=0;
  const {radio,audio,tracks}=make({fetch:(_url,opts)=>{calls++;signal=opts?.signal;return new Promise(r=>resolve=r);}});
  const first=radio.play();const second=radio.play();assert.equal(calls,1);await second;
  radio.stop();assert.equal(signal.aborted,true);
  resolve({ok:true,json:async()=>({tracks})});await first;
  assert.equal(audio.plays,0);assert.equal(audio.src,'');assert.equal(radio.state.busy,false);
});
test('queue failures and unsafe URLs are visible without starting media',async()=>{
  for(const response of [{ok:false},{ok:true,json:async()=>({tracks:[]})},{ok:true,json:async()=>({tracks:[{id:'1',stream:'https://evil/1'}]})}]) {
    const {radio,audio}=make({fetch:async()=>response});await radio.play();
    assert.ok(radio.state.error);assert.equal(radio.state.busy,false);assert.equal(audio.plays,0);
  }
});
test('ended advances only after Play; media errors stop rather than skip forever',async()=>{
  const {radio,audio}=make();audio.dispatchEvent(new Event('ended'));assert.equal(audio.plays,0);
  await radio.play();audio.dispatchEvent(new Event('ended'));await new Promise(setImmediate);
  assert.equal(audio.src,'/radio/stream/2');
  audio.dispatchEvent(new Event('error'));assert.equal(radio.state.playing,false);assert.ok(radio.state.error);
});
test('persistent media card survives widget replacement and internal navigation',async()=>{
  const {JSDOM}=require('jsdom');
  const dom=new JSDOM('<div class="page-columns"><div class="page-column"><div class="media-ops-widget">old</div></div></div>',{url:'https://test/media',runScripts:'outside-only'});
  const w=dom.window;let plays=0,requests=0;
  w.HTMLMediaElement.prototype.pause=function(){};
  w.HTMLMediaElement.prototype.load=function(){};
  w.HTMLMediaElement.prototype.play=async function(){plays++;};
  w.fetch=async()=>{requests++;return {ok:true,json:async()=>({tracks:[{id:'1',stream:'/radio/stream/1',title:'<script>bad</script>',poster:'https://evil/poster'}]})};};
  w.eval(fs.readFileSync(source,'utf8'));w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
  const card=w.document.querySelector('#plex-radio');assert.ok(card);
  assert.ok(card.closest('.page-column'),'full radio retains original Media column layout');
  assert.equal(card.closest('.media-ops-widget'),null);assert.equal(requests,0);assert.equal(plays,0);
  card.querySelector('[data-action="play"]').click();await new Promise(setImmediate);
  assert.equal(plays,1);assert.equal(card.querySelector('.pr-title').textContent,'<script>bad</script>');assert.equal(card.querySelector('img').hasAttribute('src'),false);
  // Fixed fixture markup, never library/user-controlled content.
  w.document.querySelector('.media-ops-widget').outerHTML='<div class="media-ops-widget">new</div>';
  w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));
  assert.equal(w.document.querySelector('#plex-radio'),card);
  w.history.pushState({},'', '/hardware-workloads');w.document.dispatchEvent(new w.Event('construct:route'));await new Promise(setImmediate);
  assert.equal(card.isConnected,true);assert.equal(w.document.querySelector('#plex-radio-audio').hasAttribute('src'),true);
  assert.equal(card.classList.contains('pr-mini'),true);
  assert.equal(card.querySelector('[data-action="shuffle"]').hasAttribute('aria-pressed'),false);
  card.querySelector('[data-action="play"]').click();assert.equal(card.querySelector('[data-action="play"]').textContent,'Play');
  w.dispatchEvent(new w.Event('pagehide'));w.close();
});
function mountControls(t) {
  const {JSDOM}=require('jsdom');
  const dom=new JSDOM('<div class="page-columns"><div class="page-column"></div></div>',{url:'https://test/media',runScripts:'outside-only'});
  const w=dom.window;let plays=0,requests=0;
  w.HTMLMediaElement.prototype.pause=function(){};
  w.HTMLMediaElement.prototype.load=function(){};
  w.HTMLMediaElement.prototype.play=async function(){plays++;};
  w.fetch=async()=>{requests++;return {ok:true,json:async()=>({tracks:[{id:'1',stream:'/radio/stream/1'},{id:'2',stream:'/radio/stream/2'}]})};};
  w.eval(fs.readFileSync(source,'utf8'));
  t.after(()=>{w.dispatchEvent(new w.Event('pagehide'));w.close();});
  const card=w.document.querySelector('#plex-radio');
  return {w,card,audio:w.document.querySelector('#plex-radio-audio'),plays:()=>plays,requests:()=>requests};
}
test('labeled seek control tracks media time and seeks without starting audio',async(t)=>{
  const {w,card,audio,plays,requests}=mountControls(t);
  const seek=card.querySelector('#pr-seek');
  assert.ok(seek,'seek slider missing');
  assert.equal(seek.type,'range');assert.equal(card.querySelector('label[for="pr-seek"]').textContent,'Seek');
  assert.equal(seek.disabled,true);assert.equal(plays(),0);assert.equal(requests(),0);
  card.querySelector('[data-action="play"]').click();await new Promise(setImmediate);
  card.querySelector('[data-action="play"]').click();
  Object.defineProperty(audio,'duration',{configurable:true,value:185});
  audio.currentTime=65;audio.dispatchEvent(new w.Event('loadedmetadata'));audio.dispatchEvent(new w.Event('timeupdate'));
  assert.equal(seek.disabled,false);assert.equal(seek.max,'185');assert.equal(seek.value,'65');
  assert.equal(card.querySelector('.pr-time').textContent,'1:05 / 3:05');
  assert.equal(seek.getAttribute('aria-valuetext'),'1:05 of 3:05');
  seek.value='90';seek.dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal(audio.currentTime,90);assert.equal(plays(),1);
  w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));
  assert.equal(card.querySelector('#pr-seek'),seek);assert.equal(seek.value,'90');
  card.querySelector('[data-action="next"]').click();await new Promise(setImmediate);
  assert.equal(seek.disabled,true);assert.equal(card.querySelector('.pr-time').textContent,'0:00 / 0:00');
  Object.defineProperty(audio,'duration',{configurable:true,value:Infinity});audio.dispatchEvent(new w.Event('durationchange'));
  assert.equal(seek.disabled,true);
});
test('labeled volume slider changes audio and survives widget refresh without autoplay',(t)=>{
  const {w,card,audio,plays,requests}=mountControls(t);
  const volume=card.querySelector('#pr-volume');assert.ok(volume,'volume slider missing');
  assert.equal(volume.type,'range');assert.equal(card.querySelector('label[for="pr-volume"]').textContent,'Volume');
  assert.equal(volume.min,'0');assert.equal(volume.max,'100');assert.equal(volume.value,'100');
  volume.value='27';volume.dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal(audio.volume,0.27);assert.equal(volume.getAttribute('aria-valuetext'),'27%');
  w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));
  assert.equal(card.querySelector('#pr-volume'),volume);assert.equal(volume.value,'27');
  audio.volume=0;audio.dispatchEvent(new w.Event('volumechange'));assert.equal(volume.value,'0');
  assert.equal(plays(),0);assert.equal(requests(),0);
});
test('card stylesheet follows theme tokens and accessible responsive controls',()=>{
  const cssPath=`${__dirname}/plex-radio.css`;assert.ok(fs.existsSync(cssPath));
  const css=fs.readFileSync(cssPath,'utf8');
  assert.match(css,/data-action=previous[^}]+font-size:24px/);
  assert.ok(css.includes('.pr-mini'));
  for(const token of ['--color-primary','--color-text-base','--color-text-highlight','--color-text-subdue',':focus-visible','44px','@media']) assert.ok(css.includes(token),token);
});
test('sliders have compact responsive layout and visible keyboard focus',()=>{
  const css=fs.readFileSync(`${__dirname}/plex-radio.css`,'utf8');
  for (const rule of ['.pr-sliders{','.pr-seek{','.pr-volume{','.pr-sliders input[type=range]:focus-visible{','.pr-time{']) assert.ok(css.includes(rule),`missing ${rule}`);
  assert.match(css,/@media[\s\S]*\.pr-sliders\{[^}]*grid-template-columns:minmax\(0,1fr\) 100px/);
});
test('radio exists and never loads media or queue until explicit Play',()=>{
  assert.ok(fs.existsSync(source),'Plex radio implementation missing');
  const {radio,audio,calls}=make();
  assert.equal(radio.state.shuffle,true);
  assert.equal(audio.preload,'none');
  assert.equal(audio.src,'');assert.equal(audio.plays,0);assert.equal(calls(),0);
});
