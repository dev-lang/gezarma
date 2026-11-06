/**
 * busqueda.js — Búsqueda global de la barra superior: resultados mientras se
 * escribe y Enter para la página completa (o abrir el ticket si es un RMA exacto).
 *
 * El campo vive en index.html y no se recrea al navegar: se conecta una sola
 * vez. (Antes se conectaba en cada pantalla y, después de navegar un rato,
 * cada tecla disparaba varias búsquedas y Enter abría el ticket varias veces.)
 */
const Busqueda = (() => {
    let _iniciada = false, _espera = null, _ultima = 0;

    function pintar(cont, resultados, q) {
        cont.innerHTML = resultados.length
            ? resultados.slice(0, 6).map(t => `
                <div data-ticket="${t.id}" class="p-4 border-b hover:bg-gray-50 cursor-pointer transition">
                    <div class="flex items-center gap-2">
                        <span class="font-bold text-blue-600 text-sm">${esc(t.numero_rma)}</span>
                        <span class="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded uppercase">${esc(t.estado)}</span>
                    </div>
                    <div class="text-xs text-gray-500 mt-0.5">${esc(t.producto)} · SN: ${esc(t.numero_serie)}</div>
                </div>`).join('')
              + (resultados.length > 6 ? `<div data-todos class="p-3 text-center text-blue-600 text-xs font-bold hover:bg-blue-50 cursor-pointer">Ver los ${resultados.length} resultados →</div>` : '')
            : '<div class="p-4 text-gray-400 italic text-sm">Sin resultados</div>';
        cont.querySelectorAll('[data-ticket]').forEach(el => el.addEventListener('click', () => {
            cont.classList.add('hidden');
            app.viewTicket(+el.dataset.ticket);
        }));
        cont.querySelector('[data-todos]')?.addEventListener('click', () => { cont.classList.add('hidden'); ui.loadSearchPage(q); });
        cont.classList.remove('hidden');
    }

    function iniciar() {
        if (_iniciada) return;
        const input = document.getElementById('global-search');
        const cont = document.getElementById('search-results');
        if (!input || !cont) return;
        _iniciada = true;

        input.addEventListener('keydown', e => {
            if (e.key === 'Escape') { cont.classList.add('hidden'); return; }
            if (e.key !== 'Enter') return;
            e.preventDefault();
            const q = input.value.trim();
            cont.classList.add('hidden');
            clearTimeout(_espera);
            _ultima++;   // descarta resultados que lleguen tarde
            if (q.length < 2) return;
            // N° de RMA exacto (tipeado o del lector de código de barras): abre el ticket
            Recepcion.abrirRma(q).then(abierto => {
                if (abierto) input.value = '';
                else ui.loadSearchPage(q);
            });
        });

        input.addEventListener('input', () => {
            clearTimeout(_espera);
            const q = input.value.trim();
            if (q.length < 2) { cont.classList.add('hidden'); return; }
            const pedido = ++_ultima;
            _espera = setTimeout(async () => {
                try {
                    const resultados = await api.searchGlobal(q);
                    if (pedido === _ultima) pintar(cont, resultados, q);   // solo la última búsqueda
                } catch (err) { console.error(err); }
            }, 300);
        });

        document.addEventListener('click', e => {
            if (!input.contains(e.target) && !cont.contains(e.target)) cont.classList.add('hidden');
        });
    }

    return { iniciar };
})();
window.Busqueda = Busqueda;
