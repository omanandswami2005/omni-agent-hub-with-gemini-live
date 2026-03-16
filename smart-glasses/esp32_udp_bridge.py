#!/usr/bin/env python3
"""ESP32 UDP Bridge — Omni Hub Backend Client.

Bridges a UDP-based ESP32 mic/speaker setup to the Omni Hub backend
via the /ws/live WebSocket protocol. Replaces the old STT→OpenAI→TTS
pipeline entirely — the backend handles all AI processing.

Architecture
------------
  ESP32 INMP441 mic  ──(UDP 4444)──► This script ──(WSS /ws/live)──► Omni Hub
  ESP32 I2S speaker  ◄──(UDP 5555)── This script ◄──(binary frames)── Omni Hub

Audio format
------------
  Input  (ESP32 → backend): 16kHz, 16-bit signed, mono, little-endian PCM
  Output (backend → ESP32): 24kHz from server, resampled to 16kHz 16-bit mono PCM

Usage
-----
    pip install websockets

    # Get a Firebase token first:
    #   Option A — from the dashboard (browser console):
    #     firebase.auth().currentUser.getIdToken().then(console.log)
    #   Option B — save it to token.txt from backend/test_output/token.txt
    #   Option C — use get_test_token.py in backend/scripts/

    # Run with a token string:
    python esp32_udp_bridge.py --token <firebase-jwt>

    # Run with a token file:
    python esp32_udp_bridge.py --token-file backend/test_output/token.txt

    # Custom ESP32 IP:
    python esp32_udp_bridge.py --token-file token.txt --esp32-ip 192.168.1.42

    # Local backend (development):
    python esp32_udp_bridge.py --token-file token.txt --server ws://localhost:8000

Configuration
-------------
  BACKEND_WS  = production WebSocket URL
  ESP32_IP    = IP of your ESP32 on the local network
  MIC_PORT    = UDP port this script listens on (ESP32 sends here)
  SPEAKER_PORT= UDP port ESP32 listens on (this script sends here)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import struct
import sys
import time

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

try:
    import urllib.request
except ImportError:
    pass  # stdlib — always available


# ─── Firebase credentials (embedded) ─────────────────────────────────────────

_FIREBASE_API_KEY = "AIzaSyC3a98P8sOUKEwGJuJWp2gA6i7o-CW21pE"
_FIREBASE_EMAIL   = "omanand@gmail.com"
_FIREBASE_PASSWORD = "123456"


def _get_firebase_token(email: str, password: str, api_key: str) -> str:
    """Sign in with Firebase email/password and return a fresh ID token.

    Uses the Firebase Auth REST API — no SDK required.
    Token is valid for 1 hour; call again to refresh.
    """
    import json as _json
    import urllib.request as _req
    import urllib.error as _err

    url  = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    body = _json.dumps({"email": email, "password": password,
                        "returnSecureToken": True}).encode()
    request = _req.Request(url, data=body,
                           headers={"Content-Type": "application/json"})
    try:
        with _req.urlopen(request, timeout=15) as resp:
            data = _json.loads(resp.read())
            return data["idToken"]
    except _err.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"Firebase sign-in failed ({e.code}): {body_text}") from e


# ─── Configuration ────────────────────────────────────────────────────────────

BACKEND_WS   = "wss://omni-backend-fcapusldtq-uc.a.run.app"

# ESP32 network config — update these to match your setup
ESP32_IP     = "192.168.0.101"   # ← change to your ESP32's IP address
MIC_PORT     = 4444              # UDP port: ESP32 sends mic audio here
SPEAKER_PORT = 5555              # UDP port: ESP32 listens for speaker audio here

# Audio parameters (must match ESP32 firmware)
INPUT_RATE   = 16000   # Hz — backend expects 16kHz PCM input
OUTPUT_RATE  = 24000   # Hz — backend sends 24kHz PCM output
ESP32_RATE   = 16000   # Hz — ESP32 I2S speaker expects 16kHz PCM
SAMPLE_WIDTH = 2       # bytes — 16-bit audio

# UDP chunk sizes
MIC_CHUNK    = 1024    # bytes to read per UDP recv call
SPK_CHUNK    = 2048    # bytes per UDP send to speaker

# Reconnect settings
RECONNECT_MIN_S = 3
RECONNECT_MAX_S = 30

# Exact playback pacing — must match ESP32 I2S buffer timing
# chunk_size=1024, bytes_per_sample=2, sample_rate=16000
# samples_per_chunk = 1024 // 2 = 512
# duration = 512 / 16000 = 0.032s
_SAMPLES_PER_CHUNK = SPK_CHUNK // SAMPLE_WIDTH   # 512
_SPK_SEND_INTERVAL = _SAMPLES_PER_CHUNK / ESP32_RATE  # 0.032s


def _resample_pcm(data: bytes, in_rate: int, out_rate: int) -> bytes:
    """Resample mono 16-bit PCM from in_rate to out_rate (pure stdlib).

    Uses linear interpolation — no numpy/audioop required.
    Good enough quality for voice audio.
    """
    if in_rate == out_rate:
        return data
    import struct
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

class ESP32UDPBridge:
    """Bridges UDP audio from an ESP32 to the Omni Hub /ws/live endpoint."""

    def __init__(self, token: str, server: str, esp32_ip: str,
                 mic_port: int, speaker_port: int):
        self.token = token
        self.server = server.rstrip("/")
        self.esp32_ip = esp32_ip
        self.mic_port = mic_port
        self.speaker_port = speaker_port

        self._running = False
        self._was_connected = False   # True once auth succeeds in current session

        # Mic UDP socket (this script listens here)
        self._mic_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._mic_sock.bind(("0.0.0.0", mic_port))
        self._mic_sock.setblocking(False)

        # Speaker UDP socket (this script sends to ESP32 here)
        self._spk_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Event set when server grants the mic floor — sendable only after this
        self._mic_granted = asyncio.Event()

        # Speaker audio queue — serialises playback so chunks never overlap
        self._spk_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Barge-in / interruption support
        self._interrupted = asyncio.Event()   # set when server signals interruption
        self._playing = False                 # True while ANY chunk is being sent (chunk-level)
        self._queue_has_audio = False         # True while queue has pending chunks OR chunk playing
        self._agent_state = ""                # track to detect state transitions (like React dashboard)

        # Post-playback cooldown — keep mic muted briefly after speaker stops
        # so ESP32 I2S DMA buffer drains and mic doesn't pick up the tail
        self._spk_stop_time = 0.0             # monotonic time when ALL speaker audio stopped
        _SPK_COOLDOWN_S = 0.35                # 350ms cooldown — increased to cover ESP32 I2S DMA drain
        self._spk_cooldown = _SPK_COOLDOWN_S

        # Counters for periodic mic logging
        self._mic_sent = 0
        self._mic_dropped_playing = 0
        self._mic_dropped_cooldown = 0
        self._mic_log_interval = 50           # log every N frames

        # Speaker frame counter
        self._spk_frames_received = 0
        self._spk_frames_played = 0
        self._spk_frames_dropped = 0

    def _log(self, tag: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime())
        ms = f"{time.time() % 1:.3f}"[1:]  # .XXX
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
        """Generate TTS with edge_tts and send raw PCM to ESP32 speaker.

        Decodes MP3 via ffmpeg and resamples to ESP32_RATE (16kHz).
        """
        try:
            communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
            mp3_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_bytes += chunk["data"]
            if not mp3_bytes:
                return
            # Decode MP3 → ESP32_RATE 16-bit mono PCM via ffmpeg
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
        """Repeatedly say 'Connecting' until auth succeeds."""
        while not self._was_connected:
            await self._speak("Connecting")
            if not self._was_connected:
                await asyncio.sleep(0.3)

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def _authenticate(self, ws) -> bool:
        """Send auth handshake and wait for ok response."""
        auth_msg = {
            "type": "auth",
            "token": self.token,
            "client_type": "glasses",
            "user_agent": "ESP32-UDPBridge/1.0 (Smart Glasses)",
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
            uid = resp.get("user_id", "?")
            others = resp.get("other_clients_online", [])
            self._log("AUTH", f"OK — user={uid}")
            if others:
                self._log("AUTH", f"Other devices online: {', '.join(others)}")
            self._was_connected = True
        return True

    # ── Mic floor ─────────────────────────────────────────────────────────────

    async def _acquire_mic(self, ws) -> None:
        """Request the mic floor before streaming audio."""
        self._mic_granted.clear()
        await ws.send(json.dumps({"type": "mic_acquire"}))
        self._log("MIC", "Requested mic floor — waiting for grant...")

    async def _release_mic(self, ws) -> None:
        """Release the mic floor."""
        self._mic_granted.clear()
        try:
            await ws.send(json.dumps({"type": "mic_release"}))
        except Exception:
            pass
        self._log("MIC", "Mic floor released")

    # ── Mic task: UDP → WebSocket ─────────────────────────────────────────────

    async def _send_mic_audio(self, ws) -> None:
        """Request mic floor, then forward UDP PCM frames to the backend WebSocket.

        IMPORTANT: This task calls _acquire_mic internally so that _receive is
        already running concurrently when the request is sent — otherwise the
        server's 'granted' response would arrive with nobody listening.
        """
        loop = asyncio.get_event_loop()

        self._log("MIC", f"Listening on UDP 0.0.0.0:{self.mic_port}")

        # Yield once so _receive task gets scheduled before we send mic_acquire
        await asyncio.sleep(0)
        await self._acquire_mic(ws)

        # Wait for the server's grant response.
        # If neither 'granted' nor 'acquired' (holder=glasses) arrive within 3 s,
        # proceed anyway — the first binary frame triggers the server's auto-acquire
        # fallback path, which sends an 'acquired' broadcast that _receive will catch.
        _GRANT_TIMEOUT_S = 3.0
        _loop_start = loop.time()
        while not self._mic_granted.is_set():
            elapsed = loop.time() - _loop_start
            if elapsed >= _GRANT_TIMEOUT_S:
                self._log("MIC", f"No grant received in {_GRANT_TIMEOUT_S:.0f}s — proceeding (auto-acquire on first frame)")
                self._mic_granted.set()   # optimistic — server will auto-grant on first binary
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
                now = time.monotonic()
                # ── Half-duplex: mute mic while speaker has ANY audio ──────
                # Use _queue_has_audio (not _playing) so mic stays muted between
                # consecutive chunks — _playing briefly resets to False between each
                # buffer in the queue, which was the main echo source.
                if self._queue_has_audio:
                    self._mic_dropped_playing += 1
                    total_dropped = self._mic_dropped_playing + self._mic_dropped_cooldown
                    if total_dropped % self._mic_log_interval == 1:
                        lvl = self._audio_level(data)
                        self._log("MIC-DROP", f"Dropped (playing) peak={lvl} sent={self._mic_sent} drop_play={self._mic_dropped_playing} drop_cool={self._mic_dropped_cooldown}")
                    continue
                # ── Post-playback cooldown: ESP32 I2S DMA still draining ──
                elapsed_since_stop = now - self._spk_stop_time
                if elapsed_since_stop < self._spk_cooldown:
                    self._mic_dropped_cooldown += 1
                    total_dropped = self._mic_dropped_playing + self._mic_dropped_cooldown
                    if total_dropped % self._mic_log_interval == 1:
                        lvl = self._audio_level(data)
                        self._log("MIC-DROP", f"Dropped (cooldown {elapsed_since_stop:.3f}s/{self._spk_cooldown:.3f}s) peak={lvl}")
                    continue
                # ── Send mic audio to backend ──────────────────────────────
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

    # ── Speaker task: WebSocket → UDP ────────────────────────────────────────

    def _flush_spk_queue(self) -> None:
        """Drain and discard all pending speaker audio (barge-in / interruption)."""
        flushed = 0
        flushed_bytes = 0
        while not self._spk_queue.empty():
            try:
                chunk = self._spk_queue.get_nowait()
                flushed += 1
                flushed_bytes += len(chunk)
                self._spk_frames_dropped += 1
            except asyncio.QueueEmpty:
                break
        self._queue_has_audio = False
        if flushed:
            self._log("SPK-FLUSH", f"Flushed {flushed} chunks ({flushed_bytes}B) | total_recv={self._spk_frames_received} played={self._spk_frames_played} dropped={self._spk_frames_dropped}")

    async def _play_speaker_audio(self, audio_bytes: bytes) -> None:
        """Resample to 16kHz 16-bit mono PCM and send chunked UDP to ESP32 speaker.

        Uses exact timing from reference send_audio_to_esp32():
          chunk_size = 1024, sample_rate = 16000, bytes_per_sample = 2
          duration = (chunk_size // bytes_per_sample) / sample_rate = 0.032s

        NOTE: does NOT reset _playing/_spk_stop_time on exit — _speaker_worker
        does that after the full queue is drained, so mic stays muted between
        consecutive chunks.
        """
        raw_len = len(audio_bytes)
        # Backend sends 24kHz; ESP32 I2S expects 16kHz — always resample
        if OUTPUT_RATE != ESP32_RATE:
            audio_bytes = _resample_pcm(audio_bytes, OUTPUT_RATE, ESP32_RATE)
        n_chunks = (len(audio_bytes) + SPK_CHUNK - 1) // SPK_CHUNK
        duration_s = len(audio_bytes) / (ESP32_RATE * SAMPLE_WIDTH)
        peak = self._audio_level(audio_bytes[:SPK_CHUNK]) if audio_bytes else 0
        self._log("SPK-PLAY", f"START raw={raw_len}B resampled={len(audio_bytes)}B chunks={n_chunks} duration={duration_s:.3f}s peak={peak} queue_depth={self._spk_queue.qsize()}")
        self._playing = True
        chunks_sent = 0
        t_start = time.monotonic()
        try:
            for i in range(0, len(audio_bytes), SPK_CHUNK):
                # Check for barge-in between every chunk
                if self._interrupted.is_set():
                    self._log("SPK-PLAY", f"CUT at chunk {chunks_sent}/{n_chunks} ({chunks_sent*_SPK_SEND_INTERVAL:.3f}s) — interrupted")
                    return
                chunk = audio_bytes[i : i + SPK_CHUNK]
                self._spk_sock.sendto(chunk, (self.esp32_ip, self.speaker_port))
                chunks_sent += 1
                # EXACT playback timing: 512 samples / 16000 Hz = 0.032s
                await asyncio.sleep(_SPK_SEND_INTERVAL)
            elapsed = time.monotonic() - t_start
            self._log("SPK-PLAY", f"DONE {chunks_sent} chunks in {elapsed:.3f}s (expected {duration_s:.3f}s)")
            self._spk_frames_played += 1
        finally:
            # Only reset _playing here (chunk-level flag); _queue_has_audio and
            # _spk_stop_time are managed by _speaker_worker after the full queue drains.
            self._playing = False

    async def _speaker_worker(self) -> None:
        """Drain speaker queue one buffer at a time — stops immediately on interruption."""
        self._log("SPK-WORK", "Speaker worker started")
        while True:
            pcm = await self._spk_queue.get()
            # If interrupted while waiting, discard this chunk and anything queued
            if self._interrupted.is_set():
                self._log("SPK-WORK", f"Got chunk but interrupted — discarding {len(pcm)}B + flushing queue")
                self._spk_frames_dropped += 1
                self._flush_spk_queue()
                self._queue_has_audio = False
                self._spk_stop_time = time.monotonic()
                continue
            # Mark that audio is in flight (queue-level flag — mic stays muted until
            # this goes False, even between consecutive chunks)
            self._queue_has_audio = True
            self._log("SPK-WORK", f"Dequeued {len(pcm)}B | queue_remaining={self._spk_queue.qsize()} interrupted={self._interrupted.is_set()} playing={self._playing}")
            try:
                await self._play_speaker_audio(pcm)
            except asyncio.CancelledError:
                self._log("SPK-WORK", "Cancelled")
                self._queue_has_audio = False
                self._spk_stop_time = time.monotonic()
                break
            except Exception as e:
                self._log("SPK-WORK", f"Playback error: {e}")
            # Only clear _queue_has_audio when the queue is fully drained
            if self._spk_queue.empty():
                self._queue_has_audio = False
                self._spk_stop_time = time.monotonic()
                self._log("SPK-PLAY", f"_queue_has_audio=False, cooldown={self._spk_cooldown:.3f}s starts now")

    # ── Message receiver: WebSocket → decode + route ──────────────────────────

    async def _receive(self, ws) -> None:
        """Handle all messages from the backend."""
        try:
            async for raw in ws:
                # ── Binary frame = agent voice audio ──────────────────────────────
                if isinstance(raw, bytes):
                    self._spk_frames_received += 1
                    peak = self._audio_level(raw[:min(len(raw), 200)])
                    # If interrupted, drop incoming audio frames entirely
                    if self._interrupted.is_set():
                        self._spk_frames_dropped += 1
                        self._log("WS-RX", f"Binary {len(raw)}B peak={peak} DROPPED (interrupted) | recv={self._spk_frames_received} drop={self._spk_frames_dropped}")
                        continue
                    self._spk_queue.put_nowait(raw)
                    self._log("WS-RX", f"Binary {len(raw)}B peak={peak} → queue (depth={self._spk_queue.qsize()}) | recv={self._spk_frames_received} playing={self._playing} state={self._agent_state!r}")
                    continue

                # ── JSON control frame ────────────────────────────────────────────
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                # Log every received control message for diagnostics
                if msg_type not in ("auth_response", "client_status_update", "ping"):
                    self._log("RECV", f"← {msg_type} | {json.dumps({k: v for k, v in msg.items() if k != 'type'})}")

                if msg_type == "mic_floor":
                    event = msg.get("event", "")
                    holder = msg.get("holder", "?")
                    self._log("MIC", f"Floor event={event!r} holder={holder!r} granted_state={self._mic_granted.is_set()}")
                    if event == "granted":
                        self._mic_granted.set()
                        self._log("MIC", "Floor GRANTED ✔ — mic stream will begin")
                    elif event == "denied":
                        self._mic_granted.clear()
                        self._log("MIC", f"Floor DENIED — {holder} is currently streaming. Will retry when released.")
                    elif event == "acquired":
                        # Broadcast: another device just started streaming
                        if holder == "glasses":   # it's us — treat as a grant confirmation
                            self._mic_granted.set()
                            self._log("MIC", "Floor acquired broadcast (us) — confirmed granted")
                        else:
                            self._mic_granted.clear()
                            self._log("MIC", f"Floor taken by {holder} — we must wait")
                    elif event in ("released", "busy"):
                        # Another device released — re-request if we want the floor
                        if event == "released":
                            self._log("MIC", f"Floor released by {holder} — re-acquiring...")
                            await ws.send(json.dumps({"type": "mic_acquire"}))
                    else:
                        self._log("MIC", f"Unknown mic_floor event: {event!r} | full msg: {msg}")

                elif msg_type == "transcription":
                    direction = msg.get("direction", "")
                    text = msg.get("text", "")
                    finished = msg.get("finished", False)
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
                    state = msg.get("state", "")
                    detail = msg.get("detail", "")
                    prev_state = self._agent_state
                    self._agent_state = state

                    # ── Mirrors React dashboard useAudioPlayback ──────────────
                    # Dashboard flushes audio on ANY transition to 'listening',
                    # not just when detail contains 'interrupt'.
                    if state == "listening" and prev_state != "listening":
                        self._log("INTERRUPT", f"State → listening (was {prev_state!r}, detail={detail!r}) — flushing audio | playing={self._playing} queue={self._spk_queue.qsize()}")
                        self._interrupted.set()
                        self._flush_spk_queue()
                        # Send silence to flush ESP32 I2S DMA buffer immediately
                        silence = b"\x00" * SPK_CHUNK
                        self._spk_sock.sendto(silence, (self.esp32_ip, self.speaker_port))
                        self._log("INTERRUPT", f"Sent {SPK_CHUNK}B silence to ESP32 | _interrupted={self._interrupted.is_set()} _playing={self._playing}")
                    elif state == "processing":
                        # Agent starts generating → clear interrupted flag so new audio plays
                        self._interrupted.clear()
                        self._log("...", "Thinking...")
                    elif state == "idle":
                        # Turn complete — but only clear interrupt if queue is fully drained.
                        # If we clear while chunks are still queued, mic opens mid-playback → echo.
                        if self._spk_queue.empty() and not self._queue_has_audio:
                            self._interrupted.clear()
                        else:
                            self._log("...", f"Idle but queue={self._spk_queue.qsize()} has_audio={self._queue_has_audio} — deferring interrupt clear")
                    elif state == "listening":
                        self._log("...", "Listening...")

                elif msg_type == "tool_call":
                    if msg.get("status") == "started":
                        self._log("TOOL", f"{msg.get('tool_name', '?')} started")

                elif msg_type == "tool_response":
                    tool = msg.get("tool_name", "?")
                    success = msg.get("success", True)
                    self._log("TOOL", f"{tool} {'✓' if success else '✗'}")

                elif msg_type == "image_response":
                    desc = msg.get("description", "(image)")
                    self._log("IMAGE", desc)

                elif msg_type == "error":
                    code = msg.get("code", "")
                    desc = msg.get("description", "")
                    self._log("ERROR", f"{code}: {desc}")

                elif msg_type == "session_suggestion":
                    clients = msg.get("available_clients", [])
                    self._log("SESSION", f"Also online: {', '.join(clients)}")

                # auth_response, client_status_update, ping → silent
        except websockets.exceptions.ConnectionClosed as e:
            self._log("WS-RX", f"Connection closed: code={e.code} reason={e.reason}")
        except Exception as e:
            self._log("WS-RX", f"Receive error: {type(e).__name__}: {e}")

    # ── Main session ──────────────────────────────────────────────────────────

    async def _run_session(self, conn_task: asyncio.Task | None = None) -> None:
        """Single WebSocket session: auth → acquire mic → stream bidirectionally."""
        uri = f"{self.server}/ws/live"
        self._log("WS", f"Connecting to {uri}")
        self._interrupted.clear()   # fresh session — no stale interrupt state
        self._agent_state = ""      # reset state tracking

        async with websockets.connect(
            uri,
            max_size=4 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=10,
        ) as ws:
            # Phase 1: auth
            ok = await self._authenticate(ws)
            if not ok:
                return

            # Stop connecting loop — cancel TTS announcement immediately
            if conn_task and not conn_task.done():
                conn_task.cancel()
                await asyncio.gather(conn_task, return_exceptions=True)

            # NOTE: _acquire_mic is now called from inside _send_mic_audio
            # so _receive is already running when the request is sent.
            print("\n" + "=" * 48)
            print("  ESP32 Bridge Active")
            print(f"  Mic UDP  : 0.0.0.0:{self.mic_port}")
            print(f"  Speaker  : {self.esp32_ip}:{self.speaker_port}")
            print("  Press Ctrl+C to stop")
            print("=" * 48 + "\n")

            # Phase 3: run mic sender + message receiver + speaker worker concurrently.
            # Schedule TTS announcement as a background task AFTER receiver is running
            # so the backend never sees an idle WebSocket during audio generation.
            spk_task = asyncio.create_task(self._speaker_worker(), name="spk")
            announce_task = asyncio.create_task(
                self._speak("Connected successfully"), name="announce"
            )
            try:
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._send_mic_audio(ws), name="mic"),
                        asyncio.create_task(self._receive(ws), name="recv"),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                spk_task.cancel()
                announce_task.cancel()
                await self._release_mic(ws)

            for t in pending:
                t.cancel()
            # Retrieve exceptions from ALL tasks to suppress "never retrieved" warning
            await asyncio.gather(*done, *pending, return_exceptions=True)

    # ── Reconnect loop ────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Connect and reconnect automatically on errors."""
        self._running = True
        delay = RECONNECT_MIN_S

        print("=" * 48)
        print("  Omni Hub ESP32 UDP Bridge")
        print(f"  Backend : {self.server}")
        print(f"  ESP32   : {self.esp32_ip}")
        print("=" * 48)

        while self._running:
            self._was_connected = False
            conn_task = asyncio.create_task(self._announce_connecting())
            try:
                await self._run_session(conn_task)
                delay = RECONNECT_MIN_S          # reset on clean disconnect
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
    p = argparse.ArgumentParser(
        description="ESP32 UDP ↔ Omni Hub WebSocket bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Getting a Firebase token
------------------------
  Option A — from the web dashboard (browser console):
      firebase.auth().currentUser.getIdToken().then(t => console.log(t))

  Option B — from token file (if already saved):
      python esp32_udp_bridge.py --token-file backend/test_output/token.txt

  Option C — generate via script:
      python backend/scripts/get_test_token.py --api-key <WEB_API_KEY> \\
              --email you@example.com --password yourpass

Examples
--------
  python esp32_udp_bridge.py --token <jwt> --esp32-ip 192.168.1.42
  python esp32_udp_bridge.py --token-file token.txt
  python esp32_udp_bridge.py --token-file token.txt --server ws://localhost:8000
        """,
    )
    p.add_argument("--token", help="Firebase ID token (JWT string)")
    p.add_argument("--token-file", help="Path to file containing the Firebase ID token")
    p.add_argument(
        "--server",
        default=BACKEND_WS,
        help=f"Backend WebSocket base URL (default: {BACKEND_WS})",
    )
    p.add_argument(
        "--esp32-ip",
        default=ESP32_IP,
        help=f"ESP32 IP address (default: {ESP32_IP})",
    )
    p.add_argument(
        "--mic-port",
        type=int,
        default=MIC_PORT,
        help=f"UDP port to receive ESP32 mic audio (default: {MIC_PORT})",
    )
    p.add_argument(
        "--speaker-port",
        type=int,
        default=SPEAKER_PORT,
        help=f"UDP port to send speaker audio to ESP32 (default: {SPEAKER_PORT})",
    )
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()

    # Resolve Firebase token — priority: --token > --token-file > OMNI_TOKEN > embedded creds
    token = args.token
    if not token and args.token_file:
        with open(args.token_file) as f:
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

    bridge = ESP32UDPBridge(
        token=token,
        server=args.server,
        esp32_ip=args.esp32_ip,
        mic_port=args.mic_port,
        speaker_port=args.speaker_port,
    )

    try:
        await bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()


if __name__ == "__main__":
    asyncio.run(async_main())