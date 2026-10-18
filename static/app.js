const $ = (selector) => document.querySelector(selector);
const normalizePartyName = (name) => name.normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ');
const form = $('#analysis-form');
const textBox = $('#contract-text');
const leToggle = $('#include-le');
const button = $('#submit-button');
let modelsReady = false;
let initializationPromise = null;
let healthMonitorStarted = false;
let healthRefreshRunning = false;

textBox.addEventListener('input', () => { $('#char-count').textContent = `${textBox.value.length.toLocaleString()} / 120,000`; });
leToggle.addEventListener('change', () => { $('#le-fields').hidden = !leToggle.checked; });
document.querySelectorAll('.choice-group').forEach((group) => {
  group.addEventListener('click', (event) => {
    const choice = event.target.closest('button[data-value]');
    if (!choice) return;
    group.querySelectorAll('button').forEach((button) => button.classList.toggle('selected', button === choice));
    group.dataset.selected = choice.dataset.value;
  });
});

function renderInitializationStatus(status) {
  const percent = Math.max(0, Math.min(100, Number(status.progress) || 0));
  $('#readiness-progress').style.width = `${percent}%`;
  $('#readiness-percent').textContent = `${percent}%`;
  $('#readiness-message').textContent = status.message || 'Preparing analysis agents.';
  for (const [name, value] of Object.entries(status.agents || {})) {
    const card = document.querySelector(`.agent-check[data-agent="${name}"]`);
    if (!card) continue;
    card.dataset.status = value;
    card.querySelector('.check-indicator').textContent = value === 'ready' ? '✓' : value === 'loading' ? '…' : value === 'error' ? '!' : '·';
    card.querySelector('em').textContent = value === 'ready' ? 'Ready' : value === 'loading' ? 'Loading' : value === 'error' ? 'Error' : 'Waiting';
  }
  $('#retry-initialization').hidden = status.status !== 'failed';
  if (status.status === 'ready') {
    modelsReady = true;
    startAgentHealthMonitoring();
  }
}

function renderAgentHealth(report) {
  for (const [name, result] of Object.entries(report.agents || {})) {
    const element = document.querySelector(`.health-check[data-health="${name}"]`);
    if (!element) continue;
    const state = result.status || 'pending';
    element.textContent = `Health: ${state === 'healthy' ? 'OK' : state}`;
    element.dataset.status = state;
    element.title = result.message || '';
  }
}

async function refreshAgentHealth() {
  if (healthRefreshRunning || !modelsReady) return;
  healthRefreshRunning = true;
  try {
    await fetch('/agent-health-check', { method: 'POST' });
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const response = await fetch('/agent-health');
      if (!response.ok) throw new Error('Health status request failed.');
      const report = await response.json();
      renderAgentHealth(report);
      if (report.status !== 'checking') break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  } catch {
    document.querySelectorAll('.health-check').forEach((element) => { element.textContent = 'Health: unavailable'; element.dataset.status = 'unavailable'; });
  } finally {
    healthRefreshRunning = false;
  }
}

function startAgentHealthMonitoring() {
  if (healthMonitorStarted) return;
  healthMonitorStarted = true;
  refreshAgentHealth();
  window.setInterval(() => {
    if (document.visibilityState === 'visible') refreshAgentHealth();
  }, 30000);
}

async function fetchInitializationStatus() {
  const response = await fetch('/initialization-status');
  if (!response.ok) throw new Error('Could not read agent initialization status.');
  return response.json();
}

async function initializeModels() {
  renderInitializationStatus({ status: 'initializing', progress: 1, message: 'Starting background initialization…', agents: { CRA: 'pending', CL: 'pending', COI: 'pending', LE: 'pending' } });
  const startResponse = await fetch('/initialize', { method: 'POST' });
  if (!startResponse.ok) throw new Error('Could not start model initialization.');
  while (true) {
    const status = await fetchInitializationStatus();
    renderInitializationStatus(status);
    if (status.status === 'ready') return;
    if (status.status === 'failed') throw new Error(status.message || 'Agent initialization failed.');
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
}

function ensureModelsReady() {
  if (modelsReady) return Promise.resolve();
  if (!initializationPromise) {
    initializationPromise = initializeModels().catch((error) => {
      $('#readiness-message').textContent = error.message || 'Agent initialization failed.';
      $('#retry-initialization').hidden = false;
      initializationPromise = null;
      throw error;
    });
  }
  return initializationPromise;
}

$('#retry-initialization').addEventListener('click', () => {
  ensureModelsReady().catch(() => {});
});

// Warm all agents as soon as the frontend opens; contract submission can share this promise.
ensureModelsReady().catch(() => {});

function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined && content !== null) element.textContent = String(content);
  return element;
}
function showState(name) {
  $('#empty-state').hidden = name !== 'empty';
  $('#result-content').hidden = name !== 'result';
}
function label(value, fallback = 'Unknown') {
  return value === undefined || value === null || value === '' ? fallback : String(value);
}
function riskClass(value) {
  const normalized = String(value || '').toLowerCase();
  return normalized.includes('high') ? 'risk-high' : normalized.includes('medium') ? 'risk-medium' : (normalized.includes('low') ? 'risk-low' : 'risk-baseline');
}
function metric(title, value, sub = '') {
  const box = node('div', 'metric');
  box.append(node('div', 'metric-label', title), node('div', 'metric-value', value), node('div', 'metric-sub', sub));
  return box;
}
function uniqueByOccurrence(items, typeKey = 'type') {
  const seen = new Set();
  return (items || []).filter((item) => {
    const key = [item.clause_id || '', item.start ?? '', item.end ?? '', item[typeKey] || '', item.value || ''].join('|');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
function uniqueFindingsByOccurrence(items) {
  const sensitivityRank = { CRITICAL: 5, HIGH: 4, MEDIUM: 3, LOW: 2, CONTEXT_DEPENDENT: 1 };
  const byOccurrence = new Map();
  for (const item of items || []) {
    const hasSpan = item.start !== null && item.start !== undefined && item.end !== null && item.end !== undefined
      && Number.isFinite(Number(item.start)) && Number.isFinite(Number(item.end));
    const key = hasSpan
      ? [item.clause_id || '', item.start, item.end].join('|')
      : [item.clause_id || '', String(item.value || '').trim().toLocaleLowerCase(), item.type || ''].join('|');
    const previous = byOccurrence.get(key);
    const rank = sensitivityRank[String(item.sensitivity || '').toUpperCase()] || 0;
    const previousRank = sensitivityRank[String(previous?.sensitivity || '').toUpperCase()] || 0;
    const isMoreSpecific = previous?.source === 'ner' && item.source !== 'ner';
    if (!previous || rank > previousRank || (rank === previousRank && isMoreSpecific)) byOccurrence.set(key, item);
  }
  return [...byOccurrence.values()].sort((a, b) =>
    String(a.clause_id || '').localeCompare(String(b.clause_id || '')) ||
    (Number(a.start) || 0) - (Number(b.start) || 0));
}
function maskEvidence(type, value) {
  const text = String(value || '').trim();
  if (!text) return 'Not available';
  if (type === 'EMAIL' && text.includes('@')) return `${text.split('@')[0].slice(0, 1)}***@${text.split('@')[1]}`;
  if (['PHONE_NUMBER', 'AADHAAR_NUMBER', 'PAN_NUMBER', 'BANK_ACCOUNT', 'IBAN', 'CREDIT_CARD', 'POSTAL_CODE'].includes(type)) {
    const digits = text.replace(/\D/g, '');
    return digits.length <= 4 ? '*'.repeat(digits.length) : `${'*'.repeat(digits.length - 4)}${digits.slice(-4)}`;
  }
  if (type === 'IP_ADDRESS') return text.replace(/\d+(?=\.\d+\.\d+\.\d+$)/, '***').replace(/\d+(?=\.\d+\.\d+$)/, '***').replace(/\d+(?=\.\d+$)/, '***');
  if (type.startsWith('CONFIDENTIAL_')) return `[${type}]`;
  if (['PERSON', 'ORG', 'GPE', 'LOC', 'ADDRESS'].includes(type)) {
    return text.replace(/[A-Za-z0-9]+/g, (word) => word.length <= 1 ? '*' : word.length === 2 ? `${word[0]}*` : `${word[0]}${'*'.repeat(word.length - 2)}${word.at(-1)}`);
  }
  return '***';
}
function renderDataTable(headers, rows) {
  const wrapper = node('div', 'data-table-wrap');
  const table = node('table', 'data-table');
  const thead = document.createElement('thead');
  const heading = document.createElement('tr');
  headers.forEach((title) => heading.append(node('th', '', title)));
  thead.append(heading);
  const tbody = document.createElement('tbody');
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    row.forEach((value) => tr.append(node('td', '', value)));
    tbody.append(tr);
  });
  table.append(thead, tbody);
  wrapper.append(table);
  return wrapper;
}
function combinedAgentScore(report) {
  const scores = [];
  const bandScore = { baseline: 0, seed: 0, low: 25, medium: 50, high: 75, critical: 100 };
  const craScores = (report.clauses || []).map((item) => bandScore[String(item.cra?.model?.prediction || '').toLowerCase()]).filter(Number.isFinite);
  if (craScores.length) scores.push(Math.max(...craScores)); // One CRA score: highest predicted ML risk band.

  const clScore = Number(report.confidentiality?.risk_score);
  if (Number.isFinite(clScore)) scores.push(Math.max(0, Math.min(100, clScore))); // Use CL's own score directly.

  const graph = report.coi?.graph_result || {};
  const coiBands = { none: 0, low: 35, medium: 65, high: 100 };
  const severity = String(graph.severity || '').toLowerCase();
  if (graph.conflict_detected === true && Number.isFinite(coiBands[severity])) scores.push(coiBands[severity]);
  else if (graph.status === 'complete' && graph.conflict_detected === false) scores.push(0);

  const le = report.litigation_exposure || {};
  const probability = Number(le.litigation_probability);
  if (le.status === 'complete' && Number.isFinite(probability)) scores.push(Math.max(0, Math.min(100, probability * 100)));
  return scores.length ? { score: Math.round(scores.reduce((sum, value) => sum + value, 0) / scores.length), count: scores.length } : { score: null, count: 0 };
}
function section(code, title, subtitle) {
  const card = node('section', 'agent-card');
  const heading = node('div', 'agent-title');
  heading.append(node('span', 'agent-icon', code), node('strong', '', title), node('span', 'sub', subtitle || ''));
  card.append(heading);
  const body = node('div', 'agent-body'); card.append(body);
  return { card, body };
}
function addPairs(container, pairs) {
  const row = node('div', 'mini-stats');
  for (const [name, value] of pairs) row.append(node('span', '', `${name}: ${label(value)}`));
  container.append(row);
}
function showOverallSummary(summary) {
  const dialog = $('#overall-summary-dialog');
  const content = $('#overall-summary-content');
  content.replaceChildren();
  if (!summary || summary.status !== 'complete') {
    content.append(node('p', 'result-note', summary?.message || 'The overall LLM summary is unavailable.'));
  } else {
    content.append(node('p', 'summary-lead', summary.overall_assessment || 'No overall assessment was returned.'));
    for (const [title, value] of [['CRA model and clause analysis', summary.cra_summary], ['CL confidentiality findings', summary.cl_summary]]) {
      const block = node('section', 'summary-block');
      block.append(node('h3', '', title), node('p', '', value || 'No summary returned.'));
      content.append(block);
    }
    for (const [title, items] of [['Key risks', summary.key_risks], ['Review priorities', summary.review_priorities]]) {
      const block = node('section', 'summary-block');
      block.append(node('h3', '', title));
      if (Array.isArray(items) && items.length) {
        const list = node('ul', 'summary-list');
        items.forEach((item) => list.append(node('li', '', String(item))));
        block.append(list);
      } else block.append(node('p', '', 'None reported.'));
      content.append(block);
    }
    content.append(node('p', 'summary-limit', summary.limitations || 'Automated summary; review the underlying agent results.'));
  }
  const source = summary?.source_inputs || {};
  const craOutputs = (source.cra_clause_results || [])
    .filter((item) => item.llm_output && Object.values(item.llm_output).some((value) => value !== null && value !== undefined))
    .map((item) => ({ clause_id: item.clause_id, ...item.llm_output }));
  const sourceBlocks = [
    ['CRA clause LLM output (verbatim)', craOutputs],
    ['CL output sent to the overall LLM (verbatim)', {
      skipped_clauses: source.skipped_clauses || [],
      confidentiality: source.confidentiality || {},
    }],
  ];
  for (const [title, value] of sourceBlocks) {
    const block = node('section', 'summary-block');
    block.append(node('h3', '', title));
    block.append(node('pre', 'summary-json', JSON.stringify(value, null, 2)));
    content.append(block);
  }
  dialog.showModal();
}
$('#close-summary').addEventListener('click', () => $('#overall-summary-dialog').close());
function renderLLMAnalysis(clauses) {
  const list = node('div', 'clause-list');
  clauses.forEach((item) => {
    const risk = item.cra || {};
    const analysis = risk.analysis || {};
    const card = node('article', 'clause-item');
    const header = node('div', 'clause-head');
    header.append(node('span', 'clause-id', `Clause ${label(item.clause_id, item.clause_number || '?')}`));
    for (const trigger of item.llm_trigger || []) header.append(node('span', 'risk-badge risk-baseline', trigger));
    if (analysis.assessed_risk) header.append(node('span', `risk-badge ${riskClass(analysis.assessed_risk)}`, `LLM ${analysis.assessed_risk}`));
    card.append(header);
    const reason = analysis.risk_reasoning || analysis.summary || (risk.llm_analysis_skipped ? 'LLM analysis was not run for this clause.' : item.cra_error);
    if (reason) card.append(node('p', 'clause-reason', reason));
    if (analysis.human_review_required) card.append(node('p', 'clause-reason', 'Human review required'));
    if (analysis.summary && analysis.risk_reasoning && analysis.summary !== analysis.risk_reasoning) card.append(node('p', 'result-note', analysis.summary));
    const clauseText = item.text || '';
    if (clauseText) {
      const text = node('p', 'clause-text', clauseText);
      if (clauseText.length > 280) { text.textContent = `${clauseText.slice(0, 280)}…`; text.dataset.full = clauseText; text.dataset.short = text.textContent; }
      card.append(text);
      if (clauseText.length > 280) {
        const toggle = node('button', 'expand-link', 'Show full clause'); toggle.type = 'button';
        toggle.addEventListener('click', () => { const expanded = toggle.dataset.expanded === 'true'; text.textContent = expanded ? text.dataset.short : text.dataset.full; toggle.textContent = expanded ? 'Show full clause' : 'Show less'; toggle.dataset.expanded = String(!expanded); });
        card.append(toggle);
      }
    }
    list.append(card);
  });
  return list;
}
function renderCOI(report) {
  const coi = report.coi || {};
  const graph = coi.graph_result || {};
  const { card, body } = section('COI', 'Conflict of interest', label(graph.status || coi.status, 'Unknown'));
  const parties = coi.party_roles || {};
  const partyPairs = Object.entries(parties)
    .filter(([, value]) => value !== null && value !== undefined && value !== '' && (!Array.isArray(value) || value.length))
    .map(([key, value]) => [key, Array.isArray(value) ? value.join(', ') : value]);
  if (partyPairs.length) addPairs(body, partyPairs);
  addPairs(body, [
    ['Graph status', label(graph.status, 'Unknown')],
    ['Severity', label(graph.severity, 'Unknown')],
    ['Conflict', graph.conflict_detected === true ? 'Yes' : graph.conflict_detected === false ? 'No' : 'Unknown'],
  ]);
  if (graph.note || graph.skipped_reason || coi.graph_error) {
    body.append(node('p', 'result-note', graph.note || graph.skipped_reason || `Graph lookup error: ${coi.graph_error}`));
  }
  const clauseFindings = coi.clause_findings || [];
  if (clauseFindings.length) {
    body.append(node('h4', 'summary-table-title', 'Clause evidence (not graph verified)'));
    body.append(renderDataTable(
      ['Finding', 'Person', 'Severity', 'Evidence'],
      clauseFindings.map((finding) => [
        label(finding.type, 'Potential conflict').replaceAll('_', ' '),
        label(finding.person),
        label(finding.severity),
        label(finding.evidence || finding.relationship),
      ]),
    ));
  }
  const entities = (coi.entities || []).map((entity) => entity.name).filter(Boolean);
  if (entities.length) body.append(node('p', 'result-note', `Entities searched: ${[...new Set(entities)].join(', ')}`));
  if (!partyPairs.length && !clauseFindings.length && !entities.length && !graph.note && !graph.skipped_reason && !coi.graph_error) {
    body.append(node('p', 'result-note', 'No additional COI details were returned.'));
  }
  return card;
}
function renderLE(report) {
  const le = report.litigation_exposure || { status: 'not_requested' };
  const { card, body } = section('LE', 'Litigation exposure', label(le.risk_level, le.status === 'complete' ? 'Complete' : le.status));
  if (le.status === 'complete') {
    const probability = le.litigation_probability === null || le.litigation_probability === undefined
      ? Number.NaN : Number(le.litigation_probability);
    addPairs(body, [
      ['Risk level', label(le.risk_level)],
      ['Litigation probability', Number.isFinite(probability) ? `${(probability * 100).toFixed(1)}%` : 'Unavailable'],
      ['COI conflict flag', le.conflict_flag === 1 || le.conflict_flag === true ? '1 (Yes)' : le.conflict_flag === 0 || le.conflict_flag === false ? '0 (No)' : 'Unknown'],
    ]);
    if (le.conflict_flag_source) body.append(node('p', 'result-note', `Conflict flag source: ${le.conflict_flag_source}`));
    const contributions = Object.entries(le.shap_explanation || {})
      .filter(([, value]) => Number.isFinite(Number(value)))
      .sort((a, b) => Math.abs(Number(b[1])) - Math.abs(Number(a[1])))
      .slice(0, 3);
    if (contributions.length) body.append(node('p', 'result-note', `Top model contributions: ${contributions.map(([name, value]) => `${name} ${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(3)}`).join(' | ')}`));
  } else if (le.status === 'skipped' || le.status === 'unavailable') {
    body.append(node('p', 'result-note', le.reason || `LE analysis ${le.status}.`));
    if (le.conflict_flag !== undefined) body.append(node('p', 'result-note', `COI conflict flag: ${le.conflict_flag} (${label(le.conflict_flag_source, 'source unavailable')}).`));
  } else {
    body.append(node('p', 'result-note', le.status === 'not_requested' ? 'LE prediction was not requested for this contract.' : 'No LE prediction was returned.'));
  }
  return card;
}
function render(report) {
  const root = $('#result-content');
  root.replaceChildren();
  const overallSummary = report.overall_summary || {
    status: 'unavailable',
    message: 'The analysis response did not include agent summaries.',
  };
  const card = node('section', 'overall-summary-only');
  const header = node('div', 'overall-summary-heading');
  header.append(
    node('h2', '', 'CRA and CL summaries'),
    node('span', `status-pill ${overallSummary.status === 'complete' ? 'ok' : ''}`, label(overallSummary.status, 'unavailable')),
  );
  card.append(header);
  if (!overallSummary.source_inputs && !report.confidentiality) {
    card.append(node('p', 'overall-summary-text', overallSummary.message || 'The overall summary is unavailable.'));
  } else {
    const inputs = overallSummary.source_inputs || {};
    const craRows = inputs.cra_clause_results || [];
    const craBlock = node('section', 'overall-summary-block');
    craBlock.append(node('h3', '', 'CRA clause LLM output'));
    const craOutputRows = craRows.filter((item) => item.llm_output && Object.values(item.llm_output).some((value) => value !== null && value !== undefined));
    if (craOutputRows.length) {
      craOutputRows.forEach((item) => {
        const clause = node('article', 'summary-clause');
        clause.append(node('h4', '', `Clause ${label(item.clause_id)}`));
        for (const field of ['assessed_risk', 'agreement_with_model', 'summary', 'risk_reasoning']) {
          const value = item.llm_output[field];
          if (value !== null && value !== undefined && value !== '') {
            const line = node('p', 'summary-clause-field');
            line.append(node('strong', '', `${field}: `), document.createTextNode(String(value)));
            clause.append(line);
          }
        }
        craBlock.append(clause);
      });
    } else craBlock.append(node('p', '', 'No CRA clause LLM output was returned.'));
    card.append(craBlock);

    const cl = inputs.confidentiality || report.confidentiality || {};
    const clFindings = uniqueFindingsByOccurrence(cl.findings || []);
    const sensitivity = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, CONTEXT_DEPENDENT: 0 };
    clFindings.forEach((finding) => {
      const level = String(finding.sensitivity || 'LOW').toUpperCase();
      if (sensitivity[level] !== undefined) sensitivity[level] += 1;
    });
    const categories = cl.summary || {};
    const activityCount = (cl.processing_activity || []).length;
    const clText = [
      `CL risk: ${label(cl.risk_level, 'Unknown')} (${label(cl.risk_score, 'N/A')}/100).`,
    ].join(' ');
    const clBlock = node('section', 'overall-summary-block');
    clBlock.append(node('h3', '', 'CL confidentiality summary'), node('p', '', clText));
    clBlock.append(node('p', 'summary-cl-counts', `Sensitivity counts: Critical ${sensitivity.CRITICAL} | High ${sensitivity.HIGH} | Medium ${sensitivity.MEDIUM} | Low ${sensitivity.LOW}`));
    clBlock.append(node('p', '', `Categories: Personal data ${label(categories.personal_data, 0)} | Sensitive personal data ${label(categories.sensitive_personal_data, 0)} | Business confidential ${label(categories.business_confidential, 0)}.`));
    clBlock.append(node('p', 'summary-cl-context', `${sensitivity.CONTEXT_DEPENDENT} context-dependent NER match(es); these alone do not establish a leak. Processing activities: ${activityCount}; handling context only, not proof of a leak.`));
    if (clFindings.length) {
      const rows = clFindings.map((finding) => {
        const lineNumber = finding.line_number ?? finding.line_no ?? finding.line;
        const clauseNumber = finding.clause_id ?? finding.clause_no ?? finding.clause_number;
        const hasChars = finding.start !== null && finding.start !== undefined
          && finding.end !== null && finding.end !== undefined
          && Number.isFinite(Number(finding.start)) && Number.isFinite(Number(finding.end));
        const location = [
          lineNumber !== undefined && lineNumber !== null ? `Line ${lineNumber}` : '',
          finding.section || '',
          clauseNumber ? `Clause ${clauseNumber}` : '',
          hasChars ? `Chars ${finding.start}-${finding.end}` : '',
        ].filter(Boolean).join(' | ') || 'Location unavailable';
        return [
          label(finding.type, 'Finding'),
          label(finding.sensitivity, 'LOW').replaceAll('_', ' '),
          label(finding.category, 'Unclassified').replaceAll('_', ' '),
          location,
          maskEvidence(label(finding.type, ''), finding.value),
        ];
      });
      clBlock.append(node('h4', 'summary-table-title', `Findings by clause or line (${clFindings.length})`));
      clBlock.append(renderDataTable(['Data type', 'Sensitivity', 'Category', 'Clause / line number', 'Evidence (masked)'], rows));
    } else clBlock.append(node('p', '', 'No CL findings were reported.'));
    card.append(clBlock);
  }
  root.append(card);
  root.append(renderCOI(report), renderLE(report));
  showState('result');
}
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const error = $('#form-error'); error.hidden = true; error.textContent = '';
  const client = $('#client').value.trim();
  const counterparty = $('#counterparty').value.trim();
  const additional = $('#additional').value.split(',').map((name) => name.trim()).filter(Boolean);
  if (Boolean(client) !== Boolean(counterparty)) { error.textContent = 'Enter both the client and counterparty, or leave both blank.'; error.hidden = false; return; }
  if (client && counterparty && normalizePartyName(client) === normalizePartyName(counterparty)) { error.textContent = 'Client and counterparty must be different companies or people.'; error.hidden = false; return; }
  if ((client || counterparty || additional.length) && !client && !additional.length) { error.textContent = 'Add both primary parties or at least one additional party name.'; error.hidden = false; return; }
  const request = { filename: $('#filename').value.trim() || 'contract.txt', contract_text: textBox.value, include_litigation_exposure: leToggle.checked, entities: {}, clause_deviation_score: null };
  if (client && counterparty || additional.length) request.parties = { ...(client ? { client, counterparty } : {}), additional };
  if (leToggle.checked) {
    const selectedFlag = (field) => {
      const value = document.querySelector(`.choice-group[data-field="${field}"]`).dataset.selected || 'unknown';
      return value === 'unknown' ? null : value === '1';
    };
    const numberValue = (id) => { const value = $(`#${id}`).value; return value === '' ? null : Number(value); };
    const intakeForm = {
      deal_size: numberValue('deal-size'),
      liability_cap: selectedFlag('liability_cap'),
      auto_renewal: selectedFlag('auto_renewal'),
      jurisdiction_risk: numberValue('jurisdiction-risk'),
      indemnification_clause: selectedFlag('indemnification_clause'),
      dispute_history: selectedFlag('dispute_history'),
      governing_law_clarity: numberValue('governing-clarity'),
      clause_deviation_score: numberValue('deviation'),
    };
    for (const [id, min, max, title] of [['deal-size', 50000, 5000000, 'Deal size'], ['jurisdiction-risk', 1, 10, 'Jurisdiction risk'], ['governing-clarity', 1, 5, 'Governing law clarity'], ['deviation', 0, 1, 'Clause deviation score']]) {
      const field = $(`#${id}`);
      if (field.value !== '' && (numberValue(id) < min || numberValue(id) > max || !Number.isFinite(numberValue(id)))) {
        error.textContent = `${title} must be between ${min} and ${max}.`; error.hidden = false; return;
      }
    }
    if (['jurisdiction-risk', 'governing-clarity'].some((id) => $(`#${id}`).value !== '' && !Number.isInteger(numberValue(id)))) {
      error.textContent = 'Jurisdiction risk and governing law clarity must be whole numbers.'; error.hidden = false; return;
    }
    try {
      const intakeResponse = await fetch('/build-le-intake', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(intakeForm) });
      const intake = await intakeResponse.json();
      if (!intakeResponse.ok) throw new Error(typeof intake.detail === 'string' ? intake.detail : JSON.stringify(intake.detail || intake));
      request.entities = intake.entities;
      request.clause_deviation_score = intake.clause_deviation_score;
    } catch (e) {
      error.textContent = `Could not build the LE intake: ${e.message}`; error.hidden = false; return;
    }
  }
  button.disabled = true; button.querySelector('span').textContent = 'Analyzing…';
  try {
    if (!modelsReady) await ensureModelsReady();
    const response = await fetch('/analyze-contract', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
    render(data);
  } catch (e) {
    const root = $('#result-content'); root.replaceChildren();
    const errorBox = node('div', 'error-view'); errorBox.append(node('h2', '', 'Analysis could not be completed'), node('p', '', e.message || 'Check that the API server is running and try again.')); root.append(errorBox); showState('result');
  } finally { button.disabled = false; button.querySelector('span').textContent = 'Analyze contract'; }
});
