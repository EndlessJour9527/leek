import copy,unittest
from decimal import Decimal as D
from ledger import Ledger
from execution import make_plan,transform_plan,OrderExecutor

COST={'commission_rate':0,'minimum_commission_cny':5,'adverse_slippage_rate':0}
def quote(open=10,status='trading_verified'):
    return dict(open=open,status=status,upper_limit=20,lower_limit=1,limit_evidence='synthetic_verified')
def plan(x,targets,weights=None):
    weights=weights or {s:D('.5') for s in targets}
    return make_plan('test','2024-01-02','2024-01-03',weights,targets,{s:10 for s in targets},x.nav({s:10 for s in targets}),x.positions,100,{s:False for s in targets})

class ExecutionTests(unittest.TestCase):
    def test_failed_winner_not_replaced_and_no_retry(self):
        x=Ledger(10000,['A','B','C']);p=plan(x,{'A':400,'B':400,'C':0},{'A':'.475','B':'.475','C':0})
        ex=OrderExecutor();out=ex.execute(x,p,{'A':quote(status='suspended_verified'),'B':quote(),'C':quote()},'2024-01-03',COST,100)
        self.assertEqual([t['symbol'] for t in out['trades']],['B'])
        self.assertEqual(out['rejected'][0]['reason'],'known_suspension')
        self.assertEqual(x.positions['C']['qty'],0)
        with self.assertRaises(ValueError):ex.execute(x,p,{'A':quote()},'2024-01-04',COST,100)

    def test_failed_sell_no_virtual_cash_fair_buys(self):
        x=Ledger(4500,['A','B','C']);x.fill('A','BUY',100,10,10,0,'2024-01-01')
        p=plan(x,{'A':0,'B':200,'C':200},{'A':0,'B':'.475','C':'.475'})
        out=OrderExecutor().execute(x,p,{'A':quote(status='suspended_verified'),'B':quote(),'C':quote()},'2024-01-03',COST,100)
        self.assertEqual(x.positions['A']['qty'],100)
        self.assertEqual(x.positions['B']['qty'],100)
        self.assertEqual(x.positions['C']['qty'],100)
        self.assertEqual(x.cash,1490)

    def test_sells_before_buys(self):
        x=Ledger(4000,['A','B']);x.fill('A','BUY',400,10,10,0,'2024-01-01')
        p=plan(x,{'A':0,'B':300},{'A':0,'B':'.95'})
        out=OrderExecutor().execute(x,p,{'A':quote(),'B':quote()},'2024-01-03',COST,100)
        self.assertEqual([t['side'] for t in out['trades']],['SELL','BUY'])
        self.assertEqual(x.cash,990)

    def test_open_not_hlc_and_unknown_status_not_assumed(self):
        x=Ledger(10000,['A']);p=plan(x,{'A':400},{'A':'.95'})
        y=copy.deepcopy(x);a=quote();b=quote();b.update(high=9999,low='.01',close=8888)
        out1=OrderExecutor().execute(x,p,{'A':a},'2024-01-03',COST,100)
        out2=OrderExecutor().execute(y,p,{'A':b},'2024-01-03',COST,100)
        self.assertEqual(out1,out2)
        z=Ledger(10000,['A']);out=OrderExecutor().execute(z,p,{'A':quote(status='unknown')},'2024-01-03',COST,100)
        self.assertEqual(out['trades'],[])
        self.assertEqual(out['rejected'][0]['reason'],'unknown_status')

    def test_symbol_specific_limits(self):
        x=Ledger(10000,['A','B']);p=plan(x,{'A':400,'B':400})
        a=quote(open=11);a['upper_limit']=11
        b=quote(open=11);b['upper_limit']=12
        out=OrderExecutor().execute(x,p,{'A':a,'B':b},'2024-01-03',COST,100)
        self.assertEqual([t['symbol'] for t in out['trades']],['B'])
        self.assertEqual(out['rejected'][0]['reason'],'adverse_open_limit')

    def test_plan_transform_preserves_money_caps(self):
        x=Ledger(10000,['A']);p=plan(x,{'A':400},{'A':'.95'});before=copy.deepcopy(p)
        transform_plan(p,'A',2,100)
        self.assertEqual(p['orders'][0]['quantity'],800)
        for k in ('signal_planned_notional','signal_weight_budget'):
            self.assertEqual(p['orders'][0][k],before['orders'][0][k])

    def test_zero_target_odd_residual_requires_evidence(self):
        x=Ledger(1000,['A']);x.fill('A','BUY',100,10,10,0,'2024-01-01');x.record('A','S');x.ex('A','S',0,'1.25','exact')
        p=plan(x,{'A':0},{'A':0});OrderExecutor().execute(x,p,{'A':quote()},'2024-01-03',COST,100)
        self.assertEqual(x.positions['A']['qty'],25)

if __name__=='__main__':unittest.main()
