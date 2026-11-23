"""Render registered, furniture-on/off elevation pairs from the saved Blender file."""
import json
import sys
from pathlib import Path

import bpy

out = Path(sys.argv[sys.argv.index('--') + 1])
sys.path.insert(0, str(Path(__file__).resolve().parent))
import apartment_walls as aw
from technical_plan import extract

if not hasattr(bpy.types.Scene, 'apt_room'):
    aw.register()
scene = bpy.context.scene
cameras = sorted(aw.cameras(scene).items(), key=lambda row: (row[0][0], int(row[0][1:])))
axes, plan = extract(scene, cameras)
(out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
# Capture the source's own dimensions, grid settings and notes before hiding guides.
rows=[]
for code,cam in cameras:
    aw.sync_layers(scene,code)
    row=aw.sheet_data(scene,cam,out/(code+'-furnished.png'))
    row.update(axes[code])
    rows.append(row)
(out/'sheets.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')

labels=('Проёмы','Размер','ЭП ·','Электрика ·','Сетка','Адреса на плане','Стенды ·','Развёртки ·')
decor=('Потолочный свет','Зеркало ·','Текстиль ·','Оснащение ·')
furniture=next(c for c in scene.collection.children if c.get('apt_furniture'))
for col in scene.collection.children:
    if col.name.startswith(labels) or col.get('apt_plan_only') or col.get('apt_grid'):
        col.hide_render=True

movables=[]
for group in furniture.children:
    for item in group.objects:
        if item.parent:continue
        # Keep fixed floor finishes, sanitary wall linings and the structural false wall.
        if item.name.endswith(' · пол') or any(k in item.name for k in ('раскладка Privilege','фальшстена ГКЛ','мраморный простенок','дубовый паркет','светлый паркет')):
            continue
        movables.extend([item,*item.children_recursive])

sheet = scene.copy()
sheet.render.engine='BLENDER_WORKBENCH'
paper=bpy.data.worlds.new('Фон для интерактивной развёртки')
paper.color=(1,1,1)
sheet.world=paper
sheet.render.film_transparent=False
sheet.view_settings.view_transform='Standard'
sheet.render.image_settings.file_format='PNG'
sheet.render.resolution_percentage=100
shading=sheet.display.shading
shading.color_type='MATERIAL'
shading.background_type='WORLD'
shading.light='STUDIO'
shading.show_shadows=False
shading.show_cavity=True
shading.cavity_type='SCREEN'
shading.curvature_ridge_factor=.65
shading.curvature_valley_factor=.72
shading.show_object_outline=True
shading.object_outline_color=(.40,.42,.42)
for variant in ('furnished','empty'):
    if variant=='empty':
        for item in movables:item.hide_render=True
        for col in scene.collection.children:
            if col.name.startswith(decor):col.hide_render=True
    for code,cam in cameras:
        width=cam['width_mm']
        height=cam.get('ceiling_mm',2700)
        scale=min(.55,2200/max(width,height))
        w=max(1,round(width*scale));h=max(1,round(height*scale))
        sheet.render.resolution_x=w
        sheet.render.resolution_y=h
        # Blender's pixel-aspect controls ensure even 263-mm-wide returns project
        # exactly [0,width] x [0,height] after the bitmap is scaled to its SVG extent.
        aspect=width*h/(height*w)
        sheet.render.pixel_aspect_x=max(1.,aspect)
        sheet.render.pixel_aspect_y=max(1.,1./aspect)
        cam.data.sensor_fit='HORIZONTAL'
        cam.data.ortho_scale=width/1000
        sheet.camera=cam
        frame=cam.data.view_frame(scene=sheet)
        assert abs((frame[0].x-frame[2].x)*1000-width)<.035
        assert abs((frame[0].y-frame[1].y)*1000-height)<.035
        sheet.render.filepath=str(out/(code+'-'+variant+'.png'))
        bpy.ops.render.render(write_still=True,scene=sheet.name)

