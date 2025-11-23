#!/usr/bin/env python3
"""
Diamond Hunter v2.2 (Threshold Printer)
- Stream-Safe + Adjustable
- PRINTS THE EXACT REL_VOL THRESHOLD at the end.
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.data_loader import stream_ticks_from_dir, resample_ticks_to_bars
from core.features import add_core_features
from core.shockflip_detector import ShockFlipConfig, detect_shockflip_signals

EPS = 1e-9

def mfe_at_h(bars, idx, side, atr, H=6):
    n = len(bars)
    end = min(n, idx + H + 1)
    entry_price = float(bars.iloc[idx]['close'])
    highs = bars.iloc[idx + 1:end]['high'].values
    lows = bars.iloc[idx + 1:end]['low'].values

    if side == 1: # Long
        fav = (highs - entry_price) if len(highs) else np.array([0.0])
        mfe = np.nanmax(fav) if fav.size else 0.0
    else: # Short
        fav = (entry_price - lows) if len(lows) else np.array([0.0])
        mfe = np.nanmax(fav) if fav.size else 0.0

    return float(mfe / (atr + EPS))

def get_chunk_events(bars, cfg_overrides):
    sf_cfg = ShockFlipConfig(
        source='imbalance',
        z_window=240,
        z_band=cfg_overrides['z_band'],
        jump_band=cfg_overrides['jump_band'],
        persistence_bars=cfg_overrides['persistence'],
        persistence_ratio=0.5,
        dynamic_thresholds={'enabled': False},
        location_filter={'donchian_window': 120, 'require_extreme': True}
    )

    feats = add_core_features(bars,
                              z_window=sf_cfg.z_window,
                              atr_window=60,
                              donchian_window=sf_cfg.location_filter['donchian_window'])

    feats = detect_shockflip_signals(feats, sf_cfg)
    events = []

    for idx, row in feats.iterrows():
        side = int(row.get('shockflip_signal', 0))
        if side == 0: continue

        atr = float(row.get('atr', np.nan))
        if not np.isfinite(atr) or atr <= 0: continue

        mfe6 = mfe_at_h(feats, idx, side, atr, H=6)
        
        # Rel Vol Calc
        vol = row['buy_qty'] + row['sell_qty']
        v_start = max(0, idx - 59)
        avg_vol = (feats['buy_qty'].iloc[v_start:idx+1].sum() + 
                   feats['sell_qty'].iloc[v_start:idx+1].sum()) / 60.0
        rel_vol = vol / (avg_vol + EPS)

        # Features (Velocity/Div)
        flow_z = float(row.get('imbalance_z', 0.0))
        prev_z = float(feats['imbalance_z'].iloc[idx-1]) if idx > 0 else 0.0
        z_velocity = abs(flow_z - prev_z)
        
        price_ret_6 = (row['close'] - feats['close'].iloc[max(0, idx - 6)]) / (feats['close'].iloc[max(0, idx - 6)] + EPS)
        rolling_std = feats['close'].rolling(sf_cfg.z_window, min_periods=1).std().iloc[idx]
        div_score = max(0.0, -flow_z * (price_ret_6 / (rolling_std + EPS)))

        events.append({
            'ts': row['timestamp'],
            'side': side,
            'mfe6_atr': mfe6,
            'did_snap': 1 if mfe6 >= 0.5 else 0,
            'z_velocity': z_velocity,
            'div_score': div_score,
            'rel_vol': rel_vol
        })
    return events

def analyze_diamonds(all_events_df, out_dir, min_n=10):
    if all_events_df.empty:
        print("[Diamond Hunter] No events found.")
        return

    ev = all_events_df.copy()
    
    # Calculate The Magic Number (90th Percentile)
    rel_vol_90 = ev['rel_vol'].quantile(0.90)
    rel_vol_80 = ev['rel_vol'].quantile(0.80)

    # Global Deciles
    for col in ['z_velocity', 'div_score', 'rel_vol']:
        try:
            ev[f'{col}_decile'] = pd.qcut(ev[col].rank(method='first'), 10, labels=False)
        except:
            ev[f'{col}_decile'] = 0

    rows = []
    base_rate = ev['did_snap'].mean() * 100
    rows.append({'bucket': 'BASELINE', 'n': len(ev), 'snap_rate': round(base_rate, 2), 'lift': 0.0})

    for feat in ['z_velocity', 'div_score', 'rel_vol']:
        for dec in [8, 9]:
            sel = ev[ev[f'{feat}_decile'] >= dec]
            if len(sel) < min_n: continue
            rate = sel['did_snap'].mean() * 100
            rows.append({
                'bucket': f"{feat} >= Decile {dec}",
                'n': len(sel),
                'snap_rate': round(rate, 2),
                'lift': round(rate - base_rate, 2)
            })

    results = pd.DataFrame(rows).sort_values('snap_rate', ascending=False)
    
    os.makedirs(out_dir, exist_ok=True)
    results.to_csv(os.path.join(out_dir, "diamond_candidates.csv"), index=False)
    
    # Save raw data properly this time
    ev.to_csv(os.path.join(out_dir, "events_annotated.csv"), index=False)
    
    print("\n--- DIAMOND CANDIDATES ---")
    print(results.to_string(index=False))
    
    print(f"\n\n>>> THE MAGIC NUMBERS <<<")
    print(f"Decile 9 Threshold (Rel Vol): {rel_vol_90:.4f}")
    print(f"Decile 8 Threshold (Rel Vol): {rel_vol_80:.4f}")
    print(f"Use {rel_vol_90:.4f} in your config to filter for the 'Diamond' trades.")

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tick_dir', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--z_band', type=float, default=2.0)
    p.add_argument('--jump_band', type=float, default=2.5)
    p.add_argument('--persistence', type=int, default=4)
    args = p.parse_args()

    cfg_overrides = {'z_band': args.z_band, 'jump_band': args.jump_band, 'persistence': args.persistence}
    all_events = []

    print(f"Diamond Hunter v2.2 running on {args.tick_dir}...")
    for tick_chunk in stream_ticks_from_dir(args.tick_dir, chunk_days=10):
        bars = resample_ticks_to_bars(tick_chunk, timeframe='1min')
        if len(bars) < 240: continue
        events = get_chunk_events(bars, cfg_overrides)
        all_events.extend(events)

    if all_events:
        analyze_diamonds(pd.DataFrame(all_events), args.out)
    else:
        print("No events found.")

if __name__ == '__main__':
    main()