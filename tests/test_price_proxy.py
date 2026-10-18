"""Synthetic tests verify arithmetic/guardrails, not strategy profitability."""
import csv
from datetime import date, timedelta
import hashlib
import unittest
from io import StringIO

from leek.price_proxy import read_csv, run_strategy, run_diagnostic, git_blob_sha, ProxyBlocked


def sample(prices, variant="old"):
    dates = []
    day = date(2020, 1, 2)
    while len(dates) < len(prices):
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += timedelta(days=1)
    buf = StringIO()
    cols = ["日期", "收盘", "开盘", "高", "低"] if variant == "old" else [
        "日期", "收市", "開市", "高", "低"]
    writer = csv.writer(buf)
    writer.writerow(cols)
    for d, p in reversed(list(zip(dates, prices))):
        writer.writerow([d, str(p), str(p), str(p + 1), str(p - 1)])
    return buf.getvalue().encode(), dates


class ProxyTests(unittest.TestCase):
    def test_standard_and_hk_columns(self):
        for v in ("old", "hk"):
            raw, dates = sample([100] * 123, "old" if v == "old" else "new")
            bars = read_csv(raw)
            self.assertEqual((bars[0].day, bars[-1].day), (dates[0], dates[-1]))
            self.assertEqual(bars[0].close, 100)

    def test_frozen_source_rejects_mutation(self):
        raw, dates = sample([100] * 123)
        manifest = dict(repository="test/repo", path="test.csv", commit="deadbeef",
                        blob_sha=git_blob_sha(raw), count=123,
                        first=dates[0], last=dates[-1])
        report = run_diagnostic(raw, manifest)
        self.assertEqual(report["status"], "UNVALIDATED_PRICE_PROXY")
        with self.assertRaises(ProxyBlocked):
            run_diagnostic(raw + b"\n", manifest)

    def test_signal_requires_next_open(self):
        bars = read_csv(sample([100] * 120 + [110] * 3)[0])
        baseline = run_strategy(bars, 1)
        challenger = run_strategy(bars, 3)
        self.assertEqual(baseline["fill_events"], 1)
        self.assertEqual(challenger["fill_events"], 0)
        self.assertEqual(challenger["open_position_qty"], 0)

    def test_h001_chops_less_in_synthetic_whipsaw(self):
        prices = [100] * 120 + [110, 90] * 20
        bars = read_csv(sample(prices)[0])
        fast = run_strategy(bars, 1)
        confirm = run_strategy(bars, 3)
        self.assertGreater(fast["fill_events"], confirm["fill_events"])

    def test_reproducible(self):
        bars = read_csv(sample([100] * 120 + [110] * 10 + [90] * 5)[0])
        self.assertEqual(run_strategy(bars, 3), run_strategy(bars, 3))

    def test_duplicate_session_fails(self):
        raw, _ = sample([100] * 124)
        lines = raw.decode().splitlines()
        lines[-1] = lines[-2]
        with self.assertRaises(ProxyBlocked):
            read_csv(("\n".join(lines) + "\n").encode())

    def test_invalid_ohlc_fails(self):
        raw, _ = sample([100] * 123)
        bad = raw.decode().replace(",101,99", ",90,99", 1)
        with self.assertRaises(ProxyBlocked):
            read_csv(bad.encode())

    def test_warmup_fails(self):
        with self.assertRaises(ProxyBlocked):
            read_csv(sample([100] * 122)[0])

    def test_state_matches_frozen_h001_rule(self):
        """Only on artificial fully qualified rows, never real CSVs."""
        from leek.ma_confirmation import evaluate_ma_confirmation
        prices = [100] * 120 + [110] * 3
        raw, dates = sample(prices)
        for confirm in (1, 3):
            x = evaluate_ma_confirmation(
                [{"session": d, "level": str(p), "available_at": d + "T15:10:00+08:00"}
                 for d, p in zip(dates, prices)],
                decision_time=dates[-1] + "T16:00:00+08:00", calendar_sessions=dates,
                history_qualified=True, corporate_actions_qualified=True,
                confirmation=confirm,
            )
            self.assertEqual(x.exposure_state, "ON")
        self.assertEqual(run_strategy(read_csv(raw), 3)["open_position_qty"], 0)


if __name__ == "__main__":
    unittest.main()
