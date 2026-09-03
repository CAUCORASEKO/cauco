#!/usr/bin/env python3
"""Offline rolling-window audit and runtime-trigger parity audit."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.fft import dct
from scipy.io import wavfile
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from train_acoustic_baseline import FRAME_LENGTH, HOP_LENGTH, FFT_SIZE, MEL_BANDS, MFCC_COUNT, load_wav, mel_filterbank
from wake_model import read_jsonl

WINDOW = 16_000
HOP = 2_560
THRESHOLD = 0.85


def features(samples: np.ndarray, normalize: bool = True) -> np.ndarray:
    x = samples.astype(np.float64, copy=False)
    if len(x) < FRAME_LENGTH:
        x = np.pad(x, (0, FRAME_LENGTH - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, FRAME_LENGTH)[::HOP_LENGTH]
    win = frames * np.hanning(FRAME_LENGTH)
    power = np.abs(np.fft.rfft(win, FFT_SIZE, axis=1)) ** 2 / FFT_SIZE
    logmel = np.log(np.maximum(power @ mel_filterbank().T, 1e-12))
    mfcc = dct(logmel, type=2, axis=1, norm="ortho")[:, :MFCC_COUNT]
    delta = np.gradient(mfcc, axis=0) if len(mfcc) > 1 else np.zeros_like(mfcc)
    delta2 = np.gradient(delta, axis=0) if len(delta) > 1 else np.zeros_like(delta)
    if normalize:
        logmel -= logmel.mean(axis=0, keepdims=True)
        mfcc -= mfcc.mean(axis=0, keepdims=True)
    result = []
    for indices in np.array_split(np.arange(len(logmel)), 4):
        if len(indices) == 0:
            indices = np.array([len(logmel) - 1])
        result.extend(logmel[indices].mean(0)); result.extend(logmel[indices].std(0))
        result.extend(mfcc[indices].mean(0)); result.extend(delta[indices].mean(0)); result.extend(delta2[indices].mean(0))
    return np.asarray(result, dtype=np.float64)


def percentile(values: list[float], q: float) -> float | None:
    return None if not values else float(np.percentile(values, q))


def summarize(rows: list[dict]) -> dict:
    scores = [r["probability"] for r in rows]
    out = {"recordings": len({r["source_recording"] for r in rows}), "windows": len(rows)}
    for name, q in [("min", 0), ("p10", 10), ("median", 50), ("p90", 90), ("p95", 95), ("p99", 99), ("max", 100)]: out[name] = percentile(scores, q)
    for threshold in (0.50, 0.70, 0.85, 0.95):
        count = sum(v >= threshold for v in scores)
        out[f"ge_{threshold:.2f}"] = {"count": count, "percent": 100 * count / len(scores) if scores else 0}
    return out


def distance_summary(rows: list[dict]) -> dict:
    def values(key): return [r[key] for r in rows]
    return {key: {name: percentile(values(key), q) for name, q in [("min", 0), ("median", 50), ("p90", 90), ("p95", 95), ("p99", 99), ("max", 100)]} for key in ("z_norm", "max_abs_z", "z_gt_3", "z_gt_5")}


def load_audio(path: Path) -> np.ndarray:
    try:
        return load_wav(path)
    except ValueError:
        rate, audio = wavfile.read(path)
        if rate != 16_000 or audio.ndim != 1 or audio.dtype != np.int16:
            raise ValueError(f"unsupported WAV format: {path}")
        return audio.astype(np.float64) / 32768.0


def audit(root: Path, live_root: Path | None = None) -> dict:
    records = [(row, root) for _, row in read_jsonl(root / "metadata" / "recordings.jsonl")]
    if live_root:
        records += [(json.loads(path.read_text()), live_root) for path in sorted((live_root / "metadata").glob("*.json"))]
    train_rows = [r for r, _ in records if r.get("split") == "train"]
    x_train = np.asarray([features(load_audio(root / r["relative_path"])) for r in train_rows])
    y_train = np.asarray(["hola_cauco" if r["label"] == "target" else "non_target" for r in train_rows])
    scaler = StandardScaler().fit(x_train)
    classifier = LogisticRegression(C=1, max_iter=1000, random_state=0, multi_class="ovr").fit(scaler.transform(x_train), y_train)
    target_index = list(classifier.classes_).index("hola_cauco")
    target_weights = classifier.coef_[0] if target_index == 1 else -classifier.coef_[0]
    target_intercept = classifier.intercept_[0] if target_index == 1 else -classifier.intercept_[0]
    rows = []
    for record, base_root in records:
        samples = load_audio(base_root / record["relative_path"])
        if len(samples) < WINDOW: continue
        category = record.get("category") or ("target" if record["label"] == "target" else ("near_phrase_hard_negative" if record.get("label") == "hard_negative_speech" else "background"))
        for start in range(0, len(samples) - WINDOW + 1, HOP):
            vector = features(samples[start:start + WINDOW])
            z = scaler.transform(vector.reshape(1, -1))[0]
            probability = float(classifier.predict_proba(z.reshape(1, -1))[0, target_index])
            logit = float(target_weights @ z + target_intercept)
            rows.append({"source_recording": record["recording_id"], "category": category, "split": record.get("split", "live_negative"), "ground_truth": record.get("label", category), "start_s": start / 16000, "end_s": (start + WINDOW) / 16000, "probability": probability, "logit": logit, "threshold_margin": probability - THRESHOLD, "predicted_label": "hola_cauco" if probability >= THRESHOLD else "non_target", "z_norm": float(np.linalg.norm(z)), "max_abs_z": float(np.max(np.abs(z))), "z_gt_3": int(np.sum(np.abs(z) > 3)), "z_gt_5": int(np.sum(np.abs(z) > 5))})
    categories = sorted({r["category"] for r in rows})
    by_category = {category: summarize([r for r in rows if r["category"] == category]) for category in categories}
    by_recording = {recording["recording_id"]: summarize([r for r in rows if r["source_recording"] == recording["recording_id"]]) for recording, _ in records}
    streaks = []
    for recording, _ in records:
        values = [r for r in rows if r["source_recording"] == recording["recording_id"]]
        run = best = 0; fire = None
        for row in values:
            run = run + 1 if row["probability"] >= THRESHOLD else 0; best = max(best, run)
            if run >= 3 and fire is None: fire = row["start_s"]
        streaks.append({"source_recording": recording["recording_id"], "category": next((r["category"] for r in values), "unwindowable"), "fires": fire is not None, "first_fire_s": fire, "max_streak": best, "max_probability": max((r["probability"] for r in values), default=None), "phrase": recording.get("phrase", "")})
    weights = target_weights
    extremes = sorted(((float(abs(row["z_norm"])), row["source_recording"]) for row in rows), reverse=True)[:10]
    cohorts = {"train_target": [r for r in rows if r["split"] == "train" and r["ground_truth"] == "target"], "train_negative": [r for r in rows if r["split"] == "train" and r["ground_truth"] != "target"], "curated_validation": [r for r in rows if r["split"] == "validation"], "live_negative": [r for r in rows if r["split"] == "live_negative"]}
    return {"configuration": {"window_s": 1, "hop_s": .16, "threshold": THRESHOLD, "feature_dimension": 348, "training_count": len(train_rows)}, "sklearn_classes": classifier.classes_.tolist(), "target_class": "hola_cauco", "decision_function_class": classifier.classes_[1], "category_distributions": by_category, "recording_distributions": by_recording, "cohort_distributions": {key: {"scores": summarize(value), "distances": distance_summary(value)} for key, value in cohorts.items()}, "category_distances": {category: distance_summary([r for r in rows if r["category"] == category]) for category in categories}, "recording_streaks": streaks, "window_count": len(rows), "windows": rows, "coefficient_summary": {"orientation": "hola_cauco", "intercept": float(target_intercept), "min": float(weights.min()), "max": float(weights.max()), "mean_abs": float(np.mean(np.abs(weights))), "max_abs": float(np.max(np.abs(weights))), "top_abs_weight_indices": [int(i) for i in np.argsort(np.abs(weights))[-10:][::-1]]}, "largest_window_norms": extremes}


def audit_runtime(root: Path, trigger_path: Path, live_root: Path | None = None) -> dict:
    records = [(row, root) for _, row in read_jsonl(root / "metadata" / "recordings.jsonl")]
    if live_root:
        records += [(json.loads(path.read_text()), live_root) for path in sorted((live_root / "metadata").glob("*.json"))]
    train = [r for r, _ in records if r.get("split") == "train"]
    x_train = np.asarray([features(load_audio(root / r["relative_path"])) for r in train])
    y_train = np.asarray(["hola_cauco" if r["label"] == "target" else "non_target" for r in train])
    scaler = StandardScaler().fit(x_train)
    classifier = LogisticRegression(C=1, max_iter=1000, random_state=0, multi_class="ovr").fit(scaler.transform(x_train), y_train)
    target = list(classifier.classes_).index("hola_cauco"); orientation = classifier.classes_[1]
    weights = classifier.coef_[0] if target == 1 else -classifier.coef_[0]
    intercept = classifier.intercept_[0] if target == 1 else -classifier.intercept_[0]
    payload = json.loads(trigger_path.read_text()); runtime = payload.get("records", payload) if isinstance(payload, dict) else payload
    train_z = scaler.transform(x_train); x_all = np.asarray([features(load_audio(base / r["relative_path"])) for r, base in records]); all_z = scaler.transform(x_all)
    out = []
    for item in runtime:
        vector = np.asarray(item["features"], dtype=float); z = scaler.transform(vector.reshape(1, -1))[0]
        probabilities = classifier.predict_proba(z.reshape(1, -1))[0]
        py_prob = float(probabilities[target]); py_logit = float(weights @ z + intercept)
        contrib = weights * z; order = np.argsort(contrib)
        outside = np.where((vector < x_train.min(0)) | (vector > x_train.max(0)))[0]
        nearest = {name: float(np.min(np.linalg.norm(z - cohort, axis=1))) for name, cohort in [("training_positives", train_z[y_train == "hola_cauco"]), ("training_negatives", train_z[y_train != "hola_cauco"]), ("all_recordings", all_z)]}
        out.append({"inference_sequence": item["inferenceSequence"], "relative_timestamp": item["relativeTimestamp"], "coreml_probability": item["coreMLProbability"], "coreml_logit": item["coreMLLogit"], "python_probability": py_prob, "python_probability_mapping": {str(name): float(value) for name, value in zip(classifier.classes_, probabilities)}, "python_logit_target_oriented": py_logit, "absolute_probability_difference": abs(py_prob - item["coreMLProbability"]), "absolute_target_logit_difference": abs(py_logit - item["coreMLLogit"]), "standardized_feature_norm": float(np.linalg.norm(z)), "max_abs_z": float(np.max(abs(z))), "count_abs_z_gt_3": int(np.sum(abs(z) > 3)), "count_abs_z_gt_5": int(np.sum(abs(z) > 5)), "nearest_distance": nearest, "outside_training_range_indices": [int(i) for i in outside], "top_target_positive_contributors": [{"index": int(i), "value": float(contrib[i])} for i in order[-10:][::-1]], "top_target_negative_contributors": [{"index": int(i), "value": float(contrib[i])} for i in order[:10]], "target_logit_positive_contributor_indices": [int(i) for i in np.where(contrib > 0)[0]]})
    return {"trigger_file": str(trigger_path), "training_count": len(train), "feature_dimension": 348, "sklearn_classes": classifier.classes_.tolist(), "decision_function_class": orientation, "target_class": "hola_cauco", "target_class_index": target, "coefficient_orientation": "hola_cauco", "records": out, "parity": {"max_probability_difference": max((r["absolute_probability_difference"] for r in out), default=None), "max_target_logit_difference": max((r["absolute_target_logit_difference"] for r in out), default=None), "same_near_certain_positive": all(r["python_probability"] >= .999 for r in out) and all(r["coreml_probability"] >= .999 for r in out)}}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path("wake-model/dataset")); parser.add_argument("--live-root", type=Path); parser.add_argument("--runtime-trigger", type=Path, help="saved three-record runtime audit JSON"); parser.add_argument("--output", type=Path); args = parser.parse_args()
    result = audit_runtime(args.root, args.runtime_trigger, args.live_root) if args.runtime_trigger else audit(args.root, args.live_root); payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.write_text(payload)
    print(payload, end="")


if __name__ == "__main__": main()
