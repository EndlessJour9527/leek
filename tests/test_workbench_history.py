"""Read-only real-history reader: public capsule, never private input fixtures."""
import json
import http.client
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from research.workbench import app as w
from research.workbench import history


class HistoricalReaderTests(unittest.TestCase):
    def test_explanations_have_exact_sources_and_independent_assurances(self):
        archive = history.load_experiment('ca1')
        report = archive['report']
        self.assertEqual(report['schema_version'], 'leek.workbench.report/1')
        self.assertEqual(report['operation']['value'], 'READ_ARCHIVE')
        axes = {a['id']: a for a in report['assurances']}
        self.assertEqual(axes['file_integrity']['state'], 'VERIFIED')
        self.assertEqual(axes['market_data']['state'], 'NOT_VERIFIED_HERE')
        self.assertEqual(axes['unseen_sample']['state'], 'NOT_VALIDATED')
        self.assertEqual(axes['execution']['state'], 'NOT_CERTIFIED')
        sources = {s['id']: s for s in archive['sources']}
        for metric in report['metrics'].values():
            self.assertTrue(metric['definition'])
            self.assertTrue(metric['basis'])
            self.assertTrue(metric['sources'])
            for ref in metric['sources']:
                source = sources[ref['source_id']]
                self.assertEqual(len(source['sha256']), 64)
                self.assertTrue(ref['selector'])
        self.assertEqual(report['metrics']['CA1_BASE.final_nav']['value'], '72415.43')
        self.assertEqual(report['metrics']['CA1_BASE.economic_fx7']['value'], '-17072.04')

    def test_report_values_resolve_to_frozen_source_fields(self):
        from decimal import Decimal
        result = history.load_experiment('ca1')
        sources = {s['id']: s for s in result['sources']}
        for metric in result['report']['metrics'].values():
            if metric['formula'] or metric['state'] == 'NOT_COMPUTED':
                continue
            ref = metric['sources'][0]
            path = history.CAPSULE / sources[ref['source_id']]['path']
            raw = path.read_bytes()
            if path.suffix == '.gz':
                import gzip
                raw = gzip.decompress(raw)
            value = json.loads(raw)
            for segment in ref['selector'].split('/')[1:]:
                value = value[int(segment)] if isinstance(value, list) else value[segment]
            if value is None:
                self.assertIsNone(metric['value'])
                self.assertEqual(metric['state'], 'UNDEFINED_NO_COMPLETE_TRADES')
            else:
                self.assertEqual(Decimal(str(value)), Decimal(metric['value']))

    def test_cost_scenarios_keep_counterfactual_separate_and_reconcile(self):
        from datetime import date
        from decimal import Decimal, ROUND_HALF_UP
        result = history.load_experiment('ca1')
        report = result['report']
        fixed = result['fixed_fill_cost_diagnostic']
        self.assertEqual(fixed['label'], 'BASE_FIXED_FILLS_DOUBLE_COST_NOT_EXECUTABLE')
        self.assertEqual(Decimal(fixed['final_nav']), Decimal('71917.160'))
        self.assertNotEqual(Decimal(fixed['final_nav']), Decimal(str(result['accounts']['CA1_DOUBLE']['final_nav'])))
        self.assertNotIn('daily', fixed)
        self.assertEqual(report['research_fee_basis']['calendar_days_inclusive'], 1717)
        days = (date(2026, 6, 30) - date(2021, 10, 18)).days + 1
        for account in ('CA1_BASE', 'CA1_DOUBLE'):
            for row in result['research_cost_scenarios'][account]:
                fee = (Decimal(1200) * days / Decimal('365.25') * row['fx_scenario']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                profit = Decimal(str(result['accounts'][account]['final_nav'])) - 50000
                self.assertEqual(fee, Decimal(row['expense']))
                self.assertEqual(profit - fee, Decimal(row['terminal_surplus']))
        adjusted = report['metrics']['CA1_BASE.after_research_fee_cagr']
        self.assertIsNone(adjusted['value'])
        self.assertEqual(adjusted['state'], 'NOT_COMPUTED')
        self.assertEqual(report['metrics']['CA1_BASE.win_rate']['state'], 'UNDEFINED_NO_COMPLETE_TRADES')

    def test_verified_archive_has_all_accounts_and_costs(self):
        result = history.load_experiment('ca1')
        self.assertFalse(result['synthetic'])
        self.assertFalse(result['verification']['historical_replay'])
        self.assertEqual(len(result['accounts']), 8)
        ca1 = result['accounts']['CA1_BASE']
        self.assertEqual(ca1['final_nav'], 72415.43)
        self.assertEqual(ca1['no_fill'], 2)
        self.assertIsNone(ca1['win_rate'])
        self.assertEqual(len(result['failed_orders']), 2)
        self.assertEqual(result['research_cost'][1]['terminal_surplus'], '-17072.04')
        encoded = json.dumps(result)
        for forbidden in ('raw_open', 'lock_close', 'daily', 'cycles', 'private_root'):
            self.assertNotIn('"' + forbidden + '"', encoded)
        self.assertTrue(all('/764ed05b3d5da94c513a70f4f0098214d38ebd9e/' in s['url'] for s in result['sources']))

    def test_unknown_id_cannot_be_a_path(self):
        for ident in ('../ca1', '/etc/passwd', '', 'h002', 'CA1'):
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                history.load_experiment(ident)

    def test_missing_or_changed_evidence_fails_closed(self):
        for mutation in ('summary', 'missing', 'manifest', 'symlink'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d:
                root = Path(d) / 'capsule'
                shutil.copytree(history.CAPSULE, root)
                summary = root / 'implementation/RESULTS/SUMMARY.json'
                if mutation == 'summary':
                    data = json.loads(summary.read_text())
                    data['CA1_BASE']['final_nav'] = 999999
                    summary.write_text(json.dumps(data))
                elif mutation == 'missing':
                    summary.unlink()
                elif mutation == 'manifest':
                    (root / 'PUBLIC_MANIFEST.json').write_text('{}')
                else:
                    external = Path(d) / 'external'
                    shutil.move(root / 'implementation/RESULTS', external)
                    (root / 'implementation/RESULTS').symlink_to(external)
                with self.assertRaises((ValueError, OSError)):
                    history.load_experiment('ca1', root=root)


class HistoryPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = w.Workbench(Path(self.tmp.name) / 'state')

    def tearDown(self):
        self.tmp.cleanup()

    def test_home_select_detail_and_read_only(self):
        with patch.object(w.cli, 'run_experiment', side_effect=AssertionError('no replay')):
            self.assertIn('/experiment?id=ca1', self.app.page())
            page = self.app.page(experiment='ca1')
        for text in ('真实历史归档', '72,415.43', '8.198%', '10.904%',
                     '本金', '最大回撤', '滑点', '沪深300', '模型未成交',
                     '2024-10-08', '2026-02-02', '尚未接入', '未定义',
                     '不是同风险', '39,487.47', '-17,072.04'):
            self.assertIn(text, page)
        self.assertNotIn('raw_open', page)
        self.assertNotIn(str(w.ROOT), page)
        self.assertEqual(list((self.app.state / 'runs').iterdir()), [])

    def test_unavailable_archive_does_not_show_stale_success(self):
        with patch.object(history, 'load_experiment', side_effect=ValueError('/private/SECRET')):
            page = self.app.page(experiment='ca1')
        self.assertIn('归档暂时无法核对', page)
        self.assertNotIn('72,415.43', page)
        self.assertNotIn('SECRET', page)
        self.assertIn('运行合成示例', page)

    def test_overview_exposes_cost_risk_and_next_steps_before_details(self):
        from html.parser import HTMLParser
        class VisibleSummary(HTMLParser):
            def __init__(self):
                super().__init__(); self.depth = 0; self.summary = 0; self.text = []
            def handle_starttag(self, tag, attrs):
                if tag == 'details': self.depth += 1
                if tag == 'summary': self.summary += 1
            def handle_endtag(self, tag):
                if tag == 'details': self.depth -= 1
                if tag == 'summary': self.summary -= 1
            def handle_data(self, data):
                if not self.depth or self.summary: self.text.append(data)
        page = self.app.page(experiment='ca1')
        parser = VisibleSummary(); parser.feed(page)
        visible = ''.join(parser.text)
        for value in ('22,415.43', '39,487.47', '-17,072.04', '10.904%',
                      '71,917.16', '不可执行', '不是复投年化', '下一步',
                      '市场数据真实性', '未见样本', '真实成交认证'):
            self.assertIn(value, visible)
        self.assertLess(page.index('id="experiment-overview"'), page.index('id="history-data"'))
        self.assertLess(page.index('id="experiments"'), page.index('id="layers"'))
        report = history.load_experiment('ca1')['report']
        for key in ('CA1_BASE.final_nav', 'CA1_BASE.economic_fx7', 'CA1_BASE.mdd'):
            self.assertIn('metric-' + key, page)
            self.assertIn(report['metrics'][key]['definition'], page)

    def test_metric_explanation_is_shared_and_html_escaped(self):
        result = history.load_experiment('ca1')
        result['report']['metrics']['CA1_BASE.profit']['definition'] = '<script>shared-marker</script>'
        with patch.object(history, 'load_experiment', return_value=result):
            page = self.app.page(experiment='ca1')
        self.assertIn('&lt;script&gt;shared-marker&lt;/script&gt;', page)
        self.assertNotIn('<script>shared-marker</script>', page)

    def test_http_history_export_and_rejections(self):
        with w.Server(self.app) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def get(path):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    conn.request('GET', path)
                    response = conn.getresponse()
                    return response.status, dict(response.getheaders()), response.read().decode()
                finally:
                    conn.close()

            try:
                self.assertIn('真实历史归档', get('/experiment?id=ca1')[2])
                code, headers, body = get('/experiment-export?id=ca1')
                self.assertEqual(code, 200)
                self.assertIn('leek-ca1-public-archive.json', headers['Content-Disposition'])
                data = json.loads(body)
                self.assertIs(data['synthetic'], False)
                self.assertFalse(data['verification']['historical_replay'])
                self.assertNotIn('raw_open', body)
                for suffix in ('', '?id=../secret', '?id=ca1&id=ca1', '?id=ca1&path=secret'):
                    self.assertEqual(get('/experiment' + suffix)[0], 400)
                with patch.object(history, 'load_experiment', side_effect=ValueError('SECRET')):
                    unavailable = get('/experiment-export?id=ca1')
                self.assertEqual(unavailable[0], 400)
                self.assertNotIn('SECRET', unavailable[2])
                self.assertNotIn('Content-Disposition', unavailable[1])
                self.assertEqual(list((self.app.state / 'runs').iterdir()), [])
            finally:
                server.shutdown()
                thread.join()


if __name__ == '__main__':
    unittest.main()
