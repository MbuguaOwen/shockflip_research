# ShockFlip Research Engine

This project implements the ShockFlip alpha specification.

- Tick ingestion (data/ticks/BTCUSDT/*.csv)
- 1-minute bar aggregation
- Order-flow features (Q+, Q-, delta, imbalance, z-scores)
- ShockFlip detector (v1.0) with:
  - z_window = 240
  - z_band = 2.0
  - jump_band = 2.0
  - persistence = 4 bars @ 50%
  - dynamic thresholds: disabled
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

## ShockFlip v1.0 Reference

- Spec: (z_band=2.0, jump_band=2.0, persistence=4 @ 0.5, Donchian(120), ATR(60), current TP/SL)
- Event frequency: see notes.md for latest figures
- Backtest stats: see notes.md for latest n / win / PF on the reference slice

To print lightweight diagnostics during development, add `--debug` to the runner commands. To disable progress bars, add `--no-progress`.

## Research Blueprint (v1.0 → v1.4)

- See `docs/shockflip_v1_blueprint.md` for a complete, reproducible walkthrough from v1.0 to v1.4.
- Includes best‑practice guidance (schema verification, defensive analysis, one‑promotion‑per‑iteration), and ready‑to‑run commands.
- A blueprint config for v1.4 lives at `configs/strategies_shockflip_v1_4_blueprint.yaml` (H1 promoted; H2/BE listed as candidates).

Backtest trades are written to:

- `results/backtest/trades.csv`

Event-study outputs:

- `results/event_study/events.csv`
- `results/event_study/summary.csv`

Parity replay writes a simple report to:

- `results/parity/parity_report.json`

## Parameter Sweep (Micro-grid)

Run a 27-point micro-grid around ShockFlip v1.0 to inspect event frequency, backtest stats, and event-study lifts:

```bash
python scripts/run_shockflip_sweep.py --config configs/strategies_shockflip_only.yaml --out results/sweeps/shockflip_micro_grid.csv
```

Grid:
- `z_band` in {1.8, 2.0, 2.2}
- `jump_band` in {1.8, 2.0, 2.2}
- `persistence_bars` in {3, 4, 5}

Recorded per grid point:
- Detector: n_shockflip_long, n_shockflip_short, n_events
- Backtest: n_trades, win_rate, pf
- Event-study: counts/means/lifts for long {12,18,60} and short {6,12}
