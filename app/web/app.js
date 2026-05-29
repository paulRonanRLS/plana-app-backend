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
    renderGeneralCondition(d.general_condition || 'No data yet');
    renderHealthMetrics(d.health_metrics || []);
    renderActivitiesThisWeek(d.activities_this_week || []);
    renderGoalsSnapshot(d.goals_snapshot || []);
    renderResources(d.three_week_resources || d.resources || {});
    apiFetch('/v1/health/integrations').then(renderSyncStatus).catch(() => {});
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<div class="error-state">Failed to load: ${esc(err.message)}</div>`;
  }
}

function renderGeneralCondition(condition) {
  const configs = {
    'Restored':      { cls: 'condition-restored', sub: 'Based on today\'s Garmin data' },
    'Carrying Load': { cls: 'condition-carrying',  sub: 'Based on today\'s Garmin data' },
    'Depleted':      { cls: 'condition-depleted',  sub: 'Based on today\'s Garmin data' },
    'No data yet':   { cls: 'condition-no-data',   sub: 'No Garmin data today' },
  };
  const { cls, sub } = configs[condition] || configs['No data yet'];
  const el = document.getElementById('general-condition');
  if (el) el.innerHTML =
    `<div class="condition-banner ${cls}">` +
    `<div class="condition-status">${esc(condition)}</div>` +
    `<div class="condition-sub">${esc(sub)}</div>` +
    `</div>`;
}

function renderHealthMetrics(metrics) {
  if (!metrics.length) {
    setHTML('health-metrics', '<div class="empty-state">Add health goals to see metrics</div>');
    return;
  }
  const trendGlyph = { up: '↑', down: '↓', flat: '→' };
  setHTML('health-metrics', `<div class="metric-grid">${metrics.map(m => {
    const val  = m.current_value != null ? m.current_value : '—';
    const unit = m.unit ? `<span class="metric-unit">${esc(m.unit)}</span>` : '';
    const range = (m.target_min != null || m.target_max != null)
      ? `target ${m.target_min ?? '—'} – ${m.target_max ?? '—'}` : null;
    const trendHtml = m.trend
      ? `<span class="trend-arrow trend-${m.trend}">${trendGlyph[m.trend] || ''}</span>` : '';
    return `<div class="metric-card">
      <div class="metric-card-header">
        <span class="rag-dot ${ragClass(m.rag)}"></span>
        <span class="metric-card-name">${esc(m.metric_name)}</span>
      </div>
      <div class="metric-card-value">${val}${unit}${trendHtml}</div>
      ${range ? `<div class="metric-card-range">${esc(range)}</div>` : ''}
    </div>`;
  }).join('')}</div>`);
}

const _sportEmoji = {
  run: '🏃', ride: '🚴', swim: '🏊', walk: '🚶', strength: '🏋️', other: '⚡',
};

function renderActivitiesThisWeek(activities) {
  if (!activities.length) {
    setHTML('activities-week', '<div class="empty-state">No activities this week</div>');
    return;
  }
  setHTML('activities-week', activities.map(a => {
    const emoji = _sportEmoji[a.sport_type] || '⚡';
    const dist  = a.distance_km != null ? `<span class="activity-dist">${a.distance_km}km</span>` : '';
    const tss   = a.tss != null ? `<span class="activity-tss">${a.tss} TSS</span>` : '';
    return `<div class="activity-row">
      <span class="activity-emoji">${emoji}</span>
      <span class="activity-day">${esc(a.day_name)}</span>
      ${dist}${tss}
    </div>`;
  }).join(''));
}

function renderGoalsSnapshot(goals) {
  if (!goals.length) {
    setHTML('goals-snapshot', '<div class="empty-state">No active goals</div>');
    return;
  }
  setHTML('goals-snapshot', goals.map(g => {
    const driftCls    = g.state === 'drifting' ? ' drifting' : '';
    const primacyBadge = g.is_primacy
      ? `<span class="badge badge-primacy" style="font-size:0.6rem;padding:0.1rem 0.35rem;margin-right:0.25rem">planA</span>` : '';
    let leftHtml  = '';
    let rightHtml = '';
    if (g.goal_type === 'perpetual') {
      leftHtml = `<span class="rag-dot ${ragClass(g.rag || 'none')}"></span>`;
    } else if (g.goal_type === 'achievement') {
      const days = g.days_remaining != null ? `${g.days_remaining}d` : '';
      const traj = g.trajectory || 'No data';
      rightHtml = `<span class="snapshot-status">${days ? days + ' — ' : ''}${esc(traj)}</span>`;
    } else if (g.goal_type === 'habit') {
      const count  = g.this_period_count ?? 0;
      const target = g.weekly_target != null ? g.weekly_target : '?';
      rightHtml = `<span class="snapshot-status">${count} / ${target} this week</span>`;
    }
    return `<div class="snapshot-row${driftCls}" onclick="window.location.href='/web/goals.html'">
      ${leftHtml}${primacyBadge}<span class="snapshot-title">${esc(g.title)}</span>${rightHtml}
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
    renderGoalCategories(d.goals || []);
    // Summary filters milestones to active/pending/suggested — reload each achievement
    // goal via the dedicated endpoint to pick up achieved/missed states too.
    const achievementIds = (d.goals || [])
      .filter(g => g.goal_type === 'achievement' || !g.goal_type)
      .map(g => g.id);
    achievementIds.forEach(id => reloadMilestones(id));
  } catch (err) {
    setHTML('goals-list', `<div class="error-state">Failed to load: ${esc(err.message)}</div>`);
  }
}

function _goalCardHtml(g) {
  const cardClass = g.state === 'primacy' ? 'primacy' : (g.state === 'drifting' ? 'drifting' : '');
  const badges = (g.state === 'primacy' ? stateBadge('primacy') : '') + typeBadge(g.goal_type);

  let typeBody = '';
  if (g.goal_type === 'habit') {
    typeBody = renderHabitBody(g);
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

  return `
    <div class="goal-card ${cardClass}" id="goal-card-${g.id}">
      <div class="goal-card-header" onclick="toggleGoal(this)">
        <h3>${esc(g.title)}</h3>
        ${badges}
        ${g.target_date ? `<span class="milestone-date">${fmtDate(g.target_date)}</span>` : ''}
        <div class="goal-menu-wrap" onclick="event.stopPropagation()">
          <button class="goal-menu-btn" onclick="toggleGoalMenu(event,this)" title="Options">···</button>
          <div class="goal-dropdown hidden">${_goalMenuItemsHtml(g)}</div>
        </div>
        <span class="chevron">▼</span>
      </div>
      ${_goalPanelsHtml(g)}
      <div class="goal-card-body">
        ${g.description ? `<p class="goal-description">${esc(g.description)}</p>` : ''}
        ${typeBody}
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
}

function _goalMenuItemsHtml(g) {
  const id = g.id;
  const canDelete = g.sacrifice_count === 0 &&
    !(g.milestones || []).some(m => m.state === 'achieved' || m.state === 'missed');
  const editBtn    = `<button class="goal-dropdown-item" onclick="showGoalPanel(${id},'goal-edit-panel')">Edit</button>`;
  const releaseBtn = `<button class="goal-dropdown-item goal-dropdown-danger" onclick="openReleasePanel(${id})">Release</button>`;
  const deleteBtn  = canDelete
    ? `<button class="goal-dropdown-item goal-dropdown-danger" onclick="showGoalPanel(${id},'goal-delete-panel')">Delete</button>`
    : '';
  if (g.state === 'draft') {
    return editBtn +
      `<button class="goal-dropdown-item" onclick="patchGoalState(${id},'active')">Activate</button>` +
      deleteBtn;
  }
  if (g.state === 'active' || g.state === 'subordinate') {
    return editBtn +
      `<button class="goal-dropdown-item" onclick="patchGoalState(${id},'primacy')">Set as planA</button>` +
      `<button class="goal-dropdown-item" onclick="patchGoalState(${id},'subordinate')">Set as subordinate</button>` +
      releaseBtn + deleteBtn;
  }
  if (g.state === 'primacy') {
    return editBtn +
      `<button class="goal-dropdown-item" onclick="patchGoalState(${id},'active')">Set as active</button>` +
      releaseBtn + deleteBtn;
  }
  if (g.state === 'drifting') {
    return editBtn +
      `<button class="goal-dropdown-item" onclick="patchGoalState(${id},'active')">Acknowledge drift</button>` +
      releaseBtn + deleteBtn;
  }
  return editBtn;
}

function _goalPanelsHtml(g) {
  const id = g.id;
  const goalType = g.goal_type || 'achievement';

  let typeFields = '';
  if (goalType === 'perpetual') {
    typeFields = `
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Target minimum</label>
          <input type="number" class="form-input" id="gedit-min-${id}" value="${g.target_min ?? ''}" step="0.1">
        </div>
        <div class="form-group">
          <label class="form-label">Target maximum</label>
          <input type="number" class="form-input" id="gedit-max-${id}" value="${g.target_max ?? ''}" step="0.1">
        </div>
      </div>`;
  } else if (goalType === 'habit') {
    typeFields = `
      <div class="form-group">
        <label class="form-label">Weekly target</label>
        <input type="number" class="form-input" id="gedit-target-${id}" value="${g.weekly_target ?? ''}" min="1">
      </div>`;
  } else {
    typeFields = `
      <div class="form-group">
        <label class="form-label">Deadline <span class="form-optional">(optional)</span></label>
        <input type="date" class="form-input" id="gedit-date-${id}" value="${g.target_date || ''}">
      </div>`;
  }

  return `
    <div class="goal-action-panel goal-edit-panel hidden" id="goal-edit-${id}">
      <div class="goal-panel-inner">
        <div class="form-group">
          <label class="form-label">Title</label>
          <input type="text" class="form-input" id="gedit-title-${id}" value="${esc(g.title)}">
        </div>
        <div class="form-group">
          <label class="form-label">Description <span class="form-optional">(optional)</span></label>
          <textarea class="form-textarea" id="gedit-desc-${id}" rows="2">${esc(g.description || '')}</textarea>
        </div>
        ${typeFields}
        <div class="goal-panel-actions">
          <button class="btn btn-primary btn-sm" onclick="saveGoalEdit(${id})">Save</button>
          <button class="btn btn-sm" onclick="cancelGoalPanel(${id})">Cancel</button>
          <span class="goal-panel-feedback" id="gedit-feedback-${id}"></span>
        </div>
      </div>
    </div>
    <div class="goal-action-panel goal-release-panel hidden" id="goal-release-${id}">
      <div class="goal-panel-inner">
        <div class="goal-memoir-preview" id="goal-memoir-${id}">Loading memoir draft…</div>
        <div class="form-group" style="margin-top:0.75rem">
          <label class="form-label">Your reflection <span class="form-optional">(optional)</span></label>
          <textarea class="form-textarea" id="grelease-note-${id}" rows="2" placeholder="Why are you releasing this goal?"></textarea>
        </div>
        <div class="goal-panel-actions">
          <button class="btn btn-danger btn-sm" onclick="confirmGoalRelease(${id})">Release goal</button>
          <button class="btn btn-sm" onclick="cancelGoalPanel(${id})">Cancel</button>
          <span class="goal-panel-feedback" id="grelease-feedback-${id}"></span>
        </div>
      </div>
    </div>
    <div class="goal-action-panel goal-delete-panel hidden" id="goal-delete-${id}">
      <div class="goal-panel-inner">
        <span class="goal-panel-confirm-text">Permanently delete this goal?</span>
        <div class="goal-panel-actions">
          <button class="btn btn-danger btn-sm" onclick="confirmGoalDelete(${id})">Yes, delete</button>
          <button class="btn btn-sm" onclick="cancelGoalPanel(${id})">Cancel</button>
        </div>
      </div>
    </div>`;
}

function renderGoalCards(goals) {
  const container = document.getElementById('goals-list');
  if (!container) return;
  if (!goals.length) {
    container.innerHTML = '<div class="empty-state">No active goals.</div>';
    return;
  }
  container.innerHTML = goals.map(_goalCardHtml).join('');
}

// ── Goal category grouping ────────────────────────────────────────────────────

const _HEALTH_METRICS = new Set([
  'sleep_score', 'sleep_duration_hours', 'hrv', 'resting_hr', 'body_battery', 'stress',
]);

function _categoriseGoal(g) {
  if (g.goal_type === 'perpetual' && _HEALTH_METRICS.has(g.target_metric_type)) return 'health';
  if (g.goal_type === 'achievement' && g.weekly_tss)                             return 'training';
  if (g.goal_type === 'habit')                                                    return 'habits';
  return 'other';
}

const _CATEGORY_ORDER  = ['health', 'training', 'habits', 'other'];
const _CATEGORY_LABELS = { health: 'Health', training: 'Training', habits: 'Habits', other: 'Other' };

function renderGoalCategories(goals) {
  const container = document.getElementById('goals-list');
  if (!container) return;
  if (!goals.length) {
    container.innerHTML = '<div class="empty-state">No active goals.</div>';
    return;
  }
  const groups = { health: [], training: [], habits: [], other: [] };
  goals.forEach(g => groups[_categoriseGoal(g)].push(g));
  container.innerHTML = _CATEGORY_ORDER
    .filter(cat => groups[cat].length > 0)
    .map(cat => `
      <div class="goal-category-section" data-category="${cat}">
        <div class="goal-category-header" onclick="toggleCategory(this)">
          <h3>${_CATEGORY_LABELS[cat]}</h3>
          <span class="goal-category-count">${groups[cat].length}</span>
          <span class="goal-category-chevron">▼</span>
        </div>
        <div class="goal-category-body open">
          ${groups[cat].map(_goalCardHtml).join('')}
        </div>
      </div>`)
    .join('');
}

function toggleCategory(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector('.goal-category-chevron');
  if (!body) return;
  const isOpen = body.classList.toggle('open');
  if (chevron) chevron.style.transform = isOpen ? '' : 'rotate(-90deg)';
}

async function logHabit(goalId, btn, value) {
  btn.disabled = true;
  try {
    const res = await fetch(`/v1/goals/${goalId}/habit/log`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ value: value ?? 1 }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const countEl = document.getElementById(`habit-count-${goalId}`);
    const barEl   = document.getElementById(`habit-bar-${goalId}`);

    const habitType = data.habit_type || 'count';

    if (habitType === 'consistency') {
      if (countEl) countEl.textContent = data.streak ?? 0;
    } else if (habitType === 'duration' || habitType === 'volume') {
      const displayed = Math.round(data.this_period_sum ?? 0);
      if (countEl) countEl.textContent = displayed;
      if (barEl) {
        const target = parseInt(barEl.closest('.goal-card-body')
          ?.querySelector('.habit-target')?.textContent?.replace('/', '').trim() || '1', 10);
        const pct = Math.min(Math.round((displayed / target) * 100), 100);
        barEl.style.width = `${pct}%`;
        barEl.style.background = pct >= 100 ? 'var(--rag-green)' : 'var(--teal)';
      }
    } else {
      const count = data.this_period_count ?? data.this_week_count ?? 0;
      if (countEl) countEl.textContent = count;
      if (barEl) {
        const target = parseInt(barEl.closest('.goal-card-body')
          ?.querySelector('.habit-target')?.textContent?.replace('/', '').trim() || '1', 10);
        const pct = Math.min(Math.round((count / target) * 100), 100);
        barEl.style.width = `${pct}%`;
        barEl.style.background = pct >= 100 ? 'var(--rag-green)' : 'var(--teal)';
      }
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

// ── Goal management actions ───────────────────────────────────────────────────

let _openGoalMenu = null;

function closeGoalMenus() {
  if (_openGoalMenu) {
    _openGoalMenu.classList.add('hidden');
    _openGoalMenu = null;
  }
}

function toggleGoalMenu(event, btn) {
  event.stopPropagation();
  const dropdown = btn.nextElementSibling;
  if (_openGoalMenu && _openGoalMenu !== dropdown) {
    _openGoalMenu.classList.add('hidden');
  }
  const willOpen = dropdown.classList.contains('hidden');
  dropdown.classList.toggle('hidden');
  if (willOpen) {
    const rect = btn.getBoundingClientRect();
    dropdown.style.top   = `${rect.bottom + 2}px`;
    dropdown.style.right = `${window.innerWidth - rect.right}px`;
    dropdown.style.left  = 'auto';
    _openGoalMenu = dropdown;
  } else {
    _openGoalMenu = null;
  }
}

function showGoalPanel(goalId, panelClass) {
  closeGoalMenus();
  const card = document.getElementById(`goal-card-${goalId}`);
  if (!card) return;
  card.querySelectorAll('.goal-action-panel').forEach(p => p.classList.add('hidden'));
  card.querySelector('.' + panelClass)?.classList.remove('hidden');
}

function cancelGoalPanel(goalId) {
  document.getElementById(`goal-card-${goalId}`)
    ?.querySelectorAll('.goal-action-panel')
    .forEach(p => p.classList.add('hidden'));
}

async function saveGoalEdit(goalId) {
  const feedback = document.getElementById(`gedit-feedback-${goalId}`);
  const body = {};
  const titleEl    = document.getElementById(`gedit-title-${goalId}`);
  const descEl     = document.getElementById(`gedit-desc-${goalId}`);
  const minEl      = document.getElementById(`gedit-min-${goalId}`);
  const maxEl      = document.getElementById(`gedit-max-${goalId}`);
  const targetEl   = document.getElementById(`gedit-target-${goalId}`);
  const dateEl     = document.getElementById(`gedit-date-${goalId}`);

  if (titleEl) body.title = titleEl.value.trim();
  if (!body.title) { if (feedback) feedback.textContent = 'Title required.'; return; }
  if (descEl)     body.description   = descEl.value.trim()   || null;
  if (minEl)      body.target_min    = minEl.value    !== '' ? parseFloat(minEl.value)      : null;
  if (maxEl)      body.target_max    = maxEl.value    !== '' ? parseFloat(maxEl.value)      : null;
  if (targetEl)   body.weekly_target = targetEl.value !== '' ? parseInt(targetEl.value, 10) : null;
  if (dateEl)     body.target_date   = dateEl.value   || null;

  try {
    const res = await fetch(`/v1/goals/${goalId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
    await loadGoals();
  } catch (e) { if (feedback) feedback.textContent = e.message; }
}

async function patchGoalState(goalId, state) {
  closeGoalMenus();
  try {
    const res = await fetch(`/v1/goals/${goalId}/state`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ state }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
    await loadGoals();
  } catch (e) { alert(`Could not update goal: ${e.message}`); }
}

async function openReleasePanel(goalId) {
  showGoalPanel(goalId, 'goal-release-panel');
  const memoirEl = document.getElementById(`goal-memoir-${goalId}`);
  if (!memoirEl) return;
  try {
    const data = await apiFetch(`/v1/goals/${goalId}/memoir`);
    memoirEl.textContent = data.memoir || 'No memoir available.';
  } catch { memoirEl.textContent = 'Could not load memoir draft.'; }
}

async function confirmGoalRelease(goalId) {
  const feedback  = document.getElementById(`grelease-feedback-${goalId}`);
  const user_note = document.getElementById(`grelease-note-${goalId}`)?.value.trim() || '';
  try {
    const res = await fetch(`/v1/goals/${goalId}/release`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_note }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
    await loadGoals();
  } catch (e) { if (feedback) feedback.textContent = e.message; }
}

async function confirmGoalDelete(goalId) {
  try {
    const res = await fetch(`/v1/goals/${goalId}`, { method: 'DELETE' });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
    await loadGoals();
  } catch (e) { alert(`Could not delete goal: ${e.message}`); }
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
    const [d, traj] = await Promise.all([
      apiFetch('/v1/reflection'),
      apiFetch('/v1/reflection/trajectory').catch(() => ({ goals: [] })),
    ]);
    renderTrajectory(traj.goals || []);
    renderMemoirList('completed-goals', d.completed || []);
    renderMemoirList('released-goals',  d.released  || []);
    renderSacrificePattern(d.sacrifice_pattern || {});
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<div class="error-state">Failed to load: ${esc(err.message)}</div>`;
  }
}

function renderTrajectory(goals) {
  if (!goals.length) {
    setHTML('trajectory-goals', '<div class="empty-state">No active achievement goals.</div>');
    return;
  }
  const statusClass = {
    'Ahead':    'status-ahead',
    'On Track': 'status-on-track',
    'Behind':   'status-behind',
    'No data':  'status-no-data',
  };
  setHTML('trajectory-goals', goals.map(g => {
    const daysText = g.days_remaining >= 0
      ? `${g.days_remaining}d remaining`
      : `${Math.abs(g.days_remaining)}d overdue`;

    const trend  = g.weekly_activity_trend || [];
    const maxVal = Math.max(1, ...trend);
    const barHtml = trend.length ? `
      <div class="traj-bars">${trend.map((v, i) => {
        const heightPct = Math.max(2, Math.round((v / maxVal) * 100));
        const cls = i === trend.length - 1 ? 'traj-bar traj-bar-current' : 'traj-bar';
        return `<div class="traj-bar-wrap" title="Week ${i + 1}: ${v} activities">
          <div class="${cls}" style="height:${heightPct}%"></div>
        </div>`;
      }).join('')}</div>` : '';

    const ms = g.current_milestone;
    const msHtml = ms ? `
      <div class="traj-milestone">
        <span class="milestone-state ${esc(ms.state)}"></span>
        <span class="traj-ms-text">${esc(ms.title)}</span>
        ${ms.target_value ? `<span class="traj-ms-progress">${(ms.current_value || 0).toFixed(1)} / ${ms.target_value}</span>` : ''}
      </div>` : '';

    return `
      <div class="traj-card">
        <div class="traj-header">
          <span class="traj-title">${esc(g.title)}</span>
          <span class="traj-status ${statusClass[g.status] || 'status-no-data'}">${esc(g.status)}</span>
        </div>
        <div class="traj-meta">
          ${g.target_date ? `<span>${fmtDate(g.target_date)}</span>` : ''}
          <span class="traj-days">${daysText}</span>
        </div>
        ${barHtml}
        ${msHtml}
      </div>`;
  }).join(''));
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

// ── Add Goal Panel ────────────────────────────────────────────────────────────

let _panelTemplates = null;

async function openAddGoalPanel() {
  const panel = document.getElementById('add-goal-panel');
  if (!panel) return;
  panel.classList.remove('hidden');

  const catSel = document.getElementById('goal-category');
  const tplRow = document.getElementById('goal-template-row');
  const fields = document.getElementById('goal-form-fields');
  if (catSel) catSel.value = '';
  tplRow?.classList.add('hidden');
  fields?.classList.add('hidden');

  if (!_panelTemplates) {
    try {
      const d = await apiFetch('/v1/templates');
      _panelTemplates = d.categories || {};
    } catch {
      _panelTemplates = {};
    }
  }

  if (catSel) {
    catSel.innerHTML = '<option value="">Choose a category…</option>';
    Object.values(_panelTemplates).forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat.id;
      opt.textContent = cat.label;
      catSel.appendChild(opt);
    });
    const custom = document.createElement('option');
    custom.value = '__custom__';
    custom.textContent = 'Custom';
    catSel.appendChild(custom);
  }

  panel.scrollIntoView({ block: 'nearest' });
}

function closeAddGoalPanel() {
  document.getElementById('add-goal-panel')?.classList.add('hidden');
}

async function onCategoryChange() {
  const catId  = document.getElementById('goal-category')?.value;
  const tplRow = document.getElementById('goal-template-row');
  const tplSel = document.getElementById('goal-template');
  const fields = document.getElementById('goal-form-fields');

  if (!catId) {
    tplRow?.classList.add('hidden');
    fields?.classList.add('hidden');
    return;
  }

  if (catId === '__custom__') {
    tplRow?.classList.add('hidden');
    renderGoalTypeFields(null);
    fields?.classList.remove('hidden');
    return;
  }

  const cat = _panelTemplates?.[catId];
  if (!cat || !tplSel) return;

  let activeMetrics = new Set();
  if (catId === 'health_foundation') {
    try {
      const summary = await apiFetch('/v1/goals/summary');
      for (const g of (summary.goals || [])) {
        if (g.goal_type === 'perpetual' && g.target_metric_type) {
          activeMetrics.add(g.target_metric_type);
        }
      }
    } catch {}
  }

  tplSel.innerHTML = '<option value="">Choose a template…</option>';
  (cat.templates || []).forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.id;
    const alreadyActive = t.metric && activeMetrics.has(t.metric);
    if (alreadyActive) {
      opt.textContent = t.label + ' — Already configured';
      opt.disabled = true;
    } else {
      opt.textContent = t.label;
    }
    tplSel.appendChild(opt);
  });

  tplRow?.classList.remove('hidden');
  fields?.classList.add('hidden');
}

function onTemplateChange() {
  const catId  = document.getElementById('goal-category')?.value;
  const tplId  = document.getElementById('goal-template')?.value;
  const fields = document.getElementById('goal-form-fields');

  if (!tplId) { fields?.classList.add('hidden'); return; }

  const cat = _panelTemplates?.[catId];
  const template = cat?.templates?.find(t => t.id === tplId) || null;
  renderGoalTypeFields(template);
  fields?.classList.remove('hidden');
  document.getElementById('goal-title')?.focus();
}

function renderGoalTypeFields(template) {
  const container = document.getElementById('goal-type-fields');
  if (!container) return;

  const titleEl = document.getElementById('goal-title');
  if (titleEl) titleEl.value = template?.suggested_title || '';

  const goalType = template?.goal_type || 'achievement';
  let html = '';

  if (!template) {
    html += `
      <div class="form-group">
        <label class="form-label">Type</label>
        <select class="form-select" id="goal-type-select" onchange="onCustomTypeChange()">
          <option value="achievement">Achievement</option>
          <option value="perpetual">Perpetual</option>
          <option value="habit">Habit</option>
        </select>
      </div>
      <div id="custom-achievement-fields">
        <div class="form-group">
          <label class="form-label">Deadline <span class="form-optional">(optional)</span></label>
          <input type="date" class="form-input" id="goal-target-date">
        </div>
      </div>
      <div id="custom-perpetual-fields" class="hidden">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Target minimum</label>
            <input type="number" class="form-input" id="goal-target-min" step="0.1">
          </div>
          <div class="form-group">
            <label class="form-label">Target maximum</label>
            <input type="number" class="form-input" id="goal-target-max" step="0.1">
          </div>
        </div>
      </div>
      <div id="custom-habit-fields" class="hidden">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Weekly target</label>
            <input type="number" class="form-input" id="goal-habit-target" min="1" value="3">
          </div>
          <div class="form-group">
            <label class="form-label">Unit</label>
            <input type="text" class="form-input" id="goal-habit-unit" placeholder="sessions">
          </div>
        </div>
      </div>`;
  } else if (goalType === 'achievement') {
    html += `
      <div class="form-group">
        <label class="form-label">Event date${template.requires_end_date ? '' : ' <span class="form-optional">(optional)</span>'}</label>
        <input type="date" class="form-input" id="goal-target-date"${template.requires_end_date ? ' required' : ''}>
      </div>`;
  } else if (goalType === 'perpetual') {
    html += `
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Target minimum</label>
          <input type="number" class="form-input" id="goal-target-min" value="${template.default_min ?? ''}" step="0.1">
        </div>
        <div class="form-group">
          <label class="form-label">Target maximum</label>
          <input type="number" class="form-input" id="goal-target-max" value="${template.default_max ?? ''}" step="0.1">
        </div>
      </div>`;
  } else if (goalType === 'habit') {
    const habitUnit   = template.habit_unit   || 'sessions';
    const habitPeriod = template.habit_period || 'week';
    const defaultTarget = template.default_target || 3;
    const periodLabel = { day: 'per day', week: 'per week', month: 'per month' }[habitPeriod] || '';
    html += `
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Target (${esc(habitUnit)} ${esc(periodLabel)})</label>
          <input type="number" class="form-input" id="goal-habit-target" min="1" value="${defaultTarget}">
        </div>
        <div class="form-group">
          <label class="form-label">Unit</label>
          <input type="text" class="form-input" id="goal-habit-unit" value="${esc(habitUnit)}">
        </div>
      </div>`;
  }

  container.innerHTML = html;
}

function onCustomTypeChange() {
  const type = document.getElementById('goal-type-select')?.value || 'achievement';
  document.getElementById('custom-achievement-fields')?.classList.toggle('hidden', type !== 'achievement');
  document.getElementById('custom-perpetual-fields')?.classList.toggle('hidden',  type !== 'perpetual');
  document.getElementById('custom-habit-fields')?.classList.toggle('hidden',      type !== 'habit');
}

async function submitAddGoal() {
  const btn = document.getElementById('goal-submit-btn');
  const err = document.getElementById('goal-form-error');
  if (btn) btn.disabled = true;
  if (err) err.textContent = '';

  try {
    const catId    = document.getElementById('goal-category')?.value;
    const tplId    = document.getElementById('goal-template')?.value;
    const cat      = _panelTemplates?.[catId];
    const template = cat?.templates?.find(t => t.id === tplId) || null;

    const title = document.getElementById('goal-title')?.value.trim();
    if (!title) { if (err) err.textContent = 'Title required.'; return; }

    const description = document.getElementById('goal-description')?.value.trim() || null;

    let goalType = template?.goal_type || 'achievement';
    if (!template && catId === '__custom__') {
      goalType = document.getElementById('goal-type-select')?.value || 'achievement';
    }

    const body = { title, goal_type: goalType };
    if (description) body.description = description;
    if (template?.id) body.template_id = template.id;

    const targetDate = document.getElementById('goal-target-date')?.value;
    if (targetDate) body.target_date = targetDate;

    const minVal = document.getElementById('goal-target-min')?.value;
    const maxVal = document.getElementById('goal-target-max')?.value;
    if (minVal !== '' && minVal != null) body.target_min = parseFloat(minVal);
    if (maxVal !== '' && maxVal != null) body.target_max = parseFloat(maxVal);
    if (template?.metric) body.target_metric_type = template.metric;

    const habitTarget = document.getElementById('goal-habit-target')?.value;
    const habitUnit   = document.getElementById('goal-habit-unit')?.value;
    if (habitTarget) body.weekly_target = parseInt(habitTarget, 10);
    if (habitUnit)   body.habit_unit    = habitUnit;
    if (template?.habit_type)   body.habit_type   = template.habit_type;
    if (template?.habit_period) body.habit_period = template.habit_period;
    if (template?.capture_keywords?.length) body.capture_keywords = template.capture_keywords;

    const res = await fetch('/v1/goals', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${res.status}`);
    }
    closeAddGoalPanel();
    await loadGoals();
  } catch (e) {
    if (err) err.textContent = e.message;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Habit card rendering (type-aware) ─────────────────────────────────────────

function renderHabitBody(g) {
  const habitType   = g.habit_type   || 'count';
  const habitUnit   = g.habit_unit   || 'sessions';
  const habitPeriod = g.habit_period || 'week';
  const periodLabel = { day: 'today', week: 'this week', month: 'this month' }[habitPeriod] || 'this period';
  const target = g.weekly_target || 1;

  if (habitType === 'count') {
    const count = g.this_period_count ?? g.this_week_count ?? 0;
    const pct   = Math.min(Math.round((count / target) * 100), 100);
    return `
      <div class="habit-progress">
        <div class="habit-stat">
          <span class="habit-count" id="habit-count-${g.id}">${count}</span>
          <span class="habit-target">/ ${target}</span>
          <span class="habit-unit">${esc(habitUnit)} ${esc(periodLabel)}</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" id="habit-bar-${g.id}"
               style="width:${pct}%; background:${pct >= 100 ? 'var(--rag-green)' : 'var(--teal)'}"></div>
        </div>
      </div>
      <div class="goal-actions" style="margin-top:0.5rem">
        <button class="btn btn-primary" id="habit-log-btn-${g.id}"
                onclick="logHabit(${g.id}, this, 1)">+1 Done</button>
      </div>`;

  } else if (habitType === 'duration') {
    const mins  = Math.round(g.this_period_sum ?? 0);
    const pct   = Math.min(Math.round((mins / target) * 100), 100);
    return `
      <div class="habit-progress">
        <div class="habit-stat">
          <span class="habit-count" id="habit-count-${g.id}">${mins}</span>
          <span class="habit-target">/ ${target}</span>
          <span class="habit-unit">mins ${esc(periodLabel)}</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" id="habit-bar-${g.id}"
               style="width:${pct}%; background:${pct >= 100 ? 'var(--rag-green)' : 'var(--teal)'}"></div>
        </div>
      </div>
      <div class="goal-actions" style="margin-top:0.5rem; display:flex; align-items:center; gap:0.5rem">
        <input type="number" class="habit-log-value-input" id="habit-duration-${g.id}"
               placeholder="mins" min="1" value="">
        <button class="btn btn-primary" id="habit-log-btn-${g.id}"
                onclick="logHabitValue(${g.id}, this, 'habit-duration-${g.id}')">+ Time</button>
      </div>`;

  } else if (habitType === 'consistency') {
    const streak = g.streak ?? 0;
    return `
      <div class="habit-progress">
        <div class="habit-stat">
          <span class="habit-streak" id="habit-count-${g.id}">${streak}</span>
          <span class="habit-streak-label">day streak</span>
        </div>
      </div>
      <div class="goal-actions" style="margin-top:0.5rem">
        <button class="btn btn-primary" id="habit-log-btn-${g.id}"
                onclick="logHabit(${g.id}, this, 1)">Done today</button>
      </div>`;

  } else if (habitType === 'volume') {
    const total = g.this_period_sum ?? 0;
    const pct   = Math.min(Math.round((total / target) * 100), 100);
    return `
      <div class="habit-progress">
        <div class="habit-stat">
          <span class="habit-count" id="habit-count-${g.id}">${total}</span>
          <span class="habit-target">/ ${target}</span>
          <span class="habit-unit">${esc(habitUnit)} ${esc(periodLabel)}</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" id="habit-bar-${g.id}"
               style="width:${pct}%; background:${pct >= 100 ? 'var(--rag-green)' : 'var(--teal)'}"></div>
        </div>
      </div>
      <div class="goal-actions" style="margin-top:0.5rem; display:flex; align-items:center; gap:0.5rem">
        <input type="number" class="habit-log-value-input" id="habit-volume-${g.id}"
               placeholder="${esc(habitUnit)}" min="1" value="">
        <button class="btn btn-primary" id="habit-log-btn-${g.id}"
                onclick="logHabitValue(${g.id}, this, 'habit-volume-${g.id}')">Log amount</button>
      </div>`;
  }

  // fallback
  const count = g.this_week_count || 0;
  return `<div class="habit-stat"><span class="habit-count">${count}</span><span class="habit-unit">${esc(periodLabel)}</span></div>`;
}

async function logHabitValue(goalId, btn, inputId) {
  const input = document.getElementById(inputId);
  const val   = parseFloat(input?.value);
  if (!val || val <= 0) { if (input) input.focus(); return; }
  await logHabit(goalId, btn, val);
  if (input) input.value = '';
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initCaptureBar();
  document.addEventListener('click', () => { closeMsDropdown(); closeGoalMenus(); });
  window.addEventListener('scroll', closeGoalMenus, { passive: true });

  document.getElementById('add-goal-btn')
    .addEventListener('click', openAddGoalPanel);
});
