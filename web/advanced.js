"use strict";
const byId = id => document.getElementById(id);
const sampleText = "MASTER SERVICES AGREEMENT\n\n1. Services. Alpha Labs shall deliver the services described in the signed statement of work.\n\n2. Confidentiality. Each party shall protect confidential information and limit access to authorized personnel.\n\n3. Liability. Alpha Labs shall indemnify Alpha Org for third-party intellectual property claims.\n\n4. Governing law. Indian law governs this agreement.";
const features = {
  deal_size: 750000, liability_cap: 1, auto_renewal: 1,
  jurisdiction_risk: 5, indemnification_clause: 1,
  dispute_history: 0, governing_law_clarity: 3
};
const samples = {
  "/api/tools/conflicts": { client_entity: "Alpha Org", counterparty_entity: "Alpha Labs", additional_entities: "" },
  "/api/tools/clauses": { contract_text: sampleText },
  "/api/tools/confidentiality": { contract_text: sampleText },
  "/api/tools/litigation": {
    client_entity: "Alpha Org", counterparty_entity: "Alpha Labs", additional_entities: "",
    le_features: features, clause_deviation_score: 0.35
  }
};
let latest = null;
let extraction, extracting = false, extractionVersion = 0;
function cancelExtraction() {
  extractionVersion++;
  extraction?.abort();
  extracting = false;
  byId("file").value = "";
}
function parseBody() {
  let value;
  try { value = JSON.parse(byId("request-json").value); } catch { throw Error("Enter valid JSON."); }
  if (!value || Array.isArray(value) || typeof value !== "object") throw Error("The JSON body must be an object.");
  return value;
}
function loadSample() {
  cancelExtraction();
  const route = byId("endpoint").value;
  byId("request-json").value = JSON.stringify(samples[route], null, 2);
  byId("endpoint-note").textContent = route.includes("litigation")
    ? "This route searches the configured graph before evaluating litigation exposure."
    : "The response reports unavailable or skipped checks explicitly.";
  byId("file").disabled = !Object.hasOwn(samples[route], "contract_text");
  byId("file-status").textContent = byId("file").disabled
    ? "File preview is available for clause risk and confidentiality."
    : "TXT, PDF, or DOCX up to 5 MB.";
}
function display(value, route, status) {
  latest = value;
  byId("results").hidden = false;
  byId("result-summary").textContent = "HTTP " + status + " · " + route;
  byId("result-summary").className = "response-summary " + (status >= 400 ? "failure" : "success");
  byId("result-meta").textContent = status >= 400 ? "Request failed" : "Request completed";
  byId("raw-json").textContent = JSON.stringify(value, null, 2);
  const visual = byId("visual-results");
  visual.replaceChildren();
  if (value && typeof value === "object") {
    for (const [name, part] of Object.entries(value)) {
      if (!["status", "reason", "report", "coi", "le", "clauses"].includes(name)) continue;
      const row = document.createElement("p");
      row.className = "result-line";
      row.textContent = name + ": " + (typeof part === "object" ? JSON.stringify(part) : String(part));
      visual.append(row);
    }
  }
  byId("results").scrollIntoView({ behavior: "smooth", block: "start" });
}
async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw Error("Status unavailable");
    const values = await response.json();
    let ready = 0;
    for (const agent of ["cr", "cl", "coi", "le"]) {
      const value = values[agent] || "unavailable";
      if (value === "ready") ready++;
      const element = byId("status-" + agent);
      element.textContent = value.replaceAll("_", " ");
      element.className = "service-pill " + (value === "ready" ? "ready" : value === "degraded" ? "degraded" : "unavailable");
    }
    byId("system-state").textContent = ready + " available / 4";
    byId("status-extra").textContent = "Availability reflects local dependencies. External services are checked during analysis.";
  } catch {
    byId("system-state").textContent = "Status unavailable";
    for (const agent of ["cr", "cl", "coi", "le"]) {
      byId("status-" + agent).textContent = "Unavailable";
      byId("status-" + agent).className = "service-pill unavailable";
    }
  }
}
byId("refresh-status").addEventListener("click", refreshStatus);
byId("endpoint").addEventListener("change", loadSample);
byId("load-sample").addEventListener("click", loadSample);
byId("request-json").addEventListener("input", () => {
  if (extracting) { cancelExtraction(); byId("file-status").textContent = "Extraction cancelled. Your edited JSON will be used."; }
});
byId("file").addEventListener("change", async event => {
  const file = event.target.files?.[0];
  if (!file) return;
  cancelExtraction();
  const version = extractionVersion;
  const status = byId("file-status");
  if (!/\.(pdf|docx|txt)$/i.test(file.name)) { status.textContent = "Use a PDF, DOCX, or TXT file."; return; }
  if (file.size > 5 * 1024 * 1024) { status.textContent = "The file exceeds 5 MB."; return; }
  try {
    const body = parseBody();
    extracting = true;
    extraction = new AbortController();
    const data = new FormData(); data.append("file", file);
    status.textContent = "Extracting " + file.name + "…";
    const response = await fetch("/api/extract", { method: "POST", body: data, signal: extraction.signal });
    const result = await response.json();
    if (version !== extractionVersion) return;
    if (!response.ok) throw Error(result.detail || "Extraction failed.");
    body.contract_text = result.text;
    byId("request-json").value = JSON.stringify(body, null, 2);
    status.textContent = file.name + " inserted into the JSON. Review it before sending.";
  } catch (error) { if (version === extractionVersion) status.textContent = error.message; }
  finally { if (version === extractionVersion) extracting = false; }
});
byId("request-form").addEventListener("submit", async event => {
  event.preventDefault();
  byId("form-error").hidden = true;
  const submit = byId("submit");
  if (submit.disabled) return;
  if (extracting) { byId("form-error").textContent = "Wait for document extraction to finish before sending."; byId("form-error").hidden = false; return; }
  submit.disabled = true;
  submit.textContent = "Sending…";
  byId("request-form").setAttribute("aria-busy", "true");
  for (const id of ["endpoint", "load-sample", "file", "request-json"]) byId(id).disabled = true;
  byId("results").hidden = true;
  latest = null;
  try {
    const body = parseBody(), route = byId("endpoint").value;
    const response = await fetch(route, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
    const result = await response.json();
    display(result, route, response.status);
  } catch (error) {
    byId("form-error").textContent = error.message || "Request failed.";
    byId("form-error").hidden = false;
  } finally {
    submit.disabled = false; submit.textContent = "Send request";
    byId("request-form").removeAttribute("aria-busy");
    for (const id of ["endpoint", "load-sample", "request-json"]) byId(id).disabled = false;
    byId("file").disabled = !Object.hasOwn(samples[byId("endpoint").value], "contract_text");
    refreshStatus();
  }
});
byId("download").addEventListener("click", () => {
  if (latest === null) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(latest, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = "lexguard-response.json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
loadSample();
refreshStatus();
