"""Extract public render geometry, door hinges, collision boundaries and room outlines.
Run only in a disposable background Blender process. Dimensions are metres.
"""
import collections
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

OUT = Path(sys.argv[sys.argv.index('--') + 1])
SCENE = bpy.context.scene
PITCH = .0005  # signed short at half-millimetre resolution across the apartment
AXES = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)
DRAWABLE = {'MESH', 'CURVE', 'SURFACE'}
VISIBLE = ('Дверь ·', 'Окна ·', 'Потолок ·', 'Потолочный карниз', 'Потолочный свет',
           'Текстиль ·', 'Оснащение ·', 'Зеркало ·', 'Пол ·')
ROUND = lambda a: [round(float(x), 4) for x in a]


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def read_array(collection, field, columns, dtype):
    a = np.empty(len(collection) * columns, dtype=dtype)
    collection.foreach_get(field, a)
    return a.reshape((-1, columns)) if columns > 1 else a


class BinaryModel:
    def __init__(self):
        self.binary = bytearray()
        self.doc = {'asset': {'version': '2.0', 'generator': 'Apartment release'},
                    'extensionsUsed': ['KHR_mesh_quantization'], 'extensionsRequired': ['KHR_mesh_quantization'],
                    'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
                    'materials': [], 'bufferViews': [], 'accessors': []}
        self.material_cache = {}
        self.texture_cache = {}

    def view(self, payload, target=None):
        self.binary.extend(bytes(-len(self.binary) % 4))
        view = {'buffer': 0, 'byteOffset': len(self.binary), 'byteLength': len(payload)}
        if target:
            view['target'] = target
        self.binary.extend(payload)
        self.doc['bufferViews'].append(view)
        return len(self.doc['bufferViews']) - 1

    def attribute(self, arr, component, kind, normalized=False):
        is_index = kind == 'SCALAR'
        view = self.view(arr.tobytes(), 34963 if is_index else 34962)
        # Non-index vertex data must start on 4-byte boundaries for each element.
        # Vector3 SHORT/BYTE arrays have one pad component per element.
        acc = {'bufferView': view, 'type': kind, 'componentType': component, 'count': len(arr)}
        if not is_index:
            self.doc['bufferViews'][view]['byteStride'] = arr.strides[0]
        if normalized:
            acc['normalized'] = True
        if kind == 'VEC3' and component == 5122:
            acc['min'] = arr[:, :3].min(axis=0).tolist()
            acc['max'] = arr[:, :3].max(axis=0).tolist()
        self.doc['accessors'].append(acc)
        return len(self.doc['accessors']) - 1

    def texture(self, im):
        if im.name in self.texture_cache:
            return self.texture_cache[im.name]
        if im.packed_file:
            data = im.packed_file.data
        else:
            # Use only images on a published material, never guides or the electrical plan image.
            data = Path(bpy.path.abspath(im.filepath)).read_bytes()
        if data.startswith(b'\x89PNG'):
            mime = 'image/png'
        elif data.startswith(b'\xff\xd8'):
            mime = 'image/jpeg'
        else:
            raise ValueError('Material texture needs PNG or JPEG: '+im.name)
        idx = len(self.doc.setdefault('images', []))
        self.doc['images'].append({'mimeType': mime, 'bufferView': self.view(data)})
        self.doc.setdefault('textures', []).append({'source': idx})
        self.texture_cache[im.name] = idx
        return idx

    def material(self, mat):
        name = mat.name if mat else 'Штукатурка'
        if name in self.material_cache:
            return self.material_cache[name]
        rgb = tuple(mat.diffuse_color[:3]) if mat else (.77, .74, .71)
        rough, metal, alpha = .65, 0., 1.
        image = None
        emission = None
        if mat and mat.node_tree:
            nodes = mat.node_tree.nodes
            p = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if p:
                base = p.inputs['Base Color']
                if not base.is_linked:
                    rgb = tuple(base.default_value[:3])
                else:
                    # Trace only the RGB shader branch; bump maps are not colour maps.
                    queue = [base.links[0].from_node]
                    visited = set()
                    while queue:
                        n = queue.pop(0)
                        if n in visited:
                            continue
                        visited.add(n)
                        if n.type == 'TEX_IMAGE' and n.image:
                            image = n.image
                            break
                        if n.type == 'VALTORGB':
                            rgb = tuple(n.color_ramp.evaluate(.50)[:3])
                        queue.extend(socket.links[0].from_node for socket in n.inputs if socket.is_linked)
                rough = float(p.inputs['Roughness'].default_value)
                metal = float(p.inputs['Metallic'].default_value)
                alpha = float(p.inputs['Alpha'].default_value)
                if p.inputs['Emission Strength'].default_value > 0:
                    emission = ROUND(np.clip(p.inputs['Emission Color'].default_value[:3], 0, 1))
                if p.inputs['Transmission Weight'].default_value > .3:
                    alpha = min(alpha, .27)
        lower = name.casefold()
        if 'стекло' in lower or 'хрусталь' in lower:
            alpha = min(alpha, .38 if 'хрусталь' in lower else .23)
        if 'тюль' in lower:
            alpha = min(alpha, .50)
        pbr = {'baseColorFactor': ROUND([*([1, 1, 1] if image else np.clip(rgb, 0, 1)), alpha]),
               'roughnessFactor': max(.08, rough), 'metallicFactor': metal}
        material = {'name': name, 'doubleSided': True, 'pbrMetallicRoughness': pbr}
        if alpha < .998:
            material['alphaMode'] = 'BLEND'
        if image:
            pbr['baseColorTexture'] = {'index': self.texture(image)}
        if emission:
            material['emissiveFactor'] = emission
        idx = len(self.doc['materials'])
        self.doc['materials'].append(material)
        self.material_cache[name] = (idx, bool(image))
        return idx, bool(image)

    def primitive(self, batches, material):
        # Positions/normals are already quantized. Share corner vertices before writing indices.
        stream = np.concatenate(batches, axis=0)
        packed = np.ascontiguousarray(stream).view(np.dtype((np.void, stream.dtype.itemsize * stream.shape[1]))).ravel()
        _, first, indices = np.unique(packed, return_index=True, return_inverse=True)
        unique = stream[first]
        pos = np.zeros((len(unique), 4), dtype='<i2')
        norm = np.zeros((len(unique), 4), dtype='i1')
        pos[:, :3] = unique[:, :3]
        norm[:, :3] = unique[:, 3:6]
        attrs = {'POSITION': self.attribute(pos, 5122, 'VEC3'), 'NORMAL': self.attribute(norm, 5120, 'VEC3', True)}
        if unique.shape[1] == 8:
            uv = np.ascontiguousarray(unique[:,6:8], dtype='<f4') / 16384
            attrs['TEXCOORD_0'] = self.attribute(uv, 5126, 'VEC2')
        indices = indices.astype('<u2' if len(unique) < 65536 else '<u4')
        return {'material': material, 'attributes': attrs,
                'indices': self.attribute(indices, 5123 if indices.itemsize == 2 else 5125, 'SCALAR')}

    def finish(self, batches, hinges):
        for name, by_material in batches.items():
            primitives = [self.primitive(stream, mat) for mat, stream in by_material.items()]
            mesh = len(self.doc['meshes'])
            self.doc['meshes'].append({'name': 'Geometry_'+name, 'primitives': primitives})
            self.doc['scenes'][0]['nodes'].append(len(self.doc['nodes']))
            self.doc['nodes'].append({'name': name, 'mesh': mesh, 'scale': [PITCH]*3, 'translation': ROUND(hinges[name])})
        payload = self.binary
        self.doc['buffers'] = [{'byteLength': len(payload)}]
        header = json.dumps(self.doc, ensure_ascii=False, separators=(',', ':')).encode()
        header += b' ' * (-len(header) % 4)
        payload.extend(bytes(-len(payload) % 4))
        with (OUT / 'apartment.glb').open('wb') as f:
            f.write(struct.pack('<4sII', b'glTF', 2, 28 + len(header) + len(payload)))
            f.write(struct.pack('<I4s', len(header), b'JSON'))
            f.write(header)
            f.write(struct.pack('<I4s', len(payload), b'BIN\0'))
            f.write(payload)


def public_objects():
    chosen = {o: 'Architecture' for o in SCENE.collection.objects if o.type == 'MESH'}
    furniture = set()
    for col in SCENE.collection.children:
        if col.get('apt_furniture'):
            for room in col.children:
                for o in room.all_objects:
                    chosen[o] = 'Room_'+room.name.split(' ')[0]
                    furniture.add(o)
        elif col.get('apt_plinth') or col.name.startswith(VISIBLE) or col.get('web_export'):
            group = 'Ceiling' if col.name.startswith('Потолок ·') else 'Finishes'
            for o in col.all_objects:
                chosen[o] = group
    return chosen, furniture


def hinges_for(objects):
    doors = []
    origins = collections.defaultdict(lambda: np.zeros(3))
    # D05 is modelled half-open. Establish its closed reference pose only in this export.
    for o in objects:
        if 'петли полотна' in o.name:
            code = o.name.split(' ')[0]
            angle = {'B2': 90, 'C3': 90, 'E4': -90, 'F1': 90}.get(code, 90)
        elif o.name.startswith('Д05 · створка'):
            first = o.name.endswith('1')
            o.rotation_euler.z = (-1 if first else 1) * math.pi / 2
            code = 'D05_'+('1' if first else '2')
            angle = 90 if first else -90
        elif o.get('web_door'):
            code = str(o['web_door'])
            angle = float(o.get('web_swing_degrees', 90))
        else:
            continue
        node = 'Door_'+code
        for child in o.children_recursive:
            if child in objects:
                objects[child] = node
        pivot = AXES @ o.matrix_world.translation
        origins[node] = pivot
        doors.append({'node': node, 'label': o.parent.name if o.parent else o.name, 'group': code.split('_')[0],
                      'hinge': ROUND(pivot), 'angle': math.radians(angle)})
    return doors, origins


def mesh_data(o, mesh, origin, model, batch):
    mesh.calc_loop_triangles()
    if not mesh.loop_triangles:
        return None
    mat = np.array(o.matrix_world)
    linear = AXES @ mat[:3, :3]
    pos = read_array(mesh.vertices, 'co', 3, np.float32) @ linear.T + AXES @ mat[:3, 3]
    quantized = np.rint((pos-origin)/PITCH).astype(np.int32)
    if np.max(np.abs(quantized)) > 32767:
        raise ValueError('Geometry outside public footprint: '+o.name)
    normals = read_array(mesh.corner_normals, 'vector', 3, np.float32) @ np.linalg.pinv(linear)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), .000001)
    loops = read_array(mesh.loops, 'vertex_index', 1, np.int32)
    attrs = np.concatenate([quantized[loops], np.rint(normals*127).astype(np.int32)], axis=1)
    tris = read_array(mesh.loop_triangles, 'loops', 3, np.int32)
    if np.linalg.det(linear) < 0:
        tris = tris[:, ::-1]
    materials = read_array(mesh.loop_triangles, 'material_index', 1, np.int32)
    for slot in np.unique(materials):
        m = mesh.materials[slot] if slot < len(mesh.materials) else None
        mi, textured = model.material(m)
        index = tris[materials == slot].ravel()
        stream = attrs[index]
        if textured:
            if mesh.uv_layers.active:
                uv = read_array(mesh.uv_layers.active.data, 'uv', 2, np.float32)[index]
            else:
                verts = pos[loops[index]]
                uv = verts[:, (0, 2)] if np.ptp(verts[:, 1]) < .15 else verts[:, (0, 1)]
            uv = np.column_stack((uv[:, 0], 1 - uv[:, 1]))
            stream = np.column_stack((stream, np.rint(uv * 16384).astype(np.int32)))
        batch[mi].append(stream)
    return pos.min(axis=0), pos.max(axis=0)


def outline_and_walls():
    colliders = set()
    cams = [c for c in SCENE.objects if c.type == 'CAMERA' and c.get('sector')]
    for cam in cams:
        code = cam['sector']
        start = AXES @ cam['origin_xyz']
        axis = AXES @ cam['u_xyz']
        a = start[[0,2]]
        direction = axis[[0,2]]
        runs = cam.get('profile_runs', [cam['width_mm']])
        for i, length in enumerate(runs):
            b = a + direction * float(length) / 1000
            # Windows remain solid at pedestrian height, even where there is no sill.
            if i % 2 == 0 or code in ('A4','B4','E2','F2'):
                colliders.add(tuple(ROUND([*np.minimum(a,b)-.012, *np.maximum(a,b)+.012])))
            a = b
    slab = next(o for o in SCENE.collection.objects if o.name.startswith('Условная подложка'))
    floor = []
    for face in slab.data.polygons:
        if face.normal.z <= .9:
            continue
        points = [AXES @ (slab.matrix_world @ slab.data.vertices[i].co) for i in face.vertices]
        floor.append([ROUND(p[[0,2]]) for p in points])
    return colliders, floor


def build():
    objects, furniture = public_objects()
    doors, origins = hinges_for(objects)
    colliders, floor = outline_and_walls()
    model = BinaryModel()
    batches = collections.defaultdict(lambda: collections.defaultdict(list))
    limits = collections.defaultdict(list)
    furniture_limits = collections.defaultdict(list)
    for o in objects:
        if o.type == 'CURVE':
            o.data.bevel_resolution = min(2, o.data.bevel_resolution)
            o.data.resolution_u = min(6, o.data.resolution_u)
        for modifier in o.modifiers:
            if modifier.type == 'BEVEL':
                modifier.segments = min(2, modifier.segments)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    for o, group in objects.items():
        if o.type not in DRAWABLE or o.hide_render or o.get('web_exclude'):
            continue
        ev = o.evaluated_get(deps)
        mesh = ev.to_mesh()
        if not mesh:
            continue
        try:
            bounds = mesh_data(ev, mesh, origins[group], model, batches[group])
        finally:
            ev.to_mesh_clear()
        if bounds is None:
            continue
        limits[group].append(bounds)
        if o in furniture:
            lo, hi = bounds
            if lo[1] < .86 and hi[1] > .12:
                parent = o
                while parent.parent in furniture:
                    parent = parent.parent
                furniture_limits[parent].append(bounds)
    for root, blocks in furniture_limits.items():
        if root.name.endswith(' · пол') or 'раскладка Privilege' in root.name or 'единая мраморная столешница' in root.name:
            continue
        lo = np.min([p[0] for p in blocks], axis=0)
        hi = np.max([p[1] for p in blocks], axis=0)
        if min(hi[0]-lo[0], hi[2]-lo[2]) > .035:
            colliders.add(tuple(ROUND([lo[0], lo[2], hi[0], hi[2]])))
    for door in doors:
        pieces = limits[door['node']]
        lo = np.min([b[0] for b in pieces], axis=0)
        hi = np.max([b[1] for b in pieces], axis=0)
        door['closed'] = ROUND([lo[0],lo[2],hi[0],hi[2]])
    # Public inventory is measured in the orientation of each furniture assembly.
    inventory = []
    for assembly in furniture:
        if assembly.parent or assembly.type != 'EMPTY':
            continue
        room = objects[assembly].removeprefix('Room_')
        members = [o for o in assembly.children_recursive if o.type in DRAWABLE and not o.hide_render]
        if not members or assembly.name.endswith(' · пол'):
            continue
        rotation = assembly.matrix_world.to_quaternion().to_matrix().inverted()
        corners = [rotation @ (o.matrix_world @ Vector(corner)) for o in members for corner in o.bound_box]
        dimensions = np.ptp(np.array(corners), axis=0)
        materials = sorted({m.name for o in members for m in o.data.materials if m})
        inventory.append({'roomId': room, 'name': assembly.name,
                          **dict(zip(('width','depth','height'), np.rint(dimensions*1000).astype(int).tolist())),
                          'materials': materials})
    inventory.sort(key=lambda item: (item['roomId'], item['name']))
    write_json(OUT/'inventory.json', inventory)
    # Convert the actual aimed picture lamp into a spot (glTF has no area-light type).
    for light in objects:
        if light.type != 'LIGHT' or not (light.name.startswith('G2 ·') or light.get('web_light')):
            continue
        direction = AXES @ (light.matrix_world.to_quaternion() @ Vector((0,0,-1)))
        q = Vector(direction).to_track_quat('-Z','Y')
        entry = {'name': light.name, 'type': 'spot', 'intensity': round(light.data.energy*4,3),
                 'color': ROUND(light.data.color), 'range': 2.3,
                 'spot': {'innerConeAngle': .40, 'outerConeAngle': 1.14}}
        ext = model.doc.setdefault('extensions',{}).setdefault('KHR_lights_punctual',{'lights':[]})
        model.doc['extensionsUsed'].append('KHR_lights_punctual') if 'KHR_lights_punctual' not in model.doc['extensionsUsed'] else None
        idx=len(ext['lights'])
        ext['lights'].append(entry)
        model.doc['scenes'][0]['nodes'].append(len(model.doc['nodes']))
        model.doc['nodes'].append({'name': light.name, 'translation': ROUND(AXES @ light.matrix_world.translation),
                                   'rotation':[q.x,q.y,q.z,q.w],'extensions':{'KHR_lights_punctual':{'light':idx}}})
    model.finish(batches, origins)
    all_bounds = [b for group in limits.values() for b in group]
    overall = {'min': ROUND(np.min([b[0] for b in all_bounds], axis=0)),
               'max': ROUND(np.max([b[1] for b in all_bounds], axis=0))}
    write_json(OUT / 'release.json', {'bounds': overall, 'doors': doors, 'spawn': [6.47,1.64,6.45],
               'heading': 0, 'spawnYaw': 0, 'ceilingNodes': ['Ceiling'], 'colliders': sorted(colliders),
               'floorPolygons': floor})
    if SCENE.get('web_estimates'):
        estimates = json.loads(SCENE['web_estimates'])
        coverings = collections.Counter()
        for obj in objects:
            if obj.get('Покрытие') and 'Площадь, м²' in obj:
                mesh = obj.data
                matrix = obj.matrix_world
                # Area in plan; only upward-facing polygons form the finished surface.
                measured = 0.
                for polygon in mesh.polygons:
                    if polygon.normal.z <= .5:
                        continue
                    pts = [matrix @ mesh.vertices[i].co for i in polygon.vertices]
                    measured += abs(sum(p.x*q.y-q.x*p.y for p,q in zip(pts, pts[1:]+pts[:1])))/2
                coverings[obj['Покрытие']] += measured or float(obj['Площадь, м²'])
        packs = {'Ламинат · CBM Chevron 601': ('Ламинат · французская ёлочка', 3.992),
                 'Керамогранит · Alma Ceramica Carrara': ('Керамогранит под мрамор', 1.8)}
        for item in estimates['items']:
            entry = next((v for prefix,v in packs.items() if item['label'].startswith(prefix)), None)
            if not entry or entry[0] not in coverings:
                continue
            area = coverings[entry[0]]
            raw_order = area * (1 + item['wastePct']/100)
            order = math.ceil(raw_order/entry[1])*entry[1]
            item.update(areaM2=round(area,2), orderM2=round(order,3), orderIncrementM2=entry[1],
                        totalRub=round(order*item['priceRubM2']))
        write_json(OUT/'material-estimates.json', estimates)
    print(f'Built {len(model.doc["meshes"])} groups with {len(model.doc["materials"])} materials, {len(doors)} animated leaves')


if __name__ == '__main__':
    build()

