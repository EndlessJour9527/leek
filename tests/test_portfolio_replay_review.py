import copy, json, random, tempfile, unittest, shutil, subprocess, sys
from pathlib import Path
from decimal import Decimal as D
from unittest.mock import patch
from leek import portfolio_replay as p
from leek.contract import DataBlocked

def fixture(ac=(10,11,9,8,10),bc=(10,9,11,12,10),cash='100',qty='10',fee='0',slip='0',opens=None):
    days=[f'2026-01-{i+1:02}' for i in range(len(ac))]
    cfg=dict(version=p.VERSION,initial_cash=cash,quantities={'A':qty,'B':qty},commission=fee,slippage_bps=slip,lookback=1,symbol_priority=['B','A'],execution_policy=p.POLICY)
    data=dict(version=p.VERSION,synthetic=True,instruments=['A','B'],currency='SIM',adjustment='raw',corporate_actions=[],calendar=days,bars={})
    for s,cs in [('A',ac),('B',bc)]:
        data['bars'][s]=[dict(date=day,open=str(opens[s][i] if opens else 10),close=str(c),high=str(max(c,opens[s][i] if opens else 10)+1),low=str(min(c,opens[s][i] if opens else 10)-1)) for i,(day,c) in enumerate(zip(days,cs))]
    return cfg,data

class Audit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.n=0
    def tearDown(self): self.temp.cleanup()
    def run_case(self,c,d,**kw):
        self.n+=1; base=self.root/str(self.n);base.mkdir()
        (base/'config').write_bytes(p.canonical(c));(base/'data').write_bytes(p.canonical(d))
        return p.run(base/'config',base/'data',base/'out',**kw),base
    def blocked(self,c,d,**kw):
        with self.assertRaises((DataBlocked,ValueError)):self.run_case(c,d,**kw)
        self.assertFalse((self.root/str(self.n)/'out').exists())
    def invariants(self,r,c):
        for row in r['daily']:
            self.assertGreaterEqual(D(row['cash']),0)
            self.assertEqual(D(row['nav']),D(row['cash'])+sum(D(x['market_value']) for x in row['positions'].values()))
            self.assertEqual(D(row['total_pnl']),D(row['nav'])-D(c['initial_cash']))
            self.assertEqual(D(row['total_pnl']),sum(D(x['total_pnl']) for x in row['positions'].values()))
            self.assertEqual(D(row['commission']),sum(D(x['commission']) for x in row['positions'].values()))
            self.assertEqual(D(row['slippage']),sum(D(x['slippage']) for x in row['positions'].values()))
            for pos in row['positions'].values():
                self.assertGreaterEqual(D(pos['quantity']),0);self.assertGreaterEqual(D(pos['basis']),0)
                self.assertEqual(D(pos['market_value']),D(pos['quantity'])*D(pos['close']))
                self.assertEqual(D(pos['unrealized_pnl']),D(pos['market_value'])-D(pos['basis']))
        for o in r['orders']:
            self.assertGreater(o['execute_on'],o['signal_date'])
            delta=D(o['cash_after'])-D(o['cash_before'])
            expected=(D(o['quantity'])*D(o['fill_price'])*(1 if o['side']=='SELL' else -1)-D(o['paid_commission'])) if o['status']=='filled' else D(0)
            self.assertEqual(delta,expected)
    def test_sells_before_buy_even_buy_priority_first(self):
        c,d=fixture();r,_=self.run_case(c,d)
        os=[o for o in r['orders'] if o['execute_on']=='2026-01-04']
        self.assertEqual([(o['instrument'],o['side'],o['status']) for o in os],[('A','SELL','filled'),('B','BUY','filled')]);self.invariants(r,c)
    def test_priority_cash_contention_and_no_partial(self):
        c,d=fixture((10,11,12),(10,11,12),opens={'A':[6]*3,'B':[6]*3})
        r,_=self.run_case(c,d);self.assertEqual([(o['instrument'],o['status']) for o in r['orders']],[('B','filled'),('A','rejected')]);self.assertEqual(r['orders'][1]['reason'],'INSUFFICIENT_CASH');self.assertEqual(r['orders'][1]['filled_quantity'],'0')
        c['symbol_priority'].reverse();s,_=self.run_case(c,d);self.assertEqual(s['orders'][0]['instrument'],'A');self.invariants(r,c)
    def test_fee_and_slippage_hand_calculated(self):
        c,d=fixture((10,11,9,8),(10,9,8,7),qty='5',fee='1',slip='100')
        r,_=self.run_case(c,d);last=r['daily'][-1]
        self.assertEqual(D(r['daily'][2]['cash']),D('48.5'));self.assertEqual(D(r['daily'][2]['positions']['A']['basis']),D('51.5'))
        self.assertEqual(D(last['cash']),D('97'));self.assertEqual(D(last['realized_pnl']),D('-3'));self.assertEqual(D(last['commission']),D('2'));self.assertEqual(D(last['slippage']),D('1'));self.invariants(r,c)
    def test_sell_fee_rejection_preserves_positions_cash(self):
        c,d=fixture((10,11,9,8),(10,9,8,7),cash='101',qty='10',fee='1',opens={'A':[10,10,10,D('0.01')],'B':[10]*4})
        # Repair low to remain positive for the tiny final open.
        d['bars']['A'][-1]['low']='0.001'
        r,_=self.run_case(c,d);self.assertEqual(r['orders'][-1]['reason'],'INSUFFICIENT_SELL_FEE_CASH');self.assertEqual(D(r['daily'][-1]['positions']['A']['quantity']),10);self.invariants(r,c)
    def test_future_prices_do_not_affect_prefix(self):
        c,d=fixture();r,_=self.run_case(c,d,stop_after=3);changed=copy.deepcopy(d)
        for s in changed['bars']:
            for b in changed['bars'][s][3:]:b.update(open='100',close='100',high='101',low='99')
        q,_=self.run_case(c,changed,stop_after=3)
        r.pop('binding');q.pop('binding');self.assertEqual(r,q)
    def test_full_resume_every_split_byte_equality(self):
        c,d=fixture();full,fb=self.run_case(c,d)
        for count in range(1,len(d['calendar'])+1):
            _,b=self.run_case(c,d,stop_after=count);_,rb=self.run_case(c,d,resume=b/'out/checkpoint.json')
            for f in ['report.json','checkpoint.json']:self.assertEqual((fb/'out'/f).read_bytes(),(rb/'out'/f).read_bytes())
    def test_hash_bindings_and_forged_state(self):
        c,d=fixture();r,b=self.run_case(c,d,stop_after=3);cp=b/'out/checkpoint.json'
        cc=copy.deepcopy(c);cc['commission']='1';self.blocked(cc,d,resume=cp)
        dd=copy.deepcopy(d);dd['bars']['A'][-1]['high']='100';self.blocked(c,dd,resume=cp)
        with patch.object(p,'source_hash',return_value='changed-code'):self.blocked(c,d,resume=cp)
        original=json.loads(cp.read_text())
        for mode in ('state','self_signed_state','source','progress','version'):
            tamper=copy.deepcopy(original)
            if mode in ('state','self_signed_state'):
                tamper['report']['daily'][-1]['cash']='999'
                if mode=='self_signed_state':tamper['report_sha256']=p.digest(p.canonical(tamper['report']))
            elif mode=='source':tamper['binding']['source_sha256']='wrong'
            elif mode=='progress':tamper['processed_sessions']=True
            else:tamper['version']='other'
            bad=self.root/('tamper-'+mode);bad.write_bytes(p.canonical(tamper));self.blocked(c,d,resume=bad)
    def test_bad_inputs_fail_closed(self):
        c,d=fixture()
        for mutate in [lambda x:x['bars']['A'].pop(),lambda x:x['bars']['B'][-1].update(close='NaN'),lambda x:x['bars']['A'][-1].update(open='0'),lambda x:x.update(corporate_actions=[{'kind':'dividend'}]),lambda x:x.update(adjustment='forward'),lambda x:x['calendar'].reverse(),lambda x:x['instruments'].append('A'),lambda x:x.update(synthetic=False),lambda x:x['bars']['A'][0].update(close=True),lambda x:x['bars']['A'][0].update(date='2025-01-01')]:
            dd=copy.deepcopy(d);mutate(dd);self.blocked(c,dd)
        for field,value in [('quantities',{'A':'-1','B':'10'}),('quantities',{'A':'1.5','B':'10'}),('symbol_priority',['A','A']),('lookback',True),('commission','-1'),('slippage_bps','10000')]:
            cc=copy.deepcopy(c);cc[field]=value;self.blocked(cc,d)
    def test_mapping_order_does_not_change_semantics(self):
        c,d=fixture();r,_=self.run_case(c,d);d['instruments'].reverse();d['bars']=dict(reversed(list(d['bars'].items())));s,_=self.run_case(c,d)
        r.pop('binding');s.pop('binding');self.assertEqual(r,s)
    def test_actual_source_copy_change_rejected(self):
        c,d=fixture();r,b=self.run_case(c,d,stop_after=3)
        root=self.root/'source';shutil.copytree(Path(p.__file__).parent,root/'leek')
        f=root/'leek/ledger.py';f.write_text(f.read_text()+'\n# Audit source change\n')
        result=subprocess.run([sys.executable,'-m','leek.portfolio_replay','--config',str(b/'config'),'--input',str(b/'data'),'--output',str(root/'out'),'--resume',str(b/'out/checkpoint.json')],cwd=root,capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('source, config or input mismatch',result.stderr);self.assertFalse((root/'out').exists())
    def test_report_publication_crash_recovers(self):
        c,d=fixture();original=p.atomic_create
        def fail(path,value):
            if path.name=='report.json':raise OSError('injected report write failure')
            original(path,value)
        with patch.object(p,'atomic_create',side_effect=fail),self.assertRaises(OSError):self.run_case(c,d,stop_after=3)
        checkpoint=self.root/str(self.n)/'out/checkpoint.json';self.assertTrue(checkpoint.exists())
        r,rb=self.run_case(c,d,resume=checkpoint);f,fb=self.run_case(c,d)
        self.assertEqual((rb/'out/report.json').read_bytes(),(fb/'out/report.json').read_bytes())
    def test_maximum_universe_and_single_session(self):
        c,d=fixture((10,11,12),(10,11,12),cash='10000',qty='1')
        symbols=[f'S{i}' for i in range(64)];c['symbol_priority']=symbols;c['quantities']={s:'1' for s in symbols};bars=d['bars']['A'];d['instruments']=symbols;d['bars']={s:copy.deepcopy(bars) for s in symbols}
        r,_=self.run_case(c,d);self.assertEqual(len(r['orders']),64);self.invariants(r,c)
        for s in symbols:d['bars'][s]=d['bars'][s][:1]
        d['calendar']=d['calendar'][:1];r,_=self.run_case(c,d);self.assertEqual(r['orders'],[]);self.assertEqual(r['signals'],[]);self.invariants(r,c)
    def test_randomized_cash_position_conservation(self):
        rand=random.Random(20261019)
        for _ in range(100):
            a=[rand.randrange(2,100) for _ in range(20)];b=[rand.randrange(2,100) for _ in range(20)]
            c,d=fixture(a,b,cash=str(rand.randrange(1,1000)),qty=str(rand.randrange(1,20)),fee=str(rand.randrange(0,5)),slip=str(rand.randrange(0,500)),opens={'A':[rand.randrange(2,100) for _ in a],'B':[rand.randrange(2,100) for _ in a]})
            r,_=self.run_case(c,d);self.invariants(r,c)
            cash=D(c['initial_cash']);positions={symbol:D(0) for symbol in c['symbol_priority']};pending=[]
            for index,row in enumerate(r['daily']):
                for symbol,delta in sorted(pending,key=lambda item:(item[1]>0,c['symbol_priority'].index(item[0]))):
                    raw=D(d['bars'][symbol][index]['open']);slip=D(c['slippage_bps'])/10000
                    px=raw*(1+slip if delta>0 else 1-slip)
                    net=-delta*px-D(c['commission'])
                    if cash+net>=0:
                        cash+=net;positions[symbol]+=delta
                self.assertEqual(D(row['cash']),cash)
                for symbol,qty in positions.items():self.assertEqual(D(row['positions'][symbol]['quantity']),qty)
                pending=[]
                if index>=c['lookback']:
                    for symbol in c['symbol_priority']:
                        target=D(c['quantities'][symbol]) if D(d['bars'][symbol][index]['close'])>D(d['bars'][symbol][index-c['lookback']]['close']) else D(0)
                        if target!=positions[symbol]:pending.append((symbol,target-positions[symbol]))
if __name__=='__main__':unittest.main(verbosity=2)
