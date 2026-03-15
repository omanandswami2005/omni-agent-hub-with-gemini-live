import sys
from unittest.mock import MagicMock

# Mock out GUI, audio, screen capture and automation libraries entirely before any tests run
# since they depend on display, audio hardware, and X11/Qt environments unavailable in headless CI.
sys.modules['pyautogui'] = MagicMock()
sys.modules['mss'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt6.QtWidgets'] = MagicMock()
sys.modules['PyQt6.QtCore'] = MagicMock()
sys.modules['qasync'] = MagicMock()

# Since we mocked the dependencies, the underlying src modules should not crash on import
