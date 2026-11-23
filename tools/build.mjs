import {readFile, stat, mkdir, cp, rm} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)), source=path.join(root,'public'),data=path.join(source,'data');
function local(base,file){
 if(typeof file!=='string'||!file||path.isAbsolute(file)||file.includes('\\')||file.split('/').includes('..')||file.includes(':'))throw Error('Expected relative project path');
 return path.join(base,file);
}
const read=async(base,file)=>JSON.parse(await readFile(local(base,file),'utf8'));
const release=await read(data,'release.json'),tech=await read(data,release.technical);
if(release.schema!==1||!release.version||!release.sourceDigest||!tech.rooms?.length||!tech.walls?.length)throw Error('Missing release metadata');
const model=await readFile(local(data,release.model));
if(model.toString('ascii',0,4)!=='glTF'||model.readUInt32LE(4)!==2||model.readUInt32LE(8)!==model.length)throw Error('Invalid glTF binary');
const doc=JSON.parse(model.toString('utf8',20,20+model.readUInt32LE(12))),nodes=new Set(doc.nodes.map(n=>n.name));
if(!release.ceilingNodes?.length||!release.doors?.length)throw Error('Missing navigation parts');
for(const name of [...release.ceilingNodes,...release.doors.map(d=>d.node)])if(!nodes.has(name))throw Error('Unknown model node '+name);
const vector=(v,n)=>Array.isArray(v)&&v.length===n&&v.every(Number.isFinite);
if(!vector(release.spawn,3)||!vector(release.bounds.min,3)||!vector(release.bounds.max,3)||!release.floorPolygons?.length||
 !release.floorPolygons.every(p=>p.length>=3&&p.every(v=>vector(v,2)))||!release.colliders?.length||!release.colliders.every(b=>vector(b,4)))throw Error('Invalid navigation mesh');
if(!release.doors.every(d=>vector(d.closed,4)&&vector(d.hinge,3)&&Number.isFinite(d.angle)))throw Error('Invalid door configuration');
const frontKeys=['plan','dimensions','sockets','coordinates','plumbing'];
if(tech.frontSheets?.length!==frontKeys.length || !tech.frontSheets.every((s,i)=>s.key===frontKeys[i] && s.page===i+1 && s.title))throw Error('Incomplete opening sheets');
if(!tech.plan || tech.plan.units!=='mm' || !tech.plan.rooms?.length || !tech.plan.sockets?.length || !tech.plan.furniture?.some(i=>i.category==='plumbing'))throw Error('Incomplete technical plan');
const wallPlan=tech.plan;
const footprint=p=>Array.isArray(p)&&p.length>=3&&p.every(point=>vector(point,2));
if(!vector(wallPlan.bounds,4)||!wallPlan.rooms.every(r=>footprint(r.polygon))||
 !wallPlan.wallPolygons?.length||!wallPlan.wallPolygons.every(footprint)||
 !wallPlan.furniture.every(i=>i.id&&footprint(i.polygon))||
 !wallPlan.sockets.every(s=>s.code&&Number.isFinite(s.x)&&Number.isFinite(s.y)&&Number.isFinite(s.u)&&s.heightsMm?.length&&s.heightsMm.every(Number.isFinite)))
 throw Error('Invalid technical plan geometry or electrical coordinates');
const roomIds=new Set(tech.rooms.map(r=>r.id)),wallIds=new Set();
for(const [index,wall] of tech.walls.entries()){
 if(!roomIds.has(wall.roomId)||wallIds.has(wall.code)||!wall.width||!wall.height||wall.page!==index+tech.frontSheets.length+1)throw Error('Invalid sheet '+wall.code);
 wallIds.add(wall.code);
 if(!vector(wall.origin,2)||!vector(wall.direction,2)||!Array.isArray(wall.apertures)||!vector(wall.elevations?.extent,4))throw Error('Invalid wall drawing coordinates '+wall.code);
 for(const image of [wall.image,wall.elevations.empty,wall.elevations.furnished]){
  if(!(await stat(local(data,image))).size)throw Error('Empty drawing '+wall.code);
 }
}
const pdf=await readFile(local(data,release.pdf));if(!pdf.subarray(0,5).equals(Buffer.from('%PDF-')))throw Error('Invalid PDF');
for(const file of ['index.html','scene.html','viewer.js','movement.js','reference.js','assets/living.webp','vendor/three/build/three.module.min.js'])await stat(local(source,file));
const dist=path.join(root,'dist');await rm(dist,{recursive:true,force:true});await mkdir(dist,{recursive:true});await cp(source,dist,{recursive:true});
console.log('Built release '+release.version+': '+tech.walls.length+' wall sheets, '+release.doors.length+' door leaves.');

