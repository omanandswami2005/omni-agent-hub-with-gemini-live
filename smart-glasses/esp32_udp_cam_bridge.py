#!/usr/bin/env python3
"""ESP32 Audio + Camera bridge for Omni Hub /ws/live — standalone, no imports from esp32_udp_bridge.

Bridges UDP audio from an ESP32 to the Omni Hub backend AND periodically
sends camera snapshots from an ESP32-CAM HTTP endpoint.

- Audio input : ESP32 UDP mic → backend binary PCM frames
- Audio output: backend binary PCM → ESP32 UDP speaker (resampled 24→16kHz)
- Camera input: ESP32-CAM HTTP JPEG snapshots → backend image messages
                {"type":"image","data_base64":"...","mime_type":"image/jpeg"}

All audio features from the base bridge are included verbatim:
  mic floor handshake, barge-in interruption, half-duplex echo suppression,
  TTS announcements, Firebase auto-login, detailed logging.

Usage
-----
  pip install edge-tts websockets

  # Auto-login with embedded creds (change BACKEND_WS / ESP32_IP below first):
  python esp32_udp_cam_bridge.py

  # Explicit token:
  python esp32_udp_cam_bridge.py --token <firebase-jwt>

  # Custom camera URL / frame rate:
  python esp32_udp_cam_bridge.py --cam-url http://192.168.0.107/capture --cam-fps 2.0

  # Audio only (no camera):
  python esp32_udp_cam_bridge.py --no-cam
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request

try:
    import edge_tts
except ImportError:
    print("Missing dependency. Run:  pip install edge-tts websockets")
    sys.exit(1)

try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("Missing dependency. Run:  pip install edge-tts websockets")
    sys.exit(1)



# ─── Firebase credentials (embedded) ─────────────────────────────────────────

_FIREBASE_API_KEY  = "AIzaSyC3a98P8sOUKEwGJuJWp2gA6i7o-CW21pE"
_FIREBASE_EMAIL    = "omanand@gmail.com"
_FIREBASE_PASSWORD = "123456"


def _get_firebase_token(email: str, password: str, api_key: str) -> str:
    """Sign in with Firebase email/password, return a fresh ID token."""
    import json as _json
    import urllib.request as _req
    import urllib.error as _err

    url  = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    body = _json.dumps({"email": email, "password": password,
                        "returnSecureToken": True}).encode()
    req  = _req.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with _req.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read())["idToken"]
    except _err.HTTPError as e:
        raise RuntimeError(f"Firebase sign-in failed ({e.code}): {e.read().decode(errors='replace')}") from e


# ─── Configuration ────────────────────────────────────────────────────────────

BACKEND_WS   = "wss://omni-backend-666233642847.us-central1.run.app"  # updated URL

# ESP32 network config — update to match your setup
ESP32_IP     = "192.168.1.100"   # ← change to your ESP32's IP address
CAM_IP       = ESP32_IP          # default cam same device; override with --cam-url
MIC_PORT     = 4444              # UDP port: ESP32 sends mic audio here
SPEAKER_PORT = 5555              # UDP port: ESP32 listens for speaker audio here

# Camera config
CAM_FPS      = 1.0               # frames per second to capture and send

# Audio parameters (must match ESP32 firmware)
INPUT_RATE   = 16000
OUTPUT_RATE  = 24000
ESP32_RATE   = 16000
SAMPLE_WIDTH = 2

# UDP chunk sizes
MIC_CHUNK    = 1024
SPK_CHUNK    = 1024

# Reconnect settings
RECONNECT_MIN_S = 3
RECONNECT_MAX_S = 30

# Exact playback pacing
_SAMPLES_PER_CHUNK  = SPK_CHUNK // SAMPLE_WIDTH   # 512
_SPK_SEND_INTERVAL  = _SAMPLES_PER_CHUNK / ESP32_RATE  # 0.032s


def _resample_pcm(data: bytes, in_rate: int, out_rate: int) -> bytes:
    """Resample mono 16-bit PCM in_rate → out_rate (pure stdlib, linear interp)."""
    if in_rate == out_rate:
        return data
    n_in = len(data) // 2
    samples = struct.unpack(f"<{n_in}h", data[:n_in * 2])
    ratio = in_rate / out_rate
    n_out = int(n_in / ratio)
    out = []
    for i in range(n_out):
        src = i * ratio
        idx = int(src)
        frac = src - idx
        a = samples[idx] if idx < n_in else 0
        b = samples[idx + 1] if idx + 1 < n_in else 0
        out.append(int(a + frac * (b - a)))
    return struct.pack(f"<{n_out}h", *out)


# ─── Bridge ───────────────────────────────────────────────────────────────────

class ESP32UDPCamBridge:
    """Standalone audio + camera bridge — no base class import dependency."""

    def __init__(
        self,
        token: str,
        server: str,
        esp32_ip: str,
        mic_port: int,
        speaker_port: int,
        cam_url: str,
        cam_fps: float,
        cam_enabled: bool,
    ):
        self.token = token
        self.server = server.rstrip("/")
        self.esp32_ip = esp32_ip
        self.mic_port = mic_port
        self.speaker_port = speaker_port

        self._running = False
        self._was_connected = False

        # Mic UDP socket
        self._mic_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._mic_sock.bind(("0.0.0.0", mic_port))
        self._mic_sock.setblocking(False)

        # Speaker UDP socket
        self._spk_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Asyncio synchronisation primitives
        self._mic_granted  = asyncio.Event()
        self._spk_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._interrupted  = asyncio.Event()

        # Playback state
        self._playing      = False
        self._agent_state  = ""

        # Post-playback cooldown (150ms)
        self._spk_stop_time = 0.0
        self._spk_cooldown  = 0.15

        # Mic counters
        self._mic_sent              = 0
        self._mic_dropped_playing   = 0
        self._mic_dropped_cooldown  = 0
        self._mic_log_interval      = 50

        # Speaker counters
        self._spk_frames_received = 0
        self._spk_frames_played   = 0
        self._spk_frames_dropped  = 0

        # Camera state
        self.cam_url     = cam_url
        self.cam_fps     = max(0.1, cam_fps)
        self.cam_enabled = cam_enabled
        self._cam_sent   = 0
        self._cam_fail   = 0

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _log(self, tag: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime())
        ms = f"{time.time() % 1:.3f}"[1:]
        print(f"[{ts}{ms}][{tag}] {msg}", flush=True)

    def _audio_level(self, pcm_bytes: bytes) -> int:
        """Return peak amplitude (0-32768) of 16-bit PCM for logging."""
        if len(pcm_bytes) < 2:
            return 0
        n = len(pcm_bytes) // 2
        samples = struct.unpack(f"<{n}h", pcm_bytes[:n * 2])
        return max(abs(s) for s in samples) if samples else 0

    # ── TTS announcements ─────────────────────────────────────────────────────

    async def _speak(self, text: str) -> None:
        try:
            communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
            mp3_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_bytes += chunk["data"]
            if not mp3_bytes:
                return
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                "-f", "s16le", "-ar", str(ESP32_RATE), "-ac", "1",
                "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            pcm, _ = await proc.communicate(mp3_bytes)
            self._log("TTS", f"Speaking '{text}' ({len(pcm)} PCM bytes @ {ESP32_RATE}Hz)")
            await self._play_speaker_audio(pcm)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._log("TTS", f"Error: {e}")

    async def _announce_connecting(self) -> None:
        while not self._was_connected:
            await self._speak("Connecting")
            if not self._was_connected:
                await asyncio.sleep(0.3)

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def _authenticate(self, ws) -> bool:
        auth_msg = {
            "type": "auth",
            "token": self.token,
            "client_type": "glasses",
            "capabilities": ["microphone", "speaker"],
        }
        await ws.send(json.dumps(auth_msg))
        self._log("AUTH", "Waiting for server...")
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
        except asyncio.TimeoutError:
            self._log("AUTH", "Timeout waiting for auth_response")
            return False
        resp = json.loads(raw)
        if resp.get("type") == "auth_response":
            if resp.get("status") != "ok":
                self._log("AUTH", f"Rejected: {resp.get('error', 'unknown')}")
                return False
            uid    = resp.get("user_id", "?")
            others = resp.get("other_clients_online", [])
            self._log("AUTH", f"OK — user={uid}")
            if others:
                self._log("AUTH", f"Other devices online: {', '.join(others)}")
            self._was_connected = True
        return True

    # ── Mic floor ─────────────────────────────────────────────────────────────

    async def _acquire_mic(self, ws) -> None:
        self._mic_granted.clear()
        await ws.send(json.dumps({"type": "mic_acquire"}))
        self._log("MIC", "Requested mic floor — waiting for grant...")

    async def _release_mic(self, ws) -> None:
        self._mic_granted.clear()
        try:
            await ws.send(json.dumps({"type": "mic_release"}))
        except Exception:
            pass
        self._log("MIC", "Mic floor released")

    # ── Mic task: UDP → WebSocket ─────────────────────────────────────────────

    async def _send_mic_audio(self, ws) -> None:
        loop = asyncio.get_event_loop()
        self._log("MIC", f"Listening on UDP 0.0.0.0:{self.mic_port}")

        await asyncio.sleep(0)
        await self._acquire_mic(ws)

        _GRANT_TIMEOUT_S = 3.0
        _loop_start = loop.time()
        while not self._mic_granted.is_set():
            elapsed = loop.time() - _loop_start
            if elapsed >= _GRANT_TIMEOUT_S:
                self._log("MIC", f"No grant received in {_GRANT_TIMEOUT_S:.0f}s — proceeding (auto-acquire on first frame)")
                self._mic_granted.set()
                break
            try:
                await asyncio.wait_for(
                    self._mic_granted.wait(),
                    timeout=min(1.0, _GRANT_TIMEOUT_S - elapsed),
                )
            except asyncio.TimeoutError:
                elapsed2 = loop.time() - _loop_start
                self._log("MIC", f"Still waiting for mic floor grant ({elapsed2:.1f}s / {_GRANT_TIMEOUT_S:.0f}s)...")
        self._log("MIC", "Mic floor granted — streaming audio to backend")

        while self._running:
            try:
                data = await loop.sock_recv(self._mic_sock, MIC_CHUNK)
                now  = time.monotonic()
                if self._playing:
                    self._mic_dropped_playing += 1
                    total = self._mic_dropped_playing + self._mic_dropped_cooldown
                    if total % self._mic_log_interval == 1:
                        lvl = self._audio_level(data)
                        self._log("MIC-DROP", f"Dropped (playing) peak={lvl} sent={self._mic_sent} drop_play={self._mic_dropped_playing} drop_cool={self._mic_dropped_cooldown}")
                    continue
                elapsed_since_stop = now - self._spk_stop_time
                if elapsed_since_stop < self._spk_cooldown:
                    self._mic_dropped_cooldown += 1
                    total = self._mic_dropped_playing + self._mic_dropped_cooldown
                    if total % self._mic_log_interval == 1:
                        lvl = self._audio_level(data)
                        self._log("MIC-DROP", f"Dropped (cooldown {elapsed_since_stop:.3f}s/{self._spk_cooldown:.3f}s) peak={lvl}")
                    continue
                lvl = self._audio_level(data)
                self._mic_sent += 1
                if self._mic_sent % self._mic_log_interval == 1:
                    self._log("MIC-TX", f"Sent #{self._mic_sent} {len(data)}B peak={lvl} playing={self._playing} interrupted={self._interrupted.is_set()} state={self._agent_state!r}")
                await ws.send(data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log("MIC", f"Error: {e}")
                break
        self._log("MIC", f"Stopped. Total sent={self._mic_sent} dropped_playing={self._mic_dropped_playing} dropped_cooldown={self._mic_dropped_cooldown}")

    # ── Speaker task: WebSocket → UDP ─────────────────────────────────────────

    def _flush_spk_queue(self) -> None:
        flushed = flushed_bytes = 0
        while not self._spk_queue.empty():
            try:
                chunk = self._spk_queue.get_nowait()
                flushed += 1
                flushed_bytes += len(chunk)
                self._spk_frames_dropped += 1
            except asyncio.QueueEmpty:
                break
        if flushed:
            self._log("SPK-FLUSH", f"Flushed {flushed} chunks ({flushed_bytes}B) | total_recv={self._spk_frames_received} played={self._spk_frames_played} dropped={self._spk_frames_dropped}")

    async def _play_speaker_audio(self, audio_bytes: bytes) -> None:
        raw_len = len(audio_bytes)
        if OUTPUT_RATE != ESP32_RATE:
            audio_bytes = _resample_pcm(audio_bytes, OUTPUT_RATE, ESP32_RATE)
        n_chunks   = (len(audio_bytes) + SPK_CHUNK - 1) // SPK_CHUNK
        duration_s = len(audio_bytes) / (ESP32_RATE * SAMPLE_WIDTH)
        peak       = self._audio_level(audio_bytes[:SPK_CHUNK]) if audio_bytes else 0
        self._log("SPK-PLAY", f"START raw={raw_len}B resampled={len(audio_bytes)}B chunks={n_chunks} duration={duration_s:.3f}s peak={peak} queue_depth={self._spk_queue.qsize()}")
        self._playing = True
        chunks_sent = 0
        t_start = time.monotonic()
        try:
            for i in range(0, len(audio_bytes), SPK_CHUNK):
                if self._interrupted.is_set():
                    self._log("SPK-PLAY", f"CUT at chunk {chunks_sent}/{n_chunks} ({chunks_sent*_SPK_SEND_INTERVAL:.3f}s) — interrupted")
                    return
                chunk = audio_bytes[i : i + SPK_CHUNK]
                self._spk_sock.sendto(chunk, (self.esp32_ip, self.speaker_port))
                chunks_sent += 1
                await asyncio.sleep(_SPK_SEND_INTERVAL)
            elapsed = time.monotonic() - t_start
            self._log("SPK-PLAY", f"DONE {chunks_sent} chunks in {elapsed:.3f}s (expected {duration_s:.3f}s)")
            self._spk_frames_played += 1
        finally:
            self._playing = False
            self._spk_stop_time = time.monotonic()
            self._log("SPK-PLAY", f"_playing=False, cooldown={self._spk_cooldown:.3f}s starts now")

    async def _speaker_worker(self) -> None:
        self._log("SPK-WORK", "Speaker worker started")
        while True:
            pcm = await self._spk_queue.get()
            if self._interrupted.is_set():
                self._log("SPK-WORK", f"Got chunk but interrupted — discarding {len(pcm)}B + flushing queue")
                self._spk_frames_dropped += 1
                self._flush_spk_queue()
                continue
            self._log("SPK-WORK", f"Dequeued {len(pcm)}B | queue_remaining={self._spk_queue.qsize()} interrupted={self._interrupted.is_set()} playing={self._playing}")
            try:
                await self._play_speaker_audio(pcm)
            except asyncio.CancelledError:
                self._log("SPK-WORK", "Cancelled")
                break
            except Exception as e:
                self._log("SPK-WORK", f"Playback error: {e}")

    # ── Message receiver: WebSocket → decode + route ──────────────────────────

    async def _receive(self, ws) -> None:
        async for raw in ws:
            if isinstance(raw, bytes):
                self._spk_frames_received += 1
                peak = self._audio_level(raw[:min(len(raw), 200)])
                if self._interrupted.is_set():
                    self._spk_frames_dropped += 1
                    self._log("WS-RX", f"Binary {len(raw)}B peak={peak} DROPPED (interrupted) | recv={self._spk_frames_received} drop={self._spk_frames_dropped}")
                    continue
                self._spk_queue.put_nowait(raw)
                self._log("WS-RX", f"Binary {len(raw)}B peak={peak} → queue (depth={self._spk_queue.qsize()}) | recv={self._spk_frames_received} playing={self._playing} state={self._agent_state!r}")
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type not in ("auth_response", "client_status_update", "ping"):
                self._log("RECV", f"← {msg_type} | {json.dumps({k: v for k, v in msg.items() if k != 'type'})}")

            if msg_type == "mic_floor":
                event  = msg.get("event", "")
                holder = msg.get("holder", "?")
                self._log("MIC", f"Floor event={event!r} holder={holder!r} granted_state={self._mic_granted.is_set()}")
                if event == "granted":
                    self._mic_granted.set()
                    self._log("MIC", "Floor GRANTED ✔ — mic stream will begin")
                elif event == "denied":
                    self._mic_granted.clear()
                    self._log("MIC", f"Floor DENIED — {holder} is currently streaming.")
                elif event == "acquired":
                    if holder == "glasses":
                        self._mic_granted.set()
                        self._log("MIC", "Floor acquired broadcast (us) — confirmed granted")
                    else:
                        self._mic_granted.clear()
                        self._log("MIC", f"Floor taken by {holder} — we must wait")
                elif event in ("released", "busy"):
                    if event == "released":
                        self._log("MIC", f"Floor released by {holder} — re-acquiring...")
                        await ws.send(json.dumps({"type": "mic_acquire"}))
                else:
                    self._log("MIC", f"Unknown mic_floor event: {event!r}")

            elif msg_type == "transcription":
                direction = msg.get("direction", "")
                text      = msg.get("text", "")
                finished  = msg.get("finished", False)
                if text.strip():
                    if direction == "input":
                        tag = "YOU →" if finished else "YOU .."
                    else:
                        tag = "AGENT ←" if finished else "AGENT .."
                    self._log(tag, text)

            elif msg_type == "response":
                text = msg.get("data", "")
                if text:
                    self._log("AGENT", text)

            elif msg_type == "status":
                state      = msg.get("state", "")
                detail     = msg.get("detail", "")
                prev_state = self._agent_state
                self._agent_state = state

                if state == "listening" and prev_state != "listening":
                    self._log("INTERRUPT", f"State → listening (was {prev_state!r}, detail={detail!r}) — flushing audio | playing={self._playing} queue={self._spk_queue.qsize()}")
                    self._interrupted.set()
                    self._flush_spk_queue()
                    silence = b"\x00" * SPK_CHUNK
                    self._spk_sock.sendto(silence, (self.esp32_ip, self.speaker_port))
                    self._log("INTERRUPT", f"Sent {SPK_CHUNK}B silence to ESP32 | _interrupted={self._interrupted.is_set()} _playing={self._playing}")
                elif state == "processing":
                    self._interrupted.clear()
                    self._log("...", "Thinking...")
                elif state == "idle":
                    self._interrupted.clear()
                elif state == "listening":
                    self._log("...", "Listening...")

            elif msg_type == "tool_call":
                if msg.get("status") == "started":
                    self._log("TOOL", f"{msg.get('tool_name', '?')} started")

            elif msg_type == "tool_response":
                tool    = msg.get("tool_name", "?")
                success = msg.get("success", True)
                self._log("TOOL", f"{tool} {'✓' if success else '✗'}")

            elif msg_type == "image_response":
                desc = msg.get("description", "(image)")
                self._log("IMAGE", desc)

            elif msg_type == "error":
                self._log("ERROR", f"{msg.get('code', '')}: {msg.get('description', '')}")

            elif msg_type == "session_suggestion":
                self._log("SESSION", f"Also online: {', '.join(msg.get('available_clients', []))}")

    # ── Camera task ───────────────────────────────────────────────────────────

    async def _fetch_jpeg(self) -> bytes:
        """Fetch one JPEG frame from ESP32-CAM HTTP endpoint (runs in thread)."""
        def _fetch() -> bytes:
            req = urllib.request.Request(self.cam_url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.read()
        return await asyncio.to_thread(_fetch)

    async def _send_camera_frames(self, ws) -> None:
        """Continuously fetch and forward camera frames as base64 JPEG image messages."""
        interval = 1.0 / self.cam_fps
        self._log("CAM", f"Enabled: url={self.cam_url} fps={self.cam_fps:.2f}")

        while self._running:
            t0 = time.monotonic()
            try:
                jpg = await self._fetch_jpeg()
                if not jpg:
                    raise RuntimeError("empty camera frame")
                payload = {
                    "type": "image",
                    "data_base64": base64.b64encode(jpg).decode("ascii"),
                    "mime_type": "image/jpeg",
                }
                await ws.send(json.dumps(payload))
                self._cam_sent += 1
                if self._cam_sent % 5 == 1:
                    self._log("CAM-TX", f"Sent frame #{self._cam_sent} jpeg={len(jpg)}B b64={len(payload['data_base64'])}B")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._cam_fail += 1
                self._log("CAM-ERR", f"Frame fetch/send failed ({self._cam_fail}): {e}")

            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, interval - elapsed))

        self._log("CAM", f"Stopped. sent={self._cam_sent} failed={self._cam_fail}")

    # ── Main session ──────────────────────────────────────────────────────────

    async def _run_session(self, conn_task: asyncio.Task | None = None) -> None:
        """Single session: auth -> run mic/recv/speaker/(camera) concurrently."""
        uri = f"{self.server}/ws/live"
        self._log("WS", f"Connecting to {uri}")
        self._interrupted.clear()
        self._agent_state = ""

        async with websockets.connect(
            uri,
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=10,
        ) as ws:
            ok = await self._authenticate(ws)
            if not ok:
                return

            if conn_task and not conn_task.done():
                conn_task.cancel()
                await asyncio.gather(conn_task, return_exceptions=True)
            await self._speak("Connected successfully")

            print("\n" + "=" * 56)
            print("  ESP32 Audio + Camera Bridge Active")
            print(f"  Mic UDP   : 0.0.0.0:{self.mic_port}")
            print(f"  Speaker   : {self.esp32_ip}:{self.speaker_port}")
            if self.cam_enabled:
                print(f"  Camera URL: {self.cam_url} @ {self.cam_fps:.2f} FPS")
            else:
                print("  Camera    : disabled")
            print("  Press Ctrl+C to stop")
            print("=" * 56 + "\n")

            spk_task = asyncio.create_task(self._speaker_worker(), name="spk")
            task_list = [
                asyncio.create_task(self._send_mic_audio(ws), name="mic"),
                asyncio.create_task(self._receive(ws), name="recv"),
            ]
            if self.cam_enabled:
                task_list.append(asyncio.create_task(self._send_camera_frames(ws), name="cam"))

            pending: list[asyncio.Task] = []
            try:
                done, pending = await asyncio.wait(task_list, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    exc = t.exception()
                    if exc:
                        self._log("TASK", f"{t.get_name()} ended with: {type(exc).__name__}: {exc}")
                    else:
                        self._log("TASK", f"{t.get_name()} completed")
            finally:
                spk_task.cancel()
                await self._release_mic(ws)

            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    # ── Reconnect loop ────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Connect and reconnect automatically on errors."""
        self._running = True
        delay = RECONNECT_MIN_S

        print("=" * 56)
        print("  Omni Hub ESP32 Audio + Camera Bridge")
        print(f"  Backend : {self.server}")
        print(f"  ESP32   : {self.esp32_ip}")
        if self.cam_enabled:
            print(f"  Camera  : {self.cam_url} @ {self.cam_fps:.2f} FPS")
        else:
            print("  Camera  : disabled")
        print("=" * 56)

        while self._running:
            self._was_connected = False
            conn_task = asyncio.create_task(self._announce_connecting())
            try:
                await self._run_session(conn_task)
                delay = RECONNECT_MIN_S
            except websockets.exceptions.ConnectionClosed as e:
                self._log("WS", f"Connection closed ({e.code})")
            except OSError as e:
                self._log("WS", f"Network error: {e}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                self._log("WS", f"Unexpected error: {type(e).__name__}: {e}")
            finally:
                if not conn_task.done():
                    conn_task.cancel()
                await asyncio.gather(conn_task, return_exceptions=True)

            if self._running:
                if self._was_connected:
                    await self._speak("Disconnected")
                self._log("WS", f"Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_S)

        self._log("SYS", "Stopped.")

    def stop(self) -> None:
        self._running = False
        self._mic_sock.close()
        self._spk_sock.close()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ESP32 Audio+Camera bridge")
    p.add_argument("--token", help="Firebase ID token")
    p.add_argument("--token-file", help="Path to token file")
    p.add_argument("--server", default=BACKEND_WS, help=f"Backend WS base URL (default: {BACKEND_WS})")
    p.add_argument("--esp32-ip", default=ESP32_IP, help=f"ESP32 IP (default: {ESP32_IP})")
    p.add_argument("--mic-port", type=int, default=MIC_PORT, help=f"Mic UDP port (default: {MIC_PORT})")
    p.add_argument("--speaker-port", type=int, default=SPEAKER_PORT, help=f"Speaker UDP port (default: {SPEAKER_PORT})")

    p.add_argument(
        "--cam-url",
        default="",
        help="ESP32-CAM snapshot URL (default: http://<esp32-ip>/capture)",
    )
    p.add_argument("--cam-fps", type=float, default=1.0, help="Camera send FPS (default: 1.0)")
    p.add_argument("--no-cam", action="store_true", help="Disable camera streaming")
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()

    token = args.token
    if not token and args.token_file:
        with open(args.token_file, encoding="utf-8") as f:
            token = f.read().strip()
    if not token:
        token = os.environ.get("OMNI_TOKEN", "")
    if not token:
        print("[AUTH] No token provided — signing in with embedded credentials...")
        try:
            token = _get_firebase_token(_FIREBASE_EMAIL, _FIREBASE_PASSWORD, _FIREBASE_API_KEY)
            print(f"[AUTH] Signed in as {_FIREBASE_EMAIL}")
        except Exception as e:
            print(f"[AUTH] Sign-in failed: {e}")
            sys.exit(1)

    cam_url = args.cam_url.strip() or f"http://{args.esp32_ip}/capture"
    bridge = ESP32UDPCamBridge(
        token=token,
        server=args.server,
        esp32_ip=args.esp32_ip,
        mic_port=args.mic_port,
        speaker_port=args.speaker_port,
        cam_url=cam_url,
        cam_fps=args.cam_fps,
        cam_enabled=not args.no_cam,
    )

    try:
        await bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()


if __name__ == "__main__":
    asyncio.run(async_main())
