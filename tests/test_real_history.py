"""Entirely synthetic fixtures test the real-history engine, NOT market performance."""
import copy
from datetime import date, timedelta
from decimal import Decimal as D, Context, localcontext
import json
from pathlib import Path
import tempfile
import unittest

from leek.contract import DataBlocked
from leek.history_data import parse_eastmoney, parse_tencent, parse_dividends, crosscheck, validate_bars
from leek.real_backtest import simulate, checked_config, _price, _fee

ROOT=Path(__file__).resolve().parents[1]
ZERO={'commission_rate':'0','minimum_commission':'0','slippage_bps':'0'}


def fixture(dividend=False):
    config=json.loads((ROOT/'research/real_history_protocol.json').read_text())
    days=[str(date(2019,1,2)+timedelta(days=i)) for i in range(150)]
    config.update(warmup_start='2019-01-01',evaluation_start=days[122],evaluation_end=days[-1])
    values=['4']*120+['4.2']*30
    events=[]
    if dividend:
        values[125:]=['4.1']*25
        events=[dict(event_id='DTEST',record_date=days[124],ex_date=days[125],pay_date=days[128],
                     cash_per_share='0.1',source_url='https://example.com/synthetic-fixture')]
    bars=[dict(date=day,open=p,close=p,high=str(D(p)+D('.01')),low=str(D(p)-D('.01')),volume_lots='10000') for day,p in zip(days,values)]
    return config,bars,events


def calculate(bars,events,config,strategy='h001_3d',case=ZERO):
    with localcontext(Context(prec=64)):
        return simulate(bars,events,config,strategy,case)


class RealHistoryEngineTests(unittest.TestCase):
    def test_all_variants_have_same_window_and_cash_baseline(self):
        c,b,e=fixture()
        rs=[calculate(b,e,c,s) for s in c['strategies']]
        self.assertEqual({r['summary']['evaluated_sessions'] for r in rs},{28})
        self.assertTrue(all(r['summary']['first_tradeable_date']==c['evaluation_start'] for r in rs))
        self.assertEqual(rs[0]['summary']['terminal_nav'],50000)
        self.assertEqual(rs[0]['orders'],[])

    def test_no_lookahead_and_no_warmup_trades(self):
        c,b,e=fixture(); r=calculate(b,e,c)
        self.assertTrue(r['orders'])
        for o in r['orders']:
            self.assertGreater(o['execute_on'],o['signal_date'])
            self.assertGreaterEqual(o['execute_on'],c['evaluation_start'])
        self.assertEqual(r['orders'][0]['execute_on'],b[123]['date'])

    def test_three_day_confirmation_delays_entry(self):
        c,b,e=fixture(); fast=calculate(b,e,c,'ma120_1d'); slow=calculate(b,e,c)
        self.assertLess(fast['orders'][0]['execute_on'],slow['orders'][0]['execute_on'])

    def test_dividend_drop_preserves_nav_and_exact_signal(self):
        c,b,e=fixture(True); r=calculate(b,e,c)
        self.assertEqual(r['summary']['terminal_nav'],50000)
        self.assertEqual(r['summary']['filled_orders'],1)
        self.assertEqual(r['summary']['dividend_income'],230)
        self.assertEqual(r['summary']['closed_trades'],0)
        self.assertTrue(all(x['state']=='ON' for x in r['signals'] if x['asof']>=b[123]['date']))
        record,ex,pay=[r['daily'][i-122] for i in (124,125,128)]
        self.assertEqual(D(ex['cash']),D(record['cash']))
        self.assertEqual(D(ex['receivables']),230)
        self.assertEqual(D(pay['receivables']),0)
        self.assertEqual(D(pay['cash'])-D(ex['cash']),230)

    def test_sale_on_ex_retains_income_in_closed_trade(self):
        c,b,e=fixture(True)
        for i in range(124,150):
            p='3.9' if i==124 else '3.8'
            b[i].update(open=p,close=p,high=str(D(p)+D('.01')),low=str(D(p)-D('.01')))
        r=calculate(b,e,c,'ma120_1d')
        self.assertEqual(r['summary']['closed_trades'],1)
        trade=r['closed_trades'][0]
        self.assertEqual(trade['exit_date'],b[125]['date'])
        self.assertEqual(D(trade['income']),230)
        self.assertEqual(D(trade['net_pnl']),D('-690'))
        self.assertEqual(r['summary']['terminal_nav'],49310)
        self.assertEqual(r['summary']['closed_win_rate_pct'],0)

    def test_ex_day_buyer_gets_no_dividend(self):
        c,b,e=fixture(True)
        e[0].update(record_date=b[121]['date'],ex_date=b[122]['date'],pay_date=b[128]['date'])
        r=calculate(b,e,c,'buy_hold')
        self.assertEqual(r['summary']['dividend_income'],0)

    def test_fees_and_adverse_tick_rounding_once(self):
        c,b,e=fixture(); case=c['cost_cases']['base']; r=calculate(b,e,c,'buy_hold',case)
        o=r['orders'][0]; q=D(o['quantity']); px=D(o['fill_price']); fee=D(o['commission'])
        self.assertEqual(px,D('4.203'))
        self.assertEqual(fee,5)
        expected=D('50000')-q*px-fee+q*D('4.2')
        self.assertEqual(D(str(r['summary']['terminal_nav'])),expected)
        self.assertEqual(D(o['slippage']),q*D('.003'))

    def test_unrealized_loss_in_drawdown_and_total_return(self):
        c,b,e=fixture()
        b[-1].update(close='2',low='2')
        r=calculate(b,e,c,'buy_hold')
        self.assertLess(r['summary']['max_close_drawdown_pct'],0)
        self.assertLess(r['summary']['total_return_pct'],0)
        self.assertEqual(r['summary']['closed_trades'],0)
        self.assertIsNone(r['summary']['closed_win_rate_pct'])

    def test_terminal_intent_is_not_filled(self):
        c,b,e=fixture(); b[-1].update(close='2',low='2')
        r=calculate(b,e,c,'ma120_1d')
        self.assertEqual(r['terminal_intent']['side'],'SELL')
        self.assertIsNone(r['terminal_intent']['execute_on'])
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_future_hlc_does_not_change_earlier_execution(self):
        c,b,e=fixture(); r=calculate(b,e,c)
        changed=copy.deepcopy(b)
        for row in changed[123:]: row.update(high='9',low='1',close='7')
        a=calculate(changed,e,c)
        self.assertEqual(r['orders'][0],a['orders'][0])
        self.assertEqual([s for s in r['signals'] if s['asof']<b[123]['date']],
                         [s for s in a['signals'] if s['asof']<b[123]['date']])

    def test_future_open_cannot_resize_prior_intent(self):
        c,b,e=fixture(); r=calculate(b,e,c)
        b[123].update(open='5',high='5')
        a=calculate(b,e,c)
        for key in ('quantity','id','signal_date','execute_on','side'):
            self.assertEqual(r['orders'][0][key],a['orders'][0][key])
        self.assertNotEqual(r['orders'][0]['fill_price'],a['orders'][0]['fill_price'])

    def test_gap_cash_rejection_does_not_charge_fees(self):
        c,b,e=fixture(); b[123].update(open='100',high='100')
        r=calculate(b,e,c,case=c['cost_cases']['base'])
        self.assertEqual(r['orders'][0]['status'],'rejected')
        self.assertEqual(r['orders'][0]['commission'],'0')
        self.assertEqual(r['orders'][0]['cash_before'],r['orders'][0]['cash_after'])

    def test_daily_reconciliation_and_trade_attribution(self):
        c,b,e=fixture(True); r=calculate(b,e,c,case=c['cost_cases']['base'])
        for row in r['daily']:
            self.assertEqual(D(row['nav']),D(row['cash'])+D(row['market_value'])+D(row['receivables']))
            self.assertEqual(D(row['nav'])-50000,D(row['realized_trading_pnl'])+D(row['unrealized_trading_pnl'])+D(row['dividend_income']))
            self.assertGreaterEqual(D(row['cash']),0)
        net=sum((D(x['net_pnl']) for x in r['closed_trades']),D(0))+sum((D(x['marked_net_pnl']) for x in r['open_trades']),D(0))
        self.assertEqual(D(r['daily'][-1]['nav'])-50000,net)

    def test_stress_is_full_resimulation_and_not_automatic_promotion(self):
        c,b,e=fixture(); base=calculate(b,e,c,'buy_hold',c['cost_cases']['base'])
        stress=calculate(b,e,c,'buy_hold',c['cost_cases']['stress'])
        self.assertLess(stress['summary']['terminal_nav'],base['summary']['terminal_nav'])
        self.assertFalse(stress['summary']['automatic_promotion'])

    def test_event_missing_payment_duplicate_and_bad_date_block(self):
        for field,val in [('pay_date','2099-01-01'),('record_date','1900-01-01'),('cash_per_share','NaN')]:
            c,b,e=fixture(True); e[0][field]=val
            with self.subTest(field=field),self.assertRaises((DataBlocked,ValueError)): calculate(b,e,c)
        c,b,e=fixture(True); e.append(copy.deepcopy(e[0]))
        with self.assertRaises(DataBlocked): calculate(b,e,c)

    def test_duplicate_prices_fail_closed(self):
        c,b,e=fixture(); b[50]=copy.deepcopy(b[49])
        with self.assertRaises(DataBlocked): calculate(b,e,c)

    def test_cost_config_nan_and_invalid_rules_fail(self):
        c,b,e=fixture(); c['cost_cases']['base']['commission_rate']='NaN'
        with self.assertRaises((ValueError,DataBlocked)): checked_config(c)
        c,b,e=fixture(); c['lookback']=121
        with self.assertRaises(DataBlocked): checked_config(c)


class RealHistoryAdapterTests(unittest.TestCase):
    def test_parse_raw_provider_schemas(self):
        em={'data':{'code':'510300','klines':['2020-01-02,4.000,4.100,4.200,3.900,1000,0,0,0,0,0']}}
        tx={'data':{'sh510300':{'day':[['2020-01-02','4','4.1','4.2','3.9','1000']]}}}
        a=parse_eastmoney(json.dumps(em)); b=parse_tencent(json.dumps(tx))
        self.assertEqual(crosscheck(a,b)['ohlc_cells'],4)

    def test_adjusted_series_never_silently_used(self):
        data={'data':{'sh510300':{'qfqday':[['2020-01-02','4','4','4','4','10']]}}}
        with self.assertRaises(DataBlocked):parse_tencent(json.dumps(data))

    def test_one_tick_or_calendar_disagreement_blocks(self):
        _,bars,_=fixture(); alt=copy.deepcopy(bars)
        alt[5]['open']='4.001'
        with self.assertRaises(DataBlocked): crosscheck(bars,alt)
        with self.assertRaises(DataBlocked): crosscheck(bars,bars[:-1])

    def test_dividend_per_ten_conversion(self):
        html='<table><tr><td>2025年</td><td>2025-06-17</td><td>2025-06-18</td><td>每10份派现金0.8800元</td><td>2025-06-27</td></tr></table>'
        events=parse_dividends(html.encode(),'2019-01-01','2025-12-31')
        self.assertEqual(D(events[0]['cash_per_share']),D('.088'))

    def test_unsupported_split_in_period_blocks(self):
        html='<table><tr><td>2025-06-18</td><td>份额折算</td></tr></table>'
        with self.assertRaises(DataBlocked): parse_dividends(html.encode(),'2019-01-01','2025-12-31')

    def test_zero_volume_and_excess_precision_fail(self):
        for field,value in [('volume_lots','0'),('open','4.0001')]:
            _,bars,_=fixture(); bars[0][field]=value
            with self.subTest(field=field),self.assertRaises(DataBlocked):validate_bars(bars)

if __name__=='__main__': unittest.main()
