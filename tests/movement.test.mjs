import test from 'node:test';
import assert from 'node:assert/strict';
import {walkAllowed,hitsDoor} from '../public/movement.js';
const state={floorPolygons:[[[0,0],[4,0],[4,4],[0,4]]],colliders:[[2,2,3,2.1]]};
const door={hinge:[1,0,1],closed:[1,.975,2,1.025]};
test('Пешеход остаётся внутри квартиры и останавливается перед стеной',()=>{
 assert.equal(walkAllowed(1.5,2.7,state,[]),true);
 assert.equal(walkAllowed(-.2,2,state,[]),false);
 assert.equal(walkAllowed(2.5,1.82,state,[]),false);
});
test('После поворота двери открывается проход и блокируется занятое створкой место',()=>{
 assert.equal(hitsDoor(1.65,1,.12,door,0),true);
 assert.equal(hitsDoor(1.65,1,.12,door,Math.PI/2),false);
 assert.equal(hitsDoor(1,.35,.12,door,Math.PI/2),true);
});

