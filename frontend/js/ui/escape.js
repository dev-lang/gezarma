/**
 * escape.js — Escapar texto antes de meterlo en HTML (se carga antes que todo).
 *
 * Todo dato que viene del servidor y lo escribió un usuario (descripciones,
 * comentarios, nombres, notas, etiquetas…) tiene que pasar por esc() antes de ir
 * a innerHTML o a un atributo. Si no, un cliente podría meter HTML/JS que se
 * ejecute en el navegador del taller.
 */
(function () {
    const MAPA = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' };
    window.esc = s => String(s ?? '').replace(/[&<>"'`]/g, c => MAPA[c]);
    // Color para un style="": solo #rgb / #rrggbb (si no, uno neutro)
    window.colorSeguro = (c, porDefecto = '#6b7280') => /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(String(c || '')) ? c : porDefecto;
    // Texto que se lee sobre un fondo de color elegido por el taller (estados): blanco o casi negro,
    // el que dé más contraste. Así un estado amarillo o celeste se lee igual que uno azul oscuro.
    window.textoSobre = fondo => {
        let h = colorSeguro(fondo).slice(1);
        if (h.length === 3) h = [...h].map(x => x + x).join('');
        const lin = i => { const c = parseInt(h.slice(i, i + 2), 16) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
        const L = 0.2126 * lin(0) + 0.7152 * lin(2) + 0.0722 * lin(4);
        return 1.05 / (L + 0.05) >= (L + 0.05) / 0.0617 ? '#ffffff' : '#111827';
    };
    // style="" para una insignia con el color del estado: fondo y texto legible
    window.estiloEstado = c => `background:${colorSeguro(c)};color:${textoSobre(c)}`;
})();
