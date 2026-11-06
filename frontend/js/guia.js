/**
 * guia.js — Guía de primer uso (solo administrador): los pasos para dejar el
 * sistema listo, con lo que ya está hecho tildado. Se oculta sola cuando está
 * todo hecho, o con "Ocultar guía" (se vuelve a mostrar desde Ajustes → General).
 */
const Guia = (() => {
    const ACCIONES = {
        taller:    { texto: 'Ir a Ajustes', hacer: () => irAAjustes('general') },
        email:     { texto: 'Configurar', hacer: () => irAAjustes('email') },
        productos: { texto: 'Cargar productos', hacer: () => ui.loadAdminPanel('products') },
        tecnico:   { texto: 'Crear usuario', hacer: async () => { await ui.loadAdminPanel('users'); document.getElementById('admin-new-user-btn')?.click(); } },
        impresora: { texto: 'Imprimir etiqueta de prueba', hacer: () => Documentos.abrirUrl('/tickets/impresion-prueba/etiqueta').then(() => setTimeout(cargar, 1500)) },
    };

    async function irAAjustes(grupo) {
        await ui.loadAdminPanel('ajustes');
        setTimeout(() => document.querySelector(`[data-grupo="${grupo}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 400);
    }

    async function cargar() {
        const cont = document.getElementById('guia-panel');
        if (!cont) return;
        let g;
        try { g = await api.request('config/guia'); } catch { cont.classList.add('hidden'); return; }
        if (g.oculta || g.completa) { cont.classList.add('hidden'); cont.innerHTML = ''; return; }
        const hechos = g.pasos.filter(p => p.hecho).length;
        cont.innerHTML = `
        <div class="bg-white rounded-2xl shadow border border-blue-100 overflow-hidden">
            <div class="px-5 py-4 bg-blue-50 border-b border-blue-100 flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h3 class="font-bold text-blue-900">Dejá el sistema listo</h3>
                    <p class="text-xs text-blue-700">${hechos} de ${g.pasos.length} pasos hechos</p>
                </div>
                <div class="flex items-center gap-3">
                    <div class="w-32 h-2 rounded-full bg-blue-100 overflow-hidden" role="progressbar" aria-valuemin="0"
                        aria-valuemax="${g.pasos.length}" aria-valuenow="${hechos}">
                        <div class="h-full bg-blue-600" style="width:${Math.round(hechos * 100 / g.pasos.length)}%"></div>
                    </div>
                    <button type="button" data-ocultar class="text-xs font-semibold text-blue-700 hover:text-blue-900">Ocultar guía</button>
                </div>
            </div>
            <ol class="divide-y">${g.pasos.map((p, i) => `
                <li class="px-5 py-3 flex flex-wrap items-center gap-3">
                    <span class="w-7 h-7 shrink-0 rounded-full flex items-center justify-center text-xs font-bold
                        ${p.hecho ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}" aria-hidden="true">${p.hecho ? '✓' : i + 1}</span>
                    <div class="flex-1 min-w-[12rem]">
                        <p class="text-sm font-semibold ${p.hecho ? 'text-gray-400 line-through' : 'text-gray-800'}">${esc(p.titulo)}</p>
                        ${p.hecho ? '' : `<p class="text-xs text-gray-500">${esc(p.detalle)}</p>`}
                    </div>
                    ${p.hecho ? '<span class="text-xs font-semibold text-emerald-700">Hecho</span>'
                              : `<button type="button" data-paso="${p.id}" class="text-sm font-semibold text-blue-600 hover:text-blue-800">${esc(ACCIONES[p.id]?.texto || 'Ir')} →</button>`}
                </li>`).join('')}
            </ol>
        </div>`;
        cont.classList.remove('hidden');
        cont.querySelectorAll('[data-paso]').forEach(b => b.addEventListener('click', () => ACCIONES[b.dataset.paso]?.hacer()));
        cont.querySelector('[data-ocultar]').addEventListener('click', async () => {
            await api.request('config/guia', { method: 'PUT', body: JSON.stringify({ oculta: true }) });
            cont.classList.add('hidden');
            toast.info('Guía oculta. La podés volver a ver desde Ajustes → General.');
        });
    }

    return { cargar };
})();
window.Guia = Guia;
