"""Offline contracts for the one-shot alternate source pairing."""
import importlib.util
import json
from pathlib import Path
import unittest

PATH=Path(__file__).resolve().parents[1]/'research/audits/sse_full_panel_probe_20261025.py'
spec=importlib.util.spec_from_file_location('sse_full_panel_probe', PATH)
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class TestSourceProbe(unittest.TestCase):
    def setUp(self):
        self.a={'code':'510300','kline':[
            ['20200821','4.767','4.807','4.744','4.783','123','ignored'],
            ['20200824','4.805','4.831','4.778','4.813','234','ignored']]}
        self.b={'data':{'sh510300':{'day':[
            ['2020-08-21','4.767','4.783','4.807','4.744','123'],
            ['2020-08-24','4.805','4.813','4.831','4.778','234']]}}}

    def test_exact_mapping(self):
        left=p.sse_parse(json.dumps(self.a).encode())
        right=p.tx_parse(json.dumps(self.b).encode())
        self.assertEqual(left,right)
        self.assertEqual(str(left['2020-08-21']['close']),'4.783')

    def test_one_tick_is_not_equal(self):
        left=p.sse_parse(json.dumps(self.a).encode())
        self.b['data']['sh510300']['day'][0][1]='4.768'
        right=p.tx_parse(json.dumps(self.b).encode())
        self.assertNotEqual(left['2020-08-21']['open'],right['2020-08-21']['open'])

    def test_wrong_code_is_blocked(self):
        self.a['code']='510500'
        with self.assertRaises(p.Blocked): p.sse_parse(json.dumps(self.a).encode())

    def test_adjusted_only_is_blocked(self):
        self.b['data']['sh510300']['qfqday']=self.b['data']['sh510300'].pop('day')
        with self.assertRaises(p.Blocked): p.tx_parse(json.dumps(self.b).encode())

    def test_duplicate_is_blocked(self):
        self.a['kline'].append(self.a['kline'][-1])
        with self.assertRaises(p.Blocked): p.sse_parse(json.dumps(self.a).encode())

    def test_truncated_history_is_blocked(self):
        one=p.sse_parse(json.dumps(self.a).encode())
        with self.assertRaisesRegex(p.Blocked,'coverage'): p.compare(one,one,{})

    def test_nonnumeric_is_blocked(self):
        for bad in ['NaN','Infinity','0','-1','100000','abc']:
            with self.subTest(bad=bad),self.assertRaises(p.Blocked): p.dec(bad)

    def test_price_bounds_are_blocked(self):
        self.a['kline'][0][2]='4.000'
        with self.assertRaises(p.Blocked): p.sse_parse(json.dumps(self.a).encode())

    def test_no_daily_series_is_blocked(self):
        self.a['kline']=[]
        with self.assertRaises(p.Blocked): p.sse_parse(json.dumps(self.a).encode())

if __name__=='__main__': unittest.main()
