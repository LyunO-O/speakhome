"""The conversation around one entry: one follow-up question, the read-back,
confirmation, and the fixed safety prompt. The station never gives advice."""
from __future__ import annotations

import re

from .cnnum import NUM, cn2num, normalize
from .extract import extract

SAFETY_MESSAGE = "如果現在還不舒服，請馬上聯絡家人，或撥打 119。"

QUESTIONS = {
    "severity": "大概幾分？零分是完全不會，十分是最嚴重。",
    "duration": "大概持續多久？",
    "what": "今天身體有哪裡不舒服，或是有量血壓、吃藥嗎？",
}

YES = re.compile(r"^\s*(對|是|沒錯|好|嗯|可以|正確|y|yes|ok)", re.I)
NO = re.compile(r"(不對|不是|錯|重來|n$|no)", re.I)


def follow_up_needed(fields: dict) -> str | None:
    """At most one question per entry, so a check-in never feels like a form."""
    if fields["red_flags"]:
        return None  # do not quiz someone who may be unwell
    if fields["symptoms"]:
        if fields["severity"] is None:
            return "severity"
        if fields["duration_text"] is None:
            return "duration"
        return None
    if not (fields["bp"] or fields["glucose"] or fields["medications"] or fields["well"]):
        return "what"
    return None


def merge_answer(fields: dict, slot: str, answer: str) -> dict:
    """Fill the asked slot from the answer; anything else said is merged too."""
    extra = extract(answer)
    t = normalize(answer)
    if slot == "severity":
        value = extra["severity"]
        if value is None:  # a bare "五" or "5" answers the question asked
            m = re.search(NUM, t)
            n = cn2num(m.group(0)) if m else None
            value = int(n) if n is not None and 0 <= n <= 10 else None
        if value is not None:
            fields["severity"] = value
            fields["evidence"]["severity"] = answer.strip()
    elif slot == "duration":
        if extra["duration_text"]:
            fields["duration_min"] = extra["duration_min"]
            fields["duration_text"] = extra["duration_text"]
            fields["evidence"]["duration"] = extra["duration_text"]
    # Merge any other new information from the answer.
    for key in ("symptoms", "triggers", "red_flags"):
        for item in extra[key]:
            if item not in fields[key]:
                fields[key].append(item)
                fields["evidence"].setdefault(key, {})[item] = extra["evidence"].get(key, {}).get(item, "")
    for key in ("bp", "glucose", "time_of_day"):
        if fields.get(key) is None and extra.get(key) is not None:
            fields[key] = extra[key]
    if not fields["medications"] and extra["medications"]:
        fields["medications"] = extra["medications"]
    fields["well"] = fields["well"] or extra["well"]
    return fields


def _fmt_duration(fields: dict) -> str | None:
    minutes = fields["duration_min"]
    if minutes is None:
        return fields["duration_text"]
    if minutes >= 24 * 60:
        return "一整天"
    if minutes >= 60:
        hours = minutes / 60
        return f"{hours:g} 小時"
    return f"{minutes} 分鐘"


def read_back(fields: dict) -> str:
    """The sentence the station speaks so the patient can correct it."""
    parts = []
    day = {0: "", -1: "昨天", -2: "前天"}.get(fields["day_offset"], "")
    when = day + (fields["time_of_day"] or "")
    if fields["symptoms"]:
        parts.append(when + "、".join(fields["symptoms"]))
        if fields["severity"] is not None:
            parts.append(f"{fields['severity']} 分")
        if d := _fmt_duration(fields):
            parts.append(f"持續 {d}")
    elif fields["well"]:
        parts.append(when + "身體還好")
    if fields["red_flags"]:
        parts.append("提到" + "、".join(fields["red_flags"]))
    if bp := fields["bp"]:
        parts.append(f"血壓 {bp['sys']}" + (f"/{bp['dia']}" if bp["dia"] else ""))
    if fields["glucose"]:
        parts.append(f"血糖 {fields['glucose']}")
    for med in fields["medications"]:
        parts.append(("有吃" if med["taken"] else "沒吃") + med["name"])
    if fields["triggers"]:
        parts.append("可能和" + "、".join(fields["triggers"]) + "有關")
    if not parts:
        return "我沒有聽清楚，可以再說一次嗎？"
    return "好，已記下：" + "，".join(parts) + "。這樣對嗎？"


def parse_confirmation(answer: str) -> bool | None:
    if NO.search(answer):
        return False
    if YES.search(answer):
        return True
    return None
