bl_info = {"name": "Квартира · развёртки стен", "author": "Apartment project",
           "version": (1, 5, 1), "blender": (5, 0, 0), "category": "3D View"}

import base64
import html
import tempfile
import json
import subprocess
import textwrap
from pathlib import Path
import bpy
from mathutils import Vector
from bpy_extras import view3d_utils

ROOMS = [('A', 'A · Гостиная-кухня', ''), ('B', 'B · Спальня', ''),
         ('C', 'C · Ванная', ''), ('D', 'D · Туалет', ''),
         ('E', 'E · Спальня-кабинет', ''), ('F', 'F · Детская', ''), ('G', 'G · Прихожая', '')]

OFFICE_ROOMS = [(key, 'B · Рабочий кабинет' if key == 'B' else label, hint)
                for key, label, hint in ROOMS]
OWNER_LABELS = {'C': 'Душевая', 'D': 'Ванная при спальне', 'E': 'Спальня', 'F': 'Кабинет у окна'}
OWNER_ROOMS = [(key, key + ' · ' + OWNER_LABELS[key] if key in OWNER_LABELS else label, hint)
               for key, label, hint in OFFICE_ROOMS]


def room_choices(scene, context):
    if scene.get('owner_wet_rooms'):
        return OWNER_ROOMS
    return OFFICE_ROOMS if scene.get('room_B_use') == 'office' else ROOMS


def cameras(scene):
    return {obj["sector"]: obj for obj in scene.objects if obj.type == 'CAMERA' and "sector" in obj}


def layers(scene):
    return sorted((c for c in scene.collection.children if "apt_layer_order" in c),
                  key=lambda c: c["apt_layer_order"])


def grid_layer(scene):
    return next((c for c in layers(scene) if c.get("apt_grid") or c.get("apt_title") == "Сетка 500 мм"), None)


def floor_outline(scene):
    slab = next((ob for ob in scene.objects if ob.type == 'MESH' and ob.name.startswith("Условная подложка")), None)
    if slab is None:
        return []
    # Edges shared by adjacent top faces are interior edges, not footprint boundaries.
    edges = set()
    for face in slab.data.polygons:
        if face.normal.z > .99:
            edges.symmetric_difference_update(face.edge_keys)
    points = [slab.matrix_world @ v.co for v in slab.data.vertices]
    return [tuple(tuple(round(points[i][k]*1000) for k in (0,1)) for i in edge) for edge in edges]


def plan_subdivisions(outline, step):
    for axis in (0, 1):
        coords = [p[axis] for edge in outline for p in edge]
        if not coords:
            continue
        for v in range((min(coords)//step+1)*step, max(coords), step):
            if v % 500 == 0:
                continue
            hits = sorted(a[1-axis] for a,b in outline if min(a[axis],b[axis]) <= v < max(a[axis],b[axis]))
            for lo,hi in zip(hits[::2], hits[1::2]):
                if lo < hi:
                    yield tuple(((v/1000,h/1000,.025) if axis == 0 else (h/1000,v/1000,.025)) for h in (lo,hi))


def wall_subdivisions(cam, step):
    origin = Vector(cam["origin_xyz"]) + Vector(cam["inward_xyz"])*.021
    right = Vector(cam["u_xyz"])
    up = Vector((0,0,1))
    width = cam["width_mm"]
    height = cam.get("ceiling_mm", 2710)
    for u in range(step, width, step):
        if u % 500:
            p = origin + right*(u/1000)
            yield p, p + up*(height/1000)
    for h in range(step, height, step):
        if h % 500:
            p = origin + up*(h/1000)
            yield p, p + right*(width/1000)


def update_grid(scene, context):
    layer = grid_layer(scene)
    if layer is None:
        return
    step = int(scene.apt_grid_mm)
    cams = cameras(scene)
    outline = floor_outline(scene)
    material = bpy.data.materials.get("Сетка · малые деления")
    if material is None:
        material = bpy.data.materials.new("Сетка · малые деления")
        material.diffuse_color = (.60,.70,.72,1)
    for group in layer.children:
        key = group.get("apt_view")
        if key != "PLAN" and key not in cams:
            continue
        obj = next((o for o in group.objects if o.get("apt_minor_grid")), None)
        if obj is None:
            if step == 500:
                continue
            curve = bpy.data.curves.new("Малые деления "+key, 'CURVE')
            curve.dimensions = '3D'
            curve.bevel_depth = .00115
            curve.bevel_resolution = 0
            curve.materials.append(material)
            obj = bpy.data.objects.new(curve.name, curve)
            obj["apt_minor_grid"] = True
            obj.hide_select = True
            group.objects.link(obj)
        obj.hide_render = obj.hide_viewport = step == 500
        if step == 500 or obj.get("apt_step") == step:
            continue
        obj.data.splines.clear()
        segments = plan_subdivisions(outline, step) if key == "PLAN" else wall_subdivisions(cams[key], step)
        for start,end in segments:
            spline = obj.data.splines.new('POLY')
            spline.points.add(1)
            spline.points[0].co = (*start,1)
            spline.points[1].co = (*end,1)
        obj["apt_step"] = step
    layer["apt_grid"] = True
    layer["apt_title"] = "Размерная сетка"


def grid_control(layout, scene):
    layer = grid_layer(scene)
    if layer is not None:
        row = layout.row(align=True)
        row.prop(layer, "apt_visible", text="Сетка")
        choice = row.row(align=True)
        choice.enabled = layer.apt_visible
        choice.prop(scene, "apt_grid_mm", text="")


def socket_legend(layout, context):
    box = layout.box()
    box.label(text="Цвет розетки")
    for name, words, fallback in (("ЭП · проектные размеры", "Зелёный · размер по ЭП", (.05,.33,.32,1)),
                                 ("ЭП · уточнить", "Оранжевый · уточнить", (.68,.26,.07,1))):
        row = box.row(align=True)
        material = bpy.data.materials.get(name)
        row.template_node_socket(color=tuple(material.diffuse_color) if material else fallback)
        row.label(text=words)
    ob = context.active_object
    if ob and ob.get("ЭП · номер"):
        box.label(text=f'№ {ob["ЭП · номер"]} · {ob.get("sector", "")} · {ob.get("Статус", "")}')
        box.label(text=ob.get("Привязка", ""))
        for text in textwrap.wrap(ob.get("Источник и уточнения", ""), width=32):
            box.label(text=text)


def sync_layers(scene, view):
    project_layers = layers(scene)
    if not project_layers:
        return
    scene["apt_layer_view"] = view
    for layer in project_layers:
        visible = layer.get("apt_on", True)
        plan_only = layer.get("apt_plan_only", False)
        layer.hide_viewport = not visible or (plan_only and view != "PLAN" and not scene.get("apt_dual"))
        layer.hide_render = not visible or plan_only
        for group in layer.children:
            if "apt_view" in group:
                group.hide_viewport = group["apt_view"] != view
                group.hide_render = group["apt_view"] != view or view == "PLAN"


def set_layer_visible(collection, value):
    collection["apt_on"] = bool(value)
    scene = bpy.context.scene
    if scene and collection in list(scene.collection.children):
        view = scene.get("apt_layer_view", "PLAN")
        if collection.get("apt_title") == "Исходный электроплан" and bpy.context.window:
            view = reference_plan_view(bpy.context, value, view)
        sync_layers(scene, view)


def view_areas(context):
    return sorted((a for a in context.screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.x)


def set_plan(space):
    from mathutils import Quaternion
    space.use_local_camera = False
    view = space.region_3d
    view.view_perspective = 'ORTHO'
    view.view_rotation = Quaternion((1, 0, 0, 0))
    view.view_location = (5.7, -4.35, 1.0)
    view.view_distance = 21


def reference_plan_view(context, enabled, layer_view):
    areas = view_areas(context)
    if not areas:
        return layer_view
    area = areas[0]
    space = area.spaces.active
    view, shading = space.region_3d, space.shading
    dual = context.scene.get("apt_dual") and len(areas) >= 2
    screen = context.screen
    key = "apt_before_electrical_reference"
    if enabled:
        if key not in screen:
            screen[key] = dict(mode=shading.type, color=shading.color_type, light=shading.light,
                               xray=shading.show_xray, local_camera=space.use_local_camera,
                               projection=view.view_perspective, rotation=list(view.view_rotation),
                               center=list(view.view_location), distance=view.view_distance,
                               layer_view=layer_view, scene=context.scene.name)
        # Keep the current framing when the user is already looking straight down.
        if view.view_perspective != 'ORTHO' or abs(view.view_rotation.w) < .999999:
            set_plan(space)
        shading.type = 'SOLID'
        shading.color_type = 'TEXTURE'
        shading.light = 'FLAT'
        shading.show_xray = False
        if not dual:
            layer_view = "PLAN"
    elif key in screen:
        saved = screen[key]
        if saved["scene"] == context.scene.name:
            shading.light = saved["light"]
            shading.color_type = saved["color"]
            shading.show_xray = bool(saved["xray"])
            shading.type = saved["mode"]
            if dual or layer_view == "PLAN":
                space.use_local_camera = bool(saved["local_camera"])
                view.view_rotation = saved["rotation"]
                view.view_location = saved["center"]
                view.view_distance = saved["distance"]
                view.view_perspective = saved["projection"]
                if not dual:
                    layer_view = saved["layer_view"]
        del screen[key]
    area.tag_redraw()
    return layer_view


def apply_depth(cam):
    if not cam or "profile_clear_mm" not in cam:
        return
    depth = min(cam.apt_depth_mm, cam["profile_clear_mm"]) / 1000
    cam.data.clip_start = max(.001, 10 - depth)
    cam.data.clip_end = 10 + cam.get("profile_behind_mm", 25) / 1000


def show_sector(context, cam):
    scene = context.scene
    scene.camera = cam
    scene.apt_room = cam["sector"][0]
    scene.render.resolution_x = cam["pixels_w"]
    scene.render.resolution_y = cam["pixels_h"]
    scene.render.resolution_percentage = 100
    areas = view_areas(context)
    dual = scene.get("apt_dual") and len(areas) >= 2
    space = areas[-1].spaces.active if dual else context.space_data
    space.use_local_camera = bool(dual)
    space.camera = cam
    apply_depth(cam)
    space.region_3d.view_camera_offset = (0, 0)
    space.region_3d.view_camera_zoom = 4
    space.region_3d.view_perspective = 'CAMERA'
    sync_layers(scene, cam["sector"])
    for area in areas:
        area.tag_redraw()


class APT_OT_open(bpy.types.Operator):
    bl_idname = "apt.open_sector"
    bl_label = "Развёртка стены"
    sector: bpy.props.StringProperty()

    def execute(self, context):
        cam = cameras(context.scene).get(self.sector)
        if not cam:
            return {'CANCELLED'}
        show_sector(context, cam)
        return {'FINISHED'}


class APT_OT_pick(bpy.types.Operator):
    bl_idname = "apt.pick_face"
    bl_label = "Указать стену в модели"

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Щёлкните внутреннюю грань стены или её метку. Esc — выход.")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            context.workspace.status_text_set(None)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        target = next(((a, r) for a in view_areas(context) for r in a.regions
                       if r.type == 'WINDOW' and r.x <= event.mouse_x < r.x+r.width
                       and r.y <= event.mouse_y < r.y+r.height), None)
        if target is None:
            return {'RUNNING_MODAL'}
        area, region = target
        point = (event.mouse_x-region.x, event.mouse_y-region.y)
        rv = area.spaces.active.region_3d
        origin = view3d_utils.region_2d_to_origin_3d(region, rv, point)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv, point)
        hit, pos, normal, _, obj, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
        cams = cameras(context.scene)
        cam = cams.get(obj.get("sector", "")) if hit else None
        if hit and not cam and obj.get("wall_shell"):
            for candidate in cams.values():
                p = Vector(candidate["origin_xyz"])
                delta = pos-p
                tangent = Vector(candidate["u_xyz"])
                inward = Vector(candidate["inward_xyz"])
                if normal.dot(inward) > .99 and abs(delta.dot(inward)) < .002 and -.001 <= delta.dot(tangent) <= candidate["width_mm"]/1000+.001:
                    cam = candidate
                    break
        if cam:
            context.workspace.status_text_set(None)
            show_sector(context, cam)
            return {'FINISHED'}
        self.report({'INFO'}, "Выберите вертикальную грань из комнаты или нажмите код стены в панели")
        return {'RUNNING_MODAL'}


class APT_OT_plan(bpy.types.Operator):
    bl_idname = "apt.plan"
    bl_label = "План с адресами"

    def execute(self, context):
        areas = view_areas(context)
        if context.scene.get("apt_dual") and len(areas) >= 2:
            set_plan(areas[0].spaces.active)
        else:
            set_plan(context.space_data)
            sync_layers(context.scene, "PLAN")
        return {'FINISHED'}


class APT_OT_profiles(bpy.types.Operator):
    bl_idname = "apt.profiles"
    bl_label = "План слева · профиль справа"

    def execute(self, context):
        areas = view_areas(context)
        if len(areas) == 1:
            with context.temp_override(area=areas[0]):
                bpy.ops.screen.area_split(direction='VERTICAL', factor=.45)
        scene, window = context.scene, context.window
        def finish():
            with bpy.context.temp_override(window=window):
                areas = view_areas(bpy.context)
                if len(areas) < 2:
                    return None
                scene["apt_dual"] = True
                left, right = areas[0], areas[-1]
                set_plan(left.spaces.active)
                left.spaces.active.show_region_ui = False
                right.spaces.active.show_region_ui = True
                cam = scene.camera if scene.camera and scene.camera.get("sector") else cameras(scene)["B1"]
                with bpy.context.temp_override(area=right):
                    show_sector(bpy.context, cam)
                sidebar = next(r for r in right.regions if r.type == 'UI')
                try:
                    sidebar.active_panel_category = "Стены"
                except (RuntimeError, AttributeError):
                    pass
            return None
        bpy.app.timers.register(finish, first_interval=.15)
        return {'FINISHED'}


class APT_OT_cursor(bpy.types.Operator):
    bl_idname = "apt.wall_cursor"
    bl_label = "Поставить 3D-курсор"
    def execute(self, context):
        s = context.scene
        cam = s.camera
        if not cam or not cam.get("sector"):
            return {'CANCELLED'}
        if not 0 <= s.apt_u <= cam["width_mm"]:
            self.report({'ERROR'}, "U выходит за пределы выбранной плоскости")
            return {'CANCELLED'}
        s.cursor.location = Vector(cam["origin_xyz"]) + Vector(cam["u_xyz"])*s.apt_u/1000 + Vector((0,0,s.apt_h/1000))
        self.report({'INFO'}, f'{cam["sector"]} · U {s.apt_u:g} · H {s.apt_h:g} мм')
        return {'FINISHED'}


def print_sheet(scene, cam, destination):
    # Use a scene copy so printing cannot alter the working render settings.
    sheet = scene.copy()
    try:
        sheet.camera = cam
        sheet.render.engine = 'BLENDER_WORKBENCH'
        sheet.render.resolution_x, sheet.render.resolution_y = cam["pixels_w"], cam["pixels_h"]
        sheet.render.resolution_percentage = 100
        sheet.render.image_settings.file_format = 'PNG'
        sheet.display.shading.color_type = 'MATERIAL'
        sheet.display.shading.show_shadows = False
        with tempfile.TemporaryDirectory() as tmp:
            bitmap = Path(tmp)/"wall.png"
            sheet.render.filepath = str(bitmap)
            bpy.ops.render.render(write_still=True, scene=sheet.name)
            data = base64.b64encode(bitmap.read_bytes()).decode("ascii")
    finally:
        bpy.data.scenes.remove(sheet)
    width = cam.data.ortho_scale * 1000
    height = width * cam["pixels_h"]/cam["pixels_w"]
    # The view rectangle has 60 mm bleed on each side in model space.
    sector = html.escape(cam["sector"])
    iw, ih = width/25, height/25
    ox, oy = (396-iw)/2, 15
    x0 = ox+(width-cam["width_mm"])/50
    ceiling = cam.get("ceiling_mm", 2710)
    y0 = oy+(height+ceiling)/50
    lines = []
    for dim, extent in [('U',cam["width_mm"]), ('H',ceiling)]:
        for value in sorted(set(range(0,extent,500)) | {extent}):
            if dim == 'U':
                x,y = x0+value/25,y0+5
                lines.append(f'<path d="M{x},{y-3} v3"/>')
                if value == extent or extent-value >= 240:
                    lines.append(f'<text x="{x}" y="{y+4}" text-anchor="middle">{value}</text>')
            else:
                x,y = x0-5,y0-value/25
                lines.append(f'<path d="M{x},{y} h3"/>')
                if value == extent or extent-value >= 160:
                    lines.append(f'<text x="{x-1}" y="{y+1}" text-anchor="end">{value}</text>')
    title = html.escape(cam["room_name"])
    content = f"""<!doctype html><html lang="ru"><meta charset="utf-8"><title>{sector} · {title}</title>
<style>@page{{size:A3 landscape;margin:12mm}}*{{box-sizing:border-box}}body{{font:4mm Arial;color:#173037;margin:0}}
h1{{font-size:9mm;margin:2mm 0}}p{{margin:2mm 0}}svg{{display:block;width:396mm;height:180mm}}text{{font:3mm Arial;fill:#19383e;stroke:none}}path{{stroke:#19383e;stroke-width:.35;fill:none}}</style>
<h1>{sector} · {title}</h1><p>Развёртка из комнаты · 1:25 · U вправо, H вверх · размеры в миллиметрах</p>
<svg viewBox="0 0 396 180"><image x="{ox}" y="{oy}" width="{iw}" height="{ih}" href="data:image/png;base64,{data}"/>{''.join(lines)}</svg>
<p>Ширина плоскости {cam["width_mm"]} мм. Высота профиля {ceiling} мм. {html.escape(cam.get("opening_note", ""))}</p>
<p>Проверка печати при 100% · отрезок 50 мм</p><div style="width:50mm;border-top:.5mm solid"></div></html>"""
    destination.write_text(content, encoding='utf-8')


def render_profile(scene, cam, dest):
    sheet = scene.copy()
    paper_world = bpy.data.worlds.new("Профиль · фон листа")
    try:
        sheet.camera = cam
        sheet.render.engine = 'BLENDER_WORKBENCH'
        sheet.render.resolution_x, sheet.render.resolution_y = cam["pixels_w"], cam["pixels_h"]
        sheet.render.resolution_percentage = 100
        sheet.render.image_settings.file_format = 'PNG'
        sheet.render.film_transparent = False
        paper_world.color = (1, 1, 1)
        sheet.world = paper_world
        sheet.view_settings.view_transform = 'Standard'
        sheet.display.shading.light = 'FLAT'
        sheet.display.shading.show_shadows = False
        sheet.display.shading.show_cavity = False
        sheet.display.shading.show_object_outline = True
        sheet.display.shading.object_outline_color = (.35,.39,.40)
        sheet.display.shading.color_type = 'MATERIAL'
        sheet.display.shading.background_type = 'WORLD'
        sheet.render.filepath = str(dest)
        bpy.ops.render.render(write_still=True, scene=sheet.name)
    finally:
        bpy.data.scenes.remove(sheet)
        bpy.data.worlds.remove(paper_world)


def sheet_data(scene, cam, image_path):
    sockets = {}
    for ob in scene.objects:
        number = ob.get("ЭП · номер")
        if number and not ob.get("archive_opening") and ob.get("sector") == cam["sector"] and ob.type == 'MESH' and not ob.parent:
            sockets[number] = [number, ob.get("U, мм"), ob.get("H, мм / база", ""), ob.get("Статус","")]
    return dict(code=cam["sector"], room=cam["room_name"], width=cam["width_mm"],
                ceiling=cam.get("ceiling_mm", 2710),
                opening_note=cam.get("opening_note", ""),
                socket_source=cam.get("socket_source", "Розетки по ЭП"),
                runs=list(cam.get("profile_runs", [cam["width_mm"]])), sockets=sorted(sockets.values()),
                grid=bool(grid_layer(scene) and grid_layer(scene).apt_visible), grid_mm=int(scene.apt_grid_mm),
                skirting=any(l.get("apt_plinth") and l.apt_visible for l in layers(scene)),
                floor_trim_mm=scene.get("Высота напольного плинтуса, мм", 80),
                membrane_mm=scene.get("Натяжной потолок, мм"),
                cornice_bottom_mm=scene.get("Низ потолочного карниза, мм"),
                depth=round(min(cam.apt_depth_mm, cam.get("profile_clear_mm",1200))), image=str(image_path))


class APT_OT_profile_file(bpy.types.Operator):
    bl_idname = "apt.profile_file"
    bl_label = "Сохранить профиль"
    kind: bpy.props.EnumProperty(items=[('PNG','PNG',''),('PDF','PDF','')])
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    check_existing: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context, event):
        self.filepath = str(Path(bpy.data.filepath).parent / (context.scene.camera["sector"]+'.'+self.kind.lower()))
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene, cam = context.scene, context.scene.camera
        dest = Path(bpy.path.ensure_ext(self.filepath, '.'+self.kind.lower()))
        try:
            if self.kind == 'PNG':
                render_profile(scene, cam, dest)
            else:
                from apartment_profile_pdf import bundled_python
                import apartment_profile_pdf as printer
                with tempfile.TemporaryDirectory() as folder:
                    image_path = Path(folder)/'view.png'
                    spec = Path(folder)/'sheet.json'
                    render_profile(scene, cam, image_path)
                    spec.write_text(json.dumps([sheet_data(scene,cam,image_path)],ensure_ascii=False), encoding='utf-8')
                    subprocess.run([str(bundled_python()), printer.__file__, str(spec), str(dest)],
                                   check=True, capture_output=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, str(dest))
        return {'FINISHED'}


class APT_OT_print(bpy.types.Operator):
    bl_idname = "apt.print_wall"
    bl_label = "Лист для печати…"
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.html", options={'HIDDEN'})
    def invoke(self, context, event):
        self.filepath = str(Path(bpy.data.filepath).parent/(context.scene.camera["sector"]+".html"))
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    def execute(self, context):
        print_sheet(context.scene, context.scene.camera, Path(bpy.path.ensure_ext(self.filepath,'.html')))
        self.report({'INFO'}, "Лист сохранён. Откройте его в браузере для печати A3 / PDF в масштабе 100%.")
        return {'FINISHED'}


class APT_PT_layers(bpy.types.Panel):
    bl_idname = "APT_PT_layers"
    bl_label = "Слои квартиры"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    def draw(self, context):
        grid_control(self.layout, context.scene)
        for layer in layers(context.scene):
            if layer != grid_layer(context.scene):
                self.layout.prop(layer, "apt_visible", text=layer.get("apt_title", layer.name), toggle=False)
        socket_legend(self.layout, context)


def draw_layers_menu(self, context):
    if context.scene.get("wall_atlas"):
        self.layout.popover(panel="APT_PT_layers", text="Слои", icon='RENDERLAYERS')


class APT_PT_walls(bpy.types.Panel):
    bl_idname = "APT_PT_walls"
    bl_label = "Стены и развёртки"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Стены"
    @classmethod
    def poll(cls, context):
        return bool(context.scene.get("wall_atlas"))
    def draw(self, context):
        s = context.scene
        layout = self.layout
        cam = s.camera
        if s.get("profile_book"):
            grid_control(layout, s)
            furniture = next((layer for layer in layers(s) if layer.get("apt_furniture")), None)
            if furniture is not None:
                layout.prop(furniture, "apt_visible", text="Мебель", toggle=False)
            layout.popover(panel="APT_PT_layers",text="Все слои",icon='RENDERLAYERS')
            layout.operator("apt.profiles", icon='SPLIT_VERTICAL')
            layout.prop(s, "apt_room", text="")
            if s.apt_room == 'B' and s.get('room_B_use') == 'office':
                desk = s.objects.get("B3 · подъёмный стол")
                if desk and "Подъём, м" in desk:
                    layout.prop(desk, '["Подъём, м"]', text="Подъём стола, м", slider=True)
            cells = layout.grid_flow(columns=3, even_columns=True, align=True)
            for c in sorted((c for c in cameras(s).values() if c["sector"][0]==s.apt_room), key=lambda c:int(c["sector"][1:])):
                cells.operator("apt.open_sector", text=c["sector"], depress=c==cam).sector=c["sector"]
            layout.operator("apt.pick_face",text="Выбрать грань или метку на плане")
            if cam and cam.get("sector"):
                box = layout.box()
                box.label(text=f'Профиль {cam["sector"]} · {cam["width_mm"]} мм')
                box.prop(cam,"apt_depth_mm",text="Захват, мм")
                box.label(text=f'До границы комнаты: {cam["profile_clear_mm"]} мм')
                row = box.row(align=True)
                for kind in ('PNG','PDF'):
                    row.operator("apt.profile_file",text=kind).kind=kind
                socket_legend(layout, context)
                box.prop(s,"apt_profile_details",text="Слои и координаты",toggle=True)
                if not s.apt_profile_details:
                    return
        if layers(s):
            box = layout.box()
            box.label(text="Слои проекта")
            for layer in layers(s):
                box.prop(layer, "apt_visible", text=layer.get("apt_title", layer.name))
            ob = context.active_object
            if ob and ob.get("ЭП · номер"):
                box.label(text=f'Точка {ob["ЭП · номер"]} · {ob.get("sector", "")}')
                box.label(text="По ЭП: " + ob.get("Привязка", ""))
                box.label(text=ob.get("Статус", ""))
        if s.get("profile_book"):
            layout.prop(s,"apt_u")
            layout.prop(s,"apt_h")
            layout.operator("apt.wall_cursor")
            return
        layout.operator("apt.plan", icon='VIEW_ORTHO')
        layout.operator("apt.pick_face", icon='EYEDROPPER')
        layout.prop(s, "apt_room", text="")
        cams = sorted((c for c in cameras(s).values() if c["sector"][0]==s.apt_room),key=lambda c:int(c["sector"][1:]))
        for cam in cams:
            layout.operator("apt.open_sector", text=f'{cam["sector"]}    {cam["width_mm"]} мм').sector = cam["sector"]
        if context.space_data.region_3d.view_perspective == 'CAMERA' and s.camera and s.camera.get("sector"):
            box=layout.box()
            box.label(text="Развёртка "+s.camera["sector"])
            box.prop(s,"apt_u")
            box.prop(s,"apt_h")
            box.operator("apt.wall_cursor")
            box.operator("apt.print_wall",icon='OUTPUT')


classes = (APT_OT_open, APT_OT_pick, APT_OT_plan, APT_OT_cursor, APT_OT_print, APT_OT_profiles, APT_OT_profile_file, APT_PT_layers, APT_PT_walls)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.apt_room = bpy.props.EnumProperty(items=room_choices)
    bpy.types.Scene.apt_u = bpy.props.FloatProperty(name="U, мм",min=0)
    bpy.types.Scene.apt_h = bpy.props.FloatProperty(name="H, мм",min=0)
    bpy.types.Scene.apt_profile_details = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.apt_grid_mm = bpy.props.EnumProperty(
        name="Шаг сетки", description="Расстояние между линиями. Основные линии идут через 500 мм",
        items=[(str(mm),f"{mm} мм","") for mm in (500,250,100,50)], default='500', update=update_grid)
    bpy.types.Object.apt_depth_mm = bpy.props.IntProperty(name="Глубина профиля", min=50, max=9000, default=2500, update=lambda obj, ctx: apply_depth(obj))
    bpy.types.Collection.apt_visible = bpy.props.BoolProperty(
        name="Видимость слоя", get=lambda c: bool(c.get("apt_on", True)), set=set_layer_visible)
    bpy.types.VIEW3D_HT_header.prepend(draw_layers_menu)
def unregister():
    del bpy.types.Scene.apt_grid_mm
    bpy.types.VIEW3D_HT_header.remove(draw_layers_menu)
    del bpy.types.Object.apt_depth_mm
    del bpy.types.Scene.apt_profile_details
    del bpy.types.Collection.apt_visible
    for key in ("apt_room","apt_u","apt_h"):
        delattr(bpy.types.Scene,key)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

