APP_QSS = """
* { font-family: Segoe UI; font-size: 12px; }

QMainWindow { background: #f8fafc; }

/* ✅ لا تخليها transparent */
QWidget { color: #0f172a; background: #f8fafc; }

/* Containers */
QGroupBox {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin-top: 10px;
    padding: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    font-weight: 700;
    color: #0f172a;
}

/* Inputs */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 6px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #2563eb;
}

/* Buttons */
QPushButton {
    background: #2563eb;
    color: white;
    border: none;
    padding: 8px 12px;
    border-radius: 8px;
    font-weight: 600;
}
QPushButton:hover { background: #1d4ed8; }
QPushButton:disabled { background: #94a3b8; }

/* Tabs */
QTabWidget::pane { border: 0; background: #f8fafc; }
QTabBar { background: #f8fafc; }
QTabBar::tab {
    background: #e5e7eb;
    padding: 8px 12px;
    border-radius: 8px;
    margin-right: 6px;
}
QTabBar::tab:selected {
    background: #ffffff;
    border: 1px solid #e5e7eb;
}

/* Tables */
QTableWidget {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    gridline-color: #e5e7eb;
}
QHeaderView::section {
    background: #f1f5f9;
    border: 0;
    border-bottom: 1px solid #e5e7eb;
    padding: 8px;
    font-weight: 700;
}
QTableWidget::item:selected { background: #dbeafe; }

/* Tree */
QTreeWidget {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
}

/* ✅ ScrollArea viewport */
QScrollArea { border: 0; background: #f8fafc; }
QScrollArea > QWidget > QWidget { background: #f8fafc; }
QScrollArea QWidget#qt_scrollarea_viewport { background: #f8fafc; }
"""
