/**
 * ajustes.js — Pestaña "Ajustes" del panel de administración.
 * El formulario se arma a partir de GET /config/ajustes (tipo, etiqueta, ayuda,
 * opciones de cada ajuste) y guarda con PUT /config/ajustes.
 */
const Ajustes = (() => {
    const GRUPOS = [
        { id: 'general',       titulo: 'General',                 desc: 'Datos que aparecen en documentos, mails y QR.' },
        { id: 'documentos',    titulo: 'Documentos',              desc: 'Orden de ingreso, remito de entrega, presupuesto y etiqueta.' },
        { id: 'impresion',     titulo: 'Impresoras térmicas',     desc: 'Etiquetas para el equipo y comprobantes en ticketera. Se imprimen con el diálogo del sistema, a escala 100 %.' },
        { id: 'email',         titulo: 'Email (SMTP)',            desc: 'Servidor de correo para las notificaciones.' },
        { id: 'email_eventos', titulo: 'Qué notificar por email', desc: 'Además de las notificaciones dentro del sistema.' },
        { id: 'retiro',        titulo: 'Retiro y encuesta',       desc: 'Aviso de equipo listo para retirar, plazo de guarda y encuesta de satisfacción.' },
        { id: 'taller',        titulo: 'Gestión del taller',      desc: 'Garantía de las reparaciones y costo de la hora de trabajo.' },
        { id: 'sla',           titulo: 'Alertas de SLA',          desc: 'Avisos de tickets vencidos o por vencer.' },
    ];
    // Campos SMTP que solo tienen sentido si la configuración se toma del panel
    const SMTP_PANEL = ['smtp_host', 'smtp_port', 'smtp_seguridad', 'smtp_usuario', 'smtp_password', 'smtp_remitente'];

    let _items = [];
    let _destinoPrueba = '';   // se conserva al volver a dibujar el formulario

    const inputCls = 'w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 bg-white';

    function campo(a) {
        const id = `aj-${a.clave}`;
        let control;
        if (a.tipo === 'bool') {
            return `
            <label class="flex items-start gap-3 py-2 cursor-pointer" data-clave="${a.clave}">
                <input type="checkbox" id="${id}" ${a.valor ? 'checked' : ''} class="mt-0.5 w-4 h-4 accent-blue-600">
                <span><span class="text-sm font-semibold text-gray-700">${esc(a.label)}</span>
                ${a.ayuda ? `<span class="block text-xs text-gray-400 mt-0.5">${esc(a.ayuda)}</span>` : ''}</span>
            </label>`;
        }
        if (a.tipo === 'choice') {
            control = `<select id="${id}" class="${inputCls}">` +
                Object.entries(a.opciones).map(([v, l]) => `<option value="${esc(v)}" ${v === a.valor ? 'selected' : ''}>${esc(l)}</option>`).join('') +
                `</select>`;
        } else if (a.tipo === 'text') {
            control = `<textarea id="${id}" rows="3" class="${inputCls}">${esc(a.valor)}</textarea>`;
        } else if (a.tipo === 'secret') {
            control = `<input type="password" id="${id}" value="${esc(a.valor)}" autocomplete="new-password" class="${inputCls}"
                        placeholder="${a.cargado ? '' : 'Sin cargar'}">`;
        } else {
            control = `<input type="${a.tipo === 'int' ? 'number' : 'text'}" id="${id}" value="${esc(a.valor)}" class="${inputCls}">`;
        }
        return `
        <div class="py-2" data-clave="${a.clave}">
            <label for="${id}" class="block text-sm font-semibold text-gray-700 mb-1">${esc(a.label)}</label>
            ${control}
            ${a.ayuda ? `<p class="text-xs text-gray-400 mt-1">${esc(a.ayuda)}</p>` : ''}
            <p class="aj-error hidden text-xs text-red-600 mt-1"></p>
        </div>`;
    }

    // Logo del taller: barra superior, pantalla de ingreso y pestaña del navegador
    function bloqueLogo() {
        const m = window.Barra?.datosMarca() || {};
        return `
        <div class="py-2 flex items-start gap-4">
            <div id="aj-logo-prev" class="w-16 h-16 rounded-xl border border-gray-200 bg-gray-50 flex items-center justify-center overflow-hidden text-gray-300 shrink-0">
                ${m.logo ? `<img src="/config/logo?v=${m.logo}" alt="" class="w-full h-full object-contain">` : icono('imagen', 'w-7 h-7')}</div>
            <div class="min-w-0">
                <p class="text-sm font-semibold text-gray-700">Logo del taller</p>
                <p class="text-xs text-gray-400 mt-0.5">PNG, JPG o WEBP de hasta 2 MB (mejor cuadrado). Se ve en la barra superior, la pantalla de ingreso y la pestaña del navegador.</p>
                <div class="flex flex-wrap gap-2 mt-2">
                    <label class="text-sm font-semibold border border-blue-200 text-blue-600 hover:bg-blue-50 px-3 py-1.5 rounded-lg transition cursor-pointer">
                        ${icono('subir', 'w-4 h-4 mr-1.5')}${m.logo ? 'Cambiar logo' : 'Subir logo'}
                        <input type="file" id="aj-logo-input" accept="image/png,image/jpeg,image/webp" class="sr-only"></label>
                    ${m.logo ? '<button type="button" id="aj-logo-quitar" class="text-sm font-semibold text-red-600 hover:text-red-800 px-2 py-1.5">Quitar</button>' : ''}
                </div>
            </div>
        </div>`;
    }

    async function subirLogo(archivo) {
        if (!archivo) return;
        if (archivo.size > 2 * 1024 * 1024) { toast.error('El logo puede pesar hasta 2 MB.'); return; }
        const form = new FormData();
        form.append('archivo', archivo);
        const res = await fetch('/config/logo', { method: 'PUT', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }, body: form });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { toast.error(data.detail || 'No se pudo subir el logo.'); return; }
        await window.Barra?.marca();
        render();
        toast.success('Logo actualizado.');
    }

    async function quitarLogo() {
        try {
            await api.request('config/logo', { method: 'DELETE' });
            await window.Barra?.marca();
            render();
            toast.success('Logo quitado.');
        } catch (e) { toast.error(e.message); }
    }

    function render() {
        const cont = document.getElementById('ajustes-form');
        if (!cont) return;
        cont.innerHTML = GRUPOS.map(g => {
            const items = _items.filter(a => a.grupo === g.id);
            if (!items.length) return '';
            const extra = g.id === 'general' ? `
                <div class="pt-3 mt-2 border-t border-gray-100">
                    <button type="button" id="aj-guia-btn" class="text-sm font-semibold text-blue-600 hover:text-blue-800">Mostrar la guía de primer uso en el panel</button>
                </div>` : g.id === 'impresion' ? `
                <div class="pt-3 mt-2 border-t border-gray-100 flex flex-wrap gap-2">
                    <button type="button" id="aj-prueba-etiqueta" class="text-sm font-semibold border border-blue-200 text-blue-600 hover:bg-blue-50 px-3 py-2 rounded-lg transition">${icono('etiqueta', 'w-4 h-4 mr-1.5')}Etiqueta de prueba</button>
                    <button type="button" id="aj-prueba-ticket" class="text-sm font-semibold border border-blue-200 text-blue-600 hover:bg-blue-50 px-3 py-2 rounded-lg transition">${icono('recibo', 'w-4 h-4 mr-1.5')}Comprobante de prueba</button>
                    <p class="w-full text-xs text-gray-400">Con datos de ejemplo, para revisar tamaño y lectura del código de barras. Guardá los cambios antes de probar.</p>
                </div>` : g.id === 'email' ? `
                <div class="pt-3 mt-2 border-t border-gray-100 flex flex-wrap items-center gap-2">
                    <input type="email" id="aj-test-dest" value="${esc(_destinoPrueba)}" placeholder="Mail de destino para la prueba" class="${inputCls} max-w-xs">
                    <button type="button" id="aj-test-btn" class="text-sm font-semibold border border-blue-200 text-blue-600 hover:bg-blue-50 px-3 py-2 rounded-lg transition">Enviar mail de prueba</button>
                    <span id="aj-test-res" class="text-xs"></span>
                    <p class="w-full text-xs text-gray-400">La prueba usa la configuración guardada: guardá los cambios antes de probar.</p>
                    <p id="aj-email-estado" class="w-full text-xs"></p>
                </div>` : '';
            return `
            <section class="bg-white rounded-2xl shadow border border-gray-100 overflow-hidden" data-grupo="${g.id}">
                <div class="p-5 border-b bg-gray-50">
                    <h3 class="font-bold text-gray-800">${g.titulo}</h3>
                    <p class="text-xs text-gray-400 mt-0.5">${g.desc}</p>
                </div>
                <div class="px-5 py-3">${g.id === 'general' ? bloqueLogo() : ''}${items.map(campo).join('')}${extra}</div>
            </section>`;
        }).join('');
        toggleSmtp();
        estadoEmail();
        document.getElementById('aj-smtp_origen')?.addEventListener('change', toggleSmtp);
        document.getElementById('aj-test-btn')?.addEventListener('click', probarEmail);
        document.getElementById('aj-prueba-etiqueta')?.addEventListener('click', () => Documentos.abrirUrl('/tickets/impresion-prueba/etiqueta'));
        document.getElementById('aj-prueba-ticket')?.addEventListener('click', () => Documentos.abrirUrl('/tickets/impresion-prueba/ticket_ingreso'));
        document.getElementById('aj-guia-btn')?.addEventListener('click', async () => {
            try {
                await api.request('config/guia', { method: 'PUT', body: JSON.stringify({ oculta: false }) });
                toast.success('Listo: la guía vuelve a aparecer en el panel de control (si quedan pasos por hacer).');
            } catch (e) { toast.error(e.message); }
        });
        document.getElementById('aj-test-dest')?.addEventListener('input', e => { _destinoPrueba = e.target.value; });
        document.getElementById('aj-logo-input')?.addEventListener('change', e => subirLogo(e.target.files[0]));
        document.getElementById('aj-logo-quitar')?.addEventListener('click', quitarLogo);
    }

    function toggleSmtp() {
        const panel = document.getElementById('aj-smtp_origen')?.value === 'panel';
        SMTP_PANEL.forEach(c => document.querySelector(`[data-clave="${c}"]`)?.classList.toggle('hidden', !panel));
    }

    function valores() {
        const out = {};
        for (const a of _items) {
            const el = document.getElementById(`aj-${a.clave}`);
            if (!el) continue;
            const v = a.tipo === 'bool' ? el.checked : (a.tipo === 'int' ? el.value.trim() : el.value);
            if (String(v) !== String(a.valor)) out[a.clave] = v;
        }
        return out;
    }

    async function guardar() {
        document.querySelectorAll('#ajustes-form .aj-error').forEach(e => { e.textContent = ''; e.classList.add('hidden'); });
        const cambios = valores();
        if (!Object.keys(cambios).length) { toast.info('No hay cambios para guardar.'); return; }
        const token = localStorage.getItem('token');
        const res = await fetch('/config/ajustes', {
            method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify(cambios),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const errores = data.detail?.errores || {};
            Object.entries(errores).forEach(([clave, msg]) => {
                const e = document.querySelector(`[data-clave="${clave}"] .aj-error`);
                if (e) { e.textContent = msg; e.classList.remove('hidden'); }
            });
            toast.error(data.detail?.mensaje || (typeof data.detail === 'string' ? data.detail : 'No se pudieron guardar los ajustes.'));
            return;
        }
        _items = data;
        if ('empresa_nombre' in cambios || 'registro_publico' in cambios) await window.Barra?.marca();
        render();
        toast.success('Ajustes guardados.');
    }

    async function probarEmail() {
        const dest = document.getElementById('aj-test-dest')?.value.trim();
        _destinoPrueba = dest || '';
        const out = document.getElementById('aj-test-res');
        if (!dest) { toast.warning('Ingresá un mail de destino.'); return; }
        out.textContent = 'Enviando…'; out.className = 'text-xs text-gray-500';
        try {
            const r = await api.request('config/email/prueba', { method: 'POST', body: JSON.stringify({ destino: dest }) });
            out.textContent = r.mensaje || 'Enviado.'; out.className = 'text-xs text-green-600 font-semibold';
        } catch (e) {
            out.textContent = e.message; out.className = 'text-xs text-red-600 font-semibold';
        }
        estadoEmail();
    }

    async function estadoEmail() {
        const el = document.getElementById('aj-email-estado');
        if (!el) return;
        try {
            const e = await api.request('config/email/estado');
            const f = iso => new Date(iso).toLocaleString(I18N.locale, { hour12: false });
            const errorReciente = e.ultimo_error && (!e.ultimo_ok || e.ultimo_error_fecha > e.ultimo_ok);
            el.innerHTML = errorReciente
                ? `<span class="text-red-600 font-semibold">Último envío fallido (${f(e.ultimo_error_fecha)}): ${esc(e.ultimo_error)}</span>`
                : e.ultimo_ok ? `<span class="text-green-600">Último mail enviado: ${f(e.ultimo_ok)}</span>` : '';
        } catch { el.textContent = ''; }
    }

    async function cargar() {
        const cont = document.getElementById('ajustes-form');
        if (cont) cont.innerHTML = '<p class="text-gray-400 italic text-sm p-4">Cargando…</p>';
        try {
            _items = await api.request('config/ajustes');
            render();
        } catch (e) { toast.error(e.message); }
    }

    return { cargar, guardar };
})();
window.Ajustes = Ajustes;
