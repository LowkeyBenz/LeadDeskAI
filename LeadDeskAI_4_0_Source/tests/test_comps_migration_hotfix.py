import sqlite3
from pathlib import Path

from leaddesk_ai.db.repository import Repository


def test_existing_comparable_sales_table_without_selected_is_upgraded(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE schema_meta(version INTEGER NOT NULL);
        INSERT INTO schema_meta(version) VALUES(8);
        CREATE TABLE properties(
          id INTEGER PRIMARY KEY, lead_code TEXT UNIQUE, market TEXT DEFAULT '', county TEXT DEFAULT '',
          address TEXT DEFAULT '', city TEXT DEFAULT '', state TEXT DEFAULT '', zip TEXT DEFAULT '', apn TEXT DEFAULT '',
          property_type TEXT DEFAULT '', bedrooms REAL, bathrooms REAL, square_feet REAL,
          source_file TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'New', priority TEXT NOT NULL DEFAULT 'Normal',
          follow_up_date TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE comparable_sales(
          id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
          address TEXT NOT NULL, sold_price REAL NOT NULL DEFAULT 0, sold_date TEXT DEFAULT '', square_feet REAL,
          distance_miles REAL, condition_notes TEXT DEFAULT '', source TEXT DEFAULT '',
          verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    repo = Repository(db_path)
    columns = {row["name"] for row in repo.conn.execute("PRAGMA table_info(comparable_sales)")}
    assert "selected" in columns
    repo.close()
