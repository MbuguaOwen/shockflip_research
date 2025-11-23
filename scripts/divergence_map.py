#!/usr/bin/env python3
"""
Divergence Map – Clean & Self-Contained & Memory-Safe
Streams ticks to detect order-flow/price divergences and builds a resolution heatmap.
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.data_loader import stream_ticks_from_dir, resample_ticks_to_bars
from core.features import add_core_features

# ----------------------------------------------------------------------
# Embedded Config
# ----------------------------------------------------------------------
CFG = {
    "risk": {"atr_window": 60},
    "shock_flip": {
        "z_window": 240,
        "location_filter": {"donchian_window": 120}
    }
}

EPS = 1e-9

# ----------------------------------------------------------------------
# Core Logic
# ----------------------------------------------------------------------
def tag_divergence_events(df, flow_z_threshold=2.0, price_flat_thresh=0.0, lookback_price=1):
    df = df.copy().reset_index(drop=True)
    df['price_ret_lb'] = df['close'].pct_change(periods=lookback_price).fillna(0.0)
    df['divergence_flag'] = ((df['imbalance_z'].abs() >= flow_z_threshold) &
                             (df['price_ret_lb'] <= price_flat_thresh)).astype(int)
    return df

def classify_resolution(bars, idx, side, atr, H=10, thr_atr=0.5):
    n = len(bars)
    entry_price = float(bars.loc[idx, 'close'])
    end = min(n, idx + H + 1)
    
    # Safe slicing
    highs = bars.loc[idx + 1:end, 'high'].values
    lows = bars.loc[idx + 1:end, 'low'].values

    if side > 0:   # Buying pressure
        max_fav = np.max(highs - entry_price) if len(highs) else 0.0
        max_adv = np.max(entry_price - lows) if len(lows) else 0.0
    else:          # Selling pressure
        max_fav = np.max(entry_price - lows) if len(lows) else 0.0
        max_adv = np.max(highs - entry_price) if len(highs) else 0.0

    if max_adv >= thr_atr * atr:
        return 'reversion', max_adv / (atr + EPS)
    elif max_fav >= thr_atr * atr:
        return 'breakout', max_fav / (atr + EPS)
    else:
        return 'churn', 0.0

def get_chunk_divergences(bars):
    """
    Process a chunk, detect divergences, return raw event list.
    """
    feats = add_core_features(
        bars,
        z_window=CFG['shock_flip']['z_window'],
        atr_window=CFG['risk']['atr_window'],
        donchian_window=CFG['shock_flip']['location_filter']['donchian_window']
    )

    df = tag_divergence_events(feats, flow_z_threshold=2.0)
    events = []

    for idx, row in df.iterrows():
        if not row['divergence_flag']:
            continue

        side = 1 if row['imbalance'] > 0 else -1
        atr = row.get('atr', np.nan)
        if not np.isfinite(atr) or atr <= 0:
            continue

        # Absorption duration (lookback)
        dur = 0
        # Safe loop backwards
        for j in range(idx, max(-1, idx - 30), -1):
            if abs(df.iloc[j]['imbalance_z']) >= 2.0:
                dur += 1
            else:
                break

        label, mag = classify_resolution(df, idx, side, atr)
        
        events.append({
            "ts": row['timestamp'],
            "side": side,
            "duration": dur,
            "flow_z": row['imbalance_z'],
            "resolution": label,
            "magnitude": mag
        })
        
    return events

def generate_heatmap(all_events_df, out_dir):
    """
    Generates bins and heatmap from the full event dataset.
    """
    ev = all_events_df.copy()

    # Binning (Global Quantiles)
    ev['intensity_bin'] = pd.qcut(ev['flow_z'].abs().rank(method='first'), q=4,
                                  labels=['low', 'med', 'high', 'xhigh'])
    ev['dur_bin'] = pd.cut(ev['duration'], bins=[-1, 1, 3, 6, 12, 999],
                           labels=['0-1', '2-3', '4-6', '7-12', '13+'])

    # Summary
    summary = []
    for (ib, db), grp in ev.groupby(['intensity_bin', 'dur_bin'], observed=True):
        total = len(grp)
        if total == 0: continue
        
        cnt = grp['resolution'].value_counts()
        summary.append({
            "intensity": ib,
            "duration": db,
            "total": total,
            "p_reversion": cnt.get('reversion', 0) / total,
            "p_breakout": cnt.get('breakout', 0) / total,
            "p_churn": cnt.get('churn', 0) / total,
            "avg_mag_reversion": grp.loc[grp['resolution'] == 'reversion', 'magnitude'].mean(),
            "avg_mag_breakout": grp.loc[grp['resolution'] == 'breakout', 'magnitude'].mean(),
        })

    heat = pd.DataFrame(summary)
    
    heat_path = os.path.join(out_dir, "divergence_heatmap.csv")
    ev_path = os.path.join(out_dir, "events_FULL.csv")
    
    heat.to_csv(heat_path, index=False)
    ev.to_csv(ev_path, index=False)
    
    print(f"[Divergence Map] Saved events and heatmap to {out_dir}")
    print(heat.head(10).to_string(index=False))

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tick_dir', default='data/ticks/BTCUSDT')
    parser.add_argument('--out', default='results/divergence_map')
    args = parser.parse_args()
    
    os.makedirs(args.out, exist_ok=True)
    all_events = []

    print(f"Starting Divergence Map on {args.tick_dir}...")

    # 1. Stream
    for i, tick_chunk in enumerate(stream_ticks_from_dir(args.tick_dir, chunk_days=10)):
        print(f"\n--- Chunk {i+1} ---")
        bars = resample_ticks_to_bars(tick_chunk, timeframe='1min')
        print(f"   Bars: {len(bars):,}")

        chunk_ev = get_chunk_divergences(bars)
        if chunk_ev:
            print(f"   Events found: {len(chunk_ev)}")
            all_events.extend(chunk_ev)

    # 2. Global Analysis
    print(f"\nScan complete. Total events: {len(all_events)}")
    if all_events:
        full_df = pd.DataFrame(all_events)
        generate_heatmap(full_df, args.out)
    else:
        print("No divergence events found.")

if __name__ == '__main__':
    main()