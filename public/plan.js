import {element,number} from './data.js';
import {Drawing,action,check,choice,grid,steps,storage,storeSettings,hitAttrs,svgNode,line,label,points,boxOf} from './drawing.js';
const mm=n=>number(n)+' мм';
const tones={plumbing:'#2b7391',heating:'#ae5b35',service:'#725886',furniture:'#9d9687'};
const types={plumbing:'Сантехника',heating:'Отопление',service:'Инженерное оборудование'};
const wallAt=(w,u,h=0)=>[w.origin[0]+w.direction[0]*u-w.direction[1]*h,w.origin[1]+w.direction[1]*u+w.direction[0]*h];
const font=(s,px,fill='#304239')=>({'font-size':s*px,fill,'font-family':'Source Sans 3, sans-serif','font-weight':600,stroke:'#fffefa','stroke-width':s*3,'paint-order':'stroke'});
const inset=(b,n)=>[b[0]-n,b[1]-n,b[2]+n,b[3]+n];
const middle=b=>[(b[0]+b[2])/2,(b[1]+b[3])/2];
const presets={architecture:{furniture:false,sockets:false,utilities:false,dimensions:false,addresses:true},
 electric:{furniture:false,sockets:true,utilities:false,dimensions:false,addresses:false},
 services:{furniture:false,sockets:false,utilities:true,dimensions:false,addresses:false}};
const heights=s=>s.heights||s.heightsMm||[];
const socketInfo=s=>[s.archived?'Архивная привязка':s.approximate?'Привязку уточнить':s.status,s.placement==='countertop'?'На острове':null].filter(Boolean).join(' · ');
function polygonCenter(poly){
 let a=0,x=0,y=0;
 for(let i=0;i<poly.length;i++){const p=poly[i],q=poly[(i+1)%poly.length],k=p[0]*q[1]-p[1]*q[0];a+=k;x+=(p[0]+q[0])*k;y+=(p[1]+q[1])*k}
 return a?[x/(3*a),y/(3*a)]:middle(boxOf(poly));
}
export class ApartmentPlan {
 constructor(host,tech,onWall){
  this.tech=tech;this.plan=tech.plan;this.onWall=onWall;this.focus='';this.selected=null;this.activeMode='architecture';
  this.cfg=storage('plan',{...presets.architecture,step:0});
  this.plot=new Drawing(host,'План квартиры сверху',(g,s)=>this.draw(g,s),(k,id)=>this.pick(k,id));this.makeControls();this.fitRoom();this.details();
 }
 roomName(id){return this.tech.rooms.find(r=>r.id===id)?.name||id}
 makeControls(){
  const p=this.plot;
  this.tabs=element('div',undefined,'atlas-tabs');p.tools.prepend(this.tabs);
  for(const [k,n] of [['architecture','Планировка'],['electric','Электрика'],['services','Коммуникации']]){
   const b=action(this.tabs,n,()=>{this.activeMode=k;Object.assign(this.cfg,presets[k]);this.selected=null;this.update()});b.dataset.mode=k;
  }
  this.room=choice(p.side,'Помещение',[['','Вся квартира'],...this.tech.rooms.map(r=>[r.id,r.id+' · '+r.name])],'',v=>{this.focus=v;this.selected=null;this.fitRoom();this.update()});
  this.checks={};
  for(const [k,n] of [['addresses','Адреса стен'],['dimensions','Размеры'],['furniture','Мебель'],['sockets','Розетки'],['utilities','Коммуникации']]){
   this.checks[k]=check(p.side,n,this.cfg[k],v=>{this.cfg[k]=v;this.activeMode='';this.selected=null;this.update()});
  }
  this.step=choice(p.side,'Сетка',steps,this.cfg.step,v=>{this.cfg.step=Number(v);this.update()});
  this.pointPicker=choice(p.side,'Объект на плане',[['','Выбрать…']],'',v=>{if(v){const [k,id]=v.split(':');this.pick(k,id)}});
  this.legend=element('div',undefined,'atlas-key');p.sheet.after(this.legend);
  this.update(false);
 }
 fitRoom(){
  const poly=this.plan.rooms.find(r=>r.id===this.focus)?.polygon;
  this.plot.measure=[];this.plot.fit(inset(poly?boxOf(poly):this.plan.bounds,poly?440:480));
 }
 update(redraw=true){
  storeSettings('plan',this.cfg);
  for(const b of this.tabs.children)b.setAttribute('aria-pressed',String(b.dataset.mode===this.activeMode &&
    Object.entries(presets[b.dataset.mode]).every(([k,v])=>this.cfg[k]===v)));
  for(const [k,b] of Object.entries(this.checks))b.checked=this.cfg[k];
  this.pointPicker.parentNode.hidden=!this.cfg.sockets&&!this.cfg.utilities;
  this.pointPicker.replaceChildren(new Option('Выбрать…',''));
  if(this.cfg.sockets)for(const [i,s] of this.plan.sockets.entries()){
   if(!this.focus||s.code[0]===this.focus)this.pointPicker.add(new Option('№ '+s.number+' · '+s.code,'socket:'+i));
  }
  if(this.cfg.utilities)for(const [i,v] of this.plan.furniture.entries()){
   if(types[v.category]&&(!this.focus||v.roomId===this.focus))this.pointPicker.add(new Option(v.name,'fixture:'+i));
  }
  if(this.selected)this.pointPicker.value=this.selected.kind+':'+this.selected.id;
  this.legend.replaceChildren();const entries=[];
  if(this.cfg.sockets)entries.push(['#076a72','Розетка по ЭП'],['#a35b23','Привязку уточнить / архив']);
  if(this.cfg.utilities)entries.push([tones.plumbing,'ВК · сантехника'],[tones.heating,'ОТ · отопление'],[tones.service,'ИО · оборудование и сливы']);
  for(const [color,name] of entries){const tag=element('span',name);tag.style.setProperty('--swatch',color);this.legend.append(tag)}
  this.legend.hidden=!entries.length;
  if(redraw){this.plot.render();this.details()}
 }
 pick(kind,id){
  if(kind==='room'){this.focus=id;this.room.value=id;this.selected=null;this.fitRoom();this.update();return}
  this.selected={kind,id};if(kind==='wall')this.onWall(id);
  if(kind==='socket')this.onWall(this.plan.sockets[Number(id)].code,this.plan.sockets[Number(id)].number);
  this.update();
 }
 jump(code){
  const b=action(this.plot.detail,'Открыть развёртку '+code+' ↓',()=>{this.onWall(code,this.selected?.kind==='socket'?this.plan.sockets[Number(this.selected.id)].number:undefined);document.getElementById('catalog').scrollIntoView({behavior:'smooth',block:'start'})},'jump-sheet');
  b.title='Перейти к слоям и размерам стены';
 }
 details(){
  const d=this.plot.detail;d.replaceChildren();const item=this.selected;
  const add=(a,b)=>{d.append(element('strong',a),element('span',b))};
  if(item?.kind==='wall'){
   const w=this.tech.walls.find(w=>w.code===item.id);
   add(w.code+' · '+w.room,'Длина '+mm(w.width)+(w.runs.length>1?' · '+w.runs.map(numberValue=>number(numberValue)).join(' + ')+' мм':''));this.jump(w.code);
  }else if(item?.kind==='socket'){
   const s=this.plan.sockets[Number(item.id)];
   add('Розетка №'+s.number+' · '+s.code,'U '+mm(s.u)+' · H '+(heights(s).length?heights(s).map(v=>number(v)).join(' / ')+' мм':s.height||'уточнить')+' · '+socketInfo(s));this.jump(s.code);
  }else if(item?.kind==='fixture'){
   const f=this.plan.furniture[Number(item.id)],b=boxOf(f.polygon),[x,y]=middle(b);
   add(f.name,'Габарит в плане '+mm(b[2]-b[0])+' × '+mm(b[3]-b[1])+' · центр габарита X '+mm(x-this.plan.bounds[0])+', Y '+mm(y-this.plan.bounds[1])+' от левого верхнего угла плана.');
  }else if(this.cfg.utilities){add('Инженерное оборудование','Выберите прибор для привязки. Показаны положения оборудования по модели. Трассы труб и кабелей и координаты скрытых выводов требуют отдельной исполнительной схемы.')}
  else if(this.cfg.sockets){add('Электроточки','Нажмите номер, чтобы увидеть отступ от начала стены (U), высоту от пола (H) и статус привязки.')}
  else{add(this.focus?this.focus+' · '+this.roomName(this.focus):'Помещения A–G','Выберите комнату для увеличения или стену для перехода к её развёртке.')}
 }
 draw(g,s){
  const p=this.plot,plan=this.plan,c=this.cfg,room=this.focus,sel=this.selected;
  const walls=this.tech.walls.filter(w=>w.origin&&(!room||w.roomId===room));
  const inside=id=>!room||id===room;
  for(const r of plan.rooms){
   g.append(svgNode('polygon',{points:points(r.polygon),fill:inside(r.id)?'#f5f3e9':'#f5f6f3',stroke:'none'}));
  }
  for(const poly of plan.wallPolygons||[])g.append(svgNode('polygon',{points:points(poly),fill:'#5a6760'}));
  if(c.step)grid(g,'plan-mm-grid',plan.bounds,c.step,s,[plan.bounds[0],plan.bounds[1]]);
  const serviceHits=[];
  for(const [idx,f] of plan.furniture.entries()){
   if(!inside(f.roomId)||!f.polygon?.length)continue;
   const util=Boolean(types[f.category]);if(util?!c.utilities:!c.furniture)continue;
   const selF=sel?.kind==='fixture'&&Number(sel.id)===idx;
   const shape=svgNode('polygon',{points:points(f.polygon),fill:tones[f.category]||tones.furniture,'fill-opacity':selF?.52:util?.21:.14,stroke:tones[f.category]||tones.furniture,'stroke-width':s*(selF?2:1)});
   g.append(shape);
   if(util){Object.entries(hitAttrs('fixture',idx,f.name)).forEach(([k,v])=>shape.setAttribute(k,v));shape.append(svgNode('title',{},f.name));const center=middle(boxOf(f.polygon));p.snap.push(center);serviceHits.push([idx,f,center])}
  }
  const used=[];
  const reserve=(x,y,w,h)=>used.push([x-w/2,y-h/2,x+w/2,y+h/2]);
  const free=(x,y,w,h)=>!used.some(a=>a[0]<x+w/2&&a[2]>x-w/2&&a[1]<y+h/2&&a[3]>y-h/2);
  for(const r of plan.rooms){
   if(!inside(r.id))continue;
   const center=polygonCenter(r.polygon),x=center[0],y=center[1],rad=s*(room?15:11);
   const a=g.appendChild(svgNode('g',hitAttrs('room',r.id,'Помещение '+r.id+' · '+this.roomName(r.id))));
   a.append(svgNode('circle',{cx:x,cy:y,r:rad,fill:'#345747'}));label(a,x,y,r.id,{'font-size':rad*1.32,'font-weight':650,fill:'white'});reserve(x,y,rad*2,rad*2);
  }
  for(const w of walls){
   const chosen=sel?.kind==='wall'&&sel.id===w.code;
   const a=g.appendChild(svgNode('g',hitAttrs('wall',w.code,'Стена '+w.code+', '+w.width+' мм')));
   const start=wallAt(w,0),end=wallAt(w,w.width);p.snap.push(start,end);
   // Cut openings out of the wall face, leaving a thin reveal across each window.
   let u=0;
   for(const op of [...w.apertures].sort((a,b)=>a.u-b.u)){
    if(op.u>u)line(a,wallAt(w,u),wallAt(w,op.u),{stroke:chosen?'#ad6038':'#48594e','stroke-width':s*(chosen?3.8:1.65)});
    line(a,wallAt(w,op.u),wallAt(w,op.u+op.width),{stroke:op.type==='window'?'#6f9f9c':'#b2b9ad','stroke-width':s,'stroke-dasharray':op.type==='window'?undefined:s*4+' '+s*4});
    p.snap.push(wallAt(w,op.u),wallAt(w,op.u+op.width));u=Math.max(u,op.u+op.width);
   }
   if(u<w.width)line(a,wallAt(w,u),end,{stroke:chosen?'#ad6038':'#48594e','stroke-width':s*(chosen?3.8:1.65)});
   const [dx,dy]=w.direction;
   line(a,wallAt(w,0,3*s),wallAt(w,w.width,3*s),{stroke:'transparent','stroke-width':s*9});
   if(c.addresses||chosen){
    // Place codes on their room's side, preferring the centre. Crowded returns get a leader.
    const mid=wallAt(w,w.width*.5),width=s*(w.code.length*7+4),h=s*13;
    const spots=[.5,.34,.67].flatMap(t=>[11,23,36,48].map(v=>wallAt(w,w.width*t,s*v)));
    const at=spots.find(q=>free(...q,width,h))||((room||chosen)?spots[0]:null);
    if(at){
     if(Math.hypot(mid[0]-at[0],mid[1]-at[1])>s*16)line(a,mid,at,{stroke:'#a6aea0','stroke-width':s*.7});
     label(a,...at,w.code,font(s,11,chosen?'#a14e25':'#4b6255'));reserve(...at,width,h);
    }
   }
   if(c.dimensions){
    const mid=wallAt(w,w.width/2,s*(c.addresses?40:16)),wide=(w.width/s)>55;
    if(wide||room||chosen){const ang=dx===0?-90:0;label(a,...mid,number(w.width),{...font(s,10,'#765b45'),transform:'rotate('+ang+' '+mid.join(' ')+')'});}
    if(room||chosen){
     for(const op of w.apertures){const at=wallAt(w,op.u+op.width/2,-s*11);label(a,...at,number(op.width),font(s,10,'#526d73'))}
    }
   }
  }
  if(c.utilities)for(const [idx,f,center] of serviceHits){
   const tag={plumbing:'ВК',heating:'ОТ',service:'ИО'}[f.category],a=g.appendChild(svgNode('g',hitAttrs('fixture',idx,f.name)));
   const w=21*s,h=14*s;
   const spot=[[0,0],[0,-15],[15,12],[-15,12],[0,24]].map(([dx,dy])=>[center[0]+s*dx,center[1]+s*dy]).find(q=>free(...q,w,h))||center;
   a.append(svgNode('rect',{x:spot[0]-w/2,y:spot[1]-h/2,width:w,height:h,rx:s*3,fill:tones[f.category]}));label(a,...spot,tag,{'font-size':s*9,fill:'white'});reserve(...spot,w,h);
  }
  if(c.sockets)for(const [i,v] of plan.sockets.entries()){
   if(!inside(v.code[0]))continue;const wall=this.tech.walls.find(w=>w.code===v.code),anchor=[v.x,v.y];
   const color=v.approximate||v.archived?'#a35b23':'#076a72';const g1=g.appendChild(svgNode('g',hitAttrs('socket',i,'Розетка №'+v.number+' · '+v.code)));
   const candidates=[14,29,45,60].flatMap(d=>[0,-13,13,-25,25].map(t=>[v.x+s*(t*wall.direction[0]-d*wall.direction[1]),v.y+s*(t*wall.direction[1]+d*wall.direction[0])]));
   const xy=candidates.find(q=>free(...q,20*s,19*s))||candidates[0];reserve(...xy,21*s,19*s);
   line(g1,anchor,xy,{stroke:color,'stroke-width':s});g1.append(svgNode('circle',{cx:v.x,cy:v.y,r:2*s,fill:color}));
   g1.append(svgNode('circle',{cx:xy[0],cy:xy[1],r:9*s,fill:sel?.kind==='socket'&&Number(sel.id)===i?color:'#fffdf6',stroke:color,'stroke-width':1.25*s}));
   label(g1,...xy,v.number,{'font-size':10*s,'font-weight':650,fill:sel?.kind==='socket'&&Number(sel.id)===i?'white':color});p.snap.push(anchor);
  }
 }
}

