ShockFlip Research Spec — v1.0 → v1.4 (BTC)
===========================================

Purpose
- Capture a clean, reproducible blueprint of the ShockFlip research spec from v1.0 to v1.4.
- Provide best‑practice runbooks and scripts for IS/OOS evaluation, analysis, and future promotion.

Scope
- BTCUSDT‑centric, but general enough to apply to other symbols once validated.
- Engine invariants remain sacred: ATR(60); Donchian(120); SL‑wins tie‑break; TP/SL multipliers.

Version Evolution

- v1.0 (initial)
  - Detector: z_window=240, z_band=2.5, jump_band=3.0, persistence=6@0.60, dynamic on (99th pct), Donchian(120).
  - Outcome: Starved in some slices; cond_jump never true when |z|max < 3.

- v1.1 (open gates)
  - z_band=1.8, jump_band=2.0, persistence=3@0.50, dynamic off.
  - Outcome: Healthy event/trade counts; basis for baseline.

- v1.2 (IS‑anchored)
  - z_band=2.0, jump_band=1.8, persistence=3@0.50, dynamic off.
  - Outcome: Slightly tighter magnitude; validated as a stable research baseline.

- v1.3 (explicit persistence)
  - v1.2 + persistence_ratio explicitly 0.60.
  - Outcome: Clear config, consistent across runs.

- v1.4 (proposed; BTC research spec)
  - v1.3 + H1 Prior Flow Sign filter (promoted).
  - H2 Price–Flow Divergence dead‑zone (candidate; optional in engine until validated).
  - H5/H7 Breakeven stop at X·R (candidate; optional).

Best Practices (Golden Game)
- Verify schema at each stage. Print `df.columns` where new features should land (features, events, trades).
- Keep analysis defensive. If a column is missing, warn and skip instead of crashing.
- Freeze engine spec per version; promote exactly one change per iteration.
- IS/OOS split by directory. Do not mix months in a single folder when evaluating.
- Preserve parity and invariants; never change SL‑wins tie‑break.

v1.3 Engine (current, frozen)

```
data:
  include: data.yaml

slippage_bp: 0.5
fees:
  taker_bp: 1.0

risk:
  atr_window: 60
  cooldown_bars: 10
  long:
    tp_mult: 27.5
    sl_mult: 9.0
  short:
    tp_mult: 15.0
    sl_mult: 6.5

shock_flip:
  source: "imbalance"
  z_window: 240
  z_band: 1.8
  jump_band: 2.0
  persistence_bars: 3
  persistence_ratio: 0.60
  dynamic_thresholds:
    enabled: false
    percentile: 0.99
  location_filter:
    donchian_window: 120
    require_extreme: true

filters:
  atr_percentile:
    enabled: false
    window: 5000
    low: 0.30
    high: 0.80
  macro_regime:
    enabled: false
  prior_flow_sign:        # H1 (promoted in v1.4; optional here)
    enabled: true         # set false to disable
    required_sign: -1
```

Research Features (H1–H3)
- H1 prior_flow_sign (rolling signed flow sum → sign in {−1,0,+1}).
- H2 price_flow_div (z(log‑price change over window) − z(rolling flow sum)).
- H3 atr_pct (percentile of ATR across sample; proxy for vol regime).

Post‑Path Instrumentation (H5–H7)
- mfe_price/mae_price (max favourable/adverse excursion in price units).
- mfe_r/mae_r (normalized excursions in R units, where 1R = ATR × SL_mult at entry).
- time_to_mfe_bars, holding_period_bars.

v1.4 — BTC Research Spec (Blueprint)
- v1.3 +:
  - H1 Prior Flow Sign Filter (promoted)
    - Gate entries to `prior_flow_sign == -1`.
  - H2 Price–Flow Divergence Filter (candidate)
    - Exclude “dead‑zone” div values (approx −0.0741 < div ≤ 0.26) from entries.
  - H5/H7 Breakeven Stop (candidate)
    - Move SL to entry once unrealized ≥ X·R (start with X=1.0R). Disable with 0.0.

Example v1.4 Config (blueprint)

```
# ShockFlip v1.4 – BTC research spec (BLUEPRINT)

data:
  include: data.yaml

slippage_bp: 0.5
fees:
  taker_bp: 1.0

risk:
  atr_window: 60
  cooldown_bars: 10
  long:
    tp_mult: 27.5
    sl_mult: 9.0
  short:
    tp_mult: 15.0
    sl_mult: 6.5

management:            # H5/H7 – Zombie Killer (0.0 disables)
  be_at_r: 1.0

shock_flip:
  source: "imbalance"
  z_window: 240
  z_band: 2.0
  jump_band: 2.0
  persistence_bars: 3
  persistence_ratio: 0.60
  dynamic_thresholds:
    enabled: false
    percentile: 0.99
  location_filter:
    donchian_window: 120
    require_extreme: true

filters:
  atr_percentile:
    enabled: false
    window: 5000
    low: 0.30
    high: 0.80
  macro_regime:
    enabled: false
  # H1 (promoted): engine reads filters.prior_flow_sign
  prior_flow_sign:
    enabled: true
    required_sign: -1
  # H2 (candidate): engine logic TBD; analysis suggests excluding this band
  h2_div_dead_zone:
    enabled: true
    min: -0.0741
    max: 0.26

session:
  utc_blocks: [[0, 24]]

event_study:
  horizons:
    long:  [12, 18, 60]
    short: [6, 12]
  baseline_n_random: 2000
```

IS/OOS Procedure (PowerShell examples)

- Set IS data (`configs/data.yaml`): `tick_dir: data/ticks/BTCUSDT_IS`.
  - Backtest: `python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml --out results/backtest/IS/trades_v13.csv --debug`
  - Event study: `python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml --events_out results/event_study/IS/events_v13.csv --summary_out results/event_study/IS/summary_v13.csv`

- Set OOS data (`configs/data.yaml`): `tick_dir: data/ticks/BTCUSDT_OOS`.
  - Backtest: `python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml --out results/backtest/OOS/trades_v13.csv --debug`
  - Event study: `python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml --events_out results/event_study/OOS/events_v13.csv --summary_out results/event_study/OOS/summary_v13.csv`

Analysis & Reporting
- PF by side: `python scripts/compute_pf_by_side.py --trades results/backtest/OOS/trades.csv --out results/backtest/OOS/pf_by_side.csv`
- Micro‑grid sweep: `python scripts/run_shockflip_sweep.py --config configs/strategies_shockflip_only.yaml --out results/sweeps/shockflip_micro_grid.csv`
- H1–H7 summaries: `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v13_trades.csv --events results/event_study/BTC_v13_events.csv --out_dir results/analysis/BTC_v13 --print-columns`

Minimal Run Commands (copy/paste)
- Backtest (write trades):
  - `python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml --out results/backtest/BTC_v13_trades.csv --debug`
- Analyze H1–H7 filters on those trades (requires events CSV to exist):
  - `python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v13_trades.csv --events results/event_study/BTC_v13_events.csv --out_dir results/analysis/BTC_v13`

  - OR:
  python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml --events_out results/event_study/BTC_v14_h1_events.csv --summary_out results/event_study/BTC_v14_h1_summ
  
  - If you haven’t generated events yet, run:
    - `python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml --events_out results/event_study/BTC_v13_events.csv --summary_out results/event_study/BTC_v13_summary.csv`

Promotion Rules
- Promote exactly one change at a time.
- Require measurable improvement (PF/DD) on IS and OOS.
- Keep parity sacred; validate research vs live‑style paths.
- After BTC stabilizes, attempt cross‑symbol validation (e.g., ETH).

Phased Evaluation Plan (with commands)
--------------------------------------

Pre‑Req
- Set combined 7‑month data in `configs/data.yaml`: `tick_dir: data/ticks/BTCUSDT`.
- Keep H1 live (filters.prior_flow_sign.enabled: true, required_sign: -1).

Phase A — H1 + BE@1R (no H2)
- YAML toggles (in `configs/strategies_shockflip_only.yaml`):
```
filters:
  prior_flow_sign:
    enabled: true
    required_sign: -1
  price_flow_div:
    enabled: false

risk:
  mfe_breakeven:
    enabled: true
    threshold_r: 1.0
```
- Commands (PowerShell one‑liners):
```
python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml --out results/backtest/BTC_v14_h1_be1r_trades.csv --debug
python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml --events_out results/event_study/BTC_v14_h1_be1r_events.csv --summary_out results/event_study/BTC_v14_h1_be1r_summary.csv
python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v14_h1_be1r_trades.csv --events results/event_study/BTC_v14_h1_be1r_events.csv --out_dir results/analysis/BTC_v14_h1_be1r --print-columns
```
- Expect: BE exits labeled as `result="BE"`; check PF, max drawdown, and zombie stats in the analysis output.

Phase B — H1 + H2 (BE off)
- YAML toggles:
```
filters:
  prior_flow_sign:
    enabled: true
    required_sign: -1
  price_flow_div:
    enabled: true
    dead_zone_low: -0.07     # tune from H2 buckets
    dead_zone_high: 0.26

risk:
  mfe_breakeven:
    enabled: false
```
- Commands:
```
python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml --out results/backtest/BTC_v15_h1_h2_trades.csv --debug
python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml --events_out results/event_study/BTC_v15_h1_h2_events.csv --summary_out results/event_study/BTC_v15_h1_h2_summary.csv
python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v15_h1_h2_trades.csv --events results/event_study/BTC_v15_h1_h2_events.csv --out_dir results/analysis/BTC_v15_h1_h2 --print-columns
```
- Compare to Phase A baseline: n, PF, max drawdown. If H2 improves PF/DD and holds IS/OOS, consider promotion.

Phase C — H1 + H2 + BE@1R
- YAML toggles:
```
filters:
  prior_flow_sign:
    enabled: true
    required_sign: -1
  price_flow_div:
    enabled: true
    dead_zone_low: -0.07
    dead_zone_high: 0.26

risk:
  mfe_breakeven:
    enabled: true
    threshold_r: 1.0
```
- Commands:
```
python scripts/run_backtest.py --config configs/strategies_shockflip_only.yaml --out results/backtest/BTC_v16_h1_h2_be1r_trades.csv --debug
python scripts/run_event_study.py --config configs/strategies_shockflip_only.yaml --events_out results/event_study/BTC_v16_h1_h2_be1r_events.csv --summary_out results/event_study/BTC_v16_h1_h2_be1r_summary.csv
python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v16_h1_h2_be1r_trades.csv --events results/event_study/BTC_v16_h1_h2_be1r_events.csv --out_dir results/analysis/BTC_v16_h1_h2_be1r --print-columns
```
- Confirm combined effect; re‑check PF, max drawdown, and BE/SL breakdown.

ShockFlip_BTC_v1.5 (Locked Spec)
---------------------------------

- Definition: H1 + H2 + BE@1R on top of the v1.3 detection core.
- Config file: `configs/strategies_shockflip_btc_v15.yaml`
- Rationale:
  - H1 improves PF by removing misaligned prior‑flow entries.
  - H2 removes the divergence dead‑zone; pushes the book toward extreme |div| tails.
  - BE@1R protects downside once a trade proves itself; reduces drawdown without harming PF.
- Example commands:
```
python scripts/run_backtest.py --config configs/strategies_shockflip_btc_v15.yaml --out results/backtest/BTC_v15_h1_h2_be1r_trades.csv --debug
python scripts/run_event_study.py --config configs/strategies_shockflip_btc_v15.yaml --events_out results/event_study/BTC_v15_h1_h2_be1r_events.csv --summary_out results/event_study/BTC_v15_h1_h2_be1r_summary.csv
python scripts/analyze_v13_filters.py --trades results/backtest/BTC_v15_h1_h2_be1r_trades.csv --events results/event_study/BTC_v15_h1_h2_be1r_events.csv --out_dir results/analysis/BTC_v15_h1_h2_be1r --print-columns
```
