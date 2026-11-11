/**
 * toast.js — Non-blocking notification system
 * Usage: toast.success('Ticket creado') | toast.error('Error') | toast.info('...')
 */
const toast = (() => {
    const DURATION = 4000;
    const DURATION_DESHACER = 7000;   // un poco más, para llegar a apretar "Deshacer"

    const ICONS = {
        success: `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`,
        error:   `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>`,
        info:    `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20A10 10 0 0012 2z"/></svg>`,
        warning: `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>`,
    };

    const STYLES = {
        success: 'bg-white border-l-4 border-green-500 text-gray-800',
        error:   'bg-white border-l-4 border-red-500 text-gray-800',
        info:    'bg-white border-l-4 border-blue-500 text-gray-800',
        warning: 'bg-white border-l-4 border-amber-400 text-gray-800',
    };

    const ICON_STYLES = {
        success: 'text-green-500',
        error:   'text-red-500',
        info:    'text-blue-500',
        warning: 'text-amber-400',
    };

    function show(message, type = 'info', accion = null) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const el = document.createElement('div');
        el.className = `pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-xl shadow-lg sm:min-w-[280px] sm:max-w-sm toast-enter ${STYLES[type]}`;
        el.setAttribute('role', type === 'error' ? 'alert' : 'status');
        el.innerHTML = `
            <span class="${ICON_STYLES[type]} shrink-0 mt-0.5">${ICONS[type]}</span>
            <p class="text-sm font-medium flex-1 leading-snug">${esc(message)}</p>
            ${accion ? `<button type="button" data-accion class="shrink-0 text-sm font-bold text-blue-600 hover:text-blue-800 underline-offset-2 hover:underline">${esc(accion.texto)}</button>` : ''}
            <button type="button" data-cerrar aria-label="Cerrar" class="text-gray-300 hover:text-gray-500 shrink-0 ml-2 mt-0.5 text-lg leading-none">×</button>
        `;
        el.querySelector('[data-cerrar]').addEventListener('click', () => el.remove());
        if (accion) {
            el.querySelector('[data-accion]').addEventListener('click', async () => {
                el.remove();
                try { await accion.hacer(); toast.info('Se deshizo el cambio.'); }
                catch (err) { toast.error(err.message || 'No se pudo deshacer.'); }
            }, { once: true });
        }

        container.appendChild(el);
        // En el celular quedan a la vista los 2 últimos (los demás ya se leyeron o se pisan)
        if (window.matchMedia('(max-width: 639px)').matches) {
            while (container.children.length > 2) container.firstElementChild.remove();
        }

        setTimeout(() => {
            if (!el.isConnected) return;
            el.classList.remove('toast-enter');
            el.classList.add('toast-leave');
            el.addEventListener('animationend', () => el.remove());
        }, accion ? DURATION_DESHACER : DURATION);
    }

    return {
        success: (msg) => show(msg, 'success'),
        error:   (msg) => show(msg, 'error'),
        info:    (msg) => show(msg, 'info'),
        warning: (msg) => show(msg, 'warning'),
        /** Acción reversible: toast.deshacer('Etiqueta quitada.', () => api.addTag(...)) */
        deshacer: (msg, hacer) => show(msg, 'success', { texto: 'Deshacer', hacer }),
    };
})();
