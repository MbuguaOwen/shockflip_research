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

---

ShockFlip_BTC_v1.5 — Locked Results (7‑month BTC)
=================================================

Spec
- Detection (v1.3 core): z_band=2.0, jump_band=2.0, persistence_bars=3, persistence_ratio=0.60, Donchian(120), dynamic off.
- H1 gate: prior_flow_sign == -1 (enabled)
- H2 gate: price_flow_div dead‑zone: 0.32 < div ≤ 0.86 (enabled)
- BE management: BE@1R (enabled)

Headline Metrics
- Trades (total): ~234
- PF: ~1.351
- Win rate: ~0.239
- Max drawdown: ~−13.8%

Path Stats (example split)
- BE: ~68
- SL: ~110
- TP: ~56

Zombie Stats (example)
- ≥0.5R losers: ~92 (share ≈ 0.39)
- ≥1.0R losers: ~68 (share ≈ 0.29)

H2 Buckets (example PF)
- Big positive div tail: ~2.8 PF
- Middle positive div: ~0.69 PF (worst)

Run Commands
- Backtest: `python scripts/run_backtest.py --config configs/strategies_shockflip_btc_v15.yaml --out results/backtest/BTC_v15_h1_h2_be1r_trades.csv --debug`
- Event study: `python scripts/run_event_study.py --config configs/strategies_shockflip_btc_v15.yaml --events_out results/event_study/BTC_v15_h1_h2_be1r_events.csv --summary_out results/event_study/BTC_v15_h1_h2_be1r_summary.csv`
- Analysis: `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v15_h1_h2_be1r_trades.csv --events results/event_study/BTC_v15_h1_h2_be1r_events.csv --out_dir results/analysis/BTC_v15_h1_h2_be1r --print-columns`

