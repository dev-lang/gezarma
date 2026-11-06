/**
 * atajos.js — Atajos de teclado (escritorio). No actúan mientras se escribe
 * en un campo ni con un modal abierto.
 *   /      buscar                 N    nuevo ticket
 *   G D    panel de control       G T  tablero (Kanban)
 *   G M    ingreso en mostrador   G A  administración
 *   ?      esta ayuda
 */
const Atajos = (() => {
    let _iniciados = false, _g = 0;

    const ATAJOS = [
        { teclas: ['/'], texto: 'Buscar' },
        { teclas: ['N'], texto: 'Nuevo ticket' },
        { teclas: ['G', 'D'], texto: 'Ir al panel de control' },
        { teclas: ['G', 'T'], texto: 'Ir al tablero' },
        { teclas: ['G', 'M'], texto: 'Ingreso en mostrador' },
        { teclas: ['G', 'A'], texto: 'Ir a Administración' },
        { teclas: ['Esc'], texto: 'Cerrar ventana o menú' },
        { teclas: ['?'], texto: 'Ver los atajos' },
    ];

    const escribiendo = e => {
        const t = e.target;
        return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    };
    const hayModal = () => [...document.querySelectorAll('[role=dialog]')].some(d => {
        const caja = d.closest('[id$="-modal"],[data-modal],.fixed') || d;
        return !caja.classList.contains('hidden') && caja.isConnected;
    });
    const rol = () => auth.getUser()?.role || '';
    const taller = () => ['administrador', 'tecnico'].includes(rol());

    async function alDashboard() {
        if (!document.getElementById('dashboard-section')) await ui.initDashboard();
    }

    function ayuda() {
        if (document.getElementById('atajos-modal')) return;
        const div = document.createElement('div');
        div.id = 'atajos-modal';
        div.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[70] p-4';
        div.innerHTML = `
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm" role="dialog" aria-modal="true">
            <div class="flex items-center justify-between px-5 py-4 border-b">
                <h3 class="font-bold text-gray-800">Atajos de teclado</h3>
                <button type="button" data-cerrar class="text-gray-400 hover:text-gray-600 text-2xl leading-none" aria-label="Cerrar">×</button>
            </div>
            <ul class="p-5 space-y-2 text-sm">${ATAJOS.map(a => `
                <li class="flex items-center justify-between gap-4">
                    <span class="text-gray-700">${a.texto}</span>
                    <span class="flex gap-1">${a.teclas.map(k => `<kbd translate="no" class="min-w-[1.75rem] text-center px-1.5 py-0.5 rounded border border-gray-300 bg-gray-50 text-xs font-mono font-semibold text-gray-700">${k}</kbd>`).join('<span class="text-gray-400 text-xs self-center">→</span>')}</span>
                </li>`).join('')}
            </ul>
        </div>`;
        div.querySelector('[data-cerrar]').addEventListener('click', () => div.remove());
        div.addEventListener('click', e => { if (e.target === div) div.remove(); });
        document.body.appendChild(div);
    }

    async function ejecutar(accion) {
        switch (accion) {
            case 'buscar':
                if (window.innerWidth < 640) Barra.busqueda(true);
                document.getElementById('global-search')?.focus();
                break;
            case 'nuevo':
                await alDashboard();
                document.getElementById('create-ticket-btn')?.click();
                break;
            case 'dashboard': await ui.initDashboard(); break;
            case 'tablero':
                if (!taller()) return;
                await alDashboard();
                document.querySelector('[data-vista="tablero"]')?.click();
                break;
            case 'mostrador': if (taller() && window.Recepcion) Recepcion.abrirMostrador(); break;
            case 'admin': if (rol() === 'administrador') ui.loadAdminPanel(); break;
        }
    }

    function iniciar() {
        if (_iniciados) return;
        _iniciados = true;
        document.addEventListener('keydown', e => {
            if (e.ctrlKey || e.metaKey || e.altKey || escribiendo(e) || !auth.isLoggedIn()) return;
            if (!document.getElementById('dashboard-section') && !document.getElementById('app-root')?.children.length) return;
            if (hayModal() && e.key !== '?') return;
            const k = e.key.toLowerCase();
            if (_g && Date.now() - _g < 1200) {
                _g = 0;
                const destino = { d: 'dashboard', t: 'tablero', m: 'mostrador', a: 'admin' }[k];
                if (destino) { e.preventDefault(); ejecutar(destino); }
                return;
            }
            if (k === 'g') { _g = Date.now(); return; }
            if (e.key === '/') { e.preventDefault(); ejecutar('buscar'); }
            else if (k === 'n') { e.preventDefault(); ejecutar('nuevo'); }
            else if (e.key === '?') { e.preventDefault(); ayuda(); }
        });
    }

    return { iniciar, ayuda };
})();
window.Atajos = Atajos;
