# Desktop Tools API

The backend provides 22+ tools for controlling the E2B virtual desktop sandbox.

## Lifecycle

| Tool | Description |
|---|---|
| `start_desktop` | Create a new E2B desktop sandbox |
| `stop_desktop` | Destroy the desktop sandbox |
| `desktop_status` | Get sandbox status and stream URL |

## Vision (Agent Streaming)

| Tool | Description |
|---|---|
| `desktop_start_streaming` | Start sending screenshots to Gemini Live API |
| `desktop_stop_streaming` | Stop the screenshot stream |
| `desktop_screenshot` | Take a single screenshot |

## Mouse & Keyboard

| Tool | Description |
|---|---|
| `desktop_click` | Click at (x, y) coordinates |
| `desktop_scroll` | Scroll at optional coordinates |
| `desktop_drag` | Drag from (x1,y1) to (x2,y2) |
| `desktop_type` | Type text |
| `desktop_hotkey` | Press a keyboard shortcut |

## Apps & Browser

| Tool | Description |
|---|---|
| `desktop_launch` | Launch an application |
| `desktop_open_url` | Open a URL in Chrome |
| `desktop_get_windows` | List application windows |

## Shell & Files

| Tool | Description |
|---|---|
| `desktop_bash` | Run a shell command |
| `desktop_upload_file` | Upload a file to the sandbox |
| `desktop_download_file` | Download a file from the sandbox |
| `desktop_find_file` | Search for files by name/content in the sandbox |

## Voice-Enhanced Combos

| Tool | Description |
|---|---|
| `desktop_read_screen` | Screenshot + send to dashboard |
| `desktop_exec_and_show` | Run command + screenshot |
| `desktop_find_and_click` | Locate UI element + click |
| `desktop_list_files` | List directory contents |
| `desktop_multi_step` | Execute a sequence of commands |
