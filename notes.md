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

---

ShockFlip_BTC_v1.6 — Half SL + Trailing (Design, Commands, Progress)
====================================================================

Spec Changes vs v1.5
- Risk (SL halved):
  - Long: `sl_mult = 4.5` (was 9.0)
  - Short: `sl_mult = 3.25` (was 6.5)
- Trailing stop module (R-based; default OFF):
  - `arm_threshold_r` (default 3.0): arm trailing once best MFE ≥ 3R
  - `floor_r` (default 2.5): never let realized R drop below 2.5R once armed
  - `gap_r` (default 1.0): trail ~1R behind best MFE
- Entries unchanged from v1.5:
  - H1 prior_flow_sign gate (require -1)
  - H2 price_flow_div gate (extreme-only; |div| ≥ 1.05)
  - ShockFlip core unchanged (z/jump/persistence/Donchian)

Engine Wiring (where to look)
- Trailing config plumbed like BE/H1/H2:
  - Read from YAML: `scripts/run_backtest.py`, `scripts/run_parity_replay.py`
    - `_trailing_enabled`, `_trailing_arm_r`, `_trailing_floor_r`, `_trailing_gap_r`
  - Applied in sim loop: `core/backtest.py`
    - Precompute 1R = ATR × sl_mult
    - Track best MFE in R and price; arm trailing at threshold
    - Ratchet effective SL: never move against favorable direction; respects BE first
    - Tie-break labeling tweaked so trailing exits above entry (long) or below entry (short) are not mislabeled as SL

How to Run v1.6 (repro commands)
- Baseline: half SL, trailing OFF
  - Backtest: `python scripts/run_backtest.py --config configs/strategies_shockflip_btc_v16.yaml --out results/backtest/BTC_v16_halfSL_noTrail_trades.csv --debug`
  - Event study: `python scripts/run_event_study.py --config configs/strategies_shockflip_btc_v16.yaml --events_out results/event_study/BTC_v16_halfSL_noTrail_events.csv --summary_out results/event_study/BTC_v16_halfSL_noTrail_summary.csv`
  - Analysis: `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v16_halfSL_noTrail_trades.csv --events results/event_study/BTC_v16_halfSL_noTrail_events.csv --out_dir results/analysis/BTC_v16_halfSL_noTrail --print-columns`

- Trailing ON (edit YAML: set `risk.trailing_stop.enabled: true`)
  - Backtest: `python scripts/run_backtest.py --config configs/strategies_shockflip_btc_v16.yaml --out results/backtest/BTC_v16_trail3R_trades.csv`
  - Event study: `python scripts/run_event_study.py --config configs/strategies_shockflip_btc_v16.yaml --events_out results/event_study/BTC_v16_trail3R_events.csv --summary_out results/event_study/BTC_v16_trail3R_summary.csv`
  - Analysis: `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v16_trail3R_trades.csv --events results/event_study/BTC_v16_trail3R_events.csv --out_dir results/analysis/BTC_v16_trail3R`

What to Compare (decision checklist)
- PF higher is better; MaxDD same or lower; n trades not starved.
- MFE/MAE quantiles (by result):
  - TP: are winners extending? does trailing capture >3R legs?
  - BE: does raising BE later (if configured) convert some BE → TP?
- Zombie share (`h5_zombie_stats.csv`): should fall with tighter SL and trailing.

Progress Timeline (v1.3 → v1.6)
1) v1.3 core detector: ShockFlip baseline + ATR(60) risk; fixed TP/SL; no gates.
2) v1.4 H1: promoted prior_flow_sign gate (require -1) from study → entry filter.
3) v1.5 H1 + H2 + BE:
   - H2 showed concentration at extreme |div| ⇒ promoted gating (extreme-only in v15+)
   - BE@1R defended extended TP experiments; reduced give-backs
   - MFE/MAE analysis added: quantiles by result; zombie accounting
4) v1.6 half SL + trailing:
   - Halved SL to cut wrong ideas faster/cheaper (burst regime bias)
   - Trailing: arm at 3R, floor 2.5R, gap 1R (configurable) to tax trend legs rather than capping at fixed TP

Next Experiments (optional)
- Tiny BE grid: threshold_r ∈ {1.0, 1.2, 1.4} on v1.6 to balance give-back vs churn.
- ATR gate: enable `filters.atr_percentile` with `low: 0.80` if you want fewer, higher-quality trades.
- TP scan post v1.6: after trailing results, test small TP grid around current multipliers; keep coarse, avoid overfitting.
