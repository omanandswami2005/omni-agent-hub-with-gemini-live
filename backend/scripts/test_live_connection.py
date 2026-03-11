#!/usr/bin/env python3
"""Test the Gemini Live API connection using the exact same code paths as the backend.

Run from the backend directory:
    uv run scripts/test_live_connection.py
"""

import asyncio
import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Step 1: Load settings & export env vars (same as app.config) ──────
from app.config import settings  # noqa: E402

print(f"[1/6] Settings loaded")
print(f"      Project:  {settings.GOOGLE_CLOUD_PROJECT}")
print(f"      Location: {settings.GOOGLE_CLOUD_LOCATION}")
print(f"      Model:    {settings.LIVE_MODEL}")
print(f"      VertexAI: {settings.GOOGLE_GENAI_USE_VERTEXAI}")


async def main():
    # ── Step 2: Build a minimal agent (same model as production) ──────
    from google.adk.agents import Agent

    print(f"\n[2/6] Creating minimal test agent...")
    agent = Agent(
        name="test_agent",
        model=settings.LIVE_MODEL,
        instruction="You are a test agent. Reply briefly to confirm the connection works.",
    )
    print(f"      Agent created: {agent.name} / {settings.LIVE_MODEL}")

    # ── Step 3: Create session service + session ──────────────────────
    from google.adk.sessions import InMemorySessionService

    print(f"\n[3/6] Creating session...")
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="test-live",
        user_id="test-user",
        session_id="test-session",
    )
    print(f"      Session: {session.id}")

    # ── Step 4: Create runner ─────────────────────────────────────────
    from google.adk.runners import Runner

    print(f"\n[4/6] Creating runner...")
    runner = Runner(
        app_name="test-live",
        agent=agent,
        session_service=session_service,
    )
    print(f"      Runner ready")

    # ── Step 5: Build RunConfig (same as _build_run_config) ───────────
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.genai import types

    print(f"\n[5/6] Building RunConfig (same as production)...")
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede",
                ),
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(handle=""),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow(target_tokens=16_000),
        ),
        proactivity=types.ProactivityConfig(proactive_audio=True),
        enable_affective_dialog=True,
    )
    print(f"      RunConfig built")

    # ── Step 6: run_live() — the actual connection test ───────────────
    from google.adk.agents.live_request_queue import LiveRequestQueue

    print(f"\n[6/6] Calling runner.run_live() — connecting to Live API...")
    print(f"      (This is where 'Establishing live connection' happens)\n")

    queue = LiveRequestQueue()

    # Send a text message so the agent responds
    content = types.Content(
        parts=[types.Part(text="Hello, say one short sentence to confirm you work.")],
        role="user",
    )
    queue.send_content(content)

    event_count = 0
    got_text = False
    timeout = 30

    try:
        async with asyncio.timeout(timeout):
            async for event in runner.run_live(
                user_id="test-user",
                session_id="test-session",
                live_request_queue=queue,
                run_config=run_config,
            ):
                event_count += 1

                # Print transcription / text
                if event.output_transcription and event.output_transcription.text:
                    print(f"  [transcription] {event.output_transcription.text}")
                    got_text = True

                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            print(f"  [text] {part.text}")
                            got_text = True
                        elif part.inline_data:
                            print(f"  [audio] {len(part.inline_data.data)} bytes")

                if event.turn_complete:
                    print(f"\n  [turn_complete] — agent finished responding")
                    break

                if event.interrupted:
                    print(f"  [interrupted]")

    except TimeoutError:
        print(f"\n  TIMEOUT after {timeout}s — received {event_count} events")
    except Exception as e:
        print(f"\n  ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        queue.close()

    # ── Result ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    if event_count > 0 and got_text:
        print(f"  SUCCESS — Received {event_count} events with text/transcription")
        print(f"  The Live API connection works correctly!")
    elif event_count > 0:
        print(f"  PARTIAL — Received {event_count} events (audio only, no text)")
        print(f"  Connection works but no transcription text came through.")
    else:
        print(f"  FAILED — No events received from run_live()")
        print(f"  The connection is stuck at 'Establishing live connection'.")
        print(f"  Check: credentials, project, model name, network/firewall.")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
