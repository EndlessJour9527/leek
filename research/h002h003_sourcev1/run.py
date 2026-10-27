"""Read-only supplementary H002/H003 comparison on *verified* ML001 source v1.

NEVER substitutes for original H002/H003 Eastmoney+Tencent input approval.
No network acquisition, training, optimizer, broker integration or promotion.
"""
from __future__ import annotations
import argparse
from decimal import Context, ROUND_HALF_UP, localcontext
from hashlib import sha256
import json
from pathlib import Path
import platform

from research.ml001.data import load_panel
from research.run_h002 import screen as h002_screen
from research.run_h003 import screen as h003_screen
from leek.channel_signal import MODEL_ID as H002
from leek.mean_reversion_signal import MODEL_ID as H003
from leek.real_backtest import simulate, checked_config

SOURCE_VERSION = "ML001_SSE_TENCENT_PANEL_V1"
DATASET_SHA = "7e0975c04227d0168b48f552d8e16d8313f11b1ca67dda240a03ac90dfe924e2"
PREREG_SHA = "602f9bae3e244f2c61015a4afbc676b619614477"
STRATEGIES = ("cash", "buy_hold", "ma120_1d", "h001_3d", H002, H003)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def run(input_dir, output_dir):
    if not __debug__:
        raise RuntimeError("Economic engine cannot run with Python optimization")
    root = Path(__file__).resolve().parents[2]
    dest = Path(output_dir)
    if dest.exists():
        raise ValueError("refuse existing output")

    input_dir = Path(input_dir)
    if sha256((input_dir / "dataset.json").read_bytes()).hexdigest() != DATASET_SHA:
        raise ValueError("private snapshot is not the frozen ML001 input")
    panel = load_panel(input_dir)  # independently validates all original raw bodies
    if (panel.get("version") != SOURCE_VERSION or len(panel["bars"]) != 1699
            or len(panel["dividends"]) != 7):
        raise ValueError("version, calendar, or dividend inventory changed")

    config_path = root / "research/real_history_protocol.json"
    config = json.loads(config_path.read_text())
    checked_config(config)
    if (config["evaluation_start"], config["evaluation_end"]) != ("2020-01-01", "2025-12-31"):
        raise ValueError("evaluation window changed")

    paths = {}
    with localcontext(Context(prec=64, rounding=ROUND_HALF_UP)):
        for cost_name, cost in config["cost_cases"].items():
            for name in STRATEGIES:
                paths[cost_name + "__" + name] = simulate(
                    panel["bars"], panel["dividends"], config, name, cost)
    summaries = {k: v["summary"] for k, v in paths.items()}
    decisions = {"h002": h002_screen(summaries), "h003": h003_screen(summaries)}

    fingerprint = {
        "registration_commit": PREREG_SHA,
        "source_execution_commit": "5919a1e6450560166fa3cd339aeefc56faf0ba3a",
        "dataset_sha256": DATASET_SHA,
        "source_version": SOURCE_VERSION,
        "config_sha256": sha256(config_path.read_bytes()).hexdigest(),
        "engine_sha256": sha256((root / "leek/real_backtest.py").read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "data_audit": panel["audit"],
    }
    common = {
        "status": "COMPLETED_CONDITIONAL_NEW_SOURCE_DEVELOPMENT",
        "legacy_input_gate_unchanged": True,
        "sample_role": "SEEN_DEVELOPMENT",
        "automatic_promotion": False,
        "broker_orders": False,
        "fingerprint": fingerprint,
        "decisions": decisions,
    }
    fields = ("total_return_pct", "annualized_return_pct",
              "max_close_drawdown_pct", "mean_exposure_pct", "commission",
              "slippage", "dividend_income", "closed_trades", "wins", "losses",
              "profit_factor", "open_cycles", "rejected_orders", "filled_orders",
              "annual_returns_pct")
    public = dict(common, account_summaries={
        k: {f: summary[f] for f in fields} for k, summary in summaries.items()})
    private = dict(common, paths=paths)
    # Never include raw source responses or full market bars in either output.
    dest.mkdir(parents=True)
    (dest / "public_derived_summary.json").write_bytes(encode(public))
    (dest / "private_account_details.json").write_bytes(encode(private))
    print(json.dumps({"status": common["status"], "decisions": decisions,
                      "account_summaries": public["account_summaries"]},
                     sort_keys=True))
    return public


if __name__ == "__main__":
    arg = argparse.ArgumentParser()
    arg.add_argument("--input-dir", required=True)
    arg.add_argument("--output", required=True)
    args = arg.parse_args()
    run(args.input_dir, args.output)