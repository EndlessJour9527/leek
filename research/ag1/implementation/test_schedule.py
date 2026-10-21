import unittest
from schedule import build_schedule,month_ends_from_calendar
from contract import DataBlocked

class ScheduleTests(unittest.TestCase):
    def test_initial_exception_month_end_next_exchange_day(self):
        days=['2024-01-15','2024-01-16','2024-01-31','2024-02-02','2024-02-29','2024-03-01']
        strategy=dict(kind='cross_sectional_total_return_momentum',formation_month_lag_start=12,formation_month_lag_end=1,top_k=2,selected_weight='.475')
        plan,ends=build_schedule(days,'2024-01-15','2023-12','2024-01-16','2024-02-29',strategy)
        self.assertEqual(list(plan),['2024-01-15','2024-01-31','2024-02-29'])
        self.assertEqual(plan['2024-01-31']['next_session'],'2024-02-02')
        self.assertIsNone(plan['2024-02-29']['next_session'])
        self.assertEqual(plan['2024-01-15']['decision']['formation_month'],'2023-12')
    def test_truncated_last_month_not_month_end(self):
        self.assertEqual(month_ends_from_calendar(['2024-01-31','2024-02-01','2024-02-15']),{'2024-01':'2024-01-31'})
    def test_buy_hold_only_initial_no_retry(self):
        days=['2024-01-15','2024-01-16','2024-01-31','2024-02-02']
        plan,_=build_schedule(days,'2024-01-15','2023-12','2024-01-16','2024-02-02',dict(kind='buy_hold_no_dividend_reinvestment',symbol='A',initial_weight='.95'))
        self.assertEqual(list(plan),['2024-01-15'])
    def test_no_nonadjacent_initial(self):
        with self.assertRaises(DataBlocked):build_schedule(['2024-01-01','2024-01-02','2024-01-03'],'2024-01-01','2023-12','2024-01-03','2024-01-03',{'kind':'cash'})
if __name__=='__main__':unittest.main()
