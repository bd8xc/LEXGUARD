"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const JOB_KEY = "lexguard.activeJobId";
const REPORT_KEY = "lexguard.latestReport";
function savedValue(key) { try { return sessionStorage.getItem(key); } catch { return null; } }
function saveValue(key, value) {
  try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); } catch {}
}
const exampleContract = [
  "MASTER SERVICES AGREEMENT — SYNTHETIC EXAMPLE",
  "This agreement is between Alpha Org and Alpha Labs.",
  "1. Services. Alpha Labs shall provide the agreed implementation services and meet the milestones in the statement of work.",
  "2. Renewal. The agreement renews automatically for one year unless either party gives sixty days written notice.",
  "3. Confidentiality. Each party shall restrict access to confidential information. Test notices may be sent to qa-notices@example.org.",
  "4. Liability. The supplier indemnifies the customer against third-party intellectual property claims.",
  "5. Governing law. Indian law governs this agreement and the courts at Bengaluru have jurisdiction."
].join("\n\n");

function node(tag, className = "", value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined && value !== null) element.textContent = String(value);
  return element;
}
function add(parent, ...children) { children.filter(Boolean).forEach(child => parent.append(child)); return parent; }
function text(value, fallback = "—") { return value === null || value === undefined || value === "" ? fallback : String(value); }
function list(value) { return Array.isArray(value) ? value : []; }
function field(form, name) { return form.elements.namedItem(name)?.value?.trim() || ""; }
function entities(value) { return value.split(/[,;\n]+/).map(item => item.trim()).filter(Boolean); }
function message(error) {
  if (Array.isArray(error?.detail)) return error.detail.map(item => (item.loc || []).slice(1).join(".") + ": " + item.msg).join("; ");
  return typeof error?.detail === "string" ? error.detail : "The request failed.";
}
async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { throw Error("The server returned an invalid response."); }
  if (!response.ok) { const error = Error(message(data)); error.status = response.status; throw error; }
  return data;
}
function showError(selector, value) {
  const target = $(selector);
  if (!target) return;
  target.textContent = value;
  target.hidden = false;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}
function clearError(selector) { const target = $(selector); if (target) { target.hidden = true; target.textContent = ""; } }
function themeInit() {
  $$("[data-theme-toggle]").forEach(button => button.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("lexguard-theme", next); } catch {}
  }));
  const toggle = $("[data-menu-toggle]"), menu = $("#mobile-nav");
  if (toggle && menu) {
    const closeMenu = () => { toggle.setAttribute("aria-expanded", "false"); menu.hidden = true; };
    toggle.addEventListener("click", () => {
      const opened = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!opened));
      menu.hidden = opened;
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !menu.hidden) { closeMenu(); toggle.focus(); }
    });
    document.addEventListener("click", event => { if (!event.target.closest(".site-header")) closeMenu(); });
    matchMedia("(min-width: 851px)").addEventListener("change", event => { if (event.matches) closeMenu(); });
  }
}
async function systemStatus() {
  try {
    const data = await jsonRequest("/api/status", { cache: "no-store" });
    const ready = ["cr", "cl", "coi", "le"].filter(key => data[key] === "ready").length;
    $$("[data-system-label]").forEach(element => element.textContent = ready + " of 4 agents available");
    $$(".live-chip").forEach(element => {
      element.classList.toggle("is-ready", ready === 4);
      element.classList.toggle("is-partial", ready !== 4);
    });
    $$("[data-agent-status]").forEach(element => {
      const value = data[element.dataset.agentStatus] || "unavailable";
      element.textContent = value.replaceAll("_", " ");
    });
  } catch {
    $$("[data-system-label]").forEach(element => element.textContent = "API unavailable");
    $$(".live-chip").forEach(element => { element.classList.remove("is-ready"); element.classList.add("is-partial"); });
    $$("[data-agent-status]").forEach(element => element.textContent = "Unavailable");
  }
}
function numericInputs(form) {
  const result = {};
  for (const name of ["deal_size", "liability_cap", "auto_renewal", "jurisdiction_risk", "indemnification_clause", "dispute_history", "governing_law_clarity"]) {
    const value = field(form, name);
    if (value !== "") result[name] = Number(value);
  }
  return result;
}
function validate(form, step) {
  form._invalidInput = null;
  $$("[aria-invalid]", form).forEach(input => input.removeAttribute("aria-invalid"));
  const invalid = (input, error) => { form._invalidInput = input; input?.setAttribute("aria-invalid", "true"); return error; };
  if ($("#review-file")?._pending || $("#tool-file")?._pending) return "Document extraction is still in progress.";
  const panel = step ? $('.step-panel[data-step="' + step + '"]', form) : form;
  for (const input of $$("input, textarea, select", panel)) {
    if (input.type === "file" || input.type === "checkbox") continue;
    const label = input.labels?.[0]?.querySelector("span")?.textContent.replace(/\(optional\)|\*/gi, "").trim() || input.name.replaceAll("_", " ");
    if (input.required && !input.value.trim()) return invalid(input, "Fill in " + label + ".");
    if (input.validity.badInput || (input.value && !input.checkValidity())) return invalid(input, label + ": " + (input.validationMessage || "Check the supplied value."));
  }
  const contract = $('[name="contract_text"]', panel);
  if (contract && contract.value.trim().length < 40) return invalid(contract, "Provide a document or at least 40 characters of contract text.");
  if (contract && contract.value.trim().length > 120000) return invalid(contract, "Keep contract text within 120,000 characters.");
  const additional = $('[name="additional_entities"]', panel);
  if (additional && entities(additional.value).length > 13) return invalid(additional, "Enter no more than 13 additional entities.");
  return "";
}
function formError(form, selector, error) {
  showError(selector, error);
  form._invalidInput?.focus();
}
function setupExtraction(inputSelector, textareaSelector) {
  const input = $(inputSelector), area = $(textareaSelector), status = $("#upload-status"), zone = $("#dropzone");
  if (!input || !area) return;
  let controller, revision = 0;
  input._cancelExtraction = () => {
    revision++;
    controller?.abort();
    input._pending = false;
    input._selectedFile = null;
    input._previewText = null;
    input.value = "";
    area.removeAttribute("aria-busy");
  };
  area.addEventListener("input", () => {
    if (input._pending) {
      input._cancelExtraction();
      status.textContent = "File extraction cancelled. Your edited text will be used.";
    }
  });
  async function preview(file) {
    if (!file) return;
    input._cancelExtraction();
    if (!/\.(pdf|docx|txt)$/i.test(file.name)) { status.textContent = "Use a PDF, DOCX, or TXT file."; return; }
    if (file.size > 5 * 1024 * 1024) { status.textContent = "The file exceeds the 5 MB limit."; return; }
    const current = revision;
    controller = new AbortController();
    input._pending = true;
    area.setAttribute("aria-busy", "true");
    status.textContent = "Extracting " + file.name + "…";
    const payload = new FormData();
    payload.append("file", file);
    try {
      const data = await jsonRequest("/api/extract", { method: "POST", body: payload, signal: controller.signal });
      if (current !== revision) return;
      input._pending = false;
      area.value = data.text;
      area.dispatchEvent(new Event("input", { bubbles: true }));
      input._selectedFile = file;
      input._previewText = data.text;
      status.textContent = file.name + " extracted. Review the text before analysis.";
    } catch (error) { if (current === revision) status.textContent = error.message; }
    finally { if (current === revision) { input._pending = false; area.removeAttribute("aria-busy"); } }
  }
  input.addEventListener("change", () => preview(input.files?.[0]));
  if (zone) {
    ["dragenter", "dragover"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.add("dragover"); }));
    ["dragleave", "drop"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.remove("dragover"); }));
    zone.addEventListener("drop", event => preview(event.dataTransfer?.files?.[0]));
  }
}
function submitValues(form) {
  const deviation = field(form, "clause_deviation_score");
  return {
    client_entity: field(form, "client_entity"),
    counterparty_entity: field(form, "counterparty_entity"),
    additional_entities: field(form, "additional_entities"),
    le_features: numericInputs(form),
    clause_deviation_score: deviation === "" ? null : Number(deviation)
  };
}
async function startReview(form) {
  const values = submitValues(form);
  const file = $("#review-file");
  const editedText = field(form, "contract_text");
  if (file?._selectedFile && editedText === file._previewText?.trim()) {
    const body = new FormData();
    body.append("file", file._selectedFile);
    for (const [name, value] of Object.entries(values)) {
      if (name === "le_features") {
        for (const [key, item] of Object.entries(value)) body.append(key, item);
      } else if (value !== null && value !== "") body.append(name, value);
    }
    return jsonRequest("/api/contracts", { method: "POST", body });
  }
  return jsonRequest("/api/contracts/text", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...values, contract_text: editedText })
  });
}
function reviewInit() {
  const form = $("#review-form");
  if (!form) return;
  const area = $("#contract-text");
  area.addEventListener("input", () => $("#char-count").textContent = area.value.length.toLocaleString() + " characters");
  setupExtraction("#review-file", "#contract-text");
  $("#load-example").addEventListener("click", () => {
    $("#review-file")._cancelExtraction();
    area.value = exampleContract;
    area.dispatchEvent(new Event("input"));
    $("#upload-status").textContent = "Synthetic example loaded. You can edit the text before analysis.";
    for (const [key, value] of Object.entries({ client_entity: "Alpha Org", counterparty_entity: "Alpha Labs" })) form.elements.namedItem(key).value = value;
  });
  let step = 1;
  const panels = $$(".step-panel", form), back = $("#prev-step"), next = $("#next-step"), submit = $("#review-submit");
  function move(to, focus = true) {
    step = to;
    panels.forEach(panel => panel.hidden = Number(panel.dataset.step) !== step);
    $$("[data-progress-label]").forEach(label => {
      const number = Number(label.dataset.progressLabel);
      label.classList.toggle("current", number === step);
      label.classList.toggle("done", number < step);
      if (number === step) label.setAttribute("aria-current", "step"); else label.removeAttribute("aria-current");
    });
    $("#progress-fill").style.width = (step * 100 / 3) + "%";
    back.hidden = step === 1; next.hidden = step === 3; submit.hidden = step !== 3;
    if (step === 3) {
      const recap = $("#review-recap");
      recap.replaceChildren();
      for (const [name, value] of [["CLIENT", field(form, "client_entity") || "Not supplied"], ["COUNTERPARTY", field(form, "counterparty_entity") || "Not supplied"], ["DOCUMENT", area.value.length.toLocaleString() + " characters"], ["LE INPUTS", Object.keys(numericInputs(form)).length + " of 7"]]) {
        add(recap, add(node("div"), node("small", "", name), node("strong", "", value)));
      }
    }
    clearError("#review-error");
    if (focus) {
      const heading = $('.step-panel[data-step="' + step + '"] h2', form);
      heading.tabIndex = -1;
      heading.focus();
    }
  }
  back.addEventListener("click", () => move(Math.max(1, step - 1)));
  next.addEventListener("click", () => {
    const error = validate(form, step);
    if (error) { formError(form, "#review-error", error); return; }
    move(Math.min(3, step + 1));
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (submit.disabled) return;
    if (step < 3) { next.click(); return; }
    clearError("#review-error");
    for (const check of [1, 2]) {
      const error = validate(form, check);
      if (error) { move(check); formError(form, "#review-error", error); return; }
    }
    if (!$("#acknowledge").checked) { form._invalidInput = $("#acknowledge"); formError(form, "#review-error", "Acknowledge the review requirement before continuing."); return; }
    submit.disabled = back.disabled = true;
    form.setAttribute("aria-busy", "true");
    try {
      const job = await startReview(form);
      saveValue(JOB_KEY, job.job_id);
      saveValue(REPORT_KEY, null);
      location.assign("/results?job=" + encodeURIComponent(job.job_id));
    } catch (failure) { showError("#review-error", failure.message || "Could not start analysis."); }
    finally { submit.disabled = back.disabled = false; form.removeAttribute("aria-busy"); }
  });
  move(1, false);
}
function card(title, code, state) {
  const article = node("article", "agent-report");
  article.dataset.agent = { "01 / COI": "conflicts", "02 / CR": "clauses", "03 / CL": "confidentiality", "04 / LE": "litigation" }[code];
  const head = node("div", "agent-report-head"), label = node("div", "agent-report-title");
  add(label, node("span", "agent-num", code), node("h3", "", title));
  add(head, label, node("span", "status-pill " + (state === "complete" ? "complete" : "partial"), state || "not run"));
  article.append(head);
  return article;
}
function metric(parent, label, value) { add(parent, add(node("div", "submetric"), node("small", "", label), node("strong", "", text(value)))); }
function details(parent, title, values) {
  const box = node("details"), summary = node("summary", "", title), content = node("div", "finding-list");
  values.forEach(value => content.append(node("p", "finding-row", value)));
  add(box, summary, content); parent.append(box);
}
function renderCoi(coi) {
  const value = coi || {}, report = value.report || {}, article = card("Conflict of interest", "01 / COI", value.status);
  const metrics = node("div", "submetric-row");
  metric(metrics, "GRAPH CONFLICT", value.status === "complete" ? (report.conflict_detected ? "Detected" : "Not found") : "Undetermined");
  metric(metrics, "SEVERITY", report.severity);
  article.append(metrics);
  if (value.reason) article.append(node("p", "", value.reason));
  if (value.method) article.append(node("p", "", value.method));
  const findings = list(report.findings);
  if (findings.length) details(article, "Graph findings (" + findings.length + ")", findings.map(item =>
    list(item.path).join(" → ") + " · " + text(item.severity) + " · " +
    (item.verified ? "Verified" : "Unverified") + " · " +
    list(item.evidence).map(evidence => text(evidence.evidence, evidence.type)).join("; ")
  ));
  return article;
}
function renderCr(cr) {
  const value = cr || {}, clauses = list(value.clauses), article = card("Clause risk", "02 / CR", value.status);
  const metrics = node("div", "submetric-row");
  metric(metrics, "CLAUSES", clauses.length); metric(metrics, "STATUS", value.status);
  article.append(metrics);
  if (value.reason) article.append(node("p", "", value.reason));
  if (clauses.length) {
    const section = node("div", "finding-list");
    for (const item of clauses) {
      const model = item.model || {}, analysis = item.analysis || {};
      const clause = node("details"), heading = node("summary", "",
        "Clause " + text(item.clause_id) + " · " + text(item.section) + " · " + text(analysis.assessed_risk, model.prediction || item.status));
      clause.append(heading);
      const lines = [
        ["LegalBERT prediction", model.prediction],
        ["Raw model score (uncalibrated)", Number.isFinite(model.model_score) ? (model.model_score * 100).toFixed(2) + "%" : null],
        ["Class scores", Object.entries(model.class_scores || {}).map(([name, score]) => name + ": " + (Number(score) * 100).toFixed(2) + "%").join("; ")],
        ["Summary", analysis.summary],
        ["Risk reasoning", analysis.risk_reasoning],
        ["Contractual concern", analysis.contractual_concern],
        ["Suggested mitigation", analysis.suggested_mitigation],
        ["Evidence sufficient", analysis.evidence_sufficient === undefined ? null : (analysis.evidence_sufficient ? "Yes" : "No")],
        ["Agreement with model", analysis.agreement_with_model === undefined ? null : (analysis.agreement_with_model ? "Yes" : "No")],
        ["Human review", "Required"],
        ["Error", [item.reason, item.rag_error, item.llm_error].filter(Boolean).join("; ")],
        ["Interpretation", item.interpretation_note]
      ];
      for (const [label, value] of lines) if (value !== null && value !== undefined && value !== "") {
        const line = node("p"); add(line, node("strong", "", label + ": "), document.createTextNode(String(value))); clause.append(line);
      }
      const law = list(item.retrieved_law).map(entry => "Section " + text(entry.section) + " · " + text(entry.heading) +
        " · similarity " + text(entry.score) + " · " + text(entry.text));
      if (law.length) details(clause, "Retrieved Indian law", law);
      const relevant = list(analysis.relevant_sections).map(entry => text(entry.section) + " · " + text(entry.relevance));
      if (relevant.length) details(clause, "Relevant statutory context", relevant);
      const weak = list(analysis.irrelevant_or_weak_sections).map(entry => text(entry.section) + " · " + text(entry.reason));
      if (weak.length) details(clause, "Weak or irrelevant context", weak);
      section.append(clause);
    }
    article.append(section);
  }
  return article;
}
function renderCl(cl) {
  const value = cl || {}, report = value.report || {}, article = card("Confidentiality leakage", "03 / CL", value.status);
  const metrics = node("div", "submetric-row");
  metric(metrics, "FINDINGS", report.total_findings ?? list(report.findings).length);
  metric(metrics, "STATUS", value.status);
  article.append(metrics);
  if (value.reason) article.append(node("p", "", value.reason));
  const counts = report.summary || {};
  if (Object.keys(counts).length) details(article, "Summary counts", Object.entries(counts).map(([name, count]) => name.replaceAll("_", " ") + ": " + count));
  const findings = list(report.findings);
  if (findings.length) details(article, "Sensitive findings", findings.map(item =>
    text(item.type) + " · " + text(item.sensitivity) + " · " + text(item.category) +
    " · " + text(item.value) + " · clause " + text(item.clause_id) + " · " + text(item.source)));
  const activities = list(report.processing_activity);
  if (activities.length) details(article, "Processing activity", activities.map(item =>
    text(item.activity, item.type) + " · " + text(item.value) + " · clause " + text(item.clause_id)));
  return article;
}
function renderLe(le) {
  const value = le || {}, result = value.result || {}, article = card("Litigation exposure", "04 / LE", value.status);
  const metrics = node("div", "submetric-row");
  const probability = Number(result.litigation_probability);
  metric(metrics, "MODEL SCORE", result.litigation_probability == null || !Number.isFinite(probability) ? "Not available" : (probability * 100).toFixed(1) + "%");
  metric(metrics, "RISK BAND", result.risk_level);
  article.append(metrics);
  article.append(node("p", "", value.reason || value.interpretation || "Synthetic-trained model output; human review required."));
  if (result.features_used) details(article, "Features used", Object.entries(result.features_used).map(([key, item]) => key.replaceAll("_", " ") + ": " + item));
  if (result.shap_explanation) details(article, "Model contributions", Object.entries(result.shap_explanation).map(([key, item]) => key.replaceAll("_", " ") + ": " + item));
  return article;
}
function chart(cr) {
  const root = $("#classification-chart");
  root.replaceChildren();
  const labels = list(cr?.clauses).map(item => item.model?.prediction === "Baseline" ? "Seed" : item.model?.prediction).filter(Boolean);
  if (!labels.length) { root.append(node("p", "chart-empty", "No clause classifications available.")); return; }
  for (const label of ["High", "Medium", "Low", "Seed"]) {
    const count = labels.filter(value => value === label).length;
    const row = node("div", "chart-row"), track = node("div", "chart-track"), fill = node("div", "chart-fill " + label.toLowerCase());
    fill.style.width = (100 * count / labels.length) + "%";
    add(track, fill); add(row, node("span", "", label === "Seed" ? "Baseline" : label), track, node("b", "", count));
    root.append(row);
  }
}
function renderReport(result, jobId) {
  $("#empty-results").hidden = true;
  $("#result-content").hidden = false;
  $("#download-result").hidden = false;
  $("#report-id").textContent = "REVIEW / " + text(result.document?.file_name, "CONTRACT");
  const statuses = result.agent_statuses || {};
  const completedCount = ["CR", "CL", "COI", "LE"].filter(key => statuses[key] === "complete").length;
  const complete = completedCount === 4;
  $("#report-subtitle").textContent = complete ? "All four agents completed. Findings still require human review." : "One or more checks were unavailable or skipped. Inspect each status below.";
  $("#report-state").textContent = complete ? "All four agents completed" : "Partial or incomplete coverage";
  $("#report-complete-count").textContent = completedCount + " / 4";
  const summary = $("#result-summary-grid");
  summary.replaceChildren();
  for (const [code, title, value] of [
    ["01 / COI", "Graph result", statuses.COI || "not run"],
    ["02 / CR", "Clause risk", statuses.CR || "not run"],
    ["03 / CL", "Confidentiality", statuses.CL || "not run"],
    ["04 / LE", "Litigation", statuses.LE || "not run"]
  ]) add(summary, add(node("div", "summary-cell"), node("span", "small-index", code), node("strong", "", value), node("span", "", title)));
  $("#report-details").replaceChildren(renderCoi(result.coi), renderCr(result.cr), renderCl(result.cl), renderLe(result.le));
  chart(result.cr);
  const reasons = $("#review-reasons");
  reasons.replaceChildren();
  ["Human legal review is required.", ...list(result.warnings)].forEach(value => reasons.append(node("li", "", value)));
  $("#raw-result").textContent = JSON.stringify(result, null, 2);
  $("#download-result").onclick = () => {
    if (jobId) location.assign("/api/jobs/" + encodeURIComponent(jobId) + "/reports/json");
    else downloadJson(result, "lexguard-report.json");
  };
  const pdf = $("#download-pdf");
  if (pdf) {
    pdf.hidden = !jobId || !result.outputs?.pdf;
    if (!pdf.hidden) pdf.href = "/api/jobs/" + encodeURIComponent(jobId) + "/reports/pdf";
  }
}
function downloadJson(value, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = node("a"); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function resultsInit() {
  if (!$("#result-content")) return;
  const storedJob = savedValue(JOB_KEY);
  const jobId = new URLSearchParams(location.search).get("job") || storedJob;
  let cached = null;
  try { if (jobId === storedJob) cached = JSON.parse(savedValue(REPORT_KEY) || "null"); } catch {}
  if (cached && (typeof cached !== "object" || Array.isArray(cached) || !cached.agent_statuses)) cached = null;
  if (jobId !== storedJob) { saveValue(REPORT_KEY, null); saveValue(JOB_KEY, jobId); }
  $("#clear-report").onclick = () => { saveValue(JOB_KEY, null); saveValue(REPORT_KEY, null); location.replace("/results"); };
  if (!jobId) {
    if (cached) renderReport(cached, null);
    else $("#empty-results").hidden = false;
    return;
  }
  const progress = node("section", "job-tracker");
  progress.id = "job-progress";
  progress.setAttribute("aria-label", "Live contract analysis");
  const visual = node("div", "job-visual");
  visual.setAttribute("aria-hidden", "true");
  add(visual, node("span", "job-grid"), node("span", "job-halo job-halo-outer"), node("span", "job-halo job-halo-inner"), node("span", "job-orb"));
  const sheet = node("div", "job-sheet");
  add(sheet, node("span", "job-sheet-heading", "LEXGUARD / ACTIVE REVIEW"),
    node("span", "job-sheet-title", "Agreement analysis"),
    node("span", "job-sheet-line job-sheet-line-long"),
    node("span", "job-sheet-line job-sheet-line-mid"),
    node("span", "job-sheet-focus", "CLAUSE UNDER REVIEW"),
    node("span", "job-sheet-line job-sheet-line-short"));
  visual.append(sheet, node("span", "job-scan"));
  const copy = node("div", "job-copy");
  const statusMessage = node("p", "job-message", "Waiting for the latest update…");
  statusMessage.setAttribute("role", "status");
  add(copy, node("span", "kicker", "LIVE ANALYSIS / IN PROGRESS"),
    node("h2", "", "Reading between the lines."),
    statusMessage);
  const meta = node("div", "job-meter-meta");
  add(meta, node("span", "job-stage-label", "PREPARING DOCUMENT"), node("strong", "job-percent", "0%"));
  const bar = node("progress", "job-meter"); bar.max = 100; bar.value = 0;
  bar.setAttribute("aria-label", "Contract analysis progress");
  const stages = node("div", "job-stages");
  for (const [stage, title] of [["cr", "Clause risk"], ["cl", "Privacy"], ["coi", "Conflict"], ["le", "Exposure"]]) {
    const step = node("span", "job-stage-pill", title);
    step.dataset.stage = stage;
    stages.append(step);
  }
  const log = node("ol", "progress-log"); log.setAttribute("aria-label", "Analysis events");
  add(copy, meta, bar, stages, log);
  add(progress, visual, copy);
  $("#empty-results").before(progress);
  let source, timer, refreshing = false, finished = false, lastEventId = 0;
  let lastProgress = "";
  const stop = () => { finished = true; source?.close(); clearTimeout(timer); };
  const stageLabels = { queued: "Waiting in queue", running: "Starting analysis", ingestion: "Reading document", extraction: "Reading document", cr: "Clause risk", cr_init: "Preparing clause analysis", rag: "Retrieving legal context", rag_init: "Preparing legal context", llm: "Reviewing clause evidence", llm_init: "Preparing clause explanation", cl: "Confidentiality", coi: "Conflict of interest", le: "Litigation exposure", report: "Preparing report" };
  function update(event) {
    if (finished) return;
    const signature = JSON.stringify([event.stage, event.percent, event.message]);
    if (signature === lastProgress) return;
    lastProgress = signature;
    const pct = Math.max(0, Math.min(100, Number(event.percent) || 0));
    bar.value = Math.max(bar.value, pct);
    $(".job-message", progress).textContent = text(event.message, "Analyzing…");
    $(".job-percent", progress).textContent = bar.value + "%";
    $(".job-stage-label", progress).textContent = (stageLabels[event.stage] || text(event.stage, "Preparing").replaceAll("_", " ")).toUpperCase();
    progress.style.setProperty("--job-progress", bar.value + "%");
    const order = ["cr", "cl", "coi", "le"];
    const phase = ["rag", "llm", "cr_init", "rag_init", "llm_init"].includes(event.stage) ? "cr" : event.stage;
    const position = order.indexOf(phase);
    $$(".job-stage-pill", progress).forEach((pill, index) => {
      pill.classList.toggle("is-current", index === position);
      pill.classList.toggle("is-done", position > index || event.stage === "report");
    });
    if (event.message) log.append(node("li", "", event.message));
    while (log.children.length > 45) log.firstElementChild.remove();
    log.scrollTop = log.scrollHeight;
  }
  async function refresh() {
    if (refreshing || finished) return;
    refreshing = true;
    clearTimeout(timer);
    try {
      const job = await jsonRequest("/api/jobs/" + encodeURIComponent(jobId), { cache: "no-store", signal: AbortSignal.timeout(10000) });
      if (job.status === "complete" && job.result) {
        stop(); progress.remove();
        saveValue(REPORT_KEY, JSON.stringify(job.result));
        renderReport(job.result, jobId);
      } else if (job.status === "failed") {
        stop(); progress.classList.add("is-failed");
        $(".job-copy .kicker", progress).textContent = "ANALYSIS STOPPED";
        $(".job-copy h2", progress).textContent = "This review could not finish.";
        $(".job-stage-label", progress).textContent = "FAILED";
        $(".job-message", progress).textContent = job.error || "Analysis failed.";
        const restart = node("a", "btn btn-outline", "Start a new review");
        restart.href = "/review"; $(".job-copy", progress).append(restart);
      } else {
        progress.classList.remove("is-reconnecting");
        $(".job-message", progress).textContent = text(job.latest_progress?.message, "Analyzing…");
        update(job.latest_progress || {});
      }
    } catch (error) {
      if (error.status === 404) {
        stop(); progress.remove();
        if (cached) renderReport(cached, null);
        else {
          $("#empty-results").hidden = false;
          $("#empty-results h2").textContent = "This review is no longer available.";
          $("#empty-results p").textContent = "The server may have restarted. Start a new review to generate a report.";
          $("#empty-results a").textContent = "Start a new review";
        }
      } else {
        progress.classList.add("is-reconnecting");
        $(".job-message", progress).textContent = "Connection interrupted. Retrying automatically… Your review may still be running.";
      }
    } finally {
      refreshing = false;
      if (!finished) timer = setTimeout(refresh, source ? 15000 : 4000);
    }
  }
  refresh().then(() => {
    if (finished || !window.EventSource) return;
    source = new EventSource("/api/jobs/" + encodeURIComponent(jobId) + "/events");
    source.addEventListener("progress", event => {
      const id = Number(event.lastEventId);
      if (id && id <= lastEventId) return;
      lastEventId = id;
      try { update(JSON.parse(event.data)); } catch {}
    });
    source.addEventListener("complete", refresh);
    source.addEventListener("failed", refresh);
    source.onerror = () => { source?.close(); source = null; refresh(); };
  });
  window.addEventListener("pagehide", stop, { once: true });
  window.addEventListener("pageshow", event => { if (event.persisted) location.reload(); });
}
function toolInit() {
  const form = $("#tool-form");
  if (!form) return;
  const kind = $("[data-tool]")?.dataset.tool;
  let latest = null;
  if (["clauses", "confidentiality"].includes(kind)) {
    setupExtraction("#tool-file", '[name="contract_text"]');
    $("#load-example")?.addEventListener("click", () => {
      $("#tool-file")._cancelExtraction();
      form.elements.namedItem("contract_text").value = exampleContract;
      $("#upload-status").textContent = "Synthetic example loaded. You can edit the text before analysis.";
    });
  }
  form.addEventListener("submit", async event => {
    event.preventDefault(); clearError("#tool-error");
    const submit = $("#tool-submit");
    if (submit.disabled) return;
    const invalid = validate(form);
    if (invalid) { formError(form, "#tool-error", invalid); return; }
    submit.disabled = true;
    form.setAttribute("aria-busy", "true");
    const label = [...submit.childNodes];
    submit.replaceChildren(document.createTextNode("Analyzing…"));
    $("#tool-output").hidden = true;
    latest = null;
    let url, body;
    if (kind === "clauses" || kind === "confidentiality") {
      url = "/api/tools/" + kind;
      body = { contract_text: field(form, "contract_text") };
    } else {
      const values = submitValues(form);
      url = "/api/tools/" + kind;
      body = kind === "conflicts" ? {
        client_entity: values.client_entity, counterparty_entity: values.counterparty_entity,
        additional_entities: values.additional_entities
      } : values;
    }
    try {
      latest = await jsonRequest(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const target = $("#tool-output-content");
      target.replaceChildren();
      if (kind === "conflicts") target.append(renderCoi(latest));
      if (kind === "clauses") target.append(renderCr(latest));
      if (kind === "confidentiality") target.append(renderCl(latest));
      if (kind === "litigation") add(target, renderCoi(latest.coi), renderLe(latest.le));
      const raw = node("details");
      add(raw, node("summary", "", "View raw response"), node("pre", "raw-output", JSON.stringify(latest, null, 2)));
      target.append(raw);
      $("#tool-output").hidden = false;
      $("#tool-output").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (failure) { showError("#tool-error", failure.message); }
    finally { submit.disabled = false; submit.replaceChildren(...label); form.removeAttribute("aria-busy"); }
  });
  $("#tool-export")?.addEventListener("click", () => { if (latest) downloadJson(latest, "lexguard-" + kind + ".json"); });
}
document.addEventListener("DOMContentLoaded", () => {
  themeInit(); reviewInit(); resultsInit(); toolInit(); systemStatus();
  setInterval(systemStatus, 15000);
});
