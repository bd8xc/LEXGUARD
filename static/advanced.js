"use strict";

const byId = id => document.getElementById(id);
const features = {
  deal_size: 750000,
  liability_cap: 1,
  auto_renewal: 1,
  jurisdiction_risk: 5,
  indemnification_clause: 1,
  dispute_history: 0,
  governing_law_clarity: 5
};
const sampleContract = [
  "MASTER SERVICES AGREEMENT",
  "This agreement is made on 1 October 2026 between Alpha Corp (Customer) and Vendor Four GmbH (Supplier). Supplier will configure and support Customer's inventory platform under the following terms.",
  "1. Services and acceptance. Supplier shall perform the implementation services described in a statement of work signed by both parties. Each statement of work must identify deliverables, milestones, fees, and acceptance criteria. Customer may reject a deliverable within ten business days by describing material defects in writing; Supplier shall correct those defects and resubmit it.",
  "2. Term and renewal. The initial term is two years. It renews automatically for successive one-year terms unless either party gives written notice at least 60 days before the current term ends. Customer may terminate for Supplier's material breach if Supplier fails to cure it within 30 days after receiving notice.",
  "3. Fees and payment. Customer shall pay undisputed invoices within 30 days. Supplier may suspend affected services only after giving written notice and an additional 15 days to pay an overdue undisputed amount. Fees for work outside a signed statement of work require Customer's written approval.",
  "4. Confidentiality and data. Each party shall use the other's confidential information only to perform this agreement and restrict access to personnel who need it. Supplier shall encrypt Customer data in transit and notify Customer without undue delay after confirming unauthorized access. Supplier shall return or delete Customer data within 30 days after termination, except where retention is required by law.",
  "5. Indemnity and liability. Supplier shall defend Customer against third-party claims that the deliverables infringe intellectual property rights and pay finally awarded damages. Each party's aggregate liability is limited to the fees paid or payable during the preceding 12 months. This cap does not apply to fraud, deliberate misconduct, or misuse of confidential information.",
  "6. Governing law and notices. Indian law governs this agreement, and the courts of Bengaluru have exclusive jurisdiction. Formal notices must be sent by email and registered post to the addresses in the signed statement of work. For this synthetic test, Customer's notice contact is qa-notices@example.org."
].join("\n\n");
const samples = {
  "/api/analyze": {
    doc_id: "demo-review",
    client_entity: "Alpha Corp",
    counterparty_entity: "Vendor Four GmbH",
    contract_entities: [],
    contract_text: sampleContract,
    features,
    clause_deviation_override: 0.35
  },
  "/api/coi/check": {
    doc_id: "demo-coi",
    client_entity: "Alpha Corp",
    counterparty_entity: "Beta Technologies",
    contract_entities: [],
    additional_entities: []
  },
  "/api/cr/analyze": {
    contract_text: sampleContract
  },
  "/api/cl/analyze": {
    doc_id: "demo-cl",
    contract_text: sampleContract
  },
  "/api/le/predict": {
    entities: features,
    clause_deviation_score: 0.4,
    graph_results: { conflict_flag: 0 }
  },
  "/api/risk/assess": {
    doc_id: "demo-coi-le",
    client_entity: "Alpha Corp",
    counterparty_entity: "Vendor Four GmbH",
    contract_entities: [],
    additional_entities: [],
    litigation_entities: features,
    clause_deviation_score: 0.4
  },
};
const notes = {
  "/api/analyze": "Combined review of a synthetic six-clause agreement. LE needs completed COI and an externally measured deviation; the sample deviation is for testing only.",
  "/api/coi/check": "COI searches the configured graph. A sample pair may be unresolved unless those names exist in your Neo4j database.",
  "/api/cr/analyze": "CR classifies clauses using the fine-tuned LegalBERT checkpoint. It does not call Groq.",
  "/api/cl/analyze": "CL scans supplied text and redacts sensitive values in the response.",
  "/api/le/predict": "Isolated LE model test. graph_results are supplied by you and are not verified by this route.",
  "/api/risk/assess": "COI runs first; LE receives a conflict flag only if the graph check completes.",
};
let latestResponse = null;
let extracting = false;
let sending = false;

function setBusy() {
  const button = byId("submit");
  button.disabled = extracting || sending;
  button.textContent = sending ? "Sending…" : extracting ? "Extracting…" : "Send request";
}

function showError(message) {
  byId("form-error").textContent = message;
  byId("form-error").hidden = false;
}

function loadSample() {
  const endpoint = byId("endpoint").value;
  const sample = { ...samples[endpoint] };
  byId("request-json").value = JSON.stringify(sample, null, 2);
  byId("endpoint-note").textContent = notes[endpoint] || "";
  byId("form-error").hidden = true;
  byId("file-label").textContent = "Load contract file into contract_text";
  byId("file").accept = ".txt,.pdf,.docx";
  byId("file-status").textContent = "TXT, PDF, or DOCX up to 5 MB.";
}

function parsedBody() {
  let body;
  try {
    body = JSON.parse(byId("request-json").value);
  } catch (error) {
    throw new Error("Invalid JSON: " + error.message);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new Error("The request body must be a JSON object.");
  }
  return body;
}

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = String(value);
  return node;
}

function addText(parent, label, value) {
  if (value === undefined || value === null || value === "") return;
  const row = element("p", "result-line");
  row.append(element("strong", "", label + ": "), document.createTextNode(String(value)));
  parent.append(row);
}

function agentCard(code, title, status) {
  const card = element("section", "result-card");
  const heading = element("div", "result-card-heading");
  heading.append(element("span", "agent-code", code), element("h3", "", title));
  heading.append(element("span", "result-pill " + (status === "complete" ? "complete" : "partial"), status || "unknown"));
  card.append(heading);
  return card;
}

function addList(parent, items, emptyMessage) {
  if (!items.length) {
    parent.append(element("p", "muted", emptyMessage));
    return;
  }
  const list = element("ul", "result-list");
  items.forEach(item => list.append(element("li", "", item)));
  parent.append(list);
}

function shortError(reason) {
  if (typeof reason !== "string") return "Analysis failed";
  return reason.includes("HTTP 429") ? "Grounded analysis was rate limited (HTTP 429). The clause result is incomplete." : reason;
}

function renderCoi(data) {
  const coi = data && typeof data === "object" ? data : {};
  const card = agentCard("COI", "Conflict of interest", coi.status);
  addText(card, "Finding", coi.status === "complete" ? (coi.conflict_detected ? "Verified conflict path found" : "No verified conflict found in the configured graph") : (coi.severity || "Unresolved"));
  addText(card, "Severity", coi.severity);
  addText(card, "Path", Array.isArray(coi.conflict_path) && coi.conflict_path.length ? coi.conflict_path.join(" → ") : null);
  addText(card, "Unresolved entities", Array.isArray(coi.unresolved_entities) && coi.unresolved_entities.length ? coi.unresolved_entities.join(", ") : null);
  addText(card, "Potential clause findings", Array.isArray(coi.clause_findings) && coi.clause_findings.length ? coi.clause_findings.length : null);
  addText(card, "Reason", coi.skipped_reason || coi.reason);
  return card;
}

function renderCr(data, container) {
  const cr = data && typeof data === "object" ? data : {};
  const clauses = Array.isArray(cr.clauses) ? cr.clauses : [];
  const classified = clauses.filter(clause => ["Seed", "Low", "Medium", "High"].includes(clause.model?.prediction)).length;
  const card = agentCard("CR", "Contract risk", cr.status);
  addText(card, "Classified", classified + " of " + clauses.length + " attempted clauses");
  addText(card, "Omitted", cr.omitted_clause_count || null);
  addText(card, "Reason", cr.reason);
  if (cr.mode === "legalbert") card.append(element("p", "muted", cr.model_note || "LegalBERT model classifications are risk signals, not legal conclusions."));
  container.append(card);
  if (!clauses.length) return;
  const section = element("section", "detail-section");
  section.append(element("h3", "", "Clause review"));
  const list = element("div", "clause-list");
  clauses.forEach(clause => {
    const row = element("article", "clause-row");
    const heading = element("div", "clause-heading");
    const model = clause.model && typeof clause.model === "object" ? clause.model : {};
    const analysis = clause.analysis && typeof clause.analysis === "object" ? clause.analysis : {};
    heading.append(element("strong", "", "Clause " + (clause.clause_id || "—")));
    const risk = model.prediction || "Unavailable";
    heading.append(element("span", "risk-pill risk-" + String(risk).toLowerCase(), "LegalBERT: " + (risk === "Seed" ? "Baseline (Seed)" : risk)));
    row.append(heading);
    if (typeof model.model_score === "number") addText(row, "Raw model score", (model.model_score * 100).toFixed(1) + "% (uncalibrated)");
    if (analysis.summary) row.append(element("p", "", analysis.summary));
    if (analysis.assessed_risk) addText(row, "Grounded assessment", analysis.assessed_risk);
    if (clause.status === "error") addText(row, "Error", shortError(clause.reason));
    list.append(row);
  });
  section.append(list);
  container.append(section);
}

function renderCl(data, container) {
  const cl = data && typeof data === "object" ? data : {};
  const findings = Array.isArray(cl.findings) ? cl.findings : [];
  const card = agentCard("CL", "Confidentiality leakage", cl.status);
  addText(card, "Risk level", cl.risk_level);
  addText(card, "Findings", cl.total_findings ?? findings.length);
  addText(card, "Sensitive data", cl.sensitive_data_detected === true ? "Detected" : cl.sensitive_data_detected === false ? "None detected" : null);
  addText(card, "Reason", cl.reason);
  container.append(card);
  if (!findings.length) return;
  const section = element("section", "detail-section");
  section.append(element("h3", "", "Sensitive findings"));
  const list = element("div", "finding-list");
  findings.slice(0, 20).forEach(finding => {
    const row = element("div", "finding-row");
    row.append(element("strong", "", finding.type || "Finding"));
    row.append(element("span", "", [finding.sensitivity, finding.clause_id ? "Clause " + finding.clause_id : ""].filter(Boolean).join(" · ")));
    list.append(row);
  });
  section.append(list);
  if (findings.length > 20) section.append(element("p", "muted", (findings.length - 20) + " more findings are in the downloadable JSON."));
  container.append(section);
}

function renderLe(data, status) {
  const le = data && typeof data === "object" ? data : {};
  const card = agentCard("LE", "Litigation exposure", (status || (data ? "complete" : "skipped")).split(":")[0]);
  if (typeof le.litigation_probability === "number") {
    addText(card, "Synthetic model estimate", (le.litigation_probability * 100).toFixed(1) + "%");
  }
  addText(card, "Risk band", le.risk_level);
  addText(card, "Status", !data ? status : null);
  if (data) card.append(element("p", "muted", le.interpretation || "This model is trained on synthetic labels and is not an outcome-calibrated probability."));
  return card;
}

function renderCombined(data, target) {
  const overview = element("section", "review-overview");
  overview.append(element("p", "eyebrow", "Combined review · " + (data.doc_id || "document")));
  overview.append(element("h3", "", data.review_required ? "Human review required" : "Review result"));
  overview.append(element("p", "muted", data.status === "partial" ? "At least one agent did not complete. Check the agent cards below." : "All agent steps completed. Review the findings before making a decision."));
  const reasons = data.decision && Array.isArray(data.decision.reasons) ? data.decision.reasons : [];
  addList(overview, reasons, "No decision reasons were returned.");
  target.append(overview);

  const grid = element("div", "result-grid");
  grid.append(renderCoi(data.coi));
  const crDetails = element("div");
  renderCr(data.cr, crDetails);
  grid.append(crDetails.firstChild);
  const clDetails = element("div");
  renderCl(data.cl, clDetails);
  grid.append(clDetails.firstChild);
  grid.append(renderLe(data.le, data.le_status));
  target.append(grid);
  while (crDetails.firstChild) target.append(crDetails.firstChild);
  while (clDetails.firstChild) target.append(clDetails.firstChild);
}

function renderResult(endpoint, data, ok) {
  const target = byId("visual-results");
  target.replaceChildren();
  if (!ok) {
    const details = Array.isArray(data?.detail) ? data.detail.map(item => [item.loc?.join("."), item.msg].filter(Boolean).join(": ")) : [typeof data?.detail === "string" ? data.detail : "The request failed."];
    addList(target, details, "The request failed.");
    return;
  }
  if (!data || typeof data !== "object") return;
  if (endpoint === "/api/analyze") {
    renderCombined(data, target);
  } else if (endpoint === "/api/cr/analyze") {
    renderCr(data, target);
  } else if (endpoint === "/api/cl/analyze") {
    renderCl(data, target);
  } else if (endpoint === "/api/coi/check") {
    target.append(renderCoi(data));
  } else if (endpoint === "/api/le/predict") {
    target.append(renderLe(data, "complete"));
  } else if (endpoint === "/api/risk/assess") {
    const grid = element("div", "result-grid");
    grid.append(renderCoi(data.coi), renderLe(data.litigation, data.litigation ? "complete" : data.status));
    target.append(grid);
  } else {
    target.append(element("p", "muted", "Response received. Open raw JSON for the full result."));
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("Status request failed");
    const status = await response.json();
    const values = { coi: status.coi, cr: status.cr, cl: status.cl, le: status.le };
    const names = { ready: "Ready", unavailable: "Unavailable", groq_fallback: "Groq fallback", missing_model: "Model missing", degraded: "Degraded" };
    Object.entries(values).forEach(([agent, value]) => {
      const element = byId("status-" + agent);
      element.textContent = names[value] || String(value || "Unknown").replaceAll("_", " ");
      element.className = "service-pill " + (value === "ready" ? "ready" : value === "groq_fallback" || value === "degraded" ? "degraded" : "unavailable");
    });
    const ready = Object.values(values).filter(value => value === "ready").length;
    const summary = byId("system-state");
    summary.className = "system-state " + (ready === 4 ? "good" : "warn");
    summary.textContent = ready + " ready / 4";
    byId("status-extra").textContent = "Status reflects agent initialization and the most recent health check.";
  } catch {
    ["coi", "cr", "cl", "le"].forEach(agent => {
      const element = byId("status-" + agent);
      element.textContent = "Unavailable";
      element.className = "service-pill unavailable";
    });
    byId("system-state").textContent = "Status unavailable";
    byId("status-extra").textContent = "";
  }
}

byId("refresh-status").addEventListener("click", refreshStatus);
byId("endpoint").addEventListener("change", loadSample);
byId("load-sample").addEventListener("click", loadSample);

byId("file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  const target = byId("file-status");
  let body;
  try {
    body = parsedBody();
    if (!Object.hasOwn(body, "contract_text")) {
      throw new Error("This JSON body has no contract_text field. Select combined review, CR, or CL first.");
    }
    if (file.size > 5 * 1024 * 1024) throw new Error("File must be at most 5 MB.");
  } catch (error) {
    target.textContent = error.message;
    event.target.value = "";
    return;
  }
  extracting = true;
  setBusy();
  target.textContent = "Extracting " + file.name + "…";
  try {
    const payload = new FormData();
    payload.append("file", file);
    const response = await fetch("/api/extract", { method: "POST", body: payload });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Extraction failed");
    body.contract_text = data.text;
    byId("request-json").value = JSON.stringify(body, null, 2);
    target.textContent = file.name + " inserted into contract_text. Review the JSON before sending.";
  } catch (error) {
    target.textContent = error.message || "Extraction failed";
  } finally {
    extracting = false;
    setBusy();
  }
});

byId("request-form").addEventListener("submit", async event => {
  event.preventDefault();
  byId("form-error").hidden = true;
  if (extracting || sending) return;
  try {
    parsedBody();
  } catch (error) {
    showError(error.message);
    return;
  }
  const endpoint = byId("endpoint").value;
  latestResponse = null;
  byId("results").hidden = true;
  sending = true;
  setBusy();
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: byId("request-json").value
    });
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); } catch { data = raw; }
    latestResponse = data;
    const summary = byId("result-summary");
    const partial = response.ok && (data?.status === "partial" || data?.status === "incomplete");
    summary.className = "response-summary " + (!response.ok ? "failure" : partial ? "partial" : "success");
    summary.textContent = "HTTP " + response.status + " · " + endpoint + (partial ? " · Partial result" : "");
    byId("result-meta").textContent = !response.ok ? "Request returned an error" : partial ? "Some analysis did not complete" : "Request completed";
    byId("raw-json").textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    renderResult(endpoint, data, response.ok);
    byId("results").hidden = false;
    byId("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError(error.message || "Request failed");
  } finally {
    sending = false;
    setBusy();
    refreshStatus();
  }
});

byId("download").addEventListener("click", () => {
  if (latestResponse === null) return;
  const content = typeof latestResponse === "string" ? latestResponse : JSON.stringify(latestResponse, null, 2);
  const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "lexguard-response.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

loadSample();
refreshStatus();
fetch("/initialize", { method: "POST" }).catch(() => {}).finally(refreshStatus);
setInterval(refreshStatus, 5000);
