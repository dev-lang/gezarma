/**
 * encuesta.js — Encuesta de satisfacción.
 * - En el detalle del ticket: el cliente califica (1 a 5) cuando se cierra; el
 *   taller ve la calificación.
 * - En el panel del taller: promedio, distribución y últimos comentarios.
 */
const Encuesta = (() => {
    const ETIQUETAS = ['', 'Muy mala', 'Mala', 'Regular', 'Buena', 'Excelente'];
    const estrellas = (n, cls = 'text-lg') =>
        `<span class="${cls} tracking-tight" aria-label="${n} de 5">${'★'.repeat(n)}<span class="text-gray-300">${'★'.repeat(5 - n)}</span></span>`;
    let _activa = null;

    async function activa() {
        if (_activa === null) {
            try { _activa = !!(await api.request('config/ajustes/publicos')).encuesta_activa; } catch { _activa = false; }
        }
        return _activa;
    }

    /** Selector de 1 a 5 estrellas + comentario. Devuelve () => {puntaje, comentario}. */
    function formulario(cont) {
        let puntaje = 0;
        cont.innerHTML = `
        <div class="flex items-center gap-1" role="radiogroup" aria-label="Calificación">
            ${[1, 2, 3, 4, 5].map(n => `<button type="button" data-p="${n}" role="radio" aria-checked="false" aria-label="${n} — ${ETIQUETAS[n]}"
                class="text-3xl leading-none text-gray-300 hover:scale-110 transition">★</button>`).join('')}
            <span data-etq class="ml-2 text-sm text-gray-500"></span>
        </div>
        <textarea data-com rows="2" maxlength="1000" placeholder="¿Algo para contarnos? (opcional)"
            class="mt-3 w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"></textarea>`;
        const botones = [...cont.querySelectorAll('[data-p]')];
        const pintar = n => botones.forEach(b => {
            const on = +b.dataset.p <= n;
            b.classList.toggle('text-amber-400', on); b.classList.toggle('text-gray-300', !on);
            b.setAttribute('aria-checked', String(+b.dataset.p === puntaje));
        });
        botones.forEach(b => {
            b.addEventListener('click', () => { puntaje = +b.dataset.p; pintar(puntaje); cont.querySelector('[data-etq]').textContent = ETIQUETAS[puntaje]; });
            b.addEventListener('mouseenter', () => pintar(+b.dataset.p));
            b.addEventListener('mouseleave', () => pintar(puntaje));
        });
        return () => ({ puntaje, comentario: cont.querySelector('[data-com]').value.trim() });
    }

    async function cargarDetalle(ticket) {
        const card = document.getElementById('encuesta-card');
        if (!card) return;
        const esCliente = (auth.getUser()?.role || '') === 'cliente';
        const e = ticket.encuesta;
        if (e) {
            card.innerHTML = `
            <div class="bg-amber-50 border border-amber-100 p-4 rounded-lg">
                <h3 class="text-amber-800 font-bold text-xs uppercase mb-1">${esCliente ? 'Tu calificación' : 'Calificación del cliente'}</h3>
                <p class="text-amber-500">${estrellas(e.puntaje)} <span class="text-sm text-amber-800 font-semibold ml-1">${ETIQUETAS[e.puntaje]}</span></p>
                ${e.comentario ? `<p class="text-sm text-gray-700 mt-1">“${esc(e.comentario)}”</p>` : ''}
                <p class="text-xs text-gray-400 mt-1">${new Date(e.fecha).toLocaleDateString('es-AR')}</p>
            </div>`;
            card.classList.remove('hidden');
            return;
        }
        if (!esCliente || ticket.estado !== 'Cerrado' || !(await activa())) { card.classList.add('hidden'); return; }
        card.innerHTML = `
        <div class="bg-blue-50 border border-blue-100 p-4 rounded-lg">
            <h3 class="text-blue-800 font-bold text-sm mb-1">¿Cómo te fue con la reparación?</h3>
            <p class="text-xs text-blue-600 mb-2">Calificala de 1 a 5. Nos ayuda a mejorar.</p>
            <div data-form></div>
            <button type="button" data-enviar class="mt-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-bold">Enviar calificación</button>
        </div>`;
        card.classList.remove('hidden');
        const leer = formulario(card.querySelector('[data-form]'));
        card.querySelector('[data-enviar]').addEventListener('click', async () => {
            const d = leer();
            if (!d.puntaje) { toast.error('Elegí de 1 a 5 estrellas.'); return; }
            try {
                const t = await api.request(`tickets/${ticket.id}/encuesta`, { method: 'POST', body: JSON.stringify(d) });
                toast.success('¡Gracias por tu calificación!');
                cargarDetalle(t);
            } catch (err) { toast.error(err.message); }
        });
    }

    async function panel() {
        const cont = document.getElementById('satisfaccion-panel');
        if (!cont) return;
        let r;
        try { r = await api.request('encuestas/resumen?dias=90'); } catch { cont.classList.add('hidden'); return; }
        if (!r.cantidad) { cont.classList.add('hidden'); return; }
        const max = Math.max(...Object.values(r.distribucion), 1);
        cont.innerHTML = `
        <div class="bg-white rounded-2xl shadow border border-gray-100 p-5 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
                <h3 class="font-bold text-gray-700 text-sm uppercase tracking-wide">Satisfacción · 90 días</h3>
                <p class="text-4xl font-black text-gray-800 mt-2">${r.promedio.toFixed(1).replace('.', ',')}<span class="text-lg text-gray-400 font-semibold"> / 5</span></p>
                <p class="text-amber-400">${estrellas(Math.round(r.promedio), 'text-xl')}</p>
                <p class="text-xs text-gray-400 mt-1">${r.cantidad} ${r.cantidad === 1 ? 'calificación' : 'calificaciones'}${r.tasa_respuesta !== null ? ` · respondió el ${Math.round(r.tasa_respuesta * 100)} % de los cerrados` : ''}</p>
            </div>
            <div class="space-y-1">
                ${[5, 4, 3, 2, 1].map(p => `
                <div class="flex items-center gap-2 text-xs">
                    <span class="w-4 text-right text-gray-500">${p}</span><span class="text-amber-400">★</span>
                    <div class="flex-1 bg-gray-100 rounded-full h-2"><div class="bg-amber-400 h-2 rounded-full" style="width:${(r.distribucion[p] / max) * 100}%"></div></div>
                    <span class="w-6 text-gray-500">${r.distribucion[p]}</span>
                </div>`).join('')}
            </div>
            <div>
                <p class="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Últimos comentarios</p>
                ${r.comentarios.length ? `<ul class="space-y-2 max-h-40 overflow-y-auto">${r.comentarios.map(c => `
                    <li class="text-sm cursor-pointer hover:bg-gray-50 rounded" onclick="api.getTicket(${c.ticket_id}).then(t => ui.showTicketDetail(t))">
                        <span class="text-amber-400 text-xs">${'★'.repeat(c.puntaje)}</span>
                        <span class="text-gray-700">“${esc(c.comentario)}”</span>
                        <span class="block text-[11px] text-gray-400">${esc(c.numero_rma)}${c.tecnico ? ' · ' + esc(c.tecnico) : ''}</span>
                    </li>`).join('')}</ul>` : '<p class="text-sm text-gray-400 italic">Sin comentarios.</p>'}
            </div>
        </div>`;
        cont.classList.remove('hidden');
    }

    return { cargarDetalle, panel, formulario };
})();
window.Encuesta = Encuesta;
