import json,sys,wave
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from train_calibrated_temporal import cv_folds,run,summary
def wav(p,hz):
    p.parent.mkdir(parents=True,exist_ok=True); x=(.2*32767*np.sin(2*np.pi*hz*np.arange(3200)/16000)).astype('<i2')
    with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(x.tobytes())
def test_cv_fold_calculation_and_failure():
    assert cv_folds(['target']*12+['non_target']*13)==3
    with pytest.raises(ValueError):cv_folds(['target','non_target','non_target'])
def test_metrics_and_deterministic_calibration_artifacts(tmp_path):
    rows=[]
    training=[('target','train',1200),('target','train',1100),('target','train',1300),('target','train',1250),('target','train',1150),('target','train',1350),('target','train',1280),('non_target','train',200),('non_target','train',300),('non_target','train',600),('non_target','train',250),('non_target','train',350),('non_target','train',550),('non_target','train',500)]
    for i,(label,split,hz) in enumerate(training+[('target','validation',1200),('non_target','validation',200),('non_target','validation',600)]):
        rid=f'r{i}';wav(tmp_path/'audio'/f'{rid}.wav',hz);rows.append({'recording_id':rid,'label':'target' if label=='target' else 'background','split':split,'relative_path':f'audio/{rid}.wav','phrase':'Hola Cauco' if label=='target' else ''})
    (tmp_path/'metadata').mkdir();(tmp_path/'metadata/recordings.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    # Seven samples per train class make the deterministic nested six-fold path valid.
    a=run(tmp_path,tmp_path/'out');b=run(tmp_path,tmp_path/'out2');assert a==b and (tmp_path/'out/results.json').exists();assert summary(['target','non_target'],[.8,.2])['brier_score']==pytest.approx(.04)
