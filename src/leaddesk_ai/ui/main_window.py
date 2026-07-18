from __future__ import annotations
import logging
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget
)
from leaddesk_ai.core.paths import DB_PATH
from leaddesk_ai.db.repository import Repository
from leaddesk_ai.services.backup import create_backup

log = logging.getLogger(__name__)


class DashboardPage(QWidget):
    def __init__(self, repo: Repository):
        super().__init__(); self.repo = repo
        self.layout = QVBoxLayout(self)
        title = QLabel("LeadDesk AI — Command Dashboard"); title.setObjectName("pageTitle")
        self.layout.addWidget(title)
        self.stats = QLabel(); self.stats.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.stats); self.layout.addStretch()
        self.refresh()

    def refresh(self):
        s = self.repo.stats()
        self.stats.setText(f"Properties: {s['properties']}\nOpen tasks: {s['open_tasks']}\nActive buyers: {s['buyers']}\nRestricted contacts: {s['restricted']}")


class PropertiesPage(QWidget):
    def __init__(self, repo: Repository):
        super().__init__(); self.repo = repo
        layout = QVBoxLayout(self)
        title = QLabel("Properties"); title.setObjectName("pageTitle"); layout.addWidget(title)
        row = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText("Search owner, address, city, or ZIP")
        button = QPushButton("Search"); button.clicked.connect(self.refresh); row.addWidget(self.search); row.addWidget(button); layout.addLayout(row)
        self.table = QTableWidget(0, 7); self.table.setHorizontalHeaderLabels(["ID","Owner","Address","City","State","ZIP","Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_selected); layout.addWidget(self.table)
        self.note = QTextEdit(); self.note.setPlaceholderText("Select a property, type a note, then click Add Note")
        add_note = QPushButton("Add Note to Selected Property"); add_note.clicked.connect(self.add_note)
        layout.addWidget(self.note); layout.addWidget(add_note); self.refresh()

    def refresh(self):
        rows = self.repo.list_properties(self.search.text())
        self.table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            values = [item['id'], item['owner_name'], item['address'], item['city'], item['state'], item['zip'], item['status']]
            for c, value in enumerate(values): self.table.setItem(r, c, QTableWidgetItem(str(value or "")))
        self.table.resizeColumnsToContents()

    def selected_property_id(self):
        row = self.table.currentRow()
        return int(self.table.item(row, 0).text()) if row >= 0 else None

    def add_note(self):
        property_id = self.selected_property_id()
        if not property_id: QMessageBox.warning(self, "Select property", "Select a property first."); return
        try:
            self.repo.add_note(property_id, self.note.toPlainText()); self.note.clear()
            QMessageBox.information(self, "Saved", "The note was saved and added to the audit timeline.")
        except ValueError as exc: QMessageBox.warning(self, "Cannot save", str(exc))

    def open_selected(self):
        property_id = self.selected_property_id()
        if not property_id: return
        notes = self.repo.notes(property_id)
        body = "\n\n".join(f"{n['created_at']} — {n['body']}" for n in notes) or "No notes yet."
        QMessageBox.information(self, f"Property {property_id}", body)


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository):
        super().__init__(); self.repo = repo
        self.setWindowTitle("LeadDesk AI 3.0"); self.resize(1180, 760)
        root = QWidget(); self.setCentralWidget(root); layout = QHBoxLayout(root)
        self.nav = QListWidget(); self.nav.addItems(["Dashboard", "Properties", "Migration & Backup", "About"]); self.nav.setFixedWidth(210)
        self.pages = QStackedWidget(); self.dashboard = DashboardPage(repo); self.properties = PropertiesPage(repo)
        self.pages.addWidget(self.dashboard); self.pages.addWidget(self.properties); self.pages.addWidget(self.tools_page()); self.pages.addWidget(self.about_page())
        self.nav.currentRowChanged.connect(self.change_page); self.nav.setCurrentRow(0)
        layout.addWidget(self.nav); layout.addWidget(self.pages, 1)
        self.setStyleSheet("""
            QMainWindow { background: #f4f6f8; }
            QListWidget { font-size: 15px; padding: 8px; }
            QLabel#pageTitle { font-size: 24px; font-weight: 700; margin-bottom: 12px; }
            QPushButton { padding: 8px 14px; }
            QTableWidget { background: white; }
        """)

    def change_page(self, index: int):
        self.pages.setCurrentIndex(index)
        if index == 0: self.dashboard.refresh()
        if index == 1: self.properties.refresh()

    def tools_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("Migration & Backup"); title.setObjectName("pageTitle"); layout.addWidget(title)
        text = QLabel("Migrate a compatible Version 2 database, or create a verified backup of Version 3."); text.setWordWrap(True); layout.addWidget(text)
        migrate = QPushButton("Migrate Version 2 Database"); migrate.clicked.connect(self.migrate_v2); layout.addWidget(migrate)
        backup = QPushButton("Create Verified Backup"); backup.clicked.connect(self.backup); layout.addWidget(backup); layout.addStretch()
        return page

    def about_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("LeadDesk AI 3.0 Professional Foundation"); title.setObjectName("pageTitle"); layout.addWidget(title)
        label = QLabel("PySide6 desktop UI • SQLite database • migrations • audit logging • tested backups • Git-ready project\n\nAI, SMS, email, direct mail, and automatic negotiations are not enabled in this foundation release.")
        label.setWordWrap(True); layout.addWidget(label); layout.addStretch(); return page

    def migrate_v2(self):
        source, _ = QFileDialog.getOpenFileName(self, "Select Version 2 database", "", "SQLite Database (*.db);;All Files (*)")
        if not source: return
        answer = QMessageBox.question(self, "Replace current database?", "This will replace the current Version 3 database. A backup will be created first if it contains data. Continue?")
        if answer != QMessageBox.Yes: return
        try:
            self.repo.close()
            if DB_PATH.exists() and DB_PATH.stat().st_size:
                create_backup(DB_PATH)
            count = Repository.migrate_v2_database(Path(source), DB_PATH)
            self.repo = Repository(DB_PATH)
            self.dashboard.repo = self.repo; self.properties.repo = self.repo
            self.dashboard.refresh(); self.properties.refresh()
            QMessageBox.information(self, "Migration complete", f"Migrated {count} properties into LeadDesk AI 3.0.")
        except Exception as exc:
            log.exception("Migration failed")
            self.repo = Repository(DB_PATH)
            QMessageBox.critical(self, "Migration failed", str(exc))

    def backup(self):
        try:
            target = create_backup(DB_PATH)
            QMessageBox.information(self, "Backup complete", f"Verified backup created:\n{target}")
        except Exception as exc: QMessageBox.critical(self, "Backup failed", str(exc))

    def closeEvent(self, event):
        try:
            if DB_PATH.exists(): create_backup(DB_PATH)
            self.repo.close()
        finally: event.accept()
