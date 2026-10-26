(() => {
  const $ = (id) => document.getElementById(id);
  const root = $("p4-root");
  if (!root) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const state = { scope: "individual", workspaceId: "", teamId: "", kind: "task" };

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (csrf) headers["X-CSRFToken"] = csrf;
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers
    });
    const raw = await response.text();
    let data = {};
    try { data = raw ? JSON.parse(raw) : {}; } catch (_) {}
    if (!response.ok) {
      throw new Error(data.error || data.message || `Request failed (${response.status})`);
    }
    return data;
  }

  function listFrom(data, key) {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data[key])) return data[key];
    if (Array.isArray(data.items)) return data.items;
    if (Array.isArray(data.results)) return data.results;
    return [];
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    }[c]));
  }

  function notice(message, bad = false) {
    const el = $("p4-message");
    el.textContent = message;
    el.className = "p4-message show" + (bad ? " bad" : "");
  }

  function contextParams() {
    const p = new URLSearchParams({ scope: state.scope, kind: state.kind });
    if (state.scope === "company") p.set("workspace_id", state.workspaceId);
    if (state.scope === "team") p.set("team_id", state.teamId);
    return p.toString();
  }

  function updateContextUI() {
    $("p4-workspace-wrap").hidden = state.scope === "individual";
    $("p4-team-wrap").hidden = state.scope !== "team";
    $("p4-create-team-wrap").hidden = state.scope !== "company";
    $("p4-scope-description").textContent = ({
      individual: "Private space: only you can access your personal items.",
      company: "Company space: shared within the selected company workspace.",
      team: "Team space: items are restricted to members of the selected team."
    })[state.scope];
    $("p4-heading").textContent = ({
      individual: "Your private items",
      company: "Company productivity",
      team: "Team productivity"
    })[state.scope];
  }

  async function loadWorkspaces() {
    const data = await api("/api/v4/workspaces");
    const workspaces = listFrom(data, "workspaces");
    const select = $("p4-workspace");
    select.innerHTML = '<option value="">Choose company workspace</option>' +
      workspaces.map(w => `<option value="${esc(w.id)}">${esc(w.name || w.slug || `Workspace ${w.id}`)}</option>`).join("");
    if (workspaces.length && !state.workspaceId) state.workspaceId = String(workspaces[0].id);
    if (state.workspaceId && workspaces.some(w => String(w.id) === state.workspaceId)) {
      select.value = state.workspaceId;
    } else {
      state.workspaceId = "";
    }
  }

  async function loadTeams() {
    const select = $("p4-team");
    if (!state.workspaceId) {
      select.innerHTML = '<option value="">Choose a company workspace first</option>';
      state.teamId = "";
      return;
    }
    const data = await api(`/api/v4/teams?workspace_id=${encodeURIComponent(state.workspaceId)}`);
    const teams = listFrom(data, "teams").filter(t => t.is_member !== false);
    select.innerHTML = '<option value="">Choose team</option>' +
      teams.map(t => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("");
    if (teams.length && !teams.some(t => String(t.id) === state.teamId)) {
      state.teamId = String(teams[0].id);
    }
    if (state.teamId && teams.some(t => String(t.id) === state.teamId)) {
      select.value = state.teamId;
    } else {
      state.teamId = "";
    }
  }

  function renderItems(items) {
    const list = $("p4-items");
    if (!items.length) {
      list.innerHTML = '<div class="p4-empty">Nothing here yet. Create your first item.</div>';
      return;
    }
    list.innerHTML = items.map(item => `
      <article class="p4-item">
        <div class="p4-item-head">
          <div>
            <span class="p4-pill">${esc(item.kind || state.kind)}</span>
            <span class="p4-pill">${esc(item.status || "open")}</span>
            ${item.priority ? `<span class="p4-pill">${esc(item.priority)} priority</span>` : ""}
          </div>
          <button type="button" class="p4-delete" data-delete="${esc(item.id)}">Delete</button>
        </div>
        <h3>${esc(item.title)}</h3>
        ${item.description ? `<p>${esc(item.description)}</p>` : ""}
        ${item.due_date ? `<small>Due: ${esc(item.due_date)}</small>` : ""}
      </article>
    `).join("");
  }

  async function loadItems() {
    $("p4-items").innerHTML = '<div class="p4-empty">Loading…</div>';
    if (state.scope !== "individual" && !state.workspaceId) {
      $("p4-items").innerHTML = '<div class="p4-empty">Select a company workspace first.</div>';
      return;
    }
    if (state.scope === "team" && !state.teamId) {
      $("p4-items").innerHTML = '<div class="p4-empty">Select a team you belong to.</div>';
      return;
    }
    try {
      const data = await api(`/api/v4/productivity/items?${contextParams()}`);
      renderItems(listFrom(data, "items"));
    } catch (e) {
      $("p4-items").innerHTML = `<div class="p4-empty">${esc(e.message)}</div>`;
    }
  }

  async function refresh() {
    updateContextUI();
    await loadItems();
  }

  root.querySelectorAll("[data-p4-scope]").forEach(button => {
    button.addEventListener("click", async () => {
      state.scope = button.dataset.p4Scope;
      root.querySelectorAll("[data-p4-scope]").forEach(b => b.classList.toggle("active", b === button));
      try {
        if (state.scope !== "individual") await loadWorkspaces();
        if (state.scope === "team") await loadTeams();
        await refresh();
      } catch (e) { notice(e.message, true); }
    });
  });

  $("p4-workspace").addEventListener("change", async e => {
    state.workspaceId = e.target.value;
    state.teamId = "";
    try {
      if (state.scope === "team") await loadTeams();
      await refresh();
    } catch (err) { notice(err.message, true); }
  });

  $("p4-team").addEventListener("change", e => {
    state.teamId = e.target.value;
    refresh();
  });

  $("p4-kind").addEventListener("change", e => {
    state.kind = e.target.value;
    refresh();
  });

  $("p4-form").addEventListener("submit", async e => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const payload = {
      scope: state.scope,
      kind: state.kind,
      title: String(form.get("title") || "").trim(),
      description: String(form.get("description") || "").trim(),
      priority: String(form.get("priority") || "medium"),
      due_date: String(form.get("due_date") || "") || null
    };
    if (state.scope === "company") payload.workspace_id = Number(state.workspaceId);
    if (state.scope === "team") {
      payload.workspace_id = Number(state.workspaceId);
      payload.team_id = Number(state.teamId);
    }
    if (!payload.title) return notice("Enter a title first.", true);
    try {
      await api("/api/v4/productivity/items", {
        method: "POST", body: JSON.stringify(payload)
      });
      e.currentTarget.reset();
      notice("Item created.");
      await loadItems();
    } catch (err) { notice(err.message, true); }
  });

  $("p4-create-team").addEventListener("click", async () => {
    const name = $("p4-new-team-name").value.trim();
    const description = $("p4-new-team-description").value.trim();
    if (!state.workspaceId) return notice("Choose a company workspace first.", true);
    if (!name) return notice("Enter a team name.", true);
    try {
      await api("/api/v4/teams", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: Number(state.workspaceId), name, description
        })
      });
      $("p4-new-team-name").value = "";
      $("p4-new-team-description").value = "";
      notice("Team created. You can now select it in the Teams space.");
      await loadTeams();
    } catch (err) { notice(err.message, true); }
  });

  $("p4-refresh").addEventListener("click", refresh);

  $("p4-items").addEventListener("click", async e => {
    const button = e.target.closest("[data-delete]");
    if (!button) return;
    if (!confirm("Delete this item?")) return;
    try {
      await api(`/api/v4/productivity/items/${encodeURIComponent(button.dataset.delete)}`, {
        method: "DELETE"
      });
      notice("Item deleted.");
      await loadItems();
    } catch (err) { notice(err.message, true); }
  });

  (async () => {
    try {
      await loadWorkspaces();
      updateContextUI();
      await loadItems();
    } catch (e) {
      notice("Phase 4 API could not load: " + e.message, true);
    }
  })();
})();
