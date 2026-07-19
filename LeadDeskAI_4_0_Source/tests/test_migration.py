import sqlite3
from pathlib import Path
from leaddesk_ai.db.repository import Repository


def test_v2_migration_preserves_properties(tmp_path: Path):
    source = tmp_path / "v2.db"
    conn = sqlite3.connect(source)
    conn.executescript("""
    CREATE TABLE properties(id INTEGER PRIMARY KEY, lead_code TEXT UNIQUE, market TEXT, county TEXT,address TEXT,city TEXT,state TEXT,zip TEXT,apn TEXT,property_type TEXT,bedrooms REAL,bathrooms REAL,square_feet REAL,source_file TEXT,status TEXT,created_at TEXT,updated_at TEXT);
    INSERT INTO properties VALUES(1,'L1','Phoenix','Maricopa','123 Main','Phoenix','AZ','85001','','Single Family',3,2,1500,'pilot.csv','New','2026-01-01','2026-01-01');
    """)
    conn.commit(); conn.close()
    destination = tmp_path / "v3.db"
    count = Repository.migrate_v2_database(source, destination)
    assert count == 1
    repo = Repository(destination)
    assert repo.stats()["properties"] == 1
    repo.close()
