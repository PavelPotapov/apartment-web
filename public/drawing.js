import {element} from './data.js';

export const svgNode=(name,attrs={},text)=>{
 const node=document.createElementNS('http://www.w3.org/2000/svg',name);
 for(const [k,v] of Object.entries(attrs))if(v!==undefined)node.setAttribute(k,String(v));
 if(text!==undefined)node.textContent=text;
 return node;
};
export const line=(p,a,b,style={})=>p.appendChild(svgNode('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],...style}));
export const label=(p,x,y,text,style={})=>p.appendChild(svgNode('text',{x,y,'text-anchor':'middle','dominant-baseline':'central',...style},text));
export const points=poly=>poly.map(v=>v.join(',')).join(' ');
export const boxOf=poly=>[Math.min(...poly.map(v=>v[0])),Math.min(...poly.map(v=>v[1])),Math.max(...poly.map(v=>v[0])),Math.max(...poly.map(v=>v[1]))];
export function grid(p,id,box,step,scale,anchor=[0,0]){
 if(!step)return;
 const defs=p.appendChild(svgNode('defs'));
 const minor=defs.appendChild(svgNode('pattern',{id,x:anchor[0],y:anchor[1],width:step,height:step,patternUnits:'userSpaceOnUse'}));
 minor.append(svgNode('path',{d:'M '+step+' 0 H 0 V '+step,fill:'none',stroke:'#7b9490','stroke-width':.63*scale,opacity:.54}));
 const [x,y,r,b]=box;
 p.append(svgNode('rect',{x,y,width:r-x,height:b-y,fill:'url(#'+id+')','pointer-events':'none'}));
}
export function check(parent,name,value,change){
 const lab=element('label',undefined,'layer-toggle'),input=element('input');input.type='checkbox';input.checked=value;
 input.addEventListener('change',()=>change(input.checked));lab.append(input,document.createTextNode(name));parent.append(lab);return input;
}
export function choice(parent,title,values,initial,change){
 const lab=element('label',undefined,'atlas-choice'),s=element('select');s.setAttribute('aria-label',title);
 lab.append(element('span',title),s);parent.append(lab);
 for(const [v,txt] of values){const opt=element('option',txt);opt.value=String(v);s.append(opt)}
 s.value=String(initial);s.onchange=()=>change(s.value);return s;
}
export const steps=[0,25,50,100,250,500].map(v=>[v,v?v+' мм':'Выключена']);
export function action(parent,name,fn,cls=''){
 const b=element('button',name,cls);b.type='button';b.onclick=fn;parent.append(b);return b;
}
export function storage(key,fallback){
 try{return {...fallback,...JSON.parse(localStorage.getItem('atlas-v2-'+key)||'{}')}}catch{return {...fallback}}
}
export function storeSettings(key,obj){try{localStorage.setItem('atlas-v2-'+key,JSON.stringify(obj))}catch{}}
const fmt=n=>Math.round(n).toLocaleString('ru-RU');

export class Drawing {
 constructor(host,title,draw,onPick){
  this.host=host;this.draw=draw;this.onPick=onPick;this.scale=1;this.snap=[];this.measure=[];this.pointers=new Map();
  host.replaceChildren();this.tools=element('div',undefined,'atlas-tools');this.side=element('div',undefined,'atlas-options');
  this.sheet=element('div',undefined,'atlas-sheet');this.svg=svgNode('svg',{role:'group','aria-label':title,tabindex:0});
  this.sheet.append(this.svg);this.actions=element('div',undefined,'atlas-actions');this.sheet.append(this.actions);
  for(const [caption,title,fn] of [['+','Приблизить',()=>this.zoom(1.5)],['−','Отдалить',()=>this.zoom(1/1.5)],['⤢','Весь чертёж',()=>this.fit(this.home)],['↗','На весь экран',()=>this.expand()]]){
   const b=action(this.actions,caption,fn);b.setAttribute('aria-label',title);b.title=title;
  }
  this.measureButton=action(this.tools,'Измерить',()=>{this.measuring=!this.measuring;this.measure=[];this.measureButton.setAttribute('aria-pressed',String(this.measuring));this.render()});
  this.measureButton.setAttribute('aria-pressed','false');this.measureButton.title='Измерить расстояние между двумя точками';
  this.detail=element('div',undefined,'atlas-readout');this.detail.setAttribute('aria-live','polite');
  this.readout=element('div',undefined,'atlas-measure');this.readout.setAttribute('role','status');
  host.append(this.tools,this.side,this.sheet,this.detail,this.readout);
  this.svg.addEventListener('wheel',e=>{if(!e.ctrlKey && document.activeElement!==this.svg)return;e.preventDefault();this.zoom(Math.exp(-Math.max(-180,Math.min(180,e.deltaY))*.003),this.pos(e))},{passive:false});
  this.svg.addEventListener('pointerdown',e=>{
   if(e.button!==0)return;
   this.pointers.set(e.pointerId,[e.clientX,e.clientY]);this.suppress=false;
   this.drag={x:e.clientX,y:e.clientY,box:this.view.slice()};this.svg.focus({preventScroll:true});
   if(this.pointers.size===2){this.suppress=true;this.drag=null;this.pinch=this.gap()}
  });
  this.svg.addEventListener('pointermove',e=>{
   if(!this.pointers.has(e.pointerId))return;this.pointers.set(e.pointerId,[e.clientX,e.clientY]);
   if(this.pointers.size===2){const gap=this.gap(),pts=[...this.pointers.values()];if(this.pinch>0&&gap>0)this.zoom(gap/this.pinch,this.pos({clientX:(pts[0][0]+pts[1][0])/2,clientY:(pts[0][1]+pts[1][1])/2}));this.pinch=gap;return}
   if(!this.drag)return;const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;
   if(Math.hypot(dx,dy)<5&&!this.suppress)return;
   this.suppress=true;this.svg.setPointerCapture(e.pointerId);
   this.view=[this.drag.box[0]-dx*this.scale,this.drag.box[1]-dy*this.scale,...this.drag.box.slice(2)];this.render();
  });
  const release=e=>{this.pointers.delete(e.pointerId);this.drag=null};
  this.svg.addEventListener('pointerup',release);this.svg.addEventListener('pointercancel',release);
  this.svg.addEventListener('pointerleave',e=>{if(!this.svg.hasPointerCapture(e.pointerId))release(e)});
  this.svg.addEventListener('click',e=>{
   if(this.suppress){this.suppress=false;return}
   if(this.measuring){this.mark(this.pos(e));return}
   const item=e.target.closest('[data-kind]');if(item)this.onPick(item.dataset.kind,item.dataset.id);
  });
  this.svg.addEventListener('keydown',e=>{
   const item=e.target.closest('[data-kind]');
   if((e.key==='Enter'||e.key===' ')&&item){e.preventDefault();this.onPick(item.dataset.kind,item.dataset.id)}
   if(e.key==='+')this.zoom(1.5);if(e.key==='-')this.zoom(1/1.5);
   if(e.key==='Escape'&&this.measuring)this.measureButton.click();
  });
  this.observer=new ResizeObserver(()=>{if(this.home)this.render()});this.observer.observe(this.svg);
 }
 gap(){const [a,b]=this.pointers.values();return Math.hypot(a[0]-b[0],a[1]-b[1])}
 expand(){
  const dialog=this.host.closest('dialog');if(dialog){dialog.close();return}
  const d=element('dialog',undefined,'atlas-full');const anchor=document.createComment('Чертёж');this.host.before(anchor);
  document.body.append(d);const b=action(d,'Закрыть ×',()=>d.close(),'close-sheet');d.append(this.host);
  d.addEventListener('close',()=>{anchor.replaceWith(this.host);d.remove();this.render()},{once:true});d.showModal();b.focus();
 }
 pos(e){const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(this.svg.getScreenCTM().inverse());return [p.x,p.y]}
 fit(bounds){
  this.home=bounds;const [a,b,c,d]=bounds;this.view=[a,b,c-a,d-b];this.render();
 }
 zoom(f,at){
  const [x,y,w,h]=this.view,z=Math.min(20,Math.max(.7,(this.home[2]-this.home[0])/w*f));f=z*w/(this.home[2]-this.home[0]);
  const [ax,ay]=at||[x+w/2,y+h/2];this.view=[ax+(x-ax)/f,ay+(y-ay)/f,w/f,h/f];this.render();
 }
 mark(pt){
  let best=12*this.scale,hit=pt;
  for(const p of this.snap){const dist=Math.hypot(pt[0]-p[0],pt[1]-p[1]);if(dist<best){best=dist;hit=p}}
  if(this.measure.length===2)this.measure=[];
  this.measure.push(hit);this.render();
 }
 render(){
  if(!this.view)return;this.svg.setAttribute('viewBox',this.view.join(' '));
  const transform=this.svg.getScreenCTM();if(!transform?.a)return;this.scale=1/transform.a;
  const g=svgNode('g');this.snap=[];this.draw(g,this.scale);this.svg.replaceChildren(g);this.readout.hidden=!this.measuring;
  if(this.measuring){const [a,b]=this.measure;
   this.readout.textContent=!a?'Выберите первую точку на чертеже.':!b?'Выберите вторую точку.':'Расстояние '+fmt(Math.hypot(a[0]-b[0],a[1]-b[1]))+' мм · по горизонтали '+fmt(Math.abs(a[0]-b[0]))+' мм · по вертикали чертежа '+fmt(Math.abs(a[1]-b[1]))+' мм. Щёлкните для нового замера.';
   for(const p of this.measure)g.append(svgNode('circle',{cx:p[0],cy:p[1],r:4*this.scale,fill:'#a84622'}));
   if(b)line(g,a,b,{stroke:'#a84622','stroke-width':2*this.scale});
  }
 }
}
export function hitAttrs(kind,id,aria){return {'data-kind':kind,'data-id':String(id),'aria-label':aria,role:'button',tabindex:0}}

