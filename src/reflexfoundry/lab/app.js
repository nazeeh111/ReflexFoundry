'use strict';

// This UI is intentionally read-only. Every workspace value is inserted as text.
const $ = (selector) => document.querySelector(selector);
let currentState = { records: [], discoveries: [], policies: [], deployments: [], report: null };
let inspectorValue = null;
const list = (value) => Array.isArray(value) ? value : [];
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value, fallback = 'Not recorded') => value === undefined || value === null || value === '' ? fallback : typeof value === 'object' ? JSON.stringify(value) : String(value);
const field = (item, names, fallback) => {
  for (const name of names) {
    const value = name.split('.').reduce((obj, key) => object(obj) ? obj[key] : undefined, item);
    if (value !== undefined && value !== null) return value;
  }
  return fallback;
};
const number = (value) => typeof value === 'number' && Number.isFinite(value) ? value : null;
const pretty = (value) => JSON.stringify(value, null, 2);
const titleCase = (value) => text(value, '').replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = text(content, '');
  return node;
}
function button(label, callback, className = 'text-button') {
  const node = element('button', className, label);
  node.type = 'button';
  node.addEventListener('click', callback);
  return node;
}
function badge(value) {
  const state = text(value, 'candidate');
  const good = /^(active|deployed|passed|eligible|verified)$/i.test(state);
  const warning = /blocked|reject|fail|rollback|revert|closed/i.test(state);
  return element('span', `badge${good ? ' good' : warning ? ' warning' : ''}`, state);
}
function empty(container, icon, heading, description, command) {
  const block = element('div', 'empty-state');
  block.append(element('span', 'empty-icon', icon), element('h3', '', heading), element('p', '', description));
  if (command) block.append(element('code', '', command));
  container.append(block);
}
function inspect(title, value) {
  inspectorValue = value;
  $('#inspector-title').textContent = title;
  $('#inspector-content').textContent = pretty(value);
  $('#copy-status').textContent = '';
  $('#inspector').showModal();
}
function metric(value, suffix = '') {
  const n = number(value);
  return n === null ? 'Not measured' : `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}
function rate(value) {
  const n = number(value);
  return n === null ? null : Math.min(100, Math.max(0, n <= 1 ? n * 100 : n));
}
function renderDiscoveries() {
  const root = $('#discoveries');
  root.replaceChildren();
  const discoveries = currentState.discoveries;
  $('#nav-decisions').textContent = discoveries.length.toLocaleString();
  if (!discoveries.length) {
    empty(root, '◇', 'No repeated decisions discovered yet', 'Collect authorized records, then run discovery to identify repeated low-risk decision points.', 'reflex --help');
    return;
  }
  discoveries.forEach((item, index) => {
    const card = element('article', 'decision-card');
    const top = element('div', 'card-topline');
    top.append(element('span', 'decision-symbol', index % 2 ? '⌕' : '⌁'), badge(field(item, ['status', 'state'], 'candidate')));
    const heading = field(item, ['name', 'decision', 'decision_id', 'spec_id', 'kind', 'id'], `Decision ${index + 1}`);
    card.append(top, element('h3', '', titleCase(heading)), element('p', '', field(item, ['description', 'reason', 'summary'], 'Inspect the observed inputs, candidate choices, and independent success criteria before training.')));
    const meta = element('div', 'card-metadata');
    const count = field(item, ['count', 'records', 'n', 'record_count', 'support']);
    meta.append(element('span', '', typeof count === 'number' ? `${count.toLocaleString()} ${count === 1 ? 'observation' : 'observations'}` : 'Inspect discovery evidence'), button('Inspect decision ↗', () => inspect(text(heading), item)));
    card.append(meta);
    root.append(card);
  });
}
function renderPolicies() {
  const root = $('#policy-rows');
  root.replaceChildren();
  const policies = currentState.policies;
  $('#policies-empty').hidden = policies.length > 0;
  $('#nav-policies').textContent = policies.length.toLocaleString();
  $('#policy-total').textContent = `${policies.length} ${policies.length === 1 ? 'policy' : 'policies'}`;
  policies.forEach((policy, index) => {
    const row = element('tr');
    const name = field(policy, ['name', 'policy_id', 'id', 'model'], `Policy ${index + 1}`);
    const identity = element('td');
    identity.append(element('span', 'cell-primary', name), element('span', 'cell-secondary', field(policy, ['version', 'digest', 'sha256', 'path'], 'Version not recorded')));
    const choice = element('td', '', titleCase(field(policy, ['decision', 'spec_id', 'spec', 'decision_id', 'kind'], 'Unspecified')));
    const status = element('td');
    status.append(badge(field(policy, ['status', 'state', 'mode'], 'candidate')));
    const evidence = element('td');
    evidence.append(button('Inspect ↗', () => inspect(text(name), policy)));
    row.append(identity, choice, status, evidence);
    root.append(row);
  });
}
function reportRows(report) {
  if (!object(report)) return [];
  for (const name of ['baselines', 'policies', 'results', 'comparisons', 'metrics', 'summary']) {
    const value = report[name];
    if (Array.isArray(value)) return value.filter(object);
    if (object(value)) {
      const entries = Object.entries(value).filter(([, item]) => object(item));
      if (entries.length) return entries.map(([name, item]) => ({ name, ...item }));
    }
  }
  return [];
}
function renderReport() {
  const root = $('#benchmark');
  root.replaceChildren();
  const report = currentState.report;
  $('#inspect-report').disabled = !report;
  const summary = $('#evidence-summary');
  summary.replaceChildren();
  const addFact = (label, value) => summary.append(element('dt', '', label), element('dd', '', value));
  if (!report) {
    empty(root, '▥', 'Evidence starts with a real run', 'Run the reproducible benchmark to compare the original workflow, simple heuristics, and learned policies. No estimated savings are shown.', 'reflex --help');
    addFact('Evaluation', 'No report loaded');
    addFact('Deployment gate', 'Closed until evidence supports use');
    return;
  }
  const rows = reportRows(report);
  if (!rows.length) empty(root, '▥', 'Evaluation artifact available', 'Open the evidence inspector to review the complete report. This report does not expose comparable summary rows.');
  rows.forEach((result, index) => {
    const row = element('div', 'benchmark-row');
    const name = field(result, ['name', 'policy', 'policy_id', 'baseline', 'method', 'mode'], `Result ${index + 1}`);
    const success = rate(field(result, ['success_rate', 'task_success', 'task_success_rate', 'metrics.success_rate']));
    const total = number(field(result, ['n', 'tasks', 'count', 'total', 'evaluated']));
    const correct = number(field(result, ['successes', 'passed', 'correct']));
    const observedRate = success === null && total && correct !== null ? 100 * correct / total : success;
    const heading = element('div', 'benchmark-name');
    heading.append(element('strong', '', titleCase(name)), element('span', '', observedRate === null ? 'No success rate' : `${observedRate.toFixed(1)}% success`));
    row.append(heading);
    if (observedRate !== null) {
      const track = element('div', 'bar-track');
      const fill = element('div', 'bar-fill');
      fill.style.width = `${Math.min(100, Math.max(0, observedRate))}%`;
      track.setAttribute('role', 'img');
      track.setAttribute('aria-label', `${text(name)}: ${observedRate.toFixed(1)} percent task success`);
      track.append(fill);
      row.append(track);
    }
    const detail = element('div', 'benchmark-details');
    const elapsed = field(result, ['mean_ms', 'latency_ms', 'total_ms', 'elapsed_ms', 'mean_total_ms', 'mean_latency_ms', 'time_ms']);
    const timeLabel = ['mean_ms', 'mean_total_ms', 'mean_latency_ms', 'latency_ms'].some((key) => number(result[key]) !== null) ? 'Mean time' : 'Elapsed time';
    const fallback = rate(field(result, ['fallback_rate', 'abstention_rate', 'metrics.fallback_rate']));
    detail.append(element('span', '', `${timeLabel}: ${metric(elapsed, ' ms')}`), element('span', '', fallback === null ? 'Fallback: not recorded' : `Fallback: ${fallback.toFixed(1)}%`));
    if (total !== null) detail.append(element('span', '', `n = ${total.toLocaleString()}`));
    const startup = number(result.startup_ms);
    if (startup !== null) detail.append(element('span', '', `Startup: ${metric(startup, ' ms')}`));
    const errors = number(result.errors);
    if (errors !== null) detail.append(element('span', '', `Errors: ${errors.toLocaleString()}`));
    const cost = number(field(result, ['cost_usd', 'model_cost_usd', 'total_cost_usd']));
    if (cost !== null) detail.append(element('span', '', `Model cost: $${cost.toFixed(4)}`));
    row.append(detail);
    root.append(row);
  });
  const scopeNote = report.scope ? `${text(report.scope)} ` : '';
  const gateNote = typeof report.deployment_allowed === 'boolean' ? (report.deployment_allowed ? 'Evaluation permits bounded opt-in. ' : 'Deployment gate closed. ') : '';
  root.append(element('p', 'report-note', `${scopeNote}${gateNote}Read the full artifact for split provenance, uncertainty, incorrect decisions, startup cost, and comparison limits.`));
  addFact('Evaluation', field(report, ['name', 'benchmark', 'experiment', 'run_id', 'version'], 'Local experiment artifact'));
  addFact('Deployment gate', typeof report.deployment_allowed === 'boolean' ? (report.deployment_allowed ? 'Evaluation permits bounded opt-in' : 'Closed: outcome or cost requirements not met') : field(report, ['gate.reason', 'promotion.reason', 'deployment.reason', 'gate', 'eligible', 'promotable'], 'Inspect report for the deployment decision'));
  if (list(report.reasons).length) addFact('Gate evidence', report.reasons.join('; '));
  if (report.scope) addFact('Evaluation scope', report.scope);
  if (number(report.calibration?.threshold) !== null) addFact('Abstention threshold', report.calibration.threshold);
  const split = field(report, ['split', 'test_split', 'held_out', 'provenance.test']);
  if (split !== undefined) addFact('Held-out evidence', text(split));
}
function renderRecords() {
  const root = $('#record-rows');
  root.replaceChildren();
  const query = $('#record-search').value.toLowerCase().trim();
  const filtered = currentState.records.filter((record) => !query || JSON.stringify(record).toLowerCase().includes(query));
  const visible = filtered.slice(0, 100);
  $('#records-empty').hidden = visible.length > 0;
  const emptyTitle = $('#records-empty h3');
  const emptyDescription = $('#records-empty p');
  emptyTitle.textContent = query ? 'No matching records' : 'No decision records';
  emptyDescription.textContent = query ? 'Try a different decision, repository, or record identifier.' : 'Use the CLI to collect an authorized decision or run the reproducible example.';
  $('#records-empty code').hidden = Boolean(query);
  visible.forEach((record, index) => {
    const row = element('tr');
    const name = field(record, ['id', 'record_id', 'task_id'], `Record ${index + 1}`);
    const identity = element('td');
    identity.append(element('span', 'cell-primary', name), element('span', 'cell-secondary', field(record, ['split', 'timestamp', 'created_at'], 'Local observation')));
    const context = element('td');
    context.append(element('span', 'cell-primary', titleCase(field(record, ['decision', 'spec_id', 'spec', 'decision_id', 'kind'], 'Decision'))), element('span', 'cell-secondary', field(record, ['repository', 'repo', 'group', 'repo_id'], 'Repository not recorded')));
    const choice = element('td', '', field(record, ['choice', 'selected', 'action', 'label', 'expected', 'gold'], 'Not recorded'));
    const action = element('td');
    action.append(button('Inspect ↗', () => inspect(text(name), record)));
    row.append(identity, context, choice, action);
    root.append(row);
  });
  $('#records-caption').textContent = currentState.records.length ? `Showing ${visible.length.toLocaleString()} of ${filtered.length.toLocaleString()} ${query ? 'matching ' : ''}records. ${filtered.length > 100 ? 'Filter to inspect additional records.' : ''}` : 'No private transcripts are collected by this view.';
}
function deploymentStatus() {
  const latest = currentState.deployments.at(-1);
  const active = currentState.deployments.filter((item) => /^(deployed|active)$/i.test(text(field(item, ['status', 'state', 'mode', 'action'], ''))));
  const state = latest ? titleCase(field(latest, ['status', 'state', 'mode', 'action'], 'Recorded')) : 'Inactive';
  $('#deployment-state').textContent = state;
  $('#deployment-caption').textContent = active.length ? 'Inspect history and current policy boundaries' : 'No active use inferred without deployment evidence';
  return latest;
}
function renderDeployments() {
  const root = $('#deployment-list');
  root.replaceChildren();
  const events = currentState.deployments.flatMap((deployment) => list(deployment.history).length ? deployment.history.map((event) => ({ ...event, policy: deployment.policy, mode: event.to, deployment_mode: deployment.mode })) : [deployment]);
  if (!events.length) {
    empty(root, '↶', 'No deployments recorded', 'Policies begin as candidates. Shadow use and bounded deployment are controlled through the CLI after evaluation.');
    return;
  }
  [...events].reverse().forEach((event, index) => {
    const state = field(event, ['status', 'state', 'mode', 'action'], 'event');
    const name = field(event, ['policy_id', 'policy', 'name', 'id'], `Deployment ${events.length - index}`);
    const row = element('article', `deployment-item${/rollback|revert|fail|disable/i.test(text(state)) ? ' rollback' : ''}`);
    const info = element('div', 'deployment-info');
    info.append(element('strong', '', `${titleCase(state)} · ${text(name)}`), element('p', '', field(event, ['reason', 'message', 'spec_id', 'spec', 'decision'], 'Inspect event for policy boundaries and evidence')));
    row.append(element('span', 'deployment-dot'), info);
    const when = field(event, ['timestamp', 'created_at', 'time']);
    if (when) row.append(element('time', '', when));
    row.append(button('Inspect ↗', () => inspect(`Deployment · ${text(name)}`, event)));
    root.append(row);
  });
}
function render() {
  $('#record-count').textContent = currentState.records.length.toLocaleString();
  $('#policy-count').textContent = currentState.policies.length.toLocaleString();
  const latest = deploymentStatus();
  const stages = {
    observe: currentState.records.length > 0,
    discover: currentState.discoveries.length > 0,
    train: currentState.policies.length > 0,
    evaluate: Boolean(currentState.report),
    shadow: currentState.deployments.some((item) => /shadow/i.test(text(field(item, ['status', 'state', 'mode', 'action'], '')))),
    deploy: currentState.deployments.some((item) => /^(deployed|active)$/i.test(text(field(item, ['status', 'state', 'mode', 'action'], '')))),
    monitor: Boolean(latest && field(latest, ['monitor', 'metrics', 'outcome', 'regression'], false))
  };
  document.querySelectorAll('[data-stage]').forEach((step) => step.classList.toggle('reached', stages[step.dataset.stage]));
  renderDiscoveries();
  renderPolicies();
  renderReport();
  renderRecords();
  renderDeployments();
}
async function refresh() {
  const refreshButton = $('#refresh');
  refreshButton.disabled = true;
  refreshButton.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('/api/state', { cache: 'no-store', credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Workspace request returned HTTP ${response.status}.`);
    const state = await response.json();
    if (!object(state)) throw new Error('The workspace returned an invalid state document.');
    currentState = { ...state, records: list(state.records), discoveries: list(state.discoveries), policies: list(state.policies), deployments: list(state.deployments), report: state.report || null };
    render();
    $('#error').hidden = true;
    $('#connection').className = 'connection connected';
    $('#connection').replaceChildren(element('span', 'status-dot'), document.createTextNode('Local · connected'));
    $('#updated-at').textContent = `Refreshed ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  } catch (error) {
    $('#connection').className = 'connection failed';
    $('#connection').replaceChildren(element('span', 'status-dot'), document.createTextNode('Connection unavailable'));
    $('#error').textContent = `${error.message} Start the local Lab with the CLI, then refresh. Previously loaded values remain visible.`;
    $('#error').hidden = false;
  } finally {
    refreshButton.disabled = false;
    refreshButton.removeAttribute('aria-busy');
  }
}
$('#refresh').addEventListener('click', refresh);
$('#record-search').addEventListener('input', renderRecords);
$('#inspect-report').addEventListener('click', () => inspect('Independent evaluation report', currentState.report));
$('#close-inspector').addEventListener('click', () => $('#inspector').close());
$('#inspector').addEventListener('click', (event) => {
  if (event.target !== $('#inspector')) return;
  const bounds = $('#inspector').getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) $('#inspector').close();
});
$('#copy-evidence').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(pretty(inspectorValue));
    $('#copy-status').textContent = 'JSON copied';
  } catch {
    $('#copy-status').textContent = 'Clipboard unavailable. Select the JSON above to copy it.';
  }
});
document.querySelectorAll('.nav-link').forEach((link) => link.addEventListener('click', () => {
  document.querySelectorAll('.nav-link').forEach((item) => item.classList.toggle('active', item === link));
}));
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    document.querySelectorAll('.nav-link').forEach((item) => item.classList.toggle('active', item.hash === `#${visible.target.id}`));
  }, { rootMargin: '-15% 0px -55% 0px', threshold: 0 });
  document.querySelectorAll('.section-anchor').forEach((section) => observer.observe(section));
}
render();
refresh();
