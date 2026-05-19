# Survival Governance

Last updated: 2026-05-09 KST

## Prime directive

This dashboard is optimized for survival first, not prediction impressiveness.

The system should prefer:
- wait over forced action
- small size over overconfidence
- invalidation over narrative attachment
- failure pattern logging over self-justification

## Current automation layers

### 1. Market Regime

`marketRegime` classifies the broad market before stock-level judgment.

States:
- `RISK_OFF`
- `CAUTION`
- `UNKNOWN`
- `NEUTRAL`
- `RISK_ON`

Each state carries `strategyPolicy`:
- `maxPositionPct`
- `entryRule`
- `confidenceCap`
- `plain`

The confidence cap prevents a stock from looking too actionable in a hostile market.

### 2. Survival analysis

Each stock's `expertAnalysis.survival` contains:
- `confidenceScore`
- `confidenceLevel`
- `actionState`
- `positionGuide`
- `marketRegime`
- `sectorProfile`
- `sectorRulesApplied`
- `signalConflicts`
- `invalidationRules`
- `failureRiskPatterns`

### 3. Sector weighting

Sector-specific weighting is applied after generic score generation.

Current profiles:
- semiconductor/electronics
- bio/pharma
- financial
- battery
- general fallback

### 4. Survival ledger

`data/survival-ledger.json` records every tracked survival decision.

Important fields:
- `firstSeenAt`
- `baselinePrice`
- `lastPrice`
- `returnSinceFirstPct`
- `actionState`
- `confidenceScore`
- `positionRangePct`
- `riskPatterns`
- `failurePatterns`
- `horizonReview` for 1d/5d/20d

`horizonReview` is deliberately explicit for every tracked row. Each of
`1d`, `5d`, and `20d` must exist with a status of `pending`,
`ready-for-review`, or `ready-missing-return`; longer horizons may remain
pending until the first-seen timestamp is old enough. `failurePatterns` must
stay populated from realized drawdown/missed-upside evidence when available,
otherwise from the risk patterns captured at decision time.

### 5. Survival review

`data/survival-review.json` summarizes:
- `survivalScore`
- no-trade ratio
- action counts
- confidence counts
- `topFailurePatterns` (coded summary derived from row-level `failurePatterns`)
- high-risk samples
- baseline tracking counts
- horizon status counts for 1d/5d/20d

The audit gate must fail if either the embedded dashboard `survivalReview` or
standalone `data/survival-review.json` loses the coded top failure-pattern
summary, or if their summaries drift apart.

## Non-negotiable rules

1. Never interpret score as a direct buy signal.
2. Always show confidence separately.
3. Always show position range.
4. Always preserve wait/no-trade as a valid output.
5. Always preserve invalidation rules.
6. Never let market risk be hidden under stock-specific optimism.
7. Treat missed upside during wait as a review item, not automatically a mistake.
8. Treat drawdown as a survival warning even if the original explanation sounded good.

## Next hardening priorities

1. Add regime history, not just current regime.
2. Add sector-specific regime impact matrix.
3. Add failure-pattern dashboard drilldown.
4. Add automatic 1d/5d/20d review report.
5. Add candidate-level price baselines for all non-held stocks.
6. Add explicit cash/risk budget policy per strategy.
