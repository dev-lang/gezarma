/**
 * adjuntos.js — Subida de adjuntos desde el detalle del ticket: elegir archivos,
 * vista previa con el espacio que ocupan, confirmar y subir.
 *
 * El botón "Subir" se conecta una vez por pantalla y sube SIEMPRE la última
 * selección (antes, cancelar y elegir otros archivos dejaba vivo el listener
 * anterior y se subía también el lote viejo).
 */
const Adjuntos = (() => {
    const PERMITIDOS = ['pdf', 'txt', 'jpg', 'jpeg', 'png'];
    const MAX_ARCHIVO = 10 * 1024 * 1024;
    const ICONOS = { pdf: '📄', jpg: '🖼️', jpeg: '🖼️', png: '🖼️', txt: '📃' };
    let _pendientes = null;   // { ticketId, files }

    const $ = id => document.getElementById(id);
    const ext = f => f.name.split('.').pop().toLowerCase();
    const fmtMb = n => n >= 1 ? n.toFixed(2) + ' MB' : (n * 1024).toFixed(0) + ' KB';
    const tam = b => b >= 1024 * 1024 ? (b / (1024 * 1024)).toFixed(1) + ' MB' : Math.round(b / 1024) + ' KB';

    function cerrar() {
        $('upload-preview-modal')?.classList.add('hidden');
        _pendientes = null;
    }

    async function elegidos(e) {
        const files = Array.from(e.target.files || []);
        e.target.value = '';   // para poder elegir el mismo archivo otra vez
        if (!files.length) return;
        const malos = files.filter(f => !PERMITIDOS.includes(ext(f)) || f.size > MAX_ARCHIVO);
        if (malos.length) {
            toast.error(malos.map(f => PERMITIDOS.includes(ext(f)) ? `${f.name}: supera 10 MB` : `${f.name}: tipo no permitido`).join(' · '));
            return;
        }
        const ticketId = ui.currentTicketId;
        let espacio = { used_mb: 0, remaining_mb: 10, limit_mb: 10 };
        try { espacio = (await api.getAttachments(ticketId)).storage || espacio; } catch { /* valores por defecto */ }

        const nuevoMb = files.reduce((s, f) => s + f.size, 0) / (1024 * 1024);
        const usadoDespues = espacio.used_mb + nuevoMb;
        $('upload-preview-list').innerHTML = files.map(f => `
            <div class="flex items-center gap-2 p-2 bg-gray-50 rounded-lg border border-gray-100 text-sm">
                <span>${ICONOS[ext(f)] || '📎'}</span>
                <span class="flex-1 font-medium text-gray-800 truncate">${esc(f.name)}</span>
                <span class="text-gray-400 text-xs shrink-0">${esc(ext(f).toUpperCase())} · ${tam(f.size)}</span>
            </div>`).join('');
        $('preview-total-size').textContent = fmtMb(nuevoMb);
        $('preview-used-size').textContent = fmtMb(espacio.used_mb);
        const restante = $('preview-remaining-size');
        restante.textContent = fmtMb(Math.max(0, espacio.limit_mb - usadoDespues));
        const sinLugar = usadoDespues > espacio.limit_mb;
        restante.classList.toggle('text-red-500', sinLugar);
        restante.classList.toggle('text-blue-600', !sinLugar);
        const err = $('upload-preview-error');
        err.classList.toggle('hidden', !sinLugar);
        if (sinLugar) err.textContent = `⚠ Sin espacio suficiente. Disponible: ${fmtMb(espacio.remaining_mb)}, necesario: ${fmtMb(nuevoMb)}.`;
        $('upload-preview-confirm').disabled = sinLugar;

        _pendientes = { ticketId, files };
        $('upload-preview-modal')?.classList.remove('hidden');
        $('upload-preview-confirm')?.focus();
    }

    async function subir() {
        if (!_pendientes) return;
        const { ticketId, files } = _pendientes;
        _pendientes = null;   // un solo envío por selección, aunque hagan doble click
        const boton = $('upload-preview-confirm'), spinner = $('upload-preview-spinner'), etq = $('upload-preview-confirm-label');
        boton.disabled = true; spinner?.classList.remove('hidden'); if (etq) etq.textContent = 'Subiendo...';
        let ok = 0; const fallidos = [];
        for (const f of files) {
            try { await api.uploadAttachment(ticketId, f); ok++; }
            catch (e) { fallidos.push(`${f.name}: ${e.message}`); }
        }
        spinner?.classList.add('hidden'); if (etq) etq.textContent = 'Subir archivos'; boton.disabled = false;
        $('upload-preview-modal')?.classList.add('hidden');
        if (ui.currentTicketId === ticketId) await ui.loadAttachments(ticketId);
        if (fallidos.length) toast.error(`${fallidos.length} archivo(s) fallaron: ${fallidos.join('; ')}`);
        if (ok) toast.success(`${ok} archivo(s) subido(s) correctamente.`);
    }

    /** Se llama en cada bindEvents con su `on` (que se desconecta al cambiar de pantalla). */
    function conectar(on) {
        on('upload-btn', 'click', () => $('attachment-file')?.click());
        on('attachment-file', 'change', elegidos);
        on('upload-preview-confirm', 'click', subir);
        on('upload-preview-close', 'click', cerrar);
        on('upload-preview-cancel', 'click', cerrar);
    }

    return { conectar };
})();
window.Adjuntos = Adjuntos;
