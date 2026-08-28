#!/usr/bin/env python3
"""Small, deterministic nonlinear diagnostic on normalized temporal features."""
from __future__ import annotations
import argparse,json,warnings
from pathlib import Path
import numpy as np
from sklearn.model_selection import StratifiedKFold,cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
from train_temporal_acoustic import load_records

def folds(y):
    n=min(np.bincount(np.asarray(y)=='target'))
    if n<2: raise ValueError('both classes need at least two samples')
    return min(5,int(n))
def scores(model,x): return model.predict_proba(x)[:,list(model.classes_).index('target')]
def metrics(y,s,p):
    t=np.asarray(y)=='target'; q=np.asarray(p)=='target'; tp=int((t&q).sum());fp=int((~t&q).sum());fn=int((t&~q).sum());tn=int((~t&~q).sum())
    from sklearn.metrics import average_precision_score,roc_auc_score
    return {'confusion_matrix':{'target':{'target':tp,'non_target':fn},'non_target':{'target':fp,'non_target':tn}},'accuracy':float(np.mean(t==q)),'target_precision':tp/(tp+fp) if tp+fp else 0.,'target_recall':tp/(tp+fn) if tp+fn else 0.,'fpr':fp/(fp+tn) if fp+tn else 0.,'fnr':fn/(fn+tp) if fn+tp else 0.,'roc_auc':float(roc_auc_score(t,s)),'pr_auc':float(average_precision_score(t,s))}
def thresholds(oof, train_labels, val, rows):
    out=[]
    for percentile in (90,95,97.5,99):
        threshold=float(np.percentile(oof[np.asarray(train_labels)!='target'],percentile))
        active=[r['recording_id'] for r,s in zip(rows,val) if s>=threshold]; t=np.array([r['label']=='target' for r in rows]); pos=np.array([s>=threshold for s in val]); out.append({'train_non_target_oof_percentile':percentile,'threshold':threshold,'target_recall':float((t&pos).sum()/t.sum()),'false_positive_count':int((~t&pos).sum()),'fpr':float((~t&pos).sum()/(~t).sum()),'precision':float((t&pos).sum()/pos.sum()) if pos.sum() else 0.,'activated_validation_ids':active})
    return out
def run(root,output):
    records=load_records(root,True); train=[r for r in records if r['split']=='train']; val=[r for r in records if r['split']=='validation']; x=np.array([r['features'] for r in train]); y=np.array(['target' if r['label']=='target' else 'non_target' for r in train]); xv=np.array([r['features'] for r in val]); yv=np.array(['target' if r['label']=='target' else 'non_target' for r in val]); cv=StratifiedKFold(folds(y),shuffle=True,random_state=0); result={'feature_dimension':348,'cv_folds':cv.n_splits,'models':{},'comparison':{'prior_normalized_temporal_roc_auc':.8333333333,'prior_normalized_temporal_pr_auc':.5888888889,'prior_validation_target_recall':0.,'prior_train_loo_target':'9/12'}}
    for hidden in ((8,),(16,)):
        name=f'mlp_{hidden[0]}'; base=make_pipeline(StandardScaler(),MLPClassifier(hidden_layer_sizes=hidden,activation='relu',solver='lbfgs',alpha=0.01,max_iter=1000,random_state=0)); oof=cross_val_predict(base,x,y,cv=cv,method='predict_proba')[:,1]; model=base.fit(x,y); sv=scores(model,xv); pred=model.predict(xv); train_pred=model.predict(x); samples=[{'recording_id':r['recording_id'],'label':r['label'],'phrase':r.get('phrase',''),'score':float(s),'rank':int(1+sum(sv>s))} for r,s in zip(val,sv)]; result['models'][name]={'configuration':{'hidden_layer_sizes':hidden,'solver':'lbfgs','alpha':.01,'max_iter':1000,'random_state':0},'train':metrics(y,scores(model,x),np.where(train_pred=='target','target','non_target')),'oof':metrics(y,oof,np.where(oof>=.5,'target','non_target')),'oof_target_correct':int(sum((oof>=.5)&(y=='target'))),'validation':metrics(yv,sv,pred),'validation_samples':samples,'train_derived_thresholds':thresholds(oof,y,sv,val),'convergence':{'n_iter':getattr(model[-1],'n_iter_',None),'warnings_recorded':'not suppressed; see stderr'}}
    output.mkdir(parents=True,exist_ok=True); (output/'results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); (output/'model_summary.json').write_text(json.dumps({'models':{k:v['configuration'] for k,v in result['models'].items()},'cv_folds':cv.n_splits},indent=2,sort_keys=True)+'\n'); return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='wake-model/dataset');p.add_argument('--output',default='wake-model/local-output/nonlinear-temporal');a=p.parse_args();print(json.dumps(run(Path(a.root),Path(a.output)),indent=2,sort_keys=True))
if __name__=='__main__':main()
