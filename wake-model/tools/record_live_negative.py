#!/usr/bin/env python3
"""Explicit, local-only continuous recorder for live-negative wake audits."""
from __future__ import annotations

import argparse
import json
import secrets
import signal
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one continuous live-negative WAV session")
    parser.add_argument("--category", required=True, choices=["ambient_room", "ordinary_spanish_speech", "near_phrase_negatives", "typical_noise"])
    parser.add_argument("--environment", required=True)
    parser.add_argument("--root", default="wake-model/live-negative")
    args = parser.parse_args()
    root = Path(args.root); audio_dir = root / "audio"; metadata_dir = root / "metadata"
    audio_dir.mkdir(parents=True, exist_ok=True); metadata_dir.mkdir(parents=True, exist_ok=True)
    recording_id = "live_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
    audio = audio_dir / f"{recording_id}.wav"
    print("Press Enter to start recording.", flush=True); input()
    command = ["/opt/homebrew/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", ":default", "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(audio)]
    process = subprocess.Popen(command)
    print("Recording. Press Enter to stop; Ctrl-C also cancels safely.", flush=True)
    try:
        input()
        process.send_signal(signal.SIGINT)
        process.wait(timeout=10)
    except (KeyboardInterrupt, subprocess.TimeoutExpired):
        process.terminate()
        process.wait(timeout=10)
    if process.returncode not in (0, 255) or not audio.exists():
        audio.unlink(missing_ok=True); print("recording failed; no metadata created", file=sys.stderr); return 1
    with wave.open(str(audio), "rb") as wav:
        rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
    item = {"recording_id": recording_id, "category": args.category, "device": "macbook_builtin", "sample_rate_hz": rate, "channels": channels, "environment": args.environment, "duration_ms": round(frames * 1000 / rate), "relative_path": f"audio/{audio.name}"}
    metadata = metadata_dir / f"{recording_id}.json"; metadata.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Saved WAV: {audio}"); print(f"Saved metadata: {metadata}"); return 0


if __name__ == "__main__": raise SystemExit(main())
