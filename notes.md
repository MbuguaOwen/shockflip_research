ShockFlip v1.0 — Reference Anchor
=================================

Spec Parameters
- Source: imbalance
- z_window: 240
- z_band: 2.0
- jump_band: 2.0
- persistence: 4 bars @ 0.50
- dynamic_thresholds: disabled (percentile 0.99 retained for future use)
- location_filter: Donchian window 120, require_extreme = true
- ATR window: 60
- Risk multipliers:
  - Long: TP = 27.5 × ATR, SL = 9.0 × ATR
  - Short: TP = 15.0 × ATR, SL = 6.5 × ATR
- Execution: first-touch TP/SL, SL wins ties

Event Frequency (to be updated)
- Events (all): <fill after run>
- Long events: <fill after run>
- Short events: <fill after run>
- Data slice: `configs/data.yaml` → `tick_dir` and timeframe

Backtest Stats (to be updated)
- n trades: <fill after run>
- win rate: <fill after run>
- profit factor: <fill after run>
- Output: `results/backtest/trades.csv`

How to Refresh
- Backtest: `python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml`
- Event study: `python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml`
- Parity replay: `python scripts/run_parity_replay.py --config configs/strategies_shockflip_only.yaml`
- Optional diagnostics: append `--debug` to print signal counts and condition pass-through, or set env `SF_DEBUG=1` to see loader notices.

