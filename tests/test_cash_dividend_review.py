"""Independent cash-dividend orchestration checks with hand-calculated oracles."""
import copy
from decimal import Decimal as D
import json
from fractions import Fraction
import random
from pathlib import Path
import tempfile
import unittest

from leek.cash_dividend_replay import VERSION, CA_POLICY, POLICY, validate, _replay, run
from leek.contract import DataBlocked
from leek import portfolio_replay

DAYS = [f'2025-01-{i:02d}' for i in range(2, 9)]


def fixture():
    config = dict(version=VERSION, initial_cash='1000', quantities={'A': '100', 'B': '100'},
                  commission='0', slippage_bps='0', lookback=1, symbol_priority=['A', 'B'],
                  execution_policy=POLICY, corporate_action_policy=CA_POLICY)
    def bars(closes, opens):
        return [dict(date=d, open=str(o), close=str(c), high=str(max(o,c)), low=str(min(o,c)))
                for d,o,c in zip(DAYS, opens, closes)]
    event = dict(event_id='E', instrument='A', kind='cash_dividend', published_on=DAYS[0],
                 record_date=DAYS[2], ex_date=DAYS[3], pay_date=DAYS[4],
                 cash_per_old_share='1', split_ratio='1', rounding='exact')
    data = dict(version=VERSION, synthetic=True, instruments=['A','B'], currency='SIM', adjustment='raw',
                corporate_actions=[event], calendar=DAYS,
                bars={'A':bars([9,10,10,9,9,9,9],[9,10,10,9,9,9,9]),
                      'B':bars([10,10,10,11,12,12,12],[10]*7)})
    return config,data


def replay(config,data,count=None):
    validate(config,data)
    return _replay(config,data,len(DAYS) if count is None else count,{})


class IndependentCashDividendReview(unittest.TestCase):
    def test_hand_oracle_sale_after_record_retains_receivable_and_no_double_income(self):
        c,d=fixture(); r=replay(c,d)
        at_record, at_ex, at_pay=r['daily'][2:5]
        self.assertEqual(D(at_record['cash']),0)
        self.assertEqual(D(at_record['positions']['A']['quantity']),100)
        self.assertEqual(D(at_ex['cash']),900)
        self.assertEqual(D(at_ex['receivables']),100)
        self.assertEqual(D(at_ex['realized_pnl']),-100)
        self.assertEqual(D(at_ex['dividend_income']),100)
        self.assertEqual(D(at_ex['nav']),1000)
        self.assertEqual(D(at_pay['cash']),1000)
        self.assertEqual(D(at_pay['receivables']),0)
        self.assertEqual(D(at_pay['dividend_income']),100)
        self.assertEqual(D(at_pay['nav']),1000)
        for row in r['daily']:
            self.assertEqual(D(row['nav'])-D(c['initial_cash']),sum(D(row[x]) for x in ('realized_pnl','unrealized_pnl','dividend_income')))
            self.assertEqual(sum(D(p['total_pnl']) for p in row['positions'].values()),D(row['total_pnl']))

    def test_payment_day_not_available_at_open_and_retry_next_day(self):
        c,d=fixture(); r=replay(c,d)
        orders=[o for o in r['orders'] if o['instrument']=='B']
        self.assertEqual((orders[0]['execute_on'],orders[0]['status'],orders[0]['reason']),
                         (DAYS[4],'rejected','INSUFFICIENT_CASH'))
        self.assertEqual(D(orders[0]['cash_before']),900)
        self.assertEqual(D(orders[0]['paid_commission']),0)
        self.assertEqual((orders[1]['execute_on'],orders[1]['status']),(DAYS[5],'filled'))
        self.assertEqual(D(orders[1]['cash_before']),1000)

    def test_buy_on_ex_gets_no_entitlement(self):
        c,d=fixture(); e=d['corporate_actions'][0]
        e.update(record_date=DAYS[1],ex_date=DAYS[2],pay_date=DAYS[2])
        r=replay(c,d)
        self.assertTrue(any(o['instrument']=='A' and o['side']=='BUY' and o['execute_on']==DAYS[2] for o in r['orders']))
        self.assertEqual(D(r['daily'][-1]['dividend_income']),0)

    def test_record_day_sale_gets_no_entitlement(self):
        c,d=fixture(); e=d['corporate_actions'][0]
        e.update(record_date=DAYS[3],ex_date=DAYS[4],pay_date=DAYS[5])
        r=replay(c,d)
        records=[x for x in r['corporate_action_log'] if x['phase']=='record_close']
        self.assertEqual(D(records[0]['quantity']),0)
        self.assertEqual(D(r['daily'][-1]['dividend_income']),0)

    def test_same_day_ex_and_payment_still_after_open(self):
        c,d=fixture(); d['corporate_actions'][0]['pay_date']=DAYS[3]
        r=replay(c,d)
        sell=next(o for o in r['orders'] if o['side']=='SELL' and o['instrument']=='A')
        self.assertEqual(D(sell['cash_after']),900)
        self.assertEqual(D(r['daily'][3]['cash']),1000)
        self.assertEqual(D(r['daily'][3]['receivables']),0)

    def test_event_id_is_scoped_to_symbol_and_order_independent(self):
        c,d=fixture(); c['initial_cash']='2000'; d['bars']['B']=copy.deepcopy(d['bars']['A'])
        d['corporate_actions'].append(dict(d['corporate_actions'][0],instrument='B'))
        r=replay(c,d); d['corporate_actions'].reverse(); d['instruments'].reverse()
        self.assertEqual(r,replay(c,d))
        self.assertEqual(D(r['daily'][3]['dividend_income']),200)
        self.assertEqual(D(r['daily'][3]['receivables']),200)

    def test_future_dividend_does_not_change_prefix_signals_or_fills(self):
        c,d=fixture(); a=replay(c,d,3)
        d['corporate_actions'][0]['cash_per_old_share']='2'
        b=replay(c,d,3)
        self.assertEqual(a,b)

    def test_ex_drop_is_flat_total_return_not_negative_price_momentum(self):
        c,d=fixture(); r=replay(c,d)
        self.assertEqual(D(r['daily'][2]['positions']['A']['total_return_level']),D(r['daily'][3]['positions']['A']['total_return_level']))
        # Equal is intentionally zero target, rather than claiming positive momentum.
        sig=next(s for s in r['signals'] if s['instrument']=='A' and s['asof']==DAYS[3])
        self.assertEqual(D(sig['target_quantity']),0)

    def test_all_event_boundaries_resume_byte_identically(self):
        c,d=fixture()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); cp=p/'config.json'; dp=p/'input.json'
            cp.write_text(json.dumps(c));dp.write_text(json.dumps(d))
            run(cp,dp,p/'full')
            for n in range(1,len(DAYS)+1):
                run(cp,dp,p/f'part{n}',stop_after=n)
                run(cp,dp,p/f'resume{n}',resume=p/f'part{n}'/'checkpoint.json')
                for name in ('report.json','checkpoint.json'):
                    self.assertEqual((p/'full'/name).read_bytes(),(p/f'resume{n}'/name).read_bytes())

    def test_event_change_invalidates_checkpoint_before_output(self):
        c,d=fixture()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); cp=p/'config.json'; dp=p/'input.json'
            cp.write_text(json.dumps(c));dp.write_text(json.dumps(d));run(cp,dp,p/'part',stop_after=2)
            d['corporate_actions'][0]['cash_per_old_share']='2';dp.write_text(json.dumps(d))
            with self.assertRaises(DataBlocked):run(cp,dp,p/'resume',resume=p/'part'/'checkpoint.json')
            self.assertFalse((p/'resume').exists())

    def test_reject_unsupported_actions_malformed_or_future_known_dates(self):
        mutations=[('split_ratio','2'),('rounding','ceil_whole_account'),('kind','split'),
                   ('published_on',DAYS[3]),('record_date',DAYS[3]),('pay_date',DAYS[2]),
                   ('pay_date','2030-01-01'),('instrument','C'),('cash_per_old_share','NaN'),
                   ('cash_per_old_share','10'),('cash_per_old_share','0'),('event_id','')]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                c,d=fixture(); d['corporate_actions'][0][key]=value
                with self.assertRaises((DataBlocked,ValueError)):validate(c,d)
        c,d=fixture();d['corporate_actions'].append(dict(d['corporate_actions'][0],event_id='Other'))
        with self.assertRaises(DataBlocked):validate(c,d)

    def test_same_symbol_distinct_ex_events_can_share_payment_date(self):
        c,d=fixture()
        first=d['corporate_actions'][0]
        second=dict(first,event_id='E2',ex_date=DAYS[4],pay_date=DAYS[5])
        first['pay_date']=DAYS[5]
        d['corporate_actions'].append(second)
        r=replay(c,d)
        self.assertEqual(D(r['daily'][4]['receivables']),200)
        self.assertEqual(D(r['daily'][4]['dividend_income']),200)
        self.assertEqual(D(r['daily'][5]['receivables']),0)
        self.assertEqual(D(r['daily'][5]['dividend_income']),200)
        payments=[e for e in r['corporate_action_log'] if e['phase']=='pay_after_trading']
        self.assertEqual(len(payments),2)
        self.assertEqual(sum(D(e['amount']) for e in payments),200)

    def test_one_hundred_seeded_paths_against_independent_accounting_oracle(self):
        rng=random.Random(31817)
        days=[f'2025-02-{i:02d}' for i in range(1,21)]
        for case in range(100):
            c,d=fixture()
            c.update(initial_cash=str(rng.randint(100,400)),quantities={'A':'5','B':'7'},
                     commission='0.3',slippage_bps='10',lookback=2)
            c['symbol_priority']=rng.sample(['A','B'],2)
            d['calendar']=days
            for symbol in ('A','B'):
                d['bars'][symbol]=[]
                for day in days:
                    o,close=rng.randint(8,20),rng.randint(8,20)
                    d['bars'][symbol].append(dict(date=day,open=str(o),close=str(close),
                                                 high=str(max(o,close)),low=str(min(o,close))))
            d['corporate_actions']=[]
            for symbol in ('A','B'):
                for event_no,(record,ex,pay) in enumerate(((5,6,9),(11,12,15))):
                    d['corporate_actions'].append(dict(event_id='E'+str(event_no),instrument=symbol,
                        kind='cash_dividend',published_on=days[0],record_date=days[record],
                        ex_date=days[ex],pay_date=days[pay],cash_per_old_share='0.7',split_ratio='1',rounding='exact'))
            validate(c,d); actual=_replay(c,d,len(days),{})
            cash=D(c['initial_cash']); quantity={s:D(0) for s in ('A','B')}
            basis={s:D(0) for s in ('A','B')}; realized={s:D(0) for s in ('A','B')}
            income=D(0); receivables={}; rights={}; pending={}; history={s:[] for s in ('A','B')}
            for i,day in enumerate(days):
                divs={s:D(0) for s in ('A','B')}
                for e in d['corporate_actions']:
                    if e['ex_date']==day:
                        k=(e['instrument'],e['event_id']); amount=rights[k]*D('0.7')
                        receivables[k]=amount; income+=amount; divs[e['instrument']]+=D('0.7')
                for side in ('SELL','BUY'):
                    for s in c['symbol_priority']:
                        if pending.get(s)!=side:continue
                        n=quantity[s] if side=='SELL' else D(c['quantities'][s])
                        raw=D(d['bars'][s][i]['open'])
                        price=raw*(D('0.999') if side=='SELL' else D('1.001'))
                        if side=='BUY':
                            cost=n*price+D('0.3')
                            if cost<=cash:cash-=cost;quantity[s]=n;basis[s]=cost
                        else:
                            proceeds=n*price-D('0.3')
                            if cash+proceeds>=0:
                                cash+=proceeds;realized[s]+=proceeds-basis[s];quantity[s]=D(0);basis[s]=D(0)
                for e in d['corporate_actions']:
                    k=(e['instrument'],e['event_id'])
                    if e['record_date']==day:rights[k]=quantity[e['instrument']]
                    if e['pay_date']==day:cash+=receivables.pop(k)
                nav=cash+sum(receivables.values(),D(0))+sum(quantity[s]*D(d['bars'][s][i]['close']) for s in ('A','B'))
                row=actual['daily'][i]
                with self.subTest(case=case,day=day):
                    self.assertEqual(D(row['cash']),cash)
                    self.assertEqual(D(row['nav']),nav)
                    self.assertEqual(D(row['dividend_income']),income)
                    self.assertEqual(D(row['receivables']),sum(receivables.values(),D(0)))
                    for s in ('A','B'):
                        self.assertEqual(D(row['positions'][s]['quantity']),quantity[s])
                        self.assertEqual(D(row['positions'][s]['basis']),basis[s])
                        self.assertEqual(D(row['positions'][s]['realized_pnl']),realized[s])
                pending={}
                for s in ('A','B'):
                    close=D(d['bars'][s][i]['close'])
                    h=history[s]
                    h.append(Fraction(close) if i==0 else h[-1]*Fraction(close+divs[s])/Fraction(D(d['bars'][s][i-1]['close'])))
                    if i>=2:
                        target=D(c['quantities'][s]) if h[-1]>h[-3] else D(0)
                        if target>quantity[s]:pending[s]='BUY'
                        elif target<quantity[s]:pending[s]='SELL'

    def test_no_event_economics_match_original_portfolio(self):
        c,d=fixture();d['corporate_actions']=[];new=replay(c,d)
        old_c={k:v for k,v in c.items() if k!='corporate_action_policy'}
        old_c['version']=portfolio_replay.VERSION
        old_d=dict(d,version=portfolio_replay.VERSION)
        portfolio_replay.validate(old_c,old_d)
        old=portfolio_replay._replay(old_c,old_d,len(DAYS),{})
        for a,b in zip(new['daily'],old['daily']):
            for k in ('cash','nav','realized_pnl','unrealized_pnl','total_pnl','commission','slippage'):
                self.assertEqual(D(a[k]),D(b[k]))
        self.assertEqual(new['orders'],old['orders'])
        self.assertEqual(new['signals'],old['signals'])


if __name__=='__main__':unittest.main()
