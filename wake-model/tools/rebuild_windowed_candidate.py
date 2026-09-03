#!/usr/bin/env python3
"""Development-only one-second candidate rebuild.

Positive examples must be supplied as explicitly aligned one-second WAVs in a
manifest. Existing target recordings are never windowed or relabeled here.
"""
from __future__ import annotations

import argparse, json
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import audit_windowed_classifier as audit

WINDOW, HOP, THRESHOLD, CONSECUTIVE = 16_000, 2_560, .85, 3

def negative_windows(root: Path):
    out = []
    for meta in sorted((root / "metadata").glob("*.json")):
        record = json.loads(meta.read_text()); samples = audit.load_audio(root / "audio" / f"{record['recording_id']}.wav")
        for start in range(0, max(0, len(samples) - WINDOW + 1), HOP):
            out.append({"source_recording": record["recording_id"], "category": record.get("category", "unknown"), "label": "non_target", "start_sample": start, "features": audit.features(samples[start:start + WINDOW])})
    return out

def aligned_positives(manifest: Path):
    rows = []
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        item = json.loads(line); path = Path(item["path"]); samples = audit.load_audio(path)
        if len(samples) != WINDOW: raise ValueError(f"aligned positive must be exactly 16000 samples: {path}")
        rows.append({"source_recording": item.get("source_recording", path.stem), "category": "aligned_positive", "label": "target", "start_sample": 0, "features": audit.features(samples)})
    return rows

def discover_aligned_positive(root: Path):
    rows = []
    for meta in sorted((root / "metadata").glob("*.json")):
        item = json.loads(meta.read_text()); path = root / item["audio_file"]
        valid = item.get("label") == "hola_cauco" and item.get("sample_rate") == 16000 and item.get("channels") == 1 and item.get("exact_samples") == 16000 and path.is_file()
        if valid:
            try: valid = len(audit.load_audio(path)) == WINDOW
            except ValueError: valid = False
        if valid: rows.append(item)
    return rows

def main():
    p = argparse.ArgumentParser(); p.add_argument("--live-root", type=Path, default=Path("wake-model/live-negative")); p.add_argument("--positive-root", type=Path, default=Path("wake-model/windowed-positive")); p.add_argument("--positive-manifest", type=Path); p.add_argument("--output", type=Path, default=Path("wake-model/local-output/windowed-candidate")); args = p.parse_args()
    if not args.positive_manifest:
        rows = discover_aligned_positive(args.positive_root); rows.sort(key=lambda r: (r.get("session_id", ""), r.get("source_recording_id", ""))); by_session = {s: sum(r.get("session_id") == s for r in rows) for s in ("session_001", "session_002")}; holdout = [r for r in rows if r.get("session_id") == "session_002"][-3:] if len(rows) >= 15 else []; validation_ids = [r["source_recording_id"] for r in holdout]; train_ids = [r["source_recording_id"] for r in rows if r["source_recording_id"] not in validation_ids]; print(json.dumps({"valid_aligned_positives": len(rows), "by_session": by_session, "missing": max(0, 15-len(rows)), "minimum_train_validation_satisfied": len(rows) >= 15, "minimum_train": 12, "minimum_validation": 3, "deterministic_holdout": {"training_count": len(train_ids), "validation_count": len(validation_ids), "training_source_recordings": train_ids, "validation_source_recordings": validation_ids, "source_recordings_disjoint": not set(train_ids) & set(validation_ids)}, "training_not_run": True}, indent=2, sort_keys=True)); return
    positives, negatives = aligned_positives(args.positive_manifest), negative_windows(args.live_root)
    if not positives: raise SystemExit("no aligned positive examples supplied")
    sources = sorted({r["source_recording"] for r in negatives}); validation_sources = set(sources[::5]); train = positives + [r for r in negatives if r["source_recording"] not in validation_sources]; validation = [r for r in negatives if r["source_recording"] in validation_sources]
    x = np.asarray([r["features"] for r in train]); y = np.asarray([r["label"] for r in train]); scaler = StandardScaler().fit(x); model = LogisticRegression(C=1, max_iter=1000, random_state=0).fit(scaler.transform(x), y); target = list(model.classes_).index("target")
    def score(rows): return [float(model.predict_proba(scaler.transform(np.asarray(r["features"]).reshape(1,-1)))[0,target]) for r in rows]
    def fires(rows):
        result=[]
        for source in sorted({r["source_recording"] for r in rows}):
            values=[r for r in rows if r["source_recording"]==source]; run=best=0; first=None
            for r,v in zip(values,score(values)):
                run=run+1 if v>=THRESHOLD else 0; best=max(best,run); first=first if first is not None else (r["start_sample"]/16000 if run>=CONSECUTIVE else None)
            result.append({"source_recording":source,"fires":first is not None,"first_activation_s":first,"max_streak":best})
        return result
    args.output.mkdir(parents=True, exist_ok=True)
    report={"semantics":{"window_samples":WINDOW,"hop_samples":HOP,"threshold":THRESHOLD,"consecutive":CONSECUTIVE},"sklearn_classes":model.classes_.tolist(),"train_source_recordings":sorted({r["source_recording"] for r in train}),"validation_source_recordings":sorted(validation_sources),"train_windows":len(train),"validation_windows":len(validation),"positive_windows":len(positives),"negative_windows":len(negatives),"validation_scores":score(validation),"validation_fires":fires(validation),"note":"Candidate artifacts are development-only; Core ML export is intentionally not performed."}
    (args.output/"report.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n"); print(json.dumps(report, indent=2, sort_keys=True))
if __name__ == "__main__": main()
