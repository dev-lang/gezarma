/**
 * alertas.js — Panel de alertas del dashboard (solo taller): SLA vencidos o por
 * vencer, equipos listos para retirar y repuestos bajo el stock mínimo. Si no hay alertas, no se muestra.
 */
const Alertas = (() => {
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    // Clases completas (no armadas con variables) para que Tailwind las detecte siempre
    const COLORES = {
        red:   { head: 'bg-red-50',   text: 'text-red-700',   border: 'border-red-200' },
        green: { head: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
        amber: { head: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
    };

    function tarjeta(titulo, color, filas, pie = '') {
        const c = COLORES[color];
        return `
        <div class="bg-white rounded-2xl shadow border border-gray-100 overflow-hidden">
            <div class="px-5 py-3 border-b ${c.head} flex items-center justify-between">
                <h3 class="font-bold ${c.text} text-sm uppercase tracking-wide">${titulo}</h3>
                <span class="text-xs font-bold ${c.text} bg-white border ${c.border} rounded-full px-2">${filas.length}</span>
            </div>
            <ul class="divide-y max-h-64 overflow-y-auto">${filas.join('')}</ul>${pie}
        </div>`;
    }

    function filaStock(r) {
        const neg = r.stock < 0;
        return `
        <li class="px-5 py-2.5 flex items-center justify-between text-sm">
            <span><span class="font-semibold text-gray-800">${esc(r.nombre)}</span>
                <span class="font-mono text-xs text-gray-400 ml-1">${esc(r.codigo)}</span></span>
            <span class="text-xs font-bold ${neg ? 'text-red-600' : 'text-amber-600'}">
                ${neg ? `Faltan ${-r.stock}` : `Quedan ${r.stock}`}${r.stock_minimo ? ` · mín. ${r.stock_minimo}` : ''}
            </span>
        </li>`;
    }

    function horas(h) {
        const a = Math.abs(h);
        const txt = a >= 48 ? `${Math.round(a / 24)} días` : a >= 1 ? `${Math.round(a)} h` : `${Math.max(1, Math.round(a * 60))} min`;
        return h < 0 ? `vencido hace ${txt}` : `vence en ${txt}`;
    }

    function filaSla(t) {
        const vencido = t.horas_restantes < 0;
        return `
        <li class="px-5 py-2.5 flex items-center justify-between gap-3 text-sm hover:bg-gray-50 cursor-pointer"
            onclick="api.getTicket(${t.id}).then(tk => ui.showTicketDetail(tk))">
            <span class="min-w-0"><span class="font-semibold text-blue-700">${esc(t.numero_rma)}</span>
                <span class="text-gray-500 truncate"> · ${esc(t.estado)}${t.tecnico_nombre ? ' · ' + esc(t.tecnico_nombre) : ' · sin técnico'}</span></span>
            <span class="shrink-0 text-xs font-bold ${vencido ? 'text-red-600' : 'text-amber-600'}">${horas(t.horas_restantes)}</span>
        </li>`;
    }

    function filaRetiro(t) {
        return `
        <li class="px-5 py-2.5 flex items-center justify-between gap-3 text-sm hover:bg-gray-50 cursor-pointer"
            onclick="api.getTicket(${t.id}).then(tk => ui.showTicketDetail(tk))">
            <span class="min-w-0"><span class="font-semibold text-blue-700">${esc(t.numero_rma)}</span>
                <span class="text-gray-500 truncate"> · ${esc(t.cliente || '')}${t.telefono ? ' · ' + esc(t.telefono) : ''}</span></span>
            <span class="shrink-0 text-xs font-bold ${t.vencido ? 'text-red-600' : 'text-emerald-700'}">
                ${t.vencido ? `plazo vencido · ${t.dias_esperando} días` : `${t.dias_esperando} días · quedan ${t.dias_restantes}`}</span>
        </li>`;
    }

    async function cargar() {
        const panel = document.getElementById('alertas-panel');
        if (!panel) return;
        const [sla, stock, retiro] = await Promise.all([
            api.request('tickets/sla/alertas').catch(() => []),
            api.request('stock/alertas').catch(() => []),
            api.request('tickets/retiro/pendientes').catch(() => []),
        ]);
        const bloques = [];
        if (retiro.length) bloques.push(tarjeta('Listos para retirar', 'green', retiro.map(filaRetiro)));
        if (sla.length) bloques.push(tarjeta('SLA vencidos o por vencer', 'red', sla.map(filaSla)));
        if (stock.length) {
            const pie = (auth.getUser()?.role || '') === 'administrador' ? `
                <div class="px-5 py-2.5 border-t text-right"><button type="button" onclick="ui.loadAdminPanel('pedidos')"
                    class="text-xs font-bold text-amber-700 hover:text-amber-900">Armar pedidos a proveedor →</button></div>` : '';
            bloques.push(tarjeta('Repuestos bajo el mínimo', 'amber', stock.map(filaStock), pie));
        }
        panel.innerHTML = bloques.join('');
        panel.classList.toggle('hidden', !bloques.length);
    }

    return { cargar };
})();
window.Alertas = Alertas;
