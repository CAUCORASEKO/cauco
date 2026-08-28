import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from train_acoustic_baseline import extract_features, load_wav, mel_filterbank, run, load_split


def make_wav(path, frequency=440, seconds=0.2):
    sample_count = int(16000 * seconds)
    samples = (0.3 * 32767 * np.sin(2 * np.pi * frequency * np.arange(sample_count) / 16000)).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(samples.tobytes())


def metadata(root, rows):
    (root / "metadata").mkdir(parents=True)
    (root / "metadata/recordings.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def row(recording_id, label, split, frequency):
    make_wav(ROOT / "audio" / f"{recording_id}.wav", frequency)
    return {"recording_id": recording_id, "label": label, "split": split, "relative_path": f"audio/{recording_id}.wav"}


def test_wav_features_are_fixed_deterministic_and_mel_valid(tmp_path):
    path = tmp_path / "a.wav"; make_wav(path)
    first = extract_features(path)
    assert first.shape == (61,); np.testing.assert_array_equal(first, extract_features(path))
    bank = mel_filterbank(); assert bank.shape == (24, 257); assert np.all(bank >= 0); assert np.all(bank.sum(axis=1) > 0)
    assert load_wav(path).shape[0] == 3200


def test_unsupported_wav_rejected(tmp_path):
    path = tmp_path / "bad.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2); out.setsampwidth(2); out.setframerate(8000); out.writeframes(b"\0" * 100)
    with pytest.raises(ValueError, match="unsupported"):
        load_wav(path)


def test_train_validation_separation_and_classifier_artifact(tmp_path):
    global ROOT; ROOT = tmp_path
    rows = [row("tr-bg", "background", "train", 200), row("tr-hn", "hard_negative_speech", "train", 600), row("tr-t", "target", "train", 1200), row("va-bg", "background", "validation", 200), row("va-hn", "hard_negative_speech", "validation", 600), row("va-t", "target", "validation", 1200)]
    metadata(tmp_path, rows)
    assert len(load_split(tmp_path, "train")) == 3 and len(load_split(tmp_path, "validation")) == 3 and load_split(tmp_path, "test") == []
    result = run(tmp_path, tmp_path / "out")
    assert result["train_count"] == 3 and result["validation_count"] == 3
    assert set(result["models"]) == {"logistic_regression", "linear_svm"}
    assert (tmp_path / "out/results.json").is_file()
    assert set(result["models"]["logistic_regression"]["confusion_matrix"]) == {"background", "hard_negative_speech", "target"}
