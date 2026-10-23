# Speak Home 說給家聽 — Stage I prototype

A local voice health diary for older patients and the family who cares for them.
The patient says one sentence a day in Mandarin; the station extracts the details,
asks at most one follow-up question, reads the entry back for confirmation and
stores it encrypted on the device. Before a clinic visit the caregiver gets a
one-page summary in which **every number links to the sentences it came from**.

Built for the ASUS UGen AI League (Everyday AI · Battlefield Lightning). This
Stage I version runs entirely on a laptop CPU; Stage II moves the speech and
language models onto the ASUS UGen300.

> Speak Home organises what the patient said. It does not diagnose, give
> medication advice or decide whether to see a doctor.

## Quick start

Python 3.10+.

```bash
pip install -r requirements.txt              # core: works with typed input
python -m speakhome seed --reset             # two weeks of sample entries
python -m speakhome summary --patient 王阿嬤  # writes reports/visit-summary-*.pdf and .html
```

Open the PDF and click any underlined number to jump to its source sentences.

### Speech input (optional)

```bash
pip install -r requirements-speech.txt       # faster-whisper, sounddevice, pyttsx3, opencc
python -m speakhome station                  # press Enter, speak, press Enter
```

The first run downloads the Whisper model (`small` by default; set
`SPEAKHOME_WHISPER=medium` for better accuracy on a faster machine). Audio is
kept in memory only and dropped after transcription; no audio file is written.

### Optional local language model

```bash
ollama pull qwen2.5:3b
python -m speakhome station --llm qwen2.5:3b
```

The model only fills fields the rules left empty, and every value it returns
is checked against the sentence: a number the patient never said, or a symptom
whose words are not in the sentence, is rejected and printed.

## Demo script (for the 3-minute video)

```bash
python -m speakhome seed --reset
python -m speakhome log --text "今天下午頭有點暈，大概五分，量血壓一百五，有吃早上的藥。" --answer "大概半個小時" --yes
python -m speakhome log --text "胸口很痛" --yes       # fixed keyword rule: "call family or 119"
python -m speakhome log --text "刪掉剛剛那筆"          # the patient can withdraw an entry
python -m speakhome summary --patient 王阿嬤
python -m speakhome serve --lan                      # caregiver opens it from a phone at home
```

For the video, `station` (microphone) or `station --keyboard` shows the same
flow interactively.

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

## Results so far

Field extraction, rules only, on a laptop CPU:

| Set | Sentences | Fields correct | Note |
|---|---|---|---|
| `eval/cases.jsonl` | 25 | 65 / 65 (100%) | development set; the rules were tuned on it |
| `eval/holdout.jsonl` | 12 | 22 / 27 (81%) | written afterwards and **not** tuned on |

Extraction takes well under a millisecond per sentence (median). The holdout
misses show where rules run out (for example 「膝蓋不太舒服」 and 「血壓…一百五十六、九十四」),
which is the job of the grounded language model in Stage II. Both sets are
small and written by the team; the real measure needs recordings from older
speakers, including speech-to-text error rate, which this version does not yet
report.

## Privacy

- No camera; the microphone records only between two presses of Enter (the button in the station design).
- Audio is never written to disk.
- Each entry's sentence and fields are encrypted (Fernet) with a key stored beside the database with file mode 600. Timestamps are in the clear so date ranges can be queried. A shipped station would use full-database encryption with the key in secure storage.
- `delete-last` (or saying 「刪掉剛剛那筆」) overwrites the entry's content.
- `serve --lan` has no login; use it only on a trusted home network.

## Stage II (UGen300)

1. Convert the speech-to-text and language models for the Hailo-10H and measure latency, power and memory against this CPU baseline.
2. Physical station: big button, speaker, status light, mini PC or SBC host.
3. Taiwanese speech if models allow; several older people per station; a weekly caregiver digest.

Model support on the UGen300 must be confirmed on the competition's platform page before this plan is final.

## Tests

```bash
pip install pytest
python -m pytest
```
