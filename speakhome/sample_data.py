"""Two weeks of sample entries for the demo, in the voice of an older patient.

They go through the same extraction and follow-up code as live entries, so
the demo summary is produced by the real pipeline.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .dialogue import QUESTIONS, follow_up_needed, merge_answer
from .extract import extract
from .store import Store

# (days before today, time, sentence, answer to the follow-up question or None)
SAMPLES = [
    (-13, "09:10", "早上起床頭有點暈，大概四分，坐一下十分鐘就好了。量血壓一百四十二跟八十八，有吃早上的藥。", None),
    (-12, "20:30", "今天還好，沒有哪裡不舒服，早上的藥有吃。", None),
    (-11, "15:40", "昨晚沒睡好，今天下午頭暈，大概五分，持續半個小時。", None),
    (-10, "08:50", "血壓一百三十八跟九十，早上的藥吃了。", None),
    (-9, "21:00", "膝蓋有點痛，大概三分，今天走太多了，一整天都酸酸的。", None),
    (-8, "16:20", "下午站起來太快，頭暈，大概六分，大概五分鐘。", None),
    (-7, "09:00", "忘了吃早上的藥，血壓一百五十二跟九十二。", None),
    (-6, "14:30", "頭暈，大概七分，天氣變冷，持續一個小時。", None),
    (-6, "21:30", "晚上睡不著，翻來覆去。", "大概四分"),
    (-5, "08:40", "血壓一百四十五跟八十九，早上的藥有吃。", None),
    (-4, "11:10", "今天身體不錯，有去公園走走。", None),
    (-3, "15:00", "下午又頭暈，大概六分，坐下來休息就好了。", "二十分鐘左右"),
    (-2, "09:15", "早上的藥忘記吃了，中午才發現。血壓一百五十八跟九十五。", None),
    (-1, "16:45", "頭痛，大概五分，吃了一顆止痛藥，大概兩個小時才好。昨晚沒睡好。", None),
    (0, "17:30", "今天下午頭有點暈，大概五分，量血壓一百五，有吃早上的藥。", "大概半個小時"),
]


def seed(store: Store, today: datetime | None = None) -> int:
    today = (today or datetime.now()).replace(second=0, microsecond=0)
    count = 0
    for offset, hhmm, text, answer in SAMPLES:
        h, m = map(int, hhmm.split(":"))
        ts = (today + timedelta(days=offset)).replace(hour=h, minute=m)
        fields = extract(text)
        follow = None
        if slot := follow_up_needed(fields):
            question = QUESTIONS[slot]
            if answer:
                fields = merge_answer(fields, slot, answer)
            follow = {"slot": slot, "question": question, "answer": answer}
        store.add(ts, text, fields, confirmed=True, follow_up=follow)
        count += 1
    return count
