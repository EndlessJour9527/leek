"""Offline integrity fixtures; synthetic reviews below are NOT real approvals."""
import copy
from decimal import Decimal
import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leek import history_adjudication as a
from leek.contract import DataBlocked
from leek.history_review_gate import require_history_review
from leek.replay import canonical, digest
from research.run_real_history import evidence_allowed, execute
from leek.real_backtest import run as strict_run

ROOT = Path(__file__).resolve().parents[1]


class ReviewedPrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audit = json.loads((ROOT / a.AUDIT_PATH).read_bytes())
        for name in (a.AUDIT_PATH, a.EVIDENCE_PATH):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        self.evidence = json.loads((self.root / a.EVIDENCE_PATH).read_bytes())
        self.commit = 'f' * 40  # nonexistent synthetic test identity; patched trust root only
        self.review = dict(version='DQ001.source-review.v1', status='PASS_REVIEWED_SOURCE_PRECEDENCE',
            policy=a.POLICY, review_commit=self.commit, evidence_sha256=digest(canonical(self.evidence)),
            original_audit_sha256=a.AUDIT_SHA256, synthetic_fixture=True,
            checks=dict(official_source_identity=True, field_mapping=True,
                        bounded_unadjusted_basis_supported=True, all_twenty_cells=True,
                        original_audit_preserved=True))
        (self.root / a.EVIDENCE_PATH).write_bytes(canonical(self.evidence))
        (self.root / a.REVIEW_PATH).parent.mkdir(parents=True, exist_ok=True)
        (self.root / a.REVIEW_PATH).write_bytes(canonical(self.review))
        self.record = dict(review_commit=self.commit, evidence_path=a.EVIDENCE_PATH,
            evidence_sha256=digest(canonical(self.evidence)), review_path=a.REVIEW_PATH,
            review_sha256=digest(canonical(self.review)),
            evidence_urls=['https://example.com/synthetic-review'], rationale='Synthetic contract test only')
        self.registry = dict(version='data-conflicts.v1', issues=[dict(id='DQ001',
            status='RESOLVED_REVIEWED', resolution=self.record)])
        self.registry_path = self.root / 'registry.json'
        self.registry_path.write_bytes(canonical(self.registry))
        for field, value in [('ROOT', self.root), ('EVIDENCE_COMMIT', self.commit),
                             ('EVIDENCE_SHA256', self.record['evidence_sha256']),
                             ('REVIEW_SHA256', self.record['review_sha256'])]:
            context = patch.object(a, field, value)
            context.start(); self.addCleanup(context.stop)
        context = patch('leek.history_review_gate.REGISTRY_PATH', self.registry_path)
        context.start(); self.addCleanup(context.stop)
        self.resolution = require_history_review()
        em, tx = [], []
        for day in ('2020-08-20',) + a.DATES + ('2020-08-28',):
            rows = []
            for vendor in ('eastmoney', 'tencent'):
                values = {c['field']: c[vendor] for c in self.audit['mismatches'] if c['date'] == day}
                rows.append(dict(date=day, volume_lots='100',
                    **(values or dict(open='4.800', close='4.800', high='4.900', low='4.700'))))
            em.append(rows[0]); tx.append(rows[1])
        tx[0]['volume_lots'] = '999'  # not compared or substituted
        self.em, self.tx = em, tx
        self.config = json.loads((ROOT / 'research/real_history_protocol.json').read_bytes())
        self.config.update(warmup_start='2020-01-01', evaluation_start='2020-08-22', evaluation_end='2020-12-31')
        self.data_dir = self.root / 'private-input'; (self.data_dir / 'raw').mkdir(parents=True)
        em_raw = {'data': {'code': '510300', 'klines': [','.join(
            [b['date']] + [b[f] for f in a.FIELDS] + [b['volume_lots']] + ['0'] * 5) for b in em]}}
        tx_raw = {'data': {'sh510300': {'day': [[b['date']] + [b[f] for f in a.FIELDS] + [b['volume_lots']] for b in tx]}}}
        (self.data_dir / 'raw/eastmoney.json').write_bytes(canonical(em_raw))
        (self.data_dir / 'raw/tencent-2020.json').write_bytes(canonical(tx_raw))
        bars, quality = a.reconcile_sources(em, tx, self.data_dir / 'raw', 'eastmoney.json', ['tencent-2020.json'])
        self.data = dict(version='real-history.dataset.v1', synthetic=False, instrument='510300', adjustment='raw',
            bars=bars, calendar=[b['date'] for b in bars], dividends=[], metadata=dict(crosscheck=quality))
        self.data['metadata']['sources'] = []
        for name, url in (
            ('eastmoney.json', 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.510300&klt=101&fqt=0&beg=20200101&end=20201231'),
            ('tencent-2020.json', 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh510300,day,2020-01-01,2020-12-31,640,'),
        ):
            raw = (self.data_dir / 'raw' / name).read_bytes()
            self.data['metadata']['sources'].append(dict(snapshot_name=name, url=url, sha256=digest(raw), bytes=len(raw)))
        from leek.history_data import parse_dividends, DIVIDEND_URL
        raw = b'<table><tr><td>2020</td><td>2020-08-24</td><td>2020-08-25</td><td>\xe6\xaf\x8f10\xe4\xbb\xbd\xe6\xb4\xbe\xe7\x8e\xb0\xe9\x87\x911.0000\xe5\x85\x83</td><td>2020-08-26</td></tr></table>'
        (self.data_dir / 'raw/dividends.html').write_bytes(raw)
        self.data['dividends'] = parse_dividends(raw, '2020-01-01', '2020-12-31')
        self.data['metadata']['sources'].append(dict(snapshot_name='dividends.html', url=DIVIDEND_URL,
                                                    sha256=digest(raw), bytes=len(raw)))
        self.config_path = self.root / 'config.json'; self.config_path.write_bytes(canonical(self.config))
        self.data['metadata']['config_sha256'] = digest(canonical(self.config))
        self.write_data()

    def write_data(self):
        (self.data_dir / 'dataset.json').write_bytes(canonical(self.data))

    def test_exact_reviewed_case_preserves_inputs_volume_and_twenty_real_differences(self):
        before = copy.deepcopy((self.em, self.tx))
        bars, quality = a.adjudicate(self.em, self.tx, self.resolution)
        self.assertEqual(before, (self.em, self.tx))
        self.assertEqual(bars[0]['volume_lots'], '100')
        self.assertEqual(quality['differing_cells'], 20)
        self.assertEqual(quality['resolved_cells'], 20)
        self.assertEqual(quality['unresolved_cells'], 0)
        self.assertEqual(a.validate_dataset_evidence(self.data, self.data_dir, self.config), a.GRADE)
        self.assertEqual(evidence_allowed(self.data['metadata'], False, self.data, self.data_dir, self.config), a.GRADE)
        with self.assertRaises(DataBlocked): evidence_allowed(self.data['metadata'], True)

    def test_unknown_conflicts_and_changed_current_approved_quotes_block(self):
        for vendor, row, field in [('em', 0, 'open'), ('tx', 0, 'close'), ('em', 1, 'open'), ('tx', 1, 'close')]:
            em, tx = copy.deepcopy(self.em), copy.deepcopy(self.tx)
            target = em if vendor == 'em' else tx
            target[row][field] = str(Decimal(target[row][field]) + Decimal('.001'))
            with self.subTest(vendor=vendor, row=row), self.assertRaises(DataBlocked):
                a.adjudicate(em, tx, self.resolution)
        with self.assertRaises(DataBlocked): a.adjudicate(self.em[2:], self.tx[2:], self.resolution)

    def test_bad_artifact_hashes_and_untrusted_review_commit_block(self):
        for field in ('review_sha256', 'evidence_sha256', 'review_commit'):
            record = dict(self.record); record[field] = '0' * len(record[field])
            with self.subTest(field=field), self.assertRaises(DataBlocked): a.load_resolution(record)
        for name in (a.REVIEW_PATH, a.EVIDENCE_PATH, a.AUDIT_PATH):
            path = self.root / name; original = path.read_bytes(); path.write_bytes(original + b' ')
            with self.subTest(path=name), self.assertRaises(DataBlocked): a.load_resolution(self.record)
            path.write_bytes(original)

    def test_incomplete_cells_or_unproven_basis_block_even_if_rehashed(self):
        for field, value in [('cells', self.evidence['cells'][:-1]), ('cells', self.evidence['cells'][:-1] + [self.evidence['cells'][0]])]:
            evidence = dict(self.evidence); evidence[field] = value
            hashed = digest(canonical(evidence)); record = dict(self.record, evidence_sha256=hashed)
            (self.root / a.EVIDENCE_PATH).write_bytes(canonical(evidence))
            with patch.object(a, 'EVIDENCE_SHA256', hashed), self.assertRaises(DataBlocked): a.load_resolution(record)
        (self.root / a.EVIDENCE_PATH).write_bytes(canonical(self.evidence))
        review = copy.deepcopy(self.review); review['checks']['bounded_unadjusted_basis_supported'] = False
        hashed = digest(canonical(review)); record = dict(self.record, review_sha256=hashed)
        (self.root / a.REVIEW_PATH).write_bytes(canonical(review))
        with patch.object(a, 'REVIEW_SHA256', hashed), self.assertRaises(DataBlocked): a.load_resolution(record)

    def test_raw_tamper_and_missing_file_block_before_any_simulation(self):
        path = self.data_dir / 'raw/tencent-2020.json'; path.write_bytes(path.read_bytes() + b' ')
        with patch('research.run_real_history.simulate') as simulate:
            with self.assertRaises(DataBlocked): execute(self.data_dir, self.config_path, self.root / 'out', True)
            simulate.assert_not_called()
        with patch('leek.real_backtest.simulate') as simulate:
            with self.assertRaises(DataBlocked): strict_run(self.data_dir / 'dataset.json', self.config_path, self.root / 'strict-out')
            simulate.assert_not_called()
        self.assertFalse((self.root / 'out').exists())
        self.assertFalse((self.root / 'strict-out').exists())
        path.unlink()
        with self.assertRaises(DataBlocked): a.validate_dataset_evidence(self.data, self.data_dir, self.config)

    def test_normalized_price_volume_quality_and_snapshot_path_tamper_block(self):
        for mutate in (
            lambda d: d['bars'][0].update(open='4.801'),
            lambda d: d.update(dividends=[]),
            lambda d: d['dividends'][0].update(cash_per_share='0.2'),
            lambda d: d['metadata'].update(crosscheck=None),
            lambda d: d['bars'][0].update(volume_lots='999'),
            lambda d: d['metadata']['crosscheck'].update(differing_cells=0),
            lambda d: d['metadata']['sources'][0].update(url='https://example.com/fake'),
            lambda d: d['metadata']['sources'][0].update(sha256='0' * 64),
            lambda d: d['metadata']['crosscheck']['source_snapshots']['eastmoney'][0].update(name='../escape'),
            lambda d: d['metadata']['crosscheck']['source_snapshots']['tencent'].append(
                d['metadata']['crosscheck']['source_snapshots']['tencent'][0]),
        ):
            changed = copy.deepcopy(self.data); mutate(changed)
            with self.assertRaises(DataBlocked): a.validate_dataset_evidence(changed, self.data_dir, self.config)

    def test_grade_relabel_never_bypasses_private_source_verification(self):
        for quality in (dict(status='MATCH', differing_cells=0),
                        dict(status='SECOND_PRICE_SOURCE_UNAVAILABLE', differing_cells=None, reason='missing')):
            changed = copy.deepcopy(self.data); changed['metadata']['crosscheck'] = quality
            with self.assertRaises(DataBlocked): a.validate_dataset_evidence(changed, self.data_dir, self.config, True)

    def test_selected_price_cannot_be_changed_even_when_both_sources_agree(self):
        changed = copy.deepcopy(self.data); changed['bars'][1]['open'] = self.em[1]['open']
        with self.assertRaises(DataBlocked): a.validate_dataset_evidence(changed, self.data_dir, self.config)


class ProductionReviewBindingTests(unittest.TestCase):
    def test_actual_public_review_is_hash_bound_to_preceding_evidence_commit(self):
        resolution = require_history_review()
        self.assertEqual(len(resolution['cells']), 20)
        self.assertEqual(resolution['binding']['review_commit'], '94173048588fa6c1d8c4d7ff0c6c8bba32365c6e')
        self.assertEqual(digest((ROOT / a.AUDIT_PATH).read_bytes()), a.AUDIT_SHA256)

    def test_reviewed_source_decision_does_not_claim_inputs_or_backtest(self):
        from research.cli import preflight
        with tempfile.TemporaryDirectory() as empty:
            report = preflight('h002', data_dir=empty)
        expected = 'BLOCKED_RUNTIME' if sys.flags.optimize else 'BLOCKED_INPUTS'
        self.assertEqual(report['status'], expected)
        self.assertEqual(report['historical_replays_completed'], 0)
        self.assertFalse(report['automatic_promotion'])


if __name__ == '__main__':
    unittest.main()
