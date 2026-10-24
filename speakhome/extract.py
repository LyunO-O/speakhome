"""Rule-based field extraction from one spoken Mandarin entry.

This is the always-available path: it needs no model, runs in milliseconds and
only ever records values that literally appear in the sentence. The optional
local language model (llm.py) can fill gaps, but its output is checked against
the same sentence before it is accepted.
"""
from __future__ import annotations

import re

from .cnnum import NOT_NUM, NUM, cn2num, normalize

# --- Lexicons -------------------------------------------------------------
# Canonical symptom name -> regex patterns (Traditional Chinese, colloquial).
SYMPTOMS: dict[str, list[str]] = {
    "頭暈": [r"頭.{0,3}暈", r"頭昏", r"暈眩", r"天旋地轉", r"暈暈的"],
    "頭痛": [r"頭.{0,3}[痛疼]", r"偏頭痛"],
    "胸悶": [r"胸.{0,2}悶"],
    "心悸": [r"心悸", r"心跳.{0,2}(很快|好快|亂|不規則)", r"心臟.{0,3}(亂跳|跳很快)"],
    "喘": [r"喘不過氣", r"會喘", r"很喘", r"好喘"],
    "失眠": [r"失眠", r"睡不著"],
    "腰痛": [r"腰.{0,3}[痛酸]"],
    "膝蓋痛": [r"膝蓋.{0,3}([痛酸]|不舒服)"],
    "關節痛": [r"關節.{0,3}痛"],
    "胃痛": [r"胃.{0,3}([痛]|不舒服)", r"肚子.{0,2}痛"],
    "噁心": [r"噁心", r"想吐", r"吐了"],
    "咳嗽": [r"咳嗽", r"一直咳"],
    "疲倦": [r"很累", r"好累", r"沒力氣", r"疲倦", r"全身無力"],
    "水腫": [r"腳.{0,2}腫", r"水腫"],
    "便秘": [r"便秘", r"沒(有)?大便"],
}

TRIGGERS: dict[str, list[str]] = {
    "睡眠不足": [r"沒睡好", r"睡不好", r"睡得不好", r"太晚睡"],
    "天氣變化": [r"變天", r"天氣.{0,2}(變|冷|熱|悶)", r"寒流"],
    "飲食偏鹹": [r"太鹹", r"吃.{0,2}鹹"],
    "情緒壓力": [r"壓力", r"緊張", r"生氣", r"煩惱"],
    "姿勢改變": [r"(站|起身|起床).{0,3}(太快|突然)", r"突然站起來"],
    "空腹": [r"沒吃早餐", r"空腹", r"沒吃飯"],
    "活動量大": [r"走太多", r"爬樓梯", r"走很久"],
}

# Fixed keyword rule. A match never produces medical advice, only the
# "call your family or 119" prompt in dialogue.py.
RED_FLAGS: dict[str, list[str]] = {
    "胸痛": [r"胸口?.{0,2}痛"],
    "說話不清": [r"(講話|說話|口齒).{0,2}不清", r"大舌頭"],
    "單側無力或麻木": [r"(半邊|一邊|單邊).{0,4}(無力|麻|沒力)"],
    "臉或嘴歪斜": [r"(臉|嘴).{0,3}歪"],
    "昏倒": [r"昏倒", r"暈倒", r"昏過去"],
    "呼吸困難": [r"呼吸困難", r"不能呼吸"],
}

WELL_PATTERNS = [r"(今天|身體).{0,4}(很好|不錯|都好|還好|沒事)", r"沒有(哪裡)?不舒服", r"都沒有不舒服"]
DELETE_PATTERNS = [r"刪(掉|除).{0,4}(剛剛|剛才|上一)", r"(剛剛|剛才)那筆不要"]

TIMES = ["清晨", "凌晨", "早上", "上午", "中午", "下午", "傍晚", "晚上", "半夜", "睡前", "剛剛", "剛才"]
NEGATION = re.compile(r"(沒有|沒|不|無)$")

HEART_RATE_PATTERNS = [
    rf"(?:每分鐘|一分鐘)\s*(?:大概|差不多|大約|約)?\s*(?:跳了?)?\s*({NUM})\s*多?\s*下",
    rf"跳了?\s*({NUM})\s*多?\s*下",
    rf"(?:心跳|脈搏|心率)數?{NOT_NUM}{{0,6}}?({NUM})\s*多?\s*下?",
]
HR_UNMEASURED = re.compile(r"(沒有?|忘了|忘記)量")


def _heart_rate(text: str):
    for pat in HEART_RATE_PATTERNS:
        for m in re.finditer(pat, text):
            value = cn2num(m.group(1))
            if value is not None and 30 <= value <= 250:
                return int(value), m.group(0).strip(), m.span()
    return None, None, None


def _negated(text: str, start: int, matched: str, pattern: str) -> bool:
    # "頭不暈", "頭沒有暈" -- unless 不 is part of the phrase itself ("睡不著").
    if ("不" not in pattern and "沒" not in pattern) and ("不" in matched[1:] or "沒" in matched[1:]):
        return True
    return bool(NEGATION.search(text[max(0, start - 2):start]))


def _find_terms(text: str, lexicon: dict[str, list[str]], allow_negation=False):
    found, evidence = [], {}
    for name, patterns in lexicon.items():
        for pat in patterns:
            m = re.search(pat, text)
            if m and (allow_negation or not _negated(text, m.start(), m.group(0), pat)):
                found.append(name)
                evidence[name] = m.group(0)
                break
    return found, evidence


def _severity(text: str):
    # "大概五分", "痛到七分", "6分", "6/10" -- but not "十分鐘" (minutes)
    # and not a bare "十分" (which means "very" in Mandarin).
    for m in re.finditer(rf"(大概|差不多|大約|約|痛到|暈到|有)?\s*({NUM})\s*分(?!鐘)", text):
        prefix, tok = m.group(1), m.group(2)
        if tok == "十" and not prefix:
            continue
        value = cn2num(tok)
        if value is not None and 0 <= value <= 10:
            return int(value), m.group(0).strip()
    m = re.search(r"([0-9]{1,2})\s*/\s*10", text)
    if m and 0 <= int(m.group(1)) <= 10:
        return int(m.group(1)), m.group(0)
    return None, None


def _duration(text: str):
    if m := re.search(r"(一)?整天", text):
        return 24 * 60, m.group(0)
    if m := re.search(rf"({NUM}|半)\s*個?\s*(多)?\s*(半)?\s*(小時|鐘頭|分鐘)", text):
        tok, _, half, unit = m.groups()
        value = 0.5 if tok == "半" else cn2num(tok)
        if value is None:
            return None, None
        if half:
            value += 0.5
        minutes = value * 60 if unit in ("小時", "鐘頭") else value
        return int(minutes), m.group(0)
    if m := re.search(r"(一下子|一下下|幾分鐘|一會兒)", text):
        return None, m.group(0)  # answered, but no number to count
    return None, None


def _blood_pressure(text: str):
    sys_v = dia_v = None
    evidence = None
    if m := re.search(rf"高壓{NOT_NUM}{{0,3}}({NUM})", text):
        sys_v, evidence = cn2num(m.group(1)), m.group(0)
    if m := re.search(rf"低壓{NOT_NUM}{{0,3}}({NUM})", text):
        dia_v = cn2num(m.group(1))
        evidence = (evidence + "…" if evidence else "") + m.group(0)
    if sys_v is None:
        pat = rf"血壓{NOT_NUM}{{0,6}}?({NUM})(?:\s*(?:/|跟|和|對|，|,)\s*({NUM}))?"
        if m := re.search(pat, text):
            sys_v = cn2num(m.group(1))
            dia_v = cn2num(m.group(2)) if m.group(2) else dia_v
            evidence = m.group(0)
    if sys_v is None or not 70 <= sys_v <= 260:
        return None, None
    if dia_v is not None and not 40 <= dia_v <= 160:
        dia_v = None
    return {"sys": int(sys_v), "dia": int(dia_v) if dia_v else None}, evidence


def _glucose(text: str):
    if m := re.search(rf"血糖{NOT_NUM}{{0,6}}?({NUM})", text):
        value = cn2num(m.group(1))
        if value is not None and 40 <= value <= 600:
            return int(value), m.group(0)
    return None, None


QUANTITY = re.compile(rf"^({NUM})?\s*(顆|粒|包|錠|次|種)?")


def _clean_med_name(raw: str) -> str:
    name = raw.strip().lstrip("了的過")
    name = QUANTITY.sub("", name, count=1).lstrip("的")
    if "血壓" in name:
        return "降血壓藥"
    if "止痛" in name:
        return "止痛藥"
    if "血糖" in name or "糖尿病" in name:
        return "降血糖藥"
    if "安眠" in name or "睡覺" in name:
        return "安眠藥"
    return name or "藥"


def _medications(text: str):
    meds, evidence = [], []
    for m in re.finditer(r"(沒有吃|沒吃|忘了吃|忘記吃|有吃|吃了|吃過|已經吃|有服用)(.{0,8}?藥)", text):
        verb, obj = m.groups()
        taken = not verb.startswith(("沒", "忘"))
        meds.append({"name": _clean_med_name(obj), "taken": taken})
        evidence.append(m.group(0))
    if not meds:  # object first: "降血壓的藥忘了吃", "早上的藥有吃"
        for m in re.finditer(r"([^，,。；\s]{1,8}?藥)(沒有吃|沒吃|忘了吃|忘記吃|有吃|吃了)", text):
            obj, verb = m.groups()
            meds.append({"name": _clean_med_name(obj), "taken": not verb.startswith(("沒", "忘"))})
            evidence.append(m.group(0))
    if not meds and (m := re.search(r"吃藥了|吃過藥", text)):
        meds.append({"name": "藥", "taken": True})
        evidence.append(m.group(0))
    return meds, evidence


def _day_offset(text: str) -> int:
    if "前天" in text:
        return -2
    if re.match(r"\s*(昨天|昨晚)", text) and "今天" not in text:
        return -1
    return 0


def is_delete_command(text: str) -> bool:
    return any(re.search(p, normalize(text)) for p in DELETE_PATTERNS)


def extract(text: str) -> dict:
    """Return the structured fields for one entry, plus the evidence spans."""
    t = normalize(text)
    symptoms, sym_ev = _find_terms(t, SYMPTOMS)
    triggers, trig_ev = _find_terms(t, TRIGGERS, allow_negation=True)
    red_flags, red_ev = _find_terms(t, RED_FLAGS)
    # A red-flag phrase like 胸口痛 should not also count as an ordinary symptom.
    heart_rate, hr_ev, hr_span = _heart_rate(t)
    t_rest = t if not hr_span else t[:hr_span[0]] + "，" * (hr_span[1] - hr_span[0]) + t[hr_span[1]:]
    severity, sev_ev = _severity(t_rest)
    duration_min, dur_ev = _duration(t_rest)
    bp, bp_ev = _blood_pressure(t)
    glucose, glu_ev = _glucose(t)
    meds, med_ev = _medications(t)
    # Earliest time word in the sentence, ignoring ones that name a dose ("早上的藥").
    hits = [(m.start(), w) for w in TIMES for m in re.finditer(w, t)
            if not re.match(r"的?[^，,。]{0,4}藥", t[m.end():])]
    time_of_day = min(hits)[1] if hits else None

    evidence = {"symptoms": sym_ev, "triggers": trig_ev, "red_flags": red_ev}
    for key, ev in (("severity", sev_ev), ("duration", dur_ev), ("bp", bp_ev),
                    ("glucose", glu_ev)):
        if ev:
            evidence[key] = ev
    if med_ev:
        evidence["medications"] = med_ev

    return {
        "symptoms": symptoms,
        "severity": severity,
        "time_of_day": time_of_day,
        "day_offset": _day_offset(t),
        "duration_min": duration_min,
        "duration_text": dur_ev,
        "bp": bp,
        "glucose": glucose,
        "heart_rate": heart_rate,
        "heart_rate_unmeasured": bool(heart_rate is None and "心跳" in t and HR_UNMEASURED.search(t)),
        "medications": meds,
        "triggers": triggers,
        "red_flags": red_flags,
        "well": bool(not symptoms and not red_flags and any(re.search(p, t) for p in WELL_PATTERNS)),
        "evidence": evidence,
        "source": "rules",
    }


def is_empty(fields: dict) -> bool:
    return not (fields["symptoms"] or fields["bp"] or fields["glucose"] or fields.get("heart_rate") or fields["medications"]
                or fields["red_flags"] or fields["well"])
