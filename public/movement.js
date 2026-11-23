export const avatar = Object.freeze({height:1.75, eyeHeight:1.63, mass:80, radius:.225, speed:1.55});
export function circleIntersectsBox(x,z,r,[x0,z0,x1,z1]){
 const dx=x-Math.max(x0,Math.min(x,x1)),dz=z-Math.max(z0,Math.min(z,z1));return dx*dx+dz*dz<r*r;
}
export function pointInPolygon(x,z,poly){
 let inside=false;
 for(let i=0,j=poly.length-1;i<poly.length;j=i++){
  const [ax,az]=poly[i],[bx,bz]=poly[j];
  if ((az>z)!==(bz>z) && x<(bx-ax)*(z-az)/(bz-az)+ax) inside=!inside;
 }
 return inside;
}
export function hitsDoor(x,z,r,door,angle){
 const [hx,,hz]=door.hinge,c=Math.cos(angle),s=Math.sin(angle),dx=x-hx,dz=z-hz;
 return circleIntersectsBox(hx+c*dx-s*dz,hz+s*dx+c*dz,r,door.closed);
}
export function walkAllowed(x,z,state,doors){
 if(state.floorPolygons?.length&&!state.floorPolygons.some(p=>pointInPolygon(x,z,p)))return false;
 if(state.colliders.some(box=>circleIntersectsBox(x,z,avatar.radius,box)))return false;
 return !doors.some(d=>hitsDoor(x,z,avatar.radius,d.spec,d.angle));
}

