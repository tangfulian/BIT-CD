import { state } from './state.js';
import { API } from './api.js';
import { I18n } from './i18n.js';
import { ChartUtils, createLineOption } from './chartUtils.js';
import { Modal } from './modal.js';
import { History } from './history.js';

export const Timeline = {
    _plotGroups: null,
    _selectedCards: new Set(),

    init() {},

    async render() {
        const page = document.getElementById('page-timeline');
        if (!page || !page.classList.contains('active')) return;
        const history = await API.fetchHistory();
        this.loadPlotList(history);
    },

    loadPlotList(history) {
        const plots = new Map();
        history.forEach(item => {
            const loc = item.lat_lng || item.location;
            if (!loc) return;
            if (!plots.has(loc)) plots.set(loc, []);
            plots.get(loc).push(item);
        });
        this._plotGroups = plots;

        const select = document.getElementById('timelinePlot');
        if (!select) return;
        select.innerHTML = '<option value="">-- ' + I18n.t('timeline.selectPlotPrompt') + ' --</option>';
        for (const [loc, items] of plots) {
            const opt = document.createElement('option');
            opt.value = loc;
            opt.textContent = (items[0]?.location || loc) + ' (' + items.length + I18n.t('timeline.detectionCountSuffix') + ')';
            select.appendChild(opt);
        }

        if (plots.size > 0) {
            const firstLoc = plots.keys().next().value;
            select.value = firstLoc;
            this.plot(plots.get(firstLoc));
        }

        select.onchange = () => {
            const items = plots.get(select.value) || [];
            this.plot(items);
        };
    },

    plot(data) {
        const dom = document.getElementById('timelineChart');
        if (!dom) return;

        // Reset selected cards
        this._selectedCards.clear();
        this._updateCompareBtn();

        if (!data.length) {
            ChartUtils.dispose('timelineChart');
            document.getElementById('timelinePlotInfo')?.classList.add('hidden');
            document.getElementById('timelineStripSection')?.classList.add('hidden');
            return;
        }

        data.sort((a, b) => new Date(a.time) - new Date(b.time));
        const labels = data.map(d => d.time?.slice(0, 10) || '');
        const ratios = data.map(d => parseFloat(d.ratio) || 0);

        const chart = ChartUtils.init('timelineChart');
        if (chart) {
            ChartUtils.setAndTrack('timelineChart', chart, 'line',
                { labels, values: ratios, seriesName: I18n.t('chart.changeRatioPercent'), showDataZoom: true },
                createLineOption({
                    labels,
                    values: ratios,
                    seriesName: I18n.t('chart.changeRatioPercent'),
                    xLabel: I18n.t('chart.detectionTime'),
                    yLabel: I18n.t('chart.changeRatioPercent'),
                    showDataZoom: true,
                }));
        }

        this._renderPlotInfo(data);
        this._renderImageStrip(data);
    },

    _computeTrend(data) {
        if (!data.length) return { direction: 'stable', arrow: '➡', label: I18n.t('timeline.trendStable') };
        const first = parseFloat(data[0].ratio) || 0;
        const last = parseFloat(data[data.length - 1].ratio) || 0;
        const diff = last - first;
        const threshold = 1.0;
        if (diff > threshold) return { direction: 'up', arrow: '⬆', label: I18n.t('timeline.trendUp') };
        if (diff < -threshold) return { direction: 'down', arrow: '⬇', label: I18n.t('timeline.trendDown') };
        return { direction: 'stable', arrow: '➡', label: I18n.t('timeline.trendStable') };
    },

    _renderPlotInfo(data) {
        const el = document.getElementById('timelinePlotInfo');
        if (!el) return;
        const trend = this._computeTrend(data);
        el.innerHTML = `
            <div class="timeline-plot-info-item">
                <div class="info-value">${data.length}</div>
                <div class="info-label">${I18n.t('timeline.totalDetections')}</div>
            </div>
            <div class="timeline-plot-info-item">
                <div class="info-value">${data[0]?.time?.slice(0, 10) || '-'}</div>
                <div class="info-label">${I18n.t('timeline.firstDetection')}</div>
            </div>
            <div class="timeline-plot-info-item">
                <div class="info-value">${data[data.length - 1]?.time?.slice(0, 10) || '-'}</div>
                <div class="info-label">${I18n.t('timeline.latestDetection')}</div>
            </div>
            <div class="timeline-plot-info-item">
                <div class="info-value trend-${trend.direction}">${trend.arrow} ${trend.label}</div>
                <div class="info-label">${I18n.t('timeline.trendDirection')}</div>
            </div>
        `;
        el.classList.remove('hidden');
    },

    _renderImageStrip(data) {
        const section = document.getElementById('timelineStripSection');
        if (!section) return;
        const strip = document.getElementById('timelineStrip');
        if (!strip) return;

        section.classList.remove('hidden');
        strip.innerHTML = data.map((item, idx) => this._renderStripCard(item, idx)).join('');

        // Bind card clicks and checkboxes
        strip.querySelectorAll('.timeline-strip-card').forEach(card => {
            const idx = parseInt(card.dataset.idx);
            card.onclick = (e) => {
                if (e.target.tagName === 'INPUT') return;
                this._openCardDetail(data[idx]);
            };
        });

        strip.querySelectorAll('.strip-compare-check').forEach(cb => {
            cb.onchange = () => {
                const idx = parseInt(cb.dataset.idx);
                if (cb.checked) {
                    this._selectedCards.add(idx);
                } else {
                    this._selectedCards.delete(idx);
                }
                cb.closest('.timeline-strip-card')?.classList.toggle('selected', cb.checked);
                this._updateCompareBtn();
            };
        });

        // Bind compare button
        const compareBtn = document.getElementById('timelineCompareBtn');
        if (compareBtn) {
            compareBtn.onclick = () => {
                if (this._selectedCards.size === 2) {
                    const [a, b] = [...this._selectedCards];
                    this._openMaskCompare(data[a], data[b]);
                }
            };
        }

        // Setup scroll controls
        this._setupScrollControls(strip);
    },

    _setupScrollControls(strip) {
        const btnLeft = document.getElementById('timelineScrollLeft');
        const btnRight = document.getElementById('timelineScrollRight');
        const fadeLeft = document.getElementById('timelineStripFadeLeft');
        const fadeRight = document.getElementById('timelineStripFadeRight');
        const gridToggle = document.getElementById('timelineGridToggle');

        // 默认展开全部（网格模式）
        strip.classList.add('grid-mode');
        if (btnLeft) btnLeft.style.display = 'none';
        if (btnRight) btnRight.style.display = 'none';
        if (fadeLeft) fadeLeft.style.opacity = '0';
        if (fadeRight) fadeRight.style.opacity = '0';

        if (gridToggle) {
            gridToggle.textContent = I18n.t('timeline.collapseAll');
            gridToggle.onclick = () => {
                const isGrid = strip.classList.toggle('grid-mode');
                if (isGrid) {
                    gridToggle.textContent = I18n.t('timeline.collapseAll');
                    if (btnLeft) btnLeft.style.display = 'none';
                    if (btnRight) btnRight.style.display = 'none';
                    if (fadeLeft) fadeLeft.style.opacity = '0';
                    if (fadeRight) fadeRight.style.opacity = '0';
                } else {
                    gridToggle.textContent = I18n.t('timeline.expandAll');
                    const maxScroll = strip.scrollWidth - strip.clientWidth;
                    const atStart = strip.scrollLeft <= 1;
                    const atEnd = strip.scrollLeft >= maxScroll - 1;
                    if (btnLeft) btnLeft.style.display = maxScroll > 2 && !atStart ? '' : 'none';
                    if (btnRight) btnRight.style.display = maxScroll > 2 && !atEnd ? '' : 'none';
                    if (fadeLeft) fadeLeft.style.opacity = maxScroll > 2 && !atStart ? '1' : '0';
                    if (fadeRight) fadeRight.style.opacity = maxScroll > 2 && !atEnd ? '1' : '0';
                }
            };
        }
    },

    _renderStripCard(item, idx) {
        const ratio = parseFloat(item.ratio) || 0;
        let badgeClass = 'ratio-low';
        if (ratio > 30) badgeClass = 'ratio-high';
        else if (ratio > 15) badgeClass = 'ratio-med';
        else if (ratio > 5) badgeClass = 'ratio-mid';

        const dateStr = item.time?.slice(0, 10) || '';
        const maskUrl = item.mask || '';
        const heatUrl = item.heat || '';
        const fusionUrl = item.fusion || '';

        return `
            <div class="timeline-strip-card" data-idx="${idx}">
                <div class="strip-date">${dateStr}</div>
                <div class="strip-thumbs">
                    ${maskUrl ? `<img class="strip-thumb" src="${maskUrl}" alt="mask" loading="lazy">` : ''}
                    ${heatUrl ? `<img class="strip-thumb" src="${heatUrl}" alt="heat" loading="lazy">` : ''}
                    ${fusionUrl ? `<img class="strip-thumb full" src="${fusionUrl}" alt="fusion" loading="lazy">` : ''}
                </div>
                <div class="strip-ratio ${badgeClass}">${ratio}%</div>
                ${item.ai_change_type ? `<div class="strip-ai-badge">AI: ${item.ai_change_type}</div>` : ''}
                <div class="strip-compare">
                    <input type="checkbox" class="strip-compare-check" data-idx="${idx}">
                    <span>${I18n.t('common.compare')}</span>
                </div>
            </div>
        `;
    },

    _updateCompareBtn() {
        const btn = document.getElementById('timelineCompareBtn');
        if (!btn) return;
        btn.disabled = this._selectedCards.size !== 2;
        if (this._selectedCards.size === 2) {
            btn.textContent = I18n.t('timeline.compareTwo');
        }
    },

    _openCardDetail(item) {
        if (!item) return;
        // Reuse History.showDetail for consistent detail view
        History.showDetail(item);
    },

    _openMaskCompare(a, b) {
        const t = (k) => I18n.t(k);
        const maskUrlA = a.mask || '';
        const heatUrlA = a.heat || '';
        const fusionUrlA = a.fusion || '';
        const maskUrlB = b.mask || '';
        const heatUrlB = b.heat || '';
        const fusionUrlB = b.fusion || '';
        const dateA = a.time?.slice(0, 10) || '-';
        const dateB = b.time?.slice(0, 10) || '-';
        const ratioA = parseFloat(a.ratio) || 0;
        const ratioB = parseFloat(b.ratio) || 0;

        Modal.createOverlay(`
            <div class="modal-box compare-modal-box">
                <div class="modal-title">
                    <span>${t('timeline.compareMasks')}</span>
                </div>
                <div class="modal-content">
                    <div class="compare-dual-grid">
                        <div class="compare-side">
                            <h4 class="compare-side-title">${dateA} · ${ratioA}%</h4>
                            ${maskUrlA ? `<div class="compare-image-card"><h5>${t('history.detailMask')}</h5><img src="${maskUrlA}" crossorigin="anonymous"></div>` : ''}
                            ${heatUrlA ? `<div class="compare-image-card"><h5>${t('history.detailHeat')}</h5><img src="${heatUrlA}" crossorigin="anonymous"></div>` : ''}
                            ${fusionUrlA ? `<div class="compare-image-card"><h5>${t('history.detailFusion')}</h5><img src="${fusionUrlA}" crossorigin="anonymous"></div>` : ''}
                        </div>
                        <div class="compare-divider"></div>
                        <div class="compare-side">
                            <h4 class="compare-side-title">${dateB} · ${ratioB}%</h4>
                            ${maskUrlB ? `<div class="compare-image-card"><h5>${t('history.detailMask')}</h5><img src="${maskUrlB}" crossorigin="anonymous"></div>` : ''}
                            ${heatUrlB ? `<div class="compare-image-card"><h5>${t('history.detailHeat')}</h5><img src="${heatUrlB}" crossorigin="anonymous"></div>` : ''}
                            ${fusionUrlB ? `<div class="compare-image-card"><h5>${t('history.detailFusion')}</h5><img src="${fusionUrlB}" crossorigin="anonymous"></div>` : ''}
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-modal btn-modal-secondary" id="modalCloseBtn">${t('common.close')}</button>
                </div>
            </div>
        `);
    }
};
