"""H003 synthetic causal/ledger checks; NONE of these are historical returns."""
import copy
from decimal import Decimal as D, Context, localcontext
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest

from leek.contract import DataBlocked
from leek.mean_reversion_signal import MODEL_ID, MeanReversion20
from leek.real_backtest import simulate
from research.run_h003 import run, screen
from test_real_history import fixture


class H003SignalTests(unittest.TestCase):
    def test_warmup_and_flat_no_entry(self):
        s=MeanReversion20()
        for _ in range(20):
            self.assertFalse(s.update(F(5)))
        self.assertFalse(s.update(F(4)))  # zero variance, no entry
        self.assertEqual(len(s.history),20)

    def test_exact_two_sigma_equal_entry_and_mean_exit(self):
        s=MeanReversion20()
        for p in [4]*10+[6]*10:
            self.assertFalse(s.update(F(p)))
        self.assertTrue(s.update(F(3)))  # mean=5 and variance=1
        self.assertTrue(s.update(F(4)))
        self.assertFalse(s.update(F(5))) # equal to new history mean? see independent oracle below

    def test_threshold_uses_strictly_prior_twenty(self):
        s=MeanReversion20()
        for p in [4]*10+[6]*10:
            s.update(F(p))
        self.assertTrue(s.update(F(3)))

    def test_ex_day_total_return_not_raw_drop(self):
        s=MeanReversion20(); q=MeanReversion20()
        history=[F(99,10)]*10+[F(10)]*10
        for v in history:
            s.update(v);q.update(v)
        self.assertFalse(s.update(F(10)))
        self.assertTrue(q.update(F(9))) # rejected raw-price proxy would trigger

    def test_bad_input_is_atomic(self):
        s=MeanReversion20()
        s.update(F(5))
        for x in (False,2.0,3,'4',None,F(0),F(-1)):
            old=copy.deepcopy(s.__dict__)
            with self.assertRaises(DataBlocked):
                s.update(x)
            self.assertEqual(old,s.__dict__)

    def test_independent_fixed_oracle_and_bounded_history(self):
        import random
        rng=random.Random(20261022)
        seq=[F(rng.randint(5,40),4) for _ in range(500)]
        s=MeanReversion20(); expected=False
        for i,p in enumerate(seq):
            if i>=20:
                h=seq[i-20:i]
                mean=sum(h,F(0))/20
                variance=sum(((x-mean)**2 for x in h),F(0))/20
                if expected and p>=mean: expected=False
                elif not expected and variance>0 and p<mean and (mean-p)**2>=4*variance: expected=True
            self.assertEqual(s.update(p),expected)
        self.assertEqual(len(s.history),20)

    def test_future_mutation_cannot_change_prefix(self):
        prefix=[F(4)]*10+[F(6)]*10+[F(3)]
        a,b=MeanReversion20(),MeanReversion20()
        self.assertEqual([a.update(v) for v in prefix],[b.update(v) for v in prefix])
        self.assertFalse(a.update(F(7)))
        self.assertTrue(b.update(F(1)))


class H003LedgerTests(unittest.TestCase):
    def history(self):
        c,b,e=fixture()
        for i in range(110,120):
            p='4' if i%2==0 else '6'
            b[i].update(open=p,close=p,high=p,low=p)
        for i,p in [(120,'3'),(121,'3.1'),(122,'3.2'),(123,'6'),(124,'6')]:
            b[i].update(open=p,close=p,high=p,low=p)
        return c,b,e

    def execute(self,c,b,e,strategy,cost):
        with localcontext(Context(prec=64)):
            return simulate(b,e,c,strategy,cost)

    def test_synthetic_signal_ledger_entry_exit_and_account_invariants(self):
        c,b,e=self.history()
        result=self.execute(c,b,e,MODEL_ID,c['cost_cases']['base'])
        orders=[o for o in result['orders'] if o['status']=='filled']
        self.assertTrue(any(o['side']=='BUY' for o in orders))
        self.assertTrue(any(o['side']=='SELL' for o in orders))
        self.assertTrue(all(o['signal_date']<o['execute_on'] for o in orders))
        self.assertTrue(all(o['execute_on']>=c['evaluation_start'] for o in orders))
        for d in result['daily']:
            self.assertEqual(D(d['nav']),D(d['cash'])+D(d['market_value'])+D(d['receivables']))
            self.assertEqual(D(d['nav'])-50000,D(d['realized_trading_pnl'])+
                D(d['unrealized_trading_pnl'])+D(d['dividend_income']))
        total=sum((D(t['net_pnl']) for t in result['closed_trades']),D(0))
        total+=sum((D(t['marked_net_pnl']) for t in result['open_trades']),D(0))
        self.assertEqual(D(result['daily'][-1]['nav'])-50000,total)

    def test_future_changes_do_not_affect_prior_intent(self):
        c,b,e=self.history()
        original=self.execute(c,b,e,MODEL_ID,c['cost_cases']['base'])
        self.assertTrue(original['orders'])
        i=next(i for i,x in enumerate(b) if x['date']==original['orders'][0]['execute_on'])
        changed=copy.deepcopy(b)
        for x in changed[i+2:]:
            x.update(high='10',low='1',close='4')
        other=self.execute(c,changed,e,MODEL_ID,c['cost_cases']['base'])
        self.assertEqual(original['orders'][0],other['orders'][0])
        self.assertEqual([s for s in original['signals'] if s['asof']<b[i]['date']],
                         [s for s in other['signals'] if s['asof']<b[i]['date']])

    def test_stress_recomputes_costs_and_does_not_change_baseline(self):
        c,b,e=self.history()
        a=self.execute(c,b,e,MODEL_ID,c['cost_cases']['base'])
        z=self.execute(c,b,e,MODEL_ID,c['cost_cases']['stress'])
        self.assertGreaterEqual(z['summary']['commission'],a['summary']['commission'])
        self.assertFalse(a['summary']['automatic_promotion'])
        cash=self.execute(c,b,e,'cash',c['cost_cases']['base'])
        self.assertEqual(cash['summary']['terminal_nav'],50000)

    def test_frozen_screen_rejects_failures(self):
        passes=dict(total_return_pct=2,max_close_drawdown_pct=-3,closed_trades=25,profit_factor=2)
        good={'base__'+MODEL_ID:dict(passes),
              'stress__'+MODEL_ID:dict(passes),
              'base__buy_hold':dict(passes,total_return_pct=1,max_close_drawdown_pct=-5)}
        self.assertEqual(screen(good)['decision'],'RESEARCH_SCREEN_PASS')
        bad=copy.deepcopy(good);bad['stress__'+MODEL_ID]['closed_trades']=19
        self.assertEqual(screen(bad)['decision'],'REJECTED_DEVELOPMENT_SCREEN')

    def test_dq001_gate_rejects_before_creating_or_fetching(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'new-data'; out=Path(tmp)/'new-report'
            with self.assertRaises(DataBlocked):
                run(data,out,fetch=True,allow_single_source=True)
            self.assertFalse(data.exists())
            self.assertFalse(out.exists())


if __name__=='__main__': unittest.main()
