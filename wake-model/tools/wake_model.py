#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, math, wave
from collections import Counter
from pathlib import Path

LABELS = {"target", "hard_negative_speech", "background"}; SPLITS = {"train", "validation", "test"}
FIELDS = {"recording_id","label","phrase","speaker_id","language","accent","environment_id","device_id","source_group","split","duration_ms","sample_rate_hz","channels","relative_path"}

def read_jsonl(path):
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try: yield n, json.loads(line)
                except json.JSONDecodeError as e: raise ValueError(f"{path}:{n}: malformed JSON") from e

def validate_audio(path, item):
    try:
        with wave.open(str(path), "rb") as w: rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    except (OSError, wave.Error) as e: return [f"unsupported audio: {path.name}"]
    errors = []
    if (rate, channels, width) != (16000, 1, 2): errors.append(f"audio format mismatch: {path.name}")
    duration = round(frames * 1000 / rate) if rate else 0
    if not 500 <= duration <= 3000: errors.append(f"audio duration out of range: {path.name}")
    if item.get("sample_rate_hz") != rate or item.get("channels") != channels or abs(item.get("duration_ms", -1) - duration) > 20: errors.append(f"audio metadata mismatch: {path.name}")
    return errors

def validate_dataset(root):
    meta = root / "metadata" / "recordings.jsonl"; errors=[]; warnings=[]; rows=[]; ids=set(); groups={}
    if not meta.exists(): return ["missing metadata"], []
    for line, item in read_jsonl(meta):
        if not isinstance(item, dict) or set(item) != FIELDS: errors.append(f"line {line}: metadata fields invalid"); continue
        if item["recording_id"] in ids: errors.append(f"line {line}: duplicate recording_id"); continue
        ids.add(item["recording_id"]); rows.append(item)
        if item["label"] not in LABELS: errors.append(f"line {line}: invalid label")
        if item["split"] not in SPLITS: errors.append(f"line {line}: invalid split")
        rel = Path(item["relative_path"])
        if rel.is_absolute() or ".." in rel.parts: errors.append(f"line {line}: path escapes dataset root")
        else:
            path = root / rel
            if not path.is_file(): errors.append(f"line {line}: missing audio")
            elif path.suffix.lower() != ".wav": errors.append(f"line {line}: unsupported audio container")
            else: errors.extend(validate_audio(path, item))
        groups.setdefault(item["source_group"], set()).add(item["split"])
    for group, splits in groups.items():
        if len(splits) > 1: errors.append(f"source-group leakage: {group}")
    for key in ("speaker_id", "environment_id", "device_id"):
        values={}
        for row in rows: values.setdefault(row[key], set()).add(row["split"])
        for value, splits in values.items():
            if "test" in splits and ("train" in splits or "validation" in splits): warnings.append(f"protected {key} overlap: {value}")
    counts=Counter(row["label"] for row in rows)
    for label in LABELS:
        if not counts[label]: errors.append(f"empty class: {label}")
    if counts and max(counts.values()) > 10 * max(1, min(counts.values())): warnings.append("suspicious class imbalance")
    return sorted(set(errors)), sorted(set(warnings))

def metrics(rows, threshold):
    tp=fp=tn=fn=0
    for row in rows:
        positive = row["target_probability"] >= threshold; actual = row["true_label"] == "target"
        if positive and actual: tp+=1
        elif positive: fp+=1
        elif actual: fn+=1
        else: tn+=1
    return {"threshold": threshold, "tp":tp,"fp":fp,"tn":tn,"fn":fn,"precision":tp/(tp+fp) if tp+fp else 0.0,"recall":tp/(tp+fn) if tp+fn else 0.0,"false_positive_rate":fp/(fp+tn) if fp+tn else 0.0,"false_negative_rate":fn/(fn+tp) if fn+tp else 0.0}

def temporal(rows, threshold, consecutive):
    activations=0; active=False; streak=0
    for row in sorted(rows, key=lambda x:(x.get("recording_id",""), x.get("timestamp_ms",0))):
        if row["target_probability"] >= threshold: streak += 1
        else: streak=0; active=False
        if streak >= consecutive and not active: activations += 1; active=True
    return {"threshold":threshold,"consecutive":consecutive,"activations":activations}

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command", required=True)
    d=sub.add_parser("validate-dataset"); d.add_argument("root")
    t=sub.add_parser("threshold"); t.add_argument("predictions"); t.add_argument("--thresholds", required=True)
    x=sub.add_parser("temporal"); x.add_argument("predictions"); x.add_argument("--threshold", type=float, required=True); x.add_argument("--consecutive", type=int, default=2)
    m=sub.add_parser("validate-model-manifest"); m.add_argument("manifest")
    a=p.parse_args()
    if a.command=="validate-dataset":
        e,w=validate_dataset(Path(a.root)); print("errors:", *e, sep="\n- "); print("warnings:", *w, sep="\n- "); raise SystemExit(1 if e else 0)
    if a.command in {"threshold","temporal"}:
        rows=[r for _,r in read_jsonl(Path(a.predictions))]
        out=[metrics(rows,float(v)) for v in a.thresholds.split(",")] if a.command=="threshold" else [temporal(rows,a.threshold,a.consecutive)]
        print(json.dumps(out, sort_keys=True, indent=2)); return
    value=json.loads(Path(a.manifest).read_text(encoding="utf-8")); allowed={"model_id","version","target_label","other_labels","audio_input","deployment_target","sha256"}
    if not isinstance(value,dict) or set(value)-allowed or value.get("target_label")!="hola_cauco": raise SystemExit("invalid model manifest")
    print("model manifest: valid")

if __name__ == "__main__": main()
