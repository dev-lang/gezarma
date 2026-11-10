/**
 * gestion.js — Tarjeta "Gestión de ticket" del detalle (taller).
 *
 * Cada control se guarda solo, en el momento, sin un botón general:
 *   - Estado: al elegirlo. Los estados finales (Cerrado, Cancelado…) piden
 *     confirmación; "Enviado al cliente" pide transporte y tracking primero.
 *   - Técnico: al elegirlo (con Deshacer).
 *   - Etiqueta: al elegirla.
 *   - Repuesto: con su botón "Agregar" (hay que indicar la cantidad).
 *   - Diagnóstico: con "Guardar diagnóstico".
 * Así un cambio nunca arrastra a los otros. Después de cada uno se refresca
 * solo lo que cambió (sin recargar la pantalla ni perder el lugar).
 */
const Gestion = (() => {
    const ENVIADO = 'Enviado al cliente';
    const $ = id => document.getElementById(id);
    const card = () => $('mgmt-card');

    function ocupado(el, si) {
        if (!el) return;
        el.disabled = si;
        el.classList.toggle('opacity-60', si);
        el.classList.toggle('cursor-wait', si);
    }

    /** Refresca lo que muestra el detalle sin redibujar la pantalla */
    async function refrescar(ticketId) {
        const t = await api.getTicket(ticketId);
        if (ui.currentTicketId !== ticketId) return t;
        if (ui._ticketCache) ui._ticketCache[ticketId] = t;
        const badge = $('detail-status-badge');
        if (badge) {
            components.pintarEstado(badge, t.estado);
        }
        if ($('detail-tecnico')) $('detail-tecnico').innerText = t.tecnico_nombre || I18N.t('Sin asignar');
        const c = card();
        if (c) { c.dataset.origEstado = t.estado; c.dataset.origTecnico = t.tecnico_asignado ?? ''; }
        if ($('update-status')) $('update-status').value = t.estado;
        const envio = $('detail-shipping-container');
        if (envio && t.tracking_number) {
            envio.classList.remove('hidden');
            $('detail-shipping-company').innerText = t.empresa_transporte || I18N.t('No especificada');
            $('detail-tracking').innerText = t.tracking_number;
        }
        ui.toggleShippingFields(null);
        ui.loadHistory(ticketId);
        if (typeof Recepcion !== 'undefined') Recepcion.cargarDetalle(t);
        if (typeof Encuesta !== 'undefined') Encuesta.cargarDetalle(t);
        if (typeof Ubic !== 'undefined') Ubic.cargarDetalle(t);
        if (typeof Envios !== 'undefined') Envios.cargarDetalle(t);
        return t;
    }

    const etiquetaEstado = valor => (ui._estadosCache || []).find(s => s.valor === valor);

    async function cambiarEstado(e) {
        const sel = e.target, c = card(), ticketId = ui.currentTicketId;
        const anterior = c?.dataset.origEstado ?? '', nuevo = sel.value;
        const volver = () => { sel.value = anterior; ui.toggleShippingFields(null); };
        if (nuevo === anterior) { ui.toggleShippingFields(null); return; }
        if (typeof Envios !== 'undefined' && (nuevo === Envios.ESTADO || anterior === Envios.ESTADO)) {
            // Al fabricante se manda (y se recibe) con su formulario: guarda caso, guía y resultado
            const saliendo = anterior === Envios.ESTADO;
            if (!saliendo) { volver(); Envios.desdeSelector(ticketId); return; }
            if (await Envios.desdeSelector(ticketId, { saliendo })) { volver(); return; }
        }
        if (nuevo === ENVIADO) {
            // Primero transporte y tracking; se confirma con "Marcar como enviado"
            ui.toggleShippingFields(ENVIADO);
            $('update-shipping-company')?.focus();
            return;
        }
        ui.toggleShippingFields(null);
        const cfg = etiquetaEstado(nuevo);
        const final = cfg ? cfg.es_final : ['Cerrado', 'Cancelado'].includes(nuevo);
        if (final) {
            const ok = await confirmDialog(I18N.t('¿Pasar el ticket a «{0}»?', I18N.t(cfg?.etiqueta || nuevo)),
                I18N.t('El ticket se cierra y, si está activado, se le avisa al cliente.'), I18N.t('Confirmar'), { peligro: false });
            if (!ok) { volver(); return; }
        }
        ocupado(sel, true);
        try {
            await api.updateTicketStatus(ticketId, nuevo);
            await refrescar(ticketId);
            toast.success(I18N.t('Estado: {0}', I18N.t(cfg?.etiqueta || nuevo)));
        } catch (err) {
            volver();
            toast.error(err.message);
        } finally { ocupado(sel, false); }
    }

    async function confirmarEnvio() {
        const ticketId = ui.currentTicketId;
        const empresa = $('update-shipping-company')?.value.trim(), tracking = $('update-tracking')?.value.trim();
        if (!empresa || !tracking) { toast.warning('Completá el transporte y número de tracking para marcar como enviado.'); return; }
        try {
            await api.updateShipping(ticketId, { empresa_transporte: empresa, tracking_number: tracking });
            await api.updateTicketStatus(ticketId, ENVIADO);
            await refrescar(ticketId);
            toast.success(I18N.t('Estado: {0}', I18N.t(etiquetaEstado(ENVIADO)?.etiqueta || ENVIADO)));
        } catch (err) { toast.error(err.message); }
    }

    function cancelarEnvio() {
        const sel = $('update-status');
        if (sel) sel.value = card()?.dataset.origEstado ?? sel.value;
        ui.toggleShippingFields(null);
    }

    async function cambiarTecnico(e) {
        const sel = e.target, c = card(), ticketId = ui.currentTicketId;
        const anterior = c?.dataset.origTecnico ?? '', nuevo = sel.value;
        if (nuevo === anterior) return;
        const asignar = async id => {
            await api.assignTechnician(ticketId, id ? parseInt(id) : null);
            const t = await refrescar(ticketId);
            if (ui.currentTicketId === ticketId && $('assign-tech')) $('assign-tech').value = t.tecnico_asignado ?? '';
        };
        ocupado(sel, true);
        try {
            await asignar(nuevo);
            const nombre = sel.selectedOptions[0]?.textContent || '';
            toast.deshacer(nuevo ? I18N.t('Técnico asignado: {0}', nombre) : I18N.t('Ticket sin técnico asignado.'), () => asignar(anterior));
        } catch (err) {
            sel.value = anterior;
            toast.error(err.message);
        } finally { ocupado(sel, false); }
    }

    async function agregarEtiqueta(e) {
        const sel = e.target, nombre = sel.value, ticketId = ui.currentTicketId;
        if (!nombre) return;
        ocupado(sel, true);
        try {
            await api.addTag(ticketId, nombre);
            const t = await api.getTicket(ticketId);
            if (ui.currentTicketId === ticketId) ui._renderTicketTags(t.tags || [], true);
            ui.loadHistory(ticketId);
            toast.deshacer(I18N.t('Etiqueta agregada: {0}', nombre), async () => {
                await api.removeTag(ticketId, nombre);
                const t2 = await api.getTicket(ticketId);
                if (ui.currentTicketId === ticketId) ui._renderTicketTags(t2.tags || [], true);
            });
        } catch (err) { toast.error(err.message); }
        finally { sel.value = ''; ocupado(sel, false); }
    }

    async function agregarRepuesto() {
        const ticketId = ui.currentTicketId;
        const partId = parseInt($('update-part')?.value), cant = parseInt($('update-part-qty')?.value) || 1;
        if (!partId) return;
        try {
            const t = await api.addPart(ticketId, partId, cant);
            // La lista de repuestos se redibuja con el detalle: se conserva el
            // diagnóstico que se esté escribiendo y el lugar de la pantalla
            const borrador = $('update-diagnostic')?.value || '', y = window.scrollY;
            if (ui.currentTicketId === ticketId) await ui.showTicketDetail(t);
            if ($('update-diagnostic') && borrador) { $('update-diagnostic').value = borrador; $('save-mgmt-btn').disabled = false; }
            window.scrollTo(0, y);
            toast.success(I18N.t('Repuesto agregado al ticket.'));
        } catch (err) { toast.error(err.message); }
    }

    async function guardarDiagnostico() {
        const ticketId = ui.currentTicketId, campo = $('update-diagnostic');
        const texto = campo?.value.trim();
        if (!texto) return;
        try {
            await api.addComment(ticketId, `DIAGNÓSTICO TÉCNICO: ${texto}`);
            campo.value = '';
            $('save-mgmt-btn').disabled = true;
            ui.loadComments(ticketId);
            ui.loadHistory(ticketId);
            toast.success(I18N.t('Diagnóstico guardado.'));
        } catch (err) { toast.error(err.message); }
    }

    /** Se llama en cada bindEvents con su `on` (se desconecta al cambiar de pantalla). */
    function conectar(on) {
        on('update-status', 'change', cambiarEstado);
        on('confirm-shipping-btn', 'click', confirmarEnvio);
        on('cancel-shipping-btn', 'click', cancelarEnvio);
        on('assign-tech', 'change', cambiarTecnico);
        on('update-tags', 'change', agregarEtiqueta);
        on('update-part', 'change', e => { const b = $('add-part-btn'); if (b) b.disabled = !e.target.value; });
        on('add-part-btn', 'click', agregarRepuesto);
        on('update-diagnostic', 'input', e => { const b = $('save-mgmt-btn'); if (b) b.disabled = !e.target.value.trim(); });
        on('save-mgmt-btn', 'click', guardarDiagnostico);
    }

    return { conectar, refrescar };
})();
window.Gestion = Gestion;
