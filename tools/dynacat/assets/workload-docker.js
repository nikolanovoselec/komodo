/* Preserve header controls while the one-second widget refresh replaces content. */
(() => {
 const disclosures = '.cw-docker, .cw-unmatched-host';
 let focused=null;
 document.addEventListener('focusin',e=>{focused=e.target.matches?.('[data-cw-collapse-all]')?{element:e.target,widget:e.target.closest('.cw-merged').dataset.widgetId}:null;});
 const update = w => {
  for (const d of w.querySelectorAll(disclosures)) d.querySelector('summary')?.setAttribute('aria-expanded',String(d.open));
  const button=w.querySelector('[data-cw-collapse-all]');
  if(button)button.hidden=!w.querySelector('.cw-docker[open], .cw-unmatched-host[open]');
 };
 const sync = w => {
  if (!w?.matches('.cw-merged')) return;
  const header=w.querySelector('.widget-header'), current=w.querySelector('.widget-content .cw-status');
  if (header) {
   if(current){header.querySelector('.cw-status')?.remove();header.append(current);}
   let button=header.querySelector('[data-cw-collapse-all]');
   if(!button){button=document.createElement('button');button.type='button';button.dataset.cwCollapseAll='';button.textContent='Hide containers ↑';button.hidden=true;header.append(button);}
  }
  update(w);
 };
 document.addEventListener('toggle',e=>{
  if(e.target.matches?.(disclosures)){const w=e.target.closest('.cw-merged');if(w)update(w);}
 },true);
 document.addEventListener('click',e=>{
  const all=e.target.closest?.('[data-cw-collapse-all]');
  if(all){
   const w=all.closest('.cw-merged'), open=[...w.querySelectorAll('.cw-docker[open], .cw-unmatched-host[open]')];
   for(const d of open)d.open=false;
   update(w);open[0]?.querySelector('summary')?.focus({preventScroll:true});return;
  }
  const button=e.target.closest?.('[data-cw-collapse]');if(!button)return;
  const d=button.closest('.cw-docker');if(!d)return;
  e.preventDefault();e.stopPropagation();d.open=false;
  update(d.closest('.cw-merged'));
  const summary=d.querySelector('summary');summary.focus({preventScroll:true});summary.scrollIntoView({block:'nearest'});
 });
 document.addEventListener('dynacat:widget-updated',e=>queueMicrotask(()=>{
  const w=e.detail?.widget;sync(w);
  if(w?.matches('.cw-merged')&&focused?.widget===w.dataset.widgetId&&!focused.element.isConnected&&document.activeElement===document.body){
   const button=w.querySelector('[data-cw-collapse-all]');if(button&&!button.hidden)button.focus({preventScroll:true});
  }
 }));
 document.querySelectorAll('.cw-merged').forEach(sync);
 if((location.pathname==='/'||location.pathname==='/hardware-workloads')&&!document.querySelector('.cw-merged .widget-header .cw-status')){
  const observer=new MutationObserver(()=>{document.querySelectorAll('.cw-merged').forEach(sync);if(document.querySelector('.cw-merged .widget-header .cw-status'))observer.disconnect();});observer.observe(document.body,{childList:true,subtree:true});
 }
})();
