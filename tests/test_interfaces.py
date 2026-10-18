import unittest
from dataclasses import replace
from decimal import Decimal
from leek.interfaces import SignalEnvelope
from leek.contract import DataBlocked


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.signal = SignalEnvelope('SYNTH_A', '2024-01-01T10:00:00+00:00', '2024-01-01T10:01:00+00:00', '0.5', 'synthetic-v1', 'a' * 64)
        self.decision = '2024-01-01T10:02:00+00:00'

    def test_valid_signal(self):
        self.assertEqual(self.signal.validate(self.decision), Decimal('0.5'))

    def test_late_future_naive_or_unpinned_signal_rejected(self):
        for change in ({'available_at': '2024-01-01T10:03:00+00:00'}, {'asof': '2024-01-02T00:00:00+00:00'}, {'asof': '2024-01-01T10:00:00'}, {'dataset_hash': ''}, {'target_weight': '-0.1'}):
            with self.assertRaises(DataBlocked):
                replace(self.signal, **change).validate(self.decision)
