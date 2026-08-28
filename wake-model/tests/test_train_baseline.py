import json, struct, sys, wave
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from train_baseline import features, load_split

def wav(path, value=0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(struct.pack("<"+"h"*800, *([value]*800)))
def test_features_are_deterministic_and_splits_are_explicit(tmp_path):
    audio=tmp_path/"audio"; audio.mkdir(); wav(audio/"a.wav", 1000)
    meta=tmp_path/"metadata"; meta.mkdir(); base={"recording_id":"a","label":"target","phrase":"Hola Cauco","speaker_id":"s","language":"es","accent":"x","environment_id":"e","device_id":"d","source_group":"g","duration_ms":50,"sample_rate_hz":16000,"channels":1,"relative_path":"audio/a.wav"}
    (meta/"recordings.jsonl").write_text(json.dumps({**base,"split":"train"})+"\n"+json.dumps({**base,"recording_id":"b","split":"validation","relative_path":"audio/a.wav"})+"\n")
    assert features(audio/"a.wav") == features(audio/"a.wav") and len(load_split(tmp_path,"train")) == 1 and len(load_split(tmp_path,"validation")) == 1 and load_split(tmp_path,"test") == []
def test_malformed_wav_rejected(tmp_path):
    path=tmp_path/"bad.wav"; path.write_bytes(b"bad")
    with pytest.raises(ValueError): features(path)
