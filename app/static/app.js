"use strict";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const escapeHTML = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const sample = [
  {
    sop_id: "sample-latte",
    version: 1,
    content: {
      title: "Signature iced latte",
      category: "drink",
      description:
        "Our everyday favourite. Smooth espresso, cold milk, and just the right amount of ice.",
      servings: 1,
      ingredients: [
        { name: "Espresso", quantity: 36, unit: "g" },
        { name: "Milk", quantity: 200, unit: "ml" },
        { name: "Ice", quantity: 100, unit: "g" },
      ],
      steps: [
        "Extract a double espresso.",
        "Add cold milk and ice to the serving glass.",
        "Pour espresso over the milk and serve.",
      ],
      allergens: ["Milk"],
      safety_notes:
        "Sample only. Follow your approved milk storage procedures.",
    },
  },
  {
    sop_id: "sample-toast",
    version: 1,
    content: {
      title: "Avocado sourdough",
      category: "food",
      description:
        "Golden sourdough, freshly smashed avocado, and a little finishing touch.",
      servings: 1,
      ingredients: [
        { name: "Sourdough", quantity: 1, unit: "slice" },
        { name: "Avocado", quantity: 100, unit: "g" },
      ],
      steps: [
        "Toast sourdough until golden.",
        "Mash avocado and spread over toast.",
        "Season and serve immediately.",
      ],
      allergens: ["Wheat"],
      safety_notes: "Sample only. Use clean preparation surfaces.",
    },
  },
  {
    sop_id: "sample-matcha",
    version: 1,
    content: {
      title: "Ceremonial matcha",
      category: "drink",
      description:
        "A mindful pour. Bright, earthy matcha with a silky, delicate finish.",
      servings: 1,
      ingredients: [
        { name: "Matcha", quantity: 3, unit: "g" },
        { name: "Water", quantity: 60, unit: "ml" },
        { name: "Milk", quantity: 180, unit: "ml" },
      ],
      steps: [
        "Sift matcha into a clean bowl.",
        "Whisk with warm water until smooth.",
        "Pour over milk and serve.",
      ],
      allergens: ["Milk"],
      safety_notes: "Sample only. Follow your approved handling procedures.",
    },
  },
];
let token = sessionStorage.getItem("mysop-token"),
  user = null,
  teams = [],
  team = null,
  items = [],
  view = "published",
  category = "all",
  editing = null,
  registerMode = false,
  socket = null,
  reconnect = null,
  liveGeneration = 0;
let toastTimer;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401 && user) {
      endSession();
      toast("Your session expired. Please sign in again.");
    }
    throw new Error(
      Array.isArray(data.detail)
        ? data.detail
            .map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`)
            .join("\n")
        : data.detail || "Something went wrong.",
    );
  }
  return data;
}
function errorIn(form, error) {
  form.querySelector(".form-error").textContent = error.message;
}
async function submit(form, fn) {
  form.querySelector(".form-error").textContent = "";
  const buttons = [...form.querySelectorAll("button")];
  buttons.forEach((b) => (b.disabled = true));
  try {
    await fn();
  } catch (error) {
    errorIn(form, error);
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}
function art(content) {
  if (content.photo_data_url) return `<img class="recipe-photo" src="${escapeHTML(content.photo_data_url)}" alt="${escapeHTML(content.title)}">`;
  if (content.category === "food")
    return '<svg viewBox="0 0 200 160" aria-hidden="true"><ellipse cx="100" cy="91" rx="83" ry="56" fill="#faf8ef"/><ellipse cx="100" cy="91" rx="65" ry="41" fill="#d9dac7"/><path d="M48 61 Q80 29 143 54 L159 115 Q114 144 54 116Z" fill="#a56e3e"/><path d="M54 63 Q85 37 139 59 L151 110 Q111 132 61 111Z" fill="#dbb980"/><path d="M66 68 Q99 49 130 63 L140 103 Q105 121 71 103Z" fill="#8ea55d"/><path d="M78 73 L130 96 M75 84 L123 105 M87 65 L137 87" stroke="#b3c879" stroke-width="10" stroke-linecap="round"/><g fill="#f1e1bd"><circle cx="95" cy="78" r="2"/><circle cx="112" cy="91" r="2"/><circle cx="88" cy="98" r="2"/></g></svg>';
  const matcha = content.title.toLowerCase().includes("matcha");
  return `<svg viewBox="0 0 200 160" aria-hidden="true"><ellipse cx="103" cy="143" rx="44" ry="7" fill="#58694715"/><path d="M61 29 L142 29 L133 135 Q101 146 70 135Z" fill="#fff" opacity=".65"/><path d="M66 55 L137 55 L129 130 Q101 140 75 130Z" fill="${matcha ? "#a9bb83" : "#c3a584"}"/><path d="M68 65 L135 65 L133 83 Q98 73 70 89Z" fill="${matcha ? "#b7c894" : "#e7d7bd"}"/><path d="M70 89 Q104 78 133 90 L130 115 Q100 124 73 112Z" fill="${matcha ? "#c8d5ab" : "#e8d7be"}"/><ellipse cx="101" cy="55" rx="35" ry="7" fill="${matcha ? "#8da766" : "#9b7650"}"/><g fill="#fff" opacity=".44"><rect x="79" y="38" width="20" height="19" rx="4" transform="rotate(12 89 47)"/><rect x="108" y="44" width="19" height="18" rx="3" transform="rotate(-12 117 53)"/></g><path d="M117 48 L140 5" stroke="${matcha ? "#799261" : "#8d7055"}" stroke-width="5" stroke-linecap="round"/><path d="M75 38 L81 129" stroke="#fff" opacity=".45" stroke-width="3"/></svg>`;
}
let detailRow = null,
  detailKind = "published",
  wizardStep = 0,
  prepIndex = 0,
  prepRow = null;
const statusText = (status) =>
  ({
    pending: "Awaiting owner review",
    approved: "Approved",
    changes_requested: "Changes requested",
    draft: "Private draft",
  })[status] || status;
const canAuthor = () => !user || ["owner", "supervisor"].includes(team?.role);
function updateRoleUI() {
  $("#approvals-nav").hidden = team?.role !== "owner";
  $('[data-view="drafts"]').hidden = !!user && !canAuthor();
  $("#new-sop").hidden = !!user && !canAuthor();
  $("#invite-section").hidden = team?.role !== "owner";
  $("#profile-status").textContent = user
    ? `${team?.role || "No team"} · ${team?.name || "Create or join"}`
    : "Explore the foundation";
  if (
    (view === "approvals" && team?.role !== "owner") ||
    (view === "drafts" && !canAuthor())
  )
    view = "published";
  $$("[data-view]").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === view),
  );
}
function render() {
  updateRoleUI();
  const shown = items.filter(
    (r) =>
      (category === "all" || r.content.category === category) &&
      `${r.content.title} ${r.content.description}`
        .toLowerCase()
        .includes($("#search").value.toLowerCase()),
  );
  $("#cards").innerHTML = shown
    .map((r) => {
      const c = r.content,
        key = view === "published" ? r.sop_id : r.id;
      const state =
        view === "drafts"
          ? statusText(r.status)
          : view === "approvals"
            ? "Awaiting approval"
            : user
              ? r.acknowledged_at
                ? "Acknowledged"
                : "Update to read"
              : "Sample SOP";
      return `<button class="card" data-id="${escapeHTML(key)}"><div class="card-art ${c.category} ${c.title.toLowerCase().includes("matcha") ? "tea" : ""}"><span class="category-label">${c.category === "food" ? "♨ Food" : "♧ Drink"}</span>${art(c)}<span class="art-decoration">✳</span></div><div class="card-body"><div class="card-top"><h3>${escapeHTML(c.title)}</h3><span>→</span></div><p>${escapeHTML(c.description || "A shared standard, ready for your kitchen.")}</p><div class="card-meta"><span>≡ ${c.steps.length} steps</span><span>${c.ingredients.length} ingredients · ${c.servings} servings</span></div><div class="card-bottom"><span>${view === "published" ? `Version ${r.version}` : `Revision ${r.revision}`}</span><span class="status-label ${view === "drafts" ? r.status : !r.acknowledged_at && user ? "unread" : ""}">${state}</span></div></div></button>`;
    })
    .join("");
  $("#empty").hidden = shown.length > 0;
  $("#list-count").textContent = shown.length;
  $("#stat-total").textContent = String(items.length).padStart(2, "0");
  $("#stat-food").textContent = String(
    items.filter((r) => r.content.category === "food").length,
  ).padStart(2, "0");
  $("#stat-drink").textContent = String(
    items.filter((r) => r.content.category === "drink").length,
  ).padStart(2, "0");
  $("#nav-count").textContent = items.length;
  $("#page-title").innerHTML =
    view === "drafts"
      ? "Good things in the making<span>.</span>"
      : view === "approvals"
        ? "One final check<span>.</span>"
        : "Your kitchen playbook<span>.</span>";
  $("#list-title").firstChild.textContent =
    view === "drafts"
      ? "My drafts & submissions "
      : view === "approvals"
        ? "Owner approval queue "
        : "The SOP library ";
  $(".breadcrumb strong").textContent =
    view === "drafts"
      ? "My drafts"
      : view === "approvals"
        ? "Approvals"
        : "SOP library";
  $(".stats small").textContent =
    view === "drafts"
      ? "Your drafts"
      : view === "approvals"
        ? "Pending approvals"
        : "Published SOPs";
  $$(".card").forEach(
    (el) =>
      (el.onclick = () => {
        const row = items.find(
          (r) => (view === "published" ? r.sop_id : r.id) === el.dataset.id,
        );
        if (view === "drafts" && row.status !== "pending") openEditor(row);
        else
          showDetail(
            row,
            view === "approvals"
              ? "review"
              : view === "drafts"
                ? "draft"
                : "published",
          );
      }),
  );
}
async function load() {
  updateRoleUI();
  if (!user) {
    items = view === "published" ? sample : [];
    render();
    return;
  }
  if (!team) {
    items = [];
    render();
    return;
  }
  const selected = team.id,
    selectedView = view;
  const result = await api(
    `/teams/${selected}/${view === "drafts" ? "drafts" : view === "approvals" ? "submissions" : "sops"}`,
  );
  if (team?.id === selected && view === selectedView) {
    items = result;
    render();
  }
}
async function showDetail(row, kind = "published") {
  detailRow = row;
  detailKind = kind;
  const c = row.content,
    isPublished = kind === "published";
  $("#version-warning").hidden = true;
  $("#detail-dialog").classList.toggle("sop-reader", isPublished);
  $("#detail-page-nav").hidden = !isPublished;
  $("#detail-content").innerHTML =
    `<div class="modal-heading"><div><p class="eyebrow">${kind === "review" ? "OWNER REVIEW" : "KITCHEN SOP"}</p><h2 id="detail-title">${escapeHTML(c.title)}</h2><p class="reader-meta">${isPublished ? `Version ${row.version}` : `Revision ${row.revision}`} · ${c.servings} serving${c.servings === 1 ? "" : "s"}</p></div><button class="close" data-detail-close aria-label="Close">×</button></div>${isPublished ? '<div id="sop-page" aria-live="polite"></div>' : reviewSOP(c)}${user && team?.role === "owner" ? '<button class="button owner-bom" id="open-bom">Bill of Materials</button>' : ""}`;
  if ($("#open-bom")) $("#open-bom").onclick = () => openBill(row, kind);
  $("[data-detail-close]").onclick = () => $("#detail-dialog").close();
  $("#detail-actions").innerHTML = "";
  if (kind === "review") {
    $("#detail-actions").innerHTML =
      `<form id="review-form" class="review-actions"><p class="muted">Approval publishes this exact submitted version to the whole team.</p><label>Review notes<textarea name="note" maxlength="2000" placeholder="Required when requesting changes"></textarea></label><p class="form-error" role="alert"></p><button class="button primary" type="submit" name="action" value="approve">Approve & publish</button><button class="button" type="submit" name="action" value="return">Request changes</button></form>`;
    $("#review-form").onsubmit = (e) => {
      e.preventDefault();
      const action = e.submitter.value;
      submit(e.target, async () => {
        const note = e.target.elements.note.value.trim();
        if (action === "return" && !note)
          throw Error(
            "Explain the changes required before returning the draft.",
          );
        await api(
          `/teams/${team.id}/submissions/${row.id}/${action}`,
          "POST",
          action === "return" ? { note } : undefined,
        );
        $("#detail-dialog").close();
        await load();
        toast(
          action === "approve"
            ? "Approved and published to the team."
            : "Returned to the supervisor with your notes.",
        );
      });
    };
  } else if (kind === "draft") {
    $("#detail-actions").innerHTML =
      '<p class="notice">This submitted draft is locked while awaiting owner review.</p>';
  } else {
    $("#detail-actions").innerHTML =
      `<button id="start-prep" class="button primary full">Start preparation →</button>${user ? `<div class="ack-note">${row.acknowledged_at ? `You acknowledged version ${row.version}.` : `Version ${row.version} needs your acknowledgment. Confirm you have read the ingredients, method, allergens and safety notes.`}</div><button id="acknowledge" class="button full" ${row.acknowledged_at ? "disabled" : ""}>${row.acknowledged_at ? "Acknowledged" : "I have read this version"}</button>` : '<p class="muted">Sample recipe for exploring the interface. Sign in to use real team SOPs.</p>'}${user && ["owner", "supervisor"].includes(team?.role) ? '<button id="read-report" class="button">Team read status</button>' : ""}`;
    $("#start-prep").onclick = () => startPreparation(row);
    if (user)
      $("#acknowledge").onclick = async () => {
        const button = $("#acknowledge");
        button.disabled = true;
        try {
          await api(
            `/teams/${team.id}/sops/${row.sop_id}/versions/${row.version}/acknowledge`,
            "POST",
          );
          row.acknowledged_at = Date.now() / 1000;
          button.textContent = "Acknowledged";
          $(".ack-note").textContent =
            `You acknowledged version ${row.version}.`;
          await load();
          toast(`Acknowledged version ${row.version}.`);
        } catch (e) {
          button.disabled = false;
          toast(e.message);
        }
      };
    if ($("#read-report")) $("#read-report").onclick = () => {
      $("#report-dialog").showModal();
      refreshAcknowledgmentReport(row);
    };
  }
  if (!$("#detail-dialog").open) $("#detail-dialog").showModal();
  $("#detail-dialog").scrollTop = 0;
  if (isPublished) openReader(c);
}
function refreshAcknowledgmentReport(row) {
  const selected = team.id;
  api(`/teams/${selected}/sops/${row.sop_id}/acknowledgments`)
    .then((report) => {
      if (detailRow !== row || team?.id !== selected || !$("#ack-report"))
        return;
      $("#ack-report").innerHTML =
        `<h3 class="report-heading">Team acknowledgments · v${report.version}</h3><ul class="report-list">${report.members.map((m) => `<li><span>${escapeHTML(m.email)} <small>(${escapeHTML(m.role)})</small></span><strong>${m.acknowledged_at ? "Read" : "Awaiting"}</strong></li>`).join("")}</ul>`;
    })
    .catch((e) => toast(e.message));
}
function startPreparation(row) {
  prepRow = row;
  prepIndex = 0;
  $("#prep-warning").hidden = true;
  $("#prep-title").textContent = row.content.title;
  $("#prep-version").textContent =
    `Version ${row.version} · ${row.content.servings} servings · Allergens: ${row.content.allergens.join(", ") || "Verify before serving"}`;
  renderPreparation();
  $("#prep-dialog").showModal();
}
function renderPreparation() {
  const length = prepRow.content.steps.length;
  $("#prep-progress").max = length;
  $("#prep-progress").value = prepIndex;
  $("#prep-position").textContent =
    prepIndex === length ? "COMPLETE" : `STEP ${prepIndex + 1} OF ${length}`;
  $("#prep-step").textContent =
    prepIndex === length
      ? "Preparation complete. Follow your approved serving and storage procedures."
      : prepRow.content.steps[prepIndex];
  $("#prep-back").disabled = prepIndex === 0;
  $("#prep-next").disabled = false;
  $("#prep-next").textContent =
    prepIndex === length
      ? "Close preparation"
      : prepIndex === length - 1
        ? "Finish preparation"
        : "Next step →";
}
$("#prep-back").onclick = () => {
  if (prepIndex > 0) {
    prepIndex--;
    renderPreparation();
  }
};
$("#prep-next").onclick = () => {
  if (prepIndex === prepRow.content.steps.length) $("#prep-dialog").close();
  else {
    prepIndex++;
    renderPreparation();
  }
};
function openAuth() {
  $("#auth-dialog").showModal();
}
function stopLive() {
  liveGeneration++;
  clearTimeout(reconnect);
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
}
function startLive() {
  stopLive();
  if (!team || !token) return;
  const generation = liveGeneration,
    selected = team.id;
  let after = Number(
    sessionStorage.getItem(`mysop-cursor-${user.id}-${selected}`) || 0,
  );
  function connect() {
    if (generation !== liveGeneration) return;
    let eventWork = Promise.resolve();
    $("#connection").textContent = "● Connecting…";
    const ws = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/teams/${selected}/live?after=${after}`,
    );
    socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ token }));
    ws.onmessage = ({ data }) => {
      eventWork = eventWork
        .then(async () => {
          if (generation !== liveGeneration) return;
          const event = JSON.parse(data);
          if (event.type === "ready") {
            $("#connection").textContent = "● Live updates on";
            await load();
          }
          if (event.id) {
            if (
              event.type === "team.role_changed" &&
              event.user_id === user.id
            ) {
              teams = await api("/teams");
              team = teams.find((t) => t.id === selected) || null;
              updateRoleUI();
              if (!canAuthor() && $("#editor-dialog").open)
                $("#editor-dialog").close();
            }
            await load();
            if (generation !== liveGeneration) return;
            after = event.id;
            sessionStorage.setItem(
              `mysop-cursor-${user.id}-${selected}`,
              String(after),
            );
            if (
              event.type === "sop.acknowledged" &&
              $("#detail-dialog").open &&
              detailKind === "published" &&
              detailRow?.sop_id === event.sop_id &&
              $("#ack-report")
            )
              refreshAcknowledgmentReport(detailRow);
            if (event.type === "sop.published") {
              toast("Your team library has a fresh update.");
              if (
                $("#detail-dialog").open &&
                detailKind === "published" &&
                detailRow?.sop_id === event.sop_id &&
                event.version > detailRow.version
              ) {
                $("#version-warning").hidden = false;
                $("#version-warning").innerHTML =
                  'A newer version is available. <button id="open-latest" class="button">Read the latest version</button>';
                if ($("#acknowledge")) $("#acknowledge").disabled = true;
                if ($("#start-prep")) $("#start-prep").disabled = true;
                $("#open-latest").onclick = async () => {
                  try {
                    const recipes = await api(`/teams/${selected}/sops`);
                    const latest = recipes.find(
                      (r) => r.sop_id === event.sop_id,
                    );
                    if (latest) showDetail(latest);
                  } catch (e) {
                    toast(e.message);
                  }
                };
              }
              if (
                $("#prep-dialog").open &&
                prepRow?.sop_id === event.sop_id &&
                event.version > prepRow.version
              ) {
                $("#prep-warning").hidden = false;
                $("#prep-next").disabled = true;
                $("#prep-back").disabled = true;
              }
            }
          }
        })
        .catch((e) => {
          toast(e.message);
          ws.close();
        });
    };
    ws.onclose = (event) => {
      if (generation !== liveGeneration) return;
      if (event.code === 4401) {
        endSession();
        toast("Please sign in again.");
        return;
      }
      if (event.code === 4403) {
        $("#connection").textContent = "● Team access unavailable";
        return;
      }
      $("#connection").textContent = "● Reconnecting…";
      reconnect = setTimeout(connect, 2000);
    };
  }
  connect();
}
async function refreshTeams(preferred) {
  teams = await api("/teams");
  team = teams.find((t) => t.id === preferred) || teams[0] || null;
  $("#teams").innerHTML = teams.length
    ? teams
        .map((t) => `<option value="${t.id}">${escapeHTML(t.name)}</option>`)
        .join("")
    : '<option value="">Create or join a team</option>';
  if (team) $("#teams").value = team.id;
  updateRoleUI();
  await load();
  startLive();
}
async function signedIn() {
  user = await api("/auth/me");
  $("#preview-banner").hidden = true;
  $("#auth-button").hidden = true;
  $("#logout").hidden = false;
  $("#profile-name").textContent = user.email;
  updateRoleUI();
  await refreshTeams();
  if (!team) $("#team-dialog").showModal();
}
function endSession() {
  stopLive();
  token = null;
  detailRow = null;
  prepRow = null;
  editing = null;
  $("#detail-content").innerHTML = "";
  $("#detail-actions").innerHTML = "";
  $("#editor-form").reset();
  $("#ingredients").innerHTML = "";
  clearKitchenPrivateState();
  user = null;
  team = null;
  teams = [];
  sessionStorage.removeItem("mysop-token");
  $("#preview-banner").hidden = false;
  $("#auth-button").hidden = false;
  $("#logout").hidden = true;
  $("#profile-name").textContent = "Your kitchen, connected";
  $("#profile-status").textContent = "Explore the foundation";
  $("#teams").innerHTML = '<option value="">Preview kitchen</option>';
  $("#connection").textContent = "● Sample preview";
  $("#invite-token").value = "";
  $("#invite-result").hidden = true;
  $$("dialog[open]").forEach((d) => d.close());
  view = "published";
  $$("[data-view]").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === view),
  );
  load();
}
function ingredientRow(
  i = {
    name: "",
    quantity: "",
    unit: "",
    pack_quantity: null,
    pack_cost: null,
  },
) {
  const row = document.createElement("div");
  row.className = "ingredient-row";
  row.innerHTML = `<label class="ingredient-name">Ingredient name<input data-field="name" aria-label="Ingredient name" maxlength="160" required value="${escapeHTML(i.name)}"></label><label>Recipe quantity<input data-field="quantity" aria-label="Quantity" type="number" min="0.0001" max="9999999999" step="any" required value="${escapeHTML(i.quantity)}"></label><label>Unit<input data-field="unit" aria-label="Unit" maxlength="40" required value="${escapeHTML(i.unit)}" placeholder="g / ml / each"></label><label class="ingredient-note">Staff measure (optional)<input data-field="measure_note" aria-label="Staff measure" maxlength="160" value="${escapeHTML(i.measure_note || "")}" placeholder="e.g. Fill cup to Line A"></label><button type="button" class="remove-ingredient" aria-label="Remove ingredient">Remove ingredient ×</button>`;
  row.querySelector("button").onclick = () => row.remove();
  $("#ingredients").append(row);
}
function editorContent() {
  const form = $("#editor-form");
  return {
    title: form.elements.title.value,
    category: form.elements.category.value,
    description: form.elements.description.value,
    servings: Number(form.elements.servings.value),
    photo_data_url: photoData,
    ingredients: $$(".ingredient-row").map((row) =>
      Object.fromEntries(
        [...row.querySelectorAll("[data-field]")].map((input) => [
          input.dataset.field,
          ["quantity", "pack_quantity", "pack_cost"].includes(
            input.dataset.field,
          )
            ? input.value === ""
              ? null
              : input.value
            : input.value,
        ]),
      ),
    ),
    steps: form.elements.steps.value
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
    allergens: form.elements.allergens.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    safety_notes: form.elements.safety_notes.value,
  };
}
function validatePanel(index) {
  const panel = $(`[data-panel="${index}"]`);
  for (const input of panel.querySelectorAll("input,textarea,select"))
    if (!input.reportValidity()) return false;
  if (index === 1) {
    const content = editorContent();
    if (!content.ingredients.length) {
      $("#editor-form .form-error").textContent =
        "Add at least one ingredient.";
      return false;
    }

  }
  if (index === 2 && !editorContent().steps.length) {
    $("#editor-form .form-error").textContent =
      "Add at least one preparation step.";
    return false;
  }
  return true;
}
function showWizard(index) {
  wizardStep = index;
  $$("[data-panel]").forEach(
    (p) => (p.hidden = Number(p.dataset.panel) !== index),
  );
  $$(".wizard-progress li").forEach((li, i) => {
    li.classList.toggle("current", i === index);
    li.classList.toggle("done", i < index);
    if (i === index) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  });
  $("#wizard-back").hidden = index === 0;
  $("#wizard-next").hidden = index === 3;
  $("#save-draft").hidden = index !== 3;
  $("#save-publish").hidden = index !== 3;
  $("#editor-form .form-error").textContent = "";
  $("#save-publish").textContent =
    team?.role === "owner" ? "Save & publish →" : "Submit for approval →";
  $("#publish-help").textContent =
    team?.role === "owner"
      ? "Publishing makes this version available to your whole team."
      : "Your owner will review the submitted version before it reaches the team. You can also save it as a private draft.";
  if (index === 3) {
    const c = editorContent();
    $("#editor-review").innerHTML =
      `<h3>${escapeHTML(c.title)}</h3><p>${c.category === "food" ? "Food" : "Drink"} · ${c.servings} servings · ${c.ingredients.length} ingredients · ${c.steps.length} preparation steps</p><p>${escapeHTML(c.description)}</p><ol class="detail-steps">${c.steps.map((s) => `<li>${escapeHTML(s)}</li>`).join("")}</ol><p>Allergens: ${escapeHTML(c.allergens.join(", ") || "Not specified — verify before serving.")}</p><p>Safety: ${escapeHTML(c.safety_notes || "No notes entered.")}</p>`;
  }
  $("#editor-dialog").scrollTop = 0;
  if ($("#editor-dialog").open) $(`[data-panel="${index}"] legend`).focus();
}
$("#wizard-next").onclick = () => {
  if (validatePanel(wizardStep)) showWizard(wizardStep + 1);
};
$("#wizard-back").onclick = () => showWizard(wizardStep - 1);
function openEditor(item = null) {
  if (!user) {
    openAuth();
    return;
  }
  if (!team) {
    $("#team-dialog").showModal();
    return;
  }
  if (!canAuthor()) {
    toast(
      "Staff can prepare SOPs and acknowledge updates. Ask your owner for supervisor access to author recipes.",
    );
    return;
  }
  editing = item;
  const form = $("#editor-form");
  form.reset();
  $("#ingredients").innerHTML = "";
  $("#editor-title").textContent = item ? "Refine your SOP." : "Create an SOP.";
  $("#editor-notice").hidden = !item?.review_note;
  $("#editor-notice").textContent = item?.review_note
    ? `Owner requested changes: ${item.review_note}`
    : "";
  if (item) {
    const c = item.content;
    for (const key of [
      "title",
      "category",
      "description",
      "servings",
      "safety_notes",
    ])
      form.elements[key].value = c[key];

    form.elements.steps.value = c.steps.join("\n");
    form.elements.allergens.value = c.allergens.join(", ");
    c.ingredients.forEach(ingredientRow);
  } else ingredientRow();
  photoGeneration++;
  photoBusy = false;
  photoData = item?.content.photo_data_url || null;
  $("#photo-input").value = "";
  renderPhoto();
  showWizard(0);
  $("#editor-dialog").showModal();
}
$("#auth-form").onsubmit = (e) => {
  e.preventDefault();
  submit(e.target, async () => {
    const body = Object.fromEntries(new FormData(e.target));
    if (registerMode) await api("/auth/register", "POST", body);
    const result = await api("/auth/login", "POST", body);
    token = result.access_token;
    sessionStorage.setItem("mysop-token", token);
    $("#auth-dialog").close();
    e.target.reset();
    await signedIn();
    toast("Welcome to your kitchen workspace.");
  });
};
$("#toggle-auth").onclick = () => {
  registerMode = !registerMode;
  $("#auth-title").textContent = registerMode
    ? "Make it your kitchen."
    : "Welcome back.";
  $("#auth-submit").textContent = registerMode ? "Create account" : "Sign in";
  $("#toggle-auth").textContent = registerMode
    ? "Already have an account? Sign in"
    : "New here? Create an account";
  $("#auth-form [name=password]").autocomplete = registerMode
    ? "new-password"
    : "current-password";
  $("#auth-form .form-error").textContent = "";
};
$("#auth-button").onclick = openAuth;
$("#get-started").onclick = openAuth;
$("#logout").onclick = async () => {
  try {
    await api("/auth/logout", "POST");
    endSession();
    toast("Signed out.");
  } catch (e) {
    toast(e.message);
  }
};
$$("[data-close]").forEach(
  (button) => (button.onclick = () => button.closest("dialog").close()),
);
async function loadMembers() {
  if (team?.role !== "owner") return;
  const selected = team.id,
    members = await api(`/teams/${selected}/members`);
  if (team?.id !== selected) return;
  $("#member-list").innerHTML = members
    .map(
      (m) =>
        `<div class="member-row"><span>${escapeHTML(m.email)}</span>${m.role === "owner" ? "<strong>Owner</strong>" : `<label class="sr-only" for="role-${m.id}">Access for ${escapeHTML(m.email)}</label><select id="role-${m.id}" data-member="${m.id}"><option value="staff" ${m.role === "staff" ? "selected" : ""}>Staff</option><option value="supervisor" ${m.role === "supervisor" ? "selected" : ""}>Supervisor</option></select>`}</div>`,
    )
    .join("");
  $$("#member-list select").forEach(
    (select) =>
      (select.onchange = async () => {
        select.disabled = true;
        try {
          await api(
            `/teams/${selected}/members/${select.dataset.member}`,
            "PATCH",
            { role: select.value },
          );
          toast("Team access updated.");
        } catch (e) {
          toast(e.message);
        } finally {
          await loadMembers();
        }
      }),
  );
}
$("#team-button").onclick = () => {
  if (!user) {
    openAuth();
    return;
  }
  $("#team-dialog").showModal();
  loadMembers().catch((e) => toast(e.message));
};
$("#team-form").onsubmit = (e) => {
  e.preventDefault();
  submit(e.target, async () => {
    const created = await api(
      "/teams",
      "POST",
      Object.fromEntries(new FormData(e.target)),
    );
    await refreshTeams(created.id);
    $("#team-dialog").close();
    e.target.reset();
    toast("Your team is ready. Create your first SOP.");
  });
};
$("#join-form").onsubmit = (e) => {
  e.preventDefault();
  submit(e.target, async () => {
    const result = await api(
      "/teams/join",
      "POST",
      Object.fromEntries(new FormData(e.target)),
    );
    await refreshTeams(result.team_id);
    $("#team-dialog").close();
    e.target.reset();
    toast("Welcome to the team.");
  });
};
$("#invite-button").onclick = async () => {
  $("#invite-button").disabled = true;
  $("#invite-token").value = "";
  $("#invite-result").hidden = true;
  try {
    const result = await api(`/teams/${team.id}/invitations`, "POST", {
      role: $("#invite-role").value,
    });
    $("#invite-token").value = result.invitation_token;
    $("#invite-result").hidden = false;
    $("#invite-error").textContent = "";
  } catch (e) {
    $("#invite-error").textContent = e.message;
  } finally {
    $("#invite-button").disabled = false;
  }
};
$("#teams").onchange = async (e) => {
  $$("dialog[open]").forEach(d => d.close());
  clearKitchenPrivateState();
  team = teams.find((t) => t.id === e.target.value) || null;
  updateRoleUI();
  $("#invite-result").hidden = true;
  $("#invite-token").value = "";
  startLive();
  try {
    await load();
  } catch (error) {
    toast(error.message);
  }
};
$$("[data-view]").forEach(
  (b) =>
    (b.onclick = () => {
      view = b.dataset.view;
      $$("[data-view]").forEach((n) => n.classList.toggle("active", n === b));
      load().catch((e) => toast(e.message));
    }),
);
$$("[data-category]").forEach(
  (b) =>
    (b.onclick = () => {
      category = b.dataset.category;
      $$("[data-category]").forEach((n) =>
        n.classList.toggle("selected", n === b),
      );
      render();
    }),
);
$("#search").oninput = render;
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
    e.preventDefault();
    $("#search").focus();
  }
});
$("#new-sop").onclick = () => openEditor();
$("#add-ingredient").onclick = () => ingredientRow();
$("#editor-form").onsubmit = (e) => {
  e.preventDefault();
  if (wizardStep !== 3) return;
  const sharing = e.submitter?.value === "publish";
  submit(e.target, async () => {
    if (photoBusy) throw Error("Wait for the photo to finish processing.");
    for (let i = 0; i < 3; i++) {
      showWizard(i);
      if (!validatePanel(i)) return;
    }
    showWizard(3);
    const body = editorContent(),
      root = `/teams/${team.id}/sops`;
    const saved = editing
      ? await api(
          `${root}/${editing.id}?expected_revision=${editing.revision}`,
          "PUT",
          body,
        )
      : await api(root, "POST", body);
    editing = saved;
    if (sharing)
      await api(
        `${root}/${saved.id}/${team.role === "owner" ? "publish" : "submit"}?expected_revision=${saved.revision}`,
        "POST",
      );
    $("#editor-dialog").close();
    await load();
    toast(
      sharing
        ? team.role === "owner"
          ? "Published. Your team is now up to date."
          : "Submitted to your owner for approval."
        : "Draft saved. Find it in My drafts.",
    );
  });
};
setupKitchen();
if (token)
  signedIn().catch((e) => {
    endSession();
    toast(e.message);
  });
else load();
