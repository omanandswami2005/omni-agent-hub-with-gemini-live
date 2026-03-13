# gemini_cam_narrator.py
# ESP32-CAM → Gemini Live → Speaks what it sees (no mic needed)

import asyncio, os
import aiohttp, pyaudio
from google import genai
from google.genai import types

# ─── CONFIG ──────────────────────────────────────────────────────────
GOOGLE_API_KEY    = os.environ.get("GOOGLE_API_KEY", "api-key")
ESP32_CAM_IP      = "192.168.xx.xxx"           # ← your ESP32 IP
SNAPSHOT_URL      = f"http://{ESP32_CAM_IP}/snapshot"
SNAPSHOT_INTERVAL = 5.0    # seconds between frames

FORMAT   = pyaudio.paInt16
CHANNELS = 1
SPK_RATE = 24000
CHUNK    = 4096

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

# ✅ This prompt drives everything — Gemini narrates continuously
SYSTEM_PROMPT = """
You are a live visual narrator. You are receiving a continuous stream of 
camera images. Your job is to speak out loud what you observe in each frame.

Rules:
- Describe what you see in every new frame in 1-3 sentences
- Mention changes between frames (movement, new objects, lighting changes)
- Speak naturally like a documentary narrator
- If nothing has changed, say something interesting about what you still see
- Never say "I cannot" or "I don't have audio" — just narrate what you see
- Always respond with spoken audio
"""

CONFIG = {
    "response_modalities": ["AUDIO"],
    "output_audio_transcription": {},   # print what Gemini says
    "system_instruction": SYSTEM_PROMPT,
    "speech_config": {
        "voice_config": {
            "prebuilt_voice_config": {"voice_name": "Charon"}  # deep narrator voice
        }
    },
}

pya    = pyaudio.PyAudio()
client = genai.Client(api_key=GOOGLE_API_KEY)
spk_queue = asyncio.Queue()

# ─── SPEAKER ─────────────────────────────────────────────────────────
async def play_speaker():
    stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT, channels=CHANNELS,
        rate=SPK_RATE, output=True,
        frames_per_buffer=CHUNK,
    )
    print("[SPK] ✓ Speaker ready\n")
    try:
        while True:
            data = await spk_queue.get()
            await asyncio.to_thread(stream.write, data)
    finally:
        stream.stop_stream(); stream.close()

# ─── CAMERA ──────────────────────────────────────────────────────────
async def fetch_frame(session):
    try:
        async with session.get(
            SNAPSHOT_URL, timeout=aiohttp.ClientTimeout(total=3)
        ) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as e:
        print(f"[CAM] Error: {e}")
    return None

# ─── MAIN SESSION ────────────────────────────────────────────────────
async def gemini_session():
    async with aiohttp.ClientSession() as http:

        # Camera check
        frame = await fetch_frame(http)
        if not frame:
            print("[CAM] ✗ Camera unreachable — check IP!"); return
        print(f"[CAM] ✓ Camera OK ({len(frame)//1024}KB)\n")

        reconnect_delay = 3
        while True:
            try:
                async with client.aio.live.connect(model=MODEL, config=CONFIG) as gs:
                    print("[GEMINI] ✓ Connected — starting narration...\n")
                    print("="*45)
                    print("  📷  Gemini is watching your camera feed")
                    print("  🔊  It will speak what it sees")
                    print("  Ctrl+C to stop")
                    print("="*45 + "\n")
                    reconnect_delay = 3

                    frame_count = 0

                    # ── Send frames + text prompt ─────────────────────
                    async def send_frames():
                        nonlocal frame_count
                        while True:
                            raw = await fetch_frame(http)
                            if raw:
                                frame_count += 1

                                # Send the image frame
                                await gs.send_realtime_input(
                                    video=types.Blob(
                                        data=raw,
                                        mime_type="image/jpeg"
                                    )
                                )

                                # ✅ Send a text prompt AFTER each frame
                                # This triggers Gemini to respond to what it sees
                                await gs.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[types.Part(
                                            text=f"Frame {frame_count}: Describe what you see now."
                                        )]
                                    ),
                                    turn_complete=True   # triggers response
                                )

                                print(f"[CAM] Frame {frame_count} sent ({len(raw)//1024}KB)")

                            await asyncio.sleep(SNAPSHOT_INTERVAL)

                    # ── Receive narration audio ───────────────────────
                    async def receive_responses():
                        async for msg in gs.receive():

                            # Audio → speaker
                            if msg.data:
                                await spk_queue.put(msg.data)

                            sc = msg.server_content
                            if sc:
                                # Audio in model_turn parts
                                if sc.model_turn:
                                    for part in (sc.model_turn.parts or []):
                                        if hasattr(part, 'inline_data') and part.inline_data:
                                            await spk_queue.put(part.inline_data.data)

                                # Print Gemini's narration text
                                if sc.output_transcription:
                                    t = sc.output_transcription.text
                                    if t.strip():
                                        print(f"[GEMINI]: {t}")

                                if sc.turn_complete:
                                    print()  # newline after each narration

                            if msg.text:
                                print(f"[GEMINI]: {msg.text}")

                    await asyncio.gather(
                        send_frames(),
                        receive_responses(),
                    )

            except Exception as e:
                print(f"\n[ERROR] {type(e).__name__}: {e}")
                print(f"[GEMINI] Reconnecting in {reconnect_delay}s...\n")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30)

# ─── MAIN ────────────────────────────────────────────────────────────
async def main():
    print("="*45)
    print("  ESP32-CAM Visual Narrator  (no mic)")
    print("="*45 + "\n")
    await asyncio.gather(
        play_speaker(),
        gemini_session(),
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED]")