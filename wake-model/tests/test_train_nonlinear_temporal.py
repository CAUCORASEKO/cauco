import json,sys,wave
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from train_nonlinear_temporal import folds,run
def make(p,hz):
 p.parent.mkdir(parents=True,exist_ok=True);x=(.2*32767*np.sin(2*np.pi*hz*np.arange(3200)/16000)).astype('<i2')
 with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(x.tobytes())
def test_fold_validation():
 assert folds(['target']*12+['non_target']*13)==5
 with pytest.raises(ValueError):folds(['target','non_target'])
def test_fixed_models_deterministic_and_artifacts(tmp_path):
 rows=[]
 for i,(lab,split,hz) in enumerate([*([('target','train',1200),('target','train',1100),('target','train',1300)]*3),*([('background','train',200),('background','train',300),('background','train',600)]*3),('target','validation',1200),('background','validation',200)]):
  rid=f'r{i}';make(tmp_path/'audio'/f'{rid}.wav',hz);rows.append({'recording_id':rid,'label':lab,'split':split,'relative_path':f'audio/{rid}.wav','phrase':'Hola Cauco' if lab=='target' else ''})
 (tmp_path/'metadata').mkdir();(tmp_path/'metadata/recordings.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n');a=run(tmp_path,tmp_path/'out');b=run(tmp_path,tmp_path/'out2');assert a==b and set(a['models'])=={'mlp_8','mlp_16'} and (tmp_path/'out/results.json').exists()
