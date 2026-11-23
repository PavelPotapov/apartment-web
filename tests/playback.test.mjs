import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {advancePlayback,approachDoors,excursion,panorama} from '../public/tour-playback.js';
import {buildTourRoute} from '../public/tour-route.js';
import {avatar,hitsDoor,walkAllowed} from '../public/movement.js';
const read=file=>JSON.parse(readFileSync(new URL('../public/data/'+file,import.meta.url)));

test('stationary panorama looks up and down, pauses and returns to the initial heading',()=>{
 const p=panorama({x:4.1,y:1.63,z:3.2,yaw:.25,pitch:.14});let up=0,down=0;
 for(let i=0;i<750;i++){
  advancePlayback(p,.033);up=Math.max(up,p.pose.pitch);down=Math.min(down,p.pose.pitch);
  if(i===150){p.paused=true;const t=p.time;advancePlayback(p,.5);assert.equal(t,p.time);p.paused=false}
 }
 assert.ok(p.done);assert.ok(up>.69&&down<-.64);assert.equal(p.pose.x,4.1);assert.equal(p.pose.z,3.2);
 assert.ok(Math.abs(p.pose.yaw-.25-2*Math.PI)<1e-7);assert.ok(Math.abs(p.pose.pitch-.14)<1e-7);
});
test('animated tour walks all stops and opens the swinging doors without intersecting them',()=>{
 const release=read('release.json'),route=buildTourRoute(release,read('technical.json'));
 const p=excursion(route,avatar.eyeHeight,release.heading||0);
 const doors=release.doors.map(spec=>({spec,angle:0,target:0})), visited=new Set();
 const env={allowed:(x,z)=>walkAllowed(x,z,release,doors),waitForDoors:(stop,pose)=>approachDoors(doors,stop,pose)};
 const dt=.032;
 for(let frame=0;frame<24000&&!p.done;frame++){
  for(const d of doors){
   const delta=d.target-d.angle,angle=d.angle+Math.sign(delta)*Math.min(Math.abs(delta),dt*2.25);
   if(!hitsDoor(p.pose.x,p.pose.z,avatar.radius,d.spec,angle))d.angle=angle;
  }
  advancePlayback(p,dt,env);assert.ok(!p.error,p.error+' at stop '+p.index);
  assert.ok(env.allowed(p.pose.x,p.pose.z));if(p.phase==='observe')visited.add(p.index);
 }
 assert.ok(p.done);assert.equal(visited.size,route.stops.length);assert.ok(doors.every(d=>Math.abs(d.angle-d.spec.angle)<.005));
});
