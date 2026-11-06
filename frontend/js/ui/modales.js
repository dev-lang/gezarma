/**
 * modales.js — Accesibilidad común a todos los modales, sin tocar cada uno:
 *   - role="dialog" + aria-modal + aria-labelledby (el primer título)
 *   - al abrir, el foco va al primer campo/botón; al cerrar, vuelve a donde estaba
 *   - Escape cierra el de arriba (usa su botón de cerrar/cancelar, así corre su lógica)
 *   - Tab no se escapa del modal abierto
 *
 * Se considera modal: un elemento con id "...-modal", [data-modal], o un
 * overlay "fixed inset-0" que contiene un [role=dialog] (los que arman los módulos).
 */
(() => {
    const FOCO = 'input:not([type=hidden]):not([disabled]),select:not([disabled]),textarea:not([disabled]),button:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])';
    const pila = [];          // [{ el, volver }]
    let _sinTitulo = 0;

    // Un modal es un overlay (fixed inset-0): ojo, "close-modal" y similares son botones, no modales
    const esModal = el => el.nodeType === 1 && (el.hasAttribute('data-modal') ||
        (el.classList.contains('fixed') && el.classList.contains('inset-0') &&
         ((el.id && el.id.endsWith('-modal')) || el.querySelector(':scope > [role=dialog]'))));
    const visible = el => el.isConnected && !el.classList.contains('hidden');
    const enfocables = el => [...el.querySelectorAll(FOCO)].filter(x => x.offsetParent !== null || x === document.activeElement);

    function preparar(el) {
        const caja = el.querySelector(':scope > [role=dialog]') || el;
        caja.setAttribute('role', 'dialog');
        caja.setAttribute('aria-modal', 'true');
        if (!caja.hasAttribute('aria-labelledby') && !caja.hasAttribute('aria-label')) {
            const t = caja.querySelector('h1,h2,h3');
            if (t) { if (!t.id) t.id = `modal-titulo-${++_sinTitulo}`; caja.setAttribute('aria-labelledby', t.id); }
        }
    }

    function abierto(el) {
        if (pila.some(p => p.el === el)) return;
        preparar(el);
        pila.push({ el, volver: document.activeElement });
        // Después de que el módulo termine de llenar el modal
        requestAnimationFrame(() => {
            if (!visible(el) || el.contains(document.activeElement)) return;
            const campos = enfocables(el);
            const primero = campos.find(x => x.matches('input,select,textarea')) || campos.find(x => !/close|cerrar/i.test(x.id + ' ' + (x.getAttribute('aria-label') || ''))) || campos[0];
            primero?.focus({ preventScroll: true });
        });
    }

    function cerrado(i) {
        const { volver } = pila.splice(i, 1)[0];
        if (volver?.isConnected && typeof volver.focus === 'function' && !pila.length) volver.focus({ preventScroll: true });
    }

    function revisar() {
        for (let i = pila.length - 1; i >= 0; i--) if (!visible(pila[i].el)) cerrado(i);
        document.querySelectorAll('[id$="-modal"],[data-modal],.fixed.inset-0').forEach(el => {
            if (esModal(el) && visible(el)) abierto(el);
        });
    }

    function botonCerrar(el) {
        return el.querySelector('#confirm-cancel-btn,[data-cancelar],[data-cerrar],[id^="close"],[id$="-cancel"],[id$="-close"],[aria-label="Cerrar"]');
    }

    document.addEventListener('keydown', e => {
        const arriba = pila[pila.length - 1]?.el;
        if (!arriba || !visible(arriba)) return;
        if (e.key === 'Escape') {
            e.preventDefault(); e.stopPropagation();
            const b = botonCerrar(arriba);
            if (b) b.click(); else arriba.classList.add('hidden');
        } else if (e.key === 'Tab') {
            const campos = enfocables(arriba);
            if (!campos.length) return;
            const [primero, ultimo] = [campos[0], campos[campos.length - 1]];
            if (!arriba.contains(document.activeElement)) { e.preventDefault(); primero.focus(); }
            else if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus(); }
            else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus(); }
        }
    }, true);

    let _pendiente = false;
    new MutationObserver(() => {
        if (_pendiente) return;
        _pendiente = true;
        queueMicrotask(() => { _pendiente = false; revisar(); });
    }).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
})();
