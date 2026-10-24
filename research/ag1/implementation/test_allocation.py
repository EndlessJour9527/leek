import unittest
from decimal import Decimal as D
from allocation import capped_buy_quantity,common_scalar_allocation

class AllocationTests(unittest.TestCase):
    def test_three_caps_and_cheaper_open_no_expansion(self):
        self.assertEqual(capped_buy_quantity(1000,10000,23750,5,100),D(1000))
        self.assertEqual(capped_buy_quantity(1000,10000,23750,11,100),D(900))
        self.assertEqual(capped_buy_quantity(1000,10000,5000,10,100),D(500))
    def test_equal_demand_no_order_bias_or_remainder_reallocation(self):
        a=common_scalar_allocation({'A':200,'B':200},{'A':10,'B':10},3500,100,0,5)
        self.assertEqual(a['quantities'],{'A':D(100),'B':D(100)})
        self.assertEqual(a['cash_remaining'],D(1490))
        self.assertEqual(a['alpha_interval'],{'left':'1/2','left_closed':True,'right':'1','right_closed':False})
        b=common_scalar_allocation({'B':200,'A':200},{'A':10,'B':10},3500,100,0,5)
        self.assertEqual(a,b)
    def test_unequal_demand_reachable_vector(self):
        a=common_scalar_allocation({'A':300,'B':200},{'A':10,'B':10},3500,100,0,5)
        self.assertEqual(a['quantities'],{'A':D(200),'B':D(100)})
        self.assertEqual(a['alpha_interval']['left'],'2/3')
    def test_minimum_fee_threshold(self):
        a=common_scalar_allocation({'A':100},{'A':10},1004,100,0,5)
        self.assertEqual(a['quantities'],{'A':D(0)})
        self.assertEqual(a['total_cost'],0)
    def test_full_budget(self):
        a=common_scalar_allocation({'A':100},{'A':10},1005,100,0,5)
        self.assertEqual(a['quantities'],{'A':D(100)})
        self.assertEqual(a['alpha_interval']['right_closed'],True)
if __name__=='__main__':unittest.main()
