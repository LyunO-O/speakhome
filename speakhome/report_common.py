"""Shared wording for the HTML and PDF visit summaries."""
from __future__ import annotations

from datetime import datetime

WEEKDAYS = "一二三四五六日"
DISCLAIMER = ("本摘要只整理使用者自己說的內容，不構成醫療診斷或建議。"
              "This summary only organises what the patient said. It is not a diagnosis or medical advice.")


def fmt_date(d) -> str:
    return f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）"


def fmt_ts(ts: datetime) -> str:
    return f"{fmt_date(ts)} {ts:%H:%M}"


def fmt_minutes(m) -> str:
    if m is None:
        return "—"
    if m >= 24 * 60:
        return "一整天"
    if m >= 60:
        return f"{m / 60:g} 小時"
    return f"{m:g} 分鐘"


def entry_tags(fields: dict) -> list[str]:
    """Short labels shown beside each source sentence."""
    tags = []
    if fields.get("symptoms"):
        tags.append("、".join(fields["symptoms"]))
    if fields.get("severity") is not None:
        tags.append(f"{fields['severity']} 分")
    if fields.get("duration_min"):
        tags.append(fmt_minutes(fields["duration_min"]))
    if bp := fields.get("bp"):
        tags.append(f"血壓 {bp['sys']}" + (f"/{bp['dia']}" if bp.get("dia") else ""))
    if fields.get("glucose"):
        tags.append(f"血糖 {fields['glucose']}")
    for m in fields.get("medications", []):
        tags.append(("有吃" if m["taken"] else "沒吃") + m["name"])
    for f in fields.get("red_flags", []):
        tags.append(f"警示：{f}")
    return tags


def source_text(entry: dict) -> str:
    """The patient's sentence, plus the follow-up answer if there was one."""
    text = entry["text"]
    fu = entry.get("follow_up")
    if fu and fu.get("answer"):
        text += f"（追問：{fu['question']} 回答：{fu['answer']}）"
    return text
