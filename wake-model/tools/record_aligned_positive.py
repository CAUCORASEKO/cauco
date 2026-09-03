#!/usr/bin/env python3
"""Manual, local-only recorder for exactly one-second aligned positives."""
from __future__ import annotations
import argparse, json, secrets, signal, subprocess, sys, tempfile, time, wave
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

RATE, SAMPLES = 16_000, 16_000

def inspect(path: Path) -> tuple[bool, str]:
    try:
        with wave.open(str(path), "rb") as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) != (RATE, 1, 2, SAMPLES): return False, "format is not mono 16 kHz PCM with exactly 16000 samples"
            x = np.frombuffer(w.readframes(SAMPLES), dtype="<i2").astype(np.float64) / 32768.0
    except (OSError, EOFError, wave.Error): return False, "invalid WAV"
    peak, rms = float(np.max(np.abs(x))), float(np.sqrt(np.mean(x * x)))
    edge = max(1, RATE // 20); edge_rms = (float(np.sqrt(np.mean(x[:edge] ** 2))), float(np.sqrt(np.mean(x[-edge:] ** 2))))
    first_threshold, last_threshold = max(rms * 2.5, 0.02), max(rms * 2.5, 0.02)
    energy_threshold = max(rms * 0.1, 0.002)
    active = np.abs(x) >= energy_threshold
    onset = int(np.argmax(active)) if np.any(active) else None
    offset = int(len(x) - 1 - np.argmax(active[::-1])) if np.any(active) else None
    print(f"boundary_diagnostics: whole_rms={rms:.9f} first_edge_rms={edge_rms[0]:.9f} last_edge_rms={edge_rms[1]:.9f} edge_samples={edge} edge_duration_s={edge/RATE:.3f} first_ratio={edge_rms[0]/rms if rms else 0:.3f} last_ratio={edge_rms[1]/rms if rms else 0:.3f} first_threshold={first_threshold:.9f} last_threshold={last_threshold:.9f} peak={peak:.9f} energy_threshold={energy_threshold:.9f} onset_sample={onset} offset_sample={offset}", flush=True)
    if not np.any(x): return False, "empty signal"
    if peak >= 0.999: return False, "clipped signal"
    if rms < 0.001 or rms > 0.5: return False, f"unreasonable RMS {rms:.6f}"
    if edge_rms[0] > first_threshold or edge_rms[1] > last_threshold: return False, "possible phrase truncation at recording boundary"
    return True, f"accepted (RMS {rms:.4f}, peak {peak:.4f})"

def wav_properties(path: Path) -> tuple[int, int, int, int, float]:
    with wave.open(str(path), "rb") as w:
        rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    return rate, channels, width, frames, frames / rate if rate else 0.0

def capture_one_second(ffmpeg: str, path: Path) -> tuple[bool, str]:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", ":default", str(path)]
    try: process = subprocess.Popen(command)
    except OSError as exc: return False, f"could not start native capture: {exc}"
    target = None; native_rate = None; collected = 0; deadline = time.monotonic() + 5
    try:
        while time.monotonic() < deadline:
            if path.exists():
                try:
                    rate, channels, width, frames, _ = wav_properties(path)
                    if rate > 0 and channels > 0 and width > 0:
                        native_rate = rate; target = round(rate * 1.0); collected = frames
                        if frames >= target: break
                except (OSError, EOFError, wave.Error): pass
            if process.poll() is not None: break
            time.sleep(0.02)
        if target is None: return False, "native capture produced no readable format header"
        if collected < target: return False, f"native capture ended at {collected} frames; required {target}"
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=2)
    rate, channels, width, frames, _ = wav_properties(path)
    print(f"native_rate={native_rate} native_channels={channels} native_frames_collected_total={frames} native_frames_used={target} native_duration_used={target / native_rate:.3f}", flush=True)
    if frames < target: return False, "capture stopped before target frame count"
    # Keep exactly the complete one-second native interval; excess callback frames are normal.
    with wave.open(str(path), "rb") as source:
        audio = source.readframes(target)
        params = source.getparams(); params = (params.nchannels, params.sampwidth, params.framerate, target, params.comptype, params.compname)
    with wave.open(str(path), "wb") as output:
        output.setparams(params); output.writeframes(audio)
    return True, ""

def main() -> int:
    p = argparse.ArgumentParser(description="Record aligned 'Hola Cauco' one-second positives")
    p.add_argument("--session", required=True, choices=["session_001", "session_002"]); p.add_argument("--count", type=int, required=True)
    p.add_argument("--environment", required=True); p.add_argument("--root", type=Path, default=Path("wake-model/windowed-positive")); p.add_argument("--ffmpeg", default="/opt/homebrew/bin/ffmpeg")
    a = p.parse_args(); a.root.joinpath("audio").mkdir(parents=True, exist_ok=True); a.root.joinpath("metadata").mkdir(parents=True, exist_ok=True)
    for index in range(1, a.count + 1):
        while True:
            rid = f"{a.session}_{index:02d}_{secrets.token_hex(3)}"; audio = a.root / "audio" / f"{rid}.wav"
            native = Path(tempfile.mktemp(prefix="cauco-native-", suffix=".wav"))
            print(f"\nRecording {index}/{a.count}\nReady", flush=True)
            for n in (3, 2, 1): print(n, flush=True); time.sleep(1)
            print('RECORD — say "Hola Cauco" completely inside this one second', flush=True)
            ok, reason = capture_one_second(a.ffmpeg, native)
            if ok:
                converted = [a.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(native), "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", "-t", "1.0", str(audio)]
                conversion = subprocess.run(converted, timeout=5)
                ok, reason = conversion.returncode == 0 and audio.exists(), "native-to-dataset conversion failed"
            native.unlink(missing_ok=True)
            if ok: ok, reason = inspect(audio)
            if not ok:
                print(f"Rejected: {reason}. Press Enter to retry this example.", flush=True); audio.unlink(missing_ok=True); input(); continue
            final_rate, final_channels, final_width, final_frames, final_duration = wav_properties(audio)
            print(f"normalized_rate={final_rate} normalized_channels={final_channels} normalized_frames={final_frames} normalized_duration={final_duration:.3f}", flush=True)
            metadata = {"label":"hola_cauco","session_id":a.session,"source_recording_id":rid,"device":"macbook_builtin","sample_rate":final_rate,"channels":final_channels,"exact_samples":final_frames,"environment":a.environment,"audio_file":f"audio/{audio.name}","recorded_at":datetime.now(timezone.utc).isoformat()}
            (a.root / "metadata" / f"{rid}.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
            print(f"saved {audio}", flush=True); break
    return 0
if __name__ == "__main__": raise SystemExit(main())
