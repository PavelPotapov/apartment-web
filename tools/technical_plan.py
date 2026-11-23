"""Measured plan and section data extracted from the authoring scene. Public plan axes: X east, Y south (mm)."""
import collections
import math
import re
from mathutils import Vector
import numpy as np


def xy(point):
    return [round(point[0]*1000), round(-point[1]*1000)]


def add(p, d, distance):
    return [round(p[i] + d[i]*distance) for i in (0,1)]


def convex_outline(points):
    # Convex envelope of the evaluated assembly's horizontal projection at 1-mm precision.
    pts = sorted(set(map(tuple, np.rint(points).astype(int).tolist())))
    def half(seq):
        result = []
        for p in seq:
            while len(result)>1:
                a,b=result[-2:]
                if (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]) > 0:
                    break
                result.pop()
            result.append(p)
        return result
    return half(pts)[:-1] + half(reversed(pts))[:-1]


def cut_walls(scene, z=1.15):
    """Decompose the orthogonal structural mesh into nonoverlapping strips at the plan cut."""
    ob = next(o for o in scene.collection.objects if o.type=='MESH' and o.name.startswith('Стены и '))
    matrix=ob.matrix_world
    inv=matrix.inverted()
    direction=inv.to_3x3()@Vector((0,0,1))
    normal_matrix=inv.transposed().to_3x3()
    # Coordinates are on the drawing's millimetre grid. A one-micron interior sample
    # off the cell diagonal avoids intersecting two coincident triangle edges.
    grid=list(zip(*(xy(matrix@v.co) for v in ob.data.vertices)))
    xs,ys=[sorted(set(axis)) for axis in grid]
    active={}
    rectangles=[]
    for y0,y1 in zip(ys,ys[1:]):
        spans=[]
        for x0,x1 in zip(xs,xs[1:]):
            origin=inv@Vector(((x0+x1)*.0005+.0000007,-(y0+y1)*.0005+.0000003,z))
            hit,_,normal,_=ob.ray_cast(origin,direction)
            if hit and (normal_matrix@normal).z>.5:
                if spans and spans[-1][1]==x0:
                    spans[-1]=(spans[-1][0],x1)
                else:
                    spans.append((x0,x1))
        for key in list(active):
            if key not in spans:
                rectangles.append((key[0],active.pop(key),key[1],y0))
        for key in spans:active.setdefault(key,y0)
    rectangles.extend((x0,y0,x1,ys[-1]) for (x0,x1),y0 in active.items())
    if not rectangles:raise ValueError('Empty structural cut')
    return [[[x,y],[r,y],[r,b],[x,b]] for x,y,r,b in rectangles]


def door_head(scene,marker):
    height=marker.get('Высота проёма, мм')
    if height:return height,'project'
    # The jamb/head geometry and the new wall panel over a door are separate meshes.
    if marker.name.startswith('Д05'):
        arch=next((o for o in scene.objects if o.name.startswith('D2 · проём') and o.get('Высота проёма, мм')),None)
        if arch:return arch['Высота проёма, мм'],'project'
    hits=[]
    for o in scene.objects:
        if o.type!='MESH' or not o.name.startswith(('Стены и ', 'Заполнение над дверью')):continue
        inv=o.matrix_world.inverted()
        p=marker.matrix_world.translation
        hit,loc,_n,_k=o.ray_cast(inv@Vector((p.x,p.y,.15)), inv.to_3x3()@Vector((0,0,1)))
        if hit:hits.append(round((o.matrix_world@loc).z*1000))
    return (min(hits),'model') if hits else (None,'unknown')


def drawing_walls(scene,cameras):
    markers=[o for o in scene.objects if o.name.startswith(('Д','О')) and ' • ' in o.name and o.get('Ширина проёма, мм')]
    walls={}
    rooms=collections.defaultdict(list)
    for code,cam in cameras:
        p=xy(cam['origin_xyz'])
        d=[round(cam['u_xyz'][0],6),round(-cam['u_xyz'][1],6)]
        axes={'origin':p,'direction':d,'apertures':[]}
        wall_height=cam.get('ceiling_mm',2700)
        runs=list(cam.get('profile_runs',[cam['width_mm']]))
        u=0
        for index,width in enumerate(runs):
            if index%2:
                mid=add(p,d,u+width/2)
                matched=sorted((math.dist(mid,xy(o.matrix_world.translation)),o.name,o) for o in markers if abs(o['Ширина проёма, мм']-width)<=2)
                if not matched or matched[0][0]>420:raise ValueError(f'{code}: unmatched {width} mm opening')
                mark=matched[0][2]
                label=mark.name.split(' • ')[0]
                kind='window' if label.startswith('О') else ('passage' if label=='Д02' else 'door')
                if kind=='window':
                    head,source=mark['Верх проёма, мм'],'project'
                else:
                    head,source=door_head(scene,mark)
                axes['apertures'].append({'u':u,'width':width,'sill':mark.get('Низ проёма, мм',0),
                   'head':head,'modeledHead':head or wall_height,'headSource':source,'type':kind,'label':label})
            u+=width
        if u!=cam['width_mm']:raise ValueError(f'{code} dimension chain {u} != {cam["width_mm"]}')
        walls[code]=axes
        rooms[code[0]].append(p)
    return walls,[{'id':key,'polygon':points} for key,points in rooms.items()]


def socket_points(scene,walls):
    bynum=collections.defaultdict(list)
    for ob in scene.objects:
        num=ob.get('ЭП · номер')
        if num and ob.type=='MESH' and not ob.parent and not ob.get('archive_opening'):
            bynum[(ob['sector'],str(num))].append(ob)
    result=[]
    for (code,num),parts in sorted(bynum.items(),key=lambda pair:pair[0][1]):
        data=walls[code]
        physical=[ob for ob in parts if not ob.name.startswith('ЭП ')]
        ob=physical[0] if physical else parts[0]
        u=ob['U, мм']
        note=ob.get('Источник и уточнения','')
        spec=str(ob.get('H, мм / база',''))
        anchor=xy(ob.matrix_world.translation) if physical else add(data['origin'],data['direction'],u)
        offset=math.dist(anchor, add(data['origin'],data['direction'],u))
        window=next((op for op in data['apertures'] if op['type']=='window' and op['u']-2<=u<=op['u']+op['width']+2),None)
        if window and 'подоконник' in spec:
            heights=[window['sill']+int(re.search(r'\d+',spec)[0])]
            source='sill-relative'
            note=note+' Расчётная отметка от пола: '+str(heights[0])+' мм.'
        elif re.fullmatch(r'\s*\d+(?:\s*,\s*\d+)*\s*',spec):
            heights=sorted(set(map(int,re.findall(r'\d+',spec))))
            source='floor'
        else:
            heights=[]
            source='unknown'
        archival='архивн' in note.lower()
        placement='window' if window else ('countertop' if offset>300 else 'wall')
        entry={'number':num,'code':code,'u':u,'height':spec,'heights':heights,'heightsMm':heights,
               'heightSource':source,'placement':placement,'status':ob.get('Статус',''),
               'approximate':ob.get('Статус')!='Размер по ЭП' or source!='floor' or archival,
               'archived':archival,'window':bool(window),'x':anchor[0],'y':anchor[1],'note':note,
               'anchorSource':'model' if physical else 'wall-projection'}
        result.append(entry)
    return result


def artifact_type(name):
    text=name.casefold()
    if text.endswith(' · пол'):return None
    if any(x in text for x in ('стена изголовья','столешница с полуостровом','щека полуострова',
            'филёнка торца','карниз','бра в','рамк','фартук','буазери','паркет','картина','зеркало',
            'раскладка privilege','мраморный простенок','молдинг','оформление','фальшстена','над полуостровом',
            'стеллаж васту','телевизор','верхний шкаф','подсветк')) and 'полотенцесушитель' not in text:
        return None
    if 'радиатор' in text or 'полотенцесушитель' in text:return 'heating'
    if 'инсталляци' in text or 'стирки и сушки' in text or 'прачечный' in text or 'посудомоечная' in text:return 'service'
    if any(x in text for x in ('душ 1400','душевая колонна','ceramica nova','хельсингборг','мойка','тумба из ореха')):
        return 'plumbing'
    return 'furniture'


def furniture_shapes(scene):
    import bpy
    deps=bpy.context.evaluated_depsgraph_get()
    collection=next(c for c in scene.collection.children if c.get('apt_furniture'))
    shapes=[]
    sequence=collections.Counter()
    def footprint(room,root,parts,category,name=None):
        if not parts:return
        clouds=[]
        zmin,zmax=100,-100
        for ob in parts:
            ev=ob.evaluated_get(deps)
            mesh=ev.to_mesh()
            try:
                if not mesh or not mesh.vertices:continue
                vs=np.empty(len(mesh.vertices)*3,np.float32)
                mesh.vertices.foreach_get('co',vs)
                mat=np.array(ev.matrix_world)
                vs=vs.reshape(-1,3)@mat[:3,:3].T+mat[:3,3]
                zmin=min(zmin,vs[:,2].min());zmax=max(zmax,vs[:,2].max())
                clouds.extend(convex_outline(vs[:,:2]*[1000,-1000]))
            finally:ev.to_mesh_clear()
        if len(clouds)<3:return
        poly=convex_outline(np.asarray(clouds))
        if len(poly)<3:return
        tag={'furniture':'F','plumbing':'P','service':'S','heating':'H'}[category]
        sequence[room,tag]+=1
        identifier=f'{room}-{tag}{sequence[room,tag]:02d}'
        points=np.asarray(poly)
        center=(points.min(axis=0)+points.max(axis=0))/2
        shapes.append({'id':identifier,'roomId':room,'name':name or root.name,'category':category,
                       'polygon':poly,'x':round(center[0]),'y':round(center[1]),'bottom':round(zmin*1000),
                       'top':round(zmax*1000),'geometry':'projected-envelope'})
    for col in sorted(collection.children,key=lambda c:c.name):
        room=col.name[0]
        for root in sorted((o for o in col.objects if not o.parent and o.type=='EMPTY'),key=lambda o:o.name):
            category=artifact_type(root.name)
            if not category:continue
            children=[o for o in root.children_recursive if o.type in ('MESH','CURVE','SURFACE') and not o.hide_render]
            # The decorative wall cladding, sconces and mirror above a basin do not
            # belong to the washstand's footprint.
            if 'тумба из ореха' in root.name:
                children=[o for o in children if o.name.startswith(('Тумба','Столешница','Вклеенная','Слив умывальника','Латунный излив','Корпус смесителя','Крестовая рукоять'))]
            footprint(room,root,children,category)
            detail_names={'Дно мойки':'Чаша кухонной мойки','Вклеенная фарфоровая чаша':'Чаша умывальника',
                'Фланец слива Ø50':'Слив ванны','Слив умывальника':'Слив умывальника','Корпус смесителя':'Смеситель',
                'Стиральная машина':'Стиральная машина','Сушильная машина':'Сушильная машина','Слив':'Слив кухонной мойки'}
            if category in ('plumbing','service'):
                components=collections.defaultdict(list)
                for child in root.children:
                    n=re.sub(r'\.\d+$','',child.name)
                    if n in detail_names and child.type in ('MESH','CURVE'):
                        components[detail_names[n]].append(child)
                    elif n.startswith(('C4 · линейный слив','C4 · душевая стойка и смеситель')):
                        components[n].extend(o for o in child.children_recursive if o.type in ('MESH','CURVE'))
                for name,objects in components.items():
                    footprint(room,root,objects,'service',name)
    return shapes


def extract(scene, cameras):
    walls,rooms=drawing_walls(scene,cameras)
    cut=cut_walls(scene)
    points=np.array(cut).reshape(-1,2)
    return walls,{'units':'mm','bounds':[int(n) for n in (*points.min(axis=0),*points.max(axis=0))],
            'rooms':rooms,'furniture':furniture_shapes(scene),'sockets':socket_points(scene,walls),
            'wallPolygons':cut,'cutHeight':1150}

