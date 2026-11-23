"""Print current Blender wall elevations, one measured A3 sheet per camera."""
import json
import os
import sys
from pathlib import Path


def bundled_python():
    setting = Path(__file__).with_name("apartment_profile_python.txt")
    if setting.is_file():
        runtime = Path(setting.read_text(encoding="utf-8-sig").strip())
        if runtime.is_file():
            return runtime
    packages = Path(os.environ["ProgramFiles"])/"WindowsApps"
    candidates = list(packages.glob("OpenAI.CodexPrimaryRuntime*/dependencies/python/python.exe"))
    if not candidates:
        raise FileNotFoundError("Не найдена среда печати PDF приложения Codex")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def write_pdf(sheets, destination):
    from io import BytesIO
    from PIL import Image
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    for face, file in [('body','arial.ttf'),('heavy','arialbd.ttf')]:
        pdfmetrics.registerFont(TTFont(face, str(Path(os.environ['WINDIR'])/'Fonts'/file)))
    c=Canvas(str(destination), pagesize=(420*mm,297*mm),pageCompression=1)
    c.setTitle("Квартира · профили стен")
    ink, teal, gray = '#21383E','#006B68','#53666B'
    def text(x,y,value,size=11,color=ink,bold=False,align='left',angle=0):
        c.saveState();c.translate(x*mm,(297-y)*mm);c.rotate(angle)
        c.setFillColor(HexColor(color));c.setFont('heavy' if bold else 'body',size)
        {'left':c.drawString,'mid':c.drawCentredString,'right':c.drawRightString}[align](0,0,str(value))
        c.restoreState()
    def line(x,y,xx,yy,color=gray,weight=.22):
        c.setStrokeColor(HexColor(color));c.setLineWidth(weight*mm)
        c.line(x*mm,(297-y)*mm,xx*mm,(297-yy)*mm)
    for index,s in enumerate(sheets,1):
        code=s['code'];width=s['width'];runs=s['runs'];scale=25
        text(14,15,'КВАРТИРА   /   РАЗВЁРТКИ СТЕН',10,teal,True)
        text(405,15,f'{index:02} / {len(sheets):02}',10,gray,align='right')
        text(14,31,code+'   '+s['room'],26,bold=True)
        text(14,42,'Вид из помещения · U от левого края, H вверх от проектного чистого пола · миллиметры',12)
        line(14,49,406,49)
        ceiling=s.get('ceiling',2710)
        w,h=width/scale,ceiling/scale
        x=156-w/2;y=68;bottom=y+h
        with Image.open(s['image']) as source:
            compressed=BytesIO()
            source.convert('RGB').save(compressed,format='JPEG',quality=94,subsampling=0)
            compressed.seek(0)
        img=ImageReader(compressed)
        c.drawImage(img,x*mm,(297-bottom)*mm,w*mm,h*mm,mask='auto')
        for a,b,aa,bb in [(x,y,x+w,y),(x+w,y,x+w,bottom),(x+w,bottom,x,bottom),(x,bottom,x,y)]:line(a,b,aa,bb)
        # Elevation ordinates outside the wall leave the model readable behind furniture.
        for z in [*range(0,ceiling,500),ceiling]:
            yy=bottom-z/scale
            line(x-3,yy,x,yy,teal)
            text(x-4,yy+1,str(z),9,teal,align='right')
        def chain(values,ordinate):
            total=0;line(x-1.5,ordinate,x+w+1.5,ordinate)
            for n in range(len(values)+1):
                xx=x+total/scale
                line(xx,bottom+.6,xx,ordinate+1.7,gray,.14)
                line(xx-.85,ordinate+.85,xx+.85,ordinate-.85,ink,.32)
                if n < len(values):
                    val=values[n];text(xx+val/(2*scale),ordinate-1.5,val,9.5,ink,align='mid');total+=val
        if len(runs)>1:chain(runs,bottom+10)
        chain([width],bottom+22 if len(runs)>1 else bottom+10)
        text(305,69,'Привязки по плану',15,teal,True)
        offset=0;row=80
        for j,length in enumerate(runs):
            name=('Проём' if j%2 else (code+'.'+str(j//2+1) if len(runs)>1 else code))
            text(305,row,name,11,bold=True);text(399,row,f'{length} мм',11,align='right')
            offset+=length;row+=7
        if s['sockets']:
            row+=7;text(305,row,s.get('socket_source','Розетки по ЭП'),14,teal,True)
            for num,u,height,status in s['sockets']:
                row+=7;text(305,row,f'{num}    U {u}   /   H {height}',10)
                if status=='Уточнить':
                    row+=5;text(312,row,'привязку уточнить',8,gray)
        step = s.get('grid_mm', 500)
        text(15,227,f'Захват перед стеной: {s["depth"]} мм. Сетка {step} × {step} мм '+('включена.' if s['grid'] else 'выключена.'),11)
        if s['skirting']:
            trim = s.get('floor_trim_mm', 80)
            text(15,237,f'Напольный плинтус {trim} × 12 мм. В дверях и у панорамных окон предусмотрены разрывы.',11)
        else:
            text(15,237,'Эскизный слой плинтуса выключен.',11)
        height_label = f'Высота потолка от чистого пола {ceiling} мм.' if ceiling == 2700 else f'Высота профиля {ceiling} мм.'
        if s.get('membrane_mm'):
            height_label = (f'Плита +{ceiling} мм   /   натяжной потолок +{s["membrane_mm"]} мм'
                            f'   /   низ карниза +{s["cornice_bottom_mm"]} мм. Bello Deco С14/130, сечение 130 × 60 мм.')
        text(15,247,height_label,11)
        datum_note = 'Ноль чистого пола условно совмещён с подложкой. Уточнить по месту перед монтажом.'
        if s.get('membrane_mm') and code.startswith('G'):
            datum_note = 'На обмерном плане балка в коридоре +2470 мм. Участок и узел обхода подлежат обмеру.'
        text(15,256,datum_note,10,gray)
        if s.get('opening_note'):
            text(15,263,s['opening_note'],10,teal)
        line(14,269,406,269)
        text(14,280,'Эскиз для согласования   ·   A3, альбом   ·   1:25   ·   печать 100%',11,bold=True)
        line(345,282,395,282,ink,.4)
        for a in (345,395):line(a,280,a,284)
        text(370,278,'50 мм на бумаге',9,gray,align='mid')
        c.showPage()
    c.save()


if __name__=='__main__':
    write_pdf(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')), Path(sys.argv[2]))

