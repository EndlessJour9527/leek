"""Verify published derived NAV series and the frozen AG1 decision, without market data."""
import hashlib,json,math,statistics
from pathlib import Path
from decimal import Decimal as D
from datetime import date
ROOT=Path(__file__).resolve().parent

def main():
 if not __debug__: raise RuntimeError("verification requires assertions; do not use python -O")
 pins=json.loads((ROOT/'PUBLIC_SHA256SUMS.json').read_text())
 for p,h in pins.items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 metrics=json.loads((ROOT/'results_ag1_v1/metrics.json').read_text())
 decision=json.loads((ROOT/'results_ag1_v1/decision.json').read_text())
 assert len(metrics)==8
 for key,m in metrics.items():
  rows=json.loads((ROOT/'results_ag1_v1'/key/'daily_derived.json').read_text())
  assert len(rows)==843 and len({r['date'] for r in rows})==843
  prev=peak=D(50000);dd=D(0);returns=[];exp=[]
  for r in rows:
   nav=D(r['nav']);returns.append(float(nav/prev-1));prev=nav;peak=max(peak,nav);dd=max(dd,1-nav/peak)
   exp.append(D(r['actual_exposure']))
   assert nav>0 and D(r['cash'])>=0
  days=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(rows[0]['date'])).days+1
  cagr=float(prev/D(50000))**(365.25/days)-1
  ce=cagr-1.5*statistics.pvariance(returns)*252
  for name,value in [('cagr',cagr),('max_drawdown',float(dd)),('ce3',ce),('mean_actual_exposure',float(sum(exp)/len(exp)))]:
   assert math.isclose(value,float(m[name]),rel_tol=1e-12,abs_tol=1e-12),(key,name)
  assert prev==D(m['terminal_nav'])
 for cost in ['base','double']:
  a,m,f=(metrics[n+'_'+cost] for n in ['AG1','M12','M12_FIXED_Q'])
  checks=[m['max_drawdown']-a['max_drawdown']>=.05,m['cagr']-a['cagr']<=.02,a['ce3']>f['ce3']]
  assert checks==[True,False,True]
 assert decision['decision']=='STOP_RESEARCH_VARIANT'
 print('PASS: public hashes, 8 x 843 derived NAV rows, risk metrics, both frozen STOP decisions')
if __name__=='__main__':main()
