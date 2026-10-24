import sys, json, hashlib, math
from pathlib import Path
from decimal import Decimal as D
from datetime import date
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'implementation'))
import ca1
checks=[]
def check(name,ok,details=None): checks.append(dict(name=name,passed=bool(ok),details=details))
def close(a,b): return math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-12)
def row(d,n): return dict(date=d,nav=D(n),positions={s:{'weight':D('0.25')} for s in ca1.CODES},fees=D(0),slippage=D(0),dividend_income=D(0),cash=D(n))
rows=[row('2022-01-01','100'),row('2022-01-02','110'),row('2022-01-03','99')]
m=ca1.metric(rows,D(100),D(100))
check('hand_returns_variance_CE3',close(m['ce3'],-2.52) and close(m['volatility'],math.sqrt(1.68)),m)
check('hand_CAGR_inclusive_3_days',close(m['cagr'],.99**(365.25/3)-1))
check('hand_MDD_ES_water_turnover',close(m['mdd'],.1) and close(m['es05'],-.1) and m['underwater_days']==1 and m['max_underwater_spell']==1 and close(m['turnover'],100/103))
check('actual_mean_exposure',all(close(x,.25) for x in m['mean_weights'].values()))
# Synthetic segments: never load actual price/history files.
srows=[row('2021-10-18','50000'),row('2022-12-30','55000'),row('2023-01-03','56000'),row('2024-12-31','60500'),row('2025-01-02','61000'),row('2026-06-30','66550')]
report=dict(daily=srows,turnover_principal=D(0),closed_fifo=[],round_trips=[],orders=[])
s=ca1.summarize(report)
check('continuing_segment_NAV_no_reset',len(s['segments'])==3 and all(close(x['total_return'],.1) for x in s['segments']),s['segments'])
check('zero_trades_undefined',s['win_rate'] is None and s['net_expectancy'] is None)
def summary(cagr,ce,mdd,segments=3): return dict(cagr=cagr,ce3=ce,mdd=mdd,segments=[dict(cagr=cagr) for _ in range(segments)])
def economic(a,b): return ca1.economics({f'{k}_{c}':x for c in ('BASE','DOUBLE') for k,x in [('CA1',a),('SCASH',b)]})
e=economic(summary(.03,.1,.1),summary(.02,0,.05))
check('gate_exact_1pp_inclusive',e['BASE']['gates']['cagr'],e)
try:
    e=economic(summary(.04,.1,.1,2),summary(.02,0,.05,2))
    check('missing_segment_not_pass',e['decision']!='RETAIN_FOR_FURTHER_EVIDENCE',e)
except ValueError as exc:
    check('missing_segment_not_pass',str(exc)=='INCOMPLETE_SEGMENTS',str(exc))
e=economic(summary(.04,0,.1),summary(.02,0,.05))
check('CE3_strict_equality_fails',not e['BASE']['gates']['ce3'])
x=ca1.subscription(srows); days=(date(2026,6,30)-date(2021,10,18)).days+1
check('subscription_amounts',all(y['expense']==ca1.cent(D(1200)*D(days)/D('365.25')*y['fx_scenario']) and y['terminal_surplus']==D(16550)-y['expense'] for y in x),x)
check('subscription_has_initial_cost_ratio',all('expense_to_initial' in y or 'expense_ratio' in y or 'expense_fraction_initial' in y for y in x))
check('capital_only_burdens',all(D(y['capital_burdens']['10000'])==D(1200)*y['fx_scenario']/10000 for y in x))
# Integration: manufactured stock ramp, no historical source inputs.
from datetime import timedelta
ds=[]; dt=date(2022,1,3)
while len(ds)<240:
    if dt.weekday()<5: ds.append(dt.isoformat())
    dt+=timedelta(days=1)
bars={code:{} for code in ca1.CODES}; price=D(10)
for j,dt in enumerate(ds):
    if j>10: price=ca1.tick(price*D('1.05'))
    for code in ca1.CODES:
        p=price if code=='510300' else D(10)
        bars[code][dt]={k:str(p) for k in ['open','high','low','close']}
event=dict(id='SYNTH_CA',symbol='510300',published=ds[3],record=ds[5],ex=ds[6],pay=ds[7],amount='0.1',ratio='1')
r=ca1.replay(dict(calendar=ds,bars=bars,events=[event]),'SCASH',1)
rt=r['round_trips']; slices=r['closed_fifo']
check('roundtrip_excludes_partial_slices',len(rt)>0 and len(slices)>len(rt) and all(x['exit'] is not None for x in rt),{'roundtrips':len(rt),'slices':len(slices)})
check('roundtrip_includes_CA_and_complete_costs',any(x['income']>0 for x in rt) and all(x['net_pnl']==x['sells']+x['income']-x['buys'] for x in rt),rt)
sm=ca1.summarize(r)
check('summary_uses_complete_episodes',sm['complete_round_trips']==len(rt) and close(sm['net_expectancy'],sum(float(x['net_pnl']) for x in rt)/len(rt)))
out=dict(scope='SYNTHETIC_ONLY_NO_HISTORICAL_RUN',code_sha256=hashlib.sha256((BASE/'implementation/ca1.py').read_bytes()).hexdigest(),checks=checks,all_passed=all(x['passed'] for x in checks))
path=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).with_name('checks_v1.json')
path.write_text(json.dumps(out,indent=2,default=str)+'\n')
print(json.dumps({'file':str(path),'passed':sum(x['passed'] for x in checks),'total':len(checks),'failures':[x['name'] for x in checks if not x['passed']]},indent=2))
