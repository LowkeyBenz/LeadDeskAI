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
    QDoubleSpinBox,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from leaddesk_ai.core.paths import DB_PATH
from leaddesk_ai.db.repository import Repository
from leaddesk_ai.services.backup import create_backup
from leaddesk_ai.services.calculations import analyze_deal

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
        self.setWindowTitle(f"Property Workspace — {property_id}")
        self.resize(860, 720)
        self.layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setObjectName("pageTitle")
        self.layout.addWidget(self.heading)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self.profile_tab(), "Profile")
        self.tabs.addTab(self.workflow_tab(), "Workflow")
        self.tabs.addTab(self.notes_tab(), "Notes")
        self.tabs.addTab(self.tasks_tab(), "Tasks")
        self.tabs.addTab(self.deal_analyzer_tab(), "Deal Analyzer")
        self.tabs.addTab(self.activity_tab(), "Activity")
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)
        self.refresh_all()

    def profile_tab(self):
        page = QWidget(); form = QFormLayout(page)
        self.address = QLineEdit(); self.city = QLineEdit(); self.state = QLineEdit(); self.zip_code = QLineEdit()
        self.county = QLineEdit(); self.apn = QLineEdit(); self.property_type = QLineEdit()
        self.owner_name = QLineEdit(); self.mailing_address = QLineEdit(); self.phone = QLineEdit(); self.email = QLineEdit()
        for label, widget in [("Property address", self.address), ("City", self.city), ("State", self.state), ("ZIP", self.zip_code),
                              ("County", self.county), ("APN", self.apn), ("Property type", self.property_type),
                              ("Owner name", self.owner_name), ("Mailing address", self.mailing_address),
                              ("Phone", self.phone), ("Email", self.email)]: form.addRow(label, widget)
        save = QPushButton("Save Property Profile"); save.clicked.connect(self.save_profile); form.addRow(save)
        return page

    def workflow_tab(self):
        page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout()
        self.status = QComboBox(); self.status.addItems(self.repo.PROPERTY_STATUSES)
        self.priority = QComboBox(); self.priority.addItems(self.repo.PRIORITIES)
        self.follow_up = QLineEdit(); self.follow_up.setPlaceholderText("YYYY-MM-DD")
        self.internal_dnc = QCheckBox("Internal do-not-contact"); self.opt_out = QCheckBox("Contact opted out")
        form.addRow("Status", self.status); form.addRow("Priority", self.priority); form.addRow("Follow-up date", self.follow_up)
        form.addRow("Restrictions", self.internal_dnc); form.addRow("", self.opt_out); layout.addLayout(form)
        save = QPushButton("Save Workflow"); save.clicked.connect(self.save_workflow); layout.addWidget(save); layout.addStretch()
        return page

    def notes_tab(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.history = QTextEdit(); self.history.setReadOnly(True); layout.addWidget(self.history, 1)
        self.note = QTextEdit(); self.note.setPlaceholderText("Add a seller conversation note, property detail, or next step"); self.note.setMaximumHeight(110)
        layout.addWidget(self.note); add = QPushButton("Add Note"); add.clicked.connect(self.add_note); layout.addWidget(add)
        return page

    def tasks_tab(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.tasks_table = QTableWidget(0, 5); self.tasks_table.setHorizontalHeaderLabels(["ID", "Task", "Due", "Priority", "Status"])
        self.tasks_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.tasks_table.setEditTriggers(QAbstractItemView.NoEditTriggers); layout.addWidget(self.tasks_table, 1)
        form = QFormLayout(); self.task_title = QLineEdit(); self.task_due = QLineEdit(); self.task_due.setPlaceholderText("YYYY-MM-DD")
        self.task_priority = QComboBox(); self.task_priority.addItems(self.repo.PRIORITIES)
        form.addRow("Task", self.task_title); form.addRow("Due date", self.task_due); form.addRow("Priority", self.task_priority); layout.addLayout(form)
        actions = QHBoxLayout(); add = QPushButton("Add Task"); add.clicked.connect(self.add_task); complete = QPushButton("Mark Completed"); complete.clicked.connect(self.complete_task)
        actions.addWidget(add); actions.addWidget(complete); actions.addStretch(); layout.addLayout(actions)
        return page

    def deal_analyzer_tab(self):
        page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout()
        def money(default=0.0):
            w = QDoubleSpinBox(); w.setRange(0, 100000000); w.setDecimals(2); w.setPrefix("$"); w.setValue(default); return w
        self.deal_arv = money(); self.deal_purchase = money(); self.deal_repairs = money()
        self.deal_closing = money(); self.deal_holding = money(); self.deal_marketing = money(); self.deal_misc = money()
        self.deal_fee = money(10000); self.deal_target = QDoubleSpinBox(); self.deal_target.setRange(0,100); self.deal_target.setDecimals(1); self.deal_target.setSuffix("%"); self.deal_target.setValue(70)
        for label, widget in [("After Repair Value (ARV)",self.deal_arv),("Purchase price",self.deal_purchase),("Repairs",self.deal_repairs),
                              ("Closing costs",self.deal_closing),("Holding costs",self.deal_holding),("Marketing costs",self.deal_marketing),
                              ("Miscellaneous costs",self.deal_misc),("Assignment fee target",self.deal_fee),("Buyer target percentage",self.deal_target)]: form.addRow(label,widget)
        layout.addLayout(form)
        actions=QHBoxLayout(); calc=QPushButton("Calculate"); calc.clicked.connect(self.calculate_deal); save=QPushButton("Save Analysis"); save.clicked.connect(self.save_deal)
        actions.addWidget(calc); actions.addWidget(save); actions.addStretch(); layout.addLayout(actions)
        self.deal_summary=QLabel("Enter deal numbers and click Calculate."); self.deal_summary.setWordWrap(True); self.deal_summary.setTextInteractionFlags(Qt.TextSelectableByMouse); layout.addWidget(self.deal_summary)
        self.deal_history=QTableWidget(0,7); self.deal_history.setHorizontalHeaderLabels(["ID","Created","ARV","Purchase","MAO","Profit","Score"]); self.deal_history.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.deal_history,1); return page

    def _deal_values(self):
        return dict(arv=self.deal_arv.value(), purchase_price=self.deal_purchase.value(), repairs=self.deal_repairs.value(),
                    closing_costs=self.deal_closing.value(), holding_costs=self.deal_holding.value(), marketing_costs=self.deal_marketing.value(),
                    misc_costs=self.deal_misc.value(), wholesale_fee=self.deal_fee.value(), target_pct=self.deal_target.value())

    def calculate_deal(self):
        try:
            result=analyze_deal(**self._deal_values())
            self.deal_summary.setText(f"MAO: ${result['mao']:,.2f}   |   Buyer price: ${result['buyer_price']:,.2f}\nTotal costs: ${result['total_costs']:,.2f}   |   Total investment: ${result['total_investment']:,.2f}\nProjected profit: ${result['projected_profit']:,.2f}   |   ROI: {result['roi']:.2f}%   |   Score: {result['deal_score']}")
            return result
        except ValueError as exc:
            QMessageBox.warning(self,"Cannot calculate",str(exc)); return None

    def save_deal(self):
        if self.calculate_deal() is None: return
        try:
            self.repo.save_deal_analysis(self.property_id, **self._deal_values())
            self.refresh_deals(); self.refresh_activity(); QMessageBox.information(self,"Saved","Deal analysis saved to this property.")
        except ValueError as exc: QMessageBox.warning(self,"Cannot save",str(exc))

    def refresh_deals(self):
        rows=self.repo.list_deal_analyses(self.property_id); self.deal_history.setRowCount(len(rows))
        for r,item in enumerate(rows):
            vals=[item['id'],item['created_at'],f"${item['arv']:,.2f}",f"${item['purchase_price']:,.2f}",f"${item['mao']:,.2f}",f"${item['projected_profit']:,.2f}",item['deal_score']]
            for c,val in enumerate(vals): self.deal_history.setItem(r,c,QTableWidgetItem(str(val)))
        self.deal_history.resizeColumnsToContents()

    def activity_tab(self):
        page = QWidget(); layout = QVBoxLayout(page); self.activity_history = QTextEdit(); self.activity_history.setReadOnly(True); layout.addWidget(self.activity_history); return page

    def refresh_all(self):
        d = self.repo.property_details(self.property_id)
        if d is None: return
        self.heading.setText(f"{d['address']}, {d['city']}, {d['state']} {d['zip']}")
        for widget, key in [(self.address,'address'),(self.city,'city'),(self.state,'state'),(self.zip_code,'zip'),(self.county,'county'),(self.apn,'apn'),
                            (self.property_type,'property_type'),(self.owner_name,'owner_name'),(self.mailing_address,'mailing_address'),(self.phone,'phone'),(self.email,'email')]:
            widget.setText(str(d[key] or ''))
        self.status.setCurrentText(d['status'] or 'New'); self.priority.setCurrentText(d['priority'] or 'Normal'); self.follow_up.setText(d['follow_up_date'] or '')
        self.internal_dnc.setChecked(bool(d['internal_dnc'])); self.opt_out.setChecked(bool(d['opt_out']))
        self.refresh_notes(); self.refresh_tasks(); self.refresh_deals(); self.refresh_activity()

    def save_profile(self):
        try:
            self.repo.update_property_profile(self.property_id, address=self.address.text(), city=self.city.text(), state=self.state.text(),
                zip_code=self.zip_code.text(), county=self.county.text(), apn=self.apn.text(), property_type=self.property_type.text(),
                owner_name=self.owner_name.text(), mailing_address=self.mailing_address.text(), phone=self.phone.text(), email=self.email.text())
            self.refresh_all(); QMessageBox.information(self, "Saved", "Property and owner profile saved.")
        except ValueError as exc: QMessageBox.warning(self, "Cannot save", str(exc))

    def save_workflow(self):
        try:
            self.repo.update_property_workflow(self.property_id, self.status.currentText(), self.priority.currentText(), self.follow_up.text().strip())
            self.repo.set_contact_restrictions(self.property_id, self.internal_dnc.isChecked(), self.opt_out.isChecked())
            self.refresh_activity(); QMessageBox.information(self, "Saved", "Workflow and restrictions saved.")
        except ValueError as exc: QMessageBox.warning(self, "Cannot save", str(exc))

    def add_note(self):
        try:
            self.repo.add_note(self.property_id, self.note.toPlainText()); self.note.clear(); self.refresh_notes(); self.refresh_activity()
        except ValueError as exc: QMessageBox.warning(self, "Cannot save", str(exc))

    def refresh_notes(self):
        notes = self.repo.notes(self.property_id); self.history.setPlainText("\n\n".join(f"{n['created_at']} — {n['body']}" for n in notes) or "No notes yet.")

    def add_task(self):
        try:
            self.repo.add_task(self.property_id, self.task_title.text(), self.task_due.text().strip(), self.task_priority.currentText())
            self.task_title.clear(); self.task_due.clear(); self.refresh_tasks(); self.refresh_activity()
        except ValueError as exc: QMessageBox.warning(self, "Cannot add task", str(exc))

    def selected_task_id(self):
        row = self.tasks_table.currentRow(); return int(self.tasks_table.item(row, 0).text()) if row >= 0 else None

    def complete_task(self):
        task_id = self.selected_task_id()
        if not task_id: QMessageBox.information(self, "Select task", "Select a task first."); return
        self.repo.set_task_completed(task_id, True); self.refresh_tasks(); self.refresh_activity()

    def refresh_tasks(self):
        rows = self.repo.list_tasks(self.property_id); self.tasks_table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            for c, value in enumerate([item['id'], item['title'], item['due_date'], item['priority'], item['status']]): self.tasks_table.setItem(r,c,QTableWidgetItem(str(value or '')))
        self.tasks_table.resizeColumnsToContents()

    def refresh_activity(self):
        rows = self.repo.activities(self.property_id); self.activity_history.setPlainText("\n\n".join(f"{r['created_at']} — {r['activity_type']}\n{r['details']}" for r in rows) or "No activity yet.")


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
        self.setWindowTitle("LeadDesk AI 3.3 — Deal Analyzer")
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
        title = QLabel("LeadDesk AI 3.3 Deal Analyzer")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        label = QLabel(
            "Lead CRM • Property Workspace • Deal Analyzer • saved deal history • tasks • activity timeline • notes • workflow controls • tested backups\n\n"
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
            QMessageBox.information(self, "Migration complete", f"Migrated {count} properties into LeadDesk AI 3.2.")
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
