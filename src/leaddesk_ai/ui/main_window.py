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
        self.tabs.addTab(self.seller_marketing_tab(), "Seller & Marketing")
        self.tabs.addTab(self.notes_tab(), "Notes")
        self.tabs.addTab(self.tasks_tab(), "Tasks")
        self.tabs.addTab(self.comps_offer_tab(), "Comps & Offer Builder")
        self.tabs.addTab(self.deal_analyzer_tab(), "Deal Analyzer")
        self.tabs.addTab(self.buyer_matches_tab(), "Buyer Matches")
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

    def seller_marketing_tab(self):
        page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout()
        self.motivation = QComboBox(); self.motivation.addItems([str(i) for i in range(11)])
        self.occupancy = QComboBox(); self.occupancy.addItems(self.repo.SELLER_OCCUPANCIES)
        self.timeline = QLineEdit(); self.timeline.setPlaceholderText("Example: 30 days, 3 months, flexible")
        self.preferred_contact = QComboBox(); self.preferred_contact.addItems(self.repo.CONTACT_METHODS)
        self.seller_tags = QLineEdit(); self.seller_tags.setPlaceholderText("Probate, tired landlord, vacant, referral")
        self.asking_price = QDoubleSpinBox(); self.asking_price.setRange(0, 100000000); self.asking_price.setPrefix("$")
        self.reason_for_selling = QTextEdit(); self.reason_for_selling.setMaximumHeight(80)
        self.marketing_source = QLineEdit(); self.marketing_source.setPlaceholderText("Cold Calling, Direct Mail, Referral, PPC, etc.")
        for label, widget in [("Motivation (0–10)", self.motivation), ("Occupancy", self.occupancy), ("Timeline to sell", self.timeline),
                              ("Preferred contact", self.preferred_contact), ("Seller tags", self.seller_tags), ("Asking price", self.asking_price),
                              ("Reason for selling", self.reason_for_selling), ("Marketing source", self.marketing_source)]: form.addRow(label, widget)
        layout.addLayout(form); save = QPushButton("Save Seller Profile"); save.clicked.connect(self.save_seller_profile); layout.addWidget(save)
        layout.addWidget(QLabel("Communication history"))
        self.communication_table = QTableWidget(0, 6); self.communication_table.setHorizontalHeaderLabels(["Date/Time", "Channel", "Outcome", "Notes", "Next Follow-Up", "By"])
        self.communication_table.setEditTriggers(QAbstractItemView.NoEditTriggers); layout.addWidget(self.communication_table, 1)
        comm = QFormLayout(); self.comm_channel = QComboBox(); self.comm_channel.addItems(self.repo.COMMUNICATION_CHANNELS)
        self.comm_outcome = QLineEdit(); self.comm_notes = QLineEdit(); self.comm_contacted_at = QLineEdit(); self.comm_contacted_at.setPlaceholderText("Leave blank for now")
        self.comm_follow_up = QLineEdit(); self.comm_follow_up.setPlaceholderText("YYYY-MM-DD")
        for label, widget in [("Channel", self.comm_channel), ("Outcome", self.comm_outcome), ("Notes", self.comm_notes), ("Contact date/time", self.comm_contacted_at), ("Next follow-up", self.comm_follow_up)]: comm.addRow(label, widget)
        layout.addLayout(comm); add = QPushButton("Log Communication"); add.clicked.connect(self.log_communication); layout.addWidget(add)
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

    def comps_offer_tab(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.comps_table = QTableWidget(0, 11)
        self.comps_table.setHorizontalHeaderLabels(["ID","Use","Address","Sold Price","Sold Date","Sq Ft","$/Sq Ft","Beds","Baths","Miles","Source"])
        self.comps_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.comps_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.comps_table, 1)

        form = QFormLayout()
        self.comp_address = QLineEdit(); self.comp_price = QDoubleSpinBox(); self.comp_price.setRange(0,100000000); self.comp_price.setPrefix("$")
        self.comp_date = QLineEdit(); self.comp_date.setPlaceholderText("YYYY-MM-DD")
        self.comp_sqft = QDoubleSpinBox(); self.comp_sqft.setRange(0,1000000); self.comp_sqft.setDecimals(0)
        self.comp_beds = QDoubleSpinBox(); self.comp_beds.setRange(0,100); self.comp_beds.setDecimals(1)
        self.comp_baths = QDoubleSpinBox(); self.comp_baths.setRange(0,100); self.comp_baths.setDecimals(1)
        self.comp_lot = QDoubleSpinBox(); self.comp_lot.setRange(0,100000000); self.comp_lot.setDecimals(0)
        self.comp_distance = QDoubleSpinBox(); self.comp_distance.setRange(0,1000); self.comp_distance.setDecimals(2); self.comp_distance.setSuffix(" mi")
        self.comp_source = QLineEdit(); self.comp_notes = QLineEdit(); self.comp_verified = QCheckBox("Verified")
        for label,widget in [("Comparable address",self.comp_address),("Sold price",self.comp_price),("Sold date",self.comp_date),("Square feet",self.comp_sqft),
                             ("Bedrooms",self.comp_beds),("Bathrooms",self.comp_baths),("Lot size",self.comp_lot),("Distance",self.comp_distance),
                             ("Source",self.comp_source),("Condition / notes",self.comp_notes),("Verification",self.comp_verified)]: form.addRow(label,widget)
        layout.addLayout(form)
        actions=QHBoxLayout(); add=QPushButton("Add Comparable"); add.clicked.connect(self.add_comparable)
        toggle=QPushButton("Use / Exclude Selected"); toggle.clicked.connect(self.toggle_comparable)
        delete=QPushButton("Delete Selected"); delete.clicked.connect(self.delete_comparable)
        estimate=QPushButton("Estimate ARV"); estimate.clicked.connect(self.estimate_comps_arv)
        for button in (add,toggle,delete,estimate): actions.addWidget(button)
        actions.addStretch(); layout.addLayout(actions)

        self.arv_summary=QLabel("Add comparable sales, then estimate ARV."); self.arv_summary.setWordWrap(True); self.arv_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.arv_summary)
        offer_form=QFormLayout()
        def money(default=0.0):
            w=QDoubleSpinBox(); w.setRange(0,100000000); w.setDecimals(2); w.setPrefix("$"); w.setValue(default); return w
        self.offer_arv=money(); self.seller_offer=money(); self.builder_buyer_price=money(); self.builder_fee=money(10000); self.builder_notes=QLineEdit()
        for label,widget in [("Suggested ARV",self.offer_arv),("Seller offer",self.seller_offer),("Buyer disposition price",self.builder_buyer_price),
                             ("Assignment fee target",self.builder_fee),("Offer notes",self.builder_notes)]: offer_form.addRow(label,widget)
        layout.addLayout(offer_form)
        save=QPushButton("Save Offer Scenario"); save.clicked.connect(self.save_offer_scenario); layout.addWidget(save)
        self.offer_history=QTableWidget(0,8); self.offer_history.setHorizontalHeaderLabels(["ID","Created","ARV","Seller Offer","Buyer Price","Fee Target","Spread","Notes"])
        self.offer_history.setEditTriggers(QAbstractItemView.NoEditTriggers); layout.addWidget(self.offer_history,1)
        return page

    def selected_comp_id(self):
        row=self.comps_table.currentRow(); return int(self.comps_table.item(row,0).text()) if row >= 0 else None

    def add_comparable(self):
        try:
            self.repo.add_comparable_sale(self.property_id,address=self.comp_address.text(),sold_price=self.comp_price.value(),sold_date=self.comp_date.text().strip(),
                square_feet=self.comp_sqft.value(),bedrooms=self.comp_beds.value(),bathrooms=self.comp_baths.value(),lot_size=self.comp_lot.value(),
                distance_miles=self.comp_distance.value(),condition_notes=self.comp_notes.text(),source=self.comp_source.text(),verified=self.comp_verified.isChecked())
            self.comp_address.clear(); self.comp_price.setValue(0); self.comp_date.clear(); self.comp_source.clear(); self.comp_notes.clear(); self.refresh_comps(); self.refresh_activity()
        except ValueError as exc: QMessageBox.warning(self,"Cannot add comparable",str(exc))

    def toggle_comparable(self):
        comp_id=self.selected_comp_id()
        if not comp_id: QMessageBox.information(self,"Select comparable","Select a comparable sale first."); return
        row=self.comps_table.currentRow(); selected=self.comps_table.item(row,1).text()=="Yes"
        self.repo.set_comparable_selected(comp_id,not selected); self.refresh_comps()

    def delete_comparable(self):
        comp_id=self.selected_comp_id()
        if not comp_id: QMessageBox.information(self,"Select comparable","Select a comparable sale first."); return
        self.repo.delete_comparable_sale(comp_id); self.refresh_comps()

    def estimate_comps_arv(self):
        try:
            result=self.repo.comparable_arv(self.property_id)
            self.offer_arv.setValue(result["suggested_arv"])
            latest=self.repo.latest_deal(self.property_id)
            fee=float(latest.get("wholesale_fee") or self.builder_fee.value()) if latest else self.builder_fee.value()
            target=float(latest.get("target_pct") or .70) if latest else .70
            if target > 1: target/=100
            repairs=float(latest.get("repairs") or 0) if latest else 0
            seller=max(0,result["suggested_arv"]*target-repairs-fee)
            buyer=max(0,seller+fee)
            self.seller_offer.setValue(seller); self.builder_buyer_price.setValue(buyer); self.builder_fee.setValue(fee)
            self.arv_summary.setText(f"Selected comps: {int(result['comp_count'])} | Average sale: ${result['average_price']:,.2f} | Average $/sq ft: ${result['average_ppsf']:,.2f}\nSuggested ARV: ${result['suggested_arv']:,.2f} | Range: ${result['low_arv']:,.2f}–${result['high_arv']:,.2f}")
            return result
        except ValueError as exc: QMessageBox.warning(self,"Cannot estimate ARV",str(exc)); return None

    def save_offer_scenario(self):
        try:
            self.repo.save_offer_scenario(self.property_id,suggested_arv=self.offer_arv.value(),seller_offer=self.seller_offer.value(),
                buyer_price=self.builder_buyer_price.value(),assignment_fee=self.builder_fee.value(),notes=self.builder_notes.text())
            self.builder_notes.clear(); self.refresh_offer_scenarios(); self.refresh_activity(); QMessageBox.information(self,"Saved","Offer scenario saved.")
        except ValueError as exc: QMessageBox.warning(self,"Cannot save offer",str(exc))

    def refresh_comps(self):
        rows=self.repo.list_comparable_sales(self.property_id); self.comps_table.setRowCount(len(rows))
        for r,item in enumerate(rows):
            ppsf=(float(item['sold_price'])/float(item['square_feet'])) if float(item['square_feet'] or 0)>0 else 0
            vals=[item['id'],"Yes" if item['selected'] else "No",item['address'],f"${item['sold_price']:,.2f}",item['sold_date'],f"{item['square_feet']:,.0f}" if item['square_feet'] else "",f"${ppsf:,.2f}" if ppsf else "",item['bedrooms'],item['bathrooms'],item['distance_miles'],item['source']]
            for c,val in enumerate(vals): self.comps_table.setItem(r,c,QTableWidgetItem(str(val or "")))
        self.comps_table.resizeColumnsToContents()

    def refresh_offer_scenarios(self):
        rows=self.repo.list_offer_scenarios(self.property_id); self.offer_history.setRowCount(len(rows))
        for r,item in enumerate(rows):
            vals=[item['id'],item['created_at'],f"${item['suggested_arv']:,.2f}",f"${item['seller_offer']:,.2f}",f"${item['buyer_price']:,.2f}",f"${item['assignment_fee']:,.2f}",f"${item['estimated_profit']:,.2f}",item['notes']]
            for c,val in enumerate(vals): self.offer_history.setItem(r,c,QTableWidgetItem(str(val or "")))
        self.offer_history.resizeColumnsToContents()

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

    def buyer_matches_tab(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.matches_table = QTableWidget(0, 7)
        self.matches_table.setHorizontalHeaderLabels(["Buyer ID", "Score", "Buyer", "Company", "Phone", "Target Price", "Why"] )
        self.matches_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.matches_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.matches_table, 1)
        refresh = QPushButton("Find Matching Buyers")
        refresh.clicked.connect(self.refresh_buyer_matches)
        layout.addWidget(refresh)
        form = QFormLayout()
        self.offer_amount = QDoubleSpinBox(); self.offer_amount.setRange(0, 100000000); self.offer_amount.setDecimals(2); self.offer_amount.setPrefix("$")
        self.offer_status = QComboBox(); self.offer_status.addItems(self.repo.BUYER_OFFER_STATUSES)
        self.offer_pof = QCheckBox("Proof of funds received")
        self.offer_sent = QLineEdit(); self.offer_sent.setPlaceholderText("YYYY-MM-DD")
        self.offer_responded = QLineEdit(); self.offer_responded.setPlaceholderText("YYYY-MM-DD")
        self.offer_notes = QLineEdit()
        form.addRow("Offer / buyer price", self.offer_amount); form.addRow("Pipeline status", self.offer_status)
        form.addRow("Proof of funds", self.offer_pof); form.addRow("Sent date", self.offer_sent)
        form.addRow("Responded date", self.offer_responded); form.addRow("Notes", self.offer_notes)
        layout.addLayout(form)
        add = QPushButton("Add Selected Buyer to Offer Pipeline"); add.clicked.connect(self.add_buyer_offer); layout.addWidget(add)
        self.offers_table = QTableWidget(0, 8)
        self.offers_table.setHorizontalHeaderLabels(["ID", "Buyer", "Amount", "Status", "POF", "Sent", "Responded", "Notes"])
        self.offers_table.setEditTriggers(QAbstractItemView.NoEditTriggers); layout.addWidget(self.offers_table, 1)
        return page

    def selected_match_buyer_id(self):
        row = self.matches_table.currentRow()
        return int(self.matches_table.item(row, 0).text()) if row >= 0 else None

    def refresh_buyer_matches(self):
        rows = self.repo.match_buyers(self.property_id)
        self.matches_table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            values = [item["id"], f"{item['match_score']}% {item['match_label']}", item["name"], item["company"], item["phone"], f"${item['target_price']:,.2f}", item["match_reasons"]]
            for c, value in enumerate(values): self.matches_table.setItem(r, c, QTableWidgetItem(str(value or "")))
        self.matches_table.resizeColumnsToContents()
        latest = self.repo.latest_deal(self.property_id)
        if latest: self.offer_amount.setValue(float(latest.get("buyer_price") or latest.get("mao") or 0))

    def add_buyer_offer(self):
        buyer_id = self.selected_match_buyer_id()
        if not buyer_id:
            QMessageBox.information(self, "Select buyer", "Select a matching buyer first."); return
        try:
            self.repo.add_buyer_offer(self.property_id, buyer_id, self.offer_amount.value(), self.offer_status.currentText(),
                                      self.offer_pof.isChecked(), self.offer_notes.text(), self.offer_sent.text().strip(),
                                      self.offer_responded.text().strip())
            self.offer_notes.clear(); self.refresh_offers(); self.refresh_activity()
        except ValueError as exc: QMessageBox.warning(self, "Cannot add offer", str(exc))

    def refresh_offers(self):
        rows = self.repo.list_buyer_offers(self.property_id); self.offers_table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            values = [item["id"], item["buyer_name"], f"${item['amount']:,.2f}", item["status"], "Yes" if item["proof_of_funds"] else "No", item["sent_date"], item["responded_date"], item["notes"]]
            for c, value in enumerate(values): self.offers_table.setItem(r, c, QTableWidgetItem(str(value or "")))
        self.offers_table.resizeColumnsToContents()

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
        seller = self.repo.seller_profile(self.property_id)
        self.motivation.setCurrentText(str(seller.get('motivation_level') or 0)); self.occupancy.setCurrentText(str(seller.get('occupancy') or ''))
        self.timeline.setText(str(seller.get('timeline') or '')); self.preferred_contact.setCurrentText(str(seller.get('preferred_contact') or ''))
        self.seller_tags.setText(str(seller.get('tags') or '')); self.asking_price.setValue(float(seller.get('asking_price') or 0))
        self.reason_for_selling.setPlainText(str(seller.get('reason_for_selling') or '')); self.marketing_source.setText(str(d['marketing_source'] or ''))
        self.refresh_notes(); self.refresh_tasks(); self.refresh_comps(); self.refresh_offer_scenarios(); self.refresh_deals(); self.refresh_buyer_matches(); self.refresh_offers(); self.refresh_communications(); self.refresh_activity()

    def save_profile(self):
        try:
            self.repo.update_property_profile(self.property_id, address=self.address.text(), city=self.city.text(), state=self.state.text(),
                zip_code=self.zip_code.text(), county=self.county.text(), apn=self.apn.text(), property_type=self.property_type.text(),
                owner_name=self.owner_name.text(), mailing_address=self.mailing_address.text(), phone=self.phone.text(), email=self.email.text())
            self.refresh_all(); QMessageBox.information(self, "Saved", "Property and owner profile saved.")
        except ValueError as exc: QMessageBox.warning(self, "Cannot save", str(exc))

    def save_seller_profile(self):
        try:
            self.repo.save_seller_profile(self.property_id, motivation_level=int(self.motivation.currentText()), occupancy=self.occupancy.currentText(),
                timeline=self.timeline.text(), preferred_contact=self.preferred_contact.currentText(), tags=self.seller_tags.text(),
                asking_price=self.asking_price.value() or None, reason_for_selling=self.reason_for_selling.toPlainText(), marketing_source=self.marketing_source.text())
            self.refresh_activity(); QMessageBox.information(self, "Saved", "Seller and marketing profile saved.")
        except ValueError as exc: QMessageBox.warning(self, "Cannot save", str(exc))

    def log_communication(self):
        try:
            self.repo.add_communication(self.property_id, channel=self.comm_channel.currentText(), outcome=self.comm_outcome.text(), notes=self.comm_notes.text(),
                contacted_at=self.comm_contacted_at.text(), next_follow_up_date=self.comm_follow_up.text().strip())
            self.comm_outcome.clear(); self.comm_notes.clear(); self.comm_contacted_at.clear(); self.comm_follow_up.clear(); self.refresh_communications(); self.refresh_all()
        except ValueError as exc: QMessageBox.warning(self, "Cannot log communication", str(exc))

    def refresh_communications(self):
        rows = self.repo.list_communications(self.property_id); self.communication_table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            for c, value in enumerate([item['contacted_at'], item['channel'], item['outcome'], item['notes'], item['next_follow_up_date'], item['created_by']]):
                self.communication_table.setItem(r, c, QTableWidgetItem(str(value or '')))
        self.communication_table.resizeColumnsToContents()

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


class MarketingHubPage(QWidget):
    def __init__(self, repo: Repository, dashboard: DashboardPage):
        super().__init__(); self.repo = repo; self.dashboard = dashboard
        layout = QVBoxLayout(self); title = QLabel("Marketing Hub & Follow-Up Queue"); title.setObjectName("pageTitle"); layout.addWidget(title)
        bar = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText("Search owner, property, or marketing source"); self.search.returnPressed.connect(self.refresh)
        refresh = QPushButton("Refresh Queue"); refresh.clicked.connect(self.refresh); bar.addWidget(self.search, 1); bar.addWidget(refresh); layout.addLayout(bar)
        self.table = QTableWidget(0, 11); self.table.setHorizontalHeaderLabels(["ID","Follow-Up","Priority","Owner","Property","Status","Motivation","Preferred Contact","Timeline","Source","Due Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.doubleClicked.connect(self.open_selected); layout.addWidget(self.table, 1)
        self.summary = QLabel(); layout.addWidget(self.summary); self.refresh()

    def selected_property_id(self):
        row = self.table.currentRow(); return int(self.table.item(row,0).text()) if row >= 0 else None

    def refresh(self):
        from datetime import date
        rows = self.repo.follow_up_queue(self.search.text()); today = date.today().isoformat(); self.table.setRowCount(len(rows)); overdue = due_today = 0
        for r, item in enumerate(rows):
            due = item['follow_up_date']; due_status = "Overdue" if due < today else ("Due Today" if due == today else "Upcoming")
            overdue += int(due_status == "Overdue"); due_today += int(due_status == "Due Today")
            address = ", ".join(x for x in [item['address'], item['city'], item['state'], item['zip']] if x)
            values = [item['id'], due, item['priority'], item['owner_name'], address, item['status'], f"{item['motivation_level']}/10", item['preferred_contact'], item['timeline'], item['marketing_source'], due_status]
            for c, value in enumerate(values): self.table.setItem(r,c,QTableWidgetItem(str(value or '')))
        self.table.resizeColumnsToContents(); self.summary.setText(f"Queue: {len(rows)} • Overdue: {overdue} • Due today: {due_today}")

    def open_selected(self):
        property_id = self.selected_property_id()
        if property_id and PropertyDialog(self.repo, property_id, self).exec(): pass
        self.refresh(); self.dashboard.refresh()


class BuyerEditorDialog(QDialog):
    def __init__(self, repo: Repository, buyer_id: int | None = None, parent=None):
        super().__init__(parent); self.repo = repo; self.buyer_id = buyer_id
        self.setWindowTitle("Edit Buyer" if buyer_id else "Add Buyer"); self.resize(620, 650)
        layout = QVBoxLayout(self); form = QFormLayout()
        self.name = QLineEdit(); self.company = QLineEdit(); self.email = QLineEdit(); self.phone = QLineEdit()
        self.markets = QLineEdit(); self.counties = QLineEdit(); self.zip_codes = QLineEdit(); self.property_types = QLineEdit()
        self.min_price = QDoubleSpinBox(); self.min_price.setRange(0, 100000000); self.min_price.setPrefix("$")
        self.max_price = QDoubleSpinBox(); self.max_price.setRange(0, 100000000); self.max_price.setPrefix("$")
        self.rehab_level = QComboBox(); self.rehab_level.addItems(["", "Light", "Moderate", "Heavy", "Any"])
        self.funding_type = QComboBox(); self.funding_type.addItems(["", "Cash", "Hard Money", "Private Money", "Conventional", "Other"])
        self.close_days = QLineEdit(); self.close_days.setPlaceholderText("Example: 14")
        self.active = QCheckBox("Active buyer"); self.active.setChecked(True); self.notes = QTextEdit(); self.notes.setMaximumHeight(100)
        fields = [("Buyer name", self.name), ("Company", self.company), ("Email", self.email), ("Phone", self.phone),
                  ("Markets / states", self.markets), ("Counties", self.counties), ("ZIP codes", self.zip_codes),
                  ("Property types", self.property_types), ("Minimum price", self.min_price), ("Maximum price", self.max_price),
                  ("Rehab level", self.rehab_level), ("Funding type", self.funding_type), ("Average close days", self.close_days),
                  ("Status", self.active), ("Notes", self.notes)]
        for label, widget in fields: form.addRow(label, widget)
        layout.addLayout(form); buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        if buyer_id: self.load_buyer()

    def load_buyer(self):
        b = self.repo.buyer(self.buyer_id)
        for widget, key in [(self.name,"name"),(self.company,"company"),(self.email,"email"),(self.phone,"phone"),(self.markets,"markets"),
                            (self.counties,"counties"),(self.zip_codes,"zip_codes"),(self.property_types,"property_types"),(self.close_days,"avg_close_days")]:
            widget.setText(str(b.get(key) or ""))
        self.min_price.setValue(float(b.get("min_price") or 0)); self.max_price.setValue(float(b.get("max_price") or 0))
        self.rehab_level.setCurrentText(str(b.get("rehab_level") or "")); self.funding_type.setCurrentText(str(b.get("funding_type") or ""))
        self.active.setChecked(bool(b.get("active"))); self.notes.setPlainText(str(b.get("notes") or ""))

    def save(self):
        values = {"name": self.name.text(), "company": self.company.text(), "email": self.email.text(), "phone": self.phone.text(),
                  "markets": self.markets.text(), "counties": self.counties.text(), "zip_codes": self.zip_codes.text(),
                  "property_types": self.property_types.text(), "min_price": self.min_price.value() or None,
                  "max_price": self.max_price.value() or None, "rehab_level": self.rehab_level.currentText(),
                  "funding_type": self.funding_type.currentText(), "avg_close_days": self.close_days.text().strip() or None,
                  "active": self.active.isChecked(), "notes": self.notes.toPlainText()}
        try:
            self.repo.save_buyer(values, self.buyer_id); self.accept()
        except (ValueError, TypeError) as exc: QMessageBox.warning(self, "Cannot save buyer", str(exc))


class BuyersPage(QWidget):
    def __init__(self, repo: Repository, dashboard: DashboardPage):
        super().__init__(); self.repo = repo; self.dashboard = dashboard
        layout = QVBoxLayout(self); title = QLabel("Buyer CRM"); title.setObjectName("pageTitle"); layout.addWidget(title)
        bar = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText("Search name, company, phone, market, county, ZIP, property type, or funding")
        self.search.returnPressed.connect(self.refresh); add = QPushButton("Add Buyer"); add.clicked.connect(self.add_buyer)
        edit = QPushButton("Edit Selected"); edit.clicked.connect(self.edit_buyer); delete = QPushButton("Delete Selected"); delete.clicked.connect(self.delete_buyer)
        bar.addWidget(self.search, 1); bar.addWidget(add); bar.addWidget(edit); bar.addWidget(delete); layout.addLayout(bar)
        self.table = QTableWidget(0, 12); self.table.setHorizontalHeaderLabels(["ID","Active","Buyer","Company","Phone","Email","Markets","Counties","ZIPs","Property Types","Price Range","Funding / Close"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.doubleClicked.connect(self.edit_buyer)
        layout.addWidget(self.table, 1); self.refresh()

    def selected_id(self):
        row = self.table.currentRow(); return int(self.table.item(row,0).text()) if row >= 0 else None

    def refresh(self):
        rows = self.repo.list_buyers(self.search.text()); self.table.setRowCount(len(rows))
        for r, b in enumerate(rows):
            low = f"${b['min_price']:,.0f}" if b['min_price'] is not None else "Any"; high = f"${b['max_price']:,.0f}" if b['max_price'] is not None else "Any"
            funding = str(b['funding_type'] or ""); close = f"{b['avg_close_days']} days" if b['avg_close_days'] is not None else ""
            values = [b['id'], "Yes" if b['active'] else "No", b['name'], b['company'], b['phone'], b['email'], b['markets'], b['counties'], b['zip_codes'], b['property_types'], f"{low} – {high}", " / ".join(x for x in (funding, close) if x)]
            for c, value in enumerate(values): self.table.setItem(r,c,QTableWidgetItem(str(value or "")))
        self.table.resizeColumnsToContents()

    def add_buyer(self):
        if BuyerEditorDialog(self.repo, parent=self).exec(): self.refresh(); self.dashboard.refresh()

    def edit_buyer(self):
        buyer_id = self.selected_id()
        if buyer_id and BuyerEditorDialog(self.repo, buyer_id, self).exec(): self.refresh(); self.dashboard.refresh()

    def delete_buyer(self):
        buyer_id = self.selected_id()
        if not buyer_id: return
        if QMessageBox.question(self, "Delete buyer", "Delete this buyer? Existing pipeline history will keep a deleted-buyer label.") == QMessageBox.Yes:
            self.repo.delete_buyer(buyer_id); self.refresh(); self.dashboard.refresh()


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.setWindowTitle("LeadDesk AI 3.6 — Seller CRM & Marketing Hub")
        self.resize(1320, 800)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        self.nav = QListWidget()
        self.nav.addItems(["Dashboard", "Lead Manager", "Buyer CRM", "Marketing Hub", "Migration & Backup", "About"])
        self.nav.setFixedWidth(210)
        self.pages = QStackedWidget()
        self.dashboard = DashboardPage(repo)
        self.properties = PropertiesPage(repo, self.dashboard)
        self.buyers = BuyersPage(repo, self.dashboard)
        self.marketing = MarketingHubPage(repo, self.dashboard)
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.properties)
        self.pages.addWidget(self.buyers)
        self.pages.addWidget(self.marketing)
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
        if index == 2:
            self.buyers.refresh()
        if index == 3:
            self.marketing.refresh()

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
        title = QLabel("LeadDesk AI 3.6 Seller CRM & Marketing Hub")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        label = QLabel(
            "Lead CRM • Seller CRM • Marketing Hub • Follow-Up Queue • Communication History • Deal Analyzer • Buyer CRM • Comps • tested backups\n\n"
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
