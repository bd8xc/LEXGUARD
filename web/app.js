const form = document.querySelector("#contract-form");
const fileInput = document.querySelector("#contract-file");
const submitButton = document.querySelector("#submit-button");
const formError = document.querySelector("#form-error");
const progressPanel = document.querySelector("#progress-panel");
const progressTitle = document.querySelector("#progress-title");
const progressBar = document.querySelector("#progress-bar");
const progressPercent = document.querySelector("#progress-percent");
const progressLog = document.querySelector("#progress-log");
const results = document.querySelector("#results");
const activeJobKey = "lexguard.activeJobId";
let eventSource = null;

document.querySelectorAll('input[type="range"][data-output]').forEach((slider) => {
  const output = document.getElementById(slider.dataset.output);
  const updateOutput = () => {
    output.value = slider.name === "clause_deviation_score"
      ? Number(slider.value).toFixed(2)
      : `${slider.value} / ${slider.max}`;
  };
  slider.addEventListener("input", updateOutput);
});

function make(tag, text = "", className = "") {
  const element = document.createElement(tag);
  if (text !== null && text !== undefined) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function renderTable(headers, rows) {
  if (!rows.length) return make("p", "No findings reported.", "empty-state");
  const wrap = make("div", "", "data-table-wrap");
  const table = make("table", "", "data-table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  headers.forEach((header) => headRow.append(make("th", header)));
  thead.append(headRow);
  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((value) => tr.append(make("td", value ?? "—")));
    tbody.append(tr);
  });
  table.append(thead, tbody);
  wrap.append(table);
  return wrap;
}

function setProgress(percent, message) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  progressBar.value = value;
  progressPercent.textContent = `${value}%`;
  if (message) progressTitle.textContent = message;
}

function appendProgress(event) {
  setProgress(event.percent, event.message);
  const item = make("li", event.message);
  progressLog.append(item);
  while (progressLog.children.length > 140) progressLog.firstElementChild.remove();
  progressLog.scrollTop = progressLog.scrollHeight;
}

function clearResultSections() {
  ["agent-statuses", "warnings", "clauses-list", "cl-content", "coi-content", "le-content"].forEach((id) => {
    document.getElementById(id).replaceChildren();
  });
}

function renderStatuses(data) {
  const host = document.querySelector("#agent-statuses");
  const statuses = data.agent_statuses || {
    CR: data.cr?.status,
    CL: data.cl?.status,
    COI: data.coi?.status,
    LE: data.le?.status,
  };
  Object.entries(statuses).forEach(([name, status]) => {
    const item = make("div", "", "status-item");
    item.append(make("span", name, "status-name"));
    item.append(make("span", status || "not_run", `status-value ${(status || "not_run").toLowerCase()}`));
    host.append(item);
  });
}

function renderWarnings(data) {
  const host = document.querySelector("#warnings");
  (data.warnings || []).forEach((warning) => host.append(make("p", warning, "warning-item")));
}

function riskClass(value) {
  const normalized = String(value || "").toLowerCase();
  return normalized === "high" ? "risk-tag high" : normalized === "medium" ? "risk-tag medium" : "risk-tag";
}

function field(title, value) {
  const block = make("div", "", "analysis-field");
  block.append(make("h4", title));
  block.append(make("p", value || "—"));
  return block;
}

function renderClauses(data) {
  const host = document.querySelector("#clauses-list");
  const rows = data.cr?.clauses || [];
  document.querySelector("#clause-count").textContent = `${rows.length} clause${rows.length === 1 ? "" : "s"}`;
  if (!rows.length) {
    host.append(make("p", data.cr?.reason || "CR produced no clause results.", "empty-state"));
    return;
  }

  rows.forEach((row) => {
    const analysis = row.analysis || {};
    const details = document.createElement("details");
    details.className = "clause-details";
    const summary = document.createElement("summary");
    const title = make("span", `${row.clause_id || "Clause"} · ${row.section || "Unspecified section"}`, "clause-title");
    const tag = make("span", analysis.assessed_risk || row.model?.prediction || row.status || "Unknown", riskClass(analysis.assessed_risk));
    summary.append(title, tag);
    details.append(summary);

    const body = make("div", "", "clause-body");
    body.append(make("p", row.clause || "Clause text unavailable.", "clause-text"));
    const model = row.model || {};
    const score = typeof model.model_score === "number" ? `${(model.model_score * 100).toFixed(2)}%` : "—";
    const modelTable = renderTable(
      ["Prediction", "Model score", "Windows", "LegalBERT / class scores"],
      [[model.prediction || "Unknown", score, model.num_windows ?? "—", Object.entries(model.class_scores || {}).map(([key, value]) => `${key} ${(Number(value) * 100).toFixed(2)}%`).join(" · ") || "—"]],
    );
    body.append(make("h4", "LegalBERT risk signal", "subsection-title"), modelTable);

    const law = row.retrieved_law || [];
    body.append(make("h4", "Retrieved Indian law", "subsection-title"));
    body.append(renderTable(
      ["Rank", "Section", "Heading", "Similarity", "Provision"],
      law.map((item) => [item.rank, item.section, item.heading, Number(item.score).toFixed(4), item.text]),
    ));

    body.append(make("h4", "Grounded LLM analysis", "subsection-title"));
    const analysisGrid = make("div", "", "analysis-grid");
    analysisGrid.append(
      field("Summary", analysis.summary),
      field("Risk reasoning", analysis.risk_reasoning),
      field("Agreement with LegalBERT", analysis.agreement_with_model ? "Yes" : "No"),
      field("Evidence sufficient", analysis.evidence_sufficient ? "Yes" : "No"),
      field("Human review", analysis.human_review_required ? "Required" : "Not required"),
      field("Contractual concern", analysis.contractual_concern),
      field("Suggested mitigation", analysis.suggested_mitigation),
    );
    body.append(analysisGrid);
    body.append(make("h4", "Relevant statutory context", "subsection-title"));
    body.append(renderTable(
      ["Section", "Relevance"],
      (analysis.relevant_sections || []).map((item) => [item.section, item.relevance]),
    ));
    body.append(make("h4", "Weak or irrelevant retrieved context", "subsection-title"));
    body.append(renderTable(
      ["Section", "Reason"],
      (analysis.irrelevant_or_weak_sections || []).map((item) => [item.section, item.reason]),
    ));
    if (row.llm_error || row.rag_error || row.reason) {
      body.append(make("p", [row.llm_error, row.rag_error, row.reason].filter(Boolean).join(" · "), "error-banner"));
    }
    if (row.interpretation_note) body.append(make("p", row.interpretation_note, "field-note"));
    details.append(body);
    host.append(details);
  });
}

function renderCl(data) {
  const host = document.querySelector("#cl-content");
  const report = data.cl?.report;
  if (!report) {
    host.append(make("p", data.cl?.reason || "No confidentiality report was returned.", "empty-state"));
    return;
  }
  const summary = report.summary || {};
  host.append(make("h4", "Summary counts", "subsection-title"));
  host.append(renderTable(
    ["Personal data", "Sensitive personal data", "Business confidential", "Processing activities"],
    [[summary.personal_data ?? 0, summary.sensitive_personal_data ?? 0, summary.business_confidential ?? 0, summary.processing_activities ?? 0]],
  ));

  host.append(make("h4", `Findings · ${report.total_findings ?? (report.findings || []).length}`, "subsection-title"));
  host.append(renderTable(
    ["Clause", "Type", "Sensitivity", "Category", "Masked value", "Source"],
    (report.findings || []).map((finding) => [finding.clause_id, finding.type, finding.sensitivity, finding.category, finding.value, finding.source]),
  ));

  host.append(make("h4", "Processing activity", "subsection-title"));
  host.append(renderTable(
    ["Clause", "Activity", "Value", "Source"],
    (report.processing_activity || []).map((activity) => [activity.clause_id, activity.activity || activity.type, activity.value, activity.source]),
  ));
}

function renderCoi(data) {
  const host = document.querySelector("#coi-content");
  const coi = data.coi || {};
  const report = coi.report || {};
  if (!report || !Object.keys(report).length) {
    host.append(make("p", coi.reason || "No COI report was returned.", "empty-state"));
    return;
  }
  const metrics = make("p", "", "inline-metrics");
  metrics.append(make("span", ""));
  metrics.firstElementChild.append(make("strong", "Conflict: "), document.createTextNode(report.conflict_detected ? "Detected" : "Not detected"));
  const flag = make("span", "");
  flag.append(make("strong", "Conflict flag: "), document.createTextNode(report.conflict_flag ?? "Unknown"));
  const severity = make("span", "");
  severity.append(make("strong", "Severity: "), document.createTextNode(report.severity || "Unknown"));
  metrics.append(flag, severity);
  host.append(metrics);
  host.append(renderTable(
    ["Relationship path", "Severity", "Verified", "Evidence"],
    (report.findings || []).map((finding) => [
      (finding.path || []).join(" → "),
      finding.severity,
      finding.verified ? "Yes" : "No",
      (finding.evidence || []).map((item) => item.evidence || item.type).join(" · "),
    ]),
  ));
  if (coi.method) host.append(make("p", coi.method, "field-note"));
}

function renderLe(data) {
  const host = document.querySelector("#le-content");
  const le = data.le || {};
  const result = le.result;
  if (!result) {
    host.append(make("p", le.reason || "LE was not run.", "empty-state"));
    return;
  }
  const metrics = make("p", "", "inline-metrics");
  const risk = make("span", "");
  risk.append(make("strong", "Risk level: "), document.createTextNode(result.risk_level || "Unknown"));
  const score = make("span", "");
  score.append(make("strong", "Model score: "), document.createTextNode(result.litigation_probability ?? "Unknown"));
  metrics.append(risk, score);
  host.append(metrics);
  if (le.interpretation) host.append(make("p", le.interpretation, "field-note"));
  host.append(make("h4", "Features and SHAP contribution", "subsection-title"));
  const features = result.features_used || {};
  const explanation = result.shap_explanation || {};
  host.append(renderTable(
    ["Feature", "Value", "Contribution"],
    Object.entries(features).map(([name, value]) => [name, value, explanation[name] ?? "—"]),
  ));
}

function renderResult(data, jobId) {
  clearResultSections();
  document.querySelector("#result-title").textContent = data.document?.file_name || "Contract results";
  document.querySelector("#result-meta").textContent = `${data.document?.word_count ?? "—"} words · ${data.document?.clause_count ?? 0} clauses`;
  document.querySelector("#download-json").href = `/api/jobs/${encodeURIComponent(jobId)}/reports/json`;
  const pdfLink = document.querySelector("#download-pdf");
  if (data.outputs?.pdf) {
    pdfLink.href = `/api/jobs/${encodeURIComponent(jobId)}/reports/pdf`;
    pdfLink.hidden = false;
  } else {
    pdfLink.hidden = true;
  }
  renderStatuses(data);
  renderWarnings(data);
  renderClauses(data);
  renderCl(data);
  renderCoi(data);
  renderLe(data);
  results.hidden = false;
}

async function fetchJob(jobId) {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) throw new Error(response.status === 404 ? "This job is no longer available." : "Could not load this job.");
  return response.json();
}

async function finishJob(jobId) {
  if (eventSource) eventSource.close();
  try {
    const job = await fetchJob(jobId);
    if (job.status === "complete" && job.result) {
      setProgress(100, "Analysis complete");
      renderResult(job.result, jobId);
    } else if (job.status === "failed") {
      showJobError(job.error || "Analysis failed.");
    }
  } catch (error) {
    showJobError(error.message);
  }
  submitButton.disabled = false;
}

function showJobError(message) {
  const error = make("p", message, "error-banner");
  progressPanel.append(error);
  progressTitle.textContent = "Analysis stopped";
  submitButton.disabled = false;
}

function watchJob(jobId) {
  if (eventSource) eventSource.close();
  progressPanel.hidden = false;
  eventSource = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
  eventSource.addEventListener("progress", (message) => {
    try { appendProgress(JSON.parse(message.data)); } catch { /* Ignore malformed progress frames. */ }
  });
  eventSource.addEventListener("complete", () => finishJob(jobId));
  eventSource.addEventListener("failed", (message) => {
    let detail = "Analysis failed.";
    try { detail = JSON.parse(message.data).message || detail; } catch { /* Keep fallback message. */ }
    if (eventSource) eventSource.close();
    showJobError(detail);
  });
  eventSource.onerror = async () => {
    try {
      const job = await fetchJob(jobId);
      if (job.status === "complete" || job.status === "failed") await finishJob(jobId);
    } catch {
      if (eventSource?.readyState === EventSource.CLOSED) showJobError("The progress connection was lost.");
    }
  };
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  document.querySelector("#upload-title").textContent = file ? file.name : "Choose a contract to upload";
});

form.addEventListener("submit", async (submitEvent) => {
  submitEvent.preventDefault();
  formError.textContent = "";
  if (eventSource) eventSource.close();
  document.querySelectorAll(".error-banner").forEach((node) => node.remove());
  results.hidden = true;
  progressLog.replaceChildren();
  const formData = new FormData(form);
  for (const [key, value] of [...formData.entries()]) {
    if (typeof value === "string" && value.trim() === "") formData.delete(key);
  }
  submitButton.disabled = true;
  progressPanel.hidden = false;
  setProgress(0, "Uploading contract");
  try {
    const response = await fetch("/api/contracts", { method: "POST", body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Contract upload failed.");
    localStorage.setItem(activeJobKey, payload.job_id);
    appendProgress({ message: "Contract uploaded and queued.", percent: 0 });
    watchJob(payload.job_id);
  } catch (error) {
    formError.textContent = error.message || "Could not start analysis.";
    submitButton.disabled = false;
  }
});

async function restoreActiveJob() {
  const jobId = localStorage.getItem(activeJobKey);
  if (!jobId) return;
  try {
    const job = await fetchJob(jobId);
    progressPanel.hidden = false;
    if (job.status === "complete" && job.result) {
      appendProgress({ message: "Restored the most recent completed analysis.", percent: 100 });
      renderResult(job.result, jobId);
    } else if (job.status === "failed") {
      showJobError(job.error || "Analysis failed.");
    } else {
      appendProgress(job.latest_progress || { message: "Reconnecting to analysis progress.", percent: 0 });
      watchJob(jobId);
      submitButton.disabled = true;
    }
  } catch {
    localStorage.removeItem(activeJobKey);
  }
}

restoreActiveJob();
