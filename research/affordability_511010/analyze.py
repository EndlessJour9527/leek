import json,hashlib,argparse,re,sys
from pathlib import Path
from decimal import Decimal as D,ROUND_CEILING,ROUND_HALF_UP
from datetime import date
EXPECTED_PINS = {'raw/511010_sohu.bin': '785becf38847b03871d1b452942b84117c4ad64742b0b9c2ef512d5163a47876', 'raw/511010_tencent.bin': '508806b05811c3e794f25352805678cdda132a13f384a42e8821b278984a6ac2', 'normalized/e4_sessions.json': '6cac931fc21805531a038216e60242971743c6b82e902b61f4ef38f57d190f93', 'raw/511010_sohu.meta.json': 'd5ab94af7108e0db4596f1f9648b0293dbc2c7f82a863aa88b6bc056e1f2056a', 'raw/511010_tencent.meta.json': '0293f15de7f086efee33ad5d4806ad3d6ff096d859ca1f299981602142f19ccf', 'execution_audit/rules2023.docx': '7aa2319f6dcf597be1e86b3b69d7c2ad0e6acb2a5d0cc6be48a01af602fded40', 'execution_audit/EXECUTION_QUALIFICATION.md': '7f8aca0bc322711ad8c7db03ccaf917f322b19321dc233e66d8ebe6b36422b08'}
FIRST,LAST='2021-10-18','2025-12-31'
def require(ok):
 if not ok:raise ValueError('INVALID_FROZEN_AFFORDABILITY_INPUT')
def number(x):
 require(isinstance(x,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',x) is not None)
 v=D(x);require(v.is_finite() and v>0);return v
def parse(rows,order):
 require(isinstance(rows,list))
 result={}
 for r in rows:
  require(isinstance(r,list) and len(r)>max(order))
  day=r[0];require(isinstance(day,str));require(date.fromisoformat(day).isoformat()==day)
  if not FIRST<=day<=LAST:continue
  require(day not in result);prices=tuple(number(r[i]) for i in order)
  o,h,l,c=prices;require(l<=min(o,c)<=max(o,c)<=h)
  result[day]=prices
 require(bool(result));return dict(sorted(result.items()))
def cash(opening,case):
 require(isinstance(opening,D) and opening.is_finite() and opening>0)
 px=(opening*(1+D(case['slippage_bps'])/10000)/D('.001')).to_integral_value(rounding=ROUND_CEILING)*D('.001')
 fee=max(D(case['minimum_commission']),100*px*D(case['commission_rate'])).quantize(D('.01'),rounding=ROUND_HALF_UP)
 return px,fee,px*100+fee
def validate_sources(s,t):
 require(isinstance(s,list) and len(s)==1 and isinstance(s[0],dict) and isinstance(t,dict))
 require(type(s[0].get('status')) is int and s[0]['status']==0)
 require(type(t.get('code')) is int and t['code']==0)
 require(s[0].get('code')=='cn_511010' and isinstance(t.get('data'),dict) and set(t['data'])=={'sh511010'})
def analyze(root,here):
 require(not sys.flags.optimize)
 pins=json.loads((here/'INPUT_PINS.json').read_text())
 require(isinstance(pins,dict) and pins==EXPECTED_PINS)
 require(len(pins)==7 and all(isinstance(v,str) and re.fullmatch(r'[0-9a-f]{64}',v) for v in pins.values()))
 for f,h in pins.items():require(hashlib.sha256((root/f).read_bytes()).hexdigest()==h)
 config=json.loads((here/'REFERENCE_COSTS.json').read_text())
 require(config['initial_cash']=='50000' and config['entry_budget_fraction']=='0.20' and config['lot_size']==100 and config['tick_size']=='0.001')
 require(config['cost_cases']=={'base':{'commission_rate':'0.0002','minimum_commission':'5','slippage_bps':'5'},'stress':{'commission_rate':'0.0004','minimum_commission':'10','slippage_bps':'10'}})
 s=json.loads((root/'raw/511010_sohu.bin').read_bytes().decode('gb18030'));t=json.loads((root/'raw/511010_tencent.bin').read_bytes().decode('gb18030'))
 validate_sources(s,t)
 a=parse(s[0]['hq'],(1,6,5,2));b=parse(t['data']['sh511010']['day'],(1,3,4,2));require(a==b)
 calendar=json.loads((root/'normalized/e4_sessions.json').read_text());expected=[d for d in calendar if FIRST<=d<=LAST];require(list(a)==expected and len(expected)==len(set(expected)))
 rows=[]
 for day,(o,h,l,c) in a.items():
  r={'date':day,'open_cny_per_unit':str(o),'principal':str(o*100)}
  for name,case in config['cost_cases'].items():
   px,fee,total=cash(o,case);r[name]=str(total);r[name+'_execution_price']=str(px);r[name+'_commission']=str(fee)
  rows.append(r)
 summary={}
 for key in ('principal','base','stress'):
  values=[D(r[key]) for r in rows];lo,hi=min(values),max(values)
  summary[key]={'affordable_days':sum(v<=10000 for v in values),'total_days':len(values),'min_cny':str(lo),'max_cny':str(hi),'min_dates':[r['date'] for r in rows if D(r[key])==lo],'max_dates':[r['date'] for r in rows if D(r[key])==hi]}
 return {'status':'CONDITIONAL_M1_OVERLAP_FIXED_INITIAL_BUDGET_ONLY','start':rows[0]['date'],'end':rows[-1]['date'],'budget_cny':'10000','trainable':False,'historical_trade_runs':0,'input_sha256':pins,'summary':summary,'daily':rows}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();r=analyze(args.root,Path(__file__).parent)
 with args.output.open('x') as f:json.dump(r,f,indent=2)
 print(json.dumps(r['summary'],indent=2))
