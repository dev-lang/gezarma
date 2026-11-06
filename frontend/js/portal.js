/**
 * portal.js — "Mis equipos" para el cliente: cada equipo con todas sus
 * reparaciones, los documentos para descargar y lo que tiene pendiente
 * (aprobar un presupuesto, retirar el equipo, calificar la reparación).
 */
const Portal = (() => {
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const DOCS = { ingreso: 'Orden de ingreso', presupuesto: 'Presupuesto', remito: 'Remito' };
    const ICONO = { presupuesto: '💰', retiro: '📦', encuesta: '⭐' };
    const fecha = iso => iso ? new Date(iso).toLocaleDateString('es-AR') : '';
    const abrirTicket = id => api.getTicket(id).then(t => ui.showTicketDetail(t));

    function reparacion(r) {
        return `
        <li class="py-3 first:pt-0 last:pb-0">
            <div class="flex flex-wrap items-center gap-2">
                <button type="button" data-ticket="${r.id}" class="font-mono text-sm font-bold text-blue-700 hover:underline">${esc(r.numero_rma)}</button>
                <span class="px-2 py-0.5 rounded-full text-[11px] font-bold text-white" style="background:${esc(r.color)}">${esc(r.estado_etiqueta)}</span>
                ${r.encuesta ? `<span class="text-amber-400 text-xs" title="Tu calificación">${'★'.repeat(r.encuesta)}</span>` : ''}
            </div>
            <p class="text-xs text-gray-500 mt-0.5">Ingresó el ${fecha(r.fecha_ingreso)}${r.fecha_cierre ? ` · cerrado el ${fecha(r.fecha_cierre)}` : ''} · ${r.en_garantia ? 'en garantía' : 'fuera de garantía'}</p>
            <p class="text-sm text-gray-700 mt-1 line-clamp-2">${esc(r.descripcion)}</p>
            ${r.acciones.map(a => `<p class="mt-1 text-xs font-semibold text-amber-700">${ICONO[a.tipo] || '•'} ${esc(a.texto)}${a.vence ? ` (hasta el ${fecha(a.vence)})` : ''}</p>`).join('')}
            <div class="flex flex-wrap gap-2 mt-2">
                ${r.documentos.map(d => `<button type="button" data-doc="${d}" data-id="${r.id}"
                    class="text-xs font-semibold text-gray-600 border border-gray-200 rounded-lg px-2.5 py-1 hover:bg-gray-50">📄 ${DOCS[d] || d}</button>`).join('')}
            </div>
        </li>`;
    }

    async function cargar() {
        const cont = document.getElementById('portal-panel');
        if (!cont) return;
        let d;
        try { d = await api.request('portal/equipos'); } catch { cont.classList.add('hidden'); return; }
        if (!d.equipos.length) { cont.classList.add('hidden'); return; }
        cont.innerHTML = `
        ${d.pendientes.length ? `
        <div class="bg-amber-50 border border-amber-200 rounded-2xl p-4 mb-6">
            <h3 class="font-bold text-amber-800 text-sm mb-2">Tenés ${d.pendientes.length === 1 ? 'algo pendiente' : `${d.pendientes.length} cosas pendientes`}</h3>
            <ul class="space-y-1">${d.pendientes.map(p => `
                <li><button type="button" data-ticket="${p.ticket_id}" class="text-sm text-amber-900 hover:underline text-left">
                    ${ICONO[p.tipo] || '•'} <b>${esc(p.texto)}</b> · ${esc(p.producto)} <span class="font-mono text-xs">${esc(p.numero_rma)}</span>${p.vence ? ` · hasta el ${fecha(p.vence)}` : ''}
                </button></li>`).join('')}</ul>
        </div>` : ''}
        <div class="flex items-end justify-between mb-3">
            <h3 class="text-lg font-bold text-gray-800">Mis equipos</h3>
            <p class="text-xs text-gray-400">${d.resumen.equipos} equipo${d.resumen.equipos === 1 ? '' : 's'} · ${d.resumen.reparaciones} ${d.resumen.reparaciones === 1 ? 'reparación' : 'reparaciones'}${d.resumen.en_curso ? ` · ${d.resumen.en_curso} en curso` : ''}</p>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            ${d.equipos.map(e => `
            <div class="bg-white rounded-2xl shadow border border-gray-100 p-5">
                <p class="font-bold text-gray-800">${esc(e.producto || 'Equipo')}</p>
                <p class="text-xs text-gray-400 font-mono mb-3">SN ${esc(e.numero_serie || '—')}${e.reparaciones.length > 1 ? ` · ${e.reparaciones.length} reparaciones` : ''}</p>
                <ul class="divide-y">${e.reparaciones.map(reparacion).join('')}</ul>
            </div>`).join('')}
        </div>`;
        cont.querySelectorAll('[data-ticket]').forEach(b => b.addEventListener('click', () => abrirTicket(+b.dataset.ticket)));
        cont.querySelectorAll('[data-doc]').forEach(b => b.addEventListener('click', () => Documentos.abrir(+b.dataset.id, b.dataset.doc)));
        cont.classList.remove('hidden');
    }

    return { cargar };
})();
window.Portal = Portal;
