"""Dividend-aware research tests. Synthetic fixtures are not market evidence."""
import copy
import csv
from datetime import date, timedelta
from io import StringIO
import unittest

from leek.dividend_proxy import _validate_events, compare, simulate
from leek.price_proxy import read_csv, git_blob_sha, ProxyBlocked
from leek.ledger import Ledger


def fixture():
    days=[]
    dt=date(2024,1,2)
    while len(days)<150:
        if dt.weekday()<5:
            days.append(dt.isoformat())
        dt+=timedelta(days=1)
    close=[4.0]*120+[4.2]*3+[4.077]*27
    output=StringIO()
    writer=csv.writer(output)
    writer.writerow(["日期","收盘","开盘","高","低"])
    for d,p in reversed(list(zip(days,close))):
        writer.writerow([d,str(p),str(p),str(p+0.02),str(p-0.02)])
    raw=output.getvalue().encode()
    src=dict(repository="synthetic/test",path="synthetic.csv",
             commit="a"*40,blob_sha=git_blob_sha(raw),
             first=days[0],last=days[-1],count=len(days))
    event=dict(
        id="510300:"+days[123],published_on=days[119],
        record_date=days[122],ex_date=days[123],pay_date=days[128],
        cash_per_share="0.123",
        source_url="https://example.com/announcement",
        source_grade="synthetic",
    )
    evidence=dict(version="provisional-dividend.v1",
                  symbol="510300",coverage="UNVERIFIED_SECONDARY_CROSSCHECK",
                  events=[event])
    return raw,src,evidence,days


class TestDividendProxy(unittest.TestCase):
    def test_provisional_report_is_always_blocked_from_promotion(self):
        raw,src,evidence,_=fixture()
        report=compare(raw,src,evidence)
        self.assertEqual(report["status"],"UNVALIDATED_CA_PROXY")
        self.assertFalse(report["gates"]["corporate_actions_complete"])
        self.assertFalse(report["gates"]["eligible_for_automatic_promotion"])
        self.assertEqual(len(report["events_used"]),1)
        self.assertIsNone(report["comparison"]["h001_3d"]["closed_win_rate_pct"])

    def test_cash_distribution_is_earned_by_record_date_holder(self):
        raw,src,evidence,_=fixture()
        report=compare(raw,src,evidence)
        bh=report["comparison"]["buy_hold_20pct"]
        self.assertGreater(bh["dividends_earned_cny"],0)
        self.assertEqual(bh["dividend_receivable_cny"],0)
        self.assertAlmostEqual(bh["dividends_earned_cny"],
                               bh["open_qty"]*0.123,places=2)

    def test_ex_price_drop_neutralized_for_tr_signal(self):
        raw,src,evidence,_=fixture()
        bars=read_csv(raw)
        events=_validate_events(evidence,bars)
        a=simulate(bars,events,confirmation=3)
        self.assertGreaterEqual(a["dividends_earned_cny"],0)
        self.assertGreater(a["terminal_nav_cny"],0)
        self.assertIsNone(a["closed_win_rate_pct"])

    def test_calendar_coverage_missing_paydate_hard_fails(self):
        raw,src,evidence,days=fixture()
        evidence["events"][0]["pay_date"]="2029-01-02"
        with self.assertRaises(ProxyBlocked):compare(raw,src,evidence)

    def test_publication_after_record_fails(self):
        raw,src,evidence,_=fixture()
        evidence["events"][0]["published_on"]=evidence["events"][0]["ex_date"]
        with self.assertRaises(ProxyBlocked):compare(raw,src,evidence)

    def test_zero_and_nonfinite_distribution_fails(self):
        for val in ("0","-0.1","NaN","Infinity","100"):
            with self.subTest(val=val):
                raw,src,evidence,_=fixture()
                evidence["events"][0]["cash_per_share"]=val
                with self.assertRaises(ProxyBlocked):compare(raw,src,evidence)

    def test_duplicate_ex_date_and_event_id_fails(self):
        raw,src,evidence,_=fixture()
        evidence["events"].append(copy.deepcopy(evidence["events"][0]))
        with self.assertRaises(ProxyBlocked):compare(raw,src,evidence)

    def test_feed_completeness_never_inferred_from_records(self):
        raw,src,evidence,_=fixture()
        evidence["coverage"]="COMPLETE"
        with self.assertRaises(ProxyBlocked):compare(raw,src,evidence)

    def test_broken_market_file_fails(self):
        raw,src,evidence,_=fixture()
        with self.assertRaises(ProxyBlocked):
            compare(raw.replace(b"4.077",b"4.0771",1),src,evidence)

    def test_repeatable(self):
        raw,src,evidence,_=fixture()
        self.assertEqual(compare(raw,src,evidence),compare(raw,src,evidence))

    def test_payments_cannot_spend_before_ex(self):
        ledger=Ledger("1000",["510300"])
        ledger.fill("510300","BUY","100","4","4","5","2024-01-02")
        ledger.record("510300","event")
        with self.assertRaises(ValueError):
            ledger.pay("510300","event")
        ledger.ex("510300","event","0.123","1","exact")
        self.assertEqual(str(ledger.receivables[("510300","event")]),"12.300")
        self.assertEqual(str(ledger.cash),"595")
        ledger.pay("510300","event")
        self.assertEqual(str(ledger.cash),"607.300")
        with self.assertRaises(ValueError):ledger.pay("510300","event")


if __name__=="__main__":
    unittest.main()
