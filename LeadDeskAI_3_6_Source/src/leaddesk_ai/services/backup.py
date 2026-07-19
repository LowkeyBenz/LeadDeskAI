from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from leaddesk_ai.core.paths import BACKUP_DIR


def create_backup(source: Path, backup_dir: Path | None = None) -> Path:
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(source)
    target_dir = Path(backup_dir or BACKUP_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"leaddesk_{datetime.now():%Y%m%d_%H%M%S}.db"
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    verify = sqlite3.connect(target)
    try:
        result = verify.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Backup integrity check failed: {result}")
    finally:
        verify.close()
    return target
