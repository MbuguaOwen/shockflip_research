import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

# Make repo root importable like in other scripts
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.config import load_config
from core.data_loader import load_marketdata_as_bars
from core.backtest import BacktestConfig, prepare_features_for_backtest
from core.barriers import FeesConfig, RiskConfig, RiskSideConfig
from core.shockflip_detector import ShockFlipConfig

CFG_PATH = "configs/strategies_shockflip_only.yaml"
TRADES_PATH = "results/backtest/trades.csv"


def build_backtest_cfg(cfg_dict):
    data_cfg = cfg_dict["data"]
    risk_cfg = cfg_dict["risk"]
    sf_cfg = cfg_dict["shock_flip"]
    fees_cfg = cfg_dict["fees"]

    return BacktestConfig(
        symbol=data_cfg["symbol"],
        tick_dir=data_cfg["tick_dir"],
        timeframe=data_cfg["timeframe"],
        slippage_bp=cfg_dict["slippage_bp"],
        fees=FeesConfig(taker_bp=fees_cfg["taker_bp"]),
        risk=RiskConfig(
            atr_window=risk_cfg["atr_window"],
            cooldown_bars=risk_cfg["cooldown_bars"],
            long=RiskSideConfig(**risk_cfg["long"]),
            short=RiskSideConfig(**risk_cfg["short"]),
        ),
        shockflip=ShockFlipConfig(
            source=sf_cfg["source"],
            z_window=sf_cfg["z_window"],
            z_band=sf_cfg["z_band"],
            jump_band=sf_cfg["jump_band"],
            persistence_bars=sf_cfg["persistence_bars"],
            persistence_ratio=sf_cfg["persistence_ratio"],
            dynamic_enabled=sf_cfg["dynamic_thresholds"]["enabled"],
            dynamic_percentile=sf_cfg["dynamic_thresholds"]["percentile"],
            donchian_window=sf_cfg["location_filter"]["donchian_window"],
            require_extreme=sf_cfg["location_filter"]["require_extreme"],
        ),
    )


def load_features():
    cfg = load_config(CFG_PATH)
    bt_cfg = build_backtest_cfg(cfg)

    bars, source = load_marketdata_as_bars(bt_cfg.tick_dir, bt_cfg.timeframe)
    feats = prepare_features_for_backtest(bars, bt_cfg)
    return feats


def plot_trade(trade_idx=0):
    trades = pd.read_csv(TRADES_PATH, parse_dates=["entry_ts", "exit_ts"])
    trade = trades.iloc[trade_idx]

    feats = load_features()

    # Use index window around entry_idx
    i0 = int(trade["entry_idx"])
    i1 = int(trade["exit_idx"])
    pad = 200  # bars around the trade
    start = max(0, i0 - pad)
    end = min(len(feats) - 1, i1 + pad)

    df = feats.iloc[start:end + 1].copy()

    # Plot price with Donchian
    ts = df["timestamp"]
    close = df["close"]

    plt.figure(figsize=(12, 6))
    plt.plot(ts, close, label="Close")
    if "donchian_high" in df.columns and "donchian_low" in df.columns:
        plt.plot(ts, df["donchian_high"], linestyle="--", label="Donchian High (120)")
        plt.plot(ts, df["donchian_low"], linestyle="--", label="Donchian Low (120)")

    # Mark entry and exit
    entry_ts = pd.to_datetime(trade["entry_ts"])
    exit_ts = pd.to_datetime(trade["exit_ts"])
    plt.axvline(entry_ts, linestyle=":", label="Entry")
    plt.axvline(exit_ts, linestyle=":", label="Exit")

    plt.legend()
    plt.title(f"Trade {trade_idx} – side={trade['side']}, result={trade['result']}")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    # Change index 0..5 to cycle through your 6 trades
    plot_trade(trade_idx=0)
