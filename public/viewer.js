import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {jsonAsset,projectAsset,reportError} from './data.js';
import {avatar,walkAllowed,hitsDoor} from './movement.js';
const $=id=>document.getElementById(id), stage=$('stage'),canvas=$('scene'),progress=$('progress');
let mode='orbit',release,model,renderer,world,camera,orbit,doors=[],ceiling=[],yaw=0,pitch=0,orbitReady=false;
let previous=0, drag=null, nearest=null, walkingPosition=null, walkingYaw=0,walkingPitch=0;
const keys=new Set(), held=new Set(), modes=Array.from(document.querySelectorAll('[data-mode]'));
const zoomControls=document.querySelector('.zoom-controls'), walkControl=document.querySelector('.walk-control');
const center=new THREE.Vector3(), size=new THREE.Vector3(),temp=new THREE.Vector3();
let radius=10;
function setStatus(){
 const label=nearest ? (Math.abs(nearest.target)>.01?'Закрыть дверь':'Открыть дверь') : 'Дверь';
 if($('door').dataset.label!==label){
  $('door').replaceChildren(document.createTextNode(label+' '),Object.assign(document.createElement('kbd'),{textContent:'G'}));$('door').dataset.label=label;
 }
 $('door').disabled=!nearest;$('door').title=nearest?.spec.label||'Подойдите к двери';
}
function orbitHome(){
 const vh=Math.tan(THREE.MathUtils.degToRad(camera.fov)*.5);
 const distance=radius*1.02/(vh*Math.min(1,camera.aspect));
 orbit.target.copy(center);orbit.target.y=center.y*.4;
 camera.position.copy(orbit.target).addScaledVector(temp.set(.52,1.26,1).normalize(),distance);
 orbit.minDistance=.28;orbit.maxDistance=distance*3;orbit.update();
}
function firstPosition(){
 const p=release.spawn;return new THREE.Vector3(p[0],avatar.eyeHeight+(release.floorY||0),p[2]);
}
function setMode(which,reset=false){
 if(!model)return;
 if(mode==='walk' && which==='orbit'){
  walkingPosition=camera.position.clone();walkingYaw=yaw;walkingPitch=pitch;
 }
 mode=which;orbit.enabled=which==='orbit';const walk=which==='walk';
 ceiling.forEach(o=>o.visible=walk);
 stage.classList.toggle('walk-mode',walk);zoomControls.hidden=walk;walkControl.hidden=!walk;
 modes.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===which)));
 $('mode-heading').textContent=walk?'Прогулка по квартире':'Обзор квартиры';
 $('mode-tip').textContent=walk?'WASD или стрелки · потяните изображение для осмотра':'Поворот · перетаскивание, приближение · прокрутка';
 if(walk){
  if(reset||!walkingPosition){walkingPosition=firstPosition();walkingYaw=release.heading??0;walkingPitch=0}
  yaw=walkingYaw;pitch=walkingPitch;camera.position.copy(walkingPosition);applyLook();
 }else{orbitHome();orbitReady=true}
 keys.clear();held.clear();nearest=null;setStatus();
}
function applyLook(){camera.rotation.order='YXZ';camera.rotation.set(pitch,yaw,0,'YXZ')}
function resize(){
 const w=Math.max(1,stage.clientWidth),h=Math.max(1,stage.clientHeight);renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
}
function move(dx,dz,dt){
 if(!dx&&!dz)return;
 const norm=Math.hypot(dx,dz), step=dt*avatar.speed/norm;
 const vx=(dx*Math.cos(yaw)+dz*Math.sin(yaw))*step,vz=(-dx*Math.sin(yaw)+dz*Math.cos(yaw))*step;
 const count=Math.max(1,Math.ceil(Math.hypot(vx,vz)/.055));
 for(let i=0;i<count;i++){
  const p=camera.position;
  if(walkAllowed(p.x+vx/count,p.z,release,doors))p.x+=vx/count;
  if(walkAllowed(p.x,p.z+vz/count,release,doors))p.z+=vz/count;
 }
}
function movement(t){
 const down=(a,b,c)=>keys.has(a)||keys.has(b)||held.has(c);
 const dx=Number(down('KeyD','ArrowRight','right'))-Number(down('KeyA','ArrowLeft','left'));
 const dz=Number(down('KeyS','ArrowDown','backward'))-Number(down('KeyW','ArrowUp','forward'));
 move(dx,dz,t);
}
function findDoor(){
 const p=camera.position;camera.getWorldDirection(temp);let best=null,score=Infinity;
 for(const d of doors){
  const [x0,z0,x1,z1]=d.spec.closed,dx=(x0+x1)/2-p.x,dz=(z0+z1)/2-p.z,dist=Math.hypot(dx,dz);
  if(dist>1.65)continue;
  const dot=(dx*temp.x+dz*temp.z)/Math.max(dist,.01);
  if(dot<-.3&&dist>.5)continue;const value=dist-dot*.35;
  if(value<score){score=value;best=d}
 }
 nearest=best;setStatus();
}
function operateDoor(){
 if(!nearest||mode!=='walk')return;
 const group=nearest.spec.group||nearest.spec.node, shouldOpen=Math.abs(nearest.target)<.01;
 for(const d of doors)if((d.spec.group||d.spec.node)===group)d.target=shouldOpen?d.spec.angle:0;
 setStatus();
}
function animate(now){
 const dt=Math.min(.05,(now-previous)/1000||0);previous=now;
 for(const d of doors){
  const delta=d.target-d.angle;if(Math.abs(delta)<.0001)continue;
  const angle=d.angle+Math.sign(delta)*Math.min(Math.abs(delta),dt*2.25);
  if(mode==='walk'&&hitsDoor(camera.position.x,camera.position.z,avatar.radius,d.spec,angle))continue;
  d.angle=angle;d.object.rotation.y=d.rest+angle;
 }
 if(mode==='walk'){movement(dt);findDoor()}else if(orbitReady)orbit.update();
 renderer.render(world,camera);requestAnimationFrame(animate);
}
function zoom(factor){
 const delta=temp.subVectors(camera.position,orbit.target), next=THREE.MathUtils.clamp(delta.length()*factor,orbit.minDistance,orbit.maxDistance);
 camera.position.copy(orbit.target).add(delta.setLength(next));orbit.update();
}
function bind(){
 modes.forEach(b=>b.onclick=()=>{if(b.dataset.mode!==mode)setMode(b.dataset.mode);canvas.focus({preventScroll:true})});
 $('reset').onclick=()=>setMode(mode,true);$('zoom-in').onclick=()=>zoom(.80);$('zoom-out').onclick=()=>zoom(1.25);
 $('door').onclick=operateDoor;
 const stop=()=>{keys.clear();held.clear();drag=null;document.querySelectorAll('.held').forEach(b=>b.classList.remove('held'))};
 window.addEventListener('blur',stop);document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});
 window.addEventListener('keydown',e=>{
  if(mode!=='walk'||$('controls-dialog').open||e.altKey||e.ctrlKey||e.metaKey)return;
  if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','KeyW','KeyA','KeyS','KeyD','KeyG'].includes(e.code)){
   e.preventDefault();if(e.code==='KeyG'&&!e.repeat)operateDoor();else keys.add(e.code);
  }
 });window.addEventListener('keyup',e=>keys.delete(e.code));
 for(const b of document.querySelectorAll('[data-move]')){
  const v=b.dataset.move;
  b.onpointerdown=e=>{e.preventDefault();b.setPointerCapture(e.pointerId);held.add(v);b.classList.add('held');
    const x=Number(v==='right')-Number(v==='left'),z=Number(v==='backward')-Number(v==='forward');move(x,z,.055)};
  const end=()=>{held.delete(v);b.classList.remove('held')};b.onpointerup=end;b.onpointercancel=end;b.onlostpointercapture=end;
  b.onclick=e=>{if(e.detail===0&&mode==='walk')move(Number(v==='right')-Number(v==='left'),Number(v==='backward')-Number(v==='forward'),.12)};
 }
 canvas.addEventListener('pointerdown',e=>{
  if(mode!=='walk'||drag!==null||e.button!==0)return;
  canvas.focus({preventScroll:true});drag={id:e.pointerId,x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);
 });
 canvas.addEventListener('pointermove',e=>{
  if(!drag||drag.id!==e.pointerId||mode!=='walk')return;
  yaw-=(e.clientX-drag.x)*.004;pitch=THREE.MathUtils.clamp(pitch-(e.clientY-drag.y)*.004,-1.48,1.48);
  drag.x=e.clientX;drag.y=e.clientY;applyLook();
 });
 canvas.addEventListener('lostpointercapture',()=>{drag=null});canvas.addEventListener('contextmenu',e=>e.preventDefault());
 $('help').onclick=()=>{stop();$('controls-dialog').showModal()};$('close-help').onclick=()=>$('controls-dialog').close();
 window.addEventListener('resize',resize);new ResizeObserver(resize).observe(stage);
}
try{
 release=await jsonAsset('release.json');
 renderer=new THREE.WebGLRenderer({canvas,antialias:true,powerPreference:'high-performance'});renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.7));renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.00;
 world=new THREE.Scene();world.background=new THREE.Color(0xe9e9df);
 const pmrem=new THREE.PMREMGenerator(renderer),env=new RoomEnvironment(),map=pmrem.fromScene(env,.035);world.environment=map.texture;world.environmentIntensity=.85;pmrem.dispose();env.dispose();
 world.add(new THREE.HemisphereLight(0xfff8e7,0xc1b39b,1.00));
 const sun=new THREE.DirectionalLight(0xfff0d7,1.75);sun.position.set(-4,10,-1);world.add(sun);
 camera=new THREE.PerspectiveCamera(48,1,.035,160);resize();
 orbit=new OrbitControls(camera,canvas);orbit.enableDamping=false;orbit.maxPolarAngle=Math.PI*.47;orbit.screenSpacePanning=true;
 const gltf=await new GLTFLoader().loadAsync(projectAsset(release.model).href,e=>{progress.textContent=e.total?'Загружено '+Math.round(e.loaded/e.total*100)+' %':'Загружено '+(e.loaded/1048576).toFixed(1)+' МБ'});
 model=gltf.scene;world.add(model);
 for(const spec of release.doors){const object=model.getObjectByName(spec.node);if(!object)throw Error('В модели отсутствует дверь '+spec.node);doors.push({spec,object,rest:object.rotation.y,angle:0,target:0})}
 ceiling=release.ceilingNodes.map(name=>model.getObjectByName(name)).filter(Boolean);
 const box=new THREE.Box3(new THREE.Vector3(...release.bounds.min),new THREE.Vector3(...release.bounds.max));box.getCenter(center);box.getSize(size);radius=size.length()*.5;
 bind();setMode(new URL(location.href).searchParams.get('mode')==='walk'?'walk':'orbit');$('loader').hidden=true;requestAnimationFrame(animate);
}catch(e){
 console.error(e);$('loader').querySelector('.loader-glyph').hidden=true;$('loader').querySelector('strong').textContent='Не удалось открыть 3D-сцену';
 reportError(progress,'Проверьте соединение и поддержку WebGL 2 в браузере.');const link=document.createElement('a');link.href='./index.html';link.textContent='Открыть чертежи и PDF';$('loader').append(link);
}
