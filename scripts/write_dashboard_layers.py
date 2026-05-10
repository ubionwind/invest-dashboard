#!/usr/bin/env python3
"""Write public dashboard layer snapshots for operational separation.

These files make the dashboard pipeline explicit:
- fast-market.json: volatile quote/holding/portfolio/daily fields
- strategy.json: strategy status, candidates, buy/sell review/execution layers
- analysis.json: fundamentals/technical/K-O-R analysis payloads by code
- publish.json: publication metadata and source freshness
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/dashboard-data.json'
OUT = ROOT / 'data/layers'


def compact_position(p):
    out = {k: p.get(k) for k in [
        'code', 'name', 'qty', 'entryPrice', 'currentPrice', 'currentDelta', 'currentChangePct',
        'evalAmount', 'pnl', 'returnPct', 'holdingPeriod'
    ] if k in p}
    f = p.get('fundamentals') if isinstance(p, dict) else None
    if isinstance(f, dict):
        refs = {k: f.get(k) for k in ['nxtQuote', 'stockFutureQuote'] if f.get(k)}
        if refs:
            out['marketReferences'] = refs
    return out


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    OUT.mkdir(parents=True, exist_ok=True)
    sessions = data.get('sessions') or []

    fast = {
        'schema': 'invest-dashboard.layer.fast-market.v1',
        'generatedAt': data.get('generatedAt'),
        'layerMode': data.get('layerMode') or 'full',
        'summary': {k: (data.get('summary') or {}).get(k) for k in ['totalCapital', 'totalEvalAmount', 'totalPnl', 'totalReturnPct']},
        'sessions': [{
            'name': s.get('name'),
            'daily': s.get('daily'),
            'portfolio': {k: (s.get('portfolio') or {}).get(k) for k in ['capital', 'cash', 'investmentAmount', 'evalAmount', 'pnl', 'returnPct', 'positionCount']},
            'positions': [compact_position(p) for p in ((s.get('portfolio') or {}).get('positions') or [])],
        } for s in sessions],
    }

    strategy = {
        'schema': 'invest-dashboard.layer.strategy.v1',
        'generatedAt': data.get('generatedAt'),
        'sessions': [{
            'name': s.get('name'),
            'stage': s.get('stage'),
            'status': s.get('status'),
            'candidateCount': s.get('candidateCount'),
            'validationCount': s.get('validationCount'),
            'gateCount': s.get('gateCount'),
            'dryRunCount': s.get('dryRunCount'),
            'protectedRows': s.get('protectedRows'),
            'quoteCount': s.get('quoteCount'),
            'topCandidates': s.get('topCandidates') or [],
            'buyAlerts': s.get('buyAlerts') or [],
            'sellAlerts': s.get('sellAlerts') or [],
            'strategyReview': s.get('strategyReview'),
            'comparison': s.get('comparison'),
        } for s in sessions],
    }

    by_code = {}
    for s in sessions:
        rows = []
        rows.extend((s.get('portfolio') or {}).get('positions') or [])
        rows.extend(s.get('topCandidates') or [])
        rows.extend(s.get('buyAlerts') or [])
        rows.extend(s.get('sellAlerts') or [])
        for row in rows:
            code = str((row or {}).get('code') or '').zfill(6)
            f = (row or {}).get('fundamentals')
            if code and code != '000000' and isinstance(f, dict):
                by_code[code] = f
    analysis = {
        'schema': 'invest-dashboard.layer.analysis.v1',
        'generatedAt': data.get('generatedAt'),
        'codes': by_code,
    }

    publish = {
        'schema': 'invest-dashboard.layer.publish.v1',
        'generatedAt': data.get('generatedAt'),
        'layerMode': data.get('layerMode') or 'full',
        'sessionCount': len(sessions),
        'historyCount': len(data.get('history') or []),
        'parts': {
            'dashboard': 'data/dashboard-data.json',
            'history': 'data/dashboard-history.json',
            'testManifest': 'data/test/manifest.json',
            'fast': 'data/layers/fast-market.json',
            'strategy': 'data/layers/strategy.json',
            'analysis': 'data/layers/analysis.json',
        },
    }

    files = {
        'fast-market.json': fast,
        'strategy.json': strategy,
        'analysis.json': analysis,
        'publish.json': publish,
    }
    for name, obj in files.items():
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'generatedAt': data.get('generatedAt'), 'layers': sorted(files)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
