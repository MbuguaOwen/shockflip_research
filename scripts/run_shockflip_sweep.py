import argparse
import os
import sys
from copy import deepcopy

import pandas as pd

# Ensure repo root on path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.config import load_config
from core.data_loader import load_marketdata_as_bars
from core.backtest import (
    BacktestConfig,
    prepare_features_for_backtest,
    run_backtest_from_bars,
)
from core.event_study_core import EventStudyConfig, run_event_study
from core.barriers import FeesConfig, RiskConfig, RiskSideConfig
from core.shockflip_detector import ShockFlipConfig


def build_backtest_config(cfg: dict) -> BacktestConfig:
    """Copy of scripts/run_backtest.build_backtest_config, kept local for sweeps."""
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


def build_event_study_config(cfg: dict) -> EventStudyConfig:
    es_cfg = cfg.get("event_study", {}) or {}
    horizons = es_cfg.get("horizons", {}) or {}
    long_h = horizons.get("long", [12, 18, 60])
    short_h = horizons.get("short", [6, 12])
    baseline_n_random = int(es_cfg.get("baseline_n_random", 2000))
    return EventStudyConfig(
        horizons_long=long_h,
        horizons_short=short_h,
        baseline_n_random=baseline_n_random,
    )


def main():
    parser = argparse.ArgumentParser(description="Micro-grid sweep for ShockFlip parameters.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/strategies_shockflip_only.yaml",
        help="Baseline YAML config (center of sweep).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="results/sweeps/shockflip_micro_grid.csv",
        help="Output CSV for sweep results.",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # 1) Load baseline config + build base BT/ES configs
    cfg_base = load_config(args.config)
    bt_cfg_base = build_backtest_config(cfg_base)
    es_cfg = build_event_study_config(cfg_base)

    # 2) Load bars ONCE
    print(f"[Cfg] symbol={bt_cfg_base.symbol} timeframe={bt_cfg_base.timeframe}")
    print(f"[Cfg] tick_dir={bt_cfg_base.tick_dir}")
    bars, source = load_marketdata_as_bars(bt_cfg_base.tick_dir, timeframe=bt_cfg_base.timeframe)
    print(f"[Bars] {len(bars):,} bars (source={source})")

    # 3) Define micro-grid around v1.0 baseline
    z_grid = [2.0, 2.5, 3.0]
    jump_grid = [2.0, 2.5, 3.0]
    pers_bars_grid = [3, 6, 8]

    rows = []

    for z_band in z_grid:
        for jump_band in jump_grid:
            for pers_bars in pers_bars_grid:
                cfg = deepcopy(cfg_base)
                sf_cfg = cfg.setdefault("shock_flip", {})
                sf_cfg["z_band"] = float(z_band)
                sf_cfg["jump_band"] = float(jump_band)
                sf_cfg["persistence_bars"] = int(pers_bars)
                # keep persistence_ratio from baseline; dynamic_thresholds as-is

                bt_cfg = build_backtest_config(cfg)
                # no progress / debug spam during sweeps
                try:
                    setattr(bt_cfg, "_progress", False)
                    setattr(bt_cfg, "_debug", False)
                except Exception:
                    pass

                key = f"z{z_band:.2f}_j{jump_band:.2f}_pb{pers_bars}"
                print(f"[Sweep] {key}")

                # 4) Backtest
                trades, stats = run_backtest_from_bars(bars, bt_cfg)

                # 5) Features + Event study
                feats = prepare_features_for_backtest(bars, bt_cfg)
                events_df, summary_df = run_event_study(bars, feats, es_cfg, progress=False)

                sf_counts = feats.get("shockflip_signal", pd.Series(dtype=int)).value_counts().to_dict()
                n_sf_long = int(sf_counts.get(1, 0))
                n_sf_short = int(sf_counts.get(-1, 0))

                row = {
                    "z_band": z_band,
                    "jump_band": jump_band,
                    "persistence_bars": pers_bars,
                    "persistence_ratio": float(cfg["shock_flip"].get("persistence_ratio", 0.5)),
                    "n_shockflip_long": n_sf_long,
                    "n_shockflip_short": n_sf_short,
                    "n_events": int(len(events_df)),
                    "n_trades": int(stats.get("n", 0)),
                    "win_rate": float(stats.get("win_rate", 0.0)),
                    "pf": float(stats.get("pf", 0.0)),
                }

                # Add event-study metrics for key horizons
                if not summary_df.empty:
                    for side in ("long", "short"):
                        for h in (6, 12, 18, 60):
                            mask = (summary_df["side"] == side) & (summary_df["horizon"] == h)
                            if not bool(mask.any()):
                                continue
                            m = summary_df.loc[mask].iloc[0]
                            row[f"es_n_{side}_h{h}"] = int(m["n"])
                            row[f"es_mean_{side}_h{h}"] = float(m["mean_event"])
                            row[f"es_lift_{side}_h{h}"] = float(m["lift"])

                rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"[Save] sweep -> {args.out} ({len(df)} rows)")


if __name__ == "__main__":
    main()

