/**
 * notifications.js — In-app notification bell for GEZARMA.
 * Polls the server every 30s while logged in.
 * Injected into the navbar next to the logout button.
 */

const POLL_INTERVAL_MS = 30_000;
const TIPO_ICONS = {
    comentario:    "💬",
    cambio_estado: "🔄",
    campo_editado: "✏️",
    presupuesto:   "💰",
    asignacion:    "👤",
    repuesto:      "🔧",
};

let _pollTimer     = null;
let _showAll       = false;
let _dropdownOpen  = false;
let _bellBtn       = null;

/* ── Init ───────────────────────────────────────────────────────────────── */
export function init() {
    _injectBell();
    _bindEvents();
    poll();  // immediate first fetch
}

export function stop() {
    if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
}

export async function poll() {
    if (_pollTimer) clearTimeout(_pollTimer);
    if (!window.auth?.isLoggedIn()) return;
    try {
        const { count } = await api.getUnreadCount();
        _updateBadge(count);
        if (_dropdownOpen) await _loadDropdown();
    } catch { /* silent */ }
    _pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
}

/* ── Bell button ────────────────────────────────────────────────────────── */
function _injectBell() {
    if (document.getElementById("notif-bell-btn")) return;
    const logoutBtn = document.getElementById("logout-btn");
    if (!logoutBtn) return;

    _bellBtn = document.createElement("button");
    _bellBtn.type = "button";
    _bellBtn.id   = "notif-bell-btn";
    _bellBtn.className =
        "relative w-9 h-9 rounded-lg flex items-center justify-center text-blue-200 hover:bg-blue-700 transition";
    _bellBtn.title = "Notificaciones";
    _bellBtn.innerHTML = `
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/>
        </svg>
        <span id="notif-badge"
            class="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-black flex items-center justify-center hidden">
            0
        </span>`;
    logoutBtn.parentElement.insertBefore(_bellBtn, logoutBtn);
}

function _updateBadge(count) {
    const badge = document.getElementById("notif-badge");
    if (!badge) return;
    if (count > 0) {
        badge.textContent = count > 99 ? "99+" : count;
        badge.classList.remove("hidden");
    } else {
        badge.classList.add("hidden");
    }
}

/* ── Dropdown ───────────────────────────────────────────────────────────── */
function _bindEvents() {
    document.addEventListener("click", e => {
        const bell     = document.getElementById("notif-bell-btn");
        const dropdown = document.getElementById("notif-dropdown");
        if (!bell || !dropdown) return;

        if (bell.contains(e.target)) {
            _dropdownOpen = !_dropdownOpen;
            dropdown.classList.toggle("hidden", !_dropdownOpen);
            dropdown.classList.toggle("flex", _dropdownOpen);
            if (_dropdownOpen) _loadDropdown();
            return;
        }
        // Close if clicking outside
        if (!dropdown.contains(e.target)) {
            _dropdownOpen = false;
            dropdown.classList.add("hidden");
            dropdown.classList.remove("flex");
        }
    });

    document.getElementById("notif-mark-all-btn")?.addEventListener("click", async () => {
        await api.markNotificationsRead([]);
        _updateBadge(0);
        await _loadDropdown();
    });

    document.getElementById("notif-show-all-toggle")?.addEventListener("click", async () => {
        _showAll = !_showAll;
        const btn = document.getElementById("notif-show-all-toggle");
        if (btn) btn.textContent = _showAll ? "Solo no leídas" : "Ver todas";
        await _loadDropdown();
    });
}

async function _loadDropdown() {
    const list = document.getElementById("notif-list");
    if (!list) return;
    list.innerHTML = `<p class="text-sm text-gray-400 text-center py-6">Cargando...</p>`;
    try {
        const items = await api.getNotifications(_showAll);
        if (!items.length) {
            list.innerHTML = `<p class="text-sm text-gray-400 text-center py-6">${_showAll ? "Sin notificaciones" : "No hay notificaciones sin leer 🎉"}</p>`;
            return;
        }
        list.innerHTML = items.map(n => _renderItem(n)).join("");

        // Bind ticket navigation
        list.querySelectorAll(".notif-ticket-link").forEach(btn => {
            btn.addEventListener("click", async () => {
                const ticketId = parseInt(btn.dataset.ticketId);
                if (!ticketId) return;
                // Mark as read
                await api.markNotificationsRead([parseInt(btn.closest("[data-notif-id]").dataset.notifId)]);
                _dropdownOpen = false;
                document.getElementById("notif-dropdown").classList.add("hidden");
                document.getElementById("notif-dropdown").classList.remove("flex");
                // Navigate to ticket
                try {
                    const ticket = await api.getTicket(ticketId);
                    await ui.showTicketDetail(ticket);
                    poll();
                } catch { toast.error("No se pudo abrir el ticket."); }
            });
        });

        // Bind dismiss buttons
        list.querySelectorAll(".notif-dismiss-btn").forEach(btn => {
            btn.addEventListener("click", async e => {
                e.stopPropagation();
                const id = parseInt(btn.dataset.notifId);
                await api.deleteNotification(id);
                await _loadDropdown();
                await poll();
            });
        });

        // Mark visible unread ones as read after a short delay
        const unreadIds = items.filter(n => !n.leida).map(n => n.id);
        if (unreadIds.length) {
            setTimeout(async () => {
                await api.markNotificationsRead(unreadIds);
                _updateBadge(0);
                // Re-render to show them as read
                list.querySelectorAll(".notif-unread-dot").forEach(d => d.classList.add("hidden"));
            }, 2000);
        }
    } catch {
        list.innerHTML = `<p class="text-sm text-red-400 text-center py-4">Error al cargar notificaciones</p>`;
    }
}

function _renderItem(n) {
    const icon    = TIPO_ICONS[n.tipo] || "🔔";
    const timeAgo = _timeAgo(new Date(n.fecha));
    const unread  = !n.leida;
    return `
        <div data-notif-id="${n.id}"
            class="flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition cursor-pointer group ${unread ? "bg-blue-50/40" : ""}">
            <span class="text-lg mt-0.5 shrink-0">${icon}</span>
            <div class="flex-1 min-w-0">
                <div class="flex items-start justify-between gap-1">
                    <p class="text-xs font-bold text-gray-800 leading-snug">${n.titulo}</p>
                    ${unread ? '<span class="notif-unread-dot w-2 h-2 rounded-full bg-blue-500 shrink-0 mt-1"></span>' : ""}
                </div>
                <p class="text-xs text-gray-500 mt-0.5 line-clamp-2">${n.mensaje}</p>
                <div class="flex items-center gap-3 mt-1">
                    <span class="text-[10px] text-gray-400">${timeAgo}</span>
                    ${n.ticket_rma ? `
                        <button type="button" class="notif-ticket-link text-[10px] font-bold text-blue-500 hover:text-blue-700 hover:underline"
                            data-ticket-id="${n.ticket_id}" data-notif-id="${n.id}">
                            Ver ${n.ticket_rma} →
                        </button>` : ""}
                </div>
            </div>
            <button type="button" class="notif-dismiss-btn opacity-0 group-hover:opacity-100 transition text-gray-300 hover:text-red-400 text-base leading-none shrink-0 mt-0.5"
                data-notif-id="${n.id}" title="Descartar">×</button>
        </div>`;
}

function _timeAgo(date) {
    const diff = Math.floor((Date.now() - date) / 1000);
    if (diff < 60)    return "Ahora mismo";
    if (diff < 3600)  return `Hace ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `Hace ${Math.floor(diff / 3600)} h`;
    return `Hace ${Math.floor(diff / 86400)} días`;
}
