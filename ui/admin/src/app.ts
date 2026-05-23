type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

interface CatalogueEntry {
  entity_id: string;
  tenant_id: string;
  application_id: string;
  category: string;
  status: string;
  summary: string;
  tags?: Record<string, JsonValue>;
  source?: Record<string, JsonValue> | null;
  owner?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  deleted_by?: string | null;
  deleted_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

interface CatalogueSearchResult {
  items: CatalogueEntry[];
  total: number;
}

interface LearningDiscovery {
  discovery_id: string;
  discovery_type: string;
  status: string;
  summary: string;
  confidence: number;
  warnings: string[];
  delta: {
    state: string;
    previous_hash?: string | null;
    current_hash?: string | null;
    changed_fields: string[];
  };
  source: Record<string, JsonValue>;
  proposed_tags: Record<string, JsonValue>;
}

interface LearningReport {
  run: {
    run_id: string;
    application_id: string;
    status: string;
    trigger_type: string;
    started_at: string;
    completed_at?: string | null;
    discoveries: LearningDiscovery[];
  };
  discovered_count: number;
  changed_count: number;
  removed_count: number;
  unchanged_count: number;
  rejected_count: number;
  warnings: string[];
}

interface AppState {
  activeView: "catalogue" | "memory" | "learning" | "flags";
  apiBase: string;
  token: string;
  applicationId: string;
}

const state: AppState = {
  activeView: "catalogue",
  apiBase: localStorage.getItem("totalrecall.admin.apiBase") ?? "http://localhost:8000/v1",
  token: localStorage.getItem("totalrecall.admin.token") ?? "",
  applicationId: localStorage.getItem("totalrecall.admin.applicationId") ?? "app_test",
};

const $ = <T extends HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing element: ${id}`);
  }
  return element as T;
};

function setStatus(message: string, kind: "ok" | "error" = "ok"): void {
  const statusLine = $("status-line");
  statusLine.textContent = message;
  statusLine.className = kind === "ok" ? "status-ok" : "status-error";
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function getInput(id: string): HTMLInputElement {
  return $<HTMLInputElement>(id);
}

function getSelect(id: string): HTMLSelectElement {
  return $<HTMLSelectElement>(id);
}

function getTextArea(id: string): HTMLTextAreaElement {
  return $<HTMLTextAreaElement>(id);
}

function saveConnection(): void {
  state.apiBase = getInput("api-base").value.trim().replace(/\/$/, "");
  state.token = getInput("api-token").value.trim();
  state.applicationId = getInput("application-id").value.trim();
  getInput("memory-application-id").value = state.applicationId;

  localStorage.setItem("totalrecall.admin.apiBase", state.apiBase);
  localStorage.setItem("totalrecall.admin.token", state.token);
  localStorage.setItem("totalrecall.admin.applicationId", state.applicationId);
  setStatus("Connection saved.");
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
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
  let payload: unknown = null;
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
        ? (payload as { detail: string }).detail
        : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return payload as T;
}

function paramsFrom(values: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && String(value).length > 0) {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

async function loadCatalogue(): Promise<void> {
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
  const result = await apiFetch<CatalogueSearchResult>(`/catalogue${query}`);
  renderCatalogue(result);
  setStatus(`Loaded ${result.items.length} of ${result.total} catalogue entries.`);
}

function renderCatalogue(result: CatalogueSearchResult): void {
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

  body.querySelectorAll<HTMLTableRowElement>(".catalogue-row").forEach((row) => {
    row.addEventListener("click", () => {
      const entityId = row.dataset.entityId;
      if (entityId) {
        void loadCatalogueDetail(entityId);
      }
    });
  });
}

async function loadCatalogueDetail(entityId: string): Promise<void> {
  const entry = await apiFetch<CatalogueEntry>(`/catalogue/${encodeURIComponent(entityId)}`);
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

function updateMemoryDeleteState(): void {
  const hasEntity = getInput("memory-entity-id").value.trim().length > 0;
  const hasApp = getInput("memory-application-id").value.trim().length > 0;
  const confirmed = getInput("memory-confirm").checked;
  $("memory-delete-button").toggleAttribute("disabled", !(hasEntity && hasApp && confirmed));
}

async function deleteMemory(event: SubmitEvent): Promise<void> {
  event.preventDefault();
  saveConnection();
  const entityId = getInput("memory-entity-id").value.trim();
  const applicationId = getInput("memory-application-id").value.trim();
  const reason = getTextArea("memory-reason").value.trim() || null;
  const result = await apiFetch<Record<string, JsonValue>>(
    `/memories/${encodeURIComponent(entityId)}`,
    {
      method: "DELETE",
      body: JSON.stringify({ application_id: applicationId, reason }),
    },
  );
  $("memory-result").textContent = prettyJson(result);
  getInput("memory-confirm").checked = false;
  updateMemoryDeleteState();
  setStatus(`Memory ${entityId} tombstoned.`);
}

async function loadLearningRuns(): Promise<void> {
  saveConnection();
  const limit = getInput("learning-limit").value || "20";
  const query = paramsFrom({ application_id: state.applicationId, limit });
  const runs = await apiFetch<LearningReport[]>(`/learning/runs${query}`);
  renderLearningRuns(runs);
  setStatus(`Loaded ${runs.length} learning runs.`);
}

async function triggerLearningRun(event: SubmitEvent): Promise<void> {
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
  await apiFetch<LearningReport>("/learning/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
  await loadLearningRuns();
}

function renderLearningRuns(runs: LearningReport[]): void {
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

  container.querySelectorAll<HTMLButtonElement>("[data-learning-action]").forEach((button) => {
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

function renderDiscovery(runId: string, item: LearningDiscovery): string {
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

async function decideDiscovery(
  runId: string,
  discoveryId: string,
  action: string,
): Promise<void> {
  const reason = window.prompt(`${action} ${discoveryId}: reason`) ?? "";
  await apiFetch<Record<string, JsonValue>>(
    `/learning/runs/${encodeURIComponent(runId)}/${action}/${encodeURIComponent(discoveryId)}`,
    {
      method: "POST",
      body: JSON.stringify({ reason: reason || null }),
    },
  );
  await loadLearningRuns();
}

async function loadFlagsAndMetrics(): Promise<void> {
  saveConnection();
  const [flags, metrics] = await Promise.all([
    apiFetch<Record<string, JsonValue>>("/flags"),
    apiFetch<Record<string, JsonValue>>("/metrics"),
  ]);
  renderKeyValueList("flag-list", (flags.flags as Record<string, JsonValue> | undefined)?.values ?? {});
  renderKeyValueList("metric-list", metrics);
  setStatus("Loaded flags and metrics.");
}

function renderKeyValueList(id: string, values: Record<string, JsonValue>): void {
  const entries = Object.entries(values);
  $(id).innerHTML =
    entries.length === 0
      ? "<div><dt>Empty</dt><dd>No values returned</dd></div>"
      : entries
          .map(
            ([key, value]) =>
              `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(typeof value === "object" ? prettyJson(value) : value)}</dd></div>`,
          )
          .join("");
}

function switchView(view: AppState["activeView"]): void {
  state.activeView = view;
  document.querySelectorAll<HTMLElement>(".view").forEach((section) => {
    section.classList.toggle("active", section.id === `view-${view}`);
  });
  document.querySelectorAll<HTMLButtonElement>(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
}

async function refreshActive(): Promise<void> {
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

function bind(): void {
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
  $("memory-delete-form").addEventListener("submit", (event) => void deleteMemory(event as SubmitEvent));
  $("learning-list-form").addEventListener("submit", (event) => {
    event.preventDefault();
    void loadLearningRuns().catch((error) => setStatus(String(error), "error"));
  });
  $("learning-trigger-form").addEventListener("submit", (event) =>
    void triggerLearningRun(event as SubmitEvent).catch((error) => setStatus(String(error), "error")),
  );
  $("load-flags").addEventListener("click", () =>
    void loadFlagsAndMetrics().catch((error) => setStatus(String(error), "error")),
  );

  ["memory-entity-id", "memory-application-id", "memory-confirm"].forEach((id) => {
    $(id).addEventListener("input", updateMemoryDeleteState);
    $(id).addEventListener("change", updateMemoryDeleteState);
  });

  document.querySelectorAll<HTMLButtonElement>(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.view as AppState["activeView"] | undefined;
      if (view) {
        switchView(view);
      }
    });
  });
}

bind();
setStatus("Ready.");
