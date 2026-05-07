const fmt = new Intl.NumberFormat('ko-KR');
const pct = v => v === null || v === undefined || Number.isNaN(Number(v)) ? '-' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
const money = v => v === null || v === undefined || Number.isNaN(Number(v)) ? '-' : `${fmt.format(Math.round(Number(v)))}원`;
const esc = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const qs = new URLSearchParams(location.search);
const code = String(qs.get('code') || '').padStart(6, '0');

function fetchJson(url) {
  return fetch(url, { cache: 'no-store' }).then(r => {
    if (!r.ok) throw new Error(`${url} HTTP ${r.status}`);
    return r.json();
  });
}

async function firstJson(urls) {
  const errors = [];
  for (const url of urls) {
    try { return await fetchJson(url); } catch (e) { errors.push(e.message); }
  }
  throw new Error(errors.join(' / '));
}

function walkStocks(x, out = []) {
  if (Array.isArray(x)) x.forEach(v => walkStocks(v, out));
  else if (x && typeof x === 'object') {
    if (x.code && x.fundamentals) out.push(x);
    Object.values(x).forEach(v => walkStocks(v, out));
  }
  return out;
}

function uniqContexts(items) {
  const seen = new Set();
  return items.filter(x => {
    const key = `${x.name}|${x.rank}|${x.score}|${x.reason}|${x.returnPct}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 8);
}

function list(items = []) {
  return `<ul>${(items || []).map(x => `<li>${esc(x)}</li>`).join('') || '<li>데이터 대기</li>'}</ul>`;
}

function metric(label, value, note = '') {
  return `<div class="stock-detail-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${note ? `<small>${esc(note)}</small>` : ''}</div>`;
}

function yScale(minP, maxP, top, bottom) {
  return p => top + (maxP - p) / Math.max(1, maxP - minP) * (bottom - top);
}

function renderOhlcv(rows = [], tech = {}) {
  const data = rows.slice(-90);
  if (!data.length) return '<div class="card">일봉 데이터가 없습니다.</div>';
  const w = 980, h = 430, pad = 42, plotBottom = 320, volBottom = 392;
  const support = tech.supportZone || null;
  const resistance = tech.resistanceWall || null;
  const extras = [tech.previousHigh20d, tech.previousHigh60d, support?.from, support?.to, resistance?.from, resistance?.to].map(Number).filter(Number.isFinite);
  const prices = data.flatMap(r => [Number(r.high), Number(r.low)]).filter(Number.isFinite).concat(extras);
  const vols = data.map(r => Number(r.volume || 0));
  const minP = Math.min(...prices), maxP = Math.max(...prices), maxV = Math.max(...vols, 1);
  const y = yScale(minP, maxP, pad, plotBottom);
  const xStep = (w - pad * 2) / data.length;
  const volY = v => volBottom - (v / maxV) * 58;
  const band = (zone, color, label) => {
    if (!zone || !Number.isFinite(Number(zone.from)) || !Number.isFinite(Number(zone.to))) return '';
    const a = Math.min(y(Number(zone.from)), y(Number(zone.to)));
    const b = Math.max(y(Number(zone.from)), y(Number(zone.to)));
    return `<rect x="${pad}" y="${a.toFixed(1)}" width="${w-pad*2}" height="${Math.max(5,b-a).toFixed(1)}" fill="${color}" opacity=".12" />
      <line x1="${pad}" x2="${w-pad}" y1="${a.toFixed(1)}" y2="${a.toFixed(1)}" stroke="${color}" stroke-dasharray="6 5" opacity=".85" />
      <line x1="${pad}" x2="${w-pad}" y1="${b.toFixed(1)}" y2="${b.toFixed(1)}" stroke="${color}" stroke-dasharray="6 5" opacity=".55" />
      <text x="${pad+4}" y="${Math.max(16,a-7).toFixed(1)}" fill="${color}" font-size="14" font-weight="700">${label} ${money(Math.min(zone.from, zone.to))}~${money(Math.max(zone.from, zone.to))}</text>`;
  };
  const line = (price, color, label) => !price ? '' : `<line x1="${pad}" x2="${w-pad}" y1="${y(price).toFixed(1)}" y2="${y(price).toFixed(1)}" stroke="${color}" stroke-dasharray="5 5" /><text x="${w-pad-4}" y="${(y(price)-7).toFixed(1)}" text-anchor="end" fill="${color}" font-size="13">${label} ${money(price)}</text>`;
  const candles = data.map((r, i) => {
    const open=Number(r.open), close=Number(r.close), high=Number(r.high), low=Number(r.low), volume=Number(r.volume||0);
    const x = pad + i * xStep + xStep / 2;
    const up = close >= open;
    const color = up ? '#ff4d4f' : '#3b82f6';
    const top = Math.min(y(open), y(close));
    const bodyH = Math.max(2, Math.abs(y(open)-y(close)));
    const bw = Math.max(3, xStep * .55);
    return `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y(high).toFixed(1)}" y2="${y(low).toFixed(1)}" stroke="${color}" stroke-width="1.3" />
      <rect x="${(x-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${bodyH.toFixed(1)}" rx="1" fill="${color}" />
      <rect x="${(x-bw/2).toFixed(1)}" y="${volY(volume).toFixed(1)}" width="${bw.toFixed(1)}" height="${(volBottom-volY(volume)).toFixed(1)}" fill="${color}" opacity=".25" />`;
  }).join('');
  const last = data[data.length-1];
  return `<svg class="stock-detail-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="상세 일봉 OHLCV 분석 차트">
    <rect x="0" y="0" width="${w}" height="${h}" rx="24" fill="rgba(0,0,0,.16)" />
    <line x1="${pad}" x2="${w-pad}" y1="${plotBottom}" y2="${plotBottom}" stroke="rgba(255,255,255,.15)" />
    ${band(support, '#35d399', '하단 지지')}
    ${band(resistance, '#ff8fab', '상단 매물대')}
    ${line(tech.previousHigh20d, '#ffd166', '20일 전고점')}
    ${line(tech.previousHigh60d, '#c084fc', '60일 고점')}
    ${candles}
    <text x="${pad}" y="24" fill="#8d9ab8" font-size="13">최근 ${data.length}거래일 · 거래량 포함</text>
    <text x="${w-pad}" y="24" text-anchor="end" fill="#dbe7ff" font-size="14">${last.date} · 종가 ${money(last.close)}</text>
    <text x="${pad}" y="414" fill="#8d9ab8" font-size="12">거래량 막대: 돌파 신뢰도와 매물 소화 여부 확인용</text>
  </svg>`;
}

function renderValuation(f = {}) {
  const rows = [
    ['ROE', f.roe, f.peerAverage?.roe, '%', '높을수록 자기자본 수익성이 좋습니다.'],
    ['PBR', f.pbr, f.peerAverage?.pbr, '배', 'ROE 대비 과도한 프리미엄인지 확인합니다.'],
    ['PER', f.per, f.peerAverage?.per, '배', '성장 기대가 가격에 얼마나 반영됐는지 봅니다.'],
  ];
  return `<div class="valuation-bars">${rows.map(([label, val, avg, suffix, note]) => {
    const v = Number(val), a = Number(avg);
    const max = Math.max(Math.abs(v)||0, Math.abs(a)||0, 1);
    return `<div class="valuation-row"><div><b>${label}</b><small>${note}</small></div><div class="valuation-bar-wrap"><span style="width:${Math.min(100, Math.abs(v)/max*100).toFixed(1)}%"></span><em style="width:${Math.min(100, Math.abs(a)/max*100).toFixed(1)}%"></em></div><strong>${Number.isFinite(v)?v.toFixed(2)+suffix:'-'} <small>평균 ${Number.isFinite(a)?a.toFixed(2)+suffix:'-'}</small></strong></div>`;
  }).join('')}</div>`;
}

function scenarioTable(f = {}, rows = []) {
  const tech = f.technicalStructure || {};
  const a = f.expertAnalysis || {};
  return `<div class="scenario-grid">
    <article><h3>상승 확인 조건</h3>${list(a.upsideTriggers)}</article>
    <article><h3>위험 / 방어 기준</h3>${list(a.riskSignals)}</article>
    <article><h3>접근 전략</h3>${list(a.actionPoints)}</article>
    <article><h3>현재 구조 요약</h3>${list([
      `현재가 ${money(tech.currentPrice)}, 20일 전고점 대비 ${pct(tech.distanceToHigh20dPct)}`,
      `60일 고점 대비 ${pct(tech.distanceToHigh60dPct)}, 매물벽 위험 ${tech.volumeWallRisk || '-'}`,
      `분석 기준: ${(a.basis || []).join(' · ')}`
    ])}</article>
  </div>`;
}

function contextBlock(items) {
  if (!items.length) return '';
  return `<section class="card stock-detail-section"><h2>대시보드 내 등장 맥락</h2><div class="stock-context-list">${items.map(x => `<div><strong>${esc(x.name || code)}</strong><span>${x.rank ? `후보 ${x.rank}위` : '보유/관찰'} · 판단점수 ${x.score ?? '-'} · 등락률 ${pct(x.changePct)}</span>${x.reason ? `<small>${esc(x.reason)}</small>` : ''}</div>`).join('')}</div></section>`;
}

function compactNumber(v, suffix = '') {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 100000000) return `${(n/100000000).toFixed(1)}억${suffix}`;
  if (abs >= 10000) return `${(n/10000).toFixed(1)}만${suffix}`;
  return `${fmt.format(Math.round(n))}${suffix}`;
}

function kisRows(f, key) {
  return f?.kisEnrichment?.parts?.[key]?.rows || [];
}

function renderKisSummary(f = {}) {
  const k = f.kisEnrichment || {};
  const s = k.summary || {};
  const signals = s.signals || [];
  return `<section class="card stock-detail-section"><h2>KIS 실사용 보강 데이터</h2>
    <div class="stock-detail-metrics">
      ${metric('최근 실적 기준', s.latestQuarter || '-', `매출성장 ${pct(s.salesGrowthPct)} · 영업익성장 ${pct(s.operatingProfitGrowthPct)}`)}
      ${metric('외국인/기관 5일', `${compactNumber(s.foreignNetBuyAmount5d)} / ${compactNumber(s.institutionNetBuyAmount5d)}`, '순매수대금 기준')}
      ${metric('공매도 비중', s.shortSaleVolumeRatioLatest === undefined ? '-' : `${Number(s.shortSaleVolumeRatioLatest).toFixed(2)}%`, '최근 확인값')}
      ${metric('대차잔고 5일 증감', compactNumber(s.loanBalanceChange5d, '주'), `뉴스·공시 ${s.newsCount ?? 0}건`)}
    </div>
    ${list(signals.length ? signals : ['KIS 보강 데이터 수집 대기'])}
    <p class="stock-modal-note">source: ${esc(k.source || 'K-O-R')} · updated ${esc(k.updatedAt || '-')} · ${esc(f.universeStatus === 'new' ? '신규 종목' : '기존 종목')}</p>
  </section>`;
}

function renderKisTables(f = {}) {
  const income = kisRows(f, 'incomeStatement').slice(0, 4);
  const investor = kisRows(f, 'investorFlow').slice(0, 7);
  const shortSale = kisRows(f, 'shortSale').slice(0, 7);
  const loan = kisRows(f, 'loanBalance').slice(0, 7);
  const news = kisRows(f, 'news').slice(0, 10);
  const incomeLines = income.map(r => `${r.stac_yymm}: 매출 ${compactNumber(r.sale_account)} · 영업익 ${compactNumber(r.op_prfi || r.bsop_prti)} · 순익 ${compactNumber(r.thtr_ntin)}`);
  const investorLines = investor.map(r => `${r.stck_bsop_date}: 외국인 ${compactNumber(r.frgn_ntby_tr_pbmn)} · 기관 ${compactNumber(r.orgn_ntby_tr_pbmn)} · 개인 ${compactNumber(r.prsn_ntby_tr_pbmn)}`);
  const shortLines = shortSale.map(r => `${r.stck_bsop_date}: 공매도 ${compactNumber(r.ssts_cntg_qty, '주')} · 비중 ${r.ssts_vol_rlim ?? '-'}%`);
  const loanLines = loan.map(r => `${r.bsop_date}: 대차증감 ${compactNumber(r.prdy_rmnd_vrss, '주')} · 잔고 ${compactNumber(r.rmnd_stcn, '주')}`);
  const newsLines = news.map(r => `${r.data_dt} ${r.data_tm || ''} · ${r.dorg || ''} · ${r.hts_pbnt_titl_cntt || ''}`);
  return `<section class="card stock-detail-section"><h2>실적·수급·공매도·대차·뉴스 상세</h2>
    <div class="scenario-grid">
      <article><h3>최근 실적</h3>${list(incomeLines)}</article>
      <article><h3>외국인/기관 수급</h3>${list(investorLines)}</article>
      <article><h3>공매도</h3>${list(shortLines)}</article>
      <article><h3>대차잔고</h3>${list(loanLines)}</article>
    </div>
    <h3>최근 뉴스·공시 제목</h3>${list(newsLines)}
  </section>`;
}

function renderDetail(stock, contexts, ohlcv) {
  const f = stock.fundamentals || {};
  const a = f.expertAnalysis || {};
  const tech = f.technicalStructure || {};
  document.title = `${stock.name || code} 상세 분석`;
  document.getElementById('stockTitle').textContent = `${stock.name || '종목'} 상세 분석`;
  document.getElementById('stockUpdated').textContent = `${code} · 데이터 ${f.updatedAt || '-'}`;
  const root = document.getElementById('stockDetailRoot');
  root.innerHTML = `
    <section class="stock-detail-hero card">
      <div><span class="eyebrow">${esc(code)}</span><h2>${esc(stock.name || '종목')}</h2><p>${esc(a.summary || '상세 분석 데이터 대기')}</p></div>
      <div class="stock-score-ring"><strong>${a.score ?? '-'}</strong><span>${esc(a.stance || '분석 대기')}</span></div>
    </section>
    <section class="stock-detail-metrics">
      ${metric('현재가', money(tech.currentPrice), `20일 전고점 대비 ${pct(tech.distanceToHigh20dPct)}`)}
      ${metric('20일 전고점', money(tech.previousHigh20d), tech.breakoutState || '')}
      ${metric('상단 매물대', tech.resistanceWall ? `${money(tech.resistanceWall.from)}~${money(tech.resistanceWall.to)}` : '-', `위험 ${tech.volumeWallRisk || '-'}`)}
      ${metric('하단 지지', tech.supportZone ? `${money(tech.supportZone.from)}~${money(tech.supportZone.to)}` : '-', '종가 이탈 여부 확인')}
    </section>
    <section class="card stock-detail-section"><h2>가격·거래량 구조 분석</h2>${renderOhlcv(ohlcv?.rows || [], tech)}</section>
    <section class="card stock-detail-section"><h2>ROE · PBR · PER 종합 밸류 분석</h2>${renderValuation(f)}${list(f.report)}</section>
    ${renderKisSummary(f)}
    ${renderKisTables(f)}
    <section class="card stock-detail-section"><h2>전문가형 시나리오 분석</h2>${scenarioTable(f)}</section>
    <section class="card stock-detail-section"><h2>핵심 포인트</h2>${list(a.keyPoints)}</section>
    <section class="card stock-detail-section"><h2>추가로 넣으면 좋은 자료</h2>${list(a.additionalDataNeeded)}<p class="stock-modal-note">${esc(a.disclaimer || '자동 분석은 투자 판단 보조자료입니다.')}</p></section>
    ${contextBlock(contexts)}
  `;
}

async function main() {
  if (!/^\d{6}$/.test(code)) throw new Error('종목코드가 없습니다.');
  const [dashboard, ohlcvData] = await Promise.all([
    firstJson(['data/test/dashboard-data.json', 'data/dashboard-data.json']),
    firstJson(['data/test/fundamentals/daily_ohlcv_latest.json', 'data/fundamentals/daily_ohlcv_latest.json']),
  ]);
  const matches = walkStocks(dashboard).filter(x => String(x.code).padStart(6,'0') === code);
  if (!matches.length) throw new Error(`${code} 종목 분석 데이터가 없습니다.`);
  renderDetail(matches[0], uniqContexts(matches), ohlcvData.items?.[code]);
}

main().catch(err => {
  document.getElementById('stockDetailRoot').innerHTML = `<section class="card"><h2>데이터 로드 실패</h2><p>${esc(err.message)}</p><p><a class="stock-back-link" href="./">대시보드로 돌아가기</a></p></section>`;
});
