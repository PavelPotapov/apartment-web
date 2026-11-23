"""Publish a consistent local snapshot from the saved Blender project. No network access."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

from PIL import Image
from pypdf import PdfReader
from estimate_pdf import write_estimate

TOOLS = Path(__file__).resolve().parent
WEB = TOOLS.parent
AREAS = dict(zip('ABCDEFG', [30.39, 20.11, 4.75, 3.47, 13.10, 15.10, 13.38]))


def json_file(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def run(args):
    subprocess.run([str(arg) for arg in args], check=True)


def install_snapshot(source, dest):
    """Install verified public files with the workspace's ordinary inherited read permissions."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent.parent / ('.release-' + uuid4().hex)
    staging.mkdir()
    incoming = staging / 'incoming'
    previous = staging / 'previous'
    try:
        # A secure temp directory must not become the public tree: moving it would carry
        # an owner-only Windows ACL into the site. Create fresh directories and files.
        incoming.mkdir()
        for original in source.rglob('*'):
            new = incoming / original.relative_to(source)
            if original.is_dir():
                new.mkdir(exist_ok=True)
            else:
                new.parent.mkdir(parents=True, exist_ok=True)
                with original.open('rb') as reader, new.open('wb') as writer:
                    shutil.copyfileobj(reader, writer)
        if dest.exists():
            dest.rename(previous)
        try:
            incoming.rename(dest)
        except OSError:
            if previous.exists():
                previous.rename(dest)
            raise
    finally:
        # If rollback itself failed, keep the previous release available for recovery.
        if dest.exists() or not previous.exists():
            shutil.rmtree(staging)


def release(blender, scene, version):
    scene = scene.resolve(strict=True)
    # Both Blender processes read the exact same snapshot, even if authoring continues.
    with tempfile.TemporaryDirectory(prefix='apartment-release-') as temp:
        work = Path(temp)
        for name in [scene.name, 'apartment_profile_pdf.py', 'apartment_walls.py']:
            shutil.copy2(scene if name == scene.name else TOOLS / name, work / name)
        source = work / scene.name
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        target = work / 'release'
        preview = target / 'profiles'
        preview.mkdir(parents=True)
        command = [blender, '-b', source, '--python-exit-code', '2', '-P']
        with ThreadPoolExecutor(max_workers=2) as pool:
            model = pool.submit(run, command + [TOOLS / 'model.py', '--', target])
            run(command + [TOOLS / 'profiles.py', '--', work])
            rows = json.loads((work / 'sheets.json').read_text(encoding='utf-8'))
            run([sys.executable, work / 'apartment_profile_pdf.py', work / 'sheets.json', target / 'apartment.pdf'])
            model.result()
        rooms = {}
        walls = []
        for page, row in enumerate(rows, 1):
            code = row['code']
            image = f'profiles/{code}.webp'
            with Image.open(row['image']) as sheet:
                sheet.thumbnail((1500, 1350))
                sheet.convert('RGB').save(target / image, quality=90, method=4)
            rid = code[0]
            rooms[rid] = {'id': rid, 'name': row['room'], 'area': AREAS.get(rid)}
            walls.append({**row, 'height': row['ceiling'], 'roomId': rid, 'image': image, 'page': page,
                          'sockets': [dict(zip(('number','u','height','status'), point)) for point in row['sockets']]})
        pdf = PdfReader(target / 'apartment.pdf')
        if len(pdf.pages) != len(walls) or not all(w['code'] in p.extract_text() for p, w in zip(pdf.pages, walls)):
            raise RuntimeError('PDF page count or wall order does not match the index')
        inventory = json.loads((target / 'inventory.json').read_text(encoding='utf-8'))
        (target / 'inventory.json').unlink()
        json_file(target / 'technical.json', {'units': 'mm', 'rooms': list(rooms.values()), 'walls': walls, 'inventory': inventory})
        nav = json.loads((target / 'release.json').read_text(encoding='utf-8'))
        version = version or f'{date.today()}.{digest[:8]}'
        if (target / 'material-estimates.json').exists():
            write_estimate(target / 'material-estimates.json', target / 'material-estimates.pdf', version)
        json_file(target / 'release.json', {**nav, 'schema': 1, 'version': version,
                  'date': date.today().isoformat(), 'sourceDigest': digest, 'model': 'apartment.glb',
                  'technical': 'technical.json', 'pdf': 'apartment.pdf'})
        dest = WEB / 'public' / 'data'
        install_snapshot(target, dest)
        print(f'Release {dest}: {len(walls)} sheets, {len(nav["doors"])} door leaves. Model {(dest/"apartment.glb").stat().st_size/1e6:.1f} MB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blend', type=Path, default=WEB.parent / 'Apartment_Wall_Profiles.blend')
    parser.add_argument('--blender', default=shutil.which('blender') or 'blender')
    parser.add_argument('--version', help='Public release identifier')
    options = parser.parse_args()
    release(options.blender, options.blend, options.version)

