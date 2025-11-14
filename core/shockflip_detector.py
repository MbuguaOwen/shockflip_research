from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class ShockFlipConfig:
    source: str = "imbalance"  # or "delta"
    z_window: int = 240
    z_band: float = 2.5
    jump_band: float = 3.0
    persistence_bars: int = 6
    persistence_ratio: float = 0.60
    dynamic_enabled: bool = True
    dynamic_percentile: float = 0.99
    donchian_window: int = 120
    require_extreme: bool = True


def _compute_dynamic_jump_threshold(z: pd.Series, cfg: ShockFlipConfig) -> pd.Series:
    """Compute dynamic jump threshold based on rolling |z| percentile.

    We use a longer rolling window (4 * z_window) to estimate the local
    99th percentile of |z|, then take max(config.jump_band, local_pct).
    """
    if not cfg.dynamic_enabled:
        return pd.Series(cfg.jump_band, index=z.index)

    abs_z = z.abs()
    roll = abs_z.rolling(
        cfg.z_window * 4,
        min_periods=cfg.z_window,
    )
    local_pct = roll.quantile(cfg.dynamic_percentile)
    jump = np.maximum(cfg.jump_band, local_pct.fillna(cfg.jump_band))
    return pd.Series(jump, index=z.index)


def detect_shockflip_signals(
    features: pd.DataFrame,
    cfg: ShockFlipConfig,
) -> pd.DataFrame:
    """Detect ShockFlip events on a features DataFrame.

    Expects columns:
    - imbalance_z or delta_z depending on cfg.source
    - donchian_high / donchian_low / at_upper_extreme / at_lower_extreme

    Returns a copy of the DataFrame with added columns:
    - shockflip_signal: 0, +1 (long), -1 (short)
    - shockflip_z: z-value at event
    """
    df = features.copy()

    if cfg.source == "imbalance":
        z = df["imbalance_z"]
    elif cfg.source == "delta":
        if "delta_z" not in df.columns:
            raise ValueError("delta_z not found; compute it before using source='delta'")
        z = df["delta_z"]
    else:
        raise ValueError(f"Unsupported source {cfg.source!r}")

    jump_threshold = _compute_dynamic_jump_threshold(z, cfg)

    z_abs = z.abs()
    sign = np.sign(z)

    # Core conditions
    cond_jump = z_abs >= jump_threshold
    cond_band = z_abs >= cfg.z_band

    # Persistence: last `persistence_bars` must have at least
    # `persistence_ratio` of bars with |z| >= z_band AND same sign as current.
    pers = pd.Series(False, index=z.index)

    window = cfg.persistence_bars
    ratio = cfg.persistence_ratio

    for i in range(len(z)):
        if i < window - 1:
            continue
        sl = slice(i - window + 1, i + 1)
        window_z = z.iloc[sl]
        window_sign = np.sign(window_z)
        same_sign = window_sign == sign.iloc[i]
        strong_mag = window_z.abs() >= cfg.z_band
        ok = same_sign & strong_mag
        pers.iloc[i] = ok.mean() >= ratio

    # Location filter
    at_upper = df.get("at_upper_extreme", pd.Series(False, index=df.index))
    at_lower = df.get("at_lower_extreme", pd.Series(False, index=df.index))

    # Direction:
    # - At lower Donchian extreme, a strong positive shock => long (+1).
    # - At upper Donchian extreme, a strong negative shock => short (-1).
    long_cond = (
        (sign > 0)
        & cond_jump
        & cond_band
        & pers
        & ((~cfg.require_extreme) | at_lower)
    )
    short_cond = (
        (sign < 0)
        & cond_jump
        & cond_band
        & pers
        & ((~cfg.require_extreme) | at_upper)
    )

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[long_cond] = 1
    signal[short_cond] = -1

    df["shockflip_signal"] = signal
    df["shockflip_z"] = z

    # Optional debug instrumentation: expose internal conditions
    # This does not affect downstream logic and is gated by cfg._debug.
    if bool(getattr(cfg, "_debug", False)):
        df["sf_cond_jump"] = cond_jump.astype(bool)
        df["sf_cond_band"] = cond_band.astype(bool)
        df["sf_pers"] = pers.astype(bool)
        df["sf_at_upper"] = at_upper.astype(bool)
        df["sf_at_lower"] = at_lower.astype(bool)
        df["sf_sign"] = sign
        df["sf_long_cond"] = (
            (sign > 0) & cond_jump & cond_band & pers & ((~cfg.require_extreme) | at_lower)
        )
        df["sf_short_cond"] = (
            (sign < 0) & cond_jump & cond_band & pers & ((~cfg.require_extreme) | at_upper)
        )

    return df
