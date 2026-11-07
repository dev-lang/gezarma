/**
 * confirm.js — Diálogos propios en lugar de window.confirm / window.prompt
 * (los nativos no respetan el modo oscuro, en el celular se ven como alertas
 * del sistema y algunos navegadores los bloquean).
 *
 *   const ok = await confirmDialog('¿Eliminar este repuesto?', 'No podrá recuperarse.')
 *   const ok = await confirmDialog('¿Aprobar el presupuesto?', '', 'Aprobar', { peligro: false })
 *   const txt = await promptDialog('Editar nota', 'valor actual')   // null si cancelan
 *
 * Escape, foco y Tab los maneja ui/modales.js.
 */
const confirmDialog = (title = '¿Estás seguro?', message = 'Esta acción no se puede deshacer.', okLabel = 'Eliminar',
                       { peligro = true, cancelLabel = 'Cancelar' } = {}) => {
    return new Promise((resolve) => {
        const modal   = document.getElementById('confirm-modal');
        const titleEl = document.getElementById('confirm-title');
        const msgEl   = document.getElementById('confirm-message');
        const okBtn   = document.getElementById('confirm-ok-btn');
        const cancelBtn = document.getElementById('confirm-cancel-btn');
        if (!modal) { resolve(window.confirm(title)); return; }

        titleEl.textContent = title;
        msgEl.textContent   = message || '';
        msgEl.classList.toggle('hidden', !message);
        okBtn.textContent   = okLabel;
        cancelBtn.textContent = cancelLabel;
        okBtn.classList.toggle('bg-red-600', peligro);
        okBtn.classList.toggle('hover:bg-red-700', peligro);
        okBtn.classList.toggle('bg-blue-600', !peligro);
        okBtn.classList.toggle('hover:bg-blue-700', !peligro);
        modal.querySelector('[data-confirm-icono]')?.classList.toggle('hidden', !peligro);

        modal.classList.remove('hidden');
        (peligro ? cancelBtn : okBtn).focus();   // en lo destructivo, Enter no borra por accidente

        const cleanup = (result) => {
            modal.classList.add('hidden');
            okBtn.removeEventListener('click', onOk);
            cancelBtn.removeEventListener('click', onCancel);
            resolve(result);
        };

        const onOk     = () => cleanup(true);
        const onCancel = () => cleanup(false);

        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
    });
};

const promptDialog = (title, valor = '', { okLabel = 'Guardar', multilinea = false } = {}) => {
    return new Promise((resolve) => {
        const div = document.createElement('div');
        div.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4';
        div.setAttribute('data-modal', '');
        div.innerHTML = `
        <form class="bg-white rounded-xl shadow-2xl p-6 w-full max-w-sm" role="dialog" aria-modal="true">
            <h3 class="text-lg font-bold text-gray-900 mb-3"></h3>
            ${multilinea ? '<textarea rows="3"' : '<input type="text"'} data-valor
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">${multilinea ? '</textarea>' : ''}
            <div class="flex gap-3 mt-5">
                <button type="button" data-cancelar class="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50 transition">Cancelar</button>
                <button type="submit" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition"></button>
            </div>
        </form>`;
        div.querySelector('h3').textContent = title;
        div.querySelector('[type=submit]').textContent = okLabel;
        const campo = div.querySelector('[data-valor]');
        campo.value = valor ?? '';
        const fin = r => { div.remove(); resolve(r); };
        div.querySelector('[data-cancelar]').addEventListener('click', () => fin(null));
        div.querySelector('form').addEventListener('submit', e => { e.preventDefault(); fin(campo.value); });
        document.body.appendChild(div);
        campo.focus(); campo.select();
    });
};
window.confirmDialog = confirmDialog;
window.promptDialog = promptDialog;
