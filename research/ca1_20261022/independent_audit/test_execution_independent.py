import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'implementation'))
from ca1 import *
from test_ca1 import sample,setbar,event

class IndependentExecution(unittest.TestCase):
 def test_late_ex_never_undoes_completed_sale(self):
  d=sample()
  for i in range(9,len(d['calendar'])): setbar(d,'510300',i,'6')
  e=event(d,'510300',record=10,ex=11,pay=13,amount='.1'); e['published']=d['calendar'][10]; d['events']=[e]
  r=replay(d); sells=[o for o in r['orders'] if o['side']=='SELL' and o['execute']==d['calendar'][10]]
  self.assertEqual(len(sells),1); self.assertEqual(sells[0]['status'],'FILL')
  ex=[x for x in r['corporate_actions'] if x['phase']=='EX'][0]
  self.assertEqual(ex['amount'],cent(D(r['daily'][10]['positions']['510300']['quantity'])*D('.1')))
  self.assertEqual(r['daily'][11]['positions']['510300']['quantity'],r['daily'][10]['positions']['510300']['quantity'])
 def test_record_entitlement_survives_later_sell(self):
  d=sample()
  for i in range(9,len(d['calendar'])): setbar(d,'510300',i,'6')
  e=event(d,'510300',record=8,ex=9,pay=13,amount='.1'); d['events']=[e]
  r=replay(d)
  self.assertGreater(r['daily'][8]['positions']['510300']['quantity'],r['daily'][10]['positions']['510300']['quantity'])
  self.assertEqual(r['daily'][9]['receivable'],cent(D(r['daily'][8]['positions']['510300']['quantity'])*D('.1')))
  self.assertEqual(r['daily'][13]['receivable'],0)
 def test_execution_date_gap_cannot_resize_locked_q(self):
  d=sample(); a=replay(d); base=next(o for o in a['orders'] if o['symbol']=='510300')
  for price in ('4.9','5.1','5.101'):
   z=copy.deepcopy(d); setbar(z,'510300',2,price); r=replay(z); o=next(o for o in r['orders'] if o['symbol']=='510300')
   self.assertEqual(o['quantity'],base['quantity']); self.assertEqual(o['status'],'NO_FILL' if price=='5.101' else 'FILL')
 def test_no_full_period_lookahead_into_initial_targets(self):
  a=sample(); b=copy.deepcopy(a)
  for i in range(20,len(b['calendar'])):
   for s in CODES: setbar(b,s,i,str(D(b['bars'][s][b['calendar'][i]]['close'])*D('1.2')))
  ra,rb=replay(a),replay(b)
  self.assertEqual(ra['daily'][:20],rb['daily'][:20]); self.assertEqual(ra['cycles'][:1],rb['cycles'][:1])
 def test_double_reserve_components_are_separately_rounded(self):
  self.assertEqual(reserve(100,D('1.005'),2),D('112.72'))

if __name__=='__main__':unittest.main(verbosity=2)
