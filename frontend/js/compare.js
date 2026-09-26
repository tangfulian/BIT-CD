import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { API } from './api.js';
import { I18n } from './i18n.js';

export const Compare = {
    _historyCache: [],

    init() {
        const btn = document.getElementById("compareBtn");
        if (btn) btn.onclick = () => this.doCompare();

        // Preview when selection changes
        const sel1 = document.getElementById('compareId1');
        const sel2 = document.getElementById('compareId2');
        if (sel1) sel1.onchange = () => this._showPreview();
        if (sel2) sel2.onchange = () => this._showPreview();
    },

    async render() {
        const page = document.getElementById('page-compare');
        if (!page || !page.classList.contains('active')) return;
        const history = await API.fetchHistory();
        this._historyCache = history;

        this._renderStatsBar(history);

        const select1 = document.getElementById('compareId1');
        const select2 = document.getElementById('compareId2');
        if (!select1 || !select2) return;
        var defaultOpt = '<option value="">' + I18n.t('compare.selectRecord') + '</option>';
        select1.innerHTML = defaultOpt;
        select2.innerHTML = defaultOpt;
        history.forEach(function(item) {
            var txt = '#' + item.id + ' ' + (item.model || '?') + ' ' + (item.ratio != null ? item.ratio + '%' : '') + ' ' + (item.time || '');
            var opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = txt;
            select1.appendChild(opt);
            select2.appendChild(opt.cloneNode(true));
        });
    },

    _renderStatsBar(history) {
        var total = history.length;
        var today = 0;
        var sumRatio = 0;
        var models = {};
        var todayStr = new Date().toISOString().slice(0, 10);
        history.forEach(function(item) {
            if (item.time && item.time.slice(0, 10) === todayStr) today++;
            if (item.ratio != null) sumRatio += item.ratio;
            if (item.model) models[item.model] = true;
        });
        var avgRatio = history.length > 0 ? (sumRatio / history.length).toFixed(1) : '0';
        var modelCount = Object.keys(models).length;

        var elTotal = document.getElementById('cmpTotalRecords');
        var elToday = document.getElementById('cmpTodayRecords');
        var elRatio = document.getElementById('cmpAvgRatio');
        var elModel = document.getElementById('cmpModelCount');
        if (elTotal) elTotal.textContent = total;
        if (elToday) elToday.textContent = today;
        if (elRatio) elRatio.textContent = avgRatio + '%';
        if (elModel) elModel.textContent = modelCount;
    },

    _showPreview() {
        const id1 = parseInt(document.getElementById('compareId1').value);
        const id2 = parseInt(document.getElementById('compareId2').value);
        const preview = document.getElementById('comparePreview');
        if (!preview) return;

        var allItems = [];
        if (id1) {
            var r1 = this._historyCache.find(function(h) { return h.id === id1; });
            if (r1) allItems.push({ tag: I18n.t('compare.recordA'), item: r1, color: 'var(--primary)' });
        }
        if (id2) {
            var r2 = this._historyCache.find(function(h) { return h.id === id2; });
            if (r2) allItems.push({ tag: I18n.t('compare.recordB'), item: r2, color: 'var(--accent)' });
        }

        if (allItems.length === 0) {
            preview.classList.add('hidden');
            return;
        }
        preview.classList.remove('hidden');

        var html = '<div class="preview-cards-row">';
        allItems.forEach(function(row) {
            var r = row.item;
            html += '<div class="preview-card" style="border-left: 3px solid ' + row.color + ';">';
            html += '<div class="preview-card-header"><span class="preview-tag">' + row.tag + '</span><strong>#' + r.id + ' - ' + (r.model || '?') + '</strong></div>';
            html += '<div class="preview-card-body">';
            html += '<span>' + I18n.t('detect.changeRatio') + ': <strong>' + (r.ratio != null ? r.ratio + '%' : '--') + '</strong></span>';
            html += '<span>' + I18n.t('detect.changePixel') + ': ' + (r.change_pixel || 0).toLocaleString() + '</span>';
            html += '<span>' + I18n.t('common.time') + ': ' + (r.time || '--') + '</span>';
            if (r.location) html += '<span>' + I18n.t('history.detailLocation') + ': ' + r.location + '</span>';
            html += '</div></div>';
        });
        html += '</div>';

        // If both selected, show quick diff
        if (id1 && id2) {
            var r1 = allItems[0].item;
            var r2 = allItems[1].item;
            if (r1 && r2) {
                var d = ((r1.ratio || 0) - (r2.ratio || 0)).toFixed(2);
                var sign = d >= 0 ? '+' : '';
                var diffColor = Math.abs(d) > 10 ? 'var(--danger)' : Math.abs(d) > 5 ? 'var(--accent)' : 'var(--text-secondary)';
                html += '<div class="preview-quick-diff">';
                html += '<span>' + I18n.t('compare.ratioDiff') + ': <strong style="color:' + diffColor + ';">' + sign + d + '%</strong></span>';
                html += '</div>';
            }
        }

        preview.innerHTML = html;
    },

    async doCompare() {
        const id1 = document.getElementById('compareId1').value;
        const id2 = document.getElementById('compareId2').value;
        if (!id1 || !id2) {
            Utils.showToast(I18n.t('compare.selectTwo'), 'error');
            return;
        }
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/compare?id1=${id1}&id2=${id2}`);
        let data;
        try { data = await res.json(); } catch { return Utils.showToast(I18n.t('compare.failed'), 'error'); }
        if (data.code !== 200) {
            Utils.showToast(data.detail || I18n.t('compare.failed'), 'error');
            return;
        }
        const r1 = data.data.result1;
        const r2 = data.data.result2;
        const container = document.getElementById('compareResult');
        const preview = document.getElementById('comparePreview');
        container.classList.remove('hidden');
        if (preview) preview.classList.add('hidden');
        const t = (k) => I18n.t(k);

        const buildInfo = (r) => {
            var html = '';
            html += '<p><span class="info-label">' + t('detect.threshold') + '</span>' + r.threshold + '</p>';
            html += '<p><span class="info-label">' + t('detect.changePixel') + '</span>' + r.change_pixel.toLocaleString() + '</p>';
            html += '<p><span class="info-label">' + t('detect.totalPixel') + '</span>' + r.total_pixel.toLocaleString() + '</p>';
            if (r.change_type) html += '<p><span class="info-label">' + t('history.detailChangeType') + '</span>' + r.change_type + '</p>';
            if (r.location) html += '<p><span class="info-label">' + t('history.detailLocation') + '</span>' + r.location + '</p>';
            if (r.t1_time || r.t2_time) {
                html += '<p><span class="info-label">' + t('compare.t1t2Time') + '</span>' + (r.t1_time || '?') + ' → ' + (r.t2_time || '?') + '</p>';
            }
            if (r.ai_change_type) {
                html += '<p><span class="info-label">' + t('classify.aiSuggestion') + '</span>';
                html += r.ai_change_type;
                if (r.ai_confidence) html += ' (' + (r.ai_confidence * 100).toFixed(0) + '%)';
                html += '</p>';
            }
            html += '<p><span class="info-label">' + t('common.time') + '</span>' + r.time + '</p>';
            return html;
        };

        const ratioDiff = (r1.ratio - r2.ratio).toFixed(2);
        const pixelDiff = r1.change_pixel - r2.change_pixel;
        const totalDiff = r1.total_pixel - r2.total_pixel;
        const thresholdDiff = (r1.threshold - r2.threshold).toFixed(4);
        const ratioPctChange = r2.ratio !== 0 ? ((ratioDiff / r2.ratio) * 100).toFixed(1) : '0';

        const maxRatioForBar = Math.max(r1.ratio, r2.ratio, 1);
        const bar1Width = (r1.ratio / maxRatioForBar * 100).toFixed(1);
        const bar2Width = (r2.ratio / maxRatioForBar * 100).toFixed(1);

        container.innerHTML = [
            '<div class="compare-columns">',
                '<div class="card compare-card">',
                    '<h3>' + t('compare.recordA') + ' (#' + r1.id + ') - ' + r1.model + ' - <span class="ratio-highlight">' + r1.ratio + '%</span></h3>',
                    '<div class="compare-images">',
                        '<div><span>' + t('history.detailMask') + '</span><img src="' + r1.mask + '"></div>',
                        '<div><span>' + t('history.detailHeat') + '</span><img src="' + r1.heat + '"></div>',
                        '<div style="grid-column: span 2;"><span>' + t('history.detailFusion') + '</span><img src="' + r1.fusion + '"></div>',
                    '</div>',
                    '<div class="compare-info">' + buildInfo(r1) + '</div>',
                '</div>',
                '<div class="card compare-card">',
                    '<h3>' + t('compare.recordB') + ' (#' + r2.id + ') - ' + r2.model + ' - <span class="ratio-highlight">' + r2.ratio + '%</span></h3>',
                    '<div class="compare-images">',
                        '<div><span>' + t('history.detailMask') + '</span><img src="' + r2.mask + '"></div>',
                        '<div><span>' + t('history.detailHeat') + '</span><img src="' + r2.heat + '"></div>',
                        '<div style="grid-column: span 2;"><span>' + t('history.detailFusion') + '</span><img src="' + r2.fusion + '"></div>',
                    '</div>',
                    '<div class="compare-info">' + buildInfo(r2) + '</div>',
                '</div>',
            '</div>',
            '<div class="card compare-diff">',
                '<h3>' + t('compare.diffAnalysis') + '</h3>',
                '<div class="diff-bar-section">',
                    '<div class="diff-bar-row">',
                        '<span class="diff-bar-label">' + t('compare.recordA') + '</span>',
                        '<div class="diff-bar-track"><div class="diff-bar-fill diff-bar-a" style="width:' + bar1Width + '%"></div></div>',
                        '<span class="diff-bar-value">' + r1.ratio + '%</span>',
                    '</div>',
                    '<div class="diff-bar-row">',
                        '<span class="diff-bar-label">' + t('compare.recordB') + '</span>',
                        '<div class="diff-bar-track"><div class="diff-bar-fill diff-bar-b" style="width:' + bar2Width + '%"></div></div>',
                        '<span class="diff-bar-value">' + r2.ratio + '%</span>',
                    '</div>',
                '</div>',
                '<table class="diff-table">',
                    '<tr><td>' + t('compare.ratioDiff') + '</td><td class="diff-val">' + (ratioDiff >= 0 ? '+' : '') + ratioDiff + '%</td><td class="diff-change">' + t('compare.relativeChange') + ': ' + (ratioPctChange >= 0 ? '+' : '') + ratioPctChange + '%</td></tr>',
                    '<tr><td>' + t('compare.pixelDiff') + '</td><td class="diff-val">' + (pixelDiff >= 0 ? '+' : '') + pixelDiff.toLocaleString() + '</td><td class="diff-change">' + t('compare.pixelPercent') + ': ' + (r2.change_pixel !== 0 ? ((pixelDiff / r2.change_pixel) * 100).toFixed(1) : '0') + '%</td></tr>',
                    '<tr><td>' + t('compare.totalPixelDiff') + '</td><td class="diff-val">' + (totalDiff >= 0 ? '+' : '') + totalDiff.toLocaleString() + '</td><td class="diff-change">' + (totalDiff === 0 ? t('compare.sameValue') : (totalDiff > 0 ? t('compare.aLarger') : t('compare.bLarger'))) + '</td></tr>',
                    '<tr><td>' + t('compare.thresholdDiff') + '</td><td class="diff-val">' + (thresholdDiff >= 0 ? '+' : '') + thresholdDiff + '</td><td class="diff-change">' + (r1.threshold === r2.threshold ? t('compare.sameValue') : (r1.threshold > r2.threshold ? t('compare.aLarger') : t('compare.bLarger'))) + '</td></tr>',
                '</table>',
                '<div class="diff-summary" style="margin-top:12px;">',
                    '<p><strong>' + t('compare.modelCompare') + '：</strong>' + r1.model + ' vs ' + r2.model + (r1.model === r2.model ? ' (' + t('compare.sameModel') + ')' : ' (' + t('compare.diffModel') + ')') + '</p>',
                '</div>',
            '</div>',
            '<div style="text-align:right; margin-top:10px;">',
                '<button class="btn-action" id="exportCompareBtn">' + t('compare.exportCSV') + '</button>',
            '</div>'
        ].join('');

        document.getElementById("exportCompareBtn").onclick = () => {
            Utils.exportCSV([
                [t('compare.metric'), t('compare.recordA'), t('compare.recordB'), t('compare.diff')],
                [t('compare.csvRatio'), r1.ratio, r2.ratio, (r1.ratio - r2.ratio).toFixed(2)],
                [t('detect.changePixel'), r1.change_pixel, r2.change_pixel, r1.change_pixel - r2.change_pixel],
                [t('detect.totalPixel'), r1.total_pixel, r2.total_pixel, r1.total_pixel - r2.total_pixel],
                [t('detect.threshold'), r1.threshold, r2.threshold, (r1.threshold - r2.threshold).toFixed(4)],
                [t('common.model'), r1.model, r2.model, ''],
                [t('common.time'), r1.time, r2.time, '']
            ], '对比报告_' + r1.id + '_' + r2.id);
        };
    }
};