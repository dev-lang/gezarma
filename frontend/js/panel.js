/**
 * panel.js — Panel de control a gusto de cada usuario: orden de los bloques, ancho
 * (completo, mitad o cuarto) y cuáles se ocultan.
 *
 * - Cada bloque del partial dashboard.html tiene data-bloque="id". Cada módulo sigue
 *   decidiendo si su bloque tiene algo para mostrar (clase hidden); esto es otra capa:
 *   .panel-oculto lo oculta el usuario y [data-sin-permiso] lo oculta el rol.
 * - "Personalizar": barrita en cada bloque con manija para arrastrar, flechas, ancho y
 *   ojo. Listo guarda (por usuario, en el servidor), Cancelar vuelve a como estaba,
 *   Restablecer vuelve al del equipo o al de fábrica. El administrador puede usar el
 *   suyo como predeterminado del equipo (para quien no armó el propio).
 * Ver services/panel.py.
 */
const Panel = (() => {
    const $ = id => document.getElementById(id);
    const t = (s, ...a) => esc(I18N.t(s, ...a));
    const ADMIN = ['administrador'], TALLER = ['administrador', 'tecnico'], TODOS = ['administrador', 'tecnico', 'cliente'];
    // El orden de fábrica
    const BLOQUES = [
        { id: 'guia',              titulo: 'Guía para dejar el sistema listo', roles: ADMIN,  ancho: 'completo' },
        { id: 'resumen',           titulo: 'Resumen',                          roles: TODOS,  ancho: 'completo' },
        { id: 'grafico_estados',   titulo: 'Tickets por estado',               roles: ADMIN,  ancho: 'cuarto' },
        { id: 'grafico_productos', titulo: 'Fallas por producto',              roles: ADMIN,  ancho: 'cuarto' },
        { id: 'grafico_tecnicos',  titulo: 'Carga por técnico',                roles: ADMIN,  ancho: 'cuarto' },
        { id: 'tiempo_promedio',   titulo: 'Tiempo promedio de reparación',    roles: ADMIN,  ancho: 'cuarto' },
        { id: 'para_hoy',          titulo: 'Para hoy',                         roles: TALLER, ancho: 'completo' },
        { id: 'alertas',           titulo: 'Alertas del taller',               roles: TALLER, ancho: 'completo' },
        { id: 'portal',            titulo: 'Mis equipos',                      roles: ['cliente'], ancho: 'completo' },
        { id: 'satisfaccion',      titulo: 'Satisfacción de los clientes',     roles: TALLER, ancho: 'completo' },
        { id: 'horas',             titulo: 'Horas por técnico',                roles: ADMIN,  ancho: 'completo' },
        { id: 'tickets',           titulo: 'Tickets',                          roles: TODOS,  ancho: 'completo', fijo: true },
    ];
    const ANCHOS = { completo: 'Completo', mitad: 'Mitad', cuarto: 'Cuarto' };
    const SPAN = { completo: 'md:col-span-2 lg:col-span-4', mitad: 'md:col-span-1 lg:col-span-2', cuarto: 'md:col-span-1 lg:col-span-1' };
    const TODAS_SPAN = [...new Set(Object.values(SPAN).join(' ').split(' '))];
    let _cfg = null, _cfgDe = null;   // respuesta de GET users/me/panel y de qué usuario
    let _antes = null;        // disposición al entrar a Personalizar (para Cancelar)

    const rol = () => auth.getUser()?.role || '';
    const def = id => BLOQUES.find(b => b.id === id);
    const permitido = b => b.roles.includes(rol());
    const fabrica = () => BLOQUES.map(b => ({ id: b.id, visible: true, ancho: b.ancho }));

    /** La disposición a usar: la guardada, completando los bloques que falten en su lugar de fábrica. */
    function disposicion(guardada) {
        const lista = (guardada || fabrica()).filter(x => def(x.id)).map(x => ({ ...x }));
        BLOQUES.forEach((b, i) => {
            if (lista.some(x => x.id === b.id)) return;
            // después del bloque de fábrica anterior que esté en la lista
            let pos = 0;
            for (let j = i - 1; j >= 0; j--) {
                const k = lista.findIndex(x => x.id === BLOQUES[j].id);
                if (k >= 0) { pos = k + 1; break; }
            }
            lista.splice(pos, 0, { id: b.id, visible: true, ancho: b.ancho });
        });
        return lista;
    }

    async function config(forzar = false) {
        if (!_cfg || forzar || _cfgDe !== auth.getUser()?.user_id) {
            _cfgDe = auth.getUser()?.user_id;
            try { _cfg = await api.request('users/me/panel'); } catch { _cfg = { bloques: null, propio: false, equipo: null }; }
        }
        return _cfg;
    }

    function pintar(lista) {
        const cont = $('panel-bloques');
        if (!cont) return;
        lista.forEach(x => {
            const el = cont.querySelector(`:scope > [data-bloque="${x.id}"]`);
            if (!el) return;
            cont.appendChild(el);                                   // el orden
            el.classList.remove(...TODAS_SPAN);
            el.classList.add(...SPAN[x.ancho].split(' '));
            el.dataset.ancho = x.ancho;
            el.classList.toggle('panel-oculto', !x.visible && !def(x.id).fijo);
            if (permitido(def(x.id))) delete el.dataset.sinPermiso; else el.dataset.sinPermiso = '1';
        });
    }

    /** Lo llama ui.initDashboard apenas carga la pantalla. */
    async function aplicar() {
        const c = await config();
        pintar(disposicion(c.bloques));
        const b = $('panel-personalizar');
        if (b && !b.dataset.conectado) { b.dataset.conectado = '1'; b.addEventListener('click', editar); }
    }

    /** La disposición tal como está en pantalla. */
    function leer() {
        return [...$('panel-bloques').querySelectorAll(':scope > [data-bloque]')].map(el => ({
            id: el.dataset.bloque, visible: !el.classList.contains('panel-oculto'), ancho: el.dataset.ancho || def(el.dataset.bloque).ancho,
        }));
    }

    // ── Personalizar ─────────────────────────────────────────────────────────
    function editar() {
        const cont = $('panel-bloques');
        if (!cont || cont.classList.contains('panel-editando')) return;
        _antes = leer();
        cont.classList.add('panel-editando');
        $('panel-personalizar')?.classList.add('hidden');
        cont.querySelectorAll(':scope > [data-bloque]').forEach(el => {
            if (el.dataset.sinPermiso) return;
            const d = def(el.dataset.bloque);
            const barra = document.createElement('div');
            barra.className = 'panel-barra';
            barra.innerHTML = `
                <span class="panel-manija" draggable="true" title="${t('Arrastrar para mover')}" aria-hidden="true">${icono('arriba-abajo', 'w-4 h-4')}</span>
                <span class="panel-titulo flex-1 min-w-0 truncate font-semibold" title="${t(d.titulo)}">${t(d.titulo)}<span data-vacio class="font-normal text-gray-400"> · ${t('ahora sin datos')}</span></span>
                <select data-ancho aria-label="${t('Ancho de {0}', I18N.t(d.titulo))}" title="${t('Ancho')}" class="hidden md:block w-auto shrink-0 text-xs border border-gray-200 rounded-md pl-1.5 pr-6 py-1 bg-white">
                    ${Object.entries(ANCHOS).map(([v, txt]) => `<option value="${v}" ${el.dataset.ancho === v ? 'selected' : ''}>${t(txt)}</option>`).join('')}</select>
                <button type="button" data-mover="-1" class="panel-btn" aria-label="${t('Subir {0}', I18N.t(d.titulo))}" title="${t('Subir')}">${icono('arriba', 'w-4 h-4')}</button>
                <button type="button" data-mover="1" class="panel-btn" aria-label="${t('Bajar {0}', I18N.t(d.titulo))}" title="${t('Bajar')}">${icono('abajo', 'w-4 h-4')}</button>
                ${d.fijo ? `<span class="panel-btn opacity-30" title="${t('La lista de tickets no se puede ocultar')}">${icono('ojo', 'w-4 h-4')}</span>`
                         : `<button type="button" data-ojo class="panel-btn" aria-pressed="${!el.classList.contains('panel-oculto')}"></button>`}`;
            el.prepend(barra);
            pintarOjo(el);
        });
        const pie = document.createElement('div');
        pie.id = 'panel-pie';
        pie.className = 'fixed bottom-0 inset-x-0 z-[45] bg-white border-t shadow-2xl';
        const esAdmin = rol() === 'administrador';
        pie.innerHTML = `
            <div class="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center gap-2">
                <p class="hidden sm:block text-sm text-gray-500 mr-auto">${t('Arrastrá los bloques o usá las flechas. El ojo los oculta.')}</p>
                <button type="button" data-restablecer class="px-3 py-2 text-sm font-semibold text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100">${t('Restablecer')}</button>
                ${esAdmin ? `<button type="button" data-equipo class="px-3 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50 rounded-lg">${t('Usar como predeterminado del equipo')}</button>` : ''}
                <span class="flex-1 sm:hidden"></span>
                <button type="button" data-cancelar class="px-4 py-2 text-sm font-semibold border border-gray-300 rounded-lg hover:bg-gray-50">${t('Cancelar')}</button>
                <button type="button" data-listo class="px-5 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm">${t('Listo')}</button>
            </div>`;
        document.body.appendChild(pie);
        document.body.classList.add('panel-con-pie');
        cont.addEventListener('click', alClic);
        cont.addEventListener('change', alCambiar);
        conectarArrastre(cont);
        pie.addEventListener('click', alPie);
    }

    function pintarOjo(el) {
        const b = el.querySelector('[data-ojo]'), oculto = el.classList.contains('panel-oculto');
        if (!b) return;
        b.innerHTML = icono('ojo', 'w-4 h-4') + (oculto ? `<span class="text-xs font-semibold ml-1">${t('Mostrar')}</span>` : '');
        b.title = I18N.t(oculto ? 'Mostrar' : 'Ocultar');
        b.setAttribute('aria-label', I18N.t(oculto ? 'Mostrar {0}' : 'Ocultar {0}', I18N.t(def(el.dataset.bloque).titulo)));
        b.setAttribute('aria-pressed', String(!oculto));
        b.classList.toggle('text-blue-700', oculto);
    }

    function hermanosEditables(cont) {
        return [...cont.querySelectorAll(':scope > [data-bloque]')].filter(x => !x.dataset.sinPermiso);
    }

    function alClic(e) {
        const el = e.target.closest('[data-bloque]'), cont = $('panel-bloques');
        if (!el) return;
        const mover = e.target.closest('[data-mover]');
        if (mover) {
            const lista = hermanosEditables(cont), i = lista.indexOf(el), j = i + Number(mover.dataset.mover);
            if (j < 0 || j >= lista.length) return;
            if (Number(mover.dataset.mover) < 0) cont.insertBefore(el, lista[j]); else lista[j].after(el);
            mover.focus();
            el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            return;
        }
        if (e.target.closest('[data-ojo]')) { el.classList.toggle('panel-oculto'); pintarOjo(el); }
    }

    function alCambiar(e) {
        const sel = e.target.closest('[data-ancho]');
        if (!sel) return;
        const el = sel.closest('[data-bloque]');
        el.classList.remove(...TODAS_SPAN);
        el.classList.add(...SPAN[sel.value].split(' '));
        el.dataset.ancho = sel.value;
    }

    function conectarArrastre(cont) {
        if (cont.dataset.arrastre) return;          // una vez por pantalla (el panel se rearma al volver)
        cont.dataset.arrastre = '1';
        let arrastrado = null;
        cont.addEventListener('dragstart', e => {
            const m = e.target.closest?.('.panel-manija');
            if (!m) return;
            arrastrado = m.closest('[data-bloque]');
            arrastrado.classList.add('panel-arrastrando');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', arrastrado.dataset.bloque);
            try { e.dataTransfer.setDragImage(arrastrado, 20, 20); } catch { /* algunos navegadores no */ }
        });
        cont.addEventListener('dragover', e => {
            if (!arrastrado) return;
            const sobre = e.target.closest('[data-bloque]');
            if (!sobre || sobre === arrastrado || sobre.dataset.sinPermiso) return;
            e.preventDefault();
            const r = sobre.getBoundingClientRect();
            // En la misma fila (bloques angostos) decide la mitad horizontal; si no, la vertical
            const despues = r.width < cont.clientWidth * 0.75 ? e.clientX > r.left + r.width / 2 : e.clientY > r.top + r.height / 2;
            despues ? sobre.after(arrastrado) : sobre.before(arrastrado);
        });
        const fin = () => { arrastrado?.classList.remove('panel-arrastrando'); arrastrado = null; };
        cont.addEventListener('drop', e => { if (arrastrado) e.preventDefault(); fin(); });
        cont.addEventListener('dragend', fin);
    }

    function salir() {
        const cont = $('panel-bloques');
        cont?.classList.remove('panel-editando');
        cont?.querySelectorAll('.panel-barra').forEach(b => b.remove());
        cont?.removeEventListener('click', alClic);
        cont?.removeEventListener('change', alCambiar);
        $('panel-pie')?.remove();
        document.body.classList.remove('panel-con-pie');
        $('panel-personalizar')?.classList.remove('hidden');
    }

    async function alPie(e) {
        const b = e.target.closest('button');
        if (!b) return;
        try {
            if ('listo' in b.dataset) {
                const lista = leer();
                _cfg = await api.request('users/me/panel', { method: 'PUT', body: JSON.stringify({ bloques: lista }) });
                salir();
                toast.success(I18N.t('Panel guardado.'));
            } else if ('cancelar' in b.dataset) {
                salir();
                pintar(_antes);
            } else if ('restablecer' in b.dataset) {
                _cfg = await api.request('users/me/panel', { method: 'DELETE' });
                salir();
                pintar(disposicion(_cfg.bloques));
                toast.success(I18N.t(_cfg.equipo ? 'Volviste al panel del equipo.' : 'Volviste al panel de fábrica.'));
            } else if ('equipo' in b.dataset) {
                if (!await confirmDialog(I18N.t('¿Usar este panel como predeterminado?'),
                    I18N.t('Lo van a ver los usuarios que no armaron el suyo (por ejemplo, los técnicos nuevos). Cada uno lo puede cambiar después.'),
                    I18N.t('Usar este'), { peligro: false })) return;
                const lista = leer();
                await api.request('users/me/panel/equipo', { method: 'PUT', body: JSON.stringify({ bloques: lista }) });
                _cfg = await api.request('users/me/panel', { method: 'PUT', body: JSON.stringify({ bloques: lista }) });
                salir();
                toast.success(I18N.t('Listo: es el panel predeterminado del equipo.'));
            }
        } catch (err) { toast.error(err.message); }
    }

    // Escape sale sin guardar
    document.addEventListener('keydown', e => {
        const hayDialogo = [...document.querySelectorAll('[role=dialog]')].some(d => d.offsetParent !== null);
        if (e.key === 'Escape' && $('panel-pie') && !hayDialogo) {
            const b = $('panel-pie').querySelector('[data-cancelar]');
            b?.click();
        }
    });

    return { BLOQUES, aplicar, editar, invalidar: () => { _cfg = null; } };
})();
window.Panel = Panel;
