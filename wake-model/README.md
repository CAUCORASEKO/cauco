# Hola Cauco wake-model development

Offline-only foundations for developing and evaluating a future custom Core ML
audio classifier. **No real wake model or training audio is included.** This
directory is not imported by Cauco runtime packages.

## Layout

```text
dataset/audio/                 # local recordings, never committed
dataset/metadata/recordings.jsonl
dataset/manifests/{train,validation,test}.jsonl
model-manifest.example.json
tools/wake_model.py
tests/test_wake_model.py
```

The dataset taxonomy is `target` (`Hola Cauco`), `hard_negative_speech`, and
`background`. Runtime export may later collapse the latter two into `other`,
but retaining them during evaluation makes false positives visible.

Canonical source audio is mono, PCM WAV, 16-bit, 16 kHz, with 500–3000 ms
clips. Validation is non-destructive. Metadata contains anonymous IDs and
dataset-relative paths only. Train/test splits protect speaker, environment,
device, and source-group boundaries.

Run from this directory:

```sh
python tools/wake_model.py validate-dataset dataset
python tools/wake_model.py threshold predictions.jsonl --thresholds 0.5,0.7,0.9
python tools/wake_model.py temporal predictions.jsonl --threshold 0.85 --consecutive 2
python tools/wake_model.py validate-model-manifest model-manifest.json
```

Threshold selection reports precision, recall, FPR/FNR, false activations per
hour, and hard-negative activation rate. Choose a threshold subject to a
maximum false-positive target; do not optimize accuracy alone. Temporal rules
are offline simulations only and are not production wake logic.

Future training may use Apple Create ML or another local provider. Before a
model is integrated, validate its identifier/version, checksum, deployment
target, audio input, and bounded probability labels against the model manifest.

Recordings remain local, are not uploaded or telemetered, and should be removed
using ordinary local file deletion when no longer needed. Anonymous IDs should
not be reversible to personal identities.
