from pathlib import Path
import sqlite3
from leaddesk_ai.db.repository import Repository
from leaddesk_ai.services.backup import create_backup


def test_verified_backup(tmp_path: Path):
    source = tmp_path / "source.db"
    repo = Repository(source); repo.close()
    target = create_backup(source, tmp_path / "backups")
    assert target.exists()
    conn = sqlite3.connect(target)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
