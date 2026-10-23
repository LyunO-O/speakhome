"""Optional local language model for field extraction (Ollama on this machine).

The model only fills fields the rules left empty, and every value it returns is
checked against the patient's own sentence: a number that was never said, or a
symptom whose words are not in the sentence, is thrown away. Nothing is sent
off the device; the default endpoint is localhost.

Stage II replaces this HTTP call with the same prompt running on the UGen300.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .cnnum import numbers_in, normalize
from .extract import SYMPTOMS

DEFAULT_URL = os.environ.get("SPEAKHOME_LLM_URL", "http://127.0.0.1:11434/api/generate")

PROMPT = """你是記錄助手，只整理使用者自己說的話，不做診斷、不給建議。
從下面這句話抽出欄位，只輸出 JSON，沒提到的欄位填 null 或空陣列：
{{"symptoms": [症狀名稱], "severity": 0到10的整數或null, "duration_min": 分鐘整數或null,
 "bp_sys": 收縮壓或null, "bp_dia": 舒張壓或null, "glucose": 血糖或null,
 "medications": [{{"name": 藥名, "taken": true或false}}]}}
可用的症狀名稱：{names}
句子：「{text}」"""


def _grounded_symptom(name: str, text: str) -> bool:
    return name in SYMPTOMS and all(ch in text for ch in name)


def llm_extract(text: str, model: str, url: str = DEFAULT_URL, timeout: float = 60) -> dict:
    body = json.dumps({
        "model": model,
        "prompt": PROMPT.format(names="、".join(SYMPTOMS), text=text),
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read())["response"]
    return json.loads(raw)


def merge_llm(fields: dict, text: str, model: str) -> tuple[dict, list[str]]:
    """Fill empty fields from the model. Returns (fields, list of rejected values)."""
    t = normalize(text)
    said = numbers_in(t)
    rejected: list[str] = []
    try:
        out = llm_extract(t, model)
    except Exception as exc:  # model not running, bad JSON, timeout
        return fields, [f"LLM unavailable: {exc}"]

    def number_ok(key, value, lo, hi):
        if value is None:
            return False
        try:
            value = float(value)
        except (TypeError, ValueError):
            rejected.append(f"{key}={value!r} (not a number)")
            return False
        if not lo <= value <= hi or value not in said:
            rejected.append(f"{key}={value:g} (not said in the sentence)")
            return False
        return True

    for name in out.get("symptoms") or []:
        if _grounded_symptom(name, t):
            if name not in fields["symptoms"]:
                fields["symptoms"].append(name)
        else:
            rejected.append(f"symptom={name}")
    if fields["severity"] is None and number_ok("severity", out.get("severity"), 0, 10):
        fields["severity"] = int(out["severity"])
    if fields["duration_min"] is None and out.get("duration_min") is not None:
        # Minutes are often derived ("半小時" -> 30), so only accept when a
        # duration phrase exists in the sentence.
        if fields["duration_text"] or any(u in t for u in ("分鐘", "小時", "鐘頭")):
            fields["duration_min"] = int(out["duration_min"])
        else:
            rejected.append(f"duration_min={out['duration_min']}")
    if fields["bp"] is None and number_ok("bp_sys", out.get("bp_sys"), 70, 260):
        dia = out.get("bp_dia")
        fields["bp"] = {"sys": int(out["bp_sys"]),
                        "dia": int(dia) if number_ok("bp_dia", dia, 40, 160) else None}
    if fields["glucose"] is None and number_ok("glucose", out.get("glucose"), 40, 600):
        fields["glucose"] = int(out["glucose"])
    if not fields["medications"]:
        for med in out.get("medications") or []:
            name = str(med.get("name", ""))
            if name and name.rstrip("藥") in t:
                fields["medications"].append({"name": name, "taken": bool(med.get("taken", True))})
            elif name:
                rejected.append(f"medication={name}")
    fields["source"] = f"rules+llm:{model}"
    return fields, rejected
