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
from leaddesk_ai.services.calculations import analyze_deal, estimate_arv


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
        self._ensure_deal_columns()
        self._ensure_buyer_offer_columns()
        self._ensure_comparable_columns()
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

    def _ensure_deal_columns(self) -> None:
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(deals)")}
        additions = {
            "purchase_price": "REAL NOT NULL DEFAULT 0",
            "marketing_costs": "REAL NOT NULL DEFAULT 0",
            "misc_costs": "REAL NOT NULL DEFAULT 0",
            "total_investment": "REAL NOT NULL DEFAULT 0",
            "projected_profit": "REAL NOT NULL DEFAULT 0",
            "roi": "REAL NOT NULL DEFAULT 0",
            "deal_score": "TEXT NOT NULL DEFAULT 'Marginal'",
        }
        for column, definition in additions.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE deals ADD COLUMN {column} {definition}")

    def _ensure_buyer_offer_columns(self) -> None:
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(buyer_offers)")}
        additions = {
            "sent_date": "TEXT DEFAULT ''",
            "responded_date": "TEXT DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE buyer_offers ADD COLUMN {column} {definition}")

    def _ensure_comparable_columns(self) -> None:
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(comparable_sales)")}
        additions = {
            "bedrooms": "REAL", "bathrooms": "REAL", "lot_size": "REAL",
            "selected": "INTEGER NOT NULL DEFAULT 1",
        }
        for column, definition in additions.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE comparable_sales ADD COLUMN {column} {definition}")

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

    def update_property_profile(
        self,
        property_id: int,
        *,
        address: str,
        city: str = "",
        state: str = "",
        zip_code: str = "",
        county: str = "",
        apn: str = "",
        property_type: str = "",
        owner_name: str = "",
        mailing_address: str = "",
        phone: str = "",
        email: str = "",
    ) -> None:
        address = address.strip()
        if not address:
            raise ValueError("Property address is required.")
        before = self.property_details(property_id)
        if before is None:
            raise ValueError("Property not found.")
        stamp = now()
        with self.conn:
            self.conn.execute(
                """UPDATE properties SET address=?,city=?,state=?,zip=?,county=?,apn=?,property_type=?,updated_at=? WHERE id=?""",
                (address.strip(), city.strip(), state.strip(), zip_code.strip(), county.strip(), apn.strip(), property_type.strip(), stamp, property_id),
            )
            owner = self.conn.execute("SELECT id FROM owners WHERE property_id=? ORDER BY id LIMIT 1", (property_id,)).fetchone()
            if owner:
                owner_id = int(owner["id"])
                self.conn.execute(
                    "UPDATE owners SET name=?,mailing_address=? WHERE id=?",
                    (owner_name.strip(), mailing_address.strip(), owner_id),
                )
            else:
                cur = self.conn.execute(
                    "INSERT INTO owners(property_id,name,mailing_address,created_at) VALUES(?,?,?,?)",
                    (property_id, owner_name.strip(), mailing_address.strip(), stamp),
                )
                owner_id = int(cur.lastrowid)
            self._upsert_primary_contact(owner_id, "phone", phone.strip(), stamp)
            self._upsert_primary_contact(owner_id, "email", email.strip(), stamp)
            self.conn.execute(
                "INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                (property_id, "Profile Updated", "Property and owner profile updated", "admin", stamp),
            )
        self.audit("update_property_profile", "property", property_id, before=dict(before), after={"address": address, "owner_name": owner_name})

    def _upsert_primary_contact(self, owner_id: int, contact_type: str, value: str, stamp: str) -> None:
        row = self.conn.execute(
            "SELECT id FROM contacts WHERE owner_id=? AND type=? ORDER BY is_primary DESC,id LIMIT 1",
            (owner_id, contact_type),
        ).fetchone()
        if row:
            if value:
                self.conn.execute("UPDATE contacts SET value=?,is_primary=1 WHERE id=?", (value, int(row["id"])))
            else:
                self.conn.execute("DELETE FROM contacts WHERE id=?", (int(row["id"]),))
        elif value:
            self.conn.execute(
                "INSERT INTO contacts(owner_id,type,value,label,is_clean,is_primary,created_at) VALUES(?,?,?,'Manual',0,1,?)",
                (owner_id, contact_type, value, stamp),
            )

    def add_task(self, property_id: int, title: str, due_date: str = "", priority: str = "Normal") -> int:
        title = title.strip()
        if not title:
            raise ValueError("Task title is required.")
        if priority not in self.PRIORITIES:
            raise ValueError("Invalid priority.")
        if due_date:
            try:
                datetime.strptime(due_date, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("Task due date must use YYYY-MM-DD.") from exc
        if self.property_details(property_id) is None:
            raise ValueError("Property not found.")
        stamp = now()
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO tasks(property_id,title,due_date,status,priority,created_at) VALUES(?,?,?,'Open',?,?)",
                (property_id, title, due_date, priority, stamp),
            )
            self.conn.execute(
                "INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                (property_id, "Task Added", title, "admin", stamp),
            )
        self.audit("add_task", "task", int(cur.lastrowid), after={"property_id": property_id, "title": title})
        return int(cur.lastrowid)

    def list_tasks(self, property_id: int, include_completed: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM tasks WHERE property_id=?"
        args: list[Any] = [property_id]
        if not include_completed:
            sql += " AND status='Open'"
        sql += " ORDER BY CASE status WHEN 'Open' THEN 1 ELSE 2 END, CASE priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 WHEN 'Normal' THEN 3 ELSE 4 END, due_date, id DESC"
        return list(self.conn.execute(sql, args))

    def set_task_completed(self, task_id: int, completed: bool = True) -> None:
        task = self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task is None:
            raise ValueError("Task not found.")
        status = "Completed" if completed else "Open"
        with self.conn:
            self.conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
            self.conn.execute(
                "INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                (task["property_id"], "Task Completed" if completed else "Task Reopened", task["title"], "admin", now()),
            )
        self.audit("complete_task" if completed else "reopen_task", "task", task_id, after={"status": status})

    def activities(self, property_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM activities WHERE property_id=? ORDER BY id DESC", (property_id,)))
    def save_deal_analysis(
        self, property_id: int, *, arv: float, purchase_price: float, repairs: float = 0,
        closing_costs: float = 0, holding_costs: float = 0, marketing_costs: float = 0,
        misc_costs: float = 0, wholesale_fee: float = 10000, target_pct: float = 0.70,
    ) -> int:
        if self.property_details(property_id) is None:
            raise ValueError("Property not found.")
        summary = analyze_deal(
            arv=arv, purchase_price=purchase_price, repairs=repairs, closing_costs=closing_costs,
            holding_costs=holding_costs, marketing_costs=marketing_costs, misc_costs=misc_costs,
            wholesale_fee=wholesale_fee, target_pct=target_pct,
        )
        pct = target_pct / 100 if target_pct > 1 else target_pct
        stamp = now()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO deals(property_id,arv,repairs,target_pct,wholesale_fee,closing_costs,holding_costs,buyer_price,
                purchase_price,marketing_costs,misc_costs,mao,total_investment,projected_profit,roi,deal_score,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (property_id, arv, repairs, pct, wholesale_fee, closing_costs, holding_costs, summary["buyer_price"],
                 purchase_price, marketing_costs, misc_costs, summary["mao"], summary["total_investment"],
                 summary["projected_profit"], summary["roi"], summary["deal_score"], "Analyzing", stamp),
            )
            self.conn.execute(
                "INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                (property_id, "Deal Analysis Saved", f"MAO: ${summary['mao']:,.2f}; Profit: ${summary['projected_profit']:,.2f}; Score: {summary['deal_score']}", "admin", stamp),
            )
        deal_id = int(cur.lastrowid)
        self.audit("save_deal_analysis", "deal", deal_id, after={"property_id": property_id, **summary})
        return deal_id

    def list_deal_analyses(self, property_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM deals WHERE property_id=? ORDER BY id DESC", (property_id,)))
    # --- Buyer CRM and offer pipeline ---
    BUYER_OFFER_STATUSES = ("New", "Sent", "Opened", "Interested", "Negotiating", "Under Contract", "Closed", "Passed")

    # ---------- Comparable sales and offer builder ----------
    def add_comparable_sale(self, property_id: int, *, address: str, sold_price: float, sold_date: str = "",
                            square_feet: float = 0, bedrooms: float = 0, bathrooms: float = 0,
                            lot_size: float = 0, distance_miles: float = 0, condition_notes: str = "",
                            source: str = "", verified: bool = False, selected: bool = True) -> int:
        if self.property_details(property_id) is None:
            raise ValueError("Property not found.")
        address = address.strip()
        if not address:
            raise ValueError("Comparable address is required.")
        numeric = [sold_price, square_feet, bedrooms, bathrooms, lot_size, distance_miles]
        if any(float(v or 0) < 0 for v in numeric):
            raise ValueError("Comparable values cannot be negative.")
        if float(sold_price) <= 0:
            raise ValueError("Sold price must be greater than zero.")
        if sold_date:
            try: datetime.strptime(sold_date, "%Y-%m-%d")
            except ValueError as exc: raise ValueError("Sold date must use YYYY-MM-DD.") from exc
        stamp = now()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO comparable_sales(property_id,address,sold_price,sold_date,square_feet,distance_miles,bedrooms,bathrooms,lot_size,condition_notes,source,verified,selected,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (property_id,address.strip(),float(sold_price),sold_date,float(square_feet or 0),float(distance_miles or 0),float(bedrooms or 0),float(bathrooms or 0),float(lot_size or 0),condition_notes.strip(),source.strip(),int(verified),int(selected),stamp))
            comp_id=int(cur.lastrowid)
            self.conn.execute("INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                              (property_id,"Comparable Added",f"{address} — ${float(sold_price):,.2f}","admin",stamp))
        self.audit("add_comparable_sale","comparable_sale",comp_id,after={"property_id":property_id,"address":address,"sold_price":sold_price})
        return comp_id

    def list_comparable_sales(self, property_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM comparable_sales WHERE property_id=? ORDER BY sold_date DESC,id DESC",(property_id,)))

    def set_comparable_selected(self, comp_id: int, selected: bool) -> None:
        with self.conn:
            cur=self.conn.execute("UPDATE comparable_sales SET selected=? WHERE id=?",(int(selected),comp_id))
        if cur.rowcount == 0: raise ValueError("Comparable sale not found.")

    def delete_comparable_sale(self, comp_id: int) -> None:
        with self.conn:
            cur=self.conn.execute("DELETE FROM comparable_sales WHERE id=?",(comp_id,))
        if cur.rowcount == 0: raise ValueError("Comparable sale not found.")

    def comparable_arv(self, property_id: int) -> dict[str, float]:
        prop=self.property_details(property_id)
        if prop is None: raise ValueError("Property not found.")
        comps=[dict(r) for r in self.list_comparable_sales(property_id)]
        return estimate_arv(comps,float(prop["square_feet"] or 0))

    def save_offer_scenario(self, property_id: int, *, suggested_arv: float, seller_offer: float,
                            buyer_price: float, assignment_fee: float, notes: str = "") -> int:
        if self.property_details(property_id) is None: raise ValueError("Property not found.")
        if any(float(v) < 0 for v in (suggested_arv,seller_offer,buyer_price,assignment_fee)):
            raise ValueError("Offer values cannot be negative.")
        estimated_profit=round(float(buyer_price)-float(seller_offer),2)
        stamp=now()
        with self.conn:
            cur=self.conn.execute("""INSERT INTO offer_scenarios(property_id,suggested_arv,seller_offer,buyer_price,assignment_fee,estimated_profit,notes,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",(property_id,suggested_arv,seller_offer,buyer_price,assignment_fee,estimated_profit,notes.strip(),stamp))
            offer_id=int(cur.lastrowid)
            self.conn.execute("INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                (property_id,"Offer Scenario Saved",f"Seller: ${seller_offer:,.2f}; Buyer: ${buyer_price:,.2f}; Spread: ${estimated_profit:,.2f}","admin",stamp))
        self.audit("save_offer_scenario","offer_scenario",offer_id,after={"property_id":property_id,"seller_offer":seller_offer,"buyer_price":buyer_price})
        return offer_id

    def list_offer_scenarios(self, property_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM offer_scenarios WHERE property_id=? ORDER BY id DESC",(property_id,)))

    def list_buyers(self, search: str = "", active_only: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM buyers WHERE 1=1"
        args: list[Any] = []
        if active_only:
            sql += " AND active=1"
        if search.strip():
            term = f"%{search.strip()}%"
            sql += " AND (name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ? OR markets LIKE ? OR counties LIKE ? OR zip_codes LIKE ? OR property_types LIKE ? OR funding_type LIKE ?)"
            args.extend([term] * 9)
        return list(self.conn.execute(sql + " ORDER BY active DESC, name COLLATE NOCASE", args))

    def buyer(self, buyer_id: int) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM buyers WHERE id=?", (buyer_id,)).fetchone()
        if row is None:
            raise ValueError("Buyer not found.")
        return dict(row)

    def save_buyer(self, values: dict[str, Any], buyer_id: int | None = None) -> int:
        name = str(values.get("name", "")).strip()
        if not name:
            raise ValueError("Buyer name is required.")

        def optional_float(key: str) -> float | None:
            value = values.get(key)
            if value in (None, ""):
                return None
            parsed = float(value)
            if parsed < 0:
                raise ValueError(f"{key.replace('_', ' ').title()} cannot be negative.")
            return parsed

        close_days = values.get("avg_close_days")
        close_days = None if close_days in (None, "") else int(close_days)
        if close_days is not None and close_days < 0:
            raise ValueError("Average close days cannot be negative.")
        data = (
            name, str(values.get("company", "")).strip(), str(values.get("email", "")).strip(),
            str(values.get("phone", "")).strip(), str(values.get("markets", "")).strip(),
            str(values.get("property_types", "")).strip(), optional_float("min_price"), optional_float("max_price"),
            str(values.get("rehab_level", "")).strip(), str(values.get("funding_type", "")).strip(),
            str(values.get("zip_codes", "")).strip(), str(values.get("counties", "")).strip(), close_days,
            int(bool(values.get("active", True))), str(values.get("notes", "")).strip(),
        )
        if data[6] is not None and data[7] is not None and data[6] > data[7]:
            raise ValueError("Minimum price cannot be greater than maximum price.")
        if buyer_id is not None:
            before = self.buyer(buyer_id)
            with self.conn:
                self.conn.execute(
                    """UPDATE buyers SET name=?,company=?,email=?,phone=?,markets=?,property_types=?,min_price=?,max_price=?,
                    rehab_level=?,funding_type=?,zip_codes=?,counties=?,avg_close_days=?,active=?,notes=? WHERE id=?""",
                    data + (buyer_id,),
                )
            self.audit("update_buyer", "buyer", buyer_id, before=before, after=values)
            return buyer_id
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO buyers(name,company,email,phone,markets,property_types,min_price,max_price,rehab_level,
                funding_type,zip_codes,counties,avg_close_days,active,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                data + (now(),),
            )
        new_id = int(cur.lastrowid)
        self.audit("create_buyer", "buyer", new_id, after=values)
        return new_id

    def delete_buyer(self, buyer_id: int) -> None:
        before = self.buyer(buyer_id)
        with self.conn:
            self.conn.execute("DELETE FROM buyers WHERE id=?", (buyer_id,))
        self.audit("delete_buyer", "buyer", buyer_id, before=before)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {item.strip().lower() for item in str(text or "").replace(";", ",").split(",") if item.strip()}

    def latest_deal(self, property_id: int) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM deals WHERE property_id=? ORDER BY id DESC LIMIT 1", (property_id,)).fetchone()
        return dict(row) if row else {}

    def match_buyers(self, property_id: int) -> list[dict[str, Any]]:
        details = self.property_details(property_id)
        if details is None:
            raise ValueError("Property not found.")
        prop = dict(details)
        deal = self.latest_deal(property_id)
        price = float(deal.get("buyer_price") or deal.get("mao") or 0)
        results: list[dict[str, Any]] = []
        for row in self.list_buyers(active_only=True):
            buyer = dict(row)
            score = 0
            reasons: list[str] = []
            state = str(prop.get("state") or "").strip().lower()
            county = str(prop.get("county") or "").strip().lower()
            zipcode = str(prop.get("zip") or "").strip().lower()
            property_type = str(prop.get("property_type") or "").strip().lower()
            markets = self._tokens(buyer.get("markets", ""))
            counties = self._tokens(buyer.get("counties", ""))
            zip_codes = self._tokens(buyer.get("zip_codes", ""))
            property_types = self._tokens(buyer.get("property_types", ""))
            if zipcode and zipcode in zip_codes:
                score += 35; reasons.append("ZIP match")
            elif county and any(county in item or item in county for item in counties):
                score += 25; reasons.append("county match")
            elif state and any(state == item or state in item for item in markets):
                score += 15; reasons.append("market/state match")
            if property_type and any(property_type == item or property_type in item or item in property_type for item in property_types):
                score += 20; reasons.append("property type match")
            elif not property_types:
                score += 5; reasons.append("property type unrestricted")
            min_price, max_price = buyer.get("min_price"), buyer.get("max_price")
            if price:
                if (min_price is None or price >= float(min_price)) and (max_price is None or price <= float(max_price)):
                    score += 25; reasons.append("price in buy box")
                else:
                    reasons.append("price outside buy box")
            else:
                reasons.append("deal price not entered")
            if buyer.get("funding_type"):
                score += 5
            if buyer.get("avg_close_days") and int(buyer["avg_close_days"]) <= 21:
                score += 5; reasons.append("fast closer")
            buyer.update(
                match_score=min(score, 100),
                match_label="Strong" if score >= 65 else "Possible" if score >= 35 else "Weak",
                match_reasons=", ".join(reasons),
                target_price=price,
            )
            results.append(buyer)
        return sorted(results, key=lambda item: (-item["match_score"], item["name"].lower()))

    def add_buyer_offer(self, property_id: int, buyer_id: int, amount: float, status: str = "New",
                        proof_of_funds: bool = False, notes: str = "", sent_date: str = "", responded_date: str = "") -> int:
        if self.property_details(property_id) is None:
            raise ValueError("Property not found.")
        self.buyer(buyer_id)
        amount = float(amount)
        if amount < 0:
            raise ValueError("Offer amount cannot be negative.")
        if status not in self.BUYER_OFFER_STATUSES:
            raise ValueError("Invalid offer status.")
        for label, date_value in (("Sent date", sent_date), ("Responded date", responded_date)):
            if date_value:
                try:
                    datetime.strptime(date_value, "%Y-%m-%d")
                except ValueError as exc:
                    raise ValueError(f"{label} must use YYYY-MM-DD.") from exc
        stamp = now()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO buyer_offers(property_id,buyer_id,amount,proof_of_funds,status,notes,sent_date,responded_date,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (property_id, buyer_id, amount, int(proof_of_funds), status, notes.strip(), sent_date, responded_date, stamp),
            )
            buyer_name = self.conn.execute("SELECT name FROM buyers WHERE id=?", (buyer_id,)).fetchone()["name"]
            self.conn.execute(
                "INSERT INTO activities(property_id,activity_type,details,created_by,created_at) VALUES(?,?,?,?,?)",
                (property_id, "Buyer Pipeline", f"{buyer_name} — ${amount:,.2f} ({status})", "admin", stamp),
            )
        offer_id = int(cur.lastrowid)
        self.audit("add_buyer_offer", "buyer_offer", offer_id, after={"property_id": property_id, "buyer_id": buyer_id, "amount": amount, "status": status})
        return offer_id

    def list_buyer_offers(self, property_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            """SELECT bo.*, COALESCE(b.name,'Deleted buyer') buyer_name, COALESCE(b.company,'') company
            FROM buyer_offers bo LEFT JOIN buyers b ON b.id=bo.buyer_id
            WHERE bo.property_id=? ORDER BY bo.id DESC""",
            (property_id,),
        ))

