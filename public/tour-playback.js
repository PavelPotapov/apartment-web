// Camera poses in metres / radians. Playback uses the same collision test as manual walking.
const tau=2*Math.PI;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const ease=t=>t*t*(3-2*t);
const wrap=a=>Math.atan2(Math.sin(a),Math.cos(a));
function turn(from,to,rate,dt){return from+clamp(wrap(to-from),-rate*dt,rate*dt)}
function keyframe(t,frames){
 let i=1;while(i<frames.length-1&&frames[i][0]<t)i++;
 const [ta,a]=frames[i-1],[tb,b]=frames[i];return a+(b-a)*ease(clamp((t-ta)/(tb-ta),0,1));
}
export function panorama(pose){
 return {kind:'panorama',pose:{...pose},initial:{...pose},time:0,progress:0};
}
export function excursion(route,eyeHeight,heading){
 if(!route?.stops?.length)throw Error('В экскурсии нет остановок.');
 return {kind:'tour',route,index:0,segment:0,phase:'walk',time:0,blocked:0,progress:0,
  pose:{x:route.spawn[0],z:route.spawn[1],y:eyeHeight,yaw:heading,pitch:0}};
}
function updatePanorama(player,dt){
 player.time+=dt;const t=clamp(player.time/24,0,1),start=player.initial,p=player.pose;
 p.yaw=start.yaw+tau*(t-Math.sin(tau*t)/tau*.72);
 p.pitch=keyframe(t,[[0,start.pitch],[.23,.72],[.45,0],[.70,-.68],[.87,-.12],[1,start.pitch]]);
 player.progress=t;if(t===1)player.done=true;
}
function observe(player,stop,dt){
 const p=player.pose,[x,y,z]=stop.lookAt;
 if(player.time===0){player.baseYaw=p.yaw;player.basePitch=p.pitch}
 player.time+=dt;
 const duration=stop.roomId==='G'?12:8.4,t=Math.min(player.time/duration,1);
 const axis=player.baseYaw+wrap(Math.atan2(-(x-p.x),-(z-p.z))-player.baseYaw);
 const pitch=clamp(Math.atan2(y-p.y,Math.hypot(x-p.x,z-p.z)),-.45,.45);
 const gain=ease(Math.min(t/.21,1));
 const reach=stop.roomId==='G'?1.55:.80;
 p.yaw=player.baseYaw+(axis-player.baseYaw)*gain+keyframe(t,[[0,0],[.23,0],[.48,-reach*.68],[.8,reach],[1,0]]);
 p.pitch=player.basePitch+(pitch-player.basePitch)*gain+keyframe(t,[[0,0],[.24,0],[.48,.39],[.78,-.39],[1,0]]);
 player.progress=(player.index+.6+.4*t)/player.route.stops.length;
 if(t<1)return;
 player.index++;player.phase='walk';player.segment=0;player.time=0;
 if(player.index===player.route.stops.length)player.done=true;
}
function walk(player,stop,dt,environment){
 const p=player.pose,path=stop.path;
 if(environment.waitForDoors(stop,p)){
  player.doorWait=(player.doorWait||0)+dt;
  if(player.doorWait>7)player.error='Дверь не может открыться. Продолжите прогулку вручную.';
  return;
 }
 player.doorWait=0;
 while(player.segment<path.length&&Math.hypot(path[player.segment][0]-p.x,path[player.segment][1]-p.z)<.0001)player.segment++;
 if(player.segment>=path.length){player.phase='observe';player.time=0;return}
 const [gx,gz]=path[player.segment],dx=gx-p.x,dz=gz-p.z,dist=Math.hypot(dx,dz);
 const desired=Math.atan2(-dx,-dz),error=Math.abs(wrap(desired-p.yaw));
 p.yaw=turn(p.yaw,desired,1.65,dt);p.pitch=turn(p.pitch,-.045,.66,dt);
 if(error>.86)return;
 const advance=Math.min(.89*dt*Math.max(.42,1-error*.52),dist);
 const x=p.x+advance*dx/dist,z=p.z+advance*dz/dist;
 if(!environment.allowed(x,z)){
   player.blocked+=dt;
   if(player.blocked>3)player.error='Проход занят. Продолжите вручную или начните экскурсию заново.';
   return;
 }
 p.x=x;p.z=z;player.blocked=0;player.progress=(player.index+.6*player.segment/Math.max(1,path.length))/player.route.stops.length;
}
export function advancePlayback(player,dt,environment){
 if(!player||player.done||player.paused||player.error)return;
 if(player.kind==='panorama'){updatePanorama(player,dt);return}
 const stop=player.route.stops[player.index];
 if(player.phase==='observe')observe(player,stop,dt);
 else walk(player,stop,dt,environment);
}

export function approachDoors(doors,stop,p){
 let waiting=false;
 for(const d of doors){
  if(!stop.openGroups.includes(d.spec.group||d.spec.node))continue;
  const [hx,,hz]=d.spec.hinge;
  if(Math.hypot(p.x-hx,p.z-hz)>1.85)continue;
  d.target=d.spec.angle;if(Math.abs(d.angle-d.target)>.005)waiting=true;
 }
 return waiting;
}

