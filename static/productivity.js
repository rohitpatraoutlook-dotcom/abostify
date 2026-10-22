(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const form = $("#pc-form");
  const list = $("#pc-list");
  const message = $("#pc-message");
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const sections = {
    tasks: {endpoint:"/api/tasks", singular:"task", plural:"Your tasks"},
    goals: {endpoint:"/api/goals", singular:"goal", plural:"Your goals"},
    notes: {endpoint:"/api/notes", singular:"note", plural:"Your notes"},
    calendar: {endpoint:"/api/calendar/events", singular:"event", plural:"Your events"},
    reminders: {endpoint:"/api/reminders", singular:"reminder", plural:"Your reminders"}
  };

  let active = "tasks";
  let cache = {};

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    }[c]));
  }

  function notify(text, type="success") {
    message.textContent = text;
    message.className = `pc-message show ${type}`;
    window.clearTimeout(notify.timer);
    notify.timer = window.setTimeout(() => message.className = "pc-message", 4000);
  }

  async function request(url, options={}) {
    const headers = {...(options.headers || {})};
    if (options.body) {
      headers["Content-Type"] = "application/json";
      headers["X-CSRFToken"] = csrf;
    }
    const response = await fetch(url, {...options, headers, credentials:"same-origin"});
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error(data.error || data.message || "Request rejected. Please refresh the page and sign in again.");
      }
      throw new Error(data.error || data.message || `Request failed (${response.status})`);
    }
    return data;
  }

  function field(name) {
    const el = form.elements.namedItem(name);
    return el ? el.value.trim() : "";
  }

  function showSection(section) {
    if (!sections[section]) return;
    active = section;
    document.querySelectorAll(".pc-tab").forEach(btn => {
      const selected = btn.dataset.section === section;
      btn.classList.toggle("active", selected);
      btn.setAttribute("aria-selected", String(selected));
    });
    document.querySelectorAll("[data-fields]").forEach(el => {
      el.hidden = !el.dataset.fields.split(" ").includes(section);
    });
    $("#form-heading").textContent = `Create a ${sections[section].singular}`;
    $("#pc-submit").textContent = `+ Create ${sections[section].singular}`;
    $("#list-heading").textContent = sections[section].plural;
    form.reset();
    loadSection(section);
  }

  function dateLabel(value) {
    if (!value) return "";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
  }

  function card(item, section) {
    const title = escapeHTML(item.title || "Untitled");
    const description = escapeHTML(item.description || item.content || "");
    let meta = [];

    if (section === "tasks") {
      meta.push(item.status || "todo", item.priority || "medium");
      if (item.due_at) meta.push("Due " + dateLabel(item.due_at));
    } else if (section === "goals") {
      meta.push(item.status || "active");
      meta.push(`${Number(item.progress_percent || 0)}% complete`);
    } else if (section === "notes") {
      if (item.category) meta.push(item.category);
      if (item.is_pinned) meta.push("Pinned");
      if (Array.isArray(item.tags)) meta.push(...item.tags);
    } else if (section === "calendar") {
      meta.push(dateLabel(item.starts_at));
      if (item.location) meta.push(item.location);
      if (item.is_all_day) meta.push("All day");
    } else if (section === "reminders") {
      meta.push(dateLabel(item.remind_at), item.status || "pending");
    }

    const progress = section === "goals"
      ? `<div class="pc-progress"><span style="width:${Math.max(0,Math.min(100,Number(item.progress_percent)||0))}%"></span></div>`
      : "";

    const taskActions = section === "tasks" && item.status !== "completed"
      ? `<button class="pc-btn" data-complete="${item.id}" type="button">✓ Complete</button>`
      : "";

    const goalActions = section === "goals"
      ? `<button class="pc-btn" data-progress="${item.id}" type="button">Update progress</button>`
      : "";

    const noteActions = section === "notes"
      ? `<button class="pc-btn" data-pin="${item.id}" type="button">${item.is_pinned ? "Unpin" : "Pin"}</button>
         <button class="pc-btn" data-archive="${item.id}" type="button">${item.is_archived ? "Restore" : "Archive"}</button>`
      : "";

    const editAction = `<button class="pc-btn" data-edit="${item.id}" type="button">Edit</button>`;

    return `<article class="pc-item">
      <div class="pc-item-top"><div><h3>${title}</h3>${description ? `<p>${description}</p>` : ""}</div>
      <button class="pc-delete" data-delete="${item.id}" type="button" aria-label="Delete ${title}">Delete</button></div>
      <div class="pc-meta">${meta.map(x => `<span class="pc-badge">${escapeHTML(x)}</span>`).join("")}</div>
      ${progress}
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">${editAction}${taskActions}${goalActions}${noteActions}</div>
    </article>`;
  }

  async function loadSection(section) {
    list.innerHTML = '<div class="pc-empty">Loading…</div>';
    try {
      const result = await request(sections[section].endpoint);
      cache[section] = result.items || [];
      if (!cache[section].length) {
        list.innerHTML = `<div class="pc-empty">Nothing here yet.<br>Create your first ${escapeHTML(sections[section].singular)}.</div>`;
      } else {
        list.innerHTML = cache[section].map(item => card(item, section)).join("");
      }
      updateStats();
    } catch (err) {
      list.innerHTML = `<div class="pc-empty">${escapeHTML(err.message)}</div>`;
      notify(err.message, "error");
    }
  }

  function updateStats() {
    const tasks = cache.tasks || [];
    $("#stat-tasks").textContent = cache.tasks ? tasks.length : "—";
    $("#stat-open").textContent = cache.tasks ? tasks.filter(t => t.status !== "completed" && t.status !== "cancelled").length : "—";
    $("#stat-goals").textContent = cache.goals ? cache.goals.length : "—";
    $("#stat-notes").textContent = cache.notes ? cache.notes.length : "—";
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = $("#pc-submit");
    const title = field("title");
    if (!title) return notify("Please enter a title.", "error");

    const data = {title, description:field("description")};
    if (active === "notes") {
      data.content = data.description;
      delete data.description;
    }
    if (active === "tasks") {
      data.priority = field("priority") || "medium";
      data.due_at = field("due_at") ? new Date(field("due_at")).toISOString() : null;
    } else if (active === "goals") {
      data.target_date = field("target_date") || null;
    } else if (active === "notes") {
      data.category = field("category");
      data.tags = field("tags_text").split(",").map(t=>t.trim()).filter(Boolean).slice(0,30);
    } else if (active === "calendar") {
      if (!field("starts_at")) return notify("Please select an event start time.", "error");
      data.starts_at = new Date(field("starts_at")).toISOString();
      data.ends_at = field("ends_at") ? new Date(field("ends_at")).toISOString() : null;
      data.location = field("location");
      data.timezone_name = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } else if (active === "reminders") {
      if (!field("remind_at")) return notify("Please choose a reminder time.", "error");
      data.remind_at = new Date(field("remind_at")).toISOString();
    }

    button.disabled = true;
    try {
      await request(sections[active].endpoint, {method:"POST", body:JSON.stringify(data)});
      form.reset();
      notify(`${sections[active].singular[0].toUpperCase()+sections[active].singular.slice(1)} created successfully.`);
      await loadSection(active);
    } catch (err) {
      notify(err.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  list.addEventListener("click", async event => {
    const del = event.target.closest("[data-delete]");
    const complete = event.target.closest("[data-complete]");
    const progress = event.target.closest("[data-progress]");
    const edit = event.target.closest("[data-edit]");
    const pin = event.target.closest("[data-pin]");
    const archive = event.target.closest("[data-archive]");

    try {
      if (edit) {
        const item = (cache[active] || []).find(x => String(x.id) === edit.dataset.edit);
        if (!item) return notify("Item not found. Refresh and try again.", "error");

        const title = window.prompt("Title:", item.title || "");
        if (title === null) return;
        if (!title.trim()) return notify("Title cannot be empty.", "error");

        const description = window.prompt(
          active === "notes" ? "Note content:" : "Description:",
          active === "notes" ? (item.content || "") : (item.description || "")
        );
        if (description === null) return;

        const data = {title: title.trim()};
        if (active === "notes") {
          data.content = description;
        } else {
          data.description = description;
        }

        if (active === "tasks") {
          const priority = window.prompt("Priority: low, medium, high, urgent", item.priority || "medium");
          if (priority === null) return;
          if (!["low","medium","high","urgent"].includes(priority.trim().toLowerCase())) {
            return notify("Invalid priority.", "error");
          }
          data.priority = priority.trim().toLowerCase();
        } else if (active === "goals") {
          const target = window.prompt("Target date (YYYY-MM-DD), or leave blank:", item.target_date || "");
          if (target === null) return;
          data.target_date = target.trim() || null;
        } else if (active === "notes") {
          data.category = item.category || "";
          data.tags = Array.isArray(item.tags) ? item.tags : [];
        } else if (active === "calendar") {
          const location = window.prompt("Location:", item.location || "");
          if (location === null) return;
          data.location = location.trim();
        } else if (active === "reminders") {
          const remindAt = window.prompt("Reminder date/time (ISO format):", item.remind_at || "");
          if (remindAt === null) return;
          if (!remindAt.trim()) return notify("Reminder time is required.", "error");
          const parsed = new Date(remindAt);
          if (Number.isNaN(parsed.getTime())) return notify("Invalid reminder date/time.", "error");
          data.remind_at = parsed.toISOString();
        }

        await request(`${sections[active].endpoint}/${item.id}`, {
          method:"PATCH", body:JSON.stringify(data)
        });
        notify("Changes saved successfully.");
        await loadSection(active);
      } else if (pin) {
        const item = (cache.notes || []).find(x => String(x.id) === pin.dataset.pin);
        if (!item) return;
        await request(`${sections.notes.endpoint}/${item.id}`, {
          method:"PATCH",
          body:JSON.stringify({is_pinned: !item.is_pinned})
        });
        notify(item.is_pinned ? "Note unpinned." : "Note pinned.");
        await loadSection(active);
      } else if (archive) {
        const item = (cache.notes || []).find(x => String(x.id) === archive.dataset.archive);
        if (!item) return;
        const archived = !item.is_archived;
        await request(`${sections.notes.endpoint}/${item.id}`, {
          method:"PATCH",
          body:JSON.stringify({is_archived: archived})
        });
        notify(archived ? "Note archived." : "Note restored.");
        await loadSection(active);
      } else if (del) {
        if (!window.confirm("Delete this item? This cannot be undone.")) return;
        await request(`${sections[active].endpoint}/${del.dataset.delete}`, {method:"DELETE", headers:{"X-CSRFToken":csrf}});
        notify("Item deleted.");
        await loadSection(active);
      } else if (complete) {
        await request(`${sections.tasks.endpoint}/${complete.dataset.complete}`, {
          method:"PATCH", body:JSON.stringify({status:"completed"})
        });
        notify("Task marked completed.");
        await loadSection(active);
      } else if (progress) {
        const item = (cache.goals || []).find(g => String(g.id) === progress.dataset.progress);
        const current = Number(item?.progress_percent || 0);
        const input = window.prompt("Goal progress percentage (0–100):", String(Math.min(100,current+10)));
        if (input === null) return;
        const value = Number(input);
        if (!Number.isInteger(value) || value < 0 || value > 100) return notify("Enter a whole number from 0 to 100.", "error");
        await request(`${sections.goals.endpoint}/${progress.dataset.progress}`, {
          method:"PATCH", body:JSON.stringify({progress_percent:value})
        });
        notify("Goal progress updated.");
        await loadSection(active);
      }
    } catch (err) {
      notify(err.message, "error");
    }
  });

  document.querySelectorAll(".pc-tab").forEach(btn =>
    btn.addEventListener("click", () => showSection(btn.dataset.section))
  );
  $("#pc-refresh").addEventListener("click", () => loadSection(active));

  Promise.allSettled([
    request(sections.tasks.endpoint).then(r => cache.tasks = r.items || []),
    request(sections.goals.endpoint).then(r => cache.goals = r.items || []),
    request(sections.notes.endpoint).then(r => cache.notes = r.items || [])
  ]).then(updateStats);

  showSection("tasks");
})();
