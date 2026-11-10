/**
 * ui.js — Section management, data loading, and DOM orchestration.
 * Render logic lives in js/ui/components.js
 * Feedback (toasts, confirms, skeletons) live in js/ui/
 */
const ui = {
    // ── Dark mode ──────────────────────────────────────────────────────────────
    initDarkMode() {
        // 'gezatek-dark' es la clave anterior al cambio de nombre: se sigue leyendo
        const isDark = (localStorage.getItem('gezarma-dark') ?? localStorage.getItem('gezatek-dark')) === '1';
        document.documentElement.classList.toggle('dark', isDark);
        document.getElementById('icon-sun')?.classList.toggle('hidden', !isDark);
        document.getElementById('icon-moon')?.classList.toggle('hidden', isDark);
    },
    toggleDark() {
        const html = document.documentElement;
        const nowDark = html.classList.toggle('dark');
        localStorage.setItem('gezarma-dark', nowDark ? '1' : '0');
        document.getElementById('icon-sun')?.classList.toggle('hidden', !nowDark);
        document.getElementById('icon-moon')?.classList.toggle('hidden', nowDark);
    },

    currentTicketId: null,
    _partsCache: [],   // local cache for editPartForm

    // ── Section / partial loading ──────────────────────────────────────────

    async loadPartial(name) {
        const res = await fetch(`/partials/${name}.html`);
        // Sin esto, un 404/500 se inyectaba como si fuera la pantalla
        if (!res.ok) throw new Error(`No se pudo cargar la pantalla (${res.status})`);
        return res.text();
    },

    async showSection(name) {
        if (name !== 'detail') this.currentTicketId = null;   // las cargas pendientes del detalle se descartan
        const root = document.getElementById('app-root');
        const navbar = document.getElementById('navbar');

        const authlessPartials = ['login', 'register'];

        if (authlessPartials.includes(name)) {
            root.innerHTML = await this.loadPartial(name);
            navbar.classList.add('hidden');
        } else {
            root.innerHTML = await this.loadPartial(name);
            // Modals are shared — inject once into body
            if (!document.getElementById('ticket-modal')) {
                const modals = await this.loadPartial('modals');
                document.body.insertAdjacentHTML('beforeend', modals);
            }
            if (auth.isLoggedIn()) navbar.classList.remove('hidden');
        }

        // Re-bind all event listeners after injecting new HTML
        app.bindEvents();
    },

    // ── Dashboard ──────────────────────────────────────────────────────────

    async initDashboard() {
        const user = auth.getUser();
        if (!user) return;

        await this.showSection('dashboard');

        const ROLES = { cliente: 'Cliente', tecnico: 'Técnico', administrador: 'Administrador' };
        const quien = `${user.nombre || user.username || user.sub} (${I18N.t(ROLES[user.role] || user.role)})`;
        document.getElementById('user-info').innerText = quien;
        const enMenu = document.getElementById('user-info-menu');
        if (enMenu) enMenu.innerHTML = `<span translate="no">${esc(user.nombre || user.username || '')}</span>
            <span class="block text-xs font-normal text-gray-500"><span translate="no">${esc(user.username || '')}</span> · ${esc(I18N.t(ROLES[user.role] || user.role))}</span>`;
        const nombreBarra = document.getElementById('user-nombre-barra');
        if (nombreBarra) nombreBarra.textContent = user.nombre || user.username || '';
        const rolBarra = document.getElementById('user-rol-barra');
        if (rolBarra) rolBarra.textContent = I18N.t(ROLES[user.role] || user.role);
        const iniciales = document.getElementById('user-iniciales');
        if (iniciales) iniciales.textContent = (user.nombre || user.username || '?').split(/\s+/).slice(0, 2).map(p => p[0]).join('').toUpperCase();
        document.getElementById('role-badge').innerText = I18N.t('Rol: {0}', I18N.t(ROLES[user.role] || user.role));
        document.getElementById('search-container').classList.remove('hidden');

        const isAdmin    = user.role === 'administrador';
        const isTechOrAdmin = isAdmin || user.role === 'tecnico';
        const adminBtn = document.getElementById('admin-panel-btn');
        if (adminBtn) {
            adminBtn.classList.toggle('hidden', !isAdmin);
            adminBtn.classList.toggle('flex', isAdmin);
        }
        const favBtn = document.getElementById('favorites-nav-btn');
        if (favBtn) {
            favBtn.classList.toggle('hidden', !isTechOrAdmin);
            favBtn.classList.toggle('flex', isTechOrAdmin);
        }
        document.getElementById('advanced-stats')?.classList.toggle('hidden', !isAdmin);
        const horasBtn = document.getElementById('horas-btn');
        if (horasBtn) {
            horasBtn.classList.toggle('hidden', !isTechOrAdmin);
            horasBtn.classList.toggle('flex', isTechOrAdmin);
        }
        document.getElementById('menu-horas')?.classList.toggle('hidden', !isTechOrAdmin);
        const extBtn = document.getElementById('externos-btn');
        if (extBtn) {
            extBtn.classList.toggle('hidden', !isTechOrAdmin);
            extBtn.classList.toggle('flex', isTechOrAdmin);
            if (isTechOrAdmin && typeof Envios !== 'undefined') Envios.contador();
        }
        document.getElementById('menu-horas')?.classList.toggle('flex', isTechOrAdmin);
        const mostradorBtn = document.getElementById('mostrador-btn');
        if (mostradorBtn) {
            mostradorBtn.classList.toggle('hidden', !isTechOrAdmin);
            mostradorBtn.classList.toggle('flex', isTechOrAdmin);
        }

        try {
            const pub = await api.request('config/ajustes/publicos');
            components.setSlaAvisoHoras(pub.sla_aviso_horas);
        } catch { /* se usa el valor por defecto */ }
        if (isAdmin) this.loadAdvancedStats();
        if (isAdmin && typeof Guia !== 'undefined') Guia.cargar();
        if (isTechOrAdmin && typeof Alertas !== 'undefined') Alertas.cargar();
        if (isTechOrAdmin && typeof Encuesta !== 'undefined') Encuesta.panel();
        if (user.role === 'cliente' && typeof Portal !== 'undefined') Portal.cargar();
        if (typeof Tiempo !== 'undefined') { Tiempo.chip(); if (isAdmin) Tiempo.panel(); }
        else document.getElementById('alertas-panel')?.classList.add('hidden');
        this.loadTickets();
        if (typeof Kanban !== 'undefined') Kanban.iniciar(isTechOrAdmin);
        if (typeof Documentos !== 'undefined') Documentos.abrirDesdeHash();
    },

    // ── Ticket list ────────────────────────────────────────────────────────

    // Estado de la lista: filtro por estado, orden, página y densidad (se conserva al volver al panel)
    _lista: { status: '', orden: 'fecha_desc', pagina: 0, porPagina: 50, total: 0 },
    _estadosOrden: null,

    _columnasLista() {
        return ['administrador', 'tecnico'].includes(auth.getUser()?.role) ? components.COLS_TALLER : components.COLS_CLIENTE;
    },

    async loadTickets(filters) {
        const L = this._lista;
        if (filters && 'status' in filters) { L.status = filters.status || ''; L.pagina = 0; }
        const cols = this._columnasLista();
        this._bindLista();
        const head = document.getElementById('ticket-list-head');
        if (head) head.innerHTML = components.ticketHead(cols, L.orden);
        const tbody = document.getElementById('ticket-list-body');
        if (tbody?.querySelector('tr[data-ticket-id]')) tbody.classList.add('opacity-60');      // ordenar o paginar: sin parpadeo
        else skeleton.tableRows('ticket-list-body', 6, cols.length);
        if (document.getElementById('stats-container') && !document.getElementById('stats-container').children.length) skeleton.cards('stats-container', 4);
        try {
            const params = { skip: L.pagina * L.porPagina, limit: L.porPagina, orden: L.orden };
            if (L.status) params.status = L.status;
            const { items, total } = await api.getTicketsPagina(params);
            L.total = total;
            if (!items.length && L.pagina > 0) { L.pagina = 0; return this.loadTickets(); }
            tbody?.classList.remove('opacity-60');
            this.renderTicketList(items, !!L.status);
            this._renderPaginas();
            // Totales reales (no solo los de esta página) y contadores de los filtros
            api.request('tickets/stats/resumen').then(r => { this.renderStats(r); this._renderChips(r); }).catch(() => {});
        } catch (err) {
            toast.error('Error al cargar los tickets.');
            console.error(err);
        }
    },

    renderTicketList(tickets, filtered = false) {
        const tbody = document.getElementById('ticket-list-body');
        if (!tbody) return;
        const cols = this._columnasLista();
        tbody.innerHTML = tickets.length
            ? tickets.map(t => components.ticketRow(t, cols)).join('')
            : components.ticketEmptyState(filtered);
    },

    async _renderChips(r) {
        const cont = document.getElementById('ticket-chips');
        if (!cont) return;
        if (!this._estadosOrden) {
            try { this._estadosOrden = (await api.getEstadosConfig()).sort((a, b) => a.orden - b.orden).map(e => e.valor); }
            catch { this._estadosOrden = []; }
        }
        const por = r.por_estado || {}, L = this._lista;
        const estados = [...this._estadosOrden, ...Object.keys(por).filter(e => !this._estadosOrden.includes(e))]
            .filter(e => por[e] || e === L.status);
        const chip = (valor, texto, n) => {
            const on = (L.status || '') === valor;
            return `<button type="button" data-estado="${esc(valor)}" aria-pressed="${on}"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border transition
                ${on ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'}">
                <span>${esc(texto)}</span><span class="text-xs tabular-nums ${on ? 'text-blue-100' : 'text-gray-400'}">${n || 0}</span></button>`;
        };
        cont.innerHTML = chip('', 'Todos', r.total) + estados.map(e => chip(e, e, por[e])).join('');
    },

    _renderPaginas() {
        const el = document.getElementById('ticket-paginas');
        if (!el) return;
        const L = this._lista;
        if (L.total <= 25) { el.classList.add('hidden'); el.innerHTML = ''; return; }
        const desde = L.pagina * L.porPagina + 1, hasta = Math.min(L.total, (L.pagina + 1) * L.porPagina);
        const ultima = Math.max(0, Math.ceil(L.total / L.porPagina) - 1);
        const btn = (dir, texto, off) => `<button type="button" data-pagina="${dir}" ${off ? 'disabled' : ''}
            class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-gray-200 bg-white font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">${texto}</button>`;
        el.innerHTML = `
            <span class="tabular-nums">${esc(I18N.t('Mostrando {0}–{1} de {2}', desde, hasta, L.total))}</span>
            <div class="flex items-center gap-2">
                <select data-por-pagina class="border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-sm" aria-label="${esc(I18N.t('Tickets por página'))}">
                    ${[25, 50, 100].map(n => `<option value="${n}" ${n === L.porPagina ? 'selected' : ''}>${esc(I18N.t('{0} por página', n))}</option>`).join('')}
                </select>
                ${btn(-1, icono('abajo', 'w-4 h-4 rotate-90') + esc(I18N.t('Anterior')), L.pagina === 0)}
                ${btn(1, esc(I18N.t('Siguiente')) + icono('abajo', 'w-4 h-4 -rotate-90'), L.pagina >= ultima)}
            </div>`;
        el.classList.remove('hidden');
    },

    // Los controles de la lista se conectan una vez por cada vez que se dibuja el panel
    _bindLista() {
        const wrap = document.getElementById('ticket-list-wrap');
        if (!wrap || wrap.dataset.conectada) return;
        wrap.dataset.conectada = '1';
        const L = this._lista;
        const tabla = document.getElementById('ticket-tabla');
        let compacta = false;
        try { compacta = localStorage.getItem('gezarma-densidad') === 'compacta'; } catch { /* sin almacenamiento */ }
        const densidad = document.getElementById('ticket-densidad');
        const pintarDensidad = () => { tabla?.classList.toggle('compacta', compacta); densidad?.setAttribute('aria-pressed', String(compacta));
            densidad?.classList.toggle('text-blue-700', compacta); densidad?.classList.toggle('border-blue-300', compacta); };
        pintarDensidad();
        densidad?.addEventListener('click', () => {
            compacta = !compacta; pintarDensidad();
            try { localStorage.setItem('gezarma-densidad', compacta ? 'compacta' : 'normal'); } catch { /* sin almacenamiento */ }
        });
        document.getElementById('ticket-chips')?.addEventListener('click', e => {
            const b = e.target.closest('[data-estado]');
            if (b) this.loadTickets({ status: b.dataset.estado });
        });
        wrap.addEventListener('click', e => {
            const orden = e.target.closest('[data-orden]');
            if (orden) {
                const campo = orden.dataset.orden, [actual, sentido] = L.orden.split('_');
                const porDefecto = ['fecha', 'dias', 'prioridad'].includes(campo) ? 'desc' : 'asc';
                L.orden = `${campo}_${campo === actual ? (sentido === 'asc' ? 'desc' : 'asc') : porDefecto}`;
                L.pagina = 0;
                return this.loadTickets();
            }
            const pag = e.target.closest('[data-pagina]');
            if (pag) { L.pagina = Math.max(0, L.pagina + Number(pag.dataset.pagina)); wrap.scrollIntoView({ block: 'start', behavior: 'smooth' }); return this.loadTickets(); }
            const fila = e.target.closest('tr[data-ticket-id]');
            if (fila && !e.target.closest('a,button,input,select')) app.viewTicket(Number(fila.dataset.ticketId));
        });
        wrap.addEventListener('change', e => {
            if (e.target.matches('[data-por-pagina]')) { L.porPagina = Number(e.target.value); L.pagina = 0; this.loadTickets(); }
        });
        wrap.addEventListener('keydown', e => {
            const fila = e.target.closest?.('tr[data-ticket-id]');
            if (fila && (e.key === 'Enter' || e.key === ' ') && e.target === fila) { e.preventDefault(); app.viewTicket(Number(fila.dataset.ticketId)); }
        });
    },

    renderStats(r) {
        const container = document.getElementById('stats-container');
        if (!container) return;
        const stats = { total: r.total, nuevos: r.nuevos, proceso: r.en_proceso, cerrados: r.cerrados };
        container.innerHTML = [
            { label: 'Total Tickets',  value: stats.total,   color: 'blue',   icon: 'ticket' },
            { label: 'Nuevos',         value: stats.nuevos,  color: 'amber',  icon: 'new'    },
            { label: 'En Proceso',     value: stats.proceso, color: 'indigo', icon: 'wrench' },
            { label: 'Cerrados',       value: stats.cerrados,color: 'green',  icon: 'check'  },
        ].map(components.statCard).join('');
    },

    _renderTicketTags(tags, removable = false) {
        const el = document.getElementById('detail-tags');
        if (!el) return;
        if (!tags.length) {
            el.innerHTML = '<span class="text-[10px] text-gray-300 italic">Sin etiquetas</span>';
            return;
        }
        el.innerHTML = tags.map(t => components.tagBadge(t, removable)).join('');
        if (removable) {
            el.querySelectorAll('.tag-remove-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const ticketId = ui.currentTicketId, nombre = btn.dataset.nombre;
                    const refrescar = async () => {
                        if (ui.currentTicketId !== ticketId) return;
                        const updated = await api.getTicket(ticketId);
                        ui._renderTicketTags(updated.tags || [], true);
                    };
                    try {
                        await api.removeTag(ticketId, nombre);
                        await refrescar();
                        toast.deshacer('Etiqueta quitada.', async () => { await api.addTag(ticketId, nombre); await refrescar(); });
                    } catch(e) { toast.error(e.message); }
                });
            });
        }
    },

    // ── Detail: load tags into ef-add-tag ────────────────────────────────────
    async loadTagsIntoDetail() {
        try {
            const tags = await api.getTags();
            const sel  = document.getElementById('ef-add-tag');
            if (sel) {
                sel.innerHTML = '<option value="">Agregar etiqueta...</option>' +
                    tags.map(t => `<option value="${esc(t.nombre)}" style="color:${colorSeguro(t.color)}">${esc(t.nombre)}</option>`).join('');
            }
        } catch {}
    },

    // ── Ticket detail ──────────────────────────────────────────────────────

    async showTicketDetail(ticket) {
        this.currentTicketId = ticket.id;
        await this.showSection('detail');
        if (this.currentTicketId !== ticket.id) return;   // se abrió otro mientras cargaba

        document.getElementById('detail-rma-id').innerText  = ticket.numero_rma;
        document.getElementById('detail-product').innerText = ticket.producto;
        document.getElementById('detail-serial').innerText  = ticket.numero_serie;
        document.getElementById('detail-compra').innerText  = new Date(ticket.fecha_compra).toLocaleDateString(I18N.locale);
        document.getElementById('detail-priority').innerText = ticket.prioridad;
        document.getElementById('detail-tecnico').innerText = ticket.tecnico_nombre || 'Sin asignar';
        document.getElementById('detail-description').innerText = ticket.descripcion;

        // ── Favourite star ────────────────────────────────────────────────────
        const favBtn  = document.getElementById('fav-btn');
        const userRole = auth.getUser()?.role || '';
        if (favBtn && (userRole === 'administrador' || userRole === 'tecnico')) {
            favBtn.classList.remove('hidden');
            const setFavUI = isFav => {
                favBtn.innerHTML = icono('estrella', 'w-6 h-6', { relleno: isFav });
                favBtn.dataset.fav = isFav ? '1' : '';
                favBtn.title       = isFav ? 'Quitar de favoritos' : 'Marcar como favorito';
                favBtn.classList.toggle('text-yellow-400', isFav);
                favBtn.classList.toggle('text-gray-300',   !isFav);
            };
            setFavUI(!!ticket.es_favorito);
            favBtn.onclick = async () => {
                try {
                    const isFav = favBtn.dataset.fav === '1';
                    if (isFav) {
                        await api.removeFavorite(ticket.id);
                        setFavUI(false);
                        toast.success('Quitado de favoritos.');
                    } else {
                        await api.addFavorite(ticket.id);
                        setFavUI(true);
                        toast.success('Agregado a favoritos.');
                    }
                } catch (err) { toast.error(err.message); }
            };
        } else if (favBtn) {
            favBtn.classList.add('hidden');
        }

        // ── Two-tab: Datos del Ticket / Datos del Cliente ─────────────────────
        const switchDetailTab = (tab) => {
            const isTicket = tab === 'ticket';
            document.getElementById('ticket-data-panel')?.classList.toggle('hidden', !isTicket);
            document.getElementById('client-data-panel')?.classList.toggle('hidden', isTicket);
            const btnTicket = document.getElementById('tab-ticket-data');
            const btnClient = document.getElementById('tab-client-data');
            if (btnTicket) {
                btnTicket.classList.toggle('border-blue-600', isTicket);
                btnTicket.classList.toggle('text-blue-600',   isTicket);
                btnTicket.classList.toggle('font-bold',        isTicket);
                btnTicket.classList.toggle('border-transparent', !isTicket);
                btnTicket.classList.toggle('text-gray-500',    !isTicket);
                btnTicket.classList.toggle('font-normal',      !isTicket);
            }
            if (btnClient) {
                btnClient.classList.toggle('border-blue-600', !isTicket);
                btnClient.classList.toggle('text-blue-600',   !isTicket);
                btnClient.classList.toggle('font-bold',        !isTicket);
                btnClient.classList.toggle('border-transparent', isTicket);
                btnClient.classList.toggle('text-gray-500',    isTicket);
                btnClient.classList.toggle('font-normal',      isTicket);
            }
        };
        switchDetailTab('ticket');
        document.getElementById('tab-ticket-data')?.addEventListener('click', () => switchDetailTab('ticket'));
        document.getElementById('tab-client-data')?.addEventListener('click',  () => switchDetailTab('client'));

        // ── Populate client tab ────────────────────────────────────────────────
        const rolLabels = { cliente: 'Cliente', tecnico: 'Técnico', administrador: 'Administrador' };
        document.getElementById('client-nombre').innerText    = ticket.usuario_nombre   || '—';
        document.getElementById('client-email').innerText     = ticket.usuario_email    || '—';
        document.getElementById('client-telefono').innerText  = ticket.usuario_telefono || 'Sin registrar';
        document.getElementById('client-rol').innerText       = rolLabels[ticket.usuario_rol] || ticket.usuario_rol || '—';

        // Tags
        const tagsEl = document.getElementById('detail-tags');
        const canEditTags = auth.getUser()?.role !== 'cliente';
        if (tagsEl) tagsEl.dataset.editable = canEditTags ? 'true' : 'false';
        this._renderTicketTags(ticket.tags || [], canEditTags);

        // Status badge
        const badge = document.getElementById('detail-status-badge');
        components.pintarEstado(badge, ticket.estado);

        // Shipping
        const shippingEl = document.getElementById('detail-shipping-container');
        if (ticket.tracking_number) {
            shippingEl.classList.remove('hidden');
            document.getElementById('detail-shipping-company').innerText = ticket.empresa_transporte || 'No especificada';
            document.getElementById('detail-tracking').innerText = ticket.tracking_number;
        } else {
            shippingEl.classList.add('hidden');
        }

        // Parts
        const partsEl = document.getElementById('detail-parts-container');
        if (ticket.repuestos_usados?.length) {
            partsEl.classList.remove('hidden');
            const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
            const role = userInfo.role || '';
            const editable = role === 'administrador' || role === 'tecnico';
            const partsList = document.getElementById('detail-parts-list');
            partsList.dataset.ticketId = ticket.id;
            partsList.dataset.parts = JSON.stringify(ticket.repuestos_usados);
            partsList.innerHTML = ticket.repuestos_usados.map(p => components.partUsed(p, editable)).join('');
            const hint = document.getElementById('parts-edit-hint');
            if (hint) hint.classList.toggle('hidden', !editable);
        } else {
            partsEl.classList.add('hidden');
        }

        // ── Feature 6: Creator badge ──────────────────────────────────────────
        const creatorBadgeEl = document.getElementById('detail-creator-badge');
        if (creatorBadgeEl) {
            if (ticket.usuario_rol) {
                creatorBadgeEl.outerHTML = components.creatorBadge(ticket.usuario_rol);
            } else {
                creatorBadgeEl.classList.add('hidden');
            }
        }

        // ── Feature 11: Clone badge + related ticket ───────────────────────
        const cloneBadgeEl = document.getElementById('detail-clone-badge');
        if (cloneBadgeEl) {
            if (ticket.rma_clonado_de) {
                cloneBadgeEl.textContent = `⎘ Clonado de ${ticket.rma_clonado_de}`;
                cloneBadgeEl.classList.remove('hidden');
            } else { cloneBadgeEl.classList.add('hidden'); }
        }
        if (ticket.reingreso_garantia && cloneBadgeEl) {
            cloneBadgeEl.insertAdjacentHTML('beforebegin',
                `<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800" title="El mismo equipo volvió dentro de la garantía de la reparación">↩ Reingreso en garantía de ${ticket.rma_reingreso_de || 'una reparación anterior'}</span>`);
        }
        const relContainer = document.getElementById('detail-related-container');
        const relLink      = document.getElementById('related-ticket-link');
        const unlinkBtn    = document.getElementById('unlink-related-btn');
        if (relContainer) {
            if (ticket.rma_relacionado) {
                relContainer.classList.remove('hidden');
                if (relLink)   { relLink.textContent = ticket.rma_relacionado; relLink.dataset.rmaId = ticket.ticket_relacionado; }
                if (unlinkBtn) {
                    const canEdit = auth.getUser()?.role !== 'cliente';
                    unlinkBtn.classList.toggle('hidden', !canEdit);
                }
            } else { relContainer.classList.add('hidden'); }
        }

        // ── Feature 3: Edit fields card (tech/admin) ──────────────────────
        const editCard = document.getElementById('edit-fields-card');
        const clientPdf = document.getElementById('client-pdf-btn-wrap');

        // Management panel (tech/admin)
        const user = auth.getUser();
        const mgmtCard = document.getElementById('mgmt-card');
        if (user.role === 'tecnico' || user.role === 'administrador') {
            mgmtCard.classList.remove('hidden');
            if (editCard) { editCard.classList.remove('hidden'); if (clientPdf) clientPdf.classList.add('hidden'); }
            // Load dynamic plantillas for the template buttons
            if (this._plantillasCache.length) this._renderDiagTemplates(this._plantillasCache);
            else this.loadAdminPlantillas();
            // Load dynamic estados for the status select
            if (this._estadosCache.length) this._rebuildStatusSelect(this._estadosCache);
            else this.loadAdminEstados();
            // Show edit description button for tech/admin
            document.getElementById('edit-description-btn')?.classList.remove('hidden');
            document.getElementById('update-status').value    = ticket.estado;
            document.getElementById('update-diagnostic').value = '';
            document.getElementById('update-tags').value       = '';
            // ── Store original values for dirty-checking on save ──────────────
            mgmtCard.dataset.origEstado  = ticket.estado;
            mgmtCard.dataset.origTecnico = ticket.tecnico_asignado ?? '';
            await this.loadPartsSelect();
            this.toggleShippingFields(null);   // se muestra al elegir "Enviado al cliente" (gestion.js)
            const techContainer = document.getElementById('assign-tech-container');
            if (user.role === 'administrador') {
                techContainer.classList.remove('hidden');
                await this.loadTecnicosSelect(ticket.tecnico_asignado);
            } else {
                techContainer.classList.add('hidden');
            }
        } else {
            mgmtCard.classList.add('hidden');
            if (editCard) editCard.classList.add('hidden');
            if (clientPdf) clientPdf.classList.remove('hidden');
        }

        skeleton.list('comment-list', 3);
        skeleton.list('history-list', 2);
        this.loadComments(ticket.id);
        this.loadAttachments(ticket.id);
        this.loadHistory(ticket.id);
        this.switchTab('comments');

        // ── Budget card ──────────────────────────────────────────────────────
        if (typeof Budget !== 'undefined') {
            Budget.initPresupuestoCard(ticket.id, user.role, ticket.producto_id);
        }
        // ── Recepción: checklist, firmas y fotos de ingreso ──────────────────
        if (typeof Recepcion !== 'undefined') Recepcion.cargarDetalle(ticket);
        if (typeof Encuesta !== 'undefined') Encuesta.cargarDetalle(ticket);
        if (typeof Tiempo !== 'undefined') { Tiempo.cargarDetalle(ticket.id); Tiempo.chip(); }
        if (typeof Ubic !== 'undefined') Ubic.cargarDetalle(ticket);
        if (typeof Envios !== 'undefined') Envios.cargarDetalle(ticket);
    },

    // ── Comments / History / Attachments ───────────────────────────────────

    async loadComments(ticketId) {
        try {
            const comments = await api.getComments(ticketId);
            if (ui.currentTicketId != ticketId) return;   // ya se navegó a otro ticket
            document.getElementById('comment-list').innerHTML = comments.length
                ? comments.map(components.comment).join('')
                : components.commentEmptyState();
        } catch (err) { console.error(err); }
    },

    async loadHistory(ticketId) {
        try {
            const history = await api.getTicketHistory(ticketId);
            if (ui.currentTicketId != ticketId) return;
            document.getElementById('history-list').innerHTML = history.length
                ? history.map(components.historyEntry).join('')
                : '<p class="text-gray-400 italic text-sm py-4">Sin cambios registrados.</p>';
        } catch (err) { console.error(err); }
    },

    async loadAttachments(ticketId) {
        try {
            const res = await api.getAttachments(ticketId);
            if (ui.currentTicketId != ticketId) return;
            const atts    = Array.isArray(res) ? res : (res.adjuntos || []);
            const storage = res.storage || null;
            const user    = auth.getUser();
            const role    = user?.role || '';

            const listEl = document.getElementById('attachment-list');
            if (listEl) {
                listEl.innerHTML = atts.length
                    ? atts.map(a => components.attachmentItem(a, ticketId, role)).join('')
                    : '<p class="text-gray-400 italic text-sm py-2">Sin archivos adjuntos.</p>';

                // Wire download buttons
                listEl.querySelectorAll('.adj-download-btn').forEach(btn => {
                    btn.addEventListener('click', async () => {
                        try {
                            await api.downloadAttachment(ticketId, parseInt(btn.dataset.adjId), btn.dataset.filename);
                        } catch (err) { toast.error(err.message); }
                    });
                });

                // Wire delete buttons
                listEl.querySelectorAll('.adj-delete-btn').forEach(btn => {
                    btn.addEventListener('click', async () => {
                        const adjId = parseInt(btn.dataset.adjId);
                        const ok = await confirmDialog(
                            '¿Eliminar archivo?',
                            'El archivo será eliminado permanentemente.',
                            'Eliminar'
                        );
                        if (!ok) return;
                        try {
                            await api.deleteAttachment(ticketId, adjId);
                            toast.success('Archivo eliminado.');
                            this.loadAttachments(ticketId);
                        } catch (err) { toast.error(err.message); }
                    });
                });
            }

            // Update storage bar
            const barWrap = document.getElementById('attachment-storage-bar');
            if (barWrap) {
                barWrap.classList.remove('hidden');
                const used  = storage?.used_mb  ?? 0;
                const limit = storage?.limit_mb ?? 10;
                const pct   = Math.min(100, (used / limit) * 100);
                const labelEl = document.getElementById('attachment-storage-label');
                const fillEl  = document.getElementById('attachment-storage-fill');
                if (labelEl) labelEl.textContent = `${used.toFixed(2)} / ${limit} MB`;
                if (fillEl) {
                    fillEl.style.width = pct + '%';
                    fillEl.className = 'h-1.5 rounded-full transition-all ' +
                        (pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-yellow-500' : 'bg-blue-500');
                }
            }
        } catch (err) { console.error('loadAttachments:', err); }
    },

    switchTab(tab) {
        ['comments', 'history'].forEach(k => {
            const isActive = k === tab;
            document.getElementById(`${k}-container`)?.classList.toggle('hidden', !isActive);
            const btn = document.getElementById(`tab-${k}`);
            if (btn) {
                btn.classList.toggle('border-blue-600', isActive);
                btn.classList.toggle('text-blue-600',   isActive);
                btn.classList.toggle('border-transparent', !isActive);
                btn.classList.toggle('text-gray-500',   !isActive);
            }
        });
    },

    // ── Selects ────────────────────────────────────────────────────────────

    async loadProductsSelect() {
        try {
            const products = await api.request('/products/');
            const select = document.getElementById('tk-producto-id');
            if (!select) return;
            select.innerHTML = '<option value="">Elegí un producto...</option>'
                + products.map(p => `<option value="${p.id}">${esc(p.marca)} ${esc(p.modelo)} (${esc(p.categoria)})</option>`).join('');
        } catch (err) { console.error(err); }
    },

    async loadPartsSelect() {
        try {
            const [parts, tags] = await Promise.all([api.request('/parts/'), api.getTags()]);
            const partSelect = document.getElementById('update-part');
            if (partSelect) {
                partSelect.innerHTML = '<option value="">Ninguno / Sin repuestos</option>'
                    + parts.map(p => `<option value="${p.id}" ${p.stock <= 0 ? 'disabled' : ''}>${esc(p.nombre)} (${p.stock} disp.)</option>`).join('');
            }
            // Populate both tag selects from the same source
            ['update-tags', 'ef-add-tag'].forEach(selId => {
                const sel = document.getElementById(selId);
                if (!sel) return;
                sel.innerHTML = '<option value="">Elegí una etiqueta...</option>'
                    + tags.map(t => `<option value="${esc(t.nombre)}" style="color:${colorSeguro(t.color)}">${esc(t.nombre)}</option>`).join('');
            });
        } catch (err) { console.error(err); }
    },

    async loadTecnicosSelect(currentId) {
        try {
            const techs = await api.getTecnicos();
            const select = document.getElementById('assign-tech');
            if (!select) return;
            select.innerHTML = '<option value="">Sin asignar</option>'
                + techs.map(t => `<option value="${t.id}" ${t.id === currentId ? 'selected' : ''}>${esc(t.nombre)}</option>`).join('');
        } catch (err) { console.error(err); }
    },

    /** Transporte y tracking: solo mientras se está por marcar "Enviado al cliente" (ver gestion.js). */
    toggleShippingFields(status) {
        document.getElementById('shipping-info-fields')?.classList.toggle('hidden', status !== 'Enviado al cliente');
    },

    // ── Users management ───────────────────────────────────────────────────

    _usersCache: [],

    async loadUsers() {
        await this.showSection('users');
        skeleton.tableRows('user-list-body', 4, 6);
        try {
            this._usersCache = await api.getUsers();
            this.renderUsers();
        } catch (err) { toast.error(err.message); }
    },

    renderUsers() {
        const rol    = document.getElementById('user-filter-rol')?.value || '';
        const activo = document.getElementById('user-filter-activo')?.value;
        let users = this._usersCache;
        if (rol)    users = users.filter(u => u.rol === rol);
        if (activo !== '' && activo !== undefined && activo !== null)
            users = users.filter(u => String(u.activo) === activo);
        const tbody = document.getElementById('user-list-body');
        if (tbody) tbody.innerHTML = users.length
            ? users.map(components.userRow).join('')
            : components.vacioFila(6, { icono: 'buscar', titulo: 'No hay usuarios con esos filtros.', chico: true, acciones: [{ texto: 'Limpiar filtros', limpiar: true }] });
    },

    // Los botones "Editar" pasan solo el id (antes iba el usuario entero como JSON
    // dentro del onclick: un nombre con comillas podía romperlo e inyectar código)
    openUserEditModalById(id) {
        const u = [...(this._adminUsersCache || []), ...(this._usersCache || [])].find(x => x.id === id);
        if (u) this.openUserEditModal(u);
    },

    openUserEditModal(u) {
        if (typeof u === 'string') u = JSON.parse(u);
        document.getElementById('user-edit-id').value       = u.id;
        document.getElementById('user-edit-avatar').textContent = u.nombre?.charAt(0)?.toUpperCase() || u.username?.charAt(0)?.toUpperCase();
        document.getElementById('user-edit-username').textContent   = u.username;
        document.getElementById('user-edit-email-display').textContent = u.email || 'Sin email';
        // Populate editable profile fields
        const nombreInput    = document.getElementById('user-edit-nombre');
        const emailInput     = document.getElementById('user-edit-email');
        const telefonoInput  = document.getElementById('user-edit-telefono');
        if (nombreInput)   nombreInput.value   = u.nombre   || '';
        if (emailInput)    emailInput.value    = u.email    || '';
        if (telefonoInput) telefonoInput.value = u.telefono || '';
        // Reset temp password display
        document.getElementById('temp-pw-display')?.classList.add('hidden');
        document.getElementById('temp-pw-value').textContent = '';

        // Set role radio
        const radios = document.querySelectorAll('input[name="user-rol"]');
        radios.forEach(r => { r.checked = r.value === u.rol; });
        this._updateRolDescription(u.rol);

        // Set activo toggle
        this._userEditActivo = u.activo !== false;
        this._updateActivoToggle();

        // Lock admin principal
        const isAdmin = u.username === 'admin';
        radios.forEach(r => r.disabled = isAdmin);
        document.getElementById('toggle-activo-btn').disabled = isAdmin;

        document.getElementById('user-edit-modal').classList.remove('hidden');
    },

    _userEditActivo: true,

    _updateActivoToggle() {
        const btn   = document.getElementById('toggle-activo-btn');
        const knob  = document.getElementById('toggle-activo-knob');
        const label = document.getElementById('activo-label');
        const sub   = document.getElementById('activo-sublabel');
        if (!btn) return;
        if (this._userEditActivo) {
            btn.className  = 'relative inline-flex h-6 w-11 items-center rounded-full transition-colors bg-green-500';
            knob.className = 'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform translate-x-6';
            label.textContent = 'Cuenta habilitada';
            sub.textContent   = 'El usuario puede iniciar sesión';
        } else {
            btn.className  = 'relative inline-flex h-6 w-11 items-center rounded-full transition-colors bg-gray-300';
            knob.className = 'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform translate-x-1';
            label.textContent = 'Cuenta deshabilitada';
            sub.textContent   = 'El usuario no puede iniciar sesión';
        }
    },

    _updateRolDescription(rol) {
        const descs = {
            cliente:       'Puede crear tickets y ver el estado de sus propias solicitudes.',
            tecnico:       'Puede gestionar tickets, cambiar estados y registrar diagnósticos.',
            administrador: 'Acceso total: gestión de usuarios, productos, repuestos y estadísticas.',
        };
        const el = document.getElementById('rol-description');
        if (el) el.textContent = descs[rol] || '';
    },

    // ── Parts management ───────────────────────────────────────────────────

    async loadPartsManagement() {
        await this.showSection('parts');
        skeleton.tableRows('parts-list-body', 4, 6);
        try {
            const parts = await api.getParts();
            this._partsCache = parts;
            document.getElementById('parts-list-body').innerHTML = parts.length
                ? parts.map(components.partRow).join('')
                : components.vacioFila(6, { icono: 'chip', titulo: 'No hay repuestos cargados',
                    texto: 'Cargá los repuestos que usás para descontarlos del stock y presupuestarlos.',
                    acciones: document.getElementById('new-part-btn') ? [{ texto: 'Nuevo repuesto', clic: 'new-part-btn' }] : [] });
        } catch (err) { toast.error(err.message); }
    },

    openNewPartForm() {
        ['part-form-id','part-form-nombre','part-form-codigo','part-form-proveedor'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const stockEl = document.getElementById('part-form-stock');
        const precioEl = document.getElementById('part-form-precio');
        if (stockEl) stockEl.value = '0';
        if (precioEl) precioEl.value = '0';
        const minEl = document.getElementById('part-form-stock-minimo');
        if (minEl) minEl.value = '0';
        document.getElementById('part-form-title').innerText = 'Nuevo Repuesto';
        if (typeof Ubic !== 'undefined') Ubic.llenarSelect('part-form-ubicacion', null);
        document.getElementById('parts-form-modal').classList.remove('hidden');
    },

    async openEditPartForm(id) {
        // Refresh cache if empty (e.g. user navigated directly to parts page)
        if (this._partsCache.length === 0) {
            try {
                this._partsCache = await api.getParts();
            } catch (err) {
                toast.error('No se pudo cargar el repuesto.');
                return;
            }
        }
        const part = this._partsCache.find(p => p.id === id);
        if (!part) {
            toast.error('Repuesto no encontrado.');
            return;
        }
        document.getElementById('part-form-id').value        = part.id;
        document.getElementById('part-form-nombre').value    = part.nombre;
        document.getElementById('part-form-codigo').value    = part.codigo;
        document.getElementById('part-form-proveedor').value = part.proveedor;
        document.getElementById('part-form-stock').value     = part.stock;
        document.getElementById('part-form-precio').value    = part.precio;
        const minEl = document.getElementById('part-form-stock-minimo');
        if (minEl) minEl.value = part.stock_minimo ?? 0;
        document.getElementById('part-form-title').innerText = 'Editar Repuesto';
        if (typeof Ubic !== 'undefined') Ubic.llenarSelect('part-form-ubicacion', part.ubicacion_id);
        document.getElementById('parts-form-modal').classList.remove('hidden');
    },

    // ── Products management ───────────────────────────────────────────────────

    _productsCache: [],

    async loadProducts() {
        await this.showSection('products');
        skeleton.tableRows('product-list-body', 4, 5);
        skeleton.cards('product-category-cards', 4);
        try {
            this._productsCache = await api.getProducts();
            this._buildCategoryFilter();
            this.filterProducts();
        } catch (err) { toast.error(err.message); }
    },

    _buildCategoryFilter() {
        const cats = [...new Set(this._productsCache.map(p => p.categoria))].sort();
        const sel = document.getElementById('product-filter-categoria');
        if (!sel) return;
        sel.innerHTML = '<option value="">Todas las categorías</option>'
            + cats.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');

        const cards = document.getElementById('product-category-cards');
        if (!cards) return;
        const counts = {};
        this._productsCache.forEach(p => { counts[p.categoria] = (counts[p.categoria] || 0) + 1; });
        cards.innerHTML = cats.map(c => components.productCategoryCard(c, counts[c])).join('');
    },

    filterProducts() {
        const q    = (document.getElementById('product-search-input')?.value || '').toLowerCase();
        const cat  = document.getElementById('product-filter-categoria')?.value || '';
        let prods  = this._productsCache;
        if (q)   prods = prods.filter(p => `${p.marca} ${p.modelo} ${p.categoria}`.toLowerCase().includes(q));
        if (cat) prods = prods.filter(p => p.categoria === cat);
        const tbody = document.getElementById('product-list-body');
        if (tbody) tbody.innerHTML = prods.length
            ? prods.map(components.productRow).join('')
            : (this._productsCache?.length
                ? components.vacioFila(5, { icono: 'buscar', titulo: 'No hay productos con esos criterios.', acciones: [{ texto: 'Limpiar filtros', limpiar: true }] })
                : components.vacioFila(5, { icono: 'notebook', titulo: 'Todavía no hay productos', texto: 'Marca, modelo y garantía de lo que reparás.',
                                            acciones: [{ texto: 'Nuevo producto', clic: 'admin-new-product-btn' }] }));
    },

    openNewProductForm() {
        ['product-form-id','product-form-marca','product-form-modelo','product-form-categoria','product-form-nroparte'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const g = document.getElementById('product-form-garantia');
        if (g) g.value = '12';
        document.getElementById('product-form-title').textContent = 'Nuevo Producto';
        document.getElementById('product-form-modal').classList.remove('hidden');
    },

    async openEditProductForm(id) {
        if (this._productsCache.length === 0) {
            try { this._productsCache = await api.getProducts(); } catch { toast.error('No se pudo cargar el producto.'); return; }
        }
        const p = this._productsCache.find(x => x.id === id);
        if (!p) { toast.error('Producto no encontrado.'); return; }
        document.getElementById('product-form-id').value        = p.id;
        document.getElementById('product-form-marca').value     = p.marca;
        document.getElementById('product-form-modelo').value    = p.modelo;
        document.getElementById('product-form-categoria').value = p.categoria;
        document.getElementById('product-form-garantia').value  = p.periodo_garantia_meses;
        document.getElementById('product-form-nroparte').value  = p.numero_parte || '';
        document.getElementById('product-form-title').textContent = 'Editar Producto';
        document.getElementById('product-form-modal').classList.remove('hidden');
    },

    // ── Search page ────────────────────────────────────────────────────────────

    _searchQuery: '',
    _searchFilter: '',
    _searchResults: [],

    async initFavorites() {
        await this.showSection('favorites');
        const container = document.getElementById('fav-list-container');
        try {
            const tickets = await api.getFavorites();
            if (!tickets.length) {
                container.innerHTML = components.vacio({ icono: 'estrella', titulo: 'No tenés tickets favoritos todavía.',
                    texto: 'Marcá un ticket con la estrella para verlo aquí.', acciones: [{ texto: 'Volver al listado', clic: 'back-to-list' }] });
                return;
            }
            container.innerHTML = tickets.map(t => {
                return `
                <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex items-center justify-between gap-4 hover:shadow-md transition cursor-pointer fav-ticket-row"
                     data-ticket-id="${t.id}">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="font-mono font-bold text-blue-700">${esc(t.numero_rma)}</span>
                            ${components.statusBadge(t.estado)}
                        </div>
                        <p class="text-sm text-gray-700 mt-0.5 font-medium truncate">${esc(t.producto)}</p>
                        <p class="text-xs text-gray-400">${esc(t.usuario_nombre || '—')} · ${new Date(t.fecha_creacion).toLocaleDateString(I18N.locale)}</p>
                    </div>
                    <button type="button" class="fav-remove-btn shrink-0 text-yellow-400 hover:text-gray-300 text-2xl transition"
                        data-ticket-id="${t.id}" title="Quitar de favoritos">${icono('estrella', 'w-6 h-6', { relleno: true })}</button>
                </div>`;
            }).join('');

            container.querySelectorAll('.fav-ticket-row').forEach(row => {
                row.addEventListener('click', async e => {
                    if (e.target.closest('.fav-remove-btn')) return;
                    const id = parseInt(row.dataset.ticketId);
                    try {
                        const ticket = await api.getTicket(id);
                        await this.showTicketDetail(ticket);
                    } catch { toast.error('No se pudo cargar el ticket.'); }
                });
            });

            container.querySelectorAll('.fav-remove-btn').forEach(btn => {
                btn.addEventListener('click', async e => {
                    e.stopPropagation();
                    const id = parseInt(btn.dataset.ticketId);
                    try {
                        await api.removeFavorite(id);
                        await this.initFavorites();
                        toast.deshacer('Quitado de favoritos.', async () => { await api.addFavorite(id); await ui.initFavorites(); });
                    } catch (err) { toast.error(err.message); }
                });
            });
        } catch (err) {
            container.innerHTML = `<p class="text-red-400 text-sm text-center py-8">Error al cargar favoritos.</p>`;
        }
    },

    async loadSearchPage(query = '') {
        await this.showSection('search');
        const input = document.getElementById('search-page-input');
        if (input) input.value = query;
        this._searchQuery  = query;
        this._searchFilter = '';
        if (query) await this.runSearch(query);
    },

    async runSearch(q) {
        if (!q || q.length < 2) return;
        this._searchQuery = q;
        const container = document.getElementById('search-results-page');
        if (container) container.innerHTML = Array.from({length:4}).map(() =>
            `<div class="bg-white rounded-xl border p-5"><div class="skeleton h-4 w-48 rounded mb-3"></div><div class="skeleton h-5 w-64 rounded mb-2"></div><div class="skeleton h-3 w-32 rounded"></div></div>`
        ).join('');
        try {
            this._searchResults = await api.searchGlobal(q);
            this.renderSearchResults();
        } catch (err) { toast.error(err.message); }
    },

    renderSearchResults() {
        const f = this._searchFilter;
        const results = f ? this._searchResults.filter(t => t.estado === f) : this._searchResults;
        const count = document.getElementById('search-result-count');
        if (count) count.textContent = `${results.length} resultado${results.length !== 1 ? 's' : ''}`;
        const container = document.getElementById('search-results-page');
        if (!container) return;
        container.innerHTML = results.length
            ? results.map(components.searchResultRow).join('')
            : `<div class="text-center py-16 text-gray-400">
                <svg class="w-12 h-12 mx-auto mb-3 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                </svg>
                <p class="font-semibold">Sin resultados para "${this._searchQuery}"</p>
                <p class="text-sm mt-1">Probá con otro término o eliminá el filtro de estado.</p>
               </div>`;
    },

    // ── Admin panel ────────────────────────────────────────────────────────────

    _adminUsersCache:   [],
    _adminPartsCache:   [],
    _adminProductsCache:[],
    _adminActiveTab: 'users',

    async loadAdminPanel(tab = 'users') {
        await this.showSection('admin');
        this._adminActiveTab = tab;
        this.adminSwitchTab(tab);
        // Load all data in parallel
        const [users, products, parts, stock] = await Promise.allSettled([
            api.getUsers(), api.getProducts(), api.getParts(), api.getStockHistory()
        ]);
        if (users.status === 'fulfilled') {
            this._adminUsersCache = users.value;
            document.getElementById('admin-user-count').textContent = users.value.length;
            this.adminRenderUsers();
        }
        if (products.status === 'fulfilled') {
            this._adminProductsCache = products.value;
            document.getElementById('admin-product-count').textContent = products.value.length;
            this.adminBuildProductCats();
            this.adminRenderProducts();
        }
        if (parts.status === 'fulfilled') {
            this._adminPartsCache = parts.value;
            document.getElementById('admin-parts-count').textContent = parts.value.length;
            this.adminRenderParts();
            this.adminCheckStockAlerts(parts.value);
        }
        if (stock.status === 'fulfilled') {
            this._stockHistoryCache = stock.value;
            this.renderStockHistory(stock.value);
        }
        this.populateStockFilters();
        this.loadAdminTags();
        this.loadAdminPlantillas();
        this.loadAdminEstados();
        this.loadAdminSeguridad();
    },

    adminSwitchTab(tab) {
        this._adminActiveTab = tab;
        document.querySelectorAll('.admin-tab-btn').forEach(btn => {
            const isActive = btn.dataset.tab === tab;
            btn.classList.toggle('active-tab', isActive);
            if (isActive) btn.setAttribute('aria-current', 'page'); else btn.removeAttribute('aria-current');
            if (isActive && window.innerWidth < 1024) btn.scrollIntoView({ block: 'nearest', inline: 'center' });
        });
        document.querySelectorAll('.admin-tab-content').forEach(el => {
            el.classList.toggle('hidden', !el.id.endsWith(tab));
        });
        // Load budget-specific tabs on demand
        if (tab === 'plantillas-presupuesto' && typeof Budget !== 'undefined') {
            Budget.initPlantillasPresupuesto();
        }
        if (tab === 'finanzas' && typeof Budget !== 'undefined') {
            Budget.initFinancialStats();
        }
        if (tab === 'ajustes' && typeof Ajustes !== 'undefined') {
            Ajustes.cargar();
        }
        if (tab === 'pedidos' && typeof Pedidos !== 'undefined') {
            Pedidos.cargar();
        }
        if (tab === 'ubicaciones' && typeof Ubic !== 'undefined') Ubic.cargarAdmin();
        if (tab === 'parts' && typeof Ubic !== 'undefined') { Ubic.conectarRepuestos(); Ubic.filtroRepuestos(); }
    },

    // ── Admin: Users ──────────────────────────────────────────────────────────

    adminRenderUsers() {
        const rol    = document.getElementById('admin-user-filter-rol')?.value || '';
        const activo = document.getElementById('admin-user-filter-activo')?.value;
        let users = this._adminUsersCache;
        if (rol)    users = users.filter(u => u.rol === rol);
        if (activo !== '' && activo !== undefined && activo !== null)
            users = users.filter(u => String(u.activo) === activo);
        const tbody = document.getElementById('admin-user-list-body');
        if (!tbody) return;
        tbody.innerHTML = users.length
            ? users.map(u => components.adminUserRow(u)).join('')
            : components.vacioFila(7, { icono: 'buscar', titulo: 'No hay usuarios con esos filtros.', acciones: [{ texto: 'Limpiar filtros', limpiar: true }] });
    },

    // ── Admin: Products ───────────────────────────────────────────────────────

    adminBuildProductCats() {
        const cats = {};
        this._adminProductsCache.forEach(p => { cats[p.categoria] = (cats[p.categoria]||0)+1; });
        const sel = document.getElementById('admin-product-filter-cat');
        if (sel) {
            sel.innerHTML = '<option value="">Todas las categorías</option>'
                + Object.keys(cats).sort().map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
        }
        const pills = document.getElementById('admin-product-cats');
        if (pills) {
            pills.innerHTML = Object.entries(cats).sort().map(([c,n]) =>
                `<button data-cat="${esc(c)}" onclick="document.getElementById('admin-product-filter-cat').value=this.dataset.cat; ui.adminRenderProducts();"
                    class="px-3 py-1 rounded-full text-xs font-semibold bg-green-50 text-green-700 hover:bg-green-100 transition border border-green-200">
                    ${esc(c)} <span class="opacity-60">${n}</span>
                </button>`
            ).join('') || '<span class="text-xs text-gray-400 italic">Sin categorías</span>';
        }
    },

    adminRenderProducts() {
        const q   = (document.getElementById('admin-product-search')?.value || '').toLowerCase();
        const cat = document.getElementById('admin-product-filter-cat')?.value || '';
        let prods = this._adminProductsCache;
        if (q)   prods = prods.filter(p => `${p.marca} ${p.modelo} ${p.categoria}`.toLowerCase().includes(q));
        if (cat) prods = prods.filter(p => p.categoria === cat);
        const tbody = document.getElementById('admin-product-list-body');
        if (!tbody) return;
        tbody.innerHTML = prods.length
            ? prods.map(p => components.adminProductRow(p)).join('')
            : (this._adminProductsCache?.length
                ? components.vacioFila(5, { icono: 'buscar', titulo: 'Sin resultados.', chico: true, acciones: [{ texto: 'Limpiar filtros', limpiar: true }] })
                : components.vacioFila(5, { icono: 'notebook', titulo: 'Todavía no hay productos', texto: 'Marca, modelo y garantía de lo que reparás.',
                                            chico: true, acciones: [{ texto: 'Nuevo producto', clic: 'admin-new-product-btn' }] }));
    },

    openAdminEditProduct(id) {
        const p = this._adminProductsCache.find(x => x.id === id);
        if (!p) { toast.error('Producto no encontrado.'); return; }
        document.getElementById('product-form-id').value        = p.id;
        document.getElementById('product-form-marca').value     = p.marca;
        document.getElementById('product-form-modelo').value    = p.modelo;
        document.getElementById('product-form-categoria').value = p.categoria;
        document.getElementById('product-form-garantia').value  = p.periodo_garantia_meses;
        document.getElementById('product-form-nroparte').value  = p.numero_parte || '';
        document.getElementById('product-form-title').textContent = 'Editar Producto';
        document.getElementById('product-form-modal').classList.remove('hidden');
    },

    // ── Admin: Parts ──────────────────────────────────────────────────────────

    adminRenderParts() {
        const q = (document.getElementById('admin-parts-search')?.value || '').toLowerCase();
        let parts = this._adminPartsCache;
        if (q) parts = parts.filter(p => `${p.codigo} ${p.nombre} ${p.proveedor} ${p.ubicacion_ruta || ''}`.toLowerCase().includes(q));
        if (typeof Ubic !== 'undefined') parts = Ubic.filtrar(parts);
        const tbody = document.getElementById('admin-parts-list-body');
        if (!tbody) return;
        tbody.innerHTML = parts.length
            ? parts.map(p => components.adminPartRow(p)).join('')
            : `<tr><td colspan="8" class="px-5 py-10 text-center text-gray-400 italic text-sm">Sin resultados.</td></tr>`;
        if (typeof Ubic !== 'undefined') Ubic.pintarSeleccion();
    },

    /** Vuelve a pedir los repuestos (después de un cambio en lote) */
    async recargarRepuestosAdmin() {
        this._adminPartsCache = await api.getParts();
        document.getElementById('admin-parts-count').textContent = this._adminPartsCache.length;
        this.adminRenderParts();
    },

    adminCheckStockAlerts(parts) {
        const low = parts.filter(p => p.stock <= 3);
        const alertBox = document.getElementById('admin-parts-alerts');
        const alertMsg = document.getElementById('admin-parts-alert-msg');
        if (!alertBox || !alertMsg) return;
        if (low.length > 0) {
            alertMsg.textContent = `${low.length} repuesto${low.length>1?'s':''} con stock bajo (≤3 unidades): ${low.map(p=>p.nombre).join(', ')}`;
            alertBox.classList.remove('hidden');
        } else {
            alertBox.classList.add('hidden');
        }
    },

    openAdminEditPart(id) {
        const part = this._adminPartsCache.find(p => p.id === id);
        if (!part) { toast.error('Repuesto no encontrado.'); return; }
        document.getElementById('part-form-id').value        = part.id;
        document.getElementById('part-form-nombre').value    = part.nombre;
        document.getElementById('part-form-codigo').value    = part.codigo;
        document.getElementById('part-form-proveedor').value = part.proveedor;
        document.getElementById('part-form-stock').value     = part.stock;
        document.getElementById('part-form-precio').value    = part.precio;
        const minEl = document.getElementById('part-form-stock-minimo');
        if (minEl) minEl.value = part.stock_minimo ?? 0;
        document.getElementById('part-form-title').textContent = 'Editar Repuesto';
        if (typeof Ubic !== 'undefined') Ubic.llenarSelect('part-form-ubicacion', part.ubicacion_id);
        document.getElementById('parts-form-modal').classList.remove('hidden');
    },

    // ── Admin: Plantillas CRUD ───────────────────────────────────────────────

    _plantillasCache: [],

    async loadAdminPlantillas() {
        try {
            const list = await api.getPlantillas();
            this._plantillasCache = list;
            this.renderAdminPlantillas(list);
            // Also refresh diagnosis template buttons in any open detail
            this._renderDiagTemplates(list);
        } catch(e) { console.warn('Error cargando plantillas:', e); }
    },

    renderAdminPlantillas(list) {
        const el = document.getElementById('admin-plantillas-list');
        if (!el) return;
        el.innerHTML = list.length
            ? list.map(p => components.plantillaRow(p)).join('')
            : components.vacio({ icono: 'documento', titulo: 'No hay plantillas definidas.', texto: 'Textos de diagnóstico que se cargan con un click.', chico: true,
                                 acciones: [{ texto: 'Nueva plantilla', clic: 'admin-new-plantilla-btn' }] });
        el.querySelectorAll('.plantilla-edit-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('plantilla-form-id').value     = btn.dataset.id;
                document.getElementById('plantilla-form-nombre').value = btn.dataset.nombre;
                document.getElementById('plantilla-form-texto').value  = btn.dataset.texto;
                document.getElementById('plantilla-form-orden').value  = btn.dataset.orden;
                document.getElementById('plantilla-form-container').classList.remove('hidden');
            });
        });
        el.querySelectorAll('.plantilla-del-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                confirmDialog(`¿Eliminar plantilla "${btn.dataset.nombre}"?`, '', 'Eliminar')
                    .then(ok => { if (ok) ui._deletePlantilla(parseInt(btn.dataset.id)); });
            });
        });
    },

    _renderDiagTemplates(list) {
        const cont = document.getElementById('diag-templates-container');
        if (!cont) return;
        // Keep the label span, replace the rest
        cont.innerHTML = '<span class="text-[10px] text-gray-400 font-semibold uppercase mr-1 self-center">Plantillas:</span>'
            + list.map(p => components.plantillaBtn(p)).join('');
        cont.querySelectorAll('.diag-template').forEach(btn => {
            btn.addEventListener('click', () => {
                const f = document.getElementById('update-diagnostic');
                if (!f) return;
                f.value = f.value.trim() ? f.value.trim() + '\n\n' + btn.dataset.text : btn.dataset.text;
                f.dispatchEvent(new Event('input', { bubbles: true }));   // habilita "Guardar diagnóstico"
                f.focus();
            });
        });
    },

    async _deletePlantilla(id) {
        try { await api.deletePlantilla(id); await this.loadAdminPlantillas(); toast.success('Plantilla eliminada.'); }
        catch(e) { toast.error(e.message); }
    },

    // ── Admin: Estados CRUD ──────────────────────────────────────────────────

    _estadosCache: [],

    async loadAdminEstados() {
        try {
            const list = await api.getEstadosConfig();
            this._estadosCache = list;
            this.renderAdminEstados(list);
            // Rebuild the status select in the ticket detail
            this._rebuildStatusSelect(list);
        } catch(e) { console.warn('Error cargando estados:', e); }
    },

    renderAdminEstados(list) {
        const el = document.getElementById('admin-estados-list');
        if (!el) return;
        el.innerHTML = list.length
            ? list.map(s => components.estadoRow(s)).join('')
            : '<p class="px-5 py-8 text-gray-400 italic text-sm">No hay estados configurados.</p>';
        el.querySelectorAll('.estado-edit-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('estado-form-id').value       = btn.dataset.id;
                document.getElementById('estado-form-valor').value    = btn.dataset.valor;
                document.getElementById('estado-form-etiqueta').value = btn.dataset.etiqueta;
                document.getElementById('estado-form-color').value    = btn.dataset.color;
                document.getElementById('estado-form-orden').value    = btn.dataset.orden;
                document.getElementById('estado-form-activo').checked = btn.dataset.activo === 'true';
                document.getElementById('estado-form-final').checked  = btn.dataset.final === 'true';
                document.getElementById('estado-form-container').classList.remove('hidden');
            });
        });
        el.querySelectorAll('.estado-del-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                confirmDialog(`¿Eliminar estado "${btn.dataset.etiqueta}"?`,
                    'Solo se puede eliminar si no hay tickets con este estado.', 'Eliminar')
                    .then(ok => { if (ok) ui._deleteEstado(parseInt(btn.dataset.id)); });
            });
        });
    },

    _rebuildStatusSelect(list) {
        const sel = document.getElementById('update-status');
        if (!sel) return;
        const current = sel.value;
        const active = list.filter(s => s.activo);
        sel.innerHTML = active.map(s =>
            `<option value="${esc(s.valor)}" ${s.valor === current ? 'selected' : ''}>${esc(s.etiqueta)}</option>`
        ).join('');
    },

    async _deleteEstado(id) {
        try { await api.deleteEstado(id); await this.loadAdminEstados(); toast.success('Estado eliminado.'); }
        catch(e) { toast.error(e.message); }
    },

    // ── Admin: Tags CRUD ──────────────────────────────────────────────────────

    _tagsCache: [],

    async loadAdminTags() {
        try {
            const tags = await api.getTags();
            this._tagsCache = tags;
            this.renderAdminTags(tags);
            // Also update ef-add-tag in detail view if present
            const efSel = document.getElementById('ef-add-tag');
            if (efSel) {
                efSel.innerHTML = '<option value="">Agregar etiqueta...</option>' +
                    tags.map(t => `<option value="${esc(t.nombre)}">${esc(t.nombre)}</option>`).join('');
            }
        } catch(e) { console.warn('Error cargando etiquetas:', e); }
    },

    renderAdminTags(tags) {
        const container = document.getElementById('admin-tags-list');
        if (!container) return;
        container.innerHTML = tags.length
            ? tags.map(t => components.tagCard(t)).join('')
            : `<div class="col-span-3">${components.vacio({ icono: 'etiqueta', titulo: 'No hay etiquetas definidas.', chico: true,
                                                         acciones: [{ texto: 'Nueva etiqueta', clic: 'admin-new-tag-btn' }] })}</div>`;
        container.querySelectorAll('.tag-edit-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('tag-form-id').value     = btn.dataset.id;
                document.getElementById('tag-form-nombre').value = btn.dataset.nombre;
                document.getElementById('tag-form-color').value  = btn.dataset.color;
                document.getElementById('tag-form-container').classList.remove('hidden');
                document.getElementById('tag-form-nombre').focus();
            });
        });
        container.querySelectorAll('.tag-del-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                confirmDialog(`¿Eliminar etiqueta "${btn.dataset.nombre}"?`,
                    'Se eliminará de todos los tickets que la tengan asignada.')
                    .then(ok => { if (ok) ui._deleteTag(parseInt(btn.dataset.id)); });
            });
        });
    },

    async _deleteTag(id) {
        try { await api.deleteTag(id); await this.loadAdminTags(); toast.success('Etiqueta eliminada.'); }
        catch(e) { toast.error(e.message); }
    },

    // ── Admin: Stock History ─────────────────────────────────────────────────

    _stockHistoryCache: [],

    async loadStockHistory(repuestoId = null) {
        try {
            const data = await api.getStockHistory(repuestoId ? repuestoId : null);
            this._stockHistoryCache = data;
            // Apply categoria client-side filter if selected
            const catSel  = document.getElementById('admin-stock-filter-cat');
            const cat     = catSel?.value || null;
            const parts   = this._adminPartsCache || [];
            let filtered  = data;
            if (cat) {
                const ids = new Set(parts.filter(p => (p.categoria || 'General') === cat).map(p => p.id));
                filtered = data.filter(m => ids.has(m.repuesto_id));
            }
            this.renderStockHistory(filtered);
        } catch(e) { toast.error('No se pudo cargar el historial.'); }
    },

    async populateStockFilters() {
        const parts = this._adminPartsCache || [];
        const partSel = document.getElementById('admin-stock-filter-part');
        if (partSel) {
            partSel.innerHTML = '<option value="">Todos los repuestos</option>'
                + parts.map(p => `<option value="${p.id}">${esc(p.nombre)}</option>`).join('');
        }
        const catSel = document.getElementById('admin-stock-filter-cat');
        if (catSel) {
            const cats = [...new Set(parts.map(p => p.categoria || 'General'))].sort();
            catSel.innerHTML = '<option value="">Todas las categorías</option>'
                + cats.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
        }
    },

    renderStockHistory(movs) {
        const tbody = document.getElementById('admin-stock-list-body');
        if (!tbody) return;
        if (!movs.length) {
            tbody.innerHTML = `<tr><td colspan="9" class="px-4 py-10 text-center text-gray-400 italic text-sm">Sin movimientos registrados.</td></tr>`;
            return;
        }
        tbody.innerHTML = movs.map(m => components.stockMovRow(m)).join('');
        tbody.querySelectorAll('.stock-edit-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const nota = btn.dataset.nota || '';
                const id   = parseInt(btn.dataset.id);
                const newNota = await promptDialog('Editar nota del movimiento', nota);
                if (newNota !== null) ui._updateStockMov(id, newNota);
            });
        });
        tbody.querySelectorAll('.stock-del-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                confirmDialog('¿Anular este movimiento?', 'Se registra un movimiento inverso y, si era de un ticket o un pedido, se corrige también ahí.', 'Anular')
                    .then(ok => { if (ok) ui._deleteStockMov(id); });
            });
        });
    },

    async _updateStockMov(id, nota) {
        try { await api.updateStockMovimiento(id, nota); await this.loadStockHistory(); toast.success('Nota actualizada.'); }
        catch(e) { toast.error(e.message); }
    },

    async _deleteStockMov(id) {
        try {
            await api.deleteStockMovimiento(id);
            const updated = await api.getParts();
            this._adminPartsCache = updated;
            this.adminRenderParts(); this.adminCheckStockAlerts(updated);
            await this.loadStockHistory();
            toast.success('Movimiento anulado y stock corregido.');
        } catch(e) { toast.error(e.message); }
    },

    // ── Advanced stats ─────────────────────────────────────────────────────

    async loadAdvancedStats() {
        try {
            const stats = await api.request('/tickets/stats/dashboard');
            if (!stats) return;
            const promedio = document.getElementById('avg-repair-time');
            promedio.innerText = stats.cerrados ? `${stats.tiempo_promedio_reparacion_horas}h` : '—';
            promedio.nextElementSibling.innerText = stats.cerrados ? 'Tiempo prom. reparación' : 'Todavía no hay reparaciones cerradas';
            // Sin datos: un mensaje en lugar del gráfico vacío
            const vacio = (id, texto) => {
                const caja = document.getElementById(id)?.parentElement;
                if (caja) caja.innerHTML = `<div class="h-full flex items-center justify-center text-center text-sm text-gray-400 px-4">${texto}</div>`;
            };

            ['myChart1','myChart2','myChart3'].forEach(k => {
                if (window[k] instanceof Chart) window[k].destroy();
            });

            const opts = { responsive: true, maintainAspectRatio: false, animation: false };
            // Leyenda a la derecha, con puntos: entra entera en la tarjeta (abajo se cortaba)
            // Nombres largos: recortados con "…" (el nombre completo queda en el tooltip)
            const corto = (s, n = 16) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
            const leyenda = { position: 'right', labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 7, boxHeight: 7, padding: 8, font: { size: 11 },
                generateLabels: ch => Chart.overrides.doughnut.plugins.legend.labels.generateLabels(ch).map(l => ({ ...l, text: corto(l.text, 15) })) } };

            const stateColors = {
                'Nuevo': '#3b82f6', 'En revisión': '#f59e0b', 'Aprobado para RMA': '#10b981',
                'Equipo recibido': '#6366f1', 'En diagnóstico': '#06b6d4', 'En reparación': '#8b5cf6',
                'Esperando repuestos': '#f97316', 'Reparado': '#14b8a6',
                'Enviado al cliente': '#0ea5e9', 'Cerrado': '#6b7280', 'Cancelado': '#ef4444',
            };
            const stateLabels = Object.keys(stats.tickets_por_estado);
            const stateData   = Object.values(stats.tickets_por_estado);
            const stateBgs    = stateLabels.map(l => stateColors[l] || '#94a3b8');
            if (!stateData.length) vacio('chart-states', 'Todavía no hay tickets');
            else {
            window.myChart1 = new Chart(document.getElementById('chart-states').getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: stateLabels.map(l => I18N.tr(l)),
                    datasets: [{ data: stateData, backgroundColor: stateBgs, borderWidth: 2 }]
                },
                options: { ...opts, cutout: '62%', plugins: { legend: leyenda } },
            });
            }
            if (!Object.keys(stats.fallas_por_producto).length) vacio('chart-products', 'Sin fallas registradas');
            else {
            window.myChart2 = new Chart(document.getElementById('chart-products').getContext('2d'), {
                type: 'bar',
                data: { labels: Object.keys(stats.fallas_por_producto), datasets: [{ label: I18N.tr('Fallas'), data: Object.values(stats.fallas_por_producto), backgroundColor: '#3b82f6', borderRadius: 4, maxBarThickness: 18 }] },
                options: { ...opts, indexAxis: 'y', plugins: { legend: { display: false } },
                    scales: { y: { grid: { display: false }, ticks: { font: { size: 11 }, callback(v) { return corto(this.getLabelForValue(v)); } } },
                              x: { beginAtZero: true, ticks: { precision: 0, font: { size: 10 } }, grid: { color: 'rgba(148,163,184,.2)' } } } },
            });
            }
            if (!Object.keys(stats.tickets_por_tecnico).length) vacio('chart-techs', 'Ningún ticket asignado a un técnico todavía');
            else {
            window.myChart3 = new Chart(document.getElementById('chart-techs').getContext('2d'), {
                type: 'doughnut',
                data: { labels: Object.keys(stats.tickets_por_tecnico), datasets: [{ data: Object.values(stats.tickets_por_tecnico), backgroundColor: ['#f59e0b','#10b981','#3b82f6','#8b5cf6','#ef4444'], borderWidth: 2 }] },
                options: { ...opts, cutout: '62%', plugins: { legend: leyenda } },
            });
            }
        } catch (err) { console.error(err); }
    },

    // ── Helpers ────────────────────────────────────────────────────────────

    setLoading(btnId, isLoading) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        if (isLoading) {
            btn.dataset.original = btn.innerText;
            btn.innerText = 'Cargando...';
            btn.disabled  = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
        } else {
            btn.innerText = btn.dataset.original || 'Enviar';
            btn.disabled  = false;
            btn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    },

    // ── Admin: Seguridad / Rate limit ──────────────────────────────────────────
    async loadAdminSeguridad() {
        try {
            const configs = await api.getConfigSistema();
            const container = document.getElementById('rate-limit-config-cards');
            if (!container) return;
            container.innerHTML = configs.map(c => `
                <div class="bg-white border border-gray-100 shadow rounded-xl p-5">
                    <p class="text-[10px] font-bold text-gray-400 uppercase mb-1">${esc(c.label)}</p>
                    <div class="flex items-center gap-2 mt-2">
                        <input type="number" min="1"
                            id="rl-${c.clave}"
                            value="${esc(c.valor)}"
                            class="w-full px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                        <button type="button"
                            data-clave="${c.clave}"
                            class="rl-save-btn flex-shrink-0 px-3 py-2 bg-blue-600 text-white rounded-md text-xs font-bold hover:bg-blue-700 transition">
                            Guardar
                        </button>
                    </div>
                    <p class="text-[10px] text-gray-400 mt-1">Default: ${c.default}</p>
                </div>
            `).join('');

            // Attach save handlers
            container.querySelectorAll('.rl-save-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const clave = btn.dataset.clave;
                    const val   = document.getElementById(`rl-${clave}`)?.value;
                    try {
                        await api.updateConfigSistema(clave, val);
                        toast.success('Configuración guardada.');
                    } catch(e) { toast.error(e.message); }
                });
            });
        } catch(e) { console.warn('Error cargando config seguridad:', e); }

        // Load attempts
        await this._loadLoginAttempts();

        // Bind buttons
        const refreshBtn = document.getElementById('refresh-attempts-btn');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this._loadLoginAttempts());
        const clearAllBtn = document.getElementById('clear-all-attempts-btn');
        if (clearAllBtn) clearAllBtn.addEventListener('click', async () => {
            if (!await confirmDialog('¿Limpiar todos los intentos fallidos?', 'Se borra el registro de intentos de ingreso.', 'Limpiar')) return;
            await api.clearLoginAttempts(null);
            await this._loadLoginAttempts();
            toast.success('Intentos fallidos borrados.');
        });
    },

    async _loadLoginAttempts() {
        const list = document.getElementById('login-attempts-list');
        if (!list) return;
        try {
            const rows = await api.getLoginAttempts();
            if (!rows.length) {
                list.innerHTML = '<p class="text-gray-400 italic">Sin intentos fallidos recientes.</p>';
                return;
            }
            list.innerHTML = rows.map(r => `
                <div class="flex items-center justify-between bg-red-50 border border-red-100 px-4 py-2 rounded-lg">
                    <div>
                        <span class="font-mono font-bold text-red-700">${esc(r.ip)}</span>
                        <span class="ml-3 text-xs text-red-500">${r.intentos} intentos fallidos</span>
                    </div>
                    <button type="button" data-ip="${esc(r.ip)}"
                        class="unblock-ip-btn text-xs text-red-400 hover:text-red-600 font-semibold border border-red-200 px-2 py-1 rounded hover:bg-red-100 transition">
                        Desbloquear
                    </button>
                </div>
            `).join('');
            list.querySelectorAll('.unblock-ip-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    await api.clearLoginAttempts(btn.dataset.ip);
                    await this._loadLoginAttempts();
                    toast.success(`IP ${btn.dataset.ip} desbloqueada.`);
                });
            });
        } catch(e) { list.innerHTML = '<p class="text-red-400 italic">Error cargando datos.</p>'; }
    },
};
