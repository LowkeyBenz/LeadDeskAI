from __future__ import annotations
import os
from pathlib import Path


def project_root() -> Path:
    override = os.getenv("LEADDESK_HOME")
    if override:
        return Path(override).expanduser().resolve()
    # src/leaddesk_ai/core/paths.py -> project root
    return Path(__file__).resolve().parents[3]

ROOT = project_root()
DATA_DIR = ROOT / "data"
BACKUP_DIR = ROOT / "backups"
LOG_DIR = ROOT / "logs"
DB_PATH = DATA_DIR / "leaddesk_v3.db"

for directory in (DATA_DIR, BACKUP_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)
