import {projectAsset,jsonAsset,number,element,reportError} from './data.js';
const el=id=>document.getElementById(id);
const params=new URL(location.href).searchParams;
let selected=params.get('wall')?.toUpperCase()||'A1', sheets=[], rooms=[], furniture=[], release, query='';
const clean=s=>String(s??'').toLowerCase().replace(/ё/g,'е').trim();
function searchWall(w) {
 const alias=query.toUpperCase().replace(/^[АВСДЕФГ](?=\d)/,c=>({'А':'A','В':'B','С':'C','Д':'D','Е':'E','Ф':'F','Г':'G'}[c]));
 if (w.code===alias || alias.startsWith(w.code+'.')) return true;
 if (/^(?:розетк[а-я]*\s*|№\s*|#\s*)?\d+$/.test(query)){
   const n=Number(query.match(/\d+$/)[0]);return w.sockets.some(s=>Number(s.number)===n);
 }
 return clean([w.code,w.room,w.opening_note,...w.sockets.map(s=>s.number)].join(' ')).includes(query);
}
const roomId=w=>w.roomId||w.code[0];
function button(text,value,action,active) {
 const b=element('button',text);b.type='button';b.setAttribute('aria-pressed',String(active));b.addEventListener('click',()=>action(value));return b;
}
function select(code) {
 selected=code;const url=new URL(location.href);url.searchParams.set('wall',code);history.replaceState(null,'',url);
 paint();
}
function dimensions(values){return values.map(v=>number(v)).join(' × ')+' мм'}
function metric(label,value) {
 const group=element('div');group.append(element('dt',label),element('dd',value));return group;
}
function cellRow(values){
 const tr=element('tr');for(const v of values){const td=element('td');if(v instanceof Node)td.append(v);else td.textContent=v;tr.append(td)}return tr;
}
function paint() {
 const filtered=sheets.filter(searchWall);const w=filtered.find(t=>t.code===selected)||filtered[0];
 el('catalog-grid').hidden=!w;el('data-status').hidden=!!w;
 if(!w){el('data-status').textContent='Совпадений нет. Попробуйте код стены, название комнаты или номер розетки.';return}
 const key=roomId(w), r=rooms.find(t=>t.id===key);
 el('room-list').replaceChildren(...rooms.filter(r=>filtered.some(w=>roomId(w)===r.id)).map(r=>{
   const b=button('',filtered.find(w=>roomId(w)===r.id).code,select,r.id===key);b.append(element('b',r.id),element('span',r.name));return b;
 }));
 el('wall-list').replaceChildren(...filtered.filter(t=>roomId(t)===key).map(t=>button(t.code,t.code,select,w.code===t.code)));
 el('current-room').textContent=r.name+' · '+number(r.area,2)+' м²';
 el('wall-title').textContent='Стена '+w.code;
 el('sheet-link').href=projectAsset(release.pdf)+'#page='+w.page;el('sheet-link').textContent='Лист '+w.page+' · PDF ↗';
 const img=el('drawing');img.src=projectAsset(w.image);img.alt='Развёртка стены '+w.code+' со всеми обозначениями из модели';
 el('wall-metrics').replaceChildren(metric('Длина стены',number(w.width)+' мм'),metric('Высота профиля',number(w.height??w.ceiling)+' мм'),metric('Шаг сетки',number(w.grid_mm)+' мм'));
 if(w.membrane_mm)el('wall-metrics').append(metric('Чистый потолок',number(w.membrane_mm)+' мм'));
 if(w.cornice_bottom_mm)el('wall-metrics').append(metric('Низ карниза',number(w.cornice_bottom_mm)+' мм'));
 if(w.floor_trim_mm)el('wall-metrics').append(metric('Напольный плинтус',number(w.floor_trim_mm)+' мм'));
 if(w.runs?.length>1)el('wall-metrics').append(metric('Размерная цепь',w.runs.map(n=>number(n)).join(' + ')+' мм'));
 el('wall-note').textContent=w.opening_note||'';el('wall-note').hidden=!w.opening_note;
 el('sockets').replaceChildren(...w.sockets.map(s=>cellRow(['№ '+s.number,number(s.u)+' мм',String(s.height)+' мм',s.status])));
 el('socket-section').hidden=!w.sockets.length;
 const items=furniture.filter(i=>i.roomId===key);let inventory=el('inventory');
 if(!inventory){inventory=element('details');inventory.id='inventory';inventory.className='inventory';el('socket-section').after(inventory)}
 inventory.hidden=!items.length;inventory.replaceChildren(element('summary','Мебель и оснащение · '+r.name));
 if(items.length){const div=element('div',undefined,'table-wrap');const table=element('table');const head=element('thead');const tr=element('tr');for(const t of ['Предмет','Ш × Г × В','Материалы'])tr.append(element('th',t));head.append(tr);table.append(head);
 const body=element('tbody');items.forEach(i=>body.append(cellRow([i.name,dimensions([i.width,i.depth,i.height]),(i.materials||[]).join(', ')])));table.append(body);div.append(table);inventory.append(div)}
}
async function showEstimate(){
 const response=await fetch(projectAsset('material-estimates.json'),{cache:'no-cache'});
 if(!response.ok)return;const d=await response.json();if(!d.items?.length)return;
 el('estimate-date').textContent='Ориентировочные цены на '+new Date(d.asOf+'T12:00:00').toLocaleDateString('ru-RU');
 el('estimate-note').textContent=d.note||'';const link=el('estimate-download');link.href=projectAsset('material-estimates.pdf');
 el('estimate-rows').replaceChildren(...d.items.map(i=>{
   let name=i.label;
   if(i.sourceUrl && /^https?:\/\//.test(i.sourceUrl)){name=element('a',i.label);name.href=i.sourceUrl;name.rel='noopener';name.target='_blank';name.title=i.sourceLabel||'Источник цены'}
   return cellRow([name,number(i.areaM2,2)+' м²',number(i.wastePct)+' %',number(i.orderM2,2)+' м²',number(i.priceRubM2)+' ₽',number(i.totalRub)+' ₽']);
 }));el('estimates').hidden=false;
}
el('search').addEventListener('input',e=>{query=clean(e.target.value);paint()});
el('enlarge').addEventListener('click',()=>{const img=el('drawing');el('lightbox-image').src=img.src;el('lightbox-image').alt=img.alt;el('lightbox-title').textContent=el('wall-title').textContent;el('lightbox').showModal()});
el('close-lightbox').onclick=()=>el('lightbox').close();
el('lightbox').onclick=e=>{if(e.target===el('lightbox'))el('lightbox').close()};
try {
 release=await jsonAsset('release.json');const technical=await jsonAsset(release.technical);sheets=technical.walls;rooms=technical.rooms;furniture=technical.inventory||[];
 el('download').href=projectAsset(release.pdf);el('area').replaceChildren(document.createTextNode(number(rooms.reduce((sum,r)=>sum+Number(r.area),0),2)+' '),element('small','м²'));
 el('rooms-count').textContent=rooms.length;el('walls-count').textContent=sheets.length;
 const historyLink=element('a','История выпусков ↗');historyLink.href='https://github.com/PavelPotapov/apartment-web/commits/main/public/data/release.json';historyLink.rel='noopener';historyLink.target='_blank';
 el('release-version').append(document.createTextNode('Версия '+release.version+' · '),historyLink);paint();
 showEstimate().catch(()=>{});
} catch(e){console.error(e);reportError(el('data-status'),'Альбом не загрузился. Проверьте соединение.')}

