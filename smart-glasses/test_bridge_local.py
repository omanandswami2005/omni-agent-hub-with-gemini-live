#!/usr/bin/env python3
"""Test the ESP32 bridge protocol against a local backend server.

Sends a text message via the WebSocket text-input path (not binary audio)
to verify the full pipeline without needing a real microphone.
"""

import asyncio
import json
import math
import struct
import time
import urllib.request

# Firebase auth
API_KEY = "AIzaSyC3a98P8sOUKEwGJuJWp2gA6i7o-CW21pE"
EMAIL = "omanand@gmail.com"
PASSWORD = "123456"

SERVER = "ws://127.0.0.1:8000"


def get_token():
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    body = json.dumps({"email": EMAIL, "password": PASSWORD, "returnSecureToken": True}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["idToken"]


def generate_speech_pcm(duration_s: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Generate a 300Hz sine wave at conversational volume (~-20dBFS).

    This simulates human speech loudness so Gemini detects audio activity.
    """
    n_samples = int(sample_rate * duration_s)
    amplitude = 4000  # ~-18dBFS — typical speech level
    freq = 300  # Hz — male fundamental frequency range
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        # Mix two frequencies to sound more speech-like
        val = amplitude * (0.7 * math.sin(2 * math.pi * freq * t) +
                           0.3 * math.sin(2 * math.pi * (freq * 2.5) * t))
        samples.append(max(-32768, min(32767, int(val))))
    return struct.pack(f"<{n_samples}h", *samples)


async def test():
    import websockets

    token = get_token()
    print(f"[OK] Token: {len(token)} chars")

    uri = f"{SERVER}/ws/live"
    print(f"[WS] Connecting to {uri}")

    async with websockets.connect(uri, max_size=4 * 1024 * 1024, ping_interval=20, ping_timeout=10) as ws:
        # Auth
        auth = {
            "type": "auth",
            "token": token,
            "client_type": "glasses",
            "user_agent": "ESP32-UDPBridge/1.0 (Smart Glasses)",
            "capabilities": ["microphone", "speaker"],
        }
        await ws.send(json.dumps(auth))
        print("[WS] Auth sent")

        msgs = []
        mic_sent = 0
        text_sent = False
        start = time.time()
        mic_granted = False
        got_audio_back = False
        got_status = False
        session_ready = False

        # Pre-generate speech audio (2 seconds of 300Hz tone, then silence)
        speech_pcm = generate_speech_pcm(2.0, 16000)
        silence_pcm = b"\x00" * 1024  # 512 samples of silence
        chunk_size = 1024  # 512 samples per chunk

        while time.time() - start < 60:
            # Receive
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                if isinstance(raw, bytes):
                    print(f"  [{len(msgs)+1}] AUDIO {len(raw)}B")
                    msgs.append(("audio", len(raw)))
                    got_audio_back = True
                else:
                    msg = json.loads(raw)
                    mt = msg.get("type", "")
                    summary = {k: v for k, v in msg.items() if k != "type"}
                    print(f"  [{len(msgs)+1}] {mt}: {json.dumps(summary)[:200]}")
                    msgs.append((mt, msg))

                    if mt == "auth_response" and msg.get("status") == "ok":
                        print("[OK] Auth OK — requesting mic floor")
                        await ws.send(json.dumps({"type": "mic_acquire"}))

                    if mt == "connected":
                        session_ready = True
                        print("[OK] Session ready")

                    if mt == "mic_floor" and msg.get("event") in ("granted", "acquired"):
                        mic_granted = True
                        print("[OK] Mic floor granted")

                    if mt == "status":
                        state = msg.get("state", "")
                        got_status = True
                        if state == "idle" and got_audio_back:
                            print("[OK] Got idle + audio back — full pipeline works!")
                            break

                    if mt == "transcription":
                        direction = msg.get("direction", "")
                        text = msg.get("text", "")
                        finished = msg.get("finished", False)
                        tag = "YOU" if direction == "input" else "AGENT"
                        done = "✓" if finished else "..."
                        print(f"  [{tag} {done}] {text}")

            except asyncio.TimeoutError:
                pass

            # Once mic floor is granted and session is ready, send a text message
            # This bypasses the need for actual speech detection
            if mic_granted and session_ready and not text_sent:
                elapsed = time.time() - start
                print(f"[TEXT] Sending text message ({elapsed:.1f}s elapsed)")
                await ws.send(json.dumps({
                    "type": "text",
                    "content": "Hello, say hi back in one short sentence."
                }))
                text_sent = True

            # Also send some speech-level audio frames so the session stays alive
            if mic_granted and mic_sent < 300:
                offset = mic_sent * chunk_size
                if offset < len(speech_pcm):
                    chunk = speech_pcm[offset:offset + chunk_size]
                else:
                    chunk = silence_pcm
                await ws.send(chunk)
                mic_sent += 1
                if mic_sent % 100 == 0:
                    elapsed = time.time() - start
                    print(f"[MIC] Sent {mic_sent} frames ({elapsed:.1f}s elapsed)")

            await asyncio.sleep(0.032)  # ~30fps like real mic

        print(f"\n{'='*50}")
        elapsed = time.time() - start
        print(f"[DONE] {len(msgs)} messages, {mic_sent} audio frames sent in {elapsed:.1f}s")
        types = [m[0] for m in msgs]
        audio_count = types.count("audio")
        print(f"[TYPES] {[t for t in types if t != 'audio']} + {audio_count} audio frames")
        if got_audio_back:
            print("[RESULT] PASS — got audio response from Gemini")
        elif got_status:
            print("[RESULT] PARTIAL — got status updates but no audio back")
        else:
            print("[RESULT] FAIL — no status or audio response")


if __name__ == "__main__":
    asyncio.run(test())
