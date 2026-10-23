"""Microphone, speech-to-text and text-to-speech, all local.

Recording stays in memory and is dropped after transcription; no audio file is
ever written. Every dependency here is optional so the rest of the prototype
(text input, storage, summaries) works without them.

  pip install faster-whisper sounddevice numpy   # speech input
  pip install pyttsx3                            # spoken prompts (optional)
  pip install opencc-python-reimplemented        # Simplified -> Traditional (optional)
"""
from __future__ import annotations

import os
import sys
import threading
import time

SAMPLE_RATE = 16000
WHISPER_MODEL = os.environ.get("SPEAKHOME_WHISPER", "small")
# Biases Whisper toward Traditional characters and medical vocabulary.
INITIAL_PROMPT = "以下是繁體中文的健康紀錄，例如：今天下午頭暈，大概五分，血壓一百五，有吃早上的藥。"

_model = None
_opencc = None


def _to_traditional(text: str) -> str:
    global _opencc
    try:
        if _opencc is None:
            from opencc import OpenCC
            _opencc = OpenCC("s2twp")
        return _opencc.convert(text)
    except ImportError:
        return text


def load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


def record_push_to_talk(max_seconds: float = 60.0):
    """Press Enter to start, Enter to stop. Returns a float32 numpy array."""
    import numpy as np
    import sounddevice as sd

    chunks = []
    stop = threading.Event()

    def callback(indata, frames, t, status):
        chunks.append(indata.copy())

    input("  [按 Enter 開始說話 / press Enter to start] ")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback):
        print("  ● 錄音中… 說完請按 Enter / recording, press Enter to stop")
        waiter = threading.Thread(target=lambda: (input(), stop.set()), daemon=True)
        waiter.start()
        stop.wait(timeout=max_seconds)
    return np.concatenate(chunks)[:, 0] if chunks else np.zeros(0, dtype="float32")


def transcribe(audio) -> tuple[str, float]:
    """audio: numpy float32 at 16 kHz, or a path to an audio file.
    Returns (text, seconds taken)."""
    model = load_model()
    start = time.perf_counter()
    segments, _ = model.transcribe(audio, language="zh", initial_prompt=INITIAL_PROMPT,
                                   beam_size=5, vad_filter=True)
    text = "".join(seg.text for seg in segments).strip()
    return _to_traditional(text), time.perf_counter() - start


class Voice:
    """Speaks prompts if pyttsx3 is installed; always prints them as well."""

    def __init__(self, enabled: bool = True):
        self.engine = None
        if enabled:
            try:
                import pyttsx3
                self.engine = pyttsx3.init()
                for v in self.engine.getProperty("voices"):
                    langs = " ".join(str(x) for x in (getattr(v, "languages", []) or []))
                    if any(k in (v.name + v.id + langs).lower() for k in ("zh", "chinese", "mandarin", "taiwan")):
                        self.engine.setProperty("voice", v.id)
                        break
                self.engine.setProperty("rate", 150)  # slower for older listeners
            except Exception:
                self.engine = None

    def say(self, text: str) -> None:
        print(f"  🔊 {text}")
        sys.stdout.flush()
        if self.engine:
            self.engine.say(text)
            self.engine.runAndWait()
