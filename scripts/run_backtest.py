import argparse
import os
import sys
import traceback

# Ensure repository root is on sys.path when running as a script
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd

from core.config import load_config
from core.data_loader import load_marketdata_as_bars
from core.backtest import BacktestConfig, run_backtest_from_bars
from core.barriers import FeesConfig, RiskConfig, RiskSideConfig
from core.shockflip_detector import ShockFlipConfig


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

    # Attach internal research knobs (H1/H2/BE) as optional attrs
    try:
        filters_cfg = cfg.get("filters", {}) or {}
        h1_cfg = filters_cfg.get("prior_flow_sign", {}) or {}
        h2_cfg = filters_cfg.get("price_flow_div", {}) or {}

        # H1 – already used today (keep behaviour)
        if h1_cfg.get("enabled", False):
            try:
                bt_cfg._h1_prior_flow_required_sign = int(h1_cfg.get("required_sign", -1))
            except Exception:
                bt_cfg._h1_prior_flow_required_sign = -1

        # H2 – optional divergence dead-zone
        if h2_cfg.get("enabled", False):
            try:
                bt_cfg._h2_div_dead_zone_low = float(h2_cfg.get("dead_zone_low"))
                bt_cfg._h2_div_dead_zone_high = float(h2_cfg.get("dead_zone_high"))
            except Exception:
                pass

        mfe_cfg = risk_cfg.get("mfe_breakeven", {}) or {}
        if mfe_cfg.get("enabled", False):
            try:
                be_threshold_r = float(mfe_cfg.get("threshold_r", 1.0))
                if be_threshold_r > 0:
                    bt_cfg._mfe_breakeven_r = be_threshold_r
            except Exception:
                pass
    except Exception:
        pass

    return bt_cfg


def main():
    parser = argparse.ArgumentParser(description="Run ShockFlip-only backtest.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/strategies_shockflip_only.yaml",
        help="Path to YAML config.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="results/backtest/trades.csv",
        help="Path to output trades CSV.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar output.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug diagnostics and feature stats.",
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
            # Also propagate to the ShockFlipConfig for internal instrumentation
            if hasattr(bt_cfg, "shockflip"):
                setattr(bt_cfg.shockflip, "_debug", bool(args.debug))
            # H1 gate from config filters
            h1 = (cfg.get("filters", {}) or {}).get("prior_flow_sign", {}) or {}
            if bool(h1.get("enabled", False)):
                setattr(bt_cfg, "_h1_prior_flow_required_sign", int(h1.get("required_sign", -1)))
        except Exception:
            pass

        print(f"[Cfg] symbol={bt_cfg.symbol} timeframe={bt_cfg.timeframe}")
        print(f"[Cfg] tick_dir={bt_cfg.tick_dir}")

        stage = "load_data"
        bars, source = load_marketdata_as_bars(bt_cfg.tick_dir, timeframe=bt_cfg.timeframe)
        print(f"[Bars] {len(bars):,} bars (source={source})")

        stage = "run_backtest"
        trades, stats = run_backtest_from_bars(bars, bt_cfg)

        stage = "save_trades"
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        trades.to_csv(args.out, index=False)
        print(f"[Save] trades -> {args.out} ({len(trades)} rows)")

        print(f"[Stats] n={int(stats.get('n', 0))} win={float(stats.get('win_rate', 0.0)):.3f} PF={float(stats.get('pf', 0.0)):.3f}")
        # Optional quick diagnostics when no trades
        if int(stats.get('n', 0)) == 0 and args.debug:
            try:
                # Recompute feats to inspect quickly
                feats = __import__('core.backtest', fromlist=['prepare_features_for_backtest']).prepare_features_for_backtest(bars, bt_cfg)
                n_sf = int((feats.get('shockflip_signal', 0) != 0).sum()) if 'shockflip_signal' in feats.columns else 0
                n_atr = int((feats.get('atr', 0) > 0).sum()) if 'atr' in feats.columns else 0
                print(f"[Diag] n_shockflip={n_sf}, bars_with_atr={n_atr}/{len(feats)}")
            except Exception:
                pass
    except Exception as exc:
        print("\n[Error] Backtest failed.")
        print(f"  stage = {stage}")
        print(f"  config = {args.config}")
        print(f"  message = {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
