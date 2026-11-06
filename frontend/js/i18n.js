/**
 * i18n.js — Idioma de la interfaz (se carga apenas después de escape.js).
 *
 * El sistema está escrito en español rioplatense y ese texto es la clave de
 * los diccionarios (backend/app/traducciones/<código>.json, el mismo que usa
 * el servidor para mails, documentos y errores). Las partes variables van
 * como {0}, {1}…: "Hace {0} días" → "{0} days ago".
 *
 * No hace falta envolver cada texto: un MutationObserver traduce todo lo que
 * aparece en pantalla (texto, placeholder, title, aria-label, alt). Lo que no
 * está en el diccionario queda en español.
 *   - Para que un texto NO se traduzca (lo que escribió un usuario): translate="no".
 *   - Desde el código: I18N.t('texto {0}', valor).
 *   - Fechas y números: I18N.locale en lugar de 'es-AR'.
 */
(function () {
    const IDIOMAS = { 'es-AR': 'Español (AR)', 'es-ES': 'Español (ES)', 'en': 'English', 'pt-BR': 'Português (BR)' };
    const LOCALES = { 'es-AR': 'es-AR', 'es-ES': 'es-ES', 'en': 'en-US', 'pt-BR': 'pt-BR' };
    const BASE = 'es-AR', CLAVE = 'gezarma-idioma';

    function normalizar(c) {
        if (!c) return null;
        c = String(c).replace('_', '-');
        const exacto = Object.keys(IDIOMAS).find(k => k.toLowerCase() === c.toLowerCase());
        if (exacto) return exacto;
        return { en: 'en', pt: 'pt-BR', es: BASE }[c.split('-')[0].toLowerCase()] || null;
    }
    function elegido() {
        let guardado = null;
        try { guardado = localStorage.getItem(CLAVE); } catch { /* modo privado */ }
        if (normalizar(guardado)) return normalizar(guardado);
        for (const n of navigator.languages || [navigator.language]) { const c = normalizar(n); if (c) return c; }
        return BASE;
    }

    const codigo = elegido();
    document.documentElement.lang = codigo;
    // El diccionario se carga antes que el resto de los scripts (bloqueante, a propósito:
    // así la primera pantalla ya sale traducida)
    if (codigo !== BASE) document.write(`<script src="/i18n/${codigo}.js"><\/script>`);

    // ── Motor (el mismo algoritmo que backend/app/idiomas.py) ────────────────
    const PH = /\{(\d+)\}/g;
    let exactos = null, patrones = [], indice = new Map();
    const palabras = s => (s.toLowerCase().match(/\p{L}+/gu) || []);

    function patronValido(clave) {
        const literal = clave.replace(PH, ' ');
        if (palabras(literal).some(w => w.length >= 4)) return true;
        return /^[^{]*\p{L}{2,}[.:]\s*\{0\}/u.test(clave);   // "Rol: {0}", "mín. {0}"
    }
    function preparar() {
        if (exactos) return;
        exactos = new Map();
        const dict = codigo !== BASE ? (window.I18N_DICT || {}) : {};
        for (const [k, v] of Object.entries(dict)) {
            if (!v || v === k) continue;
            if (/\{\d+\}/.test(k)) {
                if (!patronValido(k)) continue;
                const partes = k.split(/\{(\d+)\}/);
                const nombres = [];
                const rx = partes.map((p, i) => {
                    if (i % 2 === 0) return p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    nombres.push(p); return '([\\s\\S]+?)';
                }).join('');
                if (new Set(nombres).size !== nombres.length) continue;
                const literal = partes.filter((_, i) => i % 2 === 0).join('');
                patrones.push({ largo: literal.length, rx: new RegExp(`^${rx}$`), destino: v, nombres,
                                anclas: palabras(literal).filter(w => w.length >= 3) });
            } else {
                exactos.set(k.split(/\s+/).join(' ').trim(), v);
            }
        }
        patrones.sort((a, b) => b.largo - a.largo);
        patrones.forEach((p, n) => (p.anclas.length ? p.anclas : ['']).forEach(a => {
            if (!indice.has(a)) indice.set(a, []);
            indice.get(a).push(n);
        }));
    }

    function tr(texto, prof = 0) {
        if (codigo === BASE || typeof texto !== 'string') return texto;
        preparar();
        const nucleo = texto.trim();
        if (!nucleo) return texto;
        const ini = texto.slice(0, texto.length - texto.trimStart().length);
        const fin = texto.slice(texto.trimEnd().length);
        const clave = nucleo.split(/\s+/).join(' ');
        const exacto = exactos.get(clave);
        if (exacto !== undefined) return ini + exacto + fin;
        if (prof > 2) return texto;
        // "Ingresó el 3/11 · en garantía": se traduce cada parte
        if (clave.includes(' · ')) {
            const partes = clave.split(' · '), trad = partes.map(x => tr(x, prof + 1));
            if (trad.some((x, i) => x !== partes[i])) return ini + trad.join(' · ') + fin;
        }
        const cand = new Set(indice.get('') || []);
        for (const w of new Set(palabras(clave))) for (const n of indice.get(w) || []) cand.add(n);
        for (const n of [...cand].sort((a, b) => a - b)) {
            const p = patrones[n], m = p.rx.exec(clave);
            if (!m) continue;
            const valores = {};
            p.nombres.forEach((nombre, i) => { valores[nombre] = tr(m[i + 1], prof + 1); });
            return ini + p.destino.replace(PH, (x, k) => (k in valores ? valores[k] : x)) + fin;
        }
        return texto;
    }

    /** Desde el código: I18N.t('Hace {0} días', 3) */
    function t(texto, ...valores) {
        const base = tr(texto);
        return valores.length ? base.replace(PH, (x, k) => (valores[+k] ?? x)) : base;
    }

    // ── Traducción de la página ──────────────────────────────────────────────
    const ATRIBUTOS = ['placeholder', 'title', 'aria-label', 'alt'];
    const SALTEAR = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE', 'NOSCRIPT']);

    function excluido(el, paraAtributos = false) {
        for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
            // de un <textarea> se traduce el placeholder, nunca el contenido
            if (!(paraAtributos && e === el && e.tagName === 'TEXTAREA') && (SALTEAR.has(e.tagName) || e.isContentEditable)) return true;
            if (e.getAttribute('translate') === 'no' || e.classList.contains('notranslate')) return true;
        }
        return false;
    }
    function texto(nodo) {
        if (!nodo.data.trim() || excluido(nodo.parentElement)) return;
        const nuevo = tr(nodo.data);
        if (nuevo !== nodo.data) nodo.data = nuevo;
    }
    function atributos(el) {
        if (excluido(el, true)) return;
        for (const a of ATRIBUTOS) {
            const v = el.getAttribute(a);
            if (v) { const n = tr(v); if (n !== v) el.setAttribute(a, n); }
        }
        if (el.tagName === 'INPUT' && /^(button|submit)$/i.test(el.type) && el.value) {
            const n = tr(el.value); if (n !== el.value) el.value = n;
        }
    }
    function traducir(raiz) {
        if (codigo === BASE || !raiz) return;
        if (raiz.nodeType === 3) return texto(raiz);
        if (raiz.nodeType !== 1 && raiz.nodeType !== 9 && raiz.nodeType !== 11) return;
        if (raiz.nodeType === 1) { atributos(raiz); if (excluido(raiz)) return; }
        const w = document.createTreeWalker(raiz, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
            acceptNode: n => {
                if (n.nodeType !== 1) return NodeFilter.FILTER_ACCEPT;
                if (n.tagName === 'TEXTAREA') { atributos(n); return NodeFilter.FILTER_REJECT; }
                return (SALTEAR.has(n.tagName) || n.getAttribute('translate') === 'no' || n.classList.contains('notranslate'))
                    ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
            },
        });
        for (let n = w.nextNode(); n; n = w.nextNode()) n.nodeType === 3 ? texto(n) : atributos(n);
    }

    if (codigo !== BASE) {
        new MutationObserver(cambios => {
            for (const c of cambios) {
                if (c.type === 'childList') c.addedNodes.forEach(traducir);
                else if (c.type === 'characterData') texto(c.target);
                else if (c.type === 'attributes') atributos(c.target);
            }
        }).observe(document.documentElement, { subtree: true, childList: true, characterData: true,
                                                attributes: true, attributeFilter: [...ATRIBUTOS, 'value'] });
        document.addEventListener('DOMContentLoaded', () => { traducir(document.body); document.title = tr(document.title); });
    }

    /** Cambia el idioma (lo guarda en la cuenta si hay sesión) y recarga. */
    async function cambiar(nuevo) {
        nuevo = normalizar(nuevo) || BASE;
        try { localStorage.setItem(CLAVE, nuevo); } catch { /* modo privado */ }
        try {
            if (localStorage.getItem('token') && window.api) {
                await api.request('users/me/idioma', { method: 'PUT', body: JSON.stringify({ idioma: nuevo }) });
            }
        } catch { /* se aplica igual en este navegador */ }
        location.reload();
    }

    /** Al iniciar sesión: si la cuenta tiene otro idioma guardado, se usa ese. */
    function deLaCuenta(idiomaCuenta) {
        const c = normalizar(idiomaCuenta);
        if (c && c !== codigo) { try { localStorage.setItem(CLAVE, c); } catch { /* */ } location.reload(); return true; }
        if (!c && localStorage.getItem('token') && window.api) {   // la cuenta todavía no tiene: se guarda el actual
            api.request('users/me/idioma', { method: 'PUT', body: JSON.stringify({ idioma: codigo }) }).catch(() => {});
        }
        return false;
    }

    /** <select> para elegir idioma */
    function selector(clases = '') {
        const s = document.createElement('select');
        s.className = clases;
        s.setAttribute('translate', 'no');
        s.setAttribute('aria-label', tr('Idioma'));
        s.innerHTML = Object.entries(IDIOMAS).map(([k, v]) => `<option value="${k}"${k === codigo ? ' selected' : ''}>${v}</option>`).join('');
        s.addEventListener('change', () => cambiar(s.value));
        return s;
    }

    window.I18N = { codigo, locale: LOCALES[codigo], idiomas: IDIOMAS, t, tr, traducir, cambiar, deLaCuenta, selector, normalizar };
    window.t = t;
})();
