#!/usr/bin/env python3
"""Write a deterministic, non-audio feature reference for Swift parity tests."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_temporal_acoustic import temporal_features

def main() -> None:
    # Deterministic PCM-like signal; no WAV or personal data is written.
    n = 16000
    t = np.arange(n, dtype=np.float64) / 16000.0
    samples = 0.18 * np.sin(2*np.pi*440*t) + 0.07 * np.sin(2*np.pi*997*t + 0.31)
    # Use the authoritative implementation through a temporary WAV only.
    import tempfile, wave
    with tempfile.NamedTemporaryFile(suffix='.wav') as f:
        with wave.open(f.name, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(np.clip(samples * 32768, -32768, 32767).astype('<i2').tobytes())
        values = temporal_features(Path(f.name), normalize=True)
    out = Path('wake-model/local-output/coreml-pilot/feature-fixture.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'sample_id':'deterministic_synthetic_440_997','feature_dimension':348,'values':values.tolist()}, indent=2) + '\n')
    print(out)
if __name__ == '__main__': main()
