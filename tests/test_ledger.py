import unittest
from decimal import Decimal as D
from leek.ledger import Ledger

class SharedLedgerTests(unittest.TestCase):
    def test_cost_once_and_shared_cash(self):
        x = Ledger(2000, ['A', 'B'])
        x.fill('A', 'BUY', 100, 10, '10.1', 5, '2024-01-01')
        self.assertEqual(x.cash, D(985))
        self.assertEqual(x.slippage, D(10))
        self.assertEqual(x.nav({'A':10}), D(1985))
        with self.assertRaises(ValueError): x.fill('B','BUY',100,10,10,5,'2024-01-01')
        self.assertEqual(x.cash, D(985))
        x.fill('A','SELL',100,10,'9.9',5,'2024-01-02')
        self.assertEqual(x.cash,D(1970))
        self.assertEqual(x.commission,D(10))
        self.assertEqual(x.slippage,D(20))

    def test_t_plus_one_partial_lots(self):
        x = Ledger(10000,['A'])
        x.fill('A','BUY',100,10,10,0,'2024-01-01')
        x.fill('A','BUY',100,10,10,0,'2024-01-02')
        self.assertEqual(x.sellable('A','2024-01-02'),D(100))
        with self.assertRaises(ValueError): x.fill('A','SELL',200,10,10,0,'2024-01-02')
        x.fill('A','SELL',100,10,10,0,'2024-01-02')
        self.assertEqual(x.positions['A']['qty'],D(100))
        self.assertEqual(x.sellable('A','2024-01-02'),D(0))

    def test_record_ex_pay_and_sell_entitlement(self):
        x=Ledger(1000,['A'])
        x.fill('A','BUY',100,10,10,0,'2024-01-01')
        x.record('A','E')
        x.ex('A','E',1,1,'exact')
        self.assertEqual(x.nav({'A':9}),D(1000))
        self.assertEqual(x.cash,D(0))
        with self.assertRaises(ValueError): x.fill('A','BUY',1,9,9,0,'2024-01-02')
        x.fill('A','SELL',100,9,9,0,'2024-01-02')
        self.assertEqual(x.nav({}),D(1000))
        x.pay('A','E')
        self.assertEqual(x.cash,D(1000))
        with self.assertRaises(ValueError):x.pay('A','E')

    def test_buy_on_ex_no_entitlement(self):
        x=Ledger(1000,['A']);x.record('A','E');x.ex('A','E',1,1,'exact')
        x.fill('A','BUY',100,9,9,0,'2024-01-02');x.pay('A','E')
        self.assertEqual(x.cash,D(100))

    def test_reverse_split_preserves_basis_and_odd_lot(self):
        x=Ledger(1000,['A']);x.fill('A','BUY',100,10,10,0,'2024-01-01')
        x.record('A','S');x.ex('A','S',0,'.251','exact')
        self.assertEqual(x.positions['A']['qty'],D('25.100'))
        self.assertEqual(x.positions['A']['basis'],D(1000))
        self.assertEqual(x.sellable('A','2024-01-02'),D('25.100'))
        x.fill('A','SELL','25.1',40,40,0,'2024-01-02')
        self.assertEqual(x.positions['A']['basis'],D(0))

    def test_account_ceiling_reverse_split(self):
        x=Ledger(10000,['A'])
        x.fill('A','BUY',100,10,10,0,'2024-01-01')
        x.fill('A','BUY',100,10,10,0,'2024-01-02')
        x.record('A','S');x.ex('A','S',0,'.36555','ceil_whole_account')
        self.assertEqual(x.positions['A']['qty'],D(74))
        self.assertEqual(sum(n for d,n in x.positions['A']['lots']),D(74))
        self.assertEqual(x.positions['A']['basis'],D(2000))

    def test_missing_and_nonfinite_valuation(self):
        x=Ledger(1000,['A']);x.fill('A','BUY',100,10,10,0,'2024-01-01')
        for prices in ({},{'A':None},{'A':'NaN'},{'A':0}):
            with self.assertRaises((ValueError,ArithmeticError)):x.nav(prices)

    def test_event_keys_scoped_to_symbol(self):
        x=Ledger(10000,['A','B'])
        for s in ('A','B'):
            x.fill(s,'BUY',100,10,10,0,'2024-01-01');x.record(s,'same');x.ex(s,'same',1,1,'exact')
        self.assertEqual(sum(x.receivables.values()),D(200))
        with self.assertRaises(ValueError):x.ex('A','same',1,1,'exact')

if __name__=='__main__':unittest.main()
