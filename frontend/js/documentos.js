/**
 * documentos.js — Menú "Documentos" del detalle del ticket (orden de ingreso,
 * remito, presupuesto, etiqueta) y apertura de un ticket desde el QR de la
 * etiqueta (/#ticket=ID).
 *
 * El servidor decide el formato según el ajuste "pdf_modo": PDF, o HTML que
 * se imprime solo. En los dos casos se abre en una pestaña nueva.
 */
const Documentos = (() => {
    const TIPOS = [
        { id: 'ingreso',     label: 'Orden de ingreso',     cliente: true },
        { id: 'remito',      label: 'Remito de entrega',    cliente: true },
        { id: 'presupuesto', label: 'Presupuesto',          cliente: true },
        { id: 'etiqueta',    label: 'Etiqueta (62 × 29 mm)', cliente: false },
    ];

    async function abrir(ticketId, tipo) {
        // La pestaña se abre en el mismo click (si no, el navegador la bloquea)
        const w = window.open('', '_blank');
        if (w) w.document.write('<p style="font-family:sans-serif;color:#6b7280;padding:24px">Generando documento…</p>');
        try {
            const res = await fetch(`/tickets/${ticketId}/documentos/${tipo}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
            });
            if (!res.ok) {
                const d = await res.json().catch(() => ({}));
                throw new Error(d.detail || 'No se pudo generar el documento.');
            }
            const url = URL.createObjectURL(await res.blob());
            if (w) w.location.href = url; else window.open(url, '_blank');
            setTimeout(() => URL.revokeObjectURL(url), 120000);
        } catch (e) {
            if (w) w.close();
            toast.error(e.message);
        }
    }

    function cerrarMenu() {
        document.getElementById('documentos-menu')?.remove();
        document.removeEventListener('click', _fuera, true);
    }
    function _fuera(e) {
        if (!e.target.closest('#documentos-menu')) cerrarMenu();
    }

    function menu(boton) {
        if (document.getElementById('documentos-menu')) { cerrarMenu(); return; }
        const ticketId = ui.currentTicketId;
        const esCliente = (auth.getUser()?.role || '') === 'cliente';
        const tipos = TIPOS.filter(t => !esCliente || t.cliente);
        const r = boton.getBoundingClientRect();
        const div = document.createElement('div');
        div.id = 'documentos-menu';
        div.className = 'fixed z-50 bg-white border border-gray-200 rounded-xl shadow-lg py-1 text-sm';
        div.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - r.width - 8))}px`;
        div.style.width = `${r.width}px`;
        // Abajo del botón; si no entra en la pantalla, arriba
        const alto = tipos.length * 38 + 10;
        div.style.top = (r.bottom + 4 + alto > window.innerHeight && r.top - 4 - alto > 0)
            ? `${r.top - 4 - alto}px` : `${r.bottom + 4}px`;
        div.innerHTML = tipos.map(t =>
            `<button type="button" data-tipo="${t.id}" class="w-full text-left px-4 py-2 hover:bg-gray-50 font-semibold text-gray-700">📄 ${t.label}</button>`
        ).join('');
        div.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
            cerrarMenu();
            abrir(ticketId, b.dataset.tipo);
        }));
        document.body.appendChild(div);
        setTimeout(() => document.addEventListener('click', _fuera, true), 0);
        window.addEventListener('scroll', cerrarMenu, { once: true });
    }

    // QR de la etiqueta: /#ticket=ID abre ese ticket (después del login si hace falta)
    async function abrirDesdeHash() {
        const m = location.hash.match(/ticket=(\d+)/);
        if (!m) return;
        history.replaceState(null, '', location.pathname + location.search);
        try {
            const t = await api.getTicket(parseInt(m[1]));
            await ui.showTicketDetail(t);
        } catch (e) {
            toast.error('No se pudo abrir el ticket de la etiqueta: ' + e.message);
        }
    }

    return { abrir, menu, abrirDesdeHash };
})();
window.Documentos = Documentos;
