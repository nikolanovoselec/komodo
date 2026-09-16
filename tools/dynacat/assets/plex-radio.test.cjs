// Run: npm install --prefix /tmp/plex-radio-test jsdom --no-audit --no-fund
// NODE_PATH=/tmp/plex-radio-test/node_modules node --test assets/plex-radio.test.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = `${__dirname}/plex-radio.js`;
function make(options={}) {
  const {createRadio} = require(source);
  const audio = new EventTarget();
  Object.assign(audio, {paused:true, src:'', plays:0, pause(){this.paused=true;this.dispatchEvent(new Event('pause'));}, load(){}, removeAttribute(){this.src='';}, async play(){this.plays++; this.paused=false;this.dispatchEvent(new Event('playing'));}});
  const tracks = [1,2,3].map(id => ({id:String(id), title:`Track ${id}`, artist:'Artist', album:'Album',stream:`/radio/stream/${id}`}));
  let calls=0;
  const radio = createRadio({audio, fetch:async()=>{calls++;return {ok:true,json:async()=>({tracks})};}, random:()=>0, ...options});
  return {radio,audio,tracks,calls:()=>calls};
}
test('server preview seeds metadata without requests and Play keeps it first in the full queue',async()=>{
  const preview={id:'99',title:'Server choice',artist:'Artist',album:'Album',poster:'data:image/jpeg;base64,/9g=',stream:'/radio/stream/99'};
  const {radio,audio,calls}=make({preview});
  assert.equal(radio.state.tracks[radio.state.index]?.id,'99');
  assert.equal(audio.src,'');assert.equal(audio.plays,0);assert.equal(calls(),0);
  await radio.play();
  assert.equal(audio.src,'/radio/stream/99');assert.equal(calls(),1);
  assert.deepEqual(radio.state.tracks.map(t=>t.id),['99','1','2','3']);
  await radio.next();assert.equal(audio.src,'/radio/stream/1');
});
test('Shuffle from server preview fetches the full queue and starts a different track only',async()=>{
  const {radio,audio,calls}=make({preview:{id:'99',stream:'/radio/stream/99'}});
  await radio.shuffle();
  assert.equal(calls(),1);assert.equal(audio.plays,1);assert.equal(audio.src,'/radio/stream/1');
  await radio.previous();assert.equal(audio.src,'/radio/stream/99');
});
test('late native preview can fill only idle state, never pending or selected playback',async()=>{
  const {radio,audio,calls}=make();
  assert.equal(typeof radio.setPreview,'function');
  radio.setPreview({id:'99',stream:'/radio/stream/99'});
  assert.equal(radio.state.tracks[radio.state.index].id,'99');
  radio.setPreview({id:'88',stream:'/radio/stream/88'});
  assert.equal(radio.state.tracks[radio.state.index].id,'99');
  assert.equal(audio.src,'');assert.equal(calls(),0);
});
test('failed server preview remains an honest idle error until explicit Play retries',async()=>{
  const {radio,audio,calls}=make({previewError:'Radio upstream unavailable'});
  assert.equal(radio.state.error,'Radio upstream unavailable');
  assert.equal(calls(),0);assert.equal(audio.src,'');
  await radio.play();assert.equal(radio.state.error,'');assert.equal(audio.plays,1);
});
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
test('native end-of-track pause hides immediately but still advances the queue',async()=>{
  const {radio,audio}=make();await radio.play();
  audio.ended=true;audio.pause();assert.equal(radio.state.playing,false);
  audio.dispatchEvent(new Event('ended'));await new Promise(setImmediate);
  assert.equal(audio.src,'/radio/stream/2');assert.equal(audio.plays,2);
});
test('ended advances only after Play; media errors stop rather than skip forever',async()=>{
  const {radio,audio}=make();audio.dispatchEvent(new Event('ended'));assert.equal(audio.plays,0);
  await radio.play();audio.dispatchEvent(new Event('ended'));await new Promise(setImmediate);
  assert.equal(audio.src,'/radio/stream/2');
  audio.dispatchEvent(new Event('error'));assert.equal(radio.state.playing,false);assert.ok(radio.state.error);
});
test('native server preview is enhanced in place and polling cannot replace current metadata',async(t)=>{
  const {JSDOM}=require('jsdom');
  // Same controls as the real native template; data text is intentionally not HTML.
  const fixture=fs.readFileSync(`${__dirname}/../config/dynacat.yml`,'utf8');
  const template=fixture.slice(fixture.indexOf('<section class="plex-radio pr-server-preview"'),fixture.indexOf('</section>',fixture.indexOf('<section class="plex-radio pr-server-preview"'))+10);
  const html=template.replace(/\{\{[^}]*\}\}/g,'').replace('data-preview-id=""','data-preview-id="99"').replace('data-preview-codec=""','data-preview-codec="mp3"');
  const dom=new JSDOM(`<div class="page-columns"><div class="page-column"><div class="plex-radio-widget">${html}</div></div></div>`,{url:'https://test/media',runScripts:'outside-only'});
  const w=dom.window;let requests=0,plays=0;
  const native=w.document.querySelector('.pr-server-preview');
  native.querySelector('.pr-title').textContent='Server chosen song';native.querySelector('.pr-artist').textContent='Server artist';native.querySelector('.pr-album').textContent='Server album';
  native.querySelector('img').setAttribute('src','data:image/jpeg;base64,/9g=');
  w.HTMLMediaElement.prototype.pause=function(){Object.defineProperty(this,'paused',{configurable:true,value:true});this.dispatchEvent(new w.Event('pause'));};w.HTMLMediaElement.prototype.load=function(){};
  w.HTMLMediaElement.prototype.play=async function(){plays++;Object.defineProperty(this,'paused',{configurable:true,value:false});this.dispatchEvent(new w.Event('playing'));};
  w.fetch=async()=>{requests++;return {ok:true,json:async()=>({tracks:[{id:'1',stream:'/radio/stream/1'}]})};};
  w.eval(fs.readFileSync(source,'utf8'));
  t.after(()=>{w.dispatchEvent(new w.Event('pagehide'));w.close();});
  const card=w.document.querySelector('#plex-radio'),audio=w.document.querySelector('#plex-radio-audio');
  assert.equal(card,native);assert.equal(card.querySelector('.pr-title').textContent,'Server chosen song');
  assert.equal(card.querySelector('[data-action="next"]').disabled,true,'preview cannot skip until full queue loads');
  assert.ok(w.document.documentElement.classList.contains('pr-enhanced'),'native polling shell must be hidden after adoption');
  assert.equal(card.querySelector('img').getAttribute('src'),'data:image/jpeg;base64,/9g=');
  assert.equal(requests,0);assert.equal(plays,0);assert.equal(audio.hasAttribute('src'),false);
  const poll=w.document.querySelector('.plex-radio-widget');poll.innerHTML=html;
  w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));await new Promise(setImmediate);
  assert.equal(w.document.querySelectorAll('.plex-radio').length,1);
  assert.equal(card.querySelector('.pr-title').textContent,'Server chosen song');
  card.querySelector('[data-action="play"]').click();await new Promise(setImmediate);
  assert.equal(plays,1);assert.equal(audio.getAttribute('src'),'/radio/stream/99');
});
test('persistent media card survives widget replacement and internal navigation',async()=>{
  const {JSDOM}=require('jsdom');
  const dom=new JSDOM('<div class="page-columns"><div class="page-column"><div class="media-ops-widget">old</div></div></div>',{url:'https://test/media',runScripts:'outside-only'});
  const w=dom.window;let plays=0,requests=0;
  w.HTMLMediaElement.prototype.pause=function(){Object.defineProperty(this,'paused',{configurable:true,value:true});this.dispatchEvent(new w.Event('pause'));};
  w.HTMLMediaElement.prototype.load=function(){};
  w.HTMLMediaElement.prototype.play=async function(){plays++;Object.defineProperty(this,'paused',{configurable:true,value:false});this.dispatchEvent(new w.Event('playing'));};
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
  w.HTMLMediaElement.prototype.pause=function(){Object.defineProperty(this,'paused',{configurable:true,value:true});this.dispatchEvent(new w.Event('pause'));};
  w.HTMLMediaElement.prototype.load=function(){};
  w.HTMLMediaElement.prototype.play=async function(){plays++;Object.defineProperty(this,'paused',{configurable:true,value:false});this.dispatchEvent(new w.Event('playing'));};
  w.fetch=async()=>{requests++;return {ok:true,json:async()=>({tracks:[{id:'1',stream:'/radio/stream/1'},{id:'2',stream:'/radio/stream/2'}]})};};
  w.eval(fs.readFileSync(source,'utf8'));
  t.after(()=>{w.dispatchEvent(new w.Event('pagehide'));w.close();});
  const card=w.document.querySelector('#plex-radio');
  return {w,card,audio:w.document.querySelector('#plex-radio-audio'),plays:()=>plays,requests:()=>requests};
}
test('idle preview never becomes a mini player through navigation or refresh',(t)=>{
  const {w,card,audio,plays,requests}=mountControls(t);
  const preview=card.cloneNode(true);preview.removeAttribute('id');preview.classList.add('pr-server-preview');preview.dataset.previewId='99';
  preview.querySelector('.pr-title').textContent='Populated preview';
  w.document.querySelector('.page-column').append(preview);
  w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));
  for (const route of ['/hardware-workloads','/networking','/endpoints-services']) {
    w.history.pushState({},'',route);
    w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));
    assert.equal(card.hidden,true,'idle populated preview must stay hidden off Media');
  }
  w.history.pushState({},'','/media');assert.equal(card.hidden,false);
  assert.equal(plays(),0);assert.equal(requests(),0);assert.equal(audio.hasAttribute('src'),false);
});
test('mini visibility follows actual audio lifecycle, not play intent or promise resolution',async(t)=>{
  const {w,card,audio}=mountControls(t);
  Object.defineProperty(audio,'paused',{configurable:true,writable:true,value:true});
  let resolve;
  audio.play=()=>{audio.paused=false;return new Promise(r=>resolve=r);};
  audio.pause=()=>{audio.paused=true;audio.dispatchEvent(new w.Event('pause'));};
  card.querySelector('[data-action="play"]').click();await new Promise(setImmediate);
  w.history.pushState({},'','/networking');assert.equal(card.hidden,true,'pending initial play hidden');
  resolve();await new Promise(setImmediate);assert.equal(card.hidden,true,'resolved promise without playing event hidden');
  audio.dispatchEvent(new w.Event('playing'));assert.equal(card.hidden,false,'playing event reveals mini');
  audio.dispatchEvent(new w.Event('waiting'));assert.equal(card.hidden,false,'active buffering can retain mini');
  audio.pause();assert.equal(card.hidden,true,'native pause immediately hides mini');
  audio.dispatchEvent(new w.Event('playing'));assert.equal(card.hidden,true,'stale playing event while paused ignored');
  audio.paused=false;audio.dispatchEvent(new w.Event('playing'));assert.equal(card.hidden,false);
  audio.dispatchEvent(new w.Event('ended'));assert.equal(card.hidden,true,'ended hides before next track starts');
  await new Promise(setImmediate);
  audio.dispatchEvent(new w.Event('error'));assert.equal(card.hidden,true);
  w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));assert.equal(card.hidden,true);
  w.history.pushState({},'','/media');assert.equal(card.hidden,false);
});
test('rejected playback never reveals a mini player',async(t)=>{
  const {w,card,audio}=mountControls(t);
  audio.play=async()=>{throw new w.DOMException('blocked','NotAllowedError');};
  card.querySelector('[data-action="play"]').click();
  w.history.pushState({},'','/networking');await new Promise(setImmediate);
  assert.equal(card.hidden,true);assert.match(card.querySelector('.pr-status').textContent,/blocked/);
});
test('late native render seeds the idle fallback without a queue request',async(t)=>{
  const {w,card,audio,plays,requests}=mountControls(t);
  const preview=card.cloneNode(true);preview.removeAttribute('id');preview.classList.add('pr-server-preview');preview.dataset.previewId='99';
  preview.querySelector('.pr-title').textContent='Late server song';
  w.document.querySelector('.page-column').append(preview);
  await new Promise(setImmediate);
  assert.equal(card.querySelector('.pr-title').textContent,'Late server song');
  assert.equal(w.document.querySelectorAll('.plex-radio').length,1);
  assert.equal(plays(),0);assert.equal(requests(),0);assert.equal(audio.hasAttribute('src'),false);
});
test('dismiss hides only the mini player, preserves audio and stays dismissed until Media returns',async(t)=>{
  const {w,card,audio,plays}=mountControls(t);
  const dismiss=card.querySelector('[data-action="dismiss"]');
  assert.ok(dismiss,'mini-player dismiss button missing');
  assert.equal(dismiss.getAttribute('aria-label'),'Dismiss mini player');
  assert.equal(dismiss.hidden,true);
  card.querySelector('[data-action="play"]').click();await new Promise(setImmediate);
  const src=audio.src;let pauses=0;audio.pause=()=>{pauses++;};
  w.history.pushState({},'', '/hardware-workloads');
  assert.equal(dismiss.hidden,false);dismiss.click();
  assert.equal(card.hidden,true);assert.equal(audio.src,src);assert.equal(pauses,0);assert.equal(plays(),1);
  w.document.dispatchEvent(new w.Event('dynacat:widget-updated'));
  w.history.pushState({},'', '/endpoints-services');assert.equal(card.hidden,true);
  w.history.pushState({},'', '/media');assert.equal(card.hidden,false);assert.equal(dismiss.hidden,true);
  w.history.pushState({},'', '/hardware-workloads');assert.equal(card.hidden,false);
});
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
  assert.ok(css.includes('.pr-enhanced .plex-radio-widget{display:none}'));
  assert.ok(css.includes('.plex-radio-widget>.widget-header{display:none}'));
  for(const token of ['--color-primary','--color-text-base','--color-text-highlight','--color-text-subdue',':focus-visible','44px','@media']) assert.ok(css.includes(token),token);
});
test('sliders have compact responsive layout and visible keyboard focus',()=>{
  const css=fs.readFileSync(`${__dirname}/plex-radio.css`,'utf8');
  for (const rule of ['.pr-sliders{','.pr-seek{','.pr-volume{','.pr-sliders input[type=range]:focus-visible{','.pr-time{']) assert.ok(css.includes(rule),`missing ${rule}`);
  assert.match(css,/@media[\s\S]*\.pr-sliders\{[^}]*grid-template-columns:minmax\(0,1fr\) 100px/);
});
test('radio script cache key matches its exact content digest',()=>{
  const digest=require('node:crypto').createHash('sha256').update(fs.readFileSync(source)).digest('hex').slice(0,12);
  assert.ok(fs.readFileSync(`${__dirname}/../config/dynacat.yml`,'utf8').includes(`plex-radio.js?v=${digest}`));
});
test('radio exists and never loads media or queue until explicit Play',()=>{
  assert.ok(fs.existsSync(source),'Plex radio implementation missing');
  const {radio,audio,calls}=make();
  assert.equal(radio.state.shuffle,true);
  assert.equal(audio.preload,'none');
  assert.equal(audio.src,'');assert.equal(audio.plays,0);assert.equal(calls(),0);
});
