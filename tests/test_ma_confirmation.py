"""Synthetic H001 unit tests, NOT historical profitability evidence."""
import unittest
from datetime import date, timedelta
from leek.ma_confirmation import evaluate_ma_confirmation, TrendDataBlocked

def make(levels):
    d = date(2024, 1, 2)
    days = []
    while len(days) < len(levels):
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    rows = [{"session": x, "level": str(y), "available_at": x + "T15:10:00+08:00"} for x,y in zip(days,levels)]
    return rows,days

def run(levels, confirmation=3, **kw):
    rows,days=make(levels)
    return evaluate_ma_confirmation(rows,decision_time=days[-1]+"T16:00:00+08:00",
        calendar_sessions=days,history_qualified=True,corporate_actions_qualified=True,
        confirmation=confirmation,**kw)

class TestH001(unittest.TestCase):
    def test_3_day_enter(self):
        self.assertEqual(run([100]*120+[110,110]).exposure_state,"OFF")
        self.assertEqual(run([100]*120+[110]*3).exposure_state,"ON")
        self.assertEqual(run([100]*120+[110],confirmation=1).exposure_state,"ON")
    def test_3_day_exit(self):
        xs=[100]*120+[120]*10+[80]*2
        self.assertEqual(run(xs).exposure_state,"ON")
        self.assertEqual(run(xs+[80]).exposure_state,"OFF")
    def test_interrupt(self):
        xs=[100]*120+[110,110,90,110,110]
        self.assertEqual(run(xs).exposure_state,"OFF")
        self.assertEqual(run(xs+[110]).exposure_state,"ON")
    def test_future_unavailable(self):
        xs=[100]*120+[110]*3
        rows,days=make(xs+[10]*30)
        with self.assertRaises(TrendDataBlocked):
            evaluate_ma_confirmation(rows,decision_time=days[len(xs)-1]+"T16:00:00+08:00",
               calendar_sessions=days,history_qualified=True,corporate_actions_qualified=True)
    def test_insufficient_history(self):
        with self.assertRaises(TrendDataBlocked):run([100]*119)
    def test_qualification_required(self):
        rows,days=make([100]*120)
        for h,c in [(False,True),(True,False)]:
            with self.assertRaises(TrendDataBlocked):
                evaluate_ma_confirmation(rows,decision_time=days[-1]+"T16:00:00+08:00",
                    calendar_sessions=days,history_qualified=h,corporate_actions_qualified=c)
    def test_calendar_gap(self):
        rows,days=make([100]*120)
        with self.assertRaises(TrendDataBlocked):
            evaluate_ma_confirmation(rows,decision_time=days[-1]+"T16:00:00+08:00",
                calendar_sessions=days[:-1],history_qualified=True,corporate_actions_qualified=True)
    def test_lookahead_timestamp(self):
        rows,days=make([100]*120)
        with self.assertRaises(TrendDataBlocked):
            evaluate_ma_confirmation(rows,decision_time=days[-1]+"T15:05:00+08:00",
                calendar_sessions=days,history_qualified=True,corporate_actions_qualified=True)
    def test_digest_is_deterministic(self):
        x=[100]*120+[110]*3
        self.assertEqual(run(x).input_sha256,run(x).input_sha256)
        self.assertNotEqual(run(x).input_sha256,run(x[:-1]+[111]).input_sha256)
    def test_undetermined_not_an_order(self):
        result=run([100]*120+[110]*3)
        self.assertFalse(hasattr(result,"quantity"))
        self.assertFalse(hasattr(result,"target_weight"))
    def test_invalid_confirmation(self):
        for n in (0,21,True):
            with self.assertRaises(TrendDataBlocked):run([100]*120,confirmation=n)
    def test_nonfinite(self):
        for value in ("NaN","Infinity","0","-1","oops"):
            with self.assertRaises(TrendDataBlocked):run([100]*119+[value])
if __name__=="__main__":
    unittest.main()
