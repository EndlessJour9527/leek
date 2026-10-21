import copy,unittest
from decimal import Decimal as D
from portfolio import PortfolioEngine,segment
from contract import DataBlocked

COST={'commission_rate':0,'minimum_commission_cny':5,'adverse_slippage_rate':0}
def quote(px=10,status='trading_verified'):
    if status=='suspended_verified':return dict(status=status,suspension_evidence='synthetic official halt')
    return dict(open=px,high=px,low=px,close=px,status=status,upper_limit=D(px)*2,lower_limit=D(px)/2,limit_evidence='synthetic verified')
def event(**kw):
    e=dict(id='E',symbol='A',status='implemented',record_date='2024-01-02',effective_date='2024-01-03',phase='before_open',pay_date='2024-01-04',cash_per_old_share=1,ratio=1,rounding='exact',known_at='2024-01-01T00:00:00+08:00');e.update(kw);return e

def engine(events=()):return PortfolioEngine(['A'],10000,list(events),COST,100,{'A':False})
def fixed():return {'kind':'fixed','weights':{'A':'.95'}}

class PortfolioIntegrationTests(unittest.TestCase):
    def test_payment_after_close_unspendable_at_open(self):
        x=engine([event()])
        x.step('2024-01-01',{'A':quote()},fixed(),'2024-01-02')
        x.step('2024-01-02',{'A':quote()})
        x.step('2024-01-03',{'A':quote(9)},fixed(),'2024-01-04')
        cash_before=x.ledger.cash;recv=sum(x.ledger.receivables.values())
        x.step('2024-01-04',{'A':quote(9)})
        trades=x.executions[-1]['trades']
        if trades:self.assertLessEqual(sum(t['quantity']*t['fill_price']+t['commission'] for t in trades),cash_before)
        self.assertEqual(sum(x.ledger.receivables.values()),0)
        self.assertEqual(x.event_log[-1]['phase'],'after_close')
        self.assertEqual(x.event_log[-1]['amount'],recv)

    def test_after_close_split_keeps_signal_pre_basis_next_quote_once(self):
        e=event(record_date='2024-01-02',effective_date='2024-01-02',phase='after_close',ratio=2,cash_per_old_share=0,pay_date=None)
        x=engine([e]);x.step('2024-01-01',{'A':quote()},fixed(),'2024-01-02')
        row=x.step('2024-01-02',{'A':quote()},fixed(),'2024-01-03')
        self.assertEqual(x.signals[-1]['plan']['signal_closes']['A'],10)
        self.assertEqual(row['marks']['A'],5)
        self.assertEqual(row['positions']['A']['qty'],1800)
        tr=row['tr']['A'];nav=row['nav']
        row2=x.step('2024-01-03',{'A':quote(5)})
        self.assertEqual(row2['tr']['A'],tr)
        self.assertEqual(row2['nav'],nav)

    def test_halted_reverse_split_stale_and_account_rounding(self):
        e=event(cash_per_old_share=0,ratio='.36555',rounding='ceil_whole_account',pay_date=None)
        x=engine([e]);x.step('2024-01-01',{'A':quote()},fixed(),'2024-01-02');x.step('2024-01-02',{'A':quote()})
        pre=x.daily[-1];row=x.step('2024-01-03',{'A':quote(status='suspended_verified')})
        self.assertTrue(row['stale']['A'])
        self.assertAlmostEqual(row['tr']['A'],pre['tr']['A'],places=30)
        self.assertGreater(row['nav'],pre['nav'])
        rounding=x.event_log[-1]['rounding_nav_delta']
        self.assertAlmostEqual(row['nav']-pre['nav'],rounding,places=30)
        row2=x.step('2024-01-04',{'A':quote(row['marks']['A'])})
        self.assertAlmostEqual(row2['tr']['A'],row['tr']['A'],places=30)

    def test_future_data_does_not_rewrite_sealed_prefix(self):
        a,b=engine(),engine()
        for x in (a,b):
            x.step('2024-01-01',{'A':quote()},fixed(),'2024-01-02');x.step('2024-01-02',{'A':quote()})
        a.step('2024-01-03',{'A':quote(11)})
        b.step('2024-01-03',{'A':quote(15)})
        self.assertEqual(a.daily[:2],b.daily[:2]);self.assertEqual(a.executions,b.executions)
        self.assertEqual(a.signals,b.signals)

    def test_unknown_factor_blocks_decision_not_actual_account(self):
        e=event(record_date='2024-01-02',effective_date='2024-01-02',phase='after_close',ratio=2,cash_per_old_share=0,pay_date=None,known_at='2024-01-04T23:59:59+08:00')
        x=engine([e]);x.step('2024-01-01',{'A':quote()},fixed(),'2024-01-02');x.step('2024-01-02',{'A':quote()})
        self.assertEqual(x.ledger.positions['A']['qty'],1800)
        with self.assertRaises(DataBlocked):x.step('2024-01-03',{'A':quote(5)},fixed(),'2024-01-04')

    def test_cancelled_event_never_applied(self):
        x=engine([event(status='cancelled')]);x.step('2024-01-01',{'A':quote()},fixed(),'2024-01-02');x.step('2024-01-02',{'A':quote()});x.step('2024-01-03',{'A':quote()})
        self.assertEqual(x.event_log,[])
        self.assertEqual(x.ledger.positions['A']['qty'],900)

    def test_segment_keeps_first_day_fee_and_no_terminal_order(self):
        x=engine();x.step('2024-01-01',{'A':quote()},fixed(),'2024-01-02',active=False)
        x.step('2024-01-02',{'A':quote()});x.step('2024-01-03',{'A':quote(11)},fixed(),None)
        all_seg=segment(x.daily,'2024-01-02','2024-01-03',10000)
        last_seg=segment(x.daily,'2024-01-03','2024-01-03',10000)
        self.assertEqual(all_seg['starting_nav'],10000)
        self.assertEqual(last_seg['starting_nav'],9995)
        self.assertIsNone(x.pending)
        self.assertEqual(len(x.executions),1)
        self.assertEqual(x.ledger.positions['A']['qty'],900)

    def test_missing_held_quote_blocks_no_forward_fill(self):
        x=engine();x.step('2024-01-01',{'A':quote()})
        with self.assertRaises(DataBlocked):x.step('2024-01-02',{'A':{'status':'unknown'}})
        with self.assertRaises(DataBlocked):x.step('2024-01-02',{})

if __name__=='__main__':unittest.main()
