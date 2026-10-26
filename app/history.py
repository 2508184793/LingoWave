from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Caption:
    id: int
    start: float
    end: float
    source: str
    translation: str = ""
    status: str = "等待翻译"


class History:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS captions (session TEXT, id INTEGER, start REAL, end REAL, source TEXT, translation TEXT, status TEXT, PRIMARY KEY(session,id))")
        self.db.commit()

    def save(self, session: str, caption: Caption):
        self.db.execute("INSERT OR REPLACE INTO captions VALUES (?,?,?,?,?,?,?)", (session, caption.id, caption.start, caption.end, caption.source, caption.translation, caption.status))
        self.db.commit()

    def recent(self, limit: int = 100) -> list[tuple[str, Caption]]:
        rows = self.db.execute("SELECT session,id,start,end,source,translation,status FROM captions ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [(r[0], Caption(*r[1:])) for r in reversed(rows)]

    def clear(self):
        self.db.execute("DELETE FROM captions")
        self.db.commit()

    def close(self):
        self.db.close()


def srt_time(seconds: float) -> str:
    total = max(0, round(seconds * 1000))
    hours, total = divmod(total, 3600000)
    minutes, total = divmod(total, 60000)
    secs, millis = divmod(total, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def export_captions(captions: list[Caption], path: Path) -> None:
    if path.suffix.lower() == ".srt":
        blocks = []
        for i, c in enumerate(captions, 1):
            text = "\n".join(t for t in (c.source, c.translation) if t)
            blocks.append(f"{i}\n{srt_time(c.start)} --> {srt_time(max(c.end, c.start + 0.1))}\n{text}\n")
        content = "\n".join(blocks)
    else:
        content = "\n\n".join(f"[{srt_time(c.start)}]\n{c.source}\n{c.translation}" for c in captions)
    path.write_text(content, encoding="utf-8-sig")
