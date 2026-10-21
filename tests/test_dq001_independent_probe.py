"""Offline parser regressions, no real provider or strategy-performance claims."""
import copy
from datetime import datetime
from decimal import Decimal
import json
import unittest
from research.dq001_independent_probe import (
    DATES, FIELDS, TZ, EvidenceBlocked, compare, load_json, parse_quotes, price,
)


def fixture():
    q = {field: [4.783] * 5 for field in FIELDS}
    item = {'meta': {'symbol': '510300.SS', 'currency': 'CNY',
                     'exchangeTimezoneName': 'Asia/Shanghai'},
            'timestamp': [int(datetime.fromisoformat(d+'T09:30:00').replace(tzinfo=TZ).timestamp()) for d in DATES],
            'indicators': {'quote': [q], 'adjclose': [{'adjclose': [3.0] * 5}]}}
    payload = {'chart': {'result': [item], 'error': None}}
    ref = {'status': 'SOURCE_CONFLICT', 'differing_cells': 20, 'differences_resolved': False,
           'mismatches': [{'date': d, 'field': k, 'eastmoney': '4.784', 'tencent': '4.783'}
                          for d in DATES for k in FIELDS]}
    return payload, ref


def raw(value):
    return json.dumps(value).encode()


class IndependentProbeTests(unittest.TestCase):
    def test_exact_tick_comparison_not_data_resolution(self):
        p, r = fixture()
        x = compare(raw(p), r)
        self.assertEqual(x['counts']['matches_tencent_only'], 20)
        self.assertFalse(x['dq001_resolved'])
        self.assertFalse(x['backtest_executed'])
        self.assertFalse(x['automatic_promotion'])

    def test_all_other_vendor_matches_also_remain_unresolved(self):
        p, r = fixture()
        p['chart']['result'][0]['indicators']['quote'][0] = {k: [4.784]*5 for k in FIELDS}
        x = compare(raw(p), r)
        self.assertEqual(x['counts']['matches_eastmoney_only'], 20)
        self.assertFalse(x['dq001_resolved'])

    def test_serializer_epsilon_not_one_tick_tolerance(self):
        self.assertEqual(price(Decimal('4.783000469207764'))['tick_value'], '4.783')
        self.assertEqual(price('4.784')['tick_value'], '4.784')
        with self.assertRaises(EvidenceBlocked):
            price('4.7834')

    def test_null_boolean_nonfinite_offgrid_rejected(self):
        for value in (None, True, 'NaN', 'Infinity', '0', '-1', '4.7835', 4.783):
            with self.subTest(value=value), self.assertRaises(EvidenceBlocked):
                price(value)

    def test_adjclose_never_replaces_quote(self):
        p, r = fixture()
        p['chart']['result'][0]['indicators']['quote'][0]['close'][0] = None
        with self.assertRaises(EvidenceBlocked):
            compare(raw(p), r)

    def test_required_metadata(self):
        for key, value in (('symbol','510050.SS'), ('currency','USD'), ('exchangeTimezoneName','UTC')):
            p, r = fixture()
            p['chart']['result'][0]['meta'][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceBlocked):
                compare(raw(p), r)

    def test_missing_or_duplicate_dates(self):
        p, r = fixture()
        p['chart']['result'][0]['timestamp'][-1] = p['chart']['result'][0]['timestamp'][0]
        with self.assertRaises(EvidenceBlocked): compare(raw(p), r)
        p, r = fixture()
        p['chart']['result'][0]['timestamp'][-1] += 86400
        with self.assertRaises(EvidenceBlocked): compare(raw(p), r)

    def test_vector_lengths_and_range(self):
        p, r = fixture()
        p['chart']['result'][0]['indicators']['quote'][0]['high'].pop()
        with self.assertRaises(EvidenceBlocked): compare(raw(p), r)
        p, r = fixture()
        p['chart']['result'][0]['indicators']['quote'][0]['low'][0] = 9
        with self.assertRaises(EvidenceBlocked): compare(raw(p), r)

    def test_reference_not_silently_reinterpreted(self):
        p, r = fixture()
        for changed in ([], dict(r, differences_resolved=True), dict(r, mismatches=r['mismatches'][:-1])):
            with self.assertRaises(EvidenceBlocked): compare(raw(p), changed)
        r['mismatches'][0]['tencent'] = '4.782'
        with self.assertRaises(EvidenceBlocked): compare(raw(p), r)

    def test_bad_response_and_duplicate_keys(self):
        for value in ({'chart': {'result': None, 'error': {'code':'Unauthorized'}}},
                      {'chart': []}, {'chart': {'result': [], 'error': None}}, []):
            with self.subTest(value=value), self.assertRaises(EvidenceBlocked): parse_quotes(raw(value))
        with self.assertRaises(EvidenceBlocked): load_json(b'{"chart":1,"chart":2}')
        with self.assertRaises(EvidenceBlocked): load_json(b'{"x":NaN}')


if __name__ == '__main__':
    unittest.main()
