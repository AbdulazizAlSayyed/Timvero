import sys
from pathlib import Path

# ✅ make project root importable (so "client" package works)
ROOT = Path(__file__).resolve().parent.parent  # project root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

from client.ui.style import APP_QSS
from client.ui.login_dialog import LoginDialog
from client.ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    login = LoginDialog()
    if login.exec():
        win = MainWindow()
        win.show()
        sys.exit(app.exec())
