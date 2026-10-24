"""Corruption tests use disposable copies; no archived evidence is edited."""
import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAPSULE = ROOT / 'research/ca1_20261022'
spec = importlib.util.spec_from_file_location('ca1_verifier_v2', CAPSULE / 'verify_public.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class CA1VerifierTests(unittest.TestCase):
    def test_corruption_subprocess_matrix(self):
        modes = [([], None), (['-O'], None), (['-OO'], None), ([], '1'), ([], '2')]
        for corruption in ('none', 'hash', 'nav', 'row_count', 'decision', 'manifest_omission'):
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / 'capsule'
                shutil.copytree(CAPSULE, target)
                manifest = target / 'PUBLIC_MANIFEST.json'
                if corruption in ('hash', 'manifest_omission'):
                    values = json.loads(manifest.read_text())
                    if corruption == 'hash':
                        values['ACCEPTANCE_AND_BLOCKERS.md'] = '0' * 64
                    else:
                        values.pop('ACCEPTANCE_AND_BLOCKERS.md')
                    manifest.write_text(json.dumps(values))
                elif corruption in ('nav', 'row_count'):
                    path = target / 'implementation/RESULTS/CA1_BASE.json.gz'
                    values = json.loads(gzip.decompress(path.read_bytes()))
                    if corruption == 'nav':
                        values['daily'][0]['nav'] = '99999'
                    else:
                        values['daily'].pop()
                    path.write_bytes(gzip.compress(json.dumps(values).encode(), mtime=0))
                elif corruption == 'decision':
                    path = target / 'implementation/RESULTS/DECISION.json'
                    values = json.loads(path.read_text())
                    values['decision'] = 'LIVE_APPROVED'
                    path.write_text(json.dumps(values))
                for flags, optimize in modes:
                    with self.subTest(corruption=corruption, flags=flags, optimize=optimize):
                        env = os.environ.copy()
                        env.pop('PYTHONOPTIMIZE', None)
                        if optimize:
                            env['PYTHONOPTIMIZE'] = optimize
                        result = subprocess.run([sys.executable, *flags, str(target / 'verify_public.py')],
                            env=env, capture_output=True, text=True, timeout=15)
                        self.assertEqual(result.returncode, 0 if corruption == 'none' else 1,
                                         result.stdout + result.stderr)
                        self.assertEqual('PASS:' in result.stdout, corruption == 'none')

    def report(self):
        return json.loads(gzip.decompress((CAPSULE / 'implementation/RESULTS/CA1_BASE.json.gz').read_bytes()))

    def test_account_semantic_guards(self):
        original = self.report()
        for mutation in ('nav', 'rows', 'nan', 'date', 'marks', 'round_trips', 'universe'):
            report = copy.deepcopy(original)
            if mutation == 'nav': report['daily'][0]['nav'] = '99999'
            if mutation == 'rows': report['daily'].pop()
            if mutation == 'nan': report['daily'][0]['nav'] = 'NaN'
            if mutation == 'date': report['daily'][1]['date'] = report['daily'][0]['date']
            if mutation == 'marks': report['daily'][0]['positions']['510300']['close'] = '1'
            if mutation == 'round_trips': report['round_trips'] = [{}]
            if mutation == 'universe': report['daily'][0]['positions'].pop('511010')
            with self.subTest(mutation=mutation), self.assertRaises(validator.VerificationError):
                validator.verify_account(report)

    def test_valid_derived_report(self):
        self.assertEqual(validator.verify_account(self.report()), 1140)
        self.assertFalse(validator.verify()['historical_replay'])

    def test_duplicate_json_key(self):
        with self.assertRaises(validator.VerificationError):
            validator.load_json('{"a":1,"a":2}')

    def test_manifest_path_escape(self):
        with self.assertRaises(validator.VerificationError):
            validator.safe_path(CAPSULE, '../README.md')

    def test_frozen_manifest_and_source_preserved(self):
        archive = CAPSULE / 'verification_archive/v1/PUBLIC_MANIFEST.json'
        self.assertEqual(validator.sha(archive), validator.V1_MANIFEST_SHA256)
        old = json.loads(archive.read_bytes())
        current = json.loads((CAPSULE / 'PUBLIC_MANIFEST.json').read_bytes())
        self.assertEqual({k for k in old if old[k] != current[k]}, {'verify_public.py'})


if __name__ == '__main__':
    unittest.main()
