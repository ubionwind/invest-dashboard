#!/usr/bin/env python3
import json, pathlib, datetime, statistics, urllib.request, csv, io, re, collections, socket
ROOT = pathlib.Path('/home/ubion/.openclaw/workspace')
socket.setdefaulttimeout(12)
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
LIVE_MOCK_HISTORY_INDEX = {
    'jinhye.general.mock': 0,
    'jaesang.short.mock': 1,
}

STATE_PATH_BY_SESSION = {
    'jaesang.short.mock': ROOT/'shared/mock_invest_ai_short/state.json',
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
NXT_QUOTE_CACHE = {}
STOCK_FUTURE_MASTER_CACHE = None
STOCK_FUTURE_QUOTE_CACHE = {}
STOCK_FUTURE_MASTER_URL = 'https://new.real.download.dws.co.kr/common/master/fo_stk_code_mts.mst.zip'

def nxt_quote_snapshot(code):
    """Return NXT pre/after-market quote as reference only; never use for KRX P/L."""
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
                            'source': 'naver-nxt-overmarket',
                        }
                    break
    except Exception:
        out = None
    NXT_QUOTE_CACHE[code] = out
    return out

def readonly_quote_snapshot(code):
    """Return a read-only current quote for display fields only."""
    code = str(code or '').zfill(6)
    if not code or code == '000000':
        return None
    if code in READONLY_QUOTE_CACHE:
        return READONLY_QUOTE_CACHE[code]
    def fallback():
        try:
            req = urllib.request.Request(f'https://m.stock.naver.com/api/stock/{code}/basic', headers={'User-Agent': 'Mozilla/5.0'})
            r = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace'))
            price = n(r.get('closePrice') or (r.get('overMarketPriceInfo') or {}).get('overPrice'))
            if price > 0:
                return {
                    'currentPrice': round(price),
                    'currentChangePct': round(n(r.get('fluctuationsRatio')), 2) if r.get('fluctuationsRatio') not in (None, '') else None,
                    'currentDelta': round(n(r.get('compareToPreviousClosePrice'))) if r.get('compareToPreviousClosePrice') not in (None, '') else None,
                }
        except Exception:
            pass
        return None
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
    if not out or out.get('currentChangePct') in (None, ''):
        out = fallback() or out
    READONLY_QUOTE_CACHE[code] = out
    return out

def stock_future_master_rows():
    """Return nearest stock-futures master rows from KIS public master file.

    Product kind 1/3 are single-stock futures rows in fo_stk_code_mts.mst;
    spreads/options are intentionally excluded. This is read-only reference data.
    """
    global STOCK_FUTURE_MASTER_CACHE
    if STOCK_FUTURE_MASTER_CACHE is not None:
        return STOCK_FUTURE_MASTER_CACHE
    cache_path = RUNTIME/'marketdata/stock_future_master.json'
    today = datetime.datetime.now(KST).date().isoformat()
    try:
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
        if cached.get('date') == today and isinstance(cached.get('rows'), list):
            STOCK_FUTURE_MASTER_CACHE = cached.get('rows')
            return STOCK_FUTURE_MASTER_CACHE
    except Exception:
        pass
    rows = []
    try:
        import zipfile
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
    STOCK_FUTURE_MASTER_CACHE = rows
    return rows

def nearest_stock_future_contract(code):
    code = str(code or '').zfill(6)
    rows = [r for r in stock_future_master_rows() if r.get('underlyingCode') == code and r.get('futureCode')]
    if not rows:
        return None
    def key(r):
        month = r.get('expiryMonth') or '999999'
        try: month_num = int(month)
        except Exception: month_num = 999999
        try: month_code = int(str(r.get('monthCode') or '999'))
        except Exception: month_code = 999
        return (month_num, month_code, str(r.get('futureCode') or ''))
    return sorted(rows, key=key)[0]

def stock_future_quote_snapshot(code, underlying_quote=None):
    """Return nearest single-stock futures quote as reference only.

    No order/trading endpoint is used. KRX cash price remains the official P/L basis.
    """
    code = str(code or '').zfill(6)
    if not code or code == '000000':
        return None
    if code in STOCK_FUTURE_QUOTE_CACHE:
        return STOCK_FUTURE_QUOTE_CACHE[code]
    contract = nearest_stock_future_contract(code)
    if not contract:
        STOCK_FUTURE_QUOTE_CACHE[code] = None
        return None
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
                headers = {
                    'content-type':'application/json; charset=utf-8', 'authorization':f'Bearer {access}',
                    'appkey':appkey, 'appsecret':appsecret, 'tr_id':'FHMIF10000000', 'custtype':'P'
                }
                params = urllib.parse.urlencode({'FID_COND_MRKT_DIV_CODE':'JF','FID_INPUT_ISCD':contract.get('futureCode')})
                try:
                    j = get_json(f'{KIS_BASE}/uapi/domestic-futureoption/v1/quotations/inquire-price?{params}', headers)
                    o = j.get('output1') if isinstance(j, dict) else {}
                except Exception:
                    headers['tr_id'] = 'FHMIF10010000'
                    j = get_json(f'{KIS_BASE}/uapi/domestic-futureoption/v1/quotations/inquire-asking-price?{params}', headers)
                    o = j.get('output1') if isinstance(j, dict) else {}
                price = n((o or {}).get('futs_prpr'))
                if price > 0:
                    underlying_price = n((underlying_quote or {}).get('currentPrice'))
                    if underlying_price <= 0:
                        rq = readonly_quote_snapshot(code) or {}
                        underlying_price = n(rq.get('currentPrice'))
                    spread = price - underlying_price if underlying_price > 0 else None
                    spread_pct = (spread / underlying_price * 100) if spread is not None and underlying_price else None
                    under_chg = (underlying_quote or {}).get('currentChangePct')
                    if under_chg is None:
                        under_chg = (readonly_quote_snapshot(code) or {}).get('currentChangePct')
                    fut_chg = round(n(o.get('futs_prdy_ctrt')), 2) if o.get('futs_prdy_ctrt') not in (None, '') else None
                    volume = round(n(o.get('acml_vol'))) if o.get('acml_vol') not in (None, '') else None
                    rel = (fut_chg - n(under_chg)) if fut_chg is not None and under_chg is not None else None
                    signal = '선물중립'
                    signalReason = '체결가 기준 상대강도'
                    if (volume in (None, 0)) and (fut_chg in (None, 0)):
                        signal = '선물장전대기'
                        signalReason = '체결/거래량 미확인; 장전 호가 신호 아님'
                        rel = None
                    elif rel is not None and rel >= 1.0: signal = '선물강세'
                    elif rel is not None and rel <= -1.0: signal = '선물약세'
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
                        'source': 'kis-domestic-futureoption-readonly',
                        'updatedAt': datetime.datetime.now(KST).isoformat(timespec='minutes'),
                    }
    except Exception:
        out = None
    STOCK_FUTURE_QUOTE_CACHE[code] = out
    return out

VIRTUAL_LEDGER_IDS = {'jaesang.surge.mock', 'jaesang.dailynew.mock', 'jaesang.quant.value.mock', 'jaesang.quant.momentum.mock', 'jaesang.quant.mixed.mock'}
POSITION_DISPLAY_LIMIT = 50
POSITION_LIMITS = {
    'jaesang.surge.mock': 5,
    'jaesang.dailynew.mock': 5,
    'jaesang.quant.value.mock': 10,
    'jaesang.quant.momentum.mock': 10,
    'jaesang.quant.mixed.mock': 10,
}
DEFAULT_POSITION_LIMIT = 5

def live_mock_history_rows():
    try:
        history_path = OUT.parent/'dashboard-history.json'
        history = json.loads(history_path.read_text(encoding='utf-8'))
        reset_id = LIVE_MOCK_RESET_EPOCH.isoformat(timespec='minutes') + ':clean-start-v3'
        return [row for row in history if isinstance(row, dict) and row.get('dataEpoch') == reset_id]
    except Exception:
        return []

def live_mock_baseline_capital(private_id, fallback=None):
    idx = LIVE_MOCK_HISTORY_INDEX.get(private_id)
    if idx is None:
        return fallback
    for row in live_mock_history_rows():
        vals = row.get('capital') if isinstance(row.get('capital'), list) else []
        if len(vals) > idx and vals[idx] not in (None, '', 0):
            return n(vals[idx])
    return fallback

def live_mock_portfolio_fallback(private_id):
    idx = LIVE_MOCK_HISTORY_INDEX.get(private_id)
    if idx is None:
        return None
    rows = live_mock_history_rows()
    baseline = live_mock_baseline_capital(private_id, None)
    latest_eval = None
    for row in reversed(rows):
        vals = row.get('evalAmounts') if isinstance(row.get('evalAmounts'), list) else []
        if len(vals) > idx and vals[idx] not in (None, '', 0):
            latest_eval = n(vals[idx])
            break
    if not baseline or not latest_eval:
        return None
    pnl = latest_eval - baseline
    return {'capital': round(baseline), 'cash': round(latest_eval), 'investmentAmount': 0, 'evalAmount': round(latest_eval), 'pnl': round(pnl), 'returnPct': round(pnl / baseline * 100, 2), 'positionCount': 0, 'positionsComplete': True, 'positions': [], 'source': 'history-fallback'}

def account_summary(private_id):
    if private_id in VIRTUAL_LEDGER_IDS:
        vt = load_fresh(f'virtual_trades/{private_id}.json', {})
        pf = vt.get('portfolio') if isinstance(vt, dict) else None
        if isinstance(pf, dict):
            positions=[]
            all_positions = vt.get('positions') or []
            open_positions = [p for p in all_positions if isinstance(p, dict) and n(p.get('qty')) > 0]
            for p in open_positions[:POSITION_DISPLAY_LIMIT]:
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
                'positionsComplete': len(open_positions) <= POSITION_DISPLAY_LIMIT,
                'cash': pf.get('cash') if pf.get('cash') is not None else vt.get('cash'),
                'investmentAmount': pf.get('positionEvalAmount'),
                'positions': positions,
            }
    refs=ACCOUNT_REFS.get(private_id)
    if not refs: return None
    env=load_env_file(KIS_ENV_PATH)
    try:
        appkey, appsecret, cano, acnt = [env.get(x) for x in refs]
        if not all([appkey, appsecret, cano, acnt]): return live_mock_portfolio_fallback(private_id)
        access=cached_access_token(private_id)
        if not access:
            tok=post_json(f'{KIS_BASE}/oauth2/tokenP', {'grant_type':'client_credentials','appkey':appkey,'appsecret':appsecret})
            access=tok.get('access_token')
            if access: save_access_token(private_id, tok)
        if not access: return live_mock_portfolio_fallback(private_id)
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
        unrealized_pnl=n(summary.get('evlu_pfls_smtl_amt'))
        raw_capital=eval_amt-unrealized_pnl if eval_amt or unrealized_pnl else n(summary.get('dnca_tot_amt'))
        capital=live_mock_baseline_capital(private_id, raw_capital)
        pnl=eval_amt-capital if capital and eval_amt else unrealized_pnl
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
        return {'capital': round(capital), 'cash': round(cash) if cash is not None else None, 'investmentAmount': round(investment_amount), 'evalAmount': round(eval_amt), 'pnl': round(pnl), 'returnPct': ret, 'positionCount': len(positions), 'positionsComplete': len(positions) <= POSITION_DISPLAY_LIMIT, 'positions': positions[:POSITION_DISPLAY_LIMIT]}
    except Exception:
        return live_mock_portfolio_fallback(private_id)

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
    def fallback():
        try:
            req=urllib.request.Request('https://m.stock.naver.com/api/stock/069500/basic', headers={'User-Agent':'Mozilla/5.0'}, method='GET')
            r=json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8','replace'))
            price=n(r.get('closePrice'))
            traded_at=None
            try:
                traded_at=datetime.datetime.fromisoformat(str(r.get('localTradedAt')).replace('Z','+00:00')).astimezone(KST)
            except Exception:
                pass
            if price > 0:
                now=traded_at or datetime.datetime.now(KST)
                return {'label':'KODEX 200', 'code':'069500', 'value':round(price, 2), 'returnPct':None, 'dailyReturnPct':round(n(r.get('fluctuationsRatio')), 2) if r.get('fluctuationsRatio') not in (None, '') else None, 'date':now.date().isoformat(), 'time':now.strftime('%H:%M:%S'), 'periodStart':None, 'periodEnd':None, 'source':'naver-stock-basic', 'marketStatus':r.get('marketStatus')}
        except Exception:
            pass
        return {'label':'KODEX 200', 'code':'069500', 'value': None, 'returnPct': None}
    try:
        appkey, appsecret = env.get('KIS_JAESANG_MOCK_APP_KEY'), env.get('KIS_JAESANG_MOCK_APP_SECRET')
        if not appkey or not appsecret: return fallback()
        access=cached_access_token('jaesang.short.mock')
        if not access:
            tok=post_json(f'{KIS_BASE}/oauth2/tokenP', {'grant_type':'client_credentials','appkey':appkey,'appsecret':appsecret})
            access=tok.get('access_token')
            if access: save_access_token('jaesang.short.mock', tok)
        if not access: return fallback()
        params=urllib.parse.urlencode({'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':'069500'})
        j=get_json(f'{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price?{params}', {
            'content-type':'application/json; charset=utf-8', 'authorization':f'Bearer {access}', 'appkey':appkey, 'appsecret':appsecret, 'tr_id':'FHKST01010100', 'custtype':'P'
        })
        o=j.get('output') or {}
        price=n(o.get('stck_prpr'))
        if not price: return fallback()
        return {'label':'KODEX 200', 'code':'069500', 'value': round(price, 2) if price else None, 'returnPct': None, 'dailyReturnPct': round(n(o.get('prdy_ctrt')), 2) if o.get('prdy_ctrt') not in (None, '') else None, 'date': datetime.datetime.now(KST).date().isoformat(), 'time': datetime.datetime.now(KST).strftime('%H:%M:%S'), 'periodStart': None, 'periodEnd': None}
    except Exception:
        return fallback()


ETF_HOLDING_SOURCES = [
    {
        'key': 'kodex200',
        'label': 'KODEX 200',
        'code': '069500',
        'url': 'https://kr.investing.com/etfs/samsung-kodex-kospi-200-securities-holdings',
        'fnguide_url': 'https://wcomp.fnguide.com/Etp/EtfSnapshot?c_id=AA&menu_type=01&cmp_cd=069500',
    },
    {
        'key': 'tiger200',
        'label': 'TIGER 200',
        'code': '102110',
        'url': 'https://kr.investing.com/etfs/miraeasset-tiger-kospi-200-holdings',
        'fnguide_url': 'https://wcomp.fnguide.com/Etp/EtfSnapshot?c_id=AA&menu_type=01&cmp_cd=102110',
    },
]

ETF_NAME_CODE_HINTS = {
    '삼성전자': '005930', 'SK하이닉스': '000660', 'SK스퀘어': '402340', '현대차': '005380',
    '두산에너빌리티': '034020', 'KB금융': '105560', '삼성전기': '009150', '한화에어로스페이스': '012450',
    '삼성SDI': '006400', '신한지주': '055550', '삼성물산': '028260', 'NAVER': '035420', '기아': '000270',
}


def etf_holdings_snapshot(limit=15):
    """Read-only ETF top holdings for market-bias diagnostics.

    This is display/reference data only. It must never be used as an order
    target list by itself. The public dashboard uses it to explain whether the
    KOSPI200 benchmark move is concentrated in semiconductors/large caps.
    """
    out = []
    for meta in ETF_HOLDING_SOURCES:
        holdings = []
        by_name = {}
        try:
            from bs4 import BeautifulSoup
            req = urllib.request.Request(meta['url'], headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'})
            html = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'replace')
            soup = BeautifulSoup(html, 'html.parser')
            for tr in soup.find_all('tr'):
                cells = [' '.join(td.get_text(' ', strip=True).split()) for td in tr.find_all(['td', 'th'])]
                cells = [c for c in cells if c]
                # Investing holdings table shape: name, code, weight, price, change, qty
                if len(cells) < 6 or not str(cells[1]).isdigit() or '%' not in str(cells[2]):
                    continue
                weight = n(str(cells[2]).replace('%', ''))
                row = {
                    'name': cells[0],
                    'code': str(cells[1]).zfill(6),
                    'weightPct': round(weight, 2),
                    'price': round(n(cells[3])) if n(cells[3]) else None,
                    'changePct': round(n(str(cells[4]).replace('%', '')), 2) if '%' in str(cells[4]) else None,
                    'quantity': cells[5],
                    'source': 'investing.com',
                }
                holdings.append(row)
                by_name[row['name']] = row
                if len(holdings) >= limit:
                    break
        except Exception:
            holdings = []
        try:
            req = urllib.request.Request(meta['fnguide_url'], headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'})
            html = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'replace')
            m = re.search(r'etfRelTop10\s*:\s*(\[.*?\])', html, re.S)
            rel_top10 = json.loads(m.group(1)) if m else []
            if rel_top10:
                merged = []
                for item in rel_top10[:limit]:
                    name = item.get('ITEM_NM') or ''
                    ref = by_name.get(name) or {}
                    merged.append({
                        'name': name,
                        'code': ref.get('code') or ETF_NAME_CODE_HINTS.get(name),
                        'weightPct': round(n(item.get('FUND_RT')), 2),
                        'price': ref.get('price'),
                        'changePct': ref.get('changePct'),
                        'quantity': item.get('SHARES') or ref.get('quantity'),
                        'asOf': item.get('TRD_DT'),
                        'source': 'fnguide-top10+investing-quote',
                    })
                holdings = merged
        except Exception:
            pass
        semiconductor_weight = sum(n(h.get('weightPct')) for h in holdings if h.get('code') in ('005930', '000660'))
        out.append({
            'key': meta['key'],
            'label': meta['label'],
            'code': meta['code'],
            'underlying': 'KOSPI 200',
            'source': 'investing.com-holdings-page',
            'fetchedAt': datetime.datetime.now(KST).isoformat(timespec='minutes'),
            'holdings': holdings,
            'topCount': len(holdings),
            'semiconductorTopWeightPct': round(semiconductor_weight, 2) if holdings else None,
            'top10WeightPct': round(sum(n(h.get('weightPct')) for h in holdings[:10]), 2) if holdings else None,
            'note': '상위 편입종목 참고용; 실제 PDF/운용사 공시와 시점 차이가 있을 수 있음',
        })
    return out


def etf_theme_follow_snapshot():
    path = ROOT / 'shared/invest_api_common/runtime/etf_theme_follow/latest.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        themes = data.get('themes') or []
        beneficiaries = data.get('beneficiaries') or []
        return {
            'schema': data.get('schema') or 'etf-theme-follow-radar.v1',
            'sessionName': data.get('sessionName') or '재상-ETF추종-테마',
            'generatedAt': data.get('generatedAt'),
            'policy': data.get('policy') or 'READ_ONLY_ANALYTICS_NO_ORDER_EXECUTION',
            'themes': themes[:7],
            'beneficiaries': beneficiaries[:15],
            'themeCount': len(themes),
            'beneficiaryCount': len(beneficiaries),
        }
    except Exception:
        return {
            'schema': 'etf-theme-follow-radar.v1',
            'sessionName': '재상-ETF추종-테마',
            'generatedAt': None,
            'policy': 'READ_ONLY_ANALYTICS_NO_ORDER_EXECUTION',
            'themes': [],
            'beneficiaries': [],
            'themeCount': 0,
            'beneficiaryCount': 0,
        }

def market_regime_snapshot(benchmark, kodex):
    """Classify broad market regime before stock decisions.

    Read-only public market data only. The output is intentionally simple and
    conservative: it is used to reduce confidence/position size when the market
    is hostile, not to force bullish calls.
    """
    kospi = benchmark.get('dailyReturnPct') if isinstance(benchmark, dict) else None
    kodex_ret = kodex.get('dailyReturnPct') if isinstance(kodex, dict) else None
    vals = [x for x in (kospi, kodex_ret) if isinstance(x, (int, float))]
    avg = round(sum(vals) / len(vals), 2) if vals else None
    risk_score = 50
    reasons = []
    if avg is None:
        state, label, stance = 'UNKNOWN', '시장 판단 대기', '시장 데이터가 부족하므로 종목 확신도를 보수적으로 봅니다.'
        risk_score -= 8
        reasons.append('KOSPI/KODEX 당일 등락률 데이터 부족')
    elif avg <= -1.2:
        state, label, stance = 'RISK_OFF', '위험 회피장', '시장이 약해 종목이 좋아 보여도 비중을 낮추고 관망을 우선합니다.'
        risk_score -= 22
        reasons.append(f'시장 평균 당일 등락률 {avg:+.2f}%')
    elif avg <= -0.4:
        state, label, stance = 'CAUTION', '주의장', '시장 압력이 있어 신규 진입은 확인 후 작게 접근합니다.'
        risk_score -= 10
        reasons.append(f'시장 평균 당일 등락률 {avg:+.2f}%')
    elif avg >= 0.8:
        state, label, stance = 'RISK_ON', '위험 선호장', '시장 분위기는 우호적이나 종목별 무효조건은 유지합니다.'
        risk_score += 8
        reasons.append(f'시장 평균 당일 등락률 {avg:+.2f}%')
    else:
        state, label, stance = 'NEUTRAL', '중립장', '시장만으로 강한 방향을 말하기 어려워 종목 조건을 확인합니다.'
        reasons.append(f'시장 평균 당일 등락률 {avg:+.2f}%')
    if isinstance(kospi, (int, float)) and isinstance(kodex_ret, (int, float)) and kospi < 0 and kodex_ret < 0:
        reasons.append('KOSPI와 KODEX 200이 동시에 약세')
        risk_score -= 5
    market_status = benchmark.get('marketStatus') or kodex.get('marketStatus')
    if market_status:
        reasons.append(f'시장 상태 {market_status}')
    risk_score = max(0, min(100, round(risk_score)))
    policy_map = {
        'RISK_OFF': {
            'maxPositionPct': '0~2%',
            'entryRule': '신규 진입은 원칙적으로 보류. 보유 종목은 지지선/손실제한 우선 확인.',
            'confidenceCap': 55,
            'plain': '시장이 약하면 종목 분석이 좋아 보여도 먼저 살아남는 쪽을 택합니다.',
        },
        'CAUTION': {
            'maxPositionPct': '0~5%',
            'entryRule': '신규 진입은 소액·분할만 허용하고, 전고점/거래량 확인 전 추격 금지.',
            'confidenceCap': 68,
            'plain': '시장 압력이 남아 있어 확신도를 한 단계 낮춥니다.',
        },
        'UNKNOWN': {
            'maxPositionPct': '0~2%',
            'entryRule': '시장 데이터 확인 전 신규 진입 보류.',
            'confidenceCap': 55,
            'plain': '시장 상태를 모르면 쉬는 것이 기본값입니다.',
        },
        'NEUTRAL': {
            'maxPositionPct': '0~5%',
            'entryRule': '종목별 조건 충족 시에만 소액·분할 접근.',
            'confidenceCap': 78,
            'plain': '시장 방향성이 강하지 않아 종목의 조건 충족 여부를 봅니다.',
        },
        'RISK_ON': {
            'maxPositionPct': '3~20%',
            'entryRule': '우호 시장이지만 무효조건과 신호충돌이 없을 때만 비중 확대.',
            'confidenceCap': 100,
            'plain': '시장은 우호적이나 추격보다 조건 확인이 우선입니다.',
        },
    }
    policy = policy_map.get(state, policy_map['UNKNOWN'])
    return {
        'state': state,
        'label': label,
        'riskScore': risk_score,
        'stance': stance,
        'strategyPolicy': policy,
        'dailyReturnPct': avg,
        'kospiDailyReturnPct': kospi,
        'kodexDailyReturnPct': kodex_ret,
        'reasons': reasons[:5],
        'positionBias': 'reduce' if state in ('RISK_OFF', 'CAUTION', 'UNKNOWN') else ('allow' if state == 'RISK_ON' else 'neutral'),
        'source': 'KOSPI/KODEX read-only dashboard benchmark',
    }

def apply_market_regime_to_survival(survival, regime):
    if not isinstance(survival, dict) or not isinstance(regime, dict):
        return survival
    out = json.loads(json.dumps(survival, ensure_ascii=False))
    base = out.get('confidenceScore')
    try:
        base_num = float(base)
    except Exception:
        base_num = None
    delta = 0
    state = regime.get('state')
    if state == 'RISK_OFF':
        delta = -14
    elif state in ('CAUTION', 'UNKNOWN'):
        delta = -7
    elif state == 'RISK_ON':
        delta = 3
    if base_num is not None:
        new_score = max(0, min(100, round(base_num + delta)))
        cap = (regime.get('strategyPolicy') or {}).get('confidenceCap') if isinstance(regime.get('strategyPolicy'), dict) else None
        if isinstance(cap, (int, float)):
            new_score = min(new_score, int(cap))
        out['preRegimeConfidenceScore'] = round(base_num)
        out['confidenceScore'] = new_score
        if new_score >= 75:
            out['confidenceLevel'] = 'High'
        elif new_score >= 60:
            out['confidenceLevel'] = 'Medium'
        elif new_score >= 45:
            out['confidenceLevel'] = 'Low'
        else:
            out['confidenceLevel'] = 'Uncertain'
    out['marketRegime'] = regime
    out['regimeStrategyPolicy'] = regime.get('strategyPolicy') if isinstance(regime.get('strategyPolicy'), dict) else None
    notes = out.get('signalConflicts') if isinstance(out.get('signalConflicts'), list) else []
    if state == 'RISK_OFF':
        notes.append('시장 Regime이 위험 회피장이어서 종목 신호가 좋아도 비중을 낮춥니다.')
        out['actionState'] = '관망 우선' if out.get('actionState') != '매수 보류' else out.get('actionState')
        out['positionGuide'] = {'label': '시장 위험 우선', 'suggestedRangePct': '0~2%', 'plain': '시장 자체가 약해 신규 진입은 쉬거나 아주 작게만 봅니다.'}
        out['waitIsValid'] = True
    elif state in ('CAUTION', 'UNKNOWN') and out.get('actionState') in ('적극 검토', '소액/분할 접근'):
        notes.append('시장 Regime이 확신을 낮추는 구간이라 분할·소액 원칙을 우선합니다.')
        out['actionState'] = '소액/분할 접근' if out.get('actionState') == '적극 검토' else out.get('actionState')
        if out.get('positionGuide', {}).get('suggestedRangePct') == '10~20%':
            out['positionGuide'] = {'label': '시장 주의 반영', 'suggestedRangePct': '3~5%', 'plain': '종목 조건은 보이지만 시장 압력이 있어 비중을 줄입니다.'}
    out['signalConflicts'] = notes[:6]
    return out

def apply_sector_weighting_to_survival(f, survival):
    if not isinstance(f, dict) or not isinstance(survival, dict):
        return survival
    out = json.loads(json.dumps(survival, ensure_ascii=False))
    sector = out.get('sectorProfile') if isinstance(out.get('sectorProfile'), dict) else (f.get('sectorProfile') if isinstance(f.get('sectorProfile'), dict) else {})
    key = sector.get('key') or 'general'
    kis = f.get('kisEnrichment') if isinstance(f.get('kisEnrichment'), dict) else {}
    summary = kis.get('summary') if isinstance(kis.get('summary'), dict) else {}
    peer = f.get('peerGrowthMargin') if isinstance(f.get('peerGrowthMargin'), dict) else {}
    target = peer.get('target') if isinstance(peer.get('target'), dict) else {}
    avg = peer.get('peerAverage') if isinstance(peer.get('peerAverage'), dict) else {}
    code = str(f.get('code') or '').zfill(6)
    name = str(f.get('name') or '')
    rules = []
    delta = 0
    frgn5 = summary.get('foreignNetBuyAmount5d')
    orgn5 = summary.get('institutionNetBuyAmount5d')
    short_ratio = summary.get('shortSaleVolumeRatioLatest')
    loan5 = summary.get('loanBalanceChange5d')
    per, pbr, roe = f.get('per'), f.get('pbr'), f.get('roe')
    if key == 'semiconductor':
        rules.append('반도체/전자는 PER 단순 저평가보다 메모리 업황·HBM·외국인 수급·업종 상대강도를 우선합니다.')
        if code == '005930' or '삼성전자' in name:
            rules.append('삼성전자는 SOX/엔비디아 흐름, HBM 경쟁력, 환율, 외국인 수급을 PER보다 먼저 확인합니다.')
        if isinstance(frgn5, (int, float)) and isinstance(orgn5, (int, float)):
            if frgn5 > 0 and orgn5 > 0:
                delta += 4; rules.append('외국인·기관 동반 순매수로 업황 민감주 신뢰도 보강')
            elif frgn5 < 0 and orgn5 < 0:
                delta -= 7; rules.append('외국인·기관 동반 순매도로 반도체 추세 신뢰도 하향')
    elif key == 'bio':
        if code == '207940' or '삼성바이오로직스' in name:
            out['sectorProfile'] = {
                **sector,
                'key': 'cdmo',
                'label': 'CDMO 대형주',
                'importantFactors': ['수주잔고', '공장 가동률', 'CAPA', '글로벌 빅파마 계약', '환율', '영업이익률', '품질/규제 리스크'],
                'downweightedFactors': ['일반 바이오 임상 모멘텀', 'PER 단순 해석'],
                'plain': '삼성바이오로직스는 일반 바이오보다 CDMO 대형주로 봅니다. 수주·CAPA·가동률·환율·마진·품질 리스크를 우선합니다.',
            }
            sector = out['sectorProfile']
            rules.append('삼성바이오로직스는 일반 바이오가 아니라 CDMO 대형주로 분리해 수주·CAPA·가동률·환율·마진을 우선합니다.')
            if not kis.get('parts', {}).get('news', {}).get('ok'):
                delta -= 3; rules.append('CDMO 계약/증설/품질 이슈 확인 부족으로 확신도 일부 하향')
        else:
            rules.append('바이오/제약은 PER보다 임상·허가·기술수출·공시 이벤트 확인을 우선합니다.')
            if not kis.get('parts', {}).get('news', {}).get('ok'):
                delta -= 5; rules.append('뉴스/공시 이벤트 확인 부족으로 확신도 하향')
        if per is not None:
            rules.append('PER은 참고만 하고 단독 매수 근거로 쓰지 않음')
    elif key == 'financial':
        rules.append('금융은 PBR·배당·금리·건전성 중심으로 해석합니다.')
        if isinstance(pbr, (int, float)) and isinstance(roe, (int, float)):
            if pbr <= 1.2 and roe >= 8:
                delta += 4; rules.append('PBR/ROE 조합은 금융주 기준 일부 우호')
            elif pbr >= 2.0 and roe < 8:
                delta -= 5; rules.append('금융주 기준 PBR 대비 ROE 매력이 약함')
    elif key == 'battery':
        rules.append('2차전지는 광물 가격·정책·수주·CAPA와 마진 방어를 우선합니다.')
        tm, am = target.get('operatingMarginPct'), avg.get('operatingMarginPct')
        if isinstance(tm, (int, float)) and isinstance(am, (int, float)) and tm < am:
            delta -= 6; rules.append('동종 대비 마진 열위로 2차전지 확신도 하향')
    if isinstance(short_ratio, (int, float)) and short_ratio >= 8:
        delta -= 3; rules.append('공매도 부담은 업종과 무관하게 비중 확대 제한')
    if isinstance(loan5, (int, float)) and loan5 > 0:
        delta -= 2; rules.append('대차잔고 증가는 숏/헤지성 물량 가능성으로 반영')
    try:
        base = float(out.get('confidenceScore'))
        out['preSectorConfidenceScore'] = round(base)
        new_score = max(0, min(100, round(base + delta)))
        cap = (out.get('regimeStrategyPolicy') or {}).get('confidenceCap') if isinstance(out.get('regimeStrategyPolicy'), dict) else None
        if isinstance(cap, (int, float)):
            new_score = min(new_score, int(cap))
        out['confidenceScore'] = new_score
        sc = out['confidenceScore']
        out['confidenceLevel'] = 'High' if sc >= 75 else ('Medium' if sc >= 60 else ('Low' if sc >= 45 else 'Uncertain'))
    except Exception:
        pass
    out['sectorRulesApplied'] = rules[:6]
    if delta < 0 and out.get('actionState') == '적극 검토':
        out['actionState'] = '소액/분할 접근'
    if delta <= -6 and out.get('actionState') == '소액/분할 접근':
        out['actionState'] = '관망 우선'
        out['waitIsValid'] = True
    out['failureRiskPatterns'] = classify_failure_risk_patterns(f, out)
    return out

def classify_failure_risk_patterns(f, survival):
    patterns = []
    if not isinstance(f, dict) or not isinstance(survival, dict):
        return patterns
    kis = f.get('kisEnrichment') if isinstance(f.get('kisEnrichment'), dict) else {}
    summary = kis.get('summary') if isinstance(kis.get('summary'), dict) else {}
    sector = survival.get('sectorProfile') if isinstance(survival.get('sectorProfile'), dict) else {}
    regime = survival.get('marketRegime') if isinstance(survival.get('marketRegime'), dict) else {}
    conflicts = survival.get('signalConflicts') if isinstance(survival.get('signalConflicts'), list) else []
    short_ratio = summary.get('shortSaleVolumeRatioLatest')
    loan5 = summary.get('loanBalanceChange5d')
    frgn5 = summary.get('foreignNetBuyAmount5d')
    orgn5 = summary.get('institutionNetBuyAmount5d')
    if regime.get('state') in ('RISK_OFF', 'CAUTION') and survival.get('actionState') not in ('관망 우선', '매수 보류'):
        patterns.append({'code': 'REGIME_OVERRIDE_RISK', 'label': '시장위험 과소반영 후보', 'explain': '시장 상태가 약한데도 진입 판단이 남아 있어 실패 시 Regime 무시 가능성을 봅니다.'})
    if isinstance(short_ratio, (int, float)) and short_ratio >= 8:
        patterns.append({'code': 'SHORT_PRESSURE_RISK', 'label': '공매도 압력 오판위험 후보', 'explain': '공매도 비중이 높아 반등 실패 시 숏 압력 오판으로 분류합니다.'})
    if isinstance(loan5, (int, float)) and loan5 > 0:
        patterns.append({'code': 'LOAN_BALANCE_RISK', 'label': '대차잔고 증가 무시 후보', 'explain': '대차잔고 증가가 매도/헤지 압력으로 이어질 수 있습니다.'})
    if isinstance(frgn5, (int, float)) and isinstance(orgn5, (int, float)) and frgn5 < 0 and orgn5 < 0:
        patterns.append({'code': 'FLOW_DISTRIBUTION_RISK', 'label': '수급 이탈 오판위험 후보', 'explain': '외국인·기관 동반 순매도 상태에서 반등 기대가 실패할 수 있습니다.'})
    if sector.get('key') == 'cdmo' and not kis.get('parts', {}).get('news', {}).get('ok'):
        patterns.append({'code': 'CDMO_CONTRACT_GAP_RISK', 'label': 'CDMO 계약/가동률 누락 후보', 'explain': 'CDMO는 수주·CAPA·가동률·품질/규제 이슈 누락 시 판단이 틀릴 수 있습니다.'})
    elif sector.get('key') == 'bio' and not kis.get('parts', {}).get('news', {}).get('ok'):
        patterns.append({'code': 'BIO_EVENT_GAP_RISK', 'label': '바이오 이벤트 누락 후보', 'explain': '바이오는 임상·허가·공시 이벤트 누락 시 설명은 그럴듯해도 실전 판단이 틀릴 수 있습니다.'})
    if len(conflicts) >= 2:
        patterns.append({'code': 'SIGNAL_CONFLICT_RISK', 'label': '신호충돌 무시 후보', 'explain': '좋은 신호와 나쁜 신호가 섞여 있어 실패 시 신호충돌 과소평가로 기록합니다.'})
    if not patterns and survival.get('confidenceLevel') in ('Low', 'Uncertain'):
        patterns.append({'code': 'LOW_CONFIDENCE_NO_TRADE', 'label': '낮은 확신 관망', 'explain': '오판위험보다 관망 자체가 정상 판단입니다.'})
    return patterns[:5]

def walk_stock_items(x, out=None):
    out = out if out is not None else []
    if isinstance(x, list):
        for v in x: walk_stock_items(v, out)
    elif isinstance(x, dict):
        if x.get('code') and isinstance(x.get('fundamentals'), dict):
            out.append(x)
        for v in x.values(): walk_stock_items(v, out)
    return out

def apply_market_regime_to_sessions(sessions, regime):
    for item in walk_stock_items(sessions):
        f = item.get('fundamentals') or {}
        expert = f.get('expertAnalysis') if isinstance(f.get('expertAnalysis'), dict) else None
        if expert and isinstance(expert.get('survival'), dict):
            expert['survival'] = apply_sector_weighting_to_survival(f, apply_market_regime_to_survival(expert.get('survival'), regime))

def update_survival_ledger(sessions, regime, generated_at):
    path = OUT.parent/'survival-ledger.json'
    try:
        ledger = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(ledger, dict): ledger = {}
    except Exception:
        ledger = {}
    prev_hist = ledger.get('history') if isinstance(ledger.get('history'), list) else []
    def parse_ts(value):
        if not value:
            return None
        try:
            return datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except Exception:
            return None
    first_seen = {}
    for r in prev_hist:
        if not isinstance(r, dict):
            continue
        key = (r.get('publicId') or '', str(r.get('code') or '').zfill(6))
        candidate_ts = parse_ts(r.get('firstSeenAt') or r.get('ts'))
        current_ts = parse_ts((first_seen.get(key) or {}).get('firstSeenAt') or (first_seen.get(key) or {}).get('ts'))
        if key not in first_seen or (candidate_ts and (not current_ts or candidate_ts < current_ts)):
            first_seen[key] = r
    rows = []
    seen = set()
    for s in sessions:
        public_id = s.get('id') or s.get('publicId') or ''
        for item in walk_stock_items(s):
            code = str(item.get('code') or '').zfill(6)
            if not code or (public_id, code) in seen:
                continue
            seen.add((public_id, code))
            f = item.get('fundamentals') or {}
            surv = ((f.get('expertAnalysis') or {}).get('survival') or {}) if isinstance(f.get('expertAnalysis'), dict) else {}
            if not surv:
                continue
            first = first_seen.get((public_id, code)) or {}
            tech = f.get('technicalStructure') if isinstance(f.get('technicalStructure'), dict) else {}
            intraday = f.get('intradayCandle') if isinstance(f.get('intradayCandle'), dict) else {}
            current_price = item.get('currentPrice') or tech.get('currentPrice') or intraday.get('close')
            try:
                current_price = float(current_price) if current_price not in (None, '') else None
            except Exception:
                current_price = None
            baseline_price = first.get('baselinePrice') or first.get('lastPrice') or current_price
            try:
                baseline_price = float(baseline_price) if baseline_price not in (None, '') else None
            except Exception:
                baseline_price = None
            return_since_first = round((current_price - baseline_price) / baseline_price * 100, 2) if current_price and baseline_price else None
            horizons = {}
            try:
                first_ts = parse_ts(first.get('firstSeenAt') or first.get('ts'))
                now_ts = parse_ts(generated_at)
            except Exception:
                first_ts = None; now_ts = None
            for days in (1, 5, 20):
                status = 'pending'
                if first_ts and now_ts and (now_ts - first_ts).total_seconds() >= days * 86400:
                    status = 'ready-for-review' if return_since_first is not None else 'ready-missing-return'
                horizons[f'{days}d'] = {'status': status, 'returnSinceFirstPct': return_since_first if status.startswith('ready') else None}
            risk_patterns = surv.get('failureRiskPatterns') if isinstance(surv.get('failureRiskPatterns'), list) else []
            realized = []
            ret = return_since_first if return_since_first is not None else item.get('returnPct')
            if isinstance(ret, (int, float)):
                if ret <= -5:
                    realized.append({'code': 'DRAWDOWN_GT_5', 'label': '5% 이상 손실', 'explain': '진입/보유 판단 후 손실 폭이 커져 리스크 관리 실패 여부 검토 필요'})
                elif ret <= -2:
                    realized.append({'code': 'DRAWDOWN_GT_2', 'label': '2% 이상 손실', 'explain': '초기 손실이 발생해 진입 타이밍/시장상태를 재검토'})
                elif ret >= 3 and surv.get('actionState') in ('관망 우선', '매수 보류'):
                    realized.append({'code': 'MISSED_UPSIDE_WHILE_WAITING', 'label': '관망 중 상승 놓침', 'explain': '관망 판단 후 상승했으나 생존 우선 전략상 허용 가능한 기회비용인지 검토'})
            failure_patterns = realized or risk_patterns
            rows.append({
                'ts': generated_at,
                'firstSeenAt': first.get('firstSeenAt') or first.get('ts') or generated_at,
                'session': s.get('name'),
                'publicId': public_id,
                'code': code,
                'name': item.get('name') or f.get('name'),
                'baselinePrice': baseline_price,
                'lastPrice': current_price,
                'returnSinceFirstPct': return_since_first,
                'score': (f.get('expertAnalysis') or {}).get('score') if isinstance(f.get('expertAnalysis'), dict) else None,
                'actionState': surv.get('actionState'),
                'confidenceScore': surv.get('confidenceScore'),
                'confidenceLevel': surv.get('confidenceLevel'),
                'positionRangePct': (surv.get('positionGuide') or {}).get('suggestedRangePct') if isinstance(surv.get('positionGuide'), dict) else None,
                'marketRegime': regime.get('state'),
                'sector': (surv.get('sectorProfile') or {}).get('label') if isinstance(surv.get('sectorProfile'), dict) else None,
                'returnPct': item.get('returnPct'),
                'riskPatterns': risk_patterns,
                'failurePatterns': failure_patterns,
                'horizonReview': horizons,
                'failureReviewStatus': 'pending-horizon-review' if all(v.get('status') == 'pending' for v in horizons.values()) else 'review-ready',
            })
    hist = prev_hist
    hist.extend(rows)
    ledger = {
        'updatedAt': generated_at,
        'purpose': 'Survival-first decision ledger. Tracks decision state separately from explanation quality and future return review.',
        'marketRegime': regime,
        'latest': rows,
        'history': hist[-800:],
    }
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')
    return ledger

def survival_review_from_ledger(ledger, generated_at):
    latest = ledger.get('latest') if isinstance(ledger, dict) and isinstance(ledger.get('latest'), list) else []
    action_counts = collections.Counter(str(r.get('actionState') or 'unknown') for r in latest if isinstance(r, dict))
    confidence_counts = collections.Counter(str(r.get('confidenceLevel') or 'unknown') for r in latest if isinstance(r, dict))
    pattern_counts = collections.Counter()
    horizon_counts = {key: collections.Counter() for key in ('1d', '5d', '20d')}
    horizon_ready_returns = {key: [] for key in ('1d', '5d', '20d')}
    review_ready = []
    high_risk = []
    for r in latest:
        if not isinstance(r, dict):
            continue
        for p in r.get('failurePatterns') or []:
            if isinstance(p, dict) and p.get('code'):
                pattern_counts[p.get('code')] += 1
        horizons = r.get('horizonReview') if isinstance(r.get('horizonReview'), dict) else {}
        for key in ('1d', '5d', '20d'):
            h = horizons.get(key) if isinstance(horizons.get(key), dict) else {}
            status = str(h.get('status') or 'missing')
            horizon_counts[key][status] += 1
            value = h.get('returnSinceFirstPct')
            if status.startswith('ready') and isinstance(value, (int, float)):
                horizon_ready_returns[key].append(float(value))
        if any(str(v.get('status') or '').startswith('ready') for v in horizons.values() if isinstance(v, dict)):
            review_ready.append(r)
        risky_pattern = any((p or {}).get('code') not in ('LOW_CONFIDENCE_NO_TRADE',) for p in (r.get('failurePatterns') or []) if isinstance(p, dict))
        if r.get('confidenceLevel') in ('Low', 'Uncertain') and risky_pattern:
            high_risk.append(r)
    baseline_ready = [r for r in latest if isinstance(r, dict) and r.get('baselinePrice') not in (None, '') and r.get('lastPrice') not in (None, '')]
    negative_since_first = [r for r in baseline_ready if isinstance(r.get('returnSinceFirstPct'), (int, float)) and r.get('returnSinceFirstPct') < 0]
    no_trade = action_counts.get('관망 우선', 0) + action_counts.get('매수 보류', 0)
    total = len(latest)
    no_trade_ratio = round(no_trade / total * 100, 1) if total else None
    top_patterns = [{'code': code, 'count': count} for code, count in pattern_counts.most_common(8)]
    horizon_review = {}
    for key in ('1d', '5d', '20d'):
        counts = horizon_counts[key]
        returns = horizon_ready_returns[key]
        horizon_review[key] = {
            'total': sum(counts.values()),
            'statusCounts': dict(counts),
            'readyCount': sum(count for status, count in counts.items() if str(status).startswith('ready')),
            'pendingCount': counts.get('pending', 0),
            'avgReadyReturnSinceFirstPct': round(sum(returns) / len(returns), 2) if returns else None,
            'negativeReadyCount': sum(1 for value in returns if value < 0),
        }
    score = 100
    if total:
        score -= min(35, len(high_risk) / total * 45)
        score -= min(20, len(review_ready) / total * 20)
        if no_trade_ratio is not None and no_trade_ratio < 30:
            score -= 10
    score = round(max(0, min(100, score)))
    review = {
        'generatedAt': generated_at,
        'survivalScore': score,
        'totalRows': total,
        'noTradeRows': no_trade,
        'noTradeRatioPct': no_trade_ratio,
        'actionCounts': dict(action_counts),
        'confidenceCounts': dict(confidence_counts),
        'topFailurePatterns': top_patterns,
        'horizonReview': horizon_review,
        'reviewReadyCount': len(review_ready),
        'baselineTrackedCount': len(baseline_ready),
        'negativeSinceFirstCount': len(negative_since_first),
        'highRiskCount': len(high_risk),
        'highRiskSamples': [{
            'session': x.get('session'), 'code': x.get('code'), 'name': x.get('name'),
            'actionState': x.get('actionState'), 'confidenceScore': x.get('confidenceScore'),
            'patterns': [p.get('code') for p in (x.get('failurePatterns') or []) if isinstance(p, dict)]
        } for x in high_risk[:8]],
        'plain': '생존점수는 수익 예측 점수가 아니라, 낮은 확신·위험패턴·검토대기 상태를 기준으로 계좌 생존 관점의 보수성을 점검합니다.',
    }
    (OUT.parent/'survival-review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    return review

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

def backfill_market_return_arrays(history, sessions):
    for idx, session in enumerate(sessions or []):
        comp = session.get('comparison') if isinstance(session, dict) else None
        start_ts = comp.get('periodStart') if isinstance(comp, dict) else None
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
        row = {
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
        }
        row['decisionContract'] = decision_contract_for_item(row, sid, 'holding' if held else 'candidate')
        out.append(row)
    return out

def safe_alerts(obj, limit=50):
    arr=[]
    if isinstance(obj, dict):
        arr = obj.get('candidates') or obj.get('sellCandidates') or obj.get('orders') or obj.get('items') or obj.get('results') or []
    elif isinstance(obj, list):
        arr=obj
    out=[]
    for c in arr[:limit]:
        if not isinstance(c, dict): continue
        execution_status = c.get('executionStatus') or ('VIRTUAL_AUTO_STOP_FILLED' if c.get('status') == '자동손절체결' else None)
        if execution_status == 'VIRTUAL_AUTO_STOP_FILLED' or c.get('status') == '자동손절체결':
            account_type = '가상계좌'
            execution_source = 'VIRTUAL_LEDGER'
            status = '(가상계좌) 자동손절 체결'
            reason = f"자체 가상투자 ledger · KIS API 호출 없음 · {c.get('reason') or c.get('summary') or c.get('entry_reason') or c.get('exit_reason') or c.get('note') or ''}".strip(' ·')
            executed_qty = c.get('executedQty') if c.get('executedQty') not in (None, '') else c.get('qty')
        else:
            account_type = 'KIS 모의계좌' if c.get('sessionId') in ('jaesang.short.mock', 'jinhye.general.mock') else '가상계좌'
            execution_source = 'NONE'
            raw_status = public_text(c.get('status') or c.get('action') or c.get('decision') or c.get('orderDecision') or c.get('review_status') or '')
            if raw_status in ('보유유지', '보유 유지', ''):
                continue
            if raw_status and raw_status != '보유유지':
                status = f"({account_type}) 매도 검토 · 미체결"
            else:
                status = f"({account_type}) 보유 유지"
            reason = public_text(c.get('reason') or c.get('summary') or c.get('entry_reason') or c.get('exit_reason') or c.get('note') or '')
            executed_qty = c.get('executedQty') if c.get('executedQty') not in (None, '') else 0
        sell_price = c.get('sellPrice') if c.get('sellPrice') not in (None, '') else c.get('exitPrice') if c.get('exitPrice') not in (None, '') else c.get('price')
        realized_pnl = c.get('realizedPnl') if c.get('realizedPnl') not in (None, '') else c.get('pnl') if c.get('pnl') not in (None, '') else None
        sell_amount = c.get('sellAmount') if c.get('sellAmount') not in (None, '') else c.get('amount') if c.get('amount') not in (None, '') else None
        entry_amount = None
        if sell_amount not in (None, '') and realized_pnl not in (None, ''):
            entry_amount = n(sell_amount) - n(realized_pnl)
        realized_return_pct = c.get('realizedReturnPct') if c.get('realizedReturnPct') not in (None, '') else c.get('returnPct') if c.get('returnPct') not in (None, '') else c.get('pnlRate')
        if realized_return_pct in (None, '') and entry_amount and entry_amount != 0 and realized_pnl not in (None, ''):
            realized_return_pct = round(n(realized_pnl) / entry_amount * 100, 2)
        trade_result = None
        if realized_pnl not in (None, ''):
            trade_result = '익절' if n(realized_pnl) > 0 else '손절' if n(realized_pnl) < 0 else '본전'
        category = exit_review_category(c.get('action') or c.get('status') or '', reason, status, execution_status or 'REVIEW_ONLY_NOT_EXECUTED')
        row = {
            'code': str(c.get('code') or c.get('symbol') or c.get('pdno') or ''),
            'name': str(c.get('name') or c.get('stockName') or c.get('prdt_name') or ''),
            'status': status,
            'reason': reason,
            'returnPct': realized_return_pct,
            'realizedReturnPct': realized_return_pct,
            'sellScore': c.get('sellScore') if c.get('sellScore') not in (None, '') else None,
            'pnl': realized_pnl,
            'realizedPnl': realized_pnl,
            'tradeResult': trade_result,
            'sellPrice': sell_price,
            'sellAmount': sell_amount,
            'entryAmount': round(entry_amount) if entry_amount is not None else None,
            'heldQty': c.get('heldQty') if c.get('heldQty') not in (None, '') else c.get('qty'),
            'sellQty': c.get('sellQty') if c.get('sellQty') not in (None, '') else c.get('qty'),
            'executedQty': executed_qty,
            'executionStatus': execution_status or 'REVIEW_ONLY_NOT_EXECUTED',
            'accountType': account_type,
            'executionSource': execution_source,
            'reviewAction': public_text(c.get('action') or c.get('status') or ''),
            'exitReviewCategory': category,
        }
        enrich_sell_record_prices(row)
        row['finalIntegratedDecision'] = final_integrated_decision(row)
        row['decisionContract'] = decision_contract_for_item(row, None, 'sell')
        out.append(row)
    return out

def safe_buy_fills(dry, virtual, limit=50):
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
                'buyPrice': c.get('price'),
                'buyAmount': c.get('amount'),
                'buyQty': c.get('qty'),
                'buyTime': c.get('time'),
                'executionStatus': c.get('status') or 'VIRTUAL_FILLED',
                'accountType': '가상계좌',
            })
    return rows[:limit]


def parse_loose_dt(value):
    if value in (None, ''):
        return None
    text = str(value).strip().replace('Z', '+00:00')
    try:
        dt = datetime.datetime.fromisoformat(text)
    except Exception:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.datetime.strptime(text, fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def state_trade_price_context(sid, code, sell_at=None):
    """Infer missing historical buy/sell prices from local strategy ledgers.

    KIS mock order events only prove the order was accepted; they often do not
    carry fill price/average entry. For the dashboard history, use the strategy's
    own trade/position snapshots as a read-only reconstruction source and mark
    the basis so blanks do not hide useful audit context.
    """
    path = STATE_PATH_BY_SESSION.get(sid)
    if not path:
        return {}
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    code = str(code or '').zfill(6)
    sell_dt = parse_loose_dt(sell_at) or datetime.datetime.now(KST)
    out = {}
    opens = []
    for t in state.get('trade_history') or []:
        if not isinstance(t, dict) or str(t.get('code') or '').zfill(6) != code:
            continue
        if t.get('phase') != 'open' and t.get('action') not in ('매수', 'BUY'):
            continue
        tdt = parse_loose_dt(t.get('timestamp') or f"{t.get('date') or ''} {t.get('time') or ''}".strip())
        if tdt and tdt <= sell_dt and t.get('price') not in (None, '', 0):
            opens.append((tdt, t))
    if opens:
        opens.sort(key=lambda x: x[0], reverse=True)
        latest = opens[0][1]
        out.update({
            'entryPrice': latest.get('price'),
            'entryAt': latest.get('timestamp') or f"{latest.get('date') or ''} {latest.get('time') or ''}".strip(),
            'priceBasis': 'strategy_trade_history',
        })
    nearest = None
    nearest_delta = None
    for h in state.get('position_history') or []:
        if not isinstance(h, dict) or str(h.get('code') or '').zfill(6) != code:
            continue
        hdt = parse_loose_dt(h.get('key', '').split('|')[0] or f"{h.get('date') or ''} {h.get('time') or ''}".strip())
        if not hdt or h.get('price') in (None, '', 0):
            continue
        delta = abs((hdt - sell_dt).total_seconds())
        if nearest_delta is None or delta < nearest_delta:
            nearest_delta = delta
            nearest = h
    if nearest:
        out.setdefault('entryPrice', nearest.get('avg_price'))
        out['sellPrice'] = nearest.get('price')
        out['sellPriceBasis'] = 'nearest_position_history'
        out['sellPriceAt'] = f"{nearest.get('date') or ''} {nearest.get('time') or ''}".strip()
    return out

def execution_event_alerts(sid, limit=50):
    d = RUNTIME / 'order_execution_events'
    if not d.exists():
        return []
    rows = []
    for p in sorted(d.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            e = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        if e.get('sessionId') != sid or e.get('action') != 'SELL':
            continue
        row = {
            'code': str(e.get('code') or ''),
            'name': str(e.get('name') or ''),
            'status': '(KIS) 모의매도 체결 성공',
            'reason': f"{e.get('qty') or ''}주 · KIS 모의투자 API 처리 · 주문번호 {e.get('orderNo') or '-'} · 주문시각 {e.get('orderTime') or '-'}",
            'heldQty': e.get('qty'),
            'sellQty': e.get('qty'),
            'executedQty': e.get('qty'),
            'sellAt': e.get('recordedAt'),
            'executionStatus': e.get('executionStatus') or 'MOCK_SELL_FILLED_CONFIRMED_BY_KIS_RESPONSE',
            'orderNo': e.get('orderNo'),
            'orderTime': e.get('orderTime'),
            'executionSource': 'KIS_MOCK_API',
            'accountType': 'KIS 모의계좌',
            'reviewAction': '매도 체결',
        }
        row.update({k: v for k, v in state_trade_price_context(sid, row.get('code'), row.get('sellAt')).items() if v not in (None, '')})
        rows.append(enrich_sell_record_prices(row))
        if len(rows) >= limit:
            break
    return rows


def enrich_sell_record_prices(row):
    if not isinstance(row, dict):
        return row
    code = str(row.get('code') or '').zfill(6)
    entry_price = row.get('entryPrice') if row.get('entryPrice') not in (None, '') else None
    sell_price = row.get('sellPrice') if row.get('sellPrice') not in (None, '') else row.get('exitPrice') if row.get('exitPrice') not in (None, '') else None
    qty = row.get('executedQty') if row.get('executedQty') not in (None, '', 0) else row.get('sellQty') if row.get('sellQty') not in (None, '', 0) else row.get('heldQty')
    if entry_price in (None, '') and row.get('entryAmount') not in (None, '') and qty not in (None, '', 0):
        entry_price = round(n(row.get('entryAmount')) / n(qty), 2)
    quote = readonly_quote_snapshot(code) if re.fullmatch(r'\d{6}', code) else None
    current_price = (quote or {}).get('currentPrice') if (quote or {}).get('currentPrice') not in (None, '') else row.get('currentPrice')
    row['entryPrice'] = entry_price
    row['sellPrice'] = sell_price
    row['currentPrice'] = current_price
    if sell_price not in (None, '', 0) and current_price not in (None, '', 0):
        row['currentVsSellPct'] = round((n(current_price) - n(sell_price)) / n(sell_price) * 100, 2)
        diff = n(current_price) - n(sell_price)
        row['postSellDecision'] = '매도 후 하락 · 판단 유효' if diff < 0 else ('매도 후 상승 · 기회비용' if diff > 0 else '매도 후 보합')
    if entry_price not in (None, '', 0) and current_price not in (None, '', 0):
        row['entryToCurrentPct'] = round((n(current_price) - n(entry_price)) / n(entry_price) * 100, 2)
    return row


def virtual_closed_sell_records(sid, virtual, limit=80):
    if not isinstance(virtual, dict):
        return []
    rows = []
    for p in virtual.get('positions') or []:
        if not isinstance(p, dict):
            continue
        if n(p.get('qty')) > 0 or not p.get('exitAt'):
            continue
        qty = p.get('qtyBeforeExit') if p.get('qtyBeforeExit') not in (None, '') else p.get('qty')
        sell_price = p.get('exitPrice') if p.get('exitPrice') not in (None, '') else p.get('lastPrice')
        row = {
            'code': str(p.get('code') or ''),
            'name': str(p.get('name') or ''),
            'status': '(가상계좌) 매도 완료',
            'reason': public_text(p.get('exitReason') or p.get('holdReason') or ''),
            'returnPct': p.get('returnPct'),
            'realizedReturnPct': p.get('returnPct'),
            'pnl': p.get('realizedPnl'),
            'realizedPnl': p.get('realizedPnl'),
            'tradeResult': '익절' if n(p.get('realizedPnl')) > 0 else '손절' if n(p.get('realizedPnl')) < 0 else '본전',
            'entryPrice': p.get('entryPrice'),
            'sellPrice': sell_price,
            'currentPrice': p.get('lastPrice'),
            'entryAt': p.get('entryAt'),
            'sellAt': p.get('exitAt'),
            'heldQty': qty,
            'sellQty': qty,
            'executedQty': qty,
            'executionStatus': 'VIRTUAL_AUTO_STOP_FILLED' if str(p.get('status') or '').startswith('CLOSED') else (p.get('status') or 'VIRTUAL_SELL_FILLED'),
            'accountType': '가상계좌',
            'executionSource': 'VIRTUAL_LEDGER',
            'reviewAction': p.get('holdAction') or '매도 완료',
        }
        row['exitReviewCategory'] = exit_review_category(row.get('reviewAction'), row.get('reason'), row.get('status'), row.get('executionStatus'))
        row['finalIntegratedDecision'] = final_integrated_decision(row)
        row['decisionContract'] = decision_contract_for_item(row, sid, 'sellRecord')
        rows.append(enrich_sell_record_prices(row))
    rows.sort(key=lambda x: str(x.get('sellAt') or ''), reverse=True)
    return rows[:limit]

def split_sell_items(items):
    records = []
    reviews = []
    for x in items or []:
        if not isinstance(x, dict):
            continue
        status = str(x.get('executionStatus') or '')
        if 'FILLED' in status:
            records.append(x)
        else:
            reviews.append(x)
    return records, reviews

def exit_review_category(action='', reason='', status='', execution_status=''):
    text = f'{action} {reason} {status} {execution_status}'
    is_executed = 'FILLED' in str(execution_status)
    if is_executed:
        return {'code': 'EXECUTED', 'label': '체결 기록', 'plain': '이미 체결된 매도 기록입니다.', 'isExecuted': True, 'actionType': '전량청산'}
    if re.search(r'손절|리스크 차단|중대 손실', text):
        return {'code': 'STOP', 'label': '손절/리스크 차단', 'plain': '손실 확대를 막기 위한 청산 검토입니다.', 'isExecuted': False, 'actionType': '검토만'}
    if re.search(r'익절|트레일링', text):
        return {'code': 'TAKE', 'label': '익절/트레일링', 'plain': '수익 포지션의 일부익절 또는 트레일링 검토입니다.', 'isExecuted': False, 'actionType': '트레일링관찰'}
    if re.search(r'모멘텀소멸|모멘텀 소멸|모멘텀이탈|모멘텀 이탈|진입 조건 약화|후보권 이탈', text):
        return {'code': 'MOMENTUM', 'label': '모멘텀 점검', 'plain': '수익 포지션이지만 진입 당시 모멘텀 약화 여부를 점검하는 단계입니다. 즉시 자동매도 신호는 아닙니다.', 'isExecuted': False, 'actionType': '트레일링관찰'}
    if re.search(r'보유근거|단기점수약화|점수약화|근거 약화', text):
        return {'code': 'WEAK', 'label': '보유근거 약화', 'plain': '보유 근거가 약해졌는지 확인하는 점검입니다.', 'isExecuted': False, 'actionType': '보유유지'}
    if '리밸런싱' in text:
        return {'code': 'REBALANCE', 'label': '리밸런싱 검토', 'plain': '전략 비중 조정 후보입니다.', 'isExecuted': False, 'actionType': '검토만'}
    return {'code': 'EXIT', 'label': '청산 검토', 'plain': '매도 실행 전 검토 상태입니다.', 'isExecuted': False, 'actionType': '검토만'}

def final_integrated_decision(item):
    if not isinstance(item, dict):
        return None
    cat = item.get('exitReviewCategory') if isinstance(item.get('exitReviewCategory'), dict) else {}
    f = item.get('fundamentals') if isinstance(item.get('fundamentals'), dict) else {}
    expert = f.get('expertAnalysis') if isinstance(f.get('expertAnalysis'), dict) else {}
    survival = expert.get('survival') if isinstance(expert.get('survival'), dict) else {}
    score = expert.get('score')
    confidence = survival.get('confidenceScore')
    return_pct = item.get('returnPct')
    strong_stock = isinstance(score, (int, float)) and isinstance(confidence, (int, float)) and score >= 75 and confidence >= 60
    code = cat.get('code') or 'EXIT'
    stock_layer = f"종목분석: score {score if score is not None else '-'}, confidence {confidence if confidence is not None else '-'}, action {survival.get('actionState') or '-'}"
    position_layer = f"보유관리: {cat.get('label') or '청산 검토'}, 실행상태 {'체결' if cat.get('isExecuted') else '검토만/미체결'}, actionType {cat.get('actionType') or '-'}"
    if code == 'MOMENTUM':
        action = 'HOLD_WITH_TRAILING_CHECK'
        plain = '종목 자체는 우호적이나, 보유 포지션 기준에서는 진입 조건 약화 여부를 점검하는 단계입니다. 신규 매수보다 기존 보유분의 트레일링/모멘텀 유지 여부 확인이 우선입니다.' if strong_stock else '보유 포지션 기준에서는 진입 당시 모멘텀 약화 여부를 점검하는 단계입니다. 즉시 자동매도 신호는 아니며 보유 조건 확인이 우선입니다.'
    elif code == 'TAKE':
        action = 'PROTECT_PROFIT_WITH_TRAILING'
        plain = '수익 포지션의 일부익절 또는 트레일링 검토 단계입니다. 즉시 전량매도보다 수익 보호 조건 확인이 우선입니다.'
    elif code == 'STOP':
        action = 'RISK_CUT_REVIEW'
        plain = '손실 확대 방어가 우선인 리스크 차단 단계입니다. 보유 지속보다 청산 조건 확인이 우선입니다.'
    elif code == 'WEAK':
        action = 'HOLD_BASIS_RECHECK'
        plain = '보유 근거가 약해졌는지 확인하는 단계입니다. 신규 매수는 보류하고 보유 지속 조건을 재점검합니다.'
    elif code == 'REBALANCE':
        action = 'REBALANCE_REVIEW'
        plain = '종목 자체 매도 신호라기보다 전략 내 비중 조정 후보입니다. 대체 후보와 상대강도를 비교합니다.'
    elif code == 'EXECUTED':
        action = 'SELL_EXECUTED_RECORD'
        plain = '이미 체결된 매도 기록입니다. 현재 행동 지시가 아니라 사후 기록으로 봅니다.'
    else:
        action = 'EXIT_REVIEW'
        plain = '보유 포지션 청산 검토 단계입니다. 실행 전 수량·조건·체결 여부를 별도로 확인해야 합니다.'
    conditions = final_decision_conditions(code, score, confidence, return_pct)
    return {'action': action, 'plain': plain, 'conditions': conditions, 'layers': {'stockAnalysis': stock_layer, 'positionManagement': position_layer}, 'source': 'dashboard-generator-v1'}

def final_decision_conditions(code, score=None, confidence=None, return_pct=None):
    score_text = score if isinstance(score, (int, float)) else '-'
    confidence_text = confidence if isinstance(confidence, (int, float)) else '-'
    return_text = f"현재수익률 {round(return_pct, 2)}%" if isinstance(return_pct, (int, float)) else '현재수익률 확인 필요'
    common = {
        'hold': f'종목 점수 {score_text} 유지, 확신도 {confidence_text}가 55 이상, 20일 전고점/주요 지지선 위에서 거래대금이 20일 평균 이상이면 보유 유지',
        'partialTakeProfit': f'{return_text}; 수익률 +10% 이상 도달 후 거래대금이 20일 평균 아래로 둔화되면 20~30% 일부익절 검토',
        'trailingStop': '최근 고점 대비 -3~5% 하락 또는 5분봉 재돌파 2회 실패 시 트레일링 스탑 검토',
        'exit': '진입 조건 완전 훼손 + 후보권 이탈이 2회 연속 유지되거나 주요 지지선 이탈 시 전량 청산 검토',
        'newBuy': '신규 매수는 거래대금 재확인 전 보류; score 75 이상·confidence 60 이상·시장 Regime 중립 이상일 때만 분할 허용',
        'reviewAt': '다음 정규장 09:45 이후',
    }
    if code == 'TAKE':
        common.update({
            'hold': '수익 구간 유지 + 고점 대비 -3% 이내 + 거래대금 20일 평균 이상이면 잔여 보유',
            'partialTakeProfit': '수익률 +10% 이상 또는 단기 급등 후 거래대금 둔화 시 20~30% 일부익절 우선',
            'trailingStop': '익절 후 잔여분은 고점 대비 -3~5% 또는 5일선 이탈 시 축소',
            'newBuy': '추가 신규 매수는 금지; 눌림 후 거래대금 재증가 확인 전까지 추격 금지',
        })
    elif code == 'STOP':
        common.update({
            'hold': '주요 지지선 회복 + 거래대금 동반 반등 + 손실폭 -5% 이내일 때만 임시 보유',
            'partialTakeProfit': '해당 없음; 손실 방어 우선',
            'trailingStop': '반등 실패 후 전저점 재이탈 또는 고점 대비 -3% 추가 하락 시 즉시 축소 검토',
            'exit': '손실률 -5~7% 초과, 전저점 이탈, 또는 리스크 차단 신호 2회 연속이면 전량 청산 검토',
            'newBuy': '신규 매수 금지; 손절 사유 해소와 2거래일 안정화 전까지 재진입 금지',
        })
    elif code == 'MOMENTUM':
        common.update({
            'hold': '20일 전고점 또는 진입 당시 핵심 모멘텀 구간 위 유지 + 거래대금 20일 평균 이상이면 보유 유지',
            'partialTakeProfit': '수익률 +10% 이상 도달 후 거래대금 둔화 또는 장중 고점 돌파 실패 시 20~30% 일부익절 검토',
            'trailingStop': '최근 고점 대비 -3~5% 하락, 5분봉 재돌파 2회 실패, 또는 후보권 이탈 시 트레일링 스탑 검토',
            'exit': '진입 조건 완전 훼손 + 후보권 이탈이 다음 재평가까지 지속되면 전량 청산 검토',
            'newBuy': '신규 매수는 보류; 거래대금 재확인과 모멘텀 회복 전까지 기존 보유분 관리 우선',
        })
    elif code == 'WEAK':
        common.update({
            'hold': '보유 근거 회복 + confidence 55 이상 + 주요 지지선 유지 시 보유 유지',
            'partialTakeProfit': '수익 구간이면 반등 실패 시 20% 축소 검토',
            'trailingStop': '점수 70 미만 하락 또는 고점 대비 -4% 하락 시 축소 검토',
            'exit': '보유 근거 약화가 2회 연속 유지되고 score 65 미만이면 전량 청산 검토',
            'newBuy': '신규 매수 금지; 보유 근거 회복과 score 75 회복 전까지 관찰',
        })
    elif code == 'REBALANCE':
        common.update({
            'hold': '전략 내 상대강도 상위 50% 유지 또는 대체 후보 부재 시 보유 유지',
            'partialTakeProfit': '비중 초과 또는 대체 후보 score가 5점 이상 우위일 때 20~30% 축소',
            'trailingStop': '상대강도 하락 + 고점 대비 -4% 하락 시 비중 축소',
            'exit': '대체 후보가 2회 연속 우위이고 현 종목 score 65 미만이면 전량 교체 검토',
            'newBuy': '추가 매수 금지; 포트폴리오 비중 한도와 대체 후보 비교 후 허용',
        })
    elif code == 'EXECUTED':
        common.update({
            'hold': '이미 체결된 기록이므로 보유 조건 없음',
            'partialTakeProfit': '이미 체결된 기록',
            'trailingStop': '이미 체결된 기록',
            'exit': '사후 기록 검증만 수행',
            'newBuy': '재진입은 별도 신규 판단 필요; 기존 체결 기록만으로 매수 금지',
        })
    return common


def decision_contract_for_item(item, sid=None, source='candidate'):
    """Explicit AGENT -> Dashboard state contract.

    Dashboard must translate these states, not infer trading meaning from free text.
    This is read-only presentation metadata; it does not execute or authorize orders.
    """
    if not isinstance(item, dict):
        item = {}
    raw_qty = item.get('qty') if item.get('qty') not in (None, '') else item.get('heldQty')
    qty = 0 if source == 'sellRecord' else n(raw_qty)
    ret_raw = item.get('returnPct') if item.get('returnPct') not in (None, '') else item.get('realizedReturnPct')
    ret = n(ret_raw) if ret_raw not in (None, '') else None
    score = item.get('currentScoreNormalized') if item.get('currentScoreNormalized') is not None else item.get('score')
    score_num = n(score) if score is not None else None
    text = f"{item.get('status') or ''} {item.get('action') or ''} {item.get('reviewAction') or ''} {item.get('holdAction') or ''} {item.get('reason') or ''} {item.get('holdReason') or ''}"
    execution_status = str(item.get('executionStatus') or '')
    executed_qty = n(item.get('executedQty')) if item.get('executedQty') not in (None, '') else 0
    executed = 'FILLED' in execution_status or executed_qty > 0
    is_holding = source == 'holding' or (source in ('sell', 'sellAlert') and not executed and qty > 0) or qty > 0 or '보유중' in text or item.get('holdAction')
    if source in ('candidate', 'buy') and not is_holding:
        cat = {}
    else:
        cat = item.get('exitReviewCategory') if isinstance(item.get('exitReviewCategory'), dict) else exit_review_category(item.get('reviewAction') or item.get('holdAction') or item.get('action') or '', item.get('reason') or item.get('holdReason') or '', item.get('status') or '', execution_status or 'REVIEW_ONLY_NOT_EXECUTED')

    if executed:
        position_state = 'EXITED' if source in ('sell', 'sellRecord') else ('HELD_PROFIT' if ret is not None and ret >= 0 else 'HELD_LOSS' if ret is not None else 'UNKNOWN')
        agent_decision = 'SELL_EXECUTED_RECORD' if source in ('sell', 'sellRecord') else 'ENTRY_EXECUTED_RECORD'
    elif is_holding:
        position_state = 'HELD_PROFIT' if ret is not None and ret >= 0 else 'HELD_LOSS' if ret is not None else 'HELD'
        if cat.get('code') in ('STOP', 'TAKE', 'MOMENTUM', 'WEAK', 'REBALANCE', 'EXIT') and cat.get('code') != 'EXECUTED':
            agent_decision = 'HOLD_WITH_EXIT_REVIEW'
        else:
            agent_decision = 'HOLD'
    else:
        position_state = 'NOT_HELD'
        agent_decision = 'NEW_ENTRY_REVIEW' if (score_num is not None and score_num >= 70) or re.search(r'매수|후보|검토', text) else 'WATCH'

    stop_loss = cat.get('code') == 'STOP' or bool(re.search(r'손절|리스크 차단|중대 손실', text))
    partial_take = cat.get('code') == 'TAKE' or bool(re.search(r'익절|트레일링', text))
    momentum_check = cat.get('code') == 'MOMENTUM' or bool(re.search(r'모멘텀|진입 조건 약화|후보권 이탈', text))
    full_exit = cat.get('code') in ('STOP', 'EXIT')

    if executed:
        execution_state = 'EXECUTED'
        execution_label = '체결 기록'
    elif source in ('sell', 'sellAlert') or cat.get('code') in ('STOP', 'TAKE', 'MOMENTUM', 'WEAK', 'REBALANCE', 'EXIT'):
        execution_state = 'REVIEW_ONLY_NOT_EXECUTED'
        execution_label = '검토만 · 미체결 · 자동매매 아님'
    else:
        execution_state = 'NOT_EXECUTED'
        execution_label = '실행 없음'

    if is_holding:
        new_entry_allowed = False
        new_entry_state = 'LIMITED_OR_BLOCKED'
        new_entry_label = '신규 진입 제한 / 기존 보유 우선'
        hold_allowed = not stop_loss or (ret is not None and ret > -4)
        hold_state = 'HOLD_ALLOWED' if hold_allowed else 'HOLD_RECHECK_REQUIRED'
        hold_label = '기존 보유 유지 가능' if hold_allowed else '보유 지속 재점검 필요'
    else:
        new_entry_allowed = agent_decision == 'NEW_ENTRY_REVIEW' and execution_state == 'NOT_EXECUTED'
        new_entry_state = 'ENTRY_REVIEW' if new_entry_allowed else 'WATCH_ONLY'
        new_entry_label = '신규 진입 검토' if new_entry_allowed else '단순 관찰'
        hold_allowed = False
        hold_state = 'NO_POSITION'
        hold_label = '보유 없음'

    if executed:
        exit_state, exit_label, exit_type = 'EXECUTED', '체결 기록', 'EXECUTED'
    elif stop_loss:
        exit_state, exit_label, exit_type = 'STOP_LOSS_REVIEW', '손절/리스크 차단 검토', 'STOP'
    elif partial_take:
        exit_state, exit_label, exit_type = 'TAKE_PROFIT_OR_TRAILING_REVIEW', '일부익절/트레일링 검토', 'TAKE_PROFIT'
    elif momentum_check:
        exit_state, exit_label, exit_type = 'MOMENTUM_CHECK', '모멘텀 점검', 'MOMENTUM_CHECK'
    elif is_holding:
        exit_state, exit_label, exit_type = 'NO_EXIT_SIGNAL', '즉시 청산 신호 없음', 'NONE'
    else:
        exit_state, exit_label, exit_type = 'NO_POSITION_EXIT', '청산 대상 아님', 'NONE'

    if score_num is not None and score_num >= 80:
        confidence = 'HIGH'
    elif score_num is not None and score_num >= 65:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW_OR_UNKNOWN'
    risk_level = 'HIGH' if stop_loss else 'MEDIUM' if partial_take or momentum_check or (ret is not None and ret < 0) else 'LOW'

    if executed:
        plain = '이미 체결된 기록입니다. 현재 행동 지시가 아니라 사후 기록으로 봅니다.'
    elif is_holding and momentum_check:
        plain = '신규 진입보다는 기존 보유분의 모멘텀 유지 여부를 점검하는 단계입니다. 즉시 자동매도 신호는 아닙니다.'
    elif is_holding and partial_take:
        plain = '기존 보유 수익을 보호하기 위한 일부익절 또는 트레일링 검토 단계입니다. 전량 청산과 구분해서 봅니다.'
    elif is_holding and stop_loss:
        plain = '손실 확대 방어를 위한 청산 조건 점검 단계입니다. 실제 실행 여부는 별도 실행 상태를 확인해야 합니다.'
    elif is_holding:
        plain = '기존 보유는 유지 가능하며, 신규 진입 판단과 분리해서 관찰합니다.'
    elif new_entry_allowed:
        plain = '신규 진입 검토 대상입니다. 보유 판단이나 매도 판단과 분리된 진입 레이어입니다.'
    else:
        plain = '현재는 단순 관찰 상태입니다. 신규 진입·보유·청산 실행과 구분해서 표시합니다.'

    return {
        'version': 'decision-contract-v1',
        'symbol': str(item.get('code') or item.get('symbol') or ''),
        'positionState': position_state,
        'agentDecision': agent_decision,
        'newEntry': {'allowed': bool(new_entry_allowed), 'state': new_entry_state, 'label': new_entry_label},
        'holding': {'allowed': bool(hold_allowed), 'state': hold_state, 'label': hold_label},
        'exit': {
            'state': exit_state,
            'type': exit_type,
            'label': exit_label,
            'partialTakeProfitAllowed': bool(partial_take),
            'fullExitReview': bool(full_exit),
            'stopLoss': bool(stop_loss),
            'momentumCheck': bool(momentum_check),
        },
        'execution': {
            'state': execution_state,
            'executed': bool(executed),
            'executedQty': executed_qty,
            'autoTradeExecuted': bool(executed and item.get('executionSource') in ('KIS_MOCK_API', 'VIRTUAL_LEDGER')),
            'label': execution_label,
        },
        'riskLevel': risk_level,
        'confidence': confidence,
        'positionSizePolicy': 'KEEP_OR_TRAIL' if is_holding and (partial_take or momentum_check) else 'KEEP' if is_holding else 'ENTRY_REVIEW' if new_entry_allowed else 'WATCH_ONLY',
        'plainSummary': public_text(plain, 220),
    }

def sync_holding_alerts_from_positions(session):
    positions = ((session.get('portfolio') or {}).get('positions') or []) if isinstance(session.get('portfolio'), dict) else []
    by_code = {str(p.get('code') or ''): p for p in positions if isinstance(p, dict)}
    for arr_name in ('buyAlerts', 'sellAlerts'):
        arr = session.get(arr_name)
        if not isinstance(arr, list):
            continue
        for a in arr:
            if not isinstance(a, dict):
                continue
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
    sell_items = []
    seen_sell = set()
    for a in execution_event_alerts(sid):
        sell_items.append(a)
        seen_sell.add(str(a.get('code') or ''))
    for a in virtual_closed_sell_records(sid, virtual):
        key = str(a.get('code') or '')
        sell_items.append(a)
        seen_sell.add(key)
    if sell_count:
        for a in safe_alerts(sell):
            if str(a.get('code') or '') in seen_sell:
                continue
            if str(a.get('status') or '') == '보유유지':
                continue
            sell_items.append(a)
    sell_records, sell_alerts = split_sell_items(sell_items)
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
        'sellRecords': sell_records,
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
INTRADAY_CANDLE_CACHE = {}

def intraday_candle_snapshot(code):
    code = str(code or '').zfill(6)
    if not re.fullmatch(r'\d{6}', code):
        return None
    if code in INTRADAY_CANDLE_CACHE:
        return INTRADAY_CANDLE_CACHE[code]
    out = None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        basic_req = urllib.request.Request(f'https://m.stock.naver.com/api/stock/{code}/basic', headers=headers)
        basic = json.loads(urllib.request.urlopen(basic_req, timeout=8).read().decode('utf-8', 'replace'))
        today = datetime.datetime.now(KST).strftime('%Y%m%d')
        if basic.get('marketStatus') == 'CLOSE':
            try:
                env = load_env_file(KIS_ENV_PATH)
                appkey, appsecret = env.get('KIS_JAESANG_MOCK_APP_KEY'), env.get('KIS_JAESANG_MOCK_APP_SECRET')
                access = cached_access_token('jaesang.short.mock')
                if appkey and appsecret and not access:
                    tok = post_json(f'{KIS_BASE}/oauth2/tokenP', {'grant_type':'client_credentials','appkey':appkey,'appsecret':appsecret})
                    access = tok.get('access_token')
                    if access: save_access_token('jaesang.short.mock', tok)
                if appkey and appsecret and access:
                    params = urllib.parse.urlencode({'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':code})
                    q = get_json(f'{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price?{params}', {
                        'content-type':'application/json; charset=utf-8', 'authorization':f'Bearer {access}',
                        'appkey':appkey, 'appsecret':appsecret, 'tr_id':'FHKST01010100', 'custtype':'P'
                    })
                    o = q.get('output') if isinstance(q, dict) else {}
                    close = n((o or {}).get('stck_prpr'))
                    if close > 0:
                        return {
                            'date': today,
                            'open': round(n(o.get('stck_oprc')) or close),
                            'high': round(n(o.get('stck_hgpr')) or close),
                            'low': round(n(o.get('stck_lwpr')) or close),
                            'close': round(close),
                            'volume': round(n(o.get('acml_vol'))) if o.get('acml_vol') not in (None, '') else None,
                            'tradingValue': round(n(o.get('acml_tr_pbmn'))) if o.get('acml_tr_pbmn') not in (None, '') else None,
                            'changePct': round(n(o.get('prdy_ctrt')), 2) if o.get('prdy_ctrt') not in (None, '') else None,
                            'updatedAt': basic.get('localTradedAt') or datetime.datetime.now(KST).isoformat(timespec='seconds'),
                            'source': 'kis-inquire-price-close',
                            'marketStatus': basic.get('marketStatus'),
                        }
            except Exception:
                pass
        if basic.get('marketStatus') == 'CLOSE':
            try:
                daily_url = f'https://api.finance.naver.com/siseJson.naver?symbol={code}&requestType=1&startTime={today}&endTime={today}&timeframe=day'
                daily_body = urllib.request.urlopen(urllib.request.Request(daily_url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://finance.naver.com/'}), timeout=8).read().decode('euc-kr', 'replace')
                m = re.findall(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)', daily_body)
                if m:
                    d, open_p, high, low, close, volume = m[-1]
                    return {
                        'date': d,
                        'open': round(n(open_p)),
                        'high': round(n(high)),
                        'low': round(n(low)),
                        'close': round(n(close)),
                        'volume': round(n(volume)),
                        'changePct': round(n(basic.get('fluctuationsRatio')), 2) if basic.get('fluctuationsRatio') not in (None, '') else None,
                        'updatedAt': basic.get('localTradedAt') or datetime.datetime.now(KST).isoformat(timespec='seconds'),
                        'source': 'naver-sisejson-close',
                        'marketStatus': basic.get('marketStatus'),
                    }
            except Exception:
                pass
        req = urllib.request.Request(f'https://m.stock.naver.com/api/stock/{code}/integration', headers=headers)
        r = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace'))
        infos = {str(x.get('code')): x.get('value') for x in (r.get('totalInfos') or []) if isinstance(x, dict)}
        close = n(basic.get('closePrice') or (basic.get('overMarketPriceInfo') or {}).get('overPrice'))
        open_p = n(infos.get('openPrice'))
        high = n(infos.get('highPrice'))
        low = n(infos.get('lowPrice'))
        volume = n(infos.get('accumulatedTradingVolume'))
        trading_value = n(str(infos.get('accumulatedTradingValue') or '').replace('백만', '')) * 1000000 if infos.get('accumulatedTradingValue') else None
        updated = basic.get('localTradedAt') or (basic.get('overMarketPriceInfo') or {}).get('localTradedAt') or datetime.datetime.now(KST).isoformat(timespec='seconds')
        if close > 0:
            out = {
                'date': ''.join(ch for ch in str(updated)[:10] if ch.isdigit()) or datetime.datetime.now(KST).strftime('%Y%m%d'),
                'open': round(open_p or close),
                'high': round(high or close),
                'low': round(low or close),
                'close': round(close),
                'volume': round(volume) if volume else None,
                'tradingValue': round(trading_value) if trading_value else None,
                'changePct': round(n(basic.get('fluctuationsRatio')), 2) if basic.get('fluctuationsRatio') not in (None, '') else None,
                'updatedAt': updated,
                'source': 'naver-stock-integration',
                'marketStatus': basic.get('marketStatus'),
            }
    except Exception:
        out = None
    INTRADAY_CANDLE_CACHE[code] = out
    return out


AI_MEMORY_CODES = {'000660', '005930'}
AI_MEMORY_THEME = {
    'id': 'ai-memory-premium',
    'name': 'AI Memory Premium',
    'state': 'WEAKENING',
    'label': '약화 점검',
    'strengthScore': 68,
    'riskLevel': 'HIGH',
    'updatedAt': None,
    'plain': 'AI CAPEX와 HBM/고성능 DRAM 수요의 장기 근거는 유지되지만, SOX 급등 후 조정·Nvidia 등 AI 주식 차익실현·국내 대형 반도체 외국인 매도와 NXT 약세가 겹쳐 단기 프리미엄은 약화 점검 구간입니다.',
    'watchSignals': ['Nvidia/글로벌 AI CAPEX', 'HBM 공급계약·점유율', 'DRAM/NAND 가격', 'SOX/Micron/TSMC 상대강도', '외국인·기관 수급', '고PBR 정당화 여부'],
    'positiveRules': ['HBM 주도권과 AI 메모리 이익 사이클이 확인되면 PBR 경고를 완화합니다.', 'ROE 개선이 동반되면 고PBR을 단순 고평가로 보지 않습니다.'],
    'riskRules': ['AI CAPEX 둔화, HBM 판가 하락, DRAM 가격 피크아웃, SOX 약세가 겹치면 프리미엄을 종료 검토로 낮춥니다.', 'SOX/엔비디아/마이크론/TSMC 조정과 국내 외국인 매도가 동시에 이어지면 신규 진입 가중치를 낮춥니다.', '삼성전자는 HBM 경쟁력/공급 검증 전까지 하이닉스보다 프리미엄을 할인합니다.'],
    'reviewNotes': ['2026-05-17 weekly review: SOX는 3월 말 이후 급등해 과열 부담이 커졌고 최근 AI 고성장주 차익실현이 확인됐습니다.', '국내는 2026-05-15 코스피 급등 후 반락 과정에서 삼성전자·SK하이닉스 중심 외국인 매도가 커져 단기 수급 확인이 필요합니다.', '메모리 가격/HBM 수요와 TSMC·ASML의 AI 투자 전망은 구조적 근거를 지지해 ENDED가 아닌 WEAKENING으로 유지합니다.'],
    'nextLeadershipCandidates': [
        {'id': 'power-infra-ai-grid', 'name': '전력기기/AI 전력 인프라', 'state': 'CANDIDATE', 'score': 72, 'plain': 'AI 데이터센터 전력 수요와 변압기/전력망 투자 사이클은 반도체 조정 시 대체 주도 업종 후보입니다.', 'watchSignals': ['HD현대일렉트릭/효성중공업 상대강도', '미국 전력망·데이터센터 발주', '수주잔고와 마진']},
        {'id': 'shipbuilding-defense', 'name': '조선/방산', 'state': 'CANDIDATE', 'score': 66, 'plain': '수주잔고·환율·방산 수출 모멘텀이 있어 시장 확산 국면의 후보입니다.', 'watchSignals': ['HD현대중공업/한화에어로스페이스 상대강도', '신규 수주/인도 마진', '외국인 수급']},
        {'id': 'materials-metals', 'name': '금속/소재', 'state': 'WATCH', 'score': 58, 'plain': '반도체 차익실현 자금의 순환매 후보이나 경기/원자재 민감도가 높아 확인 후 접근합니다.', 'watchSignals': ['철강·구리 가격', '중국 수요', '환율과 정책 모멘텀']},
    ],
    'codePolicy': {
        '000660': {'premium': 'FULL_BUT_TACTICAL_RISK', 'label': 'AI/HBM 직접 수혜·단기 과열 점검', 'pbrPenalty': 'soften', 'plain': 'SK하이닉스는 HBM 주도권과 AI 메모리 사이클을 우선 반영하되, 외국인 매도와 글로벌 AI 주식 조정이 멈출 때까지 신규 가중은 낮춥니다.'},
        '005930': {'premium': 'PARTIAL', 'label': 'AI 수혜 일부 반영·검증 필요', 'pbrPenalty': 'partial', 'plain': '삼성전자는 AI 수혜 기대는 반영하되 HBM 경쟁력·공급 검증과 노이즈 해소 전까지 하이닉스보다 할인합니다.'},
    },
}

def theme_regime_snapshot(generated_at=None):
    theme = json.loads(json.dumps(AI_MEMORY_THEME, ensure_ascii=False))
    theme['updatedAt'] = generated_at or datetime.datetime.now(KST).isoformat(timespec='minutes')
    return {
        'generatedAt': theme['updatedAt'],
        'themes': [theme],
        'summary': {
            'primaryTheme': theme['name'],
            'state': theme['state'],
            'strengthScore': theme['strengthScore'],
            'riskLevel': theme['riskLevel'],
            'plain': theme['plain'],
            'nextLeadershipCandidates': theme.get('nextLeadershipCandidates') or [],
        },
    }

def ai_memory_theme_for_code(code):
    code = str(code or '').zfill(6)
    if code not in AI_MEMORY_CODES:
        return None
    theme = json.loads(json.dumps(AI_MEMORY_THEME, ensure_ascii=False))
    policy = theme.get('codePolicy', {}).get(code, {})
    return {
        'id': theme['id'],
        'name': theme['name'],
        'state': theme['state'],
        'label': theme['label'],
        'strengthScore': theme['strengthScore'],
        'riskLevel': theme['riskLevel'],
        'policy': policy,
        'plain': policy.get('plain') or theme['plain'],
        'watchSignals': theme['watchSignals'],
        'riskRules': theme['riskRules'],
        'reviewNotes': theme.get('reviewNotes') or [],
    }

def apply_theme_regime_to_fundamentals(f):
    if not isinstance(f, dict):
        return f
    code = str(f.get('code') or '').zfill(6)
    theme = ai_memory_theme_for_code(code)
    if not theme:
        return f
    out = json.loads(json.dumps(f, ensure_ascii=False))
    out['themeRegime'] = theme
    report = out.get('report') if isinstance(out.get('report'), list) else []
    policy = theme.get('policy') or {}
    pbr = out.get('pbr')
    if pbr is not None:
        report.insert(0, f"{theme['name']} {theme['label']}: PBR {pbr}은 단독 고평가 경고가 아니라 HBM/AI 메모리 프리미엄 정당화 여부와 함께 봅니다.")
    badge = str(out.get('badge') or '')
    if '고PBR' in badge and policy.get('pbrPenalty') == 'soften':
        out['badge'] = badge.replace('고PBR', 'AI프리미엄PBR')
    elif '고PBR' in badge and policy.get('pbrPenalty') == 'partial':
        out['badge'] = f"{badge} · AI프리미엄확인"
    out['report'] = report[:5]
    expert = out.get('expertAnalysis') if isinstance(out.get('expertAnalysis'), dict) else None
    if expert:
        basis = expert.get('basis') if isinstance(expert.get('basis'), list) else []
        basis.insert(0, f"ThemeRegime={theme['name']}:{theme['state']}:{policy.get('premium', 'WATCH')}")
        expert['basis'] = basis[:6]
        key_points = expert.get('keyPoints') if isinstance(expert.get('keyPoints'), list) else []
        key_points.insert(0, theme.get('plain'))
        expert['keyPoints'] = key_points[:6]
        survival = expert.get('survival') if isinstance(expert.get('survival'), dict) else None
        if survival:
            survival['themeRegime'] = theme
            rules = survival.get('sectorRulesApplied') if isinstance(survival.get('sectorRulesApplied'), list) else []
            rules.insert(0, policy.get('plain') or theme['plain'])
            survival['sectorRulesApplied'] = rules[:7]
            try:
                base = float(survival.get('confidenceScore'))
                delta = 4 if policy.get('premium') == 'FULL' else 1
                survival['preThemeConfidenceScore'] = round(base)
                score = max(0, min(100, round(base + delta)))
                survival['confidenceScore'] = score
                survival['confidenceLevel'] = 'High' if score >= 75 else ('Medium' if score >= 60 else ('Low' if score >= 45 else 'Uncertain'))
            except Exception:
                pass
    return out

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
    f = apply_theme_regime_to_fundamentals(f)
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
            'survival': expert.get('survival') if isinstance(expert.get('survival'), dict) else None,
            'additionalDataNeeded': [public_text(x, 260) for x in (expert.get('additionalDataNeeded') or [])[:5]],
            'basis': [public_text(x, 120) for x in (expert.get('basis') or [])[:5]],
            'disclaimer': public_text(expert.get('disclaimer'), 220),
        }
    return {
        'per': f.get('per'),
        'pbr': f.get('pbr'),
        'roe': f.get('roe'),
        'sectorProfile': f.get('sectorProfile') if isinstance(f.get('sectorProfile'), dict) else None,
        'themeRegime': f.get('themeRegime') if isinstance(f.get('themeRegime'), dict) else None,
        'peerAverage': f.get('peerAverage') if isinstance(f.get('peerAverage'), dict) else {},
        'peerGrowthMargin': f.get('peerGrowthMargin') if isinstance(f.get('peerGrowthMargin'), dict) else None,
        'badge': public_text(f.get('badge') or '', 40),
        'report': [public_text(x, 180) for x in (f.get('report') or [])[:4]],
        'expertAnalysis': public_expert,
        'technicalStructure': f.get('technicalStructure') if isinstance(f.get('technicalStructure'), dict) else None,
        'technicalSignal': signal,
        'intradayCandle': intraday_candle_snapshot(code),
        'nxtQuote': None,
        'stockFutureQuote': None,
        'kisEnrichment': kis,
        'universeStatus': f.get('universeStatus'),
        'updatedAt': f.get('updatedAt'),
        'source': f.get('source'),
    }

def attach_nxt_reference(item):
    if not isinstance(item, dict):
        return
    f = item.get('fundamentals') if isinstance(item.get('fundamentals'), dict) else None
    if not f:
        return
    f['nxtQuote'] = f.get('nxtQuote') or nxt_quote_snapshot(item.get('code'))

def attach_stock_future_reference(item):
    if not isinstance(item, dict):
        return
    f = item.get('fundamentals') if isinstance(item.get('fundamentals'), dict) else None
    if not f:
        return
    quote_snapshot = readonly_quote_snapshot(item.get('code'))
    f['stockFutureQuote'] = f.get('stockFutureQuote') or stock_future_quote_snapshot(item.get('code'), quote_snapshot)

def attach_market_references(item):
    attach_nxt_reference(item)
    attach_stock_future_reference(item)


def apply_market_lead_overlay(item, source='candidate'):
    """Use NXT / stock-futures as a live market-lead overlay.

    This is not an execution trigger. It nudges ranking and review labels only;
    orders still require the normal strategy/contract gates.
    """
    if not isinstance(item, dict):
        return item
    f = item.get('fundamentals') if isinstance(item.get('fundamentals'), dict) else {}
    nxt = f.get('nxtQuote') if isinstance(f.get('nxtQuote'), dict) else {}
    fut = f.get('stockFutureQuote') if isinstance(f.get('stockFutureQuote'), dict) else {}
    reasons = []
    delta = 0
    nxt_pct = nxt.get('changePct')
    fut_signal = fut.get('signal')
    fut_vol = fut.get('volume')
    fut_rel = fut.get('relativeStrengthPct')
    try:
        nxt_num = float(nxt_pct) if nxt_pct not in (None, '') else None
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
            item['holdReason'] = f"{item.get('holdReason') or ''}; 시장선행 위험: {note}".strip('; ')
        elif delta >= 5:
            item['holdReason'] = f"{item.get('holdReason') or ''}; 시장선행 우호: {note}".strip('; ')
    else:
        if delta <= -5:
            item['action'] = item.get('action') or '시장선행 약세로 진입조건 강화'
            item['status'] = item.get('status') if item.get('status') == '보유중' else '시장선행 약세 점검'
        elif delta >= 5:
            item['action'] = item.get('action') or '시장선행 우호 확인'
            item['status'] = item.get('status') or '시장선행 우호'
    return item


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


def slim_public_fundamentals(f):
    if not isinstance(f, dict):
        return None
    expert = f.get('expertAnalysis') if isinstance(f.get('expertAnalysis'), dict) else {}
    survival = expert.get('survival') if isinstance(expert.get('survival'), dict) else {}
    return {
        'per': f.get('per'),
        'pbr': f.get('pbr'),
        'roe': f.get('roe'),
        'badge': f.get('badge'),
        'themeRegime': f.get('themeRegime') if isinstance(f.get('themeRegime'), dict) else None,
        'updatedAt': f.get('updatedAt'),
        'universeStatus': f.get('universeStatus'),
        'technicalSignal': f.get('technicalSignal'),
        'stockFutureQuote': f.get('stockFutureQuote'),
        'nxtQuote': f.get('nxtQuote'),
        'expertAnalysis': {
            'score': expert.get('score'),
            'stance': expert.get('stance'),
            'summary': expert.get('summary'),
            'survival': {
                'actionState': survival.get('actionState'),
                'confidenceScore': survival.get('confidenceScore'),
                'confidenceLevel': survival.get('confidenceLevel'),
                'positionGuide': survival.get('positionGuide'),
            } if survival else None,
        } if expert else None,
    }


def split_stock_detail_files(data):
    """Move full fundamentals to data/stocks/{code}.json and keep dashboard rows slim."""
    stocks_dir = OUT.parent/'stocks'
    stocks_dir.mkdir(parents=True, exist_ok=True)
    details = {}

    def walk(x):
        if isinstance(x, dict):
            f = x.get('fundamentals') if isinstance(x.get('fundamentals'), dict) else None
            code = str(x.get('code') or (f or {}).get('code') or '').zfill(6)
            if f and re.fullmatch(r'\d{6}', code):
                candidate = {'code': code, 'name': x.get('name') or f.get('name'), 'fundamentals': f, 'generatedAt': data.get('generatedAt')}
                old = details.get(code)
                if old is None or len(json.dumps(candidate, ensure_ascii=False)) > len(json.dumps(old, ensure_ascii=False)):
                    details[code] = candidate
                x['fundamentals'] = slim_public_fundamentals(f)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)

    for code, raw in FUNDAMENTALS_BY_CODE.items():
        code = str(code or '').zfill(6)
        if not re.fullmatch(r'\d{6}', code) or code in details:
            continue
        f = public_fundamentals(code)
        if not isinstance(f, dict):
            continue
        expert = f.get('expertAnalysis') if isinstance(f.get('expertAnalysis'), dict) else None
        if expert and isinstance(expert.get('survival'), dict):
            expert['survival'] = apply_sector_weighting_to_survival(f, apply_market_regime_to_survival(expert.get('survival'), data.get('marketRegime') or {}))
        details[code] = {'code': code, 'name': raw.get('name') or f.get('name') or code, 'fundamentals': f, 'generatedAt': data.get('generatedAt')}

    for code, payload in details.items():
        (stocks_dir/f'{code}.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    data['stockDetailIndex'] = {'basePath': 'data/stocks/', 'count': len(details), 'mode': 'lazy-load-by-code'}
    data['stockUniverse'] = [
        {
            'code': code,
            'name': payload.get('name') or code,
            'strategy': '전체 분석',
            'fundamentals': slim_public_fundamentals(payload.get('fundamentals') or {}),
        }
        for code, payload in sorted(details.items())
    ]
    return data


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
        attach_market_references(p)
        apply_market_lead_overlay(p, 'holding')
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
        # Holding rows drive the visible portfolio cards, so use a direct
        # read-only quote snapshot whenever possible. Candidate/ledger prices
        # can be stale or strategy-entry values, especially for new panels.
        quote_snapshot = readonly_quote_snapshot(p.get('code'))
        if quote_snapshot:
            if quote_snapshot.get('currentChangePct') is not None:
                matched['changePct'] = quote_snapshot.get('currentChangePct')
            if quote_snapshot.get('currentPrice'):
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
        p['decisionContract'] = decision_contract_for_item(p, sid, 'holding')
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
        attach_market_references(c)
        apply_market_lead_overlay(c, 'candidate')
        c['technicalDecision'] = c.get('technicalDecision') or (c.get('fundamentals') or {}).get('technicalSignal')
        tech = c.get('technicalDecision') or {}
        if tech.get('state') in ('매물대주의', '전고점대기', '저항거리큼', '돌파우호'):
            note = f"기술구조 {tech.get('state')}: {tech.get('reason')}"
            c['candidateNote'] = f"{c.get('candidateNote')} · {note}" if c.get('candidateNote') and note not in c.get('candidateNote') else (c.get('candidateNote') or note)


def ensure_session_decision_contracts(session, sid):
    """Backfill Decision Contract on every dashboard-visible trading row."""
    if not isinstance(session, dict):
        return
    for arr_name, source in (('topCandidates', 'candidate'), ('buyAlerts', 'buy'), ('sellRecords', 'sellRecord'), ('sellAlerts', 'sell')):
        arr = session.get(arr_name)
        if not isinstance(arr, list):
            continue
        for item in arr:
            if not isinstance(item, dict):
                continue
            if source == 'sellRecord':
                if not isinstance(item.get('exitReviewCategory'), dict):
                    item['exitReviewCategory'] = exit_review_category(item.get('reviewAction') or item.get('status') or '', item.get('reason') or '', item.get('status') or '', item.get('executionStatus') or 'FILLED')
                if not isinstance(item.get('finalIntegratedDecision'), dict):
                    item['finalIntegratedDecision'] = final_integrated_decision(item)
            attach_market_references(item)
            apply_market_lead_overlay(item, source)
            item['decisionContract'] = decision_contract_for_item(item, sid, source)
    pf = session.get('portfolio') if isinstance(session.get('portfolio'), dict) else {}
    positions = pf.get('positions') if isinstance(pf.get('positions'), list) else []
    for item in positions:
        if isinstance(item, dict):
            attach_market_references(item)
            apply_market_lead_overlay(item, 'holding')
            item['decisionContract'] = decision_contract_for_item(item, sid, 'holding')

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
        if private_id in VIRTUAL_LEDGER_IDS:
            s['buyAlerts'] = safe_buy_fills({}, load_fresh(f'virtual_trades/{private_id}.json', {}))
        elif acct.get('positions'):
            # Use one live KIS/account snapshot for all holding cards so the
            # left "buy/holding" card and right sell-review card never show
            # different returnPct/current price for the same open position.
            s['buyAlerts'] = [{
                'code': p.get('code'),
                'name': p.get('name'),
                'status': '보유중',
                'reason': f"{p.get('qty')}주 · 매입 {p.get('entryPrice') or '-'}원 · 현재 {p.get('currentPrice') or '-'}원 · 평가 {p.get('evalAmount')}원 · 손익 {p.get('pnl')}원",
                'returnPct': p.get('returnPct'),
                'holdingPeriod': p.get('holdingPeriod'),
            } for p in acct.get('positions', [])]
        enrich_comparison_fields(s, private_id)
        synthetic_sell = []
        for p in (s.get('portfolio') or {}).get('positions') or []:
            if not isinstance(p, dict) or p.get('holdAction') in (None, '', '보유유지'):
                continue
            ret = n(p.get('returnPct'))
            action = str(p.get('holdAction') or '')
            if private_id == 'jaesang.dailynew.mock' and ret <= -12:
                status = f"(가상계좌) 손절 우선 · 미체결"
                reason = f"보유 {p.get('qty') or '-'}주 · 체결 0주 · 매일신규 중대 손실 {ret:.2f}%: 회복 기대가 아니라 청산 우선 구간 · {p.get('holdReason') or ''}"
            elif '손절' in action and ret <= -8:
                status = f"(가상계좌) 손절 우선 · 미체결"
                reason = f"보유 {p.get('qty') or '-'}주 · 체결 0주 · 손절 기준 도달 {ret:.2f}% · {p.get('holdReason') or ''}"
            else:
                status = f"(가상계좌) 매도 검토 · 미체결"
                reason = f"보유 {p.get('qty') or '-'}주 · 실제 매도 미체결 · 검토수량 미정 · {p.get('holdReason') or ''}"
            row = {
                'code': p.get('code'),
                'name': p.get('name'),
                'status': status,
                'reason': reason,
                'returnPct': p.get('returnPct'),
                'pnl': p.get('pnl'),
                'heldQty': p.get('qty'),
                'sellQty': None,
                'executedQty': 0,
                'executionStatus': 'REVIEW_ONLY_NOT_EXECUTED',
                'accountType': '가상계좌',
                'executionSource': 'NONE',
                'reviewAction': p.get('holdAction'),
                'exitReviewCategory': exit_review_category(p.get('holdAction'), reason, status, 'REVIEW_ONLY_NOT_EXECUTED'),
                'fundamentals': p.get('fundamentals') or public_fundamentals(p.get('code')),
            }
            row['finalIntegratedDecision'] = final_integrated_decision(row)
            row['decisionContract'] = decision_contract_for_item(row, private_id, 'sell')
            synthetic_sell.append(row)
        if synthetic_sell:
            existing_records = s.get('sellRecords') if isinstance(s.get('sellRecords'), list) else []
            s['sellRecords'] = existing_records
            s['sellAlerts'] = synthetic_sell
        reconcile_portfolio_from_positions(s)
        sync_holding_alerts_from_positions(s)
        ensure_session_decision_contracts(s, private_id)
    else:
        s['portfolio'] = {'capital': None, 'evalAmount': None, 'pnl': None, 'returnPct': None, 'positionCount': (s.get('performance') or {}).get('positionCount')}
    if private_id in VIRTUAL_LEDGER_IDS:
        # New panels may not have runtime yet; still show initialized status
        if s['status']=='NO_DATA': s['status']='INITIALIZED'
    if not acct:
        enrich_comparison_fields(s, private_id)
        ensure_session_decision_contracts(s, private_id)
    s.pop('runtimeId', None)
    s.pop('id', None)

benchmark = benchmark_snapshot()
kodex_benchmark = kodex200_snapshot()
etf_holdings = etf_holdings_snapshot()
etf_theme_follow = etf_theme_follow_snapshot()
market_regime = market_regime_snapshot(benchmark, kodex_benchmark)
apply_market_regime_to_sessions(sessions, market_regime)
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
history = backfill_market_return_arrays(forward_fill_history(history), sessions)
history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
survival_ledger = update_survival_ledger(sessions, market_regime, point['ts'])
survival_review = survival_review_from_ledger(survival_ledger, point['ts'])
summary['survivalScore'] = survival_review.get('survivalScore')
summary['survivalReviewReadyCount'] = survival_review.get('reviewReadyCount')
summary['survivalHighRiskCount'] = survival_review.get('highRiskCount')

theme_regime = theme_regime_snapshot(point['ts'])
data={'generatedAt': point['ts'], 'summary':summary, 'marketRegime': market_regime, 'themeRegime': theme_regime, 'survivalReview': survival_review, 'benchmark':benchmark, 'kodexBenchmark':kodex_benchmark, 'etfHoldings': etf_holdings, 'etfThemeFollow': etf_theme_follow, 'sessions':sessions, 'history':history, 'notice':'Dashboard reset; previous metrics are not inherited.'}
split_stock_detail_files(data)
OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(OUT)
