/**
 * skeleton.js — Skeleton loader rows for tables while data loads
 * Usage: skeleton.showTable('ticket-list-body', 5, 5)
 *        skeleton.showCards('stats-container', 4)
 */
const skeleton = (() => {
    function tableRows(tbodyId, rows = 5, cols = 5) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = Array.from({ length: rows }).map(() => `
            <tr class="border-b">
                ${Array.from({ length: cols }).map((_, i) => `
                    <td class="px-6 py-4">
                        <div class="skeleton h-4 ${i === 0 ? 'w-32' : i === cols - 1 ? 'w-16 ml-auto' : 'w-24'} rounded"></div>
                        ${i === 0 ? '<div class="skeleton h-3 w-20 rounded mt-2"></div>' : ''}
                    </td>
                `).join('')}
            </tr>
        `).join('');
    }

    function tarjeta() {
        return `<div class="bg-white p-6 rounded-xl shadow border-l-4 border-gray-200 h-full">
                <div class="skeleton h-3 w-20 rounded mb-3"></div>
                <div class="skeleton h-8 w-16 rounded"></div>
            </div>`;
    }

    function cards(containerId, count = 4) {
        const el = document.getElementById(containerId);
        if (!el) return;
        el.innerHTML = Array.from({ length: count }).map(() => `
            <div class="bg-white p-6 rounded-xl shadow border-l-4 border-gray-200">
                <div class="skeleton h-3 w-20 rounded mb-3"></div>
                <div class="skeleton h-8 w-16 rounded"></div>
            </div>
        `).join('');
    }

    function list(containerId, rows = 3) {
        const el = document.getElementById(containerId);
        if (!el) return;
        el.innerHTML = Array.from({ length: rows }).map(() => `
            <div class="bg-gray-50 p-4 rounded-lg border border-gray-100">
                <div class="flex justify-between mb-3">
                    <div class="skeleton h-3 w-28 rounded"></div>
                    <div class="skeleton h-3 w-20 rounded"></div>
                </div>
                <div class="skeleton h-4 w-full rounded mb-2"></div>
                <div class="skeleton h-4 w-3/4 rounded"></div>
            </div>
        `).join('');
    }

    return { tableRows, cards, tarjeta, list };
})();
