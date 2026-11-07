/**
 * recepcion.js — Ingreso en mostrador y recepción del equipo.
 *
 * - Pantalla "Ingreso en mostrador": cliente (existente o nuevo, sin clave),
 *   equipo, checklist, fotos y firma; al terminar, etiqueta y comprobante.
 * - Tarjeta "Recepción" en el detalle del ticket: checklist, firmas de ingreso
 *   y de entrega, fotos de ingreso.
 * - Lector de código de barras: escanear la etiqueta abre el ticket.
 */
const Recepcion = (() => {
    const ACCESORIOS = ['Cargador', 'Cable', 'Caja', 'Funda', 'Batería', 'Control remoto', 'Tarjeta de memoria', 'Chip / SIM'];
    const RMA_RE = /^RMA-\d{4}-[A-Z]{4}\d{3}$/i;
    const esTaller = () => ['administrador', 'tecnico'].includes(auth.getUser()?.role || '');

    // ── Checklist ────────────────────────────────────────────────────────────
    function triEstado(nombre, titulo, valor, opciones) {
        const v = valor === true ? 'si' : valor === false ? 'no' : '';
        return `
        <fieldset>
            <legend class="block text-sm font-semibold mb-1">${titulo}</legend>
            <div class="flex flex-wrap gap-2">
                ${opciones.map(([val, txt]) => `
                <label class="flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-sm cursor-pointer has-[:checked]:bg-blue-50 has-[:checked]:border-blue-400">
                    <input type="radio" name="${nombre}" value="${val}" ${v === val ? 'checked' : ''}> ${txt}
                </label>`).join('')}
            </div>
        </fieldset>`;
    }

    /** Dibuja el checklist en `cont` y devuelve una función que lo lee. */
    function checklistForm(cont, c = {}) {
        const id = 'chk' + Math.random().toString(36).slice(2, 7);
        const elegidos = new Set(c.accesorios || []);
        const extras = [...elegidos].filter(a => !ACCESORIOS.includes(a));
        cont.innerHTML = `
        <div class="space-y-4">
            <fieldset>
                <legend class="block text-sm font-semibold mb-1">Accesorios que deja</legend>
                <div class="flex flex-wrap gap-2">
                    ${ACCESORIOS.map(a => `
                    <label class="flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-sm cursor-pointer has-[:checked]:bg-blue-50 has-[:checked]:border-blue-400">
                        <input type="checkbox" data-acc value="${esc(a)}" ${elegidos.has(a) ? 'checked' : ''}> ${esc(a)}
                    </label>`).join('')}
                </div>
                <input type="text" data-campo="accesorios_otros" maxlength="500" placeholder="Otros (ej. mouse, lápiz, correa)"
                    value="${esc([c.accesorios_otros, ...extras].filter(Boolean).join(', '))}"
                    class="mt-2 w-full px-4 py-2 border rounded-lg outline-none focus:ring-2 focus:ring-blue-500 text-sm">
            </fieldset>
            <div>
                <label class="block text-sm font-semibold mb-1" for="${id}-estado">Estado físico</label>
                <textarea id="${id}-estado" data-campo="estado_fisico" rows="2" maxlength="500" placeholder="Rayones, golpes, pantalla, tornillos faltantes…"
                    class="w-full px-4 py-2 border rounded-lg outline-none focus:ring-2 focus:ring-blue-500 text-sm">${esc(c.estado_fisico || '')}</textarea>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                ${triEstado(id + '-enciende', '¿Enciende?', c.enciende, [['si', 'Sí'], ['no', 'No'], ['', 'No se probó']])}
                ${triEstado(id + '-bloqueo', '¿Tiene contraseña o patrón?', c.tiene_bloqueo, [['si', 'Sí'], ['no', 'No'], ['', 'No sabe']])}
            </div>
            <p class="text-xs text-gray-400">La clave de desbloqueo no se guarda: si el técnico la necesita, se la pide al cliente.</p>
        </div>`;
        const radio = n => {
            const v = cont.querySelector(`input[name="${id}-${n}"]:checked`)?.value ?? '';
            return v === 'si' ? true : v === 'no' ? false : null;
        };
        return () => ({
            accesorios: [...cont.querySelectorAll('input[data-acc]:checked')].map(i => i.value),
            accesorios_otros: cont.querySelector('[data-campo="accesorios_otros"]').value.trim(),
            estado_fisico: cont.querySelector('[data-campo="estado_fisico"]').value.trim(),
            enciende: radio('enciende'),
            tiene_bloqueo: radio('bloqueo'),
        });
    }

    function checklistTexto(c) {
        if (!c) return [];
        const siNo = (v, nada) => v === true ? 'Sí' : v === false ? 'No' : nada;
        const acc = [...(c.accesorios || []), c.accesorios_otros].filter(Boolean);
        return [
            ['Accesorios', acc.join(', ') || 'Ninguno'],
            ['Estado físico', c.estado_fisico || 'Sin observaciones'],
            ['Enciende', siNo(c.enciende, 'No se probó')],
            ['Bloqueo', c.tiene_bloqueo === true ? 'Sí (se pide la clave si hace falta)' : siNo(c.tiene_bloqueo, 'No informado')],
        ];
    }

    // ── Firma en pantalla ────────────────────────────────────────────────────
    /** Recuadro para firmar con el dedo, lápiz o mouse. */
    function firmaPad(cont, { aclaracion = '' } = {}) {
        cont.innerHTML = `
        <div class="relative border-2 border-dashed border-gray-300 rounded-lg bg-white">
            <canvas class="block w-full rounded-lg cursor-crosshair" style="height: 180px; touch-action: none;" aria-label="Recuadro para firmar"></canvas>
            <span data-ph class="pointer-events-none absolute inset-0 flex items-center justify-center text-gray-300 text-sm">Firmá acá</span>
            <div class="pointer-events-none absolute left-6 right-6 bottom-8 border-b border-gray-200"></div>
        </div>
        <div class="flex flex-wrap items-center gap-3 mt-2">
            <input type="text" data-aclaracion maxlength="120" placeholder="Aclaración (nombre de quien firma)" value="${esc(aclaracion)}"
                class="flex-1 min-w-[200px] px-4 py-2 border rounded-lg outline-none focus:ring-2 focus:ring-blue-500 text-sm">
            <button type="button" data-limpiar class="text-sm font-semibold text-gray-500 hover:text-gray-700 px-3 py-2">Borrar firma</button>
        </div>`;
        const canvas = cont.querySelector('canvas');
        const ph = cont.querySelector('[data-ph]');
        const ctx = canvas.getContext('2d');
        let trazos = 0, dibujando = false, ultimo = null, largo = 0;

        function dimensionar() {
            const w = canvas.clientWidth, h = canvas.clientHeight;
            if (!w) return;
            const escala = Math.min(window.devicePixelRatio || 1, 1900 / w);   // el servidor acepta hasta 2000 px
            canvas.width = Math.round(w * escala);
            canvas.height = Math.round(h * escala);
            ctx.setTransform(escala, 0, 0, escala, 0, 0);
            ctx.lineWidth = 2.6; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#111';
        }
        const punto = e => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
        canvas.addEventListener('pointerdown', e => {
            if (!canvas.width) dimensionar();
            dibujando = true; ultimo = punto(e);
            canvas.setPointerCapture(e.pointerId);
            ctx.beginPath(); ctx.arc(ultimo[0], ultimo[1], 1.2, 0, Math.PI * 2); ctx.fillStyle = '#111'; ctx.fill();
            trazos++; ph.classList.add('hidden');
        });
        canvas.addEventListener('pointermove', e => {
            if (!dibujando) return;
            const p = punto(e);
            ctx.beginPath(); ctx.moveTo(...ultimo); ctx.lineTo(...p); ctx.stroke();
            largo += Math.hypot(p[0] - ultimo[0], p[1] - ultimo[1]);
            ultimo = p;
        });
        const fin = () => { dibujando = false; };
        canvas.addEventListener('pointerup', fin);
        canvas.addEventListener('pointercancel', fin);
        // Si cambia el ancho (rotar el celular) y todavía no firmó, se reajusta
        window.addEventListener('resize', () => { if (!trazos) dimensionar(); });
        const limpiar = () => { ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.restore(); trazos = 0; largo = 0; ph.classList.remove('hidden'); cont.dispatchEvent(new Event('firma-borrada')); };
        cont.querySelector('[data-limpiar]').addEventListener('click', limpiar);
        requestAnimationFrame(dimensionar);
        return {
            vacia: () => trazos === 0,
            corta: () => trazos > 0 && largo < 60,   // un toque o un punto no es una firma
            datos: () => ({ imagen: canvas.toDataURL('image/png'), aclaracion: cont.querySelector('[data-aclaracion]').value.trim() }),
            limpiar,
        };
    }

    async function imagenFirma(ticketId, momento) {
        const res = await fetch(`/tickets/${ticketId}/firmas/${momento}/imagen`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        });
        return res.ok ? URL.createObjectURL(await res.blob()) : null;
    }

    // ── Fotos (se achican antes de subir) ─────────────────────────────────────
    async function reducirFoto(file, lado = 1600) {
        try {
            const bmp = await createImageBitmap(file);
            const k = Math.min(1, lado / Math.max(bmp.width, bmp.height));
            const c = document.createElement('canvas');
            c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
            c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
            const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.82));
            const nombre = (file.name || 'foto').replace(/\.[^.]+$/, '') + '.jpg';
            return new File([blob], nombre, { type: 'image/jpeg' });
        } catch {
            return file;   // si el navegador no la puede leer, se sube tal cual (el servidor valida)
        }
    }

    function subirFoto(ticketId, file) {
        const form = new FormData();
        form.append('file', file);
        form.append('categoria', 'ingreso');
        return fetch(`/tickets/${ticketId}/attachments`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }, body: form,
        }).then(async r => {
            if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || 'No se pudo subir la foto'); }
            return r.json();
        });
    }

    // ── Pantalla de ingreso en mostrador ─────────────────────────────────────
    let _estado = null;

    /** Cierra el modal del mostrador; si se registró un ingreso, refresca el listado de atrás. */
    function cerrarMostrador() {
        document.getElementById('mostrador-modal')?.remove();
        document.body.classList.remove('overflow-hidden');
        if (_estado?.ticket && document.getElementById('dashboard-section')) ui.initDashboard();
    }

    async function abrirMostrador() {
        // Modal sobre la pantalla actual (como "Nuevo ticket"): al cerrarlo se vuelve a donde estaba
        document.getElementById('mostrador-modal')?.remove();
        let html;
        try { html = await ui.loadPartial('mostrador'); } catch (e) { toast.error(e.message); return; }
        const overlay = document.createElement('div');
        overlay.id = 'mostrador-modal';
        overlay.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-start sm:items-center justify-center z-50 sm:p-4';
        overlay.innerHTML = `<div role="dialog" aria-modal="true" aria-labelledby="mostrador-titulo"
            class="bg-gray-50 w-full sm:max-w-3xl h-full sm:h-auto sm:max-h-[92vh] overflow-y-auto sm:rounded-2xl shadow-2xl px-4 sm:px-6 pb-4 sm:pb-6">${html}</div>`;
        document.body.appendChild(overlay);
        document.body.classList.add('overflow-hidden');
        overlay.querySelector('h2')?.setAttribute('id', 'mostrador-titulo');
        const caja = overlay.firstElementChild;
        const $ = id => document.getElementById(id);
        _estado = { cliente: null, fotos: [], ticket: null };
        const leerChecklist = checklistForm($('ing-checklist'));
        const pad = firmaPad($('ing-firma'));

        // Productos
        try {
            const productos = await api.getProducts();
            $('ing-producto').innerHTML = '<option value="">Elegí un producto…</option>'
                + productos.map(p => `<option value="${p.id}">${esc(`${p.marca} ${p.modelo} (${p.categoria})`)}</option>`).join('');
        } catch (e) { toast.error('No se pudieron cargar los productos: ' + e.message); }

        // Cliente: buscar / elegir / nuevo
        const modo = m => {
            $('ing-cli-busqueda').classList.toggle('hidden', m !== 'buscar');
            $('ing-cli-elegido').classList.toggle('hidden', m !== 'elegido');
            $('ing-cli-elegido').classList.toggle('flex', m === 'elegido');
            $('ing-cli-nuevo').classList.toggle('hidden', m !== 'nuevo');
            // Al cambiar de modo, los errores del modo anterior ya no aplican
            ['ing-cli-buscar', 'ing-cli-nombre', 'ing-cli-telefono', 'ing-cli-email'].forEach(id => marcar(id, ''));
            // Foco inmediato (con demora, lo que se empieza a tipear podía ir al campo equivocado)
            if (m === 'buscar') { _estado.cliente = null; $('ing-cli-buscar').focus(); }
            if (m === 'nuevo') { _estado.cliente = null; $('ing-cli-nombre').focus(); }
            _estado.modoCliente = m;
        };
        const elegir = c => {
            _estado.cliente = c;
            $('ing-cli-elegido-nombre').textContent = c.nombre;
            $('ing-cli-elegido-datos').textContent = [c.telefono, c.email, c.tipo_cliente === 'empresa' ? 'Empresa' : null]
                .filter(Boolean).join(' · ') || 'Sin datos de contacto';
            $('ing-cli-resultados').classList.add('hidden');
            modo('elegido');
        };
        let espera;
        $('ing-cli-buscar').addEventListener('input', e => {
            clearTimeout(espera);
            const q = e.target.value.trim();
            const res = $('ing-cli-resultados');
            if (q.length < 2) { res.classList.add('hidden'); return; }
            espera = setTimeout(async () => {
                try {
                    const lista = await api.request(`mostrador/clientes?q=${encodeURIComponent(q)}`);
                    res.innerHTML = lista.length ? lista.map((c, i) => `
                        <button type="button" data-i="${i}" class="w-full text-left px-4 py-2.5 hover:bg-gray-50 border-b last:border-0">
                            <span class="font-semibold text-gray-800">${esc(c.nombre)}</span>
                            <span class="block text-xs text-gray-500">${esc([c.telefono, c.email].filter(Boolean).join(' · ') || c.username)}</span>
                        </button>`).join('')
                        : `<div class="px-4 py-3 text-sm text-gray-500">No hay clientes con “${esc(q)}”.
                             <button type="button" data-nuevo class="font-semibold text-blue-600 hover:text-blue-800">Cargarlo como nuevo</button></div>`;
                    res.querySelectorAll('[data-i]').forEach(b => b.addEventListener('click', () => elegir(lista[+b.dataset.i])));
                    res.querySelector('[data-nuevo]')?.addEventListener('click', () => {
                        res.classList.add('hidden');
                        modo('nuevo');
                        // Lo que se buscó va al campo que corresponde
                        if (q.includes('@')) $('ing-cli-email').value = q;
                        else if (/^[+\d\s().-]{6,}$/.test(q)) $('ing-cli-telefono').value = q;
                        else $('ing-cli-nombre').value = q;
                    });
                    res.classList.remove('hidden');
                } catch (err) { toast.error(err.message); }
            }, 250);
        });
        $('ing-cli-nuevo-btn').addEventListener('click', () => modo('nuevo'));
        $('ing-cli-buscar-btn').addEventListener('click', () => modo('buscar'));
        $('ing-cli-cambiar').addEventListener('click', () => { $('ing-cli-buscar').value = ''; modo('buscar'); });
        modo('buscar');

        // Fotos
        const pintarFotos = () => {
            $('ing-fotos-lista').innerHTML = _estado.fotos.map((f, i) => `
                <div class="relative w-24 h-24 rounded-lg overflow-hidden border">
                    <img src="${f.url}" alt="Foto ${i + 1}" class="w-full h-full object-cover">
                    <button type="button" data-quitar="${i}" class="absolute top-1 right-1 bg-black/60 text-white rounded-full w-6 h-6 text-xs" aria-label="Quitar foto">✕</button>
                </div>`).join('');
            $('ing-fotos-lista').querySelectorAll('[data-quitar]').forEach(b => b.addEventListener('click', () => {
                URL.revokeObjectURL(_estado.fotos[+b.dataset.quitar].url);
                _estado.fotos.splice(+b.dataset.quitar, 1);
                pintarFotos();
            }));
        };
        $('ing-fotos-btn').addEventListener('click', () => $('ing-fotos').click());
        $('ing-fotos').addEventListener('change', async e => {
            const archivos = [...(e.target.files || [])];
            e.target.value = '';
            for (const f of archivos) {
                const chica = await reducirFoto(f);
                _estado.fotos.push({ file: chica, url: URL.createObjectURL(chica) });
            }
            pintarFotos();
        });

        // Volver / cancelar
        const salir = async () => {
            const hayDatos = _estado.cliente || $('ing-serie').value || $('ing-descripcion').value || _estado.fotos.length || !pad.vacia();
            if (!_estado.ticket && hayDatos && !(await confirmDialog('¿Descartar el ingreso?', 'Se pierden los datos cargados.', 'Sí, descartar',
                                                                     { cancelLabel: 'Seguir cargando' }))) return;
            cerrarMostrador();
        };
        $('mostrador-cerrar').addEventListener('click', salir);
        $('mostrador-cancelar').addEventListener('click', salir);

        // ── Validación ────────────────────────────────────────────────────
        // Cada problema se marca debajo de su campo (y se revisa al salir de él);
        // al registrar se revisa todo y se lleva el foco al primer error.
        const hoy = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
        $('ing-compra').max = hoy();
        const SERIE = /^[A-Za-z0-9][A-Za-z0-9 ._/\-#]{1,48}[A-Za-z0-9]$/;
        const EMAIL = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;
        const digitos = t => t.replace(/\D/g, '');
        const tocados = new Set();

        function marcar(id, mensaje) {
            const el = $(id);
            if (!el) return;
            const ancla = el.closest('[data-campo-wrap]') || el;
            let p = document.getElementById(`${id}-error`);
            el.classList.toggle('border-red-500', !!mensaje);
            el.classList.toggle('ring-1', !!mensaje);
            el.classList.toggle('ring-red-500', !!mensaje);
            if (mensaje) {
                el.setAttribute('aria-invalid', 'true');
                if (!p) {
                    p = document.createElement('p');
                    p.id = `${id}-error`; p.className = 'text-xs font-semibold text-red-600 mt-1'; p.setAttribute('role', 'alert');
                    ancla.insertAdjacentElement('afterend', p);
                    el.setAttribute('aria-describedby', p.id);
                }
                p.textContent = I18N.t(mensaje);
            } else {
                el.removeAttribute('aria-invalid'); el.removeAttribute('aria-describedby');
                p?.remove();
            }
        }

        // Cada regla devuelve el mensaje de error (o '' si está bien)
        const reglas = {
            'ing-cli-buscar': () => _estado.modoCliente === 'buscar' && !_estado.cliente
                ? 'Elegí un cliente de la lista o cargalo como nuevo.' : '',
            'ing-cli-nombre': () => {
                if (_estado.modoCliente !== 'nuevo') return '';
                const v = $('ing-cli-nombre').value.trim();
                if (!v) return 'Falta el nombre del cliente.';
                if (v.length < 2 || !/\p{L}.*\p{L}|\p{L}{2}/u.test(v)) return 'El nombre tiene que tener al menos 2 letras.';
                return '';
            },
            'ing-cli-telefono': () => {
                if (_estado.modoCliente !== 'nuevo') return '';
                const v = $('ing-cli-telefono').value.trim();
                if (!v) return $('ing-cli-email').value.trim() ? '' : 'Cargá un teléfono o un email para avisarle.';
                if (!/^\+?[\d\s().-]+$/.test(v)) return 'Usá solo números (y + al inicio si es internacional).';
                const n = digitos(v).length;
                if (n < 8 || n > 15) return 'Tiene que tener entre 8 y 15 números, con código de área (ej: 11 5555-1234).';
                return '';
            },
            'ing-cli-email': () => {
                if (_estado.modoCliente !== 'nuevo') return '';
                const v = $('ing-cli-email').value.trim();
                return v && !EMAIL.test(v) ? 'Email inválido (ej: nombre@ejemplo.com).' : '';
            },
            'ing-producto': () => $('ing-producto').value ? '' : 'Elegí el producto.',
            'ing-serie': () => {
                const v = $('ing-serie').value.trim().replace(/\s+/g, ' ');
                if (!v) return 'Falta el N° de serie.';
                if (v.length < 3) return 'El N° de serie es muy corto (mínimo 3 caracteres).';
                if (!SERIE.test(v)) return 'Usá letras, números, espacios, puntos, guiones o barras (sin símbolos al principio o al final).';
                return '';
            },
            'ing-compra': () => {
                const v = $('ing-compra').value;
                if (!v) return 'Falta la fecha de compra (si no la sabe, una aproximada).';
                if (v > hoy()) return 'La fecha de compra no puede ser futura.';
                if (v < '1990-01-01') return 'La fecha de compra es demasiado vieja: revisala.';
                return '';
            },
            'ing-descripcion': () => {
                const v = $('ing-descripcion').value.trim();
                if (!v) return 'Falta la falla que informa el cliente.';
                if (v.length < 5) return 'Describí la falla con un poco más de detalle.';
                return '';
            },
            'ing-fotos-btn': () => _estado.fotos.length > 10 ? 'Máximo 10 fotos: quitá alguna.' : '',
            'ing-firma-aclaracion': () => {
                const acl = $('ing-firma-aclaracion').value.trim();
                if (!pad.vacia() && pad.corta()) return 'La firma es muy corta: pedile que firme de nuevo.';
                if (!pad.vacia() && !acl) return 'Escribí la aclaración (nombre de quien firma).';
                if (pad.vacia() && acl) return 'Falta la firma (o borrá la aclaración).';
                return '';
            },
        };
        $('ing-firma').querySelector('[data-aclaracion]').id = 'ing-firma-aclaracion';
        $('ing-fotos-btn').setAttribute('data-campo-wrap', '');

        // Lo que rechazó el servidor (p. ej. teléfono ya usado) sigue marcado hasta que se cambie ese valor
        const delServidor = {};
        const revisar = id => {
            let m = reglas[id]();
            const s = delServidor[id];
            if (!m && s) { if ($(id)?.value === s.valor) m = s.mensaje; else delete delServidor[id]; }
            marcar(id, m);
            return m;
        };
        const revisarTodo = () => Object.keys(reglas).filter(id => revisar(id));
        // Al salir de un campo se revisa lo que se escribió (formato, largo…). Que esté
        // vacío se avisa recién al intentar registrar: si no, ir a tocar "Cliente nuevo"
        // ya mostraba un error. Y se muestra un instante después, cuando el click que
        // sacó el foco ya terminó: si el error aparece antes, empuja el botón y el click se pierde.
        const alSalir = id => setTimeout(() => {
            const el = $(id);
            if (!el?.isConnected || el.closest('.hidden')) return;
            const vacio = !(el.value || '').trim() && id !== 'ing-firma-aclaracion';
            if (vacio && !_estado.intentado) return;
            tocados.add(id); revisar(id);
        }, 200);
        Object.keys(reglas).forEach(id => {
            const el = $(id);
            if (!el || id === 'ing-cli-buscar') return;   // la búsqueda se revisa solo al registrar
            el.addEventListener('blur', () => alSalir(id));
            el.addEventListener('input', () => { if (tocados.has(id) || el.getAttribute('aria-invalid')) revisar(id); });
            el.addEventListener('change', () => { if (tocados.has(id) || el.getAttribute('aria-invalid')) revisar(id); });
        });
        // teléfono y email se exigen uno u otro: revisar los dos juntos
        ['ing-cli-telefono', 'ing-cli-email'].forEach(id => $(id).addEventListener('blur', () => setTimeout(() => {
            if (tocados.has('ing-cli-telefono') || tocados.has('ing-cli-email')) { revisar('ing-cli-telefono'); revisar('ing-cli-email'); }
        }, 220)));
        $('ing-firma').querySelector('canvas').addEventListener('pointerup', () => { if (tocados.has('ing-firma-aclaracion')) revisar('ing-firma-aclaracion'); });
        $('ing-firma').addEventListener('firma-borrada', () => marcar('ing-firma-aclaracion', ''));
        $('ing-serie').addEventListener('blur', () => { $('ing-serie').value = $('ing-serie').value.trim().replace(/\s+/g, ' ').toUpperCase(); });

        // ¿El equipo ya está en el taller? (mismo N° de serie)
        let _serieAbiertos = [], _serieConsultada = '';
        async function consultarSerie() {
            const v = $('ing-serie').value.trim();
            const aviso = $('ing-serie-aviso') || (() => {
                const p = document.createElement('p'); p.id = 'ing-serie-aviso'; p.className = 'text-xs mt-1 hidden';
                $('ing-serie').insertAdjacentElement('afterend', p); return p;
            })();
            if (v === _serieConsultada) return;
            _serieConsultada = v; _serieAbiertos = [];
            aviso.classList.add('hidden');
            if (reglas['ing-serie']()) return;
            try {
                const lista = await api.request(`mostrador/serie?numero=${encodeURIComponent(v)}`);
                if (v !== $('ing-serie').value.trim()) return;
                _serieAbiertos = lista.filter(t => t.abierto);
                if (!lista.length) return;
                const t = _serieAbiertos[0] || lista[0];
                aviso.className = `text-xs mt-1 font-semibold ${_serieAbiertos.length ? 'text-amber-700' : 'text-blue-700'}`;
                aviso.textContent = _serieAbiertos.length
                    ? I18N.t('⚠ Este equipo ya tiene un ticket abierto: {0} ({1}, de {2}).', t.numero_rma, I18N.t(t.estado), t.cliente || '—')
                    : I18N.t('Ya pasó por el taller: {0} ({1}). Si vuelve por la misma falla, se marca como reingreso.', t.numero_rma, I18N.t(t.estado));
                aviso.classList.remove('hidden');
            } catch { /* el aviso es una ayuda: si falla, se sigue igual */ }
        }
        $('ing-serie').addEventListener('blur', consultarSerie);

        // Errores que devuelve el servidor → al campo que corresponde
        const CAMPO_DEL_ERROR = [[/tel[eé]fono/i, 'ing-cli-telefono'], [/email/i, 'ing-cli-email'], [/nombre del cliente/i, 'ing-cli-nombre'],
                                 [/serie/i, 'ing-serie'], [/falla/i, 'ing-descripcion'], [/fecha de compra/i, 'ing-compra'],
                                 [/producto/i, 'ing-producto'], [/firma/i, 'ing-firma-aclaracion'], [/cliente/i, 'ing-cli-buscar']];

        // Registrar
        $('mostrador-form').addEventListener('submit', async e => {
            e.preventDefault();
            if (_estado.enviando) return;
            _estado.intentado = true;
            Object.keys(reglas).forEach(id => tocados.add(id));
            const errores = revisarTodo();
            if (errores.length) {
                toast.error(errores.length === 1 ? I18N.t('Revisá el campo marcado.') : I18N.t('Revisá los {0} campos marcados.', errores.length));
                const primero = $(errores[0]);
                primero?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                primero?.focus({ preventScroll: true });
                return;
            }
            await consultarSerie();
            if (_serieAbiertos.length) {
                const t = _serieAbiertos[0];
                const seguir = await confirmDialog(I18N.t('Este equipo ya está en el taller'),
                    I18N.t('El N° de serie tiene abierto el {0} ({1}). ¿Registrar igual un ingreso nuevo?', t.numero_rma, I18N.t(t.estado)),
                    I18N.t('Registrar igual'), { peligro: false, cancelLabel: I18N.t('Revisar') });
                if (!seguir) { $('ing-serie').focus(); return; }
            }
            const prod = $('ing-producto');
            let cliente;
            if (_estado.modoCliente === 'elegido') cliente = { cliente_id: _estado.cliente.id };
            else cliente = { cliente_nuevo: {
                nombre: $('ing-cli-nombre').value.trim().replace(/\s+/g, ' '), telefono: $('ing-cli-telefono').value.trim(),
                email: $('ing-cli-email').value.trim(), tipo_cliente: $('ing-cli-tipo').value } };

            const cuerpo = {
                ...cliente,
                ticket: {
                    producto_id: parseInt(prod.value), producto: prod.options[prod.selectedIndex].text,
                    numero_serie: $('ing-serie').value.trim().replace(/\s+/g, ' '), fecha_compra: $('ing-compra').value + 'T00:00:00',
                    descripcion: $('ing-descripcion').value.trim(), prioridad: $('ing-prioridad').value,
                },
                checklist: leerChecklist(),
                firma: pad.vacia() ? null : pad.datos(),
            };
            _estado.enviando = true;
            ui.setLoading('mostrador-submit', true);
            try {
                const t = await api.request('mostrador/ingreso', { method: 'POST', body: JSON.stringify(cuerpo) });
                _estado.ticket = t;
                const fallidas = [];
                for (const f of _estado.fotos) {
                    try { await subirFoto(t.id, f.file); } catch (err) { fallidas.push(err.message); }
                }
                $('mostrador-form').classList.add('hidden');
                $('mostrador-listo').classList.remove('hidden');
                $('mostrador-listo-rma').textContent = t.numero_rma;
                $('mostrador-listo-cliente').textContent = `${t.usuario_nombre} · ${t.producto} · SN ${t.numero_serie}`;
                if (fallidas.length) {
                    $('mostrador-listo-aviso').textContent = `No se pudieron subir ${fallidas.length} foto(s): ${fallidas[0]}. Podés subirlas desde el ticket.`;
                    $('mostrador-listo-aviso').classList.remove('hidden');
                }
                caja.scrollTo({ top: 0, behavior: 'smooth' });
            } catch (err) {
                const campo = CAMPO_DEL_ERROR.find(([rx]) => rx.test(err.message))?.[1];
                if (campo && $(campo) && !$(campo).closest('.hidden')) {
                    delServidor[campo] = { valor: $(campo).value, mensaje: err.message };
                    marcar(campo, err.message);
                    $(campo).scrollIntoView({ behavior: 'smooth', block: 'center' });
                    $(campo).focus({ preventScroll: true });
                }
                toast.error(err.message);
            } finally {
                _estado.enviando = false;
                ui.setLoading('mostrador-submit', false);
            }
        });
        document.querySelectorAll('.mostrador-doc').forEach(b =>
            b.addEventListener('click', () => Documentos.abrir(_estado.ticket.id, b.dataset.doc)));
        $('mostrador-abrir').addEventListener('click', async () => {
            const t = await api.getTicket(_estado.ticket.id);
            _estado.ticket = null;   // no hace falta refrescar el listado: se va al detalle
            cerrarMostrador();
            ui.showTicketDetail(t);
        });
        $('mostrador-otro').addEventListener('click', () => { cerrarMostrador(); abrirMostrador(); });
    }

    // ── Modal simple ─────────────────────────────────────────────────────────
    function modal(titulo, html, { guardar = 'Guardar' } = {}) {
        const div = document.createElement('div');
        div.className = 'fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4';
        div.innerHTML = `
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[92vh] overflow-y-auto" role="dialog" aria-modal="true">
            <div class="flex items-center justify-between px-6 py-4 border-b">
                <h3 class="font-bold text-gray-800">${esc(titulo)}</h3>
                <button type="button" data-cerrar class="text-gray-400 hover:text-gray-600 text-2xl leading-none" aria-label="Cerrar">×</button>
            </div>
            <div class="p-6" data-cuerpo>${html}</div>
            <div class="flex justify-end gap-3 px-6 pb-6">
                <button type="button" data-cerrar class="px-5 py-2 text-gray-500 font-semibold hover:text-gray-700">Cancelar</button>
                <button type="button" data-guardar class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-bold">${esc(guardar)}</button>
            </div>
        </div>`;
        document.body.appendChild(div);
        const cerrar = () => div.remove();
        div.querySelectorAll('[data-cerrar]').forEach(b => b.addEventListener('click', cerrar));
        return { div, cuerpo: div.querySelector('[data-cuerpo]'), boton: div.querySelector('[data-guardar]'), cerrar };
    }

    // ── Tarjeta "Recepción" del detalle ──────────────────────────────────────
    async function cargarDetalle(ticket) {
        const card = document.getElementById('recepcion-card');
        if (!card) return;
        const taller = esTaller();
        const firmas = Object.fromEntries((ticket.firmas || []).map(f => [f.momento, f]));
        const lineas = checklistTexto(ticket.checklist_ingreso);
        if (!taller && !lineas.length && !ticket.firmas?.length) { card.classList.add('hidden'); return; }
        const bloqueFirma = (momento, titulo) => {
            const f = firmas[momento];
            return `
            <div class="flex-1 min-w-[180px] border border-gray-100 rounded-lg p-3 bg-white">
                <p class="text-[10px] uppercase tracking-wide font-bold text-gray-400 mb-1">${titulo}</p>
                ${f ? `<img data-firma="${momento}" alt="Firma de ${titulo.toLowerCase()}" class="h-12 max-w-full object-contain">
                       <p class="text-xs text-gray-500 mt-1">${esc(f.aclaracion || '')} · ${new Date(f.fecha).toLocaleString(I18N.locale, { hour12: false })}</p>`
                    : '<p class="text-xs text-gray-400 italic">Sin firma</p>'}
                ${taller ? `<button type="button" data-firmar="${momento}" class="mt-2 text-xs font-semibold text-blue-600 hover:text-blue-800">✍️ ${f ? 'Volver a firmar' : 'Firmar ahora'}</button>` : ''}
            </div>`;
        };
        card.innerHTML = `
        <div class="bg-gray-50 border border-gray-100 p-4 rounded-lg">
            <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                <h3 class="text-gray-600 font-bold text-xs uppercase">Recepción del equipo</h3>
                ${taller ? `<div class="flex gap-3">
                    <button type="button" data-editar class="text-xs font-semibold text-blue-600 hover:text-blue-800">✎ ${lineas.length ? 'Editar' : 'Cargar'} checklist</button>
                    <button type="button" data-foto class="text-xs font-semibold text-blue-600 hover:text-blue-800">📷 Foto de ingreso</button>
                    <input type="file" data-foto-input accept="image/jpeg,image/png" capture="environment" multiple class="hidden">
                </div>` : ''}
            </div>
            ${lineas.length ? `<dl class="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
                ${lineas.map(([k, v]) => `<dt class="text-gray-500">${k}</dt><dd class="text-gray-800">${esc(v)}</dd>`).join('')}
            </dl>` : '<p class="text-sm text-gray-400 italic">Sin checklist de ingreso.</p>'}
            <div class="flex flex-wrap gap-3 mt-3">
                ${bloqueFirma('ingreso', 'Firma de ingreso')}
                ${bloqueFirma('entrega', 'Firma de entrega')}
            </div>
        </div>`;
        card.classList.remove('hidden');
        card.querySelectorAll('img[data-firma]').forEach(async img => {
            const url = await imagenFirma(ticket.id, img.dataset.firma);
            if (url) img.src = url;
        });
        if (!taller) return;

        const refrescar = async t => {
            await cargarDetalle(t);
            ui.loadHistory(t.id);
        };
        card.querySelector('[data-editar]').addEventListener('click', () => {
            const m = modal('Checklist de ingreso', '');
            const leer = checklistForm(m.cuerpo, ticket.checklist_ingreso || {});
            m.boton.addEventListener('click', async () => {
                try {
                    const t = await api.request(`tickets/${ticket.id}/checklist`, { method: 'PUT', body: JSON.stringify(leer()) });
                    m.cerrar(); toast.success('Checklist guardado.'); refrescar(t);
                } catch (err) { toast.error(err.message); }
            });
        });
        card.querySelectorAll('[data-firmar]').forEach(b => b.addEventListener('click', () => {
            const momento = b.dataset.firmar;
            const m = modal(momento === 'ingreso' ? 'Firma de conformidad del ingreso' : 'Firma de conformidad de la entrega',
                `<p class="text-sm text-gray-500 mb-3">${momento === 'entrega'
                    ? 'El cliente firma que retira el equipo y está conforme con el trabajo realizado.'
                    : 'El cliente firma que deja el equipo en el estado registrado en el checklist.'}</p><div data-pad></div>`,
                { guardar: 'Guardar firma' });
            const pad = firmaPad(m.cuerpo.querySelector('[data-pad]'), { aclaracion: firmas[momento]?.aclaracion || ticket.usuario_nombre || '' });
            m.boton.addEventListener('click', async () => {
                if (pad.vacia()) { toast.error('Falta la firma.'); return; }
                try {
                    const t = await api.request(`tickets/${ticket.id}/firmas/${momento}`, { method: 'PUT', body: JSON.stringify(pad.datos()) });
                    m.cerrar(); toast.success('Firma guardada.'); refrescar(t);
                } catch (err) { toast.error(err.message); }
            });
        }));
        const input = card.querySelector('[data-foto-input]');
        card.querySelector('[data-foto]').addEventListener('click', () => input.click());
        input.addEventListener('change', async e => {
            const archivos = [...(e.target.files || [])];
            e.target.value = '';
            let ok = 0;
            for (const f of archivos) {
                try { await subirFoto(ticket.id, await reducirFoto(f)); ok++; } catch (err) { toast.error(err.message); }
            }
            if (ok) { toast.success(ok === 1 ? 'Foto de ingreso subida.' : `${ok} fotos de ingreso subidas.`); ui.loadAttachments(ticket.id); ui.loadHistory(ticket.id); }
        });
    }

    // ── Lector de código de barras ───────────────────────────────────────────
    /** Abre el ticket si `texto` es un N° de RMA exacto. Devuelve true si lo abrió. */
    async function abrirRma(texto) {
        const q = (texto || '').trim();
        if (!RMA_RE.test(q)) return false;
        try {
            const t = await api.request(`tickets/rma/${encodeURIComponent(q.toUpperCase())}`);
            await ui.showTicketDetail(t);
            return true;
        } catch { return false; }
    }

    // Un lector USB "tipea" muy rápido y termina con Enter. Fuera de un campo de
    // texto, si llega un RMA así, se abre el ticket (en el buscador lo maneja app.js).
    let _buffer = '', _ultimaTecla = 0;
    function iniciarEscaner() {
        document.addEventListener('keydown', e => {
            const el = e.target;
            if (el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))) return;
            if (!auth.isLoggedIn()) return;
            const ahora = performance.now();
            if (ahora - _ultimaTecla > 80) _buffer = '';
            _ultimaTecla = ahora;
            if (e.key === 'Enter') {
                const leido = _buffer; _buffer = '';
                if (RMA_RE.test(leido)) {
                    e.preventDefault();
                    abrirRma(leido).then(ok => { if (!ok) toast.error(`No se encontró el ticket ${leido}.`); });
                }
            } else if (e.key.length === 1) {
                _buffer += e.key;
            }
        });
    }
    iniciarEscaner();

    return { abrirMostrador, cargarDetalle, abrirRma, checklistForm, firmaPad };
})();
window.Recepcion = Recepcion;
