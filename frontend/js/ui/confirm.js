/**
 * confirm.js — Custom confirmation modal (replaces window.confirm)
 * Usage: const ok = await confirmDialog('¿Eliminar este repuesto?', 'No podrá recuperarse.')
 */
const confirmDialog = (title = '¿Estás seguro?', message = 'Esta acción no se puede deshacer.', okLabel = 'Eliminar') => {
    return new Promise((resolve) => {
        const modal   = document.getElementById('confirm-modal');
        const titleEl = document.getElementById('confirm-title');
        const msgEl   = document.getElementById('confirm-message');
        const okBtn   = document.getElementById('confirm-ok-btn');
        const cancelBtn = document.getElementById('confirm-cancel-btn');

        titleEl.textContent = title;
        msgEl.textContent   = message;
        okBtn.textContent   = okLabel;

        modal.classList.remove('hidden');

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
