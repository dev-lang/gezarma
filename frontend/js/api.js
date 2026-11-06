/**
 * api.js — All HTTP calls to the backend.
 */
const api = {
    baseUrl: "/",

    async request(endpoint, options = {}) {
        const token = localStorage.getItem("token");
        const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
        if (token) headers["Authorization"] = `Bearer ${token}`;
        const res = await fetch(this.baseUrl + endpoint.replace(/^\//, ""), { ...options, headers });
        if (!res.ok) {
            // Expired/invalid token or disabled account → back to login
            if (res.status === 401 && token && typeof auth !== "undefined") {
                auth.logout();
            }
            let msg = `Error ${res.status}`;
            try { const d = await res.json(); msg = d.detail || msg; } catch {}
            throw new Error(msg);
        }
        if (res.status === 204) return null;
        const ct = res.headers.get("content-type") || "";
        if (ct.includes("application/json")) return res.json();
        return res.blob();   // for file downloads
    },

    // ── Auth ──────────────────────────────────────────────────────────────────
    login(username, password) {
        const body = new URLSearchParams({ username, password });
        return fetch(this.baseUrl + "login", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body,
        }).then(async r => {
            if (!r.ok) { const d = await r.json(); throw new Error(d.detail || "Error al iniciar sesión"); }
            return r.json();
        });
    },
    register(data) { return this.request("register", { method: "POST", body: JSON.stringify(data) }); },

    // ── Tickets ───────────────────────────────────────────────────────────────
    getTickets(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this.request(`tickets/${qs ? "?" + qs : ""}`);
    },
    getTicket(id)       { return this.request(`tickets/${id}`); },
    createTicket(data)  { return this.request("tickets/", { method: "POST", body: JSON.stringify(data) }); },

    // Feature 3: edit core fields
    editTicketFields(id, data) {
        return this.request(`tickets/${id}/fields`, { method: "PATCH", body: JSON.stringify(data) });
    },
    updateTicketStatus(id, estado) {
        return this.request(`tickets/${id}/status`, { method: "PUT", body: JSON.stringify({ estado }) });
    },
    assignTechnician(id, tecnico_id) {
        return this.request(`tickets/${id}/assign`, { method: "PUT", body: JSON.stringify({ tecnico_id }) });
    },
    updateShipping(id, data) {
        return this.request(`tickets/${id}/shipping`, { method: "PUT", body: JSON.stringify(data) });
    },
    updateDiagnostic(id, diagnostico) {
        return this.request(`tickets/${id}/diagnostic`, { method: "PUT", body: JSON.stringify({ diagnostico }) });
    },
    getDashboardStats()  { return this.request("tickets/stats/dashboard"); },
    searchGlobal(q)      { return this.request(`tickets/search/global?q=${encodeURIComponent(q)}`); },

    // Feature 4: tags
    addTag(ticketId, tag_nombre)   { return this.request(`tickets/${ticketId}/tags`, { method: "POST", body: JSON.stringify({ tag_nombre }) }); },
    setTags(ticketId, tag_nombres) { return this.request(`tickets/${ticketId}/tags`, { method: "PUT",  body: JSON.stringify({ tag_nombres }) }); },
    removeTag(ticketId, tag_nombre){ return this.request(`tickets/${ticketId}/tags/${encodeURIComponent(tag_nombre)}`, { method: "DELETE" }); },

    // Feature 9: full history
    getTicketHistory(id) { return this.request(`tickets/${id}/history`); },

    // Feature 11: clone + relation
    cloneTicket(id, relacionar = true) {
        return this.request(`tickets/${id}/clone`, { method: "POST", body: JSON.stringify({ relacionar }) });
    },
    setTicketRelation(id, ticket_relacionado_id) {
        return this.request(`tickets/${id}/relation`, { method: "PATCH", body: JSON.stringify({ ticket_relacionado_id }) });
    },

    // Parts / Attachments
    addPart(ticketId, part_id, cantidad)  { return this.request(`tickets/${ticketId}/parts`, { method: "POST", body: JSON.stringify({ part_id, cantidad }) }); },
    updateTicketPart(ticketId, partId, cantidad) { return this.request(`tickets/${ticketId}/parts/${partId}`, { method: "PATCH", body: JSON.stringify({ cantidad }) }); },
    removeTicketPart(ticketId, partId)   { return this.request(`tickets/${ticketId}/parts/${partId}`, { method: "DELETE" }); },
    getAttachments(ticketId) { return this.request(`tickets/${ticketId}/attachments`); },
    uploadAttachment(ticketId, file) {
        const form = new FormData();
        form.append('file', file);
        const token = localStorage.getItem('token');
        return fetch(`${this.baseUrl}tickets/${ticketId}/attachments`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: form,
        }).then(async r => {
            if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || 'Error al subir archivo'); }
            return r.json();
        });
    },
    // Downloads with the Authorization header (the token never goes in the URL)
    async downloadAttachment(ticketId, adjId, filename) {
        const token = localStorage.getItem('token');
        const res = await fetch(`${this.baseUrl}tickets/${ticketId}/attachments/${adjId}/download`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (!res.ok) {
            if (res.status === 401 && typeof auth !== 'undefined') auth.logout();
            const d = await res.json().catch(() => ({}));
            throw new Error(d.detail || 'Error al descargar el archivo');
        }
        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);
        const link = Object.assign(document.createElement('a'), { href: url, download: filename || 'archivo' });
        document.body.appendChild(link); link.click();
        document.body.removeChild(link); URL.revokeObjectURL(url);
    },
    deleteAttachment(ticketId, adjId) {
        return this.request(`tickets/${ticketId}/attachments/${adjId}`, { method: 'DELETE' });
    },

    // ── Comments ──────────────────────────────────────────────────────────────
    addComment(ticketId, text, isInternal = false) {
        return this.request(`tickets/${ticketId}/comments/`, {
            method: "POST",
            body: JSON.stringify({ comentario: text, is_internal: isInternal }),
        });
    },
    getComments(ticketId) { return this.request(`tickets/${ticketId}/comments/`); },

    // ── Users ────────────────────────────────────────────────────────────────
    getUsers()           { return this.request("users/"); },
    getTecnicos()        { return this.request("users/tecnicos"); },
    updateUser(id, data) { return this.request(`users/${id}`, { method: "PATCH", body: JSON.stringify(data) }); },
    updateUserProfile(id, data) { return this.request(`users/${id}/profile`, { method: "PATCH", body: JSON.stringify(data) }); },
    deleteUser(id)       { return this.request(`users/${id}`, { method: "DELETE" }); },
    resetUserPassword(id){ return this.request(`users/${id}/reset-password`, { method: "POST" }); },

    // ── Products ─────────────────────────────────────────────────────────────
    getProducts()                { return this.request("products/"); },
    createProduct(data)          { return this.request("products/",    { method: "POST",   body: JSON.stringify(data) }); },
    updateProduct(id, data)      { return this.request(`products/${id}`, { method: "PUT",  body: JSON.stringify(data) }); },
    deleteProduct(id)            { return this.request(`products/${id}`, { method: "DELETE" }); },

    // ── Parts / Repuestos ─────────────────────────────────────────────────────
    getParts()               { return this.request("parts/"); },
    createPart(data)         { return this.request("parts/",    { method: "POST",   body: JSON.stringify(data) }); },
    updatePart(id, data)     { return this.request(`parts/${id}`, { method: "PUT",  body: JSON.stringify(data) }); },
    deletePart(id)           { return this.request(`parts/${id}`, { method: "DELETE" }); },

    // ── Tags ──────────────────────────────────────────────────────────────────
    getTags()              { return this.request("tags/"); },
    createTag(data)        { return this.request("tags/",    { method: "POST",   body: JSON.stringify(data) }); },
    updateTag(id, data)    { return this.request(`tags/${id}`, { method: "PATCH", body: JSON.stringify(data) }); },
    deleteTag(id)          { return this.request(`tags/${id}`, { method: "DELETE" }); },

    // ── Stock ─────────────────────────────────────────────────────────────────
    getStockHistory(repuestoId = null) {
        const qs = repuestoId ? `?repuesto_id=${repuestoId}` : "";
        return this.request(`stock/history${qs}`);
    },
    updateStockMov(id, nota) { return this.request(`stock/${id}`, { method: "PATCH", body: JSON.stringify({ nota }) }); },
    deleteStockMov(id)       { return this.request(`stock/${id}`, { method: "DELETE" }); },
    reponerStock(repuestoId, cantidad, nota = "") {
        const qs = `?repuesto_id=${repuestoId}&cantidad=${cantidad}&nota=${encodeURIComponent(nota)}`;
        return this.request(`stock/reposicion${qs}`, { method: "POST" });
    },

    // ── Config: plantillas + estados ────────────────────────────────────────
    getPlantillas()          { return this.request('config/plantillas'); },
    createPlantilla(data)    { return this.request('config/plantillas', { method: 'POST', body: JSON.stringify(data) }); },
    updatePlantilla(id, data){ return this.request(`config/plantillas/${id}`, { method: 'PATCH', body: JSON.stringify(data) }); },
    deletePlantilla(id)      { return this.request(`config/plantillas/${id}`, { method: 'DELETE' }); },

    getEstadosConfig()       { return this.request('config/estados'); },
    createEstado(data)       { return this.request('config/estados', { method: 'POST', body: JSON.stringify(data) }); },
    updateEstado(id, data)   { return this.request(`config/estados/${id}`, { method: 'PATCH', body: JSON.stringify(data) }); },
    deleteEstado(id)         { return this.request(`config/estados/${id}`, { method: 'DELETE' }); },

    // ── Users: reset password, profile ──────────────────────────────────────
    resetPassword(userId)  { return this.request(`users/${userId}/reset-password`, { method: "POST" }); },
    changePassword(currentPw, newPw) { return this.request("users/change-password", { method: "POST", body: JSON.stringify({ current_password: currentPw, new_password: newPw }) }); },

    // ── Tickets: edit fields, clone, relation ─────────────────────────────
    editTicketFields(id, data)   { return this.request(`tickets/${id}/fields`, { method: "PATCH", body: JSON.stringify(data) }); },
    setTicketRelation(id, relId) { return this.request(`tickets/${id}/relation`, { method: "PATCH", body: JSON.stringify({ ticket_relacionado_id: relId }) }); },

    // ── Stock: edit/delete movement ───────────────────────────────────────
    updateStockMovimiento(id, nota) { return this.request(`stock/history/${id}`, { method: "PATCH", body: JSON.stringify({ nota }) }); },
    deleteStockMovimiento(id)       { return this.request(`stock/history/${id}`, { method: "DELETE" }); },

    // ── Exports (Feature 2) ───────────────────────────────────────────────────
    async downloadExport(tipo, formato = "csv") {
        const token = localStorage.getItem("token");
        const res   = await fetch(`${this.baseUrl}export/${tipo}?formato=${formato}`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!res.ok) throw new Error("Error al exportar");
        const blob = await res.blob();
        const ext  = formato === "xlsx" ? "xlsx" : "csv";
        const url  = URL.createObjectURL(blob);
        const link = Object.assign(document.createElement("a"), {
            href: url,
            download: `${tipo}_${new Date().toISOString().split("T")[0]}.${ext}`,
        });
        document.body.appendChild(link); link.click();
        document.body.removeChild(link); URL.revokeObjectURL(url);
    },

    // ── Security / Rate limit ─────────────────────────────────────────────────
    getConfigSistema()              { return this.request("config/sistema"); },
    updateConfigSistema(clave, val) { return this.request(`config/sistema/${clave}`, { method: "PUT", body: JSON.stringify({ valor: String(val) }) }); },
    getLoginAttempts()              { return this.request("config/login-attempts/stats"); },
    clearLoginAttempts(ip)          { return this.request(`config/login-attempts${ip ? "?ip=" + ip : ""}`, { method: "DELETE" }); },

    // ── Budget / Presupuesto ──────────────────────────────────────────────────
    getPresupuesto(ticketId)        { return this.request(`budget/tickets/${ticketId}/presupuesto`); },
    createPresupuesto(ticketId, d)  { return this.request(`budget/tickets/${ticketId}/presupuesto`, { method: "POST", body: JSON.stringify(d) }); },
    updatePresupuesto(ticketId, d)  { return this.request(`budget/tickets/${ticketId}/presupuesto`, { method: "PATCH", body: JSON.stringify(d) }); },
    deletePresupuesto(ticketId)     { return this.request(`budget/tickets/${ticketId}/presupuesto`, { method: "DELETE" }); },
    updateEstadoPresupuesto(ticketId, estado) {
        return this.request(`budget/tickets/${ticketId}/presupuesto/estado`, { method: "PATCH", body: JSON.stringify({ estado }) });
    },
    getVersionesPresupuesto(ticketId) { return this.request(`budget/tickets/${ticketId}/presupuesto/versiones`); },

    // ── Budget Templates ──────────────────────────────────────────────────────
    getPlantillasPresupuesto()      { return this.request("budget/plantillas"); },
    createPlantillaPresupuesto(d)   { return this.request("budget/plantillas", { method: "POST", body: JSON.stringify(d) }); },
    updatePlantillaPresupuesto(id, d) { return this.request(`budget/plantillas/${id}`, { method: "PATCH", body: JSON.stringify(d) }); },
    deletePlantillaPresupuesto(id)  { return this.request(`budget/plantillas/${id}`, { method: "DELETE" }); },

    // ── Favorites ─────────────────────────────────────────────────────────────
    getFavorites()              { return this.request("favorites/"); },
    addFavorite(ticketId)       { return this.request(`favorites/${ticketId}`, { method: "POST" }); },
    removeFavorite(ticketId)    { return this.request(`favorites/${ticketId}`, { method: "DELETE" }); },

    // ── Notifications ─────────────────────────────────────────────────────────
    getNotifications(all = false) { return this.request(`notifications/${all ? "?all=true" : ""}`); },
    getUnreadCount()              { return this.request("notifications/unread-count"); },
    markNotificationsRead(ids=[]) { return this.request("notifications/mark-read", { method: "POST", body: JSON.stringify({ ids }) }); },
    deleteNotification(id)        { return this.request(`notifications/${id}`, { method: "DELETE" }); },

    // ── Financial Stats ───────────────────────────────────────────────────────
    getFinancialStats()             { return this.request("budget/stats/financiero"); },
};
