#!/usr/bin/env python3
"""Audit public investment dashboard analysis data and stock-detail wiring.

Read-only validation. Does not call broker/order APIs.
"""
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/test/dashboard-data.json'


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

    for index, session in enumerate(data.get('sessions') or []):
        positions = (session.get('portfolio') or {}).get('positions') or []
        buy_alerts = session.get('buyAlerts') or []
        sell_alerts = session.get('sellAlerts') or []
        if positions and not buy_alerts:
            errors.append((f'sessions[{index}]', '-', 'positions exist but buy layer empty'))
        for pos in positions:
            if not pos.get('holdAction') or not pos.get('holdReason'):
                errors.append((f'sessions[{index}].positions', pos.get('code'), 'missing hold action/reason'))
        for alert in buy_alerts + sell_alerts:
            if not alert.get('code') or not alert.get('name'):
                errors.append((f'sessions[{index}].alerts', '-', 'alert missing code/name'))
            if not alert.get('status'):
                warnings.append((f'sessions[{index}].alerts', alert.get('code'), 'alert missing status'))

    app_js = (ROOT / 'app.js').read_text(encoding='utf-8')
    stock_js = (ROOT / 'stock.js').read_text(encoding='utf-8')
    if 'data-stock-info' in app_js or 'openStockInfoModal' in app_js:
        errors.append(('app.js', '-', 'stale modal click handler remains'))
    if 'stockDetailUrl' not in app_js or 'stock.html?code' not in app_js:
        errors.append(('app.js', '-', 'stock detail links missing'))
    for needle in ['renderKisSummary', 'renderKisTables', 'KIS 실사용 보강 데이터']:
        if needle not in stock_js:
            errors.append(('stock.js', '-', f'missing {needle}'))

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
