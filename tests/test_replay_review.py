"""Independent synthetic replay adversarial and conservation regressions."""
import copy, json, random, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from decimal import Decimal as D
from concurrent.futures import ThreadPoolExecutor
REPO = Path(__file__).resolve().parents[1]
from leek.replay import run, canonical, digest, atomic_create
from leek.contract import DataBlocked

class IndependentReplayAudit(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.n = 0
        self.c = json.loads((REPO / 'examples/fixtures/replay-config.json').read_text())
        self.d = json.loads((REPO / 'examples/fixtures/replay-bars.json').read_text())

    def execute(self, c=None, d=None, **kw):
        self.n += 1
        stem = self.root / str(self.n)
        cp = stem.with_suffix('.config')
        ip = stem.with_suffix('.input')
        cp.write_bytes(canonical(self.c if c is None else c))
        ip.write_bytes(canonical(self.d if d is None else d))
        return (run(cp, ip, stem, **kw), stem)

    def test_random_sequences_independent_ledger(self):
        import datetime
        rng = random.Random(4132)
        for case in range(20):
            d = copy.deepcopy(self.d)
            d['calendar'] = [str(datetime.date(2025, 1, 1) + datetime.timedelta(days=i * 2)) for i in range(40)]
            d['bars'] = []
            for date in d['calendar']:
                o = D(rng.randrange(10, 150))
                c = D(rng.randrange(10, 150))
                d['bars'].append(dict(date=date, open=str(o), close=str(c), high=str(max(o, c) + 1), low=str(min(o, c) - 1)))
            c = dict(self.c, initial_cash='2000', quantity='13', commission='2.5', slippage_bps='25')
            actual, _ = self.execute(c, d)
            cash = D('2000')
            qty = D(0)
            fee = D(0)
            slip = D(0)
            pending = None
            for i, b in enumerate(d['bars']):
                if pending is not None:
                    raw = D(b['open'])
                    px = raw * (D('1.0025') if pending > 0 else D('.9975'))
                    value = pending * px
                    if cash - value - D('2.5') >= 0:
                        cash -= value + D('2.5')
                        qty += pending
                        fee += D('2.5')
                        slip += abs(pending) * abs(px - raw)
                row = actual['daily'][i]
                self.assertEqual((D(row['cash']), D(row['quantity']), D(row['nav']), D(row['commission']), D(row['slippage'])), (cash, qty, cash + qty * D(b['close']), fee, slip))
                pending = None
                if i >= 1:
                    target = D(13) if D(b['close']) > D(d['bars'][i - 1]['close']) else D(0)
                    pending = target - qty if target != qty else None

    def test_causal_every_execution(self):
        base, _ = self.execute()
        for order in base['orders']:
            idx = self.d['calendar'].index(order['execute_on'])
            d = copy.deepcopy(self.d)
            for b in d['bars'][idx:]:
                b.update(high='1000', low='1', close='900')
            alt, _ = self.execute(d=d)
            same = [o for o in alt['orders'] if o['event_id'] == order['event_id']][0]
            self.assertEqual(same, order)
            self.assertEqual([s for s in alt['signals'] if s['asof'] < order['execute_on']], [s for s in base['signals'] if s['asof'] < order['execute_on']])

    def test_resume_chained_and_duplicate_events_tamper(self):
        full, fp = self.execute()
        _, p = self.execute(stop_after=1)
        for n in range(2, 7):
            _, p = self.execute(stop_after=n, resume=p / 'checkpoint.json')
        for name in ['report.json', 'checkpoint.json']:
            self.assertEqual((fp / name).read_bytes(), (p / name).read_bytes())
        bad = json.loads((p / 'checkpoint.json').read_text())
        bad['report']['orders'].append(copy.deepcopy(bad['report']['orders'][0]))
        bad['report']['processed_event_ids'].append(bad['report']['processed_event_ids'][0])
        bad['report_sha256'] = digest(canonical(bad['report']))
        bp = self.root / 'bad.json'
        bp.write_bytes(canonical(bad))
        with self.assertRaises(DataBlocked):
            self.execute(resume=bp)

    def test_actual_source_mutation_rejected(self):
        _, p = self.execute(stop_after=3)
        package = self.root / 'copy'
        shutil.copytree(REPO / 'leek', package / 'leek')
        f = package / 'leek/ledger.py'
        f.write_text(f.read_text() + '\n# independent source alteration\n')
        cmd = [sys.executable, '-m', 'leek.replay', '--config', str(p.with_suffix('.config')), '--input', str(p.with_suffix('.input')), '--output', str(self.root / 'mutated'), '--resume', str(p / 'checkpoint.json')]
        result = subprocess.run(cmd, cwd=package, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('source, config or input mismatch', result.stderr)
        self.assertFalse((self.root / 'mutated').exists())

    def test_atomic_concurrent_publication(self):
        dest = self.root / 'race.json'

        def create(i):
            try:
                atomic_create(dest, {'winner': i})
                return i
            except FileExistsError:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(create, range(48)))
        wins = [r for r in results if r is not None]
        self.assertEqual(len(wins), 1)
        self.assertEqual(json.loads(dest.read_bytes()), {'winner': wins[0]})
        self.assertEqual(list(self.root.iterdir()), [dest])

    def test_validation_before_any_publish(self):
        changes = [lambda d: d['bars'].pop(), lambda d: d['calendar'].append('2025-01-11'), lambda d: d['bars'][-1].update(close='NaN'), lambda d: d.update(corporate_actions=[{'type': 'dividend'}]), lambda d: d['bars'][0].update(split='2'), lambda d: d.update(adjustment='total_return')]
        for change in changes:
            d = copy.deepcopy(self.d)
            change(d)
            with self.assertRaises((DataBlocked, ValueError)):
                self.execute(d=d)
            self.assertFalse((self.root / str(self.n)).exists())

    def test_existing_empty_directory_and_symlink_preserved(self):
        _, p = self.execute(stop_after=3)
        empty = self.root / 'empty'
        empty.mkdir()
        link = self.root / 'alias'
        link.symlink_to(p, target_is_directory=True)
        before = (p / 'report.json').read_bytes()
        for out in [empty, link]:
            with self.assertRaises(FileExistsError):
                run(p.with_suffix('.config'), p.with_suffix('.input'), out)
        self.assertEqual((p / 'report.json').read_bytes(), before)
        self.assertEqual(list(empty.iterdir()), [])
if __name__ == '__main__':
    unittest.main(verbosity=2)
