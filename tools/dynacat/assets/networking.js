/* Public native update event only; no polling, requests, or browser credentials. */
(() => {
  const state={query:'',kind:'all',opened:new Set()};
  let focused=null;
  function apply(root){
    const input=root.querySelector('[data-nw-search]'),select=root.querySelector('[data-nw-kind]');
    if(input)input.value=state.query;if(select)select.value=state.kind;
    const query=state.query.trim().toLocaleLowerCase();let shown=0;
    const rows=root.querySelectorAll('[data-nw-client]');
    for(const row of rows){row.hidden=!(row.textContent.toLocaleLowerCase().includes(query)&&(state.kind==='all'||row.dataset.kind===state.kind));if(!row.hidden)shown++;}
    const result=root.querySelector('[data-nw-results]');if(result)result.textContent=`${shown} of ${rows.length} clients`;
  }
  function restore(){
    for(const root of document.querySelectorAll('.nw-dashboard')){
      for(const d of root.querySelectorAll('[data-nw-disclosure]'))d.open=state.opened.has(d.dataset.nwDisclosure);
      apply(root);
      if(focused && (document.activeElement===focused.element || (!focused.element.isConnected && document.activeElement===document.body))){
        const saved={...focused};
        const el=root.querySelector(saved.selector);el?.focus({preventScroll:true});
        if(el?.matches('[data-nw-search]')){
          el.setSelectionRange(saved.start,saved.end);
          focused={...saved,element:el};
        }
      }
    }
  }
  document.addEventListener('input',event=>{
    if(!event.target.matches('[data-nw-search]'))return;
    state.query=event.target.value;apply(event.target.closest('.nw-dashboard'));
    focused={element:event.target,selector:'[data-nw-search]',start:event.target.selectionStart,end:event.target.selectionEnd};
  });
  document.addEventListener('change',event=>{
    if(!event.target.matches('[data-nw-kind]'))return;
    state.kind=event.target.value;apply(event.target.closest('.nw-dashboard'));
  });
  document.addEventListener('toggle',event=>{
    const d=event.target;if(!d.matches?.('[data-nw-disclosure]')||!d.isConnected)return;
    if(d.open)state.opened.add(d.dataset.nwDisclosure);else state.opened.delete(d.dataset.nwDisclosure);
  },true);
  document.addEventListener('focusin',event=>{
    const e=event.target;
    if(e.matches('[data-nw-search],[data-nw-kind]'))focused={element:e,selector:e.matches('[data-nw-search]')?'[data-nw-search]':'[data-nw-kind]',start:e.selectionStart,end:e.selectionEnd};
    else if(e.matches('.nw-dashboard summary'))focused={element:e,selector:`[data-nw-disclosure="${e.parentElement.dataset.nwDisclosure}"] summary`};
    else focused=null;
  });
  function rememberSelection(){
    const e=document.activeElement;
    if(e?.matches('[data-nw-search]'))focused={element:e,selector:'[data-nw-search]',start:e.selectionStart,end:e.selectionEnd};
  }
  document.addEventListener('select',rememberSelection);
  document.addEventListener('selectionchange',rememberSelection);
  document.addEventListener('dynacat:widget-updated',restore);
  restore();
})();
