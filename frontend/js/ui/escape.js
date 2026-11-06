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
})();
