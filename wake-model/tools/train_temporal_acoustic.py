#!/usr/bin/env python3
"""Offline temporal log-mel/MFCC target-vs-rest experiment."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from scipy.fft import dct
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from train_acoustic_baseline import CLASS_MAP, FRAME_LENGTH, HOP_LENGTH, FFT_SIZE, MEL_BANDS, MFCC_COUNT, load_wav, mel_filterbank
from wake_model import read_jsonl

REGIONS = 4

def frame_features(path):
    x = load_wav(path)
    if len(x) < FRAME_LENGTH: x = np.pad(x, (0, FRAME_LENGTH-len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, FRAME_LENGTH)[::HOP_LENGTH]
    win = frames * np.hanning(FRAME_LENGTH)
    power = np.abs(np.fft.rfft(win, FFT_SIZE, axis=1)) ** 2 / FFT_SIZE
    logmel = np.log(np.maximum(power @ mel_filterbank().T, 1e-12))
    mfcc = dct(logmel, type=2, axis=1, norm='ortho')[:, :MFCC_COUNT]
    delta = np.gradient(mfcc, axis=0) if len(mfcc) > 1 else np.zeros_like(mfcc)
    delta2 = np.gradient(delta, axis=0) if len(delta) > 1 else np.zeros_like(delta)
    return logmel, mfcc, delta, delta2

def temporal_features(path, normalize=False):
    logmel, mfcc, delta, delta2 = frame_features(path)
    if normalize: logmel = logmel - logmel.mean(axis=0, keepdims=True); mfcc = mfcc - mfcc.mean(axis=0, keepdims=True)
    chunks = np.array_split(np.arange(len(logmel)), REGIONS)
    result=[]
    for indices in chunks:
        if len(indices) == 0: indices=np.array([len(logmel)-1])
        result.extend(logmel[indices].mean(0)); result.extend(logmel[indices].std(0)); result.extend(mfcc[indices].mean(0)); result.extend(delta[indices].mean(0)); result.extend(delta2[indices].mean(0))
    return np.asarray(result, dtype=np.float64)

def load_records(root, normalize):
    return [{**row, 'features': temporal_features(root/row['relative_path'], normalize)} for _,row in read_jsonl(root/'metadata/recordings.jsonl')]

def metrics(y, score, pred):
    truth=np.asarray([v=='target' for v in y]); positive=np.asarray([v=='target' for v in pred]); tp=int((truth&positive).sum()); fp=int((~truth&positive).sum()); fn=int((truth&~positive).sum()); tn=int((~truth&~positive).sum())
    return {'confusion_matrix':{'target':{'target':tp,'non_target':fn},'non_target':{'target':fp,'non_target':tn}},'accuracy':float(np.mean(truth==positive)),'target_precision':tp/(tp+fp) if tp+fp else 0.0,'target_recall':tp/(tp+fn) if tp+fn else 0.0,'target_false_positive_rate':fp/(fp+tn) if fp+tn else 0.0,'target_false_negative_rate':fn/(fn+tp) if fn+tp else 0.0,'roc_auc':float(roc_auc_score(truth,score)),'pr_auc':float(average_precision_score(truth,score))}

def score_for(model, x):
    value=model.predict_proba(x)[:, list(model.classes_).index('target')] if hasattr(model,'predict_proba') else model.decision_function(x)
    return value[:,list(model.classes_).index('target')] if getattr(value,'ndim',1)==2 else value

def run(root, output):
    all_variants={}; target_analysis={}
    for normalized in (False, True):
        records=load_records(root, normalized); train=[r for r in records if r['split']=='train']; val=[r for r in records if r['split']=='validation']; xtr=np.array([r['features'] for r in train]); xva=np.array([r['features'] for r in val]); scaler=StandardScaler().fit(xtr); xtr=scaler.transform(xtr); xva=scaler.transform(xva); ytr=np.array(['target' if r['label']=='target' else 'non_target' for r in train]); yva=np.array(['target' if r['label']=='target' else 'non_target' for r in val]); key='utterance_normalized' if normalized else 'raw'
        for classifier in ('logistic','linear_svm'):
            for balanced in (False,True):
                model=(LogisticRegression(C=1,max_iter=1000,random_state=0,class_weight='balanced' if balanced else None) if classifier=='logistic' else SVC(kernel='linear',C=1,class_weight='balanced' if balanced else None)).fit(xtr,ytr)
                val_score=score_for(model,xva); train_pred=model.predict(xtr); val_pred=model.predict(xva); name=f'{key}_{classifier}_{"balanced" if balanced else "unweighted"}'
                all_variants[name]={'train':metrics(ytr,score_for(model,xtr),train_pred),'validation':metrics(yva,val_score,val_pred),'validation_scores':[{'recording_id':r['recording_id'],'label':r['label'],'phrase':r.get('phrase',''),'score':float(s),'predicted':p} for r,s,p in zip(val,val_score,val_pred)]}
                if classifier=='logistic': all_variants[name]['thresholds']=[{'threshold':t,'target_recall':float(np.mean((val_score>=t)[yva=='target'])),'false_positive_rate':float(np.mean((val_score>=t)[yva!='target'])),'activations':[r['recording_id'] for r,s in zip(val,val_score) if s>=t]} for t in (.30,.40,.50,.65,.80)]
        # nearest train examples for each target validation utterance
        for r,v in zip(val,xva):
            distances=np.linalg.norm(xtr-v,axis=1); order=np.argsort(distances); target_analysis[r['recording_id']]={'phrase':r.get('phrase',''),'environment':r.get('environment_id'),'duration_ms':r.get('duration_ms'),'nearest_train_target':min((float(distances[i]),train[i]['recording_id']) for i in order if train[i]['label']=='target'),'nearest_train_non_target':min((float(distances[i]),train[i]['recording_id']) for i in order if train[i]['label']!='target')}
    result={'feature_config':{'sample_rate_hz':16000,'frame_length_samples':FRAME_LENGTH,'hop_length_samples':HOP_LENGTH,'fft_size':FFT_SIZE,'mel_bands':MEL_BANDS,'mfcc_count':MFCC_COUNT,'regions':REGIONS,'per_region_values':MEL_BANDS*2+MFCC_COUNT+MFCC_COUNT*2,'feature_dimension':REGIONS*(MEL_BANDS*2+MFCC_COUNT*3),'delta':'np.gradient(MFCC, axis=time)','normalization':'subtract per-utterance mean log-mel and MFCC'},'train_count':25,'validation_count':11,'variants':all_variants,'validation_target_analysis':target_analysis,'comparison':{'previous_logistic_roc_auc':0.7083333333,'previous_svm_roc_auc':0.6666666667,'previous_validation_target_recall':0.0,'previous_train_loo_target_correct':'9/12'}}
    output.mkdir(parents=True,exist_ok=True); (output/'results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); (output/'feature_config.json').write_text(json.dumps(result['feature_config'],indent=2,sort_keys=True)+'\n'); return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',default='wake-model/dataset'); p.add_argument('--output',default='wake-model/local-output/temporal-acoustic/'); a=p.parse_args(); print(json.dumps(run(Path(a.root),Path(a.output)),indent=2,sort_keys=True))
if __name__=='__main__': main()
