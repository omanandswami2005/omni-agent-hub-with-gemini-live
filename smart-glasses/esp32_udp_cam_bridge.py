#!/usr/bin/env python3
"""ESP32 Audio + Camera bridge for Omni Hub /ws/live.

This extends the existing ESP32 UDP bridge with camera frame forwarding:
- Audio input: ESP32 UDP mic -> backend binary PCM
- Audio output: backend binary PCM -> ESP32 UDP speaker
- Camera input: ESP32-CAM HTTP JPEG snapshots -> backend image messages

Image messages match dashboard format:
  {"type": "image", "data_base64": "...", "mime_type": "image/jpeg"}
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import urllib.request

import websockets
import websockets.exceptions

from esp32_udp_bridge import (
    BACKEND_WS,
    ESP32_IP,
    MIC_PORT,
    SPEAKER_PORT,
    ESP32UDPBridge,
    _FIREBASE_API_KEY,
    _FIREBASE_EMAIL,
    _FIREBASE_PASSWORD,
    _get_firebase_token,
)


class ESP32UDPCamBridge(ESP32UDPBridge):
    """Audio bridge + camera snapshot sender."""

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
        super().__init__(
            token=token,
            server=server,
            esp32_ip=esp32_ip,
            mic_port=mic_port,
            speaker_port=speaker_port,
        )
        self.cam_url = cam_url
        self.cam_fps = max(0.1, cam_fps)
        self.cam_enabled = cam_enabled
        self._cam_sent = 0
        self._cam_fail = 0

    async def _fetch_jpeg(self) -> bytes:
        """Fetch one JPEG frame from ESP32-CAM HTTP endpoint."""
        def _fetch() -> bytes:
            req = urllib.request.Request(self.cam_url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.read()

        return await asyncio.to_thread(_fetch)

    async def _send_camera_frames(self, ws) -> None:
        """Continuously fetch and forward camera frames as base64 JPEG."""
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
                    self._log(
                        "CAM-TX",
                        f"Sent frame #{self._cam_sent} jpeg={len(jpg)}B b64={len(payload['data_base64'])}B",
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._cam_fail += 1
                self._log("CAM-ERR", f"Frame fetch/send failed ({self._cam_fail}): {e}")

            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, interval - elapsed))

        self._log("CAM", f"Stopped. sent={self._cam_sent} failed={self._cam_fail}")

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
