/** "Sin garantía", "1 mes", "6 meses", "1 año", "2 años", "18 meses" (nunca "1.5 años"). */
function garantiaTexto(meses) {
    const m = +meses || 0;
    if (!m) return 'Sin garantía';
    if (m === 12) return '1 año';
    if (m % 12 === 0) return `${m / 12} años`;
    return m === 1 ? '1 mes' : `${m} meses`;
}

/** Precio en pesos con formato argentino: $ 12.345,50 */
const _ars = new Intl.NumberFormat(I18N.locale, { style: 'currency', currency: 'ARS' });
function precioARS(n) { return _ars.format(+n || 0); }
window.garantiaTexto = garantiaTexto;
window.precioARS = precioARS;

/**
 * components.js — Pure render functions for all UI elements.
 * Each function takes data and returns an HTML string.
 * No side effects, no DOM access — easy to test and reuse.
 */
const components = (() => {

    // ── Status helpers ──────────────────────────────────────────────────────
    function statusClass(status) {
        const map = {
            'Nuevo':            'bg-blue-100 text-blue-700',
            'En revisión':      'bg-amber-100 text-amber-700',
            'Aprobado para RMA':'bg-green-100 text-green-700',
            'Equipo recibido':  'bg-indigo-100 text-indigo-700',
            'En diagnóstico':   'bg-cyan-100 text-cyan-700',
            'En reparación':    'bg-purple-100 text-purple-700',
            'Esperando repuestos': 'bg-orange-100 text-orange-700',
            'Reparado':         'bg-teal-100 text-teal-700',
            'Enviado al cliente':'bg-sky-100 text-sky-700',
            'Cerrado':          'bg-gray-100 text-gray-700',
            'Cancelado':        'bg-red-100 text-red-700',
        };
        return map[status] || 'bg-gray-100 text-gray-700';
    }

    // ── Etiquetas (badges): una sola forma en todo el sistema ───────────────
    // Tipo oración, mismo tamaño, color suave y un punto opcional (estado).
    const BADGE = 'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap';
    const BADGE_GRANDE = 'inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-semibold whitespace-nowrap';
    function badge(texto, colores, { punto = false, grande = false, extra = '', titulo = '' } = {}) {
        return `<span class="${grande ? BADGE_GRANDE : BADGE} ${colores} ${extra}"${titulo ? ` title="${esc(titulo)}"` : ''}>` +
               `${punto ? '<span class="w-1.5 h-1.5 rounded-full bg-current opacity-75" aria-hidden="true"></span>' : ''}${esc(texto)}</span>`;
    }
    const statusBadge = (estado, opciones = {}) => badge(estado, statusClass(estado), { punto: true, ...opciones });
    /** Pinta un elemento existente (p. ej. #detail-status-badge) como etiqueta de estado. */
    function pintarEstado(el, estado) {
        if (!el) return;
        el.className = `${BADGE_GRANDE} ${statusClass(estado)}`;
        el.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-current opacity-75" aria-hidden="true"></span>${esc(estado)}`;
    }
    const ROLES = {
        administrador: ['Administrador', 'bg-red-100 text-red-700'],
        tecnico:       ['Técnico',       'bg-purple-100 text-purple-700'],
        cliente:       ['Cliente',       'bg-gray-100 text-gray-600'],
    };
    const rolBadge = rol => badge((ROLES[rol] || [rol])[0], (ROLES[rol] || [, 'bg-gray-100 text-gray-600'])[1]);
    const activoBadge = (activo, si = 'Activo', no = 'Inactivo') =>
        badge(activo ? si : no, activo ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500', { punto: true });
    const garantiaBadge = enGarantia => enGarantia
        ? badge('Garantía', 'bg-green-100 text-green-700', { extra: 'ml-1.5' })
        : badge('Fuera de garantía', 'bg-gray-100 text-gray-600', { extra: 'ml-1.5' });

    // Umbral de "por vencer": el mismo ajuste que usan las alertas (Ajustes → SLA)
    let _slaAvisoMs = 4 * 3_600_000;
    function setSlaAvisoHoras(h) { if (h > 0) _slaAvisoMs = h * 3_600_000; }

    function slaBadge(deadline, estado, { soloAlertas = false } = {}) {
        // Don't show SLA badge on new tickets — the 24h clock is internal,
        // not meaningful to display until the team has picked up the ticket.
        if (!deadline || estado === 'Nuevo') return '';
        const diff = new Date(deadline) - new Date();
        if (diff < 0) return badge('SLA vencido', 'bg-red-100 text-red-700', { extra: 'ml-2' });
        if (diff < _slaAvisoMs) return badge('SLA por vencer', 'bg-amber-100 text-amber-700', { extra: 'ml-2' });
        return soloAlertas ? '' : badge('En tiempo', 'bg-green-100 text-green-700', { extra: 'ml-2' });
    }

    function priorityBadge(prioridad) {
        const map = {
            'Urgente': 'bg-red-100 text-red-700',
            'Alta':    'bg-orange-100 text-orange-700',
            'Normal':  'bg-gray-100 text-gray-600',
            'Media':   'bg-gray-100 text-gray-600',
            'Baja':    'bg-gray-100 text-gray-500',
        };
        return badge(prioridad, map[prioridad] || 'bg-gray-100 text-gray-500');
    }

    // ── Lista de tickets ─────────────────────────────────────────────────────
    // Columnas según quién mira: el taller ve cliente, técnico, días y prioridad.
    const COLS_TALLER  = ['ticket', 'equipo', 'cliente', 'estado', 'tecnico', 'dias', 'prioridad'];
    const COLS_CLIENTE = ['ticket', 'equipo', 'estado', 'fecha'];
    const COL_INFO = {
        ticket:    ['Ticket', 'rma'],      equipo: ['Equipo', 'producto'], cliente: ['Cliente', 'cliente'],
        estado:    ['Estado', 'estado'],   tecnico: ['Técnico', 'tecnico'], dias: ['Días', 'dias'],
        prioridad: ['Prioridad', 'prioridad'], fecha: ['Ingreso', 'fecha'],
    };
    /** Días que lleva en el taller (null si ya se cerró). */
    function diasEnTaller(t) {
        if (t.fecha_cierre) return null;
        return Math.max(0, Math.floor((Date.now() - new Date(t.fecha_creacion)) / 86_400_000));
    }

    function ticketHead(cols, orden) {
        const [campoAct, sentido] = orden.split('_');
        return `<tr>${cols.map(c => {
            const [titulo, campo] = COL_INFO[c];
            const activo = campo === campoAct;
            const flecha = activo ? icono(sentido === 'asc' ? 'arriba' : 'abajo', 'w-3.5 h-3.5') : icono('arriba-abajo', 'w-3.5 h-3.5 opacity-0 group-hover:opacity-60');
            return `<th class="px-5 py-2.5 text-xs font-semibold text-gray-500 ${c === 'dias' ? 'text-right' : ''}" ${activo ? `aria-sort="${sentido === 'asc' ? 'ascending' : 'descending'}"` : ''}>
                <button type="button" data-orden="${campo}" class="group inline-flex items-center gap-1 hover:text-gray-800 ${activo ? 'text-gray-800' : ''}">${esc(titulo)}${flecha}</button></th>`;
        }).join('')}</tr>`;
    }

    function ticketRow(t, cols = COLS_TALLER) {
        const dias = diasEnTaller(t);
        const celda = {
            ticket: `<td data-col="ticket" class="px-5 py-3.5">
                <div class="font-semibold text-blue-700 whitespace-nowrap" translate="no">${esc(t.numero_rma)}</div>
                <div class="t-sub text-xs text-gray-400 mt-0.5">#${t.id}</div></td>`,
            equipo: `<td data-col="equipo" class="px-5 py-3.5 min-w-[11rem]">
                <div class="font-medium text-gray-800">${esc(t.producto || 'Producto Genérico')}</div>
                <div class="t-sub text-xs text-gray-400 mt-0.5"><span translate="no">SN ${esc(t.numero_serie)}</span>${garantiaBadge(t.en_garantia)}</div></td>`,
            cliente: `<td data-col="cliente" class="px-5 py-3.5 text-sm text-gray-700" translate="no">${esc(t.usuario_nombre || '—')}</td>`,
            estado: `<td data-col="estado" class="px-5 py-3.5"><div class="flex flex-wrap items-center gap-1">${statusBadge(t.estado)}${slaBadge(t.deadline_sla, t.estado, { soloAlertas: true }).replace('ml-2', '')}</div></td>`,
            tecnico: `<td data-col="tecnico" class="px-5 py-3.5 text-sm">${t.tecnico_nombre ? `<span class="text-gray-700" translate="no">${esc(t.tecnico_nombre)}</span>` : '<span class="text-gray-400">Sin asignar</span>'}</td>`,
            dias: `<td data-col="dias" class="px-5 py-3.5 text-sm text-right tabular-nums ${dias >= 7 ? 'text-amber-700 font-semibold' : 'text-gray-700'}"
                title="${esc(new Date(t.fecha_creacion).toLocaleDateString(I18N.locale))}">${dias == null ? '<span class="text-gray-400">—</span>' : `<span class="t-dias">${dias}</span>`}</td>`,
            prioridad: `<td data-col="prioridad" class="px-5 py-3.5">${priorityBadge(t.prioridad)}</td>`,
            fecha: `<td data-col="fecha" class="px-5 py-3.5 text-sm text-gray-500 tabular-nums">${new Date(t.fecha_creacion).toLocaleDateString(I18N.locale)}</td>`,
        };
        return `
        <tr class="hover:bg-gray-50 transition" data-ticket-id="${t.id}" tabindex="0" aria-label="${esc(t.numero_rma)}">
            ${cols.map(c => celda[c]).join('')}
        </tr>`;
    }

    // ── Estados vacíos: qué pasa y qué se puede hacer ─────────────────────────
    // acciones: [{ texto, clic: 'id-de-un-botón-existente' }] o [{ texto, foco: 'id-de-un-campo' }]
    // o [{ texto, limpiar: true }] (dispara el evento "vacio:limpiar" para quitar filtros)
    function vacio({ titulo, texto = '', acciones = [], icono: ico = 'bandeja', chico = false }) {
        const botones = acciones.map((a, i) => `
            <button type="button" ${a.clic ? `data-vacio-clic="${esc(a.clic)}"` : ''} ${a.foco ? `data-vacio-foco="${esc(a.foco)}"` : ''}
                ${a.limpiar ? 'data-vacio-limpiar' : ''}
                class="${i === 0 ? 'bg-blue-600 hover:bg-blue-700 text-white' : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'} px-4 py-2 rounded-lg text-sm font-semibold shadow-sm transition">${esc(a.texto)}</button>`).join('');
        return `
        <div class="flex flex-col items-center text-center gap-2 ${chico ? 'py-6' : 'py-12'} px-4">
            <span class="${chico ? 'w-10 h-10' : 'w-14 h-14'} rounded-full bg-gray-100 text-gray-400 flex items-center justify-center mb-1" aria-hidden="true">${window.icono(ico, chico ? 'w-5 h-5' : 'w-7 h-7') || esc(ico)}</span>
            <p class="font-semibold text-gray-600 ${chico ? 'text-sm' : 'text-base'}">${esc(titulo)}</p>
            ${texto ? `<p class="text-sm text-gray-400 max-w-sm">${esc(texto)}</p>` : ''}
            ${botones ? `<div class="flex flex-wrap justify-center gap-2 mt-2">${botones}</div>` : ''}
        </div>`;
    }
    const vacioFila = (columnas, opciones) => `<tr><td colspan="${columnas}">${vacio(opciones)}</td></tr>`;

    // Los botones de los estados vacíos (delegado: el HTML se rearma seguido)
    document.addEventListener('click', e => {
        const b = e.target.closest('[data-vacio-clic],[data-vacio-foco],[data-vacio-limpiar]');
        if (!b) return;
        if (b.dataset.vacioClic) document.getElementById(b.dataset.vacioClic)?.click();
        if (b.dataset.vacioFoco) { const c = document.getElementById(b.dataset.vacioFoco); c?.scrollIntoView({ block: 'center' }); c?.focus(); }
        if (b.hasAttribute('data-vacio-limpiar')) b.dispatchEvent(new CustomEvent('vacio:limpiar', { bubbles: true }));
    });

    // ── Ticket table empty state ─────────────────────────────────────────────
    function ticketEmptyState(filtered = false) {
        if (filtered) {
            return vacioFila(8, { icono: 'buscar', titulo: 'Sin resultados para ese filtro', texto: 'Probá con otro estado o limpiá el filtro.',
                                  acciones: [{ texto: 'Ver todos los tickets', limpiar: true }] });
        }
        const rol = auth.getUser()?.role || '';
        if (rol === 'cliente') {
            return vacioFila(8, { icono: 'llave', titulo: 'Todavía no tenés reparaciones', texto: 'Cargá tu equipo y te avisamos cada novedad.',
                                  acciones: [{ texto: 'Cargar un equipo', clic: 'create-ticket-btn' }] });
        }
        return vacioFila(8, { icono: 'portapapeles', titulo: 'Aún no hay tickets', texto: 'Cuando llegue un equipo, cargalo desde el mostrador o como ticket.',
                              acciones: [{ texto: 'Ingreso en mostrador', clic: 'mostrador-btn' }, { texto: 'Nuevo ticket', clic: 'create-ticket-btn' }] });
    }

    // ── Stats card ───────────────────────────────────────────────────────────
    function statCard({ label, value, color, icon }) {
        const colors = {
            blue:   'border-blue-600',
            amber:  'border-amber-500',
            indigo: 'border-indigo-500',
            green:  'border-green-600',
            red:    'border-red-500',
        };
        const icons = {
            ticket: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>`,
            new:    `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4v16m8-8H4"/>`,
            wrench: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>`,
            check:  `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>`,
        };
        return `
        <div class="bg-white p-4 md:p-6 rounded-xl shadow border-l-4 ${colors[color] || colors.blue}">
            <div class="flex justify-between items-start">
                <div>
                    <p class="text-xs font-bold text-gray-500 uppercase tracking-wide">${label}</p>
                    <p class="text-3xl font-black text-gray-800 mt-1">${value}</p>
                </div>
                ${icon ? `<svg class="hidden sm:block w-8 h-8 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">${icons[icon] || ''}</svg>` : ''}
            </div>
        </div>`;
    }

    // ── Comment ──────────────────────────────────────────────────────────────
    function comment(c) {
        const isDiag    = c.comentario.startsWith('DIAGNÓSTICO TÉCNICO:');
        const isInternal = c.is_internal === true;

        let wrapCls, headerCls, badge = '';
        if (isInternal) {
            wrapCls   = 'bg-violet-50 border-violet-200 dark:bg-violet-950/40 dark:border-violet-700';
            headerCls = 'text-violet-800 dark:text-violet-300';
            badge     = `<span class="ml-2 px-1.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-violet-200 text-violet-700 dark:bg-violet-800 dark:text-violet-200">Nota interna</span>`;
        } else if (isDiag) {
            wrapCls   = 'bg-amber-50 border-amber-200';
            headerCls = 'text-amber-800';
        } else {
            wrapCls   = 'bg-gray-50 border-gray-100';
            headerCls = 'text-blue-800';
        }

        const icon = isInternal ? icono('candado', 'w-3.5 h-3.5') : isDiag ? icono('llave', 'w-3.5 h-3.5') : '';
        return `
        <div class="p-4 rounded-lg border ${wrapCls}">
            <div class="flex justify-between items-start mb-2">
                <span class="font-bold text-sm flex items-center flex-wrap gap-1 ${headerCls}">
                    ${icon}${esc(c.usuario_nombre || 'Usuario #' + c.usuario_id)}${badge}
                </span>
                <span class="text-xs text-gray-400 shrink-0 ml-3">${new Date(c.fecha).toLocaleString(I18N.locale, { hour12: false })}</span>
            </div>
            <p class="text-sm leading-relaxed ${isInternal ? 'text-violet-900 dark:text-violet-200 italic' : 'text-gray-700'}">${esc(c.comentario)}</p>
        </div>`;
    }

    const TIPOS_MOV = { consumo: 'Consumo', reposicion: 'Reposición', devolucion: 'Devolución',
                        ajuste: 'Ajuste', anulacion: 'Anulación' };

    function stockMovRow(m) {
        const isConsumo = m.cantidad < 0;
        const cls   = isConsumo ? 'text-red-600 font-bold' : 'text-green-600 font-bold';
        const sign  = isConsumo ? '−' : '+';
        const fecha = new Date(m.fecha).toLocaleString(I18N.locale, { hour12: false });
        const ticketLink = m.ticket_rma
            ? `<span class="font-mono text-blue-600 text-xs">${esc(m.ticket_rma)}</span>`
            : '<span class="text-gray-300 text-xs">—</span>';
        const repuesto = m.repuesto_nombre
            ? `<span class="font-medium text-gray-700 text-xs">${esc(m.repuesto_nombre)}</span>`
            : '<span class="text-gray-300 text-xs">—</span>';
        const tipoCls  = isConsumo
            ? 'bg-red-50 text-red-700 border border-red-200'
            : 'bg-green-50 text-green-700 border border-green-200';
        // Los movimientos no se borran: se anulan con uno inverso (que corrige
        // también el ticket o el pedido de donde vinieron)
        const anulable = !m.anulado && !m.anula_id && !(m.ticket_id && m.tipo !== 'consumo');
        const actions = `<td class="px-4 py-2.5 text-center">
                <div class="flex items-center justify-center gap-2">
                    <button type="button" class="stock-edit-btn text-xs text-blue-500 hover:text-blue-700 font-semibold" data-id="${m.id}" data-nota="${esc(m.nota)}">Nota</button>
                    ${anulable ? `<button type="button" class="stock-del-btn text-xs text-red-400 hover:text-red-600 font-semibold" data-id="${m.id}">Anular</button>` : ''}
                    ${m.anulado ? '<span class="text-[10px] font-bold text-gray-400 uppercase">anulado</span>' : ''}
                </div>
               </td>`;
        return `<tr class="hover:bg-gray-50 transition text-sm ${m.anulado ? 'line-through opacity-50' : ''}">
            <td class="px-4 py-2.5 text-gray-400 text-xs whitespace-nowrap">${fecha}</td>
            <td class="px-4 py-2.5">${repuesto}</td>
            <td class="px-4 py-2.5">${ticketLink}</td>
            <td class="px-4 py-2.5"><span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${tipoCls}">${TIPOS_MOV[m.tipo] || esc(m.tipo)}</span></td>
            <td class="px-4 py-2.5 ${cls} text-center">${sign}${Math.abs(m.cantidad)}</td>
            <td class="px-4 py-2.5 text-center text-gray-600 font-semibold">${m.stock_nuevo}</td>
            <td class="px-4 py-2.5 text-gray-400 text-xs max-w-xs truncate">${esc(m.nota || '—')}</td>
            <td class="px-4 py-2.5 text-gray-400 text-xs">${esc(m.usuario_nombre || '—')}</td>
            ${actions}
        </tr>`;
    }

    function tagCard(tag) {
        return `
        <div class="flex items-center justify-between p-3 rounded-xl border-2 gap-2 group" style="border-color:${colorSeguro(tag.color)}20; background:${colorSeguro(tag.color)}10;">
            <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full shrink-0" style="background:${colorSeguro(tag.color)}"></span>
                <span class="font-semibold text-sm text-gray-800">${esc(tag.nombre)}</span>
            </div>
            <div class="flex gap-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100 transition">
                <button type="button" class="tag-edit-btn w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition"
                    data-id="${tag.id}" data-nombre="${esc(tag.nombre)}" data-color="${colorSeguro(tag.color)}" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>
                <button type="button" class="tag-del-btn w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition"
                    data-id="${tag.id}" data-nombre="${esc(tag.nombre)}" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>
            </div>
        </div>`;
    }

    function creatorBadge(rol) {
        const map = {
            cliente:       { label: 'Cliente',       cls: 'bg-blue-100 text-blue-700 border border-blue-200' },
            tecnico:       { label: 'Técnico',        cls: 'bg-purple-100 text-purple-700 border border-purple-200' },
            administrador: { label: 'Administrador',  cls: 'bg-red-100 text-red-700 border border-red-200' },
        };
        const { label, cls } = map[rol] || { label: rol, cls: 'bg-gray-100 text-gray-600 border border-gray-200' };
        return badge(label, cls.replace(/ ?border[^ ]*/g, ''));
    }

    function commentEmptyState() {
        return vacio({ icono: 'mensaje', titulo: 'No hay comentarios aún.', chico: true,
                       acciones: [{ texto: 'Escribir el primero', foco: 'new-comment' }] });
    }

    // ── History entry ────────────────────────────────────────────────────────
    // ── Feature 6: user badge ────────────────────────────────────────────────
    function userBadge(rol, nombre) {
        const map = {
            administrador: { bg: "bg-red-100", text: "text-red-700", label: "Admin" },
            tecnico:       { bg: "bg-purple-100", text: "text-purple-700", label: "Técnico" },
            cliente:       { bg: "bg-slate-100", text: "text-slate-600", label: "Cliente" },
        };
        const s = map[rol] || { bg: "bg-gray-100", text: "text-gray-600", label: rol };
        return badge(s.label, `${s.bg} ${s.text}`);
    }

    // ── Feature 9: rich historial entries ────────────────────────────────────
    const EVENTO_ICON = {
        cambio_estado:    { icon: "cambio", color: "blue" },
        comentario:       { icon: "mensaje", color: "gray" },
        nota_interna:     { icon: "candado", color: "violet" },
        tag_agregado:     { icon: "etiqueta", color: "green" },
        tag_eliminado:    { icon: "papelera", color: "red" },
        tag_editado:      { icon: "lapiz", color: "amber" },
        repuesto_agregado:{ icon: "paquete", color: "indigo" },
        campo_editado:    { icon: "lapiz", color: "amber" },
        tecnico_asignado: { icon: "usuario", color: "blue" },
        ticket_clonado:   { icon: "copiar", color: "teal" },
        ticket_relacionado:{ icon:"vinculo", color: "teal" },
        ticket_desasociado:{ icon:"desvincular", color: "gray" },
        archivo_subido:   { icon: "clip", color: "blue" },
        archivo_eliminado:{ icon: "papelera", color: "red" },
        checklist_ingreso:{ icon: "checklist", color: "emerald" },
        firma_registrada: { icon: "firma", color: "emerald" },
        tiempo_editado:   { icon: "reloj", color: "emerald" },
    };

    function historyEntry(h) {
        const ev      = EVENTO_ICON[h.tipo_evento] || { icon: "info", color: "gray" };
        const fecha   = new Date(h.fecha).toLocaleString(I18N.locale, { hour12: false });
        const usuario = h.usuario_nombre || "Sistema";
        let body = "";
        if (h.tipo_evento === "cambio_estado" && h.estado_anterior && h.estado_nuevo) {
            body = `<span class="text-gray-400">${esc(h.estado_anterior)}</span> → <strong>${esc(h.estado_nuevo)}</strong>`;
        } else if (h.tipo_evento === "campo_editado" && h.campo) {
            const campo = { descripcion:"Descripción", numero_serie:"Nº Serie", prioridad:"Prioridad", diagnostico:"Diagnóstico" }[h.campo] || h.campo;
            body = `<strong>${esc(campo)}</strong> cambiado`;
            if (h.valor_anterior && h.valor_nuevo) {
                const ant = h.valor_anterior.length > 40 ? h.valor_anterior.slice(0,40)+"…" : h.valor_anterior;
                const nuevo = h.valor_nuevo.length > 40 ? h.valor_nuevo.slice(0,40)+"…" : h.valor_nuevo;
                body += `<br><span class="text-xs text-gray-400">Antes: ${esc(ant)}</span>`;
                body += `<br><span class="text-xs text-gray-700">Ahora: ${esc(nuevo)}</span>`;
            }
        } else {
            body = esc(h.detalle || "");
        }
        return `<div class="flex gap-3 text-sm">
            <div class="flex flex-col items-center">
                <div class="w-8 h-8 rounded-full bg-${ev.color}-50 border-2 border-${ev.color}-200 flex items-center justify-center text-${ev.color}-600 shrink-0">${icono(ev.icon, "w-4 h-4")}</div>
                <div class="flex-1 w-px bg-gray-200 my-1"></div>
            </div>
            <div class="pb-4 flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="font-semibold text-gray-700">${esc(usuario)}</span>
                    <span class="text-gray-400 text-xs">${fecha}</span>
                </div>
                <div class="text-gray-600 mt-0.5 leading-relaxed">${body}</div>
            </div>
        </div>`;
    }


    function attachmentItem(a, ticketId, userRole) {
        const ext = (a.nombre_archivo || '').split('.').pop().toLowerCase();
        const iconMap = { pdf: 'documento', jpg: 'imagen', jpeg: 'imagen', png: 'imagen', txt: 'documento' };
        const icon = icono(iconMap[ext] || 'clip', 'w-5 h-5');

        // Human-readable size
        const bytes = a.tamanio || 0;
        const sizeStr = bytes >= 1024 * 1024
            ? (bytes / (1024 * 1024)).toFixed(1) + ' MB'
            : bytes >= 1024
                ? Math.round(bytes / 1024) + ' KB'
                : bytes + ' B';

        // MIME label
        const mimeLabel = (a.mime_type || '').replace('image/', '').replace('application/', '').replace('text/', '') || ext.toUpperCase();

        const canDelete = userRole === 'administrador' || userRole === 'tecnico';

        return `
        <div class="flex items-center justify-between gap-2 p-2.5 bg-blue-50 rounded-lg border border-blue-100 group"
             data-adj-id="${a.id}">
            <span class="shrink-0 text-blue-500">${icon}</span>
            <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-blue-900 truncate">${a.categoria === 'ingreso' ? '<span class="text-[10px] font-bold uppercase bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded mr-1">Ingreso</span>' : ''}${esc(a.nombre_archivo)}</p>
                <p class="text-[10px] text-blue-400">${mimeLabel.toUpperCase()} · ${sizeStr}</p>
            </div>
            <div class="flex items-center gap-1 shrink-0">
                <button type="button"
                   class="adj-download-btn text-xs font-bold text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-100 transition"
                   data-adj-id="${a.id}" data-filename="${esc(a.nombre_archivo)}"
                   title="Descargar">${icono('descargar', 'w-3.5 h-3.5 mr-1')}Descargar</button>
                ${canDelete ? `
                <button type="button"
                    class="adj-delete-btn text-xs text-red-400 hover:text-red-600 px-1.5 py-1 rounded hover:bg-red-50 transition opacity-0 group-hover:opacity-100 focus-within:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100"
                    data-adj-id="${a.id}" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>` : ''}
            </div>
        </div>`;
    }

    // ── Part row (in management table) ───────────────────────────────────────
    // Color del stock según el mínimo de cada repuesto (rojo = sin stock o negativo)
    function stockClass(p) {
        if (p.stock <= 0) return 'bg-red-100 text-red-700';
        if (p.stock_minimo > 0 && p.stock <= p.stock_minimo) return 'bg-amber-100 text-amber-700';
        return 'bg-green-100 text-green-700';
    }
    const stockMinTxt = p => p.stock_minimo > 0 ? `<span class="block text-[10px] text-gray-400 mt-0.5">mín. ${p.stock_minimo}</span>` : '';

    function partRow(p) {
        const stockCls = stockClass(p);
        const partJson = JSON.stringify(p).replace(/'/g, "\\'");
        return `
        <tr class="border-b hover:bg-gray-50 transition">
            <td class="py-3 pr-4 font-mono text-xs text-gray-500">${esc(p.codigo)}</td>
            <td class="py-3 pr-4 font-semibold">${esc(p.nombre)}</td>
            <td class="py-3 pr-4 text-gray-500 text-sm">${esc(p.proveedor)}</td>
            <td class="py-3 pr-4 text-center">
                <span class="px-2 py-0.5 rounded text-xs font-bold ${stockCls}">${p.stock}</span>${stockMinTxt(p)}
            </td>
            <td class="py-3 pr-4 text-right font-mono text-sm">${precioARS(p.precio)}</td>
            <td class="py-3 text-right space-x-2">
                <button onclick="ui.openEditPartForm(${p.id})"
                    class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>
                <button onclick="app.deletePart(${p.id})"
                    class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>
            </td>
        </tr>`;
    }

    // ── User row ─────────────────────────────────────────────────────────────
    function userRow(u) {
        const isProtected = u.username === 'admin';
        return `
        <tr class="border-b hover:bg-gray-50 transition ${u.activo ? '' : 'opacity-60'}">
            <td class="px-6 py-3 font-medium" translate="no">${esc(u.username)}</td>
            <td class="px-6 py-3 text-gray-600">${esc(u.nombre || '—')}</td>
            <td class="px-6 py-3 text-gray-500 text-xs">${esc(u.email || '—')}</td>
            <td class="px-6 py-3">
                ${rolBadge(u.rol)}
            </td>
            <td class="px-6 py-3 text-center">
                ${activoBadge(u.activo, 'Habilitado', 'Deshabilitado')}
            </td>
            <td class="px-6 py-3 text-right space-x-3">
                ${!isProtected ? `<button onclick="ui.openUserEditModalById(${Number(u.id)})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>` : ''}
                ${!isProtected ? `<button onclick="app.deleteUser(${u.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>` : '<span class="text-xs text-gray-300">Admin principal</span>'}
            </td>
        </tr>`;
    }

    // ── Product row ───────────────────────────────────────────────────────────
    function productRow(p) {
        const garantiaLabel = garantiaTexto(p.periodo_garantia_meses);
        return `
        <tr class="border-b hover:bg-gray-50 transition">
            <td class="px-6 py-3">
                <div class="font-semibold text-gray-800">${esc(p.marca)}</div>
                <div class="text-xs text-gray-500">${esc(p.modelo)}</div>
            </td>
            <td class="px-6 py-3">
                <span class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs font-medium">${esc(p.categoria)}</span>
            </td>
            <td class="px-6 py-3 font-mono text-xs text-gray-400">${esc(p.numero_parte || '—')}</td>
            <td class="px-6 py-3 text-center">
                <span class="px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs font-semibold">${garantiaLabel}</span>
            </td>
            <td class="px-6 py-3 text-right space-x-3">
                <button onclick="ui.openEditProductForm(${p.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>
                <button onclick="app.deleteProduct(${p.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>
            </td>
        </tr>`;
    }

    // ── Product category card ─────────────────────────────────────────────────
    function productCategoryCard(categoria, count) {
        return `
        <div class="bg-white p-4 rounded-xl shadow border border-gray-100 cursor-pointer hover:border-blue-300 transition"
            data-cat="${esc(categoria)}" onclick="document.getElementById('product-filter-categoria').value=this.dataset.cat; ui.filterProducts()">
            <p class="text-xs font-bold text-gray-400 uppercase">${esc(categoria)}</p>
            <p class="text-2xl font-black text-gray-800 mt-1">${count}</p>
            <p class="text-xs text-gray-400">producto${count !== 1 ? 's' : ''}</p>
        </div>`;
    }

    // ── Search result row ─────────────────────────────────────────────────────
    function searchResultRow(t) {
        return `
        <div class="bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow hover:border-blue-200 transition cursor-pointer p-5 flex items-start justify-between gap-4"
            onclick="app.viewTicket(${t.id})">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-3 mb-1 flex-wrap">
                    <span class="font-bold text-blue-600 text-sm">${esc(t.numero_rma)}</span>
                    ${statusBadge(t.estado)}
                    ${priorityBadge(t.prioridad)}
                    ${slaBadge(t.deadline_sla, t.estado)}
                </div>
                <p class="font-semibold text-gray-800">${esc(t.producto || 'Producto no especificado')}</p>
                <p class="text-xs text-gray-400 mt-1">Serie: <span class="font-mono">${esc(t.numero_serie)}</span> · Ticket #${t.id}</p>
                ${t.descripcion ? `<p class="text-xs text-gray-500 mt-2 line-clamp-2">${esc(t.descripcion)}</p>` : ''}
            </div>
            <div class="text-right shrink-0">
                <p class="text-xs text-gray-400">${new Date(t.fecha_creacion).toLocaleDateString(I18N.locale)}</p>
                ${t.tecnico_nombre ? `<p class="text-xs text-gray-500 mt-1">${icono('usuario', 'w-3 h-3 mr-0.5')}${esc(t.tecnico_nombre)}</p>` : ''}
            </div>
        </div>`;
    }

    // ── Ticket parts list (in detail view) ──────────────────────────────────
    function partUsed(p, editable = false) {
        if (!editable) {
            return `
            <div class="flex justify-between items-center py-1">
                <span class="text-sm">${esc(p.nombre)}
                    <span class="text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded font-bold ml-1">x${p.cantidad}</span>
                </span>
                <span class="font-mono text-gray-400 text-xs">${esc(p.codigo)}</span>
            </div>`;
        }
        return `
        <div class="flex items-center justify-between py-1.5 gap-2 group" data-part-id="${p.id}">
            <span class="text-sm flex-1 truncate">${esc(p.nombre)}
                <span class="font-mono text-gray-400 text-xs ml-1">${esc(p.codigo)}</span>
            </span>
            <div class="flex items-center gap-1 shrink-0">
                <button type="button"
                    class="part-qty-dec w-6 h-6 rounded border border-gray-200 text-gray-500 hover:bg-gray-100 text-xs font-bold flex items-center justify-center"
                    data-part-id="${p.id}" title="Reducir cantidad">−</button>
                <span class="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-bold min-w-[28px] text-center part-qty-label">${p.cantidad}</span>
                <button type="button"
                    class="part-qty-inc w-6 h-6 rounded border border-gray-200 text-gray-500 hover:bg-gray-100 text-xs font-bold flex items-center justify-center"
                    data-part-id="${p.id}" title="Aumentar cantidad">+</button>
                <button type="button"
                    class="part-remove ml-1 w-6 h-6 rounded text-red-400 hover:text-red-600 hover:bg-red-50 text-xs font-bold flex items-center justify-center border border-transparent hover:border-red-200 transition"
                    data-part-id="${p.id}" title="Quitar repuesto">${icono('x', 'w-3.5 h-3.5')}</button>
            </div>
        </div>`;
    }

    // ── Tag badge ────────────────────────────────────────────────────────────
    function tagBadge(tag, removable = false) {
        const color  = colorSeguro(tag.color, '#3b82f6');
        const bg     = color + '20';
        const border = color + '60';
        const rm = removable
            ? `<button type="button" class="tag-remove-btn ml-1 font-bold leading-none hover:opacity-70"
                data-nombre="${esc(tag.nombre)}" title="Quitar etiqueta">×</button>`
            : '';
        return `<span class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold"
            style="background:${bg};color:${color};border:1px solid ${border}">
            ${esc(tag.nombre)}${rm}
        </span>`;
    }

    function plantillaBtn(p) {
        return `<button type="button" class="diag-template px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-100 hover:bg-cyan-100 hover:text-cyan-700 text-gray-600 transition"
            data-text="${esc(p.texto)}">${esc(p.nombre)}</button>`;
    }

    function plantillaRow(p) {
        return `<div class="flex items-start gap-4 px-5 py-4 hover:bg-gray-50 group">
            <div class="flex-1 min-w-0">
                <p class="font-semibold text-sm text-gray-800">${esc(p.nombre)}</p>
                <p class="text-xs text-gray-400 mt-1 line-clamp-2">${esc(p.texto)}</p>
            </div>
            <div class="flex gap-2 shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100 transition">
                <button type="button" class="plantilla-edit-btn w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition"
                    data-id="${p.id}" data-nombre="${esc(p.nombre)}" data-orden="${esc(p.orden)}"
                    data-texto="${esc(p.texto)}" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>
                <button type="button" class="plantilla-del-btn w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition"
                    data-id="${p.id}" data-nombre="${esc(p.nombre)}" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>
            </div>
        </div>`;
    }

    function estadoRow(s) {
        const badge = `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold text-white"
            style="background:${colorSeguro(s.color)}">${esc(s.etiqueta)}</span>`;
        const activoBadge = s.activo
            ? '<span class="text-[10px] font-bold text-green-600 bg-green-50 px-2 py-0.5 rounded-full">Activo</span>'
            : '<span class="text-[10px] font-bold text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">Inactivo</span>';
        const finalBadge = s.es_final
            ? '<span class="text-[10px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">Final</span>'
            : '';
        return `<div class="flex items-center gap-4 px-5 py-4 hover:bg-gray-50 group">
            <span class="w-6 text-center text-xs text-gray-300 font-mono">${esc(s.orden)}</span>
            <div class="flex-1 flex items-center gap-3">
                ${badge}
                <span class="text-xs text-gray-400 font-mono">${s.valor !== s.etiqueta ? '← ' + esc(s.valor) : ''}</span>
                <div class="flex gap-1">${activoBadge}${finalBadge}</div>
            </div>
            <div class="flex gap-2 shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100 transition">
                <button type="button" class="estado-edit-btn w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition"
                    data-id="${s.id}" data-valor="${esc(s.valor)}" data-etiqueta="${esc(s.etiqueta)}"
                    data-color="${colorSeguro(s.color)}" data-orden="${esc(s.orden)}"
                    data-activo="${s.activo}" data-final="${s.es_final}" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>
                <button type="button" class="estado-del-btn w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition"
                    data-id="${s.id}" data-etiqueta="${esc(s.etiqueta)}" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>
            </div>
        </div>`;
    }

    // Public API
    // ── Admin panel rows ─────────────────────────────────────────────────────
    function adminUserRow(u) {
        const isProtected = u.username === 'admin';
        return `
        <tr class="hover:bg-gray-50 transition ${u.activo ? '' : 'opacity-60'}">
            <td class="px-5 py-3 text-sm font-medium text-gray-700" translate="no">${esc(u.username)}</td>
            <td class="px-5 py-3 text-gray-700">${esc(u.nombre || '—')}</td>
            <td class="px-5 py-3 text-gray-400 text-xs">${esc(u.email || '—')}</td>
            <td class="px-5 py-3"><span class="text-xs text-gray-400 capitalize">${esc(u.tipo_cliente || 'persona')}</span></td>
            <td class="px-5 py-3">${rolBadge(u.rol)}</td>
            <td class="px-5 py-3 text-center">${activoBadge(u.activo)}</td>
            <td class="px-5 py-3 text-right space-x-3">
                ${!isProtected ? `<button onclick="ui.openUserEditModalById(${Number(u.id)})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>` : ''}
                ${!isProtected ? `<button onclick="app.deleteUser(${u.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>` : '<span class="text-xs text-gray-300">Principal</span>'}
            </td>
        </tr>`;
    }

    function adminProductRow(p) {
        const m = p.periodo_garantia_meses || 0;
        const g = !m ? 'sin gar.' : m % 12 === 0 ? `${m / 12}a` : `${m}m`;
        return `
        <tr class="hover:bg-gray-50 transition">
            <td class="px-5 py-3">
                <span class="font-semibold text-gray-800">${esc(p.marca)}</span>
                <span class="text-gray-400 ml-1">${esc(p.modelo)}</span>
            </td>
            <td class="px-5 py-3"><span class="px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs font-medium">${esc(p.categoria)}</span></td>
            <td class="px-5 py-3 font-mono text-xs text-gray-400">${esc(p.numero_parte || '—')}</td>
            <td class="px-5 py-3 text-center"><span class="px-2 py-0.5 bg-blue-50 text-blue-600 rounded text-xs font-semibold">${g}</span></td>
            <td class="px-5 py-3 text-right space-x-3">
                <button onclick="ui.openAdminEditProduct(${p.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>
                <button onclick="app.deleteProduct(${p.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>
            </td>
        </tr>`;
    }

    function adminPartRow(p) {
        const stockCls = stockClass(p);
        return `
        <tr class="hover:bg-gray-50 transition">
            <td class="px-5 py-3 font-mono text-xs font-bold text-gray-600">${esc(p.codigo)}</td>
            <td class="px-5 py-3 font-medium text-gray-800">${esc(p.nombre)}</td>
            <td class="px-5 py-3 text-gray-500 text-xs">${esc(p.proveedor)}</td>
            <td class="px-5 py-3 text-center"><span class="px-2 py-0.5 rounded text-xs font-bold ${stockCls}">${p.stock} uds</span>${stockMinTxt(p)}</td>
            <td class="px-5 py-3 text-right font-semibold text-gray-700">${precioARS(p.precio)}</td>
            <td class="px-5 py-3 text-right space-x-3">
                <button onclick="ui.openAdminEditPart(${p.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition" aria-label="Editar" title="Editar">${icono('lapiz', 'w-4 h-4')}</button>
                <button onclick="app.deletePart(${p.id})" class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition" aria-label="Eliminar" title="Eliminar">${icono('papelera', 'w-4 h-4')}</button>
            </td>
        </tr>`;
    }

    return {
        statusClass, slaBadge, setSlaAvisoHoras, priorityBadge,
        badge, statusBadge, pintarEstado, rolBadge, activoBadge, garantiaBadge,
        ticketHead, COLS_TALLER, COLS_CLIENTE, diasEnTaller,
        ticketRow, ticketEmptyState, vacio, vacioFila,
        statCard,
        comment, commentEmptyState, stockMovRow, tagCard, creatorBadge, historyEntry,
        attachmentItem,
        partRow, partUsed,
        userRow,
        productRow, productCategoryCard,
        searchResultRow,
        adminUserRow, adminProductRow, adminPartRow,
        tagBadge, plantillaBtn, plantillaRow, estadoRow,
    };
})();
