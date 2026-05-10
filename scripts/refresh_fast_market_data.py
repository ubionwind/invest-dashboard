#!/usr/bin/env python3
"""Fast market layer refresh for the public dashboard.

Updates only lightweight, fast-changing fields from read-only quotes:
- holding currentPrice/currentChangePct/currentDelta
- holding evalAmount/pnl/returnPct
- portfolio investmentAmount/evalAmount/pnl/returnPct
- session daily return/PnL from holding previous-close change
- summary totals and latest history point

It intentionally does NOT recalculate candidates, fundamentals, technical analysis,
or order/strategy decisions. Those belong to slower strategy/analysis layers.
"""
import datetime as dt
import json
import pathlib
import csv
import io
import re
import urllib.parse
import urllib.request
import zipfile

ROOT = pathlib.Path('/home/ubion/.openclaw/workspace')
DASH = ROOT / 'shared/invest-dashboard'
DATA = DASH / 'data/dashboard-data.json'
SURVIVAL_REVIEW = DASH / 'data/survival-review.json'
FUTURES_HISTORY = DASH / 'data/futures/stock_futures_history.json'
KIS_ENV_PATH = ROOT / 'shared/invest_api_common/secrets/.env.local'
TOKEN_CACHE = ROOT / 'shared/invest_api_common/runtime/kis_token_cache'
RUNTIME = ROOT / 'shared/invest_api_common/runtime'
KIS_BASE = 'https://openapivts.koreainvestment.com:29443'
STOCK_FUTURE_MASTER_URL = 'https://new.real.download.dws.co.kr/common/master/fo_stk_code_mts.mst.zip'
KST = dt.timezone(dt.timedelta(hours=9))
NXT_QUOTE_CACHE = {}


def n(v):
    try:
        return float(str(v).replace(',', '').strip() or 0)
    except Exception:
        return 0.0


def load_env_file(path):
    out = {}
    try:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'content-type': 'application/json; charset=utf-8'},
        method='POST',
    )
    return json.loads(urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'replace'))


def cached_access_token(private_id='jaesang.short.mock'):
    try:
        j = json.loads((TOKEN_CACHE / f'{private_id}.json').read_text(encoding='utf-8'))
        if j.get('accessToken') and float(j.get('expiresAtMs') or 0) - dt.datetime.now().timestamp() * 1000 > 5 * 60 * 1000:
            return j.get('accessToken')
    except Exception:
        pass
    return None


def save_access_token(private_id, tok):
    try:
        TOKEN_CACHE.mkdir(parents=True, exist_ok=True)
        exp = tok.get('access_token_token_expired')
        exp_ms = 0
        if exp:
            exp_ms = dt.datetime.fromisoformat(str(exp).replace(' ', 'T')).timestamp() * 1000
        (TOKEN_CACHE / f'{private_id}.json').write_text(json.dumps({
            'sessionId': private_id,
            'accessToken': tok.get('access_token'),
            'tokenType': tok.get('token_type') or 'Bearer',
            'expiresAt': exp,
            'expiresAtMs': exp_ms,
            'updatedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def access_headers():
    env = load_env_file(KIS_ENV_PATH)
    appkey = env.get('KIS_JAESANG_MOCK_APP_KEY')
    appsecret = env.get('KIS_JAESANG_MOCK_APP_SECRET')
    if not appkey or not appsecret:
        return None
    access = cached_access_token('jaesang.short.mock')
    if not access:
        tok = post_json(f'{KIS_BASE}/oauth2/tokenP', {'grant_type': 'client_credentials', 'appkey': appkey, 'appsecret': appsecret})
        access = tok.get('access_token')
        if access:
            save_access_token('jaesang.short.mock', tok)
    if not access:
        return None
    return {
        'content-type': 'application/json; charset=utf-8',
        'authorization': f'Bearer {access}',
        'appkey': appkey,
        'appsecret': appsecret,
        'tr_id': 'FHKST01010100',
        'custtype': 'P',
    }


def stock_future_headers(headers):
    if not headers:
        return None
    out = dict(headers)
    out['tr_id'] = 'FHMIF10000000'
    return out


def get_json(url, headers):
    req = urllib.request.Request(url, headers=headers, method='GET')
    return json.loads(urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'replace'))


def quote(code, headers, cache):
    code = str(code or '').zfill(6)
    if not code or code == '000000' or not headers:
        return None
    if code in cache:
        return cache[code]
    out = None
    try:
        params = urllib.parse.urlencode({'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': code})
        req = urllib.request.Request(f'{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price?{params}', headers=headers, method='GET')
        j = json.loads(urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'replace'))
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
    cache[code] = out
    return out


def stock_future_master_rows():
    cache_path = RUNTIME / 'marketdata/stock_future_master.json'
    today = dt.datetime.now(KST).date().isoformat()
    try:
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
        if cached.get('date') == today and isinstance(cached.get('rows'), list):
            return cached.get('rows')
    except Exception:
        pass
    rows = []
    try:
        raw = urllib.request.urlopen(STOCK_FUTURE_MASTER_URL, timeout=15).read()
        zf = zipfile.ZipFile(io.BytesIO(raw))
        text = zf.read(zf.namelist()[0]).decode('cp949', 'replace').splitlines()
        for r in csv.reader(text, delimiter='|'):
            if len(r) < 9 or str(r[0]).strip() not in ('1', '3'):
                continue
            name = str(r[3] or '').strip()
            m = re.search(r'F\s+(20\d{4})', name)
            rows.append({
                'productKind': str(r[0]).strip(),
                'futureCode': str(r[1]).strip(),
                'standardCode': str(r[2]).strip(),
                'futureName': name,
                'monthCode': str(r[6]).strip(),
                'underlyingCode': str(r[7]).strip().zfill(6),
                'underlyingName': str(r[8]).strip(),
                'expiryMonth': m.group(1) if m else '',
            })
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({'date': today, 'source': STOCK_FUTURE_MASTER_URL, 'rows': rows}, ensure_ascii=False), encoding='utf-8')
    except Exception:
        rows = []
    return rows


def nearest_stock_future_contract(code, rows):
    code = str(code or '').zfill(6)
    items = [r for r in rows if r.get('underlyingCode') == code and r.get('futureCode')]
    if not items:
        return None
    def key(r):
        try: month_num = int(r.get('expiryMonth') or '999999')
        except Exception: month_num = 999999
        try: month_code = int(r.get('monthCode') or '999')
        except Exception: month_code = 999
        return (month_num, month_code, str(r.get('futureCode') or ''))
    return sorted(items, key=key)[0]


def stock_future_quote(code, headers, stock_cache, future_cache, master_rows):
    code = str(code or '').zfill(6)
    if not code or code == '000000' or not headers:
        return None
    if code in future_cache:
        return future_cache[code]
    contract = nearest_stock_future_contract(code, master_rows)
    if not contract:
        future_cache[code] = None
        return None
    out = None
    try:
        params = urllib.parse.urlencode({'FID_COND_MRKT_DIV_CODE': 'JF', 'FID_INPUT_ISCD': contract.get('futureCode')})
        h = dict(headers)
        h['tr_id'] = 'FHMIF10000000'
        try:
            j = get_json(f'{KIS_BASE}/uapi/domestic-futureoption/v1/quotations/inquire-price?{params}', h)
            o = j.get('output1') if isinstance(j, dict) else {}
        except Exception:
            h['tr_id'] = 'FHMIF10010000'
            j = get_json(f'{KIS_BASE}/uapi/domestic-futureoption/v1/quotations/inquire-asking-price?{params}', h)
            o = j.get('output1') if isinstance(j, dict) else {}
        price = n((o or {}).get('futs_prpr'))
        if price > 0:
            underlying = quote(code, headers, stock_cache) or naver_stock_quote(code) or {}
            underlying_price = n(underlying.get('currentPrice'))
            spread = price - underlying_price if underlying_price > 0 else None
            spread_pct = spread / underlying_price * 100 if spread is not None and underlying_price else None
            fut_chg = round(n(o.get('futs_prdy_ctrt')), 2) if o.get('futs_prdy_ctrt') not in (None, '') else None
            volume = round(n(o.get('acml_vol'))) if o.get('acml_vol') not in (None, '') else None
            under_chg = underlying.get('currentChangePct')
            rel = fut_chg - n(under_chg) if fut_chg is not None and under_chg is not None else None
            signal = '선물중립'
            signalReason = '체결가 기준 상대강도'
            if (volume in (None, 0)) and (fut_chg in (None, 0)):
                signal = '선물장전대기'
                signalReason = '체결/거래량 미확인; 장전 호가 신호 아님'
                rel = None
            elif rel is not None and rel >= 1.0:
                signal = '선물강세'
            elif rel is not None and rel <= -1.0:
                signal = '선물약세'
            out = {
                'market': 'KRX 주식선물',
                'underlyingCode': code,
                'futureCode': contract.get('futureCode'),
                'futureName': (o or {}).get('hts_kor_isnm') or contract.get('futureName'),
                'expiryMonth': contract.get('expiryMonth'),
                'expiryDate': (o or {}).get('futs_last_tr_date') or None,
                'remainingDays': round(n((o or {}).get('hts_rmnn_dynu'))) if (o or {}).get('hts_rmnn_dynu') not in (None, '') else None,
                'price': round(price),
                'delta': round(n(o.get('futs_prdy_vrss'))) if o.get('futs_prdy_vrss') not in (None, '') else None,
                'changePct': fut_chg,
                'volume': volume,
                'tradingValue': round(n(o.get('acml_tr_pbmn'))) if o.get('acml_tr_pbmn') not in (None, '') else None,
                'openInterest': round(n(o.get('hts_otst_stpl_qty'))) if o.get('hts_otst_stpl_qty') not in (None, '') else None,
                'openInterestChange': round(n(o.get('otst_stpl_qty_icdc'))) if o.get('otst_stpl_qty_icdc') not in (None, '') else None,
                'theoreticalPrice': round(n(o.get('hts_thpr'))) if o.get('hts_thpr') not in (None, '') else None,
                'disparityPct': round(n(o.get('dprt')), 2) if o.get('dprt') not in (None, '') else None,
                'basis': round(n(o.get('basis'))) if o.get('basis') not in (None, '') else None,
                'marketBasis': round(n(o.get('mrkt_basis'))) if o.get('mrkt_basis') not in (None, '') else None,
                'underlyingPrice': round(underlying_price) if underlying_price > 0 else None,
                'spotSpread': round(spread) if spread is not None else None,
                'spotSpreadPct': round(spread_pct, 2) if spread_pct is not None else None,
                'relativeStrengthPct': round(rel, 2) if rel is not None else None,
                'signal': signal,
                'signalReason': signalReason,
                'basisText': 'reference-only; cash KRX close remains official P/L basis',
                'source': 'kis-domestic-futureoption-readonly-fast',
                'updatedAt': dt.datetime.now(KST).isoformat(timespec='minutes'),
            }
    except Exception:
        out = None
    future_cache[code] = out
    return out


def walk_stock_items(x, out=None):
    if out is None:
        out = []
    if isinstance(x, list):
        for v in x:
            walk_stock_items(v, out)
    elif isinstance(x, dict):
        if x.get('code') and isinstance(x.get('fundamentals'), dict):
            out.append(x)
        for v in x.values():
            walk_stock_items(v, out)
    return out


def load_futures_history():
    try:
        j = json.loads(FUTURES_HISTORY.read_text(encoding='utf-8'))
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


def save_futures_history(history):
    FUTURES_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    FUTURES_HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def refresh_stock_futures(data, headers, stock_cache):
    master_rows = stock_future_master_rows()
    future_cache = {}
    items = walk_stock_items(data)
    codes = sorted({str(x.get('code') or '').zfill(6) for x in items if x.get('code')})
    history = load_futures_history()
    now = dt.datetime.now(KST).isoformat(timespec='minutes')
    changed = 0
    for code in codes:
        fq = stock_future_quote(code, stock_future_headers(headers), stock_cache, future_cache, master_rows)
        if not fq:
            continue
        row = {
            'ts': now,
            'futureCode': fq.get('futureCode'),
            'price': fq.get('price'),
            'changePct': fq.get('changePct'),
            'volume': fq.get('volume'),
            'openInterest': fq.get('openInterest'),
            'spotSpreadPct': fq.get('spotSpreadPct'),
            'relativeStrengthPct': fq.get('relativeStrengthPct'),
            'signal': fq.get('signal'),
        }
        arr = [x for x in history.get(code, []) if isinstance(x, dict)]
        if arr and arr[-1].get('ts') == now:
            arr[-1] = row
        else:
            arr.append(row)
        history[code] = arr[-240:]
    save_futures_history(history)
    for item in items:
        code = str(item.get('code') or '').zfill(6)
        fq = future_cache.get(code)
        if not fq:
            continue
        fq = dict(fq)
        fq['trend'] = history.get(code, [])[-60:]
        item['fundamentals']['stockFutureQuote'] = fq
        changed += 1
    data['stockFutureSummary'] = {
        'updatedAt': now,
        'trackedCodes': len([c for c, q in future_cache.items() if q]),
        'snapshotRows': sum(len(v) for v in history.values() if isinstance(v, list)),
        'source': 'kis-domestic-futureoption-readonly-fast',
    }
    return changed


def naver_stock_quote(code):
    try:
        req = urllib.request.Request(
            f'https://m.stock.naver.com/api/stock/{str(code).zfill(6)}/basic',
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        r = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace'))
        price = n(r.get('closePrice'))
        if price > 0:
            return {
                'currentPrice': round(price),
                'currentChangePct': round(n(r.get('fluctuationsRatio')), 2) if r.get('fluctuationsRatio') not in (None, '') else None,
                'currentDelta': round(n(r.get('compareToPreviousClosePrice'))) if r.get('compareToPreviousClosePrice') not in (None, '') else None,
                'source': 'naver-stock-basic',
                'marketStatus': r.get('marketStatus'),
            }
    except Exception:
        pass
    return None


def market_index_snapshot():
    try:
        req = urllib.request.Request(
            'https://m.stock.naver.com/api/index/KOSPI/basic',
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        r = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace'))
        price = n(r.get('closePrice'))
        traded_at = None
        try:
            traded_at = dt.datetime.fromisoformat(str(r.get('localTradedAt')).replace('Z', '+00:00')).astimezone(KST)
        except Exception:
            pass
        if price > 0:
            return {
                'label': 'KOSPI',
                'value': round(price, 2),
                'dailyReturnPct': round(n(r.get('fluctuationsRatio')), 2) if r.get('fluctuationsRatio') not in (None, '') else None,
                'date': traded_at.date().isoformat() if traded_at else None,
                'time': traded_at.strftime('%H:%M:%S') if traded_at else None,
                'source': 'naver-index-basic',
                'marketStatus': r.get('marketStatus'),
            }
    except Exception:
        pass
    return None


def first_value_since(history, value_key, start_ts=None):
    rows = []
    for x in history or []:
        if not isinstance(x, dict) or x.get(value_key) in (None, '', 0):
            continue
        ts = x.get('ts')
        if start_ts and ts and ts < start_ts:
            continue
        rows.append((ts, n(x.get(value_key))))
    return rows[0] if rows else (None, None)


def return_since(history, value_key, current_value, start_ts=None):
    base_ts, base_value = first_value_since(history, value_key, start_ts)
    if current_value in (None, '', 0) or not base_value:
        return None


def nxt_quote_snapshot(code):
    """Refresh NXT pre/after-market quote during fast-market runs.

    NXT is reference-only and must not drive KRX P/L, but it is time-sensitive
    enough that waiting for the slower full analysis layer makes the dashboard
    look stale during pre/after sessions.
    """
    code = str(code or '').zfill(6)
    if not code or code == '000000':
        return None
    if code in NXT_QUOTE_CACHE:
        return NXT_QUOTE_CACHE[code]
    out = None
    try:
        req = urllib.request.Request(f'https://m.stock.naver.com/domestic/stock/{code}/total', headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace')
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if m:
            data = json.loads(m.group(1))
            queries = (((data.get('props') or {}).get('pageProps') or {}).get('dehydratedState') or {}).get('queries') or []
            for q in queries:
                result = (((q.get('state') or {}).get('data') or {}).get('result') or {}) if isinstance(q, dict) else {}
                info = result.get('overMarketPriceInfo') if isinstance(result, dict) else None
                if isinstance(info, dict) and info.get('overPrice') not in (None, ''):
                    price = n(info.get('overPrice'))
                    if price > 0:
                        out = {
                            'market': 'NXT',
                            'session': info.get('tradingSessionType'),
                            'status': info.get('overMarketStatus'),
                            'price': round(price),
                            'delta': round(n(info.get('compareToPreviousClosePrice'))) if info.get('compareToPreviousClosePrice') not in (None, '') else None,
                            'changePct': round(n(info.get('fluctuationsRatio')), 2) if info.get('fluctuationsRatio') not in (None, '') else None,
                            'localTradedAt': info.get('localTradedAt'),
                            'basis': 'reference-only; KRX close remains official P/L basis',
                            'source': 'naver-nxt-overmarket-fast',
                            'updatedAt': dt.datetime.now(KST).isoformat(timespec='minutes'),
                        }
                    break
    except Exception:
        out = None
    NXT_QUOTE_CACHE[code] = out
    return out


def refresh_nxt_references(data):
    changed = 0
    for item in walk_stock_items(data):
        f = item.get('fundamentals')
        if not isinstance(f, dict):
            continue
        q = nxt_quote_snapshot(item.get('code'))
        if not q:
            continue
        if f.get('nxtQuote') != q:
            f['nxtQuote'] = q
            changed += 1
    data['nxtSummary'] = {
        'updatedAt': dt.datetime.now(KST).isoformat(timespec='minutes'),
        'trackedCodes': len([q for q in NXT_QUOTE_CACHE.values() if q]),
        'source': 'naver-nxt-overmarket-fast',
    }
    return changed


def apply_market_lead_overlay(item, source='candidate'):
    if not isinstance(item, dict):
        return 0
    f = item.get('fundamentals') if isinstance(item.get('fundamentals'), dict) else {}
    nxt = f.get('nxtQuote') if isinstance(f.get('nxtQuote'), dict) else {}
    fut = f.get('stockFutureQuote') if isinstance(f.get('stockFutureQuote'), dict) else {}
    reasons = []
    delta = 0
    try:
        nxt_num = float(nxt.get('changePct')) if nxt.get('changePct') not in (None, '') else None
    except Exception:
        nxt_num = None
    if nxt_num is not None:
        if nxt_num >= 6:
            delta += 4; reasons.append(f'NXT 강한 상승 {nxt_num:.2f}%')
        elif nxt_num >= 3:
            delta += 2; reasons.append(f'NXT 상승 {nxt_num:.2f}%')
        elif nxt_num <= -4:
            delta -= 5; reasons.append(f'NXT 약세 {nxt_num:.2f}%')
        elif nxt_num <= -2:
            delta -= 3; reasons.append(f'NXT 하락 {nxt_num:.2f}%')
    fut_signal = fut.get('signal')
    fut_vol = fut.get('volume')
    fut_rel = fut.get('relativeStrengthPct')
    if fut_signal == '선물강세' and fut_vol not in (None, 0):
        delta += 4; reasons.append('주식선물 체결 강세')
    elif fut_signal == '선물약세' and fut_vol not in (None, 0):
        delta -= 5; reasons.append('주식선물 체결 약세')
    elif fut_signal == '선물장전대기' or fut_vol in (None, 0):
        reasons.append('주식선물 체결/거래량 미확인')
    try:
        rel_num = float(fut_rel) if fut_rel not in (None, '') else None
    except Exception:
        rel_num = None
    if rel_num is not None:
        if rel_num >= 1.5:
            delta += 2; reasons.append(f'선물 상대강도 +{rel_num:.2f}%p')
        elif rel_num <= -1.5:
            delta -= 2; reasons.append(f'선물 상대약세 {rel_num:.2f}%p')
    delta = max(-10, min(10, delta))
    stance = '우호' if delta >= 5 else ('위험' if delta <= -5 else ('소폭우호' if delta > 0 else ('소폭위험' if delta < 0 else '중립')))
    overlay = {
        'stance': stance,
        'scoreDelta': delta,
        'reasons': reasons[:5],
        'nxtChangePct': nxt_num,
        'futureSignal': fut_signal,
        'futureVolume': fut_vol,
        'plain': 'NXT·주식선물은 단독 실행 신호가 아니라 장전/장중 우선순위와 재점검 강도를 조정하는 보조 신호입니다.',
    }
    f['marketLeadSignal'] = overlay
    item['marketLeadSignal'] = overlay
    if delta:
        key = 'currentScoreNormalized' if item.get('currentScoreNormalized') is not None else 'score'
        if item.get(key) not in (None, ''):
            try:
                base = float(item.get(key))
                item[f'preMarketLead{key[0].upper()}{key[1:]}'] = round(base, 1)
                item[key] = round(max(0, min(100, base + delta)), 1)
                if key == 'score':
                    item['currentScoreNormalized'] = item.get('score')
            except Exception:
                pass
    note = ' · '.join(reasons[:3])
    if note:
        item['marketLeadNote'] = note
    if source in ('holding', 'sell'):
        if delta <= -5:
            item['reviewAction'] = item.get('reviewAction') or '시장선행 약세 점검'
            item['holdAction'] = item.get('holdAction') or '모멘텀 점검'
        elif delta >= 5:
            item['holdReason'] = f"{item.get('holdReason') or ''}; 시장선행 우호: {note}".strip('; ')
    else:
        if delta <= -5:
            item['action'] = item.get('action') or '시장선행 약세로 진입조건 강화'
            item['status'] = item.get('status') if item.get('status') == '보유중' else '시장선행 약세 점검'
        elif delta >= 5:
            item['action'] = item.get('action') or '시장선행 우호 확인'
            item['status'] = item.get('status') or '시장선행 우호'
    return 1


def refresh_market_lead_overlays(data):
    changed = 0
    for session in data.get('sessions') or []:
        for item in ((session.get('portfolio') or {}).get('positions') or []):
            changed += apply_market_lead_overlay(item, 'holding')
        for name, source in [('topCandidates', 'candidate'), ('buyAlerts', 'buy'), ('sellAlerts', 'sell')]:
            for item in session.get(name) or []:
                changed += apply_market_lead_overlay(item, source)
    return changed
    return round((n(current_value) - base_value) / base_value * 100, 2)


def forward_fill_history(history):
    scalar_keys = ['benchmark', 'benchmarkValue', 'kodex200', 'kodex200Value']
    array_keys = ['returns', 'marketReturns', 'kodexReturns', 'evalAmounts', 'capital']
    last_scalar = {}
    last_arrays = {}
    for row in history:
        if not isinstance(row, dict):
            continue
        for key in scalar_keys:
            if row.get(key) in (None, '') and key in last_scalar:
                row[key] = last_scalar[key]
            elif row.get(key) not in (None, ''):
                last_scalar[key] = row.get(key)
        for key in array_keys:
            arr = row.get(key)
            prev = last_arrays.get(key)
            if not isinstance(arr, list):
                if isinstance(prev, list):
                    row[key] = list(prev)
                continue
            if isinstance(prev, list):
                width = max(len(arr), len(prev))
                filled = []
                for i in range(width):
                    value = arr[i] if i < len(arr) else None
                    filled.append(prev[i] if value in (None, '') and i < len(prev) else value)
                arr = filled
                row[key] = arr
            last_arrays[key] = list(arr)
    return history


def backfill_market_return_arrays(history, sessions):
    for idx, session in enumerate(sessions or []):
        start_ts = ((session.get('comparison') or {}).get('periodStart') if isinstance(session, dict) else None) or None
        _, base_kospi = first_value_since(history, 'benchmarkValue', start_ts)
        _, base_kodex = first_value_since(history, 'kodex200Value', start_ts)
        for row in history:
            if not isinstance(row, dict):
                continue
            for key, value_key, base in [('marketReturns', 'benchmarkValue', base_kospi), ('kodexReturns', 'kodex200Value', base_kodex)]:
                arr = row.get(key)
                if not isinstance(arr, list):
                    arr = []
                while len(arr) < len(sessions or []):
                    arr.append(None)
                if arr[idx] in (None, '') and base and row.get(value_key) not in (None, '', 0):
                    arr[idx] = round((n(row.get(value_key)) - base) / base * 100, 2)
                row[key] = arr
    return history


def refresh_benchmarks(data, headers, cache):
    history = data.get('history') or []
    benchmark = data.get('benchmark') if isinstance(data.get('benchmark'), dict) else {}
    snap = market_index_snapshot()
    if snap:
        start_ts = benchmark.get('periodStart')
        base_ts, base_value = first_value_since(history, 'benchmarkValue', start_ts)
        benchmark.update(snap)
        if base_value:
            benchmark['returnPct'] = round((snap['value'] - base_value) / base_value * 100, 2)
            benchmark['periodStart'] = start_ts or base_ts
            benchmark['periodEnd'] = dt.datetime.now(KST).isoformat(timespec='minutes')
            benchmark['basis'] = benchmark.get('basis') or 'firstInvestment'
        data['benchmark'] = benchmark

    kodex = data.get('kodexBenchmark') if isinstance(data.get('kodexBenchmark'), dict) else {'label': 'KODEX 200', 'code': '069500'}
    q = quote(kodex.get('code') or '069500', headers, cache)
    if not q or not q.get('currentPrice'):
        q = naver_stock_quote(kodex.get('code') or '069500')
    if q and q.get('currentPrice'):
        start_ts = kodex.get('periodStart')
        base_ts, base_value = first_value_since(history, 'kodex200Value', start_ts)
        kodex.update({
            'label': 'KODEX 200',
            'code': '069500',
            'value': q.get('currentPrice'),
            'dailyReturnPct': q.get('currentChangePct'),
            'date': dt.datetime.now(KST).date().isoformat(),
            'time': dt.datetime.now(KST).strftime('%H:%M:%S'),
        })
        if q.get('source'):
            kodex['source'] = q.get('source')
        if q.get('marketStatus'):
            kodex['marketStatus'] = q.get('marketStatus')
        if base_value:
            kodex['returnPct'] = round((q['currentPrice'] - base_value) / base_value * 100, 2)
            kodex['periodStart'] = start_ts or base_ts
            kodex['periodEnd'] = dt.datetime.now(KST).isoformat(timespec='minutes')
            kodex['basis'] = kodex.get('basis') or 'firstInvestment'
        data['kodexBenchmark'] = kodex


def reconcile_session(session, headers, cache):
    pf = session.get('portfolio') if isinstance(session.get('portfolio'), dict) else {}
    positions = pf.get('positions') if isinstance(pf.get('positions'), list) else []
    if not positions:
        return False
    changed = False
    for p in positions:
        if not isinstance(p, dict):
            continue
        q = quote(p.get('code'), headers, cache)
        if q:
            p.update({k: v for k, v in q.items() if v is not None})
            changed = True
        qty = n(p.get('qty'))
        price = n(p.get('currentPrice'))
        entry = n(p.get('entryPrice'))
        if qty > 0 and price > 0:
            p['evalAmount'] = round(qty * price)
            if entry > 0:
                p['pnl'] = round((price - entry) * qty)
                p['returnPct'] = round((price - entry) / entry * 100, 2)
    position_eval = sum(n(p.get('evalAmount')) for p in positions if isinstance(p, dict))
    cash = n(pf.get('cash')) if pf.get('cash') not in (None, '') else 0
    eval_amount = position_eval + cash
    capital = n(pf.get('capital'))
    pnl = eval_amount - capital if capital else sum(n(p.get('pnl')) for p in positions if isinstance(p, dict))
    pf['investmentAmount'] = round(position_eval)
    pf['evalAmount'] = round(eval_amount)
    pf['pnl'] = round(pnl)
    pf['returnPct'] = round(pnl / capital * 100, 2) if capital else pf.get('returnPct')
    pf['positionCount'] = len([p for p in positions if isinstance(p, dict) and n(p.get('qty')) > 0])

    weights = []
    daily_pnl = 0.0
    for p in positions:
        if not isinstance(p, dict) or p.get('currentChangePct') in (None, ''):
            continue
        ev = n(p.get('evalAmount'))
        chg = n(p.get('currentChangePct'))
        weights.append((ev, chg))
        if p.get('currentDelta') not in (None, ''):
            daily_pnl += n(p.get('currentDelta')) * n(p.get('qty'))
        elif p.get('currentPrice') not in (None, '', 0):
            prev = n(p.get('currentPrice')) / (1 + chg / 100) if (1 + chg / 100) else 0
            daily_pnl += (n(p.get('currentPrice')) - prev) * n(p.get('qty'))
    if weights:
        denom = sum(w for w, _ in weights)
        session['daily'] = {
            'returnPct': round(sum(w * c for w, c in weights) / denom, 2) if denom else None,
            'pnl': round(daily_pnl),
            'basis': 'fast-holding-prev-close',
        }
    by_code = {str(p.get('code') or ''): p for p in positions if isinstance(p, dict)}
    for arr_name in ('buyAlerts', 'sellAlerts'):
        arr = session.get(arr_name)
        if not isinstance(arr, list):
            continue
        for a in arr:
            if not isinstance(a, dict):
                continue
            # Buy alerts are also the visible holding layer. Their executionStatus
            # can be VIRTUAL_FILLED, but while the position is still open they must
            # follow the refreshed portfolio returnPct/current price. Only skip
            # filled sell/review records.
            if arr_name != 'buyAlerts' and a.get('executionStatus') and 'FILLED' in str(a.get('executionStatus')):
                continue
            p = by_code.get(str(a.get('code') or ''))
            if not p:
                continue
            a['returnPct'] = p.get('returnPct')
            a['pnl'] = p.get('pnl')
            if arr_name == 'buyAlerts':
                a['reason'] = f"{p.get('qty')}주 · 매입 {p.get('entryPrice') or '-'}원 · 현재 {p.get('currentPrice') or '-'}원 · 평가 {p.get('evalAmount')}원 · 손익 {p.get('pnl')}원"
            else:
                a['heldQty'] = p.get('qty')
    return changed


def refresh_summary_and_history(data):
    sessions = data.get('sessions') or []
    total_capital = sum(n((s.get('portfolio') or {}).get('capital')) for s in sessions if (s.get('portfolio') or {}).get('capital') is not None)
    total_eval = sum(n((s.get('portfolio') or {}).get('evalAmount')) for s in sessions if (s.get('portfolio') or {}).get('evalAmount') is not None)
    total_pnl = total_eval - total_capital if total_capital else None
    summary = data.setdefault('summary', {})
    summary['totalCapital'] = round(total_capital) if total_capital else None
    summary['totalEvalAmount'] = round(total_eval) if total_eval else None
    summary['totalPnl'] = round(total_pnl) if total_pnl is not None else None
    summary['totalReturnPct'] = round(total_pnl / total_capital * 100, 2) if total_capital and total_pnl is not None else None
    now = dt.datetime.now(KST).isoformat(timespec='minutes')
    data['generatedAt'] = now
    data['layerMode'] = 'fast-market'
    point = {
        'ts': now,
        'returns': [(s.get('portfolio') or {}).get('returnPct') for s in sessions],
        'evalAmounts': [(s.get('portfolio') or {}).get('evalAmount') for s in sessions],
        'capital': [(s.get('portfolio') or {}).get('capital') for s in sessions],
        'benchmark': (data.get('benchmark') or {}).get('returnPct'),
        'benchmarkValue': (data.get('benchmark') or {}).get('value'),
        'kodex200': (data.get('kodexBenchmark') or {}).get('returnPct'),
        'kodex200Value': (data.get('kodexBenchmark') or {}).get('value'),
        'dataEpoch': '2026-05-06T00:00+09:00:clean-start-v3',
    }
    history = [x for x in (data.get('history') or []) if isinstance(x, dict) and x.get('dataEpoch') == point['dataEpoch']]
    point['marketReturns'] = [return_since(history, 'benchmarkValue', point.get('benchmarkValue'), (s.get('comparison') or {}).get('periodStart')) for s in sessions]
    point['kodexReturns'] = [return_since(history, 'kodex200Value', point.get('kodex200Value'), (s.get('comparison') or {}).get('periodStart')) for s in sessions]
    if history and history[-1].get('ts') == now:
        history[-1] = point
    else:
        history.append(point)
    data['history'] = backfill_market_return_arrays(forward_fill_history(history[-120:]), sessions)


def sync_survival_review_snapshot(data):
    try:
        review = json.loads(SURVIVAL_REVIEW.read_text(encoding='utf-8'))
        if isinstance(review, dict) and review.get('generatedAt'):
            data['survivalReview'] = review
            summary = data.setdefault('summary', {})
            summary['survivalScore'] = review.get('survivalScore')
            summary['survivalReviewReadyCount'] = review.get('reviewReadyCount')
            summary['survivalHighRiskCount'] = review.get('highRiskCount')
    except Exception:
        pass


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    headers = access_headers()
    cache = {}
    refresh_benchmarks(data, headers, cache)
    changed_sessions = 0
    for session in data.get('sessions') or []:
        if reconcile_session(session, headers, cache):
            changed_sessions += 1
    futures_changed = refresh_stock_futures(data, headers, cache)
    nxt_changed = refresh_nxt_references(data)
    market_lead_changed = refresh_market_lead_overlays(data)
    sync_survival_review_snapshot(data)
    refresh_summary_and_history(data)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'mode': 'fast-market', 'generatedAt': data.get('generatedAt'), 'changedSessions': changed_sessions, 'quotes': len([v for v in cache.values() if v]), 'futuresChanged': futures_changed, 'nxtChanged': nxt_changed, 'marketLeadChanged': market_lead_changed}, ensure_ascii=False))


if __name__ == '__main__':
    main()
