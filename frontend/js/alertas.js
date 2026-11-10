/**
 * alertas.js — Panel de alertas del dashboard (solo taller): SLA vencidos o por
 * vencer, equipos listos para retirar, presupuestos sin respuesta y repuestos
 * bajo el stock mínimo. Arriba, "Para hoy": cuántos hay de cada cosa (click → la tarjeta).
 */
const Alertas = (() => {

    // Clases completas (no armadas con variables) para que Tailwind las detecte siempre
    const COLORES = {
        red:   { head: 'bg-red-50',   text: 'text-red-700',   border: 'border-red-200' },
        blue:  { head: 'bg-blue-50',  text: 'text-blue-700',  border: 'border-blue-200' },
        green: { head: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
        amber: { head: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
    };

    function tarjeta(titulo, color, filas, pie = '', id = '') {
        const c = COLORES[color];
        return `
        <div class="bg-white rounded-2xl shadow border border-gray-100 overflow-hidden scroll-mt-24" ${id ? `id="alerta-${id}"` : ''}>
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

    function filaPresupuesto(t) {
        return `
        <li class="px-5 py-2.5 flex items-center justify-between gap-3 text-sm hover:bg-gray-50 cursor-pointer"
            onclick="api.getTicket(${t.id}).then(tk => ui.showTicketDetail(tk))">
            <span class="min-w-0"><span class="font-semibold text-blue-700">${esc(t.numero_rma)}</span>
                <span class="text-gray-500 truncate"> · ${esc(t.cliente || '')}${t.telefono ? ' · ' + esc(t.telefono) : ''}</span></span>
            <span class="shrink-0 text-xs font-bold ${t.dias_esperando >= 3 ? 'text-red-600' : 'text-blue-700'}">${
                t.dias_esperando === 0 ? 'enviado hoy' : t.dias_esperando === 1 ? 'hace 1 día' : `hace ${t.dias_esperando} días`}</span>
        </li>`;
    }

    /** Fila de contadores de arriba: lo que hay que mirar hoy */
    function paraHoy(items) {
        const conAlgo = items.filter(i => i.n > 0);
        if (!conAlgo.length) {
            return `<div class="lg:col-span-2 flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
                ${icono('check-circulo', 'w-4 h-4')}<span>Todo al día: nada vencido ni esperando.</span></div>`;
        }
        return `
        <div class="lg:col-span-2">
            <h3 class="text-xs font-bold uppercase tracking-wide text-gray-500 mb-2">Para hoy</h3>
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">${items.map(i => `
                <button type="button" data-ir="${i.id}" ${i.n ? '' : 'disabled'}
                    class="text-left bg-white rounded-xl border ${i.n ? i.borde + ' hover:shadow-md' : 'border-gray-100 opacity-60'} shadow-sm px-4 py-3 transition">
                    <span class="block text-2xl font-black ${i.n ? i.color : 'text-gray-400'}">${i.n}</span>
                    <span class="block text-xs font-semibold text-gray-600">${i.texto}</span>
                </button>`).join('')}
            </div>
        </div>`;
    }

    async function cargar() {
        const panel = document.getElementById('alertas-panel');
        if (!panel) return;
        const taller = ['administrador', 'tecnico'].includes(auth.getUser()?.role || '');
        const [sla, stock, retiro, presupuestos, externos] = await Promise.all([
            api.request('tickets/sla/alertas').catch(() => []),
            api.request('stock/alertas').catch(() => []),
            api.request('tickets/retiro/pendientes').catch(() => []),
            api.request('tickets/presupuestos/pendientes').catch(() => []),
            taller ? api.request('envios?estado=enviado&atrasados=true').catch(() => null) : null,
        ]);
        const vencidos = sla.filter(t => t.horas_restantes < 0).length;
        const bloques = [paraHoy([
            { id: 'sla', n: vencidos, texto: 'SLA vencidos', color: 'text-red-600', borde: 'border-red-200' },
            { id: 'sla', n: sla.length - vencidos, texto: 'SLA por vencer', color: 'text-amber-600', borde: 'border-amber-200' },
            { id: 'retiro', n: retiro.length, texto: 'Listos para retirar', color: 'text-emerald-700', borde: 'border-emerald-200' },
            { id: 'presupuestos', n: presupuestos.length, texto: 'Presupuestos sin respuesta', color: 'text-blue-700', borde: 'border-blue-200' },
            { id: 'stock', n: stock.length, texto: 'Repuestos bajo el mínimo', color: 'text-amber-700', borde: 'border-amber-200' },
            ...(externos ? [{ id: 'externos', n: externos.envios.length, texto: 'Atrasados en el fabricante', color: 'text-fuchsia-700', borde: 'border-fuchsia-200' }] : []),
        ])];
        if (retiro.length) bloques.push(tarjeta('Listos para retirar', 'green', retiro.map(filaRetiro), '', 'retiro'));
        if (sla.length) bloques.push(tarjeta('SLA vencidos o por vencer', 'red', sla.map(filaSla), '', 'sla'));
        if (presupuestos.length) bloques.push(tarjeta('Presupuestos sin respuesta', 'blue', presupuestos.map(filaPresupuesto), '', 'presupuestos'));
        if (stock.length) {
            const pie = (auth.getUser()?.role || '') === 'administrador' ? `
                <div class="px-5 py-2.5 border-t text-right"><button type="button" onclick="ui.loadAdminPanel('pedidos')"
                    class="text-xs font-bold text-amber-700 hover:text-amber-900">Armar pedidos a proveedor →</button></div>` : '';
            bloques.push(tarjeta('Repuestos bajo el mínimo', 'amber', stock.map(filaStock), pie, 'stock'));
        }
        panel.innerHTML = bloques.join('');
        panel.classList.remove('hidden');
        panel.querySelectorAll('[data-ir]').forEach(b => b.addEventListener('click', () => {
            if (b.dataset.ir === 'externos') { window.Envios?.abrir(); return; }
            const destino = document.getElementById(`alerta-${b.dataset.ir}`);
            destino?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            destino?.classList.add('ring-2', 'ring-blue-400');
            setTimeout(() => destino?.classList.remove('ring-2', 'ring-blue-400'), 1500);
        }));
    }

    return { cargar };
})();
window.Alertas = Alertas;
