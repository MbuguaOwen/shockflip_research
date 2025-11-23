import argparse
import os
import sys
import traceback

# Ensure repository root is on sys.path when running as a script
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.config import load_config
from core.data_loader import load_marketdata_as_bars
from core.backtest import BacktestConfig, prepare_features_for_backtest
from core.barriers import FeesConfig, RiskConfig, RiskSideConfig
from core.shockflip_detector import ShockFlipConfig
from core.event_study_core import EventStudyConfig, run_event_study


def build_backtest_config(cfg: dict) -> BacktestConfig:
    data_cfg = cfg.get("data", {}) or {}
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
    loc_cfg = sf_cfg.get("location_filter", {}) or {}
    shockflip = ShockFlipConfig(
        source=str(sf_cfg.get("source", "imbalance")),
        z_window=int(sf_cfg.get("z_window", 240)),
        z_band=float(sf_cfg.get("z_band", 2.5)),
        jump_band=float(sf_cfg.get("jump_band", 3.0)),
        persistence_bars=int(sf_cfg.get("persistence_bars", 6)),
        persistence_ratio=float(sf_cfg.get("persistence_ratio", 0.60)),
        dynamic_thresholds=sf_cfg.get("dynamic_thresholds", {"enabled": False, "percentile": 0.99}),
        location_filter={
            "donchian_window": int(loc_cfg.get("donchian_window", 120)),
            "require_extreme": bool(loc_cfg.get("require_extreme", True)),
        },
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
    parser = argparse.ArgumentParser(description="Run ShockFlip event study.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/strategies_shockflip_only.yaml",
        help="Path to YAML config.",
    )
    parser.add_argument(
        "--events_out",
        type=str,
        default="results/event_study/events.csv",
        help="Path to per-event CSV output.",
    )
    parser.add_argument(
        "--summary_out",
        type=str,
        default="results/event_study/summary.csv",
        help="Path to summary CSV output.",
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
        es_cfg = build_event_study_config(cfg)
        
        print(f"[Cfg] symbol={bt_cfg.symbol} timeframe={bt_cfg.timeframe}")
        print(f"[Cfg] tick_dir={bt_cfg.tick_dir}")

        stage = "load_data"
        bars, source = load_marketdata_as_bars(bt_cfg.tick_dir, timeframe=bt_cfg.timeframe)
        print(f"[Bars] {len(bars):,} bars (source={source})")

        stage = "prepare_features"
        # Propagate debug flag to ShockFlipConfig to emit condition columns if enabled
        try:
            setattr(bt_cfg, "_debug", bool(args.debug))
            if hasattr(bt_cfg, "shockflip"):
                setattr(bt_cfg.shockflip, "_debug", bool(args.debug))
        except Exception:
            pass
        feats = prepare_features_for_backtest(bars, bt_cfg)

        stage = "run_event_study"
        events_df, summary_df = run_event_study(bars, feats, es_cfg, progress=(not args.no_progress))

        stage = "save_outputs"
        os.makedirs(os.path.dirname(args.events_out), exist_ok=True)
        events_df.to_csv(args.events_out, index=False)
        summary_df.to_csv(args.summary_out, index=False)

        print(f"[Save] events -> {args.events_out} ({len(events_df)} rows)")
        print(f"[Save] summary -> {args.summary_out} ({len(summary_df)} rows)")
        print(summary_df)
        if events_df.empty and args.debug:
            try:
                vc = feats.get("shockflip_signal", 0)
                n_sf = int((vc != 0).sum()) if hasattr(vc, 'sum') else 0
                print(f"[Diag] Event-study starved: n_shockflip={n_sf}, bars={len(feats)}")
            except Exception:
                pass
    except Exception as exc:
        print("\n[Error] Event study failed.")
        print(f"  stage = {stage}")
        print(f"  config = {args.config}")
        print(f"  message = {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
