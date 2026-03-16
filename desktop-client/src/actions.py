"""Desktop actions — mouse, keyboard, application control.

Wraps ``pyautogui`` for mouse/keyboard automation with safety guards.
All public functions are designed to be called as cross-client action
handlers from the WebSocket client.
"""

from __future__ import annotations

import glob
import logging
import os
import subprocess
import sys
import time

import pyautogui

logger = logging.getLogger(__name__)

# Safety — add a brief pause between automated actions to avoid runaway loops
pyautogui.PAUSE = 0.05
# Move mouse to corner to trigger pyautogui fail-safe only in emergencies
pyautogui.FAILSAFE = True


def click(x: int, y: int, button: str = "left") -> dict:
    """Click at screen coordinates.

    Args:
        x: Pixel X coordinate.
        y: Pixel Y coordinate.
        button: ``"left"``, ``"right"``, or ``"middle"``.

    Returns:
        Dict with ``ok`` and the coordinates clicked.
    """
    pyautogui.click(x, y, button=button)
    return {"ok": True, "x": x, "y": y, "button": button}


def double_click(x: int, y: int) -> dict:
    """Double-click at screen coordinates."""
    pyautogui.doubleClick(x, y)
    return {"ok": True, "x": x, "y": y}


def type_text(text: str, interval: float = 0.02) -> dict:
    """Type text using keyboard simulation.

    Args:
        text: The text string to type.
        interval: Seconds between each keystroke.

    Returns:
        Dict confirming the typed text length.
    """
    pyautogui.typewrite(text, interval=interval)
    return {"ok": True, "length": len(text)}


def hotkey(*keys: str) -> dict:
    """Press a keyboard shortcut (e.g. ``hotkey("ctrl", "s")``).

    Args:
        keys: Key names as accepted by ``pyautogui.hotkey``.

    Returns:
        Dict confirming the key combo.
    """
    pyautogui.hotkey(*keys)
    return {"ok": True, "keys": list(keys)}


def move_mouse(x: int, y: int) -> dict:
    """Move mouse cursor to the given coordinates."""
    pyautogui.moveTo(x, y)
    return {"ok": True, "x": x, "y": y}


def scroll(amount: int, x: int | None = None, y: int | None = None) -> dict:
    """Scroll the mouse wheel.

    Args:
        amount: Positive scrolls up, negative scrolls down.
        x: Optional X coordinate to scroll at.
        y: Optional Y coordinate to scroll at.

    Returns:
        Dict confirming the scroll.
    """
    if x is not None and y is not None:
        pyautogui.scroll(amount, x, y)
    else:
        pyautogui.scroll(amount)
    return {"ok": True, "amount": amount}


# ── App alias map — common natural-language names → actual executable names ──
_APP_ALIASES: dict[str, list[str]] = {
    "chrome": ["google chrome", "chrome"],
    "google chrome": ["google chrome", "chrome"],
    "firefox": ["mozilla firefox", "firefox"],
    "edge": ["microsoft edge", "msedge"],
    "microsoft edge": ["microsoft edge", "msedge"],
    "notepad": ["notepad"],
    "notepad++": ["notepad++"],
    "vscode": ["visual studio code", "code"],
    "vs code": ["visual studio code", "code"],
    "visual studio code": ["visual studio code", "code"],
    "word": ["microsoft word", "winword"],
    "excel": ["microsoft excel", "excel"],
    "powerpoint": ["microsoft powerpoint", "powerpnt"],
    "outlook": ["microsoft outlook", "outlook"],
    "teams": ["microsoft teams", "teams"],
    "spotify": ["spotify"],
    "discord": ["discord"],
    "slack": ["slack"],
    "terminal": ["windows terminal", "wt"],
    "cmd": ["command prompt", "cmd"],
    "powershell": ["powershell", "pwsh"],
    "file explorer": ["explorer"],
    "explorer": ["explorer"],
    "calculator": ["calculator", "calc"],
    "paint": ["paint", "mspaint"],
    "vlc": ["vlc media player", "vlc"],
    "obs": ["obs studio", "obs64"],
    "zoom": ["zoom", "zoom workplace"],
    "brave": ["brave", "brave browser"],
    "opera": ["opera", "opera browser"],
    "gimp": ["gimp"],
    "blender": ["blender"],
    "steam": ["steam"],
}


def _search_windows_apps(query: str) -> str | None:
    """Search Windows for an application matching *query*.

    Searches in order:
    1. Well-known alias map
    2. Start Menu shortcuts (.lnk files)
    3. Common install directories for .exe files
    4. PATH executables

    Returns the best matching path/command, or None.
    """
    query_lower = query.lower().strip()

    # 1. Alias map → try Start Menu shortcut for each alias
    aliases = _APP_ALIASES.get(query_lower, [query_lower])
    for alias in aliases:
        found = _search_start_menu(alias)
        if found:
            return found

    # 2. Direct Start Menu search with original query
    found = _search_start_menu(query_lower)
    if found:
        return found

    # 3. Search common install directories
    found = _search_install_dirs(query_lower)
    if found:
        return found

    # 4. Check PATH
    found = _search_path(query_lower)
    if found:
        return found

    return None


def _search_start_menu(query: str) -> str | None:
    """Search Start Menu folders for a .lnk shortcut matching *query*."""
    start_menu_dirs = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    best_match: str | None = None
    best_score = 0

    for base_dir in start_menu_dirs:
        if not os.path.isdir(base_dir):
            continue
        for root, _dirs, files in os.walk(base_dir):
            for fname in files:
                if not fname.lower().endswith(".lnk"):
                    continue
                name_no_ext = fname[:-4].lower()
                score = _match_score(query, name_no_ext)
                if score > best_score:
                    best_score = score
                    best_match = os.path.join(root, fname)

    if best_match and best_score >= 50:
        logger.info("app_found_start_menu", query=query, match=best_match, score=best_score)
        return best_match
    return None


def _search_install_dirs(query: str) -> str | None:
    """Search common Windows install directories for executables."""
    search_dirs = [
        os.environ.get("PROGRAMFILES", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        os.path.join(os.environ.get("LOCALAPPDATA", "")),
    ]
    best_match: str | None = None
    best_score = 0

    for base_dir in search_dirs:
        if not base_dir or not os.path.isdir(base_dir):
            continue
        # Search only 2 levels deep to avoid slowness
        for pattern in [os.path.join(base_dir, "*", "*.exe"), os.path.join(base_dir, "*", "*", "*.exe")]:
            for exe_path in glob.iglob(pattern):
                exe_name = os.path.basename(exe_path).lower()
                # Skip uninstallers, updaters, crash handlers etc.
                if any(skip in exe_name for skip in ("unins", "update", "crash", "helper", "setup", "install")):
                    continue
                score = _match_score(query, exe_name.replace(".exe", ""))
                # Also check parent folder name
                parent = os.path.basename(os.path.dirname(exe_path)).lower()
                folder_score = _match_score(query, parent)
                score = max(score, folder_score)
                if score > best_score:
                    best_score = score
                    best_match = exe_path

    if best_match and best_score >= 50:
        logger.info("app_found_install_dir", query=query, match=best_match, score=best_score)
        return best_match
    return None


def _search_path(query: str) -> str | None:
    """Check if an executable matching *query* exists on PATH."""
    query_lower = query.lower().replace(" ", "")
    for ext in ("", ".exe", ".cmd", ".bat", ".com"):
        candidate = query_lower + ext
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            full = os.path.join(path_dir, candidate)
            if os.path.isfile(full):
                return full
    return None


def _match_score(query: str, target: str) -> int:
    """Simple fuzzy match score (0-100) between query and target strings."""
    query = query.lower().strip()
    target = target.lower().strip()
    if query == target:
        return 100
    if query in target:
        return 80 + min(15, int(15 * len(query) / max(len(target), 1)))
    if target in query:
        return 70
    # Word overlap
    q_words = set(query.split())
    t_words = set(target.replace("-", " ").replace("_", " ").split())
    if q_words and t_words:
        overlap = len(q_words & t_words)
        if overlap:
            return 50 + int(30 * overlap / len(q_words))
    return 0


def _search_macos_apps(query: str) -> str | None:
    """Search macOS /Applications for an app matching *query*."""
    query_lower = query.lower()
    best: str | None = None
    best_score = 0
    for app_dir in ["/Applications", os.path.expanduser("~/Applications")]:
        if not os.path.isdir(app_dir):
            continue
        for entry in os.listdir(app_dir):
            if not entry.endswith(".app"):
                continue
            name = entry[:-4].lower()
            score = _match_score(query_lower, name)
            if score > best_score:
                best_score = score
                best = entry[:-4]  # name without .app for `open -a`
    return best if best and best_score >= 50 else None


def search_applications(query: str) -> dict:
    """Search for installed applications matching *query*.

    Returns a list of matching application names/paths so the agent
    can pick the right one before launching.

    Args:
        query: Search term (e.g. 'chrome', 'visual studio').

    Returns:
        Dict with ``matches`` list containing found applications.
    """
    matches: list[dict] = []
    query_lower = query.lower().strip()

    if sys.platform == "win32":
        # Search Start Menu shortcuts
        start_menu_dirs = [
            os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
        ]
        seen: set[str] = set()
        for base_dir in start_menu_dirs:
            if not os.path.isdir(base_dir):
                continue
            for root, _dirs, files in os.walk(base_dir):
                for fname in files:
                    if not fname.lower().endswith(".lnk"):
                        continue
                    name = fname[:-4]
                    score = _match_score(query_lower, name.lower())
                    if score >= 40 and name.lower() not in seen:
                        seen.add(name.lower())
                        matches.append({"name": name, "path": os.path.join(root, fname), "score": score})
        matches.sort(key=lambda m: m["score"], reverse=True)
    elif sys.platform == "darwin":
        for app_dir in ["/Applications", os.path.expanduser("~/Applications")]:
            if not os.path.isdir(app_dir):
                continue
            for entry in os.listdir(app_dir):
                if entry.endswith(".app"):
                    name = entry[:-4]
                    score = _match_score(query_lower, name.lower())
                    if score >= 40:
                        matches.append({"name": name, "path": os.path.join(app_dir, entry), "score": score})
        matches.sort(key=lambda m: m["score"], reverse=True)
    else:
        # Linux: search .desktop files
        desktop_dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
        for d in desktop_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if fname.endswith(".desktop"):
                    name = fname[:-8]
                    score = _match_score(query_lower, name.lower())
                    if score >= 40:
                        matches.append({"name": name, "path": os.path.join(d, fname), "score": score})
        matches.sort(key=lambda m: m["score"], reverse=True)

    return {"matches": matches[:10], "query": query}


def open_application(name_or_path: str) -> dict:
    """Launch an application by name or path.

    Searches for the application first to resolve the correct executable,
    then launches it. On Windows, searches Start Menu shortcuts, common
    install directories, and PATH. On macOS, searches /Applications.

    Args:
        name_or_path: Application name or full path.

    Returns:
        Dict with ``ok`` and the process launched.
    """
    resolved: str | None = None

    try:
        if sys.platform == "win32":
            # First, try to find the app via search
            resolved = _search_windows_apps(name_or_path)
            if resolved:
                logger.info("app_resolved", input=name_or_path, resolved=resolved)
                os.startfile(resolved)  # noqa: S606 — opens .lnk or .exe properly
            else:
                # Fallback: try `start` command with the raw name
                logger.info("app_fallback_start", input=name_or_path)
                subprocess.Popen(  # noqa: S603
                    ["cmd", "/c", "start", "", name_or_path],
                    shell=False,
                )
        elif sys.platform == "darwin":
            resolved = _search_macos_apps(name_or_path)
            app_name = resolved or name_or_path
            subprocess.Popen(["open", "-a", app_name])  # noqa: S603
        else:
            subprocess.Popen([name_or_path])  # noqa: S603

        time.sleep(0.5)
        return {"ok": True, "app": name_or_path, "resolved": resolved or name_or_path}
    except FileNotFoundError:
        return {"ok": False, "error": f"Application not found: {name_or_path}"}
    except OSError as exc:
        return {"ok": False, "error": f"Failed to open {name_or_path}: {exc}"}


def get_active_window_title() -> str:
    """Get the title of the currently focused window."""
    try:
        win = pyautogui.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""


def get_mouse_position() -> dict:
    """Return the current mouse cursor position."""
    pos = pyautogui.position()
    return {"x": pos.x, "y": pos.y}


def get_screen_size() -> dict:
    """Return the primary screen dimensions."""
    w, h = pyautogui.size()
    return {"width": w, "height": h}
