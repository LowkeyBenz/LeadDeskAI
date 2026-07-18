from __future__ import annotations
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from .schema import SCHEMA_SQL, SCHEMA_VERSION
from leaddesk_ai.core.paths import DB_PATH


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        row = self.conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO schema_meta(version) VALUES(?)", (SCHEMA_VERSION,))
        elif int(row["version"]) < SCHEMA_VERSION:
            self.conn.execute("UPDATE schema_meta SET version=?", (SCHEMA_VERSION,))
        defaults = {
            "business_name": "LeadDesk AI",
            "default_market": "Maricopa County, AZ",
            "auto_backup": "1",
            "require_approval_for_outreach": "1",
        }
        for key, value in defaults.items():
            self.conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def stats(self) -> dict[str, int]:
        q = self.conn.execute
        return {
            "properties": q("SELECT COUNT(*) c FROM properties").fetchone()["c"],
            "open_tasks": q("SELECT COUNT(*) c FROM tasks WHERE status='Open'").fetchone()["c"],
            "buyers": q("SELECT COUNT(*) c FROM buyers WHERE active=1").fetchone()["c"],
            "restricted": q("SELECT COUNT(*) c FROM communication_preferences WHERE internal_dnc=1 OR opt_out=1").fetchone()["c"],
        }

    def list_properties(self, search: str = "") -> list[sqlite3.Row]:
        sql = """SELECT p.*, COALESCE(o.name,'') owner_name,
                 COALESCE((SELECT value FROM contacts c WHERE c.owner_id=o.id AND c.type='phone' ORDER BY c.is_primary DESC,c.id LIMIT 1),'') phone
                 FROM properties p LEFT JOIN owners o ON o.property_id=p.id WHERE 1=1"""
        args: list[Any] = []
        if search.strip():
            term = f"%{search.strip()}%"
            sql += " AND (p.address LIKE ? OR p.city LIKE ? OR p.zip LIKE ? OR o.name LIKE ?)"
            args.extend([term] * 4)
        return list(self.conn.execute(sql + " ORDER BY p.id DESC", args))

    def add_note(self, property_id: int, body: str, user: str = "admin") -> int:
        body = body.strip()
        if not body:
            raise ValueError("Note cannot be empty.")
        with self.conn:
            cur = self.conn.execute("INSERT INTO notes(property_id,body,created_by,created_at) VALUES(?,?,?,?)", (property_id, body, user, now()))
            self.conn.execute("INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)", (property_id, "Note Added", body, user, now()))
        self.audit("add_note", "property", property_id, after={"body": body}, user=user)
        return int(cur.lastrowid)

    def notes(self, property_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM notes WHERE property_id=? ORDER BY id DESC", (property_id,)))

    def audit(self, action: str, entity_type: str = "", entity_id: int | None = None, before: Any = None, after: Any = None, user: str = "admin") -> None:
        self.conn.execute("INSERT INTO audit_log(user_name,action,entity_type,entity_id,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?)",
                          (user, action, entity_type, entity_id, json.dumps(before or {}, default=str), json.dumps(after or {}, default=str), now()))
        self.conn.commit()

    def record_event(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self.conn.execute("INSERT INTO app_events(event_name,payload_json,created_at) VALUES(?,?,?)", (name, json.dumps(payload or {}), now()))
        self.conn.commit()

    @staticmethod
    def migrate_v2_database(source: Path, destination: Path) -> int:
        source = Path(source)
        destination = Path(destination)
        if not source.exists():
            raise FileNotFoundError(source)
        src = sqlite3.connect(source)
        try:
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "properties" not in tables:
                raise ValueError("The selected database is not a compatible LeadDesk V2 database.")
            count = int(src.execute("SELECT COUNT(*) FROM properties").fetchone()[0])
        finally:
            src.close()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        # Opening upgrades compatible schema in place.
        repo = Repository(destination)
        repo.record_event("v2_migration", {"source": str(source), "properties": count})
        repo.close()
        return count
