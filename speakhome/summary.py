"""Turn confirmed entries into visit-summary statistics.

Every statistic carries the ids of the entries it was computed from, so the
reports can link each number back to the patient's own sentences. The summary
counts and describes; it never interprets.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, median


class Groups:
    """Source-sentence groups that numbers in the report link to."""

    def __init__(self):
        self.items: list[dict] = []

    def add(self, title: str, ids: list[int]) -> str:
        key = f"g{len(self.items) + 1}"
        self.items.append({"key": key, "title": title, "ids": sorted(set(ids))})
        return key


def _trend(points: list[tuple[datetime, int]], start: datetime, end: datetime):
    """Mean severity in the first vs second half of the period."""
    mid = start + (end - start) / 2
    first = [s for t, s in points if t < mid]
    second = [s for t, s in points if t >= mid]
    if len(first) < 2 or len(second) < 2:
        return None
    a, b = mean(first), mean(second)
    if b - a >= 1:
        label = "後半段較高"
    elif a - b >= 1:
        label = "後半段較低"
    else:
        label = "前後相近"
    return {"label": label, "first": round(a, 1), "second": round(b, 1)}


def build_summary(entries: list[dict], start: datetime, end: datetime) -> dict:
    groups = Groups()
    by_id = {e["id"]: e for e in entries}
    days_total = (end.date() - start.date()).days + 1
    days_logged = len({e["ts"].date() for e in entries})

    # Symptoms
    sym: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        for name in e["fields"].get("symptoms", []):
            sym[name].append(e)
    symptoms = []
    for name, es in sorted(sym.items(), key=lambda kv: -len(kv[1])):
        sev = [(e["ts"], e["fields"]["severity"]) for e in es if e["fields"].get("severity") is not None]
        durations = [e["fields"]["duration_min"] for e in es if e["fields"].get("duration_min")]
        times = defaultdict(int)
        for e in es:
            if tod := e["fields"].get("time_of_day"):
                times[tod] += 1
        symptoms.append({
            "name": name,
            "count": len(es),
            "days": len({e["ts"].date() for e in es}),
            "median": median([s for _, s in sev]) if sev else None,
            "max": max(s for _, s in sev) if sev else None,
            "median_duration": median(durations) if durations else None,
            "common_time": max(times, key=times.get) if times else None,
            "trend": _trend(sev, start, end),
            "group": groups.add(f"{name}（{len(es)} 次）", [e["id"] for e in es]),
        })

    # Measurements
    def readings(key):
        return [e for e in entries if e["fields"].get(key)]

    bp_es = readings("bp")
    bp = None
    if bp_es:
        sys_v = [e["fields"]["bp"]["sys"] for e in bp_es]
        dia_v = [e["fields"]["bp"]["dia"] for e in bp_es if e["fields"]["bp"].get("dia")]
        hi = max(bp_es, key=lambda e: e["fields"]["bp"]["sys"])
        lo = min(bp_es, key=lambda e: e["fields"]["bp"]["sys"])
        bp = {
            "count": len(bp_es),
            "mean_sys": round(mean(sys_v)),
            "mean_dia": round(mean(dia_v)) if dia_v else None,
            "max_sys": hi["fields"]["bp"]["sys"], "min_sys": lo["fields"]["bp"]["sys"],
            "series": [(e["ts"], e["fields"]["bp"]["sys"], e["fields"]["bp"].get("dia")) for e in bp_es],
            "group": groups.add(f"血壓（{len(bp_es)} 筆）", [e["id"] for e in bp_es]),
            "max_group": groups.add(f"血壓最高 {hi['fields']['bp']['sys']}", [hi["id"]]),
        }
    glu_es = readings("glucose")
    glucose = None
    if glu_es:
        vals = [e["fields"]["glucose"] for e in glu_es]
        glucose = {"count": len(vals), "mean": round(mean(vals)), "max": max(vals), "min": min(vals),
                   "group": groups.add(f"血糖（{len(vals)} 筆）", [e["id"] for e in glu_es])}

    # Medication
    meds: dict[str, dict[str, list[int]]] = defaultdict(lambda: {"taken": [], "missed": []})
    for e in entries:
        for m in e["fields"].get("medications", []):
            meds[m["name"]]["taken" if m["taken"] else "missed"].append(e["id"])
    medications = []
    for name, d in meds.items():
        medications.append({
            "name": name,
            "taken": len(d["taken"]),
            "missed": len(d["missed"]),
            "taken_group": groups.add(f"{name}：有吃", d["taken"]) if d["taken"] else None,
            "missed_group": groups.add(f"{name}：沒吃", d["missed"]) if d["missed"] else None,
        })

    # Possible triggers the patient mentioned
    trig: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        for t in e["fields"].get("triggers", []):
            trig[t].append(e["id"])
    triggers = [{"name": n, "count": len(ids), "group": groups.add(f"提到「{n}」", ids)}
                for n, ids in sorted(trig.items(), key=lambda kv: -len(kv[1]))]

    flags: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        for f in e["fields"].get("red_flags", []):
            flags[f].append(e["id"])
    red_flags = [{"name": n, "count": len(ids), "group": groups.add(f"警示詞「{n}」", ids)}
                 for n, ids in flags.items()]

    well = [e["id"] for e in entries if e["fields"].get("well")]

    # Daily highest severity, for the chart
    daily = []
    day = start.date()
    while day <= end.date():
        sevs = [e["fields"]["severity"] for e in entries
                if e["ts"].date() == day and e["fields"].get("severity") is not None]
        daily.append((day, max(sevs) if sevs else None))
        day += timedelta(days=1)

    return {
        "start": start, "end": end,
        "days_total": days_total, "days_logged": days_logged, "entry_count": len(entries),
        "logged_group": groups.add(f"全部紀錄（{len(entries)} 筆）", list(by_id)),
        "symptoms": symptoms, "bp": bp, "glucose": glucose,
        "medications": medications, "triggers": triggers, "red_flags": red_flags,
        "well_days": len({by_id[i]["ts"].date() for i in well}),
        "well_group": groups.add("自述身體還好", well) if well else None,
        "daily": daily, "groups": groups.items, "by_id": by_id,
    }
