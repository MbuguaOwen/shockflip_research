# ShockFlip Research Engine

This project implements the ShockFlip alpha specification:

- Tick ingestion (data/ticks/BTCUSDT/*.csv)
- 1-minute bar aggregation
- Order-flow features (Q+, Q-, delta, imbalance, z-scores)
- ShockFlip detector with:
  - z_window = 240
  - z_band = 2.5
  - jump_band = 3.0
  - persistence = 6 bars @ 60%
  - dynamic threshold (99th percentile)
  - Donchian(120) extremes
- ATR(60)-based risk with side-aware TP/SL:
  - Long: TP = 27.5 * ATR, SL = 9.0 * ATR
  - Short: TP = 15.0 * ATR, SL = 6.5 * ATR
- First-touch TP/SL with deterministic tie-break (SL wins ties).
- Backtest + Event Study + Parity replay scripts.

## Folder layout

- core/
  - data_loader.py         # ticks -> 1m bars
  - features.py            # order-flow features, ATR, Donchian
  - shockflip_detector.py  # ShockFlip signal logic
  - barriers.py            # TP/SL construction and PnL logic
  - backtest.py            # ShockFlip-only backtest engine
  - event_study_core.py    # event study utilities
  - parity.py              # simple parity replay harness
  - config.py              # YAML loader with small `include` helper
- configs/
  - data.yaml
  - strategies_shockflip_only.yaml
- scripts/
  - run_backtest.py
  - run_event_study.py
  - run_parity_replay.py
- results/
  - backtest/
  - event_study/
  - parity/
- data/
  - ticks/BTCUSDT/         # put your tick CSVs here

## Tick schema

Each CSV under `data/ticks/BTCUSDT` must have:

- ts (ISO8601 or epoch ms)
- price (float)
- qty (float)
- is_buyer_maker (bool/int; 1 = seller aggressor; 0 = buyer aggressor)

## Quickstart

```bash
# Backtest ShockFlip-only
python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml

# Event-study for ShockFlip
python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml

# Parity replay harness (research vs "live-style" engine)
python scripts/run_parity_replay.py --config configs/strategies_shockflip_only.yaml
```

Backtest trades are written to:

- `results/backtest/trades.csv`

Event-study outputs:

- `results/event_study/events.csv`
- `results/event_study/summary.csv`

Parity replay writes a simple report to:

- `results/parity/parity_report.json`
