/**
 * navegacion.js — Llegar rápido a cada pantalla.
 *
 * - "Ir a…" (Ctrl + K, o Cmd + K en Mac, o el botón del buscador): busca pantallas, secciones
 *   de Administración y ajustes puntuales ("smtp", "etiqueta"); también abre un ticket por su RMA.
 *   Con la caja vacía muestra lo último que usaste. Solo lista lo que tu rol puede ver.
 * - Links directos: cada sección de Administración tiene su dirección (#admin=ubicaciones),
 *   para guardarla en favoritos; el botón Atrás del navegador vuelve a la anterior.
 * - Recientes: las 3 secciones de Administración más usadas, en el menú de usuario.
 * - Letras: estando en Administración, una tecla por sección (la maneja atajos.js con SECCIONES).
 */
const Nav = (() => {
    const $ = id => document.getElementById(id);
    const t = (s, ...a) => esc(I18N.t(s, ...a));
    const rol = () => auth.getUser()?.role || '';
    const esAdmin = () => rol() === 'administrador';
    const esTaller = () => ['administrador', 'tecnico'].includes(rol());

    // Las secciones de Administración, con su letra (sin G ni N, que son atajos globales)
    const SECCIONES = [
        { id: 'users',                  titulo: 'Usuarios',                  letra: 'U', icono: 'usuarios',     palabras: 'técnicos clientes cuentas roles clave' },
        { id: 'products',               titulo: 'Productos',                 letra: 'P', icono: 'notebook',     palabras: 'modelos marcas garantía catálogo' },
        { id: 'parts',                  titulo: 'Repuestos',                 letra: 'R', icono: 'chip',         palabras: 'inventario piezas proveedores importar' },
        { id: 'stock',                  titulo: 'Stock',                     letra: 'S', icono: 'barras',       palabras: 'movimientos existencias' },
        { id: 'ubicaciones',            titulo: 'Ubicaciones',               letra: 'L', icono: 'pin',          palabras: 'lugares depósito estantes etiquetas' },
        { id: 'pedidos',                titulo: 'Pedidos a proveedor',       letra: 'O', icono: 'camion',       palabras: 'compras órdenes reposición' },
        { id: 'estados',                titulo: 'Estados',                   letra: 'E', icono: 'lista',        palabras: 'flujo colores' },
        { id: 'tags',                   titulo: 'Etiquetas',                 letra: 'T', icono: 'etiqueta',     palabras: 'tags' },
        { id: 'plantillas',             titulo: 'Plantillas de diagnóstico', letra: 'D', icono: 'documento',    palabras: 'diagnóstico textos' },
        { id: 'plantillas-presupuesto', titulo: 'Plantillas de presupuesto', letra: 'C', icono: 'recibo',       palabras: 'presupuesto cotización precios' },
        { id: 'ajustes',                titulo: 'Ajustes',                   letra: 'J', icono: 'engranaje',    palabras: 'configuración' },
        { id: 'seguridad',              titulo: 'Seguridad e ingresos',      letra: 'I', icono: 'candado',      palabras: 'login intentos bloqueo' },
        { id: 'finanzas',               titulo: 'Finanzas',                  letra: 'F', icono: 'billete',      palabras: 'ingresos ganancias facturación' },
        { id: 'export',                 titulo: 'Exportar',                  letra: 'X', icono: 'descargar',    palabras: 'excel csv descargar' },
    ];
    // Grupos de Ajustes (data-grupo en ajustes.js) con lo que se suele buscar
    const AJUSTES = [
        { grupo: 'general',       titulo: 'General',                 palabras: 'nombre del taller logo idioma registro seguimiento url' },
        { grupo: 'documentos',    titulo: 'Documentos',              palabras: 'pdf orden remito presupuesto' },
        { grupo: 'impresion',     titulo: 'Impresoras térmicas',     palabras: 'etiqueta ticketera dpi tamaño impresora' },
        { grupo: 'email',         titulo: 'Email (SMTP)',            palabras: 'mail correo smtp servidor' },
        { grupo: 'email_eventos', titulo: 'Qué notificar por email', palabras: 'avisos notificaciones mails' },
        { grupo: 'retiro',        titulo: 'Retiro y encuesta',       palabras: 'guarda plazo encuesta satisfacción' },
        { grupo: 'taller',        titulo: 'Gestión del taller',      palabras: 'garantía reparación tarifa hora checklist accesorios categorías quieto' },
        { grupo: 'sla',           titulo: 'Alertas de SLA',          palabras: 'plazos vencidos aviso' },
    ];

    // ── Recientes ────────────────────────────────────────────────────────────
    const leer = clave => { try { return JSON.parse(localStorage.getItem(clave) || '[]'); } catch { return []; } };
    const guardar = (clave, v) => { try { localStorage.setItem(clave, JSON.stringify(v)); } catch { /* sin almacenamiento */ } };

    /** Lo llama ui.adminSwitchTab: cuenta el uso y actualiza la dirección. */
    function seccionAbierta(tab) {
        if (!SECCIONES.some(s => s.id === tab)) return;
        const usos = Object.fromEntries(leer('gezarma-admin-usos'));
        usos[tab] = (usos[tab] || 0) + 1;
        guardar('gezarma-admin-usos', Object.entries(usos));
        guardar('gezarma-admin-ultimas', [tab, ...leer('gezarma-admin-ultimas').filter(x => x !== tab)].slice(0, 5));
        const hash = `#admin=${tab}`;
        if (location.hash !== hash) history.pushState({ admin: tab }, '', location.pathname + location.search + hash);
    }

    /** Las 3 más usadas (empate: la más reciente). */
    function masUsadas() {
        const usos = Object.fromEntries(leer('gezarma-admin-usos')), ult = leer('gezarma-admin-ultimas');
        return Object.keys(usos).filter(id => SECCIONES.some(s => s.id === id))
            .sort((a, b) => (usos[b] - usos[a]) || (ult.indexOf(a) + 1 || 99) - (ult.indexOf(b) + 1 || 99)).slice(0, 3);
    }

    function pintarRecientes() {
        const cont = $('menu-admin-recientes');
        if (!cont) return;
        const ids = esAdmin() ? masUsadas() : [];
        cont.classList.toggle('hidden', !ids.length);
        cont.innerHTML = ids.map(id => {
            const s = SECCIONES.find(x => x.id === id);
            return `<button type="button" data-admin-ir="${id}" class="text-xs font-medium text-gray-600 bg-gray-100 hover:bg-blue-50 hover:text-blue-700 rounded-full px-2.5 py-1 transition">${t(s.titulo)}</button>`;
        }).join('');
    }

    // ── Dirección (#admin=…) y botón Atrás ───────────────────────────────────
    const deHash = () => (location.hash.match(/^#admin=([\w-]+)/) || [])[1];
    // La dirección con la que se abrió la página (el login pasa antes por el panel y la limpiaría)
    let _alEntrar = deHash();

    /** Después del login o al entrar con un link guardado. */
    function abrirDesdeHash() {
        const tab = _alEntrar;
        _alEntrar = null;
        if (!tab) return false;
        if (!esAdmin() || !SECCIONES.some(s => s.id === tab)) {
            history.replaceState(null, '', location.pathname + location.search);
            return false;
        }
        ui.loadAdminPanel(tab);
        return true;
    }

    /** Lo llama ui.showSection: al salir de Administración la dirección vuelve a la normal. */
    function saliendo(nombre) {
        if (nombre !== 'admin' && deHash() && !_alEntrar) history.pushState(null, '', location.pathname + location.search);
    }

    window.addEventListener('popstate', () => {
        if (!auth.isLoggedIn()) { _alEntrar = deHash() || null; return; }   // se usa después del login
        const tab = deHash();
        if (tab && esAdmin()) {
            if ($('admin-section')) ui.adminSwitchTab(tab, { historial: false });
            else ui.loadAdminPanel(tab);
        } else if ($('admin-section')) {
            ui.initDashboard();
        }
    });

    // ── Letras dentro de Administración ──────────────────────────────────────
    const seccionDeLetra = k => SECCIONES.find(s => s.letra.toLowerCase() === k);

    /** Muestra la letra al lado de cada ítem del menú lateral (escritorio). */
    function marcarLetras() {
        document.querySelectorAll('#admin-menu .admin-tab-btn[data-tab]').forEach(b => {
            const s = SECCIONES.find(x => x.id === b.dataset.tab);
            if (!s || b.querySelector('[data-letra]')) return;
            const tieneContador = !!b.querySelector('span[id$="-count"]');
            b.insertAdjacentHTML('beforeend', `<kbd data-letra translate="no" aria-hidden="true" class="hidden lg:inline ${tieneContador ? 'ml-2' : 'ml-auto'} text-[10px] font-mono font-semibold text-gray-300 w-4 text-center">${s.letra}</kbd>`);
            b.setAttribute('aria-keyshortcuts', s.letra);
        });
    }

    // ── "Ir a…" ──────────────────────────────────────────────────────────────
    const norm = s => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    const RMA_RE = /^RMA-\d{4}-[A-Z]{4}\d{3}$/i;

    function opciones() {
        const o = [];
        const pantalla = (id, titulo, icono, hacer, palabras = '', atajo = '') => o.push({ id, titulo, icono, hacer, palabras, atajo, grupo: 'Pantallas' });
        pantalla('dashboard', 'Panel de control', 'panel', () => ui.initDashboard(), 'inicio tickets lista', 'G D');
        pantalla('nuevo', 'Nuevo ticket', 'mas', async () => { if (!$('dashboard-section')) await ui.initDashboard(); $('create-ticket-btn')?.click(); }, 'crear cargar', 'N');
        if (esTaller()) {
            pantalla('tablero', 'Tablero', 'tablero', async () => { if (!$('dashboard-section')) await ui.initDashboard(); document.querySelector('[data-vista="tablero"]')?.click(); }, 'kanban', 'G T');
            pantalla('mostrador', 'Ingreso en mostrador', 'recibo', () => Recepcion.abrirMostrador(), 'recepción recibir equipo', 'G M');
            pantalla('horas', 'Horas', 'reloj', () => Horas.abrir(), 'tiempo calendario', 'G H');
            pantalla('externos', 'Fuera del taller', 'camion', () => Envios.abrir(), 'fabricante garantía servicio oficial envíos', 'G F');
            pantalla('favoritos', 'Favoritos', 'estrella', async () => { if (!$('dashboard-section')) await ui.initDashboard(); $('favorites-nav-btn')?.click(); }, 'marcados');
        }
        if (esAdmin()) {
            SECCIONES.forEach(s => o.push({ id: 'admin:' + s.id, titulo: s.titulo, icono: s.icono, palabras: s.palabras + ' administración',
                atajo: s.letra, grupo: 'Administración', hacer: () => ui.loadAdminPanel(s.id) }));
            AJUSTES.forEach(a => o.push({ id: 'ajustes:' + a.grupo, titulo: I18N.t('Ajustes › {0}', I18N.t(a.titulo)), icono: 'engranaje',
                palabras: a.palabras + ' ajustes', grupo: 'Ajustes', hacer: () => irAAjustes(a.grupo) }));
            o.push({ id: 'setup', titulo: 'Configuración inicial', icono: 'checklist', palabras: 'asistente rubro primer uso', grupo: 'Ajustes', hacer: () => Setup.abrir(null, 0) });
        }
        const oscuro = document.documentElement.classList.contains('dark');
        o.push({ id: 'modo', titulo: oscuro ? 'Modo claro' : 'Modo oscuro', icono: oscuro ? 'sol' : 'luna', palabras: 'tema oscuro claro', grupo: 'Acciones', hacer: () => ui.toggleDark() });
        o.push({ id: 'atajos', titulo: 'Atajos de teclado', icono: 'teclado', palabras: 'ayuda teclas', atajo: '?', grupo: 'Acciones', hacer: () => Atajos.ayuda() });
        return o;
    }

    async function irAAjustes(grupo) {
        await ui.loadAdminPanel('ajustes');
        for (let i = 0; i < 30; i++) {                         // Ajustes se arma después de pedir los datos
            const sec = document.querySelector(`#ajustes-form [data-grupo="${grupo}"]`);
            if (sec) {
                window.Ajustes?.abrir(grupo);                   // la sección se despliega
                sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
                sec.classList.add('ring-2', 'ring-blue-400');
                setTimeout(() => sec.classList.remove('ring-2', 'ring-blue-400'), 1600);
                return;
            }
            await new Promise(r => setTimeout(r, 100));
        }
    }

    function buscar(q) {
        const todas = opciones();
        const query = norm(q).trim();
        if (!query) {
            const ult = leer('gezarma-ir-ultimas');
            const recientes = ult.map(id => todas.find(o => o.id === id)).filter(Boolean).slice(0, 5);
            const resto = todas.filter(o => !recientes.includes(o) && o.grupo === 'Pantallas');
            return [...recientes.map(o => ({ ...o, grupo: 'Recientes' })), ...resto];
        }
        const out = [];
        if (RMA_RE.test(q.trim())) {
            const rma = q.trim().toUpperCase();
            out.push({ id: 'rma', titulo: I18N.t('Abrir el ticket {0}', rma), icono: 'buscar', grupo: 'Tickets', sinTraducir: true,
                hacer: () => Recepcion.abrirRma(rma).then(ok => { if (!ok) toast.error(I18N.t('No se encontró el ticket {0}.', rma)); }) });
        }
        const palabras = query.split(/\s+/);
        todas.forEach(o => {
            const titulo = norm(I18N.t(o.titulo)), original = norm(o.titulo), extra = norm(o.palabras);
            const texto = `${titulo} ${original} ${extra}`;
            if (!palabras.every(p => texto.includes(p))) return;
            const puntos = (titulo.startsWith(query) || original.startsWith(query)) ? 3
                : palabras.every(p => titulo.includes(p) || original.includes(p)) ? 2 : 1;
            out.push({ ...o, puntos });
        });
        // Mejor coincidencia primero, pero sin partir los grupos (cada grupo va donde está su mejor resultado)
        out.sort((a, b) => (b.puntos || 9) - (a.puntos || 9));
        const orden = [...new Set(out.map(o => o.grupo))];
        return out.map((o, i) => ({ o, i })).sort((a, b) => (orden.indexOf(a.o.grupo) - orden.indexOf(b.o.grupo)) || (a.i - b.i)).map(x => x.o);
    }

    function paleta() {
        if (!auth.isLoggedIn()) return;
        if ($('ir-modal')) { $('ir-modal').remove(); }
        Barra?.menu?.(false);
        const div = document.createElement('div');
        div.id = 'ir-modal';
        div.className = 'fixed inset-0 bg-black bg-opacity-40 z-[80] flex items-start justify-center p-4 pt-[12vh]';
        div.innerHTML = `
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden" role="dialog" aria-modal="true" aria-label="${t('Ir a…')}">
            <div class="flex items-center gap-3 px-4 border-b">
                <span class="text-gray-400">${icono('buscar', 'w-5 h-5')}</span>
                <input id="ir-q" type="text" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="true" aria-controls="ir-lista"
                    placeholder="${t('Ir a… (sección, ajuste o N° de RMA)')}" class="flex-1 py-4 text-base outline-none bg-transparent">
                <button type="button" data-cerrar aria-label="${t('Cerrar')}" class="text-[11px] font-mono text-gray-400 hover:text-gray-700 border border-gray-200 rounded px-1.5 py-0.5"><span class="hidden sm:inline" translate="no">Esc</span><span class="sm:hidden">${icono('x', 'w-4 h-4')}</span></button>
            </div>
            <ul id="ir-lista" role="listbox" class="max-h-[55vh] overflow-y-auto py-2"></ul>
            <div class="hidden sm:flex items-center gap-4 px-4 py-2 border-t bg-gray-50 text-[11px] text-gray-500">
                <span><kbd class="font-mono">↑↓</kbd> ${t('moverse')}</span><span><kbd class="font-mono">Enter</kbd> ${t('abrir')}</span>
                <span class="ml-auto">${t('En Administración, una letra abre cada sección')}</span>
            </div>
        </div>`;
        document.body.appendChild(div);
        const q = $('ir-q'), lista = $('ir-lista');
        let items = [], sel = 0;
        const pintar = () => {
            items = buscar(q.value);
            sel = Math.min(sel, Math.max(0, items.length - 1));
            let grupo = '';
            lista.innerHTML = items.length ? items.map((o, i) => {
                const cab = o.grupo !== grupo ? `<li class="px-4 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400" role="presentation">${t(o.grupo)}</li>` : '';
                grupo = o.grupo;
                return cab + `<li id="ir-op-${i}" role="option" data-i="${i}" aria-selected="${i === sel}"
                    class="mx-2 px-3 py-2 rounded-lg flex items-center gap-3 cursor-pointer ${i === sel ? 'bg-blue-50 text-blue-800' : 'text-gray-700 hover:bg-gray-50'}">
                    <span class="${i === sel ? 'text-blue-600' : 'text-gray-400'}">${icono(o.icono, 'w-4 h-4')}</span>
                    <span class="flex-1 min-w-0 truncate text-sm">${o.sinTraducir ? esc(o.titulo) : t(o.titulo)}</span>
                    ${o.atajo ? `<kbd translate="no" class="hidden sm:inline text-[10px] font-mono font-semibold text-gray-400">${esc(o.atajo)}</kbd>` : ''}
                </li>`;
            }).join('') : `<li class="px-4 py-6 text-center text-sm text-gray-400">${t('Nada con «{0}».', q.value.trim())}</li>`;
            q.setAttribute('aria-activedescendant', items.length ? `ir-op-${sel}` : '');
            $(`ir-op-${sel}`)?.scrollIntoView({ block: 'nearest' });
        };
        const cerrar = () => div.remove();
        const elegir = i => {
            const o = items[i];
            if (!o) return;
            cerrar();
            if (o.id !== 'rma') guardar('gezarma-ir-ultimas', [o.id, ...leer('gezarma-ir-ultimas').filter(x => x !== o.id)].slice(0, 8));
            Promise.resolve(o.hacer()).catch(e => toast.error(e.message));
        };
        q.addEventListener('input', () => { sel = 0; pintar(); });
        q.addEventListener('keydown', e => {
            if (e.key === 'ArrowDown') { e.preventDefault(); sel = (sel + 1) % Math.max(1, items.length); pintar(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); sel = (sel - 1 + items.length) % Math.max(1, items.length); pintar(); }
            else if (e.key === 'Enter') { e.preventDefault(); elegir(sel); }
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cerrar(); }
        });
        lista.addEventListener('mousemove', e => {
            const li = e.target.closest('[data-i]');
            if (li && Number(li.dataset.i) !== sel) { sel = Number(li.dataset.i); pintar(); }
        });
        lista.addEventListener('click', e => { const li = e.target.closest('[data-i]'); if (li) elegir(Number(li.dataset.i)); });
        div.addEventListener('mousedown', e => { if (e.target === div) cerrar(); });
        div.querySelector('[data-cerrar]').addEventListener('click', cerrar);   // Escape lo usa (ui/modales.js)
        pintar();
        q.focus();
    }

    // Ctrl + K / Cmd + K: antes que el navegador (que lo usa para buscar en la barra de direcciones)
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k' && auth.isLoggedIn() && $('navbar') && !$('navbar').classList.contains('hidden')) {
            e.preventDefault();
            $('ir-modal') ? $('ir-modal').remove() : paleta();
        }
    }, true);

    document.addEventListener('click', e => {
        const b = e.target.closest('[data-admin-ir]');
        if (b) { Barra?.menu?.(false); ui.loadAdminPanel(b.dataset.adminIr); }
    });

    const esMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
    if ($('ir-btn-tecla')) $('ir-btn-tecla').textContent = esMac ? '⌘ K' : 'Ctrl K';
    return { SECCIONES, seccionDeLetra, seccionAbierta, pintarRecientes, abrirDesdeHash, saliendo, marcarLetras, paleta,
             teclaPaleta: esMac ? '⌘ K' : 'Ctrl K' };
})();
window.Nav = Nav;
