const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');

function render(result) {
  class Element {
    constructor(tag = 'div') {
      this.tag = tag;
      this.children = [];
      this.textContent = '';
      this.hidden = false;
      this.style = { setProperty() {} };
    }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = [...nodes]; }
    addEventListener() {}
  }
  const ids = ['result-content', 'empty-results', 'download-result', 'report-id',
    'report-subtitle', 'report-state', 'result-summary-grid', 'report-details',
    'classification-chart', 'review-reasons', 'graph-update', 'raw-result', 'clear-report'];
  const elements = Object.fromEntries(ids.map(id => [`#${id}`, new Element()]));
  const document = {
    querySelector: selector => elements[selector] || null,
    querySelectorAll: () => [],
    createElement: tag => new Element(tag),
    addEventListener() {},
  };
  const sessionStorage = { getItem: () => JSON.stringify({ result }) };
  vm.runInNewContext(source + '\nresultsInit();', { document, sessionStorage, console });
  const text = node => [node.textContent, ...node.children.map(text)].join(' ');
  return { elements, text };
}

const complete = {
  doc_id: 'review-1', status: 'complete',
  coi: { status: 'complete', conflict_detected: false, severity: 'NONE',
    party_roles: { client: 'Alpha Corp', counterparty: 'Beta Ltd' },
    findings: [], clause_findings: [], unresolved_entities: [] },
  cr: { status: 'complete', omitted_clause_count: 0,
    clauses: [{ clause_id: 'C1', model: { prediction: 'Seed', model_score: 0.3 } }] },
  cl: { status: 'complete', sensitive_data_detected: true, risk_score: 32,
    risk_level: 'MEDIUM', total_findings: 1, high_sensitivity_count: 0,
    medium_sensitivity_count: 1, context_dependent_count: 0,
    summary: { personal_data: 1 }, findings: [{ type: 'EMAIL', value: 'a***@example.com',
      sensitivity: 'MEDIUM', clause_id: 'C1' }] },
  le: { litigation_probability: 0, risk_level: 'Low', features_used: { deal_size: 100 },
    shap_explanation: { deal_size: 0.02 }, model_fingerprint: 'abc' },
  le_status: 'complete', decision: { reasons: ['Human review required.'], limitations: [] },
  graph_update: { status: 'complete', clauses: 1 },
};

const full = render(complete);
assert.equal(full.elements['#result-content'].hidden, false);
assert.match(full.text(full.elements['#result-summary-grid']), /0\.0%/);
assert.match(full.text(full.elements['#report-details']), /a\*\*\*@example\.com/);
assert.match(full.text(full.elements['#report-details']), /Features used/);
assert.match(full.text(full.elements['#report-details']), /Party roles/);
assert.match(full.elements['#raw-result'].textContent, /"model_fingerprint": "abc"/);

const partial = render({ doc_id: 'review-2', status: 'partial',
  coi: { status: 'unavailable', severity: 'UNKNOWN' },
  cr: { status: 'partial' }, cl: { status: 'unavailable' }, le: null,
  le_status: 'skipped: COI incomplete', decision: { reasons: ['Graph unavailable.'] } });
assert.match(partial.text(partial.elements['#result-summary-grid']), /Unavailable/);
assert.match(partial.text(partial.elements['#result-summary-grid']), /Not run/);
assert.match(partial.elements['#report-state'].textContent, /Partial/);
assert.doesNotMatch(partial.text(partial.elements['#report-details']), /NaN|undefined/);

console.log('Results renderer: complete and partial API shapes passed.');
