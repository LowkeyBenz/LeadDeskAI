from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from leaddesk_ai.core.logging_config import configure_logging
from leaddesk_ai.db.repository import Repository
from leaddesk_ai.ui.main_window import MainWindow


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("LeadDesk AI")
    try:
        repo = Repository()
        window = MainWindow(repo)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "LeadDesk AI could not start", str(exc))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
