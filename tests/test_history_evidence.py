"""Evidence downgrade is explicit; conflicting prices may never pass."""
import unittest
from leek.contract import DataBlocked
from research.run_real_history import evidence_allowed

class EvidenceGradeTests(unittest.TestCase):
    def test_matching_sources(self):
        self.assertEqual(evidence_allowed({'crosscheck':{'status':'MATCH','differing_cells':0}},False),'CROSS_VENDOR_OHLC_MATCH')
    def test_missing_source_requires_explicit_permission(self):
        m={'crosscheck':{'status':'SECOND_PRICE_SOURCE_UNAVAILABLE','differing_cells':None,'reason':'RemoteDisconnected'}}
        with self.assertRaises(DataBlocked): evidence_allowed(m,False)
        self.assertEqual(evidence_allowed(m,True),'SINGLE_PRICE_VENDOR_RESEARCH_ONLY')
    def test_conflicting_prices_never_downgraded(self):
        for state in ('MATCH','SECOND_PRICE_SOURCE_UNAVAILABLE'):
            with self.assertRaises(DataBlocked):
                evidence_allowed({'crosscheck':{'status':state,'differing_cells':1,'reason':'conflict'}},True)
    def test_missing_result_not_misreported_as_zero_difference(self):
        for quality in ({},{'status':'MATCH','differing_cells':None},
                        {'status':'SECOND_PRICE_SOURCE_UNAVAILABLE','differing_cells':0,'reason':'missing'}):
            with self.assertRaises(DataBlocked): evidence_allowed({'crosscheck':quality},True)

if __name__=='__main__':unittest.main()
