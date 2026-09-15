/* Plex Radio owns its audio element; native widget polling never replaces it. */
(function () {
  'use strict';
  function createRadio({audio, fetch, random = Math.random, changed = () => {}}) {
    audio.preload = 'none';
    const state = {shuffle:true, tracks:[], index:-1, history:[], playing:false, busy:false, error:'', currentTime:0, duration:0};
    const emit = () => changed(state);
    let generation=0, controller=null;
    async function play() {
      if (state.busy || state.playing) return;
      const token=++generation;
      controller=new AbortController();state.busy=true;state.error='';emit();
      try {
        if (!state.tracks.length) {
          const response = await fetch('/radio/queue',{signal:controller.signal,credentials:'same-origin'});
          if (!response.ok) throw new Error('Music library unavailable. Try Play again.');
          const data=await response.json();
          if (token!==generation) return;
          const tracks=Array.isArray(data.tracks) ? data.tracks.filter(t => t && /^\d+$/.test(String(t.id)) && t.stream===`/radio/stream/${t.id}`) : [];
          if (!tracks.length) throw new Error('No playable music is available.');
          state.tracks=tracks;
          state.index = state.shuffle ? Math.floor(random()*state.tracks.length) : 0;
        }
        if (!audio.src) audio.src = state.tracks[state.index].stream;
        await audio.play();
        if (token!==generation) return;
        state.playing=true;
      } catch (error) {
        if (token!==generation) return;
        audio.pause();state.playing=false;
        state.error=error.name==='NotAllowedError' ? 'Playback blocked. Press Play to retry.' : (error.message || 'Playback failed. Try Next or Play.');
      } finally {
        if (token===generation) {state.busy=false;emit();}
      }
    }
    function pause() {generation++;controller?.abort();audio.pause();state.playing=false;state.busy=false;emit();}
    function stop() {pause();audio.removeAttribute('src');audio.load();}
    async function select(index) {
      const resume=state.playing;audio.pause();state.playing=false;
      state.index=index;state.currentTime=0;state.duration=0;audio.src=state.tracks[index].stream;emit();
      if (resume) await play();
    }
    async function next() {
      if (state.index<0 || state.busy) return;
      state.history.push(state.index);
      const count=state.tracks.length;
      const offset=state.shuffle && count>1 ? 1+Math.floor(random()*(count-1)) : 1;
      await select((state.index+offset)%count);
    }
    async function previous() {
      if (state.busy || !state.history.length) return;
      await select(state.history.pop());
    }
    function seek(value) {
      if (!state.duration || !Number.isFinite(value)) return;
      audio.currentTime=Math.max(0,Math.min(value,state.duration));
      state.currentTime=audio.currentTime;emit();
    }
    for (const event of ['loadedmetadata','durationchange','timeupdate','emptied']) {
      audio.addEventListener(event,()=>{
        state.duration=Number.isFinite(audio.duration) && audio.duration>0 ? audio.duration : 0;
        state.currentTime=state.duration ? Math.max(0,Math.min(audio.currentTime || 0,state.duration)) : 0;
        emit();
      });
    }
    async function shuffle() {
      if (state.busy) return;
      if (state.index<0) return play();
      await next();
      if (!state.playing) await play();
    }
    audio.addEventListener('ended', () => {if (state.playing) void next();});
    audio.addEventListener('error', () => {
      if (!audio.src) return;
      pause();state.error='This track could not be played. Try Next or Play.';emit();
    });
    return {state,play,pause,stop,next,previous,shuffle,seek};
  }
  if (typeof module !== 'undefined') module.exports = {createRadio};
  if (typeof window === 'undefined' || window.__plexRadioInstalled) return;
  window.__plexRadioInstalled=true;
  let card=null, radio=null;
  const onMedia=() => /^\/media\/?$/.test(window.location.pathname);
  function placeCard() {
    const target=onMedia() ? document.querySelector('.page-columns > .page-column') : document.body;
    if(target && card.parentNode!==target) {if(onMedia())target.prepend(card);else target.append(card);}
    card.classList.toggle('pr-mini',!onMedia());
  }
  function mount() {
    if (card) {placeCard();return;}
    if (!onMedia()) return;
    const column=document.querySelector('.page-columns > .page-column');
    if (!column) return;
    card=document.createElement('section');card.id='plex-radio';card.className='plex-radio';
    card.setAttribute('aria-label','Plex Radio');
    // Static template only. All library metadata below is assigned via textContent.
    card.innerHTML=`<header class="pr-heading"><span>PLEX RADIO</span><span class="pr-mode">YOUR MUSIC · ON SHUFFLE</span></header>
      <div class="pr-body"><div class="pr-art"><span aria-hidden="true">♫</span><img alt="" hidden></div>
      <div class="pr-info"><h3 class="pr-title">Let your library play</h3><p class="pr-artist">A little discovery, from your own collection.</p><p class="pr-album"></p>
      <div class="pr-controls"><button type="button" data-action="previous" aria-label="Previous track">⏮</button><button type="button" data-action="play" class="pr-play">Play</button><button type="button" data-action="next" aria-label="Next track">⏭</button><button type="button" data-action="shuffle" title="Play a random track">Shuffle</button></div></div></div>
      <div class="pr-sliders"><div class="pr-seek"><label for="pr-seek">Seek</label><input id="pr-seek" type="range" min="0" max="0" step="1" value="0" disabled><span class="pr-time">0:00 / 0:00</span></div><div class="pr-volume"><label for="pr-volume">Volume</label><input id="pr-volume" type="range" min="0" max="100" step="1" value="100" aria-valuetext="100%"></div></div>
      <p class="pr-status" role="status" aria-live="polite">Press Play to begin. Audio stays off until you do.</p>`;
    // Never reparent a playing media element: even a same-document DOM move
    // can reset browser playback. Only the controls move to the mini player.
    const audio=document.createElement('audio');audio.id='plex-radio-audio';audio.hidden=true;audio.preload='none';
    document.body.append(audio);placeCard();
    const root=card;
    const get=selector=>root.querySelector(selector);
    const clock=value=>`${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`;
    function render(state) {
      const seek=get('#pr-seek'), current=clock(state.currentTime), duration=clock(state.duration);
      seek.disabled=!state.duration;seek.max=String(state.duration);seek.value=String(state.currentTime);
      seek.setAttribute('aria-valuetext',`${current} of ${duration}`);
      get('.pr-time').textContent=`${current} / ${duration}`;
      const track=state.tracks[state.index];
      if (track) {
        get('.pr-title').textContent=track.title || 'Untitled track';
        get('.pr-artist').textContent=track.artist || 'Unknown artist';
        get('.pr-album').textContent=[track.album,track.codec?.toUpperCase()].filter(Boolean).join(' · ');
        const image=get('img'), poster=typeof track.poster==='string' && /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(track.poster) ? track.poster : '';
        image.hidden=!poster;
        if (poster) {if(image.getAttribute('src')!==poster) image.src=poster;} else image.removeAttribute('src');
      }
      const play=get('[data-action="play"]');
      play.textContent=state.busy ? 'Cancel' : state.playing ? 'Pause' : 'Play';
      play.setAttribute('aria-label',state.busy ? 'Cancel loading' : play.textContent);
      get('[data-action="previous"]').disabled=state.busy || !state.history.length;
      get('[data-action="next"]').disabled=state.busy || state.index<0;
      get('[data-action="shuffle"]').disabled=state.busy;
      get('.pr-mode').textContent=state.shuffle ? 'YOUR MUSIC · ON SHUFFLE' : 'YOUR MUSIC · IN ORDER';
      get('.pr-status').textContent=state.error || (state.busy ? 'Tuning in…' : state.playing ? 'Playing from your Plex library' : track ? 'Paused · ready when you are' : 'Press Play to begin. Audio stays off until you do.');
      root.classList.toggle('pr-error',Boolean(state.error));root.classList.toggle('pr-playing',state.playing);
    }
    const player=createRadio({audio,fetch:window.fetch.bind(window),changed:render});radio=player;render(player.state);
    get('#pr-seek').addEventListener('input',event=>player.seek(Number(event.target.value)));
    function renderVolume() {
      const volume=get('#pr-volume'), percent=Math.round(audio.volume*100);
      volume.value=String(percent);volume.setAttribute('aria-valuetext',`${percent}%`);
    }
    get('#pr-volume').addEventListener('input',event=>{audio.volume=Number(event.target.value)/100;renderVolume();});
    audio.addEventListener('volumechange',renderVolume);
    renderVolume();
    root.addEventListener('click',event=>{
      const button=event.target.closest('button[data-action]');if (!button) return;
      const action=button.dataset.action;
      if (action==='play') {if(player.state.playing || player.state.busy) player.pause();else void player.play();}
      else if(action==='shuffle') player.shuffle();
      else if(action==='next') void player.next();
      else if(action==='previous') void player.previous();
    });
    get('img').addEventListener('error',()=>{get('img').hidden=true;});
  }
  document.addEventListener('DOMContentLoaded',mount);
  document.addEventListener('dynacat:widget-updated',mount);
  window.addEventListener('pagehide',()=>{radio?.stop();observer.disconnect();});
  window.addEventListener('popstate',mount);
  window.addEventListener('pageshow',()=>{observer.observe(document.documentElement,{childList:true,subtree:true});mount();});
  document.addEventListener('construct:route',mount);
  for (const method of ['pushState','replaceState']) {
    const original=window.history[method];
    window.history[method]=function(...args) {const result=original.apply(this,args);mount();return result;};
  }
  // Reattach only if the page layout itself is replaced, not on normal widget refreshes.
  const observer=new MutationObserver(()=>{if (!card?.isConnected) mount();});
  observer.observe(document.documentElement,{childList:true,subtree:true});
  mount();
})();
