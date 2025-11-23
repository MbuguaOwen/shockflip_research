from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

import numpy as np
import pandas as pd

from .barriers import FeesConfig, RiskConfig, build_barriers, compute_trade_pnl, enforce_tp_sl_invariants
from .features import add_core_features, add_hypothesis_features
from .shockflip_detector import ShockFlipConfig, detect_shockflip_signals
from .progress import get_progress

# -------------------------------------------------------------------------
# CONFIGURATION MODELS
# -------------------------------------------------------------------------

@dataclass
class FiltersConfig:
    min_relative_volume: Optional[float] = None
    min_divergence: Optional[float] = None
    vol_regime_low: Optional[float] = None
    vol_regime_high: Optional[float] = None
    
    def get(self, key, default=None):
        return getattr(self, key, default)

@dataclass
class BacktestConfig:
    symbol: str
    tick_dir: str
    timeframe: str
    fees: FeesConfig
    slippage_bp: float
    risk: RiskConfig
    shockflip: ShockFlipConfig
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    
    # Management Config (The Zombie Kit)
    mfe_breakeven_r: Optional[float] = None  # Lock BE after this many R
    time_stop_bars: Optional[int] = None     # Kill trade if not profitable by this bar
    time_stop_r: Optional[float] = None      # Profit threshold required to survive time stop
    
    _debug: bool = False
    _progress: bool = True

# -------------------------------------------------------------------------
# FEATURE PREPARATION & FILTERING
# -------------------------------------------------------------------------

def _compute_relative_volume(bars: pd.DataFrame, window: int = 60) -> pd.Series:
    vol = bars["buy_qty"] + bars["sell_qty"]
    rolling_sum = vol.rolling(window=window, min_periods=1).sum()
    avg_vol = rolling_sum / float(window)
    return vol / (avg_vol + 1e-9)

def apply_entry_filters(df: pd.DataFrame, cfg: FiltersConfig) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    if cfg.min_relative_volume is not None:
        if "rel_vol" in df.columns:
            mask &= (df["rel_vol"] >= float(cfg.min_relative_volume))
    if cfg.min_divergence is not None:
        if "price_flow_div" in df.columns:
            mask &= (df["price_flow_div"].abs() >= float(cfg.min_divergence))
    return mask

def prepare_features_for_backtest(bars: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    loc_filter = cfg.shockflip.location_filter
    d_window = loc_filter['donchian_window'] if isinstance(loc_filter, dict) else loc_filter.donchian_window

    df = add_core_features(
        bars,
        z_window=cfg.shockflip.z_window,
        atr_window=cfg.risk.atr_window,
        donchian_window=d_window,
    )
    df = add_hypothesis_features(df, prior_flow_window=60, div_window=60, atr_pct_window=5000)
    df["rel_vol"] = _compute_relative_volume(df, window=60)
    df = detect_shockflip_signals(df, cfg.shockflip)
    return df

# -------------------------------------------------------------------------
# SIMULATION ENGINE
# -------------------------------------------------------------------------

def _simulate_trades(features: pd.DataFrame, cfg: BacktestConfig, progress: bool = True) -> pd.DataFrame:
    df = features.reset_index(drop=True).copy()
    filter_mask = apply_entry_filters(df, cfg.filters)
    
    trades: List[Dict] = []
    cooldown = 0
    
    sl_mult_long = cfg.risk.long.sl_mult
    sl_mult_short = cfg.risk.short.sl_mult
    cooldown_bars = cfg.risk.cooldown_bars
    
    # Management Settings
    be_threshold_r = cfg.mfe_breakeven_r
    time_stop_bars = cfg.time_stop_bars
    time_stop_r = cfg.time_stop_r if cfg.time_stop_r is not None else 0.5
    
    p = get_progress(progress, total=len(df), desc="Simulate trades")
    
    for i in range(len(df)):
        p.update(1)
        if cooldown > 0:
            cooldown -= 1
            continue

        row = df.iloc[i]
        raw_signal = int(row.get("shockflip_signal", 0))
        if raw_signal == 0: continue
        if not filter_mask.iloc[i]: continue

        atr = float(row.get("atr", float("nan")))
        if not np.isfinite(atr) or atr <= 0: continue

        entry_ts = row["timestamp"]
        entry_price = float(row["close"])
        side = raw_signal
        
        sl_mult = sl_mult_long if side == 1 else sl_mult_short
        risk_per_unit = atr * sl_mult
        
        tp, sl, _, _ = build_barriers(side, entry_price, atr, cfg.risk, entry_price, entry_price)
        if tp is None or sl is None: continue

        exit_idx, exit_ts, exit_price, result = None, None, None, None
        best_fav = 0.0
        worst_adv = 0.0
        be_active = False

        for j in range(i + 1, len(df)):
            bar = df.iloc[j]
            high = float(bar["high"])
            low = float(bar["low"])
            close = float(bar["close"])
            
            # 1. Update Path Stats
            fav = side * (high - entry_price)
            adv = side * (low - entry_price)
            if fav > best_fav: best_fav = fav
            if adv < worst_adv: worst_adv = adv
            
            # 2. Breakeven Lock (The Free Shot)
            if not be_active and be_threshold_r is not None:
                 if best_fav >= be_threshold_r * risk_per_unit:
                     be_active = True
            
            # 3. Zombie Kill (The Time Stop)
            bars_held = j - i
            if time_stop_bars is not None and bars_held >= time_stop_bars:
                # If we haven't hit the survival threshold (0.5R) by bar 10...
                if best_fav < time_stop_r * risk_per_unit:
                    # KILL IT
                    exit_price = close
                    exit_ts = bar["timestamp"]
                    exit_idx = j
                    result = "ZOMBIE"
                    break

            # 4. Check Exit Barriers
            sl_eff = sl
            if be_active:
                sl_eff = max(sl_eff, entry_price) if side == 1 else min(sl_eff, entry_price)
            
            hit_sl_eff = (low <= sl_eff) if side == 1 else (high >= sl_eff)
            hit_tp = (high >= tp) if side == 1 else (low <= tp)
            
            if hit_sl_eff:
                exit_price = sl_eff
                exit_ts = bar["timestamp"]
                exit_idx = j
                # Label BE if stopped at entry
                is_be = np.isclose(sl_eff, entry_price, atol=1e-8)
                result = "BE" if is_be else "SL"
                break
                
            if hit_tp:
                result = "TP"
                exit_price = tp
                exit_ts = bar["timestamp"]
                exit_idx = j
                break
        
        # End of Data Close
        if exit_idx is None:
            bar = df.iloc[-1]
            exit_idx = len(df) - 1
            exit_ts = bar["timestamp"]
            exit_price = float(bar["close"])
            result = "TP" if side * (exit_price - entry_price) > 0 else "SL"

        pnl = compute_trade_pnl(side, entry_price, exit_price, cfg.fees, cfg.slippage_bp)
        
        trades.append(dict(
            symbol=cfg.symbol,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            result=result,
            pnl=pnl,
            mfe_r=best_fav / risk_per_unit if risk_per_unit > 0 else 0,
            holding_period=exit_idx - i
        ))
        cooldown = cooldown_bars

    p.close()
    return pd.DataFrame(trades)

def summarize_trades(trades: pd.DataFrame) -> Dict[str, float]:
    if trades.empty: return {"n": 0, "win_rate": 0.0, "pf": 0.0, "total_pnl": 0.0}
    pnl = trades["pnl"]
    pos = pnl[pnl > 0].sum()
    neg = pnl[pnl < 0].sum()
    pf = float(pos / -neg) if neg < 0 else (100.0 if pos > 0 else 0.0)
    return {"n": len(trades), "win_rate": float((pnl > 0).mean()), "pf": pf, "total_pnl": float(pnl.sum())}

def run_backtest_from_bars(bars, cfg):
    feats = prepare_features_for_backtest(bars, cfg)
    trades = _simulate_trades(feats, cfg, progress=cfg._progress)
    stats = summarize_trades(trades)
    return trades, stats