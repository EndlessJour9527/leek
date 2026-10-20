"""Synthetic engineering tests: no assertion of investment performance."""
import copy
from decimal import Context, localcontext
from fractions import Fraction
import random
import unittest
from leek.channel_signal import CloseChannel2010, MODEL_ID
from leek.contract import DataBlocked
from leek.real_backtest import simulate
from tests.test_real_history import fixture, ZERO


def run_case(config, bars, events):
    with localcontext(Context(prec=64)):
        return simulate(bars, events, config, MODEL_ID, ZERO)


class ChannelTests(unittest.TestCase):
    def test_current_close_excluded_and_equal_holds(self):
        signal=CloseChannel2010()
        for _ in range(20): self.assertFalse(signal.update(Fraction(4)))
        self.assertTrue(signal.update(Fraction(5)))
        self.assertTrue(signal.update(Fraction(4)))
        self.assertFalse(signal.update(Fraction(3)))

    def test_explicit_exit_is_ten_days_not_twenty(self):
        signal=CloseChannel2010()
        for _ in range(20): signal.update(Fraction(1))
        signal.update(Fraction(10))
        for _ in range(10): signal.update(Fraction(10))
        self.assertFalse(signal.update(Fraction(9)))

    def test_invalid_observation_is_atomic(self):
        signal=CloseChannel2010(); signal.update(Fraction(4))
        for bad in (Fraction(0),Fraction(-1),True,4.0,'4',None):
            old=copy.deepcopy(signal.__dict__)
            with self.assertRaises(DataBlocked): signal.update(bad)
            self.assertEqual(old,signal.__dict__)

    def test_bounded_memory(self):
        signal=CloseChannel2010()
        for value in range(1,1001): signal.update(Fraction(value))
        self.assertEqual(len(signal.history),20)

    def test_seeded_independent_batch_oracle(self):
        rng=random.Random(20261020)
        for _ in range(40):
            values=[Fraction(rng.randint(1,30),rng.randint(1,4)) for _ in range(150)]
            signal=CloseChannel2010(); expected=False
            for i,v in enumerate(values):
                if i>=20:
                    if expected:
                        if v<min(values[i-10:i]): expected=False
                    elif v>max(values[i-20:i]): expected=True
                self.assertEqual(signal.update(v),expected)

    def test_prefix_unchanged_by_future_path(self):
        prefix=[Fraction(i) for i in range(1,30)]
        a=CloseChannel2010(); b=CloseChannel2010()
        self.assertEqual([a.update(x) for x in prefix],[b.update(x) for x in prefix])
        self.assertTrue(a.update(Fraction(100)))
        self.assertFalse(b.update(Fraction(1)))

    def test_no_same_close_fill_or_warmup_trade(self):
        c,b,e=fixture(); result=run_case(c,b,e)
        self.assertTrue(result['orders'])
        for order in result['orders']:
            self.assertGreater(order['execute_on'],order['signal_date'])
            self.assertGreaterEqual(order['execute_on'],c['evaluation_start'])

    def test_dividend_ex_does_not_create_false_exit(self):
        c,b,e=fixture(True); result=run_case(c,b,e)
        self.assertEqual(result['summary']['terminal_nav'],50000)
        self.assertEqual(result['summary']['closed_trades'],0)
        self.assertGreater(result['summary']['dividend_income'],0)

    def test_future_open_does_not_resize_intent(self):
        c,b,e=fixture(); original=run_case(c,b,e)
        day=original['orders'][0]['execute_on']; mutated=copy.deepcopy(b)
        next(x for x in mutated if x['date']==day).update(open='8',high='8')
        changed=run_case(c,mutated,e)
        for key in ('quantity','signal_date','id','side'):
            self.assertEqual(original['orders'][0][key],changed['orders'][0][key])

    def test_future_ohlc_does_not_change_prefix(self):
        c,b,e=fixture(); original=run_case(c,b,e); mutated=copy.deepcopy(b)
        for row in mutated[135:]: row.update(open='8',close='8',high='8',low='8')
        changed=run_case(c,mutated,e)
        for key in ('signals','orders','daily'):
            timekey={'signals':'asof','orders':'execute_on','daily':'date'}[key]
            self.assertEqual([x for x in original[key] if x[timekey]<b[135]['date']],
                             [x for x in changed[key] if x[timekey]<b[135]['date']])

    def test_terminal_intent_does_not_trade(self):
        c,b,e=fixture(); b[-1].update(close='1',low='1'); result=run_case(c,b,e)
        self.assertEqual(result['terminal_intent']['side'],'SELL')
        self.assertIsNone(result['terminal_intent']['execute_on'])
        self.assertEqual(result['summary']['closed_trades'],0)

    def test_no_events_all_account_pnl_reconciles(self):
        c,b,e=fixture(); b[138].update(close='2',low='2'); result=run_case(c,b,e)
        from decimal import Decimal as D
        for r in result['daily']:
            self.assertEqual(D(r['nav'])-D(c['initial_cash']),
                D(r['realized_trading_pnl'])+D(r['unrealized_trading_pnl'])+D(r['dividend_income']))

if __name__=='__main__': unittest.main()
