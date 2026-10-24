"""Visit summary as a PDF: a one-page summary, then an appendix of source
sentences. Every number on page one is an internal link into the appendix."""
from __future__ import annotations

import os
from html import escape
from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from .report_common import (DISCLAIMER, entry_tags, fmt_date, fmt_minutes, fmt_ts,
                            source_text)

INK = colors.HexColor("#1F2A2E")
BODY = colors.HexColor("#3A4548")
MUTED = colors.HexColor("#5F686B")
LINE = colors.HexColor("#DED6C6")
HEAD = colors.HexColor("#EFE8DB")
ACCENT = colors.HexColor("#A8432F")
TEAL = "#2F6F6A"

# TrueType fonts with Traditional Chinese, embedded when found.
FONT_CANDIDATES = [
    (os.environ.get("SPEAKHOME_FONT", ""), 0),
    ("C:/Windows/Fonts/msjh.ttc", 0),                    # Microsoft JhengHei
    ("C:/Windows/Fonts/mingliu.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),     # macOS
    ("/Library/Fonts/Arial Unicode.ttf", 0),
    ("/usr/share/fonts/truetype/arphic/uming.ttc", 0),   # Linux: fonts-arphic-uming
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
]


def register_font() -> str:
    for path, index in FONT_CANDIDATES:
        if path and Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("CJK", path, subfontIndex=index))
                return "CJK"
            except Exception:
                continue
    # Fallback: a standard Traditional Chinese CID font (not embedded; PDF
    # viewers substitute a system font).
    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    return "MSung-Light"


def _styles(font: str):
    base = dict(fontName=font, textColor=BODY, leading=15, fontSize=10)
    return {
        "h1": ParagraphStyle("h1", **{**base, "fontSize": 20, "leading": 26, "textColor": INK}),
        "sub": ParagraphStyle("sub", **{**base, "textColor": MUTED}),
        "h2": ParagraphStyle("h2", **{**base, "fontSize": 13, "leading": 18, "textColor": INK,
                                      "spaceBefore": 10, "spaceAfter": 5}),
        "cell": ParagraphStyle("cell", **base),
        "head": ParagraphStyle("head", **{**base, "fontSize": 9, "textColor": MUTED}),
        "small": ParagraphStyle("small", **{**base, "fontSize": 8.5, "leading": 12, "textColor": MUTED}),
        "flag": ParagraphStyle("flag", **{**base, "backColor": colors.HexColor("#F3DCD3"),
                                          "borderPadding": 6, "textColor": INK}),
    }


def _link(group, label):
    if not group:
        return escape(label)
    return f'<a href="#{group}" color="{TEAL}"><u><b>{escape(label)}</b></u></a>'


def _table(rows, st, widths):
    data = [[Paragraph(c, st["head"]) for c in rows[0]]]
    data += [[Paragraph(c, st["cell"]) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _chart(daily, font, width):
    d = Drawing(width, 105)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 24, 18, width - 30, 78
    chart.data = [[v if v is not None else 0 for _, v in daily]]
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 10, 5
    chart.valueAxis.labels.fontName = font
    chart.valueAxis.labels.fontSize = 7
    step = max(1, len(daily) // 10)
    chart.categoryAxis.categoryNames = [f"{day.month}/{day.day}" if i % step == 0 else ""
                                        for i, (day, _) in enumerate(daily)]
    chart.categoryAxis.labels.fontName = font
    chart.categoryAxis.labels.fontSize = 7
    chart.bars[0].fillColor = ACCENT
    chart.bars[0].strokeColor = None
    chart.barSpacing = 1
    d.add(chart)
    d.add(String(width - 4, 98, "0 = 當天無症狀或未評分", fontName=font, fontSize=7,
                 fillColor=MUTED, textAnchor="end"))
    return d


def _footer(font):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, DISCLAIMER.split("This summary")[0].strip())
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Speak Home · {doc.page}")
        canvas.restoreState()
    return draw


def render_pdf(s: dict, path: str | Path, patient: str = "[姓名]") -> Path:
    font = register_font()
    st = _styles(font)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"回診摘要 {patient}", author="Speak Home")
    W = A4[0] - 36 * mm
    story = [
        Paragraph('<a name="top"/>回診摘要 <font size="11" color="#5F686B">Visit summary</font>', st["h1"]),
        Paragraph(f"{escape(patient)} · {fmt_date(s['start'])} – {fmt_date(s['end'])}，共 {s['days_total']} 天 · "
                  f"{_link(s['logged_group'], str(s['entry_count']) + ' 筆')}已確認紀錄 · "
                  f"{s['days_logged']} 天有紀錄 · {_link(s['well_group'], str(s['well_days']) + ' 天')}自述身體還好",
                  st["sub"]),
        Paragraph("藍色底線的數字可點選，會跳到附錄中的原話。Underlined numbers link to the source sentences.", st["small"]),
    ]
    if s["red_flags"]:
        items = "、".join(f'{escape(f["name"])}（{_link(f["group"], str(f["count"]) + " 次")}）' for f in s["red_flags"])
        story += [Spacer(1, 6), Paragraph(f"需要注意的字詞：{items}。當時站台已提示聯絡家人或撥打 119；此為字詞比對，不是醫療判斷。", st["flag"])]

    story.append(Paragraph("症狀 <font size='9' color='#5F686B'>Symptoms</font>", st["h2"]))
    if s["symptoms"]:
        rows = [["症狀", "次數", "嚴重度 中位數 / 最高", "常見時段", "持續（中位數）", "前後半段比較"]]
        for sym in s["symptoms"]:
            sev = "—" if sym["median"] is None else f'{sym["median"]:g} / {sym["max"]}'
            tr = sym["trend"]
            trend = "資料不足" if not tr else f'{tr["label"]}（{tr["first"]:g} → {tr["second"]:g}）'
            rows.append([f"<b>{escape(sym['name'])}</b>", _link(sym["group"], f"{sym['count']} 次") + f"（{sym['days']} 天）",
                         sev, escape(sym["common_time"] or "—"), fmt_minutes(sym["median_duration"]), trend])
        story.append(_table(rows, st, [W * x for x in (0.12, 0.16, 0.17, 0.12, 0.17, 0.26)]))
        story += [Spacer(1, 4), Paragraph("每日最高嚴重度（0–10）", st["head"]), _chart(s["daily"], font, W)]
    else:
        story.append(Paragraph("這段期間沒有提到症狀。", st["cell"]))

    if s["bp"] or s["glucose"] or s.get("heart_rate"):
        story.append(Paragraph("量測 <font size='9' color='#5F686B'>Measurements</font>", st["h2"]))
        rows = [["項目", "筆數", "平均", "最高", "最低"]]
        if bp := s["bp"]:
            avg = f'{bp["mean_sys"]}' + (f' / {bp["mean_dia"]}' if bp["mean_dia"] else "")
            rows.append(["<b>血壓</b>（收縮 / 舒張）", _link(bp["group"], f"{bp['count']} 筆"), avg,
                         _link(bp["max_group"], str(bp["max_sys"])), str(bp["min_sys"])])
        if g := s["glucose"]:
            rows.append(["<b>血糖</b>", _link(g["group"], f"{g['count']} 筆"), str(g["mean"]), str(g["max"]), str(g["min"])])
        story.append(_table(rows, st, [W * x for x in (0.3, 0.17, 0.19, 0.17, 0.17)]))

    if s["medications"]:
        story.append(Paragraph("用藥（使用者的說法） <font size='9' color='#5F686B'>Medication, as reported</font>", st["h2"]))
        rows = [["藥物", "說有吃", "說沒吃 / 忘了吃"]]
        for m in s["medications"]:
            rows.append([f"<b>{escape(m['name'])}</b>", _link(m["taken_group"], f"{m['taken']} 次"),
                         _link(m["missed_group"], f"{m['missed']} 次")])
        story.append(_table(rows, st, [W * 0.4, W * 0.3, W * 0.3]))

    if s["triggers"]:
        story.append(Paragraph("使用者提到的可能相關因素 <font size='9' color='#5F686B'>Possible factors mentioned</font>", st["h2"]))
        story.append(Paragraph("、".join(f'{escape(t["name"])}（{_link(t["group"], str(t["count"]) + " 次")}）'
                                        for t in s["triggers"]), st["cell"]))

    story += [PageBreak(), Paragraph("附錄：原話紀錄 <font size='11' color='#5F686B'>Source sentences</font>", st["h1"])]
    for g in s["groups"]:
        block = [Paragraph(f'<a name="{g["key"]}"/>{escape(g["title"])}', st["h2"])]
        for i in g["ids"]:
            e = s["by_id"][i]
            tags = " · ".join(entry_tags(e["fields"]))
            block.append(Paragraph(f'<font color="#5F686B">{fmt_ts(e["ts"])} #{i}</font>　「{escape(source_text(e))}」'
                                   f'<br/><font size="8.5" color="#5F686B">{escape(tags)}</font>', st["cell"]))
            block.append(Spacer(1, 3))
        block.append(Paragraph(f'<a href="#top" color="{TEAL}">↑ 回到摘要</a>', st["small"]))
        story.append(KeepTogether(block) if len(g["ids"]) <= 8 else block[0])
        if len(g["ids"]) > 8:
            story.extend(block[1:])

    doc.build(story, onFirstPage=_footer(font), onLaterPages=_footer(font))
    return Path(path)
