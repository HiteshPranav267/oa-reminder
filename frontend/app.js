const IST_TZ = "Asia/Kolkata";
const API_KEY_STORAGE = "oa_api_key";

let assessments = [];
let editingId = null;

// ---------------------------------------------------------------------------
// API key handling
// ---------------------------------------------------------------------------

function getApiKey() {
  let key = localStorage.getItem(API_KEY_STORAGE);
  if (!key) {
    key = window.prompt("Enter your OA Reminder API key:") || "";
    if (key) localStorage.setItem(API_KEY_STORAGE, key);
  }
  return key;
}

function forgetApiKey() {
  localStorage.removeItem(API_KEY_STORAGE);
}

async function apiFetch(path, options = {}) {
  const needsAuth = options.method && options.method !== "GET";
  const headers = Object.assign({}, options.headers);
  if (needsAuth) {
    headers["X-API-Key"] = getApiKey();
  }
  if (options.body) headers["Content-Type"] = "application/json";

  let res = await fetch(path, Object.assign({}, options, { headers }));

  if (res.status === 401 && needsAuth) {
    forgetApiKey();
    headers["X-API-Key"] = getApiKey();
    res = await fetch(path, Object.assign({}, options, { headers }));
  }
  return res;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function istDateKey(date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: IST_TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(date);
}

function fmtTime(iso) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: IST_TZ, hour: "numeric", minute: "2-digit", hour12: true,
  }).format(new Date(iso));
}

function fmtDate(iso) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: IST_TZ, month: "short", day: "numeric",
  }).format(new Date(iso));
}

function fmtCountdown(targetIso) {
  const diffMs = new Date(targetIso).getTime() - Date.now();
  const overdue = diffMs < 0;
  const abs = Math.abs(diffMs);

  const minutes = Math.floor(abs / 60000) % 60;
  const hours = Math.floor(abs / 3600000) % 24;
  const days = Math.floor(abs / 86400000);

  let text;
  if (days > 0) {
    text = `${days} day${days === 1 ? "" : "s"}${hours > 0 ? ` ${hours}h` : ""}`;
  } else if (hours > 0) {
    text = `${hours}h ${minutes}m`;
  } else {
    text = `${minutes}m`;
  }

  return overdue ? `${text} overdue` : `${text} remaining`;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function bucketize(rows) {
  const now = new Date();
  const todayKey = istDateKey(now);

  const today = [], upcoming = [], past = [];

  for (const a of rows) {
    const t = new Date(a.assessment_time);
    if (a.completed) {
      past.push(a);
    } else if (t < now) {
      past.push(a);
    } else if (istDateKey(t) === todayKey) {
      today.push(a);
    } else {
      upcoming.push(a);
    }
  }

  today.sort((a, b) => new Date(a.assessment_time) - new Date(b.assessment_time));
  upcoming.sort((a, b) => new Date(a.assessment_time) - new Date(b.assessment_time));
  past.sort((a, b) => new Date(b.assessment_time) - new Date(a.assessment_time));

  return { today, upcoming, past };
}

function renderCard(a, { isPast = false } = {}) {
  const div = document.createElement("div");
  div.className = "card" + (a.completed ? " completed" : "") + (isPast && !a.completed ? " overdue" : "");

  const main = document.createElement("div");
  main.className = "card-main";

  const timeLine = document.createElement("div");
  timeLine.className = "card-time";
  timeLine.textContent = `${fmtDate(a.assessment_time)} · ${fmtTime(a.assessment_time)}`;
  main.appendChild(timeLine);

  const company = document.createElement("div");
  company.className = "card-company";
  company.textContent = a.company;
  if (a.completed) {
    const badge = document.createElement("span");
    badge.className = "badge badge-completed";
    badge.textContent = "Completed";
    company.appendChild(badge);
  } else if (isPast) {
    const badge = document.createElement("span");
    badge.className = "badge badge-missed";
    badge.textContent = "Missed";
    company.appendChild(badge);
  }
  main.appendChild(company);

  const title = document.createElement("div");
  title.className = "card-oa-title";
  title.textContent = a.title;
  main.appendChild(title);

  if (a.notes) {
    const notes = document.createElement("div");
    notes.className = "card-notes";
    notes.textContent = a.notes;
    main.appendChild(notes);
  }

  if (!a.completed) {
    const countdown = document.createElement("div");
    countdown.className = "card-countdown";
    countdown.dataset.target = a.assessment_time;
    const diffMs = new Date(a.assessment_time) - Date.now();
    if (diffMs < 0) countdown.classList.add("overdue-text");
    else if (diffMs < 2 * 3600000) countdown.classList.add("soon");
    countdown.textContent = fmtCountdown(a.assessment_time);
    main.appendChild(countdown);
  }

  if (a.link) {
    const link = document.createElement("a");
    link.className = "card-link";
    link.href = a.link;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open OA link →";
    main.appendChild(link);
  }

  const actions = document.createElement("div");
  actions.className = "card-actions";

  if (!a.completed) {
    const completeBtn = document.createElement("button");
    completeBtn.className = "btn btn-small";
    completeBtn.textContent = "Complete";
    completeBtn.onclick = () => completeAssessment(a.id);
    actions.appendChild(completeBtn);

    const editBtn = document.createElement("button");
    editBtn.className = "btn btn-small";
    editBtn.textContent = "Edit";
    editBtn.onclick = () => openEditModal(a);
    actions.appendChild(editBtn);
  }

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "btn btn-small btn-danger";
  deleteBtn.textContent = "Delete";
  deleteBtn.onclick = () => deleteAssessment(a.id);
  actions.appendChild(deleteBtn);

  div.appendChild(main);
  div.appendChild(actions);
  return div;
}

function renderGroup(listEl, emptyEl, rows, opts) {
  listEl.innerHTML = "";
  if (rows.length === 0) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;
  for (const a of rows) {
    listEl.appendChild(renderCard(a, opts));
  }
}

function render() {
  const { today, upcoming, past } = bucketize(assessments);
  renderGroup(document.getElementById("list-today"), document.getElementById("empty-today"), today);
  renderGroup(document.getElementById("list-upcoming"), document.getElementById("empty-upcoming"), upcoming);
  renderGroup(document.getElementById("list-past"), document.getElementById("empty-past"), past, { isPast: true });
}

function refreshCountdowns() {
  document.querySelectorAll(".card-countdown").forEach((el) => {
    const target = el.dataset.target;
    el.textContent = fmtCountdown(target);
    const diffMs = new Date(target) - Date.now();
    el.classList.toggle("overdue-text", diffMs < 0);
    el.classList.toggle("soon", diffMs >= 0 && diffMs < 2 * 3600000);
  });
}

// ---------------------------------------------------------------------------
// Data loading + mutations
// ---------------------------------------------------------------------------

async function loadAssessments() {
  const res = await fetch("/api/assessments");
  assessments = await res.json();
  render();
}

async function completeAssessment(id) {
  const res = await apiFetch(`/api/assessments/${id}/complete`, { method: "POST" });
  if (res.ok) await loadAssessments();
  else alert("Failed to mark complete.");
}

async function deleteAssessment(id) {
  if (!window.confirm("Delete this OA? This can't be undone.")) return;
  const res = await apiFetch(`/api/assessments/${id}`, { method: "DELETE" });
  if (res.status === 204) await loadAssessments();
  else alert("Failed to delete.");
}

// ---------------------------------------------------------------------------
// Modal (add/edit)
// ---------------------------------------------------------------------------

const backdrop = document.getElementById("modal-backdrop");
const form = document.getElementById("oa-form");
const formError = document.getElementById("form-error");

function openAddModal() {
  editingId = null;
  document.getElementById("modal-title").textContent = "Add OA";
  form.reset();
  document.getElementById("f-remind-24h").checked = true;
  document.getElementById("f-remind-6h").checked = true;
  document.getElementById("f-remind-2h").checked = true;
  formError.hidden = true;
  backdrop.hidden = false;
  document.getElementById("f-company").focus();
}

function openEditModal(a) {
  editingId = a.id;
  document.getElementById("modal-title").textContent = "Edit OA";
  document.getElementById("f-company").value = a.company;
  document.getElementById("f-title").value = a.title;

  const localDate = new Intl.DateTimeFormat("en-CA", { timeZone: IST_TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(a.assessment_time));
  const localTime = new Intl.DateTimeFormat("en-GB", { timeZone: IST_TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(a.assessment_time));
  document.getElementById("f-date").value = localDate;
  document.getElementById("f-time").value = localTime;

  document.getElementById("f-link").value = a.link || "";
  document.getElementById("f-notes").value = a.notes || "";
  document.getElementById("f-remind-24h").checked = a.remind_24h;
  document.getElementById("f-remind-6h").checked = a.remind_6h;
  document.getElementById("f-remind-2h").checked = a.remind_2h;
  formError.hidden = true;
  backdrop.hidden = false;
  document.getElementById("f-company").focus();
}

function closeModal() {
  backdrop.hidden = true;
}

document.getElementById("add-btn").onclick = openAddModal;
document.getElementById("cancel-btn").onclick = closeModal;
backdrop.addEventListener("click", (e) => {
  if (e.target === backdrop) closeModal();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.hidden = true;

  const date = document.getElementById("f-date").value;
  const time = document.getElementById("f-time").value;
  // Build an explicit +05:30 (Asia/Kolkata) offset ISO string rather than
  // relying on the browser's own local timezone, so this works correctly
  // even if the dashboard is ever opened from outside India.
  const assessmentTime = `${date}T${time}:00+05:30`;

  const payload = {
    company: document.getElementById("f-company").value.trim(),
    title: document.getElementById("f-title").value.trim(),
    assessment_time: assessmentTime,
    link: document.getElementById("f-link").value.trim() || null,
    notes: document.getElementById("f-notes").value.trim() || null,
    remind_24h: document.getElementById("f-remind-24h").checked,
    remind_6h: document.getElementById("f-remind-6h").checked,
    remind_2h: document.getElementById("f-remind-2h").checked,
  };

  const url = editingId ? `/api/assessments/${editingId}` : "/api/assessments";
  const method = editingId ? "PUT" : "POST";

  const res = await apiFetch(url, { method, body: JSON.stringify(payload) });

  if (res.ok) {
    closeModal();
    await loadAssessments();
  } else {
    const data = await res.json().catch(() => ({}));
    formError.textContent = data.detail ? JSON.stringify(data.detail) : `Save failed (${res.status})`;
    formError.hidden = false;
  }
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

loadAssessments();
setInterval(refreshCountdowns, 30000);
setInterval(loadAssessments, 60000);
