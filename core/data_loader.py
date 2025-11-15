import os
from typing import List, Tuple

import pandas as pd


def list_tick_files(tick_dir: str) -> List[str]:
    """List CSV files under `tick_dir` sorted by name."""
    files = [
        os.path.join(tick_dir, f)
        for f in os.listdir(tick_dir)
        if f.lower().endswith(".csv")
    ]
    return sorted(files)


def _load_single_tick_csv(path: str) -> pd.DataFrame:
    """Load a single tick CSV and normalize columns.

    Expected logical columns:
    - ts (or timestamp/time)
    - price (or p/last_price/close/trade_price)
    - qty (or quantity/size/amount/vol/volume)
    - is_buyer_maker (or common aliases; default False if missing)
    """
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}

    # Timestamp aliases -> 'ts'
    if "ts" in df.columns:
        pass
    elif "timestamp" in cols:
        df = df.rename(columns={cols["timestamp"]: "ts"})
    elif "time" in cols:
        df = df.rename(columns={cols["time"]: "ts"})
    else:
        raise ValueError(f"Missing 'ts' column in {path}")

    # Price alias -> 'price'
    if "price" not in cols:
        for alt in ("p", "last_price", "close", "trade_price"):
            if alt in cols:
                df = df.rename(columns={cols[alt]: "price"})
                break
    if "price" not in df.columns:
        raise ValueError(f"Missing 'price' column in {path}")

    # Qty aliases -> 'qty'
    if "qty" not in cols:
        for alt in ("quantity", "size", "amount", "vol", "volume"):
            if alt in cols:
                df = df.rename(columns={cols[alt]: "qty"})
                break
    if "qty" not in df.columns:
        raise ValueError(f"Missing 'qty' column in {path}")

    # is_buyer_maker aliases -> 'is_buyer_maker'
    if "is_buyer_maker" not in df.columns:
        for alt in ("isbuyermaker", "buyer_is_maker", "is_buyer_mkt_maker", "is_buyer_maker"):
            if alt in cols:
                df = df.rename(columns={cols[alt]: "is_buyer_maker"})
                break
    if "is_buyer_maker" not in df.columns:
        # Treat as non-tick CSV; caller may fallback to bars
        raise ValueError(f"Missing 'is_buyer_maker' column in {path}")

    # Timestamp hygiene: accept epoch millis or ISO strings
    ts = df["ts"]
    try:
        from pandas.api import types as pdt
        is_numeric = pdt.is_numeric_dtype(ts)
    except Exception:
        # Fallback if pandas API surface changes
        is_numeric = ts.dtype.kind in ("i", "u", "f")

    if is_numeric:
        # Treat numeric timestamps as epoch milliseconds (Binance-style)
        # Cast to int64 to avoid float rounding artifacts
        df["ts"] = pd.to_datetime(ts.astype("int64"), unit="ms", utc=True, errors="coerce")
    else:
        # ISO8601-like strings
        df["ts"] = pd.to_datetime(ts, utc=True, errors="coerce")

    df = df.dropna(subset=["ts"])

    # Normalize is_buyer_maker to bool robustly
    if df["is_buyer_maker"].dtype != bool:
        if df["is_buyer_maker"].dtype == object:
            s = df["is_buyer_maker"].astype(str).str.strip().str.lower()
            mapping = {"true": 1, "t": 1, "1": 1, "false": 0, "f": 0, "0": 0}
            s = s.map(mapping)
            s = s.fillna(0)
            df["is_buyer_maker"] = s.astype(int) != 0
        else:
            num = pd.to_numeric(df["is_buyer_maker"], errors="coerce").fillna(0)
            df["is_buyer_maker"] = num.astype(int) != 0

    return df


def load_ticks_from_dir(tick_dir: str) -> pd.DataFrame:
    """Eagerly load all tick CSVs into one DataFrame.

    This may be too heavy for very large histories; the main pipeline now
    prefers `resample_ticks_dir_to_bars` via `load_marketdata_as_bars`.
    """
    files = list_tick_files(tick_dir)
    if not files:
        raise FileNotFoundError(f"No CSV files found in {tick_dir!r}")

    dfs = []
    for path in files:
        df = _load_single_tick_csv(path)
        dfs.append(df)

    ticks = pd.concat(dfs, ignore_index=True)
    ticks = ticks.sort_values("ts").reset_index(drop=True)
    return ticks


def resample_ticks_to_bars(ticks: pd.DataFrame, timeframe: str = "1min") -> pd.DataFrame:
    """Aggregate ticks into OHLCV bars with buy/sell volume.

    - price -> OHLC
    - qty -> volume
    - is_buyer_maker:
        - False => buyer aggressor => Q+
        - True  => seller aggressor => Q-
    """
    if ticks.empty:
        raise ValueError("No ticks provided")

    df = ticks.set_index("ts")

    ohlc = df["price"].resample(timeframe).ohlc()
    vol = df["qty"].resample(timeframe).sum().rename("volume")

    buy_qty = df.loc[~df["is_buyer_maker"], "qty"].resample(timeframe).sum().rename("buy_qty")
    sell_qty = df.loc[df["is_buyer_maker"], "qty"].resample(timeframe).sum().rename("sell_qty")

    bars = pd.concat([ohlc, vol, buy_qty, sell_qty], axis=1)

    # Drop bars without full OHLC
    bars = bars.dropna(subset=["open", "high", "low", "close"])

    # Fill missing buy/sell qty with 0
    bars[["buy_qty", "sell_qty"]] = bars[["buy_qty", "sell_qty"]].fillna(0.0)

    # Ensure sorted by index
    bars = bars.sort_index()

    return bars.reset_index().rename(columns={"ts": "timestamp"})


def load_bars_from_dir(bar_dir: str) -> pd.DataFrame:
    """Load pre-aggregated OHLCV CSVs from `bar_dir`."""
    files = list_tick_files(bar_dir)
    if not files:
        raise FileNotFoundError(f"No CSV files found in {bar_dir!r}")

    dfs = []
    for path in files:
        df = pd.read_csv(path)

        # Normalize timestamp column
        if "timestamp" in df.columns:
            ts_col = "timestamp"
        elif "ts" in df.columns:
            ts_col = "ts"
        elif "open_time" in df.columns:
            ts_col = "open_time"
        else:
            raise ValueError(f"Missing a timestamp column ('timestamp'/'ts'/'open_time') in {path}")

        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                raise ValueError(f"Missing '{col}' column in {path}")

        ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df = df.assign(timestamp=ts)
        df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()

        # Ensure numeric types where possible
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        else:
            df["volume"] = pd.NA

        # Optional buy/sell qty
        if "buy_qty" not in df.columns:
            df["buy_qty"] = 0.0
        if "sell_qty" not in df.columns:
            df["sell_qty"] = 0.0

        dfs.append(df[["timestamp", "open", "high", "low", "close", "volume", "buy_qty", "sell_qty"]])

    bars = pd.concat(dfs, ignore_index=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    if "volume" in bars.columns:
        bars["volume"] = bars["volume"].fillna(0.0)

    return bars


def resample_ticks_dir_to_bars(tick_dir: str, timeframe: str = "1min") -> pd.DataFrame:
    """Streaming-friendly: resample each tick CSV to bars, then concat.

    This avoids holding the full tick history in memory at once.
    """
    files = list_tick_files(tick_dir)
    if not files:
        raise FileNotFoundError(f"No CSV files found in {tick_dir!r}")

    import os as _os
    bars_list = []
    skipped = 0
    for path in files:
        try:
            df = _load_single_tick_csv(path)
        except ValueError as e:
            skipped += 1
            if _os.environ.get("SF_DEBUG"):
                print(f"[Info] Skipping non-tick CSV: {path} ({e})")
            continue
        bars = resample_ticks_to_bars(df, timeframe=timeframe)
        bars_list.append(bars)

    if not bars_list:
        raise ValueError("No valid tick CSVs found for streaming resample")

    all_bars = pd.concat(bars_list, ignore_index=True)
    all_bars = all_bars.sort_values("timestamp").reset_index(drop=True)
    return all_bars


def load_marketdata_as_bars(path: str, timeframe: str = "1min") -> Tuple[pd.DataFrame, str]:
    """Load data directory that may contain either ticks or pre-aggregated bars.

    - If tick-format (`ts`, `price`, `qty`, `is_buyer_maker`) is present, loads
      ticks file-by-file and resamples to bars using `timeframe` without
      materializing the entire tick history in memory at once.
    - Otherwise, attempts to load as OHLC bars.

    Returns: (bars_df, source), where source is 'ticks' or 'bars'.
    """
    try:
        bars = resample_ticks_dir_to_bars(path, timeframe=timeframe)
        return bars, "ticks"
    except (ValueError, KeyError, FileNotFoundError):
        bars = load_bars_from_dir(path)
        return bars, "bars"
