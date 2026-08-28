#!/usr/bin/env python3
"""Deterministic log-mel classical baselines for the pilot wake dataset."""
from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.fft import dct
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wake_model import LABELS, read_jsonl

CLASS_MAP = ("background", "hard_negative_speech", "target")
SAMPLE_RATE = 16000
FRAME_LENGTH = 400  # 25 ms
HOP_LENGTH = 160  # 10 ms
FFT_SIZE = 512
MEL_BANDS = 24
MFCC_COUNT = 13


def _hz_to_mel(hz: float) -> float:
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def mel_filterbank(sample_rate: int = SAMPLE_RATE, bands: int = MEL_BANDS) -> np.ndarray:
    if sample_rate != SAMPLE_RATE or bands <= 0:
        raise ValueError("unsupported mel configuration")
    points = np.linspace(_hz_to_mel(0), _hz_to_mel(sample_rate / 2), bands + 2)
    bins = np.floor((FFT_SIZE + 1) * np.array([_mel_to_hz(x) for x in points]) / sample_rate).astype(int)
    bank = np.zeros((bands, FFT_SIZE // 2 + 1), dtype=np.float64)
    for i in range(1, bands + 1):
        left, center, right = bins[i - 1:i + 2]
        for j in range(left, center):
            if 0 <= j < bank.shape[1] and center > left:
                bank[i - 1, j] = (j - left) / (center - left)
        for j in range(center, right):
            if 0 <= j < bank.shape[1] and right > center:
                bank[i - 1, j] = (right - j) / (right - center)
    return bank


def load_wav(path: Path) -> np.ndarray:
    try:
        with wave.open(str(path), "rb") as source:
            if (source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getcomptype()) != (16000, 1, 2, "NONE"):
                raise ValueError("unsupported WAV format; expected mono 16-bit 16 kHz PCM")
            raw = source.readframes(source.getnframes())
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError("malformed WAV") from exc
    if not raw or len(raw) % 2:
        raise ValueError("empty or malformed WAV")
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def extract_features(path: Path) -> np.ndarray:
    samples = load_wav(path)
    if len(samples) < FRAME_LENGTH:
        samples = np.pad(samples, (0, FRAME_LENGTH - len(samples)))
    frames = np.lib.stride_tricks.sliding_window_view(samples, FRAME_LENGTH)[::HOP_LENGTH]
    if len(frames) == 0:
        frames = samples[:FRAME_LENGTH][None, :]
    windowed = frames * np.hanning(FRAME_LENGTH)
    power = np.abs(np.fft.rfft(windowed, n=FFT_SIZE, axis=1)) ** 2 / FFT_SIZE
    energies = np.maximum(power @ mel_filterbank().T, 1e-12)
    log_mel = np.log(energies)
    mfcc = dct(log_mel, type=2, axis=1, norm="ortho")[:, :MFCC_COUNT]
    return np.concatenate((log_mel.mean(axis=0), log_mel.std(axis=0), mfcc.mean(axis=0))).astype(np.float64)


def load_split(root: Path, split: str):
    rows = [(row, extract_features(root / row["relative_path"])) for _, row in read_jsonl(root / "metadata" / "recordings.jsonl") if row.get("split") == split]
    return rows


def evaluate(model, rows):
    actual = [row["label"] for row, _ in rows]
    predicted = model.predict(np.array([vector for _, vector in rows]))
    matrix = {label: {other: 0 for other in CLASS_MAP} for label in CLASS_MAP}
    for truth, guess in zip(actual, predicted):
        matrix[truth][guess] += 1
    total = len(actual)
    accuracy = sum(truth == guess for truth, guess in zip(actual, predicted)) / total if total else 0.0
    per_class = {}
    for label in CLASS_MAP:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in CLASS_MAP if other != label)
        fn = sum(matrix[label][other] for other in CLASS_MAP if other != label)
        per_class[label] = {"precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0}
    target = per_class["target"]
    target_fp = sum(matrix[other]["target"] for other in CLASS_MAP if other != "target")
    non_target = total - sum(1 for label in actual if label == "target")
    return {"confusion_matrix": matrix, "accuracy": accuracy, "per_class": per_class, "target_precision": target["precision"], "target_recall": target["recall"], "target_false_positive_rate": target_fp / non_target if non_target else 0.0, "target_false_negative_rate": 1.0 - target["recall"]}


def threshold_results(model, rows):
    if not rows or not hasattr(model, "predict_proba"):
        return []
    probabilities = model.predict_proba(np.array([vector for _, vector in rows]))[:, list(model.classes_).index("target")]
    results = []
    for threshold in (0.50, 0.65, 0.80):
        positives = probabilities >= threshold
        truth = np.array([row["label"] == "target" for row, _ in rows])
        results.append({"threshold": threshold, "one_window_activations": int(positives.sum()), "two_consecutive_activations": int(sum(positives[:-1] & positives[1:])), "target_hits": int((positives & truth).sum())})
    return results


def run(root: Path, output: Path) -> dict:
    train, validation = load_split(root, "train"), load_split(root, "validation")
    if not train or not validation:
        raise ValueError("train and validation splits are required")
    x_train = np.array([v for _, v in train]); y_train = [r["label"] for r, _ in train]
    x_validation = np.array([v for _, v in validation])
    models = {"logistic_regression": LogisticRegression(C=1.0, max_iter=1000, random_state=0), "linear_svm": SVC(kernel="linear", C=1.0, probability=False, random_state=0)}
    result = {"feature_config": {"sample_rate_hz": SAMPLE_RATE, "frame_length_samples": FRAME_LENGTH, "hop_length_samples": HOP_LENGTH, "fft_size": FFT_SIZE, "mel_bands": MEL_BANDS, "mfcc_count": MFCC_COUNT, "aggregation": "mean_and_std_log_mel_plus_mean_mfcc"}, "class_map": CLASS_MAP, "train_count": len(train), "validation_count": len(validation), "train_class_counts": dict(sorted(Counter(y_train).items())), "models": {}}
    for name, model in models.items():
        model.fit(x_train, y_train)
        result["models"][name] = evaluate(model, validation)
        if name == "logistic_regression":
            result["threshold_simulation"] = threshold_results(model, validation)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="wake-model/dataset")
    parser.add_argument("--output", default="wake-model/local-output/acoustic-baseline")
    args = parser.parse_args()
    print(json.dumps(run(Path(args.root), Path(args.output)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
