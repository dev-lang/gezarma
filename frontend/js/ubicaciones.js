/**
 * ubicaciones.js — Dónde está guardado cada equipo y cada repuesto.
 *
 * - Detalle del ticket: tarjeta "Ubicación" con "Mover a…" y el historial de lugares.
 * - Lector de códigos: escanear la etiqueta del equipo (RMA) y después la del estante
 *   (U-0001) lo guarda ahí. Escanear un estante solo, muestra qué hay; un repuesto, dónde está.
 * - Administración → Ubicaciones: el árbol de lugares, qué hay en cada uno, etiquetas y
 *   "Para ordenar" (equipos sin ubicación o quietos, repuestos sin ubicación).
 * - Repuestos: columna, filtro, cambio en lote y etiqueta.
 * Las reglas están en el servidor (services/ubicaciones.py).
 */
const Ubic = (() => {
    const $ = id => document.getElementById(id);
    let _lista = null;
    let _pendiente = null;           // { ticket, hasta }: último equipo escaneado, esperando el estante
    const esTaller = () => ['administrador', 'tecnico'].includes(auth.getUser()?.role || '');
    const esAdmin = () => auth.getUser()?.role === 'administrador';

    async function lista(forzar = false) {
        if (!_lista || forzar) _lista = await api.request('ubicaciones');
        return _lista;
    }
    const elegibles = l => l.filter(u => u.activa && u.tipo !== 'externa');
    const nivel = u => (u.ruta.match(/ › /g) || []).length;
    const fechaCorta = iso => iso ? new Date(iso).toLocaleDateString(I18N.locale, { day: 'numeric', month: 'short' }) : '';
    const hace = iso => {
        if (!iso) return '';
        const d = Math.floor((Date.now() - Date.parse(iso)) / 86_400_000);
        return d <= 0 ? I18N.t('hoy') : d === 1 ? I18N.t('ayer') : I18N.t('hace {0} días', d);
    };

    function opciones(l, valor, { vacio = 'Sin ubicación' } = {}) {
        return `<option value="">${esc(I18N.t(vacio))}</option>` + elegibles(l).map(u =>
            `<option value="${u.id}" ${String(u.id) === String(valor ?? '') ? 'selected' : ''}>${esc(u.ruta)}</option>`).join('');
    }

    /** Llena un <select> existente con las ubicaciones (para formularios). */
    async function llenarSelect(id, valor, opts) {
        const sel = $(id);
        if (!sel) return;
        try { sel.innerHTML = opciones(await lista(), valor, opts); } catch { /* sin ubicaciones */ }
    }

    // ── Modal: elegir una ubicación ──────────────────────────────────────────
    async function elegir({ titulo = 'Mover a…', valor = null, ayuda = '' } = {}) {
        const l = await lista(true);
        if (!elegibles(l).length) {
            toast.warning(I18N.t(esAdmin() ? 'Todavía no hay ubicaciones: crealas en Administración → Ubicaciones.'
                : 'Todavía no hay ubicaciones: pedile a un administrador que las cree.'));
            return undefined;
        }
        return new Promise(resolve => {
            const div = document.createElement('div');
            div.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[70] p-4';
            div.setAttribute('data-modal', '');
            div.innerHTML = `
            <form class="bg-white rounded-xl shadow-2xl p-6 w-full max-w-md" role="dialog" aria-modal="true">
                <h3 class="text-lg font-bold text-gray-900 mb-1">${esc(I18N.t(titulo))}</h3>
                ${ayuda ? `<p class="text-sm text-gray-500 mb-3">${esc(I18N.t(ayuda))}</p>` : ''}
                <input type="search" data-filtro placeholder="${esc(I18N.t('Buscar ubicación…'))}" autocomplete="off"
                    class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                <select data-ubic size="8" class="w-full border border-gray-300 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">${opciones(l, valor)}</select>
                <div class="flex gap-3 mt-5">
                    <button type="button" data-cancelar class="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50 transition">${esc(I18N.t('Cancelar'))}</button>
                    <button type="submit" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition">${esc(I18N.t('Guardar acá'))}</button>
                </div>
            </form>`;
            const sel = div.querySelector('[data-ubic]'), filtro = div.querySelector('[data-filtro]');
            if (!sel.value && sel.options.length > 1 && valor == null) sel.selectedIndex = -1;
            filtro.addEventListener('input', () => {
                const q = filtro.value.trim().toLowerCase();
                [...sel.options].forEach(o => { o.hidden = !!q && o.value !== '' && !o.textContent.toLowerCase().includes(q); });
                const primera = [...sel.options].find(o => !o.hidden && o.value);
                if (q && primera) sel.value = primera.value;
            });
            const fin = r => { div.remove(); resolve(r); };
            div.querySelector('[data-cancelar]').addEventListener('click', () => fin(undefined));
            sel.addEventListener('dblclick', () => div.querySelector('form').requestSubmit());
            div.querySelector('form').addEventListener('submit', e => {
                e.preventDefault();
                if (sel.selectedIndex < 0) { sel.focus(); return; }
                fin(sel.value ? Number(sel.value) : null);
            });
            document.body.appendChild(div);
            filtro.focus();
        });
    }

    // ── Detalle del ticket ───────────────────────────────────────────────────
    function cargarDetalle(t) {
        const card = $('ubicacion-card');
        if (!card) return;
        if (!esTaller()) { card.classList.add('hidden'); return; }
        const afuera = t.estado === (window.Envios?.ESTADO) && t.envio_abierto;
        card.className = 'mt-6 border border-gray-200 rounded-lg p-4 flex flex-wrap items-center gap-3';
        card.innerHTML = `
            <span class="w-9 h-9 rounded-full ${t.ubicacion_ruta ? 'bg-blue-50 text-blue-600' : 'bg-amber-50 text-amber-600'} flex items-center justify-center shrink-0">${icono('pin', 'w-5 h-5')}</span>
            <div class="min-w-0 flex-1">
                <p class="text-xs font-semibold text-gray-500">${esc(I18N.t('Ubicación'))}</p>
                <p class="font-semibold text-gray-800 truncate max-sm:whitespace-normal max-sm:break-words">${t.ubicacion_ruta ? esc(t.ubicacion_ruta) : `<span class="text-amber-700">${esc(I18N.t('Sin ubicación'))}</span>`}</p>
                ${t.ubicacion_fecha ? `<p class="text-xs text-gray-400">${esc(I18N.t('Desde {0}', hace(t.ubicacion_fecha)))}</p>` : ''}
            </div>
            <div class="flex items-center gap-2 max-sm:w-full">
                ${afuera ? '' : `<button type="button" data-ubic-mover class="text-sm font-semibold text-blue-700 border border-blue-200 hover:bg-blue-50 px-3 py-1.5 rounded-lg max-sm:flex-1 max-sm:inline-flex max-sm:items-center max-sm:justify-center">${icono('pin', 'w-4 h-4 mr-1')}${esc(I18N.t('Mover a…'))}</button>`}
                <button type="button" data-ubic-historial class="text-sm text-gray-500 hover:text-gray-800 px-2 py-1.5" title="${esc(I18N.t('Por dónde pasó'))}">${icono('historial', 'w-4 h-4')}</button>
            </div>`;
        card.querySelector('[data-ubic-mover]')?.addEventListener('click', () => moverTicket(t.id, t.ubicacion_id));
        card.querySelector('[data-ubic-historial]').addEventListener('click', () => historial(t.id));
    }

    async function refrescarDetalle(ticketId) {
        if (ui.currentTicketId !== ticketId) return;
        const t = await api.getTicket(ticketId);
        if (ui._ticketCache) ui._ticketCache[ticketId] = t;
        cargarDetalle(t);
        ui.loadHistory(ticketId);
    }

    async function guardar(ticketId, ubicacionId, motivo = 'manual') {
        return api.request(`tickets/${ticketId}/ubicacion`, { method: 'PUT', body: JSON.stringify({ ubicacion_id: ubicacionId, motivo }) });
    }

    async function moverTicket(ticketId, actual) {
        const destino = await elegir({ titulo: 'Mover el equipo a…', valor: actual,
            ayuda: 'También podés escanear la etiqueta del equipo y después la del estante.' });
        if (destino === undefined) return;
        try {
            const r = await guardar(ticketId, destino);
            await refrescarDetalle(ticketId);
            if (!r.cambio) return;
            toast.deshacer(r.ubicacion_ruta ? I18N.t('Guardado en {0}.', r.ubicacion_ruta) : I18N.t('Quedó sin ubicación.'), async () => {
                await guardar(ticketId, actual ?? null);
                await refrescarDetalle(ticketId);
            });
        } catch (e) { toast.error(e.message); }
    }

    async function historial(ticketId) {
        let filas = [];
        try { filas = await api.request(`tickets/${ticketId}/ubicacion/historial`); } catch (e) { toast.error(e.message); return; }
        const MOTIVO = { manual: 'A mano', escaneo: 'Escaneado', mostrador: 'Ingreso', envio: 'Envío al fabricante',
                         regreso: 'Vuelta del fabricante', lote: 'En lote', importacion: 'Importación', alta: 'Al crearlo' };
        ventana(I18N.t('Por dónde pasó el equipo'), filas.length ? `
            <ol class="space-y-3">${filas.map(f => `
                <li class="border-l-2 border-blue-200 pl-3">
                    <p class="text-sm font-semibold text-gray-800">${esc(f.hacia || I18N.t('Sin ubicación'))}</p>
                    <p class="text-xs text-gray-500">${esc(new Date(f.fecha).toLocaleString(I18N.locale, { dateStyle: 'short', timeStyle: 'short', hour12: false }))}
                        · ${esc(f.usuario || '')} · ${esc(I18N.t(MOTIVO[f.motivo] || f.motivo || ''))}
                        ${f.desde ? `· ${esc(I18N.t('venía de {0}', f.desde))}` : ''}</p>
                </li>`).join('')}</ol>`
            : `<p class="text-sm text-gray-500">${esc(I18N.t('Todavía no se guardó en ninguna ubicación.'))}</p>`);
    }

    function ventana(titulo, html, { ancho = 'max-w-lg' } = {}) {
        const div = document.createElement('div');
        div.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-start sm:items-center justify-center z-[70] p-4 overflow-y-auto';
        div.setAttribute('data-modal', '');
        div.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl w-full ${ancho} my-auto" role="dialog" aria-modal="true">
            <div class="flex items-center justify-between px-5 py-4 border-b">
                <h3 class="font-bold text-gray-900">${esc(titulo)}</h3>
                <button type="button" data-cancelar class="w-9 h-9 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center" aria-label="${esc(I18N.t('Cerrar'))}">${icono('x', 'w-5 h-5')}</button>
            </div>
            <div class="p-5 max-h-[70vh] overflow-y-auto">${html}</div>
        </div>`;
        div.querySelector('[data-cancelar]').addEventListener('click', () => div.remove());
        div.addEventListener('click', e => { if (e.target === div) div.remove(); });
        document.body.appendChild(div);
        return div;
    }

    // ── Qué hay en una ubicación ─────────────────────────────────────────────
    const filaEquipo = e => `
        <li><button type="button" data-abrir-ticket="${e.id}" class="w-full text-left px-3 py-2 rounded-lg hover:bg-gray-50 flex items-center gap-3">
            <span class="min-w-0 flex-1"><span class="font-semibold text-blue-700" translate="no">${esc(e.numero_rma)}</span>
                <span class="text-gray-700">${esc(e.producto || '')}</span>
                <span class="block text-xs text-gray-400 truncate">${esc(e.cliente || '')}${e.ubicacion_ruta ? ' · ' + esc(e.ubicacion_ruta) : ''}</span></span>
            ${components.statusBadge(e.estado)}
            ${e.dias_quieto != null ? `<span class="text-xs tabular-nums ${e.dias_quieto >= 7 ? 'text-amber-700 font-semibold' : 'text-gray-400'}" title="${esc(I18N.t('Días en ese lugar'))}">${e.dias_quieto} d</span>` : ''}
        </button></li>`;
    const filaRepuesto = r => `
        <li class="px-3 py-2 flex items-center gap-3">
            <span class="font-mono text-xs font-bold text-gray-500" translate="no">${esc(r.codigo)}</span>
            <span class="flex-1 min-w-0 text-gray-800 truncate">${esc(r.nombre)}<span class="block text-xs text-gray-400">${esc(r.ubicacion_ruta || I18N.t('Sin ubicación'))}</span></span>
            <span class="text-xs text-gray-500 tabular-nums">${r.stock} ${esc(I18N.t('uds'))}</span>
        </li>`;

    function conectarTickets(div) {
        div.addEventListener('click', e => {
            const b = e.target.closest('[data-abrir-ticket]');
            if (b) { div.remove(); app.viewTicket(Number(b.dataset.abrirTicket)); }
        });
    }

    async function verContenido(uid) {
        let c;
        try { c = await api.request(`ubicaciones/${uid}/contenido`); } catch (e) { toast.error(e.message); return; }
        const seccion = (t, items, fila) => `<h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mt-1 mb-1">${esc(I18N.t(t))} · ${items.length}</h4>
            ${items.length ? `<ul class="divide-y mb-4 -mx-3">${items.map(fila).join('')}</ul>` : `<p class="text-sm text-gray-400 mb-4">${esc(I18N.t('Nada.'))}</p>`}`;
        const div = ventana(c.ubicacion.ruta, `
            <p class="text-xs text-gray-400 mb-3"><span translate="no">${esc(c.ubicacion.codigo || '')}</span>${c.ubicacion.nota ? ' · ' + esc(c.ubicacion.nota) : ''}</p>
            ${seccion('Equipos', c.equipos, filaEquipo)}${seccion('Repuestos', c.repuestos, filaRepuesto)}`, { ancho: 'max-w-2xl' });
        conectarTickets(div);
    }

    // ── Lector de códigos ────────────────────────────────────────────────────
    /** Lo llama recepcion.js después de abrir un ticket escaneado. */
    function equipoEscaneado(t) {
        if (!esTaller() || !t) return;
        _pendiente = { ticket: t, hasta: Date.now() + 90_000 };
        toast.info(I18N.t('Escaneá la etiqueta del estante para guardar {0} ahí.', t.numero_rma));
    }

    /** Un código leído que no es un RMA: ubicación o repuesto. Devuelve true si se usó. */
    async function escaneo(codigo) {
        if (!esTaller()) return false;
        let r;
        try { r = await api.request(`ubicaciones/escaneo?codigo=${encodeURIComponent(codigo)}`); } catch { return false; }
        if (r.tipo === 'ubicacion') {
            const p = _pendiente && _pendiente.hasta > Date.now() ? _pendiente.ticket : null;
            if (p && !r.externa) {
                _pendiente = null;
                try {
                    const anterior = (await api.getTicket(p.id)).ubicacion_id;
                    const res = await guardar(p.id, r.id, 'escaneo');
                    await refrescarDetalle(p.id);
                    toast.deshacer(I18N.t('{0} guardado en {1}.', p.numero_rma, res.ubicacion_ruta), async () => {
                        await guardar(p.id, anterior ?? null);
                        await refrescarDetalle(p.id);
                    });
                } catch (e) { toast.error(e.message); }
            } else {
                verContenido(r.id);
            }
            return true;
        }
        if (r.tipo === 'repuesto') {
            toast.info(`${r.codigo} · ${r.nombre}: ${r.ubicacion_ruta || I18N.t('sin ubicación')} (${I18N.t('stock')} ${r.stock})`);
            return true;
        }
        if (r.tipo === 'ticket') {
            const t = await api.getTicket(r.id);
            await ui.showTicketDetail(t);
            equipoEscaneado(t);
            return true;
        }
        return false;
    }

    // ── Administración → Ubicaciones ─────────────────────────────────────────
    async function cargarAdmin() {
        const raiz = $('ubicaciones-root');
        if (!raiz) return;
        let l, pend;
        try { [l, pend] = await Promise.all([lista(true), api.request('ubicaciones/pendientes')]); }
        catch (e) { raiz.innerHTML = `<p class="text-red-500 text-sm">${esc(e.message)}</p>`; return; }
        const n = { sin: pend.equipos_sin_ubicacion.length, quietos: pend.equipos_quietos.length, rep: pend.repuestos_sin_ubicacion.length };
        const chipPend = (clave, num, texto) => `
            <button type="button" data-pend="${clave}" ${num ? '' : 'disabled'}
                class="flex items-center gap-3 text-left bg-white border ${num ? 'border-amber-200 hover:border-amber-400' : 'border-gray-200 opacity-60'} rounded-xl px-4 py-3 transition">
                <span class="text-2xl font-bold tabular-nums ${num ? 'text-amber-600' : 'text-gray-300'}">${num}</span>
                <span class="text-sm text-gray-600 leading-tight">${esc(I18N.t(texto, pend.dias))}</span></button>`;
        const filas = l.map(u => {
            const externa = u.tipo === 'externa';
            const acc = (attr, ic, titulo, extra = '') => `<button type="button" ${attr}="${u.id}" title="${esc(I18N.t(titulo))}" aria-label="${esc(I18N.t(titulo))}"
                class="w-8 h-8 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition ${extra}">${icono(ic, 'w-4 h-4')}</button>`;
            return `
            <tr class="hover:bg-gray-50 ${u.activa ? '' : 'opacity-50'}">
                <td class="pl-4 pr-1 sm:px-5 py-2.5">
                    <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5" style="padding-left:${nivel(u) * 1.25}rem">
                        <span class="${externa ? 'text-fuchsia-500' : 'text-gray-400'}">${icono(externa ? 'camion' : 'pin', 'w-4 h-4')}</span>
                        <button type="button" data-ver="${u.id}" class="font-medium text-gray-800 hover:text-blue-700 text-left">${esc(u.nombre)}</button>
                        <span class="sm:hidden text-xs text-gray-400 tabular-nums whitespace-nowrap"><span class="font-mono" translate="no">${esc(u.codigo || '')}</span>${u.equipos || u.repuestos ? ` · ${u.equipos} · ${u.repuestos}` : ''}</span>
                        ${u.activa ? '' : components.badge('Desactivada', 'bg-gray-100 text-gray-500')}
                        ${externa ? `<span class="text-xs text-gray-400">${esc(I18N.t('la usa el sistema'))}</span>` : ''}
                    </div>
                    ${u.nota ? `<p class="text-xs text-gray-400" style="padding-left:${nivel(u) * 1.25 + 1.5}rem">${esc(u.nota)}</p>` : ''}
                </td>
                <td class="hidden sm:table-cell px-5 py-2.5 font-mono text-xs text-gray-500" translate="no">${esc(u.codigo || '')}</td>
                <td class="hidden sm:table-cell px-5 py-2.5 text-center tabular-nums text-sm">${u.equipos || '<span class="text-gray-300">0</span>'}</td>
                <td class="hidden sm:table-cell px-5 py-2.5 text-center tabular-nums text-sm">${u.repuestos || '<span class="text-gray-300">0</span>'}</td>
                <td class="px-2 sm:px-5 py-2.5 text-right"><div class="inline-flex flex-wrap justify-end max-w-[6.25rem] sm:max-w-none">
                    ${acc('data-ver', 'ojo', 'Ver qué hay')}
                    ${externa ? '' : acc('data-etiqueta', 'impresora', 'Imprimir etiqueta')}
                    ${externa || !esAdmin() ? '' : acc('data-sub', 'mas', 'Agregar adentro') + acc('data-editar', 'lapiz', 'Renombrar o mover')
                        + acc('data-activa', u.activa ? 'pausa' : 'play', u.activa ? 'Desactivar' : 'Activar')
                        + acc('data-borrar', 'papelera', 'Eliminar', 'hover:!text-red-600 hover:!bg-red-50')}
                </div></td>
            </tr>`;
        }).join('');
        raiz.innerHTML = `
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
                ${chipPend('sin', n.sin, 'Equipos sin ubicación')}
                ${chipPend('quietos', n.quietos, 'Equipos en el mismo lugar hace más de {0} días')}
                ${chipPend('rep', n.rep, 'Repuestos sin ubicación')}
            </div>
            <div class="bg-white rounded-2xl shadow border border-gray-100 overflow-hidden">
                <div class="p-5 border-b bg-gray-50 flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <h3 class="font-bold text-gray-800">${esc(I18N.t('Lugares del taller'))}</h3>
                        <p class="text-xs text-gray-400 mt-0.5">${esc(I18N.t('Depósitos, estantes, cajones y mesas. Imprimí la etiqueta de cada uno para escanearla.'))}</p>
                    </div>
                    ${esAdmin() ? `<button type="button" data-sub="" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg text-sm font-semibold shadow-sm transition">+ ${esc(I18N.t('Nueva ubicación'))}</button>` : ''}
                </div>
                ${l.length ? `<div class="overflow-x-auto"><table class="w-full text-sm text-left">
                    <thead><tr class="text-xs uppercase text-gray-400 border-b bg-gray-50">
                        <th class="pl-4 sm:px-5 py-3">${esc(I18N.t('Ubicación'))}</th><th class="hidden sm:table-cell px-5 py-3">${esc(I18N.t('Código'))}</th>
                        <th class="hidden sm:table-cell px-5 py-3 text-center">${esc(I18N.t('Equipos'))}</th><th class="hidden sm:table-cell px-5 py-3 text-center">${esc(I18N.t('Repuestos'))}</th>
                        <th class="px-2 sm:px-5 py-3 text-right">${esc(I18N.t('Acciones'))}</th></tr></thead>
                    <tbody class="divide-y divide-gray-50">${filas}</tbody></table></div>`
                : components.vacio({ icono: 'pin', titulo: 'Todavía no hay ubicaciones', texto: 'Creá los lugares donde guardás equipos y repuestos: por ejemplo "Depósito", y adentro "Estante A", "Estante B"…' })}
            </div>`;
        raiz.onclick = e => accionAdmin(e, l, pend);
    }

    async function accionAdmin(e, l, pend) {
        const b = e.target.closest('button');
        if (!b) return;
        const id = v => (v ? Number(v) : null);
        const u = l.find(x => String(x.id) === (b.dataset.ver || b.dataset.editar || b.dataset.activa || b.dataset.borrar || b.dataset.etiqueta || b.dataset.sub || '-'));
        try {
            if (b.dataset.pend) {
                const p = { sin: ['Equipos sin ubicación', pend.equipos_sin_ubicacion, filaEquipo],
                            quietos: [I18N.t('Equipos en el mismo lugar hace más de {0} días', pend.dias), pend.equipos_quietos, filaEquipo],
                            rep: ['Repuestos sin ubicación', pend.repuestos_sin_ubicacion, filaRepuesto] }[b.dataset.pend];
                const div = ventana(I18N.t(p[0]), `<ul class="divide-y -mx-3">${p[1].map(p[2]).join('')}</ul>
                    ${b.dataset.pend === 'rep' ? `<p class="text-xs text-gray-400 mt-3">${esc(I18N.t('Para ubicarlos de a varios: Administración → Repuestos, marcalos y usá "Cambiar ubicación".'))}</p>` : ''}`, { ancho: 'max-w-2xl' });
                conectarTickets(div);
            } else if ('ver' in b.dataset) verContenido(Number(b.dataset.ver));
            else if ('etiqueta' in b.dataset) Documentos.abrirUrl(`/ubicaciones/${b.dataset.etiqueta}/etiqueta`);
            else if ('sub' in b.dataset) {
                const nombre = await promptDialog(u ? I18N.t('Nueva ubicación dentro de {0}', u.ruta) : I18N.t('Nueva ubicación'), '', { okLabel: I18N.t('Crear') });
                if (!nombre?.trim()) return;
                await api.request('ubicaciones', { method: 'POST', body: JSON.stringify({ nombre: nombre.trim(), padre_id: u ? u.id : null }) });
                toast.success(I18N.t('Ubicación creada.'));
                cargarAdmin();
            } else if ('editar' in b.dataset) editarAdmin(u, l);
            else if ('activa' in b.dataset) {
                await api.request(`ubicaciones/${u.id}`, { method: 'PUT', body: JSON.stringify({ activa: !u.activa }) });
                toast.success(I18N.t(u.activa ? 'Ubicación desactivada.' : 'Ubicación activada.'));
                cargarAdmin();
            } else if ('borrar' in b.dataset) {
                if (!await confirmDialog(I18N.t('¿Eliminar la ubicación?'), u.ruta, I18N.t('Eliminar'), { peligro: true })) return;
                await api.request(`ubicaciones/${u.id}`, { method: 'DELETE' });
                toast.success(I18N.t('Ubicación eliminada.'));
                cargarAdmin();
            }
        } catch (err) { toast.error(err.message); }
    }

    function editarAdmin(u, l) {
        const prohibidos = new Set([u.id]);
        let cambio = true;
        while (cambio) { cambio = false; l.forEach(x => { if (x.padre_id && prohibidos.has(x.padre_id) && !prohibidos.has(x.id)) { prohibidos.add(x.id); cambio = true; } }); }
        const padres = `<option value="">${esc(I18N.t('— En el nivel principal —'))}</option>` +
            elegibles(l).filter(x => !prohibidos.has(x.id)).map(x => `<option value="${x.id}" ${x.id === u.padre_id ? 'selected' : ''}>${esc(x.ruta)}</option>`).join('');
        const div = ventana(I18N.t('Editar ubicación'), `
            <form class="space-y-4">
                <div><label class="block text-sm font-semibold text-gray-700 mb-1" for="ub-ed-nombre">${esc(I18N.t('Nombre'))}</label>
                    <input id="ub-ed-nombre" maxlength="60" required class="w-full border rounded-lg px-3 py-2" value="${esc(u.nombre)}"></div>
                <div><label class="block text-sm font-semibold text-gray-700 mb-1" for="ub-ed-padre">${esc(I18N.t('Está dentro de'))}</label>
                    <select id="ub-ed-padre" class="w-full border rounded-lg px-3 py-2 bg-white">${padres}</select></div>
                <div><label class="block text-sm font-semibold text-gray-700 mb-1" for="ub-ed-nota">${esc(I18N.t('Nota'))} <span class="font-normal text-gray-400">${esc(I18N.t('(opcional)'))}</span></label>
                    <input id="ub-ed-nota" maxlength="200" class="w-full border rounded-lg px-3 py-2" value="${esc(u.nota || '')}" placeholder="${esc(I18N.t('Ej.: segundo piso, al fondo'))}"></div>
                <div class="flex gap-3 pt-2"><button type="button" data-cancelar class="flex-1 px-4 py-2 border border-gray-300 rounded-lg font-semibold hover:bg-gray-50">${esc(I18N.t('Cancelar'))}</button>
                    <button type="submit" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700">${esc(I18N.t('Guardar'))}</button></div>
            </form>`, { ancho: 'max-w-md' });
        div.querySelector('form [data-cancelar]').addEventListener('click', () => div.remove());
        div.querySelector('form').addEventListener('submit', async e => {
            e.preventDefault();
            try {
                await api.request(`ubicaciones/${u.id}`, { method: 'PUT', body: JSON.stringify({
                    nombre: $('ub-ed-nombre').value.trim(), padre_id: Number($('ub-ed-padre').value) || null, nota: $('ub-ed-nota').value }) });
                div.remove();
                toast.success(I18N.t('Cambios guardados.'));
                cargarAdmin();
            } catch (err) { toast.error(err.message); }
        });
        $('ub-ed-nombre').focus();
    }

    // ── Repuestos: filtro, selección y cambio en lote ────────────────────────
    async function filtroRepuestos() {
        const sel = $('admin-parts-ubic');
        if (!sel) return;
        const valor = sel.value;
        let l = [];
        try { l = await lista(true); } catch { /* sin ubicaciones */ }
        sel.innerHTML = `<option value="">${esc(I18N.t('Todas las ubicaciones'))}</option><option value="-">${esc(I18N.t('Sin ubicación'))}</option>` +
            elegibles(l).map(u => `<option value="${u.id}">${esc(u.ruta)}</option>`).join('');
        sel.value = [...sel.options].some(o => o.value === valor) ? valor : '';
    }

    function filtrar(parts) {
        const v = $('admin-parts-ubic')?.value || '';
        if (!v) return parts;
        if (v === '-') return parts.filter(p => !p.ubicacion_id);
        const ids = new Set([Number(v)]);
        let cambio = true;
        while (cambio) { cambio = false; (_lista || []).forEach(u => { if (u.padre_id && ids.has(u.padre_id) && !ids.has(u.id)) { ids.add(u.id); cambio = true; } }); }
        return parts.filter(p => ids.has(p.ubicacion_id));
    }

    const seleccionados = () => [...document.querySelectorAll('#admin-parts-list-body [data-sel-part]:checked')].map(c => Number(c.dataset.selPart));
    function pintarSeleccion() {
        const n = seleccionados().length, barra = $('admin-parts-lote');
        if (!barra) return;
        barra.classList.toggle('hidden', !n);
        barra.classList.toggle('flex', !!n);
        $('admin-parts-lote-n').textContent = I18N.t(n === 1 ? '1 repuesto seleccionado' : '{0} repuestos seleccionados', n);
        const todos = $('admin-parts-sel-todos');
        const cajas = document.querySelectorAll('#admin-parts-list-body [data-sel-part]');
        if (todos) { todos.checked = n > 0 && n === cajas.length; todos.indeterminate = n > 0 && n < cajas.length; }
    }

    async function moverLote() {
        const ids = seleccionados();
        if (!ids.length) return;
        const destino = await elegir({ titulo: I18N.t('Guardar {0} repuestos en…', ids.length) });
        if (destino === undefined) return;
        try {
            const r = await api.request('parts/ubicacion', { method: 'POST', body: JSON.stringify({ ids, ubicacion_id: destino }) });
            toast.success(I18N.t('{0} repuestos movidos.', r.movidos));
            await ui.recargarRepuestosAdmin?.();
        } catch (e) { toast.error(e.message); }
    }

    function conectarRepuestos() {
        const cuerpo = $('admin-parts-list-body');
        if (!cuerpo || cuerpo.dataset.ubicConectado) return;
        cuerpo.dataset.ubicConectado = '1';
        cuerpo.addEventListener('change', e => { if (e.target.matches('[data-sel-part]')) pintarSeleccion(); });
        cuerpo.addEventListener('click', e => {
            const b = e.target.closest('[data-etiqueta-part]');
            if (b) Documentos.abrirUrl(`/parts/${b.dataset.etiquetaPart}/etiqueta`);
        });
        $('admin-parts-sel-todos')?.addEventListener('change', e => {
            document.querySelectorAll('#admin-parts-list-body [data-sel-part]').forEach(c => { c.checked = e.target.checked; });
            pintarSeleccion();
        });
        $('admin-parts-ubic')?.addEventListener('change', () => ui.adminRenderParts());
        $('admin-parts-lote-mover')?.addEventListener('click', moverLote);
        $('admin-parts-lote-limpiar')?.addEventListener('click', () => {
            document.querySelectorAll('#admin-parts-list-body [data-sel-part]').forEach(c => { c.checked = false; });
            pintarSeleccion();
        });
        filtroRepuestos();
    }

    return { lista, llenarSelect, elegir, cargarDetalle, moverTicket, historial, verContenido, equipoEscaneado, escaneo,
             cargarAdmin, filtrar, pintarSeleccion, conectarRepuestos, filtroRepuestos, invalidar: () => { _lista = null; } };
})();
window.Ubic = Ubic;
