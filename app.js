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

function marketPair(data) {
  return `<span class="market-split">
    <span class="market-pair market-today"><em>오늘</em><span>KOSPI ${pct(data.benchmark?.dailyReturnPct)}</span><span>KODEX ${pct(data.kodexBenchmark?.dailyReturnPct)}</span></span>
    <span class="market-pair market-cumulative"><em>누적</em><span>KOSPI ${pct(data.benchmark?.returnPct)}</span><span>KODEX ${pct(data.kodexBenchmark?.returnPct)}</span></span>
  </span>`;
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


function money(v) {
  if (v === null || v === undefined) return '-';
  return `${fmt.format(v)}원`;
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
    <div class="session-hero">
      <div>
        <span class="muted">후보</span>
        <strong>${fmt.format(s.candidateCount || 0)}</strong>
      </div>
      <div>
        <span class="muted">수익률</span>
        <strong class="${(pf.returnPct || 0) >= 0 ? 'up' : 'down'}">${pct(pf.returnPct)}</strong>
        <small class="market-compare ${cmp.excessReturnPct == null ? '' : ((cmp.excessReturnPct || 0) >= 0 ? 'up' : 'down')}">시장 대비 ${pct(cmp.excessReturnPct)}</small>
      </div>
    </div>
    ${portfolioStrip(pf)}
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
  return `<section class="holdings-card">
    <div class="alert-head"><span>보유 항목</span><strong>${positions.length}</strong></div>
    <div class="holding-items">${positions.map(p => {
      const ret = p.returnPct === null || p.returnPct === undefined || p.returnPct === '' ? null : Number(p.returnPct);
      const retClass = ret === null || Number.isNaN(ret) ? '' : (ret >= 0 ? 'up' : 'down');
      return `<div class="holding-item">
        <div>
          <strong>${p.name || '-'}</strong>${p.code ? `<span class="muted">${p.code}</span>` : ''}
          <em>${fmt.format(p.qty || 0)}주${p.holdingPeriod ? ` · ${p.holdingPeriod}` : ''}</em>
          <small class="muted">매입 ${money(p.entryPrice)} · 현재 ${money(p.currentPrice)} · 평가 ${money(p.evalAmount)}</small>
        </div>
        <div class="holding-numbers">
          <b class="${retClass}">${ret === null || Number.isNaN(ret) ? '-' : pct(ret)}</b>
          <small>${money(p.pnl)}</small>
        </div>
      </div>`;
    }).join('')}</div>
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
    <div class="session-hero">
      <div>
        <span class="muted">후보</span>
        <strong>${fmt.format(s.candidateCount || 0)}</strong>
      </div>
      <div>
        <span class="muted">수익률</span>
        <strong class="${(pf.returnPct || 0) >= 0 ? 'up' : 'down'}">${pct(pf.returnPct)}</strong>
        <small class="market-compare ${cmp.excessReturnPct == null ? '' : ((cmp.excessReturnPct || 0) >= 0 ? 'up' : 'down')}">시장 대비 ${pct(cmp.excessReturnPct)}</small>
      </div>
    </div>
    ${portfolioStrip(pf)}` : ''}
    ${holdingsBlock(pf)}
    <div class="mini-facts">
      <span>검증 ${fmt.format(s.validationCount || 0)}</span>
      <span>보호 ${fmt.format(s.protectedRows || 0)}</span>
      <span>시세 ${fmt.format(s.quoteCount || 0)}</span>
      <span>보유 ${fmt.format(pf.positionCount || 0)}</span>
    </div>
    ${tradeAlerts(s)}
    ${s.topCandidates?.length ? `<div class="strategy-candidates"><h3>후보 타일</h3><p class="candidate-help"><span class="desktop-help">판단점수는 전략별 원점수를 공통 0~100 구간으로 환산한 실행 강도입니다. 90+ 강매수권, 80+ 우선검토, 70+ 관찰강화, 60 미만은 아직 약함으로 봅니다.</span><span class="mobile-help">판단점수: 90+ 강함 · 80+ 우선 · 70+ 관찰 · 60↓ 약함</span></p>${candidateList(s.topCandidates)}</div>` : ''}
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
      <span class="market-compare ${cmp.excessReturnPct == null ? '' : ((cmp.excessReturnPct || 0) >= 0 ? 'up' : 'down')}">시장 대비 ${pct(cmp.excessReturnPct)}</span>
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
  document.getElementById('updated').textContent = `마지막 갱신: ${formatKst(data.generatedAt)}`;
  const overall = data.summary.staleCount > 0 ? '주의 필요' : '정상/대기';
  document.getElementById('overallStatus').textContent = overall;
  document.getElementById('overallStatus').className = `status-pill ${data.summary.staleCount > 0 ? 'status-STALE' : 'status-OK'}`;

  document.getElementById('summaryGrid').innerHTML = [
    summaryTile('시장/KODEX', marketPair(data), basisText(data.benchmark?.periodStart), '📈', (data.benchmark?.returnPct || 0) >= 0 ? 'good' : 'danger'),
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
