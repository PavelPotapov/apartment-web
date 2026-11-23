import {element,number,projectAsset} from './data.js';
import {Drawing,action,check,choice,grid,steps,storage,storeSettings,hitAttrs,svgNode,label,line} from './drawing.js';

const defaults={furniture:true,sockets:true,dims:true,plain:false,step:100};
const fmt=v=>number(v)+' мм';
const font=(s,px,fill='#476053')=>({'font-size':s*px,fill,'font-weight':600,stroke:'#fffdf7','stroke-width':s*3,'paint-order':'stroke'});
export function formatHeights(point){
 if(!point.heights?.length)return point.height||'уточнить';
 const value=point.heights.map(h=>number(h)).join(' / ')+' мм';
 return point.heightSource==='sill-relative'?value+' от пола ('+point.height+')':value;
}
export class Elevation{
 constructor(host,onChange){
  this.onChange=onChange;this.plot=new Drawing(host,'Развёртка стены',(g,s)=>this.draw(g,s),(k,id)=>{if(k==='electric')this.selectPoint(id)});
  this.toolbar=element('div',undefined,'atlas-tabs');this.plot.tools.prepend(this.toolbar);
  this.normal=action(this.toolbar,'Интерьер',()=>{this.cfg.furniture=true;this.cfg.plain=false;this.change()});
  this.wiring=action(this.toolbar,'Только розетки',()=>{this.cfg.furniture=false;this.cfg.plain=true;this.cfg.sockets=true;this.change()});
  this.checks={};for(const [k,n] of [['furniture','Мебель'],['sockets','Розетки'],['dims','Размеры']]){
   this.checks[k]=check(this.plot.side,n,defaults[k],v=>{this.cfg[k]=v;if(k==='furniture')this.cfg.plain=false;this.change()});
  }
  this.grid=choice(this.plot.side,'Шаг сетки',steps,100,v=>{this.cfg.step=Number(v);this.change()});
  this.picker=choice(this.plot.side,'Точка',[['','Все']],'',v=>this.selectPoint(v));
 }
 show(w){
  if(this.wall?.code===w.code)return;
  this.wall=w;this.cfg=storage('wall-'+w.code,defaults);this.active='';this.plot.measure=[];
  this.picker.replaceChildren(new Option('Все',''));
  for(const pt of w.sockets)this.picker.add(new Option('№ '+pt.number+' · '+formatHeights(pt),pt.number));
  const pad=Math.max(190,w.width*.045);
  this.plot.fit([-pad,-175,w.width+pad,w.height+275]);this.change(false);
 }
 selectPoint(id){
  this.active=String(id||'');if(this.active)this.cfg.sockets=true;
  this.picker.value=this.active;this.change();
 }
 change(save=true){
  if(!this.wall)return;
  if(save)storeSettings('wall-'+this.wall.code,this.cfg);
  for(const [k,el] of Object.entries(this.checks))el.checked=this.cfg[k];
  this.normal.setAttribute('aria-pressed',String(this.cfg.furniture&&!this.cfg.plain));
  this.wiring.setAttribute('aria-pressed',String(this.cfg.plain&&this.cfg.sockets));
  this.picker.parentNode.hidden=!this.cfg.sockets||!this.wall.sockets.length;
  this.grid.value=String(this.cfg.step);this.plot.render();this.details();this.onChange?.(this.cfg);
 }
 details(){
  const el=this.plot.detail;el.replaceChildren();
  const s=this.cfg.sockets&&this.wall.sockets.find(p=>p.number===this.active);
  if(!s){el.append(element('strong','U → от левого края · H ↑ от пола'),element('span',this.wall.sockets.length?'Выберите розетку для точной размерной привязки.':'На этой стене в проекте нет электроточек.'));return}
  const state=s.archived?'Архивная точка':s.approximate?'Привязку уточнить':s.status;
  el.append(element('strong','№ '+s.number+' · U '+fmt(s.u)+' · H '+formatHeights(s)),element('span',[state,s.placement==='countertop'?'Проекция точки на острове':null,s.note].filter(Boolean).join(' · ')));
 }
 draw(g,s){
  if(!this.wall)return;const w=this.wall,W=w.width,H=w.height,c=this.cfg,base=[0,0,W,H],p=this.plot;
  g.append(svgNode('rect',{x:0,y:0,width:W,height:H,fill:'#fffefa'}));
  if(!c.plain){
   const image=c.furniture?w.elevations.furnished:w.elevations.empty;
   g.append(svgNode('image',{href:projectAsset(image),x:0,y:0,width:W,height:H,preserveAspectRatio:'none'}));
  }
  if(c.plain)for(const a of w.apertures){
   const lo=a.sill??0,hi=a.head??a.modeledHead;if(!Number.isFinite(hi))continue;
   g.append(svgNode('rect',{x:a.u,y:H-hi,width:a.width,height:hi-lo,fill:a.type==='window'?'#eaf1ee':'#f2efe7',stroke:'#8ba398','stroke-width':s}));
   if(a.width/s>44)label(g,a.u+a.width/2,H-(lo+hi)/2,a.label||({door:'Дверь',window:'Окно',passage:'Проём'}[a.type]),font(s,10));
  }
  if(c.step)grid(g,'elevation-mm-grid',base,c.step,s,[0,H]);
  g.append(svgNode('rect',{x:0,y:0,width:W,height:H,fill:'none',stroke:'#5b7165','stroke-width':1.3*s}));
  p.snap.push([0,0],[W,0],[0,H],[W,H]);
  for(const a of w.apertures)for(const u of [a.u,a.u+a.width])for(const h of [a.sill,a.head])if(Number.isFinite(h))p.snap.push([u,H-h]);
  if(c.dims){
   const stride=c.step||100;
   const interval=Math.max(stride,Math.ceil(41*s/stride)*stride);
   for(let z=0;z<=H;z+=interval){line(g,[-5*s,H-z],[0,H-z],{stroke:'#608071','stroke-width':s});label(g,-9*s,H-z,number(z),{...font(s,10),'text-anchor':'end'})}
   label(g,W/2,-75,mmWidth(W),font(s,13));
   let sum=0;for(const seg of w.runs){const end=sum+seg;
    line(g,[sum,H],[sum,H+9*s],{stroke:'#608071','stroke-width':s});
    if(seg/s>30)label(g,(sum+end)/2,H+17*s,number(seg),font(s,10));sum=end;
   }
   line(g,[W,H],[W,H+9*s],{stroke:'#608071','stroke-width':s});
   if(w.runs.length>1)line(g,[0,H+7*s],[W,H+7*s],{stroke:'#8b998b','stroke-width':.65*s});
  }
  if(!c.sockets)return;
  const occupied=[];
  for(const pt of w.sockets){
   const active=pt.number===this.active, color=pt.approximate||pt.archived?'#9d5626':'#006b74';
   for(const h of pt.heights||[]){
    const x=pt.u,y=H-h;p.snap.push([x,y]);if(!Number.isFinite(x)||!Number.isFinite(y))continue;
    const a=g.appendChild(svgNode('g',hitAttrs('electric',pt.number,'№ '+pt.number+', U '+fmt(x)+', H '+fmt(h))));
    if(active){
     for(const [end,axis] of [[[-3*s,y],'h'],[[x,H+2*s],'u']])line(a,[x,y],end,{stroke:color,'stroke-width':s,'stroke-dasharray':s*4+' '+s*3});
     label(a,-4*s,y,number(h),{...font(s,11,color),'text-anchor':'end'});label(a,x,H+32*s,'U '+number(x),font(s,11,color));
    }
    a.append(svgNode('circle',{cx:x,cy:y,r:s*5.5,stroke:color,fill:'white','stroke-width':s*1.7}));
    line(a,[x-3*s,y],[x+3*s,y],{stroke:color,'stroke-width':s});line(a,[x,y-3*s],[x,y+3*s],{stroke:color,'stroke-width':s});
    const str=pt.number+' · '+number(h),width=str.length*s*5.7,dir=x>W*.73?-1:1;
    let pos=null;
    for(const k of [-1,1,-2,2,-3,3]){const xx=x+dir*(width/2+7*s),yy=y+k*13*s;
     if(yy<2*s||yy>H-2*s||occupied.some(b=>Math.abs(xx-b.x)<(width+b.w)/2&&Math.abs(yy-b.y)<13*s))continue;
     pos={x:xx,y:yy,w:width};break;
    }
    if(pos){occupied.push(pos);line(a,[x,y],[pos.x-dir*width*.46,pos.y],{stroke:color,'stroke-width':.7*s});label(a,pos.x,pos.y,str,font(s,10,color))}
    a.append(svgNode('title',{},'№ '+pt.number+' · U '+fmt(x)+' · H '+fmt(h)));
   }
  }
 }
}
const mmWidth=w=>'Длина '+fmt(w);

