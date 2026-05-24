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
  if (pct > 95)  return 'critical';
  if (pct >= 80) return 'warning';
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

function typeBadge(goalType) {
  const map = {
    habit:       ['badge-habit',       'Habit'],
    achievement: ['badge-achievement', 'Achievement'],
    perpetual:   ['badge-perpetual',   'Perpetual'],
  };
  const [cls, label] = map[goalType] || ['badge-active', goalType || 'Goal'];
  return `<span class="badge ${cls}">${label}</span>`;
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
    apiFetch('/v1/health/integrations').then(renderSyncStatus).catch(() => {});
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
  const trendGlyph = { up: '↑', down: '↓', flat: '→' };
  setHTML('perpetual-goals', goals.map(g => {
    const val   = g.current_value != null ? g.current_value : '—';
    const range = (g.target_min != null || g.target_max != null)
      ? `target ${g.target_min ?? '—'} – ${g.target_max ?? '—'}` : '';
    const trendHtml = g.trend
      ? `<span class="trend-arrow trend-${g.trend}">${trendGlyph[g.trend] || ''}</span>`
      : '';
    return `
      <div class="metric-row">
        <span class="rag-dot ${ragClass(g.rag)}"></span>
        <span class="metric-name">${esc(g.title)}</span>
        <span class="metric-value">${val}${trendHtml}</span>
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

function fmtSyncAge(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffH  = diffMs / 3600000;
  if (diffH < 1) return `${Math.round(diffH * 60)}m ago`;
  return `${Math.round(diffH)}h ago`;
}

function renderSyncStatus(status) {
  const el = document.getElementById('sync-status');
  if (!el) return;
  const parts = ['garmin', 'strava'].map(key => {
    const s = (status && status[key]) || {};
    const label = key.charAt(0).toUpperCase() + key.slice(1);
    const cls   = s.status || 'never';
    const txt   = s.last_sync ? fmtSyncAge(s.last_sync) : 'never';
    return `<span class="sync-item sync-${cls}" id="sync-item-${key}">${label}: <span id="sync-ts-${key}">${txt}</span>` +
      `<button class="sync-btn" id="sync-btn-${key}" onclick="triggerSync('${key}')" title="Sync now">↻</button></span>`;
  });
  el.innerHTML = `<div class="sync-footer">${parts.join('')}</div>`;
}

async function triggerSync(service) {
  const btn = document.getElementById(`sync-btn-${service}`);
  const tsEl = document.getElementById(`sync-ts-${service}`);
  const item = document.getElementById(`sync-item-${service}`);
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const res = await fetch(`/v1/admin/sync/${service}`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    // Refresh the full footer so RAG dot and timestamp update together
    apiFetch('/v1/health/integrations').then(renderSyncStatus).catch(() => {
      // fallback: just update the timestamp text inline
      if (tsEl) tsEl.textContent = 'just now';
      if (btn)  { btn.disabled = false; btn.textContent = '↻'; }
    });
  } catch {
    if (btn) { btn.disabled = false; btn.textContent = '↻'; }
  }
}

// ── Goals view ────────────────────────────────────────────────────────────────

async function loadGoals() {
  try {
    const d = await apiFetch('/v1/goals/summary');
    renderGoalCards(d.goals || []);
    // Summary filters milestones to active/pending/suggested — reload each achievement
    // goal via the dedicated endpoint to pick up achieved/missed states too.
    const achievementIds = (d.goals || [])
      .filter(g => g.goal_type === 'achievement' || !g.goal_type)
      .map(g => g.id);
    achievementIds.forEach(id => reloadMilestones(id));
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
    const badges = (g.state === 'primacy' ? stateBadge('primacy') : '') + typeBadge(g.goal_type);

    let typeBody = '';
    if (g.goal_type === 'habit') {
      const count  = g.this_week_count || 0;
      const target = g.weekly_target   || 1;
      const pct    = Math.min(Math.round((count / target) * 100), 100);
      typeBody = `
        <div class="habit-progress">
          <div class="habit-stat">
            <span class="habit-count" id="habit-count-${g.id}">${count}</span>
            <span class="habit-target">/ ${target}</span>
            <span class="habit-unit">this week</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill${pct >= 100 ? '' : ''}"
                 id="habit-bar-${g.id}"
                 style="width:${pct}%; background:${pct >= 100 ? 'var(--rag-green)' : 'var(--teal)'}"></div>
          </div>
        </div>`;
    } else if (g.goal_type === 'perpetual') {
      const val   = g.current_value != null ? g.current_value : '—';
      const range = (g.target_min != null || g.target_max != null)
        ? `target ${g.target_min ?? '—'} – ${g.target_max ?? '—'}` : '';
      typeBody = `
        <div class="metric-row" style="border-bottom:none;padding:0.5rem 0 0">
          <span class="rag-dot ${ragClass(g.rag)}"></span>
          <span class="metric-value">${val}</span>
          ${range ? `<span class="metric-range">${esc(range)}</span>` : ''}
        </div>`;
    } else {
      typeBody = `<div id="ms-list-${g.id}">${renderMilestoneRows(g.id, g.milestones)}</div>`;
    }

    const costParts = [];
    if (g.weekly_time_hours) costParts.push(`<strong>${g.weekly_time_hours}h</strong> time/wk`);
    if (g.weekly_tss)        costParts.push(`<strong>${g.weekly_tss}</strong> TSS/wk`);
    const costHtml = costParts.length
      ? `<div class="weekly-cost">${costParts.join(' · ')}</div>` : '';

    const habitLogBtn = g.goal_type === 'habit'
      ? `<button class="btn btn-primary" id="habit-log-btn-${g.id}"
           onclick="logHabit(${g.id}, this)">+1 Done</button>` : '';

    return `
      <div class="goal-card ${cardClass}">
        <div class="goal-card-header" onclick="toggleGoal(this)">
          <h3>${esc(g.title)}</h3>
          ${badges}
          ${g.target_date ? `<span class="milestone-date">${fmtDate(g.target_date)}</span>` : ''}
          <span class="chevron">▼</span>
        </div>
        <div class="goal-card-body">
          ${g.description ? `<p class="goal-description">${esc(g.description)}</p>` : ''}
          ${typeBody}
          ${costHtml}
          ${g.sacrifice_count
            ? `<div class="sacrifice-note">${g.sacrifice_count} sacrifice${g.sacrifice_count !== 1 ? 's' : ''} logged</div>`
            : ''}
          <div class="goal-actions">
            ${habitLogBtn}
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

async function logHabit(goalId, btn) {
  btn.disabled = true;
  try {
    const res = await fetch(`/v1/goals/${goalId}/habit/log`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const countEl = document.getElementById(`habit-count-${goalId}`);
    const barEl   = document.getElementById(`habit-bar-${goalId}`);
    if (countEl) countEl.textContent = data.this_week_count;
    if (barEl) {
      const target = parseInt(barEl.closest('.goal-card-body')
        ?.querySelector('.habit-target')?.textContent?.replace('/', '').trim() || '1', 10);
      const pct = Math.min(Math.round((data.this_week_count / target) * 100), 100);
      barEl.style.width = `${pct}%`;
      barEl.style.background = pct >= 100 ? 'var(--rag-green)' : 'var(--teal)';
    }
  } catch {
    // silently fail — user can reload
  } finally {
    btn.disabled = false;
  }
}

function toggleGoal(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector('.chevron');
  if (!body) return;
  const open = body.classList.toggle('open');
  if (chevron) chevron.style.transform = open ? 'rotate(180deg)' : '';
}

// ── Milestone inline actions ──────────────────────────────────────────────────

let _openMsDropdown = null;

function closeMsDropdown() {
  if (_openMsDropdown) {
    _openMsDropdown.classList.add('hidden');
    _openMsDropdown = null;
  }
}

function toggleMsMenu(event, btn) {
  event.stopPropagation();
  const dropdown = btn.nextElementSibling;
  if (_openMsDropdown && _openMsDropdown !== dropdown) {
    _openMsDropdown.classList.add('hidden');
  }
  const willOpen = dropdown.classList.contains('hidden');
  dropdown.classList.toggle('hidden');
  _openMsDropdown = willOpen ? dropdown : null;
}

function showMsPanel(mid, panelClass) {
  closeMsDropdown();
  const container = document.querySelector(`.ms-container[data-mid="${mid}"]`);
  if (!container) return;
  container.querySelectorAll('.ms-edit-panel,.ms-complete-panel,.ms-delete-panel')
    .forEach(p => p.classList.add('hidden'));
  const panel = container.querySelector('.' + panelClass);
  panel?.classList.remove('hidden');
  panel?.querySelector('input,textarea')?.focus();
}

function cancelMsPanel(mid) {
  document.querySelector(`.ms-container[data-mid="${mid}"]`)
    ?.querySelectorAll('.ms-edit-panel,.ms-complete-panel,.ms-delete-panel')
    .forEach(p => p.classList.add('hidden'));
}

function renderMilestoneRow(goalId, m) {
  const isReadOnly = m.state === 'achieved' || m.state === 'missed';

  let dropdownItems = '';
  if (m.state === 'suggested') {
    dropdownItems = `
      <button class="ms-dropdown-item" onclick="agreeMilestone(${m.id},${goalId})">Agree</button>
      <button class="ms-dropdown-item" onclick="showMsPanel(${m.id},'ms-edit-panel')">Edit</button>
      <button class="ms-dropdown-item ms-dropdown-danger" onclick="showMsPanel(${m.id},'ms-delete-panel')">Delete</button>`;
  } else if (m.state === 'pending' || m.state === 'active') {
    dropdownItems = `
      <button class="ms-dropdown-item" onclick="showMsPanel(${m.id},'ms-edit-panel')">Edit</button>
      <button class="ms-dropdown-item" onclick="showMsPanel(${m.id},'ms-complete-panel')">Mark complete</button>
      <button class="ms-dropdown-item ms-dropdown-danger" onclick="showMsPanel(${m.id},'ms-delete-panel')">Delete</button>`;
  }

  const menuHtml = !isReadOnly ? `
    <div class="ms-menu-wrap">
      <button class="ms-menu-btn" onclick="toggleMsMenu(event,this)" title="Options">···</button>
      <div class="ms-dropdown hidden">${dropdownItems}</div>
    </div>` : '';

  const panelsHtml = !isReadOnly ? `
    <div class="ms-edit-panel hidden">
      <div class="ms-panel-row">
        <input type="text" class="ms-edit-title form-input" value="${esc(m.title)}" placeholder="Milestone name">
        <input type="date" class="ms-edit-date form-input" value="${m.target_date || ''}">
      </div>
      <div class="ms-panel-actions">
        <button class="btn btn-primary btn-sm" onclick="saveMsEdit(${m.id},${goalId})">Save</button>
        <button class="btn btn-sm" onclick="cancelMsPanel(${m.id})">Cancel</button>
        <span class="ms-feedback"></span>
      </div>
    </div>
    <div class="ms-complete-panel hidden">
      <textarea class="form-textarea ms-note" rows="2" placeholder="Optional completion note…"></textarea>
      <div class="ms-panel-actions">
        <button class="btn btn-primary btn-sm" onclick="confirmMsComplete(${m.id},${goalId})">Confirm complete</button>
        <button class="btn btn-sm" onclick="cancelMsPanel(${m.id})">Cancel</button>
        <span class="ms-feedback"></span>
      </div>
    </div>
    <div class="ms-delete-panel hidden">
      <span class="ms-confirm-text">Remove this milestone?</span>
      <div class="ms-panel-actions">
        <button class="btn btn-danger btn-sm" onclick="confirmMsDelete(${m.id},${goalId})">Yes, remove</button>
        <button class="btn btn-sm" onclick="cancelMsPanel(${m.id})">Cancel</button>
      </div>
    </div>` : '';

  const noteHtml = (m.state === 'achieved' && m.description)
    ? `<div style="font-size:0.75rem;font-style:italic;color:var(--text-secondary);padding-left:1.375rem;padding-bottom:0.25rem">${esc(m.description)}</div>`
    : '';

  return `
    <div class="ms-container" data-mid="${m.id}" data-goal-id="${goalId}" data-state="${m.state}">
      <div class="milestone-row">
        <span class="milestone-state ${m.state}"></span>
        <span class="ms-title" style="flex:1">${esc(m.title)}</span>
        <span class="milestone-date ms-date">${m.target_date ? fmtDate(m.target_date) : ''}</span>
        ${menuHtml}
      </div>
      ${noteHtml}
      ${panelsHtml}
    </div>`;
}

function renderMilestoneRows(goalId, milestones) {
  const terminal = ['achieved', 'missed'];
  const active   = milestones.filter(m => !terminal.includes(m.state));
  const done     = milestones.filter(m =>  terminal.includes(m.state));
  const ordered  = [...active, ...done];
  const rows = ordered.length
    ? ordered.map(m => renderMilestoneRow(goalId, m)).join('')
    : '<div style="font-size:0.8rem;color:var(--text-secondary);padding:0.4rem 0">No milestones set.</div>';
  return rows + `<button class="ms-add-btn" onclick="addMilestoneRow(${goalId},this)">+ Add milestone</button>`;
}

function refreshMilestoneRow(goalId, milestone) {
  const container = document.querySelector(`.ms-container[data-mid="${milestone.id}"]`);
  if (container) container.outerHTML = renderMilestoneRow(goalId, milestone);
}

async function reloadMilestones(goalId) {
  const el = document.getElementById(`ms-list-${goalId}`);
  if (!el) return;
  try {
    const data = await apiFetch(`/v1/goals/${goalId}/milestones`);
    el.innerHTML = renderMilestoneRows(goalId, data.milestones);
  } catch {}
}

async function agreeMilestone(mid, goalId) {
  closeMsDropdown();
  const res = await fetch(`/v1/goals/${goalId}/milestones/${mid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state: 'pending' }),
  });
  if (!res.ok) return;
  refreshMilestoneRow(goalId, await res.json());
}

async function saveMsEdit(mid, goalId) {
  const container = document.querySelector(`.ms-container[data-mid="${mid}"]`);
  if (!container) return;
  const title   = container.querySelector('.ms-edit-title')?.value.trim();
  const dateVal = container.querySelector('.ms-edit-date')?.value;
  if (!title) return;

  const body = { title };
  if (dateVal) body.target_date = dateVal;

  const res = await fetch(`/v1/goals/${goalId}/milestones/${mid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    container.querySelector('.ms-edit-panel .ms-feedback').textContent = 'Save failed.';
    return;
  }
  const data = await res.json();
  container.querySelector('.ms-title').textContent = data.title;
  container.querySelector('.ms-date').textContent = data.target_date ? fmtDate(data.target_date) : '';
  cancelMsPanel(mid);
}

async function confirmMsComplete(mid, goalId) {
  const container = document.querySelector(`.ms-container[data-mid="${mid}"]`);
  if (!container) return;
  const note = container.querySelector('.ms-note')?.value.trim();
  const body = { state: 'achieved' };
  if (note) body.description = note;

  const res = await fetch(`/v1/goals/${goalId}/milestones/${mid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    container.querySelector('.ms-complete-panel .ms-feedback').textContent = 'Failed.';
    return;
  }
  refreshMilestoneRow(goalId, await res.json());
}

async function confirmMsDelete(mid, goalId) {
  const container = document.querySelector(`.ms-container[data-mid="${mid}"]`);
  if (!container) return;
  const res = await fetch(`/v1/goals/${goalId}/milestones/${mid}`, { method: 'DELETE' });
  if (!res.ok) return;
  container.remove();
}

function addMilestoneRow(goalId, addBtn) {
  if (addBtn.previousElementSibling?.classList.contains('ms-new-row')) return;
  const newRow = document.createElement('div');
  newRow.className = 'ms-container ms-new-row';
  newRow.innerHTML = `
    <div class="ms-edit-panel">
      <div class="ms-panel-row">
        <input type="text" class="ms-edit-title form-input" placeholder="Milestone name">
        <input type="date" class="ms-edit-date form-input">
      </div>
      <div class="ms-panel-actions">
        <button class="btn btn-primary btn-sm" onclick="saveNewMilestone(${goalId},this)">Add</button>
        <button class="btn btn-sm" onclick="this.closest('.ms-new-row').remove()">Cancel</button>
        <span class="ms-feedback"></span>
      </div>
    </div>`;
  addBtn.parentNode.insertBefore(newRow, addBtn);
  newRow.querySelector('.ms-edit-title').focus();
}

async function saveNewMilestone(goalId, btn) {
  const container = btn.closest('.ms-new-row');
  const title   = container.querySelector('.ms-edit-title').value.trim();
  const dateVal = container.querySelector('.ms-edit-date').value;
  if (!title) { container.querySelector('.ms-edit-title').focus(); return; }

  const milestone = { title };
  if (dateVal) milestone.target_date = dateVal;

  btn.disabled = true;
  const res = await fetch(`/v1/goals/${goalId}/milestones/agree`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ milestones: [milestone] }),
  });
  if (!res.ok) {
    btn.disabled = false;
    container.querySelector('.ms-feedback').textContent = 'Failed.';
    return;
  }
  container.remove();
  await reloadMilestones(goalId);
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

// ── Add Goal form ─────────────────────────────────────────────────────────────

function toggleAddGoalForm() {
  const panel = document.getElementById('add-goal-panel');
  const btn   = document.getElementById('add-goal-btn');
  if (!panel) return;
  const opening = panel.classList.contains('hidden');
  panel.classList.toggle('hidden');
  if (btn) btn.textContent = opening ? '✕ Cancel' : '+ Add Goal';
  if (opening) {
    document.getElementById('new-goal-title')?.focus();
  } else {
    document.getElementById('add-goal-form')?.reset();
    document.getElementById('deadline-group')?.classList.add('hidden');
    document.getElementById('habit-target-group')?.classList.add('hidden');
  }
}

function handleGoalTypeChange() {
  const type = document.getElementById('new-goal-type')?.value;
  const deadlineGroup = document.getElementById('deadline-group');
  const habitGroup    = document.getElementById('habit-target-group');
  if (deadlineGroup) deadlineGroup.classList.toggle('hidden', type !== 'achievement');
  if (habitGroup)    habitGroup.classList.toggle('hidden',    type !== 'habit');
}

function initAddGoalForm() {
  const form = document.getElementById('add-goal-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitBtn = document.getElementById('add-goal-submit');
    const feedback  = document.getElementById('add-goal-feedback');

    const title          = document.getElementById('new-goal-title').value.trim();
    const goalType       = document.getElementById('new-goal-type').value;
    const description    = document.getElementById('new-goal-description').value.trim() || null;
    const deadlineEl     = document.getElementById('new-goal-deadline');
    const targetDate     = (goalType === 'achievement' && deadlineEl?.value) ? deadlineEl.value : null;
    const weeklyTargetEl = document.getElementById('new-goal-weekly-target');
    const weeklyTarget   = (goalType === 'habit' && weeklyTargetEl?.value)
      ? parseInt(weeklyTargetEl.value, 10) : null;

    if (!title) return;

    submitBtn.disabled   = true;
    feedback.textContent = '';

    try {
      const res = await fetch('/v1/goals', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          title, goal_type: goalType, description,
          target_date: targetDate, weekly_target: weeklyTarget,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      // close and reset
      form.reset();
      document.getElementById('add-goal-panel').classList.add('hidden');
      document.getElementById('add-goal-btn').textContent = '+ Add Goal';
      document.getElementById('deadline-group')?.classList.add('hidden');
      document.getElementById('habit-target-group')?.classList.add('hidden');
      // reload list
      await loadGoals();
    } catch (err) {
      feedback.textContent = err.message;
    } finally {
      submitBtn.disabled = false;
    }
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initCaptureBar();
  initAddGoalForm();
  document.addEventListener('click', closeMsDropdown);
});
