"""Command line for the Speak Home prototype.

  python -m speakhome station            # the home station: speak, answer, confirm (loop)
  python -m speakhome station --keyboard # same, typing instead of a microphone
  python -m speakhome log --text "今天下午頭有點暈，大概五分" --answer "半小時" --yes
  python -m speakhome seed --reset       # two weeks of sample entries
  python -m speakhome summary            # PDF + HTML visit summary
  python -m speakhome serve --lan        # caregiver opens the summary on the home network
  python -m speakhome eval               # field-extraction accuracy on the test set
"""
from __future__ import annotations

import argparse
import http.server
import json
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from .dialogue import (QUESTIONS, SAFETY_MESSAGE, follow_up_needed, merge_answer,
                       parse_confirmation, read_back)
from .extract import extract, is_delete_command, is_empty
from .store import Store
from .summary import build_summary


# --- Input sources --------------------------------------------------------
class Input:
    """Where the patient's words come from: microphone, keyboard or fixed text."""

    def __init__(self, mode: str, text=None, answer=None, yes=False, wav=None):
        self.mode, self.text, self.answer, self.yes, self.wav = mode, text, answer, yes, wav
        self.asr_seconds = 0.0

    def _listen(self) -> str:
        if self.mode == "mic":
            from .speech import record_push_to_talk, transcribe
            audio = record_push_to_talk()
            text, secs = transcribe(audio)
            del audio  # audio lives only in memory and is dropped here
            self.asr_seconds += secs
            print(f"  📝 {text}   (speech-to-text {secs:.2f}s)")
            return text
        return input("  > ").strip()

    def entry(self) -> str:
        if self.wav:
            from .speech import transcribe
            text, secs = transcribe(self.wav)
            self.asr_seconds += secs
            print(f"  📝 {text}   (speech-to-text {secs:.2f}s)")
            return text
        if self.text is not None:
            print(f"  📝 {self.text}")
            return self.text
        return self._listen()

    def reply(self) -> str:
        if self.answer is not None:
            print(f"  📝 {self.answer}")
            return self.answer
        if self.text is not None and not sys.stdin.isatty():
            return ""
        return self._listen()

    def confirm(self) -> str:
        if self.yes:
            print("  📝 對")
            return "對"
        if self.text is not None and not sys.stdin.isatty():
            return ""
        if self.mode == "mic":
            return self._listen()
        return input("  > 對 / 不對: ").strip()


# --- One entry ------------------------------------------------------------
def run_entry(store: Store, src: Input, voice, llm_model: str | None, at: datetime | None) -> int | None:
    text = src.entry()
    if not text:
        voice.say("我沒有聽到聲音，可以再說一次嗎？")
        return None
    if is_delete_command(text):
        deleted = store.delete_last()
        voice.say("好，剛剛那筆已經刪掉了。" if deleted else "目前沒有紀錄可以刪。")
        return None

    t0 = time.perf_counter()
    fields = extract(text)
    if llm_model:
        from .llm import merge_llm
        fields, rejected = merge_llm(fields, text, llm_model)
        for r in rejected:
            print(f"  (language-model value rejected: {r})")
    extract_ms = (time.perf_counter() - t0) * 1000

    if fields["red_flags"]:
        voice.say(SAFETY_MESSAGE)

    follow = None
    if slot := follow_up_needed(fields):
        question = QUESTIONS[slot]
        voice.say(question)
        answer = src.reply()
        if answer:
            fields = merge_answer(fields, slot, answer)
        follow = {"slot": slot, "question": question, "answer": answer}
        if is_empty(fields):
            voice.say("沒關係，想到再跟我說。")
            return None

    voice.say(read_back(fields))
    confirmed = parse_confirmation(src.confirm())
    if confirmed is False:
        voice.say("好，這筆先不記。請再說一次。")
        return None

    ts = (at or datetime.now()).replace(second=0, microsecond=0) + timedelta(days=fields["day_offset"])
    entry_id = store.add(ts, text, fields, confirmed=bool(confirmed), follow_up=follow)
    status = "confirmed" if confirmed else "saved unconfirmed (not counted in summaries)"
    print(f"  ✓ entry #{entry_id} {status} · extraction {extract_ms:.1f} ms"
          + (f" · speech-to-text {src.asr_seconds:.2f}s" if src.asr_seconds else ""))
    if confirmed:
        voice.say("記好了，謝謝。")
    return entry_id


# --- Commands -------------------------------------------------------------
def _voice(args):
    from .speech import Voice
    return Voice(enabled=not args.no_voice)


def cmd_log(args, store):
    mode = "text" if (args.text is not None or args.wav) else ("keyboard" if args.keyboard else "mic")
    src = Input(mode, text=args.text, answer=args.answer, yes=args.yes, wav=args.wav)
    at = datetime.fromisoformat(args.at) if args.at else None
    run_entry(store, src, _voice(args), args.llm, at)


def cmd_station(args, store):
    voice = _voice(args)
    mode = "keyboard" if args.keyboard else "mic"
    print("Speak Home station. Ctrl+C to stop.\n" + ("Type each sentence." if args.keyboard else ""))
    voice.say("你好，今天身體怎麼樣？")
    try:
        while True:
            run_entry(store, Input(mode), voice, args.llm, None)
            print()
    except (KeyboardInterrupt, EOFError):
        print("\nbye")


def cmd_seed(args, store):
    from .sample_data import seed
    if args.reset:
        store.clear()
    n = seed(store)
    print(f"Added {n} sample entries covering the last 14 days.")


def _summary(store, days):
    end = datetime.now().replace(hour=23, minute=59, second=0, microsecond=0)
    start = (end - timedelta(days=days - 1)).replace(hour=0, minute=0)
    return build_summary(store.entries(start, end), start, end)


def cmd_summary(args, store):
    from .report_html import render_html
    from .report_pdf import render_pdf
    s = _summary(store, args.days)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    html_path = out / f"visit-summary-{stamp}.html"
    html_path.write_text(render_html(s, args.patient), encoding="utf-8")
    pdf_path = render_pdf(s, out / f"visit-summary-{stamp}.pdf", args.patient)
    print(f"{s['entry_count']} confirmed entries over {s['days_total']} days")
    print(f"  {pdf_path}\n  {html_path}")


def cmd_list(args, store):
    start = datetime.now() - timedelta(days=args.days)
    for e in store.entries(start=start, confirmed_only=not args.all):
        from .report_common import entry_tags
        mark = "" if e["confirmed"] else " (unconfirmed)"
        print(f"#{e['id']:<4} {e['ts']:%m/%d %H:%M}{mark}  {e['text']}")
        print(f"       {' · '.join(entry_tags(e['fields']))}")


def cmd_delete_last(args, store):
    deleted = store.delete_last()
    print(f"Deleted entry #{deleted}." if deleted else "Nothing to delete.")


def cmd_serve(args, store):
    from .report_html import render_html
    days, patient, data_dir = args.days, args.patient, store.dir

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            # A fresh connection per request: http.server may use another thread.
            body = render_html(_summary(Store(data_dir), days), patient).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    server = http.server.ThreadingHTTPServer((host, args.port), Handler)
    shown = host
    if args.lan:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("192.168.0.1", 1))  # no packet is sent; just picks the LAN interface
                shown = s.getsockname()[0]
        except OSError:
            shown = "<this computer's IP>"
        print("Note: anyone on this home network can open the page. The prototype has no login.")
    print(f"Visit summary at http://{shown}:{args.port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_eval(args, store):
    from .evaluate import evaluate
    evaluate(Path(args.file), args.llm)


def main(argv=None):
    p = argparse.ArgumentParser(prog="speakhome", description="Speak Home prototype")
    p.add_argument("--data", default=None, help="data folder (default ./data or $SPEAKHOME_DATA)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def voice_opts(sp):
        sp.add_argument("--no-voice", action="store_true", help="print prompts only, no text-to-speech")
        sp.add_argument("--llm", metavar="MODEL", help="also use a local Ollama model, e.g. qwen2.5:3b")

    sp = sub.add_parser("log", help="record one entry")
    sp.add_argument("--text", help="use this sentence instead of the microphone")
    sp.add_argument("--wav", help="transcribe this audio file instead of the microphone")
    sp.add_argument("--keyboard", action="store_true", help="type instead of speaking")
    sp.add_argument("--answer", help="answer to the follow-up question (scripted demo)")
    sp.add_argument("--yes", action="store_true", help="confirm the read-back automatically")
    sp.add_argument("--at", help="entry time, e.g. 2026-10-12T15:20 (default now)")
    voice_opts(sp)
    sp.set_defaults(fn=cmd_log)

    sp = sub.add_parser("station", help="run the station loop")
    sp.add_argument("--keyboard", action="store_true", help="type instead of speaking")
    voice_opts(sp)
    sp.set_defaults(fn=cmd_station)

    sp = sub.add_parser("seed", help="load two weeks of sample entries")
    sp.add_argument("--reset", action="store_true", help="delete all existing entries first")
    sp.set_defaults(fn=cmd_seed)

    for name, fn, helptext in (("summary", cmd_summary, "write the PDF and HTML visit summary"),
                               ("serve", cmd_serve, "serve the summary page to a browser")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--days", type=int, default=14)
        sp.add_argument("--patient", default="[姓名]", help="name shown on the summary")
        if name == "summary":
            sp.add_argument("--out-dir", default="reports")
        else:
            sp.add_argument("--port", type=int, default=8000)
            sp.add_argument("--lan", action="store_true", help="allow other devices on the home network")
        sp.set_defaults(fn=fn)

    sp = sub.add_parser("list", help="show recent entries")
    sp.add_argument("--days", type=int, default=14)
    sp.add_argument("--all", action="store_true", help="include unconfirmed entries")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("delete-last", help="delete the most recent entry")
    sp.set_defaults(fn=cmd_delete_last)

    sp = sub.add_parser("eval", help="measure field-extraction accuracy")
    sp.add_argument("--file", default=str(Path(__file__).resolve().parent.parent / "eval" / "cases.jsonl"))
    sp.add_argument("--llm", metavar="MODEL")
    sp.set_defaults(fn=cmd_eval)

    args = p.parse_args(argv)
    store = Store(args.data) if args.data else Store()
    args.fn(args, store)


if __name__ == "__main__":
    main()
