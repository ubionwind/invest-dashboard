const fmt = new Intl.NumberFormat('ko-KR');
const dtFmt = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
let amountChart;
let returnChart;
let itemCharts = [];
const isMobile = () => window.matchMedia('(max-width: 850px)').matches;
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

function chartWindow(history) {
  const arr = history || [];
  return isMobile() ? arr.slice(-12) : arr;
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
  const change = parts['등락률'];
  const theme = parts.theme;
  const meta = parts.meta;
  const status = c.status || '검토';
  const score = c.score === null || c.score === undefined || c.score === '' ? '-' : Number(c.score).toFixed(1);
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
      <div><span class="muted">점수</span><strong>${score}</strong></div>
      <div><span class="muted">등락률</span><strong class="${changeClass}">${change === undefined ? '-' : `${change}%`}</strong></div>
      ${buyReturn === null || Number.isNaN(buyReturn) ? '' : `<div><span class="muted">매수대비</span><strong class="${buyReturnClass}">${pct(buyReturn)}</strong></div>`}
    </div>
    <div class="candidate-meta">
      ${theme ? `<span>${theme}</span>` : ''}
      ${meta ? `<span>meta ${meta}</span>` : ''}
    </div>
    ${c.reason && (!theme && !meta && change === undefined) ? `<p class="candidate-reason">${c.reason}</p>` : ''}
  </article>`;
}

function performanceBlock(s) {
  const pf = s.portfolio || {};
  const cmp = s.comparison || {};
  return `<div class="card">
    <div class="card-head"><h3>자산 / 수익률</h3><span class="muted">요약</span></div>
    <div class="kpis">
      ${kpi('자본금', money(pf.capital))}
      ${kpi('현재 평가금액', money(pf.evalAmount))}
      ${kpi('평가손익', money(pf.pnl))}
      ${kpi('누적 수익률', pct(pf.returnPct))}
    </div>
    <div class="kpis comparison-kpis">
      ${kpi('내 누적 수익률', pct(cmp.returnPct))}
      ${kpi('시장 누적 수익률', pct(cmp.benchmarkReturnPct))}
      ${kpi('시장 대비', pct(cmp.excessReturnPct))}
    </div>
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

function renderSessionCard(s, full = false) {
  const cmp = s.comparison || {};
  const pf = s.portfolio || {};
  return `<article class="card session-card">
    <div class="card-head">
      <div>
        <h3>${s.name}</h3>
        <p class="muted">${s.stage}</p>
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
    <div class="mini-facts">
      <span>검증 ${fmt.format(s.validationCount || 0)}</span>
      <span>보호 ${fmt.format(s.protectedRows || 0)}</span>
      <span>시세 ${fmt.format(s.quoteCount || 0)}</span>
      <span>보유 ${fmt.format(pf.positionCount || 0)}</span>
    </div>
    ${tradeAlerts(s)}
    ${full ? `<h3>후보/검토 목록</h3>${candidateList(s.topCandidates)}` : ''}
  </article>${full ? performanceBlock(s) : ''}`;
}

function overviewCandidateTiles(sessions) {
  const items = (sessions || []).flatMap(s => (s.topCandidates || []).slice(0, 4).map(c => ({...c, sessionName: s.name})));
  if (!items.length) return '';
  return `<div class="card overview-candidates">
    <div class="card-head"><h2>후보 타일</h2><span class="muted">모바일 빠른 확인</span></div>
    <div class="candidate-grid overview-candidate-grid">${items.map((c, i) => candidateTile({...c, status: c.sessionName}, i)).join('')}</div>
  </div>`;
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
    summaryTile('관리 항목', fmt.format(data.summary.totalSessions), '전체 운용/관찰 대상', '📌'),
    summaryTile('전체 누적 수익률', pct(data.summary.totalReturnPct), `손익 ${money(data.summary.totalPnl)} / 평가 ${money(data.summary.totalEvalAmount)}`, '💰', (data.summary.totalReturnPct || 0) >= 0 ? 'good' : 'danger'),
    summaryTile('전체 후보', fmt.format(data.summary.candidateCount), '검토 대상 종목 수', '🧩'),
    summaryTile('주의 상태', fmt.format(data.summary.staleCount), '확인 필요 항목', data.summary.staleCount > 0 ? '⚠️' : '✅', data.summary.staleCount > 0 ? 'danger' : 'good'),
    summaryTile('시장 누적 수익률', data.benchmark?.returnPct == null ? '-' : pct(data.benchmark.returnPct), `${benchmarkNote(data.benchmark)} · ${comparisonHelp()}`, '📈', (data.benchmark?.returnPct || 0) >= 0 ? 'good' : 'danger')
  ].join('');

  const tabs = [{id:'panel-overview', name:'전체 요약'}, ...data.sessions.map((s, idx) => ({id:`panel-${idx}`, name:s.name}))];
  document.getElementById('tabs').innerHTML = tabs.map((t,i) => `<button class="tab ${i===0?'active':''}" data-target="${t.id}">${t.name}</button>`).join('');
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => setActive(t.dataset.target, true)));

  document.getElementById('sessionCards').innerHTML = data.sessions.map(s => renderSessionCard(s)).join('') + overviewCandidateTiles(data.sessions);
  document.getElementById('sessionPanels').innerHTML = data.sessions.map((s, i) => `
    <section class="panel" id="panel-${i}">
      ${renderSessionCard(s, true)}
    </section>`).join('');

  renderMainCharts(data);
  renderItemCharts(data);
  requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
}

function renderMainCharts(data) {
  const history = chartWindow(data.history);
  const labels = history.map(x => formatKst(x.ts).replace(/^\d{4}-/, ''));
  const names = data.sessions.map(s => s.name);
  const colors = ['#79a7ff', '#35d399', '#ffd166', '#ff8fab'];

  if (amountChart) amountChart.destroy();
  amountChart = new Chart(document.getElementById('amountChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        ...names.map((name, i) => ({ label: `${name} 평가금액`, data: history.map(x => x.evalAmounts?.[i]), borderColor: colors[i], backgroundColor: `${colors[i]}22`, tension: .35, spanGaps: true })),
        ...names.map((name, i) => ({ label: `${name} 자본금`, data: history.map(x => x.capital?.[i]), borderColor: colors[i], borderDash: [5, 5], pointRadius: 0, tension: 0, spanGaps: true }))
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
        ...names.map((name, i) => ({ label: `${name} 수익률`, data: history.map(x => x.returns?.[i]), borderColor: colors[i], backgroundColor: `${colors[i]}22`, tension: .35, spanGaps: true })),
        { label: '시장 기간 수익률', data: history.map(x => x.benchmark), borderColor: '#ffffff', borderDash: [6, 5], pointRadius: 0, tension: .2, spanGaps: true }
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
  const colors = ['#79a7ff', '#35d399', '#ffd166', '#ff8fab'];

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
          { label: '시장 기간 수익률', data: history.map(x => x.marketReturns?.[i] ?? null), borderColor: '#ffffff', borderDash: [6, 5], pointRadius: 0, tension: .2, spanGaps: true }
        ]
      },
      options: chartOptions(v => `${v}%`)
    }));
  });
}

fetch('data/dashboard-data.json', { cache: 'no-store' })
  .then(r => r.json())
  .then(render)
  .catch(err => {
    document.getElementById('updated').textContent = `데이터 로드 실패: ${err.message}`;
  });
