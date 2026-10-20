import copy
import math
import unittest
from datetime import date, timedelta
from decimal import Decimal as D

from leek.contract import DataBlocked
from leek.risk_signals import RiskState, estimate


class RiskTests(unittest.TestCase):
    def test_zero_sigma_caps(self):
        self.assertEqual(estimate([0] * 60), ('0.0', '0.95'))

    def test_sample_variance(self):
        sigma, exposure = estimate(['.01', '-.01'] * 30)
        expected = math.sqrt(252 * 60 * .0001 / 59)
        self.assertAlmostEqual(float(sigma), expected, places=14)
        self.assertAlmostEqual(float(exposure), .1 / expected, places=14)

    def test_invalid_windows(self):
        for values in ([0] * 59, [0] * 61, [0] * 59 + ['NaN'], [0] * 59 + [None], [0] * 59 + [1e200]):
            with self.assertRaises(DataBlocked):
                estimate(values)

    def test_warmup_and_future_independence(self):
        a = RiskState(['SYNTH_A', 'SYNTH_B'])
        start = date(2024, 1, 1)
        for i in range(60):
            a.update(str(start + timedelta(days=i)), {s: D(100) + i for s in a.symbols})
        with self.assertRaises(DataBlocked):
            a.signal()
        a.update(str(start + timedelta(days=60)), {s: 160 for s in a.symbols})
        snapshot = a.signal()
        b = copy.deepcopy(a)
        a.update(str(start + timedelta(days=61)), {s: 1000 for s in a.symbols})
        b.update(str(start + timedelta(days=61)), {s: 1 for s in b.symbols})
        self.assertNotEqual(a.signal(), b.signal())
        self.assertEqual(snapshot['observations'], 60)
        self.assertEqual(snapshot['tr_base_date'], '2024-01-01')
        self.assertEqual(snapshot['return_window_end'], '2024-03-01')

    def test_pool_chronology_and_atomic_rejection(self):
        for symbols in ([], ['A', 'A']):
            with self.assertRaises(DataBlocked):
                RiskState(symbols)
        state = RiskState(['A', 'B'])
        state.update('2024-01-01', {'A': 1, 'B': 1})
        before = copy.deepcopy(state.__dict__)
        for day, values in [('2024-01-01', {'A': 1, 'B': 1}), ('2024-01-02', {'A': 1}), ('invalid', {'A': 1, 'B': 1})]:
            with self.assertRaises(DataBlocked):
                state.update(day, values)
            self.assertEqual(state.__dict__, before)
