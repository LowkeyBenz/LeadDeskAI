from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .schema import SCHEMA_SQL, SCHEMA_VERSION
from leaddesk_ai.core.paths import DB_PATH


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Repository:
    PROPERTY_STATUSES = ("New", "Contacted", "Follow-Up", "Offer Made", "Under Contract", "Closed", "Dead")
    PRIORITIES = ("Low", "Normal", "High", "Urgent")

    def __init__(self, path: Path | None = None):
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self._ensure_property_columns()
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

    def _ensure_property_columns(self) -> None:
        """Apply small additive migrations safely to older Version 3 databases."""
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(properties)")}
        additions = {
            "priority": "TEXT NOT NULL DEFAULT 'Normal'",
            "follow_up_date": "TEXT DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE properties ADD COLUMN {column} {definition}")

    def close(self) -> None:
        self.conn.close()

    def stats(self) -> dict[str, int]:
        q = self.conn.execute
        today = datetime.now().date().isoformat()
        return {
            "properties": q("SELECT COUNT(*) c FROM properties").fetchone()["c"],
            "new_leads": q("SELECT COUNT(*) c FROM properties WHERE status='New'").fetchone()["c"],
            "follow_ups_due": q(
                "SELECT COUNT(*) c FROM properties WHERE follow_up_date<>'' AND follow_up_date<=? AND status NOT IN ('Closed','Dead')",
                (today,),
            ).fetchone()["c"],
            "open_tasks": q("SELECT COUNT(*) c FROM tasks WHERE status='Open'").fetchone()["c"],
            "buyers": q("SELECT COUNT(*) c FROM buyers WHERE active=1").fetchone()["c"],
            "restricted": q("SELECT COUNT(*) c FROM communication_preferences WHERE internal_dnc=1 OR opt_out=1").fetchone()["c"],
        }

    def list_properties(self, search: str = "", status: str = "All", priority: str = "All") -> list[sqlite3.Row]:
        sql = """SELECT p.*, COALESCE(o.name,'') owner_name,
                 COALESCE((SELECT value FROM contacts c WHERE c.owner_id=o.id AND c.type='phone' ORDER BY c.is_primary DESC,c.id LIMIT 1),'') phone,
                 COALESCE((SELECT value FROM contacts c WHERE c.owner_id=o.id AND c.type='email' ORDER BY c.is_primary DESC,c.id LIMIT 1),'') email,
                 COALESCE(cp.internal_dnc,0) internal_dnc, COALESCE(cp.opt_out,0) opt_out
                 FROM properties p
                 LEFT JOIN owners o ON o.property_id=p.id
                 LEFT JOIN communication_preferences cp ON cp.property_id=p.id
                 WHERE 1=1"""
        args: list[Any] = []
        if search.strip():
            term = f"%{search.strip()}%"
            sql += " AND (p.address LIKE ? OR p.city LIKE ? OR p.state LIKE ? OR p.zip LIKE ? OR p.apn LIKE ? OR o.name LIKE ? OR EXISTS (SELECT 1 FROM contacts sc WHERE sc.owner_id=o.id AND sc.value LIKE ?))"
            args.extend([term] * 7)
        if status and status != "All":
            sql += " AND p.status=?"
            args.append(status)
        if priority and priority != "All":
            sql += " AND p.priority=?"
            args.append(priority)
        return list(self.conn.execute(sql + " ORDER BY CASE p.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 WHEN 'Normal' THEN 3 ELSE 4 END, p.id DESC", args))

    def property_details(self, property_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT p.*, COALESCE(o.name,'') owner_name, COALESCE(o.mailing_address,'') mailing_address,
            COALESCE((SELECT value FROM contacts c WHERE c.owner_id=o.id AND c.type='phone' ORDER BY c.is_primary DESC,c.id LIMIT 1),'') phone,
            COALESCE((SELECT value FROM contacts c WHERE c.owner_id=o.id AND c.type='email' ORDER BY c.is_primary DESC,c.id LIMIT 1),'') email,
            COALESCE(cp.internal_dnc,0) internal_dnc, COALESCE(cp.opt_out,0) opt_out,
            COALESCE(cp.call_allowed,0) call_allowed, COALESCE(cp.text_allowed,0) text_allowed,
            COALESCE(cp.email_allowed,0) email_allowed, COALESCE(cp.mail_allowed,1) mail_allowed
            FROM properties p LEFT JOIN owners o ON o.property_id=p.id
            LEFT JOIN communication_preferences cp ON cp.property_id=p.id WHERE p.id=?""",
            (property_id,),
        ).fetchone()

    def update_property_workflow(self, property_id: int, status: str, priority: str, follow_up_date: str = "") -> None:
        if status not in self.PROPERTY_STATUSES:
            raise ValueError("Invalid lead status.")
        if priority not in self.PRIORITIES:
            raise ValueError("Invalid priority.")
        if follow_up_date:
            try:
                datetime.strptime(follow_up_date, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("Follow-up date must use YYYY-MM-DD.") from exc
        before = self.property_details(property_id)
        if before is None:
            raise ValueError("Property not found.")
        with self.conn:
            self.conn.execute(
                "UPDATE properties SET status=?, priority=?, follow_up_date=?, updated_at=? WHERE id=?",
                (status, priority, follow_up_date, now(), property_id),
            )
            self.conn.execute(
                "INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                (property_id, "Workflow Updated", f"Status: {status}; Priority: {priority}; Follow-up: {follow_up_date or 'None'}", "admin", now()),
            )
        self.audit("update_workflow", "property", property_id, before=dict(before), after={"status": status, "priority": priority, "follow_up_date": follow_up_date})

    def set_contact_restrictions(self, property_id: int, internal_dnc: bool, opt_out: bool) -> None:
        stamp = now()
        with self.conn:
            self.conn.execute(
                """INSERT INTO communication_preferences(property_id,internal_dnc,opt_out,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(property_id) DO UPDATE SET
                internal_dnc=excluded.internal_dnc,opt_out=excluded.opt_out,updated_at=excluded.updated_at""",
                (property_id, int(internal_dnc), int(opt_out), stamp),
            )
        self.audit("update_contact_restrictions", "property", property_id, after={"internal_dnc": internal_dnc, "opt_out": opt_out})

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

    @staticmethod
    def _pick(row: dict[str, str], aliases: Iterable[str]) -> str:
        normalized = {str(k).strip().lower().replace(" ", "_"): str(v or "").strip() for k, v in row.items()}
        for alias in aliases:
            value = normalized.get(alias.lower().replace(" ", "_"), "")
            if value:
                return value
        return ""

    def import_leads_csv(self, csv_path: Path) -> dict[str, int]:
        """Import a common lead-list CSV and skip likely duplicates.

        Duplicate identity is APN when available, otherwise normalized property address/city/state/ZIP.
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(path)
        added = skipped = failed = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV must contain a header row.")
            for source_row in reader:
                try:
                    address = self._pick(source_row, ("property_address", "address", "property_street", "street_address", "property_street_address"))
                    city = self._pick(source_row, ("property_city", "city"))
                    state = self._pick(source_row, ("property_state", "state"))
                    zip_code = self._pick(source_row, ("property_zip", "zip", "zipcode", "postal_code"))
                    apn = self._pick(source_row, ("apn", "parcel_number", "parcel", "account_number"))
                    owner = self._pick(source_row, ("owner_name", "owner", "name", "mailing_name"))
                    phone = self._pick(source_row, ("phone", "phone_1", "phone1", "primary_phone", "mobile"))
                    email = self._pick(source_row, ("email", "email_1", "email1", "primary_email"))
                    mailing_address = self._pick(source_row, ("mailing_address", "owner_address", "mail_address"))
                    market = self._pick(source_row, ("market",))
                    county = self._pick(source_row, ("county", "property_county"))
                    property_type = self._pick(source_row, ("property_type", "type"))
                    if not address and not apn:
                        failed += 1
                        continue
                    duplicate = None
                    if apn:
                        duplicate = self.conn.execute("SELECT id FROM properties WHERE apn=? AND apn<>'' LIMIT 1", (apn,)).fetchone()
                    if duplicate is None and address:
                        duplicate = self.conn.execute(
                            "SELECT id FROM properties WHERE lower(trim(address))=lower(trim(?)) AND lower(trim(city))=lower(trim(?)) AND lower(trim(state))=lower(trim(?)) AND trim(zip)=trim(?) LIMIT 1",
                            (address, city, state, zip_code),
                        ).fetchone()
                    if duplicate:
                        skipped += 1
                        continue
                    stamp = now()
                    with self.conn:
                        cur = self.conn.execute(
                            """INSERT INTO properties(lead_code,market,county,address,city,state,zip,apn,property_type,source_file,status,priority,follow_up_date,created_at,updated_at)
                            VALUES(NULL,?,?,?,?,?,?,?,?,?,'New','Normal','',?,?)""",
                            (market, county, address, city, state, zip_code, apn, property_type, path.name, stamp, stamp),
                        )
                        property_id = int(cur.lastrowid)
                        owner_cur = self.conn.execute(
                            "INSERT INTO owners(property_id,name,mailing_address,created_at) VALUES(?,?,?,?)",
                            (property_id, owner, mailing_address, stamp),
                        )
                        owner_id = int(owner_cur.lastrowid)
                        if phone:
                            self.conn.execute("INSERT INTO contacts(owner_id,type,value,label,is_clean,is_primary,created_at) VALUES(?,'phone',?,'Imported',0,1,?)", (owner_id, phone, stamp))
                        if email:
                            self.conn.execute("INSERT INTO contacts(owner_id,type,value,label,is_clean,is_primary,created_at) VALUES(?,'email',?,'Imported',0,1,?)", (owner_id, email, stamp))
                        self.conn.execute("INSERT INTO communication_preferences(property_id,updated_at) VALUES(?,?)", (property_id, stamp))
                    added += 1
                except (sqlite3.Error, ValueError, TypeError):
                    failed += 1
        self.audit("import_csv", "file", after={"file": path.name, "added": added, "skipped": skipped, "failed": failed})
        return {"added": added, "skipped": skipped, "failed": failed}

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
        repo = Repository(destination)
        repo.record_event("v2_migration", {"source": str(source), "properties": count})
        repo.close()
        return count
