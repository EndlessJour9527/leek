"""ML001 synthetic unit tests; never evidence of market profitability."""
from datetime import date,timedelta
from decimal import Context,ROUND_HALF_UP,localcontext
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from leek.contract import DataBlocked
from leek.real_backtest import simulate
from research.ml001.data import parse_sse

HAS_ML=all(importlib.util.find_spec(x) for x in ('numpy','pandas','sklearn','lightgbm'))
ROOT=Path(__file__).resolve().parents[1]


def fixture(n=320,end=None):
    import math
    bars=[];d=date(2019,1,2);i=0
    while (end is not None and d.isoformat()<=end) or (end is None and len(bars)<n):
        if d.weekday()<5:
            close=round(4+.25*math.sin(i/13)+.1*math.cos(i/5)+.0002*i,3)
            op=round(close+.003*math.sin(i/3),3)
            bars.append(dict(date=d.isoformat(),open=f'{op:.3f}',close=f'{close:.3f}',
                high=f'{max(op,close)+.02:.3f}',low=f'{min(op,close)-.02:.3f}',volume_lots=str(100000+i*10+(i%7)*100)))
            i+=1
        d+=timedelta(days=1)
    return bars


class TestML001Boundary(unittest.TestCase):
    def test_sse_field_mapping_preserves_decimal(self):
        rows=parse_sse(b'{"code":"510300","kline":[[20200821,4.7670,4.8070,4.7440,4.7830,1000,1234]]}')
        self.assertEqual(rows[0]['open'],'4.7670');self.assertEqual(rows[0]['close'],'4.7830')
        self.assertEqual(rows[0]['high'],'4.8070');self.assertEqual(rows[0]['low'],'4.7440')

    def test_wrong_symbol_and_duplicate_dates_block(self):
        row=[20200821,4.767,4.807,4.744,4.783,1000,1234]
        for payload in [{'code':'510500','kline':[row]}, {'code':'510300','kline':[row,row]}]:
            with self.assertRaises((DataBlocked,ValueError)):parse_sse(json.dumps(payload).encode())

    def test_external_policy_cannot_override_old_strategy(self):
        bars=fixture();c=json.loads((ROOT/'research/real_history_protocol.json').read_text())
        c['evaluation_start']=bars[160]['date'];c['evaluation_end']=bars[-1]['date']
        with self.assertRaises(DataBlocked):
            simulate(bars,[],c,'buy_hold',c['cost_cases']['base'],external_states={b['date']:False for b in bars})

    def test_external_missing_state_blocks(self):
        bars=fixture();c=json.loads((ROOT/'research/real_history_protocol.json').read_text())
        c['evaluation_start']=bars[160]['date'];c['evaluation_end']=bars[-1]['date']
        with self.assertRaises(DataBlocked):simulate(bars,[],c,'ml001_frozen_policy',c['cost_cases']['base'],external_states={})

    def test_external_all_off_is_cash(self):
        bars=fixture();c=json.loads((ROOT/'research/real_history_protocol.json').read_text())
        c['evaluation_start']=bars[160]['date'];c['evaluation_end']=bars[-1]['date']
        with localcontext(Context(prec=64,rounding=ROUND_HALF_UP)):
            r=simulate(bars,[],c,'ml001_frozen_policy',c['cost_cases']['base'],external_states={b['date']:False for b in bars})
        self.assertEqual(r['summary']['terminal_nav'],50000);self.assertEqual(r['orders'],[])

    def test_external_execution_occurs_next_day(self):
        bars=fixture();c=json.loads((ROOT/'research/real_history_protocol.json').read_text())
        c['evaluation_start']=bars[160]['date'];c['evaluation_end']=bars[-1]['date']
        states={b['date']:159<=i<179 for i,b in enumerate(bars)}
        with localcontext(Context(prec=64,rounding=ROUND_HALF_UP)):
            r=simulate(bars,[],c,'ml001_frozen_policy',c['cost_cases']['base'],external_states=states)
        self.assertEqual([o['execute_on'] for o in r['orders']],[bars[160]['date'],bars[180]['date']])
        for o in r['orders']:self.assertLess(o['signal_date'],o['execute_on'])


@unittest.skipUnless(HAS_ML,'ML001 optional pinned dependencies not installed')
class TestML001Learning(unittest.TestCase):
    def test_feature_prefix_invariant_to_future(self):
        import numpy as np
        from research.ml001.train import feature_table
        bars=fixture();x,*_=feature_table(bars,[])
        changed=[dict(b) for b in bars]
        for b in changed[200:]:
            for f in ('open','high','low','close'):b[f]=str(float(b[f])*2)
            b['volume_lots']=str(float(b['volume_lots'])*9)
        newer,*_=feature_table(changed,[])
        np.testing.assert_equal(x.iloc[:200].to_numpy(),newer.iloc[:200].to_numpy())

    def test_target_uses_future_open_and_correct_dividend_entitlement(self):
        from research.ml001.train import feature_table
        bars=fixture();e=dict(record_date=bars[101]['date'],ex_date=bars[102]['date'],pay_date=bars[105]['date'],cash_per_share='0.05')
        x,y,end,_=feature_table(bars,[e])
        self.assertAlmostEqual(y[100],(float(bars[106]['open'])+.05)/float(bars[101]['open'])-1)
        self.assertAlmostEqual(y[101],float(bars[107]['open'])/float(bars[102]['open'])-1)
        self.assertEqual(end[100],106)

    def test_missing_label_tail_and_no_nonfinite_features(self):
        import numpy as np
        from research.ml001.train import feature_table,FEATURES
        x,y,_,_=feature_table(fixture(),[])
        self.assertEqual(len(FEATURES),16);self.assertTrue(np.isnan(y[-6:]).all())
        self.assertTrue(np.isfinite(x.iloc[60:].to_numpy()).all())

    def test_endpoints_purged_on_both_boundaries(self):
        from research.ml001.train import feature_table,split_indices
        x,y,end,_=feature_table(fixture(1000),[])
        train,valid=split_indices(x,y,end,750)
        self.assertLess(max(end[train]),min(valid));self.assertLess(max(end[valid]),750)
        self.assertEqual(len(valid),126)

    def test_insufficient_learning_history_blocks(self):
        from research.ml001.train import feature_table,split_indices
        x,y,end,_=feature_table(fixture(),[])
        with self.assertRaises(DataBlocked):split_indices(x,y,end,200)

    def test_invalid_features_fail(self):
        from research.ml001.train import feature_table
        bars=fixture();bars[200]['close']='NaN'
        with self.assertRaises(DataBlocked):feature_table(bars,[])

    def test_fit_save_reload_and_future_prediction_invariance(self):
        from research.ml001.train import fit_predict,policies
        bars=fixture(end='2025-12-31')
        with tempfile.TemporaryDirectory() as tmp:
            report,levels=fit_predict(bars,[],Path(tmp)/'original')
            self.assertEqual(len(report['folds']),4)
            self.assertEqual(len(list((Path(tmp)/'original').glob('*/*.txt'))),4)
            self.assertEqual(len(list((Path(tmp)/'original').glob('*/*.json'))),4)
            changed=[dict(b) for b in bars]
            for b in changed:
                if b['date']>='2024-01-01':
                    for field in ('open','high','low','close'):b[field]=str(float(b[field])*1.5)
            later,_=fit_predict(changed,[],Path(tmp)/'changed')
            keys=('signal_date','next_session','ridge','lightgbm','train_mean','trained_asof')
            before=[{k:r[k] for k in keys} for r in report['records'] if r['next_session']<'2024-01-01']
            after=[{k:r[k] for k in keys} for r in later['records'] if r['next_session']<'2024-01-01']
            self.assertEqual(before,after)
            states,dates=policies(bars,report['records'],levels)
            ids={b['date']:i for i,b in enumerate(bars)}
            self.assertTrue(all(ids[b]-ids[a]==5 for a,b in zip(dates,dates[1:])))
            self.assertTrue(all(type(x) is bool for s in states.values() for x in s.values()))
            for f in report['folds']:
                self.assertLess(f['fit_last_label_endpoint'],f['validation_start'])
                self.assertLess(f['validation_last_label_endpoint'],f['first_prediction'])


if __name__=='__main__':unittest.main()
