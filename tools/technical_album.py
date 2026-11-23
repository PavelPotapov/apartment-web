"""Print the coordinated A3 album in model millimetres. Pages use a top-left paper origin."""
from collections import defaultdict
from io import BytesIO
from math import ceil, cos, hypot, pi, sin
from pathlib import Path
import os
import re

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

FRONT_SHEETS = (
    ('plan', 'План квартиры'),
    ('dimensions', 'Размеры и проёмы'),
    ('sockets', 'План электроточек'),
    ('coordinates', 'Координаты электроточек'),
    ('plumbing', 'План сантехники'),
)
INK = '#233A33'
GREEN = '#346252'
LINE = '#A6B1A9'
FINE = '#C5CDC6'
MUTED = '#53665C'
PALE = '#EAF0EA'
WHITE = '#FFFFFF'
BLUE = '#23597D'
RUST = '#985830'
ROOM_COLORS = ['#E8EBDA', '#F0E5D9', '#DCECEA', '#E3E9F1', '#EDE1E1', '#E3E6DC', '#F1EBDB']


def register_fonts():
    system = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    for face, win, fallback in [('atlas-body', 'arial.ttf', 'DejaVuSans.ttf'),
                                 ('atlas-bold', 'arialbd.ttf', 'DejaVuSans-Bold.ttf')]:
        if face in pdfmetrics.getRegisteredFontNames():
            continue
        candidates = [system / win, Path('/usr/share/fonts/truetype/dejavu') / fallback]
        source = next((p for p in candidates if p.is_file()), None)
        if not source:
            raise FileNotFoundError('Для печати нужен Arial или DejaVu Sans с кириллицей')
        pdfmetrics.registerFont(TTFont(face, str(source)))


def number(v):
    value = round(float(v), 1)
    return str(int(value)) if value.is_integer() else str(value).replace('.', ',')


def wrap(value, max_width, size, bold=False):
    font = 'atlas-bold' if bold else 'atlas-body'
    result = []
    text = ''
    for word in str(value).split():
        candidate = (text + ' ' + word).strip()
        if text and pdfmetrics.stringWidth(candidate, font, size) / mm > max_width:
            result.append(text)
            text = word
        else:
            text = candidate
    if text:
        result.append(text)
    return result


class Paper:
    def __init__(self, dest, pages, version):
        self.c = Canvas(str(dest), pagesize=(420 * mm, 297 * mm), pageCompression=1)
        self.c.setTitle('Атлас квартиры · планы и развёртки')
        self.c.setAuthor('Атлас квартиры')
        self.total = pages
        self.version = version

    def text(self, x, y, value, size=10, color=INK, bold=False, align='left', angle=0):
        c = self.c
        c.saveState()
        c.translate(x * mm, (297 - y) * mm)
        c.rotate(angle)
        c.setFont('atlas-bold' if bold else 'atlas-body', size)
        c.setFillColor(HexColor(color))
        method = {'left': c.drawString, 'mid': c.drawCentredString, 'right': c.drawRightString}[align]
        method(0, 0, str(value))
        c.restoreState()

    def paragraph(self, x, y, value, width, size=10, color=MUTED, step=4.7):
        for row in wrap(value, width, size):
            self.text(x, y, row, size, color)
            y += step
        return y

    def line(self, x, y, xx, yy, color=LINE, weight=.22, opacity=1):
        c = self.c
        c.setStrokeColor(HexColor(color)); c.setStrokeAlpha(opacity); c.setLineWidth(weight * mm)
        c.line(x * mm, (297-y)*mm, xx*mm, (297-yy)*mm)

    def rect(self, x, y, w, h, fill=None, stroke=None, weight=.18):
        c = self.c
        if fill: c.setFillColor(HexColor(fill))
        if stroke: c.setStrokeColor(HexColor(stroke))
        c.setLineWidth(weight*mm)
        c.rect(x*mm, (297-y-h)*mm, w*mm, h*mm, fill=int(bool(fill)), stroke=int(bool(stroke)))

    def polygon(self, pts, fill, stroke=None, weight=.20):
        if len(pts) < 3: return
        c = self.c; path = c.beginPath()
        path.moveTo(pts[0][0]*mm, (297-pts[0][1])*mm)
        for x,y in pts[1:]: path.lineTo(x*mm,(297-y)*mm)
        path.close()
        if fill: c.setFillColor(HexColor(fill))
        if stroke: c.setStrokeColor(HexColor(stroke))
        c.setLineWidth(weight*mm); c.drawPath(path, fill=int(bool(fill)), stroke=int(bool(stroke)))

    def circle(self,x,y,r,fill,stroke=None,weight=.18):
        c=self.c
        if fill: c.setFillColor(HexColor(fill))
        if stroke: c.setStrokeColor(HexColor(stroke))
        c.setLineWidth(weight*mm)
        c.circle(x*mm,(297-y)*mm,r*mm,fill=int(bool(fill)),stroke=int(bool(stroke)))

    def header(self, idx, title, sub):
        key='sheet-'+str(idx)
        self.c.bookmarkPage(key)
        self.c.addOutlineEntry(title,key,level=0,closed=False)
        self.text(14, 14, 'АТЛАС КВАРТИРЫ   /   ЖК ПРИВИЛЕГИЯ', 9.5, GREEN, True)
        if self.version:
            self.text(339,14,'Выпуск '+self.version,9,MUTED,align='right')
        self.text(406,14,f'{idx:02d}   /   {self.total:02d}',9.5,MUTED,True,'right')
        self.text(14,30,title,25,INK,True)
        self.text(14,40,sub,11,MUTED)
        self.line(14,45,406,45)

    def footer(self, caption):
        self.line(14,276,406,276)
        self.text(14,286,caption+'   ·   A3   ·   Печать 100%',10,INK,True)
        self.line(351,284,401,284,INK,.32)
        for x in (351,401): self.line(x,282.6,x,285.4,INK,.28)
        self.text(376,282,'Контроль 50 мм',8,MUTED,align='mid')
        self.c.showPage()


def point_on_wall(w, u):
    return [w['origin'][i] + u*w['direction'][i] for i in (0,1)]


def transform_for(plan, available=(16,56,271,194)):
    x0,y0,x1,y1=plan['bounds']
    left,top,w,h=available
    minimum=max((x1-x0)/w,(y1-y0)/h)
    scale=next((v for v in (20,25,30,35,40,50,60,65,70,75,80,90,100,125,150) if v>=minimum),ceil(minimum))
    ox=left + (w-(x1-x0)/scale)/2
    oy=top + (h-(y1-y0)/scale)/2
    def project(x,y): return (ox+(x-x0)/scale,oy+(y-y0)/scale)
    return project,scale


def inside(x,y,poly):
    hit=False
    for (ax,ay),(bx,by) in zip(poly,poly[1:]+poly[:1]):
        if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax: hit=not hit
    return hit


def room_anchor(poly):
    xs,ys=zip(*poly)
    center=((min(xs)+max(xs))/2,(min(ys)+max(ys))/2)
    if inside(*center,poly):return center
    choices=[]
    for ix in range(1,10):
        for iy in range(1,10):
            x=min(xs)+(max(xs)-min(xs))*ix/10;y=min(ys)+(max(ys)-min(ys))*iy/10
            if inside(x,y,poly):choices.append((hypot(x-center[0],y-center[1]),x,y))
    return min(choices)[1:] if choices else poly[0]


def front_page_base(p,tech,mode,space=(16,56,271,194)):
    plan=tech['plan'];project,scale=transform_for(plan,space)
    for index,room in enumerate(plan['rooms']):
        fill=ROOM_COLORS[index%len(ROOM_COLORS)] if mode=='plan' else '#F5F6F1'
        p.polygon([project(*pt) for pt in room['polygon']],fill)
    # Cut-polygons come from Blender wall solids at 1150 mm. Leave white openings
    # between jambs, including the doorway joins shared by the two bathrooms.
    for outline in plan.get('wallPolygons',[]):
        poly=[project(*pt) for pt in outline]
        p.polygon(poly,'#69756C')
    if mode=='plan':
        for item in plan.get('furniture',[]):
            if item['category'] in ('furniture','plumbing','heating'):
                p.polygon([project(*v) for v in item['polygon']],None,'#B6BBAF',.17)
    for w in tech['walls']:
        width=w['width'];end=0
        def segment(a,b,col,weight):
            start=project(*point_on_wall(w,a));stop=project(*point_on_wall(w,b));p.line(*start,*stop,col,weight)
        for ap in sorted(w['apertures'],key=lambda a:a['u']):
            begin=ap['u'];stop=begin+ap['width']
            if begin>end:segment(end,begin,INK,.72)
            if ap['type']=='window':segment(begin,stop,'#73A5AB',.58)
            for u in (begin,stop):
                px,py=project(*point_on_wall(w,u));dx,dy=w['direction']
                p.line(px-dy*.9,py+dx*.9,px+dy*.9,py-dx*.9,INK,.31)
            end=max(end,stop)
        if end<width:segment(end,width,INK,.72)
    return project,scale


def room_register(p,tech,y=64):
    p.text(300,y,'Экспликация',15,GREEN,True);y+=10
    for room in tech['rooms']:
        p.text(301,y,room['id'],13,GREEN,True)
        p.text(313,y,room['name'],10,INK)
        p.text(404,y,f"{room['area']:.2f}".replace('.',',')+' м²',10,INK,align='right')
        p.line(300,y+3,405,y+3,FINE,.13);y+=10
    return y


def marker(p,x,y,label,r,color):
    p.circle(x,y,r,WHITE,color,.29)
    p.text(x,y+1.0,label,7.0 if len(str(label))<=2 else 6,color,True,'mid')


def draw_plan(p,tech):
    p.header(1,'План квартиры','Обозначения помещений и состав альбома  ·  вид сверху')
    project,scale=front_page_base(p,tech,'plan')
    for room in tech['plan']['rooms']:
        x,y=project(*room_anchor(room['polygon']));p.circle(x,y,4.1,GREEN)
        p.text(x,y+1.55,room['id'],12,WHITE,True,'mid')
    for w in tech['walls']:
        if w['roomId']=='G':
            continue
        runs=w['runs']
        longest=max(range(0,len(runs),2),key=lambda i:runs[i])
        station=sum(runs[:longest])+runs[longest]*.50
        px,py=project(*point_on_wall(w,station));dx,dy=w['direction']
        px-=dy*2.7;py+=dx*2.7
        p.text(px,py+.8,w['code'],7.5,GREEN,True,'mid',90 if dy else 0)
    y=room_register(p,tech)
    p.text(300,y+10,'Всего',12,INK,True);p.text(404,y+10,f"{sum(r['area'] for r in tech['rooms']):.2f}".replace('.',',')+' м²',12,INK,True,'right')
    p.text(300,y+29,'Листы альбома',14,GREEN,True)
    for row,(range_,name) in enumerate([('02','Размеры и проёмы'),('03–04','Электроточки'),('05','Сантехника'),('06–'+str(p.total),'Развёртки A1–G15')]):
        p.text(301,y+40+row*8,range_,10,GREEN,True);p.text(325,y+40+row*8,name,10)
    p.paragraph(16,260,'Одно обозначение на плане соответствует одному помещению. Стены и участки внутри помещения обозначены буквой комнаты и номером плоскости.',261)
    p.footer(f'Общий план  ·  1:{scale}')


def room_size(poly):
    xs,ys=zip(*poly);return max(xs)-min(xs),max(ys)-min(ys)


def draw_dimensions(p,tech):
    p.header(2,'Размеры и проёмы','Габариты помещений по внутренним граням модели  ·  размеры в миллиметрах')
    project,scale=front_page_base(p,tech,'dimensions')
    for room in tech['plan']['rooms']:
        width,depth=room_size(room['polygon']);x,y=project(*room_anchor(room['polygon']))
        p.text(x,y-1,room['id'],12,GREEN,True,'mid')
        if room['id']!='G':p.text(x,y+4,number(width)+' × '+number(depth),8.7,GREEN,False,'mid')
    p.text(300,61,'Проёмы в стенах',14,GREEN,True)
    p.text(300,69,'Код стены и ширина проёма по модели, мм',9,MUTED)
    y=79
    for w in tech['walls']:
        if not w['apertures']:continue
        # Interior doors are scheduled on their room side; G12 is the entrance.
        if w['roomId']=='G' and w['code']!='G12':continue
        fields=[]
        for a in w['apertures']:
            kind={'window':'окно','passage':'проход','door':'дверь'}.get(a['type'],'проём')
            fields.append(kind+' '+number(a['width']))
        p.text(300,y,w['code'],10,GREEN,True)
        rows=wrap(', '.join(fields),83,9.2)
        for j,line in enumerate(rows):p.text(317,y+3.8*j,line,9.2)
        y+=max(7.3,3.8*len(rows)+2)
    # Chains on the exterior of each straight facade, leaving short corridor planes to the individual wall sheets.
    for code,side in [('A4','left'),('B4','left'),('B1','top'),('C1','top'),('D1','top'),('E1','top'),('F2','right'),('A3','bottom'),('F3','bottom')]:
        w=next((s for s in tech['walls'] if s['code']==code),None)
        if not w:continue
        first=project(*point_on_wall(w,0));last=project(*point_on_wall(w,w['width']))
        dx,dy=w['direction'];offset={'top':(0,-10),'left':(-14,0),'right':(14,0),'bottom':(0,10)}[side]
        a=(first[0]+offset[0],first[1]+offset[1]);b=(last[0]+offset[0],last[1]+offset[1])
        if min(a[0],b[0])<6 or max(a[0],b[0])>291 or min(a[1],b[1])<47 or max(a[1],b[1])>252:continue
        p.line(*a,*b,MUTED,.17);p.line(*first,*a,MUTED,.14);p.line(*last,*b,MUTED,.14)
        cursor=0
        for length in [*w['runs'],0]:
            q=project(*point_on_wall(w,cursor));cx=q[0]+offset[0];cy=q[1]+offset[1]
            p.line(cx-.72,cy+.72,cx+.72,cy-.72,INK,.25)
            if length/scale>=6.5:
                mx=cx+dx*length/(2*scale);my=cy+dy*length/(2*scale)
                p.text(mx if dx else mx-.9,my-1 if dx else my,number(length),7.3,INK,True,'mid',90 if dy else 0)
            cursor+=length
    hall=next(r for r in tech['plan']['rooms'] if r['id']=='G')
    xs,ys=zip(*hall['polygon'])
    space=(301,191,102,68)
    mini=dict(tech,plan=dict(tech['plan'],rooms=[hall],wallPolygons=[],
              bounds=[min(xs)-200,min(ys)-200,max(xs)+200,max(ys)+200]),walls=[w for w in tech['walls'] if w['roomId']=='G'])
    hp,hscale=front_page_base(p,mini,'dimensions',space)
    hw,hd=room_size(hall['polygon'])
    p.text(300,186,'Прихожая G   ·   '+number(hw)+' × '+number(hd)+' мм',12,GREEN,True)
    targets=[]
    for item in mini['walls']:
        x,y=hp(*point_on_wall(item,item['width']/2))
        targets.append(((x,y),item['code'][1:],GREEN))
    colored_marks(p,targets,(298,188,405,260),2.45)
    p.text(300,268,f'Номер в кружке обозначает стену G.   1:{hscale}',8.4,MUTED)
    p.paragraph(16,260,'Показаны ширина и глубина по крайним точкам каждого контура. Полные цепочки простенок–проём и длина каждой плоскости приведены на соответствующей развёртке.',266)
    p.footer(f'Габариты и размерные цепи  ·  1:{scale}')

def points_by_zone(plan):
    lookup=defaultdict(list)
    for s in plan['sockets']:
        lookup[s['code']].append(s)
    return lookup


def draw_electrical(p,tech):
    p.header(3,'План электроточек','Индексы точек соответствуют ведомости U/H и маркерам на развёртках стен')
    project,scale=front_page_base(p,tech,'electrical')
    for room in tech['plan']['rooms']:
        x,y=project(*room_anchor(room['polygon']));p.text(x,y,room['id'],12,'#8D9D90',True,'mid')
    sockets=tech['plan']['sockets']
    arranged_electrical(p,sockets,project)
    p.text(300,62,'Обозначения',15,GREEN,True)
    for y,col,n in [(75,BLUE,'Привязка по электроплану'),(88,RUST,'Требуется уточнение'),(101,MUTED,'Архивная точка')]:
        marker(p,303,y-1,'№',2.65,col);p.text(310,y,n,10)
    p.text(300,123,'Как читать привязки',14,GREEN,True)
    p.paragraph(300,133,'U отсчитывается слева направо при взгляде на стену из комнаты. H измеряется от проектного чистого пола до центра электроточки.',103)
    p.paragraph(300,160,'Несколько высот для одного номера означают несколько уровней установки. На развёртке отмечен каждый уровень.',104)
    p.text(300,190,'Координаты',12,GREEN,True)
    p.paragraph(300,200,'Ведомость номеров, стен, высот и статусов приведена на листе 04. Расстояния до проёмов и мебели проверяются по листу соответствующей стены.',103)
    p.paragraph(16,260,'Точка отмечает место установки из модели или его проекцию на стену. Цвет марки сохраняется на плане, в ведомости и на развёртке.',265)
    p.footer(f'План электроточек  ·  1:{scale}')


def point_color(s):
    if s.get('archived'):return MUTED
    if s.get('approximate'):return RUST
    return BLUE


def arranged_electrical(p,sockets,project):
    items=[(project(s['x'],s['y']),s['number'],point_color(s)) for s in sockets]
    colored_marks(p,items,(6,48,291,251))


def colored_marks(p,items,area,r=2.5):
    occupied=[]
    targets=[a for a,label,color in items]
    for (x,y),label,color in items:
        scores=[]
        for dist in (4.9,7.7,10.4,13.1,16.0,19):
            for i in range(16):
                angle=i*2*pi/16-pi/2;cx=x+dist*cos(angle);cy=y+dist*sin(angle)
                if not (area[0]+r<cx<area[2]-r and area[1]+r<cy<area[3]-r): continue
                penalty=sum(max(0,2*r+1-hypot(cx-a,cy-b))*12 for a,b in occupied)
                penalty+=sum(max(0,r+1-hypot(cx-a,cy-b))*3 for a,b in targets)
                scores.append((dist+penalty,cx,cy))
        _,cx,cy=min(scores) if scores else (0,x,y)
        occupied.append((cx,cy));p.line(x,y,cx,cy,color,.23);p.circle(x,y,.71,WHITE,color,.26)
        marker(p,cx,cy,label,r,color)


def height_names(s):
    hs = s.get('heightsMm') or s.get('heights') or []
    return ' / '.join(number(n) for n in hs) if hs else str(s.get('height','—'))


def status_label(s):
    if s.get('archived'):return 'Архив'
    return 'Уточнить' if s.get('approximate') else 'По ЭП'


def draw_coordinates(p,tech):
    p.header(4,'Координаты электроточек','U — от левого края стены при взгляде из помещения; H — от проектного чистого пола до центра точки. Все размеры в мм.')
    points=sorted(tech['plan']['sockets'],key=lambda t:int(re.search(r'\d+',str(t['number'])).group()))
    batch=ceil(len(points)/2)
    for column,items in enumerate((points[:batch],points[batch:])):
        x=14+column*200
        p.rect(x,55,191,10,PALE)
        fields=[x+3,x+20,x+45,x+73,x+134]
        for dx,name in zip(fields,('№','Стена','U, мм','H, мм','Статус')):
            p.text(dx,61.6,name,10,GREEN,True)
        for row,s in enumerate(items):
            y=74+row*9.15
            for i,(dx,val) in enumerate(zip(fields,(s['number'],s['code'],number(s['u']),height_names(s),status_label(s)))):
                p.text(dx,y,val,10,point_color(s) if i in (0,4) else INK,i==0)
            p.line(x,y+2.4,x+191,y+2.4,FINE,.14)
    notes=[]
    for s in points:
        if s.get('heightSource')=='sill-relative':
            notes.append('№'+str(s['number'])+' · '+str(s.get('height',''))+'; центр на отметке +'+height_names(s)+' мм.')
        if s.get('archived'):
            notes.append('№'+str(s['number'])+' · архивная точка по прежней планировке. Место и необходимость установки требуют согласования.')
    p.paragraph(14,244,'   '.join(notes),390,10)
    p.paragraph(14,264,'По ЭП — размер из исходного электроплана. Статус «Уточнить» сохраняется до подтверждения установочных размеров.',385,10)
    p.footer('Ведомость координат')


def draw_plumbing(p,tech):
    p.header(5,'План сантехники','Кухня, душевая и ванная при спальне  ·  проектные контуры оборудования в плане')
    plan=tech['plan']
    features=('посудомоечн','душевая стойка','линейный слив','колонна стирки','полотенцесушитель','слив ванны')
    fixtures=sorted([f for f in plan['furniture'] if f['category']=='plumbing' or (
        f['category'] in ('service','heating') and any(t in f['name'].lower() for t in features))],
        key=lambda f:(f['roomId'],f['id']))
    if not fixtures:raise ValueError('В экспорте отсутствуют контуры сантехнического оборудования')
    indexed=list(enumerate(fixtures,1))
    for ids,space,title in [({'C','D'},(16,58,270,110),'C / D   Душевая и ванная'),({'A'},(16,186,270,63),'A   Кухонная мойка и техника')]:
        items=[(idx,f) for idx,f in indexed if f['roomId'] in ids]
        if not items: continue
        zones=[r for r in plan['rooms'] if r['id'] in ids]
        if ids=={'A'}:points=[v for n,f in items for v in f['polygon']]
        else:points=[v for r in zones for v in r['polygon']]
        xs,ys=zip(*points);padding=140
        bounds=[min(xs)-padding,min(ys)-padding,max(xs)+padding,max(ys)+padding]
        mini=dict(tech,plan=dict(plan,rooms=zones,bounds=bounds),walls=[w for w in tech['walls'] if w['roomId'] in ids])
        left,top,w,h=space;p.rect(left,top,w,h,'#FAFBF8',FINE)
        p.c.saveState()
        path=p.c.beginPath();path.rect(left*mm,(297-top-h)*mm,w*mm,h*mm);p.c.clipPath(path,stroke=0,fill=0)
        project,scale=front_page_base(p,mini,'plumbing',space)
        marks=[]
        for n,f in items:
            poly=[project(*v) for v in f['polygon']]
            p.polygon(poly,'#C8DDD9' if f['category']=='plumbing' else '#E3ECE1','#436965',.35)
            marks.append((project(f['x'],f['y']),str(n),GREEN))
        colored_marks(p,marks,(left,top,left+w,top+h),2.95)
        p.c.restoreState()
        p.text(left,top-3,title+'   ·   1:'+str(scale),10,GREEN,True)
    p.text(300,62,'Приборы и оборудование',14,GREEN,True)
    y=74;prev=None
    for n,item in indexed:
        rid=item['roomId']
        if rid!=prev:
            p.text(300,y,rid+'   '+next(r['name'] for r in tech['rooms'] if r['id']==rid),11,GREEN,True)
            y+=7;prev=rid
        p.text(301,y,str(n).zfill(2),9.5,GREEN,True)
        y=p.paragraph(311,y,item.get('label') or item['name'],94,9.3,INK,3.95)+3
    p.paragraph(16,262,'Цифры связывают приборы с перечнем справа. Оси подключений, отметки выпусков и трассировку следует брать из инженерного проекта.',266,10)
    p.footer('Расположение сантехники')



def print_grid(p,x,y,width,height,scale):
    w=width/scale;h=height/scale;bottom=y+h;c=p.c
    c.saveState()
    # A 100-mm line every 4 mm on paper; major lines at 500 mm with axes outside the wall.
    for n in range(100,ceil(width),100):
        xx=x+n/scale
        strength=.54 if n%500==0 else .22
        p.line(xx,y,xx,bottom,GREEN,.18 if n%500==0 else .09,strength)
    for n in range(100,ceil(height),100):
        yy=bottom-n/scale
        p.line(x,yy,x+w,yy,GREEN,.18 if n%500==0 else .09,.54 if n%500==0 else .22)
    c.restoreState()
    for n in range(0,ceil(width),500):
        xx=x+n/scale;p.line(xx,y-1.2,xx,y,GREEN,.16)
        if width-n>160 or n==0:p.text(xx,y-2.5,number(n),7.3,GREEN,align='mid')
    for n in list(range(0,ceil(height),500))+[height]:
        yy=bottom-n/scale;p.line(x-2.2,yy,x,yy,GREEN,.17);p.text(x-3,yy+1,number(n),7.5,GREEN,align='right')
    p.rect(x,y,w,h,None,INK,.29)


def elevation_chain(p,x,bottom,values,scale,y):
    p.line(x-1.5,y,x+sum(values)/scale+1.5,y,MUTED,.18);cursor=0
    for n in [*values,0]:
        xx=x+cursor/scale;p.line(xx,bottom+.5,xx,y+1.5,LINE,.13);p.line(xx-.83,y+.83,xx+.83,y-.83,INK,.24)
        if n:p.text(xx+n/(2*scale),y-1.4,number(n),8.0,INK,align='mid')
        cursor+=n


def draw_elevation(p,s,base,sockets):
    code=s['code'];width=s['width'];height=s['height'];scale=25
    p.header(s['page'],code+'   '+s['room'],'Развёртка из помещения  ·  U слева направо, H вверх от чистого пола  ·  размеры в миллиметрах')
    w=width/scale;h=height/scale;x=158-w/2;y=65;bottom=y+h
    path=base/s['elevations']['furnished']
    with Image.open(path) as img:
        memory=BytesIO()
        rgb=img.convert('RGB')
        Image.blend(rgb,Image.new('RGB',rgb.size,'white'),.14).save(memory,format='JPEG',quality=95,subsampling=0)
        memory.seek(0)
    p.c.drawImage(ImageReader(memory),x*mm,(297-bottom)*mm,w*mm,h*mm)
    print_grid(p,x,y,width,height,scale)
    marks=[]
    for socket in sockets:
        levels=socket.get('heightsMm') or socket.get('heights') or []
        for level in levels:
            if 0<=float(level)<=height:
                pos=(x+socket['u']/scale,bottom-level/scale)
                marks.append((pos,socket['number'],point_color(socket)))
    colored_marks(p,marks,(max(5,x-8),y-2,min(302,x+w+9),bottom+1.5),2.2)
    if len(s['runs'])>1:elevation_chain(p,x,bottom,s['runs'],scale,bottom+9)
    elevation_chain(p,x,bottom,[width],scale,bottom+(18 if len(s['runs'])>1 else 9))
    p.text(307,62,'Привязки по стене',14,GREEN,True)
    row=72;aps=s['apertures'];cursor=0;solid=0
    for n in s['runs']:
        ap=next((a for a in aps if abs(a['u']-cursor)<2 and abs(a['width']-n)<2),None)
        if ap:
            label={'window':'Окно','passage':'Проход','door':'Дверной проём'}.get(ap['type'],'Проём')
        else:
            solid+=1;label=code+'.'+str(solid) if len(s['runs'])>1 else code
        p.text(307,row,label,10,INK,True);p.text(405,row,number(n)+' мм',10,INK,align='right')
        p.line(307,row+2.2,405,row+2.2,FINE,.14);row+=7.2;cursor+=n
    if sockets:
        row+=7;p.text(307,row,'Электроточки',13,GREEN,True)
        row+=8;p.text(307,row,'№',9,MUTED,True);p.text(323,row,'U, мм',9,MUTED,True);p.text(347,row,'H, мм',9,MUTED,True);p.text(405,row,'Статус',9,MUTED,True,'right')
        for sck in sockets:
            row+=7;p.text(307,row,sck['number'],9.5,point_color(sck),True)
            p.text(323,row,number(sck['u']),9.3);p.text(347,row,height_names(sck),9.3)
            p.text(405,row,status_label(sck),9,point_color(sck),align='right')
    p.line(14,204,406,204)
    p.text(14,214,'Отметки и детали',13,GREEN,True)
    elevation_notes=[f"Плита +{height} мм",f"натяжной потолок +{s['membrane_mm']} мм" if s.get('membrane_mm') else '',
                     f"низ карниза +{s['cornice_bottom_mm']} мм" if s.get('cornice_bottom_mm') else '',
                     f"напольный плинтус {s['floor_trim_mm']} мм" if s.get('floor_trim_mm') else '']
    p.text(14,223,'   /   '.join(filter(None,elevation_notes)),10,INK)
    after=p.paragraph(14,233,s.get('opening_note',''),260,10,MUTED,4.8)
    if code.startswith('G'):
        p.paragraph(14,max(247,after+2),'На обмере отмечена балка коридора +2470 мм. Положение и узел обхода требуют замера.',260,9.6)
    p.text(307,214,'Шаг печатной сетки',12,GREEN,True)
    p.text(307,223,'100 × 100 мм',12,INK,True)
    p.text(307,231,'Основные линии через 500 мм.',9.5,MUTED)
    p.text(307,240,'Захват перед стеной '+number(s['depth'])+' мм.',9.5,MUTED)
    if sockets:
        p.paragraph(307,251,'Кружок указывает центр. Номер и цвет соответствуют электрической ведомости на листе 04.',99,9.1)
    p.footer('Развёртка  ·  1:25')


def write_technical_pdf(technical, destination, data_root):
    register_fonts()
    wall_rows=technical['walls']
    plan=technical['plan']
    sheets=technical['frontSheets']
    if [s['key'] for s in sheets]!=[k for k,t in FRONT_SHEETS]:
        raise ValueError('Порядок вступительных листов не совпадает с оглавлением')
    paper=Paper(destination,len(sheets)+len(wall_rows),str(technical.get('version','')))
    for fn in (draw_plan,draw_dimensions,draw_electrical,draw_coordinates,draw_plumbing):
        fn(paper,technical)
    socket_index=points_by_zone(plan)
    for index,s in enumerate(wall_rows,len(sheets)+1):
        if s['page']!=index: raise ValueError(s['code']+' неверный номер листа')
        draw_elevation(paper,s,Path(data_root),socket_index[s['code']])
    paper.c.save()


