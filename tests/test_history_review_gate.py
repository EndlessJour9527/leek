"""Regression for old CLI single-source bypass; never fetch market data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leek.contract import DataBlocked
from leek.history_review_gate import require_history_review
from leek.real_backtest import run as strict_run
from research.run_real_history import execute, main


class HistoricalReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = Path(self.tmp.name) / 'registry.json'
        self.patcher = patch('leek.history_review_gate.REGISTRY_PATH', self.registry)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.unresolved = {'version':'data-conflicts.v1','issues':[{'id':'DQ001','status':'UNRESOLVED','resolution':None}]}
        self.write(self.unresolved)

    def write(self, value):
        self.registry.write_text(json.dumps(value))

    def test_unresolved_blocks(self):
        with self.assertRaisesRegex(DataBlocked, 'DQ001'):
            require_history_review()

    def test_missing_file_blocks(self):
        self.registry.unlink()
        with self.assertRaises(DataBlocked):
            require_history_review()

    def test_missing_issue_or_duplicate_issue_blocks(self):
        for issues in ([],self.unresolved['issues'] * 2):
            self.write({'version':'data-conflicts.v1','issues':issues})
            with self.assertRaises(DataBlocked): require_history_review()

    def test_bad_json_and_schema_block(self):
        for text in ('{','{"version":"data-conflicts.v1","version":"other","issues":[]}', '[]'):
            self.registry.write_text(text)
            with self.assertRaises(DataBlocked): require_history_review()

    def test_label_without_evidence_blocks(self):
        value=copy.deepcopy(self.unresolved)
        value['issues'][0]['status']='RESOLVED_REVIEWED'
        self.write(value)
        with self.assertRaises(DataBlocked): require_history_review()

    def test_declared_shape_alone_is_not_a_review_without_bound_evidence(self):
        value=copy.deepcopy(self.unresolved)
        value['issues'][0].update(status='RESOLVED_REVIEWED',resolution={
            'review_commit':'a'*40,'evidence_urls':['https://example.com/synthetic-review'],
            'rationale':'Synthetic test of record shape, not a real approval.'})
        self.write(value); before=self.registry.read_bytes()
        with self.assertRaises(DataBlocked): require_history_review()
        self.assertEqual(before,self.registry.read_bytes())
        for field in ('review_commit','evidence_urls','rationale'):
            altered=copy.deepcopy(value);altered['issues'][0]['resolution'].pop(field)
            self.write(altered)
            with self.assertRaises(DataBlocked): require_history_review()

    def test_single_source_execute_stops_before_input_or_output(self):
        out=Path(self.tmp.name)/'out'
        with patch('research.run_real_history.load') as read:
            with self.assertRaisesRegex(DataBlocked,'DQ001'):
                execute('/unused','/unused',out,True)
            read.assert_not_called()
        self.assertFalse(out.exists())

    def test_old_cli_stops_before_optional_fetch(self):
        with patch('sys.argv',['run_real_history','--fetch','--allow-single-source',
                '--data-dir','/unused','--output',str(Path(self.tmp.name)/'out')]), \
                patch('research.run_real_history.acquire') as fetch:
            with self.assertRaisesRegex(DataBlocked,'DQ001'): main()
            fetch.assert_not_called()

    def test_strict_file_cli_stops_before_market_input(self):
        with patch('leek.real_backtest.load') as read:
            with self.assertRaisesRegex(DataBlocked,'DQ001'):
                strict_run('/unused','/unused',Path(self.tmp.name)/'out')
            read.assert_not_called()


if __name__=='__main__': unittest.main()
