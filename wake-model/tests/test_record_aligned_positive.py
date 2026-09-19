import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from record_aligned_positive import estimate_sustained_bounds
import numpy as np
import os
import time
from record_aligned_positive import ContinuousPCMReader

def test_silence_has_no_sustained_bounds():
    assert estimate_sustained_bounds(np.zeros(16_000)) == (None, None)

def test_centered_activity_has_sustained_bounds():
    x = np.zeros(16_000); x[5_000:11_000] = .1
    onset, offset = estimate_sustained_bounds(x)
    assert 4_800 <= onset <= 5_000
    assert 10_900 <= offset <= 11_200

def test_short_burst_below_30ms_has_no_bounds():
    x = np.zeros(16_000); x[5_000:5_000 + 5 * 16] = .1
    assert estimate_sustained_bounds(x) == (None, None)

def test_30ms_activity_meets_sustain_requirement():
    x = np.zeros(16_000); x[5_000:5_000 + 30 * 16] = .1
    onset, offset = estimate_sustained_bounds(x)
    assert 4_800 <= onset <= 5_000
    assert 5_400 <= offset <= 5_600

def test_activity_near_end_reports_end_bound():
    x = np.zeros(16_000); x[14_000:] = .1
    onset, offset = estimate_sustained_bounds(x)
    assert 13_900 <= onset <= 14_000
    assert offset == 15_999

def test_pre_record_buffered_pcm_cannot_enter_capture_interval():
    read_fd, write_fd = os.pipe(); os.set_blocking(read_fd, False)
    class Stream:
        def fileno(self): return read_fd
    reader = ContinuousPCMReader(Stream()); os.write(write_fd, b"pre-record")
    reader.start(); time.sleep(0.02); reader.request_capture(); reader.wait_boundary(); os.write(write_fd, b"post-record")
    captured = reader.read_target(len(b"post-record"), 1.0); reader.stop(); os.close(read_fd); os.close(write_fd)
    assert captured == b"post-record"

def test_capture_is_exactly_32000_post_boundary_bytes():
    read_fd, write_fd = os.pipe(); os.set_blocking(read_fd, False)
    class Stream:
        def fileno(self): return read_fd
    reader = ContinuousPCMReader(Stream()); os.write(write_fd, b"old"); reader.start(); time.sleep(0.02); reader.request_capture(); reader.wait_boundary(); os.write(write_fd, b"n" * 32_000)
    captured = reader.read_target(32_000, 1.0); reader.stop(); os.close(read_fd); os.close(write_fd)
    assert len(captured) == 32_000 and captured == b"n" * 32_000
