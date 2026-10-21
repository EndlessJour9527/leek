"""AG1 single registered development experiment. Requires independent hash-bound release."""
import argparse,copy,hashlib,json,math,statistics
from pathlib import Path
from decimal import Decimal as D
from fractions import Fraction
from datetime import date as Date
from portfolio import PortfolioEngine
from schedule import build_schedule
from monthly_signals import momentum_scores
from cash_gate import gate_on
from batch_artifacts import dump
from contract import DataBlocked
ROOT=Path(__file__).resolve().parent.parent
FROZEN=ROOT/'frozen_input/E4_H1_REPRODUCIBLE_v1'
def read(p):return json.loads(Path(p).read_text(),parse_float=D)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inputs():
 for p,h in read(FROZEN/'PORTABLE_SHA256SUMS.json').items():
  if sha(FROZEN/p)!=h:raise DataBlocked('changed frozen file '+p)
 a=FROZEN/'adapter_original'
 return read(a/'panel.json'),read(a/'sessions.json'),read(a/'events.json'),read(FROZEN/'registration/registry.json')
def get_engine(reg,events,cost):
 return PortfolioEngine(reg['universe'],50000,events,cost,100,{s:True for s in reg['universe']})
def calibrate(panel,sessions,events,reg):
 strategy=reg['strategies'][0];start,end='2021-10-18','2022-12-30'
 sched,ends=build_schedule(sessions,'2021-10-15','2021-09',start,end,strategy)
 eng=get_engine(reg,events,reg['cost_scenarios'][0]);effective={};rows=[];on=False
 for date in sessions:
  if date>end:break
  if date in effective:on=effective[date]
  if start<=date<=end:rows.append({'date':date,'on':on})
  eng.step(date,{s:panel[s][date] for s in reg['universe']},None,None,date in ends.values(),False)
  ent=sched.get(date)
  if ent and ent['next_session']:
   dec=ent['decision'];scores=momentum_scores(eng.monthly,dec['formation_month'],12,1,reg['universe'])
   effective[ent['next_session']]=gate_on(scores,reg['universe'])
 count=sum(r['on'] for r in rows);fraction=Fraction(count,len(rows));q=D(count)/D(len(rows))
 return {'training_start':start,'training_end':end,'on_days':count,'all_days':len(rows),'q_fraction':str(fraction),'q_decimal':str(q),'target_total':str(D('.95')*q),'training_pnl_computed':False,'daily_target_state':rows}
def run(panel,sessions,events,reg,name,cost,q):
 strat=copy.deepcopy(reg['strategies'][1 if name=='EW95_CONTEXT' else 0])
 if name=='M12_FIXED_Q':strat['selected_weight']=D('.475')*q
 start,end='2023-01-03','2026-06-30'
 sched,ends=build_schedule(sessions,'2022-12-30','2022-12',start,end,strat)
 eng=get_engine(reg,events,cost)
 for date in sessions:
  if date>end:break
  ent=sched.get(date);decision=copy.deepcopy(ent['decision']) if ent else None
  if decision and name=='AG1':decision['absolute_cash_gate']=True
  # Missing limit metadata on an actual pending order is a data gate, not a fill guess.
  if eng.pending:
   for order in eng.pending['orders']:
    bar=panel[order['symbol']][date]
    if bar.get('status')!='suspended_verified' and (bar.get('upper_limit') is None or bar.get('lower_limit') is None):
     raise DataBlocked('new plan depends on unknown limit '+date+' '+order['symbol'])
  eng.step(date,{s:panel[s][date] for s in reg['universe']},decision,ent['next_session'] if ent else None,date in ends.values(),date>=start)
 return eng

def metrics(eng,start=None,end=None):
 allrows=eng.daily;rows=[r for r in allrows if (not start or r['date']>=start) and (not end or r['date']<=end)]
 prior=[r for r in allrows if r['date']<rows[0]['date']];initial=prior[-1]['nav'] if prior else D(50000)
 prev=initial;rets=[];peak=initial;dd=D(0);exposure=[];under=0;maxunder=0
 for r in rows:
  rets.append(float(r['nav']/prev-1));prev=r['nav'];peak=max(peak,r['nav']);dd=max(dd,1-r['nav']/peak)
  under=under+1 if r['nav']<peak else 0;maxunder=max(maxunder,under)
  exposure.append(sum((p['qty']*r['marks'][s] for s,p in r['positions'].items()),D(0))/r['nav'])
 n=len(rows);days=(Date.fromisoformat(rows[-1]['date'])-Date.fromisoformat(rows[0]['date'])).days+1;cagr=float(rows[-1]['nav']/initial)**(365.25/days)-1;var=statistics.pvariance(rets)*252
 executions=[x for x in eng.executions if rows[0]['date']<=x['date']<=rows[-1]['date']]
 trades=[t for x in executions for t in x['trades']]
 turnover=sum((abs(t['quantity']*t['raw_open']) for t in trades),D(0))/(sum((r['nav'] for r in rows),D(0))/n)
 commission=rows[-1]['commission']-(prior[-1]['commission'] if prior else D(0));slippage=rows[-1]['slippage']-(prior[-1]['slippage'] if prior else D(0))
 dividends=sum((e['amount'] for e in eng.event_log if e['type']=='payment' and rows[0]['date']<=e['date']<=rows[-1]['date']),D(0))
 return {'start':rows[0]['date'],'end':rows[-1]['date'],'sessions':n,'calendar_days_inclusive':days,'cagr_convention':'calendar_inclusive_365.25','initial_nav':initial,'terminal_nav':rows[-1]['nav'],'return_fraction':rows[-1]['nav']/initial-1,'cagr':cagr,'max_drawdown':float(dd),'annual_volatility':math.sqrt(var),'annual_daily_population_variance':var,'ce3':cagr-1.5*var,'mean_actual_exposure':sum(exposure,D(0))/n,'turnover_sum_raw_notional_over_mean_nav':turnover,'fill_count':len(trades),'no_fill_count':sum(len(x['rejected']) for x in executions),'commission':commission,'slippage':slippage,'cash_dividends_paid':dividends,'worst_day':min(rets),'max_underwater_sessions':maxunder,'account_reset':False}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--release',required=True);ap.add_argument('--release-sha256',required=True);ap.add_argument('--output',required=True);args=ap.parse_args()
 release=Path(args.release)
 if sha(release)!=args.release_sha256:raise DataBlocked('release hash mismatch')
 rel=read(release)
 if rel.get('status')!='RUN_AUTHORIZED':raise DataBlocked('independent run release missing')
 if rel['registration_sha256']!=sha(ROOT/'REGISTRATION_AG1.md'):raise DataBlocked('registration changed')
 for p,h in rel['implementation_hashes'].items():
  if sha(Path(__file__).parent/p)!=h:raise DataBlocked('implementation changed '+p)
 panel,sessions,events,reg=inputs();out=Path(args.output)
 if out.exists():raise FileExistsError(out)
 out.mkdir(parents=True);qrecord=calibrate(panel,sessions,events,reg);dump(out/'calibration_before_evaluation.json',qrecord)
 q=D(qrecord['q_decimal']);dump(out/'manifest_before_evaluation.json',{'release_sha256':sha(release),'registration_sha256':rel['registration_sha256'],'calibration_sha256':sha(out/'calibration_before_evaluation.json'),'labels':['ALL_SEEN_DEVELOPMENT','CONDITIONAL_FIRST_PRINT_DAILY_PROXY'],'new_variant_count':1,'paths':8})
 summaries={}
 for name in ['AG1','M12','M12_FIXED_Q','EW95_CONTEXT']:
  for cost in reg['cost_scenarios'][:2]:
   engine=run(panel,sessions,events,reg,name,cost,q);key=name+'_'+cost['id'];folder=out/key;folder.mkdir()
   for title,value in [('daily',engine.daily),('signals',engine.signals),('executions',engine.executions),('events',engine.event_log)]:dump(folder/(title+'.json'),value)
   dump(folder/'terminal.json',{'cash':engine.ledger.cash,'positions':engine.ledger.positions,'receivables':[{'symbol':s,'event_id':e,'amount':v} for (s,e),v in engine.ledger.receivables.items()],'no_terminal_liquidation':True})
   summaries[key]=metrics(engine);summaries[key]['segments']=[metrics(engine,a,b) for a,b in [('2023-01-03','2023-12-29'),('2024-01-01','2024-12-31'),('2025-01-01','2026-06-30')]]
 dump(out/'metrics.json',summaries);checks={}
 for c in ['base','double']:
  a,m,f=(summaries[x+'_'+c] for x in ['AG1','M12','M12_FIXED_Q'])
  checks[c]={'A_drawdown_reduction_ge_5pp':m['max_drawdown']-a['max_drawdown']>=.05,'B_cagr_opportunity_cost_le_2pp':m['cagr']-a['cagr']<=.02,'C_ce3_above_fixed_q':a['ce3']>f['ce3'],'drawdown_reduction':m['max_drawdown']-a['max_drawdown'],'cagr_opportunity_cost':m['cagr']-a['cagr'],'ce3_increment':a['ce3']-f['ce3']}
 passed=all(v for x in checks.values() for k,v in x.items() if k.startswith(('A_','B_','C_')))
 dump(out/'decision.json',{'criteria':checks,'decision':'KEEP_FOR_FUTURE_TEST' if passed else 'STOP_RESEARCH_VARIANT','independent_result_audit':'PENDING','not_unseen_test':True})
 dump(out/'SHA256SUMS.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()})
 print(out/'decision.json')
if __name__=='__main__':main()
