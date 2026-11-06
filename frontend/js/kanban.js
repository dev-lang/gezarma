/**
 * kanban.js — Vista de tablero del dashboard (solo taller).
 *
 * Una columna por estado activo (en el orden configurado en Administración →
 * Estados). Arrastrar una tarjeta a otra columna cambia el estado con el mismo
 * endpoint que el detalle del ticket (historial, avisos y mails incluidos).
 * Las columnas de estados finales (Cerrado, Cancelado…) muestran solo los más
 * recientes para no llenar el tablero.
 */
const Kanban = (() => {
    const MAX_FINALES = 10;
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    let _tickets = [];
    let _estados = [];
    let _arrastrado = null;

    function tarjeta(t) {
        return `
        <div class="kanban-card bg-white rounded-lg border border-gray-200 shadow-sm p-3 cursor-grab active:cursor-grabbing hover:border-blue-300 transition"
             draggable="true" data-id="${t.id}">
            <div class="flex items-start justify-between gap-2">
                <span class="font-bold text-blue-600 text-sm">#${t.id}</span>
                ${components.priorityBadge(t.prioridad)}
            </div>
            <p class="font-mono text-[10px] text-gray-400">${esc(t.numero_rma)}${t.reingreso_garantia ? ' <span class="font-sans font-bold text-amber-700" title="Reingreso en garantía de la reparación">↩ reingreso</span>' : ''}</p>
            <p class="text-sm font-semibold text-gray-800 mt-1 leading-tight">${esc(t.producto)}</p>
            <p class="text-xs text-gray-500 truncate">${esc(t.usuario_nombre || '')}</p>
            <div class="flex items-center justify-between mt-2 gap-1">
                <span class="text-[11px] ${t.tecnico_nombre ? 'text-gray-600' : 'text-gray-400 italic'} truncate">
                    ${t.tecnico_nombre ? '🔧 ' + esc(t.tecnico_nombre) : 'Sin técnico'}</span>
                ${components.slaBadge(t.deadline_sla, t.estado).replace('ml-2', '')}
            </div>
        </div>`;
    }

    function render() {
        const cont = document.getElementById('kanban-board');
        if (!cont) return;
        cont.innerHTML = _estados.map(e => {
            let lista = _tickets.filter(t => t.estado === e.valor);
            const total = lista.length;
            let extra = '';
            if (e.es_final && total > MAX_FINALES) {
                lista = [...lista].sort((a, b) => new Date(b.fecha_actualizacion) - new Date(a.fecha_actualizacion)).slice(0, MAX_FINALES);
                extra = `<p class="text-[11px] text-gray-400 text-center py-1">y ${total - MAX_FINALES} más (usá el filtro de la lista)</p>`;
            }
            return `
            <div class="kanban-col flex-shrink-0 w-64 bg-gray-100 rounded-xl flex flex-col max-h-[70vh]" data-estado="${esc(e.valor)}">
                <div class="px-3 py-2 flex items-center justify-between border-b-2" style="border-color:${esc(e.color)}">
                    <span class="text-xs font-bold uppercase tracking-wide text-gray-700">${esc(e.etiqueta)}</span>
                    <span class="text-xs font-bold text-gray-500 bg-white rounded-full px-2">${total}</span>
                </div>
                <div class="kanban-drop flex-1 overflow-y-auto p-2 space-y-2 min-h-[80px] rounded-b-xl transition">
                    ${lista.map(tarjeta).join('')}${extra}
                </div>
            </div>`;
        }).join('');
        conectar(cont);
    }

    function conectar(cont) {
        cont.querySelectorAll('.kanban-card').forEach(card => {
            card.addEventListener('dragstart', e => {
                _arrastrado = parseInt(card.dataset.id);
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', card.dataset.id);
                setTimeout(() => card.classList.add('opacity-40'), 0);
            });
            card.addEventListener('dragend', () => { card.classList.remove('opacity-40'); _arrastrado = null; });
            card.addEventListener('click', () => api.getTicket(parseInt(card.dataset.id)).then(t => ui.showTicketDetail(t)));
        });
        cont.querySelectorAll('.kanban-col').forEach(col => {
            const zona = col.querySelector('.kanban-drop');
            col.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('bg-blue-50', 'ring-2', 'ring-blue-300'); });
            col.addEventListener('dragleave', e => {
                if (!col.contains(e.relatedTarget)) zona.classList.remove('bg-blue-50', 'ring-2', 'ring-blue-300');
            });
            col.addEventListener('drop', e => {
                e.preventDefault();
                zona.classList.remove('bg-blue-50', 'ring-2', 'ring-blue-300');
                const id = _arrastrado ?? parseInt(e.dataTransfer.getData('text/plain'));
                if (id) mover(id, col.dataset.estado);
            });
        });
    }

    async function mover(id, estado) {
        const t = _tickets.find(x => x.id === id);
        if (!t || t.estado === estado) return;
        const anterior = t.estado;
        t.estado = estado;           // se mueve ya; si el servidor lo rechaza, vuelve
        render();
        try {
            const actualizado = await api.updateTicketStatus(id, estado);
            Object.assign(t, actualizado);
            render();
            toast.success(`#${id} → ${(_estados.find(e => e.valor === estado) || {}).etiqueta || estado}`);
            if (typeof Alertas !== 'undefined') Alertas.cargar();
        } catch (err) {
            t.estado = anterior;
            render();
            toast.error(`No se pudo mover el ticket: ${err.message}`);
        }
    }

    async function cargar() {
        const cont = document.getElementById('kanban-board');
        if (cont) cont.innerHTML = '<p class="text-gray-400 italic text-sm p-4">Cargando tablero…</p>';
        try {
            const [estados, tickets] = await Promise.all([api.getEstadosConfig(), api.getTickets({ limit: 1000 })]);
            _estados = estados.filter(e => e.activo).sort((a, b) => a.orden - b.orden);
            // Tickets con un estado que ya no está activo: se muestran igual, en su propia columna
            const conocidos = new Set(_estados.map(e => e.valor));
            [...new Set(tickets.map(t => t.estado))].filter(v => !conocidos.has(v))
                .forEach(v => _estados.push({ valor: v, etiqueta: v, color: '#9ca3af', es_final: false }));
            _tickets = tickets;
            render();
        } catch (e) { toast.error('No se pudo cargar el tablero: ' + e.message); }
    }

    // ── Lista / Tablero ──────────────────────────────────────────────────────
    function vista() { try { return localStorage.getItem('gezarma-vista') || 'lista'; } catch { return 'lista'; } }

    function mostrar(v, recargar = true) {
        try { localStorage.setItem('gezarma-vista', v); } catch { /* sin storage: no se recuerda */ }
        const tablero = v === 'tablero';
        document.getElementById('kanban-wrap')?.classList.toggle('hidden', !tablero);
        document.getElementById('ticket-list-wrap')?.classList.toggle('hidden', tablero);
        document.getElementById('ticket-filters')?.classList.toggle('hidden', tablero);
        document.querySelectorAll('[data-vista]').forEach(b => {
            const activo = b.dataset.vista === v;
            b.classList.toggle('bg-white', activo);
            b.classList.toggle('shadow', activo);
            b.classList.toggle('text-gray-900', activo);
            b.classList.toggle('text-gray-500', !activo);
        });
        if (tablero && recargar) cargar();
    }

    function iniciar(esTaller) {
        const selector = document.getElementById('vista-selector');
        selector?.classList.toggle('hidden', !esTaller);
        selector?.classList.toggle('flex', esTaller);
        document.querySelectorAll('[data-vista]').forEach(b => { b.onclick = () => mostrar(b.dataset.vista); });
        mostrar(esTaller ? vista() : 'lista');
    }

    return { iniciar, cargar, mostrar };
})();
window.Kanban = Kanban;
