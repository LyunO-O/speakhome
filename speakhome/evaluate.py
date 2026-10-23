"""Field-extraction accuracy on a labelled set of sentences.

Each line of the cases file is JSON: {"text": ..., "expect": {...}} with any of
symptoms, severity, duration_min, bp_sys, bp_dia, glucose, meds, triggers,
red_flags. A field is scored only on cases that label it. This measures the
text-to-fields step; speech-to-text error is measured separately on recordings.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from .extract import extract


def _actual(fields: dict) -> dict:
    bp = fields["bp"] or {}
    return {
        "symptoms": sorted(fields["symptoms"]),
        "severity": fields["severity"],
        "duration_min": fields["duration_min"],
        "bp_sys": bp.get("sys"),
        "bp_dia": bp.get("dia"),
        "glucose": fields["glucose"],
        "meds": sorted([m["name"], m["taken"]] for m in fields["medications"]),
        "triggers": sorted(fields["triggers"]),
        "red_flags": sorted(fields["red_flags"]),
    }


def evaluate(path: Path, llm_model: str | None = None) -> dict:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    hits, totals = defaultdict(int), defaultdict(int)
    failures, times = [], []
    for case in cases:
        t0 = time.perf_counter()
        fields = extract(case["text"])
        if llm_model:
            from .llm import merge_llm
            fields, _ = merge_llm(fields, case["text"], llm_model)
        times.append((time.perf_counter() - t0) * 1000)
        got = _actual(fields)
        for key, want in case["expect"].items():
            if isinstance(want, list):
                want = sorted(want)
            totals[key] += 1
            if got[key] == want:
                hits[key] += 1
            else:
                failures.append((case["text"], key, want, got[key]))

    print(f"{len(cases)} sentences · extraction {'rules + ' + llm_model if llm_model else 'rules only'}\n")
    print(f"{'field':<14}{'correct':>10}{'accuracy':>10}")
    all_hits = all_total = 0
    for key in totals:
        all_hits += hits[key]
        all_total += totals[key]
        print(f"{key:<14}{hits[key]:>5} / {totals[key]:<4}{hits[key] / totals[key]:>9.0%}")
    print(f"{'all fields':<14}{all_hits:>5} / {all_total:<4}{all_hits / all_total:>9.0%}")
    times.sort()
    print(f"\nextraction time per sentence: median {times[len(times) // 2]:.2f} ms, max {times[-1]:.2f} ms")
    if failures:
        print("\nmisses:")
        for text, key, want, got in failures:
            print(f"  [{key}] want {want!r}, got {got!r}\n        「{text}」")
    return {"accuracy": all_hits / all_total, "failures": failures}
