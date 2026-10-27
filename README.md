# Speak Home 說給家聽 — Stage I prototype

ASUS UGen AI League (Everyday AI · Battlefield Lightning) — Stage I prototype

A local voice health diary for older patients and the family who cares for them.
The patient says one sentence a day in Mandarin; the station extracts the details,
asks at most one follow-up question, reads the entry back for confirmation and
stores it encrypted on the device. Before a clinic visit the caregiver gets a
one-page summary in which **every number links to the sentences it came from**.

> Speak Home organises what the patient said. It does not diagnose, give
> medication advice or decide whether to see a doctor.

## Quick start

Python 3.10+.

### 1. Install

```bash
pip install -r requirements.txt              # storage and visit summaries
pip install -r requirements-speech.txt       # speech: faster-whisper, sounddevice, pyttsx3, opencc
```

The first time the station runs it downloads the Whisper speech model. 
After that, set `HF_HUB_OFFLINE=1` so the station never connects to
the internet.

### 2. Daily check-in

```bash
python -m speakhome station           # press Enter, speak, press Enter
```

The station asks at most one follow-up question, then reads the entry back.
Answer 「對，沒錯」 to save it; only confirmed entries count in summaries. To
withdraw the last entry, say 「刪掉剛剛那筆」 or run `delete-last`.

Audio is kept in memory only and dropped after transcription; no audio file
is written.

### 3. Before a clinic visit

```bash
python -m speakhome summary --patient 王阿嬤 --days 30
```

This writes a PDF and an HTML page covering the last 30 days, up to today.
Click any underlined number to see the sentences behind it. To let a
caregiver open the summary from a phone on the same home network:

```bash
python -m speakhome serve --lan
```

The page has no login; use it only on a trusted home network.


## Commands

| Command | What it does |
|---|---|
| `station [--keyboard] [--llm MODEL]` | The home station loop: speak, answer one question, confirm |
| `log --text/--wav/--keyboard [--answer A] [--yes]` | Record one entry (scriptable) |
| `seed [--reset]` | Load 15 sample entries over the last 14 days |
| `summary [--days 14] [--patient NAME]` | Write the PDF and HTML visit summary |
| `serve [--lan] [--port 8000]` | Serve the live summary page (no login: home network only) |
| `list [--all]` / `delete-last` | Review or withdraw entries |
| `eval [--file F] [--llm MODEL]` | Field-extraction accuracy and timing |

Data lives in `./data` (or `--data DIR`, or `$SPEAKHOME_DATA`).

## How it works

```
microphone ─► speech-to-text (Whisper, local) ─► field extraction ─► one follow-up?
                                                  rules (+ optional LLM,       │
                                                  grounded in the sentence)    ▼
caregiver ◄─ PDF / HTML summary ◄─ statistics with source ids ◄─ encrypted SQLite ◄─ read-back + confirm
```

| File | Role |
|---|---|
| `speakhome/cnnum.py` | Spoken Chinese numbers, including colloquial 一百五 = 150 |
| `speakhome/extract.py` | Rule-based extraction: symptoms, severity, duration, blood pressure, glucose, medication, possible factors, keyword alerts |
| `speakhome/llm.py` | Optional local LLM with grounding checks |
| `speakhome/dialogue.py` | Follow-up question, read-back, confirmation, safety prompt |
| `speakhome/speech.py` | Push-to-talk recording, Whisper, text-to-speech |
| `speakhome/store.py` | Encrypted local storage |
| `speakhome/summary.py` | Statistics; each one keeps the ids of its source entries |
| `speakhome/report_pdf.py`, `report_html.py` | Visit summary with links to source sentences |

Design rules carried into the code:
- **One question at most** per entry, and none when a keyword alert fires.
- **Only confirmed entries count** in summaries; unclear confirmations are stored but excluded.
- **No value without a source**: the summary is computed only from stored fields, and each statistic links to the sentences behind it.
- **Keyword alerts are a fixed rule** (chest pain, slurred speech, one-sided weakness, facial droop, fainting, breathing difficulty) that prompts "call your family or 119". It is not a medical judgement.
