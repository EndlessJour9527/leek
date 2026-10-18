"""Deterministic synthetic accounting checks, unrelated to historical prices."""
import copy,random,unittest
from decimal import Decimal as D
from leek.ledger import Ledger

class LedgerInvariantTests(unittest.TestCase):
    def test_randomized_cash_position_and_cost_conservation(self):
        rng=random.Random(309)
        x=Ledger(1000000,['A','B','C'])
        expected_cash=D(1000000)
        for i in range(150):
            symbol=rng.choice(['A','B','C']);p=x.positions[symbol]
            raw=D(rng.randint(20,100));n=D(rng.randint(1,10)*100)
            side='SELL' if p['qty']>=n and rng.choice([True,False]) else 'BUY'
            px=raw*(D('1.001') if side=='BUY' else D('.999'))
            fee=max(D(5),n*px*D('.001'))
            if side=='BUY' and n*px+fee>x.cash:continue
            date=f'{2024+i//28:04d}-01-{i%28+1:02d}'
            x.fill(symbol,side,n,raw,px,fee,date)
            expected_cash += (-n*px-fee) if side=='BUY' else (n*px-fee)
            self.assertEqual(x.cash,expected_cash)
            for pos in x.positions.values():
                self.assertEqual(pos['qty'],sum((v for _,v in pos['lots']),D(0)))
                self.assertGreaterEqual(pos['basis'],0)
            self.assertEqual(x.nav({'A':10,'B':20,'C':30}),x.cash+sum(x.positions[s]['qty']*D(v) for s,v in [('A',10),('B',20),('C',30)]))

    def test_rejected_actions_are_atomic(self):
        x=Ledger(1000,['A']);x.fill('A','BUY',100,10,10,0,'2024-01-01')
        for action in (
            lambda:x.fill('A','BUY',1,10,10,0,'2024-01-02'),
            lambda:x.fill('A','SELL',100,10,10,0,'2024-01-01'),
            lambda:x.ex('A','missing',1,1,'exact'),
            lambda:x.pay('A','missing'),
        ):
            before=copy.deepcopy(x.__dict__)
            with self.assertRaises(ValueError):action()
            self.assertEqual(x.__dict__,before)

if __name__=='__main__':unittest.main()
