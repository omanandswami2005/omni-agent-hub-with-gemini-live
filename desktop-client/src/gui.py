import asyncio
import base64
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from src.screen import capture_screen

class MainWindow(QMainWindow):
    # Signals to communicate with the asyncio client
    send_text_signal = pyqtSignal(str)
    toggle_mic_signal = pyqtSignal(bool)
    toggle_screen_signal = pyqtSignal(bool)
    send_screen_signal = pyqtSignal(str) # For sending base64 image
    connect_signal = pyqtSignal(bool) # True for connect, False for disconnect
    interrupt_signal = pyqtSignal()

    # Signal to prompt for confirmation from background thread
    security_prompt_signal = pyqtSignal(str, str, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Omni Desktop Agent")
        self.resize(500, 650)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Connection / Status Area
        self.status_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self.status_layout.addWidget(self.status_label)

        self.connect_button = QPushButton("Connect")
        self.connect_button.setCheckable(True)
        self.connect_button.clicked.connect(self._on_connect_toggled)
        self.status_layout.addWidget(self.connect_button)

        self.layout.addLayout(self.status_layout)

        # Chat Area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.layout.addWidget(self.chat_display)

        # Input Area
        self.input_layout = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a message...")
        self.text_input.returnPressed.connect(self._on_send_clicked)
        self.input_layout.addWidget(self.text_input)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)
        self.input_layout.addWidget(self.send_button)
        self.layout.addLayout(self.input_layout)

        # Controls Area
        self.controls_layout = QHBoxLayout()

        self.mic_button = QPushButton("Mic: Off")
        self.mic_button.setCheckable(True)
        self.mic_button.clicked.connect(self._on_mic_toggled)
        self.controls_layout.addWidget(self.mic_button)

        self.screen_button = QPushButton("Screen Share: Off")
        self.screen_button.setCheckable(True)
        self.screen_button.clicked.connect(self._on_screen_toggled)
        self.controls_layout.addWidget(self.screen_button)

        self.interrupt_button = QPushButton("Interrupt Agent")
        self.interrupt_button.clicked.connect(self._on_interrupt_clicked)
        self.controls_layout.addWidget(self.interrupt_button)

        self.layout.addLayout(self.controls_layout)

        # Connect internal signal
        self.security_prompt_signal.connect(self._handle_security_prompt)

        # Timer for screen sharing
        self.screen_timer = QTimer(self)
        self.screen_timer.timeout.connect(self._capture_and_send_screen)
        # Capture screen every 3 seconds when active
        self.screen_interval_ms = 3000

    def _on_connect_toggled(self, checked):
        if checked:
            self.connect_button.setText("Disconnect")
            self.connect_signal.emit(True)
        else:
            self.connect_button.setText("Connect")
            self.connect_signal.emit(False)

    def _on_send_clicked(self):
        text = self.text_input.text().strip()
        if text:
            self.append_chat(f"You: {text}")
            self.send_text_signal.emit(text)
            self.text_input.clear()

    def _on_mic_toggled(self, checked):
        if checked:
            self.mic_button.setText("Mic: On")
            self.mic_button.setStyleSheet("background-color: #ffcccc;")
        else:
            self.mic_button.setText("Mic: Off")
            self.mic_button.setStyleSheet("")
        self.toggle_mic_signal.emit(checked)

    def _on_screen_toggled(self, checked):
        if checked:
            self.screen_button.setText("Screen Share: On")
            self.screen_button.setStyleSheet("background-color: #ccffcc;")
            self.screen_timer.start(self.screen_interval_ms)
        else:
            self.screen_button.setText("Screen Share: Off")
            self.screen_button.setStyleSheet("")
            self.screen_timer.stop()
        self.toggle_screen_signal.emit(checked)

    def _on_interrupt_clicked(self):
        self.append_chat("System: Interrupting agent...")
        self.interrupt_signal.emit()

    def _capture_and_send_screen(self):
        try:
            # Capture full screen using screen_plugin utility
            img_bytes = capture_screen(quality=50) # Use lower quality for continuous streaming
            # Convert to base64
            b64_img = base64.b64encode(img_bytes).decode('utf-8')
            # Emit signal to send over websocket
            self.send_screen_signal.emit(b64_img)
        except Exception as e:
            print(f"Failed to capture screen: {e}")

    def set_status(self, connected: bool):
        if connected:
            self.status_label.setText("Status: Connected")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.connect_button.setChecked(True)
            self.connect_button.setText("Disconnect")
        else:
            self.status_label.setText("Status: Disconnected")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.connect_button.setChecked(False)
            self.connect_button.setText("Connect")
            # Stop screen share and mic on disconnect
            if self.screen_timer.isActive():
                self.screen_button.setChecked(False)
                self._on_screen_toggled(False)
            if self.mic_button.isChecked():
                self.mic_button.setChecked(False)
                self._on_mic_toggled(False)

    def append_chat(self, text: str):
        self.chat_display.append(text)

    def _handle_security_prompt(self, title: str, message: str, future):
        """Show message box safely on the main thread and set the future result."""
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        # Set the result on the asyncio Future (thread-safe handled in caller)
        loop = future.get_loop()
        if reply == QMessageBox.StandardButton.Yes:
            loop.call_soon_threadsafe(future.set_result, True)
        else:
            loop.call_soon_threadsafe(future.set_result, False)

    def show_confirmation_dialog_async(self, title: str, message: str, future):
        """Emit a signal to show the dialog on the main thread."""
        self.security_prompt_signal.emit(title, message, future)
