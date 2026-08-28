#!/usr/bin/env python3
"""Train-only cross-validated probability calibration diagnostics."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.svm import LinearSVC
from train_temporal_acoustic import load_records

THRESHOLDS=(.10,.20,.30,.40,.50,.65,.80,.90)

def cv_folds(labels):
    counts=np.bincount(np.asarray(labels)=='target')
    minimum=int(min(counts)) if len(counts)>1 else 0
    if minimum < 2: raise ValueError('calibration requires at least 2 samples per class')
    # Nested out-of-fold calibration needs each outer training fold to retain
    # enough samples for its own calibration folds; three is the conservative
    # valid choice for this tiny dataset.
    return min(3,minimum)

def summary(y, probabilities, predictions=None):
    y=np.asarray(y); truth=y=='target'; p=np.asarray(probabilities); pred=(p>=.5) if predictions is None else np.asarray(predictions)=='target'; tp=int((truth&pred).sum()); fp=int((~truth&pred).sum()); fn=int((truth&~pred).sum()); tn=int((~truth&~pred).sum())
    return {'confusion_matrix':{'target':{'target':tp,'non_target':fn},'non_target':{'target':fp,'non_target':tn}},'accuracy':float(np.mean(truth==pred)),'target_precision':tp/(tp+fp) if tp+fp else 0.,'target_recall':tp/(tp+fn) if tp+fn else 0.,'target_false_positive_rate':fp/(fp+tn) if fp+tn else 0.,'target_false_negative_rate':fn/(fn+tp) if fn+tp else 0.,'brier_score':float(brier_score_loss(truth,p)),'roc_auc':float(roc_auc_score(truth,p)),'pr_auc':float(average_precision_score(truth,p))}

def thresholds(y,p):
    y=np.asarray(y); truth=y=='target'; out=[]
    for t in THRESHOLDS:
        positive=p>=t; tp=truth&positive; fp=(~truth)&positive
        out.append({'threshold':t,'target_recall':float(tp.sum()/truth.sum()),'false_positive_rate':float(fp.sum()/(~truth).sum()),'precision':float(tp.sum()/positive.sum()) if positive.sum() else 0.,'activated_target_ids':[],'activated_hard_negative_ids':[],'activated_background_ids':[]})
    return out

def run(root, output):
    records=load_records(root,True); train=[r for r in records if r['split']=='train']; val=[r for r in records if r['split']=='validation']; xtr=np.array([r['features'] for r in train]); xva=np.array([r['features'] for r in val]); ytr=np.array(['target' if r['label']=='target' else 'non_target' for r in train]); yva=np.array(['target' if r['label']=='target' else 'non_target' for r in val]); folds=cv_folds(ytr)
    variants={}; cv=StratifiedKFold(n_splits=folds,shuffle=True,random_state=0)
    specs={'logistic':lambda cw:LogisticRegression(C=1,max_iter=1000,class_weight=cw,random_state=0),'linear_svm':lambda cw:LinearSVC(C=1,class_weight=cw,random_state=0)}
    for name,maker in specs.items():
        for weighted in (None,'balanced'):
            base=make_pipeline(StandardScaler(),maker(weighted)); cv_score=cross_val_predict(base,xtr,ytr,cv=cv,method='decision_function'); calibrated=CalibratedClassifierCV(estimator=base,method='sigmoid',cv=cv).fit(xtr,ytr); p=calibrated.predict_proba(xva)[:,list(calibrated.classes_).index('target')]; cv_prob=cross_val_predict(CalibratedClassifierCV(estimator=base,method='sigmoid',cv=cv),xtr,ytr,cv=cv,method='predict_proba')[:,1]; key=f'{name}_{weighted or "unweighted"}'
            th=thresholds(yva,p)
            for item,r in zip(th,val):
                if p[list(val).index(r)]>=item['threshold']: item[f'activated_{"target" if r["label"]=="target" else r["label"]}_ids'].append(r['recording_id'])
            variants[key]={'train_cv':summary(ytr,cv_prob),'validation':summary(yva,p),'thresholds':th,'validation_samples':[{'recording_id':r['recording_id'],'label':r['label'],'phrase':r.get('phrase',''),'probability':float(v),'rank':int(1+sum(p>v))} for r,v in zip(val,p)],'probability_range': [float(p.min()),float(p.max())]}
    result={'feature_config':{'source':'train_temporal_acoustic.py normalized','dimension':348},'train_count':len(train),'validation_count':len(val),'cv_folds':folds,'calibration_method':'sigmoid','isotonic':{'status':'skipped','reason':'not statistically defensible with only 12 minority-class training samples; isotonic would have too few observations per calibration fold'},'variants':variants,'prior_temporal_normalized':{'roc_auc':.8333333333,'pr_auc':.5888888889,'target_recall':0.0,'threshold_030_recall':.3333333333,'threshold_030_fpr':.125}}
    output.mkdir(parents=True,exist_ok=True); (output/'results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); (output/'calibration_summary.json').write_text(json.dumps({'cv_folds':folds,'method':'sigmoid','isotonic':result['isotonic'],'variants':{k:{'train_cv':v['train_cv'],'validation':v['validation'],'probability_range':v['probability_range']} for k,v in variants.items()}},indent=2,sort_keys=True)+'\n'); return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',default='wake-model/dataset'); p.add_argument('--output',default='wake-model/local-output/calibrated-temporal'); a=p.parse_args(); print(json.dumps(run(Path(a.root),Path(a.output)),indent=2,sort_keys=True))
if __name__=='__main__': main()
