import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { Toast } from './toast.js';
import { Auth } from './auth.js';
import { History } from './history.js';
import { API } from './api.js';
import { Notify } from './notify.js';
import { ReportGenerator } from './reportGenerator.js';
import { CompareSlider } from './compareSlider.js';
import { eventBus } from './eventBus.js';
import { I18n } from './i18n.js';

let _batchDone = 0;
let _batchTotal = 0;

export const BatchDetector = {
    init() {
        this._restoreSettings();
        document.getElementById("batchStart").onclick = () => this.start();
        document.getElementById("batchExport").onclick = () => this.exportCSV();
        document.getElementById("batchExportPDF").onclick = () => ReportGenerator.generateBatchReport(state.batchResult);
        const autoBtn = document.getElementById("batchAutoThresholdBtn");
        if (autoBtn) autoBtn.onclick = () => this.autoThreshold();

        // 保存设置
        const modelSel = document.getElementById("batch_model");
        const thInput = document.getElementById("batch_th");
        if (modelSel) modelSel.addEventListener('change', () => this._saveSettings());
        if (thInput) thInput.addEventListener('change', () => this._saveSettings());

        document.getElementById("batchTableBody").addEventListener("click", (e) => {
            const row = e.target.closest("tr");
            if (!row) return;
            const tbody = document.getElementById("batchTableBody");
            const index = Array.from(tbody.querySelectorAll("tr")).indexOf(row);
            if (index >= 0 && index < state.batchResult.length) {
                const item = state.batchResult[index];
                if (item && item.status === 'done') this.previewResult(item, index);
            }
        });

    },

    async start() {
        if (Auth.isGuest()) { Auth.showAuthOverlay('login'); return; }
        if (!Auth.checkLogin()) return;

        state.batchResult.forEach(item => {
            if (item.t1Url) Utils.releaseObjectURL(item.t1Url);
            if (item.t2Url) Utils.releaseObjectURL(item.t2Url);
        });
        state.batchResult = [];
        _batchDone = 0;

        const t1Files = document.getElementById("batch_t1").files;
        const t2Files = document.getElementById("batch_t2").files;
        if (t1Files.length === 0 || t2Files.length === 0 || t1Files.length !== t2Files.length) {
            return Modal.alert(I18n.t('upload.matchCount'));
        }
        for (let i = 0; i < t1Files.length; i++) {
            const v1 = Utils.validateFile(t1Files[i]);
            const v2 = Utils.validateFile(t2Files[i]);
            if (!v1.valid) return Modal.alert(`T1第${i + 1}张：${v1.msg}`);
            if (!v2.valid) return Modal.alert(`T2第${i + 1}张：${v2.msg}`);
        }

        const btn = document.getElementById("batchStart");
        const status = document.getElementById("batch_status");
        const tableBody = document.getElementById("batchTableBody");
        const exportBtn = document.getElementById("batchExport");
        const exportPDFBtn = document.getElementById("batchExportPDF");
        const progressContainer = document.getElementById("batchProgressContainer");

        btn.disabled = true;
        status.className = "status-badge show loading";
        status.innerHTML = `<span>⏳</span> ${I18n.t('batch.detecting')}`;
        tableBody.innerHTML = "";
        exportBtn.style.display = 'none';
        exportPDFBtn.style.display = 'none';
        progressContainer.classList.remove('hidden');
        Notify.init();

        _batchTotal = t1Files.length;
        _batchDone = 0;
        _showBatchSummary();
        this._setProgress(0, _batchTotal);
        status.textContent = I18n.t('batch.detecting') + '... (0/' + _batchTotal + ')';

        // 缩略图先出：用户上传完立刻能看出配对对不对
        const previews = await Promise.all(
            Array.from(t1Files).map(function (f, i) {
                return Promise.all([
                    Utils.createImagePreview(f),
                    Utils.createImagePreview(t2Files[i]),
                ]);
            })
        );

        const rows = [];
        for (let i = 0; i < t1Files.length; i++) {
            const tr = document.createElement("tr");
            tr.dataset.idx = String(i);
            tr.innerHTML = `
                <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${i + 1}</td>
                <td class="thumb-cell" style="padding:8px 12px;border-bottom:1px solid var(--border);"><img src="${previews[i][0]}" style="width:44px;height:44px;object-fit:cover;border-radius:4px;" alt=""></td>
                <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${t1Files[i].name}</td>
                <td class="ratio-cell" style="padding:14px 16px;border-bottom:1px solid var(--border);">-</td>
                <td class="action-cell" style="padding:8px 10px;border-bottom:1px solid var(--border);"></td>
                <td class="status-cell" style="padding:14px 16px;border-bottom:1px solid var(--border);">${I18n.t('batch.queued')}</td>
            `;
            tableBody.appendChild(tr);
            rows.push(tr);
        }

        // 整批一次性交给服务端。任务从这一刻起归服务端管 —— 关掉标签页也会跑完，
        // 再打开还能看到结果。这正是它从「前端循环」搬过来的理由。
        const fd = new FormData();
        for (let i = 0; i < t1Files.length; i++) {
            fd.append('img1', t1Files[i]);
            fd.append('img2', t2Files[i]);
        }
        fd.append('model', document.getElementById("batch_model").value);
        fd.append('threshold', String(parseFloat(document.getElementById("batch_th").value)));

        let job;
        try {
            const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/batch`, {
                method: 'POST', body: fd,
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.detail || ('HTTP ' + res.status));
            job = body.data;
        } catch (e) {
            btn.disabled = false;
            status.className = "status-badge show error";
            status.textContent = I18n.t('batch.uploadFailed');
            Modal.alert(String(e.message || e));
            return;
        }

        await this._pollJob(job.id, rows, previews);
    },

    _setProgress(done, total) {
        const percent = total ? Math.round((done / total) * 100) : 0;
        const bar = document.getElementById("batchProgressBar");
        const text = document.getElementById("batchProgressText");
        if (bar) bar.style.width = percent + '%';
        if (text) text.textContent = percent + '%';
    },

    async _pollJob(jobId, rows, previews) {
        const status = document.getElementById("batch_status");
        const btn = document.getElementById("batchStart");
        const progressContainer = document.getElementById("batchProgressContainer");
        const label = {
            queued: I18n.t('batch.queued'),
            running: I18n.t('batch.running'),
            done: I18n.t('batch.done'),
            failed: I18n.t('batch.failed'),
        };
        let misses = 0;

        for (;;) {
            await new Promise(r => setTimeout(r, 1500));
            let data;
            try {
                const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/batch/${jobId}`);
                if (!res.ok) throw new Error('HTTP ' + res.status);
                data = (await res.json()).data;
                misses = 0;
            } catch (e) {
                // 网络抖动不该把一整批的结果丢掉；连续失败多次才收手
                if (++misses >= 5) {
                    btn.disabled = false;
                    status.className = "status-badge show error";
                    status.textContent = I18n.t('batch.pollFailed');
                    return;
                }
                continue;
            }

            (data.items || []).forEach((it, i) => {
                const tr = rows[i];
                if (!tr) return;
                const cell = tr.querySelector('.status-cell');
                if (cell) cell.textContent = label[it.status] || label.queued;
                const rc = tr.querySelector('.ratio-cell');
                if (!rc) return;
                if (it.status === 'done' && it.result && it.result.stats) {
                    rc.textContent = it.result.stats.ratio + '%';
                } else if (it.status === 'failed') {
                    rc.textContent = '--';
                }
            });

            const finished = data.done + data.failed;
            this._setProgress(finished, data.total);
            status.textContent = I18n.t('batch.detecting') + '... (' + finished + '/' + data.total + ')';

            if (['done', 'failed', 'cancelled'].indexOf(data.status) >= 0) {
                this._buildResults(data, previews);
                _updateBatchSummary();
                progressContainer.classList.add('hidden');
                btn.disabled = false;
                status.className = 'status-badge show ' + (data.status === 'done' ? 'success' : 'error');
                status.textContent = data.status === 'done'
                    ? I18n.t('batch.complete')
                    : (data.message || I18n.t('batch.failed'));
                this._afterFinish();
                break;
            }
        }
    },

    _buildResults(data, previews) {
        state.batchResult = (data.items || []).map(function (it, i) {
            const r = it.result || {};
            const stats = r.stats || {};
            return {
                name: it.name,
                t1Url: previews[i] ? previews[i][0] : '',
                t2Url: previews[i] ? previews[i][1] : '',
                maskUrl: r.mask || '',
                heatUrl: r.heat || '',
                fusionUrl: r.fusion || '',
                ratio: stats.ratio,
                changePixel: stats.change_pixel,
                totalPixel: stats.total_pixel,
                threshold: stats.threshold,
                model: r.model || data.model,
                time: data.updated_at || '',
                actualArea: '',
                status: it.status === 'done' ? 'done' : 'error',
                error: it.error || '',
                detectionId: it.detection_id,
            };
        });
    },

    _afterFinish() {
        if (state.batchResult.some(function (r) { return r.status === 'done'; })) {
            document.getElementById("batchExport").style.display = '';
            document.getElementById("batchExportPDF").style.display = '';
        }
        if (Notify.batchComplete) Notify.batchComplete(state.batchResult);
        History.load();
    },

    _saveSettings() {
        const model = document.getElementById("batch_model")?.value;
        const threshold = document.getElementById("batch_th")?.value;
        if (model || threshold) {
            try {
                localStorage.setItem('batch_config', JSON.stringify({ model, threshold }));
            } catch(e) { /* quota exceeded, ignore */ }
        }
    },

    _restoreSettings() {
        try {
            const saved = JSON.parse(localStorage.getItem('batch_config'));
            if (saved) {
                if (saved.model && document.getElementById("batch_model"))
                    document.getElementById("batch_model").value = saved.model;
                if (saved.threshold && document.getElementById("batch_th"))
                    document.getElementById("batch_th").value = saved.threshold;
            }
        } catch(e) { /* ignore */ }
    },

    async autoThreshold() {
        const t1Files = document.getElementById("batch_t1").files;
        const t2Files = document.getElementById("batch_t2").files;
        if (t1Files.length === 0 || t2Files.length === 0) {
            Modal.alert(I18n.t('batch.uploadFirst'));
            return;
        }
        try {
            const threshold = await API.recommendThreshold(t1Files[0], t2Files[0]);
            document.getElementById("batch_th").value = threshold;
        } catch (e) {
            Modal.alert(e.message || I18n.t('detect.thresholdFailed'));
        }
    },

    previewResult(item) {
        const t = (k, fb) => I18n.t(k, fb);
        Modal.createOverlay(`
            <div class="modal-box preview-modal-box">
                <div class="modal-title">${t('batch.previewTitle')} - ${item.name}</div>
                <div class="modal-content">
                    <div class="preview-grid">
                        <div><strong>${t('detect.t1Label')}</strong><br><img src="${item.t1Url}" class="preview-img"></div>
                        <div><strong>${t('detect.t2Label')}</strong><br><img src="${item.t2Url}" class="preview-img"></div>
                        <div><strong>${t('history.detailMask')}</strong><br><img src="${item.maskUrl}" class="preview-img"></div>
                        <div><strong>${t('history.detailHeat')}</strong><br><img src="${item.heatUrl}" class="preview-img"></div>
                    </div>
                    <p class="preview-info">${t('detect.changeRatio')}：${item.ratio}% | ${t('detect.changePixel')}：${item.changePixel} | ${t('common.model')}：${item.model} | ${t('detect.threshold')}：${item.threshold}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn-modal btn-modal-primary" id="comparePreviewBtn">${t('common.compare')}</button>
                    <button class="btn-modal btn-modal-secondary" id="modalCloseBtn">${t('common.close')}</button>
                </div>
            </div>
        `, {
            '#comparePreviewBtn': () => { if (item.t1Url && item.t2Url) CompareSlider.show(item.t1Url, item.t2Url); }
        });
    },

    exportCSV() {
        if (state.batchResult.length === 0) return Modal.alert(I18n.t('batch.noExportData'));
        const t = (k) => I18n.t(k);
        const rows = [[t('batch.csvNo'), t('batch.csvName'), t('batch.csvRatio'), t('batch.csvActualArea'), t('batch.csvChangePixel'), t('batch.csvTotalPixel'), t('common.model'), t('batch.csvThreshold'), t('common.time'), t('batch.csvStatus')]];
        state.batchResult.forEach((item, idx) => {
            rows.push([
                idx + 1, item.name, item.ratio ?? '', item.actualArea ?? '', item.changePixel ?? '',
                item.totalPixel ?? '', item.model, item.threshold, item.time, item.status
            ]);
        });
        Utils.exportCSV(rows, I18n.t('batch.csvFileName'));
    }
};

function _updateBatchSummary() {
    var bar = document.getElementById('batchSummaryBar');
    if (!bar) return;
    bar.classList.remove('hidden');
    var total = _batchTotal;
    var done = 0;
    var failed = 0;
    var sumRatio = 0;
    var ratioCount = 0;
    state.batchResult.forEach(function(r) {
        if (r.ratio != null) { sumRatio += r.ratio; ratioCount++; }
        if (r.status === 'error') failed++;
        else if (r.status === 'done') done++;
    });
    setText('batchSumTotal', total);
    setText('batchSumDone', done);
    setText('batchSumFailed', failed);
    setText('batchSumAvgRatio', ratioCount > 0 ? (sumRatio / ratioCount).toFixed(1) + '%' : '--');
}

function _showBatchSummary() {
    var bar = document.getElementById('batchSummaryBar');
    if (bar) bar.classList.remove('hidden');
}

function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
}
