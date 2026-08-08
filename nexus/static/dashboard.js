function fmt(value) {
  if (value === null || value === undefined || value === '') return '—';
  return value;
}

function fmtTime(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function statusClass(status) {
  return `status status-${status}`;
}

function renderMetrics(summary) {
  const items = [
    ['Total Work', summary.total_work],
    ['ACCEPTED', summary.accepted],
    ['PROCESSING', summary.processing],
    ['RETRY_WAIT', summary.retry_wait],
    ['COMPLETED', summary.completed],
    ['FAILED', summary.failed],
    ['Workers', summary.registered_workers],
  ];

  document.getElementById('metrics').innerHTML = items.map(
    ([label, value]) => `
      <div class="metric">
        <div class="metric-label">${label}</div>
        <div class="metric-value">${value}</div>
      </div>`
  ).join('');
}

function renderHealth(summary) {
  const badge = document.getElementById('health-badge');
  const detail = document.getElementById('health-detail');
  detail.textContent = summary.health_detail;

  badge.className = 'badge';
  if (summary.health === 'attention') {
    badge.classList.add('badge-bad');
    badge.textContent = 'Attention';
  } else if (summary.health === 'degraded') {
    badge.classList.add('badge-warn');
    badge.textContent = 'Degraded';
  } else {
    badge.classList.add('badge-ok');
    badge.textContent = 'OK';
  }
}

function renderWork(workItems) {
  const tbody = document.getElementById('work-table');
  if (!workItems.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty">No work items yet.</td></tr>';
    return;
  }

  tbody.innerHTML = workItems.map((item) => `
    <tr>
      <td>${fmt(item.id)}</td>
      <td><span class="${statusClass(item.status)}">${fmt(item.status)}</span></td>
      <td>${fmt(item.priority)}</td>
      <td>${item.attempt_count}/${item.max_attempts}</td>
      <td>${fmt(item.assigned_worker_id)}</td>
      <td>${fmtTime(item.created_at)}</td>
      <td>${fmtTime(item.lease_expires_at)}</td>
      <td>${fmt(item.failure_reason)}</td>
    </tr>
  `).join('');
}

function renderWorkers(workers) {
  const tbody = document.getElementById('worker-table');
  if (!workers.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">No workers registered.</td></tr>';
    return;
  }

  tbody.innerHTML = workers.map((worker) => `
    <tr>
      <td>${fmt(worker.id)}</td>
      <td><span class="${statusClass(worker.status)}">${fmt(worker.status)}</span></td>
      <td>${fmt(worker.current_work_id)}</td>
      <td>${fmtTime(worker.last_heartbeat_at)}</td>
      <td>${fmtTime(worker.last_activity_at)}</td>
      <td>${fmtTime(worker.lease_expires_at)}</td>
      <td>${fmt(worker.failure_mode)}</td>
    </tr>
  `).join('');
}

function renderEvents(events) {
  const tbody = document.getElementById('event-table');
  if (!events.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">No events recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = events.map((event) => {
    const details = event.details
      ? JSON.stringify(event.details)
      : event.reason;
    return `
      <tr>
        <td>${fmtTime(event.timestamp)}</td>
        <td>${fmt(event.event_type)}</td>
        <td>${fmt(event.action)}</td>
        <td>${fmt(event.work_id)}</td>
        <td>${fmt(event.worker_id)}</td>
        <td class="details-cell">${fmt(details)}</td>
      </tr>`;
  }).join('');
}

async function refresh() {
  try {
    const res = await fetch('/api/operator/snapshot?event_limit=50');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    renderHealth(data.summary);
    renderMetrics(data.summary);
    renderWork(data.work);
    renderWorkers(data.workers);
    renderEvents(data.events);
    document.getElementById('last-updated').textContent =
      `Last updated ${new Date().toLocaleTimeString()} · read-only · auto-refresh every 3s`;
  } catch (err) {
    document.getElementById('health-detail').textContent =
      `Cannot load dashboard data: ${err.message}`;
    document.getElementById('health-badge').className = 'badge badge-bad';
    document.getElementById('health-badge').textContent = 'Offline';
  }
}

refresh();
setInterval(refresh, 3000);
