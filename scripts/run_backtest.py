#!/usr/bin/env python3
"""
ShockFlip Backtest Runner (Stream-Safe & Robust)
- Loads ticks via streaming (memory safe)
- Resamples to 1-min bars
- Runs Backtest with Diamond Filters AND Management
- Auto-detects FeesConfig structure
"""
import os
import sys
import argparse
import pandas as pd

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.config import load_config
from core.data_loader import stream_ticks_from_dir, resample_ticks_to_bars
from core.backtest import run_backtest_from_bars, BacktestConfig, FiltersConfig
from core.barriers import FeesConfig, RiskConfig, RiskSideConfig
from core.shockflip_detector import ShockFlipConfig

def load_full_history_as_bars(tick_dir, timeframe='1min'):
    print(f"[Loader] Streaming ticks from {tick_dir}...")
    all_bars = []
    
    for tick_chunk in stream_ticks_from_dir(tick_dir, chunk_days=20):
        if tick_chunk.empty: continue
        chunk_bars = resample_ticks_to_bars(tick_chunk, timeframe=timeframe)
        all_bars.append(chunk_bars)
        sys.stdout.write(".")
        sys.stdout.flush()
    
    print("\n[Loader] Combining history...")
    full_df = pd.concat(all_bars).sort_values("timestamp").drop_duplicates(subset="timestamp").reset_index(drop=True)
    return full_df

def build_config(yaml_path):
    raw = load_config(yaml_path)

    # 1. Data section (symbol / tick_dir / timeframe)
    data_cfg = raw.get('data', {}) or {}
    symbol = data_cfg.get('symbol', 'BTCUSDT')
    tick_dir = data_cfg.get('tick_dir', 'data/ticks/BTCUSDT')
    timeframe = data_cfg.get('timeframe', '1min')

    # 2. Fees
    fees_cfg = raw.get('fees', {}) or {}
    fees = FeesConfig(taker_bp=float(fees_cfg.get('taker_bp', 1.0)))

    # 3. Slippage
    slippage_bp = float(raw.get('slippage_bp', 0.5))

    # 4. Risk
    r = raw.get('risk', {}) or {}
    long_cfg = r.get('long', {}) or {}
    short_cfg = r.get('short', {}) or {}
    risk = RiskConfig(
        atr_window=int(r.get('atr_window', 60)),
        cooldown_bars=int(r.get('cooldown_bars', 10)),
        long=RiskSideConfig(
            tp_mult=float(long_cfg.get('tp_mult', 27.5)),
            sl_mult=float(long_cfg.get('sl_mult', 9.0)),
        ),
        short=RiskSideConfig(
            tp_mult=float(short_cfg.get('tp_mult', 15.0)),
            sl_mult=float(short_cfg.get('sl_mult', 6.5)),
        ),
    )

    # 5. ShockFlip
    sf = raw.get('shock_flip', {}) or {}
    sf_cfg = ShockFlipConfig(
        source=str(sf.get('source', 'imbalance')),
        z_window=int(sf.get('z_window', 240)),
        z_band=float(sf.get('z_band', 2.5)),
        jump_band=float(sf.get('jump_band', 3.0)),
        persistence_bars=int(sf.get('persistence_bars', 6)),
        persistence_ratio=float(sf.get('persistence_ratio', 0.6)),
        dynamic_thresholds=sf.get('dynamic_thresholds', {'enabled': False}),
        location_filter=sf.get('location_filter', {'donchian_window': 120, 'require_extreme': True})
    )

    # 6. Filters
    flt = raw.get('filters', {}) or {}
    filters = FiltersConfig(
        min_relative_volume=flt.get('min_relative_volume'),
        min_divergence=flt.get('min_divergence'),
        vol_regime_low=flt.get('vol_regime_low'),
        vol_regime_high=flt.get('vol_regime_high'),
    )

    # 7. Management (optional)
    mgmt = raw.get('management', {}) or {}
    
    return BacktestConfig(
        symbol=symbol,
        tick_dir=tick_dir,
        timeframe=timeframe,
        fees=fees,
        slippage_bp=slippage_bp,
        risk=risk,
        shockflip=sf_cfg,
        filters=filters,
        mfe_breakeven_r=mgmt.get('mfe_breakeven_r'),
        time_stop_bars=mgmt.get('time_stop_bars'),
        time_stop_r=mgmt.get('time_stop_r'),
        _debug=True
    )

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--debug', action='store_true')
    args = p.parse_args()

    cfg = build_config(args.config)
    print(f"--- Config: {args.config} ---")
    
    # Print Management Status
    if cfg.filters.min_relative_volume:
        print(f"FILTER: Diamond Active (RelVol >= {cfg.filters.min_relative_volume})")
    
    if cfg.mfe_breakeven_r:
        print(f"MANAGEMENT: BreakEven active at {cfg.mfe_breakeven_r}R")
    else:
        print("MANAGEMENT: BreakEven OFF (WARNING)")
        
    if cfg.time_stop_bars:
        print(f"MANAGEMENT: Zombie Kill active at Bar {cfg.time_stop_bars} if < {cfg.time_stop_r}R")
    else:
        print("MANAGEMENT: Zombie Kill OFF (WARNING)")

    bars = load_full_history_as_bars(cfg.tick_dir)
    trades, stats = run_backtest_from_bars(bars, cfg)

    print("\n" + "="*40)
    print(f"RESULTS: {args.config}")
    print("="*40)
    print(f"Total Trades:     {stats['n']}")
    print(f"Win Rate:         {stats['win_rate']*100:.2f}%")
    print(f"Profit Factor:    {stats['pf']:.2f}")
    print(f"Total PnL:        {stats['total_pnl']:.4f}")
    print("="*40)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    trades.to_csv(args.out, index=False)
    print(f"Trade log saved to: {args.out}")

if __name__ == '__main__':
    main()
