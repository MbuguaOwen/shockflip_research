#!/usr/bin/env python
import argparse
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_pf(df: pd.DataFrame) -> float:
    """Compute profit factor for a set of trades."""
    if df.empty or "pnl" not in df.columns:
        return np.nan
    pnl = pd.to_numeric(df["pnl"], errors="coerce").fillna(0.0)
    gross_pos = pnl[pnl > 0].sum()
    gross_neg = -pnl[pnl < 0].sum()
    if gross_neg <= 0:
        return np.nan
    return float(gross_pos / gross_neg)


def safe_win_rate(df: pd.DataFrame) -> float:
    if df.empty or "pnl" not in df.columns:
        return np.nan
    pnl = pd.to_numeric(df["pnl"], errors="coerce").fillna(0.0)
    n = len(pnl)
    if n == 0:
        return np.nan
    return float((pnl > 0).sum() / n)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Load & join
# ---------------------------------------------------------------------------

def _infer_join_cols(trades: pd.DataFrame, events: pd.DataFrame):
    """Return (left_col, right_col) for merge, handling common naming.

    Prefers 'entry_idx' (trades) ~ 'idx' (events) mapping when available.
    """
    candidates = [
        ("entry_idx", "entry_idx"),
        ("entry_idx", "idx"),
        ("entry_idx", "bar_idx"),
        ("idx", "idx"),
        ("bar_idx", "bar_idx"),
    ]
    for l, r in candidates:
        if l in trades.columns and r in events.columns:
            return l, r
    return None, None


def load_and_join(trades_path: Path, events_path: Path) -> pd.DataFrame:
    trades = pd.read_csv(trades_path)
    events = pd.read_csv(events_path)

    left_key, right_key = _infer_join_cols(trades, events)
    if left_key is None:
        raise KeyError(
            "Could not find a common join mapping between trades and events. "
            "Tried ('entry_idx'~'idx'/'bar_idx') and identical names."
        )

    merged = trades.merge(
        events,
        left_on=left_key,
        right_on=right_key,
        how="left",
        suffixes=("_trade", "_evt"),
    )

    # Sanity: we expect most trades to match to an event row
    if right_key in merged.columns:
        missing = merged[right_key].isna().sum()
        if missing > 0:
            print(f"[Warn] {missing} trades could not be matched to events by {left_key}~{right_key}.")

    return merged


# ---------------------------------------------------------------------------
# H5–H7: Path stats & zombies
# ---------------------------------------------------------------------------

def analyze_path_stats(trades: pd.DataFrame) -> pd.DataFrame:
    """Summaries for MFE/MAE and time-based stats, by result."""
    df = trades.copy()
    if "result" not in df.columns:
        # Fallback: classify result by pnl sign if result col missing
        df["result"] = np.where(pd.to_numeric(df.get("pnl", 0), errors="coerce").fillna(0.0) > 0, "WIN", "LOSS")

    cols = [
        "pnl",
        "mfe_r",
        "mae_r",
        "mfe_price",
        "mae_price",
        "time_to_mfe_bars",
        "holding_period_bars",
    ]
    for c in cols:
        if c not in df.columns:
            print(f"[Warn] Missing column '{c}' in trades; path stats will be partial.")

    grouped = []
    for result_val, g in df.groupby("result"):
        row = {"result": result_val, "n_trades": len(g)}
        row["pf"] = compute_pf(g)
        row["win_rate"] = safe_win_rate(g)
        for c in cols:
            if c in g.columns:
                row[f"{c}_mean"] = pd.to_numeric(g[c], errors="coerce").mean()
                row[f"{c}_median"] = pd.to_numeric(g[c], errors="coerce").median()
            else:
                row[f"{c}_mean"] = np.nan
                row[f"{c}_median"] = np.nan
        grouped.append(row)

    summary = pd.DataFrame(grouped)
    return summary


def analyze_zombies(trades: pd.DataFrame, thresholds=(0.5, 1.0)) -> pd.DataFrame:
    """
    H5 focus: identify "zombie" trades – losers that once had decent MFE.

    thresholds: sequence of mfe_r cutoffs (in R).
    """
    df = trades.copy()
    if "mfe_r" not in df.columns:
        raise KeyError("Expected 'mfe_r' in trades for zombie analysis.")
    if "result" not in df.columns:
        df["result"] = np.where(pd.to_numeric(df.get("pnl", 0), errors="coerce").fillna(0.0) > 0, "WIN", "LOSS")

    out_rows = []

    total_n = len(df)
    total_pf = compute_pf(df)
    total_pnl = pd.to_numeric(df.get("pnl", 0), errors="coerce").fillna(0.0).sum()

    losers = df[pd.to_numeric(df.get("pnl", 0), errors="coerce").fillna(0.0) <= 0]
    n_losers = len(losers)
    pnl_losers = pd.to_numeric(losers.get("pnl", 0), errors="coerce").fillna(0.0).sum()

    for thr in thresholds:
        mask = (pd.to_numeric(df.get("pnl", 0), errors="coerce").fillna(0.0) <= 0) & (pd.to_numeric(df.get("mfe_r", 0), errors="coerce").fillna(0.0) >= thr)
        z = df[mask]

        row = {
            "mfe_r_threshold": thr,
            "n_zombies": len(z),
            "share_of_all_trades": len(z) / total_n if total_n else np.nan,
            "share_of_losers": len(z) / n_losers if n_losers else np.nan,
            "zombies_sum_pnl": pd.to_numeric(z.get("pnl", 0), errors="coerce").fillna(0.0).sum(),
            "total_sum_pnl": total_pnl,
            "losers_sum_pnl": pnl_losers,
            "pf_all": total_pf,
        }
        out_rows.append(row)

    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# H1: Prior flow sign
# ---------------------------------------------------------------------------

def analyze_prior_flow_sign(merged: pd.DataFrame) -> pd.DataFrame:
    """
    H1: bucket trades by prior_flow_sign at entry and compute PF, win rate, etc.
    """
    if "prior_flow_sign" not in merged.columns:
        raise KeyError("Expected 'prior_flow_sign' in merged data.")

    df = merged.copy()
    df = df[~merged["prior_flow_sign"].isna()]

    rows = []
    for sign_val, g in df.groupby("prior_flow_sign"):
        row = {
            "prior_flow_sign": sign_val,
            "n_trades": len(g),
            "pf": compute_pf(g),
            "win_rate": safe_win_rate(g),
            "mean_pnl": pd.to_numeric(g.get("pnl", 0), errors="coerce").fillna(0.0).mean(),
            "median_pnl": pd.to_numeric(g.get("pnl", 0), errors="coerce").fillna(0.0).median(),
        }
        # Optional: also check by side
        if "side" in g.columns:
            for side_val, sg in g.groupby("side"):
                row[f"n_side_{side_val}"] = len(sg)
                row[f"pf_side_{side_val}"] = compute_pf(sg)
        rows.append(row)

    return pd.DataFrame(rows).sort_values("prior_flow_sign")


# ---------------------------------------------------------------------------
# H2: Price-flow divergence
# ---------------------------------------------------------------------------

def analyze_price_flow_div(merged: pd.DataFrame, n_bins: int = 5) -> pd.DataFrame:
    """
    H2: bucket trades by quantiles of price_flow_div at entry and compute PF, etc.
    """
    if "price_flow_div" not in merged.columns:
        raise KeyError("Expected 'price_flow_div' in merged data.")

    df = merged.copy()
    df = df[np.isfinite(pd.to_numeric(df["price_flow_div"], errors="coerce"))]

    # Quantile buckets; allow duplicates to be dropped.
    try:
        df["pf_div_bucket"] = pd.qcut(
            pd.to_numeric(df["price_flow_div"], errors="coerce"),
            q=n_bins,
            duplicates="drop",
        )
    except ValueError:
        # Not enough unique values; fall back to 3 bins
        df["pf_div_bucket"] = pd.qcut(
            pd.to_numeric(df["price_flow_div"], errors="coerce"),
            q=3,
            duplicates="drop",
        )

    rows = []
    for bucket, g in df.groupby("pf_div_bucket"):
        series = pd.to_numeric(g.get("price_flow_div", 0), errors="coerce").fillna(0.0)
        row = {
            "price_flow_div_bucket": str(bucket),
            "n_trades": len(g),
            "pf": compute_pf(g),
            "win_rate": safe_win_rate(g),
            "mean_pnl": pd.to_numeric(g.get("pnl", 0), errors="coerce").fillna(0.0).mean(),
            "median_pnl": pd.to_numeric(g.get("pnl", 0), errors="coerce").fillna(0.0).median(),
            "bucket_min": series.min(),
            "bucket_max": series.max(),
        }
        rows.append(row)

    return pd.DataFrame(rows).sort_values("bucket_min")


# ---------------------------------------------------------------------------
# H3: ATR percentile (vol regime)
# ---------------------------------------------------------------------------

def analyze_atr_pct(merged: pd.DataFrame, cuts=(0.0, 0.2, 0.8, 1.0)) -> pd.DataFrame:
    """
    H3: bucket trades by atr_pct regime and compute PF, etc.

    Default:
      low  vol: [0.0, 0.2]
      mid  vol: (0.2, 0.8]
      high vol: (0.8, 1.0]
    """
    if "atr_pct" not in merged.columns:
        raise KeyError("Expected 'atr_pct' in merged data.")

    df = merged.copy()
    df = df[np.isfinite(pd.to_numeric(df["atr_pct"], errors="coerce"))]

    # Ensure atr_pct is in [0,1]
    df["atr_pct"] = pd.to_numeric(df["atr_pct"], errors="coerce").clip(lower=0.0, upper=1.0)

    labels = []
    for i in range(len(cuts) - 1):
        labels.append(f"({cuts[i]:.2f}, {cuts[i+1]:.2f}]")

    df["atr_bucket"] = pd.cut(
        df["atr_pct"],
        bins=cuts,
        labels=labels,
        include_lowest=True,
    )

    rows = []
    for bucket, g in df.groupby("atr_bucket"):
        row = {
            "atr_bucket": str(bucket),
            "n_trades": len(g),
            "pf": compute_pf(g),
            "win_rate": safe_win_rate(g),
            "mean_pnl": pd.to_numeric(g.get("pnl", 0), errors="coerce").fillna(0.0).mean(),
            "median_pnl": pd.to_numeric(g.get("pnl", 0), errors="coerce").fillna(0.0).median(),
            "atr_pct_min": pd.to_numeric(g.get("atr_pct", 0), errors="coerce").fillna(0.0).min(),
            "atr_pct_max": pd.to_numeric(g.get("atr_pct", 0), errors="coerce").fillna(0.0).max(),
        }
        rows.append(row)

    return pd.DataFrame(rows).sort_values("atr_pct_min")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze BTC v1.3 ShockFlip trades/events for H1–H7 filters."
    )
    parser.add_argument("--trades", type=str, required=True, help="Path to BTC_v13_trades.csv")
    parser.add_argument("--events", type=str, required=True, help="Path to BTC_v13_events.csv")
    parser.add_argument(
        "--out_dir",
        type=str,
        default="results/analysis/BTC_v13",
        help="Directory to save analysis summaries",
    )
    parser.add_argument(
        "--print-columns",
        action="store_true",
        help="Print trades/events/merged column schemas for quick verification.",
    )

    args = parser.parse_args()

    trades_path = Path(args.trades)
    events_path = Path(args.events)
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    print(f"[Load] trades: {trades_path}")
    print(f"[Load] events: {events_path}")

    # Load both and optionally echo schemas
    trades_df = pd.read_csv(trades_path)
    events_df = pd.read_csv(events_path)
    if args.print_columns:
        print("\n[Schema] trades columns:")
        print(list(trades_df.columns))
        print("[Schema] events columns:")
        print(list(events_df.columns))

    merged = load_and_join(trades_path, events_path)
    if args.print_columns:
        print("[Schema] merged columns:")
        print(list(merged.columns))

    print(f"[Info] n_trades = {len(merged)}")
    print(f"[Info] overall PF = {compute_pf(merged):.3f}")
    print(f"[Info] overall win_rate = {safe_win_rate(merged):.3f}")

    # H5–H7: path stats
    path_stats = analyze_path_stats(merged)
    path_stats.to_csv(out_dir / "h5_h7_path_stats_by_result.csv", index=False)
    print("\n[H5–H7] Path stats by result:")
    print(path_stats)

    zombies = analyze_zombies(merged, thresholds=(0.5, 1.0))
    zombies.to_csv(out_dir / "h5_zombie_stats.csv", index=False)
    print("\n[H5] Zombie stats (losers with big MFE):")
    print(zombies)

    # H1: prior flow sign
    if "prior_flow_sign" in merged.columns:
        prior_flow_summary = analyze_prior_flow_sign(merged)
        prior_flow_summary.to_csv(out_dir / "h1_prior_flow_sign_summary.csv", index=False)
        print("\n[H1] Prior flow sign summary:")
        print(prior_flow_summary)
    else:
        print("\n[Warn] prior_flow_sign not found in merged; skipping H1 analysis.")

    # H2: price-flow divergence
    if "price_flow_div" in merged.columns:
        pf_div_summary = analyze_price_flow_div(merged, n_bins=5)
        pf_div_summary.to_csv(out_dir / "h2_price_flow_div_summary.csv", index=False)
        print("\n[H2] Price-flow divergence summary:")
        print(pf_div_summary)
    else:
        print("\n[Warn] price_flow_div not found in merged; skipping H2 analysis.")

    # H3: ATR percentile regimes
    if "atr_pct" in merged.columns:
        atr_summary = analyze_atr_pct(merged, cuts=(0.0, 0.2, 0.8, 1.0))
        atr_summary.to_csv(out_dir / "h3_atr_pct_summary.csv", index=False)
        print("\n[H3] ATR percentile (vol regime) summary:")
        print(atr_summary)
    else:
        print("\n[Warn] atr_pct not found in merged; skipping H3 analysis.")

    print(f"\n[Done] Analysis summaries saved in: {out_dir}")


if __name__ == "__main__":
    main()
