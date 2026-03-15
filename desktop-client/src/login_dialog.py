"""Login dialog for the Omni Desktop Client.

Provides email/password sign-in and sign-up via Firebase Auth REST API.
Styled to match the dark theme of the dashboard.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QWidget, QCheckBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon

from src.firebase_auth import FirebaseAuth, AuthResult

logger = logging.getLogger(__name__)

# ── Stylesheet ────────────────────────────────────────────────────────

_STYLESHEET = """
QDialog {
    background-color: #0f172a;
}
QLabel {
    color: #e2e8f0;
    font-size: 13px;
}
QLabel#title {
    font-size: 22px;
    font-weight: bold;
    color: #f8fafc;
}
QLabel#subtitle {
    font-size: 13px;
    color: #94a3b8;
}
QLabel#error {
    color: #f87171;
    font-size: 12px;
}
QLabel#link {
    color: #60a5fa;
    font-size: 12px;
}
QLineEdit {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 10px 12px;
    color: #f1f5f9;
    font-size: 13px;
    selection-background-color: #3b82f6;
}
QLineEdit:focus {
    border-color: #3b82f6;
}
QLineEdit::placeholder {
    color: #64748b;
}
QPushButton#primary {
    background-color: #3b82f6;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    color: #ffffff;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#primary:hover {
    background-color: #2563eb;
}
QPushButton#primary:pressed {
    background-color: #1d4ed8;
}
QPushButton#primary:disabled {
    background-color: #475569;
    color: #94a3b8;
}
QPushButton#secondary {
    background: transparent;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 10px 16px;
    color: #e2e8f0;
    font-size: 13px;
}
QPushButton#secondary:hover {
    background-color: #1e293b;
    border-color: #475569;
}
QCheckBox {
    color: #94a3b8;
    font-size: 12px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #475569;
    border-radius: 3px;
    background-color: #1e293b;
}
QCheckBox::indicator:checked {
    background-color: #3b82f6;
    border-color: #3b82f6;
}
"""


class LoginDialog(QDialog):
    """Modal login/sign-up dialog using Firebase email+password auth."""

    def __init__(
        self,
        firebase_api_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Omni Hub — Sign In")
        self.setFixedSize(420, 520)
        self.setStyleSheet(_STYLESHEET)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )

        self._auth = FirebaseAuth(firebase_api_key)
        self._result: Optional[AuthResult] = None

        self._init_ui()

    # ── public ────────────────────────────────────────────────────

    @property
    def auth_result(self) -> Optional[AuthResult]:
        return self._result

    # ── UI construction ───────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 28)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────
        title = QLabel("Omni Hub")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel("Desktop Client")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)
        root.addSpacing(28)

        # ── Stacked pages (0 = login, 1 = signup) ─────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_login_page())
        self._stack.addWidget(self._build_signup_page())
        root.addWidget(self._stack)

        # ── Footer / toggle ───────────────────────────────────────
        root.addSpacing(16)
        self._toggle_layout = QHBoxLayout()
        self._toggle_label = QLabel("Don't have an account?")
        self._toggle_label.setObjectName("subtitle")
        self._toggle_layout.addWidget(self._toggle_label)

        self._toggle_btn = QPushButton("Sign up")
        self._toggle_btn.setObjectName("secondary")
        self._toggle_btn.setFixedWidth(80)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_page)
        self._toggle_layout.addWidget(self._toggle_btn)
        self._toggle_layout.addStretch()
        root.addLayout(self._toggle_layout)

    # ─── Login page ───────────────────────────────────────────────

    def _build_login_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Email"))
        self._login_email = QLineEdit()
        self._login_email.setPlaceholderText("you@example.com")
        lay.addWidget(self._login_email)

        lay.addWidget(QLabel("Password"))
        self._login_password = QLineEdit()
        self._login_password.setPlaceholderText("••••••••")
        self._login_password.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._login_password)

        self._login_show_pw = QCheckBox("Show password")
        self._login_show_pw.toggled.connect(
            lambda on: self._login_password.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        lay.addWidget(self._login_show_pw)

        self._login_error = QLabel("")
        self._login_error.setObjectName("error")
        self._login_error.setWordWrap(True)
        self._login_error.hide()
        lay.addWidget(self._login_error)

        lay.addSpacing(4)
        self._login_btn = QPushButton("Sign In")
        self._login_btn.setObjectName("primary")
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.clicked.connect(self._do_login)
        lay.addWidget(self._login_btn)

        # Enter key triggers sign in
        self._login_password.returnPressed.connect(self._do_login)
        self._login_email.returnPressed.connect(
            lambda: self._login_password.setFocus()
        )

        return page

    # ─── Sign-up page ─────────────────────────────────────────────

    def _build_signup_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Email"))
        self._signup_email = QLineEdit()
        self._signup_email.setPlaceholderText("you@example.com")
        lay.addWidget(self._signup_email)

        lay.addWidget(QLabel("Password"))
        self._signup_password = QLineEdit()
        self._signup_password.setPlaceholderText("At least 6 characters")
        self._signup_password.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._signup_password)

        lay.addWidget(QLabel("Confirm Password"))
        self._signup_confirm = QLineEdit()
        self._signup_confirm.setPlaceholderText("Repeat password")
        self._signup_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._signup_confirm)

        self._signup_error = QLabel("")
        self._signup_error.setObjectName("error")
        self._signup_error.setWordWrap(True)
        self._signup_error.hide()
        lay.addWidget(self._signup_error)

        lay.addSpacing(4)
        self._signup_btn = QPushButton("Create Account")
        self._signup_btn.setObjectName("primary")
        self._signup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signup_btn.clicked.connect(self._do_signup)
        lay.addWidget(self._signup_btn)

        self._signup_confirm.returnPressed.connect(self._do_signup)

        return page

    # ── page toggle ───────────────────────────────────────────────

    def _toggle_page(self) -> None:
        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)
            self._toggle_label.setText("Already have an account?")
            self._toggle_btn.setText("Sign in")
        else:
            self._stack.setCurrentIndex(0)
            self._toggle_label.setText("Don't have an account?")
            self._toggle_btn.setText("Sign up")

    # ── auth actions ──────────────────────────────────────────────

    def _do_login(self) -> None:
        email = self._login_email.text().strip()
        password = self._login_password.text()
        if not email or not password:
            self._show_login_error("Please enter both email and password.")
            return

        self._login_btn.setEnabled(False)
        self._login_btn.setText("Signing in…")
        self._login_error.hide()
        try:
            result = self._auth.sign_in(email, password)
            self._result = result
            self.accept()  # close dialog with success
        except RuntimeError as exc:
            self._show_login_error(str(exc))
        finally:
            self._login_btn.setEnabled(True)
            self._login_btn.setText("Sign In")

    def _do_signup(self) -> None:
        email = self._signup_email.text().strip()
        password = self._signup_password.text()
        confirm = self._signup_confirm.text()

        if not email or not password:
            self._show_signup_error("Please fill in all fields.")
            return
        if password != confirm:
            self._show_signup_error("Passwords do not match.")
            return
        if len(password) < 6:
            self._show_signup_error("Password must be at least 6 characters.")
            return

        self._signup_btn.setEnabled(False)
        self._signup_btn.setText("Creating account…")
        self._signup_error.hide()
        try:
            result = self._auth.sign_up(email, password)
            self._result = result
            self.accept()
        except RuntimeError as exc:
            self._show_signup_error(str(exc))
        finally:
            self._signup_btn.setEnabled(True)
            self._signup_btn.setText("Create Account")

    # ── helpers ───────────────────────────────────────────────────

    def _show_login_error(self, msg: str) -> None:
        self._login_error.setText(msg)
        self._login_error.show()

    def _show_signup_error(self, msg: str) -> None:
        self._signup_error.setText(msg)
        self._signup_error.show()
