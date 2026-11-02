import hashlib
from pathlib import Path
import tempfile
import unittest
from research.ca1_execution_coverage.check import availability, coverage, verify_pins

class ExecutionCoverageTests(unittest.TestCase):
    def order(self, identity='synthetic-a'):
        return dict(order_id=identity, symbol='SYNTHETIC', signal='2024-01-02', execute='2024-01-03', status='FILL')
    def test_same_security_day_retained(self):
        rows=coverage([self.order(),self.order('synthetic-b')],['synthetic-a','synthetic-b'])
        self.assertEqual(len(rows),2)
        self.assertTrue(all(not r['execution_certified'] and r['opening_capacity_proof']=='UNKNOWN' for r in rows))
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): coverage([self.order(),self.order()],['synthetic-a'])
    def test_missing_rejected(self):
        with self.assertRaises(ValueError): coverage([self.order()],['synthetic-a','synthetic-b'])
    def test_rejected_and_no_order_separate(self):
        a,b=self.order(),self.order('synthetic-b');a['status']='NO_FILL';b['status']='NO_ORDER'
        self.assertEqual([r['status'] for r in coverage([a,b],['synthetic-a','synthetic-b'])],['NO_FILL','NO_ORDER'])
    def test_labels_cannot_promote(self):
        a=self.order();a['execution_certified']=True
        with self.assertRaises(ValueError): coverage([a],['synthetic-a'])
    def test_bad_dates(self):
        a=self.order();a['signal']=a['execute']
        with self.assertRaises(ValueError): coverage([a],['synthetic-a'])
    def test_boolean_status(self):
        a=self.order();a['status']=False
        with self.assertRaises(ValueError): coverage([a],['synthetic-a'])
    def test_publication_boundaries(self):
        for p,e in [('2024-01-01','BEFORE_SIGNAL_DATE_ONLY_EOD_CONVENTION'),('2024-01-02','SAME_SIGNAL_DAY_CLOSE_TIME_UNCERTAIN'),('2024-01-03','EXECUTION_DAY_EOD_NOT_KNOWN_AT_OPEN'),('2024-01-04','FUTURE_TO_ORDER_RETROSPECTIVE_ONLY')]:
            self.assertEqual(availability(p,'2024-01-02','2024-01-03'),e)
    def test_between_signal_execution(self):
        self.assertEqual(availability('2024-01-03','2024-01-02','2024-01-04'),'AFTER_SIGNAL_BEFORE_EXECUTION_DATE')
    def test_empty_pins_rejected(self):
        with self.assertRaises(ValueError): verify_pins('.',{},{})
    def test_pin_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'synthetic';p.write_bytes(b'synthetic');pins={'synthetic':hashlib.sha256(b'synthetic').hexdigest()}
            verify_pins(d,pins,pins)
            with self.assertRaises(ValueError): verify_pins(d,{},pins)
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError): verify_pins(d,pins,pins)
    def test_parent_traversal_rejected(self):
        pins={'../private':'0'*64}
        with self.assertRaises(ValueError): verify_pins('.',pins,pins)

if __name__=='__main__':unittest.main()
