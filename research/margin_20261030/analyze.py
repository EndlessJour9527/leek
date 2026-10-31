"""Adapted from archived 2026-10-30 analysis. Private raw inputs; no network."""
import json,csv,math,hashlib,statistics,argparse,sys
from pathlib import Path
from decimal import Decimal as D

def require(ok):
 if not ok: raise ValueError('INVALID_MARGIN_INPUT')
def positive(value):
 require(type(value) in (str,int,float))
 try: n=D(str(value))
 except Exception as exc: raise ValueError('INVALID_MARGIN_NUMBER') from exc
 require(n.is_finite() and n>0)
 return n

def analyze(input_dir):
 require(not sys.flags.optimize)
 p=Path(input_dir)
 markets={}
 for file in ['margin.raw','margin_page2.raw']:
  blob=json.loads((p/file).read_bytes());require(blob['success'] is True)
  for row in blob['result']['data']:
   date=row['DIM_DATE'][:10];market=row['XOB_MARKET_0001']
   if market not in ('融资融券_沪证','融资融券_深证'):continue
   key=(date,market)
   if key in markets:require(markets[key]==row)
   markets[key]=row
 balance={}
 for date in sorted({k[0] for k in markets}):
  rows=[markets.get((date,m)) for m in ('融资融券_沪证','融资融券_深证')]
  if all(rows):balance[date]=sum(positive(r['RZYE']) for r in rows)
 indices={}
 for name,code in [('SSEC','000001'),('CSI300','000300'),('CHINEXT','399006')]:
  blob=json.loads((p/(name+'.raw')).read_bytes())['data'];require(blob['code']==code)
  pairs=[(s.split(',')[0],positive(s.split(',')[2])) for s in blob['klines']];require(len(dict(pairs))==len(pairs))
  indices[name]=dict(pairs)
 dates=sorted(indices['SSEC']);require(all(sorted(v)==dates for v in indices.values()))
 aligned=[];missing=[]
 for i in range(1,len(dates)):
  day,prior=dates[i],dates[i-1]
  if not '2025-10-30'<=day<='2026-10-30':continue
  if day not in balance or prior not in balance:missing.append(day);continue
  row={'date':day,'previous_session':prior,'financing_yuan':str(balance[day]),'change_yuan':str(balance[day]-balance[prior]),'change_rate':float(balance[day]/balance[prior]-1),'publication_time':None}
  for name,prices in indices.items():
   row[name+'_same']=float(prices[day]/prices[prior]-1)
   row[name+'_next']=float(prices[dates[i+1]]/prices[day]-1) if i+1<len(dates) else None
  row['next_session']=dates[i+1] if i+1<len(dates) else None
  require(all(v is None or math.isfinite(v) for k,v in row.items() if k.endswith(('_same','_next')) or k=='change_rate'))
  aligned.append(row)
 def stats(rows,field):
  pairs=[(r['change_rate'],r[field]) for r in rows if r[field] is not None]
  if not pairs: return {'n':0,'pearson':None,'groups':{k:{'n':0,'mean_return':None,'positive_return_fraction':None} for k in ('positive','negative','zero')}}
  x=[v[0] for v in pairs];y=[v[1] for v in pairs];mx=statistics.mean(x);my=statistics.mean(y)
  den=math.sqrt(sum((v-mx)**2 for v in x)*sum((v-my)**2 for v in y))
  groups={}
  for name,fn in [('positive',lambda x:x>0),('negative',lambda x:x<0),('zero',lambda x:x==0)]:
   g=[b for a,b in pairs if fn(a)];groups[name]={'n':len(g),'mean_return':statistics.mean(g) if g else None,'positive_return_fraction':sum(v>0 for v in g)/len(g) if g else None}
  return {'n':len(pairs),'pearson':sum((a-mx)*(b-my) for a,b in pairs)/den if den else None,'groups':groups}
 result={'status':'DESCRIPTIVE_SOURCE_CONDITIONAL_NOT_TRADABLE','start':aligned[0]['date'] if aligned else None,'end':aligned[-1]['date'] if aligned else None,'n':len(aligned),'missing_financing_dates':missing,'publication_timestamps_verified':False,'scope':'Shanghai+Shenzhen financing only; Beijing excluded','results':{n:{lag:stats(aligned,n+'_'+lag) for lag in ('same','next')} for n in indices},'input_sha256':{f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in ['margin.raw','margin_page2.raw','SSEC.raw','CSI300.raw','CHINEXT.raw']}}
 if not aligned: result['status']='NO_PAIRED_SAMPLES_NOT_TRADABLE'
 return result

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--input-dir',type=Path,required=True)
 args=parser.parse_args()
 print(json.dumps(analyze(args.input_dir),indent=2,allow_nan=False))
