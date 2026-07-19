from pathlib import Path
from leaddesk_ai.db.repository import Repository


def test_database_initializes(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    assert repo.stats()["properties"] == 0
    version = repo.conn.execute("SELECT version FROM schema_meta").fetchone()[0]
    assert version == 11
    repo.close()


def test_note_requires_body(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    try:
        repo.add_note(1, "   ")
        assert False
    except ValueError:
        pass
    repo.close()
