import copy
import unittest
from unittest.mock import patch
from research.run_h002 import screen, require_data_issue_resolution, run
from leek.contract import DataBlocked


class GovernanceTests(unittest.TestCase):
    def test_unresolved_or_missing_issue_blocks(self):
        for registry in ({}, {'version':'data-conflicts.v1','issues':[]},
                         {'version':'data-conflicts.v1','issues':[{'id':'DQ001','status':'UNRESOLVED'}]}):
            with self.assertRaises(DataBlocked): require_data_issue_resolution(registry)

    def test_resolution_label_without_evidence_blocks(self):
        r={'version':'data-conflicts.v1','issues':[{'id':'DQ001','status':'RESOLVED_REVIEWED','resolution':None}]}
        with self.assertRaises(DataBlocked): require_data_issue_resolution(r)

    def test_arbitrary_resolution_fields_never_approve_a_review(self):
        r={'version':'data-conflicts.v1','issues':[{'id':'DQ001','status':'RESOLVED_REVIEWED',
            'resolution':{'review_commit':'synthetic-test','evidence_urls':['https://example.com/test'], 'rationale':'synthetic'}}]}
        with self.assertRaises(DataBlocked): require_data_issue_resolution(r)
        for field in ('review_commit','evidence_urls','rationale'):
            changed=copy.deepcopy(r); changed['issues'][0]['resolution'].pop(field)
            with self.assertRaises(DataBlocked): require_data_issue_resolution(changed)

    def test_real_runner_blocks_before_network_even_with_single_source_flag(self):
        unresolved={'version':'data-conflicts.v1','issues':[{'id':'DQ001','status':'UNRESOLVED'}]}
        with patch('research.run_h002.load', return_value=(unresolved, 'test-only')), \
                patch('research.run_h002.acquire') as fetch:
            with self.assertRaisesRegex(DataBlocked,'DQ001'):
                run('/unused/input','/unused/output',fetch=True,allow_single_source=True)
            fetch.assert_not_called()

    def test_passing_screen_is_not_promotion(self):
        candidate=dict(total_return_pct=3,max_close_drawdown_pct=-4,profit_factor=1.3,closed_trades=30)
        results={'base__h002_channel_20_10':dict(candidate), 'stress__h002_channel_20_10':dict(candidate),
                 'base__ma120_1d':dict(total_return_pct=1,max_close_drawdown_pct=-5)}
        r=screen(results)
        self.assertEqual(r['decision'],'RESEARCH_SCREEN_PASS')
        self.assertFalse(r['automatic_promotion']); self.assertFalse(r['untouched_holdout'])
        results['stress__h002_channel_20_10']['total_return_pct']=-0.1
        self.assertEqual(screen(results)['decision'],'REJECTED_DEVELOPMENT_SCREEN')

    def test_small_sample_or_undefined_profit_factor_cannot_pass(self):
        candidate=dict(total_return_pct=3,max_close_drawdown_pct=-4,profit_factor=1.3,closed_trades=30)
        r={'base__h002_channel_20_10':dict(candidate),'stress__h002_channel_20_10':dict(candidate),
           'base__ma120_1d':dict(total_return_pct=1,max_close_drawdown_pct=-5)}
        for change in ({'closed_trades':19},{'profit_factor':None},{'profit_factor':0.9}):
            changed=copy.deepcopy(r); changed['stress__h002_channel_20_10'].update(change)
            self.assertEqual(screen(changed)['decision'],'REJECTED_DEVELOPMENT_SCREEN')

if __name__=='__main__': unittest.main()
