import { I18n } from './i18n.js';
import { Modal } from './modal.js';

export const Shortcuts = {
    _bindings: [],

    register(keys, handler, { condition } = {}) {
        this._bindings.push({ keys, handler, condition });
    },

    init() {
        document.addEventListener('keydown', (e) => {
            // 在 input/textarea/select 中只响应 Escape
            const tag = e.target.tagName;
            const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
            if (isInput && e.key !== 'Escape') return;

            const ctrl = e.ctrlKey || e.metaKey;
            const shift = e.shiftKey;
            const alt = e.altKey;

            // Escape: close any open modal / chatbot
            if (e.key === 'Escape' && !ctrl && !shift && !alt) {
                if (this._closeModal()) {
                    e.preventDefault();
                    return;
                }
            }

            for (const binding of this._bindings) {
                if (binding.condition && !binding.condition()) continue;
                const parts = binding.keys.split('+');
                const mod = parts.length > 1 ? parts.slice(0, -1).join('+') : 'none';
                const key = parts[parts.length - 1];
                let match = false;
                if (mod === 'Ctrl' && ctrl && !shift && e.key === key) match = true;
                else if (mod === 'Ctrl+Shift' && ctrl && shift && e.key === key) match = true;
                else if (mod === 'Shift' && !ctrl && shift && e.key === key) match = true;
                else if (mod === 'none' && !ctrl && !shift && e.key === key) match = true;
                if (match) {
                    e.preventDefault();
                    binding.handler();
                    return;
                }
            }
        });
    },

    _closeModal() {
        // close chatbot first
        //
        // 判据必须是 .show：聊天窗的显隐走 .chatbot-window / .chatbot-window.show
        // 两条类规则（styles.css），既不加 .hidden 也不改内联 display，
        // 所以原先 "!contains('hidden') && style.display !== 'none'" 恒为真。
        // 更糟的是 #chatbotClose 绑的是 toggleWindow()，窗口关着时点它会把聊天
        // 窗**打开**，并且这里 return true 把 Esc 吞掉 —— 结果就是按 Esc 非但
        // 关不掉模态框，反而弹出助手。
        const chatbot = document.getElementById('chatbotWindow');
        if (chatbot && chatbot.classList.contains('show')) {
            document.getElementById('chatbotClose')?.click();
            return true;
        }
        // close any modal overlay
        const overlay = document.querySelector('.modal-overlay:not(.hidden)');
        if (overlay) {
            const closeBtn = overlay.querySelector('#modalCloseBtn');
            if (closeBtn) closeBtn.click();
            else overlay.classList.add('hidden');
            return true;
        }
        return false;
    },

    showHelp() {
        const t = (k) => I18n.t(k);
        Modal.createOverlay(`
            <div class="modal-box shortcuts-help-box">
                <div class="modal-title">${t('shortcuts.help')}</div>
                <div class="modal-content">
                    <table class="shortcuts-table">
                        <thead><tr><th>${t('shortcuts.key')}</th><th>${t('shortcuts.action')}</th></tr></thead>
                        <tbody>
                            <tr><td><kbd>Ctrl</kbd> + <kbd>Enter</kbd></td><td>${t('shortcuts.startDetect')}</td></tr>
                            <tr><td><kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>B</kbd></td><td>${t('shortcuts.startBatch')}</td></tr>
                            <tr><td><kbd>←</kbd> / <kbd>→</kbd></td><td>${t('shortcuts.navHistory')}</td></tr>
                            <tr><td><kbd>Esc</kbd></td><td>${t('shortcuts.closeModal')}</td></tr>
                            <tr><td><kbd>?</kbd></td><td>${t('shortcuts.showHelp')}</td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="modal-footer">
                    <button class="btn-modal btn-modal-secondary" id="modalCloseBtn">${t('common.close')}</button>
                </div>
            </div>
        `);
    }
};
