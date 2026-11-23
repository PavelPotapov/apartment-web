"""Create the printable floor material schedule from the same data as the website."""
from datetime import date
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def number(value, places=0):
    return format(value, f",.{places}f").replace(",", " ").replace(".", ",")


def write_estimate(source, destination, version):
    data = json.loads(source.read_text(encoding="utf-8"))
    if not data["items"]:
        return
    assets = Path(__file__).resolve().parents[1] / "public" / "assets"
    pdfmetrics.registerFont(TTFont("ProjectSans", str(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("ProjectSerif", str(assets / "pt-serif.ttf")))
    ink = colors.HexColor("#233d35")
    line = colors.HexColor("#d5d9ce")
    body = ParagraphStyle("body", fontName="ProjectSans", fontSize=11, leading=15, textColor=ink)
    small = ParagraphStyle("small", parent=body, fontSize=9.5, leading=13)
    title = ParagraphStyle("heading", parent=body, fontName="ProjectSerif", fontSize=26, leading=32)
    subhead = ParagraphStyle("subhead", parent=title, fontSize=16, leading=21)
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=22*mm, bottomMargin=20*mm, title="Ведомость напольных покрытий")
    stamp = date.fromisoformat(data["asOf"]).strftime("%d.%m.%Y")
    parts = [Paragraph("Квартира в Привилегии", small), Spacer(1, 5*mm),
             Paragraph("Ведомость напольных покрытий", title), Spacer(1, 3*mm),
             Paragraph(f"Выпуск {escape(version)}  ·  Цены на {stamp}", body), Spacer(1, 13*mm)]
    headings = ["Покрытие", "Площадь,<br/>м²", "Запас", "К заказу,<br/>м²", "Цена,<br/>₽/м²", "Сумма,<br/>₽"]
    rows = [[Paragraph(text, small) for text in headings]]
    for item in data["items"]:
        rows.append([Paragraph(escape(item["label"]), body), number(item["areaM2"], 2),
                     f'{item["wastePct"]}%', number(item["orderM2"], 3).rstrip("0").rstrip(","),
                     number(item["priceRubM2"]), number(item["totalRub"])])
    table = Table(rows, colWidths=[n*mm for n in (54,23,17,27,22,28)], repeatRows=1)
    table.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),"ProjectSans"),("FONTSIZE",(0,0),(-1,-1),11),
                ("TEXTCOLOR",(0,0),(-1,-1),ink),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("ALIGN",(1,1),(-1,-1),"RIGHT"),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eef1e8")),
                ("LINEBELOW",(0,0),(-1,-1),.5,line),("TOPPADDING",(0,0),(-1,-1),8),
                ("BOTTOMPADDING",(0,0),(-1,-1),8)]))
    total = sum(item["totalRub"] for item in data["items"])
    parts.extend([table,Spacer(1,8*mm),Paragraph(f"Материалы на сумму {number(total)} ₽",subhead),
                  Spacer(1,4*mm),Paragraph(escape(data["note"]), body),Spacer(1,12*mm),
                  Paragraph("Карточки для сверки цены", subhead),Spacer(1,3*mm)])
    for item in data["items"]:
        url = quoteattr(item["sourceUrl"])
        text = escape(item["sourceLabel"] + " · " + item["label"])
        parts.append(Paragraph(f'<link href={url} color="#386846"><u>{text}</u></link>', body))
    doc.build(parts)
