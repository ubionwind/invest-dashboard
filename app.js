const fmt = new Intl.NumberFormat('ko-KR');
const dtFmt = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
let amountChart;
let returnChart;
let itemCharts = [];
const isMobile = () => window.matchMedia('(max-width: 1024px)').matches;
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

function isRegularMarketPoint(x) {
  if (!x?.ts) return false;
  const d = new Date(x.ts);
  if (Number.isNaN(d.getTime())) return false;
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(d).map(p => [p.type, p.value]));
  if (parts.weekday === 'Sat' || parts.weekday === 'Sun') return false;
  const minutes = Number(parts.hour) * 60 + Number(parts.minute);
  return minutes >= 9 * 60 && minutes <= 15 * 60 + 30;
}

function chartWindow(history) {
  const arr = (history || []).filter(isRegularMarketPoint);
  const visible = arr.length ? arr : (history || []);
  return isMobile() ? visible.slice(-12) : visible;
}

function chartOptions(yCallback) {
  const mobile = isMobile();
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: !mobile, labels: { color: '#eaf0ff' }}
    },
    elements: { point: { radius: mobile ? 0 : 2 } },
    scales: {
      x: { ticks: { color: '#8d9ab8', maxRotation: 0, autoSkip: true, maxTicksLimit: mobile ? 4 : 8 }, grid: { color: 'rgba(255,255,255,.06)' }},
      y: { ticks: { color: '#8d9ab8', maxTicksLimit: mobile ? 5 : 8, callback: yCallback }, grid: { color: 'rgba(255,255,255,.06)' }}
    }
  };
}

function formatKst(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return dtFmt.format(d).replace(/\. /g, '-').replace('.', '');
}

const statusClass = (s) => `status-${String(s || 'NO_DATA').replace(/[^A-Z_]/g, '')}`;

function metric(label, value, note = '') {
  return `<div class="metric"><span class="muted">${label}</span><span class="value">${value}</span><small class="muted">${note}</small></div>`;
}


function benchmarkNote(bm) {
  if (!bm) return '기준 없음';
  const base = bm.periodStart && bm.periodEnd ? `${bm.label || 'KOSPI'} · 기간 ${String(bm.periodStart).slice(5,16)}~${String(bm.periodEnd).slice(5,16)}` : (bm.date ? `${bm.label || 'KOSPI'} · 기준 ${bm.date}${bm.time ? ` ${String(bm.time).slice(0,5)}` : ''}` : (bm.label || 'KOSPI'));
  return base;
}

function comparisonHelp() {
  return '시장 대비 = 누적 수익률 - 같은 기간 KOSPI 수익률';
}

function pctClass(v) {
  if (v === null || v === undefined) return '';
  return Number(v) >= 0 ? 'up' : 'down';
}

function marketRows(kospi, kodex) {
  return `<span class="market-rows">
    <span class="market-row"><span>KOSPI</span><b class="${pctClass(kospi)}">${pct(kospi)}</b></span>
    <span class="market-row"><span>KODEX</span><b class="${pctClass(kodex)}">${pct(kodex)}</b></span>
  </span>`;
}

function marketDailyPair(data) {
  return marketRows(data.benchmark?.dailyReturnPct, data.kodexBenchmark?.dailyReturnPct);
}

function marketCumulativePair(data) {
  return marketRows(data.benchmark?.returnPct, data.kodexBenchmark?.returnPct);
}

function basisText(start) {
  if (!start) return '기준 없음';
  return `시작 ${formatKst(start).slice(5)}`;
}

function summaryTile(label, value, note = '', icon = '•', tone = '') {
  return `<article class="summary-tile ${tone ? `summary-${tone}` : ''}">
    <div class="summary-icon">${icon}</div>
    <div>
      <span class="muted">${label}</span>
      <strong>${value}</strong>
      <small class="muted">${note}</small>
    </div>
  </article>`;
}

function kpi(label, value) {
  const shown = typeof value === 'number' ? fmt.format(value) : (value ?? '-');
  return `<div class="kpi"><span class="muted">${label}</span><strong>${shown}</strong></div>`;
}

function compactMoney(v) {
  if (v === null || v === undefined) return '-';
  const num = Number(v);
  if (Number.isNaN(num)) return '-';
  const abs = Math.abs(num);
  if (abs >= 100000000) return `${(num / 100000000).toFixed(1)}억`;
  if (abs >= 10000) return `${(num / 10000).toFixed(0)}만`;
  return fmt.format(num);
}

function portfolioStrip(pf = {}) {
  return `<div class="portfolio-strip">
    <div><span>원금</span><strong>${compactMoney(pf.capital)}</strong></div>
    <div><span>현금</span><strong>${compactMoney(pf.cash)}</strong></div>
    <div><span>투자금</span><strong>${compactMoney(pf.investmentAmount)}</strong></div>
    <div><span>수익금</span><strong class="${(pf.pnl || 0) >= 0 ? 'up' : 'down'}">${compactMoney(pf.pnl)}</strong></div>
    <div><span>수익률</span><strong class="${(pf.returnPct || 0) >= 0 ? 'up' : 'down'}">${pct(pf.returnPct)}</strong></div>
  </div>`;
}

function investmentReturnPct(pf = {}) {
  const investment = Number(pf.investmentAmount || 0);
  const pnl = Number(pf.pnl || 0);
  if (!investment || Number.isNaN(investment) || Number.isNaN(pnl)) return null;
  return (pnl / investment) * 100;
}

function returnMetricCard(label, value, note = '', toneValue = value) {
  const num = Number(toneValue);
  const cls = Number.isNaN(num) ? '' : (num >= 0 ? 'up' : 'down');
  return `<article class="return-card">
    <span>${label}</span>
    <strong class="${cls}">${value}</strong>
    ${note ? `<small>${note}</small>` : ''}
  </article>`;
}

function currentHoldingMetrics(pf = {}) {
  const positions = Array.isArray(pf.positions) ? pf.positions : [];
  const buyAmount = positions.reduce((sum, p) => {
    const qty = Number(p.qty || 0);
    const entry = Number(p.entryPrice || 0);
    return sum + Number(p.entryAmount ?? (qty && entry ? qty * entry : 0));
  }, 0);
  const evalAmount = positions.reduce((sum, p) => sum + Number(p.evalAmount || 0), 0);
  const pnl = positions.reduce((sum, p) => sum + Number(p.pnl || 0), 0);
  const returnPct = buyAmount ? (pnl / buyAmount) * 100 : null;
  return { buyAmount, evalAmount, pnl, returnPct };
}

function strategyReturnCards(s) {
  const pf = s.portfolio || {};
  const daily = s.daily || {};
  const investPct = investmentReturnPct(pf);
  const held = currentHoldingMetrics(pf);
  return `<div class="strategy-return-cards">
    ${returnMetricCard('누적 수익률', pct(pf.returnPct), '전략 실행 이후', pf.returnPct)}
    ${returnMetricCard('전략 종합 평가손익', money(pf.pnl), `총 평가 ${compactMoney(pf.evalAmount || pf.capital)}`, pf.pnl)}
    ${returnMetricCard('오늘 수익률', pct(daily.returnPct), `전체 매수 종목 오늘 ${money(daily.pnl)}`, daily.returnPct)}
    ${returnMetricCard('현재 보유 매입금액', compactMoney(held.buyAmount), `현재 보유 ${fmt.format((pf.positions || []).length)}종목`, held.pnl)}
    ${returnMetricCard('현재 보유 평가손익', money(held.pnl), `보유 수익률 ${pct(held.returnPct)}`, held.pnl)}
    ${returnMetricCard('현재 보유 평가금액', compactMoney(held.evalAmount), `매입 ${compactMoney(held.buyAmount)}`, held.pnl)}
    ${returnMetricCard('현재 보유 수익률', pct(held.returnPct), `평가손익 ${money(held.pnl)}`, held.returnPct)}
  </div>`;
}

function candidateSummary(s) {
  const candidates = s.topCandidates || [];
  const entryCount = Number(s.gateCount || 0);
  const reviewCount = candidates.filter(c => ['매수검토', '검증통과-신규검토', '검증통과-보유중추가검토'].includes(String(c.status || c.action || c.validationStatus || ''))).length;
  const names = candidates.slice(0, 3).map(c => c.name).filter(Boolean).join(' · ');
  const stateText = entryCount > 0
    ? `신규진입 대기 ${fmt.format(entryCount)}건`
    : (reviewCount > 0 ? `매수검토 ${fmt.format(reviewCount)}건 · 주문대기 없음` : '신규진입 없음 · 관찰후보만 있음');
  return `<section class="candidate-summary">
    <div>
      <span class="muted">후보</span>
      <strong>${fmt.format(s.candidateCount || 0)}</strong>
    </div>
    <p><b>${stateText}</b>${names ? ` · ${names}` : ''}</p>
  </section>`;
}

function supplySnapshot(c = {}) {
  const reason = String(c.reason || '');
  const parts = reasonParts(reason);
  const money = reason.match(/거래대금\s*([\d,.]+\s*[조억만]?)/);
  return [
    parts.theme ? `테마 ${parts.theme}` : '',
    parts.meta ? `메타 ${parts.meta}` : '',
    money ? `거래대금 ${money[1]}` : '',
    c.changePct !== null && c.changePct !== undefined ? `등락 ${pct(c.changePct)}` : '',
  ].filter(Boolean).join(' · ') || '수급/테마 데이터 보강 대기';
}

function liquidityEvidenceText(item = {}) {
  const reason = String(item.reason || item.entryReason || '');
  const amount = reason.match(/거래대금\s*([\d,.]+\s*[조억만]?)/);
  if (amount) return `거래대금 ${amount[1]}`;
  const score = reason.match(/거래대금점수\s*=\s*([\d.]+)/);
  if (score) return `거래대금 점수 ${Number(score[1]).toFixed(0)}`;
  if (reason.includes('거래대금 증가')) return '거래대금 증가';
  return '수급 데이터 대기';
}

function tradingValueText(item = {}) {
  return liquidityEvidenceText(item);
}

function standardReason(item = {}) {
  const reason = String(item.reason || item.entryReason || '').replace(/^가상\s*/, '').replace(/^진입만:\s*/, '');
  if (!reason) return '판단 근거 보강 대기';
  return reason.length > 64 ? `${reason.slice(0, 64)}…` : reason;
}

function normalizedScoreText(v) {
  return v === null || v === undefined || Number.isNaN(Number(v)) ? '-' : Number(v).toFixed(1);
}

function switchMiniGraph({ baseScore = null, currentScore = null, candidateScore = null, returnPct = null, currentLabel = '현재', triggerBaseScore = null, thresholdLabel = '교체기준' } = {}) {
  const cur = currentScore == null ? 50 : Math.max(0, Math.min(100, Number(currentScore)));
  const base = baseScore == null ? cur : Math.max(0, Math.min(100, Number(baseScore)));
  const cand = candidateScore == null ? cur + 12 : Math.max(0, Math.min(100, Number(candidateScore)));
  const triggerBase = triggerBaseScore == null ? cur : Math.max(0, Math.min(100, Number(triggerBaseScore)));
  const danger = returnPct !== null && returnPct !== undefined && Number(returnPct) <= -4;
  const trigger = Math.max(triggerBase + 12, 70);
  const toY = v => Math.round(42 - (Math.max(0, Math.min(100, v)) / 100) * 32);
  const points = `4,${toY(base)} 52,${toY(cur)} 100,${toY(cand)}`;
  const triggerY = toY(trigger);
  const help = danger ? '수익률이 손절 관찰 구간에 가까움' : `후보가 교체기준을 넘으면 교체 검토`;
  return `<div class="switch-mini" title="${help}">
    <svg viewBox="0 0 104 46" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="0" y1="${triggerY}" x2="104" y2="${triggerY}" class="switch-line" />
      <polyline points="${points}" class="switch-curve" />
      <circle cx="52" cy="${toY(cur)}" r="2.8" class="switch-dot" />
    </svg>
    <span class="switch-score-labels"><b>${thresholdLabel} ${Math.round(trigger)}</b><b>${currentLabel} ${Math.round(cur)}</b></span>
  </div>`;
}

function replacementThreshold(baseScore) {
  if (baseScore === null || baseScore === undefined || Number.isNaN(Number(baseScore))) return null;
  return Math.max(Number(baseScore) + 12, 70);
}

function thresholdFormula(baseScore) {
  const threshold = replacementThreshold(baseScore);
  if (threshold === null) return '-';
  return `${Number(baseScore).toFixed(1)} + 12 = ${threshold.toFixed(1)}`;
}

function holdingReasonText({ decision, ret, scoreGap, bestReplacement } = {}) {
  const bestName = bestReplacement?.name ? ` / 후보 ${bestReplacement.name}` : '';
  if (decision === '교체검토') return `손실 또는 점수 열위${bestName}`;
  if (decision === '익절/트레일링') return '수익권: 익절선/트레일링 관찰';
  if (decision === '비교관찰') return `후보 우위 ${scoreGap?.toFixed ? scoreGap.toFixed(1) : ''}점${bestName}`;
  if (decision === '손절관찰') return `손실 ${pct(ret)}: 회복/손절선 관찰`;
  return `유지: 교체 우위 부족${bestName}`;
}

function diagnosticRows(rows) {
  return `<div class="diagnostic-rows">${rows.map(([label, value, cls = '']) => `
    <div><span>${label}</span><b class="${cls}">${value}</b></div>
  `).join('')}</div>`;
}

function holdingSupplySnapshot(pos = {}, matched = {}) {
  if (matched?.reason) return supplySnapshot(matched);
  return [
    pos.sourceChangePct !== null && pos.sourceChangePct !== undefined ? `진입시 등락 ${pct(pos.sourceChangePct)}` : '',
    pos.entryReason || '',
  ].filter(Boolean).join(' · ') || '현재 후보권 밖 · 수급 데이터 보강 대기';
}

function decisionForHolding(pos = {}, matched = {}, bestReplacement = {}) {
  const ret = Number(pos.returnPct || 0);
  const score = matched?.score == null ? null : Number(matched.score);
  const bestScore = bestReplacement?.score == null ? null : Number(bestReplacement.score);
  const gap = score == null || bestScore == null ? null : bestScore - score;
  if (ret <= -4 || (gap !== null && gap >= 20 && ret < 0)) return '교체검토';
  if (ret >= 5) return '익절/트레일링';
  if (gap !== null && gap >= 12) return '비교관찰';
  if (ret <= -2) return '손절관찰';
  return '유지';
}

function holdingCandidateComparison(s) {
  const positions = s.portfolio?.positions || [];
  const candidates = s.topCandidates || [];
  if (!positions.length && !candidates.length) return '';
  const byCode = Object.fromEntries(candidates.map(c => [String(c.code || ''), c]));
  const scoredPositions = positions
    .map(p => ({ ...p, compareScore: p.currentScoreNormalized ?? p.sourceScoreNormalized ?? null }))
    .filter(p => p.compareScore !== null && p.compareScore !== undefined && !Number.isNaN(Number(p.compareScore)));
  const replacementTarget = scoredPositions.length
    ? scoredPositions.reduce((a, b) => Number(a.compareScore) <= Number(b.compareScore) ? a : b)
    : null;
  const lowestHeldScore = replacementTarget ? Number(replacementTarget.compareScore) : null;
  const commonThreshold = replacementThreshold(lowestHeldScore);
  const replacementPool = candidates.filter(c => !positions.some(p => String(p.code || '') === String(c.code || ''))).slice(0, 5);
  const bestReplacement = replacementPool[0] || {};
  const bestCandidateScore = bestReplacement?.score == null ? null : Number(bestReplacement.score);
  const bestPasses = commonThreshold !== null && bestCandidateScore !== null && bestCandidateScore >= commonThreshold;
  const targetLabel = replacementTarget ? `${replacementTarget.name || replacementTarget.code || '보유종목'} ${Number(lowestHeldScore).toFixed(1)}점` : '보유점수 대기';
  const orderedPositions = [...positions].sort((a, b) => {
    const aTarget = replacementTarget && String(a.code || '') === String(replacementTarget.code || '');
    const bTarget = replacementTarget && String(b.code || '') === String(replacementTarget.code || '');
    if (aTarget !== bTarget) return aTarget ? -1 : 1;
    return 0;
  });
  return `<section class="comparison-lab">
    <div class="comparison-head">
      <div>
        <h3>보유·후보 비교</h3>
        <p class="muted">공통 기준 하나만 사용: 기준종목 ${targetLabel} → 후보 통과선 ${commonThreshold === null ? '-' : commonThreshold.toFixed(1)}점. 후보가 통과선을 넘으면 기준종목과 교체 검토.</p>
      </div>
      <span class="badge compact">공통기준</span>
    </div>
    <div class="comparison-columns">
      <div class="comparison-block">
        <h4>보유 종목 진단</h4>
        ${orderedPositions.length ? orderedPositions.map(pos => {
          const matched = byCode[String(pos.code || '')] || {};
          const entryScore = pos.entryScoreNormalized ?? null;
          const currentScore = pos.currentScoreNormalized ?? pos.sourceScoreNormalized ?? null;
          const hasCurrentCandidateScore = pos.currentScoreType === 'current' || (matched.score !== null && matched.score !== undefined);
          const currentScoreLabel = hasCurrentCandidateScore ? '현재점수' : '보유점수';
          const graphCurrentLabel = hasCurrentCandidateScore ? '현재' : '보유';
          const isTarget = replacementTarget && String(pos.code || '') === String(replacementTarget.code || '');
          const decision = isTarget && bestPasses ? '교체검토' : (isTarget ? '기준종목' : '유지');
          const ret = Number(pos.returnPct || 0);
          const holdReason = pos.holdAction && pos.holdAction !== '보유유지'
            ? `${pos.holdAction}: ${pos.holdReason || ''}`
            : (isTarget
              ? (bestPasses ? `통과 후보 ${bestReplacement.name || ''}와 교체 검토` : '최고 후보가 아직 통과선 미달')
              : `교체 판단 대상 아님 · 기준종목은 ${replacementTarget?.name || '-'}`);
          return `<article class="holding-compare-card ${isTarget ? 'basis-stock-card' : ''}">
            ${isTarget ? '<div class="basis-ribbon">기준종목 · 후보 통과선 산정 기준</div>' : ''}
            <div class="compare-hero">
              <div class="compare-identity"><strong>${pos.name || '-'}</strong><b class="${ret >= 0 ? 'up' : 'down'}">${pct(pos.returnPct)}</b></div>
              ${switchMiniGraph({ baseScore: lowestHeldScore, currentScore, candidateScore: bestCandidateScore, returnPct: pos.returnPct, currentLabel: graphCurrentLabel, triggerBaseScore: lowestHeldScore, thresholdLabel: '공통기준' })}
              <div class="compare-meta"><span>${pos.code || ''}</span><em>${pos.holdAction && pos.holdAction !== '보유유지' ? pos.holdAction : decision}</em></div>
            </div>
            ${diagnosticRows([
              [currentScoreLabel, normalizedScoreText(currentScore)],
              ['후보 통과선', commonThreshold === null ? '-' : commonThreshold.toFixed(1)],
              ['역할', isTarget ? '기준종목' : '보유유지'],
              ['최고후보', bestCandidateScore == null ? '-' : normalizedScoreText(bestCandidateScore)],
              ['등락/수익', pct(pos.returnPct), ret >= 0 ? 'up' : 'down'],
              ['거래/수급', pos.liquidityText || tradingValueText(matched.reason ? matched : pos)],
              ['유지/교체 이유', holdReason],
            ])}
            <small class="muted">매입 ${money(pos.entryPrice)} · 현재 ${money(pos.currentPrice)} · 손익 ${money(pos.pnl)}</small>
          </article>`;
        }).join('') : '<p class="muted">현재 보유 종목 없음</p>'}
      </div>
      <div class="comparison-block">
        <h4>교체 후보군</h4>
        ${replacementPool.length ? replacementPool.map(c => {
          const candidateScore = c.candidateScoreNormalized ?? c.score;
          const edge = candidateScore == null || commonThreshold == null ? null : Number(candidateScore) - commonThreshold;
          const passed = edge !== null && edge >= 0;
          return `<article class="replacement-card">
            <div class="compare-hero">
              <div class="compare-identity"><strong>${c.name || '-'}</strong><b>${c.score == null ? '-' : Number(c.score).toFixed(1)}</b></div>
              ${switchMiniGraph({ baseScore: lowestHeldScore, currentScore: candidateScore, candidateScore, currentLabel: '후보', triggerBaseScore: lowestHeldScore, thresholdLabel: '공통기준' })}
              <div class="compare-meta"><span>${c.code || ''}</span><em class="${edge == null ? '' : (passed ? 'up' : 'down')}">${edge == null ? '비교대기' : (passed ? `통과 +${edge.toFixed(1)}` : `미달 ${edge.toFixed(1)}`)}</em></div>
            </div>
            ${diagnosticRows([
              ['후보점수', normalizedScoreText(c.score)],
              ['비교 기준종목', replacementTarget?.name || '-'],
              ['후보 통과선', commonThreshold === null ? '-' : commonThreshold.toFixed(1)],
              ['기준대비', edge == null ? '-' : `${edge > 0 ? '+' : ''}${edge.toFixed(1)}`, edge == null ? '' : (edge >= 0 ? 'up' : 'down')],
              ['등락/수익', c.changePct == null ? '-' : pct(c.changePct), c.changePct == null ? '' : (Number(c.changePct) >= 0 ? 'up' : 'down')],
              ['거래/수급', c.liquidityText || tradingValueText(c)],
              ['유지/교체 이유', standardReason(c)],
            ])}
            <small class="muted">${c.candidateNote || c.status || '현재 후보'}</small>
          </article>`;
        }).join('') : '<p class="muted">보유 종목보다 앞선 별도 후보 없음</p>'}
      </div>
    </div>
  </section>`;
}

function sameKstDate(a, b) {
  if (!a || !b) return false;
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' });
  return f.format(new Date(a)) === f.format(new Date(b));
}

function dailyForSession(history = [], idx) {
  const points = (history || []).filter(x => x?.ts && Array.isArray(x.returns) && x.returns[idx] !== undefined);
  if (!points.length) return { returnPct: null, pnl: null };
  const latest = points[points.length - 1];
  const sameDay = points.filter(x => sameKstDate(x.ts, latest.ts));
  const base = sameDay[0] || latest;
  const latestReturn = Number(latest.returns[idx]);
  const baseReturn = Number(base.returns[idx]);
  const latestEval = Number(latest.evalAmounts?.[idx]);
  const baseEval = Number(base.evalAmounts?.[idx]);
  return {
    returnPct: Number.isNaN(latestReturn) || Number.isNaN(baseReturn) ? null : latestReturn - baseReturn,
    pnl: Number.isNaN(latestEval) || Number.isNaN(baseEval) ? null : latestEval - baseEval,
  };
}

function enrichSessions(data) {
  data.sessions = (data.sessions || []).map((s, idx) => ({ ...s, daily: dailyForSession(data.history, idx) }));
  return data;
}


function money(v) {
  if (v === null || v === undefined) return '-';
  return `${fmt.format(v)}원`;
}

function moneyBare(v) {
  if (v === null || v === undefined) return '-';
  return fmt.format(v);
}

function pct(v) {
  if (v === null || v === undefined) return '-';
  return `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
}

function colorizePnlText(text = '') {
  const raw = String(text || '');
  return raw.replace(/(손익\s*)([+-]?\d[\d,]*원)/g, (_, label, value) => {
    const num = Number(String(value).replace(/원|,/g, ''));
    const cls = Number.isNaN(num) ? '' : (num >= 0 ? 'up' : 'down');
    return `<span class="pnl-group">${label}<span class="pnl-inline ${cls}">${value}</span></span>`;
  });
}

function reasonParts(reason = '') {
  return String(reason || '')
    .split(';')
    .map(x => x.trim())
    .filter(Boolean)
    .reduce((acc, part) => {
      const [rawKey, ...rest] = part.split('=');
      const key = String(rawKey || '').trim();
      const value = rest.join('=').trim();
      if (key && value) acc[key] = value;
      return acc;
    }, {});
}

function candidateTile(c, idx) {
  const parts = reasonParts(c.reason);
  const change = c.changePct === null || c.changePct === undefined || c.changePct === '' ? parts['등락률'] : c.changePct;
  const theme = parts.theme;
  const meta = parts.meta;
  const status = c.status || '검토';
  const score = c.score === null || c.score === undefined || c.score === '' ? '-' : Number(c.score).toFixed(1);
  const scoreNum = score === '-' ? null : Number(score);
  const scoreTone = scoreNum === null || Number.isNaN(scoreNum) ? 'score-none' : scoreNum >= 90 ? 'score-very-high' : scoreNum >= 80 ? 'score-high' : scoreNum >= 70 ? 'score-watch' : scoreNum >= 60 ? 'score-neutral' : 'score-low';
  const rawScore = c.rawScore === null || c.rawScore === undefined || c.rawScore === '' ? null : Number(c.rawScore).toFixed(1);
  const buyReturn = c.returnPct === null || c.returnPct === undefined || c.returnPct === '' ? null : Number(c.returnPct);
  const changeNum = change === undefined ? null : Number(change);
  const changeClass = changeNum === null || Number.isNaN(changeNum) ? '' : (changeNum >= 0 ? 'up' : 'down');
  const buyReturnClass = buyReturn === null || Number.isNaN(buyReturn) ? '' : (buyReturn >= 0 ? 'up' : 'down');
  const rank = String(idx + 1).padStart(2, '0');

  return `<article class="candidate-tile">
    <div class="candidate-top">
      <span class="rank">#${rank}</span>
      <span class="badge compact ${statusClass(status)}">${status}</span>
    </div>
    <div class="candidate-title">
      <strong>${c.name || '-'}</strong>
      ${c.code ? `<span class="muted">${c.code}</span>` : ''}
    </div>
    <div class="candidate-main">
      <div class="score-box ${scoreTone}"><span class="muted">판단점수</span><strong>${score}</strong></div>
      <div><span class="muted">등락률</span><strong class="${changeClass}">${change === undefined || change === null ? '-' : `${Number(change).toFixed(2)}%`}</strong></div>
      ${buyReturn === null || Number.isNaN(buyReturn) ? '' : `<div><span class="muted">매수대비</span><strong class="${buyReturnClass}">${pct(buyReturn)}</strong></div>`}
    </div>
    <div class="candidate-meta">
      ${c.rank ? `<span>현재 ${c.rank}위</span>` : ''}
      ${c.evaluatedAt ? `<span>평가 ${formatKst(c.evaluatedAt).slice(11)}</span>` : ''}
      ${theme ? `<span>${theme}</span>` : ''}
      ${meta ? `<span>meta ${meta}</span>` : ''}
      ${rawScore && rawScore !== score ? `<span>원점수 ${rawScore}</span>` : ''}
    </div>
    ${c.candidateNote ? `<details class="candidate-detail"><summary>매수/보유 기준 보기</summary><p>${c.candidateNote}</p></details>` : ''}
    ${c.reason && (!theme && !meta && change === undefined) ? `<p class="candidate-reason">${c.reason}</p>` : ''}
  </article>`;
}

function performanceBlock(s) {
  const pf = s.portfolio || {};
  const cmp = s.comparison || {};
  return `<div class="card strategy-dashboard">
    <div class="card-head">
      <div>
        <h3>${s.name} 전략 대시보드</h3>
        <p class="muted">자산 · 수익률 · 시장 비교</p>
      </div>
      <span class="badge ${statusClass(s.status)}">${s.status}</span>
    </div>
    ${strategyReturnCards(s)}
    ${candidateSummary(s)}
    <div class="kpis comparison-kpis">
      ${kpi('내 누적 수익률', pct(cmp.returnPct))}
      ${kpi('시장 누적 수익률', pct(cmp.benchmarkReturnPct))}
      ${kpi('시장 대비', pct(cmp.excessReturnPct))}
    </div>
    <div class="grid two item-chart-grid">
      <div class="mini-chart">
        <div class="chart-title">평가금액 변동</div>
        <canvas class="item-amount-chart" height="120"></canvas>
      </div>
      <div class="mini-chart">
        <div class="chart-title">수익률 vs 시장</div>
        <canvas class="item-return-chart" height="120"></canvas>
      </div>
    </div>
  </div>`;
}

function candidateList(items) {
  if (!items || !items.length) return '<p class="muted">아직 표시할 후보가 없습니다.</p>';
  return `<div class="candidate-grid">${items.map(candidateTile).join('')}</div>`;
}

function holdingsBlock(pf = {}) {
  const positions = pf.positions || [];
  if (!positions.length) {
    return `<section class="holdings-card">
      <div class="alert-head"><span>보유 항목</span><strong>0</strong></div>
      <p class="muted alert-empty">현재 보유 종목 없음</p>
    </section>`;
  }
  const totalEval = Number(pf.investmentAmount || positions.reduce((sum, p) => sum + Number(p.evalAmount || 0), 0));
  return `<section class="holdings-card">
    <div class="alert-head"><span>보유 항목</span><strong>${positions.length}</strong></div>
    <div class="holding-table-wrap"><table class="holding-table">
      <thead><tr>
        <th>종목명</th><th>종목코드</th><th>보유일</th><th>보유수량</th><th>평가손익<br>수익률(%)</th><th>평가금액<br>매입금액</th><th>현재가<br>평균단가</th><th>전일대비<br>등락률(%)</th><th>보유비중</th>
      </tr></thead>
      <tbody>${positions.map(p => {
        const ret = p.returnPct === null || p.returnPct === undefined || p.returnPct === '' ? null : Number(p.returnPct);
        const retClass = ret === null || Number.isNaN(ret) ? '' : (ret >= 0 ? 'up' : 'down');
        const qty = Number(p.qty || 0);
        const entryAmount = p.entryAmount ?? (qty && p.entryPrice ? qty * Number(p.entryPrice) : null);
        const change = p.currentChangePct ?? p.sourceChangePct;
        const changeNum = change === null || change === undefined || change === '' ? null : Number(change);
        const changeClass = changeNum === null || Number.isNaN(changeNum) ? '' : (changeNum >= 0 ? 'up' : 'down');
        const currentPrice = Number(p.currentPrice || 0);
        const prevPrice = changeNum !== null && !Number.isNaN(changeNum) && currentPrice ? currentPrice / (1 + changeNum / 100) : null;
        const delta = prevPrice ? Math.trunc(currentPrice - prevPrice) : null;
        const weight = totalEval && p.evalAmount ? Number(p.evalAmount) / totalEval * 100 : null;
        const holdingDays = String(p.holdingPeriod || '-').replace(/^보유\s*/, '');
        return `<tr>
          <td class="stock-name" data-label="종목명"><strong>${p.name || '-'}</strong></td>
          <td class="stock-code" data-label="종목코드">${p.code || '-'}</td>
          <td data-label="보유일">${holdingDays}</td>
          <td data-label="보유수량">${fmt.format(qty)}</td>
          <td class="num-pair" data-label="평가손익 / 수익률"><span class="pair-line"><b class="${retClass}">${moneyBare(p.pnl)}</b><small class="${retClass}">${ret === null || Number.isNaN(ret) ? '-' : ret.toFixed(2)}</small></span></td>
          <td class="num-pair" data-label="평가금액 / 매입금액"><span class="pair-line"><b>${moneyBare(p.evalAmount)}</b><small>${entryAmount === null ? '-' : moneyBare(entryAmount)}</small></span></td>
          <td class="num-pair" data-label="현재가 / 평균단가"><span class="pair-line"><b>${moneyBare(p.currentPrice)}</b><small>${moneyBare(p.entryPrice)}</small></span></td>
          <td class="num-pair" data-label="전일대비 / 등락률"><span class="pair-line"><b class="${changeClass}">${delta === null ? '-' : `${delta >= 0 ? '▲ ' : '▼ '}${fmt.format(Math.abs(delta))}`}</b><small class="${changeClass}">${changeNum === null || Number.isNaN(changeNum) ? '-' : changeNum.toFixed(2)}</small></span></td>
          <td data-label="보유비중">${weight === null ? '-' : weight.toFixed(2)}</td>
        </tr>`;
      }).join('')}</tbody>
    </table></div>
  </section>`;
}

function tradeAlerts(s) {
  const renderItems = (items, emptyText) => {
    if (!items || !items.length) return `<p class="muted alert-empty">${emptyText}</p>`;
    return `<div class="alert-items">${items.map(x => {
      const buyReturn = x.returnPct === null || x.returnPct === undefined || x.returnPct === '' ? null : Number(x.returnPct);
      const buyReturnClass = buyReturn === null || Number.isNaN(buyReturn) ? '' : (buyReturn >= 0 ? 'up' : 'down');
      return `<div class="alert-item">
      <div class="alert-item-top">
        <div>
          <strong>${x.name || '-'}</strong>${x.code ? `<span class="muted">${x.code}</span>` : ''}
          <em>${x.status || '검토'}${x.holdingPeriod ? ` · ${x.holdingPeriod}` : ''}</em>
        </div>
        ${buyReturn === null || Number.isNaN(buyReturn) ? '' : `<b class="return-big ${buyReturnClass}">${pct(buyReturn)}</b>`}
      </div>
      ${x.reason ? `<small>${colorizePnlText(x.reason)}</small>` : ''}
    </div>`}).join('')}</div>`;
  };
  return `<div class="trade-alerts">
    <section class="trade-alert buy-alert">
      <div class="alert-head"><span>매수 기록</span><strong>${s.buyAlerts?.length || 0}</strong></div>
      ${renderItems(s.buyAlerts, '매수 기록 없음')}
    </section>
    <section class="trade-alert sell-alert">
      <div class="alert-head"><span>매도 알림</span><strong>${s.sellAlerts?.length || 0}</strong></div>
      ${renderItems(s.sellAlerts, '매도 알림 없음')}
    </section>
  </div>`;
}

function renderSessionCard(s, full = false, showSummary = true) {
  const cmp = s.comparison || {};
  const pf = s.portfolio || {};
  return `${full ? performanceBlock(s) : ''}<article class="card session-card">
    <div class="card-head">
      <div>
        <h3>${full ? '전략 상세' : s.name}</h3>
        <p class="muted">${full ? `${s.name} · ${s.stage}` : s.stage}</p>
      </div>
      <span class="badge ${statusClass(s.status)}">${s.status}</span>
    </div>
    ${showSummary ? `
    ${strategyReturnCards(s)}
    ${candidateSummary(s)}` : ''}
    ${holdingsBlock(pf)}
    ${holdingCandidateComparison(s)}
    <div class="mini-facts">
      <span>검증 ${fmt.format(s.validationCount || 0)}</span>
      <span>보호 ${fmt.format(s.protectedRows || 0)}</span>
      <span>시세 ${fmt.format(s.quoteCount || 0)}</span>
      <span>보유 ${fmt.format(pf.positionCount || 0)}</span>
    </div>
    ${tradeAlerts(s)}
    ${s.topCandidates?.length ? `<details class="strategy-candidates"><summary><span>후보 상세 보기</span><b>${fmt.format(s.topCandidates.length)}개</b></summary><p class="candidate-help"><span class="desktop-help">판단점수는 전략별 원점수를 공통 0~100 구간으로 환산한 실행 강도입니다. 90+ 강매수권, 80+ 우선검토, 70+ 관찰강화, 60 미만은 아직 약함으로 봅니다.</span><span class="mobile-help">판단점수: 90+ 강함 · 80+ 우선 · 70+ 관찰 · 60↓ 약함</span></p>${candidateList(s.topCandidates)}</details>` : ''}
  </article>`;
}

function renderOverviewStrategyCard(s) {
  const cmp = s.comparison || {};
  const pf = s.portfolio || {};
  const basis = basisText(cmp.periodStart);
  return `<article class="card overview-strategy-card">
    <div class="overview-strategy-head">
      <div>
        <h3>${s.name}</h3>
        <p class="muted">${s.stage} · 보유 ${fmt.format(pf.positionCount || 0)}</p>
      </div>
      <span class="badge ${statusClass(s.status)}">${s.status}</span>
    </div>
    <div class="overview-return-row">
      <strong class="${(pf.returnPct || 0) >= 0 ? 'up' : 'down'}">${pct(pf.returnPct)}</strong>
      <span class="today-return ${s.daily?.returnPct == null ? '' : ((s.daily.returnPct || 0) >= 0 ? 'up' : 'down')}">오늘 ${pct(s.daily?.returnPct)}</span>
    </div>
    <div class="basis-line">${basis}</div>
    <div class="overview-compact-metrics">
      <span><b>${compactMoney(pf.capital)}</b><em>원금</em></span>
      <span><b>${compactMoney(pf.investmentAmount)}</b><em>투자</em></span>
      <span><b class="${(pf.pnl || 0) >= 0 ? 'up' : 'down'}">${compactMoney(pf.pnl)}</b><em>수익</em></span>
      <span><b>${fmt.format(s.candidateCount || 0)}</b><em>후보</em></span>
    </div>
  </article>`;
}

function scrollToPanelStart(id) {
  if (id === 'panel-overview') {
    window.scrollTo({ top: 0, behavior: 'auto' });
    return;
  }
  const panel = document.getElementById(id);
  const top = panel ? Math.max(0, panel.getBoundingClientRect().top + window.scrollY - 12) : 0;
  window.scrollTo({ top, behavior: 'auto' });
}

function setActive(id, shouldScroll = true) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.target === id));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === id));
  if (shouldScroll) requestAnimationFrame(() => scrollToPanelStart(id));
}


function render(data) {
  data = enrichSessions(data);
  document.getElementById('updated').textContent = `마지막 갱신: ${formatKst(data.generatedAt)}`;
  const overall = data.summary.staleCount > 0 ? '주의 필요' : '정상/대기';
  document.getElementById('overallStatus').textContent = overall;
  document.getElementById('overallStatus').className = `status-pill ${data.summary.staleCount > 0 ? 'status-STALE' : 'status-OK'}`;

  document.getElementById('summaryGrid').innerHTML = [
    summaryTile('오늘 시장', marketDailyPair(data), '당일 등락률', '📈', (data.benchmark?.dailyReturnPct || 0) >= 0 ? 'good' : 'danger'),
    summaryTile('시장/KODEX 누적', marketCumulativePair(data), basisText(data.benchmark?.periodStart), '📊', (data.benchmark?.returnPct || 0) >= 0 ? 'good' : 'danger'),
    ...data.sessions.map(renderOverviewStrategyCard)
  ].join('');

  const tabs = [{id:'panel-overview', name:'전체 요약'}, ...data.sessions.map((s, idx) => ({id:`panel-${idx}`, name:s.name}))];
  document.getElementById('tabs').innerHTML = tabs.map((t,i) => `<button class="tab ${i===0?'active':''}" data-target="${t.id}">${t.name}</button>`).join('');
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => setActive(t.dataset.target, true)));

  document.getElementById('sessionCards').innerHTML = '';
  document.getElementById('sessionPanels').innerHTML = data.sessions.map((s, i) => `
    <section class="panel" id="panel-${i}">
      ${renderSessionCard(s, true, false)}
    </section>`).join('');

  renderMainCharts(data);
  renderItemCharts(data);
  requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
}

function renderMainCharts(data) {
  const history = chartWindow(data.history);
  const labels = history.map(x => formatKst(x.ts).replace(/^\d{4}-/, ''));
  const names = data.sessions.map(s => s.name);
  const colors = ['#79a7ff', '#35d399', '#ffd166', '#ff8fab', '#c084fc', '#fb923c', '#67e8f9'];

  if (amountChart) amountChart.destroy();
  amountChart = new Chart(document.getElementById('amountChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        ...names.map((name, i) => ({ label: `${name} 평가금액`, data: history.map(x => x.evalAmounts?.[i]), borderColor: colors[i % colors.length], backgroundColor: `${colors[i % colors.length]}22`, tension: .35, spanGaps: true })),
        ...names.map((name, i) => ({ label: `${name} 자본금`, data: history.map(x => x.capital?.[i]), borderColor: colors[i % colors.length], borderDash: [5, 5], pointRadius: 0, tension: 0, spanGaps: true }))
      ]
    },
    options: chartOptions(v => `${fmt.format(v/10000)}만`)
  });

  if (returnChart) returnChart.destroy();
  returnChart = new Chart(document.getElementById('returnChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        ...names.map((name, i) => ({ label: `${name} 수익률`, data: history.map(x => x.returns?.[i]), borderColor: colors[i % colors.length], backgroundColor: `${colors[i % colors.length]}22`, tension: .35, spanGaps: true })),
        { label: 'KOSPI 수익률', data: history.map(x => x.benchmark), borderColor: '#ffffff', borderDash: [6, 5], pointRadius: 0, tension: .2, spanGaps: true },
        { label: 'KODEX200 수익률', data: history.map(x => x.kodex200), borderColor: '#b7ff5a', borderDash: [2, 4], pointRadius: 0, tension: .2, spanGaps: true }
      ]
    },
    options: chartOptions(v => `${v}%`)
  });
}


function renderItemCharts(data) {
  itemCharts.forEach(c => c.destroy());
  itemCharts = [];
  const history = chartWindow(data.history);
  const labels = history.map(x => formatKst(x.ts).replace(/^\d{4}-/, ''));
  const colors = ['#79a7ff', '#35d399', '#ffd166', '#ff8fab', '#c084fc', '#fb923c', '#67e8f9'];

  document.querySelectorAll('.item-amount-chart').forEach((canvas, i) => {
    const color = colors[i % colors.length];
    itemCharts.push(new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: '현재 평가금액', data: history.map(x => x.evalAmounts?.[i]), borderColor: color, backgroundColor: `${color}22`, tension: .35, spanGaps: true },
          { label: '자본금', data: history.map(x => x.capital?.[i]), borderColor: '#ffffff', borderDash: [5, 5], pointRadius: 0, tension: 0, spanGaps: true }
        ]
      },
      options: chartOptions(v => `${fmt.format(v/10000)}만`)
    }));
  });

  document.querySelectorAll('.item-return-chart').forEach((canvas, i) => {
    const color = colors[i % colors.length];
    itemCharts.push(new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: '우리 수익률', data: history.map(x => x.returns?.[i]), borderColor: color, backgroundColor: `${color}22`, tension: .35, spanGaps: true },
          { label: 'KOSPI 수익률', data: history.map(x => x.marketReturns?.[i] ?? null), borderColor: '#ffffff', borderDash: [6, 5], pointRadius: 0, tension: .2, spanGaps: true },
          { label: 'KODEX200 수익률', data: history.map(x => x.kodexReturns?.[i] ?? null), borderColor: '#b7ff5a', borderDash: [2, 4], pointRadius: 0, tension: .2, spanGaps: true }
        ]
      },
      options: chartOptions(v => `${v}%`)
    }));
  });
}

function dashboardUrls() {
  const params = new URLSearchParams(window.location.search);
  return {
    data: params.get('data') || window.DASHBOARD_DATA_URL || 'data/dashboard-data.json',
    manifest: params.get('manifest') || window.DASHBOARD_MANIFEST_URL || '',
  };
}

function fetchJson(url) {
  return fetch(url, { cache: 'no-store' }).then(r => {
    if (!r.ok) throw new Error(`${url} HTTP ${r.status}`);
    return r.json();
  });
}

async function loadDashboardData() {
  const urls = dashboardUrls();
  if (!urls.manifest) return fetchJson(urls.data);

  try {
    const manifest = await fetchJson(urls.manifest);
    const parts = manifest.parts || {};
    if (!parts.summary?.url || !parts.sessions?.url || !parts.history?.url) {
      throw new Error('manifest parts missing');
    }
    const [summaryPart, sessionsPart, historyPart] = await Promise.all([
      fetchJson(parts.summary.url),
      fetchJson(parts.sessions.url),
      fetchJson(parts.history.url),
    ]);
    return {
      ...summaryPart,
      generatedAt: manifest.generatedAt || summaryPart.generatedAt || sessionsPart.generatedAt || historyPart.generatedAt,
      sessions: sessionsPart.sessions || [],
      history: historyPart.history || [],
    };
  } catch (err) {
    console.warn('split JSON load failed; falling back to single dashboard JSON', err);
    return fetchJson(urls.data);
  }
}

loadDashboardData()
  .then(render)
  .catch(err => {
    document.getElementById('updated').textContent = `데이터 로드 실패: ${err.message}`;
  });
