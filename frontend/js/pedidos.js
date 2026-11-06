/**
 * pedidos.js — Pestaña "Pedidos" de Administración: pedidos de repuestos a
 * proveedores, armados a partir del stock bajo el mínimo.
 * borrador → enviado → parcial / recibido (o cancelado). Al recibir se suma al stock.
 */
const Pedidos = (() => {
    const pesos = n => '$ ' + Number(n || 0).toLocaleString(I18N.locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fecha = iso => iso ? new Date(iso).toLocaleDateString(I18N.locale) : '';
    const ESTADOS = {
        borrador:  ['Borrador',  'bg-gray-100 text-gray-600'],
        enviado:   ['Enviado',   'bg-blue-100 text-blue-700'],
        parcial:   ['Recibido en parte', 'bg-amber-100 text-amber-700'],
        recibido:  ['Recibido',  'bg-emerald-100 text-emerald-700'],
        cancelado: ['Cancelado', 'bg-red-100 text-red-600'],
    };
    let _filtro = 'abiertos';
    let _repuestos = [];

    const req = (url, method = 'GET', body) => api.request(url, { method, ...(body ? { body: JSON.stringify(body) } : {}) });

    async function descargar(url, nombre, abrir) {
        const res = await fetch('/' + url, { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } });
        if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'No se pudo descargar'); }
        const blobUrl = URL.createObjectURL(await res.blob());
        if (abrir) window.open(blobUrl, '_blank');
        else { const a = document.createElement('a'); a.href = blobUrl; a.download = nombre; a.click(); }
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    }

    function sugeridosHtml(grupos) {
        if (!grupos.length) return `<p class="text-sm text-gray-400 italic">No hay repuestos bajo el mínimo sin pedir.</p>`;
        return `<div class="grid grid-cols-1 xl:grid-cols-2 gap-4">${grupos.map(g => `
            <div class="border border-amber-200 bg-amber-50/50 rounded-xl p-4">
                <div class="flex items-center justify-between gap-2 mb-2">
                    <p class="font-bold text-gray-800">${esc(g.proveedor)}</p>
                    <button type="button" data-crear="${esc(g.proveedor)}" class="text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white px-3 py-1.5 rounded-lg">Armar pedido</button>
                </div>
                <table class="w-full text-xs"><thead><tr class="text-gray-400 text-left"><th class="py-1">Repuesto</th><th class="text-right">Stock / mín.</th><th class="text-right">Pedido</th><th class="text-right">Sugerido</th></tr></thead>
                <tbody>${g.items.map(i => `<tr class="border-t border-amber-100">
                    <td class="py-1"><span class="font-semibold text-gray-700">${esc(i.nombre)}</span> <span class="font-mono text-gray-400">${esc(i.codigo)}</span></td>
                    <td class="text-right ${i.stock < 0 ? 'text-red-600 font-bold' : ''}">${i.stock} / ${i.stock_minimo}</td>
                    <td class="text-right text-gray-500">${i.en_pedido || '—'}</td>
                    <td class="text-right font-bold">${i.cantidad}</td></tr>`).join('')}</tbody></table>
            </div>`).join('')}</div>`;
    }

    function itemsEditables(p) {
        return `<table class="w-full text-sm mt-2"><thead><tr class="text-xs text-gray-400 text-left"><th class="py-1">Repuesto</th><th class="text-right">Stock</th><th class="text-right w-28">Cantidad</th><th class="w-8"></th></tr></thead>
            <tbody data-items>${p.items.map(i => `<tr class="border-t" data-rep="${i.repuesto_id}">
                <td class="py-1.5">${esc(i.nombre)} <span class="font-mono text-xs text-gray-400">${esc(i.codigo)}</span></td>
                <td class="text-right text-gray-500">${i.stock}</td>
                <td class="text-right"><input type="number" min="1" value="${i.cantidad}" data-cant class="w-20 px-2 py-1 border rounded text-right"></td>
                <td class="text-right"><button type="button" data-quitar class="text-red-500 hover:text-red-700 text-xs" aria-label="Quitar">✕</button></td></tr>`).join('')}</tbody></table>
            <div class="flex flex-wrap items-center gap-2 mt-2">
                <select data-agregar class="px-2 py-1.5 border rounded-lg text-sm max-w-xs"><option value="">+ Agregar repuesto…</option>
                    ${_repuestos.filter(r => !p.items.some(i => i.repuesto_id === r.id)).map(r => `<option value="${r.id}">${esc(r.nombre)} (${esc(r.codigo)})</option>`).join('')}</select>
                <button type="button" data-guardar class="text-xs font-bold bg-gray-800 hover:bg-gray-700 text-white px-3 py-1.5 rounded-lg">Guardar cambios</button>
            </div>`;
    }

    function itemsRecepcion(p) {
        return `<table class="w-full text-sm mt-2"><thead><tr class="text-xs text-gray-400 text-left"><th class="py-1">Repuesto</th><th class="text-right">Pedido</th><th class="text-right">Llegó</th><th class="text-right w-28">Recibir ahora</th></tr></thead>
            <tbody>${p.items.map(i => `<tr class="border-t">
                <td class="py-1.5">${esc(i.nombre)} <span class="font-mono text-xs text-gray-400">${esc(i.codigo)}</span></td>
                <td class="text-right">${i.cantidad}</td><td class="text-right text-gray-500">${i.recibido}</td>
                <td class="text-right">${i.pendiente ? `<input type="number" min="0" max="${i.pendiente}" value="${i.pendiente}" data-recibir="${i.id}" class="w-20 px-2 py-1 border rounded text-right">` : '<span class="text-emerald-600 text-xs font-bold">completo</span>'}</td></tr>`).join('')}</tbody></table>
            <button type="button" data-confirmar class="mt-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg">Confirmar recepción (suma al stock)</button>`;
    }

    function itemsLectura(p) {
        return `<ul class="text-sm mt-2 divide-y">${p.items.map(i => `<li class="py-1 flex justify-between"><span>${esc(i.nombre)} <span class="font-mono text-xs text-gray-400">${esc(i.codigo)}</span></span>
            <span class="text-gray-600">${i.recibido}/${i.cantidad}</span></li>`).join('')}</ul>`;
    }

    function pedidoHtml(p) {
        const [etq, cls] = ESTADOS[p.estado] || [p.estado, 'bg-gray-100'];
        const cuerpo = p.estado === 'borrador' ? itemsEditables(p) : ['enviado', 'parcial'].includes(p.estado) ? itemsRecepcion(p) : itemsLectura(p);
        return `
        <details class="border rounded-xl bg-white" data-pedido="${p.id}" ${['borrador', 'enviado', 'parcial'].includes(p.estado) ? 'open' : ''}>
            <summary class="px-4 py-3 cursor-pointer flex flex-wrap items-center gap-x-3 gap-y-1">
                <span class="font-mono text-sm font-bold text-gray-700">N° ${String(p.id).padStart(5, '0')}</span>
                <span class="font-semibold text-gray-800">${esc(p.proveedor)}</span>
                <span class="px-2 py-0.5 rounded-full text-[11px] font-bold ${cls}">${etq}</span>
                <span class="text-xs text-gray-400 ml-auto">${p.unidades} u. · ${pesos(p.costo_estimado)} · ${p.fecha_envio ? 'enviado ' + fecha(p.fecha_envio) : 'creado ' + fecha(p.fecha_creacion)}</span>
            </summary>
            <div class="px-4 pb-4">
                ${p.notas ? `<p class="text-xs text-gray-500">Notas: ${esc(p.notas)}</p>` : ''}
                ${cuerpo}
                <div class="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t">
                    <button type="button" data-pdf class="text-xs font-semibold border px-3 py-1.5 rounded-lg hover:bg-gray-50">📄 PDF</button>
                    <button type="button" data-csv class="text-xs font-semibold border px-3 py-1.5 rounded-lg hover:bg-gray-50">⬇ CSV</button>
                    ${p.estado === 'borrador' ? `
                    <input type="email" data-email placeholder="Email del proveedor (opcional)" class="px-2 py-1.5 border rounded-lg text-sm w-56">
                    <button type="button" data-enviar class="text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg">Marcar enviado</button>` : ''}
                    ${!['recibido', 'cancelado'].includes(p.estado) ? `<button type="button" data-cancelar class="text-xs font-semibold text-red-600 hover:text-red-800 ml-auto">Cancelar pedido</button>` : ''}
                </div>
            </div>
        </details>`;
    }

    function conectar(el, p) {
        const accion = async (fn, ok) => { try { await fn(); if (ok) toast.success(ok); cargar(); } catch (err) { toast.error(err.message); } };
        el.querySelector('[data-pdf]').addEventListener('click', () => descargar(`pedidos/${p.id}/pdf`, '', true).catch(e => toast.error(e.message)));
        el.querySelector('[data-csv]').addEventListener('click', () => descargar(`pedidos/${p.id}/csv`, `pedido-${String(p.id).padStart(5, '0')}.csv`).catch(e => toast.error(e.message)));
        el.querySelector('[data-cancelar]')?.addEventListener('click', async () => {
            if (!(await confirmDialog('¿Cancelar el pedido?', 'Lo que ya se recibió queda en el stock.', 'Cancelar pedido'))) return;
            accion(() => req(`pedidos/${p.id}/cancelar`, 'POST'), 'Pedido cancelado.');
        });
        if (p.estado === 'borrador') {
            const tbody = el.querySelector('[data-items]');
            tbody.querySelectorAll('[data-quitar]').forEach(b => b.addEventListener('click', () => b.closest('tr').remove()));
            el.querySelector('[data-agregar]').addEventListener('change', e => {
                const r = _repuestos.find(x => x.id === +e.target.value);
                if (!r) return;
                tbody.insertAdjacentHTML('beforeend', `<tr class="border-t" data-rep="${r.id}"><td class="py-1.5">${esc(r.nombre)} <span class="font-mono text-xs text-gray-400">${esc(r.codigo)}</span></td>
                    <td class="text-right text-gray-500">${r.stock}</td><td class="text-right"><input type="number" min="1" value="1" data-cant class="w-20 px-2 py-1 border rounded text-right"></td>
                    <td class="text-right"><button type="button" data-quitar class="text-red-500 text-xs" aria-label="Quitar">✕</button></td></tr>`);
                tbody.lastElementChild.querySelector('[data-quitar]').addEventListener('click', ev => ev.target.closest('tr').remove());
                e.target.querySelector(`option[value="${r.id}"]`)?.remove();
                e.target.value = '';
            });
            const leer = () => [...tbody.querySelectorAll('tr[data-rep]')].map(tr => ({ repuesto_id: +tr.dataset.rep, cantidad: +tr.querySelector('[data-cant]').value }));
            el.querySelector('[data-guardar]').addEventListener('click', () =>
                accion(() => req(`pedidos/${p.id}`, 'PUT', { proveedor: p.proveedor, notas: p.notas || '', items: leer() }), 'Pedido guardado.'));
            el.querySelector('[data-enviar]').addEventListener('click', () => {
                const mail = el.querySelector('[data-email]').value.trim();
                accion(async () => {
                    await req(`pedidos/${p.id}`, 'PUT', { proveedor: p.proveedor, notas: p.notas || '', items: leer() });
                    await req(`pedidos/${p.id}/enviar`, 'POST', { email: mail });
                }, mail ? `Pedido enviado a ${mail}.` : 'Pedido marcado como enviado.');
            });
        }
        el.querySelector('[data-confirmar]')?.addEventListener('click', () => {
            const items = [...el.querySelectorAll('[data-recibir]')].map(i => ({ item_id: +i.dataset.recibir, cantidad: +i.value || 0 }));
            accion(() => req(`pedidos/${p.id}/recibir`, 'POST', { items }), 'Recepción registrada: se sumó al stock.');
        });
    }

    async function cargar() {
        const root = document.getElementById('pedidos-root');
        if (!root) return;
        let sug, lista;
        try {
            [sug, lista, _repuestos] = await Promise.all([req('pedidos/sugeridos'), req(`pedidos/?estado=${_filtro === 'todos' ? '' : _filtro}`), api.getParts()]);
        } catch (err) { root.innerHTML = `<p class="text-red-600 text-sm">${esc(err.message)}</p>`; return; }
        root.innerHTML = `
        <section class="mb-8">
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-bold text-gray-700">Para pedir <span class="text-xs font-normal text-gray-400">(repuestos en o bajo el mínimo, llevados al doble del mínimo)</span></h3>
                ${sug.length > 1 ? `<button type="button" data-crear-todos class="text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white px-3 py-1.5 rounded-lg">Armar todos (${sug.length})</button>` : ''}
            </div>
            ${sugeridosHtml(sug)}
        </section>
        <section>
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-bold text-gray-700">Pedidos</h3>
                <div class="flex gap-1 bg-gray-100 rounded-lg p-1 text-xs font-semibold">
                    ${[['abiertos', 'Abiertos'], ['todos', 'Todos']].map(([v, l]) => `<button type="button" data-filtro="${v}" class="px-3 py-1 rounded-md ${_filtro === v ? 'bg-white shadow text-gray-800' : 'text-gray-500'}">${l}</button>`).join('')}
                </div>
            </div>
            <div class="space-y-3" data-lista>${lista.length ? lista.map(pedidoHtml).join('') : '<p class="text-sm text-gray-400 italic">No hay pedidos.</p>'}</div>
        </section>`;
        root.querySelectorAll('[data-crear]').forEach(b => b.addEventListener('click', async () => {
            try { await req('pedidos/desde-sugeridos', 'POST', { proveedores: [b.dataset.crear] }); toast.success('Borrador creado: revisalo y envialo.'); cargar(); }
            catch (err) { toast.error(err.message); }
        }));
        root.querySelector('[data-crear-todos]')?.addEventListener('click', async () => {
            try { const r = await req('pedidos/desde-sugeridos', 'POST', {}); toast.success(`${r.length} borradores creados.`); cargar(); }
            catch (err) { toast.error(err.message); }
        });
        root.querySelectorAll('[data-filtro]').forEach(b => b.addEventListener('click', () => { _filtro = b.dataset.filtro; cargar(); }));
        lista.forEach(p => conectar(root.querySelector(`[data-pedido="${p.id}"]`), p));
    }

    return { cargar };
})();
window.Pedidos = Pedidos;
