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

function list(items = [], emptyText = '데이터 대기') {
  return `<ul>${(items || []).map(x => `<li>${esc(x)}</li>`).join('') || `<li>${esc(emptyText)}</li>`}</ul>`;
}

function htmlList(items = [], emptyText = '데이터 대기') {
  return `<ul>${(items || []).map(x => `<li>${x}</li>`).join('') || `<li>${esc(emptyText)}</li>`}</ul>`;
}

function newsSearchQuery(row = {}) {
  const title = String(row.hts_pbnt_titl_cntt || '').trim();
  const stock = String(row.kor_isnm1 || row.relatedNames?.[0] || code).trim();
  if (!title) return stock;
  if (stock && title.includes(stock)) return title;
  return [stock, title].filter(Boolean).join(' ');
}

function newsSearchUrl(row = {}) {
  const query = row.searchQuery || newsSearchQuery(row);
  return `https://search.naver.com/search.naver?where=news&query=${encodeURIComponent(query)}`;
}

function disclosureSearchUrl(row = {}) {
  if (row.rcept_no) return `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${encodeURIComponent(row.rcept_no)}`;
  const title = row.hts_pbnt_titl_cntt || '';
  const stock = row.kor_isnm1 || row.relatedNames?.[0] || code;
  const query = [stock, title].filter(Boolean).join(' ');
  return `https://dart.fss.or.kr/dsab007/search.ax?textCrpNm=${encodeURIComponent(query)}`;
}

function isDisclosureRow(row = {}) {
  if (row.kind === 'dart' || row.rcept_no || row.dorg === 'DART') return true;
  const text = `${row.dorg || ''} ${row.hts_pbnt_titl_cntt || ''}`;
  return /공시|거래소|IR|보고서|증권신고|사업보고|분기보고|반기보고/.test(text);
}

function renderNewsLink(row = {}) {
  const title = row.hts_pbnt_titl_cntt || '제목 없음';
  const source = row.dorg || '-';
  const time = `${row.data_dt || ''} ${row.data_tm || ''}`.trim();
  const primary = row.url || row.link || row.news_url || row.hts_url || newsSearchUrl(row);
  const disclosure = isDisclosureRow(row) && row.kind !== 'dart' ? `<a href="${disclosureSearchUrl(row)}" target="_blank" rel="noopener noreferrer">DART</a>` : '';
  const rel = row.relevance ? `<small class="news-relevance">${esc(row.relevance)}</small>` : '';
  return `<span>${esc(time)} · ${esc(source)} · <a href="${primary}" target="_blank" rel="noopener noreferrer">${esc(title)}</a></span>${disclosure ? ` <small>${disclosure}</small>` : ''}${rel ? ` ${rel}` : ''}`;
}

function tooltipAttr(value) {
  return esc(value).replaceAll('\n', '&#10;');
}

function metric(label, value, note = '') {
  return `<div class="stock-detail-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${note ? `<small>${esc(note)}</small>` : ''}</div>`;
}

function yScale(minP, maxP, top, bottom) {
  return p => top + (maxP - p) / Math.max(1, maxP - minP) * (bottom - top);
}

function normalizeDateKey(value) {
  return String(value || '').replace(/[^0-9]/g, '').slice(0, 8);
}

function chartRowsWithIntraday(rows = [], intraday = null) {
  const isTradingRow = r => Number(r?.volume || 0) > 0 && Number(r?.open || 0) > 0 && Number(r?.high || 0) > 0 && Number(r?.low || 0) > 0 && Number(r?.close || 0) > 0;
  const out = rows.filter(isTradingRow).slice(-90);
  if (!intraday || !intraday.date || !intraday.close) return out;
  const key = normalizeDateKey(intraday.date);
  const row = {
    date: key || intraday.date,
    open: Number(intraday.open || intraday.close),
    high: Number(intraday.high || intraday.close),
    low: Number(intraday.low || intraday.close),
    close: Number(intraday.close),
    volume: Number(intraday.volume || 0),
    intraday: true,
    updatedAt: intraday.updatedAt,
    source: intraday.source,
  };
  const idx = out.findIndex(r => normalizeDateKey(r.date) === key);
  if (idx >= 0) out[idx] = { ...out[idx], ...row };
  else out.push(row);
  return out.slice(-90);
}

function candleTooltip(r, open, high, low, close, volume) {
  const label = r.intraday ? `${r.date || '-'} 오늘 업데이트 기준` : `${r.date || '-'} 거래 정보`;
  return [
    label,
    `시가 ${money(open)} · 고가 ${money(high)}`,
    `저가 ${money(low)} · 종가 ${money(close)}`,
    `거래량 ${compactNumber(volume, '주')}`,
    r.updatedAt ? `업데이트 ${String(r.updatedAt).replace('T', ' ').slice(0, 16)}` : null,
  ].filter(Boolean).join('\n');
}

function renderOhlcv(rows = [], tech = {}, intraday = null) {
  const data = chartRowsWithIntraday(rows, intraday);
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
    const tip = candleTooltip(r, open, high, low, close, volume);
    return `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y(high).toFixed(1)}" y2="${y(low).toFixed(1)}" stroke="${color}" stroke-width="1.3" />
      <rect x="${(x-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${bodyH.toFixed(1)}" rx="1" fill="${color}" />
      <rect class="stock-candle-hit" x="${(x-xStep/2).toFixed(1)}" y="${pad}" width="${Math.max(5,xStep).toFixed(1)}" height="${plotBottom-pad}" fill="transparent" data-tooltip="${tooltipAttr(tip)}" />
      <rect x="${(x-bw/2).toFixed(1)}" y="${volY(volume).toFixed(1)}" width="${bw.toFixed(1)}" height="${(volBottom-volY(volume)).toFixed(1)}" fill="${color}" opacity=".25" />
      <rect class="stock-volume-hit" x="${(x-xStep/2).toFixed(1)}" y="${(volBottom-68).toFixed(1)}" width="${Math.max(5,xStep).toFixed(1)}" height="78" fill="transparent" data-tooltip="${tooltipAttr(tip)}" />`;
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

function bindStockChartTooltip() {
  let tooltip = document.querySelector('.stock-chart-tooltip');
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.className = 'stock-chart-tooltip';
    document.body.appendChild(tooltip);
  }
  const show = (event, text) => {
    tooltip.innerHTML = esc(text).split('\n').map((line, idx) => idx ? `<span>${line}</span>` : `<strong>${line}</strong>`).join('');
    tooltip.classList.add('visible');
    const pad = 14;
    const rect = tooltip.getBoundingClientRect();
    let left = event.clientX + pad;
    let top = event.clientY + pad;
    if (left + rect.width > window.innerWidth - 8) left = event.clientX - rect.width - pad;
    if (top + rect.height > window.innerHeight - 8) top = event.clientY - rect.height - pad;
    tooltip.style.left = `${Math.max(8, left)}px`;
    tooltip.style.top = `${Math.max(8, top)}px`;
  };
  document.querySelectorAll('.stock-volume-hit, .stock-candle-hit').forEach(el => {
    el.addEventListener('pointerenter', event => show(event, el.dataset.tooltip || ''));
    el.addEventListener('pointermove', event => show(event, el.dataset.tooltip || ''));
    el.addEventListener('pointerleave', () => tooltip.classList.remove('visible'));
  });
}

function renderRealtimeCandle(f = {}) {
  const c = f.intradayCandle || null;
  if (!c) return '';
  return `<section id="tab-today" class="card stock-detail-section realtime-candle-section"><h2>오늘 업데이트 기준 캔들</h2>
    <div class="stock-detail-metrics">
      ${metric('업데이트', String(c.updatedAt || '-').replace('T', ' ').slice(0, 16), c.source || '장중 시세')}
      ${metric('시가 / 고가', `${money(c.open)} / ${money(c.high)}`, '오늘 장중')}
      ${metric('저가 / 현재', `${money(c.low)} / ${money(c.close)}`, c.changePct == null ? '' : `전일대비 ${pct(c.changePct)}`)}
      ${metric('거래량', compactNumber(c.volume, '주'), c.tradingValue ? `거래대금 ${compactNumber(c.tradingValue)}` : '')}
    </div>
  </section>`;
}

function renderNxtQuote(f = {}) {
  const q = f.nxtQuote || null;
  if (!q || q.price === null || q.price === undefined) return '';
  const krx = Number(f?.technicalStructure?.currentPrice || f?.intradayCandle?.close || 0);
  const nxt = Number(q.price || 0);
  const diff = krx && nxt ? nxt - krx : null;
  const session = q.session === 'AFTER_MARKET' ? '장후' : (q.session === 'PRE_MARKET' ? '장전' : '장외');
  const time = String(q.localTradedAt || '').replace('T', ' ').slice(0, 16);
  return `<section id="tab-nxt" class="card stock-detail-section nxt-quote-section"><h2>NXT 참고 시세</h2>
    <div class="stock-detail-metrics">
      ${metric(`NXT ${session}`, money(q.price), q.changePct == null ? '' : `전일대비 ${pct(q.changePct)}`)}
      ${metric('KRX 종가 기준', money(krx || null), '평가손익·일봉 기준')}
      ${metric('KRX 대비 차이', diff === null ? '-' : `${diff >= 0 ? '+' : '-'}${money(Math.abs(diff))}`, '참고용, 공식 종가 아님')}
      ${metric('업데이트', time || '-', q.status || 'NXT')}
    </div>
    <p class="stock-modal-note">NXT 가격은 장전/장후 참고값입니다. 대시보드 평가손익과 기술분석 기준가는 KRX 종가를 유지합니다.</p>
  </section>`;
}

function renderStockFutureQuote(f = {}) {
  const q = f.stockFutureQuote || null;
  if (!q || q.price === null || q.price === undefined) return '';
  const spread = q.spotSpreadPct === null || q.spotSpreadPct === undefined ? '-' : `${q.spotSpreadPct >= 0 ? '+' : ''}${Number(q.spotSpreadPct).toFixed(2)}%`;
  const relative = q.relativeStrengthPct === null || q.relativeStrengthPct === undefined ? '-' : `${q.relativeStrengthPct >= 0 ? '+' : ''}${Number(q.relativeStrengthPct).toFixed(2)}%p`;
  const expiry = q.expiryDate ? String(q.expiryDate).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3') : (q.expiryMonth || '-');
  return `<section id="tab-future" class="card stock-detail-section future-quote-section"><h2>주식선물 신호</h2>
    <div class="stock-detail-metrics">
      ${metric(q.signal || '선물 추적', money(q.price), q.changePct == null ? '' : `전일대비 ${pct(q.changePct)}`)}
      ${metric('현물 대비 괴리', spread, q.spotSpread === null || q.spotSpread === undefined ? '' : `차이 ${money(q.spotSpread)}`)}
      ${metric('현물 대비 상대강도', relative, '선물 등락률 - 현물 등락률')}
      ${metric('거래량 / 미결제', `${compactNumber(q.volume, '계약')} / ${compactNumber(q.openInterest, '계약')}`, q.openInterestChange == null ? '' : `미결제 증감 ${compactNumber(q.openInterestChange, '계약')}`)}
      ${metric('만기', expiry, q.remainingDays == null ? '' : `잔존 ${q.remainingDays}일`)}
      ${metric('선물 코드', q.futureCode || '-', q.futureName || 'KRX 주식선물')}
    </div>
    ${renderStockFutureInterpretation(q, f)}
    ${renderStockFutureTrend(q.trend || [])}
    <p class="stock-modal-note">주식선물은 선행/심리 참고 지표입니다. 대시보드 평가손익과 기술분석 기준가는 기존처럼 KRX 현물 기준을 유지합니다.</p>
  </section>`;
}

function stockFutureInterpretation(q = {}, f = {}) {
  const spread = q.spotSpreadPct == null ? null : Number(q.spotSpreadPct);
  const rel = q.relativeStrengthPct == null ? null : Number(q.relativeStrengthPct);
  const futChg = q.changePct == null ? null : Number(q.changePct);
  const oiChg = q.openInterestChange == null ? null : Number(q.openInterestChange);
  const vol = q.volume == null ? null : Number(q.volume);
  const techState = f?.technicalSignal?.state || f?.technicalStructure?.breakoutState || '';
  let stance = '중립 관찰';
  let impact = '현물 방향성 확인 전까지는 선물 신호만으로 판단하지 않습니다.';
  let confidence = '낮음';
  const reasons = [];
  if (spread !== null) reasons.push(`현물 대비 괴리율 ${spread >= 0 ? '+' : ''}${spread.toFixed(2)}%`);
  if (rel !== null) reasons.push(`상대강도 ${rel >= 0 ? '+' : ''}${rel.toFixed(2)}%p`);
  if (vol !== null) reasons.push(`선물 거래량 ${compactNumber(vol, '계약')}`);
  if (oiChg !== null) reasons.push(`미결제 증감 ${compactNumber(oiChg, '계약')}`);

  if (rel !== null && rel >= 1.0 && spread !== null && spread >= 0) {
    stance = '선물 선행 강세';
    impact = '현물보다 선물이 먼저 강하게 반응하고 있어 시초/장중 반등 또는 상승 지속 신호로 볼 수 있습니다.';
    confidence = vol && vol >= 1000 ? '보통' : '낮음';
  } else if (rel !== null && rel <= -1.0 && spread !== null && spread <= 0) {
    stance = '선물 선행 약세';
    impact = '선물이 현물보다 약하게 움직여 단기 헤지/매도 압력 가능성이 있습니다. 현물 상승 시 추격 신뢰도는 낮게 봅니다.';
    confidence = vol && vol >= 1000 ? '보통' : '낮음';
  } else if (spread !== null && spread >= 0.5) {
    stance = '현물 대비 프리미엄';
    impact = '선물이 현물보다 높은 가격을 유지해 단기 기대감은 있으나, 상대강도 확인이 필요합니다.';
    confidence = '낮음';
  } else if (spread !== null && spread <= -0.5) {
    stance = '현물 대비 디스카운트';
    impact = '선물이 현물보다 낮게 거래되어 단기 부담 또는 헤지 수요를 의심할 수 있습니다.';
    confidence = '낮음';
  }

  if (oiChg !== null && futChg !== null) {
    if (futChg > 0 && oiChg > 0) {
      reasons.push('가격 상승 + 미결제 증가: 신규 롱 유입 가능성');
      if (stance.includes('강세')) confidence = '높음';
    } else if (futChg < 0 && oiChg > 0) {
      reasons.push('가격 하락 + 미결제 증가: 신규 숏/헤지 가능성');
      if (stance.includes('약세')) confidence = '높음';
    } else if (futChg > 0 && oiChg < 0) {
      reasons.push('가격 상승 + 미결제 감소: 숏커버 성격 가능');
    } else if (futChg < 0 && oiChg < 0) {
      reasons.push('가격 하락 + 미결제 감소: 포지션 청산 성격 가능');
    }
  }
  if (techState) reasons.push(`현물 기술구조: ${techState}`);
  if (f?.technicalSignal?.state === '돌파우호' && stance.includes('강세')) {
    impact = '현물 기술구조와 선물 강세가 같은 방향입니다. 돌파/안착 확인 시 상승 신뢰도가 올라갑니다.';
    confidence = confidence === '높음' ? '높음' : '보통';
  } else if (f?.technicalSignal?.state === '매물대주의' && stance.includes('강세')) {
    impact = '선물은 강하지만 현물 상단 매물대가 가까워, 돌파 확인 전 추격은 조심하는 편이 좋습니다.';
  }
  return { stance, impact, confidence, reasons: reasons.slice(0, 6) };
}

function renderStockFutureInterpretation(q = {}, f = {}) {
  const a = stockFutureInterpretation(q, f);
  const tone = a.stance.includes('강세') ? 'up' : (a.stance.includes('약세') || a.stance.includes('디스카운트') ? 'down' : '');
  return `<div class="future-interpretation ${tone}">
    <div><span>선물 기반 해석</span><strong>${esc(a.stance)}</strong><em>신뢰도 ${esc(a.confidence)}</em></div>
    <p>${esc(a.impact)}</p>
    ${list(a.reasons)}
  </div>`;
}

function renderStockFutureTrend(rows = []) {
  const data = (rows || []).filter(r => r && Number.isFinite(Number(r.price))).slice(-40);
  if (data.length < 2) return '<p class="stock-modal-note">선물 추이 스냅샷은 다음 fast update부터 누적됩니다.</p>';
  const w = 720, h = 190, pad = 28;
  const prices = data.map(r => Number(r.price));
  const spreads = data.map(r => Number(r.spotSpreadPct)).filter(Number.isFinite);
  const minP = Math.min(...prices), maxP = Math.max(...prices);
  const y = p => pad + (maxP - p) / Math.max(1, maxP - minP) * (h - pad * 2);
  const x = i => pad + i / Math.max(1, data.length - 1) * (w - pad * 2);
  const points = data.map((r, i) => `${x(i).toFixed(1)},${y(Number(r.price)).toFixed(1)}`).join(' ');
  const last = data[data.length - 1];
  const first = data[0];
  const priceMove = Number(last.price) - Number(first.price);
  const spreadText = spreads.length ? `괴리율 ${spreads[0].toFixed(2)}% → ${spreads[spreads.length - 1].toFixed(2)}%` : '괴리율 누적 대기';
  return `<div class="future-trend-box">
    <div class="future-trend-head"><strong>선물 스냅샷 추이</strong><span>${esc(String(first.ts || '').slice(11,16))} → ${esc(String(last.ts || '').slice(11,16))} · ${priceMove >= 0 ? '+' : '-'}${money(Math.abs(priceMove))} · ${esc(spreadText)}</span></div>
    <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="주식선물 가격 추이">
      <rect x="0" y="0" width="${w}" height="${h}" rx="18" fill="rgba(0,0,0,.16)" />
      <polyline points="${points}" fill="none" stroke="#79a7ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
      ${data.map((r, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(Number(r.price)).toFixed(1)}" r="2.4" fill="#eaf0ff"><title>${esc(String(r.ts || '').replace('T',' '))} · ${money(r.price)} · 괴리 ${r.spotSpreadPct ?? '-'}%</title></circle>`).join('')}
      <text x="${pad}" y="22" fill="#8d9ab8" font-size="12">최근 ${data.length}회 fast update</text>
      <text x="${w-pad}" y="22" text-anchor="end" fill="#dbe7ff" font-size="12">${money(last.price)} · ${esc(last.signal || '')}</text>
    </svg>
  </div>`;
}

function renderRiseTiming(f = {}, rows = []) {
  const tech = f.technicalStructure || {};
  const analysis = f.expertAnalysis || {};
  const data = (rows || []).slice(-30);
  const last = data[data.length - 1] || {};
  const recent20 = data.slice(-20);
  const avgVol20 = recent20.length ? recent20.reduce((sum, r) => sum + Number(r.volume || 0), 0) / recent20.length : 0;
  const lastVol = Number(last.volume || 0);
  const volRatio = avgVol20 ? lastVol / avgVol20 : null;
  const current = Number(tech.currentPrice || last.close || 0);
  const dist20 = tech.distanceToHigh20dPct == null ? null : Number(tech.distanceToHigh20dPct);
  const dist60 = tech.distanceToHigh60dPct == null ? null : Number(tech.distanceToHigh60dPct);
  const wall = tech.volumeWallRisk || '-';
  const breakout = tech.breakoutState || '-';
  const support = tech.supportZone || null;
  const resistance = tech.resistanceWall || null;
  let phase = '대기';
  let horizon = '조건 확인 후';
  let stance = '무리한 선진입보다 확인 매수 우선';
  if (dist20 !== null && dist20 >= 0 && wall !== '높음' && (volRatio === null || volRatio >= 1.0)) {
    phase = '돌파 확인 구간';
    horizon = '당일~3거래일';
    stance = '종가가 전고점 위에서 버티고 거래량이 유지되면 상승 재개 가능성이 큼';
  } else if (dist20 !== null && dist20 >= -3 && dist20 < 0) {
    phase = '임박/관찰 구간';
    horizon = '1~5거래일';
    stance = '전고점 돌파 전까지는 추격보다 돌파 확인 대기';
  } else if (support && current && Number(support.from) <= current && current <= Number(support.to) * 1.04) {
    phase = '지지 확인 구간';
    horizon = '반등 확인 후';
    stance = '지지선 이탈 없이 양봉/거래량 회복이 나오면 1차 진입 후보';
  } else if (wall === '높음') {
    phase = '매물 소화 대기';
    horizon = '저항 돌파 후';
    stance = '상단 매물대 통과 전에는 상승 시점보다 리스크 관리가 우선';
  }
  const triggerLines = [
    tech.previousHigh20d ? `20일 전고점 ${money(tech.previousHigh20d)} 돌파/안착` : null,
    resistance ? `상단 매물대 ${money(resistance.from)}~${money(resistance.to)} 소화` : null,
    volRatio !== null ? `거래량: 최근 20일 평균 대비 ${volRatio.toFixed(1)}배 이상 유지` : '거래량 평균 데이터 보강 대기',
    ...(analysis.upsideTriggers || []).slice(0, 2),
  ].filter(Boolean);
  const riskLines = [
    support ? `지지선 ${money(support.from)}~${money(support.to)} 종가 이탈 시 시점 판단 취소` : null,
    dist60 !== null ? `60일 고점 대비 ${pct(dist60)} 위치` : null,
    wall !== '-' ? `매물벽 위험 ${wall}` : null,
  ].filter(Boolean);
  return `<section id="tab-timing" class="card stock-detail-section rise-timing-section"><h2>오를 시점 체크</h2>
    <div class="rise-timing-grid">
      ${metric('현재 단계', phase, breakout)}
      ${metric('예상 관찰 시점', horizon, stance)}
      ${metric('전고점 거리', dist20 === null ? '-' : pct(dist20), tech.previousHigh20d ? `20일 전고점 ${money(tech.previousHigh20d)}` : '')}
      ${metric('거래량 상태', volRatio === null ? '-' : `${volRatio.toFixed(1)}배`, avgVol20 ? `20일 평균 ${compactNumber(avgVol20, '주')}` : '')}
    </div>
    <div class="scenario-grid">
      <article><h3>상승 시점 신호</h3>${list(triggerLines)}</article>
      <article><h3>시점 무효/주의</h3>${list(riskLines)}</article>
    </div>
  </section>`;
}

function beginnerVolumeText(rows = []) {
  const data = (rows || []).slice(-30);
  const last = data[data.length - 1] || {};
  const recent20 = data.slice(-20);
  const avgVol20 = recent20.length ? recent20.reduce((sum, r) => sum + Number(r.volume || 0), 0) / recent20.length : 0;
  const lastVol = Number(last.volume || 0);
  const ratio = avgVol20 ? lastVol / avgVol20 : null;
  if (ratio === null) return { ratio, line: '거래량 평균 데이터가 부족해서 아직 판단 보류입니다.', tone: '' };
  if (ratio >= 1.5) return { ratio, line: `거래량이 평소보다 ${ratio.toFixed(1)}배 많습니다. 가격이 같이 오르면 관심이 강하게 붙은 신호입니다.`, tone: 'up' };
  if (ratio >= 0.8) return { ratio, line: `거래량은 평소와 비슷한 편입니다. 방향 확인에는 추가 캔들이 더 필요합니다.`, tone: '' };
  return { ratio, line: `거래량이 평소의 ${ratio.toFixed(1)}배 수준으로 약합니다. 오르더라도 힘이 부족할 수 있습니다.`, tone: 'down' };
}

function beginnerGuide(f = {}, rows = []) {
  const a = f.expertAnalysis || {};
  const survival = a.survival || {};
  const tech = f.technicalStructure || {};
  const kis = f.kisEnrichment?.summary || {};
  const future = f.stockFutureQuote ? stockFutureInterpretation(f.stockFutureQuote, f) : null;
  const volume = beginnerVolumeText(rows);
  const score = Number(a.score);
  const dist20 = tech.distanceToHigh20dPct == null ? null : Number(tech.distanceToHigh20dPct);
  const wall = tech.volumeWallRisk || '';
  const support = tech.supportZone || null;
  const resistance = tech.resistanceWall || null;
  const current = Number(tech.currentPrice || f.intradayCandle?.close || rows?.[rows.length - 1]?.close || 0);
  const shortRatio = kis.shortSaleVolumeRatioLatest == null ? null : Number(kis.shortSaleVolumeRatioLatest);
  const loan5 = kis.loanBalanceChange5d == null ? null : Number(kis.loanBalanceChange5d);
  const frgn5 = kis.foreignNetBuyAmount5d == null ? null : Number(kis.foreignNetBuyAmount5d);
  const orgn5 = kis.institutionNetBuyAmount5d == null ? null : Number(kis.institutionNetBuyAmount5d);
  const nxt = f.nxtQuote || null;
  const peer = f.peerGrowthMargin || null;
  const targetPeer = peer?.target || {};
  const peerAvg = peer?.peerAverage || {};
  const regime = survival.marketRegime || f.marketRegime || null;
  const pos = survival.positionGuide || {};
  const invalid = survival.invalidationRules || [];

  let headline = '지금은 기다리면서 확인할 자리입니다.';
  let tone = 'wait';
  if (Number.isFinite(score) && score >= 68 && dist20 !== null && dist20 >= -3 && wall !== '높음') {
    headline = '상승 쪽 가능성은 있지만, 돌파 확인이 먼저입니다.';
    tone = 'up';
  } else if ((Number.isFinite(score) && score <= 45) || wall === '높음') {
    headline = '바로 따라가기보다 눌림이나 저항 돌파를 기다리는 편이 안전합니다.';
    tone = 'down';
  }
  if (future?.stance?.includes('약세') || future?.stance?.includes('디스카운트')) {
    headline = '선물이 약해서 단기 추격은 조심하는 편이 좋습니다.';
    tone = 'down';
  } else if (future?.stance?.includes('강세') && tone !== 'down') {
    headline = '선물은 우호적입니다. 다만 현물 가격 확인이 필요합니다.';
    tone = 'up';
  }
  if (survival.actionState === '매수 보류' || survival.actionState === '관망 우선') {
    headline = `${survival.actionState}: ${survival.positionGuide?.plain || '확신이 낮으면 쉬는 것이 전략입니다.'}`;
    tone = survival.actionState === '매수 보류' ? 'down' : 'wait';
  } else if (survival.actionState) {
    headline = `${survival.actionState}: ${survival.positionGuide?.plain || headline}`;
  }

  const waitChecks = [];
  if (tech.previousHigh20d) {
    const high = Number(tech.previousHigh20d);
    const ok = current >= high;
    waitChecks.push({
      status: ok ? 'O' : 'X',
      label: `${money(high)} 근처를 뚫고 종가가 버티는지`,
      now: current ? `현재 ${money(current)} · 기준까지 ${pct((current - high) / high * 100)}` : '현재가 데이터 대기',
      explain: ok ? '현재 기준으로는 전고점 위에 있습니다. 오늘 종가도 이 위에서 끝나면 돌파 신뢰도가 올라갑니다.' : '아직 전고점 아래라 “뚫었다”고 보기 어렵습니다. 이 가격 위에서 마감하는지 기다리는 게 안전합니다.',
    });
  }
  if (resistance) {
    const from = Number(resistance.from), to = Number(resistance.to);
    const status = current >= to ? 'O' : (current >= from ? '△' : 'X');
    waitChecks.push({
      status,
      label: `${money(from)}~${money(to)} 매물대를 넘기는지`,
      now: current ? `현재 ${money(current)}` : '현재가 데이터 대기',
      explain: status === 'O' ? '상단 매물대를 위로 넘어선 상태입니다. 다시 밀리지 않고 버티는지가 다음 확인 포인트입니다.' : (status === '△' ? '매물대 안에 들어와 있습니다. 여기서는 위아래 흔들림이 커질 수 있어 완전히 넘기는지 봐야 합니다.' : '아직 매물대 아래입니다. 위에 물린 매물이 남아 있어 상승할 때 막힐 수 있습니다.'),
    });
  }
  if (volume.ratio !== null) {
    const status = volume.ratio >= 1.5 ? 'O' : (volume.ratio >= 1.0 ? '△' : 'X');
    waitChecks.push({
      status,
      label: '거래량이 20일 평균 대비 1.0~1.5배 이상 붙는지',
      now: `현재 ${volume.ratio.toFixed(1)}배`,
      explain: status === 'O' ? '평소보다 거래가 확실히 많습니다. 가격 상승과 같이 나오면 매수 관심이 붙은 신호로 볼 수 있습니다.' : (status === '△' ? '평균 수준의 거래량입니다. 방향은 보이지만 강한 확신까지는 조금 부족합니다.' : '거래량이 부족합니다. 가격이 올라가도 따라붙는 힘이 약할 수 있습니다.'),
    });
  }
  if (!waitChecks.length && support) {
    const from = Number(support.from), to = Number(support.to);
    const status = current >= from && current <= to ? '△' : (current > to ? 'O' : 'X');
    waitChecks.push({
      status,
      label: `${money(from)}~${money(to)} 지지선에서 반등하는지`,
      now: current ? `현재 ${money(current)}` : '현재가 데이터 대기',
      explain: status === 'X' ? '지지선 아래라 조심해야 합니다. 다시 지지선 위로 올라오는지 확인이 필요합니다.' : '지지선 근처 또는 위에 있습니다. 여기서 밀리지 않고 반등하는지가 중요합니다.',
    });
  }

  const allChecks = [];
  if (current) {
    allChecks.push({
      status: dist20 !== null && dist20 >= 0 ? 'O' : (dist20 !== null && dist20 >= -3 ? '△' : 'X'),
      label: '현재가 위치',
      now: `${money(current)} · 20일 전고점 대비 ${dist20 === null ? '-' : pct(dist20)}`,
      explain: dist20 === null ? '전고점 거리 데이터가 부족합니다.' : (dist20 >= 0 ? '전고점 위라 상승 흐름이 유지되는지 볼 자리입니다.' : (dist20 >= -3 ? '전고점에 가까워졌습니다. 돌파 여부를 확인할 구간입니다.' : '아직 전고점과 거리가 있어 성급한 추격보다는 기다림이 낫습니다.')),
    });
  }
  if (support) {
    const from = Number(support.from), to = Number(support.to);
    const status = current >= from ? 'O' : 'X';
    allChecks.push({
      status,
      label: '하단 지지선 안전 여부',
      now: `${money(from)}~${money(to)} · 현재 ${current ? money(current) : '-'}`,
      explain: status === 'O' ? '현재가가 지지선 위에 있어 아직 방어선은 살아 있습니다.' : '지지선 아래로 내려와 있으면 손실 방어를 먼저 생각해야 합니다.',
    });
  }
  if (resistance) {
    const from = Number(resistance.from), to = Number(resistance.to);
    const status = current >= to ? 'O' : (current >= from ? '△' : 'X');
    allChecks.push({
      status,
      label: '상단 매물대 부담',
      now: `${money(from)}~${money(to)} · 위험 ${wall || '-'}`,
      explain: status === 'O' ? '매물대를 넘어선 상태라 버티는지만 보면 됩니다.' : (status === '△' ? '매물대 안이라 흔들릴 수 있습니다. 완전히 넘는지 확인하세요.' : '아직 위에 매물대가 남아 있어 상승할 때 막힐 수 있습니다.'),
    });
  }
  if (future) {
    const status = future.stance.includes('강세') ? 'O' : (future.stance.includes('약세') || future.stance.includes('디스카운트') ? 'X' : '△');
    allChecks.push({
      status,
      label: '주식선물 분위기',
      now: future.stance,
      explain: future.impact || '선물은 단기 심리 참고 자료입니다. 현물 가격과 같이 봐야 합니다.',
    });
  }
  if (nxt && nxt.price != null) {
    const krx = Number(tech.currentPrice || 0);
    const diff = krx ? (Number(nxt.price) - krx) / krx * 100 : null;
    allChecks.push({
      status: diff === null ? '△' : (diff >= 0.3 ? 'O' : (diff <= -0.3 ? 'X' : '△')),
      label: 'NXT 장전/장후 참고가',
      now: `${money(nxt.price)}${diff === null ? '' : ` · KRX 대비 ${pct(diff)}`}`,
      explain: diff === null ? 'KRX 기준가와 비교 데이터가 부족합니다.' : (diff > 0 ? '장외 참고가가 KRX보다 높아 단기 기대가 조금 있는 편입니다.' : (diff < 0 ? '장외 참고가가 KRX보다 낮아 단기 부담이 있을 수 있습니다.' : 'KRX와 거의 비슷해 특별한 장외 신호는 약합니다.')),
    });
  }
  if (volume.ratio !== null) {
    allChecks.push({
      status: volume.ratio >= 1.5 ? 'O' : (volume.ratio >= 1.0 ? '△' : 'X'),
      label: '거래량 힘',
      now: `20일 평균 대비 ${volume.ratio.toFixed(1)}배`,
      explain: volume.line,
    });
  }
  if (frgn5 !== null || orgn5 !== null) {
    const bothBuy = (frgn5 || 0) > 0 && (orgn5 || 0) > 0;
    const bothSell = (frgn5 || 0) < 0 && (orgn5 || 0) < 0;
    allChecks.push({
      status: bothBuy ? 'O' : (bothSell ? 'X' : '△'),
      label: '외국인·기관 수급',
      now: `외국인 ${compactNumber(frgn5)} · 기관 ${compactNumber(orgn5)}`,
      explain: bothBuy ? '큰 수급 주체가 같이 사는 흐름이라 우호적입니다.' : (bothSell ? '외국인과 기관이 같이 팔면 반등 힘이 약해질 수 있습니다.' : '외국인과 기관 방향이 엇갈려 확신은 낮습니다.'),
    });
  }
  if (shortRatio !== null) {
    allChecks.push({
      status: shortRatio < 4 ? 'O' : (shortRatio < 8 ? '△' : 'X'),
      label: '공매도 부담',
      now: `${shortRatio.toFixed(2)}%`,
      explain: shortRatio < 4 ? '공매도 비중이 낮은 편이라 위에서 누르는 힘은 제한적으로 봅니다.' : (shortRatio < 8 ? '공매도 부담이 중간 정도입니다. 상승 시 매도 압력이 나오는지 보세요.' : '공매도 비중이 높아 상승할 때 위에서 누르는 힘이 커질 수 있습니다.'),
    });
  }
  if (loan5 !== null) {
    allChecks.push({
      status: loan5 <= 0 ? 'O' : '△',
      label: '대차잔고 변화',
      now: `최근 5일 ${compactNumber(loan5, '주')}`,
      explain: loan5 <= 0 ? '빌린 주식이 줄어드는 쪽이면 매도 압력 부담이 완화될 수 있습니다.' : '빌린 주식이 늘면 향후 매도/헤지 물량 후보라 주의해서 봅니다.',
    });
  }
  if (targetPeer.operatingMarginPct != null && peerAvg.operatingMarginPct != null) {
    const ok = Number(targetPeer.operatingMarginPct) >= Number(peerAvg.operatingMarginPct);
    allChecks.push({
      status: ok ? 'O' : 'X',
      label: '동종업계 대비 수익성',
      now: `내 영업이익률 ${Number(targetPeer.operatingMarginPct).toFixed(2)}% · 평균 ${Number(peerAvg.operatingMarginPct).toFixed(2)}%`,
      explain: ok ? '동종업계 평균보다 이익률이 좋아 경쟁력이 우호적으로 보입니다.' : '동종업계 평균보다 이익률이 낮아 매출 성장만으로는 부족할 수 있습니다.',
    });
  }
  if (f.per != null || f.pbr != null || f.roe != null) {
    const expensive = Number(f.per) >= 40 || Number(f.pbr) >= 5;
    const profitable = Number(f.roe) >= 10;
    allChecks.push({
      status: expensive && !profitable ? 'X' : (expensive ? '△' : 'O'),
      label: '밸류 부담',
      now: `PER ${f.per ?? '-'} · PBR ${f.pbr ?? '-'} · ROE ${f.roe ?? '-'}`,
      explain: expensive ? '가격 부담이 있는 편입니다. 실적 성장이나 돌파 확인 없이 추격하면 위험할 수 있습니다.' : '밸류 부담은 과도하지 않은 편입니다. 다만 가격 흐름과 수급을 같이 봐야 합니다.',
    });
  }

  const danger = [];
  if (support) danger.push(`${money(support.from)} 아래로 종가가 밀리면 일단 방어`);
  if (shortRatio !== null && shortRatio >= 8) danger.push(`공매도 비중 ${shortRatio.toFixed(2)}%라 위에서 누르는 힘이 있을 수 있음`);
  if (loan5 !== null && loan5 > 0) danger.push(`대차잔고가 늘어 숏/헤지성 물량 가능성 체크`);
  if (frgn5 !== null && orgn5 !== null && frgn5 < 0 && orgn5 < 0) danger.push('외국인·기관이 같이 팔면 반등 힘이 약해질 수 있음');
  if (!danger.length) danger.push('현재 자동 데이터상 큰 경고는 제한적이지만, 지지선 이탈은 꼭 확인');

  const simpleWords = [
    `점수: ${Number.isFinite(score) ? `${score}점` : '대기'}입니다. 이 점수는 “매수강도”가 아니라 분석 신호의 강도라서, 확신도·시장상태·수급과 따로 봅니다.`,
    `확신도: ${survival.confidenceLevel || '-'} · ${survival.confidenceScore ?? '-'}점입니다. 확신도가 낮으면 점수가 높아도 관망할 수 있습니다.`,
    future ? `선물: ${future.stance}. 쉽게 말해 큰손들이 단기 방향을 어떻게 보고 있는지 보는 참고 신호입니다.` : '선물: 이 종목은 현재 선물 참고 데이터가 없거나 아직 누적 중입니다.',
    shortRatio === null ? '공매도: 데이터 대기입니다.' : `공매도: 주가가 내려갈 것에 베팅한 거래 비중입니다. 현재 ${shortRatio.toFixed(2)}%입니다.`,
    loan5 === null ? '대차잔고: 데이터 대기입니다.' : `대차잔고: 빌린 주식이 늘면 매도 압력 후보로 봅니다. 최근 5일 ${compactNumber(loan5, '주')} 변화입니다.`,
  ];
  const beginnerCards = [
    { label: '지금 행동', value: survival.actionState || '관망', note: headline },
    { label: '권장 비중', value: pos.suggestedRangePct || '0%', note: pos.plain || '확신 전에는 비중을 키우지 않습니다.' },
    { label: '한 줄 이유', value: survival.confidenceLevel || '확인 필요', note: `${regime?.label || '시장 판단 대기'} · 점수와 행동은 분리해서 봅니다.` },
    { label: '하면 안 되는 조건', value: invalid[0] ? '무효조건 있음' : '조건 확인', note: invalid[0] || danger[0] || '지지선 이탈·수급 악화 시 다시 판단합니다.' },
  ];
  return { headline, tone, waitChecks, allChecks, danger, simpleWords, volumeLine: volume.line, futureImpact: future?.impact || '', beginnerCards, score: Number.isFinite(score) ? score : null, confidenceScore: survival.confidenceScore ?? null, regime, actionState: survival.actionState || '관망', positionGuide: pos };
}

function renderDecisionBars(g = {}) {
  const score = g.score == null ? null : Math.max(0, Math.min(100, Number(g.score)));
  const confidence = g.confidenceScore == null ? null : Math.max(0, Math.min(100, Number(g.confidenceScore)));
  const regime = g.regime || {};
  const regimeTone = ['RISK_ON','NEUTRAL'].includes(regime.state) ? 'ok' : (['RISK_OFF','CAUTION'].includes(regime.state) ? 'no' : 'watch');
  const bar = (label, val, note) => `<div class="decision-bar"><div><strong>${esc(label)}</strong><span>${esc(note || '')}</span></div><em><i style="width:${val == null ? 0 : val}%"></i></em><b>${val == null ? '-' : `${Math.round(val)}점`}</b></div>`;
  return `<div class="decision-visuals">
    ${bar('분석 점수', score, '매수강도 아님')}
    ${bar('행동 확신도', confidence, '실제 행동 비중에 더 중요')}
    <div class="regime-signal ${regimeTone}"><strong>시장 Regime</strong><b>${esc(regime.label || regime.state || '판단 대기')}</b><span>${esc(regime.stance || '시장 상태를 먼저 보고 비중을 제한합니다.')}</span></div>
  </div>`;
}

function renderSurvivalGuide(f = {}) {
  const s = f.expertAnalysis?.survival || null;
  if (!s) return '';
  const sector = s.sectorProfile || f.sectorProfile || null;
  const regime = s.marketRegime || f.marketRegime || null;
  const conflicts = s.signalConflicts || [];
  const invalid = s.invalidationRules || [];
  const sectorRules = s.sectorRulesApplied || [];
  const riskPatterns = s.failureRiskPatterns || [];
  const pos = s.positionGuide || {};
  const patternLines = riskPatterns.map(p => `${p.label || p.code}: ${p.explain || ''}`);
  const policy = s.regimeStrategyPolicy || regime?.strategyPolicy || null;
  const tenSteps = [
    ['1. 최종 행동 결론', s.actionState || '관망', s.principle || '확신 없으면 쉬는 것이 전략입니다.'],
    ['2. 권장 비중', pos.suggestedRangePct || '0%', pos.plain || pos.label || '비중 가이드'],
    ['3. 행동 이유', s.confidenceLevel || '확인 필요', `점수와 행동을 분리합니다. 확신도 ${s.confidenceScore ?? '-'}점 · 데이터 품질 ${s.dataQualityScore ?? '-'}점`],
    ['4. 시장 Regime', regime ? `${regime.label || regime.state} · ${regime.riskScore ?? '-'}점` : '판단 대기', regime?.stance || '시장 상태를 먼저 봅니다'],
    ['5. 업종 Regime', sector?.label || '업종 판단 대기', sector?.plain || '업종 전용 프로필 수집 대기'],
    ['6. 종목 신호', '핵심 신호', (s.stockSignalSummary || f.expertAnalysis?.summary || '가격·수급·실적 신호를 종합합니다.')],
    ['7. 신호 충돌', conflicts.length ? `${conflicts.length}건` : '큰 충돌 제한적', conflicts[0] || '가격 조건 확인 전 추격은 금지합니다.'],
    ['8. 진입 조건', '조건부', (f.expertAnalysis?.upsideTriggers || [])[0] || '돌파·거래량·수급 확인 후 접근합니다.'],
    ['9. 판단 무효 조건', invalid.length ? '무효조건 있음' : '조건 확인', invalid[0] || '주요 지지선 이탈 또는 수급 악화 시 판단을 다시 봅니다.'],
    ['10. 사후 검증 계획', '추적', '진입 후 수익률·무효조건 발생·오판위험 후보 적중 여부를 ledger로 검증합니다.'],
  ];
  return `<section id="tab-survival" class="card stock-detail-section survival-guide"><h2>전문가용 10단계 판단</h2>
    <div class="stock-detail-metrics">
      ${metric('실전 행동', s.actionState || '관망', pos.plain || '확신 없으면 쉬는 것이 전략입니다.')}
      ${metric('확신도', `${s.confidenceLevel || '-'} · ${s.confidenceScore ?? '-'}점`, `데이터 품질 ${s.dataQualityScore ?? '-'}점`)}
      ${metric('시장 Regime', regime ? `${regime.label || regime.state} · ${regime.riskScore ?? '-'}점` : '판단 대기', regime?.stance || '시장 상태를 먼저 봅니다')}
      ${metric('Regime 전략', policy?.maxPositionPct || '보수적', policy?.entryRule || '시장 상태에 따라 비중을 조절합니다')}
      ${metric('권장 비중', pos.suggestedRangePct || '0%', pos.label || '비중 가이드')}
      ${metric('관망 인정', s.waitIsValid ? 'YES' : '조건부', '관망은 실패가 아니라 리스크 관리입니다')}
    </div>
    <ol class="decision-ladder">${tenSteps.map(([title, value, note]) => `<li><span>${esc(title)}</span><strong>${esc(value)}</strong><p>${esc(note)}</p></li>`).join('')}</ol>
    <div class="scenario-grid">
      <article><h3>업종별 해석</h3>${sector ? list([`${sector.label || '업종'}: ${sector.plain || ''}`, `중요 신호: ${(sector.importantFactors || []).join(', ') || '-'}`, sector.downweightedFactors?.length ? `덜 믿을 지표: ${sector.downweightedFactors.join(', ')}` : '']) : list(['업종 전용 프로필 수집 대기'])}</article>
      <article><h3>업종 가중치 반영</h3>${list(sectorRules.length ? sectorRules : ['일반 생존형 가중치 적용 중입니다.'])}</article>
      <article><h3>신호 충돌</h3>${list(conflicts.length ? conflicts : ['큰 신호 충돌은 제한적입니다. 그래도 가격 조건 확인 전 추격은 금지합니다.'])}</article>
      <article><h3>오판위험 후보</h3>${list(patternLines.length ? patternLines : ['아직 뚜렷한 오판위험 후보는 없습니다.'])}</article>
      <article><h3>판단 무효조건</h3>${list(invalid.length ? invalid : ['주요 지지선 이탈 또는 수급 악화 시 판단을 다시 봅니다.'])}</article>
    </div>
    <p class="stock-modal-note">${esc(s.principle || '안 죽는 AI: 확신 없으면 쉬고, 위험하면 피합니다.')}</p>
  </section>`;
}

function renderBeginnerChecks(items = []) {
  if (!items.length) return list(['현재 체크할 조건 데이터가 부족합니다.']);
  return `<div class="beginner-check-list">${items.map(x => {
    const cls = x.status === 'O' ? 'ok' : (x.status === 'X' ? 'no' : 'watch');
    return `<div class="beginner-check ${cls}"><b>${esc(x.status)}</b><div><strong>${esc(x.label)}</strong><span>${esc(x.now || '')}</span><p>${esc(x.explain || '')}</p></div></div>`;
  }).join('')}</div>`;
}

function renderBeginnerGuide(f = {}, rows = []) {
  const g = beginnerGuide(f, rows);
  return `<section id="tab-beginner" class="card stock-detail-section beginner-guide ${esc(g.tone)}"><h2>초보자용 한눈 해석</h2>
    <div class="beginner-head"><strong>${esc(g.headline)}</strong><span>전문용어를 빼고 보면 이렇습니다</span></div>
    <div class="beginner-card-grid">${g.beginnerCards.map(x => `<article><span>${esc(x.label)}</span><strong>${esc(x.value)}</strong><p>${esc(x.note)}</p></article>`).join('')}</div>
    ${renderDecisionBars(g)}
    <div class="scenario-grid beginner-grid">
      <article><h3>그래서 오를 것 같아?</h3>${list([g.headline, g.futureImpact].filter(Boolean))}</article>
      <article><h3>핵심 체크리스트</h3>${renderBeginnerChecks(g.allChecks)}</article>
      <article><h3>뭘 기다리면 돼?</h3>${renderBeginnerChecks(g.waitChecks)}</article>
      <article><h3>거래량은 어때?</h3>${list([g.volumeLine])}</article>
      <article><h3>조심할 신호</h3>${list(g.danger)}</article>
    </div>
    <article class="beginner-terms"><h3>어려운 말 쉽게 풀면</h3>${list(g.simpleWords)}</article>
  </section>`;
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

function renderPeerGrowthMargin(f = {}) {
  const p = f.peerGrowthMargin || null;
  if (!p || !p.target) return '';
  const target = p.target || {};
  const avg = p.peerAverage || {};
  const peers = Array.isArray(p.peers) ? p.peers.slice(0, 4) : [];
  const pctVal = v => v === null || v === undefined || Number.isNaN(Number(v)) ? '-' : `${Number(v).toFixed(2)}%`;
  const row = (name, code, growth, margin, sales) => `<tr><td>${esc(name || '-')}<small>${esc(code || '')}</small></td><td>${pctVal(growth)}</td><td>${pctVal(margin)}</td><td>${compactNumber(sales, '억')}</td></tr>`;
  return `<section id="tab-peer" class="card stock-detail-section peer-growth-section"><h2>동종업계 성장/마진 비교</h2>
    <div class="stock-detail-metrics">
      ${metric('내 매출 성장률', pctVal(target.salesGrowthPct), avg.salesGrowthPct == null ? 'DART 기준' : `비교군 평균 ${pctVal(avg.salesGrowthPct)}`)}
      ${metric('내 영업익 증가율', pctVal(target.operatingProfitGrowthPct), avg.operatingProfitGrowthPct == null ? '' : `비교군 평균 ${pctVal(avg.operatingProfitGrowthPct)}`)}
      ${metric('내 영업이익률', pctVal(target.operatingMarginPct), avg.operatingMarginPct == null ? '' : `비교군 평균 ${pctVal(avg.operatingMarginPct)}`)}
      ${metric('마진 변화', target.operatingMarginChangePctp == null ? '-' : `${Number(target.operatingMarginChangePctp) >= 0 ? '+' : ''}${Number(target.operatingMarginChangePctp).toFixed(2)}%p`, avg.operatingMarginChangePctp == null ? '전년 대비' : `비교군 평균 ${avg.operatingMarginChangePctp >= 0 ? '+' : ''}${Number(avg.operatingMarginChangePctp).toFixed(2)}%p`)}
      ${metric('매출 규모', compactNumber(target.sales, '억'), avg.sales == null ? '' : `비교군 평균 ${compactNumber(avg.sales, '억')}`)}
    </div>
    ${list(p.notes || [])}
    <div class="peer-table-wrap"><table class="peer-growth-table"><thead><tr><th>기업</th><th>영업익 증가율</th><th>영업이익률</th><th>매출</th></tr></thead><tbody>
      ${row(target.name, target.code, target.operatingProfitGrowthPct, target.operatingMarginPct, target.sales)}
      ${peers.map(x => row(x.name, x.code, x.operatingProfitGrowthPct, x.operatingMarginPct, x.sales)).join('')}
    </tbody></table></div>
    <p class="stock-modal-note">source: ${esc(p.source || 'peer-table')} · ${esc(p.basis || '동종업계 비교표 기준')}</p>
  </section>`;
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
  return `<section id="tab-kis" class="card stock-detail-section"><h2>KIS 실사용 보강 데이터</h2>
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
  const newsLines = news.map(renderNewsLink);
  return `<section id="tab-news" class="card stock-detail-section"><h2>실적·수급·공매도·대차·뉴스 상세</h2>
    <div class="scenario-grid">
      <article><h3>최근 실적</h3>${list(incomeLines)}</article>
      <article><h3>외국인/기관 수급</h3>${list(investorLines)}</article>
      <article><h3>공매도</h3>${list(shortLines)}</article>
      <article><h3>대차잔고</h3>${list(loanLines)}</article>
    </div>
    <h3>최근 뉴스·공시 제목</h3>${htmlList(newsLines)}
  </section>`;
}

function renderDetailTabs(f = {}) {
  const tabs = [
    ['tab-beginner', '한눈해석'],
    ['tab-survival', '생존가이드'],
    ['tab-future', '선물'],
    ['tab-nxt', 'NXT'],
    ['tab-timing', '오를시점'],
    ['tab-chart', '차트/거래량'],
    ['tab-valuation', '밸류'],
    ['tab-peer', '동종업계'],
    ['tab-kis', '실적/수급'],
    ['tab-news', '뉴스/공시'],
    ['tab-scenario', '시나리오'],
  ];
  return `<nav class="stock-detail-tabs" aria-label="종목 상세 빠른 이동">
    ${tabs.map(([id, label]) => `<a href="#${id}">${esc(label)}</a>`).join('')}
  </nav>`;
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
    ${renderDetailTabs(f)}
    ${renderNxtQuote(f)}
    ${renderStockFutureQuote(f)}
    ${renderBeginnerGuide(f, ohlcv?.rows || [])}
    ${renderSurvivalGuide(f)}
    ${renderRiseTiming(f, ohlcv?.rows || [])}
    ${renderRealtimeCandle(f)}
    <section id="tab-chart" class="card stock-detail-section"><h2>가격·거래량 구조 분석</h2>${renderOhlcv(ohlcv?.rows || [], tech, f.intradayCandle)}</section>
    <section id="tab-valuation" class="card stock-detail-section"><h2>ROE · PBR · PER 종합 밸류 분석</h2>${renderValuation(f)}${list(f.report)}</section>
    ${renderPeerGrowthMargin(f)}
    ${renderKisSummary(f)}
    ${renderKisTables(f)}
    <section id="tab-scenario" class="card stock-detail-section"><h2>전문가형 시나리오 분석</h2>${scenarioTable(f)}</section>
    <section class="card stock-detail-section"><h2>핵심 포인트</h2>${list(a.keyPoints)}</section>
    <section class="card stock-detail-section"><h2>추가로 넣으면 좋은 자료</h2>${list(a.additionalDataNeeded, '현재 추가로 필요한 자료 없음')}<p class="stock-modal-note">${esc(a.disclaimer || '자동 분석은 투자 판단 보조자료입니다.')}</p></section>
    ${contextBlock(contexts)}
  `;
  bindStockChartTooltip();
}

async function main() {
  if (!/^\d{6}$/.test(code)) throw new Error('종목코드가 없습니다.');
  const [dashboard, ohlcvData] = await Promise.all([
    firstJson(['data/test/dashboard-data.json', 'data/dashboard-data.json']),
    firstJson(['data/test/fundamentals/daily_ohlcv_latest.json', 'data/fundamentals/daily_ohlcv_latest.json']),
  ]);
  const matches = walkStocks(dashboard).filter(x => String(x.code).padStart(6,'0') === code);
  if (!matches.length) throw new Error(`${code} 종목 분석 데이터가 없습니다.`);
  matches.forEach(x => { if (x.fundamentals) x.fundamentals.marketRegime = dashboard.marketRegime; });
  renderDetail(matches[0], uniqContexts(matches), ohlcvData.items?.[code]);
}

main().catch(err => {
  document.getElementById('stockDetailRoot').innerHTML = `<section class="card"><h2>데이터 로드 실패</h2><p>${esc(err.message)}</p><p><a class="stock-back-link" href="./">대시보드로 돌아가기</a></p></section>`;
});
