import { I18n } from './i18n.js';

/**
 * 创建模态覆盖层并追加到 body。
 * @param {string} innerHTML - 覆盖层内部 HTML
 * @param {Object} [handlers] - 事件处理 { selector: fn }，选择器 #closeBtn 自动绑定关闭
 * @returns {{ overlay: HTMLElement, close: Function }} overlay 元素和关闭函数
 */
function _createOverlay(innerHTML, handlers = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = innerHTML;
    document.body.appendChild(overlay);

    let close = () => {
        if (overlay.parentNode) document.body.removeChild(overlay);
    };

    // 自动绑定关闭按钮
    const closeBtn = overlay.querySelector('#modalCloseBtn');
    if (closeBtn) closeBtn.onclick = close;

    // 点击遮罩关闭
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });

    // 自定义事件绑定
    Object.entries(handlers).forEach(([sel, fn]) => {
        const el = overlay.querySelector(sel);
        if (el) el.onclick = (e) => fn(e, close);
    });

    // Escape 键关闭
    const onKeyDown = (e) => {
        if (e.key === 'Escape') {
            e.stopPropagation();
            close();
        }
    };
    document.addEventListener('keydown', onKeyDown);

    const origClose = close;
    close = () => {
        document.removeEventListener('keydown', onKeyDown);
        origClose();
    };

    return { overlay, close };
}

// 轻量级自定义弹窗，替代 alert/confirm
export class Modal {

    /** 创建并返回一个模态覆盖层（用于自定义复杂内容） */
    static createOverlay(innerHTML, handlers) {
        return _createOverlay(innerHTML, handlers);
    }
    /**
     * 显示提示弹窗（类似 alert）
     * @param {string} message 提示内容
     * @param {string} title 标题（可选）
     */
    static alert(message, title) {
        const _title = title || I18n.t('common.tip', '提示');
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay';
            overlay.innerHTML = `
                <div class="modal-box">
                    <div class="modal-title">${_title}</div>
                    <div class="modal-content">${message}</div>
                    <div class="modal-footer">
                        <button class="btn-modal btn-modal-primary" id="modalOkBtn">${I18n.t('common.confirm')}</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);

            overlay.querySelector('#modalOkBtn').onclick = () => {
                document.body.removeChild(overlay);
                resolve();
            };
            // 点击遮罩关闭
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                    resolve();
                }
            });
        });
    }

    /**
     * 显示确认弹窗（类似 confirm）
     * @returns {Promise<boolean>} 确认返回true，取消返回false
     */
    static confirm(message, title) {
        const _title = title || I18n.t('common.pleaseConfirm', '请确认');
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay';
            overlay.innerHTML = `
                <div class="modal-box">
                    <div class="modal-title">${_title}</div>
                    <div class="modal-content">${message}</div>
                    <div class="modal-footer">
                        <button class="btn-modal btn-modal-secondary" id="modalCancelBtn">${I18n.t('common.cancel')}</button>
                        <button class="btn-modal btn-modal-primary" id="modalOkBtn">${I18n.t('common.confirm')}</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);

            overlay.querySelector('#modalOkBtn').onclick = () => {
                document.body.removeChild(overlay);
                resolve(true);
            };
            overlay.querySelector('#modalCancelBtn').onclick = () => {
                document.body.removeChild(overlay);
                resolve(false);
            };
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                    resolve(false);
                }
            });
        });
    }
}