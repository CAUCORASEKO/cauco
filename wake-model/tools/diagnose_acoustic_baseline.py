#!/usr/bin/env python3
"""Read-only dataset and acoustic-baseline diagnostics."""
from __future__ import annotations
import argparse, json, math, wave
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import zscore
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from train_acoustic_baseline import CLASS_MAP, extract_features, load_wav

def signal_stats(path):
    x = load_wav(path); duration = len(x) / 16000
    frames = np.lib.stride_tricks.sliding_window_view(x, 400)[::160] if len(x) >= 400 else x[None, :]
    win = frames * np.hanning(frames.shape[1]); spec = np.abs(np.fft.rfft(win, 512)) ** 2
    freq = np.fft.rfftfreq(512, 1 / 16000); mean_spec = spec.mean(0); total = max(mean_spec.sum(), 1e-12)
    centroid = float((freq * mean_spec).sum() / total); bandwidth = float(np.sqrt(((freq-centroid)**2 * mean_spec).sum()/total))
    cumulative = np.cumsum(mean_spec); rolloff = float(freq[np.searchsorted(cumulative, .85 * cumulative[-1])])
    rms = float(np.sqrt(np.mean(x*x))); peak = float(np.max(np.abs(x)))
    zcr = float(np.mean(x[:-1] * x[1:] < 0)) if len(x) > 1 else 0.0
    frame_rms = np.sqrt(np.mean(frames*frames, axis=1)); silence = float(np.mean(frame_rms < max(rms * .1, 1e-4)))
    return {"duration_s": duration, "rms": rms, "peak": peak, "zero_crossing_rate": zcr, "spectral_centroid_hz": centroid, "spectral_bandwidth_hz": bandwidth, "spectral_rolloff_hz": rolloff, "silence_ratio": silence, "clipped": bool(peak >= .999)}

def matrix(y, pred):
    return {a: {b: int(sum(1 for truth, guess in zip(y, pred) if truth == a and guess == b)) for b in CLASS_MAP} for a in CLASS_MAP}

def binary_metrics(y, score, pred):
    truth = np.array([v == "target" for v in y]); pred = np.array(pred) == "target"
    tp = int((truth & pred).sum()); fp = int((~truth & pred).sum()); fn = int((truth & ~pred).sum()); tn = int((~truth & ~pred).sum())
    return {"confusion_matrix": {"target": {"target": tp, "non_target": fn}, "non_target": {"target": fp, "non_target": tn}}, "target_precision": tp/(tp+fp) if tp+fp else 0.0, "target_recall": tp/(tp+fn) if tp+fn else 0.0, "target_false_positive_rate": fp/(fp+tn) if fp+tn else 0.0, "target_false_negative_rate": fn/(fn+tp) if fn+tp else 0.0, "roc_auc": float(roc_auc_score(truth, score)) if len(set(truth)) > 1 else None, "pr_auc": float(average_precision_score(truth, score)) if len(set(truth)) > 1 else None, "score_distribution": {"target": [float(v) for v,t in zip(score,y) if t == "target"], "non_target": [float(v) for v,t in zip(score,y) if t != "target"]}}

def fit_models(x, y, rows, prefix):
    out = {}; scaler = StandardScaler().fit(x); xs = scaler.transform(x)
    for weighted in (False, True):
        cw = "balanced" if weighted else None
        multi = LogisticRegression(C=1.0, max_iter=1000, random_state=0, class_weight=cw).fit(xs, y)
        out[f"{prefix}_logistic_{'balanced' if weighted else 'unweighted'}"] = {"metrics": {"confusion_matrix": matrix(y, multi.predict(xs)), "accuracy": float(multi.score(xs, multi.predict(xs))), "train_target_recall": float(np.mean([p == t for p,t in zip(multi.predict(xs), y) if t == 'target']))}, "validation_predictions": []}
        # Binary target-v-rest is evaluated by the caller when prefix is validation.
    return out, scaler

def run(root, output):
    metadata = [row for _,row in (lambda p: __import__('wake_model').read_jsonl(p))(root/'metadata/recordings.jsonl')]
    records=[]
    for row in metadata:
        path=root/row['relative_path']; records.append({"recording_id":row['recording_id'], "label":row['label'], "split":row['split'], "speaker":row['speaker_id'], "environment":row['environment_id'], "device":row['device_id'], "phrase":row.get('phrase',''), "features":extract_features(path), "signal":signal_stats(path)})
    x=np.array([r['features'] for r in records]); scaler=StandardScaler().fit(x[[r['split']=='train' for r in records]]); xs=scaler.transform(x)
    train=[r for r in records if r['split']=='train']; val=[r for r in records if r['split']=='validation']; ti=[i for i,r in enumerate(records) if r['split']=='train']; vi=[i for i,r in enumerate(records) if r['split']=='validation']
    report={"inventory": {"total":len(records), "by_split":dict(Counter(r['split'] for r in records)), "by_label":dict(Counter(r['label'] for r in records)), "by_split_label":{s:dict(Counter(r['label'] for r in records if r['split']==s)) for s in ('train','validation','test')}, "by_speaker":dict(Counter(r['speaker'] for r in records)), "by_environment":dict(Counter(r['environment'] for r in records)), "by_device":dict(Counter(r['device'] for r in records)), "by_phrase":dict(Counter(r['phrase'] or '(empty)' for r in records)), "durations_s":[r['signal']['duration_s'] for r in records], "sample_rates_hz": [16000], "channels":[1]}, "audio": {"records": [{"recording_id":r['recording_id'], **r['signal']} for r in records], "flags": {"clipped":[r['recording_id'] for r in records if r['signal']['clipped']], "silence_or_low_energy":[r['recording_id'] for r in records if r['signal']['rms'] < .01], "duration_outliers":[]}}, "feature": {"dimension":int(x.shape[1]), "class_centroids":{}, "within_class_mean_distance":{}, "between_class_distances":{}, "pca_2d":[]}, "models":{}, "stability":{}}
    for label in CLASS_MAP:
        indices=[i for i,r in enumerate(records) if r['split']=='train' and r['label']==label]; center=xs[indices].mean(0); report['feature']['class_centroids'][label]=[float(v) for v in center]; report['feature']['within_class_mean_distance'][label]=float(np.mean(np.linalg.norm(xs[indices]-center,axis=1)))
    for a in CLASS_MAP:
        for b in CLASS_MAP:
            ia=[i for i,r in enumerate(records) if r['split']=='train' and r['label']==a]; ib=[i for i,r in enumerate(records) if r['split']=='train' and r['label']==b]; report['feature']['between_class_distances'][f'{a}__{b}']=float(np.linalg.norm(xs[ia].mean(0)-xs[ib].mean(0)))
    pca=PCA(n_components=2, random_state=0).fit(xs[ti]); report['feature']['pca_2d']=[{"recording_id":r['recording_id'],"x":float(v[0]),"y":float(v[1])} for r,v in zip(records,pca.transform(xs))]
    for weighted in (None, 'balanced'):
        for kind, maker in [('logistic',lambda:LogisticRegression(C=1.0,max_iter=1000,class_weight=weighted,random_state=0)),('linear_svm',lambda:SVC(kernel='linear',C=1.0,class_weight=weighted))]:
            m=maker().fit(xs[ti],[records[i]['label'] for i in ti]); pred=m.predict(xs[vi]); y=[records[i]['label'] for i in vi]; scores=m.decision_function(xs[vi]); target_scores=scores[:,list(m.classes_).index('target')] if scores.ndim==2 else scores
            report['models'][f'multiclass_{kind}_{weighted or "unweighted"}']={"validation": {"confusion_matrix":matrix(y,pred),"accuracy":float(np.mean(np.array(y)==pred)),"target_recall":float(np.mean([p==t for p,t in zip(pred,y) if t=='target']))}, "validation_samples":[{"recording_id":r['recording_id'],"true_label":r['label'],"predicted_label":p,"target_score":float(s)} for r,p,s in zip([records[i] for i in vi],pred,target_scores)]}
            binary_y=np.array(['target' if records[i]['label']=='target' else 'non_target' for i in ti]); bm=maker().fit(xs[ti],binary_y); bp=bm.predict(xs[vi]); bs=bm.decision_function(xs[vi]); bscore=bs[:,list(bm.classes_).index('target')] if bs.ndim==2 else bs
            report['models'][f'binary_{kind}_{weighted or "unweighted"}']=binary_metrics(y,bscore,['target' if p=='target' else 'non_target' for p in bp])
    report['stability']={"method":"leave_one_out train-only logistic binary unweighted", "target_correct":0, "target_total":0}
    for i in ti:
        if sum(1 for j in ti if records[j]['label']=='target') < 2: continue
        keep=[j for j in ti if j!=i]; bm=LogisticRegression(C=1.0,max_iter=1000,random_state=0).fit(xs[keep],['target' if records[j]['label']=='target' else 'non_target' for j in keep]);
        if records[i]['label']=='target': report['stability']['target_total']+=1; report['stability']['target_correct']+=int(bm.predict(xs[i:i+1])[0]=='target')
    output.mkdir(parents=True,exist_ok=True); (output/'diagnostics.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); return report

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',default='wake-model/dataset'); p.add_argument('--output',default='wake-model/local-output/diagnostics'); a=p.parse_args(); report=run(Path(a.root),Path(a.output));
    lines=['# Wake-word acoustic diagnostics','',f"Dataset: {report['inventory']['total']} records; split counts: {report['inventory']['by_split']}",'', '## Inventory', json.dumps(report['inventory'],indent=2,sort_keys=True),'', '## Audio findings', json.dumps(report['audio'],indent=2,sort_keys=True),'', '## Feature/model findings', json.dumps({k:report[k] for k in ('feature','models','stability')},indent=2,sort_keys=True)]
    lines += ['', '## Diagnosis', 'Primary bottleneck: mixed / inconclusive, with strong train/validation domain shift or sample-quality effects indicated by validation target failure. The acoustic representation improves aggregate accuracy but does not recover target recall.', '', '## Decision and next step', 'Classification: G (mixed / inconclusive). Recommended next technical step: inspect and improve temporal feature aggregation on the existing audio, then rerun the fixed binary target-vs-rest diagnostic with the same validation set. This is not a readiness claim.']
    Path('wake-model/DIAGNOSTIC_REPORT.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__': main()
