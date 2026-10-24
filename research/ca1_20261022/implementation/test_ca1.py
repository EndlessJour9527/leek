import unittest,copy
from datetime import date,timedelta
from ca1 import *

def sample(n=70,p=('5','125','4')):
 ds=[]; d=date(2021,10,18)
 while len(ds)<n:
  if d.weekday()<5: ds.append(d.isoformat())
  d+=timedelta(days=1)
 return dict(synthetic=True,calendar=ds,bars={s:{d:dict(open=v,close=v,high=v,low=v) for d in ds} for s,v in zip(CODES,p)},events=[])
def event(data,s='511010',record=4,ex=5,pay=8,amount='1'):
 ds=data['calendar']; return dict(id=f'{s}:{ex}',symbol=s,record=ds[record],ex=ds[ex],pay=ds[pay],published=ds[record-1],amount=amount,ratio='1')
def setbar(d,s,i,o,c=None):
 c=c or o; d['bars'][s][d['calendar'][i]]=dict(open=str(o),close=str(c),high=str(max(D(o),D(c))),low=str(min(D(o),D(c))))
class Acceptance(unittest.TestCase):
 def test_01_initial_causality(self):
  d=sample(); a=replay(d); fills=[o for o in a['orders'] if o['status']=='FILL']; self.assertEqual(min(o['execute'] for o in fills),'2021-10-20'); self.assertTrue(all(x['nav']==50000 for x in a['daily'][:2]))
  e=copy.deepcopy(d); setbar(e,'510300',20,'6'); b=replay(e); self.assertEqual(a['cycles'][0],b['cycles'][0]); self.assertEqual(a['orders'][:3],b['orders'][:3])
 def test_02_schedule(self):
  d=sample(60); r=replay(d); self.assertEqual([c['signal'] for c in r['cycles']],['2021-10-18','2021-10-29','2021-11-30','2021-12-31']); self.assertEqual(len(r['daily']),60); self.assertFalse(any(o['execute']>d['calendar'][-1] for o in r['orders']))
  self.assertEqual(len(replay(d,'BH300')['cycles']),1)
 def test_03_exact_thirds_lot(self):
  b=budgets(D(50000),weights_for('CA1')); self.assertEqual(list(b.values()),[D('16666.67'),D('16666.67'),D('16666.66')]); self.assertEqual(affordable(100,D(12500),D(50000),D('124.772'),1),0)
 def test_04_locked_quantity(self):
  d=sample(); a=replay(d); e=copy.deepcopy(d); setbar(e,'510300',2,'4.91'); b=replay(e); self.assertEqual(a['orders'][0]['quantity'],b['orders'][0]['quantity']); self.assertEqual(b['orders'][0]['status'],'FILL')
  setbar(e,'510300',2,'4.8'); self.assertEqual(replay(e)['orders'][0]['reason'],'BUY_GAP')
 def test_05_cash_release(self):
  d=sample();
  for i in range(9,len(d['calendar'])): setbar(d,'510300',i,'6')
  r=replay(d); sells=[o for o in r['orders'] if o['side']=='SELL' and o['status']=='FILL']; self.assertTrue(sells)
  first=sells[0]; j=d['calendar'].index(first['execute']); self.assertGreater(r['daily'][j]['restricted'],0); self.assertEqual(r['daily'][j+1]['restricted'],0)
 def test_06_priority_no_reallocation(self):
  r=replay(sample(p=('5','1000','4'))); self.assertEqual(r['daily'][2]['positions']['511010']['quantity'],0); self.assertLess(r['daily'][2]['positions']['510300']['value'],17000); self.assertTrue(all(x['cash']>=0 for x in r['daily']))
 def test_07_failed_sell_no_retry(self):
  d=sample();
  for i in range(9,len(d['calendar'])): setbar(d,'510300',i,'6')
  d['bars']['510300'][d['calendar'][10]]['suspended']=True
  r=replay(d); sell=[o for o in r['orders'] if o['side']=='SELL'][0]; self.assertEqual(sell['status'],'NO_FILL'); self.assertEqual(r['daily'][9]['positions']['510300']['quantity'],r['daily'][10]['positions']['510300']['quantity'])
  self.assertIsNone(eligibility(dict(open='9.5'),'10','0','SELL'))
 def test_08_gap_limits_no_HL(self):
  for p in ('9.8','10.2'): self.assertIsNone(eligibility(dict(open=p),'10','0','BUY','10'))
  for p in ('9','11'): self.assertEqual(eligibility(dict(open=p),'10','0','SELL'),'MODEL_LIMIT_BOUNDARY')
  self.assertIsNone(eligibility(dict(open='9',high='999',low='0'),'10','1','BUY','9'))
  self.assertEqual(tick(D('1.2345')),D('1.235'))
 def test_09_cost_rounding(self):
  self.assertEqual(cost(100,'1.005',1),(D('100.50'),D('5'),D('.10'))); self.assertEqual(cost(100,'1.005',2),(D('100.50'),D('10'),D('.20')))
  self.assertEqual(cent(D('1.005')),D('1.01')); a=replay(sample(),'CA1',1); b=replay(sample(),'CA1',2); self.assertGreater(b['daily'][-1]['fees'],a['daily'][-1]['fees'])
 def test_10_record_ex_pay(self):
  d=sample(); e=event(d); d['events']=[e]; r=replay(d); ex=[x for x in r['corporate_actions'] if x['phase']=='EX'][0]; self.assertEqual(ex['amount'],D(100)); self.assertEqual(r['daily'][5]['receivable'],D(100)); self.assertEqual(r['daily'][8]['receivable'],0)
  l=Ledger('10000',['a']); l.fill('a','BUY',100,1,1,0,'2021-10-18'); l.record('a','e'); l.fill('a','SELL',100,1,1,0,'2021-10-19'); l.fill('a','BUY',100,1,1,0,'2021-10-19'); l.ex('a','e','.1','1','exact'); self.assertEqual(l.receivables[('a','e')],D(10)); l.pay('a','e')
  with self.assertRaises(ValueError): l.pay('a','e')
 def test_11_ex_cancel_unknown(self):
  d=sample(); e=event(d,record=0,ex=2,pay=4); e['published']=d['calendar'][0]; d['events']=[e]; r=replay(d); self.assertEqual(r['daily'][2]['positions']['511010']['quantity'],0)
  e['ratio']='2'
  with self.assertRaises(AssertionError): replay(d)
 def test_12_data_fail_closed(self):
  d=sample(); del d['bars']['510300'][d['calendar'][0]]
  with self.assertRaises(AssertionError): replay(d)
  d=sample(); d['bars']['510300'][d['calendar'][2]]['unknown_ca']=True; self.assertEqual(replay(d)['orders'][0]['reason'],'BLOCKED_STATUS_CA')
 def test_13_cash_shares_nav_fifo(self):
  d=sample()
  for i in range(9,len(d['calendar'])): setbar(d,'510300',i,'6')
  r=replay(d); self.assertTrue(r['closed_fifo']); self.assertEqual(sum(x['basis'] for x in r['closed_fifo'])+r['daily'][-1]['positions']['510300']['basis'],sum(o['notional']+o['fee']+o['slippage'] for o in r['orders'] if o['symbol']=='510300' and o['side']=='BUY' and o['status']=='FILL'))
 def test_14_metrics(self):
  r=replay(sample(),'CASH'); m=summarize(r); self.assertEqual(m['cagr'],0); self.assertEqual(m['ce3'],0); self.assertEqual(m['mdd'],0); self.assertIsNone(m['win_rate']); self.assertEqual(m['underwater_days'],0)
  rows=copy.deepcopy(r['daily'][:3]); rows[0]['nav']=D(50000); rows[1]['nav']=D(45000); rows[2]['nav']=D(50000); m=metric(rows); self.assertAlmostEqual(m['mdd'],.1); self.assertEqual(m['max_underwater_spell'],1); self.assertAlmostEqual(m['es05'],-.1)
 def test_15_economic_fail(self):
  ss={f'{a}_{c}':summarize(replay(sample(),a,m)) for a in ('CA1','SCASH','BH300','CASH') for c,m in [('BASE',1),('DOUBLE',2)]}; self.assertEqual(len(ss),8); 
  with self.assertRaises(ValueError): economics(ss)
  for v in ss.values(): v['segments']*=3
  self.assertEqual(economics(ss)['decision'],'STOP_CURRENT_VARIANT')
 def test_16_subscription_offledger(self):
  r=replay(sample(),'CASH'); before=copy.deepcopy(r); s=subscription(r['daily']); self.assertEqual(r,before); self.assertEqual([x['fx_scenario'] for x in s],[6,7,8]); self.assertEqual(s[1]['capital_burdens']['50000'],'0.168'); self.assertTrue(all(x['terminal_surplus']<0 for x in s))
if __name__=='__main__': unittest.main(verbosity=2)
