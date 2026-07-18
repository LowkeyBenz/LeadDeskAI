from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from leaddesk_ai.core.paths import DB_PATH
from leaddesk_ai.db.repository import Repository
from leaddesk_ai.services.backup import create_backup

log = logging.getLogger(__name__)


class DashboardPage(QWidget):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        layout = QVBoxLayout(self)
        title = QLabel("LeadDesk AI — Revenue Dashboard")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.stats = QLabel()
        self.stats.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.stats)
        tip = QLabel("Start with leads that have overdue follow-ups or an Urgent/High priority. Always verify contact permissions before outreach.")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        s = self.repo.stats()
        self.stats.setText(
            f"Total properties: {s['properties']}\n"
            f"New leads: {s['new_leads']}\n"
            f"Follow-ups due: {s['follow_ups_due']}\n"
            f"Open tasks: {s['open_tasks']}\n"
            f"Active buyers: {s['buyers']}\n"
            f"Restricted contacts: {s['restricted']}"
        )


class PropertyDialog(QDialog):
    def __init__(self, repo: Repository, property_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.property_id = property_id
        self.setWindowTitle(f"Lead Workspace — Property {property_id}")
        self.resize(680, 620)
        layout = QVBoxLayout(self)
        details = repo.property_details(property_id)
        if details is None:
            raise ValueError("Property not found.")

        heading = QLabel(f"{details['address']}, {details['city']}, {details['state']} {details['zip']}")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        owner = QLabel(f"Owner: {details['owner_name'] or 'Unknown'}\nPhone: {details['phone'] or '—'}\nEmail: {details['email'] or '—'}")
        owner.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(owner)

        form = QFormLayout()
        self.status = QComboBox()
        self.status.addItems(repo.PROPERTY_STATUSES)
        self.status.setCurrentText(details["status"] or "New")
        self.priority = QComboBox()
        self.priority.addItems(repo.PRIORITIES)
        self.priority.setCurrentText(details["priority"] or "Normal")
        self.follow_up = QLineEdit(details["follow_up_date"] or "")
        self.follow_up.setPlaceholderText("YYYY-MM-DD")
        self.internal_dnc = QCheckBox("Internal do-not-contact")
        self.internal_dnc.setChecked(bool(details["internal_dnc"]))
        self.opt_out = QCheckBox("Contact opted out")
        self.opt_out.setChecked(bool(details["opt_out"]))
        form.addRow("Status", self.status)
        form.addRow("Priority", self.priority)
        form.addRow("Follow-up date", self.follow_up)
        form.addRow("Restrictions", self.internal_dnc)
        form.addRow("", self.opt_out)
        layout.addLayout(form)

        save = QPushButton("Save Lead Workflow")
        save.clicked.connect(self.save_workflow)
        layout.addWidget(save)

        notes_label = QLabel("Notes")
        notes_label.setStyleSheet("font-weight: 700; font-size: 16px;")
        layout.addWidget(notes_label)
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        layout.addWidget(self.history, 1)
        self.note = QTextEdit()
        self.note.setPlaceholderText("Add a seller conversation note, property detail, or next step")
        self.note.setMaximumHeight(100)
        layout.addWidget(self.note)
        add_note = QPushButton("Add Note")
        add_note.clicked.connect(self.add_note)
        layout.addWidget(add_note)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_notes()

    def save_workflow(self):
        try:
            self.repo.update_property_workflow(
                self.property_id,
                self.status.currentText(),
                self.priority.currentText(),
                self.follow_up.text().strip(),
            )
            self.repo.set_contact_restrictions(self.property_id, self.internal_dnc.isChecked(), self.opt_out.isChecked())
            QMessageBox.information(self, "Saved", "Lead workflow and contact restrictions were saved.")
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))

    def add_note(self):
        try:
            self.repo.add_note(self.property_id, self.note.toPlainText())
            self.note.clear()
            self.refresh_notes()
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))

    def refresh_notes(self):
        notes = self.repo.notes(self.property_id)
        self.history.setPlainText("\n\n".join(f"{n['created_at']} — {n['body']}" for n in notes) or "No notes yet.")


class PropertiesPage(QWidget):
    def __init__(self, repo: Repository, dashboard: DashboardPage):
        super().__init__()
        self.repo = repo
        self.dashboard = dashboard
        layout = QVBoxLayout(self)
        title = QLabel("Lead Manager")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        actions = QHBoxLayout()
        import_button = QPushButton("Import CSV Leads")
        import_button.clicked.connect(self.import_csv)
        actions.addWidget(import_button)
        actions.addStretch()
        layout.addLayout(actions)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search owner, address, city, state, ZIP, APN, phone, or email")
        self.search.returnPressed.connect(self.refresh)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", *repo.PROPERTY_STATUSES])
        self.priority_filter = QComboBox()
        self.priority_filter.addItems(["All", *repo.PRIORITIES])
        search_button = QPushButton("Apply Filters")
        search_button.clicked.connect(self.refresh)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear_filters)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.priority_filter)
        filters.addWidget(search_button)
        filters.addWidget(clear_button)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID", "Owner", "Address", "City", "State", "ZIP", "Phone", "Email",
            "Status", "Priority", "Follow-up", "Restricted",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_selected)
        layout.addWidget(self.table)

        hint = QLabel("Double-click a lead to update status, priority, follow-up date, restrictions, and notes.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.refresh()

    def clear_filters(self):
        self.search.clear()
        self.status_filter.setCurrentText("All")
        self.priority_filter.setCurrentText("All")
        self.refresh()

    def refresh(self):
        rows = self.repo.list_properties(self.search.text(), self.status_filter.currentText(), self.priority_filter.currentText())
        self.table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            restricted = "Yes" if item["internal_dnc"] or item["opt_out"] else "No"
            values = [
                item["id"], item["owner_name"], item["address"], item["city"], item["state"], item["zip"],
                item["phone"], item["email"], item["status"], item["priority"], item["follow_up_date"], restricted,
            ]
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(str(value or "")))
        self.table.resizeColumnsToContents()

    def selected_property_id(self):
        row = self.table.currentRow()
        return int(self.table.item(row, 0).text()) if row >= 0 else None

    def open_selected(self):
        property_id = self.selected_property_id()
        if not property_id:
            return
        dialog = PropertyDialog(self.repo, property_id, self)
        dialog.exec()
        self.refresh()
        self.dashboard.refresh()

    def import_csv(self):
        source, _ = QFileDialog.getOpenFileName(self, "Select lead CSV", "", "CSV Files (*.csv);;All Files (*)")
        if not source:
            return
        try:
            result = self.repo.import_leads_csv(Path(source))
            self.refresh()
            self.dashboard.refresh()
            QMessageBox.information(
                self,
                "Import complete",
                f"Added: {result['added']}\nSkipped duplicates: {result['skipped']}\nFailed rows: {result['failed']}",
            )
        except Exception as exc:
            log.exception("CSV import failed")
            QMessageBox.critical(self, "Import failed", str(exc))


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.setWindowTitle("LeadDesk AI 3.1 — Revenue MVP")
        self.resize(1320, 800)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        self.nav = QListWidget()
        self.nav.addItems(["Dashboard", "Lead Manager", "Migration & Backup", "About"])
        self.nav.setFixedWidth(210)
        self.pages = QStackedWidget()
        self.dashboard = DashboardPage(repo)
        self.properties = PropertiesPage(repo, self.dashboard)
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.properties)
        self.pages.addWidget(self.tools_page())
        self.pages.addWidget(self.about_page())
        self.nav.currentRowChanged.connect(self.change_page)
        self.nav.setCurrentRow(0)
        layout.addWidget(self.nav)
        layout.addWidget(self.pages, 1)
        self.setStyleSheet("""
            QMainWindow { background: #f4f6f8; }
            QListWidget { font-size: 15px; padding: 8px; }
            QLabel#pageTitle { font-size: 24px; font-weight: 700; margin-bottom: 12px; }
            QPushButton { padding: 8px 14px; }
            QTableWidget, QTextEdit, QLineEdit, QComboBox { background: white; }
        """)

    def change_page(self, index: int):
        self.pages.setCurrentIndex(index)
        if index == 0:
            self.dashboard.refresh()
        if index == 1:
            self.properties.refresh()

    def tools_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Migration & Backup")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        text = QLabel("Migrate a compatible Version 2 database, or create a verified backup of Version 3.")
        text.setWordWrap(True)
        layout.addWidget(text)
        migrate = QPushButton("Migrate Version 2 Database")
        migrate.clicked.connect(self.migrate_v2)
        layout.addWidget(migrate)
        backup = QPushButton("Create Verified Backup")
        backup.clicked.connect(self.backup)
        layout.addWidget(backup)
        layout.addStretch()
        return page

    def about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("LeadDesk AI 3.1 Revenue MVP")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        label = QLabel(
            "Lead CRM • CSV import • duplicate protection • workflow statuses • priority • follow-up dates • notes • contact restrictions • tested backups\n\n"
            "This application supports organization and analysis. It does not provide legal advice or automatically authorize calls, texts, emails, contracts, or negotiations."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()
        return page

    def migrate_v2(self):
        source, _ = QFileDialog.getOpenFileName(self, "Select Version 2 database", "", "SQLite Database (*.db);;All Files (*)")
        if not source:
            return
        answer = QMessageBox.question(self, "Replace current database?", "This will replace the current Version 3 database. A backup will be created first if it contains data. Continue?")
        if answer != QMessageBox.Yes:
            return
        try:
            self.repo.close()
            if DB_PATH.exists() and DB_PATH.stat().st_size:
                create_backup(DB_PATH)
            count = Repository.migrate_v2_database(Path(source), DB_PATH)
            self.repo = Repository(DB_PATH)
            self.dashboard.repo = self.repo
            self.properties.repo = self.repo
            self.dashboard.refresh()
            self.properties.refresh()
            QMessageBox.information(self, "Migration complete", f"Migrated {count} properties into LeadDesk AI 3.1.")
        except Exception as exc:
            log.exception("Migration failed")
            self.repo = Repository(DB_PATH)
            QMessageBox.critical(self, "Migration failed", str(exc))

    def backup(self):
        try:
            target = create_backup(DB_PATH)
            QMessageBox.information(self, "Backup complete", f"Verified backup created:\n{target}")
        except Exception as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))

    def closeEvent(self, event):
        try:
            if DB_PATH.exists():
                create_backup(DB_PATH)
            self.repo.close()
        finally:
            event.accept()
