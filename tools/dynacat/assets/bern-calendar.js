/* Bern civil calendar: native-style month grid, explicitly Europe/Zurich. */
(() => {
 const boot=()=>{
 const root=document.querySelector('[data-bern-calendar]');if(!root||root.dataset.ready)return;root.dataset.ready='true';
 const today=()=>{const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const v=Object.fromEntries(p.map(x=>[x.type,x.value]));return {y:+v.year,m:+v.month-1,d:+v.day};};
 let now=today(),year=now.y,month=now.m;
 const title=root.querySelector('[data-calendar-title]'),grid=root.querySelector('[data-calendar-grid]');
 const render=()=>{
  now=today();title.textContent=new Intl.DateTimeFormat('en-GB',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(year,month,1)));
  const offset=(new Date(Date.UTC(year,month,1)).getUTCDay()+6)%7;grid.replaceChildren();
  for(let i=0;i<42;i++){const date=new Date(Date.UTC(year,month,1-offset+i));const cell=document.createElement('span');cell.textContent=date.getUTCDate();cell.setAttribute('role','gridcell');cell.dataset.date=date.toISOString().slice(0,10);if(date.getUTCMonth()!==month)cell.className='bern-outside';if(date.getUTCFullYear()===now.y&&date.getUTCMonth()===now.m&&date.getUTCDate()===now.d)cell.setAttribute('aria-current','date');grid.append(cell);}
  root.dataset.timezone='Europe/Zurich';
 };
 root.addEventListener('click',e=>{const action=e.target.closest('[data-calendar-action]')?.dataset.calendarAction;if(!action)return;if(action==='today'){now=today();year=now.y;month=now.m;}else {const d=new Date(Date.UTC(year,month+(action==='next'?1:-1),1));year=d.getUTCFullYear();month=d.getUTCMonth();}render();});
 const updateZones=()=>{for(const row of document.querySelectorAll('.cc-rail-clock [data-time-in-zone]')){let label=row.querySelector('.cc-clock-zone');if(!label){label=document.createElement('span');label.className='cc-clock-zone';row.insertBefore(label,row.querySelector('[data-time]'));}label.textContent=new Intl.DateTimeFormat('en-US',{timeZone:row.dataset.timeInZone,timeZoneName:'shortOffset'}).formatToParts(new Date()).find(p=>p.type==='timeZoneName').value;}};
 updateZones();
 render();
 setInterval(()=>{if(document.hidden)return;updateZones();const next=today();if(next.d!==now.d||next.m!==now.m||next.y!==now.y){if(year===now.y&&month===now.m){year=next.y;month=next.m;}render();}},30000);
 };
 boot();document.addEventListener('dynacat:widget-updated',boot);
 if((location.pathname==='/'||location.pathname==='/hardware-workloads')&&!document.querySelector('[data-bern-calendar][data-ready]')){
  const observer=new MutationObserver(()=>{boot();if(document.querySelector('[data-bern-calendar][data-ready]'))observer.disconnect();});observer.observe(document.body,{childList:true,subtree:true});
 }
})();
