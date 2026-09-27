/**
 * NDVI 植被指数查看器 + 面积统计面板
 * @module ndviViewer
 */
import { CONFIG } from './config.js';
import { API } from './api.js';
import { Utils } from './utils.js';
import { I18n } from './i18n.js';
import { Modal } from './modal.js';
import { state } from './state.js';

export const NDVIViewer = {

    init() {
        // Hooks into detection result area via result actions
    },

    /** 为已上传的影像计算 NDVI */
    async computeForImage(fileInputId) {
        const fileInput = document.getElementById(fileInputId);
        if (!fileInput || !fileInput.files[0]) {
            Modal.alert(I18n.t('ndvi.uploadFirst'));
            return;
        }
        try {
            const result = await API.computeNDVI(fileInput.files[0]);
            if (result.code === 200) {
                this._showNDVIResult(result.ndvi, fileInputId);
            }
        } catch (e) {
            Modal.alert(I18n.t('ndvi.failed') + ': ' + e.message);
        }
    },

    _showNDVIResult(ndvi, sourceId) {
        // 缺 approximate 字段时按近似处理：宁可多提示，也不要把近似值
        // 当成定量 NDVI 展示给用户（旧版后端不返回该字段）。
        const approx = ndvi.approximate !== false;
        const html = [
            '<div class="modal-box" style="max-width:650px;">',
                '<div class="modal-title">' + I18n.t('ndvi.title') +
                    (approx ? ' <span class="ndvi-approx-badge">' + I18n.t('ndvi.approxBadge') + '</span>' : '') +
                '</div>',
                approx ? '<div class="ndvi-approx-note">' + I18n.t('ndvi.approxNote') + '</div>' : '',
                '<div class="ndvi-classification-grid">',
                    '<div class="ndvi-class-item water"><div class="ndvi-class-dot"></div><span>' + I18n.t('ndvi.water') + '</span><strong>' + ndvi.classification.water.toLocaleString() + '</strong></div>',
                    '<div class="ndvi-class-item bare"><div class="ndvi-class-dot"></div><span>' + I18n.t('ndvi.bareSoil') + '</span><strong>' + ndvi.classification.bare_soil.toLocaleString() + '</strong></div>',
                    '<div class="ndvi-class-item low"><div class="ndvi-class-dot"></div><span>' + I18n.t('ndvi.lowVeg') + '</span><strong>' + ndvi.classification.low_veg.toLocaleString() + '</strong></div>',
                    '<div class="ndvi-class-item mid"><div class="ndvi-class-dot"></div><span>' + I18n.t('ndvi.midVeg') + '</span><strong>' + ndvi.classification.mid_veg.toLocaleString() + '</strong></div>',
                    '<div class="ndvi-class-item high"><div class="ndvi-class-dot"></div><span>' + I18n.t('ndvi.highVeg') + '</span><strong>' + ndvi.classification.high_veg.toLocaleString() + '</strong></div>',
                '</div>',
                '<div class="ndvi-stats-row">',
                    '<div class="ndvi-stat"><span>' + I18n.t('ndvi.min') + '</span><strong>' + ndvi.ndvi_min.toFixed(4) + '</strong></div>',
                    '<div class="ndvi-stat"><span>' + I18n.t('ndvi.max') + '</span><strong>' + ndvi.ndvi_max.toFixed(4) + '</strong></div>',
                    '<div class="ndvi-stat"><span>' + I18n.t('ndvi.mean') + '</span><strong>' + ndvi.ndvi_mean.toFixed(4) + '</strong></div>',
                    '<div class="ndvi-stat"><span>' + I18n.t('ndvi.std') + '</span><strong>' + ndvi.ndvi_std.toFixed(4) + '</strong></div>',
                '</div>',
                '<div class="ndvi-scale-bar">',
                    '<div class="ndvi-scale-gradient"></div>',
                    '<div class="ndvi-scale-labels"><span>-1.0</span><span>0</span><span>+1.0</span></div>',
                '</div>',
                '<div class="modal-footer">',
                    '<button class="btn-modal-primary" onclick="this.closest(\'.modal-overlay\').remove()">' + I18n.t('common.close') + '</button>',
                '</div>',
            '</div>'
        ].join('');

        Modal.createOverlay(html);
    },

    /** 计算当前检测结果的面积统计 */
    async showAreaStats() {
        const result = state.currentDetectResult;
        if (!result || !result.detection_id) {
            Modal.alert(I18n.t('detect.completeFirst'));
            return;
        }
        try {
            const areaEl = document.getElementById('area');
            const areaMu = parseFloat(areaEl?.value) || 0;
            // Rough resolution estimate: if we know area in mu and pixel count, derive resolution
            let resolution = 0;
            if (areaMu > 0 && result.total_pixel > 0) {
                const totalM2 = areaMu * 666.67;
                const m2PerPx = totalM2 / result.total_pixel;
                resolution = Math.sqrt(m2PerPx);
            }

            const res = await API.computeAreaStats(result.detection_id, resolution);
            if (res.code === 200) {
                this._showAreaStats(res.area_stats);
            }
        } catch (e) {
            Modal.alert(I18n.t('areaStats.failed') + ': ' + e.message);
        }
    },

    _showAreaStats(stats) {
        const items = [
            { key: 'total_pixel', label: I18n.t('areaStats.totalPixel'), value: stats.total_pixel?.toLocaleString() },
            { key: 'change_pixel', label: I18n.t('areaStats.changePixel'), value: stats.change_pixel?.toLocaleString() },
            { key: 'ratio_pct', label: I18n.t('areaStats.ratio'), value: stats.ratio_pct + '%', highlight: true },
        ];
        if (stats.change_area_m2) {
            items.push({ key: 'area_m2', label: I18n.t('areaStats.m2'), value: stats.change_area_m2.toLocaleString() + ' m²' });
            items.push({ key: 'area_mu', label: I18n.t('areaStats.mu'), value: stats.change_area_mu.toLocaleString() + ' ' + I18n.t('unit.mu'), highlight: true });
            items.push({ key: 'area_ha', label: I18n.t('areaStats.ha'), value: stats.change_area_ha.toLocaleString() + ' ha' });
        }

        const rows = items.map(item => {
            const cls = item.highlight ? ' class="area-stat-highlight"' : '';
            return '<div class="area-stat-row"' + cls + '><span>' + item.label + '</span><strong>' + item.value + '</strong></div>';
        }).join('');

        const html = [
            '<div class="modal-box" style="max-width:480px;">',
                '<div class="modal-title">' + I18n.t('areaStats.title') + '</div>',
                '<div class="area-stats-grid">' + rows + '</div>',
                stats.resolution_m ? '<p style="margin-top:12px;font-size:12px;color:var(--text-tertiary);">' + I18n.t('areaStats.resolution') + ': ' + stats.resolution_m.toFixed(2) + ' m/px</p>' : '',
                '<div class="modal-footer">',
                    '<button class="btn-modal-primary" onclick="this.closest(\'.modal-overlay\').remove()">' + I18n.t('common.close') + '</button>',
                '</div>',
            '</div>'
        ].join('');

        Modal.createOverlay(html);
    },

    /** 检查已上传的 T1/T2 影像是否配准 */
    async checkRegistration() {
        const file1 = document.getElementById('file1')?.files[0];
        const file2 = document.getElementById('file2')?.files[0];
        if (!file1 || !file2) {
            Modal.alert(I18n.t('detect.uploadFirst'));
            return;
        }
        try {
            const res = await API.checkRegistration(file1, file2);
            if (res.code === 200) {
                const reg = res.registration;
                const cls = reg.aligned ? 'reg-ok' : 'reg-warn';
                const icon = reg.aligned ? '✅' : '⚠️';
                Modal.alert(icon + ' ' + reg.reason + '\n\n' + I18n.t('registration.score') + ': ' + reg.score.toFixed(4), cls);
            }
        } catch (e) {
            Modal.alert(I18n.t('registration.failed') + ': ' + e.message);
        }
    },

    /** 导出当前检测结果的变化掩膜为 GeoJSON */
    async exportGeoJSON() {
        const result = state.currentDetectResult;
        if (!result || !result.detection_id) {
            Modal.alert(I18n.t('detect.completeFirst'));
            return;
        }
        try {
            const res = await API.exportGeoJSON(result.detection_id, true);
            if (res.code === 200) {
                const jsonStr = JSON.stringify(res.geojson, null, 2);
                const blob = new Blob([jsonStr], { type: 'application/geo+json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'change_mask_' + result.detection_id + '.geojson';
                a.click();
                URL.revokeObjectURL(url);
                Utils.showToast(I18n.t('geojson.exported'), 'success');
            }
        } catch (e) {
            Modal.alert(I18n.t('geojson.failed') + ': ' + e.message);
        }
    }
};
