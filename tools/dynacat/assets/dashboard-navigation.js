/* Dynacat 3.0 route lifecycle bridge. Installed once from its existing page
 * module (gateway.conf), so native initializers/pollers and the single SSE
 * connection stay authoritative. Cache at most these three native DOM trees:
 * revisits retain bound controls, rather than accumulating listeners/timers.
 * The audio stays in document.body and is never detached or reconstructed. */
export function installNavigation({pageData, activate}) {
  if (window.constructNavigate) return;
  const routes=new Map([['/hardware-workloads','Hardware & Workloads'],['/media','Media'],['/endpoints-services','Endpoints & Services']]);
  const normalize=path=>path==='/' ? '/hardware-workloads' : path.replace(/\/$/,'');
  let current=normalize(location.pathname), generation=0, pending=null;
  const pages=new Map();
  const page=document.querySelector('#page'), content=document.querySelector('#page-content');
  if (!page || !content || !routes.has(current)) return;
  const error=document.createElement('p');error.className='cc-navigation-error';error.setAttribute('role','alert');error.hidden=true;page.before(error);
  const mark=()=>{
    for(const link of document.querySelectorAll('a.nav-item[href]')) {
      const selected=normalize(new URL(link.href).pathname)===current;
      link.classList.toggle('nav-item-current',selected);
      if(selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
    }
    const select=document.querySelector('.cc-page-select');if(select)select.value=current;
  };
  async function navigate(path,{historyMode='push'}={}) {
    const url=new URL(path,location.href), next=normalize(url.pathname);
    if(url.origin!==location.origin || !routes.has(next) || url.search || url.hash) return false;
    if(!page.classList.contains('content-ready')) return false;
    if(next===current) {pending?.abort();pending=null;generation++;page.setAttribute('aria-busy','false');error.hidden=true;mark();return true;}
    const token=++generation;pending?.abort();pending=new AbortController();
    const controller=pending;
    page.setAttribute('aria-busy','true');error.hidden=true;
    try {
      let destination=pages.get(next), first=!destination;
      if(first) {
        const response=await fetch(`${pageData.baseURL || ''}/api/pages/${next.slice(1)}/content/`,{credentials:'same-origin',signal:controller.signal});
        if(!response.ok || response.headers.get('X-Dynacat-Cache-Building')==='true') throw new Error('Page unavailable');
        const html=await response.text();
        if(token!==generation)return true;
        const template=document.createElement('template');template.innerHTML=html;
        if(!template.content.querySelector('.page-columns'))throw new Error('Invalid dashboard content');
        // No scripts are executed from fetched pages. All dashboard assets are
        // installed once; their public widget event binds new native content.
        destination=template.content;
      }
      if(token!==generation)return true;
      const previous=document.createDocumentFragment();
      while(content.firstChild)previous.append(content.firstChild);
      pages.set(current,previous);
      content.append(destination);pages.set(next,destination);
      current=next;pageData.slug=next.slice(1);
      if(historyMode==='push')history.pushState({},'',next);
      document.title=routes.get(next);const heading=page.querySelector('h1');if(heading)heading.textContent=routes.get(next);
      mark();
      activate(first);
      document.dispatchEvent(new CustomEvent('construct:route'));
      document.dispatchEvent(new CustomEvent('dynacat:widget-updated'));
      window.scrollTo({top:0,behavior:'instant'});
      return true;
    } catch(e) {
      if(token!==generation || e.name==='AbortError')return true;
      error.textContent='This dashboard page could not be loaded. Select it again to retry; your music is still available.';error.hidden=false;
      if(historyMode==='pop')history.replaceState({},'',current);
      mark();return true;
    } finally {if(token===generation){pending=null;page.setAttribute('aria-busy','false');}}
  }
  window.constructNavigate=navigate;
  document.addEventListener('click',event=>{
    const link=event.target.closest?.('a[href]');
    if(!link || event.defaultPrevented || event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.hasAttribute('download') || (link.target && link.target!=='_self'))return;
    const url=new URL(link.href,location.href);
    if(url.origin!==location.origin || !routes.has(normalize(url.pathname)) || url.search || url.hash || !page.classList.contains('content-ready'))return;
    event.preventDefault();void navigate(url.href);
  });
  document.addEventListener('change',event=>{
    if(!event.target.matches?.('.cc-page-select'))return;
    event.stopImmediatePropagation();void navigate(event.target.value);
  },true);
  // Native Dynacat's chord handler assigns location.href. Handle only these
  // dashboard chords first; leave all editing keys and other shortcuts alone.
  let chordUntil=0;
  window.addEventListener('keydown',event=>{
    if(event.ctrlKey || event.metaKey || event.altKey || event.target.closest?.('input,textarea,select,[contenteditable="true"]'))return;
    const key=event.key.toLowerCase(), paths={h:'/hardware-workloads',m:'/media',e:'/endpoints-services'};
    if(key==='d'){chordUntil=Date.now()+1500;event.stopImmediatePropagation();return;}
    if(chordUntil>Date.now() && paths[key]) {event.preventDefault();event.stopImmediatePropagation();void navigate(paths[key]);}
    chordUntil=0;
  },true);
  window.addEventListener('popstate',()=>void navigate(location.href,{historyMode:'pop'}));
  mark();
}
