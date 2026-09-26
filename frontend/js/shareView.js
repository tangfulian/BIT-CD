import { Modal } from './modal.js';
import { I18n } from './i18n.js';
import { CONFIG } from './config.js';

function _absUrl(url) {
    if (!url || url.startsWith('http') || url.startsWith('blob:') || url.startsWith('data:')) return url;
    return (CONFIG.API_BASE_URL + '/' + url.replace(/^\//, '')).replace(/([^:]);$/, '$1');
}

export const ShareView = {
    generateUrl(result) {
        const data = {
            model: result.model,
            mask_url: result.mask_url,
            heat_url: result.heat_url,
            fusion_url: result.fusion_url,
            change_pixel: result.change_pixel,
            total_pixel: result.total_pixel,
            ratio: result.change_area_ratio,
            threshold: result.threshold,
            change_type: result.change_type,
            location: result.location,
            actual_area: result.actual_area,
            time: result.time || new Date().toLocaleString()
        };
        const json = JSON.stringify(data);
        const encoded = btoa(encodeURIComponent(json));
        return `${location.origin}${location.pathname}#share=${encoded}`;
    },

    async copyLink(result) {
        const url = this.generateUrl(result);
        try {
            await navigator.clipboard.writeText(url);
            const { Utils } = await import('./utils.js');
            Utils.showToast(I18n.t('share.copied'), 'success');
        } catch {
            // 降级：显示链接让用户手动复制
            const { Utils } = await import('./utils.js');
            Utils.showToast(url, 'info');
        }
    },

    checkAndRender() {
        const hash = location.hash;
        const match = hash.match(/^#share=(.+)$/);
        if (!match) return;
        try {
            const json = decodeURIComponent(atob(match[1]));
            const data = JSON.parse(json);
            this.render(data);
        } catch {}
    },

    render(data) {
        const t = (k) => I18n.t(k);
        Modal.createOverlay(`
            <div class="modal-box share-view-box">
                <div class="modal-title">${t('share.title')}</div>
                <div class="modal-content">
                    <div class="share-stats">
                        <div class="share-stat"><span class="share-label">${t('common.model')}</span><span class="share-value">${data.model || '-'}</span></div>
                        <div class="share-stat"><span class="share-label">${t('detect.changeRatio')}</span><span class="share-value highlight">${data.ratio != null ? data.ratio + '%' : '-'}</span></div>
                        <div class="share-stat"><span class="share-label">${t('detect.changePixel')}</span><span class="share-value">${data.change_pixel != null ? data.change_pixel : '-'} / ${data.total_pixel != null ? data.total_pixel : '-'}</span></div>
                        ${data.actual_area != null ? `<div class="share-stat"><span class="share-label">${t('detect.actualArea')}</span><span class="share-value highlight">${data.actual_area} 亩</span></div>` : ''}
                        <div class="share-stat"><span class="share-label">${t('detect.threshold')}</span><span class="share-value">${data.threshold != null ? data.threshold : '-'}</span></div>
                        <div class="share-stat"><span class="share-label">${t('history.detailChangeType')}</span><span class="share-value">${data.change_type || '-'}</span></div>
                        <div class="share-stat"><span class="share-label">${t('common.location')}</span><span class="share-value">${data.location || '-'}</span></div>
                        <div class="share-stat"><span class="share-label">${t('common.time')}</span><span class="share-value">${data.time || '-'}</span></div>
                    </div>
                    <div class="share-images">
                        ${data.mask_url ? `<div class="share-image-card"><h4>${t('history.detailMask')}</h4><img src="${_absUrl(data.mask_url)}" crossorigin="anonymous"></div>` : ''}
                        ${data.heat_url ? `<div class="share-image-card"><h4>${t('history.detailHeat')}</h4><img src="${_absUrl(data.heat_url)}" crossorigin="anonymous"></div>` : ''}
                        ${data.fusion_url ? `<div class="share-image-card full-width"><h4>${t('history.detailFusion')}</h4><img src="${_absUrl(data.fusion_url)}" crossorigin="anonymous"></div>` : ''}
                    </div>
                </div>
                <div class="modal-footer">
                    <span style="font-size:12px;color:var(--text-tertiary);">${new Date().toLocaleString()}</span>
                    <button class="btn-modal btn-modal-secondary" id="modalCloseBtn">${t('common.close')}</button>
                </div>
            </div>
        `);
    }
};
