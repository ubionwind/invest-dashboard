#!/usr/bin/env python3
"""Audit public investment dashboard analysis data and stock-detail wiring.

Read-only validation. Does not call broker/order APIs.
"""
import collections
import datetime as dt
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'data/test/dashboard-data.json'
LAYERS = ROOT / 'data/layers'
KST = dt.timezone(dt.timedelta(hours=9))


def parse_kst(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(KST)
    except Exception:
        return None


def market_dt(obj):
    if not isinstance(obj, dict):
        return None
    if obj.get('periodEnd'):
        return parse_kst(obj.get('periodEnd'))
    if obj.get('date') and obj.get('time'):
        return parse_kst(f"{obj.get('date')}T{obj.get('time')}+09:00")
    return None


def walk(obj, path=''):
    if isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from walk(value, f'{path}[{i}]')
    elif isinstance(obj, dict):
        if obj.get('code') and (obj.get('fundamentals') or obj.get('returnPct') is not None or obj.get('status')):
            yield path, obj
        for key, value in obj.items():
            yield from walk(value, f'{path}.{key}')


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    errors = []
    warnings = []
    stats = collections.Counter()
    rows = list(walk(data))
    generated_at = parse_kst(data.get('generatedAt'))

    # Decision Contract is the explicit AGENT -> Dashboard translation layer.
    # Every visible trading row must carry the four separated states so UI code
    # does not infer buy/hold/exit/execution meaning from free-text reason fields.
    contract_paths = ('topCandidates', 'buyAlerts', 'sellAlerts', 'sellRecords', 'positions')
    for path, item in rows:
        if not path.startswith('.sessions') or not any(token in path for token in contract_paths):
            continue
        dc = item.get('decisionContract') if isinstance(item, dict) else None
        if not isinstance(dc, dict):
            errors.append((path, item.get('code') if isinstance(item, dict) else '-', 'missing decisionContract'))
            continue
        for key in ['newEntry', 'holding', 'exit', 'execution']:
            if not isinstance(dc.get(key), dict):
                errors.append((path, item.get('code'), f'missing decisionContract.{key}'))
        if not dc.get('plainSummary'):
            errors.append((path, item.get('code'), 'missing decisionContract.plainSummary'))
        if dc.get('execution', {}).get('executed') and dc.get('execution', {}).get('state') != 'EXECUTED':
            errors.append((path, item.get('code'), 'executed row has non-EXECUTED execution state'))

    regime = data.get('marketRegime') or {}
    if regime.get('state') not in {'RISK_OFF', 'CAUTION', 'UNKNOWN', 'NEUTRAL', 'RISK_ON'}:
        errors.append(('marketRegime', '-', 'missing/invalid state'))
    policy = regime.get('strategyPolicy') or {}
    for key in ['maxPositionPct', 'entryRule', 'confidenceCap', 'plain']:
        if policy.get(key) in (None, '', []):
            errors.append(('marketRegime.strategyPolicy', '-', f'missing {key}'))
    review = data.get('survivalReview') or {}
    if review.get('survivalScore') in (None, ''):
        errors.append(('survivalReview', '-', 'missing survivalScore'))
    if review.get('totalRows') in (None, ''):
        errors.append(('survivalReview', '-', 'missing totalRows'))
    if review.get('baselineTrackedCount') in (None, ''):
        errors.append(('survivalReview', '-', 'missing baselineTrackedCount'))
    horizons = review.get('horizonReview') if isinstance(review.get('horizonReview'), dict) else {}
    for key in ['1d', '5d', '20d']:
        h = horizons.get(key) if isinstance(horizons.get(key), dict) else {}
        if h.get('total') in (None, '') or h.get('readyCount') is None or h.get('pendingCount') is None:
            errors.append(('survivalReview.horizonReview', key, 'missing horizon review counts'))
    ledger_path = ROOT / 'data/survival-ledger.json'
    review_path = ROOT / 'data/survival-review.json'
    if not ledger_path.exists():
        errors.append(('data/survival-ledger.json', '-', 'missing survival ledger'))
    else:
        try:
            ledger_file = json.loads(ledger_path.read_text(encoding='utf-8'))
            latest = ledger_file.get('latest') if isinstance(ledger_file.get('latest'), list) else []
            if not latest:
                errors.append(('data/survival-ledger.json', 'latest', 'empty survival latest rows'))
            allowed_horizon_statuses = {'pending', 'ready-for-review', 'ready-missing-return'}
            ledger_horizon_statuses = {key: collections.Counter() for key in ['1d', '5d', '20d']}
            ledger_pattern_count = 0
            ledger_updated_at = parse_kst(ledger_file.get('updatedAt'))
            for idx, row in enumerate(latest):
                if not isinstance(row, dict):
                    errors.append(('data/survival-ledger.json', f'latest[{idx}]', 'row is not an object'))
                    continue
                row_id = f"{row.get('publicId') or '-'}:{row.get('code') or '-'}"
                if row.get('baselinePrice') in (None, '', 0) or row.get('lastPrice') in (None, '', 0):
                    errors.append(('data/survival-ledger.json', row_id, 'missing baseline/last price'))
                if row.get('actionState') in (None, '', []):
                    errors.append(('data/survival-ledger.json', row_id, 'missing actionState'))
                if row.get('confidenceLevel') in (None, '', []):
                    errors.append(('data/survival-ledger.json', row_id, 'missing confidenceLevel'))
                patterns = row.get('failurePatterns')
                if not isinstance(patterns, list):
                    errors.append(('data/survival-ledger.json', row_id, 'missing failurePatterns list'))
                else:
                    ledger_pattern_count += len([p for p in patterns if isinstance(p, dict) and p.get('code')])
                row_horizons = row.get('horizonReview') if isinstance(row.get('horizonReview'), dict) else {}
                first_seen_at = parse_kst(row.get('firstSeenAt') or row.get('ts'))
                for key in ['1d', '5d', '20d']:
                    h = row_horizons.get(key) if isinstance(row_horizons.get(key), dict) else {}
                    status = h.get('status')
                    if status not in allowed_horizon_statuses:
                        errors.append(('data/survival-ledger.json', row_id, f'missing/invalid horizonReview.{key}.status'))
                    ledger_horizon_statuses[key][status or 'missing'] += 1
                    days = int(key[:-1])
                    if first_seen_at and ledger_updated_at and (ledger_updated_at - first_seen_at).total_seconds() >= days * 86400 and not str(status).startswith('ready'):
                        errors.append(('data/survival-ledger.json', row_id, f'horizonReview.{key} should be ready based on firstSeenAt'))
                    if str(status).startswith('ready') and 'returnSinceFirstPct' not in h:
                        errors.append(('data/survival-ledger.json', row_id, f'missing horizonReview.{key}.returnSinceFirstPct'))
            if ledger_pattern_count <= 0:
                errors.append(('data/survival-ledger.json', 'failurePatterns', 'no coded failure patterns found'))
            for key in ['1d', '5d', '20d']:
                if sum(ledger_horizon_statuses[key].values()) != len(latest):
                    errors.append(('data/survival-ledger.json', key, 'horizon count does not cover latest rows'))
        except Exception as exc:
            errors.append(('data/survival-ledger.json', '-', f'invalid json: {exc}'))
    if not review_path.exists():
        errors.append(('data/survival-review.json', '-', 'missing survival review'))
    else:
        try:
            review_file = json.loads(review_path.read_text(encoding='utf-8'))
            # Fast-market refreshes update the dashboard/layer timestamp without
            # rebuilding the survival review. The standalone review file should
            # match the embedded survivalReview snapshot, not necessarily the
            # outer dashboard generatedAt.
            if review_file.get('generatedAt') != review.get('generatedAt'):
                errors.append(('data/survival-review.json', '-', 'generatedAt mismatch'))
            file_horizons = review_file.get('horizonReview') if isinstance(review_file.get('horizonReview'), dict) else {}
            for key in ['1d', '5d', '20d']:
                if key not in file_horizons:
                    errors.append(('data/survival-review.json', key, 'missing horizon review summary'))
        except Exception as exc:
            errors.append(('data/survival-review.json', '-', f'invalid json: {exc}'))

    for key, label in [('benchmark', 'KOSPI'), ('kodexBenchmark', 'KODEX')]:
        obj = data.get(key) or {}
        if obj.get('value') in (None, '', 0):
            errors.append((key, label, 'missing market value'))
        if obj.get('dailyReturnPct') in (None, ''):
            errors.append((key, label, 'missing dailyReturnPct'))
        if obj.get('returnPct') in (None, ''):
            errors.append((key, label, 'missing cumulative returnPct'))
        md = market_dt(obj)
        if generated_at and md:
            age_min = abs((generated_at - md).total_seconds()) / 60
            # Public cards must not mix fresh dashboard data with stale market cards.
            if age_min > 15:
                errors.append((key, label, f'stale market timestamp {age_min:.1f} min behind generatedAt'))
        elif generated_at:
            errors.append((key, label, 'missing market timestamp'))

    history = data.get('history') or []
    if history:
        latest = history[-1] if isinstance(history[-1], dict) else {}
        if latest.get('ts') != data.get('generatedAt'):
            errors.append(('history[-1]', '-', f'timestamp mismatch {latest.get("ts")} vs generatedAt {data.get("generatedAt")}'))
        if latest.get('benchmarkValue') in (None, '', 0):
            errors.append(('history[-1]', 'KOSPI', 'missing benchmarkValue'))
        if latest.get('benchmark') in (None, ''):
            errors.append(('history[-1]', 'KOSPI', 'missing benchmark return series'))
        if latest.get('kodex200Value') in (None, '', 0):
            errors.append(('history[-1]', 'KODEX', 'missing kodex200Value'))
        if latest.get('kodex200') in (None, ''):
            errors.append(('history[-1]', 'KODEX', 'missing kodex200 return series'))
        for idx, row in enumerate(history[-12:]):
            if row.get('benchmarkValue') not in (None, '', 0) and row.get('benchmark') in (None, ''):
                errors.append((f'history[-12+{idx}]', 'KOSPI', 'benchmark value present but return series missing'))
            if row.get('kodex200Value') not in (None, '', 0) and row.get('kodex200') in (None, ''):
                errors.append((f'history[-12+{idx}]', 'KODEX', 'kodex value present but return series missing'))
        session_count = len(data.get('sessions') or [])
        for hidx, row in enumerate(history):
            for key in ['returns', 'evalAmounts', 'capital', 'marketReturns', 'kodexReturns']:
                arr = row.get(key)
                if not isinstance(arr, list) or len(arr) < session_count:
                    errors.append((f'history[{hidx}]', key, 'missing session series array'))
                    continue
                missing = [i for i in range(session_count) if arr[i] in (None, '')]
                if missing:
                    errors.append((f'history[{hidx}]', key, f'missing session series indexes {missing}'))
    else:
        errors.append(('history', '-', 'empty history'))

    split_details = isinstance(data.get('stockDetailIndex'), dict)
    for path, item in rows:
        code = str(item.get('code') or '').zfill(6)
        fundamentals = item.get('fundamentals') or {}
        analysis = fundamentals.get('expertAnalysis') or {}
        kis = fundamentals.get('kisEnrichment') or {}
        tech = fundamentals.get('technicalStructure') or {}
        if not re.fullmatch(r'\d{6}', code):
            errors.append((path, code, 'bad code'))
        if fundamentals:
            stats['fundamental_rows'] += 1
            if split_details and not fundamentals.get('kisEnrichment') and not fundamentals.get('technicalStructure'):
                for required in ['score', 'stance', 'summary']:
                    if required not in analysis or analysis.get(required) in (None, '', []):
                        errors.append((path, code, f'missing slim expertAnalysis.{required}'))
                survival = analysis.get('survival') if isinstance(analysis, dict) else None
                if not isinstance(survival, dict):
                    errors.append((path, code, 'missing slim expertAnalysis.survival'))
                else:
                    for required in ['confidenceScore', 'confidenceLevel', 'actionState', 'positionGuide']:
                        if survival.get(required) in (None, '', []):
                            errors.append((path, code, f'missing slim survival.{required}'))
                continue
            for required in ['score', 'stance', 'summary', 'keyPoints', 'upsideTriggers', 'riskSignals', 'actionPoints']:
                if required not in analysis or analysis.get(required) in (None, '', []):
                    errors.append((path, code, f'missing expertAnalysis.{required}'))
            if not tech or tech.get('error'):
                errors.append((path, code, 'missing technicalStructure'))
            if not kis:
                errors.append((path, code, 'missing kisEnrichment'))
            else:
                parts = kis.get('parts') or {}
                ok_parts = [name for name, part in parts.items() if isinstance(part, dict) and part.get('ok')]
                stats['kis_part_ok'] += len(ok_parts)
                if len(ok_parts) < 7:
                    warnings.append((path, code, f'kis ok parts {len(ok_parts)}/7'))
                if not (kis.get('summary') or {}).get('signals'):
                    errors.append((path, code, 'missing kis summary signals'))
            survival = analysis.get('survival') if isinstance(analysis, dict) else None
            if not isinstance(survival, dict):
                errors.append((path, code, 'missing expertAnalysis.survival'))
            else:
                for required in ['confidenceScore', 'confidenceLevel', 'actionState', 'positionGuide', 'marketRegime']:
                    if survival.get(required) in (None, '', []):
                        errors.append((path, code, f'missing survival.{required}'))
                if 'failureRiskPatterns' not in survival:
                    errors.append((path, code, 'missing survival.failureRiskPatterns'))
                if isinstance(survival.get('marketRegime'), dict) and survival['marketRegime'].get('state') != regime.get('state'):
                    errors.append((path, code, 'survival marketRegime mismatch'))

    if split_details:
        stocks_dir = ROOT / 'data/stocks'
        files = sorted(stocks_dir.glob('*.json')) if stocks_dir.exists() else []
        if len(files) < int((data.get('stockDetailIndex') or {}).get('count') or 0):
            errors.append(('data/stocks', '-', 'stock detail file count below index count'))
        for fp in files:
            try:
                payload = json.loads(fp.read_text(encoding='utf-8'))
            except Exception as exc:
                errors.append((str(fp), '-', f'invalid json: {exc}'))
                continue
            code = str(payload.get('code') or fp.stem).zfill(6)
            f = payload.get('fundamentals') if isinstance(payload.get('fundamentals'), dict) else {}
            analysis = f.get('expertAnalysis') if isinstance(f.get('expertAnalysis'), dict) else {}
            survival = analysis.get('survival') if isinstance(analysis.get('survival'), dict) else {}
            if not f:
                errors.append((str(fp), code, 'missing detail fundamentals'))
                continue
            for required in ['score', 'stance', 'summary', 'keyPoints', 'upsideTriggers', 'riskSignals', 'actionPoints']:
                if analysis.get(required) in (None, '', []):
                    errors.append((str(fp), code, f'missing detail expertAnalysis.{required}'))
            if not f.get('technicalStructure'):
                errors.append((str(fp), code, 'missing detail technicalStructure'))
            if not f.get('kisEnrichment'):
                errors.append((str(fp), code, 'missing detail kisEnrichment'))
            for required in ['confidenceScore', 'confidenceLevel', 'actionState', 'positionGuide', 'marketRegime']:
                if survival.get(required) in (None, '', []):
                    errors.append((str(fp), code, f'missing detail survival.{required}'))
            if 'failureRiskPatterns' not in survival:
                errors.append((str(fp), code, 'missing detail survival.failureRiskPatterns'))

    for index, session in enumerate(data.get('sessions') or []):
        pf = session.get('portfolio') or {}
        positions = pf.get('positions') or []
        buy_alerts = session.get('buyAlerts') or []
        sell_records = session.get('sellRecords') or []
        sell_alerts = session.get('sellAlerts') or []
        if positions and not buy_alerts:
            errors.append((f'sessions[{index}]', '-', 'positions exist but buy layer empty'))
        if positions:
            position_eval = sum(float(pos.get('evalAmount') or 0) for pos in positions if isinstance(pos, dict))
            cash = float(pf.get('cash') or 0)
            eval_amount = float(pf.get('evalAmount') or 0)
            capital = float(pf.get('capital') or 0)
            pnl = float(pf.get('pnl') or 0)
            position_count = int(pf.get('positionCount') or 0)
            if position_count != len([p for p in positions if isinstance(p, dict) and float(p.get('qty') or 0) > 0]):
                errors.append((f'sessions[{index}].portfolio', session.get('name'), 'positionCount/displayed positions mismatch'))
            if abs(eval_amount - (position_eval + cash)) > max(2, len(positions)):
                errors.append((f'sessions[{index}].portfolio', session.get('name'), f'evalAmount mismatch: {eval_amount} vs positions+cash {position_eval + cash}'))
            if capital and abs(pnl - (eval_amount - capital)) > max(2, len(positions)):
                errors.append((f'sessions[{index}].portfolio', session.get('name'), f'pnl mismatch: {pnl} vs eval-capital {eval_amount - capital}'))
            expected_ret = round((eval_amount - capital) / capital * 100, 2) if capital else None
            if expected_ret is not None and pf.get('returnPct') is not None and abs(float(pf.get('returnPct')) - expected_ret) > 0.02:
                errors.append((f'sessions[{index}].portfolio', session.get('name'), f'returnPct mismatch: {pf.get("returnPct")} vs {expected_ret}'))
            daily = session.get('daily') or {}
            if daily.get('basis') == 'holding-prev-close':
                weights = [(float(pos.get('evalAmount') or 0), float(pos.get('currentChangePct'))) for pos in positions if isinstance(pos, dict) and pos.get('currentChangePct') not in (None, '')]
                if not weights:
                    errors.append((f'sessions[{index}].daily', session.get('name'), 'daily holding basis but no position changePct'))
                else:
                    denom = sum(w for w, _ in weights)
                    expected_daily = round(sum(w * c for w, c in weights) / denom, 2) if denom else None
                    if expected_daily is not None and abs(float(daily.get('returnPct')) - expected_daily) > 0.02:
                        errors.append((f'sessions[{index}].daily', session.get('name'), f'daily return mismatch: {daily.get("returnPct")} vs {expected_daily}'))
        for pos in positions:
            if not pos.get('holdAction') or not pos.get('holdReason'):
                errors.append((f'sessions[{index}].positions', pos.get('code'), 'missing hold action/reason'))
            if pos.get('currentPrice') in (None, '', 0) or pos.get('currentChangePct') in (None, ''):
                errors.append((f'sessions[{index}].positions', pos.get('code'), 'missing current price/change'))
        for alert in buy_alerts + sell_records + sell_alerts:
            if not alert.get('code') or not alert.get('name'):
                errors.append((f'sessions[{index}].alerts', '-', 'alert missing code/name'))
            if not alert.get('status'):
                warnings.append((f'sessions[{index}].alerts', alert.get('code'), 'alert missing status'))
        by_code = {str(pos.get('code') or ''): pos for pos in positions if isinstance(pos, dict)}
        for alert in buy_alerts:
            pos = by_code.get(str(alert.get('code') or ''))
            if pos and alert.get('returnPct') is not None and pos.get('returnPct') is not None and abs(float(alert.get('returnPct')) - float(pos.get('returnPct'))) > 0.02:
                errors.append((f'sessions[{index}].buyAlerts', alert.get('code'), f'returnPct mismatch vs position: {alert.get("returnPct")} vs {pos.get("returnPct")}'))
        for alert in sell_alerts:
            status = str(alert.get('status') or '')
            cat = alert.get('exitReviewCategory') if isinstance(alert.get('exitReviewCategory'), dict) else {}
            if cat.get('code') not in {'STOP', 'TAKE', 'MOMENTUM', 'WEAK', 'REBALANCE', 'EXIT'}:
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'missing/invalid exitReviewCategory'))
            for required in ['label', 'plain', 'isExecuted', 'actionType']:
                if required not in cat:
                    errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), f'missing exitReviewCategory.{required}'))
            if cat.get('isExecuted') is not False:
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'sellAlert category must be isExecuted=false'))
            if cat.get('actionType') not in {'검토만', '일부익절', '전량청산', '보유유지', '트레일링관찰'}:
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'invalid exitReviewCategory.actionType'))
            decision = alert.get('finalIntegratedDecision') if isinstance(alert.get('finalIntegratedDecision'), dict) else {}
            if not decision.get('action') or not decision.get('plain'):
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'missing finalIntegratedDecision action/plain'))
            conditions = decision.get('conditions') if isinstance(decision.get('conditions'), dict) else {}
            for required in ['hold', 'partialTakeProfit', 'trailingStop', 'exit', 'newBuy', 'reviewAt']:
                if not conditions.get(required):
                    errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), f'missing finalIntegratedDecision.conditions.{required}'))
            if cat.get('code') == 'MOMENTUM' and decision.get('action') != 'HOLD_WITH_TRAILING_CHECK':
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'momentum review missing HOLD_WITH_TRAILING_CHECK decision'))
            if cat.get('code') == 'STOP' and float(alert.get('returnPct') or 0) > 0 and '손절' not in str(alert.get('reviewAction') or ''):
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'positive position incorrectly categorized as STOP'))
            if cat.get('code') == 'MOMENTUM' and ('손절' in cat.get('label', '') or '익절' in cat.get('label', '')):
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'momentum review mislabeled as sell/take-profit'))
            if any(token in status for token in ['검토', '점검', '미체결']) and alert.get('executionStatus') != 'REVIEW_ONLY_NOT_EXECUTED':
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'review/hold alert missing non-execution marker'))
            if alert.get('executionStatus') == 'REVIEW_ONLY_NOT_EXECUTED' and int(alert.get('executedQty') or 0) != 0:
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'review sell alert has executedQty'))
            if 'FILLED' in str(alert.get('executionStatus') or ''):
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'filled sell must be in sellRecords, not sellAlerts'))
            if session.get('name') == '매일신규' and alert.get('returnPct') is not None and float(alert.get('returnPct')) <= -12 and '손절 우선' not in status:
                errors.append((f'sessions[{index}].sellAlerts', alert.get('code'), 'dailynew severe loss must be 손절 우선'))
        for alert in sell_records:
            cat = alert.get('exitReviewCategory') if isinstance(alert.get('exitReviewCategory'), dict) else {}
            if cat.get('code') not in {'EXECUTED', 'STOP', 'TAKE'}:
                errors.append((f'sessions[{index}].sellRecords', alert.get('code'), 'missing/invalid executed exitReviewCategory'))
            for required in ['label', 'plain', 'isExecuted', 'actionType']:
                if required not in cat:
                    errors.append((f'sessions[{index}].sellRecords', alert.get('code'), f'missing exitReviewCategory.{required}'))
            if cat.get('isExecuted') is not True:
                errors.append((f'sessions[{index}].sellRecords', alert.get('code'), 'sellRecord category must be isExecuted=true'))
            decision = alert.get('finalIntegratedDecision') if isinstance(alert.get('finalIntegratedDecision'), dict) else {}
            if not decision.get('action') or not decision.get('plain'):
                errors.append((f'sessions[{index}].sellRecords', alert.get('code'), 'missing finalIntegratedDecision action/plain'))
            conditions = decision.get('conditions') if isinstance(decision.get('conditions'), dict) else {}
            for required in ['hold', 'partialTakeProfit', 'trailingStop', 'exit', 'newBuy', 'reviewAt']:
                if not conditions.get(required):
                    errors.append((f'sessions[{index}].sellRecords', alert.get('code'), f'missing finalIntegratedDecision.conditions.{required}'))
            if 'FILLED' not in str(alert.get('executionStatus') or ''):
                errors.append((f'sessions[{index}].sellRecords', alert.get('code'), 'sell record missing filled executionStatus'))
    events_dir = ROOT.parent / 'invest_api_common/runtime/order_execution_events'
    if events_dir.exists():
        sold = []
        for p in events_dir.glob('*.json'):
            try:
                e = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                continue
            if e.get('action') == 'SELL' and e.get('code'):
                sold.append((e.get('sessionId'), str(e.get('code'))))
        if sold:
            name_to_sid = {'단기': 'jaesang.short.mock', '일반': 'jinhye.general.mock'}
            present = {(s.get('runtimeIdForComparison') or name_to_sid.get(s.get('name')), str(a.get('code') or '')) for s in (data.get('sessions') or []) for a in ((s.get('sellRecords') or []) + (s.get('sellAlerts') or []))}
            for item in sold:
                if item not in present:
                    errors.append(('order_execution_events', item[1], 'mock sell execution missing from dashboard sellAlerts'))

    app_js = (ROOT / 'app.js').read_text(encoding='utf-8')
    stock_js = (ROOT / 'stock.js').read_text(encoding='utf-8')
    if 'data-stock-info' in app_js or 'openStockInfoModal' in app_js:
        errors.append(('app.js', '-', 'stale modal click handler remains'))
    if 'stockDetailUrl' not in app_js or ('stock.html?code' not in app_js and 'stock-tabs.html?code' not in app_js):
        errors.append(('app.js', '-', 'stock detail links missing'))
    for needle in ['finalIntegratedAction', '최종 판단:', 'action-brief', 'final-conditions', 'action-detail']:
        if needle not in app_js:
            errors.append(('app.js', '-', f'missing action matrix integrated judgement marker: {needle}'))
    for needle in ['renderKisSummary', 'renderKisTables', 'KIS 실사용 보강 데이터']:
        if needle not in stock_js:
            errors.append(('stock.js', '-', f'missing {needle}'))

    for layer_name in ['fast-market.json', 'strategy.json', 'analysis.json', 'publish.json']:
        p = LAYERS / layer_name
        if not p.exists():
            errors.append((f'data/layers/{layer_name}', '-', 'missing layer output'))
            continue
        try:
            layer = json.loads(p.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append((f'data/layers/{layer_name}', '-', f'invalid json: {exc}'))
            continue
        if layer.get('generatedAt') != data.get('generatedAt'):
            errors.append((f'data/layers/{layer_name}', '-', f'generatedAt mismatch {layer.get("generatedAt")} vs {data.get("generatedAt")}'))

    result = {
        'ok': not errors,
        'generatedAt': data.get('generatedAt'),
        'sessions': len(data.get('sessions') or []),
        'stockLikeRows': len(rows),
        'fundamentalRows': stats['fundamental_rows'],
        'avgKisOkParts': round(stats['kis_part_ok'] / max(1, stats['fundamental_rows']), 2),
        'errors': errors[:50],
        'warnings': warnings[:50],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()
