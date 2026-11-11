/**
 * tablas.js — Tablas que en el celular se ven como tarjetas.
 *
 * A una <table class="tabla-tarjetas"> le copia a cada celda el nombre de su columna
 * (data-label="Proveedor"), así el CSS de pantallas chicas muestra cada fila como una
 * tarjeta con "Rótulo  valor". También marca la primera celda (título de la tarjeta),
 * la de acciones, la de la casilla de selección y las filas vacías ("Sin resultados").
 * Se rehace sola cada vez que cambian las filas. En escritorio no cambia nada.
 */
(function () {
    const soloCasilla = c => c.querySelector('input[type=checkbox]') && !c.textContent.trim();

    function etiquetar(tabla) {
        const ths = [...tabla.querySelectorAll('thead th')];
        const nombres = ths.map(th => th.textContent.trim().replace(/\s+/g, ' '));
        ths.forEach(th => {
            const check = soloCasilla(th) || th.querySelector(':scope > label[data-todos]');
            th.classList.toggle('celda-check', !!check);
            // En el celular no hay encabezados: la casilla de "todos" lleva su texto al lado
            if (check && !th.querySelector('[data-todos]')) {
                const caja = th.querySelector('input[type=checkbox]');
                const l = document.createElement('label');
                l.dataset.todos = '';
                l.className = 'inline-flex items-center gap-2 cursor-pointer';
                caja.replaceWith(l);
                l.append(caja, Object.assign(document.createElement('span'), {
                    className: 'sm:hidden text-sm font-semibold text-gray-600 normal-case',
                    textContent: window.I18N ? I18N.t('Seleccionar todos') : 'Seleccionar todos' }));
            }
        });
        const filas = [...(tabla.tBodies[0]?.rows || [])];
        // La última columna es la de acciones si en alguna fila tiene botones (en otras puede decir "Principal")
        const conAcciones = filas.some(tr => tr.cells.length > 2 && tr.cells[tr.cells.length - 1].querySelector('button, a'));
        for (const tr of filas) {
            const celdas = [...tr.cells];
            if (celdas.length === 1 && celdas[0].colSpan > 1) { celdas[0].classList.add('celda-vacia'); continue; }
            let titulo = false;
            tr.classList.toggle('con-check', celdas.some(soloCasilla));
            celdas.forEach((td, i) => {
                const nombre = nombres[i] || '';
                if (td.dataset.label !== nombre) td.dataset.label = nombre;
                const check = soloCasilla(td);
                td.classList.toggle('celda-check', !!check);
                const acciones = conAcciones && i === celdas.length - 1 && celdas.length > 2;
                td.classList.toggle('celda-acciones', acciones);
                const esTitulo = !titulo && !check && !acciones;
                td.classList.toggle('celda-titulo', esTitulo);
                if (esTitulo) titulo = true;
            });
        }
    }

    const vistas = new WeakSet();
    function observar(tabla) {
        if (vistas.has(tabla)) return;
        vistas.add(tabla);
        etiquetar(tabla);
        new MutationObserver(() => etiquetar(tabla)).observe(tabla, { childList: true, subtree: true });
    }

    function buscar(raiz = document) {
        raiz.querySelectorAll?.('table.tabla-tarjetas').forEach(observar);
    }

    // Las pantallas llegan como partials: se buscan las tablas nuevas cuando aparecen
    const iniciar = () => {
        buscar();
        new MutationObserver(cambios => {
            for (const c of cambios) for (const n of c.addedNodes) {
                if (n.nodeType !== 1) continue;
                if (n.matches?.('table.tabla-tarjetas')) observar(n); else buscar(n);
            }
        }).observe(document.body, { childList: true, subtree: true });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
    window.Tablas = { etiquetar };
})();
