/**
 * 多时相时序分析
 *
 * 一个「序列」是同一地块的 N 期观测，期次是挂在序列下的检测记录。
 *
 * 本次改造修掉了两个原有问题：
 *   1. 横轴原先按记录创建时间（created_at）排序 —— 那画的是"你什么时候点的检测"，
 *      不是"影像拍于何时"。现在一律按影像日期排序。
 *   2. 原先的"趋势"只取首末两点差值、阈值硬编码 1.0、不返回数值。现在由后端
 *      做最小二乘拟合，并连 n 与 R² 一起给出，且明确不外推。
 *
 * @module timeline
 */
import { API } from './api.js';
import { I18n } from './i18n.js';
import { ChartUtils, createLineOption, createTrendBarOption } from './chartUtils.js';
import { Modal } from './modal.js';
import { Toast } from './toast.js';
import { Utils } from './utils.js';
import { History } from './history.js';
import { CONFIG } from './config.js';

const $ = (id) => document.getElementById(id);

export const Timeline = {
    _series: [],
    _detail: null,
    _trend: null,
    _selectedCards: new Set(),

    init() {
        const createBtn = $('timelineCreateBtn');
        if (createBtn) createBtn.onclick = () => this._openCreateModal();
        const delBtn = $('timelineDeleteBtn');
        if (delBtn) delBtn.onclick = () => this._deleteSeries();
        const sel = $('timelineSeries');
        if (sel) sel.onchange = () => this._selectSeries(parseInt(sel.value, 10));
    },

    async render() {
        const page = $('page-timeline');
        if (!page || !page.classList.contains('active')) return;
        await this._loadSeriesList();
    },

    async _loadSeriesList() {
        try {
            this._series = await API.fetchSeriesList();
        } catch (e) {
            Toast.error(I18n.t('series.loadFailed', '序列加载失败'));
            return;
        }
        const sel = $('timelineSeries');
        const emptyBox = $('timelineEmpty');
        const body = $('timelineBody');

        if (!sel) return;
        sel.innerHTML = '';
        if (!this._series.length) {
            sel.innerHTML = `<option value="">${I18n.t('series.none', '暂无序列')}</option>`;
            emptyBox?.classList.remove('hidden');
            body?.classList.add('hidden');
            return;
        }
        emptyBox?.classList.add('hidden');
        this._series.forEach((s) => {
            const opt = document.createElement('option');
            opt.value = String(s.id);
            opt.textContent = `${s.name}（${s.member_count} ${I18n.t('series.phases', '期')}）`;
            sel.appendChild(opt);
        });
        sel.value = String(this._series[0].id);
        await this._selectSeries(this._series[0].id);
    },

    async _selectSeries(id) {
        if (!id) return;
        try {
            const [detail, trend] = await Promise.all([
                API.fetchSeriesDetail(id),
                API.fetchSeriesTrend(id),
            ]);
            this._detail = detail;
            this._trend = trend.trend;
        } catch (e) {
            Toast.error(e.message || I18n.t('series.loadFailed', '序列加载失败'));
            return;
        }
        this._selectedCards.clear();
        this._renderAll();
    },

    _renderAll() {
        const body = $('timelineBody');
        if (!body || !this._detail) return;
        body.classList.remove('hidden');
        this._renderSeriesInfo();
        this._renderTrendCards();
        this._renderPhaseTable();
        this._renderCharts();
        this._renderImageStrip(this._detail.records || []);
        this._renderCaveats();
    },

    _renderSeriesInfo() {
        const el = $('timelineSeriesInfo');
        const s = this._detail.series;
        const t = this._trend;
        if (!el) return;
        const items = [
            [s.location || '-', I18n.t('series.location', '地点')],
            [s.area_mu ? s.area_mu + ' ' + I18n.t('unit.mu', '亩') : '-', I18n.t('series.area', '地块面积')],
            [String(t.interval_count), I18n.t('series.intervalCount', '有效区间数')],
            [
                t.summary?.first_start && t.summary?.last_end
                    ? `${t.summary.first_start.slice(0, 7)} → ${t.summary.last_end.slice(0, 7)}`
                    : '-',
                I18n.t('series.span', '观测跨度'),
            ],
        ];
        el.innerHTML = items.map(([v, l]) =>
            `<div class="timeline-plot-info-item"><div class="info-value">${Utils.escapeHtml(String(v))}</div><div class="info-label">${l}</div></div>`
        ).join('');
        el.classList.remove('hidden');
    },

    _renderTrendCards() {
        const el = $('timelineTrendCards');
        const t = this._trend;
        if (!el) return;
        const fit = t.fit;
        const sum = t.summary || {};
        const unit = t.area_mu ? I18n.t('unit.mu', '亩') : '%';

        let cards = '';
        if (!fit) {
            cards = `<div class="trend-card trend-card-muted">
                <div class="trend-card-value">—</div>
                <div class="trend-card-label">${I18n.t('series.needTwo', '至少需 2 个有效区间才能拟合趋势')}</div>
            </div>`;
        } else {
            cards += `<div class="trend-card">
                <div class="trend-card-value">${fit.slope}<span class="trend-card-unit">${Utils.escapeHtml(unit)}/${I18n.t('series.perYear', '年')}</span></div>
                <div class="trend-card-label">${I18n.t('series.slope', '累计变化速率（拟合斜率）')}</div>
            </div>`;
            cards += `<div class="trend-card">
                <div class="trend-card-value">${fit.r2 === null ? '—' : fit.r2}</div>
                <div class="trend-card-label">${I18n.t('series.r2', '拟合优度 R²')} · n=${fit.n}</div>
            </div>`;
        }
        if (sum.total_change_area_mu != null) {
            cards += `<div class="trend-card">
                <div class="trend-card-value">${sum.total_change_area_mu}<span class="trend-card-unit">${I18n.t('unit.mu', '亩')}</span></div>
                <div class="trend-card-label">${I18n.t('series.totalArea', '累计变化面积')}</div>
            </div>`;
        } else if (sum.total_change_ratio_pct != null) {
            cards += `<div class="trend-card">
                <div class="trend-card-value">${sum.total_change_ratio_pct}<span class="trend-card-unit">%</span></div>
                <div class="trend-card-label">${I18n.t('series.totalRatio', '累计变化比例')}</div>
            </div>`;
        }
        if (fit && fit.n < 6) {
            cards += `<div class="trend-card trend-card-warn">
                <div class="trend-card-value">n=${fit.n}</div>
                <div class="trend-card-label">${I18n.t('series.fewPoints', '期次偏少，R² 不稳定，请谨慎判读')}</div>
            </div>`;
        }
        el.innerHTML = cards;
        el.classList.remove('hidden');

        // 突变点单独提示，并且明确标注是启发式判定
        const bpEl = $('timelineBreakpoints');
        if (bpEl) {
            const bps = t.breakpoints || [];
            if (!bps.length) {
                bpEl.classList.add('hidden');
            } else {
                bpEl.classList.remove('hidden');
                bpEl.innerHTML =
                    `<strong>${I18n.t('series.breakpoints', '突变点（启发式）')}</strong>` +
                    bps.map((b) =>
                        `<div class="breakpoint-item">${Utils.escapeHtml(b.start.slice(0, 7))} → ${Utils.escapeHtml(b.end.slice(0, 7))}：${Utils.escapeHtml(b.reason)}</div>`
                    ).join('');
            }
        }
    },

    _renderPhaseTable() {
        const el = $('timelinePhaseTable');
        const t = this._trend;
        if (!el) return;
        const rows = (t.intervals || []).map((iv, i) => {
            const area = iv.change_area_mu != null ? iv.change_area_mu : '-';
            const rate = iv.rate_area_per_year != null
                ? iv.rate_area_per_year + ' ' + I18n.t('unit.mu', '亩') + '/' + I18n.t('series.perYear', '年')
                : (iv.rate_pct_per_year != null ? iv.rate_pct_per_year + '%/' + I18n.t('series.perYear', '年') : '-');
            return `<tr>
                <td>${i + 1}</td>
                <td>${Utils.escapeHtml(iv.start.slice(0, 7))} → ${Utils.escapeHtml(iv.end.slice(0, 7))}</td>
                <td>${iv.days}</td>
                <td>${iv.ratio_pct}%</td>
                <td>${area}</td>
                <td>${rate}</td>
            </tr>`;
        }).join('');

        const skipped = (t.skipped || []);
        const skipNote = skipped.length
            ? `<p class="series-skip-note">${I18n.t('series.skipped', '已跳过')} ${skipped.length} ${I18n.t('series.skippedTail', '条缺日期或日期非法的记录：')}
               ${skipped.map((s) => `#${s.detection_id}（${Utils.escapeHtml(s.reason)}）`).join('、')}</p>`
            : '';

        el.innerHTML = `
            <div class="table-wrapper"><table class="data-table">
                <thead><tr>
                    <th>${I18n.t('series.thIndex', '期次')}</th>
                    <th>${I18n.t('series.thInterval', '影像区间')}</th>
                    <th>${I18n.t('series.thDays', '天数')}</th>
                    <th>${I18n.t('series.thRatio', '变化比例')}</th>
                    <th>${I18n.t('series.thArea', '变化面积（亩）')}</th>
                    <th>${I18n.t('series.thRate', '速率')}</th>
                </tr></thead>
                <tbody>${rows || `<tr><td colspan="6">${I18n.t('series.noIntervals', '没有可用的区间')}</td></tr>`}</tbody>
            </table></div>${skipNote}`;
    },

    _renderCharts() {
        const t = this._trend;
        const ivs = t.intervals || [];
        if (!ivs.length) {
            ChartUtils.dispose('timelineChart');
            ChartUtils.dispose('timelineCumChart');
            return;
        }
        const labels = ivs.map((iv) => iv.end.slice(0, 7));

        // 每区间变化量：柱状图。用 createTrendBarOption 而非 createLineOption ——
        // 后者把 Y 轴单位写死成 %，而这里的量纲可以是亩。
        const useArea = t.area_mu && ivs[0].change_area_mu != null;
        const barValues = ivs.map((iv) => useArea ? iv.change_area_mu : iv.ratio_pct);
        const barUnit = useArea ? I18n.t('unit.mu', '亩') : '%';

        const bar = ChartUtils.init('timelineChart');
        if (bar) {
            ChartUtils.setAndTrack('timelineChart', bar, 'trendBar',
                { labels, values: barValues, seriesName: I18n.t('series.perInterval', '每期变化量') },
                createTrendBarOption({
                    labels, values: barValues,
                    seriesName: `${I18n.t('series.perInterval', '每期变化量')}（${barUnit}）`,
                }));
        }

        // 累计变化比例随时间：折线。这里 % 是对的，故可复用 createLineOption。
        let cum = 0;
        const cumValues = ivs.map((iv) => {
            cum += iv.ratio_pct;
            return Math.round(cum * 100) / 100;
        });
        const line = ChartUtils.init('timelineCumChart');
        if (line) {
            ChartUtils.setAndTrack('timelineCumChart', line, 'line',
                { labels, values: cumValues, seriesName: I18n.t('series.cumulative', '累计变化比例'), showDataZoom: false },
                createLineOption({
                    labels, values: cumValues,
                    seriesName: I18n.t('series.cumulative', '累计变化比例'),
                    xLabel: I18n.t('series.imageDate', '影像日期'),
                    yLabel: '%',
                    showDataZoom: false,
                }));
        }
    },

    _renderCaveats() {
        const el = $('timelineCaveats');
        if (!el || !this._trend) return;
        const list = (this._trend.caveats || []);
        el.innerHTML = list.map((c) => `<div class="caveat-item">${Utils.escapeHtml(c)}</div>`).join('');
    },

    _renderImageStrip(records) {
        const section = $('timelineStripSection');
        const strip = $('timelineStrip');
        if (!section || !strip) return;
        // 卡片顺序同样按影像日期（后端已排好），不是记录创建时间
        section.classList.remove('hidden');
        strip.innerHTML = records.map((r, idx) => this._renderStripCard(r, idx)).join('');

        strip.querySelectorAll('.timeline-strip-card').forEach((card) => {
            const idx = parseInt(card.dataset.idx, 10);
            card.onclick = (e) => {
                if (e.target.tagName === 'INPUT') return;
                this._openCardDetail(records[idx]);
            };
        });
        strip.querySelectorAll('.strip-compare-check').forEach((cb) => {
            cb.onchange = () => {
                const idx = parseInt(cb.dataset.idx, 10);
                if (cb.checked) this._selectedCards.add(idx);
                else this._selectedCards.delete(idx);
                cb.closest('.timeline-strip-card')?.classList.toggle('selected', cb.checked);
                this._updateCompareBtn();
            };
        });
        const compareBtn = $('timelineCompareBtn');
        if (compareBtn) {
            compareBtn.onclick = () => {
                if (this._selectedCards.size === 2) {
                    const [a, b] = [...this._selectedCards];
                    this._openMaskCompare(records[a], records[b]);
                }
            };
        }
        this._setupScrollControls(strip);
    },

    _setupScrollControls(strip) {
        const btnLeft = $('timelineScrollLeft');
        const btnRight = $('timelineScrollRight');
        const fadeLeft = $('timelineStripFadeLeft');
        const fadeRight = $('timelineStripFadeRight');
        const gridToggle = $('timelineGridToggle');

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
                    if (btnLeft) btnLeft.style.display = maxScroll > 2 ? '' : 'none';
                    if (btnRight) btnRight.style.display = maxScroll > 2 ? '' : 'none';
                    if (fadeLeft) fadeLeft.style.opacity = maxScroll > 2 ? '1' : '0';
                    if (fadeRight) fadeRight.style.opacity = maxScroll > 2 ? '1' : '0';
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

        // 显示影像区间，而不是检测时间 —— 后者与"这是哪一期"无关
        const t1 = (item.t1_time || '').slice(0, 7);
        const t2 = (item.t2_time || '').slice(0, 7);
        const dateStr = t1 && t2 ? `${t1} → ${t2}` : (t2 || t1 || '-');

        return `
            <div class="timeline-strip-card" data-idx="${idx}">
                <div class="strip-date">${Utils.escapeHtml(dateStr)}</div>
                <div class="strip-thumbs">
                    ${item.mask ? `<img class="strip-thumb" src="${item.mask}" alt="mask" loading="lazy">` : ''}
                    ${item.heat ? `<img class="strip-thumb" src="${item.heat}" alt="heat" loading="lazy">` : ''}
                    ${item.fusion ? `<img class="strip-thumb full" src="${item.fusion}" alt="fusion" loading="lazy">` : ''}
                </div>
                <div class="strip-ratio ${badgeClass}">${ratio}%</div>
                ${item.change_type ? `<div class="strip-ai-badge">${Utils.escapeHtml(item.change_type)}</div>` : ''}
                <div class="strip-compare">
                    <input type="checkbox" class="strip-compare-check" data-idx="${idx}">
                    <span>${I18n.t('common.compare')}</span>
                </div>
            </div>`;
    },

    _updateCompareBtn() {
        const btn = $('timelineCompareBtn');
        if (!btn) return;
        btn.disabled = this._selectedCards.size !== 2;
    },

    _openCardDetail(item) {
        if (item) History.showDetail(item);
    },

    _openMaskCompare(a, b) {
        const t = (k) => I18n.t(k);
        const fmt = (x) => {
            const t1 = (x.t1_time || '').slice(0, 7), t2 = (x.t2_time || '').slice(0, 7);
            return (t1 && t2 ? `${t1} → ${t2}` : (t2 || t1 || '-')) + ' · ' + (parseFloat(x.ratio) || 0) + '%';
        };
        const side = (x) => `
            <div class="compare-side">
                <h4 class="compare-side-title">${Utils.escapeHtml(fmt(x))}</h4>
                ${x.mask ? `<div class="compare-image-card"><h5>${t('history.detailMask')}</h5><img src="${x.mask}" crossorigin="anonymous"></div>` : ''}
                ${x.heat ? `<div class="compare-image-card"><h5>${t('history.detailHeat')}</h5><img src="${x.heat}" crossorigin="anonymous"></div>` : ''}
                ${x.fusion ? `<div class="compare-image-card"><h5>${t('history.detailFusion')}</h5><img src="${x.fusion}" crossorigin="anonymous"></div>` : ''}
            </div>`;

        Modal.createOverlay(`
            <div class="modal-box compare-modal-box">
                <div class="modal-title"><span>${t('timeline.compareMasks')}</span></div>
                <div class="modal-content">
                    <div class="compare-dual-grid">${side(a)}<div class="compare-divider"></div>${side(b)}</div>
                </div>
                <div class="modal-footer">
                    <button class="btn-modal btn-modal-secondary" id="modalCloseBtn">${t('common.close')}</button>
                </div>
            </div>`);
    },

    async _deleteSeries() {
        const sel = $('timelineSeries');
        const id = sel ? parseInt(sel.value, 10) : 0;
        if (!id) return;
        const ok = await Modal.confirm(I18n.t('series.confirmDelete',
            '删除该序列？检测记录会保留，只是不再归属本序列。'));
        if (!ok) return;
        try {
            await API.deleteSeries(id);
            Toast.success(I18n.t('series.deleted', '序列已删除'));
            await this._loadSeriesList();
        } catch (e) {
            Toast.error(e.message || I18n.t('series.deleteFailed', '删除失败'));
        }
    },

    // ---------------- 新建序列 ----------------

    _openCreateModal() {
        const t = (k, fb) => I18n.t(k, fb);
        Modal.createOverlay(`
            <div class="modal-box series-create-box">
                <div class="modal-title"><span>${t('series.createTitle', '新建影像序列')}</span></div>
                <div class="modal-content">
                    <div class="series-form-row">
                        <div class="form-group"><label>${t('series.name', '序列名称')}</label>
                            <input type="text" id="seriesName" class="form-control" placeholder="${t('series.namePh', '例如：试验田A区 2020-2023')}"></div>
                        <div class="form-group"><label>${t('series.location', '地点')}</label>
                            <input type="text" id="seriesLocation" class="form-control" placeholder="${t('series.locationPh', '例如：黑龙江省大庆市')}"></div>
                        <div class="form-group"><label>${t('series.area', '地块面积（亩）')}</label>
                            <input type="number" id="seriesArea" class="form-control" min="0" step="0.01">
                            <span class="field-hint">${t('series.areaHint', '留空则速率只给 %/年 口径')}</span></div>
                    </div>

                    <div class="series-tabs">
                        <button class="series-tab active" id="seriesTabPick">${t('series.tabPick', '从历史记录勾选')}</button>
                        <button class="series-tab" id="seriesTabUpload">${t('series.tabUpload', '上传新影像')}</button>
                    </div>

                    <div id="seriesPanePick">
                        <p class="field-hint">${t('series.pickHint', '选择同一地块不同时期的检测记录，并补填每期的影像月份（形如 2024-05）。')}</p>
                        <div id="seriesRecordList" class="series-record-list">${t('common.loading', '加载中…')}</div>
                    </div>

                    <div id="seriesPaneUpload" class="hidden">
                        <p class="field-hint">${t('series.uploadHint', '按时间顺序上传各期影像，系统会对相邻两期逐一检测（N 期影像产生 N-1 次检测）。')}</p>
                        <div id="seriesUploadRows"></div>
                        <button class="btn-gray btn-sm" id="seriesAddRow">+ ${t('series.addPhase', '添加一期')}</button>
                    </div>

                    <div id="seriesCreateMsg" class="series-create-msg hidden"></div>
                </div>
                <div class="modal-footer">
                    <button class="btn-modal btn-modal-secondary" id="seriesCancel">${t('common.cancel', '取消')}</button>
                    <button class="btn-modal btn-modal-primary" id="seriesSubmit">${t('series.submit', '创建')}</button>
                </div>
            </div>`);

        this._createMode = 'pick';
        $('seriesTabPick').onclick = () => this._switchCreateTab('pick');
        $('seriesTabUpload').onclick = () => this._switchCreateTab('upload');
        $('seriesCancel').onclick = () => document.querySelector('.modal-overlay')?.remove();
        $('seriesSubmit').onclick = () => this._submitCreate();
        $('seriesAddRow').onclick = () => this._addUploadRow();

        this._loadPickableRecords();
        for (let i = 0; i < 3; i++) this._addUploadRow();
    },

    _switchCreateTab(mode) {
        this._createMode = mode;
        $('seriesTabPick')?.classList.toggle('active', mode === 'pick');
        $('seriesTabUpload')?.classList.toggle('active', mode === 'upload');
        $('seriesPanePick')?.classList.toggle('hidden', mode !== 'pick');
        $('seriesPaneUpload')?.classList.toggle('hidden', mode !== 'upload');
    },

    async _loadPickableRecords() {
        const box = $('seriesRecordList');
        if (!box) return;
        try {
            const res = await Utils.authFetch(CONFIG.API_BASE_URL + '/history?limit=500');
            const json = await res.json();
            const records = (json.data || []).filter((r) => !r.series_id);
            if (!records.length) {
                box.innerHTML = `<p class="field-hint">${I18n.t('series.noPickable', '暂无可用的检测记录')}</p>`;
                return;
            }
            box.innerHTML = records.slice(0, 200).map((r) => `
                <div class="series-record-row">
                    <label class="series-record-check">
                        <input type="checkbox" class="series-pick" value="${r.id}">
                        <span>#${r.id} · ${Utils.escapeHtml(r.location || '-')} · ${r.ratio}% · ${Utils.escapeHtml(r.model || '')}</span>
                    </label>
                    <input type="month" class="form-control series-t1" data-id="${r.id}" value="${Utils.escapeHtml(r.t1_time || '')}" placeholder="T1">
                    <input type="month" class="form-control series-t2" data-id="${r.id}" value="${Utils.escapeHtml(r.t2_time || '')}" placeholder="T2">
                </div>`).join('');
        } catch (e) {
            box.innerHTML = `<p class="field-hint">${I18n.t('series.loadFailed', '序列加载失败')}</p>`;
        }
    },

    _addUploadRow() {
        const box = $('seriesUploadRows');
        if (!box) return;
        const idx = box.children.length + 1;
        const row = document.createElement('div');
        row.className = 'series-upload-row';
        row.innerHTML = `
            <span class="series-upload-idx">${idx}</span>
            <input type="file" class="form-control series-file" accept="image/*">
            <input type="month" class="form-control series-month">
            <button class="btn-gray btn-sm series-remove">×</button>`;
        row.querySelector('.series-remove').onclick = () => {
            row.remove();
            [...box.children].forEach((r, i) => {
                r.querySelector('.series-upload-idx').textContent = String(i + 1);
            });
        };
        box.appendChild(row);
    },

    _msg(text, kind) {
        const el = $('seriesCreateMsg');
        if (!el) return;
        el.className = 'series-create-msg ' + (kind || '');
        el.textContent = text;
        el.classList.remove('hidden');
    },

    async _submitCreate() {
        const name = ($('seriesName')?.value || '').trim();
        const location = ($('seriesLocation')?.value || '').trim();
        const area = parseFloat($('seriesArea')?.value) || 0;
        if (!name) {
            this._msg(I18n.t('series.needName', '请填写序列名称'), 'error');
            return;
        }

        const btn = $('seriesSubmit');
        if (btn) btn.disabled = true;
        try {
            const created = await API.createSeries({ name, location, area_mu: area });
            const sid = created.series.id;

            if (this._createMode === 'pick') {
                const picks = [...document.querySelectorAll('.series-pick:checked')];
                if (!picks.length) {
                    this._msg(I18n.t('series.needPick', '请至少勾选一条检测记录'), 'error');
                    return;
                }
                const records = picks.map((cb) => {
                    const id = cb.value;
                    return {
                        detection_id: parseInt(id, 10),
                        t1_time: document.querySelector(`.series-t1[data-id="${id}"]`)?.value || '',
                        t2_time: document.querySelector(`.series-t2[data-id="${id}"]`)?.value || '',
                    };
                });
                await API.attachSeriesRecords(sid, records);
            } else {
                await this._runUploads(sid, { location });
            }

            Toast.success(I18n.t('series.created', '序列已创建'));
            document.querySelector('.modal-overlay')?.remove();
            await this._loadSeriesList();
            const sel = $('timelineSeries');
            if (sel) { sel.value = String(sid); await this._selectSeries(sid); }
        } catch (e) {
            this._msg(e.message || I18n.t('series.createFailed', '创建序列失败'), 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    /** 按顺序对相邻两期跑检测，N 期产生 N-1 次 */
    async _runUploads(seriesId, meta) {
        const rows = [...document.querySelectorAll('.series-upload-row')];
        const phases = [];
        for (const r of rows) {
            const f = r.querySelector('.series-file')?.files?.[0];
            const m = r.querySelector('.series-month')?.value || '';
            if (f) phases.push({ file: f, month: m });
        }
        if (phases.length < 2) {
            throw new Error(I18n.t('series.needTwoImages', '至少需要两期影像'));
        }
        if (phases.some((p) => !p.month)) {
            throw new Error(I18n.t('series.needMonth', '每期影像都要填写观测月份'));
        }

        for (let i = 0; i < phases.length - 1; i++) {
            this._msg(I18n.t('series.running', '正在检测第') + ` ${i + 1}/${phases.length - 1} ` +
                I18n.t('series.runningTail', '个区间…'), 'info');
            const fd = new FormData();
            fd.append('img1', phases[i].file);
            fd.append('img2', phases[i + 1].file);
            // 模型与阈值在这里是**写死的**。
            // 原代码是 `$('seriesModel')?.value || 'BIT'` —— 但全前端没有任何
            // 元素的 id 是 seriesModel（建序列弹窗里只有 name/location/area 与
            // 上传行）。可选链让 undefined 静默退化成 'BIT'，看起来可配置、
            // 实际一直跑 BIT。要让它可配，得先在弹窗里加选择器；在那之前，
            // 与其留一个查不到的元素假装可配，不如把事实写出来。
            fd.append('model', 'BIT');
            fd.append('threshold', '0.5');
            fd.append('series_id', String(seriesId));
            fd.append('phase_index', String(i));
            fd.append('t1_time', phases[i].month);
            fd.append('t2_time', phases[i + 1].month);
            fd.append('lat_lng', '');
            fd.append('location', meta.location || '');

            const res = await Utils.authFetch(CONFIG.API_BASE_URL + '/detect', {
                method: 'POST', body: fd,
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `第 ${i + 1} 个区间检测失败`);
            }
        }
    }
};
