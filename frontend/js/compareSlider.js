import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { I18n } from './i18n.js';

export const CompareSlider = {
    show(t1Url, t2Url, title) {
        const _title = title || I18n.t('slider.title', 'T1 vs T2 时相对比');
        const { overlay, close } = Modal.createOverlay(`
            <div class="modal-box" style="max-width: 750px;">
                <div class="modal-title">${_title}</div>
                <div class="modal-content" style="padding:0;">
                    <div class="compare-slider-container" id="compareSliderContainer">
                        <img src="${t1Url}" class="compare-img compare-img-t1" style="width:100%;display:block;">
                        <div class="compare-img-overlay" id="compareOverlay" style="width:50%;">
                            <img src="${t2Url}" class="compare-img compare-img-t2" style="width:100%;display:block;">
                        </div>
                        <div class="compare-handle" id="compareHandle" style="left:50%;">
                            <div class="compare-handle-line"></div>
                            <div class="compare-handle-grip">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="white" stroke="#333" stroke-width="2"><polyline points="8 6 16 12 8 18"/><polyline points="16 6 8 12 16 18"/></svg>
                            </div>
                            <div class="compare-handle-line"></div>
                        </div>
                    </div>
                    <div class="compare-slider-labels">
                        <span>${I18n.t('slider.t1Label', 'T1 前时相（左）')}</span>
                        <span>${I18n.t('slider.t2Label', 'T2 后时相（右）')}</span>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-modal btn-modal-secondary" id="modalCloseBtn">${I18n.t('common.close')}</button>
                </div>
            </div>
        `);

        const container = overlay.querySelector('#compareSliderContainer');
        const handle = overlay.querySelector('#compareHandle');
        const overlayDiv = overlay.querySelector('#compareOverlay');
        let dragging = false;

        const onMove = (e) => {
            if (!dragging) return;
            const rect = container.getBoundingClientRect();
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            let pct = ((clientX - rect.left) / rect.width) * 100;
            pct = Math.max(5, Math.min(95, pct));
            overlayDiv.style.width = pct + '%';
            handle.style.left = pct + '%';
        };

        const onMouseUp = () => { dragging = false; };

        const cleanup = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.removeEventListener('touchend', onMouseUp);
            close();
        };

        handle.addEventListener('mousedown', () => { dragging = true; });
        handle.addEventListener('touchstart', (e) => { dragging = true; e.preventDefault(); });
        document.addEventListener('mousemove', onMove);
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('touchend', onMouseUp);

        // Replace the auto-close with our cleanup
        const closeBtn = overlay.querySelector('#modalCloseBtn');
        if (closeBtn) closeBtn.onclick = cleanup;
        overlay.onclick = (e) => { if (e.target === overlay) cleanup(); };
    }
};