import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from wake_model import metrics, temporal, validate_dataset

FIELDS = {"recording_id","label","phrase","speaker_id","language","accent","environment_id","device_id","source_group","split","duration_ms","sample_rate_hz","channels","relative_path"}

def row(**changes):
    value = {"recording_id":"r1","label":"target","phrase":"Hola Cauco","speaker_id":"s1","language":"es","accent":"neutral","environment_id":"e1","device_id":"d1","source_group":"g1","split":"train","duration_ms":1000,"sample_rate_hz":16000,"channels":1,"relative_path":"audio/r1.wav"}
    value.update(changes); return value

def write_manifest(tmp_path, rows):
    path = tmp_path / "metadata"; path.mkdir(); (path / "recordings.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

def test_metrics_and_thresholds_are_deterministic():
    rows = [{"true_label":"target","target_probability":.9}, {"true_label":"background","target_probability":.8}, {"true_label":"background","target_probability":.1}]
    assert metrics(rows, .85) == {"threshold":.85,"tp":1,"fp":0,"tn":2,"fn":0,"precision":1.0,"recall":1.0,"false_positive_rate":0.0,"false_negative_rate":0.0}
    assert temporal([{"recording_id":"r","timestamp_ms":i,"target_probability":p} for i,p in enumerate([.9,.9,.9])], .8, 2)["activations"] == 1

def test_dataset_validator_rejects_unknown_label_and_traversal(tmp_path):
    write_manifest(tmp_path, [row(label="unknown"), row(recording_id="r2", relative_path="../secret.wav")])
    errors, _ = validate_dataset(tmp_path)
    assert any("invalid label" in e for e in errors); assert any("escapes" in e for e in errors)

def test_dataset_validator_detects_duplicate_and_leakage(tmp_path):
    write_manifest(tmp_path, [row(), row(recording_id="r2", split="test", source_group="g2")])
    errors, warnings = validate_dataset(tmp_path)
    assert any("protected speaker" in w for w in warnings)

def test_dataset_validator_detects_duplicate_ids(tmp_path):
    write_manifest(tmp_path, [row(), row(label="background")])
    errors, _ = validate_dataset(tmp_path)
    assert any("duplicate" in e for e in errors)
