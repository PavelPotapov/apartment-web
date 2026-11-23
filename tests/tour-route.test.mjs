import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildTourRoute} from '../public/tour-route.js';
import {avatar,pointInPolygon,walkAllowed} from '../public/movement.js';

function read(name){return JSON.parse(readFileSync(new URL('../public/data/'+name,import.meta.url),'utf8'));}
test('Экскурсия проходит по всем помещениям и открывает двери перед проходом',()=>{
  const release=read('release.json'), technical=read('technical.json');
  const tour=buildTourRoute(release,technical);
  assert.deepEqual([...new Set(tour.stops.map(s=>s.roomId))],['G','A','B','C','F','E','D']);
  assert.equal(tour.radius,avatar.radius);
  let position=tour.spawn;
  const opened=new Set();
  for(const stop of tour.stops){
    for(const id of stop.openGroups)opened.add(id);
    const doors=release.doors.map(spec=>({spec,angle:opened.has(spec.group||spec.node)?spec.angle:0}));
    assert.deepEqual(stop.path[0],position);
    assert.deepEqual(stop.path.at(-1),stop.position);
    assert.ok(stop.lookAt.every(Number.isFinite));
    const polygon=technical.plan.rooms.find(r=>r.id===stop.roomId).polygon.map(([x,y])=>[x/1000,y/1000]);
    assert.ok(pointInPolygon(...stop.position,polygon),stop.roomId);
    for(let j=1;j<stop.path.length;j++){
      const [x,z]=stop.path[j-1], [u,v]=stop.path[j];
      const steps=Math.ceil(Math.hypot(u-x,v-z)/.01);
      for(let k=0;k<=steps;k++){
        const t=k/steps;
        assert.ok(walkAllowed(x+(u-x)*t,z+(v-z)*t,release,doors),'Столкновение на пути к '+stop.label);
      }
    }
    position=stop.position;
  }
  assert.deepEqual(opened,new Set(release.doors.map(d=>d.group||d.node)));
});

