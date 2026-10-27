"""Offline boundary tests only; no synthetic fixture is market evidence."""
from pathlib import Path
import tempfile
import unittest

from research.h002h003_sourcev1.run import DATASET_SHA, SOURCE_VERSION, STRATEGIES, run


class ConditionalSourceReplayTests(unittest.TestCase):
    def test_registered_input_and_account_controls_frozen(self):
        self.assertEqual(
            SOURCE_VERSION, "ML001_SSE_TENCENT_PANEL_V1")
        self.assertEqual(len(DATASET_SHA), 64)
        self.assertEqual(STRATEGIES, (
            "cash", "buy_hold", "ma120_1d", "h001_3d",
            "h002_channel_20_10", "h003_close_tr_bb20_2"))

    def test_reject_unregistered_snapshot_before_any_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private = root / "private"
            private.mkdir()
            (private / "dataset.json").write_text("{}")
            output = root / "report"
            with self.assertRaisesRegex(ValueError, "not the frozen ML001 input"):
                run(private, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
