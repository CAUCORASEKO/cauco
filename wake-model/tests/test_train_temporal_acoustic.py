import json, sys, wave
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from train_temporal_acoustic import frame_features, temporal_features, run

def wav(path, hz=440, seconds=.2):
    path.parent.mkdir(parents=True,exist_ok=True); x=(.2*32767*np.sin(2*np.pi*hz*np.arange(int(16000*seconds))/16000)).astype('<i2')
    with wave.open(str(path),'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(x.tobytes())
def row(root,i,label,split,hz):
    wav(root/'audio'/f'{i}.wav',hz); return {'recording_id':i,'label':label,'split':split,'relative_path':f'audio/{i}.wav','phrase':'Hola Cauco' if label=='target' else ''}
def manifest(root, rows):
    (root/'metadata').mkdir(); (root/'metadata/recordings.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
def test_temporal_segmentation_deltas_and_normalization_are_deterministic(tmp_path):
    p=tmp_path/'x.wav'; wav(p); a=frame_features(p); b=temporal_features(p); assert len(a)==4 and b.shape==(4*87,); np.testing.assert_array_equal(b,temporal_features(p)); assert not np.array_equal(b,temporal_features(p,True))
def test_short_clip_has_fixed_features(tmp_path):
    p=tmp_path/'short.wav'; wav(p,seconds=.005); assert temporal_features(p).shape==(348,)
def test_binary_artifacts_and_evaluation_are_deterministic(tmp_path):
    rows=[row(tmp_path,'trt','target','train',1200),row(tmp_path,'trn','background','train',200),row(tmp_path,'trh','hard_negative_speech','train',600),row(tmp_path,'vat','target','validation',1200),row(tmp_path,'van','background','validation',200),row(tmp_path,'vah','hard_negative_speech','validation',600)]; manifest(tmp_path,rows); out=tmp_path/'out'; first=run(tmp_path,out); second=run(tmp_path,tmp_path/'out2'); assert first['feature_config']['feature_dimension']==348 and first['variants']==second['variants']; assert (out/'results.json').exists() and (out/'feature_config.json').exists()
