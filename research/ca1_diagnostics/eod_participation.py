import json,hashlib,math,argparse,sys,re
from collections import Counter
from pathlib import Path
from decimal import Decimal as D

def require(ok):
 if not ok: raise ValueError('INVALID_FROZEN_EOD_INPUT')
def positive(value):
 require(isinstance(value,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value) is not None)
 n=D(value);require(n.is_finite() and n>0);return n
EXPECTED = {'510300-early-verification.json': '85d42fa96a4071b3b9cf05d5690c567f42e7c075f628c4c06c766b48f4c258a3', '510300-new.json': '14bd2f0b65f5a75b3265e018cd2b60a965b833c4055959bee54ccba23f0c21c9', 'RESULT.json': '8aa0bc94e6beafca6194d4a6e80622dc3c901687796336f4f47d68487e0897e0', 'cross_asset_m1_20261022/raw/511010_sohu.bin': '785becf38847b03871d1b452942b84117c4ad64742b0b9c2ef512d5163a47876', 'cross_asset_m1_20261022/raw/518880_sohu.bin': '3b2f26e93d783589f1fb8a7576f22a0625bdae9ae552b7d453e376caa8324360'}

def validate_orders(orders):
 require(isinstance(orders,list))
 seen=set();counts=Counter();states=Counter()
 for r in orders:
  require(isinstance(r,dict))
  ptr=r.get('order_pointer');cost=r.get('cost');symbol=r.get('symbol');status=r.get('status')
  require(isinstance(ptr,str) and ptr not in seen);seen.add(ptr)
  require(cost in ('BASE','DOUBLE') and symbol in ('510300','511010','518880') and r.get('side') in ('BUY','SELL'))
  require(status in ('FILL','NO_FILL','NO_ORDER'));states[cost,status]+=1
  if status=='FILL':counts[cost,symbol]+=1;positive(r.get('notional_cny'))
 require(dict(counts)=={('BASE','510300'):38,('BASE','511010'):1,('BASE','518880'):35,('DOUBLE','510300'):40,('DOUBLE','511010'):1,('DOUBLE','518880'):36})
 require(dict(states)=={('BASE','FILL'):74,('BASE','NO_FILL'):2,('BASE','NO_ORDER'):2,('DOUBLE','FILL'):77,('DOUBLE','NO_FILL'):2,('DOUBLE','NO_ORDER'):1})

def source_rows(doc,symbol):
 require(isinstance(doc,list) and len(doc)==1 and isinstance(doc[0],dict))
 require(type(doc[0].get('status')) is int and doc[0]['status']==0 and doc[0].get('code')=='cn_'+symbol)
 require(isinstance(doc[0].get('hq'),list))
 for row in doc[0]['hq']:
  require(isinstance(row,list) and len(row)>=9 and isinstance(row[0],str))
  positive(row[8])
 return doc[0]['hq']

def run(root, evidence, coverage):
 require(not sys.flags.optimize)
 p=Path(evidence);pins={}
 def read(path):
  b=path.read_bytes();key=str(path.relative_to(root)) if path.is_relative_to(root) else path.name
  digest=hashlib.sha256(b).hexdigest();require(EXPECTED.get(key)==digest);pins[key]=digest
  return json.loads(b.decode('gb18030'))
 old=read(Path(coverage));validate_orders(old['orders']);tables={};changes=[]
 for s in ('510300','511010','518880'):
  paths=[p/'510300-early-verification.json',p/'510300-new.json'] if s=='510300' else [root/'cross_asset_m1_20261022/raw'/f'{s}_sohu.bin']
  table={}
  for path in paths:
   doc=read(path)
   for i,row in enumerate(source_rows(doc,s)):
    require(row[0] not in table)
    amount=positive(row[8])
    table[row[0]]=(amount,path.name+'#/0/hq/'+str(i)+'/8')
  tables[s]=table
 rows=[];groups={}
 for r in old['orders']:
  if r['status']!='FILL':continue
  amount,ptr=tables[r['symbol']][r['execute']];n=positive(r['notional_cny'])
  ratio=n/(amount*10000)
  if r['amount_candidate_unconverted'] is not None and amount!=D(r['amount_candidate_unconverted']):changes.append(r['order_pointer'])
  out={**r,'amount_cny':str(amount*10000),'amount_source_v2':ptr,'capacity_ratio':str(ratio),'participation_pct':str(ratio*100),'blocker':None};rows.append(out)
  for key in (r['cost']+'/'+r['symbol'],r['cost']+'/'+r['symbol']+'/'+r['side']):groups.setdefault(key,[]).append(out)
 summaries={}
 for key,rr in groups.items():
  ordered=sorted(rr,key=lambda x:D(x['capacity_ratio']));count=len(rr)
  summaries[key]={'n':count,'percentiles_pct':{str(q):ordered[math.ceil(count*q/100)-1]['participation_pct'] for q in (50,90,95,99,100)},'max_order':ordered[-1]['order_pointer']}
 require(len(rows)==151)
 return {'status':'CONDITIONAL_EX_POST_EOD_PARTICIPATION_ONLY','source_version':'SOHU_AMOUNT_V2_20261031','inputs_sha256':pins,'filled_records':len(rows),'prior_candidate_differences':changes,'groups':summaries,'new_backtests':0,'opening_fill_certified':False}
if __name__=='__main__':
 a=argparse.ArgumentParser(description='Private-input EOD arithmetic; emits aggregate results only.')
 a.add_argument('--root',type=Path,required=True)
 a.add_argument('--evidence',type=Path,required=True)
 a.add_argument('--coverage',type=Path,required=True)
 args=a.parse_args();print(json.dumps(run(args.root,args.evidence,args.coverage),indent=2,sort_keys=True))
