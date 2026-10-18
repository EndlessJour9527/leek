"""Independent synthetic regression tests for paper-only accounting boundaries."""
import copy
from dataclasses import replace
from decimal import Decimal as D
import unittest

from leek.contract import DataBlocked
from leek.interfaces import SignalEnvelope
from leek.ledger import Ledger


class IndependentBoundaryTests(unittest.TestCase):
    def test_future_sale_cash_cannot_fund_past_buy(self):
        account = Ledger('100', ['SYNTH_A', 'SYNTH_B'])
        account.fill('SYNTH_A', 'BUY', '10', '10', '10', '0', '2024-01-01')
        account.fill('SYNTH_A', 'SELL', '10', '10', '10', '0', '2024-01-03')
        before = copy.deepcopy(account.__dict__)
        with self.assertRaises(ValueError):
            account.fill('SYNTH_B', 'BUY', '10', '10', '10', '0', '2024-01-02')
        self.assertEqual(account.__dict__, before)

    def test_same_day_cross_symbol_cash_is_permitted(self):
        account = Ledger('100', ['SYNTH_A', 'SYNTH_B'])
        account.fill('SYNTH_A', 'BUY', '10', '10', '10', '0', '2024-01-01')
        account.fill('SYNTH_A', 'SELL', '10', '10', '10', '0', '2024-01-02')
        account.fill('SYNTH_B', 'BUY', '10', '10', '10', '0', '2024-01-02')
        self.assertEqual(account.cash, D(0))
        self.assertEqual(account.sellable('SYNTH_B', '2024-01-02'), D(0))

    def test_split_rounding_does_not_make_today_lot_settled(self):
        account = Ledger('100', ['SYNTH_A'])
        account.fill('SYNTH_A', 'BUY', '1', '10', '10', '0', '2024-01-01')
        account.fill('SYNTH_A', 'BUY', '1', '10', '10', '0', '2024-01-02')
        account.record('SYNTH_A', 'synthetic-split')
        account.ex('SYNTH_A', 'synthetic-split', '0', '.3', 'ceil_whole_account')
        self.assertEqual(account.positions['SYNTH_A']['qty'], D(1))
        self.assertEqual(account.sellable('SYNTH_A', '2024-01-02'), D('.3'))
        self.assertEqual(sum(n for _, n in account.positions['SYNTH_A']['lots']), D(1))

    def test_cash_dividend_and_exact_split_nav_conserved(self):
        account = Ledger('100', ['SYNTH_A'])
        account.fill('SYNTH_A', 'BUY', '7', '10', '10', '0', '2024-01-01')
        account.record('SYNTH_A', 'synthetic-action')
        account.ex('SYNTH_A', 'synthetic-action', '1', '1.5', 'exact')
        self.assertEqual(account.nav({'SYNTH_A': '6'}), D(100))
        account.pay('SYNTH_A', 'synthetic-action')
        self.assertEqual(account.nav({'SYNTH_A': '6'}), D(100))
        self.assertEqual(account.positions['SYNTH_A']['basis'], D(70))

    def test_duplicate_actions_leave_state_unchanged(self):
        account = Ledger('100', ['SYNTH_A'])
        account.record('SYNTH_A', 'synthetic-action')
        account.ex('SYNTH_A', 'synthetic-action', '1', '1', 'exact')
        account.pay('SYNTH_A', 'synthetic-action')
        for action in (
            lambda: account.record('SYNTH_A', 'synthetic-action'),
            lambda: account.ex('SYNTH_A', 'synthetic-action', '1', '1', 'exact'),
            lambda: account.pay('SYNTH_A', 'synthetic-action'),
        ):
            before = copy.deepcopy(account.__dict__)
            with self.assertRaises(ValueError):
                action()
            self.assertEqual(account.__dict__, before)

    def test_signal_timestamps_compare_absolute_instants(self):
        envelope = SignalEnvelope('SYNTH_A', '2024-01-01T18:00:00+08:00',
                                  '2024-01-01T18:01:00+08:00', '.5',
                                  'synthetic-model', 'a' * 64)
        self.assertEqual(envelope.validate('2024-01-01T10:02:00Z'), D('.5'))
        with self.assertRaises(DataBlocked):
            envelope.validate('2024-01-01T09:59:00Z')

    def test_malformed_signal_fails_with_contract_error(self):
        envelope = SignalEnvelope('SYNTH_A', '2024-01-01T10:00:00Z',
                                  '2024-01-01T10:01:00Z', '.5',
                                  'synthetic-model', 'a' * 64)
        for changes in ({'target_weight': 'NaN'}, {'dataset_hash': None},
                        {'instrument': 123}, {'model_id': []}):
            with self.subTest(changes=changes):
                with self.assertRaises(DataBlocked):
                    replace(envelope, **changes).validate('2024-01-01T10:02:00Z')


if __name__ == '__main__':
    unittest.main()
