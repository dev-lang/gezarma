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
        if (abierto) {
            // Marca Administración si ya estás ahí
            const adm = $('menu-admin');
            if (adm) document.getElementById('admin-section') ? adm.setAttribute('aria-current', 'page') : adm.removeAttribute('aria-current');
            ui._textoModo?.(document.documentElement.classList.contains('dark'));
            [...m.querySelectorAll('button')].find(x => x.offsetParent !== null)?.focus();
        }
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
        $('menu-horas')?.addEventListener('click', () => { menu(false); window.Horas?.abrir(); });
        $('menu-admin')?.addEventListener('click', () => { menu(false); ui.loadAdminPanel(); });
        $('menu-atajos')?.addEventListener('click', () => { menu(false); window.Atajos?.ayuda(); });
        $('search-toggle')?.addEventListener('click', () => busqueda());
        // El nombre lleva al panel de control (o al login si no hay sesión).
        // Ctrl/Cmd+click sigue abriendo otra pestaña, como cualquier link.
        $('logo-home')?.addEventListener('click', e => {
            if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
            e.preventDefault();
            menu(false);
            if (auth.isLoggedIn()) {
                ui.initDashboard();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            } else location.href = '/';
        });
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

    // ── Marca del taller: nombre y logo (Ajustes → General) ───────────────
    let _marca = { nombre: 'GEZARMA', logo: null, registro_publico: true };
    async function marca() {
        try {
            const r = await fetch('/config/marca');
            if (r.ok) _marca = await r.json();
        } catch { /* se queda con la marca por defecto */ }
        pintarMarca();
    }
    function pintarMarca() {
        const m = _marca, src = m.logo ? `/config/logo?v=${m.logo}` : null;
        const img = cls => `<img src="${src}" alt="" class="${cls}">`;
        const nombre = $('marca-nombre');
        if (nombre) nombre.textContent = m.nombre;
        const logo = $('marca-logo');
        if (logo) {
            logo.innerHTML = src ? img('w-full h-full object-contain') : icono('llave', 'w-4 h-4');
            logo.classList.toggle('bg-white', !!src);
            logo.classList.toggle('bg-white/15', !src);
        }
        const lLogo = $('login-marca-logo');
        if (lLogo) {
            lLogo.innerHTML = src ? img('w-full h-full object-contain') : icono('llave', 'w-8 h-8');
            lLogo.classList.toggle('bg-blue-600', !src);
            lLogo.classList.toggle('text-white', !src);
            lLogo.classList.toggle('bg-white', !!src);
        }
        document.querySelectorAll('[data-marca-nombre]').forEach(el => { el.textContent = m.nombre; });
        $('login-registro')?.classList.toggle('hidden', !m.registro_publico);
        $('login-seguimiento')?.classList.toggle('hidden', m.seguimiento_publico === false);
        document.title = `${m.nombre} - ${I18N.t('Gestión de RMA')}`;
        const fav = $('favicon');
        if (fav) { fav.type = src ? 'image/png' : 'image/svg+xml'; fav.href = src || '/favicon.svg'; }
    }
    marca();

    return { iniciar, busqueda, marca, pintarMarca, datosMarca: () => _marca };
})();
window.Barra = Barra;
