"""Fixed-position diagnostic only. No engine imports or data acquisition."""
import argparse, hashlib, json, sys
from decimal import Decimal as D
from pathlib import Path
SYMBOLS=('510300','511010','518880')
def require(x):
    if not x:raise ValueError('INVALID_FROZEN_ACCOUNT')
def number(x):
    require(isinstance(x,(str,int)) and not isinstance(x,bool));v=D(x);require(v.is_finite());return v
def mark(row,shocks):
    require(set(shocks)<=set(SYMBOLS))
    cash=number(row['cash']);rec=number(row['receivable']);nav=number(row['nav'])
    require(cash>=0 and rec>=0 and nav>0 and set(row['positions'])==set(SYMBOLS))
    values={}
    for s,p in row['positions'].items():
        q=number(p['quantity']);price=number(p['close']);value=number(p['value'])
        require(q>=0 and price>0 and q*price==value);values[s]=value
    require(cash+rec+sum(values.values())==nav)
    require(all(D('-1')<=v<=0 for v in shocks.values()))
    loss=-sum((values[s]*shocks.get(s,D(0)) for s in SYMBOLS),D(0))
    return dict(loss_cny=str(loss),loss_pct_terminal_nav=str(loss/nav*100),loss_pct_initial_capital=str(loss/D(50000)*100),stressed_nav=str(nav-loss),residual_gain_vs_initial=str(nav-loss-D(50000)))
def analyze(root,pins):
    require(not sys.flags.optimize)
    scenarios={'ZERO':{}}
    for s in SYMBOLS:
        for x in ('0.10','0.20'):scenarios[s+'_-'+x]={s:-D(x)}
    scenarios['ALL_-0.20']={s:D('-0.20') for s in SYMBOLS}
    out={}
    for name,expected in pins.items():
        raw=(root/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==expected)
        account=json.loads(raw);rows=account['daily'];require(len(rows)==1140 and rows[-1]['date']=='2026-06-30')
        require(name==account['account']+'_'+account['cost']+'.json')
        out[name[:-5]]={label:mark(rows[-1],shocks) for label,shocks in scenarios.items()}
    require(len(out)==8)
    return dict(status='FIXED_POSITION_DIAGNOSTIC_ONLY',sample='SEEN_DEVELOPMENT',date='2026-06-30',initial_capital='50000',new_backtests=0,new_model_calls=0,new_candidates=0,automatic_promotion=False,input_sha256=pins,results=out)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results-root',type=Path,required=True);args=p.parse_args()
    pins=json.loads(Path(__file__).with_name('INPUT_PINS.json').read_text())
    print(json.dumps(analyze(args.results_root,pins),indent=2,sort_keys=True))
