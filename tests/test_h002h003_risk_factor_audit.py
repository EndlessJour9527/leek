"""Synthetic arithmetic tests; not historical-market evidence."""
import unittest

from research.h002h003_sourcev1.risk_factor_audit import audit, regress_hac, SOURCE


class RiskFactorAuditTests(unittest.TestCase):
    def test_regression_exact_line(self):
        b=[.01*(i%7-3) for i in range(200)]
        r=regress_hac([.00015+.4*v for v in b],b,20)
        self.assertAlmostEqual(r['beta'],.4)
        self.assertEqual(r['annual_arithmetic_intercept_pct'],3.78)
        self.assertEqual(r['hac_approx_95pct'],[3.78,3.78])

    def test_insufficient_history(self):
        with self.assertRaises(ValueError):
            regress_hac([0]*20,[0]*20,20)

    def test_zero_variance(self):
        with self.assertRaises(ValueError):
            regress_hac([0]*100,[.01]*100,20)

    def test_wrong_fingerprint(self):
        with self.assertRaises(ValueError):
            audit({'fingerprint':{'data_version':SOURCE,'private_dataset_sha256':'bad'},'accounts':{}})


if __name__=='__main__':
    unittest.main()
