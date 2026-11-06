/**
 * budget.js — Presupuesto (budget) management for GEZARMA.
 * Handles:
 *   - Budget card on ticket detail (create/edit/state transitions/versions)
 *   - Admin: budget item templates CRUD
 *   - Admin: financial stats panel
 */

/* ── Helpers ─────────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const _ars = new Intl.NumberFormat(I18N.locale, { style: 'currency', currency: 'ARS' });
const fmt = n => _ars.format(+n || 0);   // $ 12.345,50

const ESTADO_COLORS = {
    borrador:  { bg: "bg-gray-100",    text: "text-gray-600",    label: "Borrador"  },
    enviado:   { bg: "bg-amber-100",   text: "text-amber-700",   label: "Enviado"   },
    aprobado:  { bg: "bg-emerald-100", text: "text-emerald-700", label: "Aprobado"  },
    rechazado: { bg: "bg-red-100",     text: "text-red-700",     label: "Rechazado" },
};

/* ═══════════════════════════════════════════════════════════════════════════
   TICKET DETAIL — Presupuesto card
   ═══════════════════════════════════════════════════════════════════════════ */

let _currentTicketId = null;
let _currentBudget   = null;
let _editingBudget   = false;  // false = create, true = edit
let _plantillas      = [];
let _repuestos       = [];   // catálogo (solo taller), para vincular ítems a repuestos

let _productoTicket = null;   // producto_id del ticket: sus plantillas se sugieren primero

export async function initPresupuestoCard(ticketId, userRole, productoId = null) {
    _currentTicketId = ticketId;
    _productoTicket  = productoId;
    _editingBudget   = false;

    // Load templates (for the picker) — only tech/admin edit budgets
    _plantillas = [];
    if (userRole !== "cliente") {
        try { _plantillas = await api.getPlantillasPresupuesto(); } catch { _plantillas = []; }
        try { _repuestos = await api.getParts(); } catch { _repuestos = []; }
    }

    // Load budget
    let budget = null;
    try { budget = await api.getPresupuesto(ticketId); } catch { /* no budget yet */ }
    // Mientras cargaba se pudo salir del ticket (o abrir otro, p. ej. con el lector)
    if (!$("presupuesto-empty") || ui.currentTicketId !== ticketId) return;
    _currentBudget = budget;

    renderPresupuestoCard(budget, userRole);
    bindCardEvents(userRole);
}

function renderPresupuestoCard(budget, userRole) {
    const isTechAdmin = ["tecnico", "administrador"].includes(userRole);
    const isClient    = userRole === "cliente";

    if (!budget) {
        $("presupuesto-empty").classList.remove("hidden");
        $("presupuesto-summary").classList.add("hidden");
        $("presupuesto-estado-badge").classList.add("hidden");
        $("create-presupuesto-btn").classList.toggle("hidden", !isTechAdmin);
        return;
    }

    $("presupuesto-empty").classList.add("hidden");
    $("presupuesto-summary").classList.remove("hidden");

    // Badge
    const badge = $("presupuesto-estado-badge");
    const cfg   = ESTADO_COLORS[budget.estado] || ESTADO_COLORS.borrador;
    badge.textContent = cfg.label;
    badge.className   = `px-2.5 py-0.5 rounded-full text-xs font-bold uppercase ${cfg.bg} ${cfg.text}`;
    badge.classList.remove("hidden");

    // Totals — clients only see the price (the API doesn't send cost/profit to them)
    $("presupuesto-costo").textContent    = fmt(budget.costo_total);
    $("presupuesto-precio").textContent   = fmt(budget.precio_total);
    $("presupuesto-ganancia").textContent = fmt(budget.ganancia);
    $("presupuesto-costo").parentElement.classList.toggle("hidden", isClient);
    $("presupuesto-ganancia").parentElement.classList.toggle("hidden", isClient);
    const totalsGrid = $("presupuesto-precio").parentElement.parentElement;
    totalsGrid.classList.toggle("grid-cols-3", !isClient);
    totalsGrid.classList.toggle("grid-cols-1", isClient);

    // Items list (compact)
    const list = $("presupuesto-items-list");
    list.innerHTML = budget.items.map(i =>
        `<div class="flex justify-between text-gray-600 py-0.5 border-b border-gray-50">
            <span class="truncate flex-1">${i.repuesto_codigo ? '📦 ' : ''}${escHtml(i.descripcion)} <span class="text-gray-400">×${i.cantidad}</span>${
                i.stock_disponible != null && i.stock_disponible < i.cantidad && budget.estado !== "aprobado"
                    ? ' <span class="text-red-600 font-semibold">(stock insuficiente)</span>' : ''}</span>
            <span class="font-semibold ml-2">${fmt(i.precio_total)}</span>
        </div>`
    ).join("") || '<p class="text-gray-400 text-center py-2">Sin ítems</p>';

    // Notes
    const notasEl = $("presupuesto-notas-display");
    if (budget.notas) {
        notasEl.textContent = budget.notas;
        notasEl.classList.remove("hidden");
    } else {
        notasEl.classList.add("hidden");
    }

    // Actions
    $("edit-presupuesto-btn").classList.toggle("hidden",
        !isTechAdmin || budget.estado === "aprobado");
    $("send-presupuesto-btn").classList.toggle("hidden",
        !isTechAdmin || budget.estado !== "borrador");
    $("client-presupuesto-actions").classList.toggle("hidden",
        !(isClient || isTechAdmin) || budget.estado !== "enviado");
    $("view-versions-btn").classList.toggle("hidden",
        !isTechAdmin || (budget.versiones && budget.versiones.length === 0));
}

function bindCardEvents(userRole) {
    /* Create */
    $("create-presupuesto-btn").onclick = () => openBudgetModal(false);

    /* Edit */
    $("edit-presupuesto-btn").onclick = () => openBudgetModal(true);

    /* Send */
    $("send-presupuesto-btn").onclick = async () => {
        if (!await confirmDialog("¿Enviar el presupuesto al cliente?", "El cliente lo va a ver en el portal y podrá aprobarlo o rechazarlo.", "Enviar", { peligro: false })) return;
        try {
            _currentBudget = await api.updateEstadoPresupuesto(_currentTicketId, "enviado");
            renderPresupuestoCard(_currentBudget, userRole);
            showToast("Presupuesto enviado al cliente", "success");
        } catch (e) { showToast(e.message || "Error", "error"); }
    };

    /* Approve */
    $("approve-presupuesto-btn").onclick = async () => {
        if (!await confirmDialog("¿Aprobar el presupuesto?", "", "Aprobar", { peligro: false })) return;
        try {
            _currentBudget = await api.updateEstadoPresupuesto(_currentTicketId, "aprobado");
            renderPresupuestoCard(_currentBudget, userRole);
            showToast("Presupuesto aprobado ✓", "success");
        } catch (e) { showToast(e.message || "Error", "error"); }
    };

    /* Reject */
    $("reject-presupuesto-btn").onclick = async () => {
        if (!await confirmDialog("¿Rechazar el presupuesto?", "", "Rechazar")) return;
        try {
            _currentBudget = await api.updateEstadoPresupuesto(_currentTicketId, "rechazado");
            renderPresupuestoCard(_currentBudget, userRole);
            showToast("Presupuesto rechazado", "warn");
        } catch (e) { showToast(e.message || "Error", "error"); }
    };

    /* Versions */
    $("view-versions-btn").onclick = () => openVersionesModal();

    /* Modal close */
    $("close-presupuesto-modal").onclick = closeBudgetModal;
    $("presupuesto-modal-overlay").onclick = closeBudgetModal;
    $("cancel-presupuesto-btn").onclick = closeBudgetModal;
    $("save-presupuesto-btn").onclick = () => saveBudget(userRole);

    /* Add item row */
    $("add-item-row-btn").onclick = () => addItemRow();

    /* Versiones modal close */
    $("close-versiones-modal").onclick = () => $("versiones-modal").classList.add("hidden");
    $("versiones-modal-overlay").onclick = () => $("versiones-modal").classList.add("hidden");
}

/* ── Budget modal (create / edit) ──────────────────────────────────────── */
function openBudgetModal(editing) {
    _editingBudget = editing;
    $("presupuesto-modal-title").textContent = editing ? "Editar Presupuesto" : "Crear Presupuesto";
    $("presupuesto-items-body").innerHTML = "";
    $("presupuesto-notas").value = editing && _currentBudget ? (_currentBudget.notas || "") : "";

    if (editing && _currentBudget) {
        _currentBudget.items.forEach(i => addItemRow(i));
    } else {
        addItemRow(); // start with one empty row
    }

    renderTemplatePills();
    renderRepuestoPicker();
    recalcTotals();
    $("presupuesto-modal").classList.remove("hidden");
}

function closeBudgetModal() {
    $("presupuesto-modal").classList.add("hidden");
}

function renderTemplatePills() {
    const wrap = $("template-pills");
    wrap.innerHTML = "";
    const activas  = _plantillas.filter(p => p.activo);
    const delModelo = activas.filter(p => _productoTicket && p.producto_id === _productoTicket);
    const generales = activas.filter(p => !p.producto_id);   // las de otros modelos no se muestran
    const agregar = p => {
        // Si la única fila está vacía, se reemplaza en lugar de dejarla en blanco
        const filas = [...$("presupuesto-items-body").querySelectorAll("tr")];
        if (filas.length === 1 && !filas[0].querySelector(".item-desc").value.trim()) filas[0].remove();
        addItemRow({ descripcion: p.descripcion, cantidad: 1, costo_interno: p.costo_interno, precio_cliente: p.precio_cliente });
        recalcTotals();
    };
    const pill = (p, cls) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `px-3 py-1 rounded-full text-xs font-semibold border transition ${cls}`;
        btn.textContent = `+ ${p.nombre}`;
        btn.onclick = () => agregar(p);
        return btn;
    };
    if (delModelo.length) {
        const fila = document.createElement("div");
        fila.className = "w-full flex flex-wrap items-center gap-2 mb-1";
        fila.innerHTML = `<span class="text-[11px] font-bold uppercase text-indigo-500">Para este modelo:</span>`;
        delModelo.forEach(p => fila.appendChild(pill(p, "border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100")));
        const todas = document.createElement("button");
        todas.type = "button";
        todas.className = "px-3 py-1 rounded-full text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white";
        todas.textContent = `Cargar las ${delModelo.length}`;
        todas.onclick = () => delModelo.forEach(agregar);
        if (delModelo.length > 1) fila.appendChild(todas);
        wrap.appendChild(fila);
    }
    generales.forEach(p => wrap.appendChild(pill(p, "border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100")));
}

function renderRepuestoPicker() {
    const sel = $("presupuesto-repuesto-select");
    if (!sel) return;
    sel.innerHTML = '<option value="">Elegí un repuesto…</option>' + _repuestos.map(r =>
        `<option value="${r.id}">${escHtml(r.nombre)} · ${escHtml(r.codigo)} · stock ${r.stock}</option>`).join("");
    sel.onchange = () => {
        const r = _repuestos.find(x => String(x.id) === sel.value);
        sel.value = "";
        if (!r) return;
        addItemRow({ repuesto_id: r.id, repuesto_codigo: r.codigo, stock_disponible: r.stock,
                     descripcion: r.nombre, cantidad: 1, costo_interno: r.precio, precio_cliente: 0 });
        recalcTotals();
    };
}

const escHtml = s => window.esc(s);   // ui/escape.js

function addItemRow(data = {}) {
    const tbody = $("presupuesto-items-body");
    const tr = document.createElement("tr");
    tr.className = "border-b border-gray-50";
    if (data.repuesto_id) {
        tr.dataset.repuestoId = data.repuesto_id;
        tr.dataset.stock = data.stock_disponible ?? "";
    }
    const repBadge = data.repuesto_id
        ? `<div class="item-rep text-[10px] mt-0.5 text-indigo-600 font-semibold">📦 ${escHtml(data.repuesto_codigo || "")} · stock ${data.stock_disponible ?? "?"}<span class="item-rep-warn text-red-600"></span></div>`
        : "";
    tr.innerHTML = `
        <td class="px-1 py-1">
            <input type="text" class="item-desc w-full px-2 py-1 border rounded text-xs focus:ring-1 focus:ring-blue-400 outline-none"
                value="${escHtml(data.descripcion || "")}" placeholder="Descripción">${repBadge}
        </td>
        <td class="px-1 py-1">
            <input type="number" class="item-qty w-16 px-2 py-1 border rounded text-xs text-right focus:ring-1 focus:ring-blue-400 outline-none"
                value="${data.cantidad ?? 1}" min="1" step="1">
        </td>
        <td class="px-1 py-1">
            <input type="number" class="item-cost w-24 px-2 py-1 border rounded text-xs text-right focus:ring-1 focus:ring-blue-400 outline-none"
                value="${data.costo_interno ?? 0}" min="0" step="0.01">
        </td>
        <td class="px-1 py-1">
            <input type="number" class="item-price w-24 px-2 py-1 border rounded text-xs text-right focus:ring-1 focus:ring-blue-400 outline-none"
                value="${data.precio_cliente ?? 0}" min="0" step="0.01">
        </td>
        <td class="px-1 py-1 text-right">
            <span class="item-total text-xs font-semibold text-blue-700">$0.00</span>
        </td>
        <td class="px-1 py-1 text-center">
            <button type="button" class="remove-item-btn text-red-400 hover:text-red-600 text-base leading-none font-bold">×</button>
        </td>`;
    tbody.appendChild(tr);

    // Events
    tr.querySelectorAll("input").forEach(inp => inp.addEventListener("input", () => {
        updateRowTotal(tr);
        recalcTotals();
    }));
    tr.querySelector(".remove-item-btn").onclick = () => { tr.remove(); recalcTotals(); };
    updateRowTotal(tr);
}

function updateRowTotal(tr) {
    const qty   = parseInt(tr.querySelector(".item-qty").value)    || 0;
    const price = parseFloat(tr.querySelector(".item-price").value) || 0;
    tr.querySelector(".item-total").textContent = fmt(qty * price);
    const warn = tr.querySelector(".item-rep-warn");
    if (warn && tr.dataset.stock !== "") {
        warn.textContent = qty > parseInt(tr.dataset.stock) ? " · stock insuficiente" : "";
    }
}

function recalcTotals() {
    let costo = 0, precio = 0;
    $("presupuesto-items-body").querySelectorAll("tr").forEach(tr => {
        const qty   = parseInt(tr.querySelector(".item-qty").value)    || 0;
        const cost  = parseFloat(tr.querySelector(".item-cost").value)  || 0;
        const price = parseFloat(tr.querySelector(".item-price").value) || 0;
        costo  += qty * cost;
        precio += qty * price;
    });
    $("modal-costo-total").textContent  = fmt(costo);
    $("modal-precio-total").textContent = fmt(precio);
    $("modal-ganancia").textContent     = fmt(precio - costo);
}

function collectItems() {
    const items = [];
    $("presupuesto-items-body").querySelectorAll("tr").forEach(tr => {
        const desc = tr.querySelector(".item-desc").value.trim();
        const repuestoId = tr.dataset.repuestoId ? parseInt(tr.dataset.repuestoId) : null;
        if (!desc && !repuestoId) return;
        items.push({
            descripcion:    desc,
            cantidad:       parseInt(tr.querySelector(".item-qty").value)    || 1,
            costo_interno:  parseFloat(tr.querySelector(".item-cost").value)  || 0,
            precio_cliente: parseFloat(tr.querySelector(".item-price").value) || 0,
            repuesto_id:    repuestoId,
        });
    });
    return items;
}

async function saveBudget(userRole) {
    const items = collectItems();
    const notas = $("presupuesto-notas").value.trim() || null;
    const payload = { items, notas };

    try {
        if (_editingBudget) {
            _currentBudget = await api.updatePresupuesto(_currentTicketId, payload);
        } else {
            _currentBudget = await api.createPresupuesto(_currentTicketId, payload);
        }
        closeBudgetModal();
        renderPresupuestoCard(_currentBudget, userRole);
        showToast("Presupuesto guardado", "success");
    } catch (e) {
        showToast(e.message || "Error al guardar el presupuesto", "error");
    }
}

/* ── Versions modal ──────────────────────────────────────────────────────── */
async function openVersionesModal() {
    $("versiones-list").innerHTML = '<p class="text-gray-400 text-sm text-center">Cargando...</p>';
    $("versiones-modal").classList.remove("hidden");
    try {
        const versiones = await api.getVersionesPresupuesto(_currentTicketId);
        renderVersiones(versiones);
    } catch {
        $("versiones-list").innerHTML = '<p class="text-red-400 text-sm text-center">Error al cargar versiones</p>';
    }
}

function renderVersiones(versiones) {
    const el = $("versiones-list");
    if (!versiones.length) {
        el.innerHTML = '<p class="text-gray-400 text-sm text-center">Sin versiones anteriores</p>';
        return;
    }
    el.innerHTML = versiones.map(v => {
        const cfg = ESTADO_COLORS[v.estado] || ESTADO_COLORS.borrador;
        const items = (v.items_snapshot || []).map(i =>
            `<li class="text-xs text-gray-500">${escHtml(i.descripcion)} ×${escHtml(i.cantidad)} — ${fmt(i.precio_total)}</li>`
        ).join("");
        return `
            <div class="bg-gray-50 rounded-xl p-4 border border-gray-100">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-sm font-bold text-gray-700">Versión ${v.version}</span>
                    <span class="px-2 py-0.5 rounded-full text-xs font-bold ${cfg.bg} ${cfg.text}">${cfg.label}</span>
                </div>
                <p class="text-xs text-gray-400 mb-2">
                    ${escHtml(v.usuario_nombre || "—")} &bull; ${new Date(v.fecha).toLocaleString(I18N.locale, { hour12: false })}
                </p>
                ${v.notas ? `<p class="text-xs italic text-gray-500 mb-2">"${escHtml(v.notas)}"</p>` : ""}
                ${items ? `<ul class="space-y-0.5 list-disc list-inside">${items}</ul>` : ""}
            </div>`;
    }).join("");
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN — Plantillas de Presupuesto
   ═══════════════════════════════════════════════════════════════════════════ */

// In-memory category list (persisted via plantilla data)
let _ppCategories = ["General", "Servicio", "Repuesto"];
let _ppActiveCatFilter = ""; // "" = all

function _syncCatsFromItems(items) {
    const fromItems = [...new Set(items.map(i => i.categoria).filter(Boolean))];
    fromItems.forEach(c => { if (!_ppCategories.includes(c)) _ppCategories.push(c); });
}

function _rebuildCatSelect() {
    const sel = document.getElementById("pp-categoria");
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = _ppCategories.map(c =>
        `<option value="${escHtml(c)}" ${c === current ? "selected" : ""}>${escHtml(c)}</option>`
    ).join("");
    if (!sel.value) sel.value = _ppCategories[0] || "General";
}

function _renderCatFilterPills(items) {
    const wrap = document.getElementById("pp-cat-filter-pills");
    if (!wrap) return;
    const cats = ["", ..._ppCategories.filter(c =>
        items.some(i => i.categoria === c)
    )];
    wrap.innerHTML = cats.map(c => {
        const active = _ppActiveCatFilter === c;
        const label  = c === "" ? "Todas" : c;
        return `<button type="button" data-cat="${escHtml(c)}"
            class="pp-cat-pill px-3 py-1 rounded-full text-xs font-semibold border transition
                ${active ? "bg-emerald-600 text-white border-emerald-600" : "border-gray-200 text-gray-600 hover:bg-gray-50"}">
            ${escHtml(label)}
        </button>`;
    }).join("");
    wrap.querySelectorAll(".pp-cat-pill").forEach(btn => {
        btn.onclick = () => {
            _ppActiveCatFilter = btn.dataset.cat;
            _renderCatFilterPills(items);
            _renderPlantillaRows(items);
        };
    });
}

function _renderPlantillaRows(items) {
    const list = document.getElementById("plantillas-pres-list");
    if (!list) return;
    const filtered = _ppActiveCatFilter
        ? items.filter(i => i.categoria === _ppActiveCatFilter)
        : items;

    if (!filtered.length) {
        list.innerHTML = '<p class="text-gray-400 text-sm p-5 text-center">Sin plantillas para esta categoría</p>';
        return;
    }
    list.innerHTML = filtered.map(p => `
        <div class="flex items-center px-5 py-3.5 hover:bg-gray-50 transition gap-4" data-id="${p.id}">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm font-semibold text-gray-800">${escHtml(p.nombre)}</span>
                    <span class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">${escHtml(p.categoria || "General")}</span>
                    ${!p.activo ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-500 font-bold">inactivo</span>' : ""}
                    ${p.producto_nombre ? `<span class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-600">📦 ${escHtml(p.producto_nombre)}</span>` : ""}
                </div>
                <p class="text-xs text-gray-400 mt-0.5 truncate">${escHtml(p.descripcion)}</p>
                <p class="text-xs text-gray-500 mt-0.5">
                    <span class="text-gray-400">Costo:</span> <strong>${fmt(p.costo_interno)}</strong>
                    &nbsp;·&nbsp;
                    <span class="text-gray-400">Precio:</span> <strong class="text-blue-700">${fmt(p.precio_cliente)}</strong>
                    &nbsp;·&nbsp;
                    <span class="text-emerald-600 font-semibold">+${fmt(p.precio_cliente - p.costo_interno)}</span>
                </p>
            </div>
            <div class="flex gap-3 shrink-0">
                <button type="button" class="edit-pp-btn text-xs text-blue-500 hover:text-blue-700 font-semibold" data-id="${p.id}">Editar</button>
                <button type="button" class="del-pp-btn text-xs text-red-400 hover:text-red-600 font-semibold" data-id="${p.id}">Eliminar</button>
            </div>
        </div>`).join("");

    // Bind edit buttons
    list.querySelectorAll(".edit-pp-btn").forEach(btn => {
        btn.onclick = () => {
            const item = items.find(x => x.id == btn.dataset.id);
            if (!item) return;
            _openPpModal(item);
        };
    });

    // Bind delete buttons
    list.querySelectorAll(".del-pp-btn").forEach(btn => {
        btn.onclick = async () => {
            if (!await confirmDialog("¿Eliminar esta plantilla?", "Los presupuestos ya hechos con ella no cambian.")) return;
            try {
                await api.deletePlantillaPresupuesto(btn.dataset.id);
                showToast("Plantilla eliminada", "success");
                await loadPlantillasPresupuesto();
            } catch (e) { showToast(e.message || "Error", "error"); }
        };
    });
}

function _openPpModal(item = null) {
    const isEdit = !!item;
    document.getElementById("pp-modal-title").textContent = isEdit ? "Editar plantilla" : "Nueva plantilla";
    document.getElementById("pp-edit-id").value    = item ? item.id : "";
    document.getElementById("pp-nombre").value     = item ? item.nombre : "";
    document.getElementById("pp-descripcion").value = item ? item.descripcion : "";
    document.getElementById("pp-costo").value      = item ? item.costo_interno : 0;
    document.getElementById("pp-precio").value     = item ? item.precio_cliente : 0;
    document.getElementById("pp-orden").value      = item ? item.orden : 0;
    _rebuildCatSelect();
    if (item) document.getElementById("pp-categoria").value = item.categoria || "General";
    const sel = document.getElementById("pp-producto");
    api.getProducts().then(productos => {
        sel.innerHTML = '<option value="">Todos los productos</option>' + productos.map(pr =>
            `<option value="${pr.id}">${escHtml(`${pr.marca} ${pr.modelo}`)}</option>`).join("");
        sel.value = item && item.producto_id ? String(item.producto_id) : "";
    }).catch(() => {});
    document.getElementById("pp-modal").classList.remove("hidden");
    document.getElementById("pp-nombre").focus();
}

function _closePpModal() {
    document.getElementById("pp-modal").classList.add("hidden");
}

// ── Category manager modal ────────────────────────────────────────────────────
function _openCatsModal() {
    _renderCatsModalList();
    document.getElementById("pp-new-cat-input").value = "";
    document.getElementById("pp-cats-modal").classList.remove("hidden");
}
function _closeCatsModal() {
    document.getElementById("pp-cats-modal").classList.add("hidden");
}
function _renderCatsModalList() {
    const list = document.getElementById("pp-cats-list");
    if (!list) return;
    if (!_ppCategories.length) {
        list.innerHTML = '<p class="text-gray-400 text-sm text-center">Sin categorías</p>';
        return;
    }
    list.innerHTML = _ppCategories.map(c => `
        <div class="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
            <span class="text-sm font-medium text-gray-700">${escHtml(c)}</span>
            ${c !== "General" ? `<button type="button" class="del-cat-btn text-xs text-red-400 hover:text-red-600 font-semibold" data-cat="${escHtml(c)}">Eliminar</button>` : '<span class="text-xs text-gray-300">predeterminada</span>'}
        </div>`).join("");
    list.querySelectorAll(".del-cat-btn").forEach(btn => {
        btn.onclick = () => {
            const cat = btn.dataset.cat;
            _ppCategories = _ppCategories.filter(c => c !== cat);
            _renderCatsModalList();
            _rebuildCatSelect();
            loadPlantillasPresupuesto();
        };
    });
}

export async function initPlantillasPresupuesto() {
    await loadPlantillasPresupuesto();

    // New plantilla button → open modal
    document.getElementById("new-plantilla-pres-btn").onclick = () => _openPpModal(null);

    // Modal close
    document.getElementById("close-pp-modal").onclick       = _closePpModal;
    document.getElementById("cancel-pp-modal-btn").onclick  = _closePpModal;
    document.getElementById("pp-modal-overlay").onclick     = _closePpModal;

    // Save plantilla
    document.getElementById("save-plantilla-pres-btn").onclick = savePlantillaPresupuesto;

    // Category manager
    document.getElementById("manage-pp-cats-btn").onclick       = _openCatsModal;
    document.getElementById("close-pp-cats-modal").onclick      = _closeCatsModal;
    document.getElementById("pp-cats-modal-overlay").onclick    = _closeCatsModal;
    document.getElementById("add-pp-cat-btn").onclick           = () => {
        const input = document.getElementById("pp-new-cat-input");
        const val   = input.value.trim();
        if (!val) return;
        if (_ppCategories.includes(val)) { showToast("Esa categoría ya existe", "warn"); return; }
        _ppCategories.push(val);
        input.value = "";
        _renderCatsModalList();
        _rebuildCatSelect();
        loadPlantillasPresupuesto();
    };
    // Allow Enter key in category input
    document.getElementById("pp-new-cat-input").onkeydown = e => {
        if (e.key === "Enter") document.getElementById("add-pp-cat-btn").click();
    };
}

async function loadPlantillasPresupuesto() {
    const list = document.getElementById("plantillas-pres-list");
    if (!list) return;
    list.innerHTML = '<p class="text-gray-400 text-sm p-5 text-center">Cargando...</p>';
    try {
        const items = await api.getPlantillasPresupuesto();
        _syncCatsFromItems(items);
        _renderCatFilterPills(items);
        _renderPlantillaRows(items);
    } catch {
        list.innerHTML = '<p class="text-red-400 text-sm p-5 text-center">Error al cargar plantillas</p>';
    }
}

async function savePlantillaPresupuesto() {
    const id    = document.getElementById("pp-edit-id").value;
    const payload = {
        nombre:         document.getElementById("pp-nombre").value.trim(),
        descripcion:    document.getElementById("pp-descripcion").value.trim(),
        costo_interno:  parseFloat(document.getElementById("pp-costo").value)  || 0,
        precio_cliente: parseFloat(document.getElementById("pp-precio").value) || 0,
        categoria:      document.getElementById("pp-categoria").value.trim() || "General",
        orden:          parseInt(document.getElementById("pp-orden").value)    || 0,
        activo:         true,
        producto_id:    parseInt(document.getElementById("pp-producto").value) || null,
    };
    if (!payload.nombre) { showToast("El nombre es obligatorio", "warn"); return; }
    if (!payload.descripcion) { showToast("La descripción es obligatoria", "warn"); return; }
    try {
        if (id) {
            await api.updatePlantillaPresupuesto(id, payload);
        } else {
            await api.createPlantillaPresupuesto(payload);
        }
        _closePpModal();
        showToast("Plantilla guardada", "success");
        await loadPlantillasPresupuesto();
    } catch (e) { showToast(e.message || "Error", "error"); }
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN — Financial Stats
   ═══════════════════════════════════════════════════════════════════════════ */

export async function initFinancialStats() {
    const ids = ["fin-ingreso-total","fin-ganancia-total","fin-costo-total",
                 "fin-margen","fin-ganancia-prom","fin-costo-prom"];
    ids.forEach(id => { const el = $(id); if (el) el.textContent = "Cargando..."; });

    try {
        const s = await api.getFinancialStats();
        $("fin-ingreso-total").textContent  = fmt(s.ingreso_total);
        $("fin-ganancia-total").textContent = fmt(s.ganancia_total);
        $("fin-costo-total").textContent    = fmt(s.costo_total);
        $("fin-margen").textContent         = `${s.margen_promedio.toFixed(1)}%`;
        $("fin-ganancia-prom").textContent  = fmt(s.ganancia_promedio_ticket);
        $("fin-costo-prom").textContent     = fmt(s.costo_promedio_ticket);
        $("fin-tickets-count").textContent  = `${s.tickets_con_presupuesto} presupuestos aprobados`;

        renderMonthlyChart(s);
        renderMonthlyTable(s);
    } catch (e) {
        ids.forEach(id => { const el = $(id); if (el) el.textContent = "—"; });
        console.error("Financial stats error:", e);
    }
}

function renderMonthlyChart(s) {
    const container = $("fin-chart");
    if (!container) return;
    const meses = Object.keys(s.ganancias_por_mes);
    if (!meses.length) {
        container.innerHTML = '<p class="text-gray-400 text-sm text-center py-8">Sin datos aún</p>';
        return;
    }

    const maxVal = Math.max(
        ...Object.values(s.ingresos_por_mes),
        ...Object.values(s.ganancias_por_mes), 1
    );

    container.innerHTML = `
        <div class="flex items-end gap-3 h-40 overflow-x-auto pb-2">
            ${meses.map(m => {
                const ingreso  = s.ingresos_por_mes[m]  || 0;
                const ganancia = s.ganancias_por_mes[m] || 0;
                const costo    = s.costos_por_mes[m]    || 0;
                const hI = Math.max(4, Math.round((ingreso  / maxVal) * 130));
                const hG = Math.max(4, Math.round((ganancia / maxVal) * 130));
                const hC = Math.max(4, Math.round((costo    / maxVal) * 130));
                const label = m.slice(0,7); // YYYY-MM
                return `
                    <div class="flex flex-col items-center gap-1 shrink-0" style="min-width:56px">
                        <div class="flex items-end gap-0.5">
                            <div class="w-4 bg-blue-200 rounded-t" style="height:${hI}px" title="Ingresos: ${fmt(ingreso)}"></div>
                            <div class="w-4 bg-emerald-400 rounded-t" style="height:${hG}px" title="Ganancia: ${fmt(ganancia)}"></div>
                            <div class="w-4 bg-rose-300 rounded-t" style="height:${hC}px" title="Costo: ${fmt(costo)}"></div>
                        </div>
                        <span class="text-[10px] text-gray-400 rotate-45 origin-left whitespace-nowrap">${label}</span>
                    </div>`;
            }).join("")}
        </div>
        <div class="flex gap-4 mt-3 text-xs text-gray-500">
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-blue-200 inline-block"></span>Ingresos</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-emerald-400 inline-block"></span>Ganancia</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-rose-300 inline-block"></span>Costo</span>
        </div>`;
}

function renderMonthlyTable(s) {
    const tbody = $("fin-monthly-table");
    if (!tbody) return;
    const meses = Object.keys(s.ganancias_por_mes);
    if (!meses.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-gray-400 py-4 text-sm">Sin datos</td></tr>';
        return;
    }
    tbody.innerHTML = meses.map(m => {
        const ing = s.ingresos_por_mes[m]  || 0;
        const cos = s.costos_por_mes[m]    || 0;
        const gan = s.ganancias_por_mes[m] || 0;
        const mar = ing ? (gan / ing * 100).toFixed(1) + "%" : "—";
        return `<tr class="hover:bg-gray-50 transition">
            <td class="px-4 py-2.5 font-semibold text-gray-700">${m}</td>
            <td class="px-4 py-2.5 text-right text-blue-700 font-semibold">${fmt(ing)}</td>
            <td class="px-4 py-2.5 text-right text-rose-500 font-semibold">${fmt(cos)}</td>
            <td class="px-4 py-2.5 text-right text-emerald-600 font-bold">${fmt(gan)}</td>
            <td class="px-4 py-2.5 text-right text-gray-500">${mar}</td>
        </tr>`;
    }).join("");
}

/* ── Tiny toast helper (falls back to global if available) ──────────────── */
function showToast(msg, type = "info") {
    const t = window.toast;
    if (t) {
        const map = { success: "success", error: "error", warn: "warning", info: "info" };
        const fn = map[type] || "info";
        if (t[fn]) t[fn](msg);
    } else {
        console.log(`[${type}] ${msg}`);
    }
}
