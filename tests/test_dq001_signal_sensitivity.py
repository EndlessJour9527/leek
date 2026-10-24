"""Offline invariance AND positive control: check the comparison detects actual flips."""
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import tempfile

from leek.channel_signal import CloseChannel2010
from leek.mean_reversion_signal import MeanReversion20
from research.dq001_signal_sensitivity import (
    SensitivityInputError, different_state_days, exact_levels, parse_archive_entry,
)


class TestDQ001SignalSensitivity(unittest.TestCase):
    def setUp(self):
        self.days = [f"day-{i:02}" for i in range(21)]

    def test_positive_control_detects_h002_entry_flip(self):
        prev = [Fraction(1)] * 20
        a = prev + [Fraction(2)]
        b = prev + [Fraction(1)]
        self.assertEqual(different_state_days(self.days, a, b, 20, CloseChannel2010, False), [self.days[-1]])
        self.assertEqual(different_state_days(self.days, a, b, 20, CloseChannel2010, True), [])

    def test_positive_control_detects_h003_entry_flip(self):
        prev = [Fraction(10)] * 10 + [Fraction(12)] * 10
        a = prev + [Fraction(9)]  # mean=11, population sigma=1
        b = prev + [Fraction(10)]
        self.assertEqual(different_state_days(self.days, a, b, 20, MeanReversion20, False), [self.days[-1]])
        self.assertEqual(different_state_days(self.days, a, b, 20, MeanReversion20, True), [])

    def test_one_tick_h002_flips_at_strict_boundary(self):
        prev = [Fraction('1.000')] * 20
        base = prev + [Fraction('1.000')]
        raised = prev + [Fraction('1.001')]
        self.assertEqual(different_state_days(self.days, base, raised, 20, CloseChannel2010, False), [self.days[-1]])

    def test_one_tick_h003_flips_at_exact_band(self):
        prev = [Fraction(10)] * 10 + [Fraction(12)] * 10
        at_threshold = prev + [Fraction('9.000')]
        one_tick_higher = prev + [Fraction('9.001')]
        self.assertEqual(different_state_days(self.days, at_threshold, one_tick_higher, 20, MeanReversion20, False), [self.days[-1]])

    def test_identical_input_yields_no_signal_disagreement(self):
        a = [Fraction(10)] * 10 + [Fraction(12)] * 10 + [Fraction(9)]
        for cls in (MeanReversion20, CloseChannel2010):
            for state in (False, True):
                self.assertEqual(different_state_days(self.days, a, a, 20, cls, state), [])

    def test_previous_window_required(self):
        with self.assertRaises(SensitivityInputError):
            different_state_days(self.days, [Fraction(1)] * 21, [Fraction(1)] * 21, 19, CloseChannel2010, False)

    def test_mirror_ledger_exact_dividend_transition(self):
        days = ["a", "b", "c"]
        levels = exact_levels(days, {"a":Decimal('4.000'),"b":Decimal('4.010'),"c":Decimal('3.910')},
                              {"c":Decimal('0.100')})
        self.assertEqual(levels, [Fraction(4),Fraction('4.010'),Fraction('4.010')])

    def test_wrong_archive_does_not_silently_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'invalid.zip'
            p.write_bytes(b'not a zip')
            with self.assertRaises(SensitivityInputError):
                parse_archive_entry(p)


if __name__ == "__main__":
    unittest.main()
