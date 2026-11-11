/**
 * envios.js — Equipos que se mandan a la garantía del fabricante o a un servicio oficial.
 *
 * - Detalle del ticket: "Enviar al fabricante" (destino, N° de caso, guía, accesorios, fecha
 *   estimada…). El ticket pasa solo a "En servicio técnico oficial" y la ubicación a "Fuera
 *   del taller". Cuando vuelve: "Registrar vuelta" (resultado, serie nueva si lo cambiaron,
 *   comprobante y dónde se guarda); el ticket vuelve a "Equipo recibido".
 * - Pantalla "Fuera del taller": todo lo que está afuera, cuántos días lleva, los atrasados
 *   y exportar a Excel / CSV.
 * El cliente solo ve el estado. Las reglas están en el servidor (services/envios.py).
 */
const Envios = (() => {
    const ESTADO = 'En servicio técnico oficial';
    const $ = id => document.getElementById(id);
    const esTaller = () => ['administrador', 'tecnico'].includes(auth.getUser()?.role || '');
    const RESULTADOS = [
        ['reparado', 'Reparado'], ['reemplazado', 'Reemplazado por otro equipo'],
        ['rechazado', 'Rechazado (sin garantía)'], ['sin_falla', 'Sin falla'],
    ];
    const COLOR_RES = { reparado: 'bg-emerald-100 text-emerald-700', reemplazado: 'bg-blue-100 text-blue-700',
                        rechazado: 'bg-red-100 text-red-700', sin_falla: 'bg-gray-100 text-gray-700' };
    const st = { estado: 'enviado', destino: '', atrasados: false };

    const fecha = iso => iso ? new Date(iso).toLocaleDateString(I18N.locale, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
    const hoyLocal = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
    const aInput = iso => { if (!iso) return ''; const d = new Date(iso); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
    /** "2026-11-10" → ISO; si es hoy, la hora actual (el servidor no acepta fechas futuras). */
    const deInput = (v, { pasado = true } = {}) => {
        if (!v) return null;
        if (pasado && v === hoyLocal()) return new Date().toISOString();
        return new Date(`${v}T12:00:00`).toISOString();
    };
    const dias = n => n === 1 ? I18N.t('1 día') : I18N.t('{0} días', n);
    const finalDe = t => {
        const cfg = (ui._estadosCache || []).find(s => s.valor === t.estado);
        return cfg ? cfg.es_final : ['Cerrado', 'Cancelado'].includes(t.estado);
    };

    // ── Detalle del ticket ───────────────────────────────────────────────────
    async function cargarDetalle(t) {
        const card = $('externo-card');
        if (!card) return;
        if (!esTaller()) { card.classList.add('hidden'); return; }
        let envios = [];
        try { envios = await api.request(`tickets/${t.id}/envios`); } catch { /* sin permiso o error de red */ }
        if (ui.currentTicketId !== t.id) return;
        const abierto = envios.find(e => e.estado === 'enviado');
        const anteriores = envios.filter(e => e.estado !== 'enviado');
        if (!abierto && !anteriores.length && (finalDe(t) || t.estado === 'Enviado al cliente')) { card.classList.add('hidden'); return; }
        const dato = (k, v) => v ? `<div><dt class="text-xs text-gray-500">${esc(I18N.t(k))}</dt><dd class="font-medium text-gray-800 break-words">${esc(v)}</dd></div>` : '';
        const resumenAbierto = e => `
            <div class="flex flex-wrap items-start gap-3">
                <span class="w-9 h-9 rounded-full bg-fuchsia-50 text-fuchsia-600 flex items-center justify-center shrink-0">${icono('camion', 'w-5 h-5')}</span>
                <div class="flex-1 min-w-0">
                    <p class="text-xs font-semibold text-fuchsia-700">${esc(I18N.t('En el servicio técnico oficial'))}</p>
                    <p class="font-bold text-gray-900">${esc(e.destino)}</p>
                    <p class="text-sm ${e.atrasado ? 'text-red-600 font-semibold' : 'text-gray-500'}">
                        ${esc(I18N.t('Enviado el {0}', fecha(e.fecha_envio)))}${e.dias ? ` · ${esc(I18N.t('hace {0}', dias(e.dias)))}` : ''}
                        ${e.fecha_estimada ? ` · ${esc(I18N.t(e.atrasado ? 'tenía que volver el {0}' : 'vuelve aprox. el {0}', fecha(e.fecha_estimada)))}` : ''}</p>
                </div>
            </div>
            <dl class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm mt-3">
                ${dato('N° de caso', e.numero_caso)}${dato('Transporte', e.transportista)}${dato('Guía', e.guia)}
                ${dato('Qué se mandó', e.contenido)}${dato('Accesorios', e.accesorios)}${dato('Envió', e.enviado_por)}
            </dl>
            ${e.nota ? `<p class="text-sm text-gray-600 mt-2 whitespace-pre-line">${esc(e.nota)}</p>` : ''}
            <div class="flex flex-wrap gap-2 mt-4">
                <button type="button" data-env-vuelta class="bg-fuchsia-600 hover:bg-fuchsia-700 text-white px-4 py-2 rounded-lg text-sm font-semibold shadow-sm">${icono('bandeja', 'w-4 h-4 mr-1')}${esc(I18N.t('Registrar vuelta'))}</button>
                <button type="button" data-env-editar class="border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg text-sm font-semibold">${icono('lapiz', 'w-4 h-4 mr-1')}${esc(I18N.t('Editar datos'))}</button>
            </div>`;
        const filaAnterior = e => `
            <li class="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span class="font-semibold text-gray-800">${esc(e.destino)}</span>
                <span class="text-gray-500">${esc(fecha(e.fecha_envio))} → ${esc(fecha(e.fecha_recepcion))} · ${esc(dias(e.dias))}</span>
                ${components.badge(I18N.t(e.resultado_texto || e.resultado || ''), COLOR_RES[e.resultado] || 'bg-gray-100 text-gray-700')}
                ${e.numero_caso ? `<span class="text-xs text-gray-400">${esc(I18N.t('Caso {0}', e.numero_caso))}</span>` : ''}
                ${e.serie_nueva ? `<span class="text-xs text-gray-500">${esc(I18N.t('Serie nueva: {0}', e.serie_nueva))}</span>` : ''}
                ${e.comprobante ? `<span class="text-xs text-gray-400">${esc(I18N.t('Comprobante {0}', e.comprobante))}</span>` : ''}
            </li>`;
        const puedeEnviar = !abierto && !finalDe(t) && t.estado !== 'Enviado al cliente';
        card.className = `mt-6 border rounded-lg p-4 ${abierto ? 'border-fuchsia-200 bg-fuchsia-50/40' : 'border-gray-200'}`;
        card.innerHTML = `
            ${abierto ? resumenAbierto(abierto) : ''}
            ${puedeEnviar ? `<div class="flex flex-wrap items-center gap-3">
                <span class="w-9 h-9 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center shrink-0">${icono('camion', 'w-5 h-5')}</span>
                <p class="flex-1 min-w-0 text-sm text-gray-600">${esc(I18N.t('¿Lo tiene que ver el fabricante? Registrá el envío y seguilo hasta que vuelva.'))}</p>
                <button type="button" data-env-enviar class="text-sm font-semibold text-fuchsia-700 border border-fuchsia-200 hover:bg-fuchsia-50 px-3 py-1.5 rounded-lg max-sm:w-full">${esc(I18N.t('Enviar al fabricante'))}</button>
            </div>` : ''}
            ${anteriores.length ? `<div class="${abierto || puedeEnviar ? 'mt-4 pt-3 border-t' : ''}">
                <p class="text-xs font-semibold text-gray-500">${esc(I18N.t('Envíos anteriores'))}</p>
                <ul class="divide-y">${anteriores.map(filaAnterior).join('')}</ul></div>` : ''}`;
        card.querySelector('[data-env-enviar]')?.addEventListener('click', () => formEnvio(t.id));
        card.querySelector('[data-env-editar]')?.addEventListener('click', () => formEnvio(t.id, abierto));
        card.querySelector('[data-env-vuelta]')?.addEventListener('click', () => formVuelta(abierto));
    }

    async function refrescar(ticketId) {
        if (typeof Gestion !== 'undefined' && ui.currentTicketId === ticketId) await Gestion.refrescar(ticketId);
        if ($('externos-section')) cargar();
    }

    // ── Formularios ──────────────────────────────────────────────────────────
    function modal(titulo, cuerpo, okTexto) {
        const div = document.createElement('div');
        div.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-start sm:items-center justify-center z-[70] p-4 overflow-y-auto';
        div.setAttribute('data-modal', '');
        div.innerHTML = `
        <form class="bg-white rounded-xl shadow-2xl w-full max-w-xl my-auto" role="dialog" aria-modal="true" novalidate>
            <div class="flex items-center justify-between px-5 py-4 border-b">
                <h3 class="font-bold text-gray-900">${esc(titulo)}</h3>
                <button type="button" data-cerrar class="w-9 h-9 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center" aria-label="${esc(I18N.t('Cerrar'))}">${icono('x', 'w-5 h-5')}</button>
            </div>
            <div class="p-5 space-y-4 max-h-[70vh] overflow-y-auto">${cuerpo}
                <p data-error class="hidden text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"></p></div>
            <div class="flex gap-3 px-5 py-4 border-t">
                <button type="button" data-cerrar class="flex-1 px-4 py-2 border border-gray-300 rounded-lg font-semibold hover:bg-gray-50">${esc(I18N.t('Cancelar'))}</button>
                <button type="submit" data-ok class="flex-1 px-4 py-2 bg-fuchsia-600 hover:bg-fuchsia-700 text-white rounded-lg font-semibold">${esc(okTexto)}</button>
            </div>
        </form>`;
        div.querySelectorAll('[data-cerrar]').forEach(b => b.addEventListener('click', () => div.remove()));
        document.body.appendChild(div);
        const error = msg => { const p = div.querySelector('[data-error]'); p.textContent = msg; p.classList.toggle('hidden', !msg); if (msg) p.scrollIntoView({ block: 'nearest' }); };
        return { div, form: div.querySelector('form'), error };
    }
    const campo = (id, etiqueta, html, { opcional = false, ayuda = '' } = {}) => `
        <div><label class="block text-sm font-semibold text-gray-700 mb-1" for="${id}">${esc(I18N.t(etiqueta))}${opcional ? ` <span class="font-normal text-gray-400">${esc(I18N.t('(opcional)'))}</span>` : ''}</label>
            ${html}${ayuda ? `<p class="text-xs text-gray-400 mt-1">${esc(I18N.t(ayuda))}</p>` : ''}</div>`;
    const input = (id, valor = '', extra = '') => `<input id="${id}" value="${esc(valor || '')}" ${extra}
        class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-500">`;

    async function formEnvio(ticketId, envio = null) {
        let destinos = [];
        try { destinos = await api.request('envios/destinos'); } catch { /* sin sugerencias */ }
        const e = envio || {};
        const { div, form, error } = modal(I18N.t(envio ? 'Datos del envío' : 'Enviar al fabricante'), `
            ${envio ? '' : `<p class="text-sm text-gray-500 -mt-1">${esc(I18N.t('El ticket pasa a "En servicio técnico oficial" y el equipo queda "Fuera del taller" hasta que registres la vuelta. El cliente solo ve el estado.'))}</p>`}
            ${campo('env-destino', 'Fabricante o servicio oficial *', input('env-destino', e.destino, `maxlength="120" list="env-destinos" placeholder="${esc(I18N.t('Ej.: Lenovo — servicio oficial'))}" autocomplete="off"`)
                + `<datalist id="env-destinos">${destinos.map(d => `<option value="${esc(d)}">`).join('')}</datalist>`)}
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                ${campo('env-caso', 'N° de caso del fabricante', input('env-caso', e.numero_caso, 'maxlength="60"'), { opcional: true })}
                ${envio ? '' : campo('env-fecha', 'Fecha de envío', input('env-fecha', hoyLocal(), `type="date" max="${hoyLocal()}"`))}
                ${campo('env-transporte', 'Transporte', input('env-transporte', e.transportista, `maxlength="80" placeholder="${esc(I18N.t('Ej.: Andreani, retiro del fabricante'))}"`), { opcional: true })}
                ${campo('env-guia', 'N° de guía', input('env-guia', e.guia, 'maxlength="80"'), { opcional: true })}
                ${campo('env-contenido', 'Qué se mandó', input('env-contenido', e.contenido, `maxlength="120" placeholder="${esc(I18N.t('Ej.: equipo completo, solo la placa'))}"`), { opcional: true })}
                ${campo('env-estimada', 'Vuelve aprox. el', input('env-estimada', aInput(e.fecha_estimada), 'type="date"'), { opcional: true, ayuda: 'Si pasa la fecha y no volvió, se marca como atrasado.' })}
            </div>
            ${campo('env-accesorios', 'Accesorios que van con el equipo', input('env-accesorios', e.accesorios, `maxlength="300" placeholder="${esc(I18N.t('Ej.: cargador, funda'))}"`), { opcional: true })}
            ${campo('env-nota', 'Nota', `<textarea id="env-nota" rows="2" maxlength="2000" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-500">${esc(e.nota || '')}</textarea>`, { opcional: true })}`,
            I18N.t(envio ? 'Guardar' : 'Registrar envío'));
        $('env-destino').focus();
        form.addEventListener('submit', async ev => {
            ev.preventDefault();
            error('');
            const destino = $('env-destino').value.trim();
            if (!destino) { error(I18N.t('Indicá a qué fabricante o servicio se manda.')); $('env-destino').focus(); return; }
            const cuerpo = {
                destino, numero_caso: $('env-caso').value.trim() || null, transportista: $('env-transporte').value.trim() || null,
                guia: $('env-guia').value.trim() || null, contenido: $('env-contenido').value.trim() || null,
                accesorios: $('env-accesorios').value.trim() || null, nota: $('env-nota').value.trim() || null,
                fecha_estimada: deInput($('env-estimada').value, { pasado: false }),
            };
            if (!envio) cuerpo.fecha_envio = deInput($('env-fecha').value);
            const ok = div.querySelector('[data-ok]');
            ok.disabled = true;
            try {
                if (envio) await api.request(`envios/${envio.id}`, { method: 'PUT', body: JSON.stringify(cuerpo) });
                else await api.request(`tickets/${ticketId}/envios`, { method: 'POST', body: JSON.stringify(cuerpo) });
                div.remove();
                toast.success(I18N.t(envio ? 'Datos del envío guardados.' : 'Envío registrado: el equipo está en el servicio técnico oficial.'));
                await refrescar(ticketId);
                contador();
            } catch (err) { error(err.message); ok.disabled = false; }
        });
    }

    async function formVuelta(envio) {
        const ubic = typeof Ubic !== 'undefined';
        const { div, form, error } = modal(I18N.t('Volvió de {0}', envio.destino), `
            <fieldset><legend class="block text-sm font-semibold text-gray-700 mb-2">${esc(I18N.t('¿Qué resolvió el fabricante? *'))}</legend>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">${RESULTADOS.map(([v, txt]) => `
                    <label class="flex items-center gap-2 border border-gray-200 rounded-lg px-3 py-2 cursor-pointer hover:bg-gray-50 has-[:checked]:border-fuchsia-400 has-[:checked]:bg-fuchsia-50 text-sm">
                        <input type="radio" name="env-resultado" value="${v}" class="accent-fuchsia-600">${esc(I18N.t(txt))}</label>`).join('')}
                </div></fieldset>
            <div id="env-serie-wrap" class="hidden">${campo('env-serie', 'N° de serie del equipo nuevo *', input('env-serie', '', 'maxlength="80" spellcheck="false" autocapitalize="characters"'), { ayuda: 'Se actualiza en el ticket (queda el anterior en el historial).' })}</div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                ${campo('env-fecha-vuelta', 'Fecha en que volvió', input('env-fecha-vuelta', hoyLocal(), `type="date" max="${hoyLocal()}"`))}
                ${campo('env-comprobante', 'Comprobante / N° de orden', input('env-comprobante', '', 'maxlength="80"'), { opcional: true })}
            </div>
            ${ubic ? campo('env-ubicacion', 'Dónde se guarda', `<select id="env-ubicacion" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-fuchsia-500"><option value="">${esc(I18N.t('Sin ubicación'))}</option></select>`, { opcional: true }) : ''}
            ${campo('env-nota-vuelta', 'Nota', `<textarea id="env-nota-vuelta" rows="2" maxlength="2000" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-500" placeholder="${esc(I18N.t('Ej.: cambiaron la placa madre'))}"></textarea>`, { opcional: true })}
            <p class="text-xs text-gray-400">${esc(I18N.t('Adjuntá el informe o el comprobante del fabricante en la pestaña "Adjuntos" del ticket.'))}</p>`,
            I18N.t('Registrar vuelta'));
        if (ubic) Ubic.llenarSelect('env-ubicacion', null);
        form.addEventListener('change', ev => {
            if (ev.target.name === 'env-resultado') $('env-serie-wrap').classList.toggle('hidden', ev.target.value !== 'reemplazado');
        });
        form.querySelector('input[name=env-resultado]').focus();
        form.addEventListener('submit', async ev => {
            ev.preventDefault();
            error('');
            const resultado = form.querySelector('input[name=env-resultado]:checked')?.value;
            if (!resultado) { error(I18N.t('Elegí qué resolvió el fabricante.')); return; }
            const serie = $('env-serie').value.trim();
            if (resultado === 'reemplazado' && !serie) { error(I18N.t('Cargá el N° de serie del equipo nuevo.')); $('env-serie').focus(); return; }
            const ok = div.querySelector('[data-ok]');
            ok.disabled = true;
            try {
                await api.request(`envios/${envio.id}/recepcion`, { method: 'POST', body: JSON.stringify({
                    resultado, serie_nueva: resultado === 'reemplazado' ? serie : null,
                    fecha_recepcion: deInput($('env-fecha-vuelta').value), comprobante: $('env-comprobante').value.trim() || null,
                    nota_recepcion: $('env-nota-vuelta').value.trim() || null,
                    ubicacion_id: ubic ? (Number($('env-ubicacion').value) || null) : null }) });
                div.remove();
                toast.success(I18N.t('Vuelta registrada: el ticket pasó a "Equipo recibido".'));
                await refrescar(envio.ticket_id);
                contador();
            } catch (err) { error(err.message); ok.disabled = false; }
        });
    }

    /** Lo llama gestion.js cuando se elige este estado en el selector o se intenta salir de él. */
    /** Devuelve true si se encargó (abrió un formulario); false si el cambio de estado puede seguir normal. */
    async function desdeSelector(ticketId, { saliendo = false } = {}) {
        if (!saliendo) { formEnvio(ticketId); return true; }
        let envios = [];
        try { envios = await api.request(`tickets/${ticketId}/envios`); } catch { return false; }
        const abierto = envios.find(e => e.estado === 'enviado');
        if (!abierto) return false;
        toast.info(I18N.t('Primero registrá la vuelta del servicio técnico oficial.'));
        formVuelta(abierto);
        return true;
    }

    // ── Pantalla "Fuera del taller" ──────────────────────────────────────────
    async function abrir() {
        if (!esTaller()) return;
        await ui.showSection('externos');
        $('externos-cuerpo').addEventListener('click', e => {
            const b = e.target.closest('[data-abrir-ticket]');
            if (b) app.viewTicket(Number(b.dataset.abrirTicket));
        });
        document.querySelectorAll('[data-ext-estado]').forEach(b => b.addEventListener('click', () => { st.estado = b.dataset.extEstado; cargar(); }));
        $('externos-destino').addEventListener('change', e => { st.destino = e.target.value; cargar(); });
        $('externos-atrasados').addEventListener('change', e => { st.atrasados = e.target.checked; cargar(); });
        document.querySelectorAll('[data-ext-exportar]').forEach(b => b.addEventListener('click', () => exportar(b.dataset.extExportar)));
        try {
            const destinos = await api.request('envios/destinos');
            $('externos-destino').innerHTML = `<option value="">${esc(I18N.t('Todos los destinos'))}</option>` +
                destinos.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
            $('externos-destino').value = destinos.includes(st.destino) ? st.destino : '';
        } catch { /* sin destinos */ }
        $('externos-atrasados').checked = st.atrasados;
        await cargar();
    }

    function consulta() {
        const q = new URLSearchParams({ estado: st.estado });
        if (st.destino) q.set('destino', st.destino);
        if (st.atrasados) q.set('atrasados', 'true');
        return q;
    }

    async function cargar() {
        const cuerpo = $('externos-cuerpo');
        if (!cuerpo) return;
        document.querySelectorAll('[data-ext-estado]').forEach(b => {
            const activo = b.dataset.extEstado === st.estado;
            b.classList.toggle('bg-fuchsia-600', activo); b.classList.toggle('text-white', activo);
            b.setAttribute('aria-pressed', activo);
        });
        $('externos-atrasados-wrap').classList.toggle('hidden', st.estado !== 'enviado');
        let r;
        try { r = await api.request(`envios?${consulta()}`); } catch (e) { cuerpo.innerHTML = `<p class="text-red-500 text-sm">${esc(e.message)}</p>`; return; }
        $('externos-resumen').innerHTML = `
            <span class="inline-flex items-center gap-2"><span class="text-2xl font-bold text-fuchsia-700 tabular-nums">${r.resumen.afuera}</span><span class="text-sm text-gray-600">${esc(I18N.t('equipos afuera'))}</span></span>
            <span class="inline-flex items-center gap-2"><span class="text-2xl font-bold tabular-nums ${r.resumen.atrasados ? 'text-red-600' : 'text-gray-300'}">${r.resumen.atrasados}</span><span class="text-sm text-gray-600">${esc(I18N.t('atrasados'))}</span></span>`;
        if (!r.envios.length) {
            cuerpo.innerHTML = `<div class="bg-white rounded-2xl shadow border border-gray-100">${components.vacio({ icono: 'camion',
                titulo: st.estado === 'enviado' ? 'No hay equipos afuera' : 'No hay envíos para mostrar',
                texto: st.estado === 'enviado' ? 'Cuando mandes un equipo a la garantía del fabricante, desde el ticket, aparece acá hasta que vuelva.' : '' })}</div>`;
            return;
        }
        const fila = e => `
            <tr class="hover:bg-gray-50 ${e.atrasado ? 'bg-red-50/50' : ''}">
                <td class="px-4 py-3"><button type="button" data-abrir-ticket="${e.ticket_id}" class="font-semibold text-blue-700 hover:underline" translate="no">${esc(e.numero_rma)}</button>
                    <span class="block text-xs text-gray-500">${esc(e.producto || '')}</span></td>
                <td class="px-4 py-3 text-gray-700 hidden md:table-cell">${esc(e.cliente || '')}</td>
                <td class="px-4 py-3"><span class="font-medium text-gray-800">${esc(e.destino)}</span>
                    ${e.numero_caso ? `<span class="block text-xs text-gray-400">${esc(I18N.t('Caso {0}', e.numero_caso))}</span>` : ''}</td>
                <td class="px-4 py-3 text-gray-600 whitespace-nowrap">${esc(fecha(e.fecha_envio))}</td>
                <td class="px-4 py-3 text-center tabular-nums font-semibold ${e.atrasado ? 'text-red-600' : 'text-gray-700'}">${e.dias}</td>
                <td class="px-4 py-3 whitespace-nowrap">${e.estado === 'enviado'
                    ? (e.fecha_estimada ? `<span class="${e.atrasado ? 'text-red-600 font-semibold' : 'text-gray-600'}">${esc(fecha(e.fecha_estimada))}</span>${e.atrasado ? `<span class="block text-xs text-red-600">${esc(I18N.t('Atrasado'))}</span>` : ''}` : '<span class="text-gray-300">—</span>')
                    : components.badge(I18N.t(e.resultado_texto || e.resultado || ''), COLOR_RES[e.resultado] || 'bg-gray-100 text-gray-700')}</td>
                <td class="px-4 py-3 text-xs text-gray-500 hidden lg:table-cell">${esc([e.transportista, e.guia].filter(Boolean).join(' · '))}</td>
            </tr>`;
        // En el celular, tarjetas; en pantallas más anchas, la tabla
        const vuelta = e => e.estado === 'enviado'
            ? (e.fecha_estimada ? `<span class="${e.atrasado ? 'text-red-600 font-semibold' : 'text-gray-600'}">${esc(I18N.t(e.atrasado ? 'tenía que volver el {0}' : 'vuelve aprox. el {0}', fecha(e.fecha_estimada)))}</span>` : '')
            : components.badge(I18N.t(e.resultado_texto || e.resultado || ''), COLOR_RES[e.resultado] || 'bg-gray-100 text-gray-700');
        const tarjeta = e => `
            <li><button type="button" data-abrir-ticket="${e.ticket_id}" class="w-full text-left bg-white rounded-xl border ${e.atrasado ? 'border-red-200' : 'border-gray-200'} shadow-sm p-4">
                <span class="flex items-start justify-between gap-3">
                    <span class="min-w-0"><span class="block font-semibold text-blue-700" translate="no">${esc(e.numero_rma)}</span>
                        <span class="block text-xs text-gray-500 truncate">${esc(e.producto || '')}${e.cliente ? ' · ' + esc(e.cliente) : ''}</span></span>
                    <span class="shrink-0 text-right"><span class="block text-xl font-bold tabular-nums ${e.atrasado ? 'text-red-600' : 'text-gray-800'}">${e.dias}</span>
                        <span class="block text-[11px] text-gray-400">${esc(I18N.t('Días'))}</span></span>
                </span>
                <span class="block mt-2 text-sm font-medium text-gray-800">${esc(e.destino)}${e.numero_caso ? ` <span class="text-xs font-normal text-gray-400">· ${esc(I18N.t('Caso {0}', e.numero_caso))}</span>` : ''}</span>
                <span class="block text-xs text-gray-500 mt-0.5">${esc(I18N.t('Enviado el {0}', fecha(e.fecha_envio)))}</span>
                <span class="block text-xs mt-1">${vuelta(e)}</span>
            </button></li>`;
        cuerpo.innerHTML = `
            <ul class="sm:hidden space-y-3">${r.envios.map(tarjeta).join('')}</ul>
            <div class="hidden sm:block bg-white rounded-2xl shadow border border-gray-100 overflow-hidden"><div class="overflow-x-auto">
            <table class="w-full text-sm text-left">
                <thead><tr class="text-xs uppercase text-gray-400 border-b bg-gray-50">
                    <th class="px-4 py-3">${esc(I18N.t('Ticket'))}</th><th class="px-4 py-3 hidden md:table-cell">${esc(I18N.t('Cliente'))}</th>
                    <th class="px-4 py-3">${esc(I18N.t('Destino'))}</th><th class="px-4 py-3">${esc(I18N.t('Enviado'))}</th>
                    <th class="px-4 py-3 text-center">${esc(I18N.t('Días'))}</th>
                    <th class="px-4 py-3">${esc(I18N.t({ enviado: 'Vuelve aprox.', recibido: 'Resultado', todos: 'Vuelta o resultado' }[st.estado]))}</th>
                    <th class="px-4 py-3 hidden lg:table-cell">${esc(I18N.t('Transporte'))}</th></tr></thead>
                <tbody class="divide-y divide-gray-50">${r.envios.map(fila).join('')}</tbody>
            </table></div></div>`;
    }

    async function exportar(formato) {
        const q = consulta(); q.set('formato', formato);
        try {
            const blob = await api.request(`envios/exportar?${q}`);
            const url = URL.createObjectURL(blob);
            const a = Object.assign(document.createElement('a'), { href: url, download: `fuera_del_taller_${hoyLocal()}.${formato}` });
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (err) { toast.error(err.message); }
    }

    /** El dato de "Fuera del taller" en los accesos del panel (lo pinta Panel.accesos). */
    async function contador() {
        if (typeof Panel !== 'undefined' && esTaller()) Panel.accesos();
    }

    return { ESTADO, cargarDetalle, formEnvio, formVuelta, desdeSelector, abrir, cargar, contador };
})();
window.Envios = Envios;
