#!/usr/bin/env python3
import json, pathlib, datetime, statistics, urllib.request, csv, io, re
ROOT = pathlib.Path('/home/ubion/.openclaw/workspace')
RUNTIME = ROOT/'shared/invest_api_common/runtime'
OUT = pathlib.Path(__file__).resolve().parents[1]/'data/dashboard-data.json'
KST = datetime.timezone(datetime.timedelta(hours=9))
LIVE_MOCK_RESET_EPOCH = datetime.datetime(2026, 5, 6, 0, 0, tzinfo=KST)
PUBLIC_IDS = {
    'jaesang.short.mock': 'panel1',
    'jinhye.general.mock': 'panel2',
    'jaesang.surge.mock': 'panel3',
    'jaesang.dailynew.mock': 'panel4',
}
PUBLIC_TAG_LABELS = {
    'tag_short_risk': '단기 리스크',
    'tag_dart': '공시',
    'tag_news': '뉴스',
    'tag_investor': '수급',
    'tag_event': '이벤트',
    'tag_sector': '섹터',
    'tag_verified_dynamic': '검증 이력',
    'tag_user_preference': '선호 기준',
    'tag_manual_lock': '수동 고정',
}


KIS_ENV_PATH = ROOT/'shared/invest_api_common/secrets/.env.local'
KIS_BASE = 'https://openapivts.koreainvestment.com:29443'
TOKEN_CACHE = ROOT/'shared/invest_api_common/runtime/kis_token_cache'
ACCOUNT_REFS = {
    'jaesang.short.mock': ('KIS_JAESANG_MOCK_APP_KEY','KIS_JAESANG_MOCK_APP_SECRET','KIS_JAESANG_MOCK_CANO','KIS_JAESANG_MOCK_ACNT_PRDT_CD'),
    'jinhye.general.mock': ('KIS_JINHYE_MOCK_APP_KEY','KIS_JINHYE_MOCK_APP_SECRET','KIS_JINHYE_MOCK_CANO','KIS_JINHYE_MOCK_ACNT_PRDT_CD'),
}

def load_env_file(path):
    out={}
    try:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line=raw.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k,v=line.split('=',1); v=v.strip().strip('"').strip("'")
            out[k.strip()]=v
    except Exception:
        pass
    return out

def post_json(url, payload):
    req=urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'content-type':'application/json; charset=utf-8'}, method='POST')
    return json.loads(urllib.request.urlopen(req, timeout=12).read().decode('utf-8','replace'))

def cached_access_token(private_id):
    try:
        j=json.loads((TOKEN_CACHE/f'{private_id}.json').read_text(encoding='utf-8'))
        if j.get('accessToken') and float(j.get('expiresAtMs') or 0) - datetime.datetime.now().timestamp()*1000 > 5*60*1000:
            return j.get('accessToken')
    except Exception:
        pass
    return None

def save_access_token(private_id, tok):
    try:
        TOKEN_CACHE.mkdir(parents=True, exist_ok=True)
        exp=tok.get('access_token_token_expired')
        exp_ms=0
        if exp:
            exp_ms=datetime.datetime.fromisoformat(str(exp).replace(' ', 'T')).timestamp()*1000
        (TOKEN_CACHE/f'{private_id}.json').write_text(json.dumps({'sessionId':private_id,'accessToken':tok.get('access_token'),'tokenType':tok.get('token_type') or 'Bearer','expiresAt':exp,'expiresAtMs':exp_ms,'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

def get_json(url, headers):
    req=urllib.request.Request(url, headers=headers, method='GET')
    return json.loads(urllib.request.urlopen(req, timeout=12).read().decode('utf-8','replace'))

def n(v):
    try: return float(str(v).replace(',','').strip() or 0)
    except Exception: return 0.0

READONLY_QUOTE_CACHE = {}

def readonly_quote_snapshot(code):
    """Return a read-only current quote for display fields only."""
    code = str(code or '').zfill(6)
    if not code or code == '000000':
        return None
    if code in READONLY_QUOTE_CACHE:
        return READONLY_QUOTE_CACHE[code]
    env = load_env_file(KIS_ENV_PATH)
    out = None
    try:
        appkey, appsecret = env.get('KIS_JAESANG_MOCK_APP_KEY'), env.get('KIS_JAESANG_MOCK_APP_SECRET')
        if appkey and appsecret:
            access = cached_access_token('jaesang.short.mock')
            if not access:
                tok = post_json(f'{KIS_BASE}/oauth2/tokenP', {'grant_type':'client_credentials','appkey':appkey,'appsecret':appsecret})
                access = tok.get('access_token')
                if access: save_access_token('jaesang.short.mock', tok)
            if access:
                params = urllib.parse.urlencode({'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':code})
                j = get_json(f'{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price?{params}', {
                    'content-type':'application/json; charset=utf-8', 'authorization':f'Bearer {access}',
                    'appkey':appkey, 'appsecret':appsecret, 'tr_id':'FHKST01010100', 'custtype':'P'
                })
                o = j.get('output') if isinstance(j, dict) else {}
                price = n((o or {}).get('stck_prpr'))
                if price > 0:
                    out = {
                        'currentPrice': round(price),
                        'currentChangePct': round(n(o.get('prdy_ctrt')), 2) if o.get('prdy_ctrt') not in (None, '') else None,
                        'currentDelta': round(n(o.get('prdy_vrss'))) if o.get('prdy_vrss') not in (None, '') else None,
                    }
    except Exception:
        out = None
    READONLY_QUOTE_CACHE[code] = out
    return out

VIRTUAL_LEDGER_IDS = {'jaesang.surge.mock', 'jaesang.dailynew.mock', 'jaesang.quant.value.mock', 'jaesang.quant.momentum.mock', 'jaesang.quant.mixed.mock'}
POSITION_LIMITS = {
    'jaesang.surge.mock': 5,
    'jaesang.dailynew.mock': 5,
    'jaesang.quant.value.mock': 10,
    'jaesang.quant.momentum.mock': 10,
    'jaesang.quant.mixed.mock': 10,
}
DEFAULT_POSITION_LIMIT = 5

def account_summary(private_id):
    if private_id in VIRTUAL_LEDGER_IDS:
        vt = load_fresh(f'virtual_trades/{private_id}.json', {})
        pf = vt.get('portfolio') if isinstance(vt, dict) else None
        if isinstance(pf, dict):
            positions=[]
            for p in (vt.get('positions') or [])[:8]:
                if not isinstance(p, dict):
                    continue
                qty = n(p.get('qty'))
                current_price = n(p.get('lastPrice'))
                positions.append({
                    'code': str(p.get('code') or ''),
                    'name': str(p.get('name') or ''),
                    'qty': p.get('qty'),
                    'entryPrice': round(n(p.get('entryPrice'))),
                    'currentPrice': round(current_price),
                    'entryAt': p.get('entryAt'),
                    'holdingPeriod': holding_period_text(p.get('entryAt')),
                    'evalAmount': round(current_price * qty),
                    'pnl': round(n(p.get('unrealizedPnl'))),
                    'returnPct': p.get('returnPct'),
                    'sourceScore': round(n(p.get('sourceScore')), 1) if p.get('sourceScore') not in (None, '') else None,
                    'sourceScoreNormalized': round(normalized_candidate_score(n(p.get('sourceScore')), private_id), 1) if p.get('sourceScore') not in (None, '') else None,
                    'entryScoreRaw': round(n(p.get('sourceScore')), 1) if p.get('sourceScore') not in (None, '') else None,
                    'entryScoreNormalized': round(normalized_candidate_score(n(p.get('sourceScore')), private_id), 1) if p.get('sourceScore') not in (None, '') else None,
                    'sourceChangePct': round(n(p.get('sourceChangePct')), 2) if p.get('sourceChangePct') not in (None, '') else None,
                    'entryReason': public_text(p.get('entryReason') or '', 140),
                    'holdAction': public_text(p.get('holdAction') or ''),
                    'holdScore': p.get('holdScore') if p.get('holdScore') not in (None, '') else None,
                    'holdReason': public_text(p.get('holdReason') or '', 160),
                })
            return {
                'capital': pf.get('capital'),
                'evalAmount': pf.get('evalAmount'),
                'pnl': pf.get('pnl'),
                'returnPct': pf.get('returnPct'),
                'positionCount': pf.get('positionCount'),
                'cash': pf.get('cash') if pf.get('cash') is not None else vt.get('cash'),
                'investmentAmount': pf.get('positionEvalAmount'),
                'positions': positions,
            }
    refs=ACCOUNT_REFS.get(private_id)
    if not refs: return None
    env=load_env_file(KIS_ENV_PATH)
    try:
        appkey, appsecret, cano, acnt = [env.get(x) for x in refs]
        if not all([appkey, appsecret, cano, acnt]): return None
        access=cached_access_token(private_id)
        if not access:
            tok=post_json(f'{KIS_BASE}/oauth2/tokenP', {'grant_type':'client_credentials','appkey':appkey,'appsecret':appsecret})
            access=tok.get('access_token')
            if access: save_access_token(private_id, tok)
        if not access: return None
        params=urllib.parse.urlencode({
            'CANO': cano, 'ACNT_PRDT_CD': acnt, 'AFHR_FLPR_YN':'N', 'OFL_YN':'', 'INQR_DVSN':'01', 'UNPR_DVSN':'01',
            'FUND_STTL_ICLD_YN':'N', 'FNCG_AMT_AUTO_RDPT_YN':'N', 'PRCS_DVSN':'01', 'CTX_AREA_FK100':'', 'CTX_AREA_NK100':''
        })
        j=get_json(f'{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-balance?{params}', {
            'content-type':'application/json; charset=utf-8', 'authorization':f'Bearer {access}', 'appkey':appkey, 'appsecret':appsecret, 'tr_id':'VTTC8434R', 'custtype':'P'
        })
        rows=j.get('output1') if isinstance(j.get('output1'), list) else []
        summary=(j.get('output2') or [{}])[0] if isinstance(j.get('output2'), list) else (j.get('output2') or {})
        eval_amt=n(summary.get('tot_evlu_amt'))
        pnl=n(summary.get('evlu_pfls_smtl_amt'))
        capital=eval_amt-pnl if eval_amt or pnl else n(summary.get('dnca_tot_amt'))
        ret=round((pnl/capital*100),2) if capital else None
        positions=[]
        for r in rows:
            qty=n(r.get('hldg_qty'))
            if qty <= 0: continue
            code = str(r.get('pdno') or '').zfill(6)
            entry_at = first_buy_time_for_code(private_id, code)
            eval_amount = n(r.get('evlu_amt'))
            current_price = n(
                r.get('prpr')
                or r.get('stck_prpr')
                or r.get('now_pric')
                or r.get('prpr_pric')
                or r.get('evlu_pric')
                or r.get('thdt_clpr')
            )
            if current_price <= 0 and qty > 0 and eval_amount > 0:
                current_price = eval_amount / qty
            positions.append({
                'code': code,
                'name': str(r.get('prdt_name') or ''),
                'qty': int(qty) if float(qty).is_integer() else qty,
                'entryPrice': round(n(r.get('pchs_avg_pric') or r.get('pchs_avg_price') or r.get('avg_prvs') or r.get('buy_avg_pric'))),
                'currentPrice': round(current_price),
                'entryAt': entry_at,
                'holdingPeriod': holding_period_text(entry_at),
                'evalAmount': round(eval_amount),
                'pnl': round(n(r.get('evlu_pfls_amt'))),
                'returnPct': round(n(r.get('evlu_pfls_rt')), 2) if r.get('evlu_pfls_rt') not in (None, '') else None,
            })
        investment_amount = sum(n(p.get('evalAmount')) for p in positions)
        cash = eval_amt - investment_amount if eval_amt else None
        return {'capital': round(capital), 'cash': round(cash) if cash is not None else None, 'investmentAmount': round(investment_amount), 'evalAmount': round(eval_amt), 'pnl': round(pnl), 'returnPct': ret, 'positionCount': len(positions), 'positions': positions[:8]}
    except Exception:
        return None

def benchmark_snapshot():
    # Public market benchmark snapshot. If unavailable, keep nulls rather than fabricating.
    # Prefer Naver's realtime-ish index API because Stooq can stay fixed at the prior
    # snapshot during Korean market hours, which makes market-relative returns stale.
    try:
        req = urllib.request.Request(
            'https://m.stock.naver.com/api/index/KOSPI/basic',
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        raw = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace')
        r = json.loads(raw)
        price = n(r.get('closePrice'))
        traded_at = parse_dt(r.get('localTradedAt'))
        if price > 0:
            return {
                'label': 'KOSPI',
                'value': round(price, 2),
                'returnPct': None,
                'dailyReturnPct': round(n(r.get('fluctuationsRatio')), 2) if r.get('fluctuationsRatio') not in (None, '') else None,
                'date': traded_at.date().isoformat() if traded_at else None,
                'time': traded_at.strftime('%H:%M:%S') if traded_at else None,
                'periodStart': None,
                'periodEnd': None,
                'source': 'naver-index-basic',
                'marketStatus': r.get('marketStatus'),
            }
    except Exception:
        pass
    try:
        raw = urllib.request.urlopen('https://stooq.com/q/l/?s=^kospi&f=sd2t2ohlcv&h&e=csv', timeout=8).read().decode('utf-8', 'replace')
        rows = list(csv.DictReader(io.StringIO(raw)))
        if rows:
            r = rows[0]
            open_v = float(r.get('Open') or 0)
            close_v = float(r.get('Close') or 0)
            daily_ret = ((close_v - open_v) / open_v * 100) if open_v else None
            return {'label':'KOSPI', 'value': round(close_v, 2), 'returnPct': None, 'dailyReturnPct': round(daily_ret, 2) if daily_ret is not None else None, 'date': r.get('Date'), 'time': r.get('Time'), 'periodStart': None, 'periodEnd': None, 'source': 'stooq-fallback'}
    except Exception:
        pass
    return {'label':'KOSPI', 'value': None, 'returnPct': None, 'dailyReturnPct': None, 'date': None, 'time': None, 'periodStart': None, 'periodEnd': None}

def kodex200_snapshot():
    # KODEX 200 ETF (069500) read-only quote. Used as an additional benchmark,
    # never as an order target.
    env=load_env_file(KIS_ENV_PATH)
    try:
        appkey, appsecret = env.get('KIS_JAESANG_MOCK_APP_KEY'), env.get('KIS_JAESANG_MOCK_APP_SECRET')
        if not appkey or not appsecret: return {'label':'KODEX 200', 'code':'069500', 'value': None, 'returnPct': None}
        access=cached_access_token('jaesang.short.mock')
        if not access:
            tok=post_json(f'{KIS_BASE}/oauth2/tokenP', {'grant_type':'client_credentials','appkey':appkey,'appsecret':appsecret})
            access=tok.get('access_token')
            if access: save_access_token('jaesang.short.mock', tok)
        if not access: return {'label':'KODEX 200', 'code':'069500', 'value': None, 'returnPct': None}
        params=urllib.parse.urlencode({'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':'069500'})
        j=get_json(f'{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price?{params}', {
            'content-type':'application/json; charset=utf-8', 'authorization':f'Bearer {access}', 'appkey':appkey, 'appsecret':appsecret, 'tr_id':'FHKST01010100', 'custtype':'P'
        })
        o=j.get('output') or {}
        price=n(o.get('stck_prpr'))
        return {'label':'KODEX 200', 'code':'069500', 'value': round(price, 2) if price else None, 'returnPct': None, 'dailyReturnPct': round(n(o.get('prdy_ctrt')), 2) if o.get('prdy_ctrt') not in (None, '') else None, 'date': datetime.datetime.now(KST).date().isoformat(), 'time': datetime.datetime.now(KST).strftime('%H:%M:%S'), 'periodStart': None, 'periodEnd': None}
    except Exception:
        return {'label':'KODEX 200', 'code':'069500', 'value': None, 'returnPct': None}

def benchmark_period_return(history, current_benchmark):
    vals=[]
    for x in history:
        if isinstance(x, dict) and x.get('benchmarkValue'):
            vals.append((x.get('ts'), float(x.get('benchmarkValue'))))
    if current_benchmark.get('value'):
        vals.append((datetime.datetime.now(KST).isoformat(timespec='minutes'), float(current_benchmark['value'])))
    if not vals:
        return None, None, None
    start_ts, start_v = vals[0]
    end_ts, end_v = vals[-1]
    if not start_v:
        return None, start_ts, end_ts
    return round((end_v - start_v) / start_v * 100, 2), start_ts, end_ts

def parse_dt(v):
    if not v: return None
    try:
        s = str(v).replace('Z', '+00:00')
        return datetime.datetime.fromisoformat(s).astimezone(KST)
    except Exception:
        return None

def holding_period_text(entry_at):
    t = parse_dt(entry_at)
    if not t:
        return None
    now = datetime.datetime.now(KST)
    # 사용자가 보는 보유일은 24시간 경과가 아니라 '날짜가 바뀐 횟수' 기준.
    # 예: 어제 매수 후 오늘 확인하면 24시간 미만이어도 보유 1일.
    calendar_days = max(0, (now.date() - t.date()).days)
    if calendar_days >= 1:
        return f'보유 {calendar_days}일'
    minutes = max(0, int((now - t).total_seconds() // 60))
    if minutes < 60:
        return f'보유 {minutes}분'
    hours, mins = divmod(minutes, 60)
    return f'보유 {hours}시간 {mins}분'

def first_buy_time_for_code(sid, code):
    times=[]
    locks = load_fresh('order_gate/order_locks.json', {})
    if isinstance(locks, dict):
        needle = f'|{sid}|{code}|BUY'
        for key, row in (locks.get('locks') or {}).items():
            if needle not in str(key):
                continue
            state = str((row or {}).get('state') or '')
            if state not in {'WAITING_APPROVAL', 'ORDER_EXECUTED', 'FILLED', 'LOCKED_DUPLICATE'}:
                continue
            t = parse_dt((row or {}).get('createdAt'))
            if t and t >= LIVE_MOCK_RESET_EPOCH: times.append(t)
    dry = load_fresh(f'order_dry_run/{sid}.json', {})
    if isinstance(dry, dict):
        for r in dry.get('results') or []:
            if str(r.get('code') or '') == str(code) and ((r.get('execution') or {}).get('executed')):
                t = parse_dt(r.get('checkedAt'))
                if t: times.append(t)
    return min(times).isoformat(timespec='minutes') if times else None

def first_investment_time(sid):
    # Market comparison should start when this strategy first takes risk, not at dashboard reset/open.
    times=[]
    dry = load_fresh(f'order_dry_run/{sid}.json', {})
    if isinstance(dry, dict):
        for r in dry.get('results') or []:
            if ((r.get('execution') or {}).get('executed')):
                t = parse_dt(r.get('checkedAt'))
                if t: times.append(t)
    vt = load_fresh(f'virtual_trades/{sid}.json', {})
    if isinstance(vt, dict):
        for p in vt.get('positions') or []:
            t = parse_dt(p.get('entryAt'))
            if t: times.append(t)
        for tr in vt.get('trades') or []:
            if tr.get('side') == 'BUY':
                t = parse_dt(tr.get('time'))
                if t: times.append(t)
    locks = load_fresh('order_gate/order_locks.json', {})
    if isinstance(locks, dict):
        for key, row in (locks.get('locks') or {}).items():
            if f'|{sid}|' not in str(key) or '|BUY' not in str(key):
                continue
            state = str((row or {}).get('state') or '')
            # For KIS-backed mock sessions, later duplicate-lock runs can overwrite the
            # original fill log. The first post-reset BUY lock is still the closest
            # durable risk-on timestamp, so use it as the comparison baseline fallback.
            if state in {'WAITING_APPROVAL', 'ORDER_EXECUTED', 'FILLED', 'LOCKED_DUPLICATE'}:
                t = parse_dt((row or {}).get('createdAt'))
                if t: times.append(t)
    return min(times) if times else None

def benchmark_return_since(history, current_benchmark, start_dt, value_key='benchmarkValue'):
    if not start_dt:
        return None, None, None
    vals=[]
    for x in history:
        if isinstance(x, dict) and x.get(value_key):
            t=parse_dt(x.get('ts'))
            if t:
                vals.append((x.get('ts'), t, float(x.get(value_key))))
    if current_benchmark.get('value'):
        now_ts = datetime.datetime.now(KST).isoformat(timespec='minutes')
        vals.append((now_ts, parse_dt(now_ts), float(current_benchmark['value'])))
    vals=[v for v in vals if v[1] is not None]
    if len(vals) < 1:
        return None, start_dt.isoformat(timespec='minutes'), None
    # Baseline is the market index at strategy risk-on time. Because we only have
    # sampled benchmark snapshots, use the latest sample at/before the first buy;
    # if none exists, fall back to the earliest sample after it. This makes the
    # benchmark line conceptually start from 0 at the buy point instead of using
    # the whole day/open-session return.
    before=[v for v in vals if v[1] <= start_dt]
    baseline = max(before, key=lambda v: v[1]) if before else min(vals, key=lambda v: v[1])
    end = max(vals, key=lambda v: v[1])
    start_ts, _, start_v = baseline
    end_ts, _, end_v = end
    if not start_v:
        return None, start_ts, end_ts
    return round((end_v - start_v) / start_v * 100, 2), start_dt.isoformat(timespec='minutes'), end_ts

def benchmark_series(history, start_dt, value_key='benchmarkValue'):
    if not start_dt:
        return [None for _ in history]
    vals=[]
    for idx, x in enumerate(history):
        if isinstance(x, dict) and x.get(value_key):
            t=parse_dt(x.get('ts'))
            if t:
                vals.append((idx, x.get('ts'), t, float(x.get(value_key))))
    if not vals:
        return [None for _ in history]
    before=[v for v in vals if v[2] <= start_dt]
    baseline=max(before, key=lambda v: v[2]) if before else min(vals, key=lambda v: v[2])
    base_v=baseline[3]
    out=[]
    for x in history:
        t=parse_dt(x.get('ts')) if isinstance(x, dict) else None
        v=x.get(value_key) if isinstance(x, dict) else None
        if not t or not v or t < start_dt or not base_v:
            out.append(None)
        else:
            out.append(round((float(v)-base_v)/base_v*100, 2))
    # For chart readability, the first visible market-comparison point is the
    # investment baseline itself: 0%. The KPI still uses the latest/baseline value.
    for i, v in enumerate(out):
        if v is not None:
            out[i] = 0.0
            break
    return out

def load(rel, default):
    p = RUNTIME/rel
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return default

def is_fresh_runtime(rel):
    p = RUNTIME/rel
    try:
        return datetime.datetime.fromtimestamp(p.stat().st_mtime, KST) >= LIVE_MOCK_RESET_EPOCH
    except Exception:
        return False

def load_fresh(rel, default):
    # The live mock dashboard must not inherit pre-reset legacy session candidates,
    # returns, quotes, or protection state. Old files can still exist as audit inputs,
    # but they are hidden until the live mock pipeline creates fresh runtime output.
    if not is_fresh_runtime(rel):
        return default
    return load(rel, default)

def count_items(obj, keys=('candidates','validations','items','rows','results')):
    if isinstance(obj, list): return len(obj)
    if isinstance(obj, dict):
        for k in keys:
            if isinstance(obj.get(k), list): return len(obj[k])
    return 0

def public_text(value, limit=120):
    text = str(value or '')
    for old, new in {
        '주문금지/가상만': '진입 기준',
        '주문금지/': '',
        '가상매수': '매수',
        '가상체결': '체결',
        '가상 진입': '진입',
        '가상진입': '진입',
        '가상 투자': '투자',
        '가상투자': '투자',
        '가상만': '기록',
        'VIRTUAL_FILLED': '체결완료',
        'virtual tracking only': 'tracking',
        'virtual': '',
        '주문 금지': '관찰 기준',
        '주문금지': '관찰 기준',
        '모의주문': '검토',
        '주문': '검토',
        'orderDecision': 'decision',
        'KIS ': '',
        'KIS': '',
        'Google': '',
        'google': '',
        'mock': '',
    }.items():
        text = text.replace(old, new)
    return text[:limit]

def normalized_candidate_score(raw_score_num, sid):
    # Convert strategy-native scores into a public 0~100 "decision score".
    # This is intentionally threshold-based: each strategy has different raw
    # score scales, so the dashboard score should answer "how actionable is this
    # inside its own strategy right now?" rather than expose raw math directly.
    if sid == 'jaesang.surge.mock':
        if raw_score_num >= 250: return 95
        if raw_score_num >= 180: return 88
        if raw_score_num >= 120: return 80
        if raw_score_num >= 80: return 70
        return 55
    if sid == 'jaesang.short.mock':
        if raw_score_num >= 65: return 90
        if raw_score_num >= 62: return 82
        if raw_score_num >= 60: return 75
        if raw_score_num >= 55: return 65
        return 50
    if sid == 'jinhye.general.mock':
        if raw_score_num >= 65: return 90
        if raw_score_num >= 58: return 80
        if raw_score_num >= 50: return 70
        if raw_score_num >= 42: return 55
        return 45
    if sid == 'jaesang.dailynew.mock':
        if raw_score_num >= 80: return 90
        if raw_score_num >= 75: return 82
        if raw_score_num >= 70: return 75
        if raw_score_num >= 65: return 65
        return 50
    if sid in {'jaesang.quant.value.mock', 'jaesang.quant.momentum.mock', 'jaesang.quant.mixed.mock'}:
        if raw_score_num >= 90: return 95
        if raw_score_num >= 80: return 88
        if raw_score_num >= 70: return 78
        if raw_score_num >= 60: return 65
        return 50
    return max(0, min(100, raw_score_num))

STRATEGY_ANALYSIS_WEIGHTS = {
    'jinhye.general.mock': {'technical': 0.8, 'fundamental': 0.9},
    'jaesang.short.mock': {'technical': 1.1, 'fundamental': 0.25},
    'jaesang.surge.mock': {'technical': 1.35, 'fundamental': 0.1},
    'jaesang.dailynew.mock': {'technical': 1.0, 'fundamental': 0.35},
    'jaesang.quant.value.mock': {'technical': 0.35, 'fundamental': 1.25},
    'jaesang.quant.momentum.mock': {'technical': 1.25, 'fundamental': 0.25},
    'jaesang.quant.mixed.mock': {'technical': 0.8, 'fundamental': 0.8},
}


def fundamental_bias(f):
    if not isinstance(f, dict):
        return 0, []
    per, pbr, roe = f.get('per'), f.get('pbr'), f.get('roe')
    bias = 0
    notes = []
    if roe is not None:
        if roe >= 20:
            bias += 4; notes.append('고ROE 가점')
        elif roe >= 15:
            bias += 2; notes.append('ROE 양호')
        elif roe < 5:
            bias -= 4; notes.append('저ROE 감점')
    if pbr is not None:
        if pbr <= 1:
            bias += 3; notes.append('저PBR 가점')
        elif pbr >= 6:
            bias -= 3; notes.append('고PBR 부담')
        elif pbr >= 4:
            bias -= 1; notes.append('PBR 부담')
    if per is not None:
        if per <= 0:
            bias -= 3; notes.append('PER 해석주의')
        elif per <= 10:
            bias += 3; notes.append('저PER 가점')
        elif per >= 45:
            bias -= 3; notes.append('고PER 부담')
        elif per >= 35:
            bias -= 1; notes.append('PER 부담')
    return bias, notes[:3]


def strategy_adjustment(sid, fundamentals):
    weights = STRATEGY_ANALYSIS_WEIGHTS.get(sid, {'technical': 0.5, 'fundamental': 0.5})
    tech = (fundamentals or {}).get('technicalSignal') if isinstance(fundamentals, dict) else None
    tech_bias = n((tech or {}).get('bias')) if isinstance(tech, dict) and tech.get('bias') is not None else 0
    fund_bias, fund_notes = fundamental_bias(fundamentals)
    adjustment = tech_bias * weights.get('technical', 0) + fund_bias * weights.get('fundamental', 0)
    adjustment = max(-12, min(12, adjustment))
    reasons = []
    if tech and tech.get('state') not in ('구조중립', '기술분석대기'):
        reasons.append(f"기술 {tech.get('state')} {tech_bias:+.0f}")
    reasons.extend(fund_notes)
    return {
        'value': round(adjustment, 1),
        'technicalWeight': weights.get('technical', 0),
        'fundamentalWeight': weights.get('fundamental', 0),
        'reasons': reasons[:4],
    }


def apply_strategy_adjustment(score, sid, fundamentals):
    if score is None:
        return None, strategy_adjustment(sid, fundamentals)
    adj = strategy_adjustment(sid, fundamentals)
    return round(max(0, min(100, n(score) + adj['value'])), 1), adj


def first_present(*values):
    for v in values:
        if v not in (None, ''):
            return v
    return None

def liquidity_evidence_text(reason):
    text = str(reason or '')
    m = re.search(r'거래대금\s*([\d,.]+\s*[조억만]?)', text)
    if m:
        return f"거래대금 {m.group(1)}"
    m = re.search(r'거래대금점수\s*=\s*([\d.]+)', text)
    if m:
        return f"거래대금 점수 {round(n(m.group(1)))}"
    if '거래대금 증가' in text:
        return '거래대금 증가'
    return '수급 데이터 대기'

def replacement_watch_line(score):
    return round(max(n(score) + 12, 70), 1) if score is not None else None

def safe_candidates(obj, sid=None, limit=8):
    arr=[]
    positions=[]
    evaluated_at=None
    if isinstance(obj, dict):
        arr = obj.get('candidates') or obj.get('validations') or obj.get('items') or []
        positions = obj.get('positions') if isinstance(obj.get('positions'), list) else []
        evaluated_at = obj.get('checkedAt') or obj.get('checkedAtKst') or obj.get('createdAt')
    elif isinstance(obj, list): arr=obj
    held_by_code = {str(p.get('code') or ''): p for p in positions if isinstance(p, dict) and p.get('qty', 0)}
    position_limit = POSITION_LIMITS.get(sid, DEFAULT_POSITION_LIMIT)
    full_position_limit = len(held_by_code) >= position_limit
    out=[]
    for idx, c in enumerate(arr[:limit]):
        if not isinstance(c, dict): continue
        quote = c.get('quote') if isinstance(c.get('quote'), dict) else {}
        change_pct = c.get('changePct')
        if change_pct is None:
            change_pct = c.get('changeRate')
        if change_pct is None:
            change_pct = quote.get('changeRate')
        current_price = first_present(c.get('currentPrice'), c.get('price'), c.get('lastPrice'), quote.get('price'), quote.get('currentPrice'))
        raw_score = first_present(c.get('score'), c.get('totalScore'), c.get('priorityScore'), c.get('confidence_score'))
        raw_score_num = n(raw_score)
        # Public dashboard score is normalized to 0~100 so different strategies
        # can be read at a glance. Keep the original score as a small reference.
        if raw_score in (None, ''):
            base_normalized_score = None
        else:
            base_normalized_score = normalized_candidate_score(raw_score_num, sid)
        normalized_score = base_normalized_score
        code = str(c.get('code') or c.get('symbol') or c.get('pdno') or '')
        held = held_by_code.get(code)
        status = public_text(c.get('status') or c.get('action') or c.get('validationStatus') or c.get('decision') or c.get('orderDecision') or c.get('review_status') or '')
        if held:
            status = '보유중'
        elif not status:
            status = '현재후보'
        candidate_note = None
        entry_score_raw = round(n(held.get('sourceScore')), 1) if held and held.get('sourceScore') not in (None, '') else None
        entry_score_norm = round(normalized_candidate_score(n(held.get('sourceScore')), sid), 1) if held and held.get('sourceScore') not in (None, '') else None
        if held:
            candidate_note = f"진입시각 {str(held.get('entryAt') or '')[:16]} · 진입 판단점수 {entry_score_norm if entry_score_norm is not None else '-'} · 진입 원점수 {entry_score_raw if entry_score_raw is not None else '-'} · 진입 당시 등락률 {held.get('sourceChangePct', '-')}%"
        elif full_position_limit:
            candidate_note = f'현재 평가 기준 후보지만 보유 한도 {position_limit}종목이 이미 차 있어 신규 매수 없음'
        reason_text = public_text(c.get('reason') or c.get('summary') or c.get('entry_reason') or c.get('note') or '')
        fundamentals = public_fundamentals(code)
        normalized_score, strategy_adj = apply_strategy_adjustment(base_normalized_score, sid, fundamentals)
        tech_signal = (fundamentals or {}).get('technicalSignal') if isinstance(fundamentals, dict) else None
        if tech_signal and tech_signal.get('state') not in ('구조중립', '기술분석대기'):
            tech_note = f"기술구조 {tech_signal.get('state')}: {tech_signal.get('reason')}"
            candidate_note = f"{candidate_note} · {tech_note}" if candidate_note else tech_note
        out.append({
            'code': code,
            'name': str(c.get('name') or c.get('stockName') or c.get('prdt_name') or ''),
            'score': round(normalized_score, 1) if normalized_score is not None else None,
            'baseScoreNormalized': round(base_normalized_score, 1) if base_normalized_score is not None else None,
            'scoreAdjustment': strategy_adj,
            'rawScore': round(raw_score_num, 1) if raw_score not in (None, '') else None,
            'currentScoreNormalized': round(normalized_score, 1) if normalized_score is not None else None,
            'currentScoreRaw': round(raw_score_num, 1) if raw_score not in (None, '') else None,
            'entryScoreNormalized': entry_score_norm,
            'entryScoreRaw': entry_score_raw,
            'changePct': round(n(change_pct), 2) if change_pct not in (None, '') else None,
            'currentPrice': round(n(current_price)) if current_price not in (None, '') else None,
            'rank': idx + 1,
            'evaluatedAt': evaluated_at,
            'status': status,
            'action': public_text(c.get('action') or ''),
            'validationStatus': public_text(c.get('validationStatus') or ''),
            'suggestedQty': c.get('suggestedQty') if c.get('suggestedQty') not in (None, '') else None,
            'candidateNote': public_text(candidate_note, 160) if candidate_note else None,
            'reason': reason_text,
            'liquidityText': liquidity_evidence_text(reason_text),
            'positionLimit': position_limit,
            'technicalDecision': tech_signal,
            'fundamentals': fundamentals,
        })
    return out

def safe_alerts(obj, limit=4):
    arr=[]
    if isinstance(obj, dict):
        arr = obj.get('candidates') or obj.get('sellCandidates') or obj.get('orders') or obj.get('items') or obj.get('results') or []
    elif isinstance(obj, list):
        arr=obj
    out=[]
    for c in arr[:limit]:
        if not isinstance(c, dict): continue
        out.append({
            'code': str(c.get('code') or c.get('symbol') or c.get('pdno') or ''),
            'name': str(c.get('name') or c.get('stockName') or c.get('prdt_name') or ''),
            'status': public_text(c.get('status') or c.get('action') or c.get('decision') or c.get('orderDecision') or c.get('review_status') or ''),
            'reason': public_text(c.get('reason') or c.get('summary') or c.get('entry_reason') or c.get('exit_reason') or c.get('note') or ''),
            'returnPct': c.get('returnPct') if c.get('returnPct') not in (None, '') else c.get('pnlRate'),
            'sellScore': c.get('sellScore') if c.get('sellScore') not in (None, '') else None,
            'pnl': c.get('pnl') if c.get('pnl') not in (None, '') else None,
        })
    return out

def safe_buy_fills(dry, virtual, limit=4):
    # The dashboard "buy alert" area must mean actual filled/recorded entries,
    # not candidates under review. Candidate/review items belong in topCandidates.
    rows=[]
    if isinstance(dry, dict) and dry.get('executeFlag') is True:
        for c in (dry.get('results') or []):
            execution = c.get('execution') or {}
            response = execution.get('response') or {}
            if not (execution.get('executed') and response.get('ok')):
                continue
            output = (response.get('json') or {}).get('output') if isinstance(response.get('json'), dict) else {}
            rows.append({
                'code': str(c.get('code') or ''),
                'name': str(c.get('name') or ''),
                'status': '체결완료',
                'reason': f"{c.get('qty') or ''}주 · 체결완료 · 체결시각 {str((output or {}).get('ORD_TMD', ''))[:6]}"[:120],
            })
    if not rows and isinstance(virtual, dict):
        pos_by_code = {str(p.get('code') or ''): p for p in (virtual.get('positions') or []) if isinstance(p, dict)}
        for c in (virtual.get('trades') or []):
            if c.get('side') != 'BUY':
                continue
            pos = pos_by_code.get(str(c.get('code') or '')) or {}
            rows.append({
                'code': str(c.get('code') or ''),
                'name': str(c.get('name') or ''),
                'status': '보유중',
                'reason': public_text(f"{c.get('qty') or ''}주 · 매입 {c.get('price') or ''}원 · 평가 {round(n(pos.get('lastPrice')) * n(pos.get('qty')))}원 · 손익 {round(n(pos.get('unrealizedPnl')))}원")[:120],
                'returnPct': pos.get('returnPct'),
                'holdingPeriod': holding_period_text(pos.get('entryAt') or c.get('time')),
            })
    return rows[:limit]

def rule_review_for(sid):
    rr = load('rule_review/latest.json', {})
    reviews = rr.get('reviews') or [] if isinstance(rr, dict) else []
    wanted = {'jaesang.short.mock':'short', 'jinhye.general.mock':'general'}.get(sid)
    if not wanted: return None
    for r in reviews:
        if r.get('mode') == wanted:
            signals=[]
            for x in (r.get('strongSignals') or [])[:3]:
                y=dict(x)
                raw=y.pop('tag', '')
                y['label']=PUBLIC_TAG_LABELS.get(raw, raw.replace('tag_', '') or '근거')
                signals.append(y)
            return {
                'checkedAt': rr.get('checkedAt'),
                'strongSignals': signals,
                'overtradeSymbols': (r.get('overtradeSymbols') or [])[:5],
                'actions': [a.replace('KIS ', '').replace('KIS', '').replace('모의주문', '검토').replace('주문', '검토').replace('tag_verified_dynamic', '검증 이력').replace('tag_short_risk', '단기 리스크').replace('tag_dart', '공시').replace('tag_news', '뉴스').replace('tag_investor', '수급').replace('tag_event', '이벤트').replace('tag_sector', '섹터') for a in (r.get('actions') or [])[:4]],
            }
    return None

def account_performance(sid):
    snap = load_fresh(f'kis_snapshots/{sid}.json', {})
    bal = snap.get('balanceStatus') if isinstance(snap, dict) else {}
    return {
        'accountPnlAvailable': False,
        'positionCount': (bal or {}).get('positionCount'),
        'totalEvalAmount': None,
        'unrealizedPnl': None,
        'returnPct': None,
        'note': '성과 집계 대기'
    }

def session_status(sid):
    health = load_fresh(f'realtime_daemon/{sid}.json', {})
    quotes = load_fresh(f'realtime_quotes/{sid}.json', {})
    fallback = load_fresh(f'fallback_quotes/{sid}.json', {})
    prot = load_fresh(f'realtime_protection/{sid}.json', {})
    cand = load_fresh(f'order_candidates/{sid}.json', {})
    sell = load_fresh(f'sell_candidates/{sid}.json', {})
    val = load_fresh(f'order_validations/{sid}.json', {})
    gate = load_fresh(f'order_gate/{sid}.json', {})
    dry = load_fresh(f'order_dry_run/{sid}.json', {})
    virtual = load_fresh(f'virtual_trades/{sid}.json', {})
    # Health label without exposing account/key info
    htxt = json.dumps(health, ensure_ascii=False).upper()
    if 'STALE' in htxt or 'NOT ALIVE' in htxt:
        status='STALE'
    elif health:
        status='OK'
    elif fallback:
        status='FALLBACK'
    else:
        status='NO_DATA'
    protected = prot.get('protectedRows') if isinstance(prot, dict) else None
    if protected is None and isinstance(prot, dict):
        protected = len(prot.get('protected') or prot.get('rows') or [])
    candidate_count = count_items(cand) or count_items(virtual, ('candidates','items','results'))
    sell_count = count_items(sell, ('sellCandidates','candidates','items','results'))
    validation_count = count_items(val)
    gate_count = count_items(gate, ('orders','queue','candidates','items'))
    dry_count = count_items(dry, ('orders','results','items')) or count_items(virtual, ('trades','results','items'))
    # If no post-reset candidate/validation/gate artifact exists, do not
    # display fallback quotes/protection produced from the legacy seed universe.
    has_current_items = any([candidate_count, validation_count, gate_count, dry_count])
    if not has_current_items:
        status = 'INITIALIZED'
        protected = 0
        quote_count = 0
        top_candidates = []
    else:
        if status == 'NO_DATA' and isinstance(virtual, dict) and count_items(virtual, ('positions','trades','candidates')):
            status = 'OK'
        quote_count = count_items(quotes, ('quotes','items','results')) or count_items(fallback, ('quotes','items','results'))
        top_candidates = safe_candidates(cand, sid) or safe_candidates(virtual, sid)
    buy_alerts = safe_buy_fills(dry, virtual) if has_current_items else []
    sell_alerts = safe_alerts(sell) if sell_count else []
    return {
        'status': status,
        'candidateCount': candidate_count,
        'sellCandidateCount': sell_count,
        'validationCount': validation_count,
        'gateCount': gate_count,
        'dryRunCount': dry_count,
        'protectedRows': protected or 0,
        'quoteCount': quote_count,
        'topCandidates': top_candidates,
        'buyAlerts': buy_alerts,
        'sellAlerts': sell_alerts,
        'performance': account_performance(sid),
        'strategyReview': rule_review_for(sid),
    }

def has_actual_buy(s):
    pf = s.get('portfolio') or {}
    try:
        return int(pf.get('positionCount') or 0) > 0
    except Exception:
        return False


def comparable_return(s):
    # Do not compare against market before the session has actually bought/held anything.
    # Cash-only 0.00% vs rising KOSPI looks like underperformance even though the strategy
    # has not started taking market risk yet.
    if not has_actual_buy(s):
        return None
    pf = s.get('portfolio') or {}
    if pf.get('returnPct') is not None:
        return pf.get('returnPct')
    p = s.get('performance') or {}
    if p.get('accountPnlAvailable') and p.get('returnPct') is not None:
        return p.get('returnPct')
    return None

FUNDAMENTALS = load_fresh('fundamentals/latest.json', {})
FUNDAMENTALS_BY_CODE = FUNDAMENTALS.get('fundamentals') if isinstance(FUNDAMENTALS, dict) and isinstance(FUNDAMENTALS.get('fundamentals'), dict) else {}

def technical_analysis_signal(f):
    t = (f or {}).get('technicalStructure') if isinstance(f, dict) else None
    if not isinstance(t, dict) or t.get('error'):
        return {'state': '기술분석대기', 'bias': 0, 'reason': '전고점/매물대 분석 데이터 대기'}
    dist20 = n(t.get('distanceToHigh20dPct')) if t.get('distanceToHigh20dPct') is not None else None
    wall = t.get('volumeWallRisk') or '낮음'
    breakout = t.get('breakoutState') or ''
    if dist20 is not None and dist20 >= 0 and wall != '높음':
        return {'state': '돌파우호', 'bias': 4, 'reason': f'{breakout}; 20일 전고점 대비 {dist20:.2f}%, 매물벽 위험 {wall}'}
    if wall == '높음':
        return {'state': '매물대주의', 'bias': -6, 'reason': '상단 매물대가 가까워 돌파 확인 전 추격 주의'}
    if dist20 is not None and -3 <= dist20 < 0:
        return {'state': '전고점대기', 'bias': -2, 'reason': f'20일 전고점까지 {abs(dist20):.2f}% 남아 돌파 확인 필요'}
    if dist20 is not None and dist20 < -10:
        return {'state': '저항거리큼', 'bias': -3, 'reason': f'20일 전고점까지 {abs(dist20):.2f}% 거리; 회복 확인 필요'}
    return {'state': '구조중립', 'bias': 0, 'reason': f'{breakout or "가격 구조 중립"}; 매물벽 위험 {wall}'}


def public_fundamentals(code):
    f = FUNDAMENTALS_BY_CODE.get(str(code or '').zfill(6)) or FUNDAMENTALS_BY_CODE.get(str(code or ''))
    if not isinstance(f, dict):
        return None
    kis = f.get('kisEnrichment') if isinstance(f.get('kisEnrichment'), dict) else None
    if kis:
        # Public dashboard label only. Keep the data, avoid noisy vendor/API wording
        # in public JSON and automation safety reports.
        kis = json.loads(json.dumps(kis, ensure_ascii=False))
        kis['source'] = 'K-O-R'
    signal = technical_analysis_signal(f)
    expert = f.get('expertAnalysis') if isinstance(f.get('expertAnalysis'), dict) else {}
    public_expert = None
    if expert:
        public_expert = {
            'stance': public_text(expert.get('stance'), 40),
            'score': expert.get('score'),
            'summary': public_text(expert.get('summary'), 260),
            'keyPoints': [public_text(x, 260) for x in (expert.get('keyPoints') or [])[:5]],
            'upsideTriggers': [public_text(x, 260) for x in (expert.get('upsideTriggers') or [])[:4]],
            'riskSignals': [public_text(x, 280) for x in (expert.get('riskSignals') or [])[:5]],
            'actionPoints': [public_text(x, 260) for x in (expert.get('actionPoints') or [])[:3]],
            'additionalDataNeeded': [public_text(x, 260) for x in (expert.get('additionalDataNeeded') or [])[:5]],
            'basis': [public_text(x, 120) for x in (expert.get('basis') or [])[:5]],
            'disclaimer': public_text(expert.get('disclaimer'), 220),
        }
    return {
        'per': f.get('per'),
        'pbr': f.get('pbr'),
        'roe': f.get('roe'),
        'peerAverage': f.get('peerAverage') if isinstance(f.get('peerAverage'), dict) else {},
        'badge': public_text(f.get('badge') or '', 40),
        'report': [public_text(x, 180) for x in (f.get('report') or [])[:4]],
        'expertAnalysis': public_expert,
        'technicalStructure': f.get('technicalStructure') if isinstance(f.get('technicalStructure'), dict) else None,
        'technicalSignal': signal,
        'kisEnrichment': kis,
        'universeStatus': f.get('universeStatus'),
        'updatedAt': f.get('updatedAt'),
        'source': f.get('source'),
    }


def dashboard_holding_judgement(sid, p):
    ret = n(p.get('returnPct'))
    score = p.get('currentScoreNormalized')
    score_num = n(score) if score is not None else None
    if sid == 'jaesang.short.mock':
        if ret <= -4:
            return '손절검토', f'단기 손절 기준 {ret:.2f}% <= -4%'
        if ret >= 8:
            return '2차익절/트레일링', f'단기 2차 익절권 {ret:.2f}% >= 8%'
        if ret >= 5:
            return '부분익절검토', f'단기 1차 익절권 {ret:.2f}% >= 5%'
        if score_num is not None and score_num < 60:
            return '단기점수약화', f'현재 판단점수 {score_num:.1f}; 단기 후보 강도 약화'
    elif sid == 'jinhye.general.mock':
        if ret <= -8:
            return '손절검토', f'일반 손절 기준 {ret:.2f}% <= -8%'
        if ret >= 20:
            return '2차익절/리밸런싱', f'일반 2차 익절권 {ret:.2f}% >= 20%'
        if ret >= 12:
            return '부분익절검토', f'일반 1차 익절권 {ret:.2f}% >= 12%'
        if score_num is not None and score_num < 50:
            return '보유근거약화', f'현재 판단점수 {score_num:.1f}; 신규 후보 강도 약함'
    return '보유유지', '보유 기준상 즉시 매도 신호 없음'


def attach_public_fundamentals(items):
    for x in items or []:
        if isinstance(x, dict):
            x['fundamentals'] = x.get('fundamentals') or public_fundamentals(x.get('code'))


def enrich_comparison_fields(s, sid):
    pf = s.get('portfolio') or {}
    positions = pf.get('positions') if isinstance(pf.get('positions'), list) else []
    candidates = s.get('topCandidates') if isinstance(s.get('topCandidates'), list) else []
    attach_public_fundamentals(candidates)
    attach_public_fundamentals(s.get('buyAlerts') if isinstance(s.get('buyAlerts'), list) else [])
    attach_public_fundamentals(s.get('sellAlerts') if isinstance(s.get('sellAlerts'), list) else [])
    by_code = {str(c.get('code') or ''): c for c in candidates if isinstance(c, dict)}
    for p in positions:
        if not isinstance(p, dict):
            continue
        matched = by_code.get(str(p.get('code') or '')) or {}
        current_norm = matched.get('score') if matched.get('score') is not None else p.get('sourceScoreNormalized')
        current_raw = matched.get('rawScore') if matched.get('rawScore') is not None else None
        score_type = 'current' if matched.get('score') is not None else 'holding'
        p['fundamentals'] = p.get('fundamentals') or public_fundamentals(p.get('code'))
        if matched.get('score') is None and current_norm is not None:
            adjusted_norm, strategy_adj = apply_strategy_adjustment(current_norm, sid, p.get('fundamentals'))
            p['baseScoreNormalized'] = round(n(current_norm), 1)
            p['scoreAdjustment'] = strategy_adj
            current_norm = adjusted_norm
        else:
            p['baseScoreNormalized'] = matched.get('baseScoreNormalized') if matched.get('baseScoreNormalized') is not None else (round(n(current_norm), 1) if current_norm is not None else None)
            p['scoreAdjustment'] = matched.get('scoreAdjustment')
        p['currentScoreNormalized'] = round(n(current_norm), 1) if current_norm is not None else None
        p['currentScoreRaw'] = round(n(current_raw), 1) if current_raw is not None else None
        p['currentScoreType'] = score_type
        p['technicalDecision'] = (p.get('fundamentals') or {}).get('technicalSignal')
        quote_snapshot = None
        if matched.get('changePct') is None or matched.get('currentPrice') in (None, '', 0):
            quote_snapshot = readonly_quote_snapshot(p.get('code'))
            if quote_snapshot:
                if matched.get('changePct') is None and quote_snapshot.get('currentChangePct') is not None:
                    matched['changePct'] = quote_snapshot.get('currentChangePct')
                if matched.get('currentPrice') in (None, '', 0) and quote_snapshot.get('currentPrice'):
                    matched['currentPrice'] = quote_snapshot.get('currentPrice')
                if quote_snapshot.get('currentDelta') is not None:
                    p['currentDelta'] = quote_snapshot.get('currentDelta')
        if matched.get('currentPrice') not in (None, '', 0):
            p['currentPrice'] = matched.get('currentPrice')
            qty_for_eval = n(p.get('qty'))
            if qty_for_eval > 0:
                p['evalAmount'] = round(qty_for_eval * n(p.get('currentPrice')))
                if p.get('entryPrice') not in (None, '', 0):
                    p['pnl'] = round((n(p.get('currentPrice')) - n(p.get('entryPrice'))) * qty_for_eval)
                    p['returnPct'] = round((n(p.get('currentPrice')) - n(p.get('entryPrice'))) / n(p.get('entryPrice')) * 100, 2)
        p['currentChangePct'] = matched.get('changePct') if matched.get('changePct') is not None else p.get('sourceChangePct')
        p['entryScoreRaw'] = p.get('entryScoreRaw') if p.get('entryScoreRaw') is not None else p.get('sourceScore')
        p['entryScoreNormalized'] = p.get('entryScoreNormalized') if p.get('entryScoreNormalized') is not None else p.get('sourceScoreNormalized')
        p['replacementWatchLine'] = replacement_watch_line(p.get('currentScoreNormalized'))
        p['liquidityText'] = liquidity_evidence_text((matched or {}).get('reason') or p.get('entryReason') or '')
        if not p.get('holdAction'):
            action, reason = dashboard_holding_judgement(sid, p)
            p['holdAction'] = action
            tech = p.get('technicalDecision') or {}
            if tech.get('state') in ('매물대주의', '전고점대기', '저항거리큼'):
                reason = f"{reason}; 기술구조 {tech.get('state')} - {tech.get('reason')}"
            elif tech.get('state') == '돌파우호':
                reason = f"{reason}; 기술구조 돌파우호"
            p['holdReason'] = reason
    held_scores = [n(p.get('currentScoreNormalized')) for p in positions if isinstance(p, dict) and p.get('currentScoreNormalized') is not None]
    lowest_held = min(held_scores) if held_scores else None
    for c in candidates:
        if not isinstance(c, dict):
            continue
        c['candidateScoreNormalized'] = c.get('score')
        c['candidateScoreRaw'] = c.get('rawScore')
        c['comparisonBaseScore'] = round(lowest_held, 1) if lowest_held is not None else None
        c['replacementWatchLine'] = replacement_watch_line(lowest_held)
        c['scoreVsHeldLowest'] = round(n(c.get('score')) - lowest_held, 1) if c.get('score') is not None and lowest_held is not None else None
        c['liquidityText'] = c.get('liquidityText') or liquidity_evidence_text(c.get('reason') or '')
        c['fundamentals'] = c.get('fundamentals') or public_fundamentals(c.get('code'))
        c['technicalDecision'] = c.get('technicalDecision') or (c.get('fundamentals') or {}).get('technicalSignal')
        tech = c.get('technicalDecision') or {}
        if tech.get('state') in ('매물대주의', '전고점대기', '저항거리큼', '돌파우호'):
            note = f"기술구조 {tech.get('state')}: {tech.get('reason')}"
            c['candidateNote'] = f"{c.get('candidateNote')} · {note}" if c.get('candidateNote') and note not in c.get('candidateNote') else (c.get('candidateNote') or note)

def reconcile_portfolio_from_positions(s):
    """Keep card totals aligned with the currently displayed holding rows."""
    pf = s.get('portfolio') if isinstance(s.get('portfolio'), dict) else None
    if not pf:
        return
    positions = pf.get('positions') if isinstance(pf.get('positions'), list) else []
    if not positions:
        return
    position_eval = sum(n(p.get('evalAmount')) for p in positions if isinstance(p, dict))
    if position_eval <= 0:
        return
    cash = n(pf.get('cash')) if pf.get('cash') not in (None, '') else 0
    eval_amount = cash + position_eval
    capital = n(pf.get('capital'))
    pnl = eval_amount - capital if capital else sum(n(p.get('pnl')) for p in positions if isinstance(p, dict))
    pf['investmentAmount'] = round(position_eval)
    pf['evalAmount'] = round(eval_amount)
    pf['pnl'] = round(pnl)
    pf['returnPct'] = round(pnl / capital * 100, 2) if capital else pf.get('returnPct')
    pf['positionCount'] = len([p for p in positions if isinstance(p, dict) and n(p.get('qty')) > 0])
    daily_weighted = []
    daily_pnl = 0
    for p in positions:
        if not isinstance(p, dict):
            continue
        change = p.get('currentChangePct')
        if change in (None, ''):
            continue
        eval_v = n(p.get('evalAmount'))
        daily_weighted.append((eval_v, n(change)))
        if p.get('currentDelta') not in (None, ''):
            daily_pnl += n(p.get('currentDelta')) * n(p.get('qty'))
        elif p.get('currentPrice') not in (None, '', 0):
            prev = n(p.get('currentPrice')) / (1 + n(change) / 100) if (1 + n(change) / 100) else 0
            daily_pnl += (n(p.get('currentPrice')) - prev) * n(p.get('qty'))
    if daily_weighted:
        denom = sum(w for w, _ in daily_weighted) or 0
        s['daily'] = {
            'returnPct': round(sum(w * c for w, c in daily_weighted) / denom, 2) if denom else None,
            'pnl': round(daily_pnl),
            'basis': 'holding-prev-close',
        }

sessions = [
    {'runtimeId':'jinhye.general.mock','name':'일반','stage':'운영'},
    {'runtimeId':'jaesang.short.mock','name':'단기','stage':'운영'},
    {'runtimeId':'jaesang.surge.mock','name':'급등','stage':'관찰'},
    {'runtimeId':'jaesang.dailynew.mock','name':'매일신규','stage':'관찰'},
    {'runtimeId':'jaesang.quant.value.mock','name':'퀀트가치','stage':'관찰'},
    {'runtimeId':'jaesang.quant.momentum.mock','name':'퀀트모멘텀','stage':'관찰'},
    {'runtimeId':'jaesang.quant.mixed.mock','name':'퀀트혼합','stage':'관찰'},
]
session_runtime_ids = [s['runtimeId'] for s in sessions]
for s in sessions:
    private_id = s['runtimeId']
    s['runtimeIdForComparison'] = private_id
    s.update(session_status(private_id))
    acct = account_summary(private_id)
    if acct:
        s['portfolio'] = acct
        held_by_code = {str(p.get('code') or ''): p for p in (acct.get('positions') or []) if isinstance(p, dict)}
        if held_by_code and s.get('topCandidates'):
            for c in s.get('topCandidates') or []:
                p = held_by_code.get(str(c.get('code') or ''))
                if not p:
                    continue
                c['status'] = '보유중'
                if not c.get('candidateNote'):
                    c['candidateNote'] = f"{p.get('holdingPeriod') or '보유중'} · 매입 {p.get('entryPrice') or '-'}원 · 현재 {p.get('currentPrice') or '-'}원 · 평가 {p.get('evalAmount') or '-'}원 · 손익 {p.get('pnl') or 0}원"
        if not s.get('buyAlerts') and acct.get('positions'):
            s['buyAlerts'] = [{
                'code': p.get('code'),
                'name': p.get('name'),
                'status': '보유중',
                'reason': f"{p.get('qty')}주 · 매입 {p.get('entryPrice') or '-'}원 · 현재 {p.get('currentPrice') or '-'}원 · 평가 {p.get('evalAmount')}원 · 손익 {p.get('pnl')}원",
                'returnPct': p.get('returnPct'),
                'holdingPeriod': p.get('holdingPeriod'),
            } for p in acct.get('positions', [])[:4]]
        enrich_comparison_fields(s, private_id)
        synthetic_sell = []
        for p in (s.get('portfolio') or {}).get('positions') or []:
            if not isinstance(p, dict) or p.get('holdAction') in (None, '', '보유유지'):
                continue
            synthetic_sell.append({
                'code': p.get('code'),
                'name': p.get('name'),
                'status': f"검토: {p.get('holdAction')}",
                'reason': f"보유 {p.get('qty') or '-'}주 · 실제 매도 미체결 · 검토수량 미정 · {p.get('holdReason') or ''}",
                'returnPct': p.get('returnPct'),
                'pnl': p.get('pnl'),
                'heldQty': p.get('qty'),
                'sellQty': None,
                'executedQty': 0,
                'executionStatus': 'REVIEW_ONLY_NOT_EXECUTED',
                'fundamentals': p.get('fundamentals') or public_fundamentals(p.get('code')),
            })
        if synthetic_sell:
            s['sellAlerts'] = synthetic_sell[:4]
        reconcile_portfolio_from_positions(s)
    else:
        s['portfolio'] = {'capital': None, 'evalAmount': None, 'pnl': None, 'returnPct': None, 'positionCount': (s.get('performance') or {}).get('positionCount')}
    if private_id in VIRTUAL_LEDGER_IDS:
        # New panels may not have runtime yet; still show initialized status
        if s['status']=='NO_DATA': s['status']='INITIALIZED'
    if not acct:
        enrich_comparison_fields(s, private_id)
    s.pop('runtimeId', None)
    s.pop('id', None)

benchmark = benchmark_snapshot()
kodex_benchmark = kodex200_snapshot()
summary = {
    'totalSessions': len(sessions),
    'staleCount': sum(1 for s in sessions if s['status']=='STALE'),
    'candidateCount': sum(s['candidateCount'] for s in sessions),
    'protectedRows': sum(s['protectedRows'] for s in sessions),
}
total_capital = sum(n((s.get('portfolio') or {}).get('capital')) for s in sessions if (s.get('portfolio') or {}).get('capital') is not None)
total_eval = sum(n((s.get('portfolio') or {}).get('evalAmount')) for s in sessions if (s.get('portfolio') or {}).get('evalAmount') is not None)
total_pnl = total_eval - total_capital if total_capital else None
summary['totalCapital'] = round(total_capital) if total_capital else None
summary['totalEvalAmount'] = round(total_eval) if total_eval else None
summary['totalPnl'] = round(total_pnl) if total_pnl is not None else None
summary['totalReturnPct'] = round(total_pnl / total_capital * 100, 2) if total_capital and total_pnl is not None else None
# Simple chart series from current snapshot; future generator runs can append history if desired.
history_path = OUT.parent/'dashboard-history.json'
history=[]
try: history=json.loads(history_path.read_text(encoding='utf-8'))
except Exception: pass
reset_id = LIVE_MOCK_RESET_EPOCH.isoformat(timespec='minutes') + ':clean-start-v3'
history=[x for x in history if isinstance(x, dict) and x.get('dataEpoch') == reset_id]
active_starts = []
for sid, s in zip(session_runtime_ids, sessions):
    if sid and has_actual_buy(s):
        t = first_investment_time(sid)
        if t: active_starts.append(t)
market_dashboard_start = min(active_starts) if active_starts else None
period_ret, period_start, period_end = benchmark_return_since(history, benchmark, market_dashboard_start) if market_dashboard_start else (None, None, None)
benchmark['returnPct'] = period_ret
benchmark['periodStart'] = period_start
benchmark['periodEnd'] = period_end
benchmark['basis'] = 'firstInvestment' if market_dashboard_start else 'noInvestmentYet'
kodex_ret, kodex_start, kodex_end = benchmark_return_since(history, kodex_benchmark, market_dashboard_start, 'kodex200Value') if market_dashboard_start else (None, None, None)
kodex_benchmark['returnPct'] = kodex_ret
kodex_benchmark['periodStart'] = kodex_start
kodex_benchmark['periodEnd'] = kodex_end
kodex_benchmark['basis'] = 'firstInvestment' if market_dashboard_start else 'noInvestmentYet'

for sid, s in zip(session_runtime_ids, sessions):
    cr = comparable_return(s)
    invest_start = first_investment_time(sid) if sid else None
    market_ret, market_start, market_end = benchmark_return_since(history, benchmark, invest_start) if has_actual_buy(s) else (None, None, None)
    s['comparison'] = {'returnPct': cr, 'benchmarkReturnPct': market_ret, 'excessReturnPct': round(cr - market_ret, 2) if cr is not None and market_ret is not None else None}
    if market_start or market_end:
        s['comparison']['periodStart'] = market_start
        s['comparison']['periodEnd'] = market_end
    s.pop('runtimeIdForComparison', None)
    s.pop('strategyReview', None)
    s.pop('performance', None)

point={'ts': datetime.datetime.now(KST).isoformat(timespec='minutes'), 'dataEpoch': reset_id, 'candidates': summary['candidateCount'], 'protected': summary['protectedRows'], 'stale': summary['staleCount'], 'benchmark': benchmark.get('returnPct'), 'benchmarkValue': benchmark.get('value'), 'kodex200': kodex_benchmark.get('returnPct'), 'kodex200Value': kodex_benchmark.get('value'), 'returns':[ (x.get('comparison') or {}).get('returnPct') for x in sessions ], 'marketReturns':[ (x.get('comparison') or {}).get('benchmarkReturnPct') for x in sessions ], 'evalAmounts':[ (x.get('portfolio') or {}).get('evalAmount') for x in sessions ], 'capital':[ (x.get('portfolio') or {}).get('capital') for x in sessions ]}
history.append(point); history=history[-120:]
overall_series = benchmark_series(history, market_dashboard_start)
overall_kodex_series = benchmark_series(history, market_dashboard_start, 'kodex200Value')
session_starts = [first_investment_time(sid) if has_actual_buy(s) else None for sid, s in zip(session_runtime_ids, sessions)]
session_series = [benchmark_series(history, st) for st in session_starts]
session_kodex_series = [benchmark_series(history, st, 'kodex200Value') for st in session_starts]
for idx, x in enumerate(history):
    x['benchmark'] = overall_series[idx] if idx < len(overall_series) else None
    x['kodex200'] = overall_kodex_series[idx] if idx < len(overall_kodex_series) else None
    x['marketReturns'] = [series[idx] if idx < len(series) else None for series in session_series]
    x['kodexReturns'] = [series[idx] if idx < len(series) else None for series in session_kodex_series]
history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')

data={'generatedAt': point['ts'], 'summary':summary, 'benchmark':benchmark, 'kodexBenchmark':kodex_benchmark, 'sessions':sessions, 'history':history, 'notice':'Dashboard reset; previous metrics are not inherited.'}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(OUT)
