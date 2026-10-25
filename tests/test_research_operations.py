"""Offline operations tests; mocked ready paths are NOT market evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research import cli
from leek.contract import DataBlocked


class OperationsTests(unittest.TestCase):
    def test_conflict_gate_precedes_market_reads_and_fetch(self):
        for name in ('h002', 'h003'):
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / 'new-output'
                with patch.object(cli, 'require_history_review', side_effect=DataBlocked('DQ001 unresolved fixture')), \
                     patch.object(cli, 'load', side_effect=AssertionError('input read')), \
                     patch('research.run_real_history.acquire', side_effect=AssertionError('fetch')):
                    report = cli.run_experiment(name, target, Path(temp) / 'absent', fetch=True,
                                                allow_single_source=True)
                self.assertEqual(report['status'], 'BLOCKED_DATA')
                self.assertEqual(report['historical_replays_completed'], 0)
                self.assertFalse(target.exists())

    def test_ca1_missing_files_all_reported(self):
        report = cli.preflight('ca1')
        self.assertEqual(report['status'], 'BLOCKED_INPUTS')
        self.assertEqual(len(report['missing']), 10)
        self.assertEqual(report['mismatched'], [])
        self.assertIn('implementation/INPUTS.json', report['missing'])
        self.assertIn('independent_audit/metrics_final.json', report['missing'])

    def test_ca1_bad_hash_reported_without_reissuing_release(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'implementation'; p.mkdir()
            (p / 'INPUTS.json').write_text('{}')
            report = cli.preflight('ca1', private_root=temp)
            self.assertIn('implementation/INPUTS.json', report['mismatched'])
            self.assertEqual(report['status'], 'BLOCKED_INPUTS')

    def test_missing_source_never_creates_restore_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'new'
            report = cli.restore_ca1(temp, target)
            self.assertEqual(report['status'], 'BLOCKED_INPUTS')
            self.assertFalse(target.exists())

    def test_synthetic_private_restore_and_exclusive_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            capsule, source, dest = [Path(temp) / x for x in ('public', 'source', 'restored')]
            capsule.mkdir(); source.mkdir()
            (capsule / 'README.md').write_text('synthetic public fixture')
            (source / 'input.json').write_text('synthetic private fixture')
            required = {'input.json': cli.sha(source / 'input.json')}
            with patch.object(cli, 'CAPSULE', capsule), patch.object(cli, 'ca1_requirements', return_value=required):
                report = cli.restore_ca1(source, dest)
                self.assertEqual(report['status'], 'RESTORED_PRIVATE_INPUTS')
                self.assertEqual(report['historical_replays_completed'], 0)
                self.assertEqual((dest / 'input.json').read_bytes(), (source / 'input.json').read_bytes())
                with self.assertRaises(ValueError): cli.restore_ca1(source, dest)
                (source / 'input.json').write_text('changed')
                blocked = cli.restore_ca1(source, Path(temp) / 'other')
                self.assertEqual(blocked['status'], 'BLOCKED_INPUTS')
                self.assertFalse((Path(temp) / 'other').exists())

    def test_paths_cannot_escape_or_use_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'file').write_text('x')
            (root / 'link').symlink_to(root / 'file')
            for path in ('../outside', 'link', '/etc/passwd'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    cli.bound_path(root, path)

    def test_status_has_real_code_bindings_not_returns(self):
        with patch.object(cli, 'require_history_review', side_effect=DataBlocked('DQ001 unresolved fixture')):
            report = cli.status()
        self.assertEqual(report['status'], 'STATUS_REPORT_ONLY')
        lanes = {x['experiment']: x for x in report['lanes']}
        self.assertEqual(lanes['h003']['implementation'], 'IMPLEMENTED')
        self.assertEqual(lanes['h003']['readiness']['status'], 'BLOCKED_DATA')
        self.assertEqual(report['seats'][3]['implementation_state'], 'IMPLEMENTED_UNVALIDATED')
        self.assertFalse(report['automatic_promotion'])

    def test_cli_report_is_exclusive_and_blocked_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'report.json'
            with patch.object(cli, 'require_history_review', side_effect=DataBlocked('DQ001 unresolved fixture')), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(['preflight', '--experiment', 'h003', '--report', str(path)])
            self.assertEqual(code, 2)
            initial = path.read_bytes()
            self.assertEqual(json.loads(initial)['status'], 'BLOCKED_DATA')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                cli.main(['preflight', '--experiment', 'h003', '--report', str(path)])
            self.assertEqual(path.read_bytes(), initial)

    def test_dispatch_does_not_claim_qualified_success(self):
        # Synthetic mock protocol tests only: no gate or data file changed.
        original = dict(evidence_grade='TEST_ONLY', assessment={'decision': 'REJECTED_DEVELOPMENT_SCREEN'}, binding={})
        with tempfile.TemporaryDirectory() as temp, patch.object(cli, 'preflight', return_value={'status': 'READY_FOR_CONDITIONAL_RESEARCH'}), \
             patch('research.run_h003.run', return_value=original) as runner:
            report = cli.run_experiment('h003', Path(temp) / 'result', data_dir='synthetic')
            runner.assert_called_once()
            self.assertEqual(report['status'], 'COMPLETED_CONDITIONAL_RESEARCH')
            self.assertFalse(report['automatic_promotion'])
            self.assertFalse(report['new_independent_market_evidence'])

    def test_downstream_block_is_not_completion(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(cli, 'preflight', return_value={'status': 'READY_FOR_ACQUISITION'}), \
             patch('research.run_h002.run', side_effect=DataBlocked('conflict detected')):
            report = cli.run_experiment('h002', Path(temp) / 'out', fetch=True)
            self.assertEqual(report['status'], 'BLOCKED_DATA')
            self.assertEqual(report['historical_replays_completed'], 0)

    def test_optimized_historical_runner_is_disabled(self):
        for mode in ('-O', '-OO'):
            with tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / 'out'
                result = subprocess.run([sys.executable, mode, '-m', 'research.cli', 'run',
                    '--experiment', 'ca1', '--output', str(out)], cwd=cli.ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'BLOCKED_RUNTIME')
                self.assertFalse(out.exists())

    def test_unknown_experiment_rejected(self):
        with self.assertRaises(ValueError): cli.preflight('anything')


if __name__ == '__main__':
    unittest.main()
