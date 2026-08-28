#!/usr/bin/env python3
"""Deliberately record one local pilot clip; never used by Cauco runtime."""
from __future__ import annotations
import argparse, json, secrets, shutil, subprocess, sys, time, wave
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wake_model import FIELDS, LABELS, SPLITS, validate_audio

MIN_SECONDS, MAX_SECONDS = .5, 3.0

def recording_id(existing: set[str]) -> str:
    while True:
        value = "rec_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
        if value not in existing: return value

def append_record(root: Path, item: dict, audio: Path) -> None:
    metadata = root / "metadata" / "recordings.jsonl"; metadata.parent.mkdir(parents=True, exist_ok=True)
    old = metadata.read_text(encoding="utf-8") if metadata.exists() else ""
    tmp = metadata.with_suffix(".tmp")
    try:
        tmp.write_text(old + json.dumps(item, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(metadata)
    except Exception:
        tmp.unlink(missing_ok=True); audio.unlink(missing_ok=True); raise

def record_sample(root: Path, label: str, phrase: str, speaker: str, environment: str, device: str, duration: float, language: str = "es", accent: str = "unspecified", split: str = "train", recorder=None) -> dict:
    if label not in LABELS: raise ValueError("unsupported label")
    if split not in SPLITS: raise ValueError("unsupported split")
    if not MIN_SECONDS <= duration <= MAX_SECONDS: raise ValueError("duration must be between 0.5 and 3 seconds")
    if label == "target" and phrase != "Hola Cauco": raise ValueError('target phrase must be "Hola Cauco"')
    if label == "background" and phrase: raise ValueError("background phrase must be empty")
    meta = root / "metadata" / "recordings.jsonl"; existing = set()
    if meta.exists():
        from wake_model import read_jsonl
        existing = {row["recording_id"] for _, row in read_jsonl(meta)}
    rid = recording_id(existing); audio = root / "audio" / f"{rid}.wav"; audio.parent.mkdir(parents=True, exist_ok=True)
    if audio.exists(): raise FileExistsError(audio)
    print(f"Recording {label}: {phrase or '(background)'} for {duration:.1f}s. Press Ctrl-C to cancel.")
    time.sleep(1)
    command = recorder or ["/opt/homebrew/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", ":default", "-t", str(duration), "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(audio)]
    try:
        if callable(command): command(audio, duration)
        else: subprocess.run(command, check=True, capture_output=True, text=True)
    except (subprocess.SubprocessError, OSError, KeyboardInterrupt): audio.unlink(missing_ok=True); raise RuntimeError("recording failed; no dataset item was created")
    try:
        with wave.open(str(audio), "rb") as w: rate, channels, frames = w.getframerate(), w.getnchannels(), w.getnframes()
        item = {"recording_id": rid, "label": label, "phrase": phrase, "speaker_id": speaker, "language": language, "accent": accent, "environment_id": environment, "device_id": device, "source_group": rid, "split": split, "duration_ms": round(frames * 1000 / rate), "sample_rate_hz": rate, "channels": channels, "relative_path": f"audio/{rid}.wav"}
        errors = validate_audio(audio, item)
        if errors: raise ValueError("; ".join(errors))
        append_record(root, item, audio); return item
    except Exception:
        audio.unlink(missing_ok=True); raise

def main():
    p=argparse.ArgumentParser(description="Record exactly one local wake-model dataset clip")
    p.add_argument("--label", required=True, choices=sorted(LABELS)); p.add_argument("--phrase", default=""); p.add_argument("--speaker", required=True); p.add_argument("--environment", required=True); p.add_argument("--device", required=True); p.add_argument("--root", default="wake-model/dataset"); p.add_argument("--duration", type=float, default=2.0); p.add_argument("--language", default="es"); p.add_argument("--accent", default="unspecified"); p.add_argument("--split", choices=["train","validation","test"], default="train"); a=p.parse_args()
    try: print(json.dumps(record_sample(Path(a.root), a.label, a.phrase, a.speaker, a.environment, a.device, a.duration, a.language, a.accent, a.split), sort_keys=True, indent=2))
    except Exception as e: print(f"recording failed: {e}", file=sys.stderr); raise SystemExit(1)
if __name__ == "__main__": main()
