"""Persistence back-ends for leads: CSV and SQLite.

Both stores share the :class:`LeadStore` interface so the pipeline and CLI can
treat them interchangeably. Writes are idempotent-friendly: SQLite upserts on
the dedupe key, and CSV can append or overwrite.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable, Protocol

from .dedupe import dedupe_key
from .models import FIELD_ORDER, Lead


class LeadStore(Protocol):
    def write(self, leads: Iterable[Lead]) -> int: ...
    def read(self) -> list[Lead]: ...


class CsvStore:
    """Write/read leads as a UTF-8 CSV file with a stable column order."""

    def __init__(self, path: str | Path, append: bool = False) -> None:
        self.path = Path(path)
        self.append = append

    def write(self, leads: Iterable[Lead]) -> int:
        leads = list(leads)
        file_exists = self.path.exists()
        mode = "a" if (self.append and file_exists) else "w"
        write_header = not (self.append and file_exists)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open(mode, newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELD_ORDER, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for lead in leads:
                writer.writerow(lead.to_row())
        return len(leads)

    def read(self) -> list[Lead]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return [Lead.from_row(row) for row in csv.DictReader(fh)]


class SqliteStore:
    """Store leads in a SQLite table, upserting on the dedupe key."""

    def __init__(self, path: str | Path, table: str = "leads") -> None:
        self.path = Path(path)
        self.table = table
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        cols = ",\n  ".join(f'"{c}" TEXT' for c in FIELD_ORDER)
        with self._connect() as conn:
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{self.table}" (\n'
                f'  dedupe_key TEXT PRIMARY KEY,\n  {cols}\n)'
            )

    def write(self, leads: Iterable[Lead]) -> int:
        placeholders = ", ".join(["?"] * (len(FIELD_ORDER) + 1))
        columns = ", ".join(["dedupe_key"] + [f'"{c}"' for c in FIELD_ORDER])
        count = 0
        with self._connect() as conn:
            for i, lead in enumerate(leads):
                row = lead.to_row()
                key = dedupe_key(lead) or f"row:{lead.source}:{i}:{lead.scraped_at}"
                values = [key] + [row[c] for c in FIELD_ORDER]
                conn.execute(
                    f'INSERT INTO "{self.table}" ({columns}) VALUES ({placeholders}) '
                    f"ON CONFLICT(dedupe_key) DO UPDATE SET "
                    + ", ".join(f'"{c}"=excluded."{c}"' for c in FIELD_ORDER),
                    values,
                )
                count += 1
        return count

    def read(self) -> list[Lead]:
        with self._connect() as conn:
            rows = conn.execute(f'SELECT * FROM "{self.table}"').fetchall()
        return [Lead.from_row({k: r[k] for k in r.keys()}) for r in rows]


def open_store(path: str | Path, fmt: str | None = None, append: bool = False) -> LeadStore:
    """Factory: pick a store from an explicit format or the file extension."""
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".")).lower()
    if fmt in ("sqlite", "db", "sqlite3"):
        return SqliteStore(path)
    if fmt in ("csv", ""):
        return CsvStore(path, append=append)
    raise ValueError(f"Unsupported output format: {fmt!r}")
