"""Run with Blender in background against the saved authoring file."""
import json
import sys
from pathlib import Path

import bpy

out = Path(sys.argv[sys.argv.index('--') + 1])
sys.path.insert(0, str(Path(bpy.data.filepath).parent))
import apartment_walls as aw

if not hasattr(bpy.types.Scene, 'apt_room'):
    aw.register()
scene = bpy.context.scene
rows = []
for code, camera in sorted(aw.cameras(scene).items(), key=lambda item: (item[0][0], int(item[0][1:]))):
    aw.sync_layers(scene, code)
    path = out / (code + '.png')
    aw.render_profile(scene, camera, path)
    row = aw.sheet_data(scene, camera, path)
    rows.append(row)
(out / 'sheets.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')

