"""Registry integrity checks, not strategy performance or agent-runtime tests."""
import json
from pathlib import Path
import unittest

from leek.channel_signal import MODEL_ID
from leek.real_backtest import STRATEGIES

ROOT = Path(__file__).resolve().parents[1]


class TraderTeamRegistryTests(unittest.TestCase):
    def setUp(self):
        self.team = json.loads((ROOT / 'research/trader_team.json').read_text(encoding='utf-8'))
        self.seats = self.team['seats']

    def test_ten_unique_stable_seats(self):
        self.assertEqual(self.team['version'], 'daily-trader-team.v1')
        self.assertEqual([s['id'] for s in self.seats], [f'T{i:02d}' for i in range(1, 11)])
        self.assertEqual(len(set(s['name'] for s in self.seats)), 10)

    def test_daily_all_seats_not_teamwide_single_candidate(self):
        self.assertIs(self.team['review_all_seats_each_run'], True)
        self.assertEqual(self.team['max_new_hypotheses_per_seat_per_round'], 1)
        self.assertEqual(self.team['shared_new_candidate_budget_per_stage'], 8)
        self.assertEqual(self.team['budget_scope'], 'whole_team_all_attempts_including_failures')

    def test_existing_strategy_bindings_are_supported(self):
        supported = set(STRATEGIES) | {MODEL_ID}
        implemented = [s for s in self.seats if s['implementation_state'] == 'IMPLEMENTED_UNVALIDATED']
        self.assertEqual(len(implemented), 3)
        self.assertEqual({s['engine_strategy'] for s in implemented},
                         {'ma120_1d', 'h001_3d', MODEL_ID})
        self.assertTrue(all(s['engine_strategy'] in supported for s in implemented))

    def test_planned_seats_do_not_claim_executable_models(self):
        planned = [s for s in self.seats if s['implementation_state'] == 'PLANNED']
        self.assertEqual(len(planned), 7)
        for seat in planned:
            self.assertIsNone(seat['engine_strategy'])
            self.assertIn('IMPLEMENTATION_MISSING', seat['current_blockers'])

    def test_every_seat_has_data_requirements_and_concrete_work(self):
        expected = {'id', 'name', 'family', 'engine_strategy', 'implementation_state',
                    'role', 'required_data', 'current_blockers', 'next_deliverable'}
        for seat in self.seats:
            self.assertEqual(set(seat), expected)
            for key in ('required_data', 'current_blockers'):
                self.assertTrue(seat[key])
                self.assertTrue(all(isinstance(x, str) and x for x in seat[key]))
            self.assertGreater(len(seat['next_deliverable']), 8)
            self.assertGreater(len(seat['role']), 8)

    def test_known_conflict_cannot_disappear_from_implemented_lanes(self):
        registry = json.loads((ROOT / 'research/data_conflicts.json').read_text(encoding='utf-8'))
        self.assertIn('DQ001', {x['id'] for x in registry['issues']})
        for seat in self.seats[:3]:
            self.assertIn('DQ001', seat['current_blockers'])

    def test_no_live_trading_or_capital_pooling(self):
        self.assertEqual(self.team['mode'], 'research_and_paper_only')
        self.assertIs(self.team['live_trading_enabled'], False)
        self.assertIs(self.team['automatic_promotion'], False)
        self.assertEqual(self.team['paper_account_policy'], 'isolated_per_strategy_never_sum_as_one_account')

    def test_related_trend_rules_not_labelled_independent_families(self):
        by_id = {s['id']: s for s in self.seats}
        self.assertEqual(by_id['T01']['family'], by_id['T02']['family'])
        self.assertNotEqual(by_id['T03']['family'], by_id['T01']['family'])

    def test_specialized_data_is_not_replaced_with_daily_ohlc(self):
        by_id = {s['id']: s for s in self.seats}
        self.assertIn('point_in_time_financials', by_id['T07']['required_data'])
        self.assertIn('actual_publication_times', by_id['T07']['required_data'])
        self.assertIn('timestamped_announcements', by_id['T08']['required_data'])
        self.assertIn('limit_queue_and_fill_evidence', by_id['T09']['required_data'])
        self.assertIn('out_of_selection_strategy_returns', by_id['T10']['required_data'])

    def test_registry_is_not_a_performance_report_or_deployed_runtime(self):
        self.assertEqual(self.team['implemented_batch_entrypoint'], 'research.run_h002')
        self.assertIn('sequentially', self.team['batch_entrypoint_note'])
        self.assertIn('not a deployed', self.team['batch_entrypoint_note'])
        for seat in self.seats:
            for key in ('profit', 'win_rate', 'validated', 'agent_running', 'account_balance'):
                self.assertNotIn(key, seat)


if __name__ == '__main__':
    unittest.main()
