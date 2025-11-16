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

## ShockFlip_BTC_v1.5

- Locked BTC spec combining H1 + H2 + BE@1R.
- Config: `configs/strategies_shockflip_btc_v15.yaml`
- Quick run commands (PowerShell one‑liners):
  - `python scripts/run_backtest.py --config configs/strategies_shockflip_btc_v15.yaml --out results/backtest/BTC_v15_h1_h2_be1r_trades.csv --debug`
  - `python scripts/run_event_study.py --config configs/strategies_shockflip_btc_v15.yaml --events_out results/event_study/BTC_v15_h1_h2_be1r_events.csv --summary_out results/event_study/BTC_v15_h1_h2_be1r_summary.csv`
  - `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v15_h1_h2_be1r_trades.csv --events results/event_study/BTC_v15_h1_h2_be1r_events.csv --out_dir results/analysis/BTC_v15_h1_h2_be1r --print-columns`

Backtest trades are written to:

- `results/backtest/trades.csv`

Event-study outputs:

- `results/event_study/events.csv`
- `results/event_study/summary.csv`

Parity replay writes a simple report to:

- `results/parity/parity_report.json`

## ShockFlip_BTC_v1.6 (v16)

- BTC spec that halves SL distance and adds optional R-based trailing stops.
- Entries are identical to v1.5 (ShockFlip core + H1 gate + H2 extreme-only); only risk management changes.
- Config: `configs/strategies_shockflip_btc_v16.yaml`

What changed vs v1.5
- SL halved: long `sl_mult: 4.5` (was 9.0), short `sl_mult: 3.25` (was 6.5).
- Trailing stop (config-driven; default OFF):
  - Arms when best MFE ≥ `arm_threshold_r` (default 3.0R)
  - Never gives back below `floor_r` (default 2.5R)
  - Trails at a wide `gap_r` behind best MFE (default 1.0R)
  - Coexists with BE: first move SL to entry at BE threshold if enabled; trailing then ratchets beyond entry.

Quick runs (PowerShell one-liners)

- Baseline v1.6: half SL, trailing OFF
  - `python scripts/run_backtest.py --config configs/strategies_shockflip_btc_v16.yaml --out results/backtest/BTC_v16_halfSL_noTrail_trades.csv --debug`
  - `python scripts/run_event_study.py --config configs/strategies_shockflip_btc_v16.yaml --events_out results/event_study/BTC_v16_halfSL_noTrail_events.csv --summary_out results/event_study/BTC_v16_halfSL_noTrail_summary.csv`
  - `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v16_halfSL_noTrail_trades.csv --events results/event_study/BTC_v16_halfSL_noTrail_events.csv --out_dir results/analysis/BTC_v16_halfSL_noTrail --print-columns`

- Trailing ON (edit YAML: set `risk.trailing_stop.enabled: true`)
  - `python scripts/run_backtest.py --config configs/strategies_shockflip_btc_v16.yaml --out results/backtest/BTC_v16_trail3R_trades.csv`
  - `python scripts/run_event_study.py --config configs/strategies_shockflip_btc_v16.yaml --events_out results/event_study/BTC_v16_trail3R_events.csv --summary_out results/event_study/BTC_v16_trail3R_summary.csv`
  - `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v16_trail3R_trades.csv --events results/event_study/BTC_v16_trail3R_events.csv --out_dir results/analysis/BTC_v16_trail3R`

Compare per run
- `overall_summary.csv` in the analysis folder (PF, win_rate, maxDD).
- `h5_mfe_mae_by_result.csv` for MFE/MAE quantiles (are winners extended, are BE trades healthier?).
- `h5_zombie_stats.csv` (share of losers that once had large MFE; lower is better).

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
