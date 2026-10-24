import unittest
from decimal import Decimal as D
from monthly_signals import momentum_scores,ranked_symbols,target_shares
from contract import DataBlocked

class MonthlySignalTests(unittest.TestCase):
    def test_exact_initial_endpoints_and_future_invariance(self):
        rows={'A':{'2020-09':100,'2021-03':110,'2021-08':121,'2021-09':9000,'2022-01':9999}}
        self.assertEqual(momentum_scores(rows,'2021-09',12,1,['A']),{'A':D('.21')})
        self.assertEqual(momentum_scores(rows,'2021-09',6,1,['A']),{'A':D('.1')})
        rows['A']['2021-09']=1
        self.assertEqual(momentum_scores(rows,'2021-09',12,1,['A']),{'A':D('.21')})
    def test_missing_endpoint_blocks(self):
        with self.assertRaises(DataBlocked):momentum_scores({'A':{}},'2021-09',12,1,['A'])
    def test_tie_order_and_negative_investment_rank(self):
        scores={'B':D('-.2'),'A':D('-.2000000000001'),'C':D('-.5')}
        self.assertEqual(ranked_symbols(scores,'1e-12'),['A','B','C'])
        self.assertEqual(ranked_symbols(dict(reversed(list(scores.items()))),'1e-12'),['A','B','C'])
    def test_signal_nav_and_lot_floor(self):
        self.assertEqual(target_shares({'A':'.475','B':'.475'},50000,{'A':10,'B':20},100),{'A':D(2300),'B':D(1100)})
if __name__=='__main__':unittest.main()
