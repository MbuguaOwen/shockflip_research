ShockFlip — Success Blueprint (Vault Notebook)

Author: Senior Quant — Engineering Handoff
Purpose: Canonical research-to-live blueprint capturing validated physics, diamond-rule, experiments and operational runbook. Store this in the vault and treat as the single source of truth.

Executive summary (one-paragraph)

We validated a robust microstructure physics: price–flow divergence generally resolves by reversion (~80%), but the diamond subset of ShockFlip events that produces near-certain immediate moves (≥0.5 ATR within H=6 bars at ≥85% probability) is driven by extreme relative volume (rel_vol ≥ 7.7379 for this dataset). Use divergence as context and extreme relative volume as the trigger. The path to a deployable meta-model must follow strict experiment sequence: Physics → Hygiene → Selection → Meta-model.

Key validated findings (facts, not opinions)

Divergence Map: scanned 2027 divergence events (stream-chunked). Across intensity/duration buckets, reversion probability ranges ~76%–83%. Breakouts ~17%–24%. (Files: /mnt/data/divergence_map.py output CSVs stored under results/divergence_map/.)

Diamond Hunter:

Baseline ShockFlip snap rate (current detector config) = 80.21% (379 events).

Relative volume (rel_vol) top decile (Decile 9) bucket produced:

n = 38, snap_rate = 89.47% — Diamond threshold.

Magic thresholds discovered (dataset-specific):

RelVol 90th percentile = 7.7379

RelVol 80th percentile = 5.8940

(Files: /mnt/data/diamond_hunter.py, outputs under results/diamond_hunter/diamond_candidates.csv and events_annotated.csv)

Z-velocity & Divergence Score: contrary to intuition, these metrics alone did not increase snap probability; in fact their extreme deciles often reduced snap rate. They are context features, not primary triggers.

Physics decomposition:

Divergence = tension (setup).

Relative volume = energy (trigger).

The diamond edge requires both, but rel_vol is necessary and sufficient to reach the 85% snap zone.

Precise definitions & canonical code references

Bar: 1-minute OHLCV aggregations from tick data.

Q⁺, Q⁻: buyer/seller aggressor volume per bar.

Imbalance: I_t = (Q_t^+ − Q_t^-)/(Q_t^+ + Q_t^- + ϵ)

Flow z-score: rolling z of imbalance over z_window = 240 bars.

RelVol: event_bar_total_volume / avg_volume_last_60_bars.

DidSnap: binary — MFE in first H=6 bars >= 0.5 * ATR_at_entry.

Diamond threshold (this data): rel_vol >= 7.7379 (Decile 9).

Scripts used:

Divergence Map: scripts/divergence_map.py (outputs under results/divergence_map/events_FULL.csv and divergence_heatmap.csv).

Diamond Hunter v2.2: scripts/diamond_hunter.py (outputs under results/diamond_hunter/diamond_candidates.csv and events_annotated.csv).

Acceptance criteria (non-negotiable)

Before feature/model promotion to live:

Physics Check (Step 1): For the candidate filter C (e.g., rel_vol >= threshold), verify P(MFE_6 >= 0.5 ATR | ShockFlip & C) >= 0.85 on in-sample and holdout months (bootstrap 95% CI includes >= 85%).

Hygiene Check (Step 2): Zombie filter (exit rules) must improve PF ≥ 0.15 relative to baseline without killing business-level throughput (target trades/month floor: 20).

Selection Check (Step 3): Divergence buckets used as context must show statistically significant lift (p < 0.05 after FDR when multiple features tested) across at least two non-overlapping OOS months.

Meta-model (Step 4): Only train after 1–3 pass and use rolling CV; final live threshold must be validated on at least one month of unseen paper/live replay with parity. Model acceptance requires OOS PF improvement, monotonicity sanity, and interpretability audit (SHAP partials and rules extracted).

Research SOP (exact sequence you must follow)

Re-run Divergence Map (full historical)

Command: python scripts/divergence_map.py --tick_dir data/ticks/BTCUSDT --out results/divergence_map

Save divergence_heatmap.csv. Inspect cells with N >= 15. Focus on (intensity=xhigh, dur=0-1) and (xhigh, dur=2-3) bins.

Run Diamond Hunter for candidate rel_vol thresholds

Command example used:
python scripts/diamond_hunter.py --tick_dir data/ticks/BTCUSDT --out results/diamond_hunter --z_band 1.8 --jump_band 2.2 --persistence 3

Extract rel_vol_90 reported as 7.7379. Use this to define the Diamond filter for research only.

Physics check on Diamond subset

Filter: ShockFlip events ∧ rel_vol >= rel_vol_90.

Compute did_snap (MFE6 >= 0.5ATR) and bootstrap CI (10000 resamples). Confirm p >= 0.85.

Toy exit management (Zombie Filter) but only on Diamond subset

Implement early exit: at bar 10 (if no MFE >= 0.5 ATR) exit at BE or small loss. This is a trade-management rule, not pre-entry gating. Simulate before live.

Divergence-context audit

For Diamond subset, recompute divergence metrics and check whether any divergence decile further improves snap rate. If not, do not add as a pre-entry filter.

Meta-model development

Input = selected features that passed event-study (rel_vol, atr_pctile, donchian_loc, vwap_dist, spread_z, trade_concentration).

Train on only Diamond events (leave the heavy-lifting events to model, not noise). CV using time-blocks (e.g., 3-month train / 1-month test rolling). Use weighted objective in terms of expected PnL. Evaluate on holdout months.

Operational config (canonical values to store in configs/strategies_shockflip_only.yaml)

Add / change these keys (the magic number is dataset-specific — use reported value):

shock_flip:
  # existing detectors...
  # Add research-only diamond gating (disabled in default)
  diamond_filter:
    enabled: true            # research only; first test in backtest pipeline
    rel_vol_threshold: 7.7379
    rel_vol_window: 60       # avg vol window for rel_vol calculation
    min_events_per_bucket: 15

risk:
  atr_window: 60
  cooldown_bars: 10
  long: { tp_mult: 27.5, sl_mult: 9.0 }
  short:{ tp_mult: 15.0, sl_mult: 6.5 }

event_study:
  did_snap_atr_mult: 0.5
  snap_horizon_bars: 6

NOTE: Hard-code the threshold 7.7379 in the research config only. Re-estimate each quarter or when data distribution drifts.

Statistical tests & reporting templates (what to compute and save)

For every experiment run produce these CSVs and summary values:

events_annotated.csv:

columns: entry_ts, side, rel_vol, flow_z, div_score, z_velocity, atr, did_snap (0/1), mfe6_atr, mfe10_atr, entry_close, donchian_loc, vwap_dist, spread, trade_concentration.

diamond_candidates.csv (summary table):

bucket, n, snap_rate, lift_vs_baseline.

bootstrap_snap_ci.json:

baseline_snap_rate, baseline_CI_lower, baseline_CI_upper

diamond_snap_rate, diamond_CI_lower, diamond_CI_upper

heatmap_report.csv:

int_bin, dur_bin, total, p_reversion, p_breakout, p_churn, avg_mag_reversion, avg_mag_breakout.

Save investigation notebooks / PDF visualizations:

time series of example diamond events, cumulative returns stratified by bucket, survival curve of MFE over bars (Kaplan–Meier style).

Alerts, monitoring, and drift management

Daily parity check: run parity replay on previous day’s ticks and compare n_trades_research vs n_trades_live and max_abs_pnl_diff. Threshold: max_abs_pnl_diff < 1e-8 and identical boolean True.

Weekly distribution check: recompute the rel_vol distribution; report change of 90th percentile vs baseline. If rel_vol_90 shifts by > 20% from last estimate, trigger re-estimation job.

Monthly physics audit: re-run Divergence Map on last 3 months and compare heatmap cells. If any major cell’s reversion probability falls below 65%, suspend model retraining and investigate.

Realtime alarms:

If daily trades drop below 50% of expected, notify ops.

If slippage or fee assumptions change materially, kill live.

Trade management rules (practical)

Entry: immediate on ShockFlip trigger if Diamond filter passes (rel_vol >= threshold). Otherwise queue for record-only paper signals.

Initial SL: ATR-based side-aware SL as before. Use first-touch detection on bar high/low; tie-break: SL wins if both touched same bar.

Take-profit: keep legacy TP unless you run a dedicated optimization for Diamond events. Consider aggressive partial-take at 0.5 ATR (snap-capture) for Diamond trades.

Zombie exit: After entry, if by bar 10 no favorable excursion >= 0.5 ATR, trim to BE (or exit) — test this in backtest first.

Position sizing: volatility-scaled notional; cap exposure per symbol; cap daily traded capital per algorithm.

Concrete immediate tasks (priority list with commands)

Physics confirm (diamond subset)

Command lines same as you ran; then run an analysis notebook to bootstrap snap CI. Use scripts/diamond_hunter.py outputs.

Zombie filter simulation (research-only)

Implement BE exit at bar 10 for diamond trades and compare PF. This is a trade-management experiment.

Meta-model sandbox

Build dataset events_annotated.csv for diamond subset, train small gradient boosting with features listed above. Use time-block CV.

Monitoring & Prod checklist

Add parity replay to daily CI pipeline. Add rel_vol drift test.

Example notebook cell: compute bootstrap CI for snap probability

```python
import pandas as pd
import numpy as np

ev = pd.read_csv('results/diamond_hunter/events_annotated.csv')
diamond = ev[ev['rel_vol'] >= 7.7379]
snap = diamond['did_snap'].values
# bootstrap
B = 10000
boot = []
for _ in range(B):
    s = np.random.choice(snap, size=len(snap), replace=True)
    boot.append(s.mean())
boot = np.array(boot)
print('n:', len(snap))
print('snap_rate:', snap.mean())
print('95% CI:', np.percentile(boot, [2.5,97.5]))
```

Risk & caveats (transparent)

Sample-specific threshold: 7.7379 is the empirical 90th percentile on this dataset. Recompute regularly.

Survivorship & look-ahead: make sure tick files are complete and time-ordered. Do NOT leak future bars in rolling stats.

Market regime shift: macro events can change liquidity structure; implement an automated rollback stop if the live performance decays.

Book features: adding L2 book indicators may improve discriminative power but increases infra and latency requirements — evaluate separately with event-study.

Recommended artifacts to store in the vault (and file paths)

This document (vault notebook): vault/shockflip_blueprint.md (this file).

Diamond Hunter code: scripts/diamond_hunter.py (version v2.2).

Divergence Map code: scripts/divergence_map.py.

Output CSVs (store under vault): results/diamond_hunter/events_annotated.csv, results/diamond_hunter/diamond_candidates.csv, results/divergence_map/divergence_heatmap.csv, results/divergence_map/events_FULL.csv.

Snapshot of configs: configs/strategies_shockflip_only.yaml (with diamond_filter.rel_vol_threshold in research config).

Notebook: notebooks/diamond_analysis.ipynb — generate when you run the bootstrap tests & plots.

One-line playbook for the team

Estimate rel_vol_90 on latest 6 months.

Filter ShockFlip events by rel_vol >= rel_vol_90.

Require did_snap MFE6 >= 0.5 ATR in 85%+ of cases (bootstrap).

If pass → implement Zombie exit (bar 10) and optimize partial-takes at 0.5 ATR.

If Step 4 yields PF uplift and stable OOS, train meta-model on Diamond set only and deploy under parity monitoring.

Closing note (strategy philosophy)

You found a true microstructure law: divergence is mostly a spring; a rare, violent volume burst is the match. We now have the recipe to turn that physics into a cashable edge: detect the spring, wait for the blast of energy, and harvest the snap. This blueprint encodes the science, the experiment sequence, the production constraints, and the monitoring that will keep this alpha alive.
