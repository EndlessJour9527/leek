"""Two frozen learners, endpoint-purged expanding folds; no random CV or tuning."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
import lightgbm as lgb
import sklearn
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from leek.contract import DataBlocked
from .data import encoded

EVALUATION_START='2022-01-01'
FEATURES=(['mom_'+str(w) for w in (1,5,10,20,60)]
          +['vol_'+str(w) for w in (5,20,60)]
          +['distance_'+str(w) for w in (5,20,60)]
          +['volume_ratio_'+str(w) for w in (5,20)]
          +['range_fraction','intraday_return','neutralized_gap'])
THRESHOLD=0.0025


def feature_table(bars,events):
    """Future values appear only in y. X is strictly causal; no global imputation."""
    days=[b['date'] for b in bars];lookup={d:i for i,d in enumerate(days)}
    o=np.array([float(b['open']) for b in bars]);c=np.array([float(b['close']) for b in bars])
    h=np.array([float(b['high']) for b in bars]);lo=np.array([float(b['low']) for b in bars])
    v=np.array([float(b['volume_lots']) for b in bars]);div=np.zeros(len(bars))
    if not all(np.isfinite(x).all() and (x>0).all() for x in (o,c,h,lo,v)):
        raise DataBlocked('nonfinite or nonpositive model input')
    for e in events:
        r,ex=lookup[e['record_date']],lookup[e['ex_date']]
        if ex!=r+1:raise DataBlocked('unsupported label entitlement chronology')
        div[ex]+=float(e['cash_per_share'])
    level=np.empty(len(bars));level[0]=c[0]
    for i in range(1,len(bars)):level[i]=level[i-1]*(c[i]+div[i])/c[i-1]
    tr=pd.Series(level);volume=pd.Series(v);daily=tr.pct_change(fill_method=None)
    x=pd.DataFrame(index=range(len(bars)))
    for w in (1,5,10,20,60):x['mom_'+str(w)]=tr/tr.shift(w)-1
    for w in (5,20,60):x['vol_'+str(w)]=daily.rolling(w).std(ddof=0)
    for w in (5,20,60):x['distance_'+str(w)]=tr/tr.rolling(w).mean()-1
    for w in (5,20):x['volume_ratio_'+str(w)]=volume/volume.rolling(w).mean()-1
    x['range_fraction']=(h-lo)/c;x['intraday_return']=c/o-1
    x['neutralized_gap']=(pd.Series(o)+div)/pd.Series(c).shift(1)-1
    if list(x.columns)!=FEATURES or not np.isfinite(x.iloc[60:].to_numpy()).all():
        raise DataBlocked('feature schema or finite-value check failed')
    y=np.full(len(bars),np.nan);endpoint=np.arange(len(bars))+6
    # Buy at t+1 open; ex on the buy day confers no entitlement. Sell at t+6 open.
    for i in range(len(bars)-6):y[i]=(o[i+6]+sum(div[i+2:i+7]))/o[i+1]-1
    return x,y,endpoint,level


def split_indices(x,y,endpoint,first_signal,valid_size=126,min_train=350):
    eligible=np.flatnonzero(np.isfinite(x.to_numpy()).all(axis=1)&np.isfinite(y)&(endpoint<first_signal))
    if len(eligible)<valid_size+min_train+6:raise DataBlocked('insufficient mature learning history')
    valid=eligible[-valid_size:]
    train=eligible[(eligible<valid[0])&(endpoint[eligible]<valid[0])]
    if len(train)<min_train or max(endpoint[train])>=min(valid) or max(endpoint[valid])>=first_signal:
        raise DataBlocked('split maturity/purge constraint failed')
    return train,valid


def ridge_from_json(obj,values):
    return ((np.asarray(values)-obj['mean'])/obj['scale'])@np.asarray(obj['coef'])+obj['intercept']


def mse(a,b):
    return float(np.mean((np.asarray(a)-np.asarray(b))**2))


def predictive_metrics(records):
    valid=[r for r in records if r['target'] is not None]
    y=np.array([r['target'] for r in valid]);out={}
    for name in ('ridge','lightgbm','zero','train_mean'):
        pred=np.array([r[name] for r in valid])
        corr=None
        if np.std(pred)>0 and np.std(y)>0:
            corr=float(pd.Series(pred).corr(pd.Series(y),method='spearman'))
        out[name]={'mse':mse(y,pred),'time_series_spearman':corr,'n':len(y)}
    return out


def fit_predict(bars,events,model_directory):
    x,y,endpoint,levels=feature_table(bars,events)
    days=[b['date'] for b in bars]
    root=Path(model_directory);root.mkdir(parents=True,exist_ok=False)
    groups={}
    for i in range(60,len(days)-1):
        if days[i+1]>=EVALUATION_START:groups.setdefault(days[i+1][:4],[]).append(i)
    if set(groups)!={'2022','2023','2024','2025'}:raise DataBlocked('four registered yearly folds required')
    records=[];folds=[]
    for year,indices in sorted(groups.items()):
        first=indices[0];train,valid=split_indices(x,y,endpoint,first)
        folder=root/year;folder.mkdir()
        scaler=StandardScaler().fit(x.iloc[train])
        ridge=Ridge(alpha=1.0,solver='svd').fit(scaler.transform(x.iloc[train]),y[train])
        pr=ridge.predict(scaler.transform(x.iloc[indices]))
        state=dict(feature_names=FEATURES,mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),
                   coef=ridge.coef_.tolist(),intercept=float(ridge.intercept_),alpha=1.0)
        (folder/'ridge.json').write_bytes(encoded(state))
        if not np.allclose(pr,ridge_from_json(json.loads((folder/'ridge.json').read_text()),x.iloc[indices].to_numpy()),rtol=0,atol=1e-12):
            raise DataBlocked('Ridge saved model prediction mismatch')
        params=dict(objective='regression',metric='l2',learning_rate=.03,num_leaves=7,max_depth=3,
                    min_data_in_leaf=60,lambda_l2=1.0,num_threads=1,device_type='cpu',
                    deterministic=True,force_col_wise=True,seed=20261025,verbosity=-1)
        dtrain=lgb.Dataset(x.iloc[train],label=y[train],feature_name=FEATURES)
        dvalid=lgb.Dataset(x.iloc[valid],label=y[valid],reference=dtrain,feature_name=FEATURES)
        booster=lgb.train(params,dtrain,num_boost_round=200,valid_sets=[dvalid],
                          callbacks=[lgb.early_stopping(20,verbose=False)])
        pg=booster.predict(x.iloc[indices],num_iteration=booster.best_iteration,num_threads=1)
        booster.save_model(str(folder/'lightgbm.txt'),num_iteration=booster.best_iteration)
        reload=lgb.Booster(model_file=str(folder/'lightgbm.txt'))
        if not np.allclose(pg,reload.predict(x.iloc[indices],num_threads=1),rtol=0,atol=1e-12):
            raise DataBlocked('LightGBM saved model prediction mismatch')
        hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
        fold=dict(year=year,fit_start=days[train[0]],fit_end=days[train[-1]],
                  fit_last_label_endpoint=days[int(endpoint[train[-1]])],
                  validation_start=days[valid[0]],validation_end=days[valid[-1]],
                  validation_last_label_endpoint=days[int(endpoint[valid[-1]])],
                  first_prediction=days[first],last_prediction=days[indices[-1]],
                  train_rows=len(train),validation_rows=len(valid),prediction_rows=len(indices),
                  lightgbm_best_iteration=booster.best_iteration,model_hashes=hashes,
                  feature_gain=dict(zip(FEATURES,booster.feature_importance('gain').astype(float).tolist())),
                  ridge_validation_mse=mse(y[valid],ridge.predict(scaler.transform(x.iloc[valid]))),
                  lightgbm_validation_mse=mse(y[valid],booster.predict(x.iloc[valid],num_threads=1)))
        folds.append(fold)
        for k,i in enumerate(indices):
            target=float(y[i]) if np.isfinite(y[i]) else None
            records.append(dict(signal_date=days[i],next_session=days[i+1],fold=year,
                trained_asof=days[first-1],label_end=days[int(endpoint[i])] if endpoint[i]<len(days) else None,
                target=target,ridge=float(pr[k]),lightgbm=float(pg[k]),zero=0.,train_mean=float(np.mean(y[train]))))
    return dict(records=records,folds=folds,metrics=predictive_metrics(records),
                versions=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,
                              scikit_learn=sklearn.__version__,lightgbm=lgb.__version__)),levels


def policies(bars,records,levels):
    days=[b['date'] for b in bars];first=next(i for i,d in enumerate(days) if d>=EVALUATION_START)-1
    bydate={r['signal_date']:r for r in records}
    if len(bydate)!=len(records):raise DataBlocked('duplicate prediction date')
    result={name:{} for name in ('ridge','lightgbm','ma120_weekly')};state={name:False for name in result}
    decision_dates=[]
    for i,day in enumerate(days):
        if i>=first and i<len(days)-1 and (i-first)%5==0:
            if day not in bydate:raise DataBlocked('missing forecast at decision')
            decision_dates.append(day)
            for name in ('ridge','lightgbm'):state[name]=bydate[day][name]>THRESHOLD
            ma=float(np.mean(levels[i-119:i+1]))
            if levels[i]>ma:state['ma120_weekly']=True
            elif levels[i]<ma:state['ma120_weekly']=False
        for name in result:result[name][day]=bool(state[name])
    return result,decision_dates
