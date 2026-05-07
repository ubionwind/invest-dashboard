# Survival System Backlog

## P0 — already active

- [x] Confidence separate from score
- [x] Position guide
- [x] Wait/no-trade first-class state
- [x] Invalidation rules
- [x] Market Regime layer
- [x] Sector profile weighting
- [x] Survival ledger
- [x] Failure pattern candidates
- [x] Baseline price tracking
- [x] Survival review summary

## P1 — next development

- [ ] Regime history series
- [ ] Sector x Regime impact matrix
- [ ] Failure-pattern drilldown page/card
- [ ] 1d/5d/20d review report generator
- [ ] Strategy-specific max exposure budget
- [ ] Cash/risk budget visual card
- [ ] Candidate vs held-stock separate survival scores
- [ ] “Missed upside while waiting” review semantics

## P2 — validation and learning

- [ ] Explanation quality vs return separation
- [ ] Pattern precision tracking
- [ ] False-positive risk pattern tracking
- [ ] Conservative-wait opportunity cost tracking
- [ ] Drawdown by actionState
- [ ] Drawdown by confidence bucket
- [ ] Drawdown by marketRegime
- [ ] Drawdown by sectorProfile

## Guardrails

- No order execution changes unless explicitly requested.
- No widening of auto-order target sessions.
- No public/external sending from automation unless explicitly configured.
- Read-only market/fundamental/news data only for analysis hardening.
