const fmt = new Intl.NumberFormat('ko-KR');
let DATA = null;
let activeFilter = 'ALL';
let activeReference = 'open';

const filters = [
  ['ALL', '전체'],
  ['ENTRY_REVIEW', '진입검토'],
  ['WATCH_ONLY', '관찰'],
  ['BLOCK_CHASE', '추격금지'],
  ['BLOCK_OVERHEAT', '과열금지'],
  ['BLOCK_FALLING', '급락금지'],
];

function money(value) {
  const n = Number(value || 0);
  const sign = n > 0 ? '+' : n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (abs >= 100000000) return `${sign}${(abs / 100000000).toFixed(1)}억`;
  if (abs >= 10000) return `${sign}${(abs / 10000).toFixed(0)}만`;
  return `${sign}${fmt.format(abs)}`;
}

function pct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const n = Number(value);
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function cls(value) {
  return Number(value || 0) >= 0 ? 'up' : 'down';
}

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function card(label, value, note, toneValue) {
  return `<article class="summary-card">
    <span>${escapeHtml(label)}</span>
    <strong class="${toneValue === undefined ? '' : cls(toneValue)}">${escapeHtml(value)}</strong>
    <small>${escapeHtml(note || '')}</small>
  </article>`;
}

function renderSummary() {
  const legacy = DATA.legacySummary || {};
  const next = DATA.newVersion || {};
  document.getElementById('summaryGrid').innerHTML = [
    card('레거시 총수익률', pct(legacy.totalReturnPct), `손익 ${money(legacy.totalPnl)}`, legacy.totalPnl),
    card('신규 버전', next.name || 'Survival V1', next.orderMode || 'virtual-only'),
    card('신규 현금', money(next.cash), `가상자본 ${money(next.capital)}`),
    card('신규 포지션', `${fmt.format(next.positionCount || 0)}개`, '기존 보유 승계 없음'),
    card('승격 조건', '5~10거래일', '자동손절/평균손실/시장대비 검증'),
  ].join('');
}

function benchmarkCard(label, start, current, returnPct, note) {
  const startValue = start?.value == null ? '-' : fmt.format(start.value);
  const currentValue = current?.value == null ? '-' : fmt.format(current.value);
  return `<article class="benchmark-card">
    <span>${escapeHtml(label)}</span>
    <strong class="${cls(returnPct)}">${pct(returnPct)}</strong>
    <small>시작 ${escapeHtml(startValue)} / 현재 ${escapeHtml(currentValue)}</small>
    <small>${escapeHtml(note || '')}</small>
  </article>`;
}

function renderBenchmarks() {
  const start = DATA.benchmarkStart || {};
  const current = DATA.benchmarkCurrent || {};
  const latest = (DATA.performanceHistory || []).at(-1) || {};
  document.getElementById('benchmarkCards').innerHTML = [
    benchmarkCard('Survival V1', start.survival, { value: latest.survivalEvalAmount }, latest.survivalReturnPct, start.startedAt || ''),
    benchmarkCard('KOSPI', start.kospi, current.kospi, latest.kospiReturnPct, `${current.kospi?.date || ''} ${current.kospi?.time || ''}`),
    benchmarkCard('KODEX 200TR', start.kodex200tr, current.kodex200tr, latest.kodex200trReturnPct, `${current.kodex200tr?.date || ''} ${current.kodex200tr?.time || ''}`),
  ].join('');
}

function seriesPath(points, key, x, y) {
  return points.map((p, index) => {
    const value = Number(p[key] || 0);
    return `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`;
  }).join(' ');
}

function seriesDots(points, key, x, y, klass) {
  return points.map((p, index) => {
    const value = Number(p[key] || 0);
    return `<circle class="chart-dot ${klass}" cx="${x(index).toFixed(1)}" cy="${y(value).toFixed(1)}" r="4"><title>${escapeHtml(p.ts || '')} ${pct(value)}</title></circle>`;
  }).join('');
}

function renderChart() {
  const points = DATA.performanceHistory || [];
  const box = document.getElementById('returnChart');
  if (!points.length) {
    box.innerHTML = '<p class="muted">그래프 데이터 대기</p>';
    return;
  }
  const values = points.flatMap(p => [
    Number(p.survivalReturnPct || 0),
    Number(p.kospiReturnPct || 0),
    Number(p.kodex200trReturnPct || 0),
  ]);
  const min = Math.min(-1, ...values);
  const max = Math.max(1, ...values);
  const pad = Math.max(1, (max - min) * 0.18);
  const yMin = min - pad;
  const yMax = max + pad;
  const w = 720;
  const h = 240;
  const left = 50;
  const right = 20;
  const top = 20;
  const bottom = 36;
  const innerW = w - left - right;
  const innerH = h - top - bottom;
  const x = index => points.length === 1 ? left + innerW / 2 : left + (innerW * index / (points.length - 1));
  const y = value => top + ((yMax - value) / (yMax - yMin)) * innerH;
  const ticks = [yMin, 0, yMax];
  box.innerHTML = `
    <div class="chart-legend">
      <span class="survival"><i></i>Survival V1</span>
      <span class="kospi"><i></i>KOSPI</span>
      <span class="kodex"><i></i>KODEX 200TR</span>
    </div>
    <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="누적 수익률 비교 그래프">
      ${ticks.map(t => `<line class="chart-grid" x1="${left}" x2="${w - right}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}"></line>
        <text class="chart-label" x="10" y="${(y(t) + 4).toFixed(1)}">${pct(t)}</text>`).join('')}
      <line class="chart-axis" x1="${left}" x2="${w - right}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}"></line>
      <path class="chart-line survival" d="${seriesPath(points, 'survivalReturnPct', x, y)}"></path>
      <path class="chart-line kospi" d="${seriesPath(points, 'kospiReturnPct', x, y)}"></path>
      <path class="chart-line kodex" d="${seriesPath(points, 'kodex200trReturnPct', x, y)}"></path>
      ${seriesDots(points, 'survivalReturnPct', x, y, 'survival')}
      ${seriesDots(points, 'kospiReturnPct', x, y, 'kospi')}
      ${seriesDots(points, 'kodex200trReturnPct', x, y, 'kodex')}
      <text class="chart-label" x="${left}" y="${h - 10}">시작</text>
      <text class="chart-label" x="${w - right - 36}" y="${h - 10}">현재</text>
    </svg>`;
}

function renderPolicy() {
  document.getElementById('policyList').innerHTML = (DATA.policy || []).map(rule => `
    <div class="rule">
      <b>${escapeHtml(rule.label)}</b>
      <p>${escapeHtml(rule.detail)}</p>
    </div>
  `).join('');
}

function renderPatterns() {
  document.getElementById('failurePatterns').innerHTML = (DATA.failurePatterns || []).map(item => `
    <div class="pattern">
      <span class="muted">${escapeHtml(item.title)}</span>
      <strong>${escapeHtml(item.metric)}</strong>
      <p>${escapeHtml(item.note)}</p>
    </div>
  `).join('');
}

function renderFilterTabs() {
  document.getElementById('filterTabs').innerHTML = filters.map(([key, label]) => `
    <button class="segment ${activeFilter === key ? 'active' : ''}" data-filter="${key}" type="button">${label}</button>
  `).join('');
  document.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      activeFilter = btn.dataset.filter;
      renderFilterTabs();
      renderWatchlist();
    });
  });
}

function renderWatchlist() {
  const rows = (DATA.watchlist || []).filter(row => activeFilter === 'ALL' || row.action === activeFilter);
  document.getElementById('watchlist').innerHTML = rows.map(row => `
    <article class="watch-card">
      <div class="watch-top">
        <div>
          <h3>${escapeHtml(row.name)}</h3>
          <span class="code">${escapeHtml(row.code)} · ${escapeHtml(row.source || '')}</span>
        </div>
        <span class="action ${escapeHtml(row.action)}">${escapeHtml(row.action)}</span>
      </div>
      <div class="watch-meta">
        <div><span>점수</span><b>${row.score == null ? '-' : escapeHtml(row.score)}</b></div>
        <div><span>등락률</span><b class="${cls(row.changePct)}">${pct(row.changePct)}</b></div>
        <div><span>현재가</span><b>${row.price ? fmt.format(row.price) : '-'}</b></div>
      </div>
      <p>${escapeHtml(row.reason || '')}</p>
    </article>
  `).join('') || '<p class="muted">해당 조건 후보 없음</p>';
}

function renderLegacySessions() {
  const rows = DATA.legacySessions || [];
  document.getElementById('legacySessions').innerHTML = `<table>
    <thead><tr><th>세션</th><th>수익률</th><th>손익</th><th>매도</th><th>손실매도</th><th>실현손익</th></tr></thead>
    <tbody>
      ${rows.map(row => `<tr>
        <td>${escapeHtml(row.label)}</td>
        <td class="${cls(row.returnPct)}">${pct(row.returnPct)}</td>
        <td class="${cls(row.pnl)}">${money(row.pnl)}</td>
        <td>${fmt.format(row.sellCount || 0)}</td>
        <td>${fmt.format(row.lossSellCount || 0)}</td>
        <td class="${cls(row.realizedPnl)}">${money(row.realizedPnl)}</td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

function renderReferenceTabs() {
  const tabs = [['open', '현재 보유 참고'], ['stops', '최악 손절']];
  document.getElementById('referenceTabs').innerHTML = tabs.map(([key, label]) => `
    <button class="segment ${activeReference === key ? 'active' : ''}" data-ref="${key}" type="button">${label}</button>
  `).join('');
  document.querySelectorAll('[data-ref]').forEach(btn => {
    btn.addEventListener('click', () => {
      activeReference = btn.dataset.ref;
      renderReferenceTabs();
      renderReferenceBody();
    });
  });
}

function renderReferenceBody() {
  if (activeReference === 'stops') {
    document.getElementById('referenceBody').innerHTML = `<div class="ref-list">
      ${(DATA.worstStops || []).map(item => `<div class="ref-item">
        <div>
          <strong>${escapeHtml(item.name)} <span class="code">${escapeHtml(item.code)}</span></strong>
          <p>${escapeHtml(item.sessionLabel || '')} · ${escapeHtml(item.date || '')} · ${escapeHtml(item.reason || '')}</p>
        </div>
        <strong class="down">${money(item.realizedPnl)} · ${pct(item.realizedReturnPct)}</strong>
      </div>`).join('')}
    </div>`;
    return;
  }
  document.getElementById('referenceBody').innerHTML = `<div class="ref-list">
    ${(DATA.referenceOpenPositions || []).map(item => `<div class="ref-item">
      <div>
        <strong>${escapeHtml(item.name)} <span class="code">${escapeHtml(item.code)}</span></strong>
        <p>${escapeHtml(item.sessionLabel || '')} · 기존 보유 참고만, Survival V1 자동 승계 없음</p>
      </div>
      <strong class="${cls(item.unrealizedPnl)}">${money(item.unrealizedPnl)} · ${pct(item.returnPct)}</strong>
    </div>`).join('')}
  </div>`;
}

function render() {
  document.getElementById('updated').textContent = `생성 ${DATA.generatedAt || '-'} · 원본 ${DATA.sourceDashboardGeneratedAt || '-'}`;
  document.getElementById('orderMode').textContent = DATA.status || 'VIRTUAL_ONLY';
  renderSummary();
  renderBenchmarks();
  renderChart();
  renderPolicy();
  renderPatterns();
  renderFilterTabs();
  renderWatchlist();
  renderLegacySessions();
  renderReferenceTabs();
  renderReferenceBody();
}

fetch('data/survival-v1.json?ts=' + Date.now())
  .then(res => res.json())
  .then(data => {
    DATA = data;
    render();
  })
  .catch(err => {
    document.getElementById('updated').textContent = 'data load failed';
    document.querySelector('main').insertAdjacentHTML('afterbegin', `<p class="muted">${escapeHtml(err.message)}</p>`);
  });
