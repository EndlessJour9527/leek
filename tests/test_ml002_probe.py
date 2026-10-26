"""Synthetic contract tests only. No market profitability assertions."""
import json
import unittest
from decimal import Decimal
from research.ml002.probe import Blocked, _normalize, compare_prices, parse_sse, parse_tencent


class MultiETFProbeTests(unittest.TestCase):
    def setUp(self):
        self.sse = json.dumps({'code':'511010', 'kline':[
            [20250102,'141.001','141.011','140.900','141.003','10',None],
            [20250103,'141.050','141.070','141.001','141.030','20',None]]}).encode()
        self.tx = json.dumps({'data':{'sh511010':{'day':[
            ['2025-01-02','141.001','141.003','141.011','140.900','10'],
            ['2025-01-03','141.050','141.030','141.070','141.001','20']]}}}).encode()

    def test_decimal_identity_and_affordability_research_budget(self):
        a = parse_sse(self.sse,'511010')
        b = parse_tencent(self.tx,'511010',2025)
        self.assertEqual(a,b)
        q = compare_prices(a,b,list(a))
        self.assertTrue(q['prices_feasible'])
        self.assertTrue(q['lot_always_exceeds_reference_budget'])
        self.assertEqual(q['sessions_affordable_at_fixed_reference_budget'],0)
        self.assertEqual(q['differing_ohlc_cells'],0)

    def test_one_tick_rejected_without_tolerance(self):
        a = parse_sse(self.sse,'511010')
        b = parse_tencent(self.tx,'511010',2025)
        b['2025-01-02']['close'] += Decimal('0.001')
        q = compare_prices(a,b,list(a))
        self.assertFalse(q['prices_feasible'])
        self.assertEqual(q['differing_ohlc_cells'],1)

    def test_missing_session_blocks(self):
        a = parse_sse(self.sse,'511010')
        b = parse_tencent(self.tx,'511010',2025)
        b.pop('2025-01-03')
        q = compare_prices(a,b,list(a))
        self.assertFalse(q['prices_feasible'])
        self.assertEqual(q['tencent_missing_vs_calendar'],1)

    def test_wrong_symbol_and_duplicate_block(self):
        with self.assertRaises(Blocked):parse_sse(self.sse,'510300')
        with self.assertRaises(Blocked):parse_sse(self.sse.replace(b'20250103',b'20250102'),'511010')

    def test_invalid_hilo_blocks(self):
        with self.assertRaises(Blocked):parse_sse(self.sse.replace(b'140.900',b'141.040'),'511010')

    def test_invalid_day_and_empty_block(self):
        with self.assertRaises(Blocked):_normalize([('2025-02-30',{'open':1,'high':2,'low':1,'close':2})])
        with self.assertRaises(Blocked):_normalize([])


if __name__ == '__main__':unittest.main()
