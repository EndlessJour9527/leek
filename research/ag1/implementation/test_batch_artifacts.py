import copy,tempfile,unittest
from pathlib import Path
from batch_artifacts import execute_batch
from registration_guard import read_registration
from run_portfolio import run_path
from contract import DataBlocked

REG=Path(__file__).resolve().parent.parent/'registration'

def fixture():
    registry,_=read_registration(REG)
    sessions=['2020-09-30','2020-10-30','2020-11-30','2020-12-31','2021-01-29','2021-02-26','2021-03-31','2021-04-30','2021-05-31','2021-06-30','2021-07-30','2021-08-31','2021-09-30','2021-10-15','2021-10-18','2021-10-29','2021-11-01','2021-11-30','2021-12-01']
    panel={s:{d:dict(open=10,high=10,low=10,close=10,status='trading_verified',upper_limit=11,lower_limit=9,limit_evidence='HAND_AUTHORED_SYNTHETIC') for d in sessions} for s in registry['universe']}
    window=dict(initial_signal='2021-10-15',initial_formation='2021-09',start='2021-10-18',end='2021-11-30')
    q={'fixture_kind':'HAND_AUTHORED_SYNTHETIC','odd_lot_exit_allowed':{s:False for s in registry['universe']}}
    return registry,sessions,panel,window,q

class BatchArtifactTests(unittest.TestCase):
    def test_all_15_synthetic_paths_reproducible_and_no_overwrite(self):
        r,s,p,w,q=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            a=execute_batch(p,s,[],r,w,q,Path(tmp)/'one',REG)
            b=execute_batch(p,s,[],r,w,q,Path(tmp)/'two',REG)
            self.assertEqual(a,b)
            self.assertEqual(len(list((Path(tmp)/'one').glob('*/terminal.json'))),15)
            with self.assertRaises(FileExistsError):execute_batch(p,s,[],r,w,q,Path(tmp)/'one',REG)
    def test_formal_historical_gate_not_enabled(self):
        r,s,p,w,q=fixture();q.pop('fixture_kind')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'blocked'
            with self.assertRaises(DataBlocked):execute_batch(p,s,[],r,w,q,out,REG)
            self.assertFalse(out.exists())
    def test_unregistered_parameter_and_cost_blocked(self):
        r,s,p,w,q=fixture();strategy=copy.deepcopy(r['strategies'][0]);strategy['top_k']=1
        with self.assertRaises(DataBlocked):run_path(p,s,[],r,strategy,r['cost_scenarios'][0],w,q)
        cost=copy.deepcopy(r['cost_scenarios'][0]);cost['commission_rate']='0'
        with self.assertRaises(DataBlocked):run_path(p,s,[],r,r['strategies'][0],cost,w,q)
if __name__=='__main__':unittest.main()
