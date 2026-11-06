/**
 * barra.js — Barra superior en el celular: menú de usuario (idioma, modo
 * oscuro, atajos, salir) y búsqueda que se abre con la lupa.
 * La barra no se recrea al navegar: se conecta una sola vez.
 */
const Barra = (() => {
    let _iniciada = false;
    const $ = id => document.getElementById(id);

    function menu(abrir) {
        const m = $('user-menu'), b = $('user-menu-btn');
        if (!m || !b) return;
        const abierto = abrir ?? m.classList.contains('hidden');
        m.classList.toggle('hidden', !abierto);
        b.setAttribute('aria-expanded', String(abierto));
        if (abierto) m.querySelector('#menu-dark')?.focus();
    }

    function busqueda(abrir) {
        const c = $('search-container'), b = $('search-toggle');
        if (!c) return;
        const abierta = abrir ?? !c.classList.contains('abierto');
        c.classList.toggle('abierto', abierta);
        b?.setAttribute('aria-expanded', String(abierta));
        if (abierta) $('global-search')?.focus();
    }

    function iniciar() {
        if (_iniciada || !$('navbar')) return;
        _iniciada = true;
        $('user-menu-btn')?.addEventListener('click', e => { e.stopPropagation(); menu(); });
        $('menu-dark')?.addEventListener('click', () => { ui.toggleDark(); menu(false); });
        $('menu-logout')?.addEventListener('click', () => auth.logout());
        $('menu-atajos')?.addEventListener('click', () => { menu(false); window.Atajos?.ayuda(); });
        $('search-toggle')?.addEventListener('click', () => busqueda());
        document.addEventListener('click', e => {
            if (!$('user-menu')?.contains(e.target)) menu(false);
        });
        document.addEventListener('keydown', e => {
            if (e.key !== 'Escape') return;
            if (!$('user-menu')?.classList.contains('hidden')) { menu(false); $('user-menu-btn')?.focus(); }
            const input = $('global-search');
            if (document.activeElement === input && !input.value && $('search-container')?.classList.contains('abierto')) busqueda(false);
        });
    }

    return { iniciar, busqueda };
})();
window.Barra = Barra;
