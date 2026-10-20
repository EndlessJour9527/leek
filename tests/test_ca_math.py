import unittest
from decimal import Decimal as D
from leek.ca_math import transformed_reference,chain_total_return
from leek.ledger import Ledger

class PriceBasisTests(unittest.TestCase):
    def test_merge_halted_stale_theoretical_tr_flat_account_rounding_separate(self):
        ratio=D('.36555');prior=D(1);mark=transformed_reference(prior,0,ratio)
        self.assertAlmostEqual(chain_total_return(100,prior,mark,0,ratio),D(100),places=20)
        x=Ledger(1000,['A']);x.fill('A','BUY',1000,1,1,0,'2024-01-01')
        x.record('A','S');x.ex('A','S',0,ratio,'ceil_whole_account')
        rounding_nav=x.nav({'A':mark})-1000
        self.assertGreater(rounding_nav,0)
        self.assertAlmostEqual(rounding_nav,(D(366)-D(1000)*ratio)*mark,places=20)
    def test_split_close_phase_not_applied_to_pre_split_quote(self):
        # The orchestration layer must supply the ratio on the first post-basis quote.
        pre=chain_total_return(100,10,10,0,1)
        post=chain_total_return(pre,10,D(10)/D('1.14539'),0,'1.14539')
        self.assertAlmostEqual(pre,D(100),places=20)
        self.assertAlmostEqual(post,D(100),places=20)
    def test_cash_ex_preserves_tr(self):
        self.assertEqual(chain_total_return(100,10,9,1,1),D(100))
        self.assertEqual(transformed_reference(10,1,1),D(9))
if __name__=='__main__':unittest.main()
