from typing import Tuple

import numpy as np
import pandas as pd


def compute_orderflow_features(bars: pd.DataFrame, eps: float = 1e-9) -> pd.DataFrame:
    """Add Q+, Q-, delta, imbalance, and z-scores to bars.

    Assumes bars has:
    - buy_qty
    - sell_qty
    """
    df = bars.copy()

    df["q_plus"] = df["buy_qty"].astype(float)
    df["q_minus"] = df["sell_qty"].astype(float)
    df["delta"] = df["q_plus"] - df["q_minus"]
    df["imbalance"] = (df["q_plus"] - df["q_minus"]) / (
        df["q_plus"] + df["q_minus"] + eps
    )

    return df


def rolling_zscore(series: pd.Series, window: int, eps: float = 1e-9) -> pd.Series:
    """Causal rolling z-score (includes current bar in window)."""
    roll_mean = series.rolling(window, min_periods=window).mean()
    roll_std = series.rolling(window, min_periods=window).std(ddof=0)
    z = (series - roll_mean) / (roll_std + eps)
    return z


def compute_atr(bars: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Compute ATR(window) using classic True Range definition."""
    df = bars.copy()
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["tr"] = tr
    df["atr"] = tr.rolling(window, min_periods=window).mean()

    return df


def compute_donchian(bars: pd.DataFrame, window: int = 120, eps: float = 1e-9) -> pd.DataFrame:
    """Compute Donchian channel and location.

    - donchian_high: rolling max of high
    - donchian_low: rolling min of low
    - donchian_loc: (close - low) / (high - low + eps) in [0,1]
    - at_upper_extreme: bar makes new window high (high >= donchian_high)
    - at_lower_extreme: bar makes new window low (low <= donchian_low)
    """
    df = bars.copy()
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    donchian_high = high.rolling(window, min_periods=window).max()
    donchian_low = low.rolling(window, min_periods=window).min()

    df["donchian_high"] = donchian_high
    df["donchian_low"] = donchian_low

    rng = donchian_high - donchian_low
    df["donchian_loc"] = (close - donchian_low) / (rng + eps)

    df["at_upper_extreme"] = high >= donchian_high
    df["at_lower_extreme"] = low <= donchian_low

    return df


def add_core_features(
    bars: pd.DataFrame,
    z_window: int = 240,
    atr_window: int = 60,
    donchian_window: int = 120,
) -> pd.DataFrame:
    """Convenience: compute orderflow, imbalance z, ATR, Donchian."""
    df = compute_orderflow_features(bars)
    df["imbalance_z"] = rolling_zscore(df["imbalance"], window=z_window)
    df = compute_atr(df, window=atr_window)
    df = compute_donchian(df, window=donchian_window)
    return df
