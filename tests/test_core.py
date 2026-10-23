from datetime import datetime

import pytest

from speakhome.cnnum import cn2num
from speakhome.dialogue import follow_up_needed, merge_answer, parse_confirmation, read_back
from speakhome.extract import extract, is_delete_command
from speakhome.store import Store
from speakhome.summary import build_summary


@pytest.mark.parametrize("token,value", [
    ("一百五", 150), ("一百五十", 150), ("一百零五", 105), ("兩百", 200), ("十五", 15),
    ("三十", 30), ("九十八", 98), ("兩百一", 210), ("一千二", 1200), ("145", 145), ("５", 5),
])
def test_cn2num(token, value):
    assert cn2num(token) == value


def test_example_from_proposal():
    f = extract("今天下午頭有點暈，大概五分，量血壓一百五，有吃早上的藥。")
    assert f["symptoms"] == ["頭暈"]
    assert f["severity"] == 5
    assert f["time_of_day"] == "下午"
    assert f["bp"] == {"sys": 150, "dia": None}
    assert f["medications"] == [{"name": "早上的藥", "taken": True}]
    assert follow_up_needed(f) == "duration"


def test_minutes_are_not_severity():
    f = extract("頭暈，大概五分鐘就好了")
    assert f["severity"] is None
    assert f["duration_min"] == 5


def test_negated_symptom_is_ignored():
    assert extract("今天頭不暈了，血壓一百三十")["symptoms"] == []


def test_red_flag_skips_follow_up():
    f = extract("胸口很痛")
    assert f["red_flags"] == ["胸痛"]
    assert follow_up_needed(f) is None


def test_answer_fills_the_asked_slot():
    f = extract("晚上睡不著")
    assert follow_up_needed(f) == "severity"
    f = merge_answer(f, "severity", "四")
    assert f["severity"] == 4
    assert "4 分" in read_back(f)


def test_confirmation_words():
    assert parse_confirmation("對") is True
    assert parse_confirmation("不對") is False
    assert parse_confirmation("是的") is True
    assert parse_confirmation("不是") is False
    assert parse_confirmation("嗯…") is True


def test_delete_command():
    assert is_delete_command("刪掉剛剛那筆")
    assert not is_delete_command("頭暈")


def test_store_is_encrypted_and_summary_links(tmp_path):
    store = Store(tmp_path)
    now = datetime(2026, 10, 12, 15, 0)
    for text in ["頭暈，大概五分，十分鐘", "頭暈，大概七分，半小時", "血壓一百五十跟九十"]:
        store.add(now, text, extract(text), confirmed=True)
    store.add(now, "頭暈，大概九分，一小時", extract("頭暈，大概九分，一小時"), confirmed=False)
    raw = (tmp_path / "speakhome.db").read_bytes()
    assert "頭暈".encode() not in raw  # sentences are not stored in plain text

    entries = store.entries()
    assert len(entries) == 3  # the unconfirmed entry is not counted
    s = build_summary(entries, datetime(2026, 10, 1), datetime(2026, 10, 12, 23, 59))
    dizzy = s["symptoms"][0]
    assert (dizzy["name"], dizzy["count"], dizzy["max"]) == ("頭暈", 2, 7)
    group = next(g for g in s["groups"] if g["key"] == dizzy["group"])
    assert len(group["ids"]) == 2
    assert s["bp"]["max_sys"] == 150

    store.delete_last()
    assert len(store.entries(confirmed_only=False)) == 3
