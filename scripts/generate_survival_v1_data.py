#!/usr/bin/env python3
import datetime
import json
import pathlib
import socket
import urllib.request


ROOT = pathlib.Path('/home/ubion/.openclaw/workspace')
DASHBOARD = ROOT / 'shared/invest-dashboard'
RUNTIME = ROOT / 'shared/invest_api_common/runtime'
OUT = DASHBOARD / 'data/survival-v1.json'
SURVIVAL_LEDGER = RUNTIME / 'virtual_trades/jaesang.survival.v1.mock.json'
KST = datetime.timezone(datetime.timedelta(hours=9))
socket.setdefaulttimeout(8)

TARGET_SESSIONS = {
    '재상-급등-모의투자',
    '재상-매일신규-모의투자',
    '재상-퀀트모멘텀-모의투자',
    '재상-퀀트가치-모의투자',
    '재상-퀀트혼합-모의투자',
    '재상-급등-V2-가상검증',
    '재상-매일신규-V2-가상검증',
    '재상-퀀트가치-V2-가상검증',
    '재상-퀀트모멘텀-V2-가상검증',
    '재상-퀀트혼합-V2-가상검증',
}


def now_kst():
    return datetime.datetime.now(KST).replace(microsecond=0).isoformat()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def num(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(str(value).replace(',', '').strip())
    except Exception:
        return default


def pct(value):
    value = num(value, None)
    return value if value is not None else None


def fetch_naver_stock_basic(code, label):
    try:
        req = urllib.request.Request(
            f'https://m.stock.naver.com/api/stock/{code}/basic',
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace'))
        price = num(data.get('closePrice') or data.get('now') or data.get('tradePrice'), None)
        if not price:
            return None
        return {
            'label': label,
            'code': code,
            'value': round(price, 2),
            'dailyReturnPct': pct(data.get('fluctuationsRatio') or data.get('changeRate')),
            'date': data.get('localTradedAt', '')[:10] or None,
            'time': data.get('localTradedAt', '')[11:19] or None,
            'source': 'naver-stock-basic',
        }
    except Exception:
        return None


def action_for_candidate(row):
    if row.get('changePct') in (None, ''):
        return 'WATCH_ONLY', '등락률 확인 전 관찰 유지'
    change = num(row.get('changePct'), 0)
    risk = ' '.join(str(row.get(k) or '') for k in ['risk', 'reason', 'candidateNote'])
    if change >= 3.2:
        return 'BLOCK_CHASE', '당일 +3.2% 이상 추격 금지'
    if change <= -3.0:
        return 'BLOCK_FALLING', '당일 -3% 이하 급락 반등 확인 전 금지'
    if '과열' in risk or '추격' in risk:
        return 'BLOCK_OVERHEAT', '과열/추격 위험 태그'
    if -1.8 <= change <= 2.8:
        return 'ENTRY_REVIEW', '가격 위치 허용, 추가 게이트 검토'
    return 'WATCH_ONLY', '관찰 유지'


def candidate_score(row):
    for key in ['candidateScoreNormalized', 'score', 'currentScoreNormalized', 'baseScoreNormalized']:
        if row.get(key) not in (None, ''):
            return round(num(row.get(key)), 1)
    return None


def normalize_candidate(row, source):
    code = str(row.get('code') or '').zfill(6)
    if not code or code == '000000':
        return None
    action, reason = action_for_candidate(row)
    return {
        'code': code,
        'name': row.get('name') or code,
        'source': source,
        'score': candidate_score(row),
        'changePct': pct(row.get('changePct')),
        'price': round(num(row.get('currentPrice') or row.get('price'))) or None,
        'action': action,
        'reason': reason,
        'rawReason': row.get('reason') or row.get('entryCondition') or '',
    }


def load_candidates(dashboard):
    by_code = {}
    priority = {
        'ENTRY_REVIEW': 0,
        'WATCH_ONLY': 1,
        'BLOCK_OVERHEAT': 2,
        'BLOCK_CHASE': 3,
        'BLOCK_FALLING': 4,
    }
    for session in dashboard.get('sessions') or []:
        source = session.get('name') or 'dashboard'
        for row in session.get('topCandidates') or []:
            item = normalize_candidate(row, source)
            if not item:
                continue
            old = by_code.get(item['code'])
            if not old or (item.get('score') or 0) > (old.get('score') or 0):
                by_code[item['code']] = item

    surge_latest = load_json(ROOT / 'shared/mock_invest_jaesang_surge/runtime/latest.json', {})
    for row in surge_latest.get('candidates') or []:
        item = normalize_candidate(row, '급등 최신감시')
        if not item:
            continue
        old = by_code.get(item['code'])
        if not old or priority.get(item['action'], 9) < priority.get(old.get('action'), 9):
            by_code[item['code']] = item

    rows = sorted(
        by_code.values(),
        key=lambda r: (priority.get(r.get('action'), 9), -(r.get('score') or 0), r.get('code') or ''),
    )
    return rows[:36]


def ledger_files():
    return sorted((RUNTIME / 'virtual_trades').glob('*.json'))


def analyze_ledgers():
    sessions = []
    all_sells = []
    open_positions = []
    closed_positions = []

    for path in ledger_files():
        data = load_json(path, {})
        label = data.get('label') or data.get('sessionId') or path.stem
        if TARGET_SESSIONS and label not in TARGET_SESSIONS:
            continue
        portfolio = data.get('portfolio') or {}
        trades = data.get('trades') or []
        positions = data.get('positions') or []
        sells = [t for t in trades if t.get('side') == 'SELL']
        buys = [t for t in trades if t.get('side') == 'BUY']
        losses = [t for t in sells if num(t.get('realizedPnl')) < 0]
        wins = [t for t in sells if num(t.get('realizedPnl')) > 0]

        sessions.append({
            'sessionId': data.get('sessionId') or path.stem,
            'label': label,
            'checkedAt': data.get('checkedAt') or data.get('generatedAt'),
            'capital': round(num(portfolio.get('capital'))),
            'pnl': round(num(portfolio.get('pnl'))),
            'returnPct': pct(portfolio.get('returnPct')),
            'cash': round(num(portfolio.get('cash'))),
            'positionCount': round(num(portfolio.get('positionCount'))),
            'buyCount': len(buys),
            'sellCount': len(sells),
            'lossSellCount': len(losses),
            'winSellCount': len(wins),
            'realizedPnl': round(sum(num(t.get('realizedPnl')) for t in sells)),
            'avgLossPnl': round(sum(num(t.get('realizedPnl')) for t in losses) / len(losses)) if losses else None,
        })

        for t in sells:
            item = dict(t)
            item['sessionLabel'] = label
            all_sells.append(item)

        for p in positions:
            item = dict(p)
            item['sessionLabel'] = label
            if num(p.get('qty')) > 0:
                open_positions.append(item)
            elif p.get('status') == 'CLOSED_AUTO_STOP':
                closed_positions.append(item)

    sessions = sorted(sessions, key=lambda s: num(s.get('returnPct')), reverse=False)
    worst_sells = sorted(all_sells, key=lambda t: num(t.get('realizedPnl')))[:16]
    chase_stops = [
        p for p in closed_positions
        if num(p.get('sourceChangePct')) >= 3.2 or '급등' in str(p.get('entryReason') or '')
    ]
    return sessions, open_positions, worst_sells, chase_stops


def build_failure_patterns(sessions, worst_sells, chase_stops):
    total_sells = sum(s.get('sellCount') or 0 for s in sessions)
    loss_sells = sum(s.get('lossSellCount') or 0 for s in sessions)
    win_sells = sum(s.get('winSellCount') or 0 for s in sessions)
    total_realized = sum(s.get('realizedPnl') or 0 for s in sessions)
    return [
        {
            'title': '점수와 진입 허가가 섞임',
            'metric': f'{len(chase_stops)}건',
            'note': '당일 급등 또는 추격형 진입 뒤 자동손절된 레거시 포지션',
        },
        {
            'title': '실현 손익이 손절에 편중',
            'metric': f'{loss_sells}/{total_sells}',
            'note': f'매도 중 손실 비중, 실현손익 {total_realized:,}원',
        },
        {
            'title': '익절 회수 구조 약함',
            'metric': f'{win_sells}건',
            'note': '레거시 가상 원장에서 플러스 매도 기록이 거의 없음',
        },
        {
            'title': '손실 상위가 반복 종목/테마에 집중',
            'metric': f'{len(worst_sells)}건',
            'note': '최악 손절 샘플을 금지 규칙과 포지션 크기 조정에 사용',
        },
    ]


def build_policy():
    return [
        {'rule': 'SCORE_IS_OBSERVATION', 'label': '점수는 관찰 신호', 'detail': '점수만으로 신규 진입을 만들지 않는다.'},
        {'rule': 'NO_CHASE', 'label': '+3.2% 이상 신규매수 금지', 'detail': '급등주는 관찰/눌림 대기만 허용한다.'},
        {'rule': 'NO_FALLING_KNIFE', 'label': '-3% 이하 급락 매수 금지', 'detail': '반등 확인 전 자동 매수 후보에서 제외한다.'},
        {'rule': 'SMALL_FIRST_ENTRY', 'label': '1차 20~30% 진입', 'detail': '초기 포지션을 작게 잡고 확인 후 증액한다.'},
        {'rule': 'PARTIAL_TAKE_PROFIT', 'label': '부분익절 + 트레일링', 'detail': '+5~8%에서 일부 회수하고 잔여는 추세 확인한다.'},
        {'rule': 'VIRTUAL_ONLY', 'label': '실제/모의 주문 잠금', 'detail': '5~10거래일 성과 검증 전 주문 API를 열지 않는다.'},
    ]


def build_new_version():
    ledger = load_json(SURVIVAL_LEDGER, {})
    portfolio = ledger.get('portfolio') or {}
    return {
        'name': ledger.get('label') or 'Survival V1',
        'sessionId': ledger.get('sessionId') or 'jaesang.survival.v1.mock',
        'capital': round(num(portfolio.get('capital') or ledger.get('capital') or 10000000)),
        'cash': round(num(portfolio.get('cash') or ledger.get('cash') or 10000000)),
        'positionCount': round(num(portfolio.get('positionCount'))),
        'returnPct': pct(portfolio.get('returnPct')) or 0,
        'pnl': round(num(portfolio.get('pnl'))),
        'checkedAt': ledger.get('checkedAt'),
        'orderMode': 'virtual-only / no KIS order API',
        'promotionGate': '최소 5~10거래일 검증, 자동손절 감소, 평균손실 축소, 시장대비 초과수익 확인 전 승격 금지',
    }


def benchmark_snapshot(dashboard):
    kospi = dict(dashboard.get('benchmark') or {})
    kospi = {
        'label': 'KOSPI',
        'value': kospi.get('value'),
        'dailyReturnPct': kospi.get('dailyReturnPct'),
        'date': kospi.get('date'),
        'time': kospi.get('time'),
        'source': kospi.get('source') or 'dashboard-benchmark',
    }
    kodex_tr = fetch_naver_stock_basic('278530', 'KODEX 200TR')
    if not kodex_tr:
        fallback = dict(dashboard.get('kodexBenchmark') or {})
        kodex_tr = {
            'label': fallback.get('label') or 'KODEX 200',
            'code': fallback.get('code') or '069500',
            'value': fallback.get('value'),
            'dailyReturnPct': fallback.get('dailyReturnPct'),
            'date': fallback.get('date'),
            'time': fallback.get('time'),
            'source': f"{fallback.get('source') or 'dashboard-kodex'}-fallback",
        }
    return {'kospi': kospi, 'kodex200tr': kodex_tr}


def benchmark_return(current, start):
    cur = num((current or {}).get('value'), None)
    base = num((start or {}).get('value'), None)
    if not cur or not base:
        return None
    return round((cur - base) / base * 100, 2)


def build_benchmark_block(dashboard, new_version, generated_at):
    current = benchmark_snapshot(dashboard)
    previous = load_json(OUT, {})
    start = previous.get('benchmarkStart') or {}
    if not start.get('startedAt'):
        start = {
            'startedAt': (new_version.get('checkedAt') or generated_at),
            'survival': {'label': 'Survival V1', 'value': new_version.get('capital'), 'returnPct': 0},
            'kospi': current.get('kospi'),
            'kodex200tr': current.get('kodex200tr'),
        }

    point = {
        'ts': generated_at,
        'survivalReturnPct': new_version.get('returnPct') or 0,
        'survivalEvalAmount': (new_version.get('capital') or 0) + (new_version.get('pnl') or 0),
        'kospiReturnPct': benchmark_return(current.get('kospi'), start.get('kospi')),
        'kodex200trReturnPct': benchmark_return(current.get('kodex200tr'), start.get('kodex200tr')),
        'kospiValue': (current.get('kospi') or {}).get('value'),
        'kodex200trValue': (current.get('kodex200tr') or {}).get('value'),
    }
    history = previous.get('performanceHistory') or []
    history = [p for p in history if p.get('ts') != point['ts']]
    history.append(point)
    history = history[-120:]
    return {
        'benchmarkStart': start,
        'benchmarkCurrent': current,
        'performanceHistory': history,
    }


def main():
    dashboard = load_json(DASHBOARD / 'data/dashboard-data.json', {})
    generated_at = now_kst()
    sessions, open_positions, worst_sells, chase_stops = analyze_ledgers()
    candidates = load_candidates(dashboard)
    summary = dashboard.get('summary') or {}
    new_version = build_new_version()
    benchmark_block = build_benchmark_block(dashboard, new_version, generated_at)
    out = {
        'schema': 'invest-survival-v1.dashboard.v1',
        'generatedAt': generated_at,
        'sourceDashboardGeneratedAt': dashboard.get('generatedAt'),
        'status': 'VIRTUAL_ONLY',
        'mission': '실패한 레거시 투자 데이터를 금지 규칙으로 재사용해 손실 반복 루프를 끊는 생존형 신규 버전',
        'legacySummary': {
            'totalSessions': summary.get('totalSessions'),
            'totalCapital': summary.get('totalCapital'),
            'totalEvalAmount': summary.get('totalEvalAmount'),
            'totalPnl': summary.get('totalPnl'),
            'totalReturnPct': summary.get('totalReturnPct'),
        },
        'newVersion': new_version,
        **benchmark_block,
        'failurePatterns': build_failure_patterns(sessions, worst_sells, chase_stops),
        'policy': build_policy(),
        'legacySessions': sessions,
        'watchlist': candidates,
        'referenceOpenPositions': sorted(open_positions, key=lambda p: num(p.get('unrealizedPnl')), reverse=True)[:24],
        'worstStops': [
            {
                'sessionLabel': t.get('sessionLabel'),
                'date': t.get('date'),
                'code': str(t.get('code') or '').zfill(6),
                'name': t.get('name'),
                'realizedPnl': round(num(t.get('realizedPnl'))),
                'realizedReturnPct': pct(t.get('realizedReturnPct')),
                'entryPrice': t.get('entryPrice'),
                'exitPrice': t.get('price'),
                'reason': t.get('reason') or '',
            }
            for t in worst_sells
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'out': str(OUT), 'watchlist': len(candidates), 'sessions': len(sessions)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
