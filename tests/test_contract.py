import unittest,tempfile,hashlib
from pathlib import Path
from leek.contract import DataBlocked,require_pool,validate_calendar,validate_raw_bar,require_observation,verify_pins

class ContractTests(unittest.TestCase):
    def test_pool_no_fallback(self):
        with self.assertRaises(DataBlocked):require_pool(['A','B'],['A'],{})
        with self.assertRaises(DataBlocked):require_pool(['A','B'],['A','B'],{'A':{}})
    def test_calendar(self):
        for cal in ([],['2024-01-01','2024-01-01'],['2024-01-02','2024-01-01'],['2024-02-30']):
            with self.assertRaises(DataBlocked):validate_calendar(cal)
    def test_no_implicit_price_fill(self):
        with self.assertRaises(DataBlocked):require_observation({},'2024-01-01','A')
        row=dict(date='2024-01-01',open=10,high=11,low=9,close=10)
        for k in ('open','high','low','close'):
            bad=dict(row);bad[k]='NaN'
            with self.assertRaises(DataBlocked):validate_raw_bar(bad)
    def test_hash_and_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'a';p.write_text('frozen')
            pin={'path':'a','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            verify_pins(temp,[pin]);p.write_text('changed')
            with self.assertRaises(DataBlocked):verify_pins(temp,[pin])
            with self.assertRaises(DataBlocked):verify_pins(temp,[dict(path='../escape',sha256='')])
if __name__=='__main__':unittest.main()
