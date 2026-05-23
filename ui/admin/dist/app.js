const state = {
  activeView: "catalogue",
  apiBase: localStorage.getItem("totalrecall.admin.apiBase") ?? "http://localhost:8000/v1",
  token: localStorage.getItem("totalrecall.admin.token") ?? "",
  applicationId: localStorage.getItem("totalrecall.admin.applicationId") ?? "app_test",
};

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
  state.applicationId = getInput("application-id").value.trim();
  getInput("memory-application-id").value = state.applicationId;

  localStorage.setItem("totalrecall.admin.apiBase", state.apiBase);
  localStorage.setItem("totalrecall.admin.token", state.token);
  localStorage.setItem("totalrecall.admin.applicationId", state.applicationId);
  setStatus("Connection saved.");
}

async function apiFetch(path, init = {}) {
  if (!state.apiBase) {
    throw new Error("API base is required.");
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
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
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
    .map(
      (entry) => `
        <tr class="catalogue-row" data-entity-id="${escapeHtml(entry.entity_id)}">
          <td>${escapeHtml(entry.entity_id)}</td>
          <td><span class="badge">${escapeHtml(entry.category)}</span></td>
          <td>${escapeHtml(entry.status)}</td>
          <td>${escapeHtml(entry.summary)}</td>
        </tr>
      `,
    )
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
    .map(
      (report) => `
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
      `,
    )
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
  await apiFetch(
    `/learning/runs/${encodeURIComponent(runId)}/${action}/${encodeURIComponent(discoveryId)}`,
    {
      method: "POST",
      body: JSON.stringify({ reason: reason || null }),
    },
  );
  await loadLearningRuns();
}

async function loadFlagsAndMetrics() {
  saveConnection();
  const [flags, metrics] = await Promise.all([apiFetch("/flags"), apiFetch("/metrics")]);
  renderKeyValueList("flag-list", flags.flags?.values ?? {});
  renderKeyValueList("metric-list", metrics);
  setStatus("Loaded flags and metrics.");
}

function renderKeyValueList(id, values) {
  const entries = Object.entries(values);
  $(id).innerHTML =
    entries.length === 0
      ? "<div><dt>Empty</dt><dd>No values returned</dd></div>"
      : entries
          .map(
            ([key, value]) =>
              `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(
                typeof value === "object" ? prettyJson(value) : value,
              )}</dd></div>`,
          )
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
    if (state.activeView === "catalogue") {
      await loadCatalogue();
    } else if (state.activeView === "learning") {
      await loadLearningRuns();
    } else if (state.activeView === "flags") {
      await loadFlagsAndMetrics();
    } else {
      setStatus("Memory form ready.");
    }
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), "error");
  }
}

function bind() {
  getInput("api-base").value = state.apiBase;
  getInput("api-token").value = state.token;
  getInput("application-id").value = state.applicationId;
  getInput("memory-application-id").value = state.applicationId;

  $("save-connection").addEventListener("click", saveConnection);
  $("refresh-active").addEventListener("click", () => void refreshActive());
  $("catalogue-form").addEventListener("submit", (event) => {
    event.preventDefault();
    void refreshActive();
  });
  $("memory-delete-form").addEventListener("submit", (event) => void deleteMemory(event));
  $("learning-list-form").addEventListener("submit", (event) => {
    event.preventDefault();
    void loadLearningRuns().catch((error) => setStatus(String(error), "error"));
  });
  $("learning-trigger-form").addEventListener("submit", (event) =>
    void triggerLearningRun(event).catch((error) => setStatus(String(error), "error")),
  );
  $("load-flags").addEventListener("click", () =>
    void loadFlagsAndMetrics().catch((error) => setStatus(String(error), "error")),
  );

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
