import copy
import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal, Context, localcontext

from leek.contract import DataBlocked
from leek import cash_dividend_replay as ca


def inputs():
    calendar = ['2030-01-%02d' % i for i in range(1, 9)]
    prices = {'AAA': ['9', '10', '10', '9', '9', '10', '10', '9'],
              'BBB': ['2'] * 8}
    bars = {s: [dict(date=d, open=p, high=p, low=p, close=p)
                for d, p in zip(calendar, series)] for s, series in prices.items()}
    event = dict(event_id='DIV1', instrument='AAA', kind='cash_dividend',
                 published_on=calendar[0], record_date=calendar[2], ex_date=calendar[3],
                 pay_date=calendar[5], cash_per_old_share='1', split_ratio='1', rounding='exact')
    data = dict(version=ca.VERSION, synthetic=True, instruments=['AAA', 'BBB'],
                currency='SIM', adjustment='raw', corporate_actions=[event], calendar=calendar, bars=bars)
    config = dict(version=ca.VERSION, initial_cash='1000', quantities={'AAA': '10', 'BBB': '10'},
                  commission='0', slippage_bps='0', lookback=1, symbol_priority=['AAA', 'BBB'],
                  execution_policy=ca.POLICY, corporate_action_policy=ca.CA_POLICY)
    return config, data


def replay(config, data, count=None):
    ca.validate(config, data)
    with localcontext(Context(prec=64)):
        return ca._replay(config, data, count or len(data['calendar']), {})


class CashDividendTests(unittest.TestCase):
    def test_record_sale_ex_and_delayed_payment(self):
        c, d = inputs()
        r = replay(c, d)
        self.assertEqual(r['daily'][2]['positions']['AAA']['quantity'], '10')
        ex = r['daily'][3]
        self.assertEqual(ex['positions']['AAA']['quantity'], '0')
        self.assertEqual(ex['receivables'], '10')
        self.assertEqual(ex['dividend_income'], '10')
        self.assertEqual(ex['cash'], '990')
        self.assertEqual(ex['nav'], '1000')
        self.assertEqual(r['daily'][5]['receivables'], '0')
        self.assertEqual(r['daily'][5]['dividend_income'], '10')
        self.assertEqual(r['daily'][5]['cash'], '1000')
        self.assertEqual([e['phase'] for e in r['corporate_action_log']],
                         ['record_close', 'ex_before_open', 'pay_after_trading'])

    def test_total_return_not_raw_ex_drop(self):
        c, d = inputs()
        c['lookback'] = 2
        r = replay(c, d)
        # Prices 10 -> 9 plus dividend 1: no loss in the signal series.
        self.assertEqual(r['daily'][2]['positions']['AAA']['total_return_level'], '10')
        self.assertEqual(r['daily'][3]['positions']['AAA']['total_return_level'], '10')
        self.assertEqual(next(s for s in r['signals'] if s['instrument']=='AAA' and s['asof']==d['calendar'][3])['target_quantity'], '0')

    def test_zero_entitlement_still_logs_zero_payment(self):
        c, d = inputs()
        c['lookback'] = 7
        r = replay(c, d)
        self.assertEqual(r['daily'][-1]['dividend_income'], '0')
        self.assertEqual(r['corporate_action_log'][-1]['amount'], '0')

    def test_ex_day_buy_not_entitled(self):
        c, d = inputs()
        d['corporate_actions'][0]['record_date'] = d['calendar'][1]
        d['corporate_actions'][0]['ex_date'] = d['calendar'][2]
        r = replay(c, d)
        self.assertEqual(r['daily'][2]['positions']['AAA']['quantity'], '10')
        self.assertEqual(r['daily'][2]['dividend_income'], '0')

    def test_cash_receivable_not_buying_power(self):
        c, d = inputs()
        c['initial_cash'] = '100'
        # On ex day A sells for 90. B needs 100; even 10 receivable cannot fund.
        for i, p in enumerate(['9','9','10','10','10','10','10','10']):
            d['bars']['BBB'][i].update(open=p, high=p, low=p, close=p)
        d['corporate_actions'][0]['pay_date'] = d['calendar'][3]
        r = replay(c, d)
        rejected = [o for o in r['orders'] if o['instrument']=='BBB' and o['execute_on']==d['calendar'][3]][0]
        self.assertEqual(rejected['reason'], 'INSUFFICIENT_CASH')
        self.assertEqual(r['daily'][3]['cash'], '100')

    def test_income_attribution_and_nav_all_days(self):
        c, d = inputs()
        c.update(commission='0.01', slippage_bps='5')
        r = replay(c, d)
        for row in r['daily']:
            self.assertEqual(Decimal(row['nav'])-Decimal(c['initial_cash']), Decimal(row['total_pnl']))
            self.assertEqual(sum((Decimal(p['total_pnl']) for p in row['positions'].values()), Decimal(0)), Decimal(row['total_pnl']))
            self.assertEqual(Decimal(row['cash'])+sum((Decimal(p['nav_contribution']) for p in row['positions'].values()), Decimal(0)), Decimal(row['nav']))

    def test_no_events_price_signal_equivalence(self):
        c, d = inputs()
        d['corporate_actions'] = []
        r = replay(c,d)
        for signal in r['signals']:
            i=d['calendar'].index(signal['asof']);s=signal['instrument']
            expected=c['quantities'][s] if Decimal(d['bars'][s][i]['close'])>Decimal(d['bars'][s][i-1]['close']) else '0'
            self.assertEqual(signal['target_quantity'],expected)

    def test_future_event_does_not_rewrite_past(self):
        c,d=inputs(); before=replay(c,d,2)
        changed=copy.deepcopy(d); changed['corporate_actions'][0]['cash_per_old_share']='2'
        self.assertEqual(before,replay(c,changed,2))

    def test_event_input_order_independent(self):
        c,d=inputs();e=copy.deepcopy(d['corporate_actions'][0]);e.update(instrument='BBB',cash_per_old_share='0.1')
        d['corporate_actions'].append(e);r=replay(c,d);d['corporate_actions'].reverse()
        self.assertEqual(r,replay(c,d))

    def test_future_open_changes_only_execution(self):
        c,d=inputs();r=replay(c,d,3);changed=copy.deepcopy(d)
        changed['bars']['AAA'][3].update(open='8',low='8')
        self.assertEqual(r,replay(c,changed,3))

    def test_reject_event_variants(self):
        mutations=[('kind','split'),('split_ratio','2'),('rounding','ceil_whole_account'),
                   ('cash_per_old_share','0'),('cash_per_old_share','NaN'),('cash_per_old_share','10'),
                   ('published_on','2030-01-04'),('record_date','2029-12-31'),
                   ('ex_date','2030-01-03'),('pay_date','2030-01-03'),('pay_date','2030-01-09'),
                   ('event_id','x:y'),('instrument','MISSING'),('published_on',None)]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                c,d=inputs();d['corporate_actions'][0][key]=value
                with self.assertRaises((DataBlocked,ValueError)):replay(c,d)

    def test_unknown_fields_and_duplicate_events(self):
        for variant in ('extra','duplicate','same_ex'):
            c,d=inputs()
            if variant=='extra':d['corporate_actions'][0]['tax']='0'
            else:
                e=copy.deepcopy(d['corporate_actions'][0])
                if variant=='same_ex':e['event_id']='DIV2'
                d['corporate_actions'].append(e)
            with self.assertRaises(DataBlocked):replay(c,d)

    def test_reject_policy_real_data_and_schemas(self):
        for variant in ('policy','real','version','list'):
            c,d=inputs()
            if variant=='policy':c['corporate_action_policy']='net_of_tax'
            if variant=='real':d['synthetic']=False
            if variant=='version':d['version']='synthetic-portfolio-replay.v1'
            if variant=='list':d['corporate_actions']={}
            with self.assertRaises(DataBlocked):replay(c,d)

    def test_resume_every_phase_and_tamper(self):
        c,d=inputs()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);cp=p/'config.json';ip=p/'input.json'
            cp.write_text(json.dumps(c));ip.write_text(json.dumps(d))
            ca.run(cp,ip,p/'full')
            for n in range(1,9):
                part=p/f'part{n}';out=p/f'resumed{n}'
                ca.run(cp,ip,part,stop_after=n);ca.run(cp,ip,out,resume=part/'checkpoint.json')
                for name in ('report.json','checkpoint.json'):
                    self.assertEqual((p/'full'/name).read_bytes(),(out/name).read_bytes())
            checkpoint=p/'part4'/'checkpoint.json';v=json.loads(checkpoint.read_text());v['report']['daily'][3]['dividend_income']='999'
            checkpoint.write_text(json.dumps(v))
            with self.assertRaises(DataBlocked):ca.run(cp,ip,p/'tampered',resume=checkpoint)
            self.assertFalse((p/'tampered').exists())
            d['corporate_actions'][0]['cash_per_old_share']='0.5';ip.write_text(json.dumps(d))
            with self.assertRaises(DataBlocked):ca.run(cp,ip,p/'changed',resume=p/'part2'/'checkpoint.json')
            self.assertFalse((p/'changed').exists())

    def test_invalid_events_leave_no_output(self):
        c,d=inputs();d['corporate_actions'][0]['split_ratio']='2'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'c').write_text(json.dumps(c));(p/'d').write_text(json.dumps(d))
            with self.assertRaises(DataBlocked):ca.run(p/'c',p/'d',p/'out')
            self.assertFalse((p/'out').exists())

if __name__=='__main__':unittest.main()
