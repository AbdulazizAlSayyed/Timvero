# client/ui/main_window.py
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Optional
from PyQt6.QtCore import QTimer
from ..ui.login_dialog import LoginDialog  

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QMessageBox, QSpinBox, QDoubleSpinBox, QFileDialog, QDateEdit, QGroupBox,
    QHeaderView, QDialog, QTreeWidget, QInputDialog, QTreeWidgetItem, QFrame,
    QCheckBox,QAbstractItemView
)
from PyQt6.QtGui import QIcon, QAction, QColor

from PyQt6.QtWidgets import QScrollArea, QSizePolicy
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtCore import QTimer

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QIcon
from pathlib import Path

from ..services import api, session


# ---------------------------
# Constants
# ---------------------------
COMPANIES = ["Tempo Glass", "ProSteel"]
COMPANIES_FALLBACK = ["Tempo Glass", "ProSteel"]
KINDS = ["overhead", "stage", "project_name"]
DATAENTRY_KINDS = ["overhead", "stage"]

# ---------------------------
# Small helpers
# ---------------------------
def _msg_ok(parent, text): QMessageBox.information(parent, "OK", text)
def _msg_err(parent, text): QMessageBox.critical(parent, "Error", text)

def _api_optional(fn_name: str) -> Optional[Callable]:
    return getattr(api, fn_name, None)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._ts_loading = False
        
        self._login_open = False
        session.ON_UNAUTHORIZED = self.on_unauthorized

        ASSETS = Path(__file__).resolve().parents[1] / "assets"
        self.setWindowIcon(QIcon(str(ASSETS / "icon.png")))
        self.setWindowTitle("Timvero (Desktop)")
        self.resize(1100, 720)


        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Header
        header = QHBoxLayout()
        self.lblUser = QLabel(f"User: {session.USERNAME}   |   Role: {session.ROLE}")
        self.lblUser.setStyleSheet("font-size: 13px; font-weight: 700;")
        header.addWidget(self.lblUser)

        header.addStretch(1)

        self.btnRefresh = QPushButton("Refresh All")
        self.btnRefresh.clicked.connect(self.refresh_all)
        header.addWidget(self.btnRefresh)

        layout.addLayout(header)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # tabs
        self.tabEmployees = QWidget()
        self.tabCategories = QWidget()
        self.tabProjects = QWidget()
        self.tabTimesheet = QWidget()
        self.tabPayments = QWidget()
        self.tabReport = QWidget()

        # Always allow these:
        self.tabs.addTab(self.tabEmployees, "Employees")
        self.tabs.addTab(self.tabTimesheet, "Timesheet")

        # Only HR/Admin see the rest
        if session.ROLE in ("HR", "Admin"):
            self.tabs.addTab(self.tabCategories, "Categories")
            self.tabs.addTab(self.tabProjects, "Projects")
            self.tabs.addTab(self.tabReport, "Reports")
            self.tabs.addTab(self.tabPayments, "Payments (Locked)")

        # caches
        self.employees: list[dict] = []
        self.categories: list[dict] = []
        self._salary_rows: list[dict] = []
        self._report_rows: list[dict] = []

        # build UI
        self._build_employees()
        self._build_categories()
        self._build_projects()
        self._build_timesheet()
        self._build_report()
        if session.ROLE in ("HR", "Admin"):
            self._build_payments()

        self.refresh_all()
    
    def on_unauthorized(self):
        """
        Called from client/services/api.py when any request returns 401.
        Must run on the UI thread -> use QTimer.singleShot.
        """
        # avoid multiple dialogs
        if getattr(self, "_login_open", False):
            return

        self._login_open = True

        def _do():
            try:
                # تأكد UI ما يعلق على tabs محمية
                self._lock_after_logout()

                QMessageBox.warning(self, "Session expired", "Please login again.")

                dlg = LoginDialog()
                ok = dlg.exec()

                if ok:
                    # بعد login جديد: رجّع تحديث كامل + header user/role
                    self.lblUser.setText(f"User: {session.USERNAME}   |   Role: {session.ROLE}")
                    self.refresh_all()
                else:
                    # المستخدم سكر نافذة اللوجين
                    # خيار: خليه مسكر أو خليه Locked
                    pass

            finally:
                self._login_open = False

        QTimer.singleShot(0, _do)

    
    def _ts_key(self) -> tuple:
        """Unique key for current selection (emp/date/company/mode)"""
        emp_id = self.tsEmp.currentData()
        company = (self.tsCompany.currentText() or "").strip()
        mode = self.tsMode.currentText()

        if not emp_id or company in ("", "All"):
            return (None, None, None, None)

        if mode == "Daily":
            date_str = self.tsDate.date().toString("yyyy-MM-dd")
            return (int(emp_id), company, mode, date_str)
        else:
            return (int(emp_id), company, mode, int(self.tsYear.value()), int(self.tsMonth.value()))


    def _fill_company_combos(self):
        companies = (self.companies or [])[:]
        names = [c.get("name", "") for c in companies if c.get("name")]
        if not names:
            names = list(COMPANIES_FALLBACK)

        # ---------------- Timesheet company ----------------
        if hasattr(self, "tsCompany"):
            cur = self.tsCompany.currentText() if self.tsCompany.count() else "All"
            self.tsCompany.blockSignals(True)
            self.tsCompany.clear()
            self.tsCompany.addItem("All")
            self.tsCompany.addItems(names)
            idx = self.tsCompany.findText(cur)
            self.tsCompany.setCurrentIndex(idx if idx >= 0 else self.tsCompany.findText("All"))
            self.tsCompany.blockSignals(False)

        # ---------------- Categories company filter (id) ----------------
        if hasattr(self, "catCompany"):
            cur_id = self.catCompany.currentData() if self.catCompany.count() else None
            self.catCompany.blockSignals(True)
            self.catCompany.clear()
            self.catCompany.addItem("All Companies", None)
            for c in companies:
                if c.get("id") is None:
                    continue
                self.catCompany.addItem(c.get("name", ""), int(c.get("id")))
            if cur_id is None:
                self.catCompany.setCurrentIndex(0)
            else:
                idx = self.catCompany.findData(cur_id)
                self.catCompany.setCurrentIndex(idx if idx >= 0 else 0)
            self.catCompany.blockSignals(False)

        # ---------------- Projects filters ----------------
        if hasattr(self, "projCompany"):
            cur_id = self.projCompany.currentData() if self.projCompany.count() else None
            self.projCompany.blockSignals(True)
            self.projCompany.clear()
            self.projCompany.addItem("All Companies", None)
            for c in companies:
                if c.get("id") is None:
                    continue
                self.projCompany.addItem(c.get("name", ""), int(c.get("id")))
            if cur_id is None:
                self.projCompany.setCurrentIndex(0)
            else:
                idx = self.projCompany.findData(cur_id)
                self.projCompany.setCurrentIndex(idx if idx >= 0 else 0)
            self.projCompany.blockSignals(False)

        if hasattr(self, "projComp"):
            cur_id = self.projComp.currentData() if self.projComp.count() else None
            self.projComp.blockSignals(True)
            self.projComp.clear()
            for c in companies:
                if c.get("id") is None:
                    continue
                self.projComp.addItem(c.get("name", ""), int(c.get("id")))
            if cur_id is not None:
                idx = self.projComp.findData(cur_id)
                if idx >= 0:
                    self.projComp.setCurrentIndex(idx)
            self.projComp.blockSignals(False)

        # ---------------- Reports company filter ----------------
        if hasattr(self, "repCompany"):
            cur = self.repCompany.currentText() if self.repCompany.count() else "All"
            self.repCompany.blockSignals(True)
            self.repCompany.clear()
            self.repCompany.addItem("All")
            self.repCompany.addItems(names)
            idx = self.repCompany.findText(cur)
            self.repCompany.setCurrentIndex(idx if idx >= 0 else 0)
            self.repCompany.blockSignals(False)

    # =========================================================
    # Employees
    # =========================================================
    def _build_employees(self):
        lay = QVBoxLayout(self.tabEmployees)

        top = QHBoxLayout()
        self.empFilter = QLineEdit()
        self.empFilter.setPlaceholderText("Filter by name...")
        self.empFilter.textChanged.connect(self._render_employees_table)
        top.addWidget(self.empFilter)
        lay.addLayout(top)

        addRow = QHBoxLayout()
        self.empStaffId = QLineEdit()
        self.empStaffId.setPlaceholderText("Staff ID")

        self.empName = QLineEdit()
        self.empName.setPlaceholderText("Employee name")

        self.empAdd = QPushButton("Add")
        self.empAdd.clicked.connect(self._add_employee)

        addRow.addWidget(self.empStaffId)
        addRow.addWidget(self.empName)
        addRow.addWidget(self.empAdd)
        addRow.addStretch(1)
        lay.addLayout(addRow)

        # ✅ NEW: readonly username "data"
        readonly = self._is_readonly_employee_user()

        # If User OR readonly username "data": only 2 columns (no actions)
        if session.ROLE == "User" or readonly:
            self.empTable = QTableWidget(0, 2)
            self.empTable.setHorizontalHeaderLabels(["Staff ID", "Name"])
        else:
            self.empTable = QTableWidget(0, 3)
            self.empTable.setHorizontalHeaderLabels(["Staff ID", "Name", "Actions"])

        self.empTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.empTable.verticalHeader().setVisible(False)
        self.empTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.empTable)

        hint = QLabel("Company is selected in Timesheet.")
        hint.setStyleSheet("color:#94a3b8;")
        lay.addWidget(hint)

        # Delete button handler
        self._confirm_delete_dialog = None
  
    def _is_readonly_employee_user(self) -> bool:
        # block edit/delete ONLY for username "data"
        return (session.USERNAME or "").strip().lower() == "data"
    def _add_employee(self):
        try:
            staff_id = self.empStaffId.text().strip()
            name = self.empName.text().strip()
            
            if not staff_id:
                _msg_err(self, "Staff ID required.")
                return
                
            if not name:
                _msg_err(self, "Employee name required.")
                return

            api.employees_add(staff_id, name, "")

            self.empStaffId.clear()
            self.empName.clear()
            self.refresh_all()
            _msg_ok(self, "Employee saved.")
        except Exception as e:
            _msg_err(self, str(e))

    def _edit_employee(self, emp_data: dict):
        try:
            # ✅ NEW hard guard: block ONLY username "data"
            if self._is_readonly_employee_user():
                _msg_err(self, "Not allowed for this user.")
                return

            if session.ROLE == "User":
                _msg_err(self, "Not allowed.")
                return

            emp_id = emp_data.get("id")
            current_staff_id = emp_data.get("staff_id", "")
            current_name = emp_data.get("name", "")

            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Employee")
            dialog.setModal(True)
            dialog.resize(350, 200)

            layout = QVBoxLayout(dialog)

            staff_id_label = QLabel("Staff ID:")
            staff_id_input = QLineEdit()
            staff_id_input.setText(current_staff_id)
            layout.addWidget(staff_id_label)
            layout.addWidget(staff_id_input)

            name_label = QLabel("Employee Name:")
            name_input = QLineEdit()
            name_input.setText(current_name)
            layout.addWidget(name_label)
            layout.addWidget(name_input)

            btn_layout = QHBoxLayout()
            ok_btn = QPushButton("Save")
            cancel_btn = QPushButton("Cancel")
            btn_layout.addWidget(ok_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)

            def save_employee():
                new_staff_id = staff_id_input.text().strip()
                new_name = name_input.text().strip()

                if not new_staff_id:
                    _msg_err(dialog, "Staff ID required.")
                    return
                if not new_name:
                    _msg_err(dialog, "Employee name required.")
                    return

                try:
                    api.employees_update(emp_id, new_staff_id, new_name, "")
                    dialog.accept()
                    self.refresh_all()
                    _msg_ok(self, "Employee updated successfully.")
                except Exception as e:
                    _msg_err(dialog, f"Failed to update employee: {str(e)}")

            ok_btn.clicked.connect(save_employee)
            cancel_btn.clicked.connect(dialog.reject)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                pass

        except Exception as e:
            _msg_err(self, f"Failed to edit employee: {str(e)}")


    def _delete_employee(self, emp_id: int):
        try:
            # ✅ NEW hard guard: block ONLY username "data"
            if self._is_readonly_employee_user():
                _msg_err(self, "Not allowed for this user.")
                return

            if session.ROLE == "User":
                _msg_err(self, "Not allowed.")
                return

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete employee ID {emp_id}?\n"
                f"This will also delete all associated timesheet entries.\n"
                f"This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                api.employees_delete(emp_id)
                self.refresh_all()
                _msg_ok(self, "Employee and associated timesheet entries deleted successfully.")
        except Exception as e:
            _msg_err(self, f"Failed to delete employee: {str(e)}")
    def _render_employees_table(self):
        q = self.empFilter.text().strip().lower()
        rows = self.employees
        if q:
            rows = [r for r in rows if q in (r.get("name", "") or "").lower()]

        readonly = self._is_readonly_employee_user()

        self.empTable.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.empTable.setItem(i, 0, QTableWidgetItem(str(r.get("staff_id", ""))))
            self.empTable.setItem(i, 1, QTableWidgetItem(r.get("name", "")))

            # ✅ If User OR readonly username "data": no actions column
            if session.ROLE == "User" or readonly:
                continue

            # Actions buttons (Edit/Delete)
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(2)

            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda _, emp_data=r: self._edit_employee(emp_data))
            edit_btn.setFixedWidth(60)
            btn_layout.addWidget(edit_btn)

            delete_btn = QPushButton("Delete")
            delete_btn.clicked.connect(lambda _, emp_id=r.get("id"): self._delete_employee(emp_id))
            delete_btn.setFixedWidth(60)
            btn_layout.addWidget(delete_btn)

            btn_container = QWidget()
            btn_container.setLayout(btn_layout)
            self.empTable.setCellWidget(i, 2, btn_container)

        # Adjust column widths
        header = self.empTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        if session.ROLE != "User" and not readonly:
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)


    # =========================================================
    # Categories (UPDATED + Budget)
    # =========================================================
    def _build_categories(self):
        lay = QVBoxLayout(self.tabCategories)

        top = QHBoxLayout()
        top.addWidget(QLabel("Company:"))

        self.catCompany = QComboBox()
        self.catCompany.addItem("All Companies", None)   # ✅ data=None يعني كل الشركات
        self.catCompany.currentIndexChanged.connect(self._load_category_tree)
        top.addWidget(self.catCompany)

        top.addStretch(1)
        lay.addLayout(top)

        bar = QHBoxLayout()
        self.btnCatAdd = QPushButton("➕ Add")
        self.btnCatEdit = QPushButton("✏️ Edit")
        self.btnCatDel = QPushButton("🗑 Delete")
        self.btnCatAdd.clicked.connect(lambda: self._ui_cat_add(as_child=False))
        self.btnCatEdit.clicked.connect(self._ui_cat_edit)
        self.btnCatDel.clicked.connect(self._ui_cat_delete)
        bar.addWidget(self.btnCatAdd)
        bar.addWidget(self.btnCatEdit)
        bar.addWidget(self.btnCatDel)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.catTree = QTreeWidget()
        self.catTree.setHeaderLabels(["Name", "Kind", "Level"])
        self.catTree.setColumnWidth(0, 320)
        self.catTree.setColumnWidth(1, 120)
        self.catTree.setColumnWidth(2, 60)

        self.catTree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.catTree.customContextMenuRequested.connect(self._cat_context_menu)
        self.catTree.itemDoubleClicked.connect(lambda item, col: self._ui_cat_edit())

        lay.addWidget(self.catTree, 1)

    
    def _build_projects(self):
        """Build the Projects management page"""
        lay = QVBoxLayout(self.tabProjects)

        # Top controls
        top_layout = QHBoxLayout()
        
        # Company filter
        top_layout.addWidget(QLabel("Company:"))
        self.projCompany = QComboBox()
        self.projCompany.addItem("All Companies", None)  # بينملى ديناميكياً بـ _fill_company_combos()

        self.projCompany.currentTextChanged.connect(self._load_projects)
        top_layout.addWidget(self.projCompany)
        
        # Status filter
        top_layout.addWidget(QLabel("Status:"))
        self.projStatus = QComboBox()
        self.projStatus.addItems(["All Statuses", "Active", "Completed", "On Hold", "Cancelled"])
        self.projStatus.currentTextChanged.connect(self._load_projects)
        top_layout.addWidget(self.projStatus)
        
        # Refresh button
        self.projRefresh = QPushButton("Refresh Projects")
        self.projRefresh.clicked.connect(self._load_projects)
        top_layout.addWidget(self.projRefresh)
        
        top_layout.addStretch(1)
        lay.addLayout(top_layout)

        # Projects table
        self.projTable = QTableWidget(0, 8)
        self.projTable.setHorizontalHeaderLabels([
            "Code", "Name", "Company", "Status", "Budget", "Spent", "Remaining", "Actions"
        ])
        self.projTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.projTable.verticalHeader().setVisible(False)
        self.projTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.projTable)

        # Add project form
        form_group = QGroupBox("Add New Project")
        form_layout = QVBoxLayout(form_group)
        
        # Form row 1
        row1 = QHBoxLayout()
        self.projCode = QLineEdit()
        self.projCode.setPlaceholderText("Project Code (e.g., PROJ001)")
        row1.addWidget(QLabel("Code:"))
        row1.addWidget(self.projCode)
        
        self.projName = QLineEdit()
        self.projName.setPlaceholderText("Project Name")
        row1.addWidget(QLabel("Name:"))
        row1.addWidget(self.projName)
        
        self.projComp = QComboBox()
        row1.addWidget(QLabel("Company:"))
        row1.addWidget(self.projComp)
        
        form_layout.addLayout(row1)
        
        # Form row 2
        row2 = QHBoxLayout()
        self.projDesc = QLineEdit()
        self.projDesc.setPlaceholderText("Project Description (optional)")
        row2.addWidget(QLabel("Description:"))
        row2.addWidget(self.projDesc)
        
        self.projBudget = QDoubleSpinBox()
        self.projBudget.setMinimum(0.0)
        self.projBudget.setMaximum(1e12)
        self.projBudget.setDecimals(2)
        self.projBudget.setPrefix("$")
        self.projBudget.setValue(0.0)
        row2.addWidget(QLabel("Budget:"))
        row2.addWidget(self.projBudget)
        
        self.projAdd = QPushButton("Add Project")
        self.projAdd.clicked.connect(self._add_project)
        row2.addWidget(self.projAdd)
        
        form_layout.addLayout(row2)
        lay.addWidget(form_group)
        
        # Load initial data
        self._load_projects()
        self._load_companies_for_projects()

    def _load_companies_for_projects(self):
        """Load companies for project form dropdown"""
        try:
            companies = api.companies_list()
            self.projComp.clear()
            for company in companies:
                self.projComp.addItem(company.get("name", ""), company.get("id"))
        except Exception as e:
            print(f"Failed to load companies: {e}")

    def _load_projects(self):
        """Load and display projects"""
        try:
            # Get filters
            company_name = self.projCompany.currentText()
            status_text = self.projStatus.currentText()
            
            company_id = None
            if company_name != "All Companies":
                # Find company ID
                companies = api.companies_list()
                for company in companies:
                    if company.get("name") == company_name:
                        company_id = company.get("id")
                        break
            
            status = None
            if status_text != "All Statuses":
                status = status_text.lower()
            
            # Load projects
            projects = api.projects_list(company_id=company_id, status=status) or []
            
            # Update table
            self.projTable.setRowCount(len(projects))
            for i, proj in enumerate(projects):
                self.projTable.setItem(i, 0, QTableWidgetItem(proj.get("code", "")))
                self.projTable.setItem(i, 1, QTableWidgetItem(proj.get("name", "")))
                self.projTable.setItem(i, 2, QTableWidgetItem(proj.get("company_name", "")))
                self.projTable.setItem(i, 3, QTableWidgetItem(proj.get("status", "").title()))
                
                # Financial data
                budget = proj.get("budget", 0)
                spent = proj.get("spent_amount", 0)
                remaining = proj.get("remaining_budget", budget - spent)
                
                self.projTable.setItem(i, 4, QTableWidgetItem(f"${budget:,.2f}"))
                self.projTable.setItem(i, 5, QTableWidgetItem(f"${spent:,.2f}"))
                self.projTable.setItem(i, 6, QTableWidgetItem(f"${remaining:,.2f}"))
                
                # Action buttons
                btn_layout = QHBoxLayout()
                btn_layout.setContentsMargins(2, 2, 2, 2)
                btn_layout.setSpacing(2)
                
                edit_btn = QPushButton("Edit")
                edit_btn.clicked.connect(lambda _, p=proj: self._edit_project(p))
                edit_btn.setFixedWidth(60)
                btn_layout.addWidget(edit_btn)
                
                delete_btn = QPushButton("Delete")
                delete_btn.clicked.connect(lambda _, pid=proj.get("id"): self._delete_project(pid))
                delete_btn.setFixedWidth(60)
                btn_layout.addWidget(delete_btn)
                
                btn_container = QWidget()
                btn_container.setLayout(btn_layout)
                self.projTable.setCellWidget(i, 7, btn_container)
            
            self.projTable.resizeColumnsToContents()
            
        except Exception as e:
            _msg_err(self, f"Failed to load projects: {str(e)}")

    def _add_project(self):
        """Add new project"""
        try:
            code = self.projCode.text().strip()
            name = self.projName.text().strip()
            description = self.projDesc.text().strip() or None
            budget = float(self.projBudget.value())
            company_id = self.projComp.currentData()
            
            if not code:
                _msg_err(self, "Project code required.")
                return
            
            if not name:
                _msg_err(self, "Project name required.")
                return
            
            if not company_id:
                _msg_err(self, "Please select a company.")
                return
            
            # Add project
            api.projects_add(
                code=code,
                name=name,
                company_id=company_id,
                description=description,
                budget=budget
            )
            
            # Clear form
            self.projCode.clear()
            self.projName.clear()
            self.projDesc.clear()
            self.projBudget.setValue(0.0)
            
            # Refresh
            self._load_projects()
            _msg_ok(self, "Project added successfully.")
            
        except Exception as e:
            _msg_err(self, f"Failed to add project: {str(e)}")

    def _edit_project(self, project_data: dict):
        """Edit existing project"""
        try:
            proj_id = project_data.get("id")
            current_code = project_data.get("code", "")
            current_name = project_data.get("name", "")
            current_desc = project_data.get("description", "")
            current_status = project_data.get("status", "active")
            current_budget = project_data.get("budget", 0.0)
            
            # Create edit dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Project")
            dialog.setModal(True)
            dialog.resize(400, 250)
            
            layout = QVBoxLayout(dialog)
            
            # Code
            code_label = QLabel("Project Code:")
            code_input = QLineEdit()
            code_input.setText(current_code)
            layout.addWidget(code_label)
            layout.addWidget(code_input)
            
            # Name
            name_label = QLabel("Project Name:")
            name_input = QLineEdit()
            name_input.setText(current_name)
            layout.addWidget(name_label)
            layout.addWidget(name_input)
            
            # Description
            desc_label = QLabel("Description:")
            desc_input = QLineEdit()
            desc_input.setText(current_desc or "")
            layout.addWidget(desc_label)
            layout.addWidget(desc_input)
            
            # Status
            status_label = QLabel("Status:")
            status_combo = QComboBox()
            status_combo.addItems(["Active", "Completed", "On Hold", "Cancelled"])
            status_combo.setCurrentText(current_status.title())
            layout.addWidget(status_label)
            layout.addWidget(status_combo)
            
            # Budget
            budget_label = QLabel("Budget:")
            budget_input = QDoubleSpinBox()
            budget_input.setMinimum(0.0)
            budget_input.setMaximum(1e12)
            budget_input.setDecimals(2)
            budget_input.setPrefix("$")
            budget_input.setValue(current_budget)
            layout.addWidget(budget_label)
            layout.addWidget(budget_input)
            
            # Buttons
            btn_layout = QHBoxLayout()
            save_btn = QPushButton("Save")
            cancel_btn = QPushButton("Cancel")
            btn_layout.addWidget(save_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)
            
            # Save function
            def save_project():
                try:
                    new_code = code_input.text().strip()
                    new_name = name_input.text().strip()
                    new_desc = desc_input.text().strip() or None
                    new_status = status_combo.currentText().lower()
                    new_budget = budget_input.value()
                    
                    if not new_code:
                        _msg_err(dialog, "Project code required.")
                        return
                    
                    if not new_name:
                        _msg_err(dialog, "Project name required.")
                        return
                    
                    # Update project
                    api.projects_update(
                        proj_id,
                        code=new_code,
                        name=new_name,
                        description=new_desc,
                        status=new_status,
                        budget=new_budget
                    )
                    
                    dialog.accept()
                    self._load_projects()
                    _msg_ok(self, "Project updated successfully.")
                    
                except Exception as e:
                    _msg_err(dialog, f"Failed to update project: {str(e)}")
            
            save_btn.clicked.connect(save_project)
            cancel_btn.clicked.connect(dialog.reject)
            
            dialog.exec()
            
        except Exception as e:
            _msg_err(self, f"Failed to edit project: {str(e)}")

    def _delete_project(self, project_id: int):
        try:
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                "Are you sure you want to delete this project?\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                api.projects_delete(project_id)
                self._load_projects()
                _msg_ok(self, "Project deleted successfully.")
        except Exception as e:
            _msg_err(self, f"Failed to delete project: {str(e)}")


    def _load_category_tree(self):
        try:
            self.catTree.clear()

            companies = api.companies_list() or []
            company_name_by_id = {int(c["id"]): c.get("name","") for c in companies if c.get("id") is not None}

            selected_company_id = None
            if hasattr(self, "catCompany"):
                selected_company_id = self.catCompany.currentData()  # ✅ None = all

            if selected_company_id is None:
                company_id = None
                show_company_ids = list(company_name_by_id.keys())
            else:
                company_id = int(selected_company_id)
                show_company_ids = [company_id]

            rows = api.categories_tree_flat(company_id=company_id) or []
            self.categories = rows

            # company roots
            root_by_cid = {}
            for cid in show_company_ids:
                cname = company_name_by_id.get(cid, f"Company {cid}")
                root = QTreeWidgetItem([cname, "", ""])
                root.setExpanded(True)
                root.setData(0, Qt.ItemDataRole.UserRole, {"_root": True, "company_id": cid, "name": cname})
                self.catTree.addTopLevelItem(root)
                root_by_cid[cid] = root

            items_by_id = {}
            for c in rows:
                item = self._create_tree_item(c)
                items_by_id[int(c["id"])] = item

            for c in rows:
                cid = int(c.get("company_id"))
                pid = c.get("parent_id")
                item = items_by_id[int(c["id"])]

                if pid is not None and int(pid) in items_by_id:
                    items_by_id[int(pid)].addChild(item)
                else:
                    root = root_by_cid.get(cid)
                    if root:
                        root.addChild(item)

            self.catTree.expandToDepth(2)

        except Exception as e:
            _msg_err(self, f"Failed to load category tree: {str(e)}")


    def _build_tree_with_company_roots(self, categories, company_by_id, show_company_ids):
    # Create root items for companies
        company_root_items = {}
        for cid in show_company_ids:
            cname = company_by_id.get(cid, f"Company {cid}")
            root = QTreeWidgetItem([cname, "", "", "", ""])
            root.setExpanded(True)
            self.catTree.addTopLevelItem(root)
            company_root_items[cid] = root

        # Create all items first
        items_by_id = {}
        for cat in categories:
            item = self._create_tree_item(cat)
            items_by_id[cat.get("id")] = item

        # Attach items to parent or company root
        for cat in categories:
            cid = cat.get("company_id")
            parent_id = cat.get("parent_id")

            item = items_by_id.get(cat.get("id"))
            if not item:
                continue

            if parent_id and parent_id in items_by_id:
                items_by_id[parent_id].addChild(item)
            else:
                # No parent -> attach to company root
                root = company_root_items.get(cid)
                if root:
                    root.addChild(item)


    def _populate_parent_combobox_with_company_roots(self, categories, company_by_id, show_company_ids):
        self.catParent.clear()
        self.catParent.addItem("Root Level", None)

        # Add company roots as selectable parents
        for cid in show_company_ids:
            cname = company_by_id.get(cid, f"Company {cid}")
            # store tuple so we know this is a company-root selection
            self.catParent.addItem(f"{cname} (Root)", ("company_root", cid))

        # Add categories
        for cat in categories:
            lvl = int(cat.get("level", 1) or 1)
            indent = "  " * (lvl - 1)
            name = cat.get("name", "")
            self.catParent.addItem(f"{indent}{name} (Level {lvl})", ("category", cat.get("id")))
        
    def _build_tree_from_list(self, categories):
        """Build tree structure from flat category list"""
        # Group categories by level and parent
        level_groups = {}
        for cat in categories:
            level = cat.get("level", 1)
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(cat)
        
        # Create root items
        root_items = []
        if 1 in level_groups:
            for cat in level_groups[1]:
                item = self._create_tree_item(cat)
                root_items.append(item)
                self.catTree.addTopLevelItem(item)
                # Process children
                self._add_children_to_item(item, cat.get("id"), level_groups, 2)
    
    def _add_children_to_item(self, parent_item, parent_id, level_groups, current_level):
        """Recursively add children to tree items"""
        if current_level not in level_groups:
            return
            
        for cat in level_groups[current_level]:
            if cat.get("parent_id") == parent_id:
                child_item = self._create_tree_item(cat)
                parent_item.addChild(child_item)
                # Continue with grandchildren
                self._add_children_to_item(child_item, cat.get("id"), level_groups, current_level + 1)
    
    def _create_tree_item(self, c: dict) -> QTreeWidgetItem:
        name = c.get("name", "")
        kind = c.get("kind", "")
        level = str(c.get("level", 1))

        item = QTreeWidgetItem([name, kind, level])
        # store full category payload on the item
        item.setData(0, Qt.ItemDataRole.UserRole, c)
        return item
    def _selected_cat_data(self) -> dict | None:
        item = self.catTree.currentItem()
        if not item:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _cat_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        act_add_child = menu.addAction("Add child")
        act_rename = menu.addAction("Rename / Edit")
        act_delete = menu.addAction("Delete")

        act = menu.exec(self.catTree.viewport().mapToGlobal(pos))
        if act == act_add_child:
            self._ui_cat_add(as_child=True)
        elif act == act_rename:
            self._ui_cat_edit()
        elif act == act_delete:
            self._ui_cat_delete()
    def _ui_cat_add(self, as_child: bool = False):
        try:
            sel = self._selected_cat_data()

            parent_id = None
            company_id = None

            if as_child:
                if not sel:
                    _msg_err(self, "Select a parent item first.")
                    return

                # If user clicked on company root
                if sel.get("_root"):
                    company_id = int(sel["company_id"])
                    parent_id = None
                else:
                    parent_id = int(sel["id"])
                    company_id = int(sel["company_id"])

            else:
                # Add root category under selected company filter
                selected_company = self.catCompany.currentText().strip()
                if selected_company == "All Companies":
                    comp, okc = QInputDialog.getItem(self, "Select Company", "Company:", COMPANIES, 0, False)
                    if not okc:
                        return
                    company_id = api._resolve_company_id(comp)
                else:
                    company_id = api._resolve_company_id(selected_company)
                parent_id = None

            name, ok = QInputDialog.getText(self, "Add Category", "Name:")
            if not ok or not name.strip():
                return

            kind, ok2 = QInputDialog.getItem(self, "Add Category", "Kind:", KINDS, 0, False)
            if not ok2:
                return

            # category_type: keep simple
            category_type = "other"

            # code unique
            import time
            clean = "".join(ch for ch in name if ch.isalnum())[:10].upper()
            code = f"CAT_{int(time.time())}_{clean}"

            api.categories_tree_add(
                code=code,
                name=name.strip(),
                parent_id=parent_id,
                company_id=int(company_id),
                category_type=category_type,
                kind=kind,
                budget=0.0,
                sort_order=0
            )

            self.refresh_all()
            _msg_ok(self, "Category added.")
        except Exception as e:
            _msg_err(self, f"Add failed: {str(e)}")

    def _ui_cat_edit(self):
        try:
            sel = self._selected_cat_data()
            if not sel:
                _msg_err(self, "Select an item first.")
                return

            # Prevent editing company root
            if sel.get("_root"):
                _msg_err(self, "Company root cannot be edited here.")
                return

            current_name = sel.get("name", "")
            current_kind = sel.get("kind", "overhead")

            new_name, ok = QInputDialog.getText(self, "Edit Category", "Name:", text=current_name)
            if not ok or not new_name.strip():
                return

            kind_index = KINDS.index(current_kind) if current_kind in KINDS else 0
            new_kind, ok2 = QInputDialog.getItem(self, "Edit Category", "Kind:", KINDS, kind_index, False)
            if not ok2:
                return

            api.categories_tree_update(int(sel["id"]), name=new_name.strip(), kind=new_kind)

            self.refresh_all()
            _msg_ok(self, "Category updated.")
        except Exception as e:
            _msg_err(self, f"Edit failed: {str(e)}")


    def _ui_cat_delete(self):
        try:
            sel = self._selected_cat_data()
            if not sel:
                _msg_err(self, "Select an item first.")
                return

            if sel.get("_root"):
                _msg_err(self, "Company root cannot be deleted.")
                return

            msg = "Delete this category?\nIf it has children, normal delete will fail."
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            try:
                api.categories_tree_delete(int(sel["id"]), cascade=False)
            except Exception:
                reply2 = QMessageBox.question(
                    self,
                    "Has children",
                    "This category has children.\nDo you want to cascade delete (delete all descendants)?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply2 != QMessageBox.StandardButton.Yes:
                    return
                api.categories_tree_delete(int(sel["id"]), cascade=True)

            self.refresh_all()
            _msg_ok(self, "Category deleted.")
        except Exception as e:
            _msg_err(self, f"Delete failed: {str(e)}")


    def _populate_parent_combobox(self, categories):
        """Populate parent category combobox"""
        # Add root level option
        self.catParent.addItem("Root Level", None)
        
        # Add all categories as potential parents
        for cat in categories:
            display_text = f"{'  ' * (cat.get('level', 1) - 1)}{cat.get('name', '')} (Level {cat.get('level', 1)})"
            self.catParent.addItem(display_text, cat.get("id"))
    
    def _add_category_tree(self):
        try:
            name = self.catName.text().strip()
            category_type = self.catType.currentText().strip()
            kind = self.catKind.currentText().strip()
            budget = float(self.catBudget.value())

            if not name:
                _msg_err(self, "Category name required.")
                return

            # parent selection: can be company root or category
            parent_data = self.catParent.currentData()
            parent_id = None
            company_id = None

            if parent_data is None:
                # no parent chosen => use selected company from dropdown
                company_id = api._resolve_company_id(self.catAddCompany.currentText())
            else:
                ptype, pid = parent_data
                if ptype == "company":
                    company_id = int(pid)
                    parent_id = None
                else:
                    parent_id = int(pid)
                    # inherit company_id from parent category
                    parent_cat = next((c for c in self.categories if int(c["id"]) == parent_id), None)
                    if not parent_cat:
                        _msg_err(self, "Parent category not found.")
                        return
                    company_id = int(parent_cat.get("company_id"))

            # generate code (unique)
            import time
            clean = "".join(ch for ch in name if ch.isalnum())[:10].upper()
            code = f"CAT_{int(time.time())}_{clean}"

            api.categories_tree_add(
                code=code,
                name=name,
                parent_id=parent_id,
                company_id=company_id,
                category_type=category_type,
                kind=kind,
                budget=budget,
                sort_order=0
            )

            self.catName.clear()
            self.catBudget.setValue(0.0)
            self.catParent.setCurrentIndex(0)

            self.refresh_all()  
            _msg_ok(self, "Category added successfully.")

        except Exception as e:
            _msg_err(self, f"Failed to add category: {str(e)}")

    def _toggle_budget_visibility(self, kind: str):
        kind = (kind or "").strip()
        self.catBudget.setVisible(kind == "project_name")

    def _add_category(self):
        try:
            name = self.catName.text().strip()
            kind = self.catKind.currentText().strip()

            if not name:
                _msg_err(self, "Category name required.")
                return

            # 🔒 HARD GUARD
            if session.ROLE == "DataEntry" and kind == "project_name":
                _msg_err(self, "You are not allowed to add Projects.")
                return

            budget = None
            if kind == "project_name":
                budget = float(self.catBudget.value())

            api.categories_add(name, kind, budget)

            self.catName.clear()
            self.catBudget.setValue(0.0)
            self.refresh_all()
            _msg_ok(self, "Category saved.")

        except Exception as e:
            _msg_err(self, str(e))  


    def _edit_category(self, cat_data: dict):
        try:
            cat_id = cat_data.get("id")
            current_name = cat_data.get("name", "")
            current_kind = cat_data.get("kind", "")
            current_budget = cat_data.get("budget", 0.0)
            
            # Create dialog for editing
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Category")
            dialog.setModal(True)
            dialog.resize(350, 200)
            
            layout = QVBoxLayout(dialog)
            
            # Name input
            name_label = QLabel("Category Name:")
            name_input = QLineEdit()
            name_input.setText(current_name)
            layout.addWidget(name_label)
            layout.addWidget(name_input)
            
            # Kind selection
            kind_label = QLabel("Category Kind:")
            kind_combo = QComboBox()
            if session.ROLE == "DataEntry":
                kind_combo.addItems(DATAENTRY_KINDS)
            else:
                kind_combo.addItems(KINDS)
            kind_combo.setCurrentText(current_kind)
            layout.addWidget(kind_label)
            layout.addWidget(kind_combo)
            
            # Budget input
            budget_label = QLabel("Budget:")
            budget_input = QDoubleSpinBox()
            budget_input.setMinimum(0.0)
            budget_input.setMaximum(1e12)
            budget_input.setDecimals(2)
            budget_input.setValue(float(current_budget) if current_budget else 0.0)
            budget_input.setVisible(current_kind == "project_name")
            layout.addWidget(budget_label)
            layout.addWidget(budget_input)
            
            # Update budget visibility when kind changes
            def toggle_budget_visibility(kind: str):
                budget_input.setVisible(kind == "project_name")
            
            kind_combo.currentTextChanged.connect(toggle_budget_visibility)
            
            # Buttons
            btn_layout = QHBoxLayout()
            ok_btn = QPushButton("Save")
            cancel_btn = QPushButton("Cancel")
            btn_layout.addWidget(ok_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)
            
            # Connect buttons
            def save_category():
                new_name = name_input.text().strip()
                new_kind = kind_combo.currentText().strip()
                new_budget = budget_input.value() if new_kind == "project_name" else None
                
                if not new_name:
                    _msg_err(dialog, "Category name required.")
                    return
                
                # 🔒 HARD GUARD
                if session.ROLE == "DataEntry" and new_kind == "project_name":
                    _msg_err(dialog, "You are not allowed to edit Projects.")
                    return
                
                try:
                    api.categories_update(cat_id, new_name, new_kind, new_budget)
                    dialog.accept()
                    self.refresh_all()
                    _msg_ok(self, "Category updated successfully.")
                except Exception as e:
                    _msg_err(dialog, f"Failed to update category: {str(e)}")
            
            ok_btn.clicked.connect(save_category)
            cancel_btn.clicked.connect(dialog.reject)
            
            # Show dialog
            if dialog.exec() == QDialog.DialogCode.Accepted:
                pass
                
        except Exception as e:
            _msg_err(self, f"Failed to edit category: {str(e)}")

    def _delete_category(self, cat_id: int):
        try:
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete category ID {cat_id}?\n"
                f"This will also delete all associated timesheet entries.\n"
                f"This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                api.categories_delete(cat_id)
                self.refresh_all()
                _msg_ok(self, "Category and associated timesheet entries deleted successfully.")
        except Exception as e:
            _msg_err(self, f"Failed to delete category: {str(e)}")


    def _render_categories_table(self):
        rows = self.categories
        if session.ROLE == "DataEntry":
            rows = [r for r in rows if r.get("kind") != "project_name"]

        self.catTable.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.catTable.setItem(i, 0, QTableWidgetItem(str(r.get("id", ""))))
            self.catTable.setItem(i, 1, QTableWidgetItem(r.get("name", "")))
            self.catTable.setItem(i, 2, QTableWidgetItem(r.get("kind", "")))

            b = r.get("budget", None)
            if b is None:
                txt = ""
            else:
                try:
                    txt = f"{float(b):.2f}"
                except Exception:
                    txt = str(b)

            it = QTableWidgetItem(txt)
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.catTable.setItem(i, 3, it)
            
            # Add edit and delete buttons
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(2)
            
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda _, cat_data=r: self._edit_category(cat_data))
            edit_btn.setFixedWidth(60)
            btn_layout.addWidget(edit_btn)
            
            delete_btn = QPushButton("Delete")
            delete_btn.clicked.connect(lambda _, cat_id=r.get("id"): self._delete_category(cat_id))
            delete_btn.setFixedWidth(60)
            btn_layout.addWidget(delete_btn)
            
            # Create container widget for buttons
            btn_container = QWidget()
            btn_container.setLayout(btn_layout)
            self.catTable.setCellWidget(i, 4, btn_container)

        self.catTable.resizeColumnsToContents()
        
        # Adjust column widths
        header = self.catTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)


    # =========================================================
    # Timesheet (Wizard + Scroll + ProSteel: Dept leaf -> Project)
    # Manual Save only (NO AUTO SAVE)
    # =========================================================

    def _build_timesheet(self):
        # ---- Scroll wrapper for the whole tab ----
        tab_lay = QVBoxLayout(self.tabTimesheet)
        tab_lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tab_lay.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        lay = QVBoxLayout(container)
        lay.setSpacing(10)
        lay.setContentsMargins(10, 10, 10, 10)

        title = QLabel("⏱️ Timesheet Entry (Step by Step)")
        title.setStyleSheet("font-size: 18px; font-weight: 800; padding: 6px;")
        lay.addWidget(title)

        # =========================
        # Step 1: Employee
        # =========================
        self.step1Box = QGroupBox("Step 1: Select Employee")
        s1 = QVBoxLayout(self.step1Box)
        s1.setContentsMargins(10, 10, 10, 10)
        s1.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Filter:"))
        self.tsEmpFilter = QLineEdit()
        self.tsEmpFilter.setPlaceholderText("Type employee name to filter...")
        self.tsEmpFilter.textChanged.connect(self._filter_timesheet_emps)
        row.addWidget(self.tsEmpFilter, 1)

        row.addWidget(QLabel("Select:"))
        self.tsEmp = QComboBox()
        self.tsEmp.currentIndexChanged.connect(self._on_step_employee_done)
        row.addWidget(self.tsEmp, 1)

        s1.addLayout(row)
        lay.addWidget(self.step1Box)

        # =========================
        # Step 2: Date/Period
        # =========================
        self.step2Box = QGroupBox("Step 2: Select Date/Period")
        s2 = QVBoxLayout(self.step2Box)
        s2.setContentsMargins(10, 10, 10, 10)
        s2.setSpacing(8)

        row2 = QHBoxLayout()
        self.tsMode = QComboBox()
        self.tsMode.addItems(["Daily", "Monthly"])
        self.tsMode.currentTextChanged.connect(self._ts_mode_changed)
        row2.addWidget(QLabel("Mode:"))
        row2.addWidget(self.tsMode)

        self.tsDate = QDateEdit()
        self.tsDate.setCalendarPopup(True)
        self.tsDate.setDate(QDate.currentDate())
        self.tsDate.dateChanged.connect(self._on_step_date_done)
        row2.addWidget(QLabel("Date:"))
        row2.addWidget(self.tsDate)

        self.tsYear = QSpinBox()
        self.tsYear.setRange(2020, 2100)
        self.tsYear.setValue(QDate.currentDate().year())
        self.tsYear.valueChanged.connect(self._on_step_date_done)

        self.tsMonth = QSpinBox()
        self.tsMonth.setRange(1, 12)
        self.tsMonth.setValue(QDate.currentDate().month())
        self.tsMonth.valueChanged.connect(self._on_step_date_done)

        row2.addWidget(QLabel("Year:"))
        row2.addWidget(self.tsYear)
        row2.addWidget(QLabel("Month:"))
        row2.addWidget(self.tsMonth)
        row2.addStretch(1)

        s2.addLayout(row2)
        lay.addWidget(self.step2Box)

        # =========================
        # Step 3: Company
        # =========================
        self.step3Box = QGroupBox("Step 3: Select Company")
        s3 = QVBoxLayout(self.step3Box)
        s3.setContentsMargins(10, 10, 10, 10)
        s3.setSpacing(8)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Company:"))

        self.tsCompany = QComboBox()
        self.tsCompany.addItem("All")
        self.tsCompany.currentTextChanged.connect(self._ts_company_changed)



        row3.addWidget(self.tsCompany, 1)
        row3.addStretch(1)
        s3.addLayout(row3)
        lay.addWidget(self.step3Box)

        # =========================
        # Step 4: Department leaf (and Project for ProSteel)
        # =========================
        self.step4Box = QGroupBox("Step 4: Select Department (Leaf) ثم Project (ProSteel only)")
        s4 = QVBoxLayout(self.step4Box)
        s4.setContentsMargins(10, 10, 10, 10)
        s4.setSpacing(8)

        self.tsCategoryTree = QTreeWidget()
        self.tsCategoryTree.setHeaderLabels(["Category", "Type", "Level"])
        self.tsCategoryTree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tsCategoryTree.itemSelectionChanged.connect(self._on_category_selected)
        self.tsCategoryTree.setMinimumHeight(170)
        s4.addWidget(self.tsCategoryTree)

        proj_row = QHBoxLayout()
        self.tsProjLabel = QLabel("Project:")
        self.tsProject = QComboBox()
        self.tsProject.addItem("Select project...", None)
        self.tsProject.currentIndexChanged.connect(self._on_project_selected)
        proj_row.addWidget(self.tsProjLabel)
        proj_row.addWidget(self.tsProject, 1)
        s4.addLayout(proj_row)

        lay.addWidget(self.step4Box)

        # =========================
        # Step 5: Timesheet table
        # =========================
        self.step5Box = QGroupBox("Step 5: Timesheet")
        s5 = QVBoxLayout(self.step5Box)
        s5.setContentsMargins(10, 10, 10, 10)
        s5.setSpacing(8)

        bottom = QHBoxLayout()
        self.tsTotal = QLabel("Total Hours: 0.00")
        self.tsTotal.setStyleSheet("font-weight: 800;")
        bottom.addWidget(self.tsTotal)

        self.tsManualSave = QPushButton("Save")
        self.tsManualSave.clicked.connect(self._save_timesheet)
        self.tsManualSave.setStyleSheet("padding: 5px 10px; font-weight: bold;")
        bottom.addWidget(self.tsManualSave)

        self.tsManualLoad = QPushButton("Load")
        self.tsManualLoad.clicked.connect(self._load_timesheet)
        self.tsManualLoad.setStyleSheet("padding: 5px 10px; font-weight: bold;")
        bottom.addWidget(self.tsManualLoad)

        bottom.addStretch(1)
        self.tsInfo = QLabel("Manual Save/Load (No Auto-save)")
        self.tsInfo.setStyleSheet("color:#64748b;")
        bottom.addWidget(self.tsInfo)
        s5.addLayout(bottom)

        self.tsTable = QTableWidget(0, 3)
        self.tsTable.setHorizontalHeaderLabels(["Reference", "Hours (0..24)", "Actions"])
        self.tsTable.verticalHeader().setVisible(False)
        self.tsTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tsTable.itemChanged.connect(self._on_timesheet_item_changed)
        s5.addWidget(self.tsTable)

        hdr = self.tsTable.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tsTable.setMinimumHeight(220)

        lay.addWidget(self.step5Box)

        # ---- initial visibility ----
        self.step2Box.setVisible(False)
        self.step3Box.setVisible(False)
        self.step4Box.setVisible(False)
        self.step5Box.setVisible(False)

        # project row hidden initially
        self.tsProjLabel.setVisible(False)
        self.tsProject.setVisible(False)

        # state cache
        self._ts_selected_leaf_item = None
        self._ts_projects_cache = []

        # init
        self._ts_mode_changed(self.tsMode.currentText())
        self._filter_timesheet_emps()

        # ✅ Ensure correct UI state for "All"
        self._ts_company_changed("All")


    def _on_step_employee_done(self, *_):
        self._ts_reset_company_to_all()

        emp_ok = bool(self.tsEmp.currentData())
        self.step2Box.setVisible(emp_ok)

        self.step3Box.setVisible(False)
        self.step4Box.setVisible(False)
        self.step5Box.setVisible(False)

        self.tsCategoryTree.clear()
        self.tsTable.setRowCount(0)
        self._update_timesheet_total()


    def _on_step_date_done(self, *_):
        if not self.step2Box.isVisible():
            return

        self._ts_reset_company_to_all()

        self.step3Box.setVisible(True)
        self.step4Box.setVisible(False)
        self.step5Box.setVisible(False)

        self.tsCategoryTree.clear()
        self.tsTable.setRowCount(0)
        self._update_timesheet_total()


    def _ts_reset_company_to_all(self):
        if not hasattr(self, "tsCompany"):
            return
        self.tsCompany.blockSignals(True)
        idx = self.tsCompany.findText("All")
        if idx >= 0:
            self.tsCompany.setCurrentIndex(idx)
        self.tsCompany.blockSignals(False)

        # طبق تأثير الشركة All (إخفاء الشجرة والجدول + تنظيف)
        self._ts_company_changed("All")

    def _ts_mode_changed(self, mode: str):
        is_daily = (mode == "Daily")
        self.tsDate.setVisible(is_daily)
        self.tsYear.setVisible(not is_daily)
        self.tsMonth.setVisible(not is_daily)
        self._update_timesheet_total()


    def _ts_company_changed(self, txt: str):
        company = (txt or "").strip()
        company_ok = (company != "All")

        # Reset UI common
        self.tsCategoryTree.clear()
        self.tsTable.setRowCount(0)
        self._update_timesheet_total()

        self.tsProject.blockSignals(True)
        self.tsProject.clear()
        self.tsProject.addItem("Select project...", None)
        self.tsProject.blockSignals(False)

        self.tsProjLabel.setVisible(False)
        self.tsProject.setVisible(False)
        self._ts_selected_leaf_item = None
        self._ts_projects_cache = []

        # ✅ Show/Hide tree based on company
        self.step4Box.setVisible(company_ok)
        self.step5Box.setVisible(False)

        if company_ok:
            self._load_category_hierarchy()


    def _filter_timesheet_emps(self):
        q = (self.tsEmpFilter.text() or "").strip().lower()

        self.tsEmp.blockSignals(True)
        try:
            self.tsEmp.clear()
            for e in (self.employees or []):
                name = (e.get("name") or "").strip()
                if not name:
                    continue
                if (not q) or (q in name.lower()):
                    self.tsEmp.addItem(name, e.get("id"))
        finally:
            self.tsEmp.blockSignals(False)

        self._on_step_employee_done()


    def _load_category_hierarchy(self):
        try:
            self.tsCategoryTree.clear()
            company_name = self.tsCompany.currentText().strip()
            if company_name == "All":
                return

            company_id = api._resolve_company_id(company_name)
            categories = api.categories_tree_flat(company_id=company_id) or []

            # cache for name lookup on load
            self._ts_cat_name_by_id = {int(c["id"]): (c.get("name") or "") for c in categories if c.get("id") is not None}

            self._build_ts_category_tree(categories)

                        # ✅ Load projects for ANY company (Tempo Glass + ProSteel)
            self._ts_projects_cache = []
            try:
                self._ts_projects_cache = api.projects_list(company_id=company_id) or []
            except Exception:
                self._ts_projects_cache = []


        except Exception as e:
            _msg_err(self, f"Failed to load category hierarchy: {str(e)}")


    def _build_ts_category_tree(self, categories):
        items_by_id: dict[int, QTreeWidgetItem] = {}

        for cat in categories:
            item = QTreeWidgetItem([
                cat.get("name", ""),
                cat.get("category_type", "") or cat.get("kind", ""),
                str(cat.get("level", 1)),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, {**cat, "_node_type": "category"})
            items_by_id[int(cat["id"])] = item

        for cat in categories:
            cid = int(cat["id"])
            pid = cat.get("parent_id")
            item = items_by_id[cid]
            if pid is not None and int(pid) in items_by_id:
                items_by_id[int(pid)].addChild(item)
            else:
                self.tsCategoryTree.addTopLevelItem(item)

        self.tsCategoryTree.expandToDepth(2)


    def _on_category_selected(self):
        items = self.tsCategoryTree.selectedItems()
        if not items:
            return

        item = items[0]

        # must be leaf
        if item.childCount() > 0:
            self.tsCategoryTree.blockSignals(True)
            self.tsCategoryTree.clearSelection()
            self.tsCategoryTree.blockSignals(False)
            _msg_err(self, "Please select a LEAF node (last level).")
            return

        company_name = self.tsCompany.currentText().strip()
        if company_name == "All":
            _msg_err(self, "Select a company first.")
            return

        # ✅ For ANY company: leaf -> choose project
        self._ts_selected_leaf_item = item

        # fill projects combo from cache
        self.tsProject.blockSignals(True)
        try:
            self.tsProject.clear()
            self.tsProject.addItem("Select project...", None)
            for p in (self._ts_projects_cache or []):
                self.tsProject.addItem(p.get("name", ""), p.get("id"))
        finally:
            self.tsProject.blockSignals(False)

        self.tsProjLabel.setVisible(True)
        self.tsProject.setVisible(True)

        # don't show table until project chosen
        self.step5Box.setVisible(False)



    def _on_project_selected(self, *_):
        company = self.tsCompany.currentText().strip()
        if company == "All":
            return

        proj_id = self.tsProject.currentData()
        if not proj_id:
            return

        if not self._ts_selected_leaf_item:
            _msg_err(self, "Select a Department leaf first.")
            return

        leaf_data = self._ts_selected_leaf_item.data(0, Qt.ItemDataRole.UserRole) or {}
        dept_id = leaf_data.get("id")
        if dept_id is None:
            _msg_err(self, "Invalid department selection.")
            return

        def build_path(it: QTreeWidgetItem) -> str:
            parts = []
            cur = it
            while cur is not None:
                parts.append(cur.text(0))
                cur = cur.parent()
            return " -> ".join(reversed(parts))

        dept_path = build_path(self._ts_selected_leaf_item)
        proj_name = self.tsProject.currentText().strip()
        row_label = f"{dept_path} -> {proj_name}"

        self._add_project_to_timesheet(
            dept_id=int(dept_id),
            dept_path=dept_path,
            project_id=int(proj_id),
            project_name=proj_name,
            label=row_label
        )
        self.step5Box.setVisible(True)

    def _add_project_to_timesheet(self, dept_id: int, dept_path: str, project_id: int, project_name: str, label: str):
        key = f"dept:{dept_id}|proj:{project_id}"

        for row in range(self.tsTable.rowCount()):
            it = self.tsTable.item(row, 0)
            if it and it.data(Qt.ItemDataRole.UserRole) == key:
                return

        row = self.tsTable.rowCount()
        self.tsTable.insertRow(row)

        name_item = QTableWidgetItem(label)
        name_item.setData(Qt.ItemDataRole.UserRole, key)
        name_item.setData(Qt.ItemDataRole.UserRole + 1, {
            "_node_type": "project",
            "dept_id": dept_id,
            "dept_path": dept_path,
            "project_id": project_id,
            "project_name": project_name,
        })
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.tsTable.setItem(row, 0, name_item)

        hours_item = QTableWidgetItem("0")
        hours_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.tsTable.setItem(row, 1, hours_item)

        btn = QPushButton("Remove")
        btn.clicked.connect(self._remove_timesheet_row_from_button)

        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.addWidget(btn)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tsTable.setCellWidget(row, 2, w)

        self._update_timesheet_total()


    def _add_category_to_timesheet(self, category_data: dict):
        category_id = int(category_data.get("id"))
        category_name = category_data.get("name", "")

        for row in range(self.tsTable.rowCount()):
            it = self.tsTable.item(row, 0)
            if it and it.data(Qt.ItemDataRole.UserRole) == category_id:
                return

        row = self.tsTable.rowCount()
        self.tsTable.insertRow(row)

        cat_item = QTableWidgetItem(category_name)
        cat_item.setData(Qt.ItemDataRole.UserRole, category_id)
        cat_item.setData(Qt.ItemDataRole.UserRole + 1, {"_node_type": "category", "category_id": category_id})
        cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.tsTable.setItem(row, 0, cat_item)

        hours_item = QTableWidgetItem("0")
        hours_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.tsTable.setItem(row, 1, hours_item)

        btn = QPushButton("Remove")
        btn.clicked.connect(self._remove_timesheet_row_from_button)

        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.addWidget(btn)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tsTable.setCellWidget(row, 2, w)

        self._update_timesheet_total()


    def _remove_timesheet_row_from_button(self):
        btn = self.sender()
        if not btn:
            return
        idx = self.tsTable.indexAt(btn.parent().pos())
        if idx.isValid():
            self.tsTable.removeRow(idx.row())
            self._update_timesheet_total()


    def _compute_table_total(self) -> float:
        total = 0.0
        for row in range(self.tsTable.rowCount()):
            it = self.tsTable.item(row, 1)
            if not it:
                continue
            try:
                total += float((it.text() or "0").strip())
            except Exception:
                pass
        return total


    def _update_timesheet_total(self):
        self.tsTotal.setText(f"Total Hours: {self._compute_table_total():.2f}")


    def _on_timesheet_item_changed(self, item: QTableWidgetItem):
        if item.column() != 1:
            return

        txt = (item.text() or "").strip()
        if txt == "":
            item.setText("0")
            self._update_timesheet_total()
            return

        try:
            hours = float(txt)
        except Exception:
            self._update_timesheet_total()
            return

        if hours < 0:
            item.setText("0")
        elif hours > 24:
            item.setText("24")

        self._update_timesheet_total()


    def _collect_timesheet_payload(self) -> list[dict]:
        entries = []
        for row in range(self.tsTable.rowCount()):
            ref_it = self.tsTable.item(row, 0)
            hrs_it = self.tsTable.item(row, 1)
            if not ref_it or not hrs_it:
                continue

            meta = ref_it.data(Qt.ItemDataRole.UserRole + 1) or {}
            try:
                hours = float((hrs_it.text() or "0").strip())
            except Exception:
                hours = 0.0

            # ignore zeros (we don't save zeros)
            if hours <= 0:
                continue

            if meta.get("_node_type") == "project":
                entries.append({
                    "category_id": int(meta["dept_id"]),
                    "project_id": int(meta["project_id"]),
                    "hours": float(hours),
                })
            else:
                cat_id = ref_it.data(Qt.ItemDataRole.UserRole)
                entries.append({"category_id": int(cat_id), "project_id": None, "hours": float(hours)})

        return entries


    def _save_timesheet(self):
        """Manual Save ONLY."""
        try:
            emp_id = self.tsEmp.currentData()
            if not emp_id:
                _msg_err(self, "Select employee first.")
                return

            company = self.tsCompany.currentText().strip()
            if company == "All":
                _msg_err(self, "Select a specific company to Save.")
                return

            entries = self._collect_timesheet_payload()

            if self.tsMode.currentText() == "Daily":
                date_str = self.tsDate.date().toString("yyyy-MM-dd")
                api.timesheet_daily_bulk_upsert(int(emp_id), date_str, company, entries)
            else:
                year = int(self.tsYear.value())
                month = int(self.tsMonth.value())
                api.timesheet_bulk_upsert(int(emp_id), year, month, company, entries)

            self.tsInfo.setText("Saved ✔ (Manual)")
            _msg_ok(self, "Saved.")

        except Exception as e:
            self.tsInfo.setText("Save failed")
            _msg_err(self, f"Save failed: {str(e)}")


    def _load_timesheet(self):
        """Load ONLY (never saves)."""
        try:
            emp_id = self.tsEmp.currentData()
            if not emp_id:
                _msg_err(self, "Select employee first.")
                return

            company = self.tsCompany.currentText().strip()
            if company == "All":
                _msg_err(self, "Select a specific company to Load.")
                return

            if not hasattr(self, "_ts_cat_name_by_id"):
                self._load_category_hierarchy()

            if self.tsMode.currentText() == "Daily":
                date_str = self.tsDate.date().toString("yyyy-MM-dd")
                res = api.timesheet_get_daily_sheet(int(emp_id), date_str, company)
            else:
                year = int(self.tsYear.value())
                month = int(self.tsMonth.value())
                res = api.timesheet_get_sheet(int(emp_id), year, month, company)

            rows = (res.get("entries") if isinstance(res, dict) else res) or []

            self.tsTable.blockSignals(True)
            try:
                self.tsTable.setRowCount(0)

                for r in rows:
                    cat_id = int(r.get("category_id"))
                    hours = float(r.get("hours", 0.0))
                    proj_id = r.get("project_id")

                    if proj_id is not None:
                        dept_name = self._ts_cat_name_by_id.get(cat_id, f"Dept {cat_id}")
                        proj_name = r.get("project_name")
                        if not proj_name:
                            nm = (r.get("name") or "").strip()
                            if "->" in nm:
                                proj_name = nm.split("->")[-1].strip()

                        if not proj_name:
                            proj_name = f"Project {proj_id}"
                        label = f"{dept_name} -> {proj_name}"

                        self._add_project_to_timesheet(
                            dept_id=cat_id,
                            dept_path=dept_name,
                            project_id=int(proj_id),
                            project_name=proj_name,
                            label=label,
                        )
                    else:
                        name = self._ts_cat_name_by_id.get(cat_id, f"Category {cat_id}")
                        self._add_category_to_timesheet({"id": cat_id, "name": name})

                    last_row = self.tsTable.rowCount() - 1
                    if last_row >= 0:
                        self.tsTable.item(last_row, 1).setText(f"{hours:g}")

            finally:
                self.tsTable.blockSignals(False)

            self._update_timesheet_total()
            self.step5Box.setVisible(True)
            _msg_ok(self, "Loaded.")

        except Exception as e:
            _msg_err(self, f"Load failed: {str(e)}")



  # =========================================================
    # Payments (Monthly + Optional Default Salary)
    # =========================================================
    def _build_payments(self):
        lay = QVBoxLayout(self.tabPayments)

        # ----- Default Salary (optional) -----
        boxSalary = QGroupBox("Default Salary (set once) - optional")
        boxLay = QVBoxLayout(boxSalary)

        salTop = QHBoxLayout()
        self.salEmpFilter = QLineEdit()
        self.salEmpFilter.setPlaceholderText("Filter employee...")
        self.salEmpFilter.textChanged.connect(self._render_salary_table)
        salTop.addWidget(self.salEmpFilter)

        self.salLoadAll = QPushButton("Load Salaries")
        self.salLoadAll.clicked.connect(self._load_salaries)
        salTop.addWidget(self.salLoadAll)

        self.salSaveAll = QPushButton("Save Changes")
        self.salSaveAll.clicked.connect(self._save_salaries)
        salTop.addWidget(self.salSaveAll)

        salTop.addStretch(1)
        boxLay.addLayout(salTop)

        self.salTable = QTableWidget(0, 3)
        self.salTable.setHorizontalHeaderLabels(["Employee ID", "Employee", "Salary"])
        self.salTable.verticalHeader().setVisible(False)
        boxLay.addWidget(self.salTable)

        note1 = QLabel("إذا ما عندك endpoints للسالاري بالـ backend، هالقسم رح يعطي Error واضح.")
        note1.setStyleSheet("color:#94a3b8;")
        boxLay.addWidget(note1)

        lay.addWidget(boxSalary)

        # ----- Monthly override -----
        boxMonth = QGroupBox("Monthly Payment (override)")
        mLay = QVBoxLayout(boxMonth)

        top = QHBoxLayout()
        self.payYear = QSpinBox(); self.payYear.setMinimum(2020); self.payYear.setMaximum(2100); self.payYear.setValue(QDate.currentDate().year())
        self.payMonth = QSpinBox(); self.payMonth.setMinimum(1); self.payMonth.setMaximum(12); self.payMonth.setValue(QDate.currentDate().month())
        self.payEmp = QComboBox()

        self.payAmount = QDoubleSpinBox()
        self.payAmount.setMinimum(0.0)
        self.payAmount.setMaximum(1e12)
        self.payAmount.setDecimals(2)

        self.payLoad = QPushButton("Load")
        self.paySave = QPushButton("Save (Locked)")
        self.payLoad.clicked.connect(self._load_payment)
        self.paySave.clicked.connect(self._save_payment)

        top.addWidget(QLabel("Year")); top.addWidget(self.payYear)
        top.addWidget(QLabel("Month")); top.addWidget(self.payMonth)
        top.addWidget(QLabel("Employee")); top.addWidget(self.payEmp)
        top.addWidget(QLabel("Amount")); top.addWidget(self.payAmount)
        top.addWidget(self.payLoad); top.addWidget(self.paySave)
        top.addStretch(1)
        mLay.addLayout(top)

        note = QLabel("Payments are restricted to HR/Admin (server-side).")
        note.setStyleSheet("color:#94a3b8;")
        mLay.addWidget(note)

        lay.addWidget(boxMonth)

    def _load_salaries(self):
        try:
            fn = _api_optional("salary_list")
            if not fn:
                raise Exception("Missing API: salary_list")
            self._salary_rows = fn() or []
            self._render_salary_table()
        except Exception as e:
            _msg_err(self, str(e))

    def _render_salary_table(self):
        q = (self.salEmpFilter.text().strip().lower() if hasattr(self, "salEmpFilter") else "")
        rows = self._salary_rows if hasattr(self, "_salary_rows") else []
        if q:
            rows = [r for r in rows if q in (r.get("employee_name", "") or "").lower()]

        self.salTable.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.salTable.setItem(i, 0, QTableWidgetItem(str(r.get("employee_id", ""))))
            self.salTable.setItem(i, 1, QTableWidgetItem(r.get("employee_name", "")))

            sal_item = QTableWidgetItem(f"{float(r.get('salary', 0.0)):.2f}")
            sal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.salTable.setItem(i, 2, sal_item)

        self.salTable.resizeColumnsToContents()

    def _save_salaries(self):
        try:
            fn = _api_optional("salary_upsert_bulk")
            if not fn:
                raise Exception("Missing API: salary_upsert_bulk")

            payload = []
            for row in range(self.salTable.rowCount()):
                emp_id = int(self.salTable.item(row, 0).text())
                txt = (self.salTable.item(row, 2).text() or "0").strip()
                salary = float(txt)
                if salary < 0:
                    raise Exception(f"Salary must be >= 0 (row {row+1})")
                payload.append({"employee_id": emp_id, "salary": salary})

            fn(payload)
            _msg_ok(self, "Default salaries saved.")
            self._load_salaries()
        except Exception as e:
            _msg_err(self, str(e))

    def _load_payment(self):
        try:
            emp_id = self.payEmp.currentData()
            if not emp_id:
                _msg_err(self, "Select employee.")
                return
            year = int(self.payYear.value())
            month = int(self.payMonth.value())
            res = api.payment_get(emp_id, year, month)
            self.payAmount.setValue(float(res.get("amount", 0.0)))
        except Exception as e:
            _msg_err(self, str(e))

    def _save_payment(self):
        try:
            emp_id = self.payEmp.currentData()
            if not emp_id:
                _msg_err(self, "Select employee.")
                return
            year = int(self.payYear.value())
            month = int(self.payMonth.value())
            amount = float(self.payAmount.value())
            api.payment_upsert(emp_id, year, month, amount)
            _msg_ok(self, "Payment saved.")
        except Exception as e:
            _msg_err(self, str(e))


    # =========================================================
    # Reports (Pivot like Excel) - COMPLETE (drop-in)
    # Put ALL of this inside your MainWindow class.
    # Remove/replace any older Reports functions to avoid duplicates.
    # =========================================================

    def _build_report(self):
        lay = QVBoxLayout(self.tabReport)

        # ---------------- Filters ----------------
        top = QHBoxLayout()

        self.repYear = QSpinBox()
        self.repYear.setRange(2020, 2100)
        self.repYear.setValue(QDate.currentDate().year())

        self.repMonth = QSpinBox()
        self.repMonth.setRange(1, 12)
        self.repMonth.setValue(QDate.currentDate().month())

        self.repCompany = QComboBox()
        self.repCompany.addItems(["All"] + list(COMPANIES))

        self.repEmployee = QComboBox()
        self.repEmployee.addItem("All Employees", None)

        self.repEmpFilter = QLineEdit()
        self.repEmpFilter.setPlaceholderText("Filter employee...")

        self.repChkOverheads = QCheckBox("Overheads")
        self.repChkOverheads.setChecked(True)

        self.repChkStages = QCheckBox("Stages")
        self.repChkStages.setChecked(True)

        # ✅ NEW: Excel-like Matrix (Stages x Overheads)
        self.repChkMatrix = QCheckBox("Leaf x Project (Excel)")

        self.repChkMatrix.setChecked(True)

        self.repRefresh = QPushButton("Refresh")
        self.repExport = QPushButton("Export CSV (raw)")

        # ✅ CONNECTS
        self.repYear.valueChanged.connect(self._load_report)
        self.repMonth.valueChanged.connect(self._load_report)
        self.repCompany.currentTextChanged.connect(self._load_report)
        self.repEmployee.currentIndexChanged.connect(self._load_report)
        self.repEmpFilter.textChanged.connect(self._filter_report_employees)
        self.repRefresh.clicked.connect(self._load_report)
        self.repExport.clicked.connect(self._export_report_csv)

        # toggles re-render (no re-fetch)
        self.repChkOverheads.toggled.connect(lambda *_: self._render_report_pivots())
        self.repChkStages.toggled.connect(lambda *_: self._render_report_pivots())
        self.repChkMatrix.toggled.connect(lambda *_: self._render_report_pivots())

        top.addWidget(QLabel("Year")); top.addWidget(self.repYear)
        top.addWidget(QLabel("Month")); top.addWidget(self.repMonth)
        top.addWidget(QLabel("Company")); top.addWidget(self.repCompany)
        top.addWidget(QLabel("Employee")); top.addWidget(self.repEmployee)
        top.addWidget(QLabel("Filter")); top.addWidget(self.repEmpFilter)

        top.addWidget(self.repChkOverheads)
        top.addWidget(self.repChkStages)
        top.addWidget(self.repChkMatrix)  # ✅ here exactly

        top.addWidget(self.repRefresh)
        top.addWidget(self.repExport)
        top.addStretch(1)
        lay.addLayout(top)

        # ---------------- Scroll area for ALL report sections ----------------
        self.repScroll = QScrollArea()
        self.repScroll.setWidgetResizable(True)
        lay.addWidget(self.repScroll, 1)

        self.repScrollBody = QWidget()
        self.repScroll.setWidget(self.repScrollBody)

        self.repBodyLay = QVBoxLayout(self.repScrollBody)
        self.repBodyLay.setContentsMargins(10, 10, 10, 10)
        self.repBodyLay.setSpacing(14)

        # store sections widgets here
        self._rep_sections = {}
        self._report_rows = []
        self._rep_cat_index_by_companyname = {}

        # ---------------- Summary (global) ----------------
        self.repSummary = QLabel("Total: Hours=0.00 | Allocated=0.00 | $=0.00")
        self.repSummary.setStyleSheet("font-weight:700; padding:6px;")
        lay.addWidget(self.repSummary)

    # ---------------------------
    # Helpers (UI)
    # ---------------------------

    def _rep_apply_table_style(self, table: QTableWidget):
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setWordWrap(True)

        # IMPORTANT: let PAGE scroll, not the table
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


    def _rep_fit_table_height(self, table: QTableWidget):
        """
        Make QTableWidget show ALL rows (no internal vertical scroll).
        Works well inside a QScrollArea.
        """
        # small guard
        if table.rowCount() <= 0:
            table.setFixedHeight(90)
            return

        vh = table.verticalHeader()
        hh = table.horizontalHeader()

        height = 0
        height += hh.height()

        # add all row heights (already set by us)
        for r in range(table.rowCount()):
            height += vh.sectionSize(r)

        # add frame + a bit padding
        height += 14
        table.setFixedHeight(height)


    # ---------------------------
    # Employees dropdown filter
    # ---------------------------

    def _filter_report_employees(self):
        q = (self.repEmpFilter.text() or "").strip().lower()

        self.repEmployee.blockSignals(True)
        try:
            self.repEmployee.clear()
            self.repEmployee.addItem("All Employees", None)

            for e in (self.employees or []):
                name = (e.get("name") or "").strip()
                if not name:
                    continue
                if (not q) or (q in name.lower()):
                    self.repEmployee.addItem(name, e.get("id"))
            self.repEmployee.setCurrentIndex(0)
        finally:
            self.repEmployee.blockSignals(False)

        # only re-render if we already loaded rows
        if getattr(self, "_report_rows", None) is not None:
            self._render_report_pivots()


    # ---------------------------
    # Category Index per company (from tree)
    # (Fixes: cross-company leak + "missing" due to duplicate names)
    # ---------------------------

    def _build_cat_index(self, company_id: int) -> dict:
        """
        Returns dict with:
        - meta_by_id: {id: meta}
        - metas_by_name: {name: [meta, meta, ...]}  (supports duplicates!)
        meta includes:
        id, name, kind, level, parent_id, parent_name, is_leaf, path(list), path_str, sort
        """
        cats = api.categories_tree_flat(company_id=company_id) or []

        by_id = {}
        children = set()

        for c in cats:
            cid = int(c.get("id"))
            pid = c.get("parent_id")
            if pid is not None:
                children.add(int(pid))

            by_id[cid] = {
                "id": cid,
                "name": (c.get("name") or "").strip(),
                "kind": (c.get("kind") or "").strip(),
                "level": int(c.get("level", 1) or 1),
                "parent_id": int(pid) if pid is not None else None,
                # optional ordering if your API has it
                "sort": c.get("sort") if c.get("sort") is not None else (
                    c.get("order") if c.get("order") is not None else c.get("position")
                ),
            }

        # parent_name + is_leaf
        for cid, m in by_id.items():
            pid = m["parent_id"]
            m["parent_name"] = (by_id.get(pid, {}).get("name", "") if pid else "")
            m["is_leaf"] = (cid not in children)

        # compute path for each node (memoized)
        _path_cache = {}

        def _path_for(cid: int) -> list:
            if cid in _path_cache:
                return _path_cache[cid]
            cur = by_id.get(cid)
            if not cur:
                _path_cache[cid] = []
                return []
            nm = (cur.get("name") or "").strip()
            pid = cur.get("parent_id")
            if pid:
                p = _path_for(int(pid))
                out = p + ([nm] if nm else [])
            else:
                out = ([nm] if nm else [])
            _path_cache[cid] = out
            return out

        for cid, m in by_id.items():
            p = _path_for(cid)
            m["path"] = p
            m["path_str"] = " / ".join(p)

        # name -> list of metas (NOT last-wins)
        metas_by_name = {}
        for m in by_id.values():
            nm = (m.get("name") or "").strip()
            if not nm:
                continue
            metas_by_name.setdefault(nm, []).append(m)

        return {"meta_by_id": by_id, "metas_by_name": metas_by_name}


    def _prepare_report_cat_indexes(self):
        self._rep_cat_index_by_companyname = {}

        company_names = [c.get("name","") for c in (self.companies or []) if c.get("name")]
        if not company_names:
            company_names = list(COMPANIES_FALLBACK)

        for comp in company_names:
            try:
                cid = api._resolve_company_id(comp)
                self._rep_cat_index_by_companyname[comp] = self._build_cat_index(cid)
            except Exception:
                self._rep_cat_index_by_companyname[comp] = {"meta_by_id": {}, "metas_by_name": {}}

    # ---------------------------
    # Sections (per company) - NO QLabel deleted errors
    # ---------------------------

    def _report_clear_sections(self):
        if not hasattr(self, "repBodyLay"):
            return

        while self.repBodyLay.count():
            item = self.repBodyLay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        self._rep_sections = {}


    def _ensure_report_sections(self, company_names):
        """
        Build UI sections per company:
        - groupbox title = company
        - Overheads table
        - Stages table
        - Matrix table (Stages x Overheads)
        - section summary
        """
        self._report_clear_sections()

        for comp in company_names:
            box = QGroupBox(comp)
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(10, 10, 10, 10)
            box_lay.setSpacing(10)

            # Overheads
            over_title = QLabel("Overheads")
            over_title.setStyleSheet("font-weight:800;")
            box_lay.addWidget(over_title)

            over_table = QTableWidget()
            self._rep_apply_table_style(over_table)
            box_lay.addWidget(over_table)

            # Stages
            stage_title = QLabel("Stages / Operations")
            stage_title.setStyleSheet("font-weight:800; margin-top:6px;")
            box_lay.addWidget(stage_title)

            stage_table = QTableWidget()
            self._rep_apply_table_style(stage_table)
            box_lay.addWidget(stage_table)

            # ✅ NEW: Matrix like Excel (Stages x Overheads)
            matrix_title = QLabel("Leaf x Project (Excel)")

            matrix_title.setStyleSheet("font-weight:800; margin-top:6px;")
            box_lay.addWidget(matrix_title)

            matrix_table = QTableWidget()
            self._rep_apply_table_style(matrix_table)
            box_lay.addWidget(matrix_table)

            # Section summary (per company)
            sec_sum = QLabel("Company Total: Hours=0.00 | Allocated=0.00 | $=0.00")
            sec_sum.setStyleSheet("color:#334155; font-weight:700; padding:4px;")
            box_lay.addWidget(sec_sum)

            self.repBodyLay.addWidget(box)

            self._rep_sections[comp] = {
                "box": box,
                "over_table": over_table,
                "stage_table": stage_table,
                "matrix_title": matrix_title,
                "matrix_table": matrix_table,
                "sec_sum": sec_sum,
            }

        self.repBodyLay.addStretch(1)

    # ---------------------------
    # Salary (optional)
    # ---------------------------

    def _get_salary_by_employee(self) -> dict:
        """
        Optional: API may have salary_list() -> [{employee_name, salary}, ...]
        Returns: {employee_name: salary_float}
        """
        out = {}
        try:
            fn = None
            if " _api_optional" in globals():
                try:
                    fn = _api_optional("salary_list")
                except Exception:
                    fn = None
            if fn is None:
                fn = getattr(api, "salary_list", None)

            if not fn:
                return out

            rows = fn() or []
            for r in rows:
                nm = (r.get("employee_name") or r.get("employee") or "").strip()
                if nm:
                    out[nm] = float(r.get("salary", 0.0) or 0.0)
        except Exception:
            return out
        return out


    # ---------------------------
    # Load report rows
    # ---------------------------

    def _load_report(self):
        try:
            year = int(self.repYear.value())
            month = int(self.repMonth.value())
            company = (self.repCompany.currentText() or "").strip()
            emp_id = self.repEmployee.currentData()  # None = all employees

            company_names = [c.get("name","") for c in (self.companies or []) if c.get("name")]
            if not company_names:
                company_names = list(COMPANIES_FALLBACK)

            rows = []
            if company == "All":
                for comp in company_names:
                    part = api.report_allocation(year, month, comp, emp_id) or []
                    for r in part:
                        r["company"] = comp
                    rows.extend(part)
            else:
                part = api.report_allocation(year, month, company, emp_id) or []
                for r in part:
                    r["company"] = company
                rows = part

            # normalize
            for r in rows:
                r["employee"] = (r.get("employee") or r.get("employee_name") or "").strip()
                r["category"] = (r.get("category") or r.get("category_name") or "").strip()
                r["kind"] = (r.get("kind") or "").strip()

                if "hours" not in r and "total" in r:
                    r["hours"] = float(r.get("total", 0.0) or 0.0)
                r["hours"] = float(r.get("hours", 0.0) or 0.0)

                r["allocated"] = float(r.get("allocated", 0.0) or 0.0)

                if "category_id" in r:
                    try:
                        r["category_id"] = int(r.get("category_id"))
                    except Exception:
                        pass

                r["company"] = (r.get("company") or "").strip()

            self._report_rows = rows
            self._prepare_report_cat_indexes()

            companies_to_show = company_names if company == "All" else [company]
            self._ensure_report_sections(companies_to_show)

            self._render_report_pivots()

        except Exception as e:
            _msg_err(self, str(e))

    # ---------------------------
    # Overheads pivot (with totals $)
    # ---------------------------
    def _build_stage_overhead_matrix_excel(
        self,
        table: QTableWidget,
        matrix_rows: list,
        row_labels: list[str],
        col_labels: list[str],
    ):
        """
        matrix_rows: list of dict rows {row_name, col_name, amount}
        row_labels: ordered rows
        col_labels: ordered cols
        """
        m = {}
        for r in matrix_rows:
            rn = (r.get("row_name") or "").strip()
            cn = (r.get("col_name") or "").strip()
            amt = float(r.get("amount", 0.0) or 0.0)
            if rn and cn:
                m[(rn, cn)] = m.get((rn, cn), 0.0) + amt

        table.blockSignals(True)
        try:
            table.clear()
            headers = ["Overhead"] + col_labels + ["Total"]

            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)

            table.setRowCount(len(row_labels) + 1)  # + TOTAL row

            # body
            for ri, row_name in enumerate(row_labels):
                table.setItem(ri, 0, QTableWidgetItem(row_name))

                row_total = 0.0
                for ci, col_name in enumerate(col_labels, start=1):
                    v = float(m.get((row_name, col_name), 0.0) or 0.0)
                    row_total += v
                    it = QTableWidgetItem("-" if v <= 0 else f"${v:,.2f}")
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(ri, ci, it)

                it_tot = QTableWidgetItem(f"${row_total:,.2f}")
                it_tot.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(ri, 1 + len(col_labels), it_tot)

            # TOTAL row
            tr = len(row_labels)
            it_total = QTableWidgetItem("TOTAL")
            it_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(tr, 0, it_total)

            grand = 0.0
            for ci, col_name in enumerate(col_labels, start=1):
                col_sum = 0.0
                for row_name in row_labels:
                    col_sum += float(m.get((row_name, col_name), 0.0) or 0.0)
                grand += col_sum
                it = QTableWidgetItem(f"${col_sum:,.2f}")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(tr, ci, it)

            it_grand = QTableWidgetItem(f"${grand:,.2f}")
            it_grand.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(tr, 1 + len(col_labels), it_grand)

            # sizing
            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for c in range(1, table.columnCount()):
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

            for r in range(table.rowCount()):
                table.setRowHeight(r, 36)

            self._rep_fit_table_height(table)

        finally:
            table.blockSignals(False)

    def _safe_span(self, table: QTableWidget, row: int, col: int, row_span: int, col_span: int):
        """Avoid Qt warning: span of 1x1 is ignored."""
        if row_span <= 1 and col_span <= 1:
            return
        table.setSpan(row, col, row_span, col_span)

    def _build_excel_matrix_like_screenshot(self, table: QTableWidget, matrix_rows: list, company: str | None = None):
        """
        Excel-like Matrix:
        - Departments group stays as-is
        - Stages group becomes Aluminum / Steel (from category tree path using category_id)
        """

        def norm(s: str) -> str:
            return (s or "").strip()

        def mk_item(text: str, bold=False, center=True, bg: QColor | None = None):
            it = QTableWidgetItem(text)
            if center:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if bold:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            if bg:
                it.setBackground(bg)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return it

        def set_span_safe(r: int, c: int, rs: int, cs: int):
            if rs > 1 or cs > 1:
                table.setSpan(r, c, rs, cs)

        # --- lookup from tree (to get Aluminum / Steel) ---
        meta_by_id = {}
        try:
            if company:
                idx = (getattr(self, "_rep_cat_index_by_companyname", {}) or {}).get(company, {}) or {}
                meta_by_id = idx.get("meta_by_id", {}) or {}
        except Exception:
            meta_by_id = {}

        # ---------- collect values ----------
        group_cols: dict[str, list[str]] = {}
        row_names: list[str] = []
        val = {}  # (row, group, leaf) -> amount

        for r in (matrix_rows or []):
            rn = norm(r.get("row_name"))
            if rn and rn not in row_names:
                row_names.append(rn)

            grp = norm(r.get("col_group"))     # "Departments" or "Stages"
            leaf = norm(r.get("col_name"))     # "Fabrication" / "Installation" / dept name ...
            amt = float(r.get("amount", 0.0) or 0.0)

            # ✅ NEW: if this is stage column, derive parent group from category tree path
            # try many keys for id
            cid = r.get("col_category_id")
            if cid is None:
                cid = r.get("category_id")
            if cid is None:
                cid = r.get("col_id")

            if cid is not None:
                try:
                    cid = int(cid)
                    m = meta_by_id.get(cid)
                    if m:
                        p = m.get("path") or []
                        # leaf = last node, group = parent node (Aluminum/Steel)
                        if len(p) >= 2:
                            parent_name = (p[-2] or "").strip()
                            leaf_name = (p[-1] or "").strip()
                            if (grp.lower() in ("stages", "stage")) and parent_name:
                                grp = parent_name
                                leaf = leaf_name or leaf
                        elif len(p) == 1:
                            # fallback
                            if grp.lower() in ("stages", "stage"):
                                leaf = (p[-1] or leaf).strip()
                except Exception:
                    pass

            if not grp:
                grp = "Other"

            if leaf:
                group_cols.setdefault(grp, [])
                if leaf not in group_cols[grp]:
                    group_cols[grp].append(leaf)

            if rn and grp and leaf:
                val[(rn, grp, leaf)] = val.get((rn, grp, leaf), 0.0) + amt

        # ---------- ordering ----------
        # ✅ Departments first, then Aluminum, then Steel, then rest
        groups = list(group_cols.keys())
        def group_sort_key(g: str):
            gl = g.lower()
            if g == "Departments":
                return (0, "")
            if gl == "aluminum":
                return (1, "")
            if gl == "steel":
                return (2, "")
            return (3, gl)

        groups.sort(key=group_sort_key)

        # keep leaf order inside each group (alphabetic)
        for g in groups:
            group_cols[g] = sorted(group_cols[g], key=lambda x: x.lower())

        # row order
        rows = sorted(row_names, key=lambda x: x.lower())

        # ---------- build columns ----------
        col_labels: list[tuple[str, str]] = []
        for g in groups:
            for lf in group_cols[g]:
                col_labels.append((g, lf))

        header_rows = 2
        total_cols = 1 + len(col_labels) + 1  # Stage/Project + all cols + Total
        total_rows = header_rows + len(rows) + 1

        header_bg = QColor(241, 245, 249)

        table.blockSignals(True)
        try:
            table.clear()
            table.setRowCount(total_rows)
            table.setColumnCount(total_cols)

            last_col = total_cols - 1

            # left header
            set_span_safe(0, 0, 2, 1)
            table.setItem(0, 0, mk_item("Stage / Project", bold=True, center=True, bg=header_bg))

            # total header
            set_span_safe(0, last_col, 2, 1)
            table.setItem(0, last_col, mk_item("Total", bold=True, center=True, bg=header_bg))

            # group headers + leaf headers
            c0 = 1
            for g in groups:
                leaves = group_cols[g]
                span = len(leaves)
                if span <= 0:
                    continue

                table.setItem(0, c0, mk_item(g, bold=True, center=True, bg=header_bg))
                set_span_safe(0, c0, 1, span)

                for j, leaf in enumerate(leaves):
                    table.setItem(1, c0 + j, mk_item(leaf, bold=True, center=True, bg=header_bg))

                c0 += span

            # body
            for i, rn in enumerate(rows):
                rr = header_rows + i
                table.setItem(rr, 0, mk_item(rn, bold=False, center=False))

                row_total = 0.0
                for ci, (g, leaf) in enumerate(col_labels, start=1):
                    v = float(val.get((rn, g, leaf), 0.0) or 0.0)
                    row_total += v
                    txt = "-" if abs(v) < 1e-9 else f"${v:,.2f}"
                    table.setItem(rr, ci, mk_item(txt, bold=False, center=True))

                table.setItem(rr, last_col, mk_item(f"${row_total:,.2f}", bold=True, center=True))

            # TOTAL row
            tr = header_rows + len(rows)
            table.setItem(tr, 0, mk_item("TOTAL", bold=True, center=True, bg=header_bg))

            grand = 0.0
            for ci, (g, leaf) in enumerate(col_labels, start=1):
                s = 0.0
                for rn in rows:
                    s += float(val.get((rn, g, leaf), 0.0) or 0.0)
                grand += s
                table.setItem(tr, ci, mk_item(f"${s:,.2f}", bold=True, center=True, bg=header_bg))

            table.setItem(tr, last_col, mk_item(f"${grand:,.2f}", bold=True, center=True, bg=header_bg))

            # sizing
            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for cc in range(1, table.columnCount()):
                hdr.setSectionResizeMode(cc, QHeaderView.ResizeMode.ResizeToContents)

            table.setRowHeight(0, 30)
            table.setRowHeight(1, 44)
            for r in range(2, table.rowCount()):
                table.setRowHeight(r, 36)

            self._rep_fit_table_height(table)

        finally:
            table.blockSignals(False)


    def _build_overheads_pivot_with_totals(
        self,
        table: QTableWidget,
        comp_rows: list,
        company: str,
        idx_by_company: dict,
        salary_by_emp: dict,
        emp_total_hours_month: dict,
    ):
        idx = idx_by_company.get(company, {}) or {}
        meta_by_id = idx.get("meta_by_id", {}) or {}

        # ✅ Columns from THIS company's TREE: leaf overhead nodes
        cols = []
        for m in meta_by_id.values():
            if (m.get("kind") or "").strip() != "overhead":
                continue
            if not bool(m.get("is_leaf")):
                continue
            nm = (m.get("name") or "").strip()
            if nm:
                cols.append(nm)

        cols = sorted(set(cols))

        data = [r for r in comp_rows if (r.get("kind") or "").strip() == "overhead"]
        employees = sorted({(r.get("employee") or "").strip() for r in data if (r.get("employee") or "").strip()})

        hours_map = {e: {c: 0.0 for c in cols} for e in employees}
        for r in data:
            e = (r.get("employee") or "").strip()
            c = (r.get("category") or "").strip()
            if not e or c not in hours_map.get(e, {}):
                continue
            hours_map[e][c] += float(r.get("hours", 0.0) or 0.0)

        emp_total_in_table = {e: sum(hours_map[e].values()) for e in employees}

        emp_cost_in_table = {}
        for e in employees:
            sal = float(salary_by_emp.get(e, 0.0) or 0.0)
            month_total = float(emp_total_hours_month.get(e, 0.0) or 0.0)
            htab = float(emp_total_in_table.get(e, 0.0) or 0.0)
            emp_cost_in_table[e] = (sal * (htab / month_total)) if (sal > 0 and month_total > 0 and htab > 0) else 0.0

        col_tot_hours = {c: 0.0 for c in cols}
        col_tot_cost = {c: 0.0 for c in cols}
        for e in employees:
            sal = float(salary_by_emp.get(e, 0.0) or 0.0)
            month_total = float(emp_total_hours_month.get(e, 0.0) or 0.0)
            for c in cols:
                h = float(hours_map[e].get(c, 0.0) or 0.0)
                col_tot_hours[c] += h
                if sal > 0 and month_total > 0 and h > 0:
                    col_tot_cost[c] += sal * (h / month_total)

        grand_hours = sum(col_tot_hours.values())
        grand_total_cost = sum(emp_cost_in_table.values())

        table.blockSignals(True)
        try:
            table.clear()

            headers = ["Name"] + cols + ["Total Hours", "Total $"]
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)

            table.setRowCount(len(employees) + 1)

            for ri, emp in enumerate(employees):
                table.setItem(ri, 0, QTableWidgetItem(emp))
                total = float(emp_total_in_table.get(emp, 0.0) or 0.0)

                for ci, cat in enumerate(cols, start=1):
                    h = float(hours_map.get(emp, {}).get(cat, 0.0) or 0.0)
                    if h <= 0:
                        txt = "-\n0.00%"
                    else:
                        pct = (h / total * 100.0) if total > 0 else 0.0
                        txt = f"{h:.2f}\n{pct:.2f}%"
                    it = QTableWidgetItem(txt)
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(ri, ci, it)

                it_h = QTableWidgetItem(f"{total:.2f}")
                it_h.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(ri, 1 + len(cols), it_h)

                it_cost = QTableWidgetItem(f"{emp_cost_in_table.get(emp, 0.0):.2f}")
                it_cost.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(ri, 2 + len(cols), it_cost)

            tr = len(employees)
            it_total = QTableWidgetItem("TOTAL")
            it_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(tr, 0, it_total)

            for ci, cat in enumerate(cols, start=1):
                h = float(col_tot_hours.get(cat, 0.0) or 0.0)
                cost = float(col_tot_cost.get(cat, 0.0) or 0.0)
                it = QTableWidgetItem(f"{h:.2f}\n{cost:.2f}$")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(tr, ci, it)

            it_gt_h = QTableWidgetItem(f"{grand_hours:.2f}")
            it_gt_h.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(tr, 1 + len(cols), it_gt_h)

            it_gt_cost = QTableWidgetItem(f"{grand_total_cost:.2f}")
            it_gt_cost.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(tr, 2 + len(cols), it_gt_cost)

            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for c in range(1, table.columnCount()):
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

            for r in range(table.rowCount()):
                table.setRowHeight(r, 44)

            self._rep_fit_table_height(table)

        finally:
            table.blockSignals(False)

    # ---------------------------
    # Stage pivot (multi-row headers like Excel) + totals $
    # ---------------------------
    def _build_stage_projects_pivot_with_totals(
        self,
        table: QTableWidget,
        stage_rows: list,          # from api.report_stage_projects
        company: str,
        salary_by_emp: dict,
        emp_total_hours_month: dict,
    ):
        """
        Table 2 (Stages/Operations):
        Grouping: Aluminum / Steel  ->  Leaf (Fabrication/Installation)  ->  Projects
        Rows = Employees
        Cells = hours + % (within the table-total for that employee)
        Totals row = hours + allocated $
        """

        def s(x): return (x or "").strip()

        # ---- get category index to derive Aluminum/Steel from category_id path ----
        idx = (getattr(self, "_rep_cat_index_by_companyname", {}) or {}).get(company, {}) or {}
        meta_by_id = idx.get("meta_by_id", {}) or {}

        # employees
        employees = sorted({s(r.get("employee")) for r in stage_rows if s(r.get("employee"))})

        # groups: super (Aluminum/Steel) -> leaf (Fabrication/Installation) -> [projects]
        super_groups: dict[str, dict[str, list[str]]] = {}   # super -> leaf -> [projects]
        val = {}  # (emp, super, leaf, project) -> hours

        for r in stage_rows:
            emp = s(r.get("employee"))
            proj = s(r.get("project_name")) or f"Project {r.get('project_id')}"
            h = float(r.get("hours", 0.0) or 0.0)

            if not emp or not proj:
                continue

            # derive super+leaf from category tree path using stage_category_id
            cid = r.get("stage_category_id")
            super_name = "Stages"
            leaf_name = s(r.get("stage_name")) or "Leaf"

            try:
                if cid is not None:
                    cid = int(cid)
                    m = meta_by_id.get(cid)
                    if m:
                        p = m.get("path") or []
                        # path example: ["Steel","Fabrication"] or ["Aluminum","Fabrication"]
                        if len(p) >= 2:
                            super_name = s(p[-2]) or super_name
                            leaf_name = s(p[-1]) or leaf_name
                        elif len(p) == 1:
                            leaf_name = s(p[-1]) or leaf_name
            except Exception:
                pass

            super_groups.setdefault(super_name, {})
            super_groups[super_name].setdefault(leaf_name, [])
            if proj not in super_groups[super_name][leaf_name]:
                super_groups[super_name][leaf_name].append(proj)

            key = (emp, super_name, leaf_name, proj)
            val[key] = val.get(key, 0.0) + h

        # ---- ordering: Aluminum then Steel then others ----
        def super_sort_key(x: str):
            xl = x.lower()
            if xl == "aluminum":
                return (0, "")
            if xl == "steel":
                return (1, "")
            return (2, xl)

        super_names = sorted(super_groups.keys(), key=super_sort_key)
        for sup in super_names:
            leafs = super_groups[sup]
            # leaf order alphabetic
            for lf in list(leafs.keys()):
                leafs[lf] = sorted(leafs[lf], key=lambda z: z.lower())
            super_groups[sup] = dict(sorted(leafs.items(), key=lambda kv: kv[0].lower()))

        # ---- flatten columns: list of (super, leaf, project) ----
        col_defs = []
        for sup in super_names:
            for lf, projects in super_groups[sup].items():
                for proj in projects:
                    col_defs.append((sup, lf, proj))

        # ---- 3 header rows now ----
        header_rows = 3
        name_col = 0
        first_col = 1
        total_hours_col = first_col + len(col_defs)
        total_cost_col = total_hours_col + 1

        total_rows = header_rows + len(employees) + 1
        total_cols = 1 + len(col_defs) + 2

        table.blockSignals(True)
        try:
            table.clear()
            table.setRowCount(total_rows)
            table.setColumnCount(total_cols)

            # Name / Totals span 3 rows
            self._safe_span(table, 0, name_col, 3, 1)
            it = QTableWidgetItem("Name")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, name_col, it)

            self._safe_span(table, 0, total_hours_col, 3, 1)
            it = QTableWidgetItem("Total Hours")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, total_hours_col, it)

            self._safe_span(table, 0, total_cost_col, 3, 1)
            it = QTableWidgetItem("Total $")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, total_cost_col, it)

            # Row0: Aluminum/Steel groups
            # Row1: leaf groups
            # Row2: project headers
            c = first_col

            # helper to count span for a super group and for a leaf group
            def span_super(sup: str) -> int:
                return sum(len(super_groups[sup][lf]) for lf in super_groups[sup].keys())

            def span_leaf(sup: str, lf: str) -> int:
                return len(super_groups[sup][lf])

            for sup in super_names:
                sup_span = span_super(sup)
                it_sup = QTableWidgetItem(sup)
                it_sup.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(0, c, it_sup)
                self._safe_span(table, 0, c, 1, sup_span)

                c_leaf = c
                for lf in super_groups[sup].keys():
                    lf_span = span_leaf(sup, lf)
                    it_lf = QTableWidgetItem(lf)
                    it_lf.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(1, c_leaf, it_lf)
                    self._safe_span(table, 1, c_leaf, 1, lf_span)

                    # projects row2
                    for j, proj in enumerate(super_groups[sup][lf]):
                        it_p = QTableWidgetItem(proj)
                        it_p.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        table.setItem(2, c_leaf + j, it_p)

                    c_leaf += lf_span

                c += sup_span

            # totals per employee in THIS table
            emp_hours_in_table = {}
            for emp in employees:
                tot = 0.0
                for sup, lf, proj in col_defs:
                    tot += float(val.get((emp, sup, lf, proj), 0.0) or 0.0)
                emp_hours_in_table[emp] = tot

            # cost per employee (allocated by month total hours)
            emp_cost_in_table = {}
            for emp in employees:
                sal = float(salary_by_emp.get(emp, 0.0) or 0.0)
                month_total = float(emp_total_hours_month.get(emp, 0.0) or 0.0)
                htab = float(emp_hours_in_table.get(emp, 0.0) or 0.0)
                emp_cost_in_table[emp] = (sal * (htab / month_total)) if (sal > 0 and month_total > 0 and htab > 0) else 0.0

            # column totals
            col_tot_hours = [0.0] * len(col_defs)
            col_tot_cost = [0.0] * len(col_defs)

            for emp in employees:
                sal = float(salary_by_emp.get(emp, 0.0) or 0.0)
                month_total = float(emp_total_hours_month.get(emp, 0.0) or 0.0)
                for k, (sup, lf, proj) in enumerate(col_defs):
                    hh = float(val.get((emp, sup, lf, proj), 0.0) or 0.0)
                    col_tot_hours[k] += hh
                    if sal > 0 and month_total > 0 and hh > 0:
                        col_tot_cost[k] += sal * (hh / month_total)

            # body rows start after header_rows
            for ri, emp in enumerate(employees):
                rrow = header_rows + ri
                table.setItem(rrow, name_col, QTableWidgetItem(emp))

                total_emp = float(emp_hours_in_table.get(emp, 0.0) or 0.0)

                for k, (sup, lf, proj) in enumerate(col_defs):
                    hh = float(val.get((emp, sup, lf, proj), 0.0) or 0.0)
                    if hh <= 0:
                        txt = "-\n0.00%"
                    else:
                        pct = (hh / total_emp * 100.0) if total_emp > 0 else 0.0
                        txt = f"{hh:.2f}\n{pct:.2f}%"
                    it = QTableWidgetItem(txt)
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(rrow, first_col + k, it)

                it_h = QTableWidgetItem(f"{total_emp:.2f}")
                it_h.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(rrow, total_hours_col, it_h)

                it_c = QTableWidgetItem(f"{emp_cost_in_table.get(emp, 0.0):.2f}")
                it_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(rrow, total_cost_col, it_c)

            # TOTAL row
            trow = header_rows + len(employees)
            it = QTableWidgetItem("TOTAL")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(trow, name_col, it)

            grand_hours = 0.0
            for k in range(len(col_defs)):
                hh = float(col_tot_hours[k] or 0.0)
                cc = float(col_tot_cost[k] or 0.0)
                grand_hours += hh
                it = QTableWidgetItem(f"{hh:.2f}\n{cc:.2f}$")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(trow, first_col + k, it)

            it = QTableWidgetItem(f"{grand_hours:.2f}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(trow, total_hours_col, it)

            grand_cost = sum(emp_cost_in_table.values())
            it = QTableWidgetItem(f"{grand_cost:.2f}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(trow, total_cost_col, it)

            # sizing
            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for cc in range(1, table.columnCount()):
                hdr.setSectionResizeMode(cc, QHeaderView.ResizeMode.ResizeToContents)

            table.setRowHeight(0, 26)
            table.setRowHeight(1, 26)
            table.setRowHeight(2, 40)
            for r in range(3, table.rowCount()):
                table.setRowHeight(r, 44)

            self._rep_fit_table_height(table)

        finally:
            table.blockSignals(False)



    def _build_stage_hierarchy_pivot_with_totals(
        self,
        table: QTableWidget,
        comp_rows: list,
        company: str,
        idx_by_company: dict,
        salary_by_emp: dict,
        emp_total_hours_month: dict,
    ):
        """
        NEW (Excel-like 2-row header):
        Groups مثل Aluminum / Steel
        Leafs مثل Fabrication / Installation
        + Total Hours + Total $
        """
        idx = idx_by_company.get(company, {}) or {}
        meta_by_id = idx.get("meta_by_id", {}) or {}

        # stage rows only
        data = [r for r in comp_rows if (r.get("kind") or "").strip() == "stage"]
        employees = sorted({(r.get("employee") or "").strip() for r in data if (r.get("employee") or "").strip()})

        # collect leaf stage metas (from tree)
        leaf_metas = []
        for m in meta_by_id.values():
            if (m.get("kind") or "").strip() != "stage":
                continue
            if not bool(m.get("is_leaf")):
                continue
            p = m.get("path") or []
            if p:
                leaf_metas.append(m)

        table.blockSignals(True)
        try:
            table.clear()

            if not leaf_metas:
                table.setRowCount(0)
                table.setColumnCount(1)
                table.setHorizontalHeaderLabels(["Name"])
                self._rep_fit_table_height(table)
                return

            # ---- group leaves by "super" (parent in path) ----
            # super = path[-2] (مثل Aluminum / Steel)
            # leaf  = path[-1] (مثل Fabrication / Installation)
            groups: dict[str, list[dict]] = {}
            for m in leaf_metas:
                p = m.get("path") or []
                leaf = (p[-1] if len(p) >= 1 else (m.get("name") or "")).strip()
                super_name = (p[-2] if len(p) >= 2 else "Stages").strip()
                if not super_name:
                    super_name = "Stages"
                if not leaf:
                    continue
                groups.setdefault(super_name, []).append(m)

            # ordering: alphabetic (you can customize)
            group_names = sorted(groups.keys(), key=lambda x: x.lower())
            for g in group_names:
                # order leaves inside group by leaf name
                groups[g] = sorted(groups[g], key=lambda mm: ((mm.get("name") or "").lower()))

            # build flat columns list (group, leaf_name, category_id)
            col_defs: list[tuple[str, str, int]] = []
            for g in group_names:
                for m in groups[g]:
                    p = m.get("path") or []
                    leaf = (p[-1] if len(p) >= 1 else (m.get("name") or "")).strip()
                    col_defs.append((g, leaf, int(m["id"])))

            header_rows = 2
            total_cols = 1 + len(col_defs) + 2  # Name + leaf cols + Total Hours + Total $
            total_rows = header_rows + len(employees) + 1  # headers + employees + TOTAL

            name_col = 0
            first_leaf_col = 1
            total_hours_col = 1 + len(col_defs)
            total_cost_col = 2 + len(col_defs)

            table.setRowCount(total_rows)
            table.setColumnCount(total_cols)

            # ----- Headers with spans (avoid Qt single-span warnings) -----
            # Name span 2 rows
            self._safe_span(table, 0, name_col, 2, 1)
            it_name = QTableWidgetItem("Name")
            it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, name_col, it_name)

            # Total Hours / Total $ span 2 rows
            self._safe_span(table, 0, total_hours_col, 2, 1)
            self._safe_span(table, 0, total_cost_col, 2, 1)

            it_th = QTableWidgetItem("Total Hours")
            it_th.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, total_hours_col, it_th)

            it_tc = QTableWidgetItem("Total $")
            it_tc.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, total_cost_col, it_tc)

            # Group headers (row 0) + leaf headers (row 1)
            c = first_leaf_col
            i = 0
            while i < len(col_defs):
                g = col_defs[i][0]
                start = i
                while i < len(col_defs) and col_defs[i][0] == g:
                    i += 1
                span = i - start

                # group cell (row 0, col c, span columns)
                it_g = QTableWidgetItem(g)
                it_g.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(0, c, it_g)
                self._safe_span(table, 0, c, 1, span)

                # leaf headers in row 1
                for j in range(span):
                    leaf_name = col_defs[start + j][1]
                    it_leaf = QTableWidgetItem(leaf_name)
                    it_leaf.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(1, c + j, it_leaf)

                c += span

            # ----- Fill data -----
            # map category_id -> column index
            catid_to_col = {}
            for idx_col, (_, _, cat_id) in enumerate(col_defs):
                catid_to_col[cat_id] = idx_col  # 0..N-1

            # hours_map[emp][col]
            hours_map = {e: [0.0] * len(col_defs) for e in employees}

            for r in data:
                emp = (r.get("employee") or "").strip()
                if not emp:
                    continue
                h = float(r.get("hours", 0.0) or 0.0)

                cid = r.get("category_id")
                if cid is None:
                    continue
                try:
                    cid = int(cid)
                except Exception:
                    continue

                col0 = catid_to_col.get(cid)
                if col0 is None:
                    continue
                hours_map[emp][col0] += h

            emp_total_in_table = {e: sum(hours_map.get(e, [])) for e in employees}

            # salary cost per employee for THIS table
            emp_cost_in_table = {}
            for e in employees:
                sal = float(salary_by_emp.get(e, 0.0) or 0.0)
                month_total = float(emp_total_hours_month.get(e, 0.0) or 0.0)
                htab = float(emp_total_in_table.get(e, 0.0) or 0.0)
                emp_cost_in_table[e] = (sal * (htab / month_total)) if (sal > 0 and month_total > 0 and htab > 0) else 0.0

            # column totals (hours + cost)
            col_tot_hours = [0.0] * len(col_defs)
            col_tot_cost = [0.0] * len(col_defs)

            for e in employees:
                sal = float(salary_by_emp.get(e, 0.0) or 0.0)
                month_total = float(emp_total_hours_month.get(e, 0.0) or 0.0)
                vals = hours_map.get(e, [0.0] * len(col_defs))
                for k, hh in enumerate(vals):
                    hh = float(hh or 0.0)
                    col_tot_hours[k] += hh
                    if sal > 0 and month_total > 0 and hh > 0:
                        col_tot_cost[k] += sal * (hh / month_total)

            grand_hours = sum(col_tot_hours)
            grand_cost = sum(emp_cost_in_table.values())

            # employee rows start
            for ri, emp in enumerate(employees):
                row_index = header_rows + ri
                table.setItem(row_index, name_col, QTableWidgetItem(emp))

                total_emp = float(emp_total_in_table.get(emp, 0.0) or 0.0)
                vals = hours_map.get(emp, [0.0] * len(col_defs))

                for k, hh in enumerate(vals):
                    hh = float(hh or 0.0)
                    if hh <= 0:
                        txt = "-\n0.00%"
                    else:
                        pct = (hh / total_emp * 100.0) if total_emp > 0 else 0.0
                        txt = f"{hh:.2f}\n{pct:.2f}%"
                    it = QTableWidgetItem(txt)
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row_index, first_leaf_col + k, it)

                it_h = QTableWidgetItem(f"{total_emp:.2f}")
                it_h.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row_index, total_hours_col, it_h)

                it_c = QTableWidgetItem(f"{emp_cost_in_table.get(emp, 0.0):.2f}")
                it_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row_index, total_cost_col, it_c)

            # TOTAL row
            total_row = header_rows + len(employees)
            it_t = QTableWidgetItem("TOTAL")
            it_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(total_row, name_col, it_t)

            for k, hh in enumerate(col_tot_hours):
                cost = float(col_tot_cost[k] or 0.0)
                itv = QTableWidgetItem(f"{float(hh or 0.0):.2f}\n{cost:.2f}$")
                itv.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(total_row, first_leaf_col + k, itv)

            it_gt_h = QTableWidgetItem(f"{grand_hours:.2f}")
            it_gt_h.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(total_row, total_hours_col, it_gt_h)

            it_gt_c = QTableWidgetItem(f"{grand_cost:.2f}")
            it_gt_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(total_row, total_cost_col, it_gt_c)

            # sizing
            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for cc in range(1, table.columnCount()):
                hdr.setSectionResizeMode(cc, QHeaderView.ResizeMode.ResizeToContents)

            table.setRowHeight(0, 28)
            table.setRowHeight(1, 40)
            for r in range(2, table.rowCount()):
                table.setRowHeight(r, 44)

            self._rep_fit_table_height(table)

        finally:
            table.blockSignals(False)

    # ---------------------------
    # Render (NO rebuilding layout here)
    # ---------------------------

    def _render_report_pivots(self):
        rows = list(getattr(self, "_report_rows", []) or [])

        # employee filter (by selected employee name)
        sel_emp_name = (self.repEmployee.currentText() or "").strip()
        if sel_emp_name and sel_emp_name != "All Employees":
            rows = [r for r in rows if (r.get("employee") or "") == sel_emp_name]

        idx_by_company = getattr(self, "_rep_cat_index_by_companyname", {}) or {}

        show_over = bool(self.repChkOverheads.isChecked())
        show_stage = bool(self.repChkStages.isChecked())
        show_matrix = bool(getattr(self, "repChkMatrix", None) and self.repChkMatrix.isChecked())

        # salary map (optional)
        salary_by_emp = self._get_salary_by_employee()

        # total hours per employee in the month (for salary allocation)
        emp_total_hours_month = {}
        for r in rows:
            e = (r.get("employee") or "").strip()
            if not e:
                continue
            emp_total_hours_month[e] = emp_total_hours_month.get(e, 0.0) + float(r.get("hours", 0.0) or 0.0)

        grand_hours = 0.0
        grand_alloc = 0.0
        grand_cost = 0.0

        for comp, sec in (getattr(self, "_rep_sections", {}) or {}).items():
            over_table: QTableWidget = sec["over_table"]
            stage_table: QTableWidget = sec["stage_table"]
            matrix_title: QLabel = sec.get("matrix_title")
            matrix_table: QTableWidget = sec.get("matrix_table")
            sec_sum: QLabel = sec["sec_sum"]

            # show/hide tables
            over_table.setVisible(show_over)
            stage_table.setVisible(show_stage)
            if matrix_title:
                matrix_title.setVisible(show_matrix)
            if matrix_table:
                matrix_table.setVisible(show_matrix)

            comp_rows = [r for r in rows if (r.get("company") or "").strip() == comp]

            # render overheads table
            if show_over:
                self._build_overheads_pivot_with_totals(
                    over_table, comp_rows, comp, idx_by_company, salary_by_emp, emp_total_hours_month
                )
            else:
                over_table.clear()
                over_table.setRowCount(0)
                over_table.setColumnCount(1)
                over_table.setHorizontalHeaderLabels(["Name"])
                self._rep_fit_table_height(over_table)

            # render stages table
            if show_stage:
                try:
                    year = int(self.repYear.value())
                    month = int(self.repMonth.value())
                    emp_id = self.repEmployee.currentData()  # None allowed

                    stage_rows = api.report_stage_projects(year, month, comp, emp_id) or []
                except Exception:
                    stage_rows = []

                if not stage_rows:
                    stage_table.clear()
                    stage_table.setRowCount(0)
                    stage_table.setColumnCount(1)
                    stage_table.setHorizontalHeaderLabels(["Name"])
                    self._rep_fit_table_height(stage_table)
                else:
                    self._build_stage_projects_pivot_with_totals(
                        stage_table,
                        stage_rows,
                        comp,                 # ✅ company name
                        salary_by_emp,
                        emp_total_hours_month,
                    )
            else:
                stage_table.clear()
                stage_table.setRowCount(0)
                stage_table.setColumnCount(1)
                stage_table.setHorizontalHeaderLabels(["Name"])
                self._rep_fit_table_height(stage_table)


            # ✅ Matrix (Excel Like Screenshot)
            if show_matrix and matrix_table is not None:
                try:
                    year = int(self.repYear.value())
                    month = int(self.repMonth.value())
                    emp_id = self.repEmployee.currentData()  # None allowed

                    # ✅ NEW endpoint
                    matrix_rows = api.report_matrix_leaf_project(year, month, comp, emp_id) or []

                except Exception:
                    matrix_rows = []

                if not matrix_rows:
                    matrix_table.clear()
                    matrix_table.setRowCount(0)
                    matrix_table.setColumnCount(1)
                    matrix_table.setHorizontalHeaderLabels(["Stage / Project"])
                    self._rep_fit_table_height(matrix_table)
                else:
                    # ✅ NEW renderer (multi-level header with spans)
                    self._build_excel_matrix_like_screenshot(matrix_table, matrix_rows, comp)



            elif matrix_table is not None:
                matrix_table.clear()
                matrix_table.setRowCount(0)
                matrix_table.setColumnCount(1)
                matrix_table.setHorizontalHeaderLabels(["Stage / Project"])
                self._rep_fit_table_height(matrix_table)

            # company totals (from comp_rows)
            comp_hours = sum(float(r.get("hours", 0.0) or 0.0) for r in comp_rows)
            comp_alloc = sum(float(r.get("allocated", 0.0) or 0.0) for r in comp_rows)

            # cost for the company (salary allocation by employee-hours)
            comp_emp_hours = {}
            for r in comp_rows:
                e = (r.get("employee") or "").strip()
                if not e:
                    continue
                comp_emp_hours[e] = comp_emp_hours.get(e, 0.0) + float(r.get("hours", 0.0) or 0.0)

            comp_cost = 0.0
            for e, h in comp_emp_hours.items():
                sal = float(salary_by_emp.get(e, 0.0) or 0.0)
                month_total = float(emp_total_hours_month.get(e, 0.0) or 0.0)
                comp_cost += (sal * (h / month_total)) if (sal > 0 and month_total > 0 and h > 0) else 0.0

            sec_sum.setText(f"Company Total: Hours={comp_hours:.2f} | Allocated={comp_alloc:.2f} | $={comp_cost:.2f}")

            grand_hours += comp_hours
            grand_alloc += comp_alloc
            grand_cost += comp_cost

        self.repSummary.setText(f"Total: Hours={grand_hours:.2f} | Allocated={grand_alloc:.2f} | $={grand_cost:.2f}")

    # ---------------------------
    # Export raw CSV (same as before, but adds company if present)
    # ---------------------------

    def _export_report_csv(self):
        try:
            rows = list(getattr(self, "_report_rows", []) or [])
            if not rows:
                _msg_err(self, "No data to export.")
                return

            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save report as CSV",
                str(Path.home() / "report.csv"),
                "CSV Files (*.csv)"
            )
            if not path:
                return

            headers = ["company", "employee", "category", "kind", "hours", "total_hours", "percent", "allocated"]
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for r in rows:
                    w.writerow([
                        (r.get("company") or ""),
                        (r.get("employee") or ""),
                        (r.get("category") or ""),
                        (r.get("kind") or ""),
                        float(r.get("hours", 0.0) or 0.0),
                        float(r.get("total_hours", 0.0) or 0.0),
                        float(r.get("percent", 0.0) or 0.0),
                        float(r.get("allocated", 0.0) or 0.0),
                    ])

            _msg_ok(self, f"Exported:\n{path}")

        except Exception as e:
            _msg_err(self, str(e))


    # =========================================================
    # Refresh all
    # =========================================================
    def refresh_all(self):
        try:
            if not session.TOKEN:
                return
            # ----------- fetch core data -----------
            self.employees = api.employees_list() or []
            self.companies = api.companies_list() or []
            self._fill_company_combos()

            # ----------- render employees -----------
            self._render_employees_table()

            # ----------- categories tree reload -----------
            self._load_category_tree()

            # ----------- projects reload -----------
            self._load_projects()

            # ----------- timesheet employee combo -----------
            if hasattr(self, "tsEmp"):
                self.tsEmp.blockSignals(True)
                try:
                    self.tsEmp.clear()
                    for e in self.employees:
                        name = (e.get("name") or "").strip()
                        if name:
                            self.tsEmp.addItem(name, e.get("id"))
                finally:
                    self.tsEmp.blockSignals(False)

                self._filter_timesheet_emps()

                # ✅ as you want: any refresh -> company becomes All
                self._ts_reset_company_to_all()

            # ----------- payments employee combo -----------
            if session.ROLE in ("HR", "Admin") and hasattr(self, "payEmp"):
                self.payEmp.blockSignals(True)
                try:
                    self.payEmp.clear()
                    for e in self.employees:
                        self.payEmp.addItem(e.get("name", ""), e.get("id"))
                finally:
                    self.payEmp.blockSignals(False)

            # ----------- reports employee combo -----------
            if session.ROLE in ("HR", "Admin") and hasattr(self, "repEmployee"):
                self.repEmployee.blockSignals(True)
                try:
                    self.repEmployee.clear()
                    self.repEmployee.addItem("All Employees", None)
                    for e in self.employees:
                        self.repEmployee.addItem(e.get("name", ""), e.get("id"))
                    self.repEmployee.setCurrentIndex(0)
                finally:
                    self.repEmployee.blockSignals(False)

                QTimer.singleShot(100, self._load_report)

        except Exception as e:
            _msg_err(self, str(e))

