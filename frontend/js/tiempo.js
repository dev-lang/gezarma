/**
 * tiempo.js — Registro del tiempo de trabajo (solo taller).
 * - Tarjeta en el detalle del ticket: iniciar / pausar, cargar tiempo a mano,
 *   total por técnico y costo de mano de obra.
 * - Indicador en la barra superior con el trabajo en curso.
 * - Panel del administrador: horas por técnico de los últimos 30 días.
 */
const Tiempo = (() => {
    const esTaller = () => ['administrador', 'tecnico'].includes(auth.getUser()?.role || '');
    const pesos = n => '$ ' + Number(n).toLocaleString(I18N.locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    function duracion(min) {
        const m = Math.round(min);
        const h = Math.floor(m / 60);
        return h ? `${h} h ${String(m % 60).padStart(2, '0')} min` : `${m} min`;
    }
    const reloj = seg => [Math.floor(seg / 3600), Math.floor(seg / 60) % 60, Math.floor(seg) % 60]
        .map((n, i) => i ? String(n).padStart(2, '0') : n).join(':');

    let _tic = null;   // intervalo del contador en vivo de la tarjeta

    async function cargarDetalle(ticketId) {
        const card = document.getElementById('tiempo-card');
        if (!card) return;
        if (!esTaller()) { card.classList.add('hidden'); return; }
        let d;
        try { d = await api.request(`tickets/${ticketId}/tiempo`); } catch { card.classList.add('hidden'); return; }
        if (ui.currentTicketId !== ticketId) return;
        clearInterval(_tic);
        const corriendo = d.registros.find(r => r.id === d.en_curso_mio);
        const yo = auth.getUser();
        card.innerHTML = `
        <div class="bg-gray-50 border border-gray-100 p-4 rounded-lg">
            <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h3 class="text-gray-600 font-bold text-xs uppercase">Tiempo de trabajo</h3>
                    <p class="text-2xl font-black text-gray-800" data-total>${duracion(d.total_minutos)}</p>
                    <p class="text-xs text-gray-500">${d.por_tecnico.map(p => `${esc(p.nombre)}: ${duracion(p.minutos)}`).join(' · ') || 'Sin registros todavía.'}${d.costo !== null && d.total_minutos ? ` · mano de obra ${pesos(d.costo)}` : ''}</p>
                </div>
                <div class="flex items-center gap-2">
                    ${corriendo
                        ? `<span class="font-mono text-lg font-bold text-emerald-700" data-vivo>0:00:00</span>
                           <button type="button" data-accion="pausar" class="bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-bold">⏸ Pausar</button>`
                        : `<button type="button" data-accion="iniciar" class="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-bold">▶ Iniciar trabajo</button>`}
                    <button type="button" data-accion="manual" class="text-sm font-semibold text-blue-600 hover:text-blue-800 px-2">+ Cargar a mano</button>
                </div>
            </div>
            <form data-manual class="hidden mt-3 flex flex-wrap items-end gap-2">
                <label class="text-xs font-semibold text-gray-600">Minutos
                    <input type="number" min="1" max="1440" required data-min class="block w-24 px-3 py-1.5 border rounded-lg text-sm"></label>
                <label class="text-xs font-semibold text-gray-600 flex-1 min-w-[160px]">Qué se hizo (opcional)
                    <input type="text" maxlength="200" data-nota class="block w-full px-3 py-1.5 border rounded-lg text-sm"></label>
                <button class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg text-sm font-bold">Agregar</button>
            </form>
            ${d.registros.length ? `
            <details class="mt-3">
                <summary class="text-xs font-semibold text-gray-500 cursor-pointer">Ver ${d.registros.length} registro${d.registros.length === 1 ? '' : 's'}</summary>
                <ul class="mt-2 divide-y text-sm">${d.registros.map(r => `
                    <li class="py-1.5 flex items-center justify-between gap-2">
                        <span><b>${esc(r.usuario_nombre)}</b> · ${new Date(r.inicio).toLocaleString(I18N.locale, { hour12: false, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                            · ${r.en_curso ? '<span class="text-emerald-700 font-semibold">en curso</span>' : duracion(r.minutos)}${r.manual ? ' <span class="text-[10px] text-gray-400">(a mano)</span>' : ''}${r.nota ? ` — ${esc(r.nota)}` : ''}</span>
                        ${(r.usuario_id === yo?.user_id || yo?.role === 'administrador') && !r.en_curso
                            ? `<button type="button" data-borrar="${r.id}" class="text-xs text-red-500 hover:text-red-700" aria-label="Borrar registro">✕</button>` : ''}
                    </li>`).join('')}</ul>
            </details>` : ''}
        </div>`;
        card.classList.remove('hidden');

        if (corriendo) {
            const vivo = card.querySelector('[data-vivo]');
            const inicio = new Date(corriendo.inicio).getTime();
            const pintar = () => { if (vivo.isConnected) vivo.textContent = reloj((Date.now() - inicio) / 1000); else clearInterval(_tic); };
            pintar(); _tic = setInterval(pintar, 1000);
        }
        const refrescar = async (url, body) => {
            try {
                await api.request(url, { method: 'POST', body: JSON.stringify(body || {}) });
                await cargarDetalle(ticketId); chip();
            } catch (err) { toast.error(err.message); }
        };
        card.querySelector('[data-accion="iniciar"]')?.addEventListener('click', () => refrescar(`tickets/${ticketId}/tiempo/iniciar`));
        card.querySelector('[data-accion="pausar"]')?.addEventListener('click', () => refrescar(`tickets/${ticketId}/tiempo/pausar`));
        const form = card.querySelector('[data-manual]');
        card.querySelector('[data-accion="manual"]').addEventListener('click', () => { form.classList.toggle('hidden'); form.querySelector('[data-min]').focus(); });
        form.addEventListener('submit', e => {
            e.preventDefault();
            refrescar(`tickets/${ticketId}/tiempo/manual`, { minutos: +form.querySelector('[data-min]').value, nota: form.querySelector('[data-nota]').value });
        });
        card.querySelectorAll('[data-borrar]').forEach(b => b.addEventListener('click', async () => {
            if (!(await confirmDialog('¿Borrar este registro de tiempo?', 'Se descuenta del total del ticket.', 'Borrar'))) return;
            try { await api.request(`tiempo/${b.dataset.borrar}`, { method: 'DELETE' }); cargarDetalle(ticketId); }
            catch (err) { toast.error(err.message); }
        }));
    }

    // ── Indicador en la barra superior ───────────────────────────────────────
    let _chipTic = null;
    async function chip() {
        clearInterval(_chipTic);
        document.getElementById('tiempo-chip')?.remove();
        if (!auth.isLoggedIn() || !esTaller()) return;
        let r = null;
        try { r = await api.request('tiempo/actual'); } catch { return; }
        if (!r) return;
        const info = document.getElementById('user-info');
        if (!info) return;
        info.insertAdjacentHTML('beforebegin', `
            <button type="button" id="tiempo-chip" title="Trabajo en curso: ${esc(r.numero_rma)}"
                class="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-3 py-1.5 rounded-full">
                ⏱ <span class="font-mono">${esc(r.numero_rma)}</span> <span class="font-mono" data-vivo></span>
            </button>`);
        const el = document.getElementById('tiempo-chip');
        el.addEventListener('click', () => api.getTicket(r.ticket_id).then(t => ui.showTicketDetail(t)));
        const inicio = new Date(r.inicio).getTime();
        const pintar = () => { const v = el.querySelector('[data-vivo]'); if (v) v.textContent = reloj((Date.now() - inicio) / 1000); };
        pintar(); _chipTic = setInterval(pintar, 1000);
    }

    // ── Panel del administrador ──────────────────────────────────────────────
    async function panel() {
        const cont = document.getElementById('tiempo-panel');
        if (!cont) return;
        let r;
        try { r = await api.request('tiempo/resumen?dias=30'); } catch { cont.classList.add('hidden'); return; }
        if (!r.tecnicos.length) { cont.classList.add('hidden'); return; }
        const max = Math.max(...r.tecnicos.map(t => t.minutos), 1);
        cont.innerHTML = `
        <div class="bg-white rounded-2xl shadow border border-gray-100 p-5">
            <div class="flex items-end justify-between mb-3">
                <h3 class="font-bold text-gray-700 text-sm uppercase tracking-wide">Horas de trabajo · 30 días</h3>
                <p class="text-xs text-gray-400">Total ${duracion(r.total_minutos)}${r.costo !== null ? ` · ${pesos(r.costo)}` : ''}</p>
            </div>
            <ul class="space-y-2">${r.tecnicos.map(t => `
                <li class="text-sm">
                    <div class="flex justify-between gap-2"><span class="font-semibold text-gray-700">${esc(t.nombre)}${t.en_curso ? ' <span class="text-emerald-600 text-xs">● trabajando</span>' : ''}</span>
                        <span class="text-gray-500 text-xs">${duracion(t.minutos)} · ${t.tickets} ticket${t.tickets === 1 ? '' : 's'} · prom. ${duracion(t.promedio_por_ticket)}${t.costo !== null ? ` · ${pesos(t.costo)}` : ''}</span></div>
                    <div class="bg-gray-100 rounded-full h-2 mt-1"><div class="bg-blue-500 h-2 rounded-full" style="width:${(t.minutos / max) * 100}%"></div></div>
                </li>`).join('')}</ul>
        </div>`;
        cont.classList.remove('hidden');
    }

    return { cargarDetalle, chip, panel };
})();
window.Tiempo = Tiempo;
