import unittest
from decimal import Decimal as D
from cash_gate import gate_on
from contract import DataBlocked
from monthly_signals import ranked_symbols
class CashGateTests(unittest.TestCase):
 def test_all_negative(self): self.assertFalse(gate_on({'a':D('-.1'),'b':D('-.2')},['a','b']))
 def test_zero_off(self): self.assertFalse(gate_on({'a':D('0'),'b':D('-.2')},['a','b']))
 def test_one_positive(self): self.assertTrue(gate_on({'a':D('.1'),'b':D('-.2')},['a','b']))
 def test_tiny_positive_unquantized(self): self.assertTrue(gate_on({'a':D('0.00000000000001'),'b':D('-.2')},['a','b']))
 def test_missing(self):
  with self.assertRaises(DataBlocked):gate_on({'a':D('0')},['a','b'])
 def test_nan(self):
  with self.assertRaises(DataBlocked):gate_on({'a':D('NaN')},['a'])
 def test_second_negative_still_ranked(self):
  scores={'a':D('.1'),'b':D('-.2'),'c':D('-.3'),'d':D('-.4')}
  self.assertTrue(gate_on(scores,list(scores)));self.assertEqual(ranked_symbols(scores,'0.000000000001')[:2],['a','b'])
if __name__=='__main__':unittest.main()

from unittest.mock import patch
from portfolio import PortfolioEngine
from test_portfolio import quote,COST
class GateIntegrationTests(unittest.TestCase):
 def make(self,scores,gate=True):
  x=PortfolioEngine(['a','b','c','d'],50000,[],COST,100,{s:True for s in scores})
  with patch('portfolio.momentum_scores',return_value=scores):
   x.step('2023-01-31',{s:quote() for s in scores},{'kind':'momentum','formation_month':'2023-01','start_lag':12,'top_k':2,'selected_weight':D('.475'),'absolute_cash_gate':gate},'2023-02-01')
  return x
 def test_actual_zero_weights(self):
  x=self.make({'a':D(0),'b':D(-1),'c':D(-2),'d':D(-3)})
  self.assertEqual(sum(x.pending['weights'].values()),0)
 def test_actual_two_weights_when_one_positive(self):
  x=self.make({'a':D('.000000000000001'),'b':D('-.1'),'c':D('-.2'),'d':D('-.3')})
  self.assertEqual(x.pending['weights'],{'a':D('.475'),'b':D('.475'),'c':D(0),'d':D(0)})
  self.assertEqual(x.ledger.cash,50000);self.assertEqual(x.executions,[])
  x.step('2023-02-01',{s:quote() for s in ['a','b','c','d']})
  self.assertEqual(len(x.executions),1);self.assertLess(x.daily[-1]['nav'],50000)
 def test_disabled_unchanged(self):
  scores={'a':D('.1'),'b':D('-.1'),'c':D('-.2'),'d':D('-.3')}
  a=self.make(scores,True);b=self.make(scores,False)
  self.assertEqual(a.pending,b.pending)
 def test_metrics_initial_cost(self):
  from run_ag1 import metrics
  x=self.make({'a':D('.1'),'b':D('-.1'),'c':D('-.2'),'d':D('-.3')});x.daily=[]
  x.step('2023-02-01',{s:quote() for s in ['a','b','c','d']})
  m=metrics(x);self.assertEqual(m['initial_nav'],50000);self.assertLess(m['worst_day'],0)
 def test_rank_tie_unchanged(self):
  x=self.make({'d':D('.1'),'c':D('.1'),'b':D('.1'),'a':D('.1')})
  self.assertEqual(x.signals[-1]['ranking'],['a','b','c','d'])
