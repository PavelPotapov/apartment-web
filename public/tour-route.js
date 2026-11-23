import {avatar, circleIntersectsBox, hitsDoor, pointInPolygon, walkAllowed} from './movement.js';

// Each subject is resolved against the current export, so moving its Blender assembly
// moves its tour focus. The room and fallback wall keep a tour possible after renaming.
const itinerary = [
  ['G','У входа · зеркало над консолью',/консоль 1000/i,'G13',1.55,1.47],
  ['G','Картина и подсветка на стене G2',/ботанический этюд/i,'G2',1.65,1.49],
  ['A','Кухня и полуостров',/полуостров с филёнками|варочная поверхность/i,'A3',2.4,1.12],
  ['A','Гостиная и диван',/Vienna.*диван/i,'A3',2.7,1.02],
  ['A','Обеденная группа',/обеденный стол/i,'A1',2.2,.89],
  ['B','Каминная группа',/электрокамин/i,'B1',2.25,1.05],
  ['B','Рабочее место в кабинете',/подъёмный стол/i,'B3',1.85,.95],
  ['C','Душевая и умывальник',/душ 1400|тумба из ореха/i,'C4',1.25,1.19],
  ['F','Кабинет у окна',/ОР-530|Ангстрем.*правый/i,'F1',1.75,1.0],
  ['F','Кресло у окна',/кресло Hygge/i,'F3',1.75,.9],
  ['E','Изголовье спальни',/Madison Lite/i,'E1',2.15,1.06],
  ['E','Шкаф и комод',/единый платяной шкаф|Фортуна.*комод/i,'E3',1.65,1.16],
  ['D','Ванная при спальне',/Хельсингборг/i,'D4',1.15,.91],
];
const STEP=.065;
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const directions=[[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];

function makeNav(release,radius) {
  const doors=release.doors.map(spec=>({spec,angle:spec.angle}));
  const valid=radius===avatar.radius ? (x,z)=>walkAllowed(x,z,release,doors) : (x,z)=>
    release.floorPolygons.some(poly=>pointInPolygon(x,z,poly)) &&
    !release.colliders.some(box=>circleIntersectsBox(x,z,radius,box)) &&
    !doors.some(d=>hitsDoor(x,z,radius,d.spec,d.angle));
  const [x0,,z0]=release.bounds.min,[x1,,z1]=release.bounds.max;
  const columns=Math.ceil((x1-x0)/STEP)+1, rows=Math.ceil((z1-z0)/STEP)+1, count=columns*rows;
  const x=i=>x0+(i%columns)*STEP, z=i=>z0+Math.floor(i/columns)*STEP;
  const point=i=>[x(i),z(i)];
  const clear=new Uint8Array(count);
  for(let i=0;i<count;i++)clear[i]=Number(valid(x(i),z(i)));
  function segment(a,b) {
    const steps=Math.max(1,Math.ceil(distance(a,b)/.018));
    for(let k=0;k<=steps;k++){
      const t=k/steps;if(!valid(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))return false;
    }
    return true;
  }
  function nearest(p) {
    let best=-1,score=Infinity;
    for(let i=0;i<count;i++)if(clear[i]){
      const d=(x(i)-p[0])**2+(z(i)-p[1])**2;
      if(d<score&&segment(p,point(i))){score=d;best=i;}
    }
    return best;
  }
  // Breadth-first navigation only uses safe edges. With diagonals, reject corner-cutting.
  function flood(start) {
    const parent=new Int32Array(count).fill(-1), queue=new Int32Array(count);
    parent[start]=start;queue[0]=start;
    let head=0,tail=1;
    while(head<tail){
      const i=queue[head++], col=i%columns,row=Math.floor(i/columns);
      for(const [dx,dz] of directions){
        const nx=col+dx,nz=row+dz,j=i+dz*columns+dx;
        if(nx<0||nx>=columns||nz<0||nz>=rows||!clear[j]||parent[j]!==-1)continue;
        if(dx&&dz&&(!clear[i+dx]||!clear[i+dz*columns]))continue;
        parent[j]=i;queue[tail++]=j;
      }
    }
    return {parent,cells:queue.subarray(0,tail)};
  }
  function route(start,end,parent) {
    const reverse=[];
    for(let i=end;i!==start;i=parent[i]){if(i<0)throw Error('Недоступная точка маршрута');reverse.push(point(i));}
    const line=[point(start),...reverse.reverse()];
    const compact=[line[0]];
    for(let i=0;i<line.length-1;){
      let j=line.length-1;
      while(j>i&&!segment(line[i],line[j]))j--;
      if(j===i)throw Error('Столкновение на участке маршрута');
      compact.push(line[j]);i=j;
    }
    return compact;
  }
  return {point,nearest,flood,route,segment};
}

function sightPenalty(origin,target,colliders){
  const distanceTo=distance(origin,target);
  let blocked=0;
  // Ignore the target's own footprint; penalize intervening furniture.
  for(const box of colliders){
    if(circleIntersectsBox(...target,.075,box))continue;
    for(let d=.12;d<distanceTo-.06;d+=.14){
      const t=d/distanceTo;
      if(circleIntersectsBox(origin[0]+(target[0]-origin[0])*t,origin[1]+(target[1]-origin[1])*t,.01,box)){blocked++;break;}
    }
  }
  return blocked;
}

function targetPoint(technical,items,room,pattern,wallCode){
  const subject=items.find(item=>item.roomId===room && pattern.test(item.name));
  if(subject)return [subject.x/1000,subject.y/1000];
  const wall=technical.walls.find(item=>item.code===wallCode);
  if(!wall)throw Error('Нет координат стены '+wallCode);
  return wall.origin.map((v,j)=>(v+wall.direction[j]*wall.width/2)/1000);
}

function groupsNear(path,doors,radius){
  const groups=new Set();
  for(const d of doors){
    let found=false;
    for(let i=0;i<path.length&&!found;i++){
      const a=path[i], b=path[i+1]||a, steps=Math.max(1,Math.ceil(distance(a,b)/.10));
      for(let k=0;k<=steps;k++){
        const x=a[0]+(b[0]-a[0])*k/steps,z=a[1]+(b[1]-a[1])*k/steps;
        if(hitsDoor(x,z,radius+.38,d,0)||Math.hypot(x-d.hinge[0],z-d.hinge[2])<.86){found=true;break;}
      }
    }
    if(found)groups.add(d.group||d.node);
  }
  return [...groups];
}

export function buildTourRoute(release,technical,{radius=avatar.radius}={}){
  const plan=technical.plan, nav=makeNav(release,radius);
  const roomPolygons=new Map(plan.rooms.map(r=>[r.id,r.polygon.map(([x,y])=>[x/1000,y/1000])]));
  const spawn=[release.spawn[0],release.spawn[2]];
  let start=nav.nearest(spawn), last=spawn;
  if(start<0)throw Error('Входная точка экскурсии недоступна');
  const stops=[];
  for(const [roomId,label,pattern,wallCode,ideal,eyeTarget] of itinerary){
    const poly=roomPolygons.get(roomId);
    if(!poly)throw Error('В плане отсутствует помещение '+roomId);
    const focus=targetPoint(technical,plan.furniture,roomId,pattern,wallCode);
    if(!stops.length){
      stops.push({roomId,label,position:spawn,lookAt:[focus[0],eyeTarget,focus[1]],path:[spawn],openGroups:[]});
      continue;
    }
    const reachable=nav.flood(start), choices=[];
    for(const index of reachable.cells){
      const p=nav.point(index);
      if(!pointInPolygon(...p,poly))continue;
      const range=distance(p,focus), movement=distance(p,last);
      if(range<.18)continue;
      const score=Math.abs(range-ideal)+.8*Math.max(0,1.0-movement)+.035*movement;
      choices.push({index,p,score});
    }
    if(!choices.length)throw Error('Нет доступной позиции в помещении '+roomId);
    choices.sort((a,b)=>a.score-b.score);
    let best=null,bestScore=Infinity;
    for(const choice of choices){
      if(choice.score>=bestScore)break;
      const score=choice.score+.85*sightPenalty(choice.p,focus,release.colliders);
      if(score<bestScore){best=choice;bestScore=score;}
    }
    let path=nav.route(start,best.index,reachable.parent);
    if(distance(path[0],last)>0)path=[last,...path];
    stops.push({roomId,label,position:best.p,lookAt:[focus[0],eyeTarget,focus[1]],path,
                openGroups:groupsNear(path,release.doors,radius)});
    last=best.p;start=best.index;
  }
  return {stops,spawn,radius};
}

