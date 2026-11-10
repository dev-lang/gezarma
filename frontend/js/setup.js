/**
 * setup.js — Configuración inicial del taller (asistente de primer uso, solo administrador).
 *
 * Aparece sola la primera vez que entra un administrador a un sistema nuevo. Cada paso
 * guarda al avanzar y se puede saltear; "Terminar más tarde" lo cierra y queda el aviso en
 * la guía del panel (y el botón en Ajustes → General) para retomarlo.
 * Pasos: taller · cuenta · rubro · equipo · catálogo y lugares · impresión · avisos · listo.
 * Las reglas están en el servidor (services/setup.py); cada paso usa los endpoints de siempre.
 */
const Setup = (() => {
    const $ = id => document.getElementById(id);
    const t = (s, ...a) => esc(I18N.t(s, ...a));
    const PASOS = [
        { id: 'taller',    titulo: 'Tu taller',            icono: 'etiqueta' },
        { id: 'cuenta',    titulo: 'Tu cuenta',            icono: 'usuario' },
        { id: 'rubro',     titulo: 'Qué reparás',          icono: 'llave' },
        { id: 'equipo',    titulo: 'Tu equipo',            icono: 'usuarios' },
        { id: 'catalogo',  titulo: 'Catálogo y lugares',   icono: 'paquete' },
        { id: 'impresion', titulo: 'Impresión',            icono: 'impresora' },
        { id: 'avisos',    titulo: 'Avisos y clientes',    icono: 'mail' },
        { id: 'listo',     titulo: 'Listo',                icono: 'check-circulo' },
    ];
    const st = { i: 0, estado: null, ajustes: {}, rubros: null, elegidos: new Set(), quitarEjemplos: true };

    const input = (id, valor = '', extra = '') => `<input id="${id}" value="${esc(valor ?? '')}" ${extra}
        class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">`;
    const campo = (id, etiqueta, html, { ayuda = '', opcional = false } = {}) => `
        <div><label class="block text-sm font-semibold text-gray-700 mb-1" for="${id}">${t(etiqueta)}${opcional ? ` <span class="font-normal text-gray-400">${t('(opcional)')}</span>` : ''}</label>
            ${html}${ayuda ? `<p class="text-xs text-gray-400 mt-1">${t(ayuda)}</p>` : ''}</div>`;
    const select = (id, opciones, valor) => `<select id="${id}" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
        ${Object.entries(opciones).map(([v, txt]) => `<option value="${esc(v)}" ${String(v) === String(valor) ? 'selected' : ''}>${esc(txt)}</option>`).join('')}</select>`;
    const interruptor = (id, texto, activo, ayuda = '') => `
        <label class="flex items-start gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50">
            <input type="checkbox" id="${id}" ${activo ? 'checked' : ''} class="mt-0.5 w-4 h-4 accent-blue-600">
            <span><span class="block text-sm font-semibold text-gray-800">${t(texto)}</span>${ayuda ? `<span class="block text-xs text-gray-500">${t(ayuda)}</span>` : ''}</span>
        </label>`;
    const tarjeta = html => `<div class="bg-white border border-gray-200 rounded-xl p-4 sm:p-5">${html}</div>`;

    // ── Entrada ──────────────────────────────────────────────────────────────
    /** Desde el panel: la abre sola si el sistema es nuevo y no se dejó para después. */
    async function revisar() {
        if (auth.getUser()?.role !== 'administrador' || $('setup-modal')) return;
        try {
            const e = await api.request('setup');
            if (!e.terminado && !e.pospuesto) abrir(e);
        } catch { /* sin permiso o sin red: no molesta */ }
    }

    async function abrir(estado = null, paso = null) {
        if ($('setup-modal')) return;
        try {
            st.estado = estado || await api.request('setup');
            const lista = await api.request('config/ajustes');
            st.ajustes = Object.fromEntries(lista.map(a => [a.clave, a]));
        } catch (e) { toast.error(e.message); return; }
        st.elegidos = new Set(st.estado.rubros || []);
        // Retoma en el primer paso sin hacer
        st.i = paso != null ? paso : Math.max(0, PASOS.findIndex(p => p.id !== 'listo' && !st.estado.pasos.includes(p.id)));
        if (st.i < 0) st.i = PASOS.length - 1;
        const div = document.createElement('div');
        div.id = 'setup-modal';
        div.className = 'fixed inset-0 z-[55] bg-gray-50 overflow-y-auto';   // debajo de confirmar e importar (z-60)
        div.innerHTML = `
        <div class="min-h-full flex flex-col" role="dialog" aria-modal="true" aria-labelledby="setup-titulo">
            <header class="bg-white border-b sticky top-0 z-10">
                <div class="max-w-5xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
                    <div class="flex items-center gap-3 min-w-0">
                        <span class="w-9 h-9 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0">${icono('engranaje', 'w-5 h-5')}</span>
                        <div class="min-w-0">
                            <p class="text-xs font-semibold text-blue-700">${t('Configuración inicial')}</p>
                            <p id="setup-paso-n" class="text-sm text-gray-500 truncate"></p>
                        </div>
                    </div>
                    <button type="button" id="setup-luego" data-cerrar class="shrink-0 whitespace-nowrap text-sm font-semibold text-gray-500 hover:text-gray-800 px-3 py-2 rounded-lg hover:bg-gray-100"><span class="sm:hidden">${t('Más tarde')}</span><span class="hidden sm:inline">${t('Terminar más tarde')}</span></button>
                </div>
                <div class="h-1 bg-gray-100"><div id="setup-barra" class="h-full bg-blue-600 transition-all"></div></div>
            </header>
            <div class="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-6 flex gap-8">
                <nav class="hidden md:block w-52 shrink-0" aria-label="${t('Pasos')}"><ol id="setup-nav" class="space-y-1 sticky top-24"></ol></nav>
                <main class="flex-1 min-w-0">
                    <h2 id="setup-titulo" class="text-2xl font-bold text-gray-900"></h2>
                    <p id="setup-bajada" class="text-sm text-gray-500 mt-1 mb-5"></p>
                    <div id="setup-cuerpo" class="space-y-4"></div>
                    <p id="setup-error" class="hidden mt-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"></p>
                </main>
            </div>
            <footer class="bg-white border-t sticky bottom-0">
                <div class="max-w-5xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
                    <button type="button" id="setup-atras" class="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100">← ${t('Atrás')}</button>
                    <div class="flex items-center gap-2">
                        <button type="button" id="setup-saltear" class="px-4 py-2 text-sm font-semibold text-gray-500 hover:text-gray-800 rounded-lg hover:bg-gray-100">${t('Saltear')}</button>
                        <button type="button" id="setup-seguir" class="px-5 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm">${t('Guardar y seguir')}</button>
                    </div>
                </div>
            </footer>
        </div>`;
        document.body.appendChild(div);
        document.body.classList.add('overflow-hidden');
        $('setup-luego').addEventListener('click', luego);
        $('setup-atras').addEventListener('click', () => ir(st.i - 1));
        $('setup-saltear').addEventListener('click', () => ir(st.i + 1));
        $('setup-seguir').addEventListener('click', seguir);
        $('setup-nav').addEventListener('click', e => { const b = e.target.closest('[data-ir]'); if (b) ir(Number(b.dataset.ir)); });
        pintar();
    }

    function cerrar() {
        $('setup-modal')?.remove();
        document.body.classList.remove('overflow-hidden');
    }

    async function luego() {
        try { await api.request('setup', { method: 'PUT', body: JSON.stringify({ pospuesto: true }) }); } catch { /* igual se cierra */ }
        cerrar();
        toast.info(I18N.t('Podés seguir cuando quieras desde la guía del panel o desde Ajustes → General.'));
        if (typeof Guia !== 'undefined') Guia.cargar();
    }

    function ir(i) {
        if (i < 0 || i >= PASOS.length) return;
        st.i = i;
        error('');
        pintar();
        $('setup-modal')?.scrollTo({ top: 0 });
    }

    function error(msg) {
        const p = $('setup-error');
        if (!p) return;
        p.textContent = msg || '';
        p.classList.toggle('hidden', !msg);
    }

    function pintar() {
        const p = PASOS[st.i], hechos = new Set(st.estado.pasos);
        $('setup-paso-n').textContent = I18N.t('Paso {0} de {1} · {2}', st.i + 1, PASOS.length, I18N.t(p.titulo));
        $('setup-barra').style.width = `${Math.round((st.i + 1) * 100 / PASOS.length)}%`;
        $('setup-nav').innerHTML = PASOS.map((x, i) => `
            <li><button type="button" data-ir="${i}" ${i === st.i ? 'aria-current="step"' : ''}
                class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-left transition ${i === st.i ? 'bg-blue-50 text-blue-800 font-semibold' : 'text-gray-600 hover:bg-gray-100'}">
                <span class="w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0 ${hechos.has(x.id) ? 'bg-emerald-100 text-emerald-700' : i === st.i ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-500'}">${hechos.has(x.id) ? icono('check', 'w-3.5 h-3.5') : i + 1}</span>
                <span class="truncate">${t(x.titulo)}</span></button></li>`).join('');
        $('setup-atras').classList.toggle('invisible', st.i === 0);
        const final = p.id === 'listo';
        $('setup-saltear').classList.toggle('hidden', final);
        $('setup-seguir').textContent = I18N.t(final ? 'Ir al panel' : 'Guardar y seguir');
        PANTALLAS[p.id]();
    }

    function encabezado(titulo, bajada) {
        $('setup-titulo').textContent = I18N.t(titulo);
        $('setup-bajada').textContent = I18N.t(bajada);
    }

    async function seguir() {
        const p = PASOS[st.i], b = $('setup-seguir');
        error('');
        b.disabled = true;
        try {
            if (p.id === 'listo') { await terminar(); return; }
            const ok = await (GUARDAR[p.id] || (async () => true))();
            if (ok === false) return;
            st.estado = await api.request('setup', { method: 'PUT', body: JSON.stringify({ paso: p.id }) });
            ir(st.i + 1);
        } catch (e) { error(e.message); }
        finally { if ($('setup-seguir')) $('setup-seguir').disabled = false; }
    }

    async function guardarAjustes(valores) {
        // Directo con fetch: si algo no valida, el servidor devuelve el error de cada campo
        const res = await fetch('/config/ajustes', { method: 'PUT', body: JSON.stringify(valores), headers: {
            'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Accept-Language': I18N.codigo } });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const d = data.detail;
            throw new Error(d?.errores ? Object.values(d.errores).join(' · ') : (d?.mensaje || d || I18N.t('No se pudo guardar.')));
        }
        st.ajustes = Object.fromEntries(data.map(a => [a.clave, a]));
    }
    const aj = clave => st.ajustes[clave]?.valor;
    const opcionesDe = clave => st.ajustes[clave]?.opciones || {};

    async function terminar() {
        await api.request('setup', { method: 'PUT', body: JSON.stringify({ terminado: true }) });
        cerrar();
        toast.success(I18N.t('¡Listo! El taller quedó configurado.'));
        if (typeof Barra !== 'undefined') Barra.marca?.();
        ui.initDashboard();
    }

    // ── Pantallas ────────────────────────────────────────────────────────────
    const PANTALLAS = {
        taller() {
            encabezado('Tu taller', 'Cómo se llama y cómo contactarlo. Sale en la barra, en la pantalla de ingreso, en los documentos y en los mails.');
            const logo = typeof Barra !== 'undefined' ? Barra.datosMarca()?.logo : null;
            $('setup-cuerpo').innerHTML = tarjeta(`
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    <div class="space-y-4">
                        ${campo('su-nombre', 'Nombre del taller', input('su-nombre', aj('empresa_nombre') === 'GEZARMA' ? '' : aj('empresa_nombre'), `maxlength="80" placeholder="${t('Ej.: Servicio Técnico Norte')}"`))}
                        ${campo('su-datos', 'Datos de contacto para los documentos', `<textarea id="su-datos" rows="4" maxlength="500" placeholder="${t('Dirección\nTeléfono\nMail\nCUIT')}" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">${esc(aj('empresa_datos') || '')}</textarea>`, { ayuda: 'Una línea por dato.', opcional: true })}
                        ${campo('su-idioma', 'Idioma predeterminado', select('su-idioma', opcionesDe('idioma_predeterminado'), aj('idioma_predeterminado')), { ayuda: 'Para los mails y documentos de quien no eligió idioma.' })}
                    </div>
                    <div>
                        <p class="block text-sm font-semibold text-gray-700 mb-1">${t('Logo')} <span class="font-normal text-gray-400">${t('(opcional)')}</span></p>
                        <div class="flex items-center gap-3 mb-4">
                            <div id="su-logo-prev" class="w-16 h-16 rounded-xl border border-gray-200 bg-gray-50 flex items-center justify-center overflow-hidden text-gray-300 shrink-0">${logo ? `<img src="/config/logo?v=${logo}" alt="" class="w-full h-full object-contain">` : icono('imagen', 'w-7 h-7')}</div>
                            <label class="cursor-pointer border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 px-3 py-1.5 rounded-lg text-sm font-semibold">${icono('subir', 'w-4 h-4 mr-1.5')}${t('Subir logo')}
                                <input type="file" id="su-logo" accept="image/png,image/jpeg,image/webp" class="sr-only"></label>
                        </div>
                        <p class="text-xs font-semibold text-gray-500 mb-1">${t('Así se ve en la orden de ingreso')}</p>
                        <div class="border border-gray-200 rounded-lg p-4 bg-white shadow-sm text-[11px] leading-snug">
                            <div class="flex items-start gap-3 border-b pb-2 mb-2">
                                <div id="su-prev-logo" class="w-10 h-10 shrink-0 flex items-center justify-center text-gray-300">${logo ? `<img src="/config/logo?v=${logo}" alt="" class="max-w-full max-h-full object-contain">` : ''}</div>
                                <div class="min-w-0"><p id="su-prev-nombre" class="font-bold text-sm text-gray-900 truncate"></p><p id="su-prev-datos" class="text-gray-500 whitespace-pre-line"></p></div>
                                <p class="ml-auto font-bold text-gray-800 whitespace-nowrap">${t('Orden de ingreso')}</p>
                            </div>
                            <p class="text-gray-400">RMA-2026-AD0001 · ${t('Equipo de prueba')}</p>
                        </div>
                    </div>
                </div>`);
            const prev = () => {
                $('su-prev-nombre').textContent = $('su-nombre').value.trim() || 'GEZARMA';
                $('su-prev-datos').textContent = $('su-datos').value.trim();
            };
            $('su-nombre').addEventListener('input', prev);
            $('su-datos').addEventListener('input', prev);
            $('su-logo').addEventListener('change', e => subirLogo(e.target.files[0]));
            prev();
            $('su-nombre').focus();
        },

        cuenta() {
            encabezado('Tu cuenta', 'Tu nombre y tu mail como administrador. Si todavía usás la clave inicial, cambiala acá.');
            const u = auth.getUser();
            $('setup-cuerpo').innerHTML = tarjeta(`<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    ${campo('su-yo-nombre', 'Tu nombre', input('su-yo-nombre', u?.nombre || '', 'maxlength="80"'))}
                    ${campo('su-yo-email', 'Tu mail', input('su-yo-email', st._email || '', 'type="email" maxlength="120"'), { ayuda: 'Para los avisos de stock bajo, SLA y reingresos.' })}
                </div>`) + tarjeta(`
                <p class="text-sm font-semibold text-gray-800 mb-3">${t('Cambiar la clave')} <span class="font-normal text-gray-400">${t('(opcional)')}</span></p>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    ${campo('su-clave-actual', 'Clave actual', input('su-clave-actual', '', 'type="password" autocomplete="current-password"'))}
                    ${campo('su-clave-nueva', 'Clave nueva', input('su-clave-nueva', '', 'type="password" autocomplete="new-password" minlength="6"'), { ayuda: 'Al menos 6 caracteres.' })}
                    ${campo('su-clave-otra', 'Repetila', input('su-clave-otra', '', 'type="password" autocomplete="new-password"'))}
                </div>`);
            api.request('users/').then(us => {
                const yo = us.find(x => x.id === u?.user_id);
                if (yo && $('su-yo-email') && !$('su-yo-email').value) { st._email = yo.email || ''; $('su-yo-email').value = st._email; }
            }).catch(() => {});
        },

        async rubro() {
            encabezado('Qué reparás', 'Elegí uno o varios. Se suman los estados, el checklist de ingreso, las categorías y las plantillas de diagnóstico típicas. Después lo podés cambiar todo.');
            const cuerpo = $('setup-cuerpo');
            if (!st.rubros) {
                cuerpo.innerHTML = `<p class="text-sm text-gray-400">${t('Cargando...')}</p>`;
                try { st.rubros = await api.request('setup/rubros'); } catch (e) { error(e.message); return; }
                if (PASOS[st.i].id !== 'rubro') return;
            }
            const ej = st.estado.ejemplos_de_fabrica || {};
            cuerpo.innerHTML = `
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" role="group" aria-label="${t('Tipos de taller')}">
                    ${st.rubros.map(r => `
                    <label class="relative flex sm:flex-col items-center sm:items-start gap-3 sm:gap-2 bg-white border-2 rounded-xl p-3 sm:p-4 cursor-pointer transition hover:border-blue-300 has-[:checked]:border-blue-600 has-[:checked]:bg-blue-50/50 border-gray-200">
                        <input type="checkbox" data-rubro="${r.id}" ${st.elegidos.has(r.id) ? 'checked' : ''} class="absolute top-3 right-3 w-4 h-4 accent-blue-600">
                        <span class="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">${icono(r.icono, 'w-5 h-5')}</span>
                        <span class="min-w-0 pr-6"><span class="block font-semibold text-gray-900">${t(r.nombre)}</span>
                            <span class="block text-xs text-gray-500 mt-0.5 sm:mt-1">${t(r.descripcion)}</span></span>
                    </label>`).join('')}
                </div>
                <div id="su-rubro-resumen"></div>
                ${ej.productos || ej.repuestos ? interruptor('su-quitar-ej', 'Quitar los productos y repuestos de ejemplo que vienen instalados', st.quitarEjemplos,
                    'Los 3 productos (ASUS, Logitech, Samsung) y los 2 repuestos que trae el sistema. Solo se quitan si no se usaron.') : ''}`;
            cuerpo.addEventListener('change', e => {
                if (e.target.matches('[data-rubro]')) {
                    e.target.checked ? st.elegidos.add(e.target.dataset.rubro) : st.elegidos.delete(e.target.dataset.rubro);
                    resumenRubros();
                }
                if (e.target.id === 'su-quitar-ej') st.quitarEjemplos = e.target.checked;
            });
            resumenRubros();
        },

        async equipo() {
            encabezado('Tu equipo', 'Cada técnico tiene su usuario: ve los tickets, carga horas y recibe los que le asignás. Podés sumar más después desde Administración → Usuarios.');
            $('setup-cuerpo').innerHTML = `
                <div id="su-tecnicos"></div>
                ${tarjeta(`<p class="text-sm font-semibold text-gray-800 mb-3">${t('Sumar un técnico')}</p>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        ${campo('su-tec-nombre', 'Nombre y apellido', input('su-tec-nombre', '', 'maxlength="80"'))}
                        ${campo('su-tec-email', 'Mail', input('su-tec-email', '', 'type="email" maxlength="120"'))}
                        ${campo('su-tec-usuario', 'Usuario para entrar', input('su-tec-usuario', '', 'maxlength="40" autocapitalize="none" spellcheck="false"'))}
                        ${campo('su-tec-clave', 'Clave temporal', `<div class="flex gap-2">${input('su-tec-clave', '', 'maxlength="40" spellcheck="false"')}
                            <button type="button" id="su-tec-generar" class="shrink-0 px-3 py-2 border border-gray-300 rounded-lg text-sm font-semibold hover:bg-gray-50">${t('Generar')}</button></div>`,
                            { ayuda: 'Pasásela al técnico; la cambia al entrar por primera vez.' })}
                    </div>
                    <div class="mt-4 flex justify-end"><button type="button" id="su-tec-agregar" class="px-4 py-2 bg-white border border-blue-300 text-blue-700 hover:bg-blue-50 rounded-lg text-sm font-semibold">${icono('mas', 'w-4 h-4 mr-1')}${t('Agregar técnico')}</button></div>`)}`;
            $('su-tec-nombre').addEventListener('input', () => {
                if ($('su-tec-usuario').dataset.tocado) return;
                $('su-tec-usuario').value = $('su-tec-nombre').value.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
                    .split(/\s+/).filter(Boolean).slice(0, 2).join('.').replace(/[^a-z0-9._-]/g, '');
            });
            $('su-tec-usuario').addEventListener('input', e => { e.target.dataset.tocado = '1'; });
            $('su-tec-generar').addEventListener('click', () => { $('su-tec-clave').value = claveTemporal(); });
            $('su-tec-agregar').addEventListener('click', agregarTecnico);
            pintarTecnicos();
        },

        async catalogo() {
            encabezado('Catálogo y lugares', 'Los productos que reparás, los repuestos que tenés y dónde guardás cada cosa. Todo se puede cargar después; acá van los atajos.');
            let ubic = [];
            try { ubic = (await api.request('ubicaciones')).filter(u => u.tipo !== 'externa'); } catch { /* sin ubicaciones */ }
            if (PASOS[st.i].id !== 'catalogo') return;
            const d = st.estado.demo;
            $('setup-cuerpo').innerHTML = `
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    ${tarjeta(`<div class="flex items-start gap-3"><span class="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">${icono('subir', 'w-5 h-5')}</span>
                        <div class="min-w-0"><p class="font-semibold text-gray-900">${t('Importar desde Excel')}</p>
                        <p class="text-sm text-gray-500 mb-3">${t('Bajá la plantilla, completala y subila. Se revisa antes de guardar.')}</p>
                        <div class="flex flex-wrap gap-2">
                            <button type="button" data-importar="productos" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm font-semibold hover:bg-gray-50">${t('Productos')}</button>
                            <button type="button" data-importar="repuestos" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm font-semibold hover:bg-gray-50">${t('Repuestos')}</button>
                        </div></div></div>`)}
                    ${tarjeta(`<div class="flex items-start gap-3"><span class="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">${icono('pin', 'w-5 h-5')}</span>
                        <div class="min-w-0 flex-1"><p class="font-semibold text-gray-900">${t('Dónde guardás las cosas')}</p>
                        ${ubic.length ? `<p class="text-sm text-gray-500 mb-2">${t(ubic.length === 1 ? 'Ya tenés 1 ubicación.' : 'Ya tenés {0} ubicaciones.', ubic.length)}</p>` : `<p class="text-sm text-gray-500 mb-2">${t('Un depósito y sus estantes, para saber dónde está cada equipo.')}</p>`}
                        <div class="grid grid-cols-1 gap-2">
                            ${input('su-ub-lugar', '', `maxlength="60" placeholder="${t('Ej.: Depósito')}" aria-label="${t('Lugar')}"`)}
                            ${input('su-ub-estantes', '', `maxlength="120" placeholder="${t('Estantes: A, B, C')}" aria-label="${t('Estantes')}"`)}
                        </div>
                        <button type="button" id="su-ub-crear" class="mt-2 px-3 py-1.5 border border-blue-300 text-blue-700 rounded-lg text-sm font-semibold hover:bg-blue-50">${t('Crear')}</button>
                        </div></div>`)}
                </div>
                ${d.puede_crear || d.puede_borrar ? tarjeta(`<div class="flex flex-wrap items-center gap-3">
                    <span class="w-10 h-10 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">${icono('play', 'w-5 h-5')}</span>
                    <div class="flex-1 min-w-[14rem]"><p class="font-semibold text-gray-900">${t('Probar con datos de ejemplo')}</p>
                        <p class="text-sm text-gray-500">${d.puede_borrar
                            ? t('Hay {0} tickets de ejemplo cargados. Cuando quieras empezar en serio, borralos: se van solo los de ejemplo.', d.tickets)
                            : t('Carga clientes, equipos y tickets ficticios en distintos estados para ver cómo funciona todo. Se borran todos juntos con un botón.')}</p></div>
                    ${d.puede_borrar ? `<button type="button" id="su-demo-borrar" class="px-4 py-2 border border-red-200 text-red-700 rounded-lg text-sm font-semibold hover:bg-red-50">${icono('papelera', 'w-4 h-4 mr-1')}${t('Borrar datos de ejemplo')}</button>`
                                     : `<button type="button" id="su-demo-crear" class="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-semibold">${t('Cargar datos de ejemplo')}</button>`}
                </div>`) : ''}`;
            $('setup-cuerpo').querySelectorAll('[data-importar]').forEach(b => b.addEventListener('click', () => Importar.abrir(b.dataset.importar, () => {})));
            $('su-ub-crear').addEventListener('click', crearUbicaciones);
            $('su-demo-crear')?.addEventListener('click', crearDemo);
            $('su-demo-borrar')?.addEventListener('click', borrarDemo);
        },

        impresion() {
            encabezado('Impresión', 'La etiqueta va pegada en el equipo (con QR y código de barras) y el comprobante se le da al cliente. Si no tenés impresora térmica, se imprime en A4.');
            const sugerida = st.estado.etiqueta_sugerida;
            const tam = aj('etiqueta_tamano') === '62x29' && sugerida ? sugerida : aj('etiqueta_tamano');
            $('setup-cuerpo').innerHTML = tarjeta(`
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    ${campo('su-etq', 'Tamaño de la etiqueta', select('su-etq', opcionesDe('etiqueta_tamano'), tam),
                        { ayuda: sugerida && sugerida !== '62x29' ? 'Sugerido para tu rubro: 50 × 25 mm (entra en una bolsita o en la bandeja).' : '' })}
                    ${campo('su-dpi', 'Resolución de la impresora de etiquetas', select('su-dpi', opcionesDe('etiqueta_dpi'), aj('etiqueta_dpi')), { ayuda: 'Está en la hoja de datos de la impresora.' })}
                    ${campo('su-tk', 'Ancho del rollo de la ticketera', select('su-tk', opcionesDe('ticketera_ancho'), aj('ticketera_ancho')))}
                    ${campo('su-pdf', 'Cómo se generan los documentos', select('su-pdf', opcionesDe('pdf_modo'), aj('pdf_modo')))}
                </div>`) + tarjeta(`<div class="flex flex-wrap items-center gap-3">
                    <p class="flex-1 min-w-[14rem] text-sm text-gray-600">${t('Guardá y probá: revisá que entre en la etiqueta y que el celular lea el QR.')}</p>
                    <button type="button" data-prueba="etiqueta" class="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold hover:bg-gray-50">${icono('impresora', 'w-4 h-4 mr-1')}${t('Etiqueta de prueba')}</button>
                    <button type="button" data-prueba="ticket_ingreso" class="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold hover:bg-gray-50">${icono('recibo', 'w-4 h-4 mr-1')}${t('Comprobante de prueba')}</button>
                </div>`);
            $('setup-cuerpo').querySelectorAll('[data-prueba]').forEach(b => b.addEventListener('click', async () => {
                try { await GUARDAR.impresion(); } catch (e) { error(e.message); return; }
                Documentos.abrirUrl(`/tickets/impresion-prueba/${b.dataset.prueba}`);
            }));
        },

        avisos() {
            encabezado('Avisos y clientes', 'Los mails al cliente (cambios de estado, presupuestos, listo para retirar) y lo que puede hacer sin ser del taller.');
            const panel = aj('smtp_origen') === 'panel';
            $('setup-cuerpo').innerHTML = tarjeta(`
                ${interruptor('su-mail-on', 'Enviar notificaciones por email', aj('email_activo'), 'Necesita una cuenta de correo que permita enviar por SMTP (Gmail con contraseña de aplicación, Zoho, el hosting del dominio…).')}
                <div id="su-mail-datos" class="${aj('email_activo') ? '' : 'hidden'} mt-4 space-y-4">
                    ${campo('su-smtp-origen', 'De dónde se toma la configuración SMTP', select('su-smtp-origen', opcionesDe('smtp_origen'), aj('smtp_origen')))}
                    <div id="su-smtp" class="${panel ? '' : 'hidden'} grid grid-cols-1 sm:grid-cols-2 gap-4">
                        ${campo('su-smtp-host', 'Servidor SMTP', input('su-smtp-host', aj('smtp_host'), 'placeholder="smtp.gmail.com" spellcheck="false"'))}
                        ${campo('su-smtp-port', 'Puerto', input('su-smtp-port', aj('smtp_port'), 'type="number" min="1" max="65535"'))}
                        ${campo('su-smtp-seg', 'Seguridad', select('su-smtp-seg', opcionesDe('smtp_seguridad'), aj('smtp_seguridad')))}
                        ${campo('su-smtp-user', 'Usuario', input('su-smtp-user', aj('smtp_usuario'), 'spellcheck="false" autocomplete="off"'))}
                        ${campo('su-smtp-pass', 'Contraseña', input('su-smtp-pass', '', `type="password" autocomplete="new-password" placeholder="${st.ajustes.smtp_password?.cargado ? '••••••••' : ''}"`), { ayuda: st.ajustes.smtp_password?.cargado ? 'Ya hay una cargada; dejalo vacío para no cambiarla.' : '' })}
                        ${campo('su-smtp-from', 'Remitente (From)', input('su-smtp-from', aj('smtp_remitente'), 'spellcheck="false" placeholder="Taller <avisos@tutaller.com>"'))}
                    </div>
                    <div class="flex flex-wrap items-end gap-2">
                        <div class="flex-1 min-w-[14rem]">${campo('su-mail-prueba', 'Mandar un mail de prueba a', input('su-mail-prueba', st._email || '', 'type="email"'))}</div>
                        <button type="button" id="su-mail-probar" class="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold hover:bg-gray-50">${icono('enviar', 'w-4 h-4 mr-1')}${t('Probar')}</button>
                    </div>
                </div>`) + tarjeta(`<div class="space-y-3">
                    ${interruptor('su-seguimiento', 'Seguimiento público de reparaciones', aj('seguimiento_publico'), 'El cliente consulta el estado con el N° de RMA y el de serie, sin cuenta (el QR del comprobante lleva ahí).')}
                    ${interruptor('su-registro', 'Los clientes pueden crearse una cuenta', aj('registro_publico'), 'Si lo desactivás, las cuentas las crea el taller (por ejemplo, en el ingreso en mostrador).')}
                </div>`);
            $('su-mail-on').addEventListener('change', e => $('su-mail-datos').classList.toggle('hidden', !e.target.checked));
            $('su-smtp-origen').addEventListener('change', e => $('su-smtp').classList.toggle('hidden', e.target.value !== 'panel'));
            $('su-mail-probar').addEventListener('click', async () => {
                error('');
                try {
                    await GUARDAR.avisos();
                    await api.request('config/email/prueba', { method: 'POST', body: JSON.stringify({ destino: $('su-mail-prueba').value.trim() }) });
                    toast.success(I18N.t('Mail de prueba enviado. Revisá la bandeja (y el spam).'));
                } catch (e) { error(e.message); }
            });
        },

        listo() {
            encabezado('Listo', 'Esto quedó configurado. Lo salteado lo podés hacer después: queda en la guía del panel.');
            const hechos = new Set(st.estado.pasos);
            $('setup-cuerpo').innerHTML = tarjeta(`<ul class="divide-y">${PASOS.filter(p => p.id !== 'listo').map((p, i) => `
                <li class="py-3 flex items-center gap-3">
                    <span class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${hechos.has(p.id) ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-400'}">${icono(hechos.has(p.id) ? 'check' : p.icono, 'w-4 h-4')}</span>
                    <span class="flex-1 text-sm ${hechos.has(p.id) ? 'text-gray-800 font-medium' : 'text-gray-500'}">${t(p.titulo)}</span>
                    ${hechos.has(p.id) ? `<span class="text-xs font-semibold text-emerald-700">${t('Hecho')}</span>`
                        : `<button type="button" data-volver="${i}" class="text-sm font-semibold text-blue-600 hover:text-blue-800">${t('Hacerlo ahora')}</button>`}
                </li>`).join('')}</ul>`) + tarjeta(`<p class="text-sm font-semibold text-gray-800 mb-2">${t('Para arrancar')}</p>
                <ul class="text-sm text-gray-600 space-y-1.5 list-disc pl-5">
                    <li>${t('Registrá el primer equipo con «Ingreso en mostrador» (atajo G M).')}</li>
                    <li>${t('Imprimí la etiqueta y pegala en el equipo: escaneándola se abre el ticket.')}</li>
                    <li>${t('Todo esto se cambia después en Administración → Ajustes.')}</li>
                </ul>`);
            $('setup-cuerpo').querySelectorAll('[data-volver]').forEach(b => b.addEventListener('click', () => ir(Number(b.dataset.volver))));
        },
    };

    // ── Guardar cada paso ────────────────────────────────────────────────────
    const GUARDAR = {
        async taller() {
            const nombre = $('su-nombre').value.trim();
            if (!nombre) { error(I18N.t('Poné el nombre del taller.')); $('su-nombre').focus(); return false; }
            await guardarAjustes({ empresa_nombre: nombre, empresa_datos: $('su-datos').value.trim(), idioma_predeterminado: $('su-idioma').value });
            if (typeof Barra !== 'undefined') Barra.marca?.();
        },
        async cuenta() {
            const u = auth.getUser();
            const nombre = $('su-yo-nombre').value.trim(), email = $('su-yo-email').value.trim();
            if (!nombre) { error(I18N.t('Poné tu nombre.')); return false; }
            await api.request(`users/${u.user_id}/profile`, { method: 'PATCH', body: JSON.stringify({ nombre, email: email || null }) });
            st._email = email;
            const info = { ...u, nombre };
            localStorage.setItem('user_info', JSON.stringify(info));
            const actual = $('su-clave-actual').value, nueva = $('su-clave-nueva').value, otra = $('su-clave-otra').value;
            if (actual || nueva || otra) {
                if (nueva !== otra) { error(I18N.t('Las dos claves nuevas no coinciden.')); $('su-clave-otra').focus(); return false; }
                const r = await api.changePassword(actual, nueva);
                if (r.access_token) localStorage.setItem('token', r.access_token);
                toast.success(I18N.t('Clave cambiada.'));
            }
            const nom = document.getElementById('user-nombre-barra');
            if (nom) nom.textContent = nombre;
        },
        async rubro() {
            if (!st.elegidos.size) { error(I18N.t('Elegí al menos un tipo de taller (o salteá este paso).')); return false; }
            const orden = (st.rubros || []).map(r => r.id).filter(id => st.elegidos.has(id));
            const r = await api.request('setup/rubros', { method: 'POST', body: JSON.stringify({ rubros: orden, quitar_ejemplos: !!$('su-quitar-ej')?.checked }) });
            const partes = [];
            if (r.estados.length) partes.push(I18N.t('estados: {0}', r.estados.map(e => I18N.t(e)).join(', ')));
            if (r.plantillas_agregadas) partes.push(I18N.t('{0} plantillas de diagnóstico', r.plantillas_agregadas));
            if (r.controles) partes.push(I18N.t('{0} preguntas en el checklist', r.controles));
            toast.success(partes.length ? I18N.t('Se agregaron {0}.', partes.join(' · ')) : I18N.t('Listo: ya estaba todo.'));
            st.estado.etiqueta_sugerida = r.etiqueta_sugerida;
            const lista = await api.request('config/ajustes');
            st.ajustes = Object.fromEntries(lista.map(a => [a.clave, a]));
        },
        async impresion() {
            await guardarAjustes({ etiqueta_tamano: $('su-etq').value, etiqueta_dpi: $('su-dpi').value,
                                   ticketera_ancho: $('su-tk').value, pdf_modo: $('su-pdf').value });
        },
        async avisos() {
            const v = { email_activo: $('su-mail-on').checked, seguimiento_publico: $('su-seguimiento').checked,
                        registro_publico: $('su-registro').checked, smtp_origen: $('su-smtp-origen').value };
            if (v.smtp_origen === 'panel') {
                Object.assign(v, { smtp_host: $('su-smtp-host').value.trim(), smtp_port: $('su-smtp-port').value || 587,
                                   smtp_seguridad: $('su-smtp-seg').value, smtp_usuario: $('su-smtp-user').value.trim(),
                                   smtp_remitente: $('su-smtp-from').value.trim() });
                if ($('su-smtp-pass').value) v.smtp_password = $('su-smtp-pass').value;
            }
            await guardarAjustes(v);
        },
    };

    // ── Ayudantes de cada paso ───────────────────────────────────────────────
    async function subirLogo(archivo) {
        if (!archivo) return;
        if (archivo.size > 2 * 1024 * 1024) { toast.error(I18N.t('El logo puede pesar hasta 2 MB.')); return; }
        const form = new FormData();
        form.append('archivo', archivo);
        const res = await fetch('/config/logo', { method: 'PUT', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }, body: form });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { toast.error(data.detail || I18N.t('No se pudo subir el logo.')); return; }

        const img = `<img src="/config/logo?v=${data.logo}" alt="" class="w-full h-full object-contain">`;
        if ($('su-logo-prev')) $('su-logo-prev').innerHTML = img;
        if ($('su-prev-logo')) $('su-prev-logo').innerHTML = img;
        if (typeof Barra !== 'undefined') Barra.marca?.();
    }

    function resumenRubros() {
        const cont = $('su-rubro-resumen');
        if (!cont) return;
        const elegidos = (st.rubros || []).filter(r => st.elegidos.has(r.id));
        if (!elegidos.length) { cont.innerHTML = ''; return; }
        const unir = campo => [...new Set(elegidos.flatMap(r => r[campo]))];
        const plazo = k => Math.max(...elegidos.map(r => r.sla[k]));
        const fila = (titulo, items) => items.length ? `<div><dt class="text-xs font-semibold text-gray-500">${t(titulo)}</dt>
            <dd class="mt-1 flex flex-wrap gap-1.5">${items.map(x => `<span class="text-xs bg-gray-100 text-gray-700 rounded-full px-2 py-0.5">${t(x)}</span>`).join('')}</dd></div>` : '';
        cont.innerHTML = tarjeta(`<p class="text-sm font-semibold text-gray-800 mb-3">${t('Qué se agrega')}</p>
            <dl class="space-y-3">
                ${fila('Estados', unir('estados'))}
                ${fila('Accesorios del checklist', unir('accesorios'))}
                ${fila('Preguntas del checklist', unir('controles'))}
                ${fila('Categorías de productos', unir('categorias'))}
                ${fila('Plantillas de diagnóstico', unir('plantillas'))}
                <div><dt class="text-xs font-semibold text-gray-500">${t('Plazos (SLA)')}</dt>
                    <dd class="text-sm text-gray-700 mt-1">${t('Revisar un ticket nuevo: {0} h · Diagnosticar: {1} h · Reparar: {2} días', plazo('horas_nuevo'), plazo('horas_diagnostico'), plazo('dias_reparacion'))}</dd></div>
            </dl>`);
    }

    function claveTemporal() {
        const letras = 'abcdefghjkmnpqrstuvwxyz', nums = '23456789';
        const r = n => crypto.getRandomValues(new Uint32Array(1))[0] % n;
        let s = '';
        for (let i = 0; i < 6; i++) s += letras[r(letras.length)];
        return s.charAt(0).toUpperCase() + s.slice(1) + '-' + nums[r(nums.length)] + nums[r(nums.length)];
    }

    async function pintarTecnicos() {
        const cont = $('su-tecnicos');
        if (!cont) return;
        let tecs = [];
        try { tecs = (await api.request('users/')).filter(u => u.rol === 'tecnico' && u.activo !== false); } catch { /* sin datos */ }
        if (!$('su-tecnicos')) return;
        cont.innerHTML = tecs.length ? tarjeta(`<p class="text-sm font-semibold text-gray-800 mb-2">${t(tecs.length === 1 ? '1 técnico' : '{0} técnicos', tecs.length)}</p>
            <ul class="divide-y">${tecs.map(u => `<li class="py-2 flex items-center gap-3 text-sm">
                <span class="w-8 h-8 rounded-full bg-blue-50 text-blue-700 flex items-center justify-center text-xs font-bold shrink-0">${esc((u.nombre || '?').split(/\s+/).map(x => x[0]).slice(0, 2).join('').toUpperCase())}</span>
                <span class="flex-1 min-w-0"><span class="block font-medium text-gray-800 truncate">${esc(u.nombre)}</span><span class="block text-xs text-gray-400" translate="no">${esc(u.username)}</span></span></li>`).join('')}</ul>`) : '';
    }

    async function agregarTecnico() {
        error('');
        const nombre = $('su-tec-nombre').value.trim(), email = $('su-tec-email').value.trim(),
              usuario = $('su-tec-usuario').value.trim(), clave = $('su-tec-clave').value;
        if (!nombre || !email || !usuario) { error(I18N.t('Completá nombre, mail y usuario.')); return; }
        if (clave.length < 6) { error(I18N.t('La clave temporal tiene que tener al menos 6 caracteres.')); $('su-tec-clave').focus(); return; }
        try {
            await api.request('register', { method: 'POST', body: JSON.stringify({ nombre, email, username: usuario, password: clave,
                                                                                    rol: 'tecnico', cambiar_clave: true }) });
            toast.success(I18N.t('Técnico agregado: {0} (usuario {1}).', nombre, usuario));
            ['su-tec-nombre', 'su-tec-email', 'su-tec-usuario', 'su-tec-clave'].forEach(id => { $(id).value = ''; });
            delete $('su-tec-usuario').dataset.tocado;
            pintarTecnicos();
        } catch (e) { error(e.message); }
    }

    async function crearUbicaciones() {
        error('');
        const lugar = $('su-ub-lugar').value.trim();
        const estantes = $('su-ub-estantes').value.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);
        if (!lugar) { error(I18N.t('Poné el nombre del lugar (por ejemplo, Depósito).')); $('su-ub-lugar').focus(); return; }
        try {
            const dep = await api.request('ubicaciones', { method: 'POST', body: JSON.stringify({ nombre: lugar }) });
            for (const e of estantes) {
                const nombre = /^[A-Z0-9]{1,3}$/i.test(e) ? `${I18N.t('Estante')} ${e.toUpperCase()}` : e;
                await api.request('ubicaciones', { method: 'POST', body: JSON.stringify({ nombre, padre_id: dep.id }) });
            }
            if (typeof Ubic !== 'undefined') Ubic.invalidar();
            toast.success(estantes.length ? I18N.t('Creado: {0} con {1} lugares adentro.', lugar, estantes.length) : I18N.t('Creado: {0}.', lugar));
            PANTALLAS.catalogo();
        } catch (e) { error(e.message); }
    }

    async function crearDemo() {
        const b = $('su-demo-crear');
        b.disabled = true;
        try {
            const r = await api.request('setup/demo', { method: 'POST' });
            st.estado = await api.request('setup');
            toast.success(I18N.t('Se cargaron {0} tickets de ejemplo.', r.tickets));
            PANTALLAS.catalogo();
        } catch (e) { error(e.message); b.disabled = false; }
    }

    async function borrarDemo() {
        if (!await confirmDialog(I18N.t('¿Borrar los datos de ejemplo?'),
            I18N.t('Se borran los tickets, clientes, productos, repuestos y ubicaciones de ejemplo. Lo que hayas cargado vos no se toca.'),
            I18N.t('Borrar'), { peligro: true })) return;
        try {
            const r = await api.request('setup/demo', { method: 'DELETE' });
            st.estado = await api.request('setup');
            const c = r.conservados, quedan = c.productos + c.repuestos + c.ubicaciones + c.clientes;
            toast.success(quedan ? I18N.t('Datos de ejemplo borrados. Quedaron {0} que ya usaste en algo real.', quedan) : I18N.t('Datos de ejemplo borrados.'));
            if (PASOS[st.i].id === 'catalogo') PANTALLAS.catalogo();
        } catch (e) { error(e.message); }
    }

    return { revisar, abrir, cerrar, borrarDemo };
})();
window.Setup = Setup;
