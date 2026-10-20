"""Synthetic-only portfolio orchestration invariants."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal as D, localcontext
from unittest.mock import patch

from leek.contract import DataBlocked
from leek.portfolio_replay import VERSION, POLICY, run, validate
from leek.replay import canonical, digest


def fixture():
    config = dict(version=VERSION, initial_cash='25', quantities={'ALPHA':'2', 'BETA':'2'},
                  commission='1', slippage_bps='0', lookback=1,
                  symbol_priority=['BETA', 'ALPHA'], execution_policy=POLICY)
    calendar = ['2025-01-02','2025-01-03','2025-01-06','2025-01-08','2025-01-09','2025-01-10']
    prices = {'ALPHA': [(10,10),(10,11),(10,12),(10,13),(10,12),(10,11)],
              'BETA': [(10,10),(10,11),(10,9),(10,8),(10,9),(10,10)]}
    bars = {s: [dict(date=d, open=str(o), close=str(c), high=str(max(o,c)+1), low=str(min(o,c)-1))
                for d,(o,c) in zip(calendar,values)] for s,values in prices.items()}
    data = dict(version=VERSION, synthetic=True, instruments=['ALPHA','BETA'], currency='SIM',
                adjustment='raw', corporate_actions=[], calendar=calendar, bars=bars)
    return config,data


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config,self.data = fixture()
        self.serial = 0

    def execute(self, config=None, data=None, **kwargs):
        self.serial += 1
        c,p = self.root/'config.json',self.root/'bars.json'
        c.write_bytes(canonical(self.config if config is None else config))
        p.write_bytes(canonical(self.data if data is None else data))
        out = self.root/str(self.serial)
        report = run(c,p,out,**kwargs)
        return report,out

    def test_shared_cash_priority_rejection_and_sale_funds_buy(self):
        r,_ = self.execute()
        orders = r['orders']
        self.assertEqual([(o['instrument'],o['side'],o['status']) for o in orders[:4]],
            [('BETA','BUY','filled'),('ALPHA','BUY','rejected'),('BETA','SELL','filled'),('ALPHA','BUY','filled')])
        self.assertEqual(orders[1]['reason'],'INSUFFICIENT_CASH')
        self.assertEqual(orders[1]['paid_commission'],'0')
        self.assertEqual(orders[1]['cash_before'], orders[1]['cash_after'])
        self.assertEqual(D(orders[2]['cash_after']),D(23))
        self.assertEqual(D(orders[3]['cash_after']),D(2))
        for row in r['daily']:
            ps=row['positions'].values()
            self.assertEqual(D(row['nav']),D(row['cash'])+sum(D(p['nav_contribution']) for p in ps))
            self.assertEqual(D(row['total_pnl']),sum(D(p['total_pnl']) for p in ps))
            for field in ('commission','slippage','realized_pnl','unrealized_pnl'):
                self.assertEqual(D(row[field]),sum(D(p[field]) for p in ps))

    def test_all_resume_points_and_chained_resume_byte_equal(self):
        _,full=self.execute()
        resume=None
        for count in range(1,len(self.data['calendar'])+1):
            _,part=self.execute(stop_after=count,resume=resume)
            resume=part/'checkpoint.json'
            _,continued=self.execute(resume=resume)
            for name in ('report.json','checkpoint.json'):
                self.assertEqual((full/name).read_bytes(),(continued/name).read_bytes())

    def test_future_ohlc_does_not_change_prefix(self):
        r,_=self.execute(stop_after=3)
        other=copy.deepcopy(self.data)
        for bars in other['bars'].values():
            for bar in bars[3:]:
                bar.update(open='200',high='201',low='198',close='199')
        changed,_=self.execute(data=other,stop_after=3)
        for key in ('daily','signals','orders','pending_orders'):
            self.assertEqual(r[key],changed[key])

    def test_execution_uses_only_next_open(self):
        r,_=self.execute(stop_after=3)
        other=copy.deepcopy(self.data)
        for bars in other['bars'].values():
            bars[2].update(high='999',low='1',close='500')
        changed,_=self.execute(data=other,stop_after=3)
        self.assertEqual(r['orders'],changed['orders'])

    def test_terminal_intent_remains_unfilled(self):
        self.data['bars']['BETA'][-1].update(close='1',low='1')
        r,_=self.execute()
        self.assertTrue(r['complete'])
        self.assertTrue(r['pending_orders'])
        self.assertTrue(all(o['execute_on'] is None for o in r['pending_orders']))
        self.assertFalse(set(o['event_id'] for o in r['pending_orders']) & set(r['processed_event_ids']))

    def test_costs_in_basis_not_double_subtracted(self):
        self.config.update(initial_cash='100',slippage_bps='100')
        r,_=self.execute(stop_after=3)
        row=r['daily'][-1]
        self.assertEqual(D(row['commission']),D(2))
        self.assertEqual(D(row['slippage']),D('.4'))
        self.assertEqual(D(row['cash']),D('57.6'))
        self.assertEqual(D(row['nav']),D('99.6'))
        self.assertEqual(D(row['total_pnl']),D('-.4'))

    def test_input_order_does_not_allocate_cash(self):
        r,_=self.execute()
        data=copy.deepcopy(self.data)
        data['instruments'].reverse()
        data['bars']=dict(reversed(list(data['bars'].items())))
        changed,_=self.execute(data=data)
        for field in ('daily','orders','signals','pending_orders'):
            self.assertEqual(r[field],changed[field])

    def test_config_priority_changes_winner_explicitly(self):
        self.config['symbol_priority'].reverse()
        r,_=self.execute(stop_after=3)
        self.assertEqual(r['orders'][0]['instrument'],'ALPHA')
        self.assertEqual(r['orders'][0]['status'],'filled')

    def test_fail_closed_contract_variations(self):
        changes=[
            ('data','corporate_actions',[{}]),('data','adjustment','adjusted'),
            ('data','synthetic',1),('data','currency','USD'),
            ('data','instruments',['ALPHA','ALPHA']),('data','instruments',['ALPHA']),
            ('config','symbol_priority',['ALPHA','ALPHA']),('config','execution_policy','pro-rata'),
            ('config','lookback',True),('config','initial_cash',True),
            ('config','commission','NaN'),('config','slippage_bps','10000'),
            ('config','quantities',{'ALPHA':'1.5','BETA':'2'}),
        ]
        for target,field,value in changes:
            c,d=fixture()
            (c if target=='config' else d)[field]=value
            with self.subTest(field=field,value=value), self.assertRaises(DataBlocked):
                validate(c,d)
        for mutation in ('missing_symbol','missing_bar','invalid_ohlc','duplicate_date','future_missing','unknown'):
            c,d=fixture()
            if mutation=='missing_symbol': del d['bars']['BETA']
            if mutation in ('missing_bar','future_missing'): d['bars']['BETA'].pop()
            if mutation=='invalid_ohlc': d['bars']['BETA'][0]['open']='900'
            if mutation=='duplicate_date': d['calendar'][1]=d['calendar'][0]
            if mutation=='unknown': d['extra']=True
            with self.subTest(mutation=mutation),self.assertRaises(DataBlocked): self.execute(c,d,stop_after=1)

    def test_resume_tamper_and_rehashed_forgery_blocked(self):
        _,out=self.execute(stop_after=3)
        checkpoint=json.loads((out/'checkpoint.json').read_bytes())
        checkpoint['report']['daily'][-1]['cash']='999999'
        checkpoint['report_sha256']=digest(canonical(checkpoint['report']))
        path=self.root/'forged.json';path.write_bytes(canonical(checkpoint))
        with self.assertRaises(DataBlocked): self.execute(resume=path)

    def test_resume_source_input_config_and_cursor_binding(self):
        _,out=self.execute(stop_after=3)
        p=out/'checkpoint.json'
        with patch('leek.portfolio_replay.source_hash',return_value='changed'):
            with self.assertRaises(DataBlocked): self.execute(resume=p)
        c=copy.deepcopy(self.config);c['symbol_priority'].reverse()
        with self.assertRaises(DataBlocked): self.execute(config=c,resume=p)
        d=copy.deepcopy(self.data);d['bars']['ALPHA'][-1]['high']='999'
        with self.assertRaises(DataBlocked): self.execute(data=d,resume=p)
        with self.assertRaises(DataBlocked): self.execute(resume=p,stop_after=2)

    def test_duplicate_json_keys_and_output_no_clobber(self):
        _,out=self.execute()
        c,p=self.root/'config.json',self.root/'bars.json'
        before=(out/'report.json').read_bytes()
        with self.assertRaises(FileExistsError): run(c,p,out)
        self.assertEqual(before,(out/'report.json').read_bytes())
        c.write_text('{"version":"a","version":"b"}')
        with self.assertRaises(DataBlocked): run(c,p,self.root/'bad')

    def test_decimal_context_independent(self):
        with localcontext() as ctx:
            ctx.prec=6
            r,_=self.execute()
        other,_=self.execute()
        self.assertEqual(r,other)

    def test_sell_fee_rejection_is_atomic(self):
        self.config.update(initial_cash='100',commission='9')
        # First purchases spend 58; after day 3 close both positions want exit.
        for s in self.data['instruments']:
            self.data['bars'][s][2].update(close='1',low='1')
            self.data['bars'][s][3].update(open='1',low='1')
        r,_=self.execute(stop_after=4)
        self.assertTrue(all(o['status']=='filled' for o in r['orders']))
        # Much larger fees leave too little cash to sell either whole position.
        self.config.update(initial_cash='122',commission='40')
        r,_=self.execute(stop_after=4)
        rejected=[o for o in r['orders'] if o['status']=='rejected']
        self.assertEqual([o['reason'] for o in rejected],['INSUFFICIENT_SELL_FEE_CASH']*2)
        self.assertEqual(D(r['daily'][-1]['cash']),D(2))
        self.assertTrue(all(D(p['quantity'])==2 for p in r['daily'][-1]['positions'].values()))


if __name__=='__main__': unittest.main()
