"""Visit summary as one self-contained HTML page (for the caregiver's browser).
Every number is a link to the sentences it came from."""
from __future__ import annotations

from html import escape

from .report_common import (DISCLAIMER, entry_tags, fmt_date, fmt_minutes, fmt_ts,
                            source_text)

CSS = """
:root{--ink:#1F2A2E;--body:#3A4548;--muted:#5F686B;--paper:#F6F2EA;--card:#FFFDF8;
--line:#DED6C6;--accent:#A8432F;--teal:#2F6F6A;--hl:#F3DCD3}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--body);
font:17px/1.6 "Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:30px;color:var(--ink);margin:0 0 4px}h2{font-size:21px;color:var(--ink);
margin:36px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line)}
.sub{color:var(--muted);margin:0}.en{color:var(--muted);font-size:14px;font-weight:400}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi b{display:block;font-size:26px;color:var(--ink)}.kpi span{color:var(--muted);font-size:14px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:14px;color:var(--muted);font-weight:600;background:#EFE8DB}
tr:last-child td{border-bottom:none}
a.n{color:var(--teal);font-weight:700;text-decoration:none;border-bottom:2px solid #9CC3BF}
a.n:hover{background:#E3F0EE}
.flag{background:var(--hl);border-left:4px solid var(--accent);padding:12px 16px;border-radius:8px}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.group{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:14px 0;scroll-margin-top:16px}
.group:target{outline:3px solid var(--teal)}
.group h3{margin:0 0 8px;font-size:17px;color:var(--ink)}
.group ol{margin:0;padding-left:0;list-style:none}.group li{padding:8px 0;border-top:1px dashed var(--line)}
.group li:first-child{border-top:none}.when{color:var(--muted);font-size:14px}
.tag{display:inline-block;font-size:13px;background:#EFE8DB;border-radius:999px;padding:1px 9px;margin:2px 4px 0 0}
.back{font-size:14px;color:var(--teal)}footer{margin-top:40px;color:var(--muted);font-size:14px}
@media print{a.n{border:none;color:var(--ink)}.group{break-inside:avoid}}
"""


def _link(group: str | None, label: str) -> str:
    if not group:
        return escape(label)
    return f'<a class="n" href="#{group}">{escape(label)}</a>'


def _chart(daily) -> str:
    w, h, pad_l, pad_b = 820, 180, 28, 26
    n = len(daily)
    bw = (w - pad_l) / max(n, 1)
    bars = []
    for i, (day, v) in enumerate(daily):
        x = pad_l + i * bw
        if v is not None:
            bh = (h - pad_b - 10) * v / 10
            bars.append(f'<rect x="{x + 3:.1f}" y="{h - pad_b - bh:.1f}" width="{bw - 6:.1f}" height="{bh:.1f}" rx="3" fill="#A8432F"><title>{fmt_date(day)} 最高 {v} 分</title></rect>')
        else:
            bars.append(f'<rect x="{x + 3:.1f}" y="{h - pad_b - 2}" width="{bw - 6:.1f}" height="2" fill="#C9BFAE"/>')
        if n <= 31 and (i % max(1, n // 10) == 0 or i == n - 1):
            bars.append(f'<text x="{x + bw / 2:.1f}" y="{h - 8}" font-size="11" text-anchor="middle" fill="#5F686B">{day.month}/{day.day}</text>')
    grid = "".join(
        f'<line x1="{pad_l}" x2="{w}" y1="{h - pad_b - (h - pad_b - 10) * g / 10:.1f}" y2="{h - pad_b - (h - pad_b - 10) * g / 10:.1f}" stroke="#E6DFD2"/>'
        f'<text x="{pad_l - 6}" y="{h - pad_b - (h - pad_b - 10) * g / 10 + 4:.1f}" font-size="11" text-anchor="end" fill="#5F686B">{g}</text>'
        for g in (0, 5, 10))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="每日最高嚴重度">'
            f'{grid}{"".join(bars)}</svg>')


def render_html(s: dict, patient: str = "[姓名]") -> str:
    out = [f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>回診摘要 · {escape(patient)}</title><style>{CSS}</style></head><body><main id="top">']
    out.append(f'<h1>回診摘要 <span class="en">Visit summary</span></h1>'
               f'<p class="sub">{escape(patient)} · {fmt_date(s["start"])} – {fmt_date(s["end"])}，共 {s["days_total"]} 天</p>')
    out.append('<div class="kpis">'
               f'<div class="kpi"><b>{_link(s["logged_group"], str(s["entry_count"]))}</b><span>筆已確認紀錄 · confirmed entries</span></div>'
               f'<div class="kpi"><b>{s["days_logged"]} / {s["days_total"]}</b><span>天有紀錄 · days logged</span></div>'
               f'<div class="kpi"><b>{_link(s["well_group"], str(s["well_days"]))}</b><span>天自述身體還好 · good days</span></div></div>')

    if s["red_flags"]:
        items = "、".join(f'{escape(f["name"])}（{_link(f["group"], str(f["count"]) + " 次")}）' for f in s["red_flags"])
        out.append(f'<h2>需要注意的字詞 <span class="en">Keyword alerts</span></h2>'
                   f'<p class="flag">紀錄中出現：{items}。當時站台已提示聯絡家人或撥打 119。此為字詞比對，不是醫療判斷。</p>')

    out.append('<h2>症狀 <span class="en">Symptoms</span></h2>')
    if s["symptoms"]:
        out.append('<table><tr><th>症狀</th><th>次數</th><th>嚴重度（中位數 / 最高）</th><th>常見時段</th><th>持續時間（中位數）</th><th>前後半段比較</th></tr>')
        for sym in s["symptoms"]:
            sev = "—" if sym["median"] is None else f'{sym["median"]:g} / {sym["max"]}'
            tr = sym["trend"]
            trend = "資料不足" if not tr else f'{tr["label"]}（{tr["first"]:g} → {tr["second"]:g}）'
            out.append(f'<tr><td><b>{escape(sym["name"])}</b></td><td>{_link(sym["group"], str(sym["count"]) + " 次")}'
                       f'<br><span class="when">{sym["days"]} 天</span></td><td>{sev}</td>'
                       f'<td>{escape(sym["common_time"] or "—")}</td><td>{fmt_minutes(sym["median_duration"])}</td><td>{trend}</td></tr>')
        out.append('</table>')
        out.append(f'<h2>每日最高嚴重度 <span class="en">Highest severity per day (0–10)</span></h2>'
                   f'<div class="chart">{_chart(s["daily"])}</div>')
    else:
        out.append('<p>這段期間沒有提到症狀。</p>')

    if s["bp"] or s["glucose"]:
        out.append('<h2>量測 <span class="en">Measurements</span></h2><table><tr><th>項目</th><th>筆數</th><th>平均</th><th>最高</th><th>最低</th></tr>')
        if bp := s["bp"]:
            avg = f'{bp["mean_sys"]}' + (f' / {bp["mean_dia"]}' if bp["mean_dia"] else "")
            out.append(f'<tr><td><b>血壓</b>（收縮 / 舒張）</td><td>{_link(bp["group"], str(bp["count"]) + " 筆")}</td>'
                       f'<td>{avg}</td><td>{_link(bp["max_group"], str(bp["max_sys"]))}</td><td>{bp["min_sys"]}</td></tr>')
        if g := s["glucose"]:
            out.append(f'<tr><td><b>血糖</b></td><td>{_link(g["group"], str(g["count"]) + " 筆")}</td>'
                       f'<td>{g["mean"]}</td><td>{g["max"]}</td><td>{g["min"]}</td></tr>')
        out.append('</table>')

    if s["medications"]:
        out.append('<h2>用藥 <span class="en">Medication, as reported</span></h2><table><tr><th>藥物（使用者的說法）</th><th>說有吃</th><th>說沒吃 / 忘了吃</th></tr>')
        for m in s["medications"]:
            out.append(f'<tr><td><b>{escape(m["name"])}</b></td><td>{_link(m["taken_group"], str(m["taken"]) + " 次")}</td>'
                       f'<td>{_link(m["missed_group"], str(m["missed"]) + " 次")}</td></tr>')
        out.append('</table>')

    if s["triggers"]:
        items = "".join(f'<tr><td>{escape(t["name"])}</td><td>{_link(t["group"], str(t["count"]) + " 次")}</td></tr>' for t in s["triggers"])
        out.append(f'<h2>使用者提到的可能相關因素 <span class="en">Possible factors the patient mentioned</span></h2>'
                   f'<table><tr><th>因素</th><th>提到次數</th></tr>{items}</table>')

    out.append('<h2>原話紀錄 <span class="en">Source sentences</span></h2>'
               '<p class="sub">點上方任一數字，會跳到它的來源句子。Click any number above to see the sentences behind it.</p>')
    for g in s["groups"]:
        out.append(f'<section class="group" id="{g["key"]}"><h3>{escape(g["title"])}</h3><ol>')
        for i in g["ids"]:
            e = s["by_id"][i]
            tags = "".join(f'<span class="tag">{escape(t)}</span>' for t in entry_tags(e["fields"]))
            out.append(f'<li><span class="when">{fmt_ts(e["ts"])} · #{i}</span><br>「{escape(source_text(e))}」<br>{tags}</li>')
        out.append('</ol><a class="back" href="#top">↑ 回到摘要</a></section>')

    out.append(f'<footer>{escape(DISCLAIMER)}<br>由 Speak Home 在本機產生，未上傳任何資料。</footer></main></body></html>')
    return "".join(out)
