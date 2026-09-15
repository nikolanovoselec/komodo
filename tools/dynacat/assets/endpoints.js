/* Local-only launcher filtering and fixed legacy-route aliases. No network calls. */
(() => {
 const aliases={'/command-center':'/','/media-ops':'/media','/directory':'/endpoints-services','/news':'/endpoints-services#news-desk'};
 if(aliases[location.pathname]){location.replace(aliases[location.pathname]);return;}
 const boot=()=>{
 const root=document.querySelector('.es-launcher');if(!root||root.dataset.ready)return;root.dataset.ready='true';
 const input=root.querySelector('#endpoint-search'),items=[...root.querySelectorAll('.es-endpoint')],groups=[...root.querySelectorAll('.es-group')];
 let category='all';
 const filter=()=>{
  const query=input.value.trim().toLocaleLowerCase();let visible=0;
  for(const group of groups){let count=0;for(const item of group.querySelectorAll('.es-endpoint')){
   const show=(category==='all'||category===group.dataset.esGroup)&&item.dataset.esSearch.toLocaleLowerCase().includes(query);
   item.hidden=!show;if(show){count++;visible++;}
  }group.hidden=count===0;}
  root.querySelector('.es-result-count').textContent=visible+' / '+items.length+' endpoints';root.querySelector('.es-empty').hidden=visible!==0;
 };
 input.addEventListener('input',filter);
 root.querySelectorAll('[data-es-category]').forEach(button=>button.addEventListener('click',()=>{
  category=button.dataset.esCategory;root.querySelectorAll('[data-es-category]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));filter();
 }));
 document.addEventListener('keydown',event=>{
  if(event.key==='/'&&!event.ctrlKey&&!event.metaKey&&!event.target.closest('input,textarea,[contenteditable="true"]')){event.preventDefault();event.stopPropagation();input.focus();}
  if(event.key==='Escape'&&document.activeElement===input){input.value='';filter();}
 });
 filter();
 };
 boot();
 document.addEventListener('dynacat:widget-updated',boot);
 if(location.pathname==='/endpoints-services'&&!document.querySelector('.es-launcher[data-ready]')){
  const observer=new MutationObserver(()=>{boot();if(document.querySelector('.es-launcher[data-ready]'))observer.disconnect();});observer.observe(document.body,{childList:true,subtree:true});
 }
})();
