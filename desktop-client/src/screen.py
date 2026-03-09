"""Screen capture utilities using mss."""

# TODO: Implement:
#   - Full screen capture → PIL Image → JPEG bytes
#   - Region capture (x, y, w, h)
#   - Active window capture
#   - Screen resolution info
#   - Multi-monitor support
#   - Compress for WS transmission (JPEG quality 60-80)

import logging

logger = logging.getLogger(__name__)


def capture_screen(region=None, quality=75):
    """Capture screen or region, return JPEG bytes."""
    pass


def get_screen_info():
    """Return screen resolution and monitor layout."""
    pass


def capture_active_window():
    """Capture only the active/focused window."""
    pass
