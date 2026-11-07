/**
 * horas.js — Calendario de horas de los técnicos (pantalla "Horas", atajo G H).
 *
 * Vistas: día, semana (por defecto) y mes; en el celular, un día por vez.
 * Cada tramo es un bloque: clic para corregirlo, arrastrar a otro día para moverlo
 * (en el celular, "Mover a…"). Las reglas las aplica el servidor (services/horas.py):
 * sin superposiciones, nada a futuro, hasta 16 h por día y un plazo para corregir.
 * Los días y horarios son los del negocio (zona que devuelve /tiempo/calendario).
 */
const Horas = (() => {
    const $ = id => document.getElementById(id);
    const st = {
        vista: 'semana', ancla: null, tecnico: '', datos: null, zona: 'America/Argentina/Buenos_Aires',
        tic: null, edit: null, ticket: null, buscarTic: null,
    };
    const esAdmin = () => auth.getUser()?.role === 'administrador';
    const esTaller = () => ['administrador', 'tecnico'].includes(auth.getUser()?.role || '');
    const movil = () => window.innerWidth < 640;

    // ── Fechas 'YYYY-MM-DD' (sin depender de la zona del navegador) ─────────
    const _d = s => new Date(s + 'T12:00:00Z');
    const sumar = (s, n) => { const d = _d(s); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
    const diaSemana = s => _d(s).getUTCDay();                       // 0 = domingo
    const lunes = s => sumar(s, -((diaSemana(s) + 6) % 7));
    const may = t => t.charAt(0).toUpperCase() + t.slice(1);
    const nombreDia = (s, o) => may(_d(s).toLocaleDateString(I18N.locale, { timeZone: 'UTC', ...o }));
    const corto = s => `${nombreDia(s, { weekday: 'short' }).replace('.', '')} ${_d(s).toLocaleDateString(I18N.locale, { timeZone: 'UTC', day: 'numeric', month: 'numeric' })}`;
    const enZona = (iso, o) => new Date(iso).toLocaleString('en-CA', { timeZone: st.zona, hour12: false, ...o });
    const fechaLocal = iso => enZona(iso, { year: 'numeric', month: '2-digit', day: '2-digit' });
    const horaLocal = iso => enZona(iso, { hour: '2-digit', minute: '2-digit' }).replace(/^24/, '00');
    const hoy = () => st.datos?.hoy || new Date().toLocaleDateString('en-CA', { timeZone: st.zona });
    const dur = m => {
        m = Math.round(m);
        const h = Math.floor(m / 60), r = m % 60;
        return h ? (r ? `${h} h ${String(r).padStart(2, '0')} min` : `${h} h`) : `${r} min`;
    };
    const minutos = r => r.en_curso ? Math.max(0, (Date.now() - Date.parse(r.inicio)) / 60000) : r.minutos;

    function rango() {
        const a = st.ancla;
        if (st.vista === 'dia') return [a, a];
        if (st.vista === 'semana') { const l = lunes(a); return [l, sumar(l, 6)]; }
        const ini = a.slice(0, 8) + '01';
        const fin = sumar(sumar(ini, 32).slice(0, 8) + '01', -1);
        return [ini, fin];
    }

    // ── Entrada ──────────────────────────────────────────────────────────────
    async function abrir() {
        if (!esTaller()) return;
        await ui.showSection('horas');
        st.ancla = st.ancla || hoy();
        if (movil()) st.vista = 'dia';
        if (!esAdmin()) st.tecnico = '';
        bind();
        await cargar();
    }

    function bind() {
        $('horas-ant').addEventListener('click', () => mover_(-1));
        $('horas-sig').addEventListener('click', () => mover_(1));
        $('horas-hoy').addEventListener('click', () => { st.ancla = hoy(); cargar(); });
        document.querySelectorAll('[data-horas-vista]').forEach(b => b.addEventListener('click', () => {
            st.vista = b.dataset.horasVista; cargar();
        }));
        document.querySelectorAll('[data-horas-exportar]').forEach(b => b.addEventListener('click', () => exportar(b.dataset.horasExportar)));
        $('horas-tecnico').addEventListener('change', e => { st.tecnico = e.target.value; cargar(); });
        $('horas-nueva').addEventListener('click', () => abrirModal({ dia: st.vista === 'dia' ? st.ancla : hoy() }));
        bindModal();
        const cuerpo = $('horas-cuerpo');
        cuerpo.addEventListener('click', alClic);
        // Arrastrar y soltar entre días (escritorio)
        cuerpo.addEventListener('dragstart', e => {
            const b = e.target.closest('[data-tramo][draggable="true"]');
            if (!b) return;
            e.dataTransfer.setData('text/plain', b.dataset.tramo);
            e.dataTransfer.effectAllowed = 'move';
            b.classList.add('opacity-50');
        });
        cuerpo.addEventListener('dragend', e => e.target.closest?.('[data-tramo]')?.classList.remove('opacity-50'));
        cuerpo.addEventListener('dragover', e => {
            const dia = e.target.closest('[data-soltar]');
            if (!dia) return;
            e.preventDefault();
            cuerpo.querySelectorAll('[data-soltar]').forEach(d => d.classList.toggle('ring-2', d === dia));
        });
        cuerpo.addEventListener('dragleave', e => { if (!cuerpo.contains(e.relatedTarget)) limpiarSoltar(); });
        cuerpo.addEventListener('drop', e => {
            const dia = e.target.closest('[data-soltar]');
            limpiarSoltar();
            if (!dia) return;
            e.preventDefault();
            const id = Number(e.dataTransfer.getData('text/plain'));
            if (id) moverA(id, dia.dataset.soltar);
        });
        clearInterval(st.tic);
        st.tic = setInterval(() => {
            if (!$('horas-section')) { clearInterval(st.tic); return; }
            if (st.datos?.registros.some(r => r.en_curso)) pintar();
        }, 30000);
    }
    const limpiarSoltar = () => document.querySelectorAll('[data-soltar]').forEach(d => d.classList.remove('ring-2'));

    function mover_(n) {
        if (st.vista === 'dia') st.ancla = sumar(st.ancla, n);
        else if (st.vista === 'semana') st.ancla = sumar(st.ancla, 7 * n);
        else { const d = _d(st.ancla.slice(0, 8) + '15'); d.setUTCMonth(d.getUTCMonth() + n); st.ancla = d.toISOString().slice(0, 8) + '01'; }
        cargar();
    }

    async function cargar() {
        const [desde, hasta] = rango();
        const q = new URLSearchParams({ desde, hasta });
        if (st.tecnico) q.set('usuario_id', st.tecnico);
        try {
            st.datos = await api.request(`tiempo/calendario?${q}`);
        } catch (err) {
            $('horas-cuerpo').innerHTML = `<p class="text-red-500 text-sm text-center py-8">${esc(err.message)}</p>`;
            return;
        }
        st.zona = st.datos.zona || st.zona;
        pintar();
    }

    // ── Pintar ───────────────────────────────────────────────────────────────
    function pintar() {
        if (!$('horas-section') || !st.datos) return;
        const d = st.datos;
        document.querySelectorAll('[data-horas-vista]').forEach(b => {
            const on = b.dataset.horasVista === st.vista;
            b.classList.toggle('bg-blue-600', on); b.classList.toggle('text-white', on);
            b.setAttribute('aria-pressed', on);
        });
        const sel = $('horas-tecnico');
        if (esAdmin()) {
            sel.classList.remove('hidden');
            sel.innerHTML = `<option value="">${esc(I18N.t('Todos los técnicos'))}</option>` +
                d.tecnicos.map(t => `<option value="${t.id}" ${String(t.id) === String(st.tecnico) ? 'selected' : ''}>${esc(t.nombre)}</option>`).join('');
        }
        const [desde, hasta] = rango();
        $('horas-rango').textContent = st.vista === 'dia' ? nombreDia(desde, { weekday: 'long', day: 'numeric', month: 'long' })
            : st.vista === 'semana' ? `${nombreDia(desde, { day: 'numeric', month: 'short' })} – ${nombreDia(hasta, { day: 'numeric', month: 'short', year: 'numeric' })}`
            : nombreDia(desde, { month: 'long', year: 'numeric' });
        $('horas-sig').disabled = hasta >= hoy();
        $('horas-sig').classList.toggle('opacity-40', hasta >= hoy());

        const regs = d.registros;
        const total = regs.reduce((a, r) => a + minutos(r), 0);
        const tick = regs.filter(r => r.ticket_id).reduce((a, r) => a + minutos(r), 0);
        const tarjeta = (t, v, x = '') => `<div class="bg-white rounded-xl border p-3"><p class="text-xs text-gray-500">${esc(I18N.t(t))}</p>
            <p class="text-xl font-bold text-gray-800">${v}</p>${x ? `<p class="text-xs text-gray-400">${x}</p>` : ''}</div>`;
        $('horas-resumen').innerHTML =
            tarjeta('Total del período', dur(total)) + tarjeta('En tickets', dur(tick)) +
            tarjeta('Tareas del taller', dur(total - tick)) +
            tarjeta('Mano de obra', d.costo != null ? precioARS(d.costo) : '—', d.costo == null ? esc(I18N.t('Cargá el costo de la hora en Ajustes')) : esc(I18N.t('solo horas en tickets')));
        const ayuda = [];
        if (d.limite_correccion) ayuda.push(I18N.t('Podés cargar y corregir horas desde el {0}. Para días anteriores, pedíselo a un administrador.')
            .replace('{0}', nombreDia(d.limite_correccion, { day: 'numeric', month: 'long' })));
        if (!movil() && st.vista !== 'mes') ayuda.push(I18N.t('Arrastrá un tramo a otro día para moverlo; hacé clic para corregirlo.'));
        $('horas-ayuda').textContent = ayuda.join(' ');

        marcarSuperpuestos(regs);
        const cuerpo = $('horas-cuerpo');
        if (st.vista === 'mes') cuerpo.innerHTML = mes(desde, hasta);
        else {
            const dias = [];
            for (let s = desde; s <= hasta; s = sumar(s, 1)) dias.push(s);
            cuerpo.innerHTML = `<div class="${st.vista === 'semana' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-3' : ''}">${dias.map(diaHtml).join('')}</div>`;
        }
    }

    function marcarSuperpuestos(regs) {
        const por = {};
        regs.forEach(r => { r._pisa = false; (por[r.usuario_id] ||= []).push(r); });
        Object.values(por).forEach(l => {
            l.sort((a, b) => a.inicio.localeCompare(b.inicio));
            let finMax = 0, previo = null;
            l.forEach(r => {
                const ini = Date.parse(r.inicio), fin = r.fin ? Date.parse(r.fin) : Date.now();
                if (previo && ini < finMax) { r._pisa = true; previo._pisa = true; }
                if (fin > finMax) { finMax = fin; previo = r; }
            });
        });
    }

    const delDia = s => st.datos.registros.filter(r => r.dia === s);
    function avisos(s, regs) {
        const a = [];
        const finde = [0, 6].includes(diaSemana(s));
        const unTecnico = !esAdmin() || st.tecnico;
        if (unTecnico && !regs.length && !finde && s < hoy()) a.push(['amber', 'Sin horas']);
        if (regs.some(r => r._pisa)) a.push(['red', 'Tramos superpuestos']);
        if (regs.some(r => r.en_curso && minutos(r) > 600)) a.push(['red', '¿Quedó corriendo?']);
        return a;
    }
    const chip = ([c, t]) => `<span class="text-[11px] font-semibold px-1.5 py-0.5 rounded bg-${c}-100 text-${c}-800">${esc(I18N.t(t))}</span>`;
    const puedeCargar = s => s <= hoy() && (!st.datos.limite_correccion || s >= st.datos.limite_correccion);

    function diaHtml(s) {
        const regs = delDia(s).sort((a, b) => a.inicio.localeCompare(b.inicio));
        const total = regs.reduce((a, r) => a + minutos(r), 0);
        const esHoy = s === hoy();
        const grande = st.vista === 'dia';
        return `
        <div class="bg-white rounded-xl border ${esHoy ? 'border-blue-400' : ''} p-3 flex flex-col gap-2 ${grande ? '' : 'min-h-[9rem]'} ring-blue-400" data-soltar="${s}">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <p class="text-sm font-bold ${esHoy ? 'text-blue-700' : 'text-gray-700'}">${esc(grande ? nombreDia(s, { weekday: 'long', day: 'numeric', month: 'long' }) : corto(s))}</p>
                    <p class="text-xs text-gray-500">${regs.length ? dur(total) : '—'}</p>
                </div>
                ${puedeCargar(s) ? `<button type="button" data-cargar="${s}" class="shrink-0 w-8 h-8 rounded-lg text-blue-600 hover:bg-blue-50 text-lg font-bold" aria-label="${esc(I18N.t('Cargar horas'))}" title="${esc(I18N.t('Cargar horas'))}">+</button>` : ''}
            </div>
            ${avisos(s, regs).length ? `<div class="flex flex-wrap gap-1">${avisos(s, regs).map(chip).join('')}</div>` : ''}
            <div class="${grande ? 'space-y-2' : 'space-y-1.5'}">${regs.map(bloque).join('')}</div>
        </div>`;
    }

    function bloque(r) {
        const color = r.en_curso ? 'bg-emerald-50 border-emerald-500' : r.ticket_id ? 'bg-blue-50 border-blue-500' : 'bg-violet-50 border-violet-400';
        const titulo = r.ticket_id ? `<span class="font-mono font-bold text-blue-700" translate="no">${esc(r.numero_rma)}</span>`
            : `<span class="font-semibold text-violet-800">${esc(I18N.t(r.categoria_etiqueta))}</span>`;
        const hasta = r.en_curso ? I18N.t('ahora') : horaLocal(r.fin);
        const arrastrable = r.editable && !movil() && st.vista !== 'mes';
        return `
        <div data-tramo="${r.id}" ${arrastrable ? 'draggable="true"' : ''} role="button" tabindex="0"
             class="rounded-lg border-l-4 ${color} ${r._pisa ? 'ring-2 ring-red-400' : ''} px-2 py-1.5 text-xs cursor-pointer hover:shadow ${arrastrable ? 'cursor-grab' : ''}">
            <div class="flex items-center justify-between gap-1 text-gray-600">
                <span class="font-mono">${horaLocal(r.inicio)}–${esc(hasta)}</span>
                <span class="font-semibold text-gray-800">${dur(minutos(r))}</span>
            </div>
            <div class="truncate">${titulo}</div>
            ${r.producto ? `<div class="truncate text-gray-600">${esc(r.producto)}</div>` : ''}
            ${r.nota ? `<div class="truncate text-gray-500 italic">${esc(r.nota)}</div>` : ''}
            <div class="flex flex-wrap items-center gap-1 mt-0.5">
                ${esAdmin() && !st.tecnico ? `<span class="text-[11px] text-gray-500">${icono('usuario', 'w-3 h-3 mr-0.5')}${esc(r.usuario_nombre || '')}</span>` : ''}
                ${r.en_curso ? `<span class="text-[11px] font-semibold text-emerald-700">${icono('reloj', 'w-3 h-3 mr-0.5')}${esc(I18N.t('en curso'))}</span>` : ''}
                ${r.editado ? `<span class="text-[11px] text-gray-500 bg-white border rounded px-1">${esc(I18N.t('editado'))}</span>` : ''}
                ${!r.editable && !r.en_curso ? '<span class="text-[11px] text-gray-400" title="' + esc(I18N.t(r.motivo_no_editable)) + '">' + icono('candado', 'w-3 h-3') + '</span>' : ''}
                ${r.editable && movil() ? `<button type="button" data-mover="${r.id}" class="ml-auto text-[11px] font-semibold text-blue-700 underline px-1 py-1">${esc(I18N.t('Mover a…'))}</button>` : ''}
            </div>
        </div>`;
    }

    function mes(desde, hasta) {
        const ini = lunes(desde);
        const cab = [0, 1, 2, 3, 4, 5, 6].map(i => `<div class="text-xs font-semibold text-gray-500 text-center py-1">${esc(nombreDia(sumar(ini, i), { weekday: 'short' }))}</div>`).join('');
        let celdas = '';
        for (let s = ini; s <= hasta || diaSemana(s) !== 1; s = sumar(s, 1)) {
            if (s > hasta && diaSemana(s) === 1) break;
            const fuera = s < desde || s > hasta;
            const regs = fuera ? [] : delDia(s);
            const total = regs.reduce((a, r) => a + minutos(r), 0);
            const av = fuera ? [] : avisos(s, regs);
            celdas += `
            <button type="button" ${fuera ? 'disabled' : `data-ir-dia="${s}"`} class="text-left rounded-lg border p-2 min-h-[4.5rem] ${fuera ? 'bg-gray-50 opacity-40' : 'bg-white hover:border-blue-400'} ${s === hoy() ? 'border-blue-400' : ''}">
                <span class="text-xs font-semibold text-gray-600">${Number(s.slice(8))}</span>
                ${total ? `<span class="block text-sm font-bold text-gray-800">${dur(total)}</span>` : ''}
                ${av.map(([c]) => `<span class="inline-block w-2 h-2 rounded-full bg-${c}-500 mr-0.5"></span>`).join('')}
            </button>`;
        }
        return `<div class="grid grid-cols-7 gap-1 sm:gap-2">${cab}${celdas}</div>
            <p class="text-xs text-gray-400 mt-2">${esc(I18N.t('Tocá un día para ver el detalle.'))}</p>`;
    }

    function alClic(e) {
        const t = e.target;
        const c = t.closest('[data-cargar]');
        if (c) return abrirModal({ dia: c.dataset.cargar });
        const ir = t.closest('[data-ir-dia]');
        if (ir) { st.ancla = ir.dataset.irDia; st.vista = 'dia'; return cargar(); }
        const mv = t.closest('[data-mover]');
        if (mv) return abrirModal({ registro: buscar(mv.dataset.mover), mover: true });
        const b = t.closest('[data-tramo]');
        if (b) abrirModal({ registro: buscar(b.dataset.tramo) });
    }
    const buscar = id => st.datos.registros.find(r => String(r.id) === String(id));

    // ── Mover (arrastrar) ────────────────────────────────────────────────────
    const cuerpoTramo = (r, dia) => {
        const offset = Math.round((_d(fechaLocal(r.fin)) - _d(fechaLocal(r.inicio))) / 86400000);
        return { ticket_id: r.ticket_id, categoria: r.categoria, nota: r.nota || '',
                 inicio: `${dia}T${horaLocal(r.inicio)}`, fin: `${sumar(dia, offset)}T${horaLocal(r.fin)}` };
    };
    async function moverA(id, dia) {
        const r = buscar(id);
        if (!r || r.dia === dia) return;
        if (!r.editable) { toast.warning(I18N.t(r.motivo_no_editable)); return; }
        const origen = r.dia;
        try {
            await api.request(`tiempo/${id}`, { method: 'PUT', body: JSON.stringify(cuerpoTramo(r, dia)) });
            await cargar();
            toast.deshacer(I18N.t('Tramo movido al {0}.').replace('{0}', nombreDia(dia, { weekday: 'long', day: 'numeric' })), async () => {
                await api.request(`tiempo/${id}`, { method: 'PUT', body: JSON.stringify(cuerpoTramo(r, origen)) });
                await cargar();
            });
        } catch (err) { toast.error(err.message); }
    }

    // ── Modal: cargar / corregir ─────────────────────────────────────────────
    const radio = n => document.querySelector(`input[name="${n}"]:checked`)?.value;
    function segmentos() {
        document.querySelectorAll('#horas-form [data-seg]').forEach(l => {
            const on = l.querySelector('input').checked;
            l.classList.toggle('bg-blue-600', on); l.classList.toggle('text-white', on);
        });
        const taller = radio('horas-tipo') === 'taller';
        $('horas-f-ticket-wrap').classList.toggle('hidden', taller);
        $('horas-f-cat-wrap').classList.toggle('hidden', !taller);
        const dura = radio('horas-modo') === 'duracion';
        $('horas-f-horario').classList.toggle('hidden', dura);
        $('horas-f-duracion').classList.toggle('hidden', !dura);
        totalModal();
    }
    const aMin = v => { const [h, m] = (v || '').split(':').map(Number); return isNaN(h) ? null : h * 60 + (m || 0); };
    function minutosModal() {
        if (radio('horas-modo') === 'duracion') return (Number($('horas-f-h').value) || 0) * 60 + (Number($('horas-f-m').value) || 0);
        const a = aMin($('horas-f-desde').value), b = aMin($('horas-f-hasta').value);
        return a == null || b == null ? null : b - a;
    }
    function totalModal() {
        const m = minutosModal();
        $('horas-f-total').textContent = m > 0 ? `${I18N.t('Duración:')} ${dur(m)}` : '';
    }
    function error(id, msg) {
        const el = $(id);
        el.textContent = msg ? I18N.t(msg) : '';
        el.classList.toggle('hidden', !msg);
        return !!msg;
    }

    function bindModal() {
        const form = $('horas-form');
        const cerrar = () => { $('horas-modal').classList.add('hidden'); st.edit = null; };
        $('horas-cerrar').addEventListener('click', cerrar);
        $('horas-cancelar').addEventListener('click', cerrar);
        $('horas-modal').addEventListener('click', e => { if (e.target.id === 'horas-modal') cerrar(); });
        form.addEventListener('change', e => { if (e.target.name) segmentos(); });
        ['horas-f-desde', 'horas-f-hasta', 'horas-f-h', 'horas-f-m'].forEach(id => $(id).addEventListener('input', () => { totalModal(); error('horas-f-tiempo-err', ''); }));
        $('horas-f-dia').addEventListener('input', () => error('horas-f-dia-err', ''));
        // Buscar ticket
        $('horas-f-ticket').addEventListener('input', e => {
            clearTimeout(st.buscarTic);
            const q = e.target.value.trim();
            const lista = $('horas-f-ticket-res');
            if (q.length < 2) { lista.classList.add('hidden'); return; }
            st.buscarTic = setTimeout(async () => {
                let res = [];
                try { res = (await api.searchGlobal(q)).slice(0, 8); } catch { /* sin resultados */ }
                lista.innerHTML = res.length ? res.map(t => `
                    <li><button type="button" data-elegir="${t.id}" class="w-full text-left px-3 py-2 hover:bg-blue-50">
                        <span class="font-mono font-bold text-blue-700" translate="no">${esc(t.numero_rma)}</span>
                        <span class="text-gray-700">${esc(t.producto)}</span>
                        <span class="text-xs text-gray-400">· ${esc(I18N.t(t.estado))}</span></button></li>`).join('')
                    : `<li class="px-3 py-2 text-gray-400">${esc(I18N.t('Sin resultados'))}</li>`;
                lista.classList.remove('hidden');
                lista.querySelectorAll('[data-elegir]').forEach(b => b.addEventListener('click', () => {
                    const t = res.find(x => String(x.id) === b.dataset.elegir);
                    elegirTicket({ id: t.id, numero_rma: t.numero_rma, producto: t.producto });
                }));
            }, 250);
        });
        $('horas-f-ticket-sel').addEventListener('click', e => {
            if (e.target.closest('[data-cambiar]')) { elegirTicket(null); $('horas-f-ticket').focus(); }
        });
        form.addEventListener('submit', e => { e.preventDefault(); guardar(); });
        $('horas-borrar').addEventListener('click', borrar);
    }

    function elegirTicket(t) {
        st.ticket = t;
        $('horas-f-ticket-res').classList.add('hidden');
        error('horas-f-ticket-err', '');
        const sel = $('horas-f-ticket-sel');
        $('horas-f-ticket').classList.toggle('hidden', !!t);
        sel.classList.toggle('hidden', !t);
        sel.innerHTML = t ? `<span><span class="font-mono font-bold text-blue-700" translate="no">${esc(t.numero_rma)}</span> ${esc(t.producto || '')}</span>
            <button type="button" data-cambiar class="text-blue-700 underline text-xs font-semibold">${esc(I18N.t('Cambiar'))}</button>` : '';
        if (!t) $('horas-f-ticket').value = '';
    }

    function abrirModal({ registro = null, dia = null, mover = false } = {}) {
        const r = registro;
        if (r && !r.editable) { toast.warning(I18N.t(r.motivo_no_editable)); return; }
        st.edit = r;
        const d = st.datos;
        $('horas-modal-titulo').textContent = I18N.t(r ? (mover ? 'Mover a otro día' : 'Corregir horas') : 'Cargar horas');
        // Técnico: el admin con "todos" elige para quién
        const conTecnico = esAdmin() && !r && !st.tecnico;
        $('horas-f-tecnico-wrap').classList.toggle('hidden', !conTecnico);
        if (conTecnico) $('horas-f-tecnico').innerHTML = d.tecnicos.map(t =>
            `<option value="${t.id}" ${t.id === auth.getUser()?.user_id ? 'selected' : ''}>${esc(t.nombre)}</option>`).join('');
        $('horas-f-categoria').innerHTML = Object.entries(d.categorias).map(([k, v]) => `<option value="${k}">${esc(I18N.t(v))}</option>`).join('');
        document.querySelector(`input[name="horas-tipo"][value="${r && !r.ticket_id ? 'taller' : 'ticket'}"]`).checked = true;
        document.querySelector('input[name="horas-modo"][value="horario"]').checked = true;
        $('horas-f-modo-wrap').classList.toggle('hidden', !!r);
        elegirTicket(r?.ticket_id ? { id: r.ticket_id, numero_rma: r.numero_rma, producto: r.producto } : null);
        if (r?.categoria) $('horas-f-categoria').value = r.categoria;
        $('horas-f-dia').value = r ? r.dia : (dia || hoy());
        $('horas-f-dia').max = hoy();
        if (d.limite_correccion) $('horas-f-dia').min = d.limite_correccion; else $('horas-f-dia').removeAttribute('min');
        $('horas-f-desde').value = r ? horaLocal(r.inicio) : '';
        $('horas-f-hasta').value = r ? horaLocal(r.fin) : '';
        $('horas-f-h').value = ''; $('horas-f-m').value = '';
        $('horas-f-nota').value = r?.nota || '';
        ['horas-f-ticket-err', 'horas-f-dia-err', 'horas-f-tiempo-err', 'horas-f-error'].forEach(id => error(id, ''));
        $('horas-borrar').classList.toggle('hidden', !r);
        $('horas-f-cambios-wrap').classList.add('hidden');
        if (r) historial(r.id);
        segmentos();
        $('horas-modal').classList.remove('hidden');
        setTimeout(() => (mover ? $('horas-f-dia') : r ? $('horas-f-desde') : $('horas-f-ticket')).focus(), 50);
    }

    async function historial(id) {
        let filas = [];
        try { filas = await api.request(`tiempo/${id}/cambios`); } catch { return; }
        if (filas.length < 2) return;
        const acc = { alta: 'Cargado', edicion: 'Corregido', movido: 'Movido', borrado: 'Borrado' };
        const tramo = f => f ? `${fechaLocal(f.inicio).slice(8, 10)}/${fechaLocal(f.inicio).slice(5, 7)} ${horaLocal(f.inicio)}–${f.fin ? horaLocal(f.fin) : ''} · ${f.numero_rma || I18N.t(st.datos.categorias[f.categoria] || '')}` : '';
        $('horas-f-cambios').innerHTML = filas.map(c => `
            <li class="border-l-2 border-gray-200 pl-2">
                <p class="text-xs text-gray-500">${new Date(c.fecha).toLocaleString(I18N.locale, { hour12: false, dateStyle: 'short', timeStyle: 'short' })} · ${esc(c.usuario_nombre || '')}</p>
                <p><span class="font-semibold">${esc(I18N.t(acc[c.accion] || c.accion))}</span>
                ${c.antes ? `<span class="text-gray-500 line-through" translate="no">${esc(tramo(c.antes))}</span> →` : ''}
                <span translate="no">${esc(tramo(c.despues))}</span></p>
            </li>`).join('');
        $('horas-f-cambios-wrap').classList.remove('hidden');
    }

    function leer() {
        const taller = radio('horas-tipo') === 'taller';
        const dia = $('horas-f-dia').value;
        let mal = false;
        if (!taller && !st.ticket) mal = error('horas-f-ticket-err', 'Elegí el ticket en el que se trabajó.') || mal;
        if (!dia) mal = error('horas-f-dia-err', 'Indicá el día.') || mal;
        else if (dia > hoy()) mal = error('horas-f-dia-err', 'No se pueden cargar horas a futuro.') || mal;
        else if (st.datos.limite_correccion && dia < st.datos.limite_correccion)
            mal = error('horas-f-dia-err', 'Ese día ya no se puede corregir: pedíselo a un administrador.') || mal;
        const dura = radio('horas-modo') === 'duracion' && !st.edit;
        const m = minutosModal();
        if (!dura && (!$('horas-f-desde').value || !$('horas-f-hasta').value)) mal = error('horas-f-tiempo-err', 'Completá desde y hasta.') || mal;
        else if (!dura && m <= 0) mal = error('horas-f-tiempo-err', 'La hora de fin tiene que ser posterior a la de inicio.') || mal;
        else if (dura && !(m > 0)) mal = error('horas-f-tiempo-err', 'Indicá cuánto tiempo fue.') || mal;
        else if (m > 16 * 60) mal = error('horas-f-tiempo-err', 'Un tramo puede durar como mucho 16 horas.') || mal;
        if (mal) return null;
        const body = { ticket_id: taller ? null : st.ticket.id, categoria: taller ? $('horas-f-categoria').value : null,
                       nota: $('horas-f-nota').value.trim() };
        if (dura) Object.assign(body, { fecha: dia, minutos: m });
        else Object.assign(body, { inicio: `${dia}T${$('horas-f-desde').value}`, fin: `${dia}T${$('horas-f-hasta').value}` });
        return body;
    }

    async function guardar() {
        error('horas-f-error', '');
        const body = leer();
        if (!body) { $('horas-form').querySelector('p.text-red-600:not(.hidden)')?.scrollIntoView({ block: 'center' }); return; }
        const r = st.edit;
        if (!r) {
            if (esAdmin()) body.usuario_id = Number(st.tecnico || $('horas-f-tecnico').value) || null;
        }
        try {
            const res = await api.request(r ? `tiempo/${r.id}` : 'tiempo', { method: r ? 'PUT' : 'POST', body: JSON.stringify(body) });
            $('horas-modal').classList.add('hidden');
            st.edit = null;
            if (res.dia !== st.ancla && st.vista === 'dia' && !r) st.ancla = res.dia;
            await cargar();
            toast.success(I18N.t(r ? 'Cambios guardados.' : 'Horas cargadas.'));
        } catch (err) { error('horas-f-error', err.message); }
    }

    async function borrar() {
        const r = st.edit;
        if (!r) return;
        try {
            await api.request(`tiempo/${r.id}`, { method: 'DELETE' });
            $('horas-modal').classList.add('hidden');
            st.edit = null;
            await cargar();
            toast.deshacer(I18N.t('Tramo borrado.'), async () => {
                const b = { ...cuerpoTramo(r, r.dia), usuario_id: esAdmin() ? r.usuario_id : null };
                await api.request('tiempo', { method: 'POST', body: JSON.stringify(b) });
                await cargar();
            });
        } catch (err) { error('horas-f-error', err.message); }
    }

    // ── Exportar ─────────────────────────────────────────────────────────────
    async function exportar(formato) {
        const [desde, hasta] = rango();
        const q = new URLSearchParams({ desde, hasta, formato });
        if (st.tecnico) q.set('usuario_id', st.tecnico);
        try {
            const blob = await api.request(`tiempo/exportar?${q}`);
            const url = URL.createObjectURL(blob);
            const a = Object.assign(document.createElement('a'), { href: url, download: `horas_${desde}_${hasta}.${formato}` });
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (err) { toast.error(err.message); }
    }

    // Teclado: Enter sobre un bloque lo abre
    document.addEventListener('keydown', e => {
        const b = e.target.closest?.('[data-tramo]');
        if (b && (e.key === 'Enter' || e.key === ' ') && !e.target.closest('button')) { e.preventDefault(); abrirModal({ registro: buscar(b.dataset.tramo) }); }
    });

    return { abrir };
})();
window.Horas = Horas;
