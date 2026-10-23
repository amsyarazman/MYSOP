"use strict";
let photoData = null, photoBusy = false, photoGeneration = 0;
let activeBill = null, billGeneration = 0;
let readerPages = [], readerIndex = 0, readerObserver = null;

function renderPhoto() {
  const preview = $("#photo-preview");
  preview.hidden = !photoData;
  if (photoData) preview.src = photoData;
  else preview.removeAttribute("src");
  $("#remove-photo").hidden = !photoData;
  $("#photo-status").textContent = "";
}

function clearKitchenPrivateState() {
  billGeneration++;
  photoGeneration++;
  photoBusy = false;
  photoData = null;
  activeBill = null;
  $("#bom-prices").replaceChildren();
  $("#bom-extras").replaceChildren();
  $("#bom-summary").replaceChildren();
  $("#bom-recipe").textContent = "";
  $("#ack-report").replaceChildren();
  renderPhoto();
}

function reviewSOP(c) {
  return `${c.photo_data_url ? `<img class="photo-preview" src="${escapeHTML(c.photo_data_url)}" alt="${escapeHTML(c.title)}">` : ""}<p>${escapeHTML(c.description)}</p><h3>Ingredients</h3>${c.ingredients.map(i => `<div class="reader-ingredient"><span>${escapeHTML(i.name)} </span><strong> ${escapeHTML(i.measure_note || `${i.quantity} ${i.unit}`)}</strong></div>`).join("")}<h3>Procedure</h3><ol>${c.steps.map(s => `<li>${escapeHTML(s)}</li>`).join("")}</ol><p>Allergens: ${escapeHTML(c.allergens.join(", ") || "Verify before serving")}</p><p>${escapeHTML(c.safety_notes)}</p>`;
}

function readerBlocks(c) {
  const box = document.createElement("div");
  box.innerHTML = `${c.photo_data_url ? `<img class="reader-photo" src="${escapeHTML(c.photo_data_url)}" alt="${escapeHTML(c.title)}">` : ""}<h3>Ingredients</h3>${c.ingredients.map(i => `<div class="reader-ingredient"><span>${escapeHTML(i.name)} </span><strong> ${escapeHTML(i.measure_note || `${i.quantity} ${i.unit}`)}</strong></div>`).join("")}<h3>Procedure</h3>${c.steps.map((s, i) => `<p class="reader-step">${i + 1}. ${escapeHTML(s)}</p>`).join("")}<h3>Allergens & safety</h3><p>Allergens: ${escapeHTML(c.allergens.join(", ") || "Not specified. Verify before serving.")}</p><p>${escapeHTML(c.safety_notes || "Follow your approved handling and storage procedures.")}</p>`;
  return [...box.children];
}

function openReader(content, keepPosition = false) {
  readerObserver?.disconnect();
  const page = $("#sop-page");
  if (!page) return;
  const oldIndex = keepPosition ? readerIndex : 0;
  page.replaceChildren();
  readerPages = [];
  let current = [];
  const fits = () => page.scrollHeight <= page.clientHeight + 1;
  const finish = () => {
    if (current.length) readerPages.push(current);
    current = [];
    page.replaceChildren();
  };
  for (const block of readerBlocks(content)) {
    if (block.tagName === "IMG") {
      const size = Math.min(110, page.clientHeight);
      block.style.width = block.style.height = `${size}px`;
    }
    page.append(block);
    if (fits()) { current.push(block.cloneNode(true)); continue; }
    block.remove();
    finish();
    page.append(block);
    if (fits()) { current.push(block.cloneNode(true)); continue; }
    // Split unusually long steps/notes across pages; never discard or shrink text.
    const text = Array.from(block.textContent);
    let remaining = text;
    page.replaceChildren();
    while (remaining.length) {
      const part = block.cloneNode(false);
      page.append(part);
      let low = 1, high = remaining.length, count = 0;
      while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        part.textContent = remaining.slice(0, mid).join("");
        if (fits()) { count = mid; low = mid + 1; } else high = mid - 1;
      }
      // The compact controls leave room for at least a line on supported phone sizes.
      count = Math.max(1, count);
      const candidate = remaining.slice(0, count).join("");
      const wordEnd = candidate.lastIndexOf(" ");
      if (count < remaining.length && wordEnd > count / 2) count = wordEnd + 1;
      part.textContent = remaining.slice(0, count).join("");
      remaining = remaining.slice(count);
      current.push(part.cloneNode(true));
      if (remaining.length) finish();
    }
  }
  finish();
  readerIndex = Math.min(oldIndex, readerPages.length - 1);
  renderReaderPage();
  const width = page.clientWidth, height = page.clientHeight;
  readerObserver = new ResizeObserver(() => {
    if (page.clientWidth !== width || page.clientHeight !== height)
      requestAnimationFrame(() => {
        if ($("#detail-dialog").open && $("#sop-page") === page) openReader(content, true);
      });
  });
  readerObserver.observe(page);
}

function renderReaderPage() {
  $("#sop-page").replaceChildren(...(readerPages[readerIndex] || []).map(n => n.cloneNode(true)));
  $("#sop-position").textContent = `${readerIndex + 1} / ${readerPages.length}`;
  $("#sop-previous").disabled = readerIndex === 0;
  $("#sop-next").disabled = readerIndex >= readerPages.length - 1;
}

function billSummary(cost) {
  const currency = escapeHTML(cost.currency);
  return `<div class="cost-summary"><p>Total recipe cost</p><strong>${cost.total === null ? "Cost incomplete" : `${currency} ${escapeHTML(cost.total)}`}</strong><p>${cost.per_serving === null ? `Known subtotal: ${currency} ${escapeHTML(cost.known_subtotal)} · ${cost.missing_prices} ingredient price(s) missing.` : `${currency} ${escapeHTML(cost.per_serving)} per serving`}</p><p>Ingredients: ${currency} ${escapeHTML(cost.ingredient_subtotal)} per recipe</p><p>Other costs: ${currency} ${escapeHTML(cost.other_per_serving)} per serving · ${currency} ${escapeHTML(cost.other_total)} per recipe</p></div>`;
}

function extraCostRow(value = {name: "", per_serving: ""}) {
  const row = document.createElement("div");
  row.className = "extra-cost-row";
  row.innerHTML = `<label>Cost name<input data-extra="name" aria-label="Other cost name" required maxlength="160" placeholder="e.g. Packaging" value="${escapeHTML(value.name)}"></label><label>Amount per serving<input data-extra="per_serving" aria-label="Other cost per serving" type="number" min="0" max="9999999999" step="0.0001" required value="${escapeHTML(value.per_serving)}"></label><button type="button" class="text-button" aria-label="Remove other cost">Remove ×</button>`;
  row.querySelector("button").onclick = () => { row.remove(); provisionalBill(); };
  $("#bom-extras").append(row);
}

function billBody() {
  return {
    currency: $("#bom-form").elements.currency.value,
    prices: $$(".material-price").map(row => ({
      name: row.dataset.name, unit: row.dataset.unit,
      pack_quantity: row.querySelector('[data-price="pack_quantity"]').value || null,
      pack_cost: row.querySelector('[data-price="pack_cost"]').value || null,
    })),
    other_costs: $$(".extra-cost-row").map(row => ({
      name: row.querySelector('[data-extra="name"]').value,
      per_serving: row.querySelector('[data-extra="per_serving"]').value,
    })),
  };
}

function provisionalBill() {
  if (!activeBill) return;
  const body = billBody();
  let ingredients = 0, missing = 0;
  body.prices.forEach((p, i) => {
    const amount = p.pack_quantity === null || p.pack_cost === null || Number(p.pack_quantity) <= 0 ? null : Number(activeBill.prices[i].quantity) / Number(p.pack_quantity) * Number(p.pack_cost);
    if (amount === null) missing++;
    else ingredients += amount;
    $$(".material-line-cost")[i].textContent = amount === null ? "Price not entered" : `${body.currency} ${amount.toFixed(2)} per recipe`;
  });
  const other = body.other_costs.reduce((n, c) => n + Number(c.per_serving || 0), 0);
  const total = ingredients + other * activeBill.servings;
  $("#bom-summary").innerHTML = '<p class="muted">Estimate while editing. Save for the server-calculated total.</p>' + billSummary({
    currency: body.currency, total: missing ? null : total.toFixed(2), per_serving: missing ? null : (total / activeBill.servings).toFixed(2),
    known_subtotal: total.toFixed(2), missing_prices: missing, ingredient_subtotal: ingredients.toFixed(2), other_per_serving: other.toFixed(2), other_total: (other * activeBill.servings).toFixed(2),
  });
}

async function openBill(row, kind) {
  if (team?.role !== "owner") return;
  const selected = team.id, generation = ++billGeneration;
  const id = row.sop_id || row.id;
  const suffix = kind === "published" ? `?version=${row.version}` : "";
  try {
    const data = await api(`/teams/${selected}/sops/${id}/bom${suffix}`);
    if (generation !== billGeneration || team?.id !== selected || team?.role !== "owner") return;
    activeBill = {...data, teamId: selected, suffix};
    $("#bom-form .form-error").textContent = "";
    $("#bom-form").elements.currency.value = data.currency;
    $("#bom-recipe").textContent = `${data.title} · ${data.servings} servings · ${data.recipe_version ? `SOP version ${data.recipe_version}` : `Draft revision ${data.recipe_revision}`}`;
    $("#bom-prices").innerHTML = data.prices.map(p => `<div class="material-price" data-name="${escapeHTML(p.name)}" data-unit="${escapeHTML(p.unit)}"><p><strong>${escapeHTML(p.name)}</strong> · ${escapeHTML(p.quantity)} ${escapeHTML(p.unit)} per recipe</p><div class="form-row"><label>Pack size (${escapeHTML(p.unit)})<input data-price="pack_quantity" aria-label="Pack size for ${escapeHTML(p.name)}" type="number" min="0.0001" max="9999999999" step="0.0001" value="${escapeHTML(p.pack_quantity ?? "")}"></label><label>Pack price<input data-price="pack_cost" aria-label="Pack price for ${escapeHTML(p.name)}" type="number" min="0" max="9999999999" step="0.0001" value="${escapeHTML(p.pack_cost ?? "")}"></label></div><p class="material-line-cost">${p.recipe_cost === null ? "Price not entered" : `${escapeHTML(data.currency)} ${escapeHTML(p.recipe_cost)} per recipe`}</p></div>`).join("");
    $("#bom-extras").replaceChildren();
    data.other_costs.forEach(extraCostRow);
    $("#bom-summary").innerHTML = billSummary(data.costing);
    $("#bom-dialog").showModal();
  } catch (e) { toast(e.message); }
}

function setupKitchen() {
  $("#photo-input").onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    const generation = ++photoGeneration;
    photoBusy = true;
    $("#photo-status").textContent = "Preparing square photo…";
    try {
      if (file.size > 20_000_000) throw Error("Choose a photo smaller than 20 MB.");
      const image = await createImageBitmap(file);
      try {
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 512;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 512, 512);
        const size = Math.min(image.width, image.height);
        ctx.drawImage(image, (image.width - size) / 2, (image.height - size) / 2, size, size, 0, 0, 512, 512);
        let data;
        for (const quality of [.82, .7, .55, .4]) {
          data = canvas.toDataURL("image/jpeg", quality);
          if (data.length <= 200_022) break;
        }
        if (data.length > 200_022) throw Error("Could not compress this photo below 150 KB. Choose a smaller photo.");
        if (generation !== photoGeneration) return;
        photoData = data;
        renderPhoto();
        $("#photo-status").textContent = `Square photo ready · ${Math.ceil((data.length - 23) * .75 / 1000)} KB`;
      } finally { image.close(); }
    } catch (e) {
      if (generation === photoGeneration) $("#photo-status").textContent = e.message || "Could not read this photo.";
    } finally { if (generation === photoGeneration) photoBusy = false; }
  };
  $("#remove-photo").onclick = () => { photoGeneration++; photoBusy = false; photoData = null; $("#photo-input").value = ""; renderPhoto(); };
  $("#add-other-cost").onclick = () => extraCostRow();
  $("#bom-form").addEventListener("input", provisionalBill);
  $("#bom-dialog").addEventListener("close", () => {
    billGeneration++; activeBill = null;
    $("#bom-prices").replaceChildren(); $("#bom-extras").replaceChildren(); $("#bom-summary").replaceChildren();
  });
  $("#bom-form").onsubmit = e => {
    e.preventDefault();
    submit(e.target, async () => {
      if (!activeBill || team?.id !== activeBill.teamId || team?.role !== "owner") throw Error("Reopen costing for the selected team.");
      const selectedBill = activeBill, generation = billGeneration;
      const separator = activeBill.suffix ? "&" : "?";
      const data = await api(`/teams/${activeBill.teamId}/sops/${activeBill.sop_id}/bom${activeBill.suffix}${separator}expected_revision=${activeBill.revision}`, "PUT", billBody());
      if (generation !== billGeneration || activeBill !== selectedBill) return;
      activeBill = {...activeBill, ...data};
      $$(".material-line-cost").forEach((line, i) => { line.textContent = data.prices[i].recipe_cost === null ? "Price not entered" : `${data.currency} ${data.prices[i].recipe_cost} per recipe`; });
      $("#bom-summary").innerHTML = billSummary(data.costing);
      toast("Costing saved. Staff instructions are unchanged.");
    });
  };
  $("#sop-previous").onclick = () => { if (readerIndex > 0) { readerIndex--; renderReaderPage(); } };
  $("#sop-next").onclick = () => { if (readerIndex < readerPages.length - 1) { readerIndex++; renderReaderPage(); } };
  $("#detail-dialog").addEventListener("close", () => { readerObserver?.disconnect(); readerPages = []; });
  $("#detail-dialog").addEventListener("keydown", e => {
    if (!$("#sop-page") || e.target.matches("input,textarea,select")) return;
    if (e.key === "ArrowRight") { e.preventDefault(); $("#sop-next").click(); }
    if (e.key === "ArrowLeft") { e.preventDefault(); $("#sop-previous").click(); }
  });
}
