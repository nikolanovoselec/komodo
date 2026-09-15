/* Explicit workload collapse affordance and header status alignment. */
(() => {
 const sync = w => {
  if (!w?.matches('.cw-merged')) return;
  for (const d of w.querySelectorAll('.cw-docker')) d.querySelector('summary')?.setAttribute('aria-expanded',String(d.open));
  const header=w.querySelector('.widget-header'), current=w.querySelector('.widget-content .cw-status');
  if (header) {header.querySelector('.cw-status')?.remove();if(current)header.append(current);}
 };
 document.addEventListener('toggle',e=>{
  const d=e.target;
  if(d.matches?.('.cw-docker'))d.querySelector('summary')?.setAttribute('aria-expanded',String(d.open));
 },true);
 document.addEventListener('click',e=>{
  const button=e.target.closest?.('[data-cw-collapse]');if(!button)return;
  const d=button.closest('.cw-docker');if(!d)return;
  e.preventDefault();e.stopPropagation();d.open=false;
  const summary=d.querySelector('summary');summary.setAttribute('aria-expanded','false');summary.focus({preventScroll:true});summary.scrollIntoView({block:'nearest'});
 });
 document.addEventListener('dynacat:widget-updated',e=>sync(e.detail?.widget));
 document.querySelectorAll('.cw-merged').forEach(sync);
 if((location.pathname==='/'||location.pathname==='/hardware-workloads')&&!document.querySelector('.cw-merged .widget-header .cw-status')){
  const observer=new MutationObserver(()=>{document.querySelectorAll('.cw-merged').forEach(sync);if(document.querySelector('.cw-merged .widget-header .cw-status'))observer.disconnect();});observer.observe(document.body,{childList:true,subtree:true});
 }
})();
