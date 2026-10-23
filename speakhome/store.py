"""Local encrypted storage.

Each entry's sentence and fields are encrypted with a key kept beside the
database (file mode 600). Only the timestamp and flags are stored in the clear,
so date-range queries work. Audio is never written here.

Prototype note: this is field-level encryption with Fernet (AES-128-CBC +
HMAC). A shipped station would use full-database encryption (e.g. SQLCipher)
with the key in the device's secure storage.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet

DATA_DIR = Path(os.environ.get("SPEAKHOME_DATA", Path.cwd() / "data"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,          -- ISO local time the event refers to
    logged_at TEXT NOT NULL,          -- when it was recorded
    confirmed INTEGER NOT NULL DEFAULT 0,
    deleted   INTEGER NOT NULL DEFAULT 0,
    payload   BLOB NOT NULL           -- encrypted JSON: text, fields, follow-up
);
CREATE INDEX IF NOT EXISTS idx_entries_ts ON entries(ts);
"""


class Store:
    def __init__(self, data_dir: Path | str = DATA_DIR):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.fernet = Fernet(self._key())
        self.db = sqlite3.connect(self.dir / "speakhome.db")
        self.db.executescript(SCHEMA)

    def _key(self) -> bytes:
        path = self.dir / "speakhome.key"
        if not path.exists():
            path.write_bytes(Fernet.generate_key())
            os.chmod(path, 0o600)
        return path.read_bytes()

    def add(self, ts: datetime, text: str, fields: dict, confirmed: bool,
            follow_up: dict | None = None) -> int:
        payload = json.dumps({"text": text, "fields": fields, "follow_up": follow_up},
                             ensure_ascii=False).encode()
        cur = self.db.execute(
            "INSERT INTO entries (ts, logged_at, confirmed, payload) VALUES (?, ?, ?, ?)",
            (ts.isoformat(timespec="minutes"), datetime.now().isoformat(timespec="seconds"),
             int(confirmed), self.fernet.encrypt(payload)))
        self.db.commit()
        return cur.lastrowid

    def entries(self, start: datetime | None = None, end: datetime | None = None,
                confirmed_only: bool = True) -> list[dict]:
        sql = "SELECT id, ts, confirmed, payload FROM entries WHERE deleted = 0"
        args: list = []
        if start:
            sql += " AND ts >= ?"
            args.append(start.isoformat(timespec="minutes"))
        if end:
            sql += " AND ts <= ?"
            args.append(end.isoformat(timespec="minutes"))
        if confirmed_only:
            sql += " AND confirmed = 1"
        rows = self.db.execute(sql + " ORDER BY ts", args).fetchall()
        out = []
        for id_, ts, confirmed, blob in rows:
            data = json.loads(self.fernet.decrypt(blob))
            out.append({"id": id_, "ts": datetime.fromisoformat(ts),
                        "confirmed": bool(confirmed), **data})
        return out

    def delete_last(self) -> int | None:
        row = self.db.execute(
            "SELECT id FROM entries WHERE deleted = 0 ORDER BY logged_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        # Overwrite the content, not just flag it, so the sentence is really gone.
        self.db.execute("UPDATE entries SET deleted = 1, payload = ? WHERE id = ?",
                        (self.fernet.encrypt(b'{"text": "", "fields": {}}'), row[0]))
        self.db.commit()
        return row[0]

    def clear(self) -> None:
        self.db.execute("DELETE FROM entries")
        self.db.commit()
