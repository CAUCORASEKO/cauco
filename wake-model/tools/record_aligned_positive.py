#!/usr/bin/env python3
"""Manual, local-only recorder for exactly one-second aligned positives."""
from __future__ import annotations
import argparse, json, secrets, select, signal, subprocess, sys, time, wave, os, threading
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

RATE, SAMPLES = 16_000, 16_000

def estimate_sustained_bounds(x: np.ndarray) -> tuple[int | None, int | None]:
    """Diagnostic-only bounds: 10 ms RMS frames, 5 ms hop, 30 ms sustain."""
    frame, hop, minimum = RATE // 100, RATE // 200, 5
    threshold = max(float(np.sqrt(np.mean(x * x))) * 0.1, 0.002)
    energies = np.array([np.sqrt(np.mean(x[start:start + frame] ** 2)) for start in range(0, len(x) - frame + 1, hop)])
    active = energies >= threshold
    runs = []; start = None
    for index, value in enumerate(np.r_[active, False]):
        if value and start is None: start = index
        elif not value and start is not None:
            if index - start >= minimum: runs.append((start, index - 1))
            start = None
    if not runs: return None, None
    return runs[0][0] * hop, min(len(x) - 1, runs[-1][1] * hop + frame - 1)

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
    onset, offset = estimate_sustained_bounds(x)
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

def read_pipe(stream, size: int, timeout: float) -> bytes:
    fd = stream.fileno(); chunks = []; total = 0; deadline = time.monotonic() + timeout
    while total < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0: break
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready: break
        try: chunk = os.read(fd, min(64 * 1024, size - total))
        except BlockingIOError: continue
        if not chunk: break
        chunks.append(chunk); total += len(chunk)
    return b"".join(chunks)

def stop_capture(process) -> int:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=1)
    return process.returncode

class ContinuousPCMReader:
    def __init__(self, stream):
        self.stream = stream; self.fd = stream.fileno(); self.capture = False; self.requested = threading.Event(); self.boundary = None; self.boundary_ack = threading.Event(); self.data = bytearray(); self.lock = threading.Lock(); self.done = threading.Event(); self.thread = threading.Thread(target=self._run, daemon=True)
    def start(self): self.thread.start()
    def request_capture(self): self.requested.set()
    def wait_boundary(self, timeout=1.0):
        if not self.boundary_ack.wait(timeout): raise TimeoutError("reader did not acknowledge RECORD boundary")
        return self.boundary
    def read_target(self, size: int, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if len(self.data) >= size: return bytes(self.data[:size])
            time.sleep(0.001)
        with self.lock: return bytes(self.data[:size])
    def stop(self): self.done.set(); self.thread.join(timeout=1)
    def _run(self):
        while not self.done.is_set():
            if self.requested.is_set() and not self.capture:
                with self.lock: self.data.clear(); self.capture = True; self.boundary = time.monotonic_ns()
                self.boundary_ack.set()
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if not ready: continue
            capture_this_read = self.capture
            try: chunk = os.read(self.fd, 64 * 1024)
            except BlockingIOError: continue
            if not chunk: return
            with self.lock:
                if capture_this_read: self.data.extend(chunk)

def start_pcm_capture(ffmpeg: str):
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", ":default", "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"]
    started = time.monotonic_ns()
    try: process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as exc: return None, None, f"could not start capture: {exc}"
    stream = process.stdout; warmup = read_pipe(stream, 4096, 5.0); ready = time.monotonic_ns()
    os.set_blocking(stream.fileno(), False)
    if len(warmup) < 2: process.terminate(); process.wait(); return None, None, "capture produced no PCM readiness data"
    print(f"capture_timing: popen_before_ns={started} pcm_ready_ns={ready} warmup_frames={len(warmup)//2} elapsed_to_pcm_ready_ms={(ready-started)/1_000_000:.3f}", flush=True)
    return process, stream, ""

def capture_pcm_interval(process, reader: ContinuousPCMReader, boundary: int) -> bytes:
    audio = reader.read_target(SAMPLES * 2, 3.0); reached = time.monotonic_ns()
    reader.stop(); stop_capture(process); exited = time.monotonic_ns()
    print(f"capture_timing: record_boundary_ns={boundary} pcm_target_reached_ns={reached} ffmpeg_exited_ns={exited} target_frames={SAMPLES} captured_frames={len(audio)//2} elapsed_record_to_target_ms={(reached-boundary)/1_000_000:.3f} elapsed_target_to_exit_ms={(exited-reached)/1_000_000:.3f}", flush=True)
    return audio

def drain_before_record(stream) -> int:
    """Nonblocking snapshot drain; never waits for producer quiescence."""
    fd = stream.fileno(); drained = 0
    while True:
        ready, _, _ = select.select([fd], [], [], 0)
        if not ready: return drained
        try: chunk = os.read(fd, 64 * 1024)
        except BlockingIOError: return drained
        if not chunk: return drained
        drained += len(chunk)

def main() -> int:
    p = argparse.ArgumentParser(description="Record aligned 'Hola Cauco' one-second positives")
    p.add_argument("--session", required=True, choices=["session_001", "session_002"]); p.add_argument("--count", type=int, required=True)
    p.add_argument("--environment", required=True); p.add_argument("--root", type=Path, default=Path("wake-model/windowed-positive")); p.add_argument("--ffmpeg", default="/opt/homebrew/bin/ffmpeg")
    a = p.parse_args(); a.root.joinpath("audio").mkdir(parents=True, exist_ok=True); a.root.joinpath("metadata").mkdir(parents=True, exist_ok=True)
    for index in range(1, a.count + 1):
        while True:
            rid = f"{a.session}_{index:02d}_{secrets.token_hex(3)}"; audio = a.root / "audio" / f"{rid}.wav"
            print(f"\nRecording {index}/{a.count}\nReady", flush=True)
            process, stream, reason = start_pcm_capture(a.ffmpeg)
            if process is None:
                print(f"Rejected: {reason}", file=sys.stderr); return 1
            for n in (3, 2, 1): print(n, flush=True); time.sleep(1)
            reader = ContinuousPCMReader(stream); reader.start()
            print("capture_timing: record_boundary_preparation=continuous_discard_before_RECORD", flush=True)
            reader.request_capture(); boundary = reader.wait_boundary(); print(f"capture_timing: record_boundary_established_ns={boundary}", flush=True)
            print('RECORD — say "Hola Cauco" completely inside this one second', flush=True)
            pcm = capture_pcm_interval(process, reader, boundary)
            with wave.open(str(audio), "wb") as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(RATE); output.writeframes(pcm)
            ok, reason = len(pcm) == SAMPLES * 2, "capture ended before 16000 normalized samples"
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
