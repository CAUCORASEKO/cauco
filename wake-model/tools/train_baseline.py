#!/usr/bin/env python3
"""Dependency-free, deterministic pilot baseline; not a production detector."""
from __future__ import annotations
import argparse, json, math, struct, wave
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wake_model import LABELS, read_jsonl

CLASS_MAP = ("background", "hard_negative_speech", "target")

def features(path: Path) -> list[float]:
    try:
        with wave.open(str(path), "rb") as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2): raise ValueError("unsupported WAV format")
            raw = w.readframes(w.getnframes())
    except (OSError, EOFError, wave.Error) as exc: raise ValueError("malformed WAV") from exc
    if not raw: raise ValueError("empty WAV")
    samples = [v / 32768.0 for v in struct.unpack("<" + "h" * (len(raw) // 2), raw)]
    rms = math.sqrt(sum(v*v for v in samples) / len(samples)); zc = sum(a*b < 0 for a,b in zip(samples, samples[1:])) / len(samples)
    bins=[]; step=max(1, len(samples)//256)
    for k in range(1, 17):
        re=im=0.0
        for i in range(0, len(samples), step):
            angle=2*math.pi*k*i/len(samples); re += samples[i]*math.cos(angle); im -= samples[i]*math.sin(angle)
        bins.append(math.sqrt(re*re+im*im)/max(1, len(samples)//step))
    return [rms, zc] + bins

def load_split(root: Path, split: str):
    path=root/"metadata"/"recordings.jsonl"
    rows=[row for _,row in read_jsonl(path) if row.get("split") == split]
    loaded=[]
    for row in rows:
        audio=root/row["relative_path"]
        if not audio.is_file(): raise ValueError(f"missing audio for {row.get('recording_id','unknown')}")
        loaded.append((row, features(audio)))
    return loaded

def evaluate(rows, centroids):
    matrix={actual:{pred:0 for pred in CLASS_MAP} for actual in CLASS_MAP}
    for row, vector in rows:
        pred=min(CLASS_MAP, key=lambda label: sum((a-b)**2 for a,b in zip(vector, centroids[label])))
        matrix[row["label"]][pred]+=1
    return matrix

def main():
    p=argparse.ArgumentParser(); p.add_argument("--root", required=True); p.add_argument("--output", required=True); a=p.parse_args(); root=Path(a.root); out=Path(a.output)
    train=load_split(root,"train"); validation=load_split(root,"validation"); test=load_split(root,"test")
    if not train: raise SystemExit("training split is empty")
    counts=Counter(row["label"] for row,_ in train); missing=[label for label in CLASS_MAP if not counts[label]]
    if missing: raise SystemExit("training classes missing: " + ", ".join(missing))
    centroids={label:[sum(v[i] for row,v in train if row["label"]==label)/counts[label] for i in range(len(train[0][1]))] for label in CLASS_MAP}
    out.mkdir(parents=True, exist_ok=True); (out/"baseline.json").write_text(json.dumps({"model":"nearest_centroid","class_map":CLASS_MAP,"feature":"rms_zero_crossing_16_dft_bins","centroids":centroids},sort_keys=True,indent=2)+"\n")
    matrix=evaluate(validation,centroids); result={"train_count":len(train),"validation_count":len(validation),"test_count":len(test),"train_class_counts":dict(sorted(counts.items())),"test_evaluation":"available" if test else "test evaluation unavailable","validation_confusion_matrix":matrix}
    (out/"results.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n"); print(json.dumps(result,sort_keys=True,indent=2))

if __name__ == "__main__": main()
