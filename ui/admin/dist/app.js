"use strict";
const state = {
    activeView: "catalogue",
    apiBase: localStorage.getItem("totalrecall.admin.apiBase") ?? "http://localhost:8000/v1",
    token: localStorage.getItem("totalrecall.admin.token") ?? "",
    tenantId: localStorage.getItem("totalrecall.admin.tenantId") ?? "tenant_dev",
    applicationId: localStorage.getItem("totalrecall.admin.applicationId") ?? "app_test",
};
let monitoringRefreshTimer = null;
const $ = (id) => {
    const element = document.getElementById(id);
    if (!element) {
        throw new Error(`Missing element: ${id}`);
    }
    return element;
};
function setStatus(message, kind = "ok") {
    const statusLine = $("status-line");
    statusLine.textContent = message;
    statusLine.className = kind === "ok" ? "status-ok" : "status-error";
}
function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
function prettyJson(value) {
    return JSON.stringify(value, null, 2);
}
function getInput(id) {
    return $(id);
}
function getSelect(id) {
    return $(id);
}
function getTextArea(id) {
    return $(id);
}
function saveConnection() {
    state.apiBase = getInput("api-base").value.trim().replace(/\/$/, "");
    state.token = getInput("api-token").value.trim();
    state.tenantId = getInput("tenant-id").value.trim();
    state.applicationId = getInput("application-id").value.trim();
    getInput("memory-application-id").value = state.applicationId;
    localStorage.setItem("totalrecall.admin.apiBase", state.apiBase);
    localStorage.setItem("totalrecall.admin.token", state.token);
    localStorage.setItem("totalrecall.admin.tenantId", state.tenantId);
    localStorage.setItem("totalrecall.admin.applicationId", state.applicationId);
    setStatus("Connection saved.");
}
function requiresBearerToken(path) {
    return path.startsWith("/monitoring/")
        || path.startsWith("/credentials")
        || path.startsWith("/catalogue")
        || path.startsWith("/memories/")
        || path.startsWith("/learning/")
        || path.startsWith("/generations")
        || path.startsWith("/flags");
}
async function apiFetch(path, init = {}) {
    if (!state.apiBase) {
        throw new Error("API base is required.");
    }
    if (requiresBearerToken(path) && !state.token) {
        throw new Error("Bearer token is required. For Docker, use dev-token and click Save.");
    }
    const headers = new Headers(init.headers);
    if (state.token) {
        headers.set("Authorization", `Bearer ${state.token}`);
    }
    if (init.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    const response = await fetch(`${state.apiBase}${path}`, { ...init, headers });
    const text = await response.text();
    let payload = null;
    if (text) {
        try {
            payload = JSON.parse(text);
        }
        catch {
            payload = text;
        }
    }
    if (!response.ok) {
        const detail = typeof payload === "object" && payload !== null && "detail" in payload
            ? payload.detail
            : response.statusText;
        throw new Error(`${response.status} ${detail}`);
    }
    return payload;
}
function paramsFrom(values) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(values)) {
        if (value !== null && value !== undefined && String(value).length > 0) {
            params.set(key, String(value));
        }
    }
    const query = params.toString();
    return query ? `?${query}` : "";
}
function commaList(value) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
}
function selectedTestTypes() {
    return Array.from(document.querySelectorAll("[data-generation-test-type]:checked")).map((input) => input.value);
}
async function generateFromPrompt(event) {
    event.preventDefault();
    saveConnection();
    const prompt = getTextArea("generation-prompt").value.trim();
    const domain = getInput("generation-domain").value.trim();
    const jiraKey = getInput("generation-jira-key").value.trim();
    const route = getInput("generation-route").value.trim();
    const tags = commaList(getInput("generation-tags").value);
    const testTypes = selectedTestTypes();
    const maxInputTokens = Number(getInput("generation-max-input-tokens").value || "12000");
    if (!state.tenantId || !state.applicationId || !prompt || !domain) {
        throw new Error("Tenant, application, prompt, and domain are required.");
    }
    const body = {
        tenant_id: state.tenantId,
        application_id: state.applicationId,
        prompt,
        ...(jiraKey ? { jira_key: jiraKey } : {}),
        ...(testTypes.length > 0 ? { test_types: testTypes } : {}),
        target: {
            language: getSelect("generation-language").value,
            framework: getSelect("generation-framework").value,
            pattern: "pom",
            locator_strategy: getSelect("generation-locator").value,
        },
        scope: {
            domain,
            ...(route ? { route } : {}),
            tags,
        },
        provider: {
            provider_id: getInput("generation-provider").value.trim() || "stub",
            model: getInput("generation-model").value.trim() || "stub",
        },
        options: {
            validate: getInput("generation-validate").checked,
            allow_repair: getInput("generation-allow-repair").checked,
            max_input_tokens: Number.isFinite(maxInputTokens) && maxInputTokens > 0 ? maxInputTokens : 12000,
        },
    };
    $("generation-result").innerHTML = '<p class="muted">Generation running.</p>';
    const result = await apiFetch("/generations", {
        method: "POST",
        body: JSON.stringify(body),
    });
    renderGenerationResult(result);
    setStatus(`Generation ${result.status}: ${result.request_id}`);
}
function renderGenerationResult(result) {
    const context = result.context ?? {};
    const skills = context.skill_ids ?? [];
    const memories = context.memory_ids ?? [];
    const artifacts = result.artifacts ?? [];
    const validationStatus = result.validation?.status ?? "n/a";
    $("generation-result").innerHTML = `
    <dl class="result-summary">
      <div><dt>Status</dt><dd>${escapeHtml(result.status)}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(validationStatus)}</dd></div>
      <div><dt>Input tokens</dt><dd>${escapeHtml(context.estimated_input_tokens ?? 0)}</dd></div>
      <div><dt>Artifacts</dt><dd>${escapeHtml(artifacts.length)}</dd></div>
      <div><dt>Request</dt><dd>${escapeHtml(result.request_id)}</dd></div>
      <div><dt>Skills</dt><dd>${escapeHtml(skills.length ? skills.join(", ") : "none")}</dd></div>
      <div><dt>Memory</dt><dd>${escapeHtml(memories.length ? memories.join(", ") : "none")}</dd></div>
      <div><dt>Tokens saved</dt><dd>${escapeHtml(context.estimated_tokens_saved ?? 0)}</dd></div>
    </dl>
    ${renderTestCasePack(result.test_case_pack)}
    ${renderArtifacts(artifacts)}
    ${renderErrors(result.errors ?? [])}
    <h3>Raw Result</h3>
    <pre>${escapeHtml(prettyJson(result))}</pre>
  `;
}
function renderTestCasePack(pack) {
    if (!pack) {
        return "";
    }
    return `
    <h3>Test Case Pack</h3>
    <pre>${escapeHtml(prettyJson(pack))}</pre>
  `;
}
function renderArtifacts(artifacts) {
    if (artifacts.length === 0) {
        return "";
    }
    return `
    <h3>Generated Artifacts</h3>
    <div class="artifact-list">
      ${artifacts
        .map((artifact) => `
            <article class="artifact">
              <strong>${escapeHtml(artifact.path)} <span class="badge">${escapeHtml(artifact.artifact_type)}</span></strong>
              <pre>${escapeHtml(artifact.content)}</pre>
            </article>
          `)
        .join("")}
    </div>
  `;
}
function renderErrors(errors) {
    if (errors.length === 0) {
        return "";
    }
    return `
    <h3>Errors</h3>
    <pre>${escapeHtml(prettyJson(errors))}</pre>
  `;
}
async function loadCredentials() {
    saveConnection();
    const result = await apiFetch("/credentials");
    renderCredentials(result.credentials);
    setStatus(`Loaded ${result.total} credential definitions.`);
}
async function saveRuntimeCredential(event) {
    event.preventDefault();
    saveConnection();
    const credentialKey = getSelect("credential-key").value;
    const value = getInput("credential-value").value.trim();
    const activate = getInput("credential-activate").checked;
    if (!value) {
        throw new Error("Credential value is required.");
    }
    const result = await apiFetch(`/credentials/${encodeURIComponent(credentialKey)}`, {
        method: "PUT",
        body: JSON.stringify({ value, activate }),
    });
    getInput("credential-value").value = "";
    getInput("credential-activate").checked = false;
    await loadCredentials();
    setStatus(result.activated
        ? `Saved ${credentialKey} and applied runtime defaults.`
        : `Saved ${credentialKey}.`);
}
function renderCredentials(credentials) {
    const body = $("credential-results");
    if (credentials.length === 0) {
        body.innerHTML = '<tr><td colspan="5" class="empty-cell">No credentials available.</td></tr>';
        return;
    }
    body.innerHTML = credentials
        .map((item) => {
        const integration = [
            item.provider_id ? `Provider: ${item.provider_id}` : "",
            item.memory_adapter ? `Memory: ${item.memory_adapter}` : "",
            item.env_var ? `Env: ${item.env_var}` : "",
        ]
            .filter(Boolean)
            .join(" | ");
        return `
        <tr class="credential-row ${item.configured ? "configured" : ""}">
          <td><span class="badge">${escapeHtml(item.platform)}</span></td>
          <td>
            <strong>${escapeHtml(item.label)}</strong>
            <p class="muted">${escapeHtml(item.usage)}</p>
            ${item.notes ? `<p class="muted">${escapeHtml(item.notes)}</p>` : ""}
          </td>
          <td>${item.configured ? "Configured" : "Not configured"}</td>
          <td>${escapeHtml(integration || "Stored credential")}</td>
          <td>
            <button type="button" data-credential-delete="${escapeHtml(item.key)}" ${item.configured ? "" : "disabled"}>Remove</button>
          </td>
        </tr>
      `;
    })
        .join("");
    body.querySelectorAll("[data-credential-delete]").forEach((button) => {
        button.addEventListener("click", () => {
            const key = button.dataset.credentialDelete;
            if (key) {
                void deleteRuntimeCredential(key).catch((error) => setStatus(String(error), "error"));
            }
        });
    });
}
async function deleteRuntimeCredential(credentialKey) {
    if (!window.confirm(`Remove stored credential '${credentialKey}'?`)) {
        return;
    }
    await apiFetch(`/credentials/${encodeURIComponent(credentialKey)}`, {
        method: "DELETE",
    });
    await loadCredentials();
    setStatus(`Removed ${credentialKey}.`);
}
async function loadMonitoring() {
    saveConnection();
    const summary = await apiFetch("/monitoring/summary");
    renderMonitoring(summary);
    setStatus(`Monitoring loaded: ${summary.status}.`);
}
function statusClass(status) {
    if (["healthy", "ok", "active"].includes(status)) {
        return "status-pill ok";
    }
    if (["degraded", "inactive", "unregistered", "unconfigured"].includes(status)) {
        return "status-pill warning";
    }
    return "status-pill error";
}
function statusPill(status) {
    return `<span class="${statusClass(status)}">${escapeHtml(status)}</span>`;
}
function renderMonitoring(summary) {
    const memory = summary.memory;
    const token = summary.token_efficiency;
    $("monitoring-status-cards").innerHTML = `
    <article class="metric-card">
      <span class="metric-label">System</span>
      <strong>${statusPill(summary.status)}</strong>
      <small>${escapeHtml(summary.tenant_id)} / ${escapeHtml(summary.actor_id)}</small>
    </article>
    <article class="metric-card">
      <span class="metric-label">Memory</span>
      <strong>${statusPill(memory.health.status)}</strong>
      <small>${escapeHtml(memory.active_adapter)} active</small>
    </article>
    <article class="metric-card">
      <span class="metric-label">Mem0</span>
      <strong>${statusPill(memory.mem0.status)}</strong>
      <small>${memory.mem0.credential_configured ? "credential configured" : "credential missing"}</small>
    </article>
    <article class="metric-card">
      <span class="metric-label">Tokens saved</span>
      <strong>${escapeHtml(token.estimated_tokens_saved_total)}</strong>
      <small>${escapeHtml(token.last_token_savings_percent)}% last run</small>
    </article>
  `;
    renderKeyValueList("monitoring-memory-list", {
        active_adapter: memory.active_adapter,
        configured_adapter: memory.configured_adapter,
        degraded: memory.health.degraded,
        mem0_credential_configured: memory.mem0.credential_configured,
        mem0_sdk_available: memory.mem0.sdk_available,
        memory_write_enabled: memory.mem0.write_enabled,
        memory_fail_open_on_search: memory.mem0.fail_open_on_search,
        search_total: memory.operations.search_total,
        search_success_total: memory.operations.search_success_total,
        search_failure_total: memory.operations.search_failure_total,
        search_cache_hit_total: memory.operations.search_cache_hit_total,
        average_search_latency_ms: memory.operations.average_search_latency_ms,
        upsert_total: memory.operations.upsert_total,
        delete_total: memory.operations.delete_total,
        last_success_at: memory.operations.last_success_at ?? "n/a",
        last_failure_at: memory.operations.last_failure_at ?? "n/a",
        last_error_type: memory.operations.last_error_type ?? "n/a",
    });
    renderKeyValueList("monitoring-token-list", {
        generations_total: token.generations_total,
        input_tokens_total: token.input_tokens_total,
        output_tokens_total: token.output_tokens_total,
        estimated_tokens_saved_total: token.estimated_tokens_saved_total,
        last_context_plan_id: token.last_context_plan_id ?? "n/a",
        last_baseline_input_tokens: token.last_baseline_input_tokens,
        last_estimated_input_tokens: token.last_estimated_input_tokens,
        last_estimated_tokens_saved: token.last_estimated_tokens_saved,
        last_token_savings_percent: token.last_token_savings_percent,
        last_selected_skill_count: token.last_selected_skill_count,
        last_selected_memory_count: token.last_selected_memory_count,
        last_excluded_memory_count: token.last_excluded_memory_count,
        last_max_input_tokens: token.last_max_input_tokens,
    });
    renderProviderMonitoring(summary.providers);
    $("monitoring-raw").textContent = prettyJson(summary);
}
function renderProviderMonitoring(providers) {
    const body = $("monitoring-provider-results");
    if (providers.length === 0) {
        body.innerHTML = '<tr><td colspan="5" class="empty-cell">No providers returned.</td></tr>';
        return;
    }
    body.innerHTML = providers
        .map((provider) => `
        <tr>
          <td>
            <strong>${escapeHtml(provider.provider_id)}</strong>
            <p class="muted">${provider.registered ? "registered" : "not registered"}</p>
          </td>
          <td>${statusPill(provider.status)}</td>
          <td>${provider.credential_configured ? "Configured" : "Not configured"}</td>
          <td>${escapeHtml(provider.latency_ms ?? "n/a")}</td>
          <td>${escapeHtml(provider.error ?? "")}</td>
        </tr>
      `)
        .join("");
}
function updateMonitoringRefresh() {
    if (monitoringRefreshTimer !== null) {
        window.clearInterval(monitoringRefreshTimer);
        monitoringRefreshTimer = null;
    }
    const intervalMs = Number(getSelect("monitoring-refresh-interval").value || "0");
    if (intervalMs > 0) {
        monitoringRefreshTimer = window.setInterval(() => {
            if (state.activeView === "monitoring") {
                void loadMonitoring().catch((error) => setStatus(String(error), "error"));
            }
        }, intervalMs);
    }
}
async function loadCatalogue() {
    saveConnection();
    const category = getSelect("catalogue-category").value;
    const status = getSelect("catalogue-status").value;
    const limit = getInput("catalogue-limit").value || "50";
    const query = paramsFrom({
        application_id: state.applicationId,
        category,
        status,
        limit,
    });
    const result = await apiFetch(`/catalogue${query}`);
    renderCatalogue(result);
    setStatus(`Loaded ${result.items.length} of ${result.total} catalogue entries.`);
}
function renderCatalogue(result) {
    const body = $("catalogue-results");
    if (result.items.length === 0) {
        body.innerHTML = '<tr><td colspan="4" class="empty-cell">No catalogue entries found.</td></tr>';
        return;
    }
    body.innerHTML = result.items
        .map((entry) => `
        <tr class="catalogue-row" data-entity-id="${escapeHtml(entry.entity_id)}">
          <td>${escapeHtml(entry.entity_id)}</td>
          <td><span class="badge">${escapeHtml(entry.category)}</span></td>
          <td>${escapeHtml(entry.status)}</td>
          <td>${escapeHtml(entry.summary)}</td>
        </tr>
      `)
        .join("");
    body.querySelectorAll(".catalogue-row").forEach((row) => {
        row.addEventListener("click", () => {
            const entityId = row.dataset.entityId;
            if (entityId) {
                void loadCatalogueDetail(entityId);
            }
        });
    });
}
async function loadCatalogueDetail(entityId) {
    const entry = await apiFetch(`/catalogue/${encodeURIComponent(entityId)}`);
    $("catalogue-detail").innerHTML = `
    <h3>${escapeHtml(entry.entity_id)}</h3>
    <p>${escapeHtml(entry.summary)}</p>
    <dl class="key-value-list">
      <div><dt>Category</dt><dd>${escapeHtml(entry.category)}</dd></div>
      <div><dt>Status</dt><dd>${escapeHtml(entry.status)}</dd></div>
      <div><dt>Application</dt><dd>${escapeHtml(entry.application_id)}</dd></div>
      <div><dt>Owner</dt><dd>${escapeHtml(entry.owner ?? "n/a")}</dd></div>
    </dl>
    <pre>${escapeHtml(prettyJson(entry))}</pre>
  `;
    if (entry.category === "dynamic_memory") {
        getInput("memory-entity-id").value = entry.entity_id;
        getInput("memory-application-id").value = entry.application_id;
    }
}
function updateMemoryDeleteState() {
    const hasEntity = getInput("memory-entity-id").value.trim().length > 0;
    const hasApp = getInput("memory-application-id").value.trim().length > 0;
    const confirmed = getInput("memory-confirm").checked;
    $("memory-delete-button").toggleAttribute("disabled", !(hasEntity && hasApp && confirmed));
}
async function deleteMemory(event) {
    event.preventDefault();
    saveConnection();
    const entityId = getInput("memory-entity-id").value.trim();
    const applicationId = getInput("memory-application-id").value.trim();
    const reason = getTextArea("memory-reason").value.trim() || null;
    const result = await apiFetch(`/memories/${encodeURIComponent(entityId)}`, {
        method: "DELETE",
        body: JSON.stringify({ application_id: applicationId, reason }),
    });
    $("memory-result").textContent = prettyJson(result);
    getInput("memory-confirm").checked = false;
    updateMemoryDeleteState();
    setStatus(`Memory ${entityId} tombstoned.`);
}
async function loadLearningRuns() {
    saveConnection();
    const limit = getInput("learning-limit").value || "20";
    const query = paramsFrom({ application_id: state.applicationId, limit });
    const runs = await apiFetch(`/learning/runs${query}`);
    renderLearningRuns(runs);
    setStatus(`Loaded ${runs.length} learning runs.`);
}
async function triggerLearningRun(event) {
    event.preventDefault();
    saveConnection();
    const framework = getSelect("learning-framework").value;
    const domain = getInput("learning-domain").value.trim();
    const body = {
        application_id: state.applicationId,
        scope: {
            repository: getInput("learning-repository").value.trim(),
            branch: getInput("learning-branch").value.trim(),
            path: getInput("learning-path").value.trim(),
            ...(framework ? { framework } : {}),
            ...(domain ? { domain } : {}),
        },
        trigger_type: "manual",
    };
    await apiFetch("/learning/runs", {
        method: "POST",
        body: JSON.stringify(body),
    });
    await loadLearningRuns();
}
function renderLearningRuns(runs) {
    const container = $("learning-runs");
    if (runs.length === 0) {
        container.innerHTML = '<p class="muted">No learning runs found.</p>';
        return;
    }
    container.innerHTML = runs
        .map((report) => `
        <article class="run-panel">
          <div class="run-header">
            <div>
              <h3>${escapeHtml(report.run.run_id)}</h3>
              <p>${escapeHtml(report.run.status)} - ${escapeHtml(report.discovered_count)} discovered</p>
            </div>
            <span class="badge">${escapeHtml(report.run.trigger_type)}</span>
          </div>
          <div class="discovery-list">
            ${report.run.discoveries.map((item) => renderDiscovery(report.run.run_id, item)).join("")}
          </div>
        </article>
      `)
        .join("");
    container.querySelectorAll("[data-learning-action]").forEach((button) => {
        button.addEventListener("click", () => {
            const action = button.dataset.learningAction;
            const runId = button.dataset.runId;
            const discoveryId = button.dataset.discoveryId;
            if (action && runId && discoveryId) {
                void decideDiscovery(runId, discoveryId, action);
            }
        });
    });
}
function renderDiscovery(runId, item) {
    const disabled = item.status !== "discovered" ? "disabled" : "";
    return `
    <section class="discovery">
      <strong>${escapeHtml(item.discovery_id)} - ${escapeHtml(item.discovery_type)}</strong>
      <span>${escapeHtml(item.summary)}</span>
      <span class="muted">Status: ${escapeHtml(item.status)} | Delta: ${escapeHtml(item.delta.state)} | Confidence: ${escapeHtml(item.confidence)}</span>
      <div class="action-row">
        <button type="button" class="secondary-button" data-learning-action="approve" data-run-id="${escapeHtml(runId)}" data-discovery-id="${escapeHtml(item.discovery_id)}" ${disabled}>Approve</button>
        <button type="button" data-learning-action="reject" data-run-id="${escapeHtml(runId)}" data-discovery-id="${escapeHtml(item.discovery_id)}" ${disabled}>Reject</button>
      </div>
    </section>
  `;
}
async function decideDiscovery(runId, discoveryId, action) {
    const reason = window.prompt(`${action} ${discoveryId}: reason`) ?? "";
    await apiFetch(`/learning/runs/${encodeURIComponent(runId)}/${action}/${encodeURIComponent(discoveryId)}`, {
        method: "POST",
        body: JSON.stringify({ reason: reason || null }),
    });
    await loadLearningRuns();
}
async function loadFlagsAndMetrics() {
    saveConnection();
    const [flags, metrics] = await Promise.all([
        apiFetch("/flags"),
        apiFetch("/metrics"),
    ]);
    const flagSnapshot = flags.flags;
    renderKeyValueList("flag-list", flagSnapshot?.values ?? {});
    renderKeyValueList("metric-list", metrics);
    setStatus("Loaded flags and metrics.");
}
function renderKeyValueList(id, values) {
    const entries = Object.entries(values);
    $(id).innerHTML =
        entries.length === 0
            ? "<div><dt>Empty</dt><dd>No values returned</dd></div>"
            : entries
                .map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(typeof value === "object" ? prettyJson(value) : value)}</dd></div>`)
                .join("");
}
function switchView(view) {
    state.activeView = view;
    document.querySelectorAll(".view").forEach((section) => {
        section.classList.toggle("active", section.id === `view-${view}`);
    });
    document.querySelectorAll(".tab-button").forEach((button) => {
        button.classList.toggle("active", button.dataset.view === view);
    });
}
async function refreshActive() {
    try {
        if (state.activeView === "generate") {
            setStatus("Generation form ready.");
        }
        else if (state.activeView === "credentials") {
            await loadCredentials();
        }
        else if (state.activeView === "monitoring") {
            await loadMonitoring();
        }
        else if (state.activeView === "catalogue") {
            await loadCatalogue();
        }
        else if (state.activeView === "learning") {
            await loadLearningRuns();
        }
        else if (state.activeView === "flags") {
            await loadFlagsAndMetrics();
        }
        else {
            setStatus("Memory form ready.");
        }
    }
    catch (error) {
        setStatus(error instanceof Error ? error.message : String(error), "error");
    }
}
function bind() {
    getInput("api-base").value = state.apiBase;
    getInput("api-token").value = state.token;
    getInput("tenant-id").value = state.tenantId;
    getInput("application-id").value = state.applicationId;
    getInput("memory-application-id").value = state.applicationId;
    $("save-connection").addEventListener("click", saveConnection);
    $("refresh-active").addEventListener("click", () => void refreshActive());
    $("generation-form").addEventListener("submit", (event) => void generateFromPrompt(event).catch((error) => setStatus(String(error), "error")));
    $("credential-form").addEventListener("submit", (event) => void saveRuntimeCredential(event).catch((error) => setStatus(String(error), "error")));
    $("load-credentials").addEventListener("click", () => void loadCredentials().catch((error) => setStatus(String(error), "error")));
    $("load-monitoring").addEventListener("click", () => void loadMonitoring().catch((error) => setStatus(String(error), "error")));
    $("monitoring-refresh-interval").addEventListener("change", updateMonitoringRefresh);
    $("catalogue-form").addEventListener("submit", (event) => {
        event.preventDefault();
        void refreshActive();
    });
    $("memory-delete-form").addEventListener("submit", (event) => void deleteMemory(event));
    $("learning-list-form").addEventListener("submit", (event) => {
        event.preventDefault();
        void loadLearningRuns().catch((error) => setStatus(String(error), "error"));
    });
    $("learning-trigger-form").addEventListener("submit", (event) => void triggerLearningRun(event).catch((error) => setStatus(String(error), "error")));
    $("load-flags").addEventListener("click", () => void loadFlagsAndMetrics().catch((error) => setStatus(String(error), "error")));
    ["memory-entity-id", "memory-application-id", "memory-confirm"].forEach((id) => {
        $(id).addEventListener("input", updateMemoryDeleteState);
        $(id).addEventListener("change", updateMemoryDeleteState);
    });
    document.querySelectorAll(".tab-button").forEach((button) => {
        button.addEventListener("click", () => {
            const view = button.dataset.view;
            if (view) {
                switchView(view);
            }
        });
    });
}
bind();
setStatus("Ready.");
