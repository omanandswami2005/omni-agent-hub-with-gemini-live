#!/usr/bin/env python3
"""Interactive WebSocket test client for /ws/live endpoint.

Usage
-----
    # 1. Get a Firebase ID token (see --help for options)
    python scripts/test_ws_live.py --token <FIREBASE_ID_TOKEN>

    # 2. Or use a test token from the Firebase Auth Emulator
    python scripts/test_ws_live.py --token-from-env FIREBASE_TEST_TOKEN

    # 3. Text-only mode (no mic, just typed messages)
    python scripts/test_ws_live.py --token <TOKEN> --text-only

    # 4. With audio file playback (send a .wav/.pcm file)
    python scripts/test_ws_live.py --token <TOKEN> --audio-file test.pcm

    # 5. Skip auth (only works if backend auth is disabled)
    python scripts/test_ws_live.py --no-auth

Requires: websockets (already in project deps)
    pip install websockets  # if running outside venv
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import sys
import time
from pathlib import Path


async def main():
    parser = argparse.ArgumentParser(description="Test the /ws/live WebSocket endpoint")
    parser.add_argument("--url", default="ws://localhost:8000/ws/live", help="WebSocket URL")
    parser.add_argument("--token", help="Firebase ID token for auth")
    parser.add_argument("--token-from-env", metavar="VAR", help="Read token from env var")
    parser.add_argument("--no-auth", action="store_true", help="Skip auth handshake")
    parser.add_argument("--text-only", action="store_true", help="Text mode (no audio)")
    parser.add_argument("--audio-file", type=Path, help="Send a raw PCM file (16kHz 16-bit mono)")
    parser.add_argument("--chunk-ms", type=int, default=100, help="Audio chunk size in ms (default: 100)")
    parser.add_argument("--voice", default="Aoede", help="Voice name for RunConfig")
    parser.add_argument("--timeout", type=int, default=60, help="Max seconds to run (0=unlimited)")
    args = parser.parse_args()

    # Resolve token
    token = args.token
    if args.token_from_env:
        token = os.environ.get(args.token_from_env)
        if not token:
            print(f"ERROR: Environment variable {args.token_from_env} is not set")
            sys.exit(1)

    if not token and not args.no_auth:
        print("ERROR: --token, --token-from-env, or --no-auth is required")
        sys.exit(1)

    try:
        import websockets
    except ImportError:
        print("ERROR: websockets package not found. Run: pip install websockets")
        sys.exit(1)

    print(f"Connecting to {args.url} ...")
    async with websockets.connect(args.url) as ws:
        print("  Connected!")

        # Phase 1: Auth handshake
        if not args.no_auth:
            auth_msg = json.dumps({"type": "auth", "token": token})
            await ws.send(auth_msg)
            print("  Sent auth handshake, waiting for response...")

            response = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(response)
            print(f"  Auth response: {json.dumps(data, indent=2)}")

            if data.get("status") == "error":
                print(f"  Auth FAILED: {data.get('error')}")
                return

            # Read connected message
            response2 = await asyncio.wait_for(ws.recv(), timeout=5)
            data2 = json.loads(response2)
            print(f"  Connected message: {json.dumps(data2, indent=2)}")

        # Phase 2: Bidirectional streaming
        print("\n--- Streaming started ---")
        print("Commands: type a message and press Enter, or 'quit' to exit")
        if not args.text_only:
            print("Audio: binary PCM frames are printed as [AUDIO ...]")
        print()

        receiver_task = asyncio.create_task(_receive_loop(ws))
        sender_task = asyncio.create_task(
            _send_loop(ws, args.text_only, args.audio_file, args.chunk_ms)
        )

        tasks = {receiver_task, sender_task}
        if args.timeout > 0:
            timeout_task = asyncio.create_task(asyncio.sleep(args.timeout))
            tasks.add(timeout_task)

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        print("\n--- Session ended ---")


async def _receive_loop(ws):
    """Receive and display messages from the server."""
    audio_bytes_total = 0
    audio_chunks = 0
    try:
        async for msg in ws:
            if isinstance(msg, bytes):
                audio_bytes_total += len(msg)
                audio_chunks += 1
                if audio_chunks % 10 == 1:
                    print(f"  [AUDIO] chunk #{audio_chunks}, {len(msg)} bytes (total: {audio_bytes_total:,} bytes)")
            else:
                try:
                    data = json.loads(msg)
                    msg_type = data.get("type", "unknown")
                    if msg_type == "transcript":
                        direction = data.get("direction", "?")
                        text = data.get("text", "")
                        finished = data.get("finished", False)
                        marker = "FINAL" if finished else "partial"
                        icon = "🎤" if direction == "input" else "🤖"
                        print(f"  {icon} [{direction}/{marker}] {text}")
                    elif msg_type == "response":
                        print(f"  📝 [RESPONSE] {data.get('data', '')[:200]}")
                    elif msg_type == "status":
                        print(f"  ⚡ [STATUS] state={data.get('state')} detail={data.get('detail', '')}")
                    elif msg_type == "tool_call":
                        print(f"  🔧 [TOOL_CALL] {data.get('tool_name')}({json.dumps(data.get('arguments', {}))})")
                    elif msg_type == "tool_response":
                        result = str(data.get("result", ""))[:100]
                        print(f"  🔧 [TOOL_RESULT] {data.get('tool_name')} → {result}")
                    else:
                        print(f"  📨 [{msg_type}] {json.dumps(data, indent=2)[:300]}")
                except json.JSONDecodeError:
                    print(f"  ❓ [RAW] {msg[:200]}")
    except Exception as e:
        print(f"  Receiver ended: {e}")
    finally:
        if audio_chunks > 0:
            print(f"  Audio summary: {audio_chunks} chunks, {audio_bytes_total:,} bytes total")


async def _send_loop(ws, text_only: bool, audio_file: Path | None, chunk_ms: int):
    """Send user input or audio file to the server."""
    # If audio file provided, send it first
    if audio_file and audio_file.exists():
        await _send_audio_file(ws, audio_file, chunk_ms)
        print("  Audio file sent. You can still type messages.")

    # Interactive text input
    loop = asyncio.get_event_loop()
    try:
        while True:
            line = await loop.run_in_executor(None, _input_line)
            if line is None or line.strip().lower() == "quit":
                print("  Quitting...")
                return
            if line.strip():
                msg = json.dumps({"type": "text", "content": line.strip()})
                await ws.send(msg)
                print(f"  → Sent text: {line.strip()[:80]}")
    except Exception:
        pass


async def _send_audio_file(ws, path: Path, chunk_ms: int):
    """Stream a raw PCM file (16kHz, 16-bit, mono) in timed chunks."""
    # chunk_ms ms at 16kHz 16-bit mono = chunk_ms/1000 * 16000 * 2 bytes
    chunk_bytes = int(chunk_ms / 1000 * 16000 * 2)
    data = path.read_bytes()
    total = len(data)
    sent = 0
    print(f"  Streaming {path.name} ({total:,} bytes) in {chunk_ms}ms chunks...")
    t0 = time.monotonic()
    while sent < total:
        chunk = data[sent : sent + chunk_bytes]
        await ws.send(chunk)
        sent += len(chunk)
        # Pace at real-time speed
        elapsed = time.monotonic() - t0
        expected = sent / (16000 * 2)  # seconds of audio sent
        if expected > elapsed:
            await asyncio.sleep(expected - elapsed)
    duration = time.monotonic() - t0
    print(f"  Sent {total:,} bytes in {duration:.1f}s ({total / (16000 * 2):.1f}s of audio)")


def _input_line() -> str | None:
    """Blocking readline from stdin."""
    try:
        return input("> ")
    except (EOFError, KeyboardInterrupt):
        return None


def _generate_sine_pcm(freq: float = 440.0, duration: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Generate a sine wave as raw PCM16 bytes (for quick testing)."""
    import math
    n_samples = int(sample_rate * duration)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        sample = int(0x7FFF * 0.5 * math.sin(2 * math.pi * freq * t))
        samples.append(struct.pack("<h", sample))
    return b"".join(samples)


if __name__ == "__main__":
    asyncio.run(main())
