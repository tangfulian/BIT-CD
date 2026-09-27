/**
 * 农业灾害定损
 *
 * 界面上刻意把三类数字分区展示：
 *   实测（系统算出）  —— 变化像素、分级面积
 *   假设（人给定）    —— 亩产、单价、减产比例、分级下界、查勘单价
 *   草稿（AI 生成）   —— 说明文字，非结论
 * 三者混在一起展示是这个功能最大的风险：假设值会被读成测算结论。
 *
 * @module disaster
 */
import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { I18n } from './i18n.js';
import { Modal } from './modal.js';
import { Toast } from './toast.js';
import { API } from './api.js';
import { ChartUtils } from './chartUtils.js';

const $ = (id) => document.getElementById(id);

export const Disaster = {
    _params: null,      // /disaster/params 的默认值
    _records: [],       // 可用于定损的历史记录（必须有概率图）
    _result: null,      // 最近一次测算结果
    _draft: '',         // AI 说明草稿

    init() {
        const btn = $('disasterAssessBtn');
        if (btn) btn.onclick = () => this._assess();

        const resetBtn = $('disasterResetBtn');
        if (resetBtn) resetBtn.onclick = () => this._fillDefaults();

        const draftBtn = $('disasterDraftBtn');
        if (draftBtn) draftBtn.onclick = () => this._narrative();

        const csvBtn = $('disasterExportCsv');
        if (csvBtn) csvBtn.onclick = () => this._exportCsv();

        const pdfBtn = $('disasterExportPdf');
        if (pdfBtn) pdfBtn.onclick = () => this._exportPdf();

        const cropSel = $('disasterCrop');
        if (cropSel) cropSel.onchange = () => this._applyCropDefaults();
    },

    /** 切到本页时调用：记录列表与默认参数都要现拉 */
    async render() {
        await Promise.all([this._loadRecords(), this._loadParams()]);
    },

    async _loadParams() {
        try {
            const data = await API.fetchDisasterParams();
            if (data.code === 200) {
                this._params = data;
                this._populateCropOptions();
                this._fillDefaults();
            }
        } catch (e) {
            Toast.error(I18n.t('disaster.paramsFailed', '默认参数加载失败'));
        }
    },

    async _loadRecords() {
        const sel = $('disasterRecord');
        if (!sel) return;
        try {
            const res = await Utils.authFetch(CONFIG.API_BASE_URL + '/history?limit=500');
            if (!res.ok) return;
            const json = await res.json();
            // 只有带概率图的记录能定损：没有 score 的记录（多模型对比产生的、
            // 以及早期记录）后端会拒绝，不该让用户选到。
            this._records = (json.data || []).filter((r) => r.score);
            sel.innerHTML = '';
            if (this._records.length === 0) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = I18n.t('disaster.noRecords', '暂无可用于定损的记录');
                sel.appendChild(opt);
                return;
            }
            this._records.forEach((r) => {
                const opt = document.createElement('option');
                opt.value = String(r.id);
                opt.textContent = `#${r.id} · ${r.model || '-'} · ${r.ratio != null ? r.ratio + '%' : '-'} · ${r.time || ''}`
                    + (r.location ? ` · ${r.location}` : '');
                sel.appendChild(opt);
            });
            this._syncAreaFromRecord();
        } catch (e) {
            Toast.error(I18n.t('disaster.recordsFailed', '记录列表加载失败'));
        }
    },

    /** 记录本身不含地块面积，只能由使用者填；这里不猜、不预填假值 */
    _syncAreaFromRecord() {
        const areaEl = $('disasterArea');
        if (areaEl && !areaEl.value) areaEl.value = '';
    },

    _populateCropOptions() {
        const sel = $('disasterCrop');
        if (!sel || !this._params) return;
        sel.innerHTML = '';
        Object.keys(this._params.crop_params || {}).forEach((name) => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            sel.appendChild(opt);
        });
    },

    _applyCropDefaults() {
        const crop = $('disasterCrop')?.value;
        const p = this._params?.crop_params?.[crop];
        if (!p) return;
        if ($('disasterYield')) $('disasterYield').value = p.yield_per_mu;
        if ($('disasterPrice')) $('disasterPrice').value = p.price_per_kg;
    },

    _fillDefaults() {
        const p = this._params;
        if (!p) return;
        this._applyCropDefaults();
        const lr = p.loss_rates || {};
        if ($('disasterRateMild')) $('disasterRateMild').value = Math.round((lr.mild ?? 0) * 100);
        if ($('disasterRateModerate')) $('disasterRateModerate').value = Math.round((lr.moderate ?? 0) * 100);
        if ($('disasterRateSevere')) $('disasterRateSevere').value = Math.round((lr.severe ?? 0) * 100);
        if ($('disasterRateTotal')) $('disasterRateTotal').value = Math.round((lr.total ?? 0) * 100);

        const gb = p.grade_bounds || {};
        if ($('disasterBoundModerate')) $('disasterBoundModerate').value = gb.moderate;
        if ($('disasterBoundSevere')) $('disasterBoundSevere').value = gb.severe;
        if ($('disasterBoundTotal')) $('disasterBoundTotal').value = gb.total;

        const sc = p.survey_costs || {};
        if ($('disasterManualCost')) $('disasterManualCost').value = sc.manual_per_mu;
        if ($('disasterRemoteCost')) $('disasterRemoteCost').value = sc.remote_per_mu;
    },

    _payload() {
        const num = (id, fallback) => {
            const v = parseFloat($(id)?.value);
            return Number.isFinite(v) ? v : fallback;
        };
        return {
            detection_id: parseInt($('disasterRecord')?.value, 10),
            area_mu: num('disasterArea', 0),
            crop_type: $('disasterCrop')?.value || '',
            yield_per_mu: num('disasterYield', null),
            price_per_kg: num('disasterPrice', null),
            loss_rates: {
                mild: num('disasterRateMild', 20) / 100,
                moderate: num('disasterRateModerate', 40) / 100,
                severe: num('disasterRateSevere', 70) / 100,
                total: num('disasterRateTotal', 100) / 100,
            },
            grade_bounds: {
                moderate: num('disasterBoundModerate', null),
                severe: num('disasterBoundSevere', null),
                total: num('disasterBoundTotal', null),
            },
            survey_costs: {
                manual_per_mu: num('disasterManualCost', null),
                remote_per_mu: num('disasterRemoteCost', null),
            },
        };
    },

    async _assess() {
        const payload = this._payload();
        if (!payload.detection_id) {
            Modal.alert(I18n.t('disaster.pickRecord', '请先选择一条检测记录'));
            return;
        }
        if (!payload.area_mu) {
            Modal.alert(I18n.t('disaster.needArea', '请填写地块总面积（亩）—— 受灾面积由它按像素占比摊派'));
            return;
        }
        const btn = $('disasterAssessBtn');
        if (btn) btn.disabled = true;
        try {
            const data = await API.assessDisaster(payload);
            this._result = data.result;
            this._draft = '';
            this._renderResult();
        } catch (e) {
            Toast.error(e.message || I18n.t('disaster.assessFailed', '定损测算失败'));
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    _renderResult() {
        const r = this._result;
        const box = $('disasterResult');
        if (!box || !r) return;
        box.classList.remove('hidden');
        const t = (k, fb) => I18n.t(k, fb);
        const yuan = (v) => Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        let html = '';

        // ---- 一、受灾分级（系统算出） ----
        html += `<div class="card disaster-card">`;
        html += `<h3 class="disaster-card-title">${t('disaster.secGrade', '受灾分级（系统测算）')}</h3>`;
        html += `<div class="table-wrapper"><table class="data-table"><thead><tr>`;
        html += `<th>${t('disaster.level', '等级')}</th><th>${t('disaster.pixels', '变化像素')}</th>`;
        html += `<th>${t('disaster.areaMu', '面积（亩）')}</th><th>${t('disaster.lossRate', '减产比例（假设）')}</th>`;
        html += `<th>${t('disaster.lossYuan', '估算损失（元）')}</th></tr></thead><tbody>`;
        r.levels.forEach((l) => {
            html += `<tr><td>${Utils.escapeHtml(l.label)}</td><td>${l.pixels}</td>`;
            html += `<td>${l.area_mu}</td><td>${(l.loss_rate * 100).toFixed(0)}%</td>`;
            html += `<td>${yuan(l.loss_yuan)}</td></tr>`;
        });
        html += `<tr class="disaster-total-row"><td>${t('disaster.total', '合计')}</td><td>${r.change_pixel}</td>`;
        html += `<td>${r.affected_area_mu}</td><td>—</td><td>${yuan(r.total_loss_yuan)}</td></tr>`;
        html += `</tbody></table></div>`;
        html += `<div id="disasterChart" class="disaster-chart"></div>`;
        html += `<p class="disaster-note">${Utils.escapeHtml(r.disclaimer)}</p>`;
        html += `</div>`;

        // ---- 二、查勘成本对比 ----
        const sc = r.survey_cost;
        html += `<div class="card disaster-card">`;
        html += `<h3 class="disaster-card-title">${t('disaster.secCost', '查勘成本对比')}</h3>`;
        html += `<div class="disaster-cost-grid">`;
        html += `<div class="disaster-cost-item"><span>${t('disaster.manualCost', '人工踏勘')}</span>`
            + `<strong>${yuan(sc.manual_cost_yuan)} 元</strong>`
            + `<em>${sc.manual_per_mu} 元/亩 · ${sc.manual_days} 天</em></div>`;
        html += `<div class="disaster-cost-item"><span>${t('disaster.remoteCost', '遥感定损')}</span>`
            + `<strong>${yuan(sc.remote_cost_yuan)} 元</strong>`
            + `<em>${sc.remote_per_mu} 元/亩 · ${sc.remote_days} 天</em></div>`;
        html += `<div class="disaster-cost-item highlight"><span>${t('disaster.saving', '节省')}</span>`
            + `<strong>${yuan(sc.saving_yuan)} 元</strong>`
            + `<em>${t('disaster.cycle', '周期')} ${sc.manual_days} → ${sc.remote_days} ${t('disaster.days', '天')}</em></div>`;
        html += `</div>`;
        html += `<p class="disaster-note">${Utils.escapeHtml(sc.source_note)}</p>`;
        html += `</div>`;

        // ---- 三、假设参数（必须与测算结果分开列） ----
        html += `<div class="card disaster-card disaster-assumptions">`;
        html += `<h3 class="disaster-card-title">${t('disaster.secAssumptions', '本次采用的假设参数')}`
            + `<span class="assumption-badge">${t('disaster.assumptionBadge', '假设，非实测')}</span></h3>`;
        html += `<div class="table-wrapper"><table class="data-table"><thead><tr>`;
        html += `<th>${t('disaster.param', '参数')}</th><th>${t('disaster.value', '取值')}</th>`;
        html += `<th>${t('disaster.source', '来源说明')}</th></tr></thead><tbody>`;
        r.assumptions.forEach((a) => {
            const val = typeof a.value === 'object' ? JSON.stringify(a.value) : `${a.value} ${a.unit || ''}`;
            html += `<tr><td>${Utils.escapeHtml(a.label)}</td><td>${Utils.escapeHtml(val)}</td>`;
            html += `<td class="disaster-source">${Utils.escapeHtml(a.note)}</td></tr>`;
        });
        html += `</tbody></table></div></div>`;

        // ---- 四、AI 说明草稿（独立分区，带固定横幅） ----
        html += `<div class="card disaster-card">`;
        html += `<h3 class="disaster-card-title">${t('disaster.secDraft', '定损说明')}`;
        html += this._draft ? `<span class="draft-badge">${t('disaster.draftBadge', 'AI 草稿 · 需人工复核')}</span>` : '';
        html += `</h3>`;
        if (this._draft) {
            html += `<div class="draft-disclaimer">${Utils.escapeHtml(
                this._imageDisclaimer || t('disaster.noImage', '本说明由大模型根据上述数值生成，模型未接收任何影像数据。'))}</div>`;
            html += `<div class="draft-body">${Utils.escapeHtml(this._draft)}</div>`;
        } else {
            html += `<p class="disaster-note">${t('disaster.draftHint', '尚未生成。点击下方按钮由 AI 依据上表数值撰写，生成后需人工复核。')}</p>`;
        }
        html += `</div>`;

        box.innerHTML = html;
        this._renderChart();
    },

    _renderChart() {
        const el = $('disasterChart');
        if (!el || !this._result) return;
        const levels = this._result.levels.filter((l) => l.pixels > 0);
        if (levels.length === 0) return;
        ChartUtils.setAndTrack(
            'disasterChart',
            ChartUtils.init('disasterChart'),
            'doughnut',
            null,
            ChartUtils.createDoughnutOption({
                labels: levels.map((l) => l.label),
                values: levels.map((l) => l.area_mu),
            })
        );
    },

    async _narrative() {
        if (!this._result) {
            Modal.alert(I18n.t('disaster.assessFirst', '请先完成定损测算'));
            return;
        }
        const btn = $('disasterDraftBtn');
        if (btn) btn.disabled = true;
        try {
            const data = await API.generateDisasterNarrative(this._payload());
            if (data.code !== 200) {
                // 草稿失败不影响已算出的金额，只是不显示文字
                Toast.error(data.error || I18n.t('disaster.draftFailed', '草稿生成失败'));
                return;
            }
            this._draft = data.draft || '';
            this._imageDisclaimer = data.image_disclaimer || '';
            this._renderResult();
        } catch (e) {
            Toast.error(e.message || I18n.t('disaster.draftFailed', '草稿生成失败'));
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    _exportCsv() {
        if (!this._result) {
            Modal.alert(I18n.t('disaster.assessFirst', '请先完成定损测算'));
            return;
        }
        const r = this._result;
        const rows = [
            [I18n.t('disaster.csvHeaderNote', '本表为遥感代理测算结果，非实测减产率，不作为理赔依据')],
            [],
            [I18n.t('disaster.level', '等级'), I18n.t('disaster.pixels', '变化像素'),
             I18n.t('disaster.areaMu', '面积（亩）'), I18n.t('disaster.lossRate', '减产比例（假设）'),
             I18n.t('disaster.lossYuan', '估算损失（元）')],
        ];
        r.levels.forEach((l) => rows.push([l.label, l.pixels, l.area_mu, l.loss_rate, l.loss_yuan]));
        rows.push([I18n.t('disaster.total', '合计'), r.change_pixel, r.affected_area_mu, '', r.total_loss_yuan]);
        rows.push([]);
        rows.push([I18n.t('disaster.param', '假设参数'), I18n.t('disaster.value', '取值'),
                   I18n.t('disaster.source', '来源说明')]);
        r.assumptions.forEach((a) => {
            const val = typeof a.value === 'object' ? JSON.stringify(a.value) : a.value;
            rows.push([a.label, val, a.note]);
        });
        if (this._draft) {
            rows.push([]);
            rows.push([I18n.t('disaster.draftBadge', 'AI 草稿 · 需人工复核')]);
            rows.push([this._draft]);
        }
        Utils.exportCSV(rows, I18n.t('disaster.csvName', '灾害定损测算单'));
    },

    async _exportPdf() {
        if (!this._result) {
            Modal.alert(I18n.t('disaster.assessFirst', '请先完成定损测算'));
            return;
        }
        const r = this._result;
        const t = (k, fb) => I18n.t(k, fb);
        const esc = Utils.escapeHtml;
        const yuan = (v) => Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        let html = `<div style="font-family:'WenQuanYi Micro Hei','Microsoft YaHei',sans-serif;padding:16px;color:#1a231e;">`;
        html += `<h1 style="text-align:center;font-size:20px;margin-bottom:4px;">${t('disaster.pdfTitle', '农业灾害定损测算单（遥感辅助）')}</h1>`;
        html += `<p style="text-align:center;color:#c44536;font-size:11px;margin-bottom:14px;">`
            + `${t('disaster.pdfFooter', '本表为遥感代理测算结果，非实测减产率，不作为理赔依据。')}</p>`;

        html += `<h3 style="font-size:14px;">一、${t('disaster.secGrade', '受灾分级（系统测算）')}</h3>`;
        html += '<table style="width:100%;border-collapse:collapse;font-size:12px;" border="1" cellpadding="6">';
        html += `<tr><th>${t('disaster.level', '等级')}</th><th>${t('disaster.pixels', '变化像素')}</th>`
            + `<th>${t('disaster.areaMu', '面积（亩）')}</th><th>${t('disaster.lossRate', '减产比例（假设）')}</th>`
            + `<th>${t('disaster.lossYuan', '估算损失（元）')}</th></tr>`;
        r.levels.forEach((l) => {
            html += `<tr><td>${esc(l.label)}</td><td>${l.pixels}</td><td>${l.area_mu}</td>`
                + `<td>${(l.loss_rate * 100).toFixed(0)}%</td><td>${yuan(l.loss_yuan)}</td></tr>`;
        });
        html += `<tr><td><b>${t('disaster.total', '合计')}</b></td><td>${r.change_pixel}</td>`
            + `<td>${r.affected_area_mu}</td><td>—</td><td><b>${yuan(r.total_loss_yuan)}</b></td></tr></table>`;

        html += `<h3 style="font-size:14px;margin-top:14px;">二、${t('disaster.secCost', '查勘成本对比')}</h3>`;
        html += `<p style="font-size:12px;">${t('disaster.manualCost', '人工踏勘')}：${yuan(r.survey_cost.manual_cost_yuan)} 元`
            + `（${r.survey_cost.manual_per_mu} 元/亩，${r.survey_cost.manual_days} 天）<br>`
            + `${t('disaster.remoteCost', '遥感定损')}：${yuan(r.survey_cost.remote_cost_yuan)} 元`
            + `（${r.survey_cost.remote_per_mu} 元/亩，${r.survey_cost.remote_days} 天）<br>`
            + `<b>${t('disaster.saving', '节省')}：${yuan(r.survey_cost.saving_yuan)} 元</b></p>`;

        html += `<h3 style="font-size:14px;margin-top:14px;">三、${t('disaster.secAssumptions', '本次采用的假设参数')}</h3>`;
        html += '<table style="width:100%;border-collapse:collapse;font-size:12px;" border="1" cellpadding="6">';
        html += `<tr><th>${t('disaster.param', '参数')}</th><th>${t('disaster.value', '取值')}</th>`
            + `<th>${t('disaster.source', '来源说明')}</th></tr>`;
        r.assumptions.forEach((a) => {
            const val = typeof a.value === 'object' ? JSON.stringify(a.value) : `${a.value} ${a.unit || ''}`;
            html += `<tr><td>${esc(a.label)}</td><td>${esc(val)}</td><td>${esc(a.note)}</td></tr>`;
        });
        html += `</table>`;

        if (this._draft) {
            html += `<h3 style="font-size:14px;margin-top:14px;">四、${t('disaster.secDraft', '定损说明')}</h3>`;
            html += `<p style="color:#c44536;font-size:12px;font-weight:bold;border:1px solid #c44536;padding:4px 8px;display:inline-block;">`
                + `${t('disaster.draftBadge', 'AI 草稿 · 需人工复核')}</p>`;
            html += `<p style="font-size:12px;white-space:pre-wrap;">${esc(this._draft)}</p>`;
            html += `<p style="font-size:11px;color:#5a6a60;">${esc(this._imageDisclaimer || '')}</p>`;
        }

        html += `<p style="font-size:11px;color:#5a6a60;margin-top:14px;border-top:1px solid #e0dcd5;padding-top:8px;">`
            + `${esc(r.disclaimer)}</p></div>`;

        try {
            const mod = await import('./reportGenerator.js');
            await mod.ReportGenerator.generateDisasterReport(
                html,
                `${t('disaster.pdfName', '灾害定损测算单')}_${new Date().toISOString().slice(0, 10)}.pdf`,
                t('disaster.pdfFooter', '本表为遥感代理测算结果，非实测减产率，不作为理赔依据。')
            );
        } catch (e) {
            Toast.error(I18n.t('disaster.pdfFailed', 'PDF 导出失败'));
        }
    }
};
