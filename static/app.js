// Where Did My Day Go dashboard client

const CATEGORY_COLORS = {
  claude_desktop: getCssVar('--c-claude_desktop'),
  claude_code:    getCssVar('--c-claude_code'),
  chatgpt:        getCssVar('--c-chatgpt'),
  chrome:         getCssVar('--c-chrome'),
  vscode:         getCssVar('--c-vscode'),
  cursor:         getCssVar('--c-cursor'),
  terminal:       getCssVar('--c-terminal'),
  xcode:          getCssVar('--c-xcode'),
  slack:          getCssVar('--c-slack'),
  discord:        getCssVar('--c-discord'),
  messages:       getCssVar('--c-messages'),
  mail:           getCssVar('--c-mail'),
  safari:         getCssVar('--c-safari'),
  firefox:        getCssVar('--c-firefox'),
  spotify:        getCssVar('--c-spotify'),
  calendar:       getCssVar('--c-calendar'),
  figma:          getCssVar('--c-figma'),
  notion:         getCssVar('--c-notion'),
  obs:            getCssVar('--c-obs'),
  excel:          getCssVar('--c-excel'),
  word:           getCssVar('--c-word'),
  powerpoint:     getCssVar('--c-powerpoint'),
  outlook:        getCssVar('--c-outlook'),
  postman:        getCssVar('--c-postman'),
  vlc:            getCssVar('--c-vlc'),
  finder:         getCssVar('--c-finder'),
  preview:        getCssVar('--c-preview'),
  quicktime:      getCssVar('--c-quicktime'),
  dashboard:      getCssVar('--c-dashboard'),
  other:          getCssVar('--c-other'),
  idle:           getCssVar('--c-idle'),
};

const CATEGORY_LABELS = {
  claude_desktop: 'Claude (desktop)',
  claude_code:    'Claude Code (terminal)',
  chatgpt:        'ChatGPT',
  chrome:         'Chrome',
  vscode:         'VS Code',
  cursor:         'Cursor',
  terminal:       'Terminal',
  xcode:          'Xcode',
  slack:          'Slack',
  discord:        'Discord',
  messages:       'Messages',
  mail:           'Mail',
  safari:         'Safari',
  firefox:        'Firefox',
  spotify:        'Spotify',
  calendar:       'Calendar',
  figma:          'Figma',
  notion:         'Notion',
  obs:            'OBS',
  excel:          'Excel',
  word:           'Word',
  powerpoint:     'PowerPoint',
  outlook:        'Outlook',
  postman:        'Postman',
  vlc:            'VLC',
  finder:         'Finder',
  preview:        'Preview',
  quicktime:      'QuickTime',
  dashboard:      'Dashboard (meta)',
  other:          'Other',
  idle:           'Away from desk',
};

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function fmtDuration(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function fmtClock(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtClockSec(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function todayStr() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function shiftDate(s, deltaDays) {
  const [y, m, d] = s.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + deltaDays);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
}

// ------------------------------------------------------------------

const state = {
  date: todayStr(),
  autoRefresh: true,
  hourlyChart: null,
  categoryChart: null,
  lastFetchTs: 0,
};

const els = {
  picker: document.getElementById('date-picker'),
  prev: document.getElementById('prev-day'),
  next: document.getElementById('next-day'),
  today: document.getElementById('today-btn'),
  autoRefresh: document.getElementById('auto-refresh'),
  timeline: document.getElementById('timeline'),
  timelineAxis: document.getElementById('timeline-axis'),
  timelineDate: document.getElementById('timeline-date'),
  legend: document.getElementById('legend'),
  hover: document.getElementById('hover-info'),
  appsBody: document.querySelector('#apps-table tbody'),
  urlsBody: document.querySelector('#urls-table tbody'),
  footer: document.getElementById('footer-status'),
};

els.picker.value = state.date;

els.picker.addEventListener('change', () => {
  state.date = els.picker.value || todayStr();
  refresh();
});
els.prev.addEventListener('click', () => {
  state.date = shiftDate(state.date, -1);
  els.picker.value = state.date;
  refresh();
});
els.next.addEventListener('click', () => {
  state.date = shiftDate(state.date, 1);
  els.picker.value = state.date;
  refresh();
});
els.today.addEventListener('click', () => {
  state.date = todayStr();
  els.picker.value = state.date;
  refresh();
});
els.autoRefresh.addEventListener('change', e => {
  state.autoRefresh = e.target.checked;
});

// ------------------------------------------------------------------

async function refresh() {
  els.timelineDate.textContent = state.date === todayStr() ? `today (${state.date})` : state.date;
  try {
    const [summary, timeline] = await Promise.all([
      fetch(`/api/summary?date=${state.date}`).then(r => r.json()),
      fetch(`/api/timeline?date=${state.date}`).then(r => r.json()),
    ]);
    renderKpis(summary);
    renderTimeline(timeline, summary);
    renderHourly(summary);
    renderCategoryChart(summary);
    renderApps(summary);
    renderUrls(summary);
    renderLegend(summary);
    state.lastFetchTs = Date.now();
    els.footer.textContent = `Updated ${new Date().toLocaleTimeString()} · ${timeline.intervals.length} intervals · DB: ${fmtDuration(summary.tracked_seconds)} tracked`;
  } catch (e) {
    console.error(e);
    els.footer.textContent = `Error: ${e.message}`;
  }
}

function renderKpis(summary) {
  const cats = Object.fromEntries(summary.categories.map(c => [c.category, c.seconds]));
  const claude = (cats.claude_desktop || 0) + (cats.claude_code || 0);
  const tracked = summary.tracked_seconds || 1;

  setKpi('active',   summary.active_seconds, summary.active_seconds / tracked);
  setKpi('idle',     summary.idle_seconds,   summary.idle_seconds / tracked);
  setKpi('claude',   claude,                 claude / tracked);
  setKpi('chrome',   cats.chrome || 0,       (cats.chrome || 0) / tracked);
  setKpi('vscode',   cats.vscode || 0,       (cats.vscode || 0) / tracked);
  setKpi('terminal', cats.terminal || 0,     (cats.terminal || 0) / tracked);
}

function setKpi(key, seconds, share) {
  document.getElementById(`kpi-${key}`).textContent = fmtDuration(seconds);
  const sub = document.getElementById(`kpi-${key}-sub`);
  if (sub) {
    sub.textContent = seconds > 0 ? `${(share * 100).toFixed(1)}% of tracked` : '—';
  }
}

function renderTimeline(timeline, summary) {
  els.timeline.innerHTML = '';
  els.timelineAxis.innerHTML = '';

  const dayStart = timeline.start_ts;
  const dayEnd = timeline.start_ts + 86400; // always render full 24h scale
  const total = dayEnd - dayStart;

  for (const iv of timeline.intervals) {
    const seg = document.createElement('div');
    seg.className = 'seg';
    const leftPct = ((iv.start_ts - dayStart) / total) * 100;
    const widthPct = ((iv.end_ts - iv.start_ts) / total) * 100;
    seg.style.left = `${leftPct}%`;
    seg.style.width = `${Math.max(0.02, widthPct)}%`;
    seg.style.background = CATEGORY_COLORS[iv.category] || CATEGORY_COLORS.other;
    seg.dataset.iv = JSON.stringify(iv);
    seg.addEventListener('mouseenter', onHoverSeg);
    seg.addEventListener('mouseleave', () => { els.hover.textContent = 'Hover the timeline for details'; });
    els.timeline.appendChild(seg);
  }

  // axis ticks every 3h
  for (let h = 0; h <= 24; h += 3) {
    const tick = document.createElement('div');
    tick.className = 'tick';
    tick.style.left = `${(h / 24) * 100}%`;
    tick.textContent = h === 24 ? '24:00' : `${String(h).padStart(2, '0')}:00`;
    els.timelineAxis.appendChild(tick);
  }
}

function onHoverSeg(e) {
  const iv = JSON.parse(e.currentTarget.dataset.iv);
  const dur = fmtDuration(iv.duration);
  const label = CATEGORY_LABELS[iv.category] || iv.category;
  const title = iv.window_title || '(no title)';
  const url = iv.chrome_url ? `  ${iv.chrome_url}` : '';
  els.hover.innerHTML = `<b>${label}</b> · ${iv.app_name} · ${fmtClockSec(iv.start_ts)}–${fmtClockSec(iv.end_ts)} (${dur})<br><span style="opacity:0.7">${escapeHtml(title)}${escapeHtml(url)}</span>`;
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"]/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]
  ));
}

function renderLegend(summary) {
  const cats = summary.categories.map(c => c.category);
  els.legend.innerHTML = '';
  for (const c of cats) {
    const it = document.createElement('span');
    it.className = 'item';
    it.innerHTML = `<span class="swatch" style="background:${CATEGORY_COLORS[c] || CATEGORY_COLORS.other}"></span>${CATEGORY_LABELS[c] || c}`;
    els.legend.appendChild(it);
  }
}

function renderHourly(summary) {
  const ctx = document.getElementById('hourly-chart');
  const hours = [...Array(24).keys()];
  const cats = new Set();
  for (const h of hours) {
    for (const c of Object.keys(summary.hourly[h] || {})) cats.add(c);
  }
  // pleasing order: claude_code, claude_desktop, vscode, terminal, chrome, then alpha, idle last
  const ORDER = ['claude_code','claude_desktop','chatgpt','vscode','cursor','terminal','chrome','safari','firefox','postman','slack','discord','messages','mail','outlook','spotify','figma','notion','calendar','xcode','excel','word','powerpoint','preview','quicktime','vlc','obs','finder','dashboard','other','idle'];
  const ordered = [...cats].sort((a,b) => (ORDER.indexOf(a) - ORDER.indexOf(b)));

  const datasets = ordered.map(c => ({
    label: CATEGORY_LABELS[c] || c,
    data: hours.map(h => Math.round(((summary.hourly[h] || {})[c] || 0) / 60)), // minutes
    backgroundColor: CATEGORY_COLORS[c] || CATEGORY_COLORS.other,
    borderWidth: 0,
    stack: 'a',
  }));

  if (state.hourlyChart) state.hourlyChart.destroy();
  state.hourlyChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: hours.map(h => String(h).padStart(2,'0')),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}m`,
          }
        }
      },
      scales: {
        x: { stacked: true, ticks: { color: '#8b949e' }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { stacked: true, max: 60, ticks: { color: '#8b949e', stepSize: 15, callback: v => v + 'm' }, grid: { color: 'rgba(255,255,255,0.04)' } },
      },
    },
  });
}

function renderCategoryChart(summary) {
  const ctx = document.getElementById('category-chart');
  const labels = summary.categories.map(c => CATEGORY_LABELS[c.category] || c.category);
  const data = summary.categories.map(c => Math.round(c.seconds / 60));
  const colors = summary.categories.map(c => CATEGORY_COLORS[c.category] || CATEGORY_COLORS.other);

  if (state.categoryChart) state.categoryChart.destroy();
  state.categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: '#161b22', borderWidth: 2 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { color: '#e6edf3', boxWidth: 10, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.label}: ${fmtDuration(ctx.parsed * 60)}`,
          }
        }
      },
      cutout: '55%',
    },
  });
}

function renderApps(summary) {
  els.appsBody.innerHTML = '';
  const total = summary.apps.reduce((s, a) => s + a.seconds, 0) || 1;
  for (const a of summary.apps) {
    const tr = document.createElement('tr');
    const share = a.seconds / total;
    tr.innerHTML = `
      <td>${escapeHtml(a.app_name)}</td>
      <td><span class="cat-pill" style="color:${CATEGORY_COLORS[a.category] || CATEGORY_COLORS.other}">${CATEGORY_LABELS[a.category] || a.category}</span></td>
      <td class="num">${fmtDuration(a.seconds)}</td>
      <td>
        <div class="bar-cell"><div class="fill" style="width:${(share * 100).toFixed(1)}%;background:${CATEGORY_COLORS[a.category] || CATEGORY_COLORS.other}"></div></div>
      </td>
    `;
    els.appsBody.appendChild(tr);
  }
  if (summary.apps.length === 0) {
    els.appsBody.innerHTML = '<tr><td colspan="4" style="color:#8b949e">No active app data yet for this day.</td></tr>';
  }
}

function renderUrls(summary) {
  els.urlsBody.innerHTML = '';
  for (const u of summary.urls) {
    const tr = document.createElement('tr');
    const safeUrl = escapeHtml(u.chrome_url);
    tr.innerHTML = `
      <td class="url-cell"><a href="${safeUrl}" target="_blank" rel="noopener">${safeUrl}</a></td>
      <td class="num">${fmtDuration(u.seconds)}</td>
    `;
    els.urlsBody.appendChild(tr);
  }
  if (summary.urls.length === 0) {
    els.urlsBody.innerHTML = '<tr><td colspan="2" style="color:#8b949e">No Chrome tab data yet. Grant Automation permission to Chrome when prompted.</td></tr>';
  }
}

// ------------------------------------------------------------------

refresh();
setInterval(() => {
  if (state.autoRefresh && state.date === todayStr()) refresh();
}, 15000);
