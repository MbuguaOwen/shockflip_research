import argparse
import json
import os
import sys
import traceback

# Ensure repository root is on sys.path when running as a script
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.config import load_config
from core.data_loader import load_marketdata_as_bars
from core.backtest import BacktestConfig
from core.barriers import FeesConfig, RiskConfig, RiskSideConfig
from core.shockflip_detector import ShockFlipConfig
from core.parity import run_parity, parity_report_to_dict


def build_backtest_config(cfg: dict) -> BacktestConfig:
    data_cfg = cfg["data"]
    symbol = data_cfg.get("symbol", "BTCUSDT")
    tick_dir = data_cfg.get("tick_dir", "data/ticks/BTCUSDT")
    timeframe = data_cfg.get("timeframe", "1min")

    fees_cfg = cfg.get("fees", {}) or {}
    fees = FeesConfig(taker_bp=float(fees_cfg.get("taker_bp", 1.0)))

    slippage_bp = float(cfg.get("slippage_bp", 0.5))

    risk_cfg = cfg.get("risk", {}) or {}
    atr_window = int(risk_cfg.get("atr_window", 60))
    cooldown_bars = int(risk_cfg.get("cooldown_bars", 10))
    long_cfg = risk_cfg.get("long", {}) or {}
    short_cfg = risk_cfg.get("short", {}) or {}

    risk = RiskConfig(
        atr_window=atr_window,
        cooldown_bars=cooldown_bars,
        long=RiskSideConfig(
            tp_mult=float(long_cfg.get("tp_mult", 27.5)),
            sl_mult=float(long_cfg.get("sl_mult", 9.0)),
        ),
        short=RiskSideConfig(
            tp_mult=float(short_cfg.get("tp_mult", 15.0)),
            sl_mult=float(short_cfg.get("sl_mult", 6.5)),
        ),
    )

    sf_cfg = cfg.get("shock_flip", {}) or {}
    shockflip = ShockFlipConfig(
        source=str(sf_cfg.get("source", "imbalance")),
        z_window=int(sf_cfg.get("z_window", 240)),
        z_band=float(sf_cfg.get("z_band", 2.5)),
        jump_band=float(sf_cfg.get("jump_band", 3.0)),
        persistence_bars=int(sf_cfg.get("persistence_bars", 6)),
        persistence_ratio=float(sf_cfg.get("persistence_ratio", 0.60)),
        dynamic_enabled=bool(sf_cfg.get("dynamic_thresholds", {}).get("enabled", True)),
        dynamic_percentile=float(sf_cfg.get("dynamic_thresholds", {}).get("percentile", 0.99)),
        donchian_window=int(sf_cfg.get("location_filter", {}).get("donchian_window", 120)),
        require_extreme=bool(sf_cfg.get("location_filter", {}).get("require_extreme", True)),
    )

    bt_cfg = BacktestConfig(
        symbol=symbol,
        tick_dir=tick_dir,
        timeframe=timeframe,
        fees=fees,
        slippage_bp=slippage_bp,
        risk=risk,
        shockflip=shockflip,
    )
    return bt_cfg


def main():
    parser = argparse.ArgumentParser(description="Run backtest vs live-style parity replay.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/strategies_shockflip_only.yaml",
        help="Path to YAML config.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="results/parity/parity_report.json",
        help="Path to parity report JSON.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar output.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug diagnostics.",
    )
    args = parser.parse_args()
    
    stage = "init"
    try:
        stage = "load_config"
        cfg = load_config(args.config)
        bt_cfg = build_backtest_config(cfg)
        try:
            setattr(bt_cfg, "_progress", not args.no_progress)
            setattr(bt_cfg, "_debug", bool(args.debug))
            if hasattr(bt_cfg, "shockflip"):
                setattr(bt_cfg.shockflip, "_debug", bool(args.debug))
        except Exception:
            pass

        print(f"[Cfg] symbol={bt_cfg.symbol} timeframe={bt_cfg.timeframe}")
        print(f"[Cfg] tick_dir={bt_cfg.tick_dir}")

        stage = "load_data"
        bars, source = load_marketdata_as_bars(bt_cfg.tick_dir, timeframe=bt_cfg.timeframe)
        print(f"[Bars] {len(bars):,} bars (source={source})")

        stage = "run_parity"
        report, research_trades, live_trades = run_parity(bars, bt_cfg, progress=(not args.no_progress))

        stage = "save_output"
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(parity_report_to_dict(report), f, indent=2)

        print("[Parity]", parity_report_to_dict(report))
    except Exception as exc:
        print("\n[Error] Parity replay failed.")
        print(f"  stage = {stage}")
        print(f"  config = {args.config}")
        print(f"  message = {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
