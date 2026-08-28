import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from wake_model import metrics, temporal, validate_dataset
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from record_sample import record_sample
import wave
import subprocess

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

def test_recording_backend_writes_strict_metadata_without_personal_name(tmp_path, monkeypatch):
    def fake_run(output, duration):
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0" * 32000)
    monkeypatch.setattr("record_sample.time.sleep", lambda _: None)
    item = record_sample(tmp_path, "target", "Hola Cauco", "speaker_001", "room_001", "device_001", 2, recorder=fake_run)
    assert item["relative_path"].startswith("audio/rec_") and "speaker_001" not in item["recording_id"]
    assert not Path(item["relative_path"]).is_absolute()

@pytest.mark.parametrize("label,phrase", [("hard_negative_speech", "Hola Claudio"), ("background", "")])
def test_recording_metadata_supports_all_bounded_labels(tmp_path, monkeypatch, label, phrase):
    def fake(output, _duration):
        with wave.open(str(output), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0" * 16000)
    monkeypatch.setattr("record_sample.time.sleep", lambda _: None)
    item = record_sample(tmp_path, label, phrase, "speaker_001", "room_001", "device_001", 1, recorder=fake)
    assert item["label"] == label and item["phrase"] == phrase
    assert json.loads((tmp_path / "metadata/recordings.jsonl").read_text())["relative_path"] == item["relative_path"]

@pytest.mark.parametrize("duration", [0.49, 3.01])
def test_duration_bounds_reject_without_recording(tmp_path, duration):
    with pytest.raises(ValueError): record_sample(tmp_path, "target", "Hola Cauco", "s", "e", "d", duration, recorder=lambda *_: pytest.fail("recorder invoked"))

def test_recording_rejects_bad_label_duration_and_cleans_failed_output(tmp_path, monkeypatch):
    monkeypatch.setattr("record_sample.time.sleep", lambda _: None)
    with pytest.raises(ValueError): record_sample(tmp_path, "unknown", "", "s", "e", "d", 1, recorder=["fake"])
    with pytest.raises(ValueError): record_sample(tmp_path, "background", "noise", "s", "e", "d", 4, recorder=["fake"])
    with pytest.raises(RuntimeError): record_sample(tmp_path, "target", "Hola Cauco", "s", "e", "d", 1, recorder=lambda *_: (_ for _ in ()).throw(RuntimeError()))
    assert not list((tmp_path / "audio").glob("*.wav"))

def test_invalid_wav_and_metadata_write_failures_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr("record_sample.time.sleep", lambda _: None)
    def invalid(output, _): output.write_bytes(b"not wav")
    with pytest.raises(Exception): record_sample(tmp_path, "target", "Hola Cauco", "s", "e", "d", 1, recorder=invalid)
    assert not list((tmp_path / "audio").glob("*.wav")) and not (tmp_path / "metadata/recordings.jsonl").exists()
    def valid(output, _):
        with wave.open(str(output), "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0" * 16000)
    monkeypatch.setattr("record_sample.append_record", lambda *_: (_ for _ in ()).throw(OSError("secret path")))
    with pytest.raises(OSError): record_sample(tmp_path, "target", "Hola Cauco", "s", "e", "d", 1, recorder=valid)
    assert not list((tmp_path / "audio").glob("*.wav"))

def test_collision_does_not_overwrite_and_backend_is_fixed_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr("record_sample.time.sleep", lambda _: None)
    monkeypatch.setattr("record_sample.recording_id", lambda existing: "rec_fixed" if "rec_fixed" not in existing else (_ for _ in ()).throw(FileExistsError("collision")))
    def valid(output, _):
        with wave.open(str(output), "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0" * 16000)
    record_sample(tmp_path, "target", "Hola Cauco", "s", "e", "d", 1, recorder=valid)
    with pytest.raises(FileExistsError): record_sample(tmp_path, "target", "Hola Cauco", "s", "e", "d", 1, recorder=valid)
    source = Path(__file__).parents[1] / "tools/record_sample.py"
    text = source.read_text()
    assert "requests" not in text.lower() and "urllib" not in text and "http" not in text

def test_missing_ffmpeg_backend_is_bounded_and_safe(tmp_path, monkeypatch):
    monkeypatch.setattr("record_sample.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="recording failed"):
        record_sample(tmp_path, "target", "Hola Cauco", "s", "e", "d", 1, recorder=["/definitely/missing/ffmpeg"])
    assert not list((tmp_path / "audio").glob("*.wav"))

def test_gitignore_keeps_reusable_fixtures_visible():
    ignore = Path(__file__).parents[2] / ".gitignore"; text = ignore.read_text()
    assert "wake-model/dataset/audio/*.wav" in text and "wake-model/dataset/metadata/recordings.jsonl" in text
    assert "wake-model/tests/" not in text
