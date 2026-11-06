/**
 * importar.js — Importar productos o repuestos desde Excel (.xlsx) o CSV.
 *
 * Paso 1: bajar la plantilla (o los datos actuales para editarlos) y elegir el archivo.
 * Paso 2: vista previa fila por fila (nuevos, cambios, sin cambios, errores).
 * Paso 3: importar; las filas con error se saltean y se pueden corregir y volver a subir.
 * Backend: routers/importacion.py.
 */
const Importar = (() => {
    const TIPOS = {
        productos: { titulo: 'Importar productos', actuales: '⬇ Mis productos actuales (para editar)',
                     ayuda: 'Se reconocen por nombre, en cualquier orden. Si ya existe uno con la misma marca y modelo (o el mismo N° de parte), se actualiza; una celda vacía no cambia ese dato.',
                     columnas: 'Marca, Modelo, Categoría, Garantía (meses), N° de parte' },
        repuestos: { titulo: 'Importar repuestos', actuales: '⬇ Mis repuestos actuales (para editar)',
                     ayuda: 'Se reconocen por nombre, en cualquier orden. Si ya existe uno con el mismo código, se actualiza; una celda vacía no cambia ese dato.',
                     columnas: 'Código, Nombre, Proveedor, Precio, Stock, Stock mínimo, Categoría' },
    };
    const ACCIONES = {
        crear:       { texto: 'Nuevo',        cls: 'bg-emerald-100 text-emerald-700' },
        actualizar:  { texto: 'Actualiza',    cls: 'bg-blue-100 text-blue-700' },
        sin_cambios: { texto: 'Sin cambios',  cls: 'bg-gray-100 text-gray-500' },
        omitir:      { texto: 'Se omite',     cls: 'bg-gray-100 text-gray-500' },
        error:       { texto: 'Error',        cls: 'bg-red-100 text-red-700' },
    };
    let _div = null, _archivo = null, _tipo = null, _alTerminar = null;

    const cabeceras = () => ({ 'Authorization': `Bearer ${localStorage.getItem('token')}`, 'Accept-Language': I18N.codigo });

    async function descargar(conDatos, formato) {
        try {
            const res = await fetch(`/importar/${_tipo}/plantilla?formato=${formato}${conDatos ? '&con_datos=true' : ''}`, { headers: cabeceras() });
            if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || I18N.t('No se pudo descargar.'));
            const url = URL.createObjectURL(await res.blob());
            const a = Object.assign(document.createElement('a'), { href: url, download: `${_tipo}${conDatos ? '' : '-plantilla'}.${formato}` });
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 30000);
        } catch (e) { toast.error(e.message); }
    }

    async function enviar(previa) {
        const fd = new FormData();
        fd.append('archivo', _archivo);
        fd.append('actualizar', _div.querySelector('[data-actualizar]').checked ? 'true' : 'false');
        const res = await fetch(`/importar/${_tipo}${previa ? '/vista-previa' : ''}`, { method: 'POST', headers: cabeceras(), body: fd });
        const datos = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof datos.detail === 'string' ? datos.detail : I18N.t('No se pudo leer el archivo.'));
        return datos;
    }

    const valor = v => (v === null || v === undefined || v === '') ? '—' : esc(String(v));

    function filaHtml(f) {
        const a = ACCIONES[f.accion];
        const ident = f.datos.codigo || [f.datos.marca, f.datos.modelo].filter(Boolean).join(' ') || '—';
        let detalle = '';
        if (f.errores.length) detalle = `<span class="text-red-600">${f.errores.map(esc).join(' · ')}</span>`;
        else if (f.accion === 'actualizar') detalle = Object.entries(f.cambios).map(([c, [antes, despues]]) =>
            `<span class="whitespace-nowrap"><span class="text-gray-500">${esc(c.replace(/_/g, ' '))}:</span> ${valor(antes)} → <b>${valor(despues)}</b></span>`).join(' · ');
        else if (f.accion === 'crear') detalle = `<span class="text-gray-500">${esc(f.datos.nombre || f.datos.categoria || '')}</span>`;
        return `
        <tr class="${f.accion === 'error' ? 'bg-red-50/50' : ''}" data-accion-fila="${f.accion}">
            <td class="px-3 py-2 text-xs text-gray-400 font-mono">${f.fila}</td>
            <td class="px-3 py-2"><span class="text-[11px] font-bold px-2 py-0.5 rounded-full ${a.cls}">${a.texto}</span></td>
            <td class="px-3 py-2 text-sm font-semibold text-gray-800" translate="no">${esc(ident)}</td>
            <td class="px-3 py-2 text-xs">${detalle}</td>
        </tr>`;
    }

    function mostrarVista(v) {
        const r = v.resumen;
        const validas = r.crear + r.actualizar;
        const chip = (n, accion, texto) => n ? `<button type="button" data-filtro="${accion}" class="text-xs font-bold px-2.5 py-1 rounded-full ${ACCIONES[accion].cls}"><span>${texto}</span>: <span>${n}</span></button>` : '';
        _div.querySelector('[data-paso2]').innerHTML = `
            <div class="flex flex-wrap items-center gap-2 mb-3">
                <span class="text-sm text-gray-600">${v.total === 1 ? '1 fila' : `${v.total} filas`}</span>
                ${chip(r.crear, 'crear', 'Nuevos')}${chip(r.actualizar, 'actualizar', 'Con cambios')}
                ${chip(r.sin_cambios, 'sin_cambios', 'Sin cambios')}${chip(r.omitir, 'omitir', 'Se omiten')}${chip(r.error, 'error', 'Con errores')}
                <button type="button" data-filtro="" class="text-xs font-semibold text-blue-600 hover:text-blue-800 ml-1">Ver todas</button>
            </div>
            <p class="text-xs text-gray-500 mb-2"><span>Columnas reconocidas:</span> <span translate="no">${v.columnas.map(esc).join(', ')}</span>${v.ignoradas.length
                ? ` · <span class="text-amber-700"><span>se ignoran:</span> <span translate="no">${v.ignoradas.map(esc).join(', ')}</span></span>` : ''}</p>
            ${r.error ? `<p class="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-2">Las filas con error no se importan. Podés importar el resto y después corregirlas en el archivo y volver a subirlo.</p>` : ''}
            <div class="border rounded-lg overflow-auto max-h-[45vh]">
                <table class="w-full text-left min-w-[520px]">
                    <thead class="bg-gray-50 sticky top-0"><tr class="text-[11px] uppercase text-gray-500">
                        <th class="px-3 py-2">Fila</th><th class="px-3 py-2">Qué pasa</th><th class="px-3 py-2">${_tipo === 'repuestos' ? 'Código' : 'Producto'}</th><th class="px-3 py-2">Detalle</th>
                    </tr></thead>
                    <tbody class="divide-y" data-cuerpo>${v.filas.map(filaHtml).join('')}</tbody>
                </table>
            </div>
            ${v.recortada ? `<p class="text-xs text-gray-400 mt-1">Se muestran las primeras filas y todos los errores.</p>` : ''}`;
        _div.querySelector('[data-paso2]').classList.remove('hidden');
        _div.querySelectorAll('[data-filtro]').forEach(b => b.addEventListener('click', () => {
            _div.querySelectorAll('[data-accion-fila]').forEach(tr =>
                tr.classList.toggle('hidden', !!b.dataset.filtro && tr.dataset.accionFila !== b.dataset.filtro));
        }));
        const boton = _div.querySelector('[data-importar]');
        boton.disabled = !validas;
        boton.textContent = validas ? I18N.t('Importar {0} filas', validas) : I18N.t('No hay nada para importar');
    }

    async function revisar() {
        if (!_archivo) return;
        const err = _div.querySelector('[data-error]');
        err.classList.add('hidden');
        _div.querySelector('[data-paso2]').classList.add('hidden');
        _div.querySelector('[data-importar]').disabled = true;
        _div.querySelector('[data-nombre]').textContent = _archivo.name;
        try { mostrarVista(await enviar(true)); }
        catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
    }

    async function importar() {
        const boton = _div.querySelector('[data-importar]');
        boton.disabled = true;
        try {
            const r = await enviar(false);
            cerrar();
            const partes = [r.creados && I18N.t('{0} nuevos', r.creados), r.actualizados && I18N.t('{0} actualizados', r.actualizados),
                            r.con_error && I18N.t('{0} con error (no se importaron)', r.con_error)].filter(Boolean);
            (r.con_error ? toast.warning : toast.success)(I18N.t('Importación terminada: {0}.', partes.join(', ') || I18N.t('sin cambios')));
            _alTerminar?.();
        } catch (e) {
            boton.disabled = false;
            toast.error(e.message);
        }
    }

    function cerrar() { _div?.remove(); _div = null; _archivo = null; }

    /** Abre el asistente. tipo: 'productos' | 'repuestos'; alTerminar: para recargar la lista. */
    function abrir(tipo, alTerminar) {
        cerrar();
        _tipo = tipo; _alTerminar = alTerminar;
        const T = TIPOS[tipo];
        _div = document.createElement('div');
        _div.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4';
        _div.setAttribute('data-modal', '');
        _div.innerHTML = `
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[94vh] flex flex-col" role="dialog" aria-modal="true">
            <div class="flex items-center justify-between px-6 py-4 border-b">
                <h3 class="font-bold text-gray-800">${T.titulo}</h3>
                <button type="button" data-cerrar class="text-gray-400 hover:text-gray-600 text-2xl leading-none" aria-label="Cerrar">×</button>
            </div>
            <div class="p-6 overflow-y-auto space-y-4">
                <div class="text-sm text-gray-600 space-y-1">
                    <p>Subí un Excel (.xlsx) o un CSV con una fila de encabezados. Columnas: <b>${T.columnas}</b>.</p>
                    <p class="text-xs text-gray-500"><span>${T.ayuda}</span>${tipo === 'repuestos' ? ' <span>Los cambios de stock quedan en el historial como ajuste.</span>' : ''}</p>
                </div>
                <div class="flex flex-wrap gap-2 text-sm">
                    <button type="button" data-bajar="0:xlsx" class="border border-gray-300 rounded-lg px-3 py-1.5 font-semibold text-gray-700 hover:bg-gray-50">⬇ Plantilla Excel</button>
                    <button type="button" data-bajar="0:csv" class="border border-gray-300 rounded-lg px-3 py-1.5 font-semibold text-gray-700 hover:bg-gray-50">⬇ Plantilla CSV</button>
                    <button type="button" data-bajar="1:xlsx" class="border border-blue-200 rounded-lg px-3 py-1.5 font-semibold text-blue-700 hover:bg-blue-50">${T.actuales}</button>
                </div>
                <label data-zona class="flex flex-col items-center justify-center gap-1 border-2 border-dashed border-gray-300 rounded-xl px-4 py-8 cursor-pointer hover:border-blue-400 hover:bg-blue-50/40 transition text-center">
                    <span class="text-3xl" aria-hidden="true">📄</span>
                    <span class="text-sm font-semibold text-gray-700">Elegí el archivo o arrastralo acá</span>
                    <span class="text-xs text-gray-400" data-nombre translate="no">.xlsx o .csv · hasta 5000 filas</span>
                    <input type="file" accept=".xlsx,.csv" class="hidden" data-input>
                </label>
                <label class="flex items-center gap-2 text-sm text-gray-700">
                    <input type="checkbox" data-actualizar checked class="w-4 h-4 accent-blue-600">
                    Actualizar los que ya existen (si no, solo se agregan los nuevos)
                </label>
                <p data-error class="hidden text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2"></p>
                <div data-paso2 class="hidden"></div>
            </div>
            <div class="flex justify-end gap-3 px-6 py-4 border-t">
                <button type="button" data-cancelar class="px-5 py-2 text-gray-500 font-semibold hover:text-gray-700">Cancelar</button>
                <button type="button" data-importar disabled class="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-bold">Importar</button>
            </div>
        </div>`;
        document.body.appendChild(_div);
        _div.querySelectorAll('[data-cerrar],[data-cancelar]').forEach(b => b.addEventListener('click', cerrar));
        _div.querySelectorAll('[data-bajar]').forEach(b => b.addEventListener('click', () => {
            const [conDatos, formato] = b.dataset.bajar.split(':');
            descargar(conDatos === '1', formato);
        }));
        const input = _div.querySelector('[data-input]');
        input.addEventListener('change', () => { _archivo = input.files[0] || null; input.value = ''; revisar(); });
        _div.querySelector('[data-actualizar]').addEventListener('change', revisar);
        const zona = _div.querySelector('[data-zona]');
        zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('border-blue-500', 'bg-blue-50'); });
        zona.addEventListener('dragleave', () => zona.classList.remove('border-blue-500', 'bg-blue-50'));
        zona.addEventListener('drop', e => {
            e.preventDefault(); zona.classList.remove('border-blue-500', 'bg-blue-50');
            _archivo = e.dataTransfer.files[0] || null; revisar();
        });
        _div.querySelector('[data-importar]').addEventListener('click', importar);
    }

    return { abrir };
})();
window.Importar = Importar;
