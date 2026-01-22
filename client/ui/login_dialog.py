from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from pathlib import Path
from client.services import api

ASSETS = Path(__file__).resolve().parents[1] / "assets"
APP_ICON = str(ASSETS / "icon.png")
APP_LOGO = str(ASSETS / "logo.png")


class ChangePasswordDialog(QDialog):
    def __init__(self, preset_username: str = ""):
        super().__init__()
        self.setWindowTitle("Timvero - Change Password")
        self.setWindowIcon(QIcon(APP_ICON))
        self.setFixedSize(360, 300)

        lay = QVBoxLayout(self)

        # small logo (optional)
        logo = QLabel()
        pm = QPixmap(APP_LOGO)
        if not pm.isNull():
            logo.setPixmap(pm.scaledToWidth(180, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(logo)

        title = QLabel("Change Password")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(title)

        lay.addWidget(QLabel("Username"))
        self.user = QLineEdit()
        self.user.setPlaceholderText("Enter username")
        self.user.setText(preset_username or "")
        lay.addWidget(self.user)

        lay.addWidget(QLabel("Current Password"))
        self.old_pw = QLineEdit()
        self.old_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_pw.setPlaceholderText("••••••")
        lay.addWidget(self.old_pw)

        lay.addWidget(QLabel("New Password"))
        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pw.setPlaceholderText("••••••")
        lay.addWidget(self.new_pw)

        lay.addWidget(QLabel("Confirm New Password"))
        self.confirm_pw = QLineEdit()
        self.confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pw.setPlaceholderText("••••••")
        lay.addWidget(self.confirm_pw)

        self.btn = QPushButton("Update Password")
        self.btn.clicked.connect(self.do_change)
        lay.addWidget(self.btn)

        self.setModal(True)

    def do_change(self):
        u = self.user.text().strip()
        oldp = self.old_pw.text().strip()
        newp = self.new_pw.text().strip()
        conf = self.confirm_pw.text().strip()

        if not u or not oldp or not newp or not conf:
            QMessageBox.warning(self, "Missing", "Please fill all fields.")
            return
        if newp != conf:
            QMessageBox.warning(self, "Mismatch", "Passwords do not match.")
            return
        if len(newp) < 6:
            QMessageBox.warning(self, "Weak", "Password must be at least 6 characters.")
            return

        try:
            res = api.change_password(u, oldp, newp)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        if not res.get("ok"):
            QMessageBox.critical(self, "Error", res.get("message", "Failed to change password"))
            return

        QMessageBox.information(self, "Success", res.get("message", "Password updated"))
        self.accept()


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timvero - Login")
        self.setWindowIcon(QIcon(APP_ICON))
        self.setFixedSize(360, 320)

        lay = QVBoxLayout(self)

        # BIG logo
        logo = QLabel()
        pm = QPixmap(APP_LOGO)
        if not pm.isNull():
            logo.setPixmap(pm.scaledToWidth(220, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        subtitle = QLabel("Sign in to continue")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #64748b;")
        lay.addWidget(subtitle)

        lay.addWidget(QLabel("Username"))
        self.user = QLineEdit()
        self.user.setPlaceholderText("Username")
        lay.addWidget(self.user)

        lay.addWidget(QLabel("Password"))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setPlaceholderText("Password")
        lay.addWidget(self.pw)

        self.btn = QPushButton("Login")
        self.btn.clicked.connect(self.do_login)
        lay.addWidget(self.btn)

        self.change_btn = QPushButton("Change Password")
        self.change_btn.clicked.connect(self.open_change_password)
        lay.addWidget(self.change_btn)

        lay.addStretch(1)
        self.setModal(True)

    def open_change_password(self):
        dlg = ChangePasswordDialog(preset_username=self.user.text().strip())
        dlg.exec()

    def do_login(self):
        u = self.user.text().strip()
        p = self.pw.text().strip()
        if not u or not p:
            QMessageBox.warning(self, "Missing", "Enter username and password.")
            return

        try:
            res = api.login(u, p)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        if not res.get("ok"):
            QMessageBox.critical(self, "Error", res.get("message", "Login failed"))
            return

        self.accept()
