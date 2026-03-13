# Smart Glasses — Omni Hub Client

ESP32-CAM + INMP441 I2S microphone → Omni Hub backend → real-time AI assistant you can wear.

## Architecture

```
┌────────────────────────────────────┐
│  ESP32-CAM + INMP441 Mic           │
│  Firmware: firmware/esp32_cam_mic  │
│                                    │
│  HTTP Endpoints:                   │
│    /snapshot → JPEG frame          │
│    /audio   → PCM 16kHz stream     │
│    /status  → JSON health check    │
└──────────┬─────────────────────────┘
           │ WiFi (HTTP)
           │
┌──────────▼─────────────────────────┐
│  Python Host Client                │
│  glasses_client.py                 │
│                                    │
│  • Fetches camera frames           │
│  • Streams mic audio (host or ESP) │
│  • Plays agent audio via speaker   │
│  • Handles T3 tool invocations     │
│  • Reconnects automatically        │
└──────────┬─────────────────────────┘
           │ WebSocket /ws/live
           │
┌──────────▼─────────────────────────┐
│  Omni Hub Backend (port 8000)      │
│  Same agent as dashboard/desktop   │
│  • All tools, plugins, MCP         │
│  • Cross-device actions            │
│  • Session continuity              │
└────────────────────────────────────┘
```

The glasses connect to the **same backend and same agent** as the web dashboard, desktop client, CLI, etc.
The backend handles all AI processing — the ESP32 just provides camera and mic hardware.

---

## Hardware

### Required Components

| Component | Purpose | ~Cost |
|-----------|---------|-------|
| ESP32-CAM (AI-Thinker) | Camera + WiFi | $6 |
| INMP441 I2S MEMS Mic | Microphone | $3 |
| USB-UART adapter (FTDI) | Flashing firmware | $3 |
| Power supply (3.3V/5V) | Powering the board | $2 |
| Jumper wires | Connections | $1 |

**Optional** (for standalone glasses):
- 3D-printed glasses frame
- LiPo battery + TP4056 charger
- MAX98357A I2S DAC (speaker on glasses — currently speaker is on host)
- ESP32-S3-CAM (more GPIOs, better for expansion)

### Wiring Diagram — ESP32-CAM + INMP441

```
ESP32-CAM (AI-Thinker)              INMP441
┌─────────────────────┐       ┌──────────────┐
│                     │       │              │
│  GPIO 14 ──────────────────── SCK (BCLK)  │
│  GPIO 15 ──────────────────── WS  (LRCLK) │
│  GPIO 13 ──────────────────── SD  (DOUT)  │
│                     │       │              │
│  3.3V ─────────────────────── VDD          │
│  GND ──────────────────────── GND          │
│                     │   ┌──── L/R          │
│                     │   │   └──────────────┘
└─────────────────────┘   │
                         GND  (L/R → GND = left channel)
```

> **Note**: GPIO 12/13/14/15 are shared with the SD card slot.
> The INMP441 wiring works when the SD card is **not** inserted.
> If you need the SD card, use an ESP32-S3 board (see below).

### Alternative: ESP32-S3 Wiring

If using an ESP32-S3-CAM board (more GPIOs available):

| INMP441 Pin | ESP32-S3 GPIO |
|-------------|---------------|
| SCK (BCLK)  | GPIO 42 |
| WS (LRCLK)  | GPIO 41 |
| SD (DOUT)   | GPIO 2  |
| VDD          | 3.3V    |
| GND          | GND     |
| L/R          | GND     |

Update the `#define` pins in `firmware/esp32_cam_mic.ino` accordingly.

---

## Firmware Setup

### Option A: Arduino IDE

1. Install [ESP32 board support](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html)
2. Open `firmware/esp32_cam_mic.ino` in Arduino IDE
3. Set your WiFi credentials at the top of the file:
   ```cpp
   const char* WIFI_SSID     = "YourWiFi";
   const char* WIFI_PASSWORD = "YourPassword";
   ```
4. Board: **AI Thinker ESP32-CAM**
5. Partition Scheme: **Huge APP (3MB No OTA/1MB SPIFFS)**
6. Upload speed: 921600
7. Connect FTDI adapter (GPIO 0 → GND during flash, release after)
8. Upload

### Option B: PlatformIO

```bash
cd smart-glasses/firmware
# Edit WiFi credentials in esp32_cam_mic.ino
pio run -t upload -t monitor
```

### Verify

After flashing, open Serial Monitor (115200 baud). You should see:
```
=== ESP32 Smart Glasses Firmware ===
[WIFI] Connected! IP: 192.168.1.100
[CAM] Camera initialized OK
[MIC] I2S microphone initialized OK (16000Hz)
=== Ready ===
  Camera:  http://192.168.1.100/snapshot
  Audio:   http://192.168.1.100/audio
  Status:  http://192.168.1.100/status
```

Test in a browser:
- `http://192.168.1.100/snapshot` — should show a JPEG image
- `http://192.168.1.100/status` — should show JSON status

---

## Python Client Setup

### Prerequisites

```bash
pip install websockets aiohttp pyaudio
```

On Linux, PyAudio may need:
```bash
sudo apt install portaudio19-dev
pip install pyaudio
```

On macOS:
```bash
brew install portaudio
pip install pyaudio
```

### Get a Firebase Token

Use the token from the dashboard dev tools, or:
```bash
cd backend
python scripts/get_test_token.py
# Save the output token
```

### Run

```bash
cd smart-glasses

# Basic: ESP32 camera + host computer mic
python glasses_client.py --token <jwt> --esp32-ip 192.168.1.100

# With ESP32 INMP441 mic (audio streamed from ESP32):
python glasses_client.py --token <jwt> --esp32-ip 192.168.1.100 --mic esp32

# Camera only, no mic (visual narrator mode):
python glasses_client.py --token <jwt> --esp32-ip 192.168.1.100 --no-mic

# Custom backend server:
python glasses_client.py --token <jwt> --server ws://myserver.com:8000

# Token from file:
python glasses_client.py --token-file ../backend/test_output/token.txt --esp32-ip 192.168.1.100

# Faster frame rate (every 2 seconds):
python glasses_client.py --token <jwt> --esp32-ip 192.168.1.100 --interval 2
```

### What Happens

1. Client connects to your Omni Hub backend at `/ws/live`
2. Authenticates with Firebase JWT as `client_type: "glasses"`
3. Registers capabilities: `camera_capture`, `microphone`, `speaker`, `visual_narration`
4. Starts parallel tasks:
   - **Camera**: Grabs JPEG from ESP32 every N seconds, sends as base64 image
   - **Mic**: Streams PCM audio (from host mic or ESP32 INMP441) as binary frames
   - **Speaker**: Plays audio received from agent
   - **Receiver**: Handles all JSON messages (transcriptions, tool calls, etc.)
5. The agent can:
   - See what the camera sees
   - Hear what the mic picks up
   - Speak back through the host speaker
   - Call T3 tools on the glasses (e.g., `capture_photo`, `set_frame_rate`)
   - Route actions to other devices (desktop, chrome, etc.)

---

## T3 Tools (Agent → Glasses)

The glasses advertise these tools that the agent can invoke:

| Tool | Description |
|------|-------------|
| `capture_photo` | Take an on-demand photo from the camera |
| `set_frame_rate` | Change camera frame interval (1-30 seconds) |

Example agent interaction:
> "Take a photo of what's in front of you" → agent calls `capture_photo` → gets JPEG back

---

## Mic Modes

| Mode | Flag | Audio Source | Latency |
|------|------|-------------|---------|
| **Host** (default) | `--mic host` | Host computer mic via PyAudio | Low |
| **ESP32** | `--mic esp32` | INMP441 on ESP32 via HTTP `/audio` | Medium |
| **None** | `--no-mic` | No mic — camera-only visual narrator | N/A |

**Host mic** is recommended for lowest latency. Use **ESP32 mic** when the glasses
need to be fully wireless (e.g., walking around with just glasses + phone hotspot).

---

## Compared to Old `gemini_cam_narrator.py`

| Feature | Old (narrator) | New (glasses_client) |
|---------|---------------|---------------------|
| Backend connection | Direct Gemini API | Omni Hub `/ws/live` |
| Authentication | API key only | Firebase JWT |
| Other clients | None | Shared with dashboard, desktop, etc. |
| Tools & Plugins | None | Full access to all backend tools |
| Microphone | None | Host mic or ESP32 INMP441 |
| T3 reverse-RPC | None | `capture_photo`, `set_frame_rate` |
| Cross-device | None | Can trigger actions on desktop/chrome |
| Session continuity | None | Resumable sessions, memory |
| Interruptions | None | Backend handles interruptions |
| Cost tracking | None | Backend callback tracks tokens |
| Permission checks | None | Backend blocks destructive tools |

---

## Troubleshooting

**Camera not responding**
- Check ESP32-CAM IP matches `--esp32-ip`
- Try `http://<ip>/status` in browser
- Ensure camera module ribbon cable is properly seated

**No audio from mic**
- Verify INMP441 wiring (especially L/R → GND)
- Check `http://<ip>/status` shows `"microphone": true`
- Try `--mic host` to verify backend audio path works

**WebSocket connection fails**
- Ensure backend is running: `cd backend && uv run uvicorn app.main:app --port 8000`
- Verify token is valid (not expired)
- Check firewall allows WebSocket connections

**Audio playback issues**
- List audio devices: `python -c "import pyaudio; p=pyaudio.PyAudio(); [print(p.get_device_info_by_index(i)['name']) for i in range(p.get_device_count())]"`
- Ensure speakers/headphones are the default output device

**ESP32-CAM pin conflicts**
- GPIO 12/13/14/15 conflict with SD card — remove SD card
- GPIO 4 is the flash LED — don't use for I2S
- If you need SD + mic, use ESP32-S3 board
