"""Offline end-to-end and adversarial tests, using only synthetic prices."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from decimal import getcontext, localcontext, ROUND_UP
from unittest.mock import patch

from leek.contract import DataBlocked
from leek.replay import atomic_create, canonical, digest, load, run, VERSION

FIXTURES = Path(__file__).resolve().parents[1] / 'examples' / 'fixtures'


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = json.loads((FIXTURES / 'replay-config.json').read_text())
        self.data = json.loads((FIXTURES / 'replay-bars.json').read_text())
        self.sequence = 0

    def execute(self, config=None, data=None, **kwargs):
        self.sequence += 1
        prefix = self.root / str(self.sequence)
        config_path = prefix.with_suffix('.config.json')
        data_path = prefix.with_suffix('.data.json')
        config_path.write_bytes(canonical(self.config if config is None else config))
        data_path.write_bytes(canonical(self.data if data is None else data))
        result = run(config_path, data_path, prefix, **kwargs)
        return result, prefix

    def test_exact_ledger_and_next_explicit_session(self):
        report, _ = self.execute()
        self.assertEqual([x['execute_on'] for x in report['orders']], ['2025-01-06', '2025-01-08', '2025-01-09'])
        first = report['daily'][2]
        self.assertEqual(first['cash'], '8957.960')
        self.assertEqual(first['basis'], '1042.040')
        self.assertEqual(first['unrealized_pnl'], '-32.040')
        self.assertEqual(first['nav'], '9967.960')
        final = report['daily'][-1]
        self.assertEqual(final['cash'], '8893.920')
        self.assertEqual(final['nav'], '9933.920')
        self.assertEqual(final['realized_pnl'], '-54.030')
        self.assertEqual(final['unrealized_pnl'], '-12.050')
        self.assertEqual(final['commission'], '3')
        self.assertEqual(final['slippage'], '3.080')
        self.assertIsNone(report['pending_order']['execute_on'])
        self.assertEqual(len(report['processed_event_ids']), len(set(report['processed_event_ids'])))

    def test_every_checkpoint_split_is_byte_identical(self):
        full, full_path = self.execute()
        for count in range(1, len(self.data['calendar']) + 1):
            with self.subTest(count=count):
                partial, path = self.execute(stop_after=count)
                resumed, resumed_path = self.execute(resume=path / 'checkpoint.json')
                self.assertEqual(full, resumed)
                for name in ('report.json', 'checkpoint.json'):
                    self.assertEqual((full_path / name).read_bytes(), (resumed_path / name).read_bytes())

    def test_future_hlc_do_not_change_open_execution(self):
        original, _ = self.execute()
        changed = copy.deepcopy(self.data)
        changed['bars'][2].update(high='200', low='1', close='150')
        altered, _ = self.execute(data=changed)
        self.assertEqual(original['signals'][0], altered['signals'][0])
        self.assertEqual(original['orders'][0], altered['orders'][0])
        self.assertNotEqual(original['daily'][2]['nav'], altered['daily'][2]['nav'])

    def test_future_open_only_changes_fill_not_order_quantity(self):
        original, _ = self.execute()
        changed = copy.deepcopy(self.data)
        changed['bars'][2]['open'] = '105'
        altered, _ = self.execute(data=changed)
        for key in ('event_id', 'quantity', 'side', 'signal_date', 'execute_on'):
            self.assertEqual(original['orders'][0][key], altered['orders'][0][key])
        self.assertNotEqual(original['orders'][0]['fill_price'], altered['orders'][0]['fill_price'])

    def test_no_calendar_skip_missing_duplicate_or_unknown_bar_fields(self):
        cases = []
        missing = copy.deepcopy(self.data); missing['bars'].pop(2); cases.append(missing)
        duplicate = copy.deepcopy(self.data); duplicate['bars'][2] = duplicate['bars'][1]; cases.append(duplicate)
        extra = copy.deepcopy(self.data); extra['bars'][0]['adjusted_close'] = '100'; cases.append(extra)
        unordered = copy.deepcopy(self.data); unordered['calendar'].reverse(); cases.append(unordered)
        invalid = copy.deepcopy(self.data); invalid['calendar'][0] = None; cases.append(invalid)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(DataBlocked):
                self.execute(data=data)

    def test_corporate_actions_adjustment_and_real_data_fail_closed(self):
        for field, value in [('corporate_actions', [{'type': 'split', 'ratio': '2'}]),
                             ('adjustment', 'split_adjusted'), ('synthetic', False), ('currency', 'USD')]:
            data = copy.deepcopy(self.data); data[field] = value
            with self.subTest(field=field), self.assertRaises(DataBlocked):
                self.execute(data=data)

    def test_insufficient_cash_rejects_without_fees_or_partial_fill(self):
        config = dict(self.config, initial_cash='1')
        report, _ = self.execute(config=config)
        self.assertTrue(report['orders'])
        self.assertTrue(all(x['status'] == 'rejected' for x in report['orders']))
        self.assertTrue(all(x['cash'] == '1' and x['quantity'] == '0' and x['commission'] == '0' for x in report['daily']))

    def test_input_config_and_source_changes_reject_resume(self):
        _, path = self.execute(stop_after=3)
        checkpoint = path / 'checkpoint.json'
        with self.assertRaises(DataBlocked):
            self.execute(config=dict(self.config, quantity='11'), resume=checkpoint)
        data = copy.deepcopy(self.data); data['bars'][-1]['close'] = '105'
        with self.assertRaises(DataBlocked):
            self.execute(data=data, resume=checkpoint)
        with patch('leek.replay.source_hash', return_value='0' * 64), self.assertRaises(DataBlocked):
            self.execute(resume=checkpoint)

    def test_tampered_checkpoint_rejected_even_with_recomputed_digest(self):
        _, path = self.execute(stop_after=3)
        original, _ = load(path / 'checkpoint.json')
        for field, value in [('cash', '999999'), ('quantity', '100')]:
            checkpoint = copy.deepcopy(original)
            checkpoint['report']['daily'][-1][field] = value
            checkpoint['report_sha256'] = digest(canonical(checkpoint['report']))
            tampered = self.root / ('tampered-' + field + '.json')
            tampered.write_bytes(canonical(checkpoint))
            with self.assertRaises(DataBlocked):
                self.execute(resume=tampered)
        for cursor in (True, 0, 999, '3'):
            checkpoint = copy.deepcopy(original); checkpoint['processed_sessions'] = cursor
            tampered = self.root / 'cursor.json'; tampered.write_bytes(canonical(checkpoint))
            with self.assertRaises(DataBlocked):
                self.execute(resume=tampered)

    def test_repeat_run_and_resume_refuse_existing_directory(self):
        _, path = self.execute(stop_after=3)
        before = (path / 'checkpoint.json').read_bytes()
        config = path.with_suffix('.config.json'); data = path.with_suffix('.data.json')
        for resume in (None, path / 'checkpoint.json'):
            with self.assertRaises(FileExistsError):
                run(config, data, path, resume=resume)
        self.assertEqual(before, (path / 'checkpoint.json').read_bytes())

    def test_atomic_create_never_overwrites_and_cleans_temp(self):
        path = self.root / 'out.json'; atomic_create(path, {'v': 1})
        with self.assertRaises(FileExistsError):
            atomic_create(path, {'v': 2})
        self.assertEqual(path.read_bytes(), canonical({'v': 1}))
        self.assertEqual(list(self.root.iterdir()), [path])
        with patch('leek.replay.os.link', side_effect=OSError('simulated failure')), self.assertRaises(OSError):
            atomic_create(self.root / 'failed.json', {'v': 2})
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_recovery_after_report_publication_failure(self):
        import leek.replay as module
        real = module.atomic_create
        def fail_report(path, value):
            if path.name == 'report.json':
                raise OSError('simulated interruption')
            real(path, value)
        with patch('leek.replay.atomic_create', side_effect=fail_report), self.assertRaises(OSError):
            self.execute(stop_after=3)
        checkpoint = self.root / '1' / 'checkpoint.json'
        self.assertTrue(checkpoint.is_file())
        recovered, _ = self.execute(resume=checkpoint)
        expected, _ = self.execute()
        self.assertEqual(expected, recovered)

    def test_decimal_context_does_not_change_results(self):
        expected, _ = self.execute()
        with localcontext() as context:
            context.prec = 6; context.rounding = ROUND_UP; context.Emax = 2
            actual, _ = self.execute()
        self.assertEqual(expected, actual)

    def test_invalid_config_and_duplicate_json_rejected(self):
        for field, value in [('lookback', True), ('quantity', '0.1'), ('commission', '-1'), ('slippage_bps', '10000'), ('initial_cash', 'NaN')]:
            with self.subTest(field=field), self.assertRaises(DataBlocked):
                self.execute(config=dict(self.config, **{field: value}))
        path = self.root / 'duplicate.json'; path.write_text('{"v":1,"v":2}')
        with self.assertRaises(DataBlocked): load(path)


if __name__ == '__main__':
    unittest.main()
