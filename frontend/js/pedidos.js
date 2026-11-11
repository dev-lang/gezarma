/**
 * pedidos.js — Administración → Pedidos a proveedor.
 *
 * Recorrido (se muestra arriba, en tres pasos):
 *   1. Armar: desde "Para pedir" (repuestos en o bajo su mínimo, agrupados por
 *      proveedor) o con "Nuevo pedido" a mano. Queda como borrador editable.
 *   2. Enviar: por email (PDF + CSV adjuntos) o "Ya lo pedí" si se pidió por
 *      teléfono/WhatsApp. Desde ahí ya no se edita.
 *   3. Recibir: al llegar la mercadería se carga cuánto vino de cada uno y se
 *      suma al stock (puede llegar en partes).
 * Estados: borrador → enviado → recibido en parte / recibido (o cancelado).
 */
const Pedidos = (() => {
    const pesos = n => Number(n || 0).toLocaleString(I18N.locale, { style: 'currency', currency: 'ARS' });
    const fecha = iso => iso ? new Date(iso).toLocaleDateString(I18N.locale) : '';
    const numero = id => String(id).padStart(5, '0');
    const ESTADOS = {
        borrador:  ['Borrador',  'bg-gray-100 text-gray-600'],
        enviado:   ['Enviado — esperando la mercadería', 'bg-blue-100 text-blue-700'],
        parcial:   ['Recibido en parte', 'bg-amber-100 text-amber-700'],
        recibido:  ['Recibido', 'bg-emerald-100 text-emerald-700'],
        cancelado: ['Cancelado', 'bg-red-100 text-red-600'],
    };
    const PASO = { borrador: 1, enviado: 3, parcial: 3, recibido: 4, cancelado: 0 };
    const CLAVE_MAILS = 'gezarma-mails-proveedor';
    let _filtro = 'abiertos';
    let _repuestos = [];
    let _nuevoAbierto = false;

    const req = (url, method = 'GET', body) => api.request(url, { method, ...(body ? { body: JSON.stringify(body) } : {}) });

    // Recordar el email de cada proveedor en este navegador (comodidad, no es un dato del sistema)
    const mails = () => { try { return JSON.parse(localStorage.getItem(CLAVE_MAILS) || '{}'); } catch { return {}; } };
    const recordarMail = (prov, mail) => { try { localStorage.setItem(CLAVE_MAILS, JSON.stringify({ ...mails(), [prov]: mail })); } catch { /* */ } };

    async function descargar(url, nombre, abrir) {
        const res = await fetch('/' + url, { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}`, 'Accept-Language': I18N.codigo } });
        if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || I18N.t('No se pudo descargar.')); }
        const blobUrl = URL.createObjectURL(await res.blob());
        if (abrir) window.open(blobUrl, '_blank');
        else { const a = document.createElement('a'); a.href = blobUrl; a.download = nombre; a.click(); }
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    }

    // ── Ayuda: los tres pasos ────────────────────────────────────────────────
    function comoFunciona(abierto) {
        const paso = (n, titulo, texto) => `
            <li class="flex gap-3">
                <span class="w-7 h-7 shrink-0 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center" aria-hidden="true">${n}</span>
                <div><p class="text-sm font-bold text-gray-800">${titulo}</p><p class="text-xs text-gray-500 mt-0.5">${texto}</p></div>
            </li>`;
        return `
        <details class="mb-6 rounded-xl border border-blue-100 bg-blue-50/60" ${abierto ? 'open' : ''}>
            <summary class="px-4 py-3 cursor-pointer text-sm font-bold text-blue-800">¿Cómo funciona?</summary>
            <ol class="px-4 pb-4 grid gap-4 sm:grid-cols-3">
                ${paso(1, 'Armá el pedido', 'Con "Armar pedido" en los repuestos que están bajo su mínimo, o con "Nuevo pedido" para pedir lo que quieras. Queda como borrador: podés cambiar cantidades y agregar o quitar repuestos.')}
                ${paso(2, 'Mandalo al proveedor', 'Por email desde acá (le llega con el PDF y el CSV) o, si lo pediste por teléfono o WhatsApp, con "Ya lo pedí". Desde ese momento no se modifica.')}
                ${paso(3, 'Recibí la mercadería', 'Cuando llega, cargá cuánto vino de cada repuesto y confirmá: se suma al stock. Si llega en partes, cargás cada entrega por separado.')}
            </ol>
        </details>`;
    }

    // ── Paso 1a: sugeridos ───────────────────────────────────────────────────
    function sugeridosHtml(grupos) {
        if (!grupos.length) {
            return `
            <div class="rounded-xl border border-dashed border-gray-200 px-4 py-6 text-center">
                <p class="text-sm font-semibold text-gray-600">Ningún repuesto está en o bajo su stock mínimo.</p>
                <p class="text-xs text-gray-400 mt-1 max-w-md mx-auto">Las sugerencias salen del "Stock mínimo" de cada repuesto (en Repuestos). Si no lo cargaste, acá no va a aparecer nada: igual podés armar un pedido a mano.</p>
            </div>`;
        }
        return `<div class="grid grid-cols-1 xl:grid-cols-2 gap-4">${grupos.map(g => `
            <div class="border border-amber-200 bg-amber-50/50 rounded-xl p-4">
                <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <p class="font-bold text-gray-800" translate="no">${esc(g.proveedor)}</p>
                    <button type="button" data-crear="${esc(g.proveedor)}" class="text-xs font-bold bg-amber-500 hover:bg-amber-600 text-amber-950 px-3 py-1.5 rounded-lg">Armar pedido</button>
                </div>
                <div class="overflow-x-auto"><table class="w-full text-xs min-w-[20rem]"><thead><tr class="text-gray-400 text-left">
                    <th class="py-1">Repuesto</th><th class="text-right">Stock / mín.</th><th class="text-right">Ya pedido</th><th class="text-right">A pedir</th></tr></thead>
                <tbody>${g.items.map(i => `<tr class="border-t border-amber-100">
                    <td class="py-1"><span class="font-semibold text-gray-700" translate="no">${esc(i.nombre)}</span> <span class="font-mono text-gray-400" translate="no">${esc(i.codigo)}</span></td>
                    <td class="text-right ${i.stock < 0 ? 'text-red-600 font-bold' : ''}">${i.stock} / ${i.stock_minimo}</td>
                    <td class="text-right text-gray-500">${i.en_pedido || '—'}</td>
                    <td class="text-right font-bold">${i.cantidad}</td></tr>`).join('')}</tbody></table></div>
            </div>`).join('')}</div>`;
    }

    // ── Paso 1b: pedido a mano ───────────────────────────────────────────────
    function nuevoHtml() {
        const proveedores = [...new Set(_repuestos.map(r => (r.proveedor || '').trim()).filter(Boolean))].sort();
        return `
        <div data-nuevo class="rounded-xl border border-blue-200 bg-white p-4 mb-4">
            <div class="flex items-center justify-between mb-3">
                <h4 class="font-bold text-gray-800">Nuevo pedido</h4>
                <button type="button" data-nuevo-cerrar class="text-gray-400 hover:text-gray-600 text-xl leading-none" aria-label="Cerrar">×</button>
            </div>
            <label class="block text-xs font-bold text-gray-500 uppercase mb-1" for="nuevo-proveedor">Proveedor</label>
            <input id="nuevo-proveedor" list="nuevo-proveedores" data-prov placeholder="Elegí o escribí el proveedor"
                class="w-full sm:w-80 px-3 py-2 border rounded-lg text-sm">
            <datalist id="nuevo-proveedores">${proveedores.map(p => `<option value="${esc(p)}">`).join('')}</datalist>
            <p class="text-xs text-gray-400 mt-1">Al elegirlo se listan sus repuestos; poné la cantidad en los que quieras pedir.</p>
            <div data-nuevo-items class="mt-3"></div>
            <div class="flex flex-wrap items-center gap-2 mt-3">
                <select data-nuevo-otro class="px-2 py-1.5 border rounded-lg text-sm max-w-full sm:max-w-xs">
                    <option value="">+ Agregar un repuesto de otro proveedor…</option>
                    ${_repuestos.map(r => `<option value="${r.id}">${esc(r.nombre)} (${esc(r.codigo)})</option>`).join('')}
                </select>
                <button type="button" data-nuevo-crear class="ml-auto text-sm font-bold bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">Crear borrador</button>
            </div>
        </div>`;
    }

    function filaCantidad(r, cant = '') {
        return `<tr class="border-t" data-rep="${r.id}">
            <td class="py-1.5"><span translate="no">${esc(r.nombre)}</span> <span class="font-mono text-xs text-gray-400" translate="no">${esc(r.codigo)}</span></td>
            <td class="text-right text-gray-500 text-xs">${r.stock}${r.stock_minimo ? ` / ${r.stock_minimo}` : ''}</td>
            <td class="text-right"><input type="number" min="0" value="${cant}" placeholder="0" data-cant class="w-20 px-2 py-1 border rounded text-right"></td></tr>`;
    }

    function conectarNuevo(root) {
        const caja = root.querySelector('[data-nuevo]');
        if (!caja) return;
        const cont = caja.querySelector('[data-nuevo-items]');
        const tabla = filas => filas ? `<div class="overflow-x-auto"><table class="w-full text-sm min-w-[20rem]"><thead><tr class="text-xs text-gray-400 text-left">
            <th class="py-1">Repuesto</th><th class="text-right">Stock / mín.</th><th class="text-right w-24">Cantidad</th></tr></thead><tbody data-cuerpo>${filas}</tbody></table></div>` : '';
        const prov = caja.querySelector('[data-prov]');
        prov.addEventListener('input', () => {
            const p = prov.value.trim().toLowerCase();
            const suyos = _repuestos.filter(r => (r.proveedor || '').trim().toLowerCase() === p);
            const ya = [...cont.querySelectorAll('tr[data-rep]')].filter(tr => +tr.querySelector('[data-cant]').value > 0)
                .map(tr => ({ r: _repuestos.find(x => x.id === +tr.dataset.rep), cant: tr.querySelector('[data-cant]').value }));
            const lista = [...ya, ...suyos.filter(r => !ya.some(y => y.r.id === r.id)).map(r => ({ r, cant: '' }))];
            cont.innerHTML = lista.length ? tabla(lista.map(x => filaCantidad(x.r, x.cant)).join(''))
                : (p ? `<p class="text-xs text-gray-400 italic">No hay repuestos cargados con ese proveedor: agregalos con el selector de abajo.</p>` : '');
        });
        caja.querySelector('[data-nuevo-otro]').addEventListener('change', e => {
            const r = _repuestos.find(x => x.id === +e.target.value);
            e.target.value = '';
            if (!r || cont.querySelector(`tr[data-rep="${r.id}"]`)) return;
            if (!cont.querySelector('[data-cuerpo]')) cont.innerHTML = tabla(' ');
            cont.querySelector('[data-cuerpo]').insertAdjacentHTML('beforeend', filaCantidad(r, 1));
        });
        caja.querySelector('[data-nuevo-cerrar]').addEventListener('click', () => { _nuevoAbierto = false; caja.remove(); });
        caja.querySelector('[data-nuevo-crear]').addEventListener('click', async () => {
            const proveedor = prov.value.trim();
            const items = [...cont.querySelectorAll('tr[data-rep]')]
                .map(tr => ({ repuesto_id: +tr.dataset.rep, cantidad: +tr.querySelector('[data-cant]').value || 0 }))
                .filter(i => i.cantidad > 0);
            if (!proveedor) { toast.warning(I18N.t('Falta el proveedor')); prov.focus(); return; }
            if (!items.length) { toast.warning(I18N.t('Poné la cantidad de al menos un repuesto.')); return; }
            try {
                await req('pedidos/', 'POST', { proveedor, notas: '', items });
                _nuevoAbierto = false;
                toast.success(I18N.t('Borrador creado: revisalo y mandalo al proveedor.'));
                cargar();
            } catch (err) { toast.error(err.message); }
        });
        prov.focus();
    }

    // ── Cada pedido ──────────────────────────────────────────────────────────
    function etapas(estado) {
        if (estado === 'cancelado') return '';
        const actual = PASO[estado];
        const e = (n, texto) => `<li class="flex items-center gap-1.5 ${n < actual ? 'text-emerald-700' : n === actual ? 'text-blue-700 font-bold' : 'text-gray-400'}">
            <span class="w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center ${n < actual ? 'bg-emerald-100' : n === actual ? 'bg-blue-600 text-white' : 'bg-gray-100'}">${n < actual ? icono('check', 'w-3 h-3') : n}</span>${texto}</li>`;
        return `<ol class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs mb-3">${e(1, 'Armar')}${e(2, 'Enviar')}${e(3, 'Recibir')}</ol>`;
    }

    function itemsEditables(p) {
        return `
            <div class="grid gap-3 sm:grid-cols-2 mb-3">
                <label class="text-xs font-bold text-gray-500 uppercase">Proveedor
                    <input data-prov value="${esc(p.proveedor)}" class="mt-1 w-full px-3 py-2 border rounded-lg text-sm font-normal normal-case text-gray-800"></label>
                <label class="text-xs font-bold text-gray-500 uppercase">Notas para el proveedor
                    <input data-notas value="${esc(p.notas || '')}" placeholder="Opcional" class="mt-1 w-full px-3 py-2 border rounded-lg text-sm font-normal normal-case text-gray-800"></label>
            </div>
            <div class="overflow-x-auto"><table class="w-full text-sm min-w-[20rem]"><thead><tr class="text-xs text-gray-400 text-left"><th class="py-1">Repuesto</th><th class="text-right">Stock</th><th class="text-right w-28">Cantidad</th><th class="w-8"></th></tr></thead>
            <tbody data-items>${p.items.map(i => `<tr class="border-t" data-rep="${i.repuesto_id}">
                <td class="py-1.5"><span translate="no">${esc(i.nombre)}</span> <span class="font-mono text-xs text-gray-400" translate="no">${esc(i.codigo)}</span></td>
                <td class="text-right text-gray-500">${i.stock}</td>
                <td class="text-right"><input type="number" min="1" value="${i.cantidad}" data-cant class="w-20 px-2 py-1 border rounded text-right"></td>
                <td class="text-right"><button type="button" data-quitar class="text-red-500 hover:text-red-700 text-xs" aria-label="Quitar">${icono('x', 'w-4 h-4')}</button></td></tr>`).join('')}</tbody></table></div>
            <div class="flex flex-wrap items-center gap-2 mt-2">
                <select data-agregar class="px-2 py-1.5 border rounded-lg text-sm max-w-full sm:max-w-xs"><option value="">+ Agregar repuesto…</option>
                    ${_repuestos.filter(r => !p.items.some(i => i.repuesto_id === r.id)).map(r => `<option value="${r.id}">${esc(r.nombre)} (${esc(r.codigo)})</option>`).join('')}</select>
                <button type="button" data-guardar class="text-xs font-semibold border border-gray-300 hover:bg-gray-50 text-gray-700 px-3 py-1.5 rounded-lg">Guardar borrador</button>
            </div>
            <div class="mt-4 rounded-xl bg-blue-50/60 border border-blue-100 p-3">
                <p class="text-sm font-bold text-gray-800 mb-2">Paso 2 · Mandalo al proveedor</p>
                <div class="flex flex-wrap items-center gap-2">
                    <input type="email" data-email value="${esc(mails()[p.proveedor] || '')}" placeholder="Email del proveedor"
                        class="flex-1 min-w-[12rem] px-3 py-2 border rounded-lg text-sm bg-white">
                    <button type="button" data-enviar class="text-sm font-bold bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">${icono('mail', 'w-4 h-4 mr-1.5')}Enviar por email</button>
                </div>
                <p class="text-xs text-gray-500 mt-2">Le llega con el pedido en PDF y CSV. ¿Lo pediste por teléfono o WhatsApp?
                    <button type="button" data-ya-pedido class="font-semibold text-blue-700 hover:text-blue-900 underline underline-offset-2">Ya lo pedí, marcarlo como enviado</button></p>
            </div>`;
    }

    function itemsRecepcion(p) {
        return `
            <p class="text-sm text-gray-600 mb-2"><b>Paso 3 · Cuando llegue la mercadería</b>, cargá cuánto vino de cada repuesto y confirmá: se suma al stock. Si falta algo, el pedido queda abierto para la próxima entrega.</p>
            <div class="overflow-x-auto"><table class="w-full text-sm min-w-[20rem]"><thead><tr class="text-xs text-gray-400 text-left"><th class="py-1">Repuesto</th><th class="text-right">Pedido</th><th class="text-right">Ya llegó</th><th class="text-right w-28">Llegó ahora</th></tr></thead>
            <tbody>${p.items.map(i => `<tr class="border-t">
                <td class="py-1.5"><span translate="no">${esc(i.nombre)}</span> <span class="font-mono text-xs text-gray-400" translate="no">${esc(i.codigo)}</span></td>
                <td class="text-right">${i.cantidad}</td><td class="text-right text-gray-500">${i.recibido}</td>
                <td class="text-right">${i.pendiente ? `<input type="number" min="0" max="${i.pendiente}" value="${i.pendiente}" data-recibir="${i.id}" class="w-20 px-2 py-1 border rounded text-right">` : '<span class="text-emerald-600 text-xs font-bold">completo</span>'}</td></tr>`).join('')}</tbody></table></div>
            <button type="button" data-confirmar class="mt-3 text-sm font-bold bg-emerald-700 hover:bg-emerald-800 text-white px-4 py-2 rounded-lg">Confirmar recepción (suma al stock)</button>`;
    }

    function itemsLectura(p) {
        return `<ul class="text-sm divide-y">${p.items.map(i => `<li class="py-1 flex justify-between gap-3"><span><span translate="no">${esc(i.nombre)}</span> <span class="font-mono text-xs text-gray-400" translate="no">${esc(i.codigo)}</span></span>
            <span class="text-gray-600 shrink-0">${i.recibido}/${i.cantidad}</span></li>`).join('')}</ul>`;
    }

    function pedidoHtml(p) {
        const [etq, cls] = ESTADOS[p.estado] || [p.estado, 'bg-gray-100'];
        const cuerpo = p.estado === 'borrador' ? itemsEditables(p) : ['enviado', 'parcial'].includes(p.estado) ? itemsRecepcion(p) : itemsLectura(p);
        return `
        <details class="border rounded-xl bg-white" data-pedido="${p.id}" ${['borrador', 'enviado', 'parcial'].includes(p.estado) ? 'open' : ''}>
            <summary class="px-4 py-3 cursor-pointer flex flex-wrap items-center gap-x-3 gap-y-1">
                <span class="font-mono text-sm font-bold text-gray-700">N° ${numero(p.id)}</span>
                <span class="font-semibold text-gray-800" translate="no">${esc(p.proveedor)}</span>
                <span class="px-2 py-0.5 rounded-full text-[11px] font-bold ${cls}">${etq}</span>
                <span class="text-xs text-gray-400 sm:ml-auto">${p.unidades} u. · ${pesos(p.costo_estimado)} · ${p.fecha_envio ? `enviado ${fecha(p.fecha_envio)}` : `creado ${fecha(p.fecha_creacion)}`}</span>
            </summary>
            <div class="px-4 pb-4">
                ${etapas(p.estado)}
                ${p.notas && p.estado !== 'borrador' ? `<p class="text-xs text-gray-500 mb-2">Notas: ${esc(p.notas)}</p>` : ''}
                ${cuerpo}
                <div class="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t">
                    <button type="button" data-pdf class="text-xs font-semibold border px-3 py-1.5 rounded-lg hover:bg-gray-50">${icono('documento', 'w-3.5 h-3.5 mr-1')}Ver PDF</button>
                    <button type="button" data-csv class="text-xs font-semibold border px-3 py-1.5 rounded-lg hover:bg-gray-50">${icono('descargar', 'w-3.5 h-3.5 mr-1')}CSV</button>
                    ${!['recibido', 'cancelado'].includes(p.estado) ? `<button type="button" data-cancelar class="text-xs font-semibold text-red-600 hover:text-red-800 ml-auto">Cancelar pedido</button>` : ''}
                </div>
            </div>
        </details>`;
    }

    function conectar(el, p) {
        const accion = async (fn, ok) => { try { await fn(); if (ok) toast.success(ok); cargar(); } catch (err) { toast.error(err.message); } };
        el.querySelector('[data-pdf]').addEventListener('click', () => descargar(`pedidos/${p.id}/pdf`, '', true).catch(e => toast.error(e.message)));
        el.querySelector('[data-csv]').addEventListener('click', () => descargar(`pedidos/${p.id}/csv`, `pedido-${numero(p.id)}.csv`).catch(e => toast.error(e.message)));
        el.querySelector('[data-cancelar]')?.addEventListener('click', async () => {
            if (!(await confirmDialog(I18N.t('¿Cancelar el pedido?'), I18N.t('Lo que ya se recibió queda en el stock.'), I18N.t('Sí, cancelar pedido')))) return;
            accion(() => req(`pedidos/${p.id}/cancelar`, 'POST'), I18N.t('Pedido cancelado.'));
        });
        if (p.estado === 'borrador') {
            const tbody = el.querySelector('[data-items]');
            tbody.querySelectorAll('[data-quitar]').forEach(b => b.addEventListener('click', () => b.closest('tr').remove()));
            el.querySelector('[data-agregar]').addEventListener('change', e => {
                const r = _repuestos.find(x => x.id === +e.target.value);
                if (!r) return;
                tbody.insertAdjacentHTML('beforeend', `<tr class="border-t" data-rep="${r.id}"><td class="py-1.5"><span translate="no">${esc(r.nombre)}</span> <span class="font-mono text-xs text-gray-400" translate="no">${esc(r.codigo)}</span></td>
                    <td class="text-right text-gray-500">${r.stock}</td><td class="text-right"><input type="number" min="1" value="1" data-cant class="w-20 px-2 py-1 border rounded text-right"></td>
                    <td class="text-right"><button type="button" data-quitar class="text-red-500 text-xs" aria-label="Quitar">${icono('x', 'w-4 h-4')}</button></td></tr>`);
                tbody.lastElementChild.querySelector('[data-quitar]').addEventListener('click', ev => ev.target.closest('tr').remove());
                e.target.querySelector(`option[value="${r.id}"]`)?.remove();
                e.target.value = '';
            });
            const datos = () => ({
                proveedor: el.querySelector('[data-prov]').value.trim(),
                notas: el.querySelector('[data-notas]').value.trim(),
                items: [...tbody.querySelectorAll('tr[data-rep]')].map(tr => ({ repuesto_id: +tr.dataset.rep, cantidad: +tr.querySelector('[data-cant]').value })),
            });
            el.querySelector('[data-guardar]').addEventListener('click', () =>
                accion(() => req(`pedidos/${p.id}`, 'PUT', datos()), I18N.t('Borrador guardado.')));
            el.querySelector('[data-enviar]').addEventListener('click', () => {
                const mail = el.querySelector('[data-email]').value.trim();
                if (!mail) { toast.warning(I18N.t('Escribí el email del proveedor, o usá "Ya lo pedí" si se lo pediste por otro medio.')); el.querySelector('[data-email]').focus(); return; }
                accion(async () => {
                    const d = datos();
                    await req(`pedidos/${p.id}`, 'PUT', d);
                    await req(`pedidos/${p.id}/enviar`, 'POST', { email: mail });
                    recordarMail(d.proveedor, mail);
                }, I18N.t('Pedido enviado a {0}.', mail));
            });
            el.querySelector('[data-ya-pedido]').addEventListener('click', async () => {
                if (!(await confirmDialog(I18N.t('¿Marcar el pedido como enviado?'),
                    I18N.t('Usalo si ya se lo pediste al proveedor por otro medio. Después no se puede modificar.'), I18N.t('Marcar como enviado'), { peligro: false }))) return;
                accion(async () => {
                    await req(`pedidos/${p.id}`, 'PUT', datos());
                    await req(`pedidos/${p.id}/enviar`, 'POST', { email: '' });
                }, I18N.t('Pedido marcado como enviado.'));
            });
        }
        el.querySelector('[data-confirmar]')?.addEventListener('click', () => {
            const items = [...el.querySelectorAll('[data-recibir]')].map(i => ({ item_id: +i.dataset.recibir, cantidad: +i.value || 0 }));
            accion(() => req(`pedidos/${p.id}/recibir`, 'POST', { items }), I18N.t('Recepción registrada: se sumó al stock.'));
        });
    }

    async function cargar() {
        const root = document.getElementById('pedidos-root');
        if (!root) return;
        let sug, lista, hayAlguno;
        try {
            [sug, lista, _repuestos] = await Promise.all([req('pedidos/sugeridos'), req(`pedidos/?estado=${_filtro === 'todos' ? '' : _filtro}`), api.getParts()]);
            hayAlguno = lista.length || (_filtro === 'abiertos' && (await req('pedidos/')).length);
        } catch (err) { root.innerHTML = `<p class="text-red-600 text-sm">${esc(err.message)}</p>`; return; }
        root.innerHTML = `
        ${comoFunciona(!hayAlguno)}
        ${_nuevoAbierto ? nuevoHtml() : ''}
        <section class="mb-8">
            <div class="flex flex-wrap items-center justify-between gap-2 mb-1">
                <h3 class="font-bold text-gray-700">Para pedir</h3>
                <div class="flex flex-wrap gap-2">
                    ${sug.length > 1 ? `<button type="button" data-crear-todos class="text-xs font-bold bg-amber-500 hover:bg-amber-600 text-amber-950 px-3 py-1.5 rounded-lg">Armar todos (${sug.length})</button>` : ''}
                    ${_nuevoAbierto ? '' : `<button type="button" data-nuevo-abrir class="text-xs font-bold border border-blue-300 text-blue-700 hover:bg-blue-50 px-3 py-1.5 rounded-lg">+ Nuevo pedido</button>`}
                </div>
            </div>
            <p class="text-xs text-gray-400 mb-3">Repuestos en o bajo su stock mínimo, agrupados por proveedor. La cantidad sugerida lleva el stock al doble del mínimo, descontando lo que ya está pedido.</p>
            ${sugeridosHtml(sug)}
        </section>
        <section>
            <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                <h3 class="font-bold text-gray-700">Pedidos</h3>
                <div class="flex gap-1 bg-gray-100 rounded-lg p-1 text-xs font-semibold">
                    ${[['abiertos', 'En curso'], ['todos', 'Todos']].map(([v, l]) => `<button type="button" data-filtro="${v}" class="px-3 py-1 rounded-md ${_filtro === v ? 'bg-white shadow text-gray-800' : 'text-gray-500'}">${l}</button>`).join('')}
                </div>
            </div>
            <div class="space-y-3" data-lista>${lista.length ? lista.map(pedidoHtml).join('')
                : `<p class="text-sm text-gray-400 italic">${_filtro === 'abiertos' ? 'No hay pedidos en curso.' : 'Todavía no hay pedidos.'}</p>`}</div>
        </section>`;
        root.querySelectorAll('[data-crear]').forEach(b => b.addEventListener('click', async () => {
            try { await req('pedidos/desde-sugeridos', 'POST', { proveedores: [b.dataset.crear] }); toast.success(I18N.t('Borrador creado: revisalo y mandalo al proveedor.')); cargar(); }
            catch (err) { toast.error(err.message); }
        }));
        root.querySelector('[data-crear-todos]')?.addEventListener('click', async () => {
            try { const r = await req('pedidos/desde-sugeridos', 'POST', {}); toast.success(I18N.t('{0} borradores creados.', r.length)); cargar(); }
            catch (err) { toast.error(err.message); }
        });
        root.querySelector('[data-nuevo-abrir]')?.addEventListener('click', () => { _nuevoAbierto = true; cargar(); });
        conectarNuevo(root);
        root.querySelectorAll('[data-filtro]').forEach(b => b.addEventListener('click', () => { _filtro = b.dataset.filtro; cargar(); }));
        lista.forEach(p => conectar(root.querySelector(`[data-pedido="${p.id}"]`), p));
    }

    return { cargar };
})();
window.Pedidos = Pedidos;
