/* planA — shared frontend utilities */

// ── HTML escaping ─────────────────────────────────────────────────────────────

function esc(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── DOM helpers ───────────────────────────────────────────────────────────────

function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

function fmtDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function ragClass(rag) {
  const map = { green: 'rag-green', amber: 'rag-amber', red: 'rag-red' };
  return map[rag] || 'rag-none';
}

function progressClass(pct) {
  if (pct >= 100) return 'critical';
  if (pct >= 80)  return 'warning';
  return '';
}

function stateBadgeClass(state) {
  return { primacy: 'badge-primacy', drifting: 'badge-drifting', active: 'badge-active',
           subordinate: 'badge-subordinate', draft: 'badge-draft' }[state] || 'badge-active';
}

function stateLabel(state) {
  return { primacy: 'planA', drifting: 'Drifting', active: 'Active',
           subordinate: 'Subordinate', draft: 'Draft' }[state] || state;
}

function stateBadge(state) {
  return `<span class="badge ${stateBadgeClass(state)}">${stateLabel(state)}</span>`;
}

// ── API ───────────────────────────────────────────────────────────────────────

async function apiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Capture bar ───────────────────────────────────────────────────────────────

function initCaptureBar() {
  const form     = document.getElementById('capture-form');
  const input    = document.getElementById('capture-input');
  const btn      = document.getElementById('capture-btn');
  const feedback = document.getElementById('capture-feedback');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    btn.disabled = true;
    feedback.textContent = 'Sending…';

    try {
      const res = await fetch('/v1/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      feedback.textContent = data.response || 'Logged.';
      input.value = '';
    } catch {
      feedback.textContent = 'Could not connect.';
    } finally {
      btn.disabled = false;
    }
  });
}

// prefill the capture bar (used by goal card buttons)
function prefillCapture(text) {
  const input = document.getElementById('capture-input');
  if (input) { input.value = text; input.focus(); }
}

// ── Now view ──────────────────────────────────────────────────────────────────

async function loadNow() {
  try {
    const d = await apiFetch('/v1/now');
    renderPerpetualGoals(d.perpetual_goals   || []);
    renderThisWeekMilestones(d.this_week_milestones || []);
    renderGoalsWithDeadlines(d.goals_with_deadlines || []);
    renderResources(d.resources || {});
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<div class="error-state">Failed to load: ${esc(err.message)}</div>`;
  }
}

function renderPerpetualGoals(goals) {
  if (!goals.length) {
    setHTML('perpetual-goals', '<div class="empty-state">No perpetual goals active.</div>');
    return;
  }
  setHTML('perpetual-goals', goals.map(g => {
    const val   = g.current_value != null ? g.current_value : '—';
    const range = (g.target_min != null || g.target_max != null)
      ? `target ${g.target_min ?? '—'} – ${g.target_max ?? '—'}` : '';
    return `
      <div class="metric-row">
        <span class="rag-dot ${ragClass(g.rag)}"></span>
        <span class="metric-name">${esc(g.title)}</span>
        <span class="metric-value">${val}</span>
        ${range ? `<span class="metric-range">${esc(range)}</span>` : ''}
      </div>`;
  }).join(''));
}

function renderThisWeekMilestones(milestones) {
  if (!milestones.length) {
    setHTML('this-week-milestones', '<div class="empty-state">No milestones due this week.</div>');
    return;
  }
  setHTML('this-week-milestones', milestones.map(m => `
    <div class="milestone-row">
      <span class="milestone-state ${m.state}"></span>
      <div style="flex:1;min-width:0">
        <div class="milestone-goal">${esc(m.goal_title)}</div>
        <div>${esc(m.title)}</div>
      </div>
      ${m.target_date ? `<span class="milestone-date">${fmtDate(m.target_date)}</span>` : ''}
    </div>`).join(''));
}

function renderGoalsWithDeadlines(goals) {
  if (!goals.length) {
    setHTML('deadline-goals', '<div class="empty-state">No goals with deadlines.</div>');
    return;
  }
  setHTML('deadline-goals', goals.map(g => {
    const urgent = g.days_remaining <= 30;
    const soon   = g.days_remaining <= 90;
    const daysClass = urgent ? 'urgent' : (soon ? 'soon' : '');
    const daysTxt = g.days_remaining >= 0
      ? `${g.days_remaining}d`
      : `${Math.abs(g.days_remaining)}d overdue`;
    return `
      <div class="deadline-row">
        ${stateBadge(g.state)}
        <span class="deadline-name">${esc(g.title)}</span>
        <span class="deadline-days ${daysClass}">${daysTxt}</span>
        ${g.next_milestone
          ? `<span class="milestone-date" style="font-size:0.8rem;color:var(--text-secondary)">→ ${esc(g.next_milestone)}</span>`
          : ''}
      </div>`;
  }).join(''));
}

function renderResources(res) {
  const timePct  = res.time_pct   || 0;
  const recovPct = res.recovery_pct || 0;
  const attn     = res.attention_count || 0;

  const barsHtml = `
    <div class="resource-grid">
      <div class="resource-item">
        <div class="resource-label">Time <span class="resource-pct">${timePct}%</span></div>
        <div class="progress-track">
          <div class="progress-fill ${progressClass(timePct)}" style="width:${Math.min(timePct,100)}%"></div>
        </div>
      </div>
      <div class="resource-item">
        <div class="resource-label">Recovery <span class="resource-pct">${recovPct}%</span></div>
        <div class="progress-track">
          <div class="progress-fill ${progressClass(recovPct)}" style="width:${Math.min(recovPct,100)}%"></div>
        </div>
      </div>
      <div class="resource-item">
        <div class="resource-label">Attention</div>
        <div class="attention-count">${attn}</div>
        <div style="font-size:0.7rem;color:var(--text-secondary)">open items</div>
      </div>
    </div>`;

  const tw = res.three_week || {};
  const weeks = [tw.last_week, tw.this_week, tw.next_week].filter(Boolean);
  const threeWeekHtml = weeks.length ? `
    <div class="three-week-grid">
      ${weeks.map(w => {
        const label = { last_week: 'Last week', this_week: 'This week', next_week: 'Next week' }[w.label] || w.label;
        const isCurrent = w.label === 'this_week';
        return `<div class="week-card${isCurrent ? ' current' : ''}">
          <div class="week-label">${label}</div>
          <div class="week-stat">Time <strong>${w.time_committed_hours}h / ${w.time_envelope_hours}h</strong></div>
          <div class="week-stat">Recovery <strong>${w.recovery_committed_tss} / ${w.recovery_envelope_tss} TSS</strong></div>
          ${w.recovery_actual_tss != null
            ? `<div class="week-stat">Actual TSS <strong>${w.recovery_actual_tss}</strong></div>` : ''}
          <div class="week-stat">Attention <strong>${w.attention_count}</strong></div>
        </div>`;
      }).join('')}
    </div>` : '';

  setHTML('resources', barsHtml + threeWeekHtml);
}

// ── Goals view ────────────────────────────────────────────────────────────────

async function loadGoals() {
  try {
    const d = await apiFetch('/v1/goals/summary');
    renderGoalCards(d.goals || []);
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<div class="error-state">Failed to load: ${esc(err.message)}</div>`;
  }
}

function renderGoalCards(goals) {
  const container = document.getElementById('goals-list');
  if (!container) return;
  if (!goals.length) {
    container.innerHTML = '<div class="empty-state">No active goals.</div>';
    return;
  }

  container.innerHTML = goals.map(g => {
    const cardClass = g.state === 'primacy' ? 'primacy' : (g.state === 'drifting' ? 'drifting' : '');

    const milestonesHtml = g.milestones.length
      ? g.milestones.map(m => `
          <div class="milestone-row">
            <span class="milestone-state ${m.state}"></span>
            <span style="flex:1">${esc(m.title)}</span>
            ${m.target_date ? `<span class="milestone-date">${fmtDate(m.target_date)}</span>` : ''}
          </div>`).join('')
      : '<div style="font-size:0.8rem;color:var(--text-secondary);padding:0.4rem 0">No milestones set.</div>';

    const costParts = [];
    if (g.weekly_time_hours) costParts.push(`<strong>${g.weekly_time_hours}h</strong> time/wk`);
    if (g.weekly_tss)        costParts.push(`<strong>${g.weekly_tss}</strong> TSS/wk`);
    const costHtml = costParts.length
      ? `<div class="weekly-cost">${costParts.join(' · ')}</div>` : '';

    return `
      <div class="goal-card ${cardClass}">
        <div class="goal-card-header" onclick="toggleGoal(this)">
          <h3>${esc(g.title)}</h3>
          ${stateBadge(g.state)}
          ${g.target_date ? `<span class="milestone-date">${fmtDate(g.target_date)}</span>` : ''}
          <span class="chevron">▼</span>
        </div>
        <div class="goal-card-body">
          ${g.description ? `<p class="goal-description">${esc(g.description)}</p>` : ''}
          ${milestonesHtml}
          ${costHtml}
          ${g.sacrifice_count
            ? `<div class="sacrifice-note">${g.sacrifice_count} sacrifice${g.sacrifice_count !== 1 ? 's' : ''} logged</div>`
            : ''}
          <div class="goal-actions">
            <button class="btn btn-primary"
              onclick="prefillCapture('sacrifice for ${esc(g.title).replace(/'/g,"\\'")}')">
              Log sacrifice
            </button>
            <button class="btn"
              onclick="prefillCapture('note on ${esc(g.title).replace(/'/g,"\\'")}:')">
              Add note
            </button>
          </div>
        </div>
      </div>`;
  }).join('');
}

function toggleGoal(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector('.chevron');
  if (!body) return;
  const open = body.classList.toggle('open');
  if (chevron) chevron.style.transform = open ? 'rotate(180deg)' : '';
}

// ── Reflection view ───────────────────────────────────────────────────────────

async function loadReflection() {
  try {
    const d = await apiFetch('/v1/reflection');
    renderMemoirList('completed-goals', d.completed || []);
    renderMemoirList('released-goals',  d.released  || []);
    renderSacrificePattern(d.sacrifice_pattern || {});
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<div class="error-state">Failed to load: ${esc(err.message)}</div>`;
  }
}

function renderMemoirList(id, goals) {
  if (!goals.length) {
    setHTML(id, '<div class="empty-state">None yet.</div>');
    return;
  }
  setHTML(id, goals.map(g => `
    <div class="memoir-card">
      <div class="memoir-header">
        <h3>${esc(g.title)}</h3>
        <span class="milestone-date">${g.closed_at ? fmtDate(g.closed_at.split('T')[0]) : ''}</span>
      </div>
      <div class="memoir-body">
        ${g.memoir
          ? `<div class="memoir-text">${esc(g.memoir)}</div>`
          : '<div style="font-size:0.8rem;color:var(--text-secondary);font-style:italic">No memoir written.</div>'}
        ${g.release_reason
          ? `<div class="memoir-meta">Released because: ${esc(g.release_reason)}</div>` : ''}
        ${g.sacrifice_count
          ? `<div class="memoir-meta">${g.sacrifice_count} sacrifice${g.sacrifice_count !== 1 ? 's' : ''} logged</div>`
          : ''}
      </div>
    </div>`).join(''));
}

function renderSacrificePattern(pattern) {
  const total      = pattern.sacrifice_count_28d || 0;
  const byResource = pattern.by_resource || {};
  const maxVal     = Math.max(1, ...Object.values(byResource));

  const summary = `<div class="sacrifice-summary">
    <strong>${total}</strong> sacrifice${total !== 1 ? 's' : ''} in the last 28 days
    ${pattern.dominant_resource
      ? `— dominant resource: <strong>${pattern.dominant_resource}</strong>` : ''}
  </div>`;

  const bars = Object.entries(byResource).map(([resource, count]) => `
    <div class="sacrifice-bar-row">
      <span class="sacrifice-bar-label">${esc(resource)}</span>
      <div class="sacrifice-bar-track">
        <div class="sacrifice-bar-fill" style="width:${Math.round((count / maxVal) * 100)}%"></div>
      </div>
      <span class="sacrifice-bar-count">${count}</span>
    </div>`).join('');

  setHTML('sacrifice-pattern', summary + `<div class="sacrifice-bars">${bars}</div>`);
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', initCaptureBar);
