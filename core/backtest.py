from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .barriers import FeesConfig, RiskConfig, build_barriers, compute_trade_pnl, enforce_tp_sl_invariants
from .features import add_core_features, add_hypothesis_features
from .shockflip_detector import ShockFlipConfig, detect_shockflip_signals
from .progress import get_progress


@dataclass
class BacktestConfig:
    symbol: str
    tick_dir: str
    timeframe: str
    fees: FeesConfig
    slippage_bp: float
    risk: RiskConfig
    shockflip: ShockFlipConfig


def prepare_features_for_backtest(
    bars: pd.DataFrame,
    cfg: BacktestConfig,
) -> pd.DataFrame:
    """Compute all features required for ShockFlip backtest + H1–H3."""
    df = add_core_features(
        bars,
        z_window=cfg.shockflip.z_window,
        atr_window=cfg.risk.atr_window,
        donchian_window=cfg.shockflip.donchian_window,
    )
    # H1–H3: pre-context research features (do not affect signals)
    df = add_hypothesis_features(
        df,
        prior_flow_window=60,
        div_window=60,
        atr_pct_window=5000,
    )
    df = detect_shockflip_signals(df, cfg.shockflip)
    return df


def _simulate_trades(
    features: pd.DataFrame,
    cfg: BacktestConfig,
    progress: bool = True,
) -> pd.DataFrame:
    """Simulate trades based on ShockFlip signals with first-touch TP/SL.

    Deterministic tie-break rule:
    - If both TP and SL are hit in the same bar (no intrabar info),
      we choose the *worse* outcome (SL) as a conservative assumption.
    """
    df = features.reset_index(drop=True).copy()

    trades: List[Dict] = []
    cooldown = 0

    p = get_progress(progress, total=len(df), desc="Simulate trades")
    for i in range(len(df)):
        p.update(1)
        if cooldown > 0:
            cooldown -= 1
            continue

        row = df.iloc[i]
        side = int(row.get("shockflip_signal", 0))
        if side == 0:
            continue

        # H1 entry filter: require prior_flow_sign == required_sign if configured
        required_sign = getattr(cfg, "_h1_prior_flow_required_sign", None)
        if required_sign is not None:
            pfs = row.get("prior_flow_sign")
            try:
                if pd.isna(pfs) or int(pfs) != int(required_sign):
                    continue
            except Exception:
                continue

        atr = float(row.get("atr", float("nan")))
        if not np.isfinite(atr) or atr <= 0:
            continue

        entry_idx = i
        entry_ts = row["timestamp"]
        entry_price = float(row["close"])

        # H5–H7: track path statistics for this trade
        best_fav = 0.0   # max favourable excursion (price units, >= 0)
        worst_adv = 0.0  # most adverse excursion (price units, <= 0)
        time_to_mfe = 0  # bars from entry until best_fav

        # Simulate forward until barrier hit or we run out of data
        exit_idx = None
        exit_ts = None
        exit_price = None
        result = None

        # Build TP/SL once based on entry ATR
        # We'll use per-bar high/low to check hits.
        for j in range(i + 1, len(df)):
            bar = df.iloc[j]
            high = float(bar["high"])
            low = float(bar["low"])

            # --- H5–H7 path stats update ------------------------------------
            # Favourable move from entry (from POV of 'side')
            fav = side * (high - entry_price)
            # Adverse move from entry (from POV of 'side')
            adv = side * (low - entry_price)

            if fav > best_fav:
                best_fav = fav
                time_to_mfe = j - i

            if adv < worst_adv:
                worst_adv = adv
            # ---------------------------------------------------------------

            tp, sl, hit_tp, hit_sl = build_barriers(
                side=side,
                entry=entry_price,
                atr=atr,
                risk=cfg.risk,
                high=high,
                low=low,
            )

            if tp is None or sl is None:
                continue

            if hit_tp and hit_sl:
                # Deterministic tie-break: SL wins (worst-case)
                result = "SL"
                exit_price = sl
                exit_ts = bar["timestamp"]
                exit_idx = j
                break
            elif hit_tp:
                result = "TP"
                exit_price = tp
                exit_ts = bar["timestamp"]
                exit_idx = j
                break
            elif hit_sl:
                result = "SL"
                exit_price = sl
                exit_ts = bar["timestamp"]
                exit_idx = j
                break

        # If no barrier hit, close at last close
        if exit_idx is None:
            bar = df.iloc[-1]
            exit_idx = len(df) - 1
            exit_ts = bar["timestamp"]
            exit_price = float(bar["close"])
            # Decide TP vs SL by sign of raw return
            raw = side * (exit_price - entry_price)
            result = "TP" if raw > 0 else "SL"

        pnl = compute_trade_pnl(
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            fees=cfg.fees,
            slippage_bp=cfg.slippage_bp,
        )

        enforce_tp_sl_invariants(
            side=side,
            result=result,
            pnl=pnl,
            entry=entry_price,
            exit_price=exit_price,
        )

        # Normalize excursions to "R" units using entry ATR and side-specific SL
        risk_per_unit = atr * (
            cfg.risk.long.sl_mult if side == 1 else cfg.risk.short.sl_mult
        )
        if risk_per_unit > 0:
            mfe_r = best_fav / risk_per_unit
            mae_r = worst_adv / risk_per_unit
        else:
            mfe_r = np.nan
            mae_r = np.nan

        holding_period = exit_idx - entry_idx

        trades.append(
            dict(
                symbol=cfg.symbol,
                entry_ts=entry_ts,
                exit_ts=exit_ts,
                entry_idx=entry_idx,
                exit_idx=exit_idx,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                result=result,
                pnl=pnl,
                atr=atr,
                shockflip_z=float(row.get("shockflip_z", float("nan"))),
                # H5–H7: post-path instrumentation
                mfe_price=best_fav,
                mae_price=worst_adv,
                mfe_r=mfe_r,
                mae_r=mae_r,
                time_to_mfe_bars=time_to_mfe,
                holding_period_bars=holding_period,
            )
        )

        cooldown = cfg.risk.cooldown_bars

    p.close()
    trades_df = pd.DataFrame(trades)
    return trades_df


def summarize_trades(trades: pd.DataFrame) -> Dict[str, float]:
    if trades.empty:
        return {"n": 0, "win_rate": 0.0, "pf": 0.0}

    pnl = trades["pnl"]
    n = len(trades)
    win_rate = float((pnl > 0).mean())

    pos = pnl[pnl > 0].sum()
    neg = pnl[pnl < 0].sum()
    pf = float(pos / -neg) if neg < 0 else 0.0

    return {"n": n, "win_rate": win_rate, "pf": pf}


def run_backtest_from_bars(
    bars: pd.DataFrame,
    cfg: BacktestConfig,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    feats = prepare_features_for_backtest(bars, cfg)

    # Optional diagnostics: feature stats and signal counts
    if bool(getattr(cfg, "_debug", False)):
        try:
            vc = feats.get("shockflip_signal", pd.Series(dtype=int)).value_counts().sort_index()
            print("[Debug] shockflip_signal counts:", dict(vc))
            for col in ("imbalance", "imbalance_z", "atr", "donchian_loc"):
                if col in feats.columns:
                    s = feats[col].dropna()
                    if not s.empty:
                        print(f"[Debug] {col}: min={s.min():.4f} mean={s.mean():.4f} max={s.max():.4f}")
            # If no signals, probe gating conditions when available
            if int(vc.get(-1, 0) + vc.get(1, 0)) == 0:
                keys = ["sf_cond_band", "sf_cond_jump", "sf_pers", "sf_at_upper", "sf_at_lower", "sf_long_cond", "sf_short_cond"]
                have = [k for k in keys if k in feats.columns]
                if have:
                    print("[Debug] Condition pass counts:")
                    for k in have:
                        cnt = int(feats[k].sum()) if feats[k].dtype != float else int(feats[k].astype(bool).sum())
                        print(f"  - {k}: {cnt}")
                # q_plus/q_minus health
                if all(c in feats.columns for c in ("q_plus", "q_minus")):
                    qplus = float(feats["q_plus"].sum())
                    qminus = float(feats["q_minus"].sum())
                    print(f"[Debug] q_plus sum={qplus:.2f}, q_minus sum={qminus:.2f}")
        except Exception:
            # Never break pipeline on diagnostics
            pass
    # Allow caller to toggle progress via cfg attribute if present or through direct param.
    # We detect a "progress" kw in locals of the caller by function default in scripts.
    # To keep signature stable here, derive from attribute if attached dynamically.
    progress = getattr(cfg, "_progress", True)
    trades = _simulate_trades(feats, cfg, progress=progress)
    stats = summarize_trades(trades)
    return trades, stats
