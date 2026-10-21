import json,tempfile,unittest
from pathlib import Path
from contract import DataBlocked
from release_gate import VerifiedRelease
from test_batch_artifacts import fixture
from run_portfolio import run_path

class ReleaseGateTests(unittest.TestCase):
    def test_boolean_flags_cannot_release_history(self):
        r,s,p,w,q=fixture();q.pop('fixture_kind');q.update(data_gate_passed=True,independent_engine_audit_passed=True,historical_run_authorized=True)
        with self.assertRaises(DataBlocked):run_path(p,s,[],r,r['strategies'][0],r['cost_scenarios'][0],w,q)
    def test_expected_approval_hash_must_match(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'release.json';path.write_text('{}')
            with self.assertRaises(DataBlocked):VerifiedRelease(path,'0'*64)
if __name__=='__main__':unittest.main()
