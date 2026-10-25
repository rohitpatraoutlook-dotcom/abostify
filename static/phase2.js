(function () {
  "use strict";

  const API = "/api/v2";

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;

    const input = document.querySelector(
      'input[name="csrf_token"]'
    );
    return input ? input.value : "";
  }

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const method = (options.method || "GET").toUpperCase();

    if (method !== "GET" && method !== "HEAD") {
      const token = csrfToken();
      if (token) headers.set("X-CSRFToken", token);
    }

    if (
      options.body &&
      !(options.body instanceof FormData) &&
      typeof options.body === "object"
    ) {
      headers.set("Content-Type", "application/json");
      options.body = JSON.stringify(options.body);
    }

    const response = await fetch(API + path, {
      ...options,
      method,
      headers,
      credentials: "same-origin"
    });

    const type = response.headers.get("content-type") || "";
    const data = type.includes("application/json")
      ? await response.json()
      : { error: await response.text() };

    if (!response.ok) {
      throw new Error(data.error || "Request failed: " + response.status);
    }

    return data;
  }

  const companyPath = id => {
    const value = Number(id);
    if (!Number.isInteger(value) || value < 1) {
      throw new Error("Valid company ID required");
    }
    return "/companies/" + value;
  };

  window.ABOSTIFY = window.ABOSTIFY || {};
  window.ABOSTIFY.request = request;

  window.ABOSTIFY.attendance = {
    checkIn: id =>
      request(companyPath(id) + "/attendance/check-in", {
        method: "POST"
      }),

    checkOut: id =>
      request(companyPath(id) + "/attendance/check-out", {
        method: "POST"
      }),

    list: (id, filters = {}) => {
      const query = new URLSearchParams(filters).toString();
      return request(
        companyPath(id) + "/attendance" + (query ? "?" + query : "")
      );
    }
  };

  window.ABOSTIFY.leaves = {
    list: (id, status) => {
      const query = status
        ? "?status=" + encodeURIComponent(status)
        : "";
      return request(companyPath(id) + "/leaves" + query);
    },

    apply: (id, data) =>
      request(companyPath(id) + "/leaves", {
        method: "POST",
        body: data
      }),

    review: (id, leaveId, status) =>
      request(
        companyPath(id) + "/leaves/" + Number(leaveId) + "/review",
        { method: "POST", body: { status } }
      ),

    cancel: (id, leaveId) =>
      request(
        companyPath(id) + "/leaves/" + Number(leaveId) + "/cancel",
        { method: "POST" }
      )
  };

  window.ABOSTIFY.documents = {
    list: id => request(companyPath(id) + "/documents"),

    upload: (id, file) => {
      const form = new FormData();
      form.append("file", file);

      return request(companyPath(id) + "/documents", {
        method: "POST",
        body: form
      });
    },

    downloadUrl: (id, documentId) =>
      API + companyPath(id) + "/documents/" +
      Number(documentId) + "/download",

    delete: (id, documentId) =>
      request(
        companyPath(id) + "/documents/" + Number(documentId),
        { method: "DELETE" }
      )
  };

  window.ABOSTIFY.notifications = {
    list: unreadOnly =>
      request("/notifications" +
        (unreadOnly ? "?unread=true" : "")),

    markRead: id =>
      request("/notifications/" + Number(id) + "/read", {
        method: "POST"
      }),

    markAllRead: () =>
      request("/notifications/read-all", { method: "POST" })
  };

})();

/* Phase 2 company workspace UI */
(function () {
  "use strict";

  const root = document.getElementById("phase2-workspace");
  if (!root || !window.ABOSTIFY) return;

  const companyId = Number(root.dataset.companyId);
  const canReviewLeaves = ["owner", "admin", "hr"].includes(root.dataset.role);
  const api = window.ABOSTIFY;
  const byId = id => document.getElementById(id);
  const messageBox = byId("p2-message");

  function showMessage(message, isError = false) {
    messageBox.textContent = message;
    messageBox.hidden = !message;
    messageBox.classList.toggle("error", isError);
    messageBox.classList.toggle("success", !isError);
  }

  function escapeHTML(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  function localTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? escapeHTML(value) : escapeHTML(d.toLocaleString());
  }

  function bytes(value) {
    const n = Number(value || 0);
    return n < 1024 ? n + " B" :
      n < 1048576 ? (n / 1024).toFixed(1) + " KB" :
      (n / 1048576).toFixed(2) + " MB";
  }

  async function action(fn, successMessage) {
    try {
      await fn();
      if (successMessage) showMessage(successMessage);
    } catch (error) {
      showMessage(error.message || "Request failed.", true);
    }
  }

  async function loadSummary() {
    const data = await api.request(
      "/companies/" + companyId + "/summary"
    );
    byId("p2-total").textContent = data.total_employees;
    byId("p2-active").textContent = data.active_employees;
    byId("p2-suspended").textContent = data.suspended_employees;
  }

  async function loadAttendance() {
    const data = await api.attendance.list(companyId);
    const rows = data.attendance || [];
    byId("p2-attendance-list").innerHTML = rows.length ? rows.map(x =>
      "<tr><td>" + escapeHTML(x.date) + "</td><td>" +
      escapeHTML(x.username) + "</td><td>" + localTime(x.check_in) +
      "</td><td>" + localTime(x.check_out) + "</td><td>" +
      escapeHTML(x.status) + "</td></tr>"
    ).join("") : '<tr><td colspan="5">No attendance records found.</td></tr>';
  }

  async function loadLeaves() {
    const status = byId("p2-leave-filter").value;
    const data = await api.leaves.list(companyId, status);
    const rows = data.leaves || [];
    byId("p2-leave-list").innerHTML = rows.length ? rows.map(x => {
      let buttons = "";
      if (x.status === "pending") {
        buttons += '<button class="button button-secondary" data-leave-cancel="' +
          Number(x.id) + '" type="button">Cancel</button>';
        if (canReviewLeaves) {
          buttons += '<button class="button button-primary" data-leave-review="approved" data-leave-id="' +
            Number(x.id) + '" type="button">Approve</button>';
          buttons += '<button class="button button-secondary" data-leave-review="rejected" data-leave-id="' +
            Number(x.id) + '" type="button">Reject</button>';
        }
      }
      return '<article class="company-card"><strong>' +
        escapeHTML(x.leave_type) + '</strong> · ' + escapeHTML(x.status) +
        '<p>' + escapeHTML(x.start_date) + ' to ' + escapeHTML(x.end_date) + '</p>' +
        '<p>' + escapeHTML(x.reason) + '</p><p class="company-small">By ' +
        escapeHTML(x.username) + ' · ' + localTime(x.created_at) + '</p>' +
        '<div class="company-actions">' + buttons + '</div></article>';
    }).join("") : "<p>No leave requests found.</p>";
  }

  async function loadDocuments() {
    const data = await api.documents.list(companyId);
    const rows = data.documents || [];
    byId("p2-document-list").innerHTML = rows.length ? rows.map(x =>
      '<article class="company-card"><strong>' + escapeHTML(x.filename) +
      '</strong><p class="company-small">' + escapeHTML(x.uploaded_by) +
      ' · ' + bytes(x.size_bytes) + ' · ' + localTime(x.created_at) + '</p>' +
      '<div class="company-actions"><a class="button button-primary" href="' +
      api.documents.downloadUrl(companyId, x.id) + '">Download</a>' +
      '<button class="button button-secondary" type="button" data-doc-delete="' +
      Number(x.id) + '">Delete</button></div></article>'
    ).join("") : "<p>No documents uploaded yet.</p>";
  }

  async function loadNotifications() {
    const data = await api.notifications.list(false);
    const rows = data.notifications || [];
    byId("p2-unread-count").textContent = data.unread_count ?? 0;
    byId("p2-notification-list").innerHTML = rows.length ? rows.map(x =>
      '<article class="company-card"><strong>' + escapeHTML(x.title) +
      '</strong><p>' + escapeHTML(x.body) + '</p><p class="company-small">' +
      localTime(x.created_at) + ' · ' + (x.is_read ? "Read" : "Unread") +
      '</p>' + (x.is_read ? "" :
        '<button class="button button-secondary" type="button" data-notification-read="' +
        Number(x.id) + '">Mark read</button>') + '</article>'
    ).join("") : "<p>No notifications yet.</p>";
  }

  async function loadActivity() {
    const data = await api.request("/companies/" + companyId + "/activity");
    const rows = Array.isArray(data.activities) ? data.activities : [];

    byId("p2-activity-list").innerHTML = rows.length
      ? rows.map(item => {
          const details = item.details && typeof item.details === "object"
            ? JSON.stringify(item.details)
            : "";
          return '<article class="company-card"><strong>' +
            escapeHTML(item.action || "Activity") + '</strong><p>' +
            escapeHTML(item.object_type || "company") +
            (item.object_id ? " #" + Number(item.object_id) : "") +
            '</p><p class="company-small">By ' +
            escapeHTML(item.actor || "System") + ' · ' +
            localTime(item.created_at) + '</p>' +
            (details && details !== "{}"
              ? '<p>' + escapeHTML(details) + '</p>' : '') +
            '</article>';
        }).join("")
      : "<p>No activity recorded yet.</p>";
  }

  byId("p2-check-in").addEventListener("click", () =>
    action(async () => {
      await api.attendance.checkIn(companyId);
      await loadAttendance();
    }, "Check-in recorded."));

  byId("p2-check-out").addEventListener("click", () =>
    action(async () => {
      await api.attendance.checkOut(companyId);
      await loadAttendance();
    }, "Check-out recorded."));

  byId("p2-refresh-summary").addEventListener("click", () =>
    action(loadSummary, "Summary refreshed."));
  byId("p2-refresh-attendance").addEventListener("click", () =>
    action(loadAttendance, "Attendance refreshed."));
  byId("p2-refresh-leaves").addEventListener("click", () =>
    action(loadLeaves, "Leave requests refreshed."));
  byId("p2-leave-filter").addEventListener("change", () =>
    action(loadLeaves));
  byId("p2-refresh-documents").addEventListener("click", () =>
    action(loadDocuments, "Documents refreshed."));
  byId("p2-refresh-notifications").addEventListener("click", () =>
    action(loadNotifications, "Notifications refreshed."));
  byId("p2-refresh-activity").addEventListener("click", () =>
    action(loadActivity, "Activity refreshed."));

  byId("p2-leave-form").addEventListener("submit", event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    action(async () => {
      await api.leaves.apply(companyId, data);
      form.reset();
      await loadLeaves();
    }, "Leave request submitted.");
  });

  byId("p2-document-form").addEventListener("submit", event => {
    event.preventDefault();
    const form = event.currentTarget;
    const file = form.elements.file.files[0];
    if (!file) return showMessage("Choose a file first.", true);
    if (file.size > 5 * 1024 * 1024)
      return showMessage("Maximum file size is 5 MB.", true);
    action(async () => {
      await api.documents.upload(companyId, file);
      form.reset();
      await loadDocuments();
    }, "Document uploaded.");
  });

  root.addEventListener("click", event => {
    const cancel = event.target.closest("[data-leave-cancel]");
    const review = event.target.closest("[data-leave-review]");
    const remove = event.target.closest("[data-doc-delete]");
    const read = event.target.closest("[data-notification-read]");

    if (cancel) action(async () => {
      await api.leaves.cancel(companyId, Number(cancel.dataset.leaveCancel));
      await loadLeaves();
    }, "Leave request cancelled.");

    if (review) action(async () => {
      await api.leaves.review(
        companyId, Number(review.dataset.leaveId), review.dataset.leaveReview
      );
      await loadLeaves();
    }, "Leave request reviewed.");

    if (remove && window.confirm("Delete this document?")) action(async () => {
      await api.documents.delete(companyId, Number(remove.dataset.docDelete));
      await loadDocuments();
    }, "Document deleted.");

    if (read) action(async () => {
      await api.notifications.markRead(Number(read.dataset.notificationRead));
      await loadNotifications();
    }, "Notification marked read.");
  });

  byId("p2-read-all").addEventListener("click", () =>
    action(async () => {
      await api.notifications.markAllRead();
      await loadNotifications();
    }, "Notifications marked read."));

  // Load each module independently so one API error does not block the others.
  [
    loadSummary, loadAttendance, loadLeaves,
    loadDocuments, loadNotifications, loadActivity
  ].forEach(fn => action(fn));
})();
