import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { Auth } from './auth.js';
import { History } from './history.js';
import { API } from './api.js';
import { Notify } from './notify.js';
import { ReportGenerator } from './reportGenerator.js';
import { CompareSlider } from './compareSlider.js';
import { taskQueue } from './taskQueue.js';
import { eventBus } from './eventBus.js';
import { I18n } from './i18n.js';
import { BatchStore } from './indexedDB.js';

let _taskMeta = {};   // id -> { row, t1Url, t2Url, name, files, index, ... }
let _batchDone = 0;
let _batchTotal = 0;
let _onBatchComplete = null;

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
            const btn = e.target.closest('button');
            const row = e.target.closest("tr");
            if (!row) return;

            if (btn) {
                const taskId = parseInt(row.dataset.taskId);
                if (btn.classList.contains('btn-pause')) {
                    taskQueue.pause(taskId);
                    btn.textContent = '▶';
                    btn.className = 'btn-small-action btn-resume';
                    row.querySelector('.status-cell').textContent = I18n.t('batch.paused');
                } else if (btn.classList.contains('btn-resume')) {
                    _retryTask(taskId);
                    btn.textContent = '⏸';
                    btn.className = 'btn-small-action btn-pause';
                } else if (btn.classList.contains('btn-cancel')) {
                    taskQueue.cancel(taskId);
                    row.querySelector('.status-cell').textContent = I18n.t('batch.cancelled');
                    row.querySelector('.status-cell').style.color = '#94a3b8';
                    row.querySelector('.action-cell').innerHTML = '<button class="btn-small-action btn-retry">↻</button>';
                } else if (btn.classList.contains('btn-retry')) {
                    _retryTask(taskId);
                    row.querySelector('.action-cell').innerHTML = '<button class="btn-small-action btn-pause">⏸</button> <button class="btn-small-action btn-cancel">✕</button>';
                    row.querySelector('.status-cell').textContent = I18n.t('batch.retrying');
                    row.querySelector('.status-cell').style.color = '';
                }
                return;
            }

            const tbody = document.getElementById("batchTableBody");
            const rows = Array.from(tbody.querySelectorAll("tr"));
            const index = rows.indexOf(row);
            if (index >= 0 && index < state.batchResult.length) {
                const item = state.batchResult[index];
                if (item && item.status === 'done') {
                    this.previewResult(item, index);
                }
            }
        });

        eventBus.on('task-progress', ({ completed, error }) => {
            var percent = _batchTotal ? Math.round(((completed + error) / _batchTotal) * 100) : 0;
            var progressBar = document.getElementById("batchProgressBar");
            var progressText = document.getElementById("batchProgressText");
            if (progressBar) progressBar.style.width = percent + '%';
            if (progressText) progressText.textContent = percent + '%';

            // 更新状态文字（每个任务完成/失败后都更新）
            var status = document.getElementById("batch_status");
            if (status && _batchTotal) {
                status.textContent = I18n.t('batch.detecting') + '... (' + (completed + error) + '/' + _batchTotal + ')';
            }

            // 每完成一个任务（成功或失败）都刷新汇总栏
            _updateBatchSummary();

            // 所有任务都已结束（成功 + 失败 >= 总数）→ 触发完成回调
            if (_batchTotal && (completed + error) >= _batchTotal) {
                _finishBatch();
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
        _taskMeta = {};
        _batchDone = 0;
        taskQueue.reset();

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
        state.batchResult = [];
        exportBtn.style.display = 'none';
        exportPDFBtn.style.display = 'none';
        progressContainer.classList.remove('hidden');
        Notify.init();

        _batchTotal = t1Files.length;
        _batchDone = 0;
        _showBatchSummary();
        status.textContent = I18n.t('batch.detecting') + '... (0/' + _batchTotal + ')';

        const modelName = document.getElementById("batch_model").value;
        const threshold = parseFloat(document.getElementById("batch_th").value);
        const currentLatLng = document.getElementById("lat_lng")?.value || '';
        const currentProvince = document.getElementById("province")?.value || '';
        const currentCity = document.getElementById("city")?.value || '';
        const currentLocation = `${currentProvince}${currentCity}`;
        let currentChangeType = document.getElementById("change_type_define")?.value || '';
        if (!currentChangeType) currentChangeType = "黑土层变薄退化";
        const currentArea = parseFloat(document.getElementById("area")?.value) || 0;

        // 预生成所有缩略图URL（含TIFF解码）
        const previewUrls = await Promise.all(
            Array.from(t1Files).map(function(f, i) {
                return Promise.all([
                    Utils.createImagePreview(f),
                    Utils.createImagePreview(t2Files[i])
                ]);
            })
        );

        const ids = [];
        for (let i = 0; i < t1Files.length; i++) {
            const index = i;
            const t1Url = previewUrls[index][0];
            const t2Url = previewUrls[index][1];

            const tr = document.createElement("tr");
            tr.dataset.taskId = '';
            tr.innerHTML = `
                <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${index + 1}</td>
                <td class="thumb-cell" style="padding:8px 12px;border-bottom:1px solid var(--border);"><span style="color:var(--text-light);font-size:12px;">${I18n.t('batch.queued')}</span></td>
                <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${t1Files[index].name}</td>
                <td style="padding:14px 16px;border-bottom:1px solid var(--border);">-</td>
                <td class="action-cell" style="padding:8px 10px;border-bottom:1px solid var(--border);"><button class="btn-small-action btn-pause">⏸</button> <button class="btn-small-action btn-cancel">✕</button></td>
                <td class="status-cell" style="padding:14px 16px;border-bottom:1px solid var(--border);">${I18n.t('batch.queued')}</td>
            `;
            tableBody.appendChild(tr);

            const id = taskQueue.add(async (signal) => {
                const statusCell = tr.querySelector('.status-cell');
                const thumbCell = tr.querySelector('.thumb-cell');
                statusCell.textContent = I18n.t('batch.running');
                statusCell.style.color = '';

                const fd = new FormData();
                fd.append("img1", t1Files[index]);
                fd.append("img2", t2Files[index]);
                fd.append("model", modelName);
                fd.append("threshold", threshold);
                fd.append("lat_lng", currentLatLng);
                fd.append("location", currentLocation);
                fd.append("change_type", currentChangeType);
                fd.append("t1_time", "");
                fd.append("t2_time", "");

                try {
                    const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect`, {
                        method: 'POST',
                        body: fd,
                        signal
                    });
                    const json = await res.json();
                    if (json.code !== 200) throw new Error(json.msg || I18n.t('detect.detectFailed'));

                    const actualArea = (currentArea > 0 && json.stats.total_pixel > 0)
                        ? parseFloat(((json.stats.change_pixel / json.stats.total_pixel) * currentArea).toFixed(2))
                        : null;
                    tr.children[3].textContent = json.stats.ratio + "%" + (actualArea != null ? ' (' + actualArea + I18n.t('unit.mu', '亩') + ')' : '');
                    thumbCell.innerHTML = '<div class="batch-thumb"><img src="' + t1Url + '" class="thumb-img thumb-t1"><img src="' + t2Url + '" class="thumb-img thumb-t2"></div>';
                    statusCell.textContent = I18n.t('batch.done');
                    statusCell.style.color = "#4ade80";
                    tr.querySelector('.action-cell').innerHTML = '';
                    _putBatchResult({
                        name: t1Files[index].name,
                        ratio: json.stats.ratio,
                        changePixel: json.stats.change_pixel,
                        totalPixel: json.stats.total_pixel,
                        model: modelName,
                        threshold: threshold,
                        time: new Date().toLocaleString(),
                        status: 'done',
                        maskUrl: json.mask,
                        heatUrl: json.heat,
                        fusionUrl: json.fusion,
                        t1Url: t1Url, t2Url: t2Url,
                        actualArea: actualArea
                    });
                    _batchDone++;
                    state.persist();
                    return json;
                } catch (e) {
                    statusCell.textContent = e.name === 'AbortError' ? I18n.t('batch.cancelled') : I18n.t('batch.failed', '失败');
                    statusCell.style.color = '#f87171';
                    _putBatchResult({
                        name: t1Files[index].name,
                        ratio: null,
                        changePixel: null,
                        totalPixel: null,
                        model: modelName,
                        threshold: threshold,
                        time: new Date().toLocaleString(),
                        status: 'error',
                        maskUrl: null,
                        heatUrl: null,
                        fusionUrl: null,
                        t1Url: t1Url, t2Url: t2Url,
                        actualArea: null,
                        error: e.message || String(e)
                    });
                    state.persist();
                    throw e;
                }
            }, { tr, index });

            tr.dataset.taskId = id;
            _taskMeta[id] = { tr, t1Url, t2Url, name: t1Files[index].name, index, t1File: t1Files[index], t2File: t2Files[index], modelName, threshold, currentLatLng, currentLocation, currentChangeType };
            ids.push(id);

            // Persist file data to IndexedDB
            _persistTaskToDB(id, index, t1Files[index], t2Files[index], modelName, threshold, currentLatLng, currentLocation, currentChangeType);
        }

        _onBatchComplete = () => {
            status.className = "status-badge show success";
            status.innerHTML = `<span>✅</span> ${I18n.t('batch.complete')}`;
            btn.disabled = false;
            exportBtn.style.display = "block";
            exportPDFBtn.style.display = "block";
            progressContainer.classList.add('hidden');

            const doneCount = state.batchResult.filter(r => r.status === 'done').length;
            const errCount = state.batchResult.filter(r => r.status === 'error').length;
            Notify.batchComplete(_batchTotal, doneCount, errCount);
            History.load();
            _onBatchComplete = null;
        };
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
    },

    /** 检查是否有可恢复的批量任务 */
    async checkRestorable() {
        try {
            const tasks = await BatchStore.getAllTasks();
            if (!tasks || tasks.length === 0) return false;
            const doneCount = tasks.filter(t => t.status === 'completed').length;
            return { tasks, doneCount, total: tasks.length };
        } catch { return false; }
    },

    /** 恢复批量任务 */
    async restore(tasks) {
        if (!tasks || tasks.length === 0) return;

        const tableBody = document.getElementById("batchTableBody");
        const btn = document.getElementById("batchStart");
        const status = document.getElementById("batch_status");
        const exportBtn = document.getElementById("batchExport");
        const exportPDFBtn = document.getElementById("batchExportPDF");
        const progressContainer = document.getElementById("batchProgressContainer");

        btn.disabled = true;
        status.className = "status-badge show loading";
        status.innerHTML = `<span>⏳</span> ${I18n.t('batch.detecting')}`;
        exportBtn.style.display = 'none';
        exportPDFBtn.style.display = 'none';
        progressContainer.classList.remove('hidden');

        _taskMeta = {};
        _batchDone = tasks.filter(t => t.status === 'completed').length;
        _batchTotal = tasks.length;
        _showBatchSummary();

        const pendingTasks = tasks.filter(t => t.status !== 'completed');

        // Render all tasks
        for (const task of tasks) {
            const t1File = new File([task.t1File], task.fileName, { type: 'image/png' });
            const t2File = new File([task.t2File], task.fileName, { type: 'image/png' });
            const t1Url = await Utils.createImagePreview(t1File);
            const t2Url = await Utils.createImagePreview(t2File);

            const tr = document.createElement("tr");
            tr.dataset.taskId = task.status === 'completed' ? '' : '';
            if (task.status === 'completed' && task.result) {
                const r = task.result;
                var restoreArea = parseFloat(document.getElementById('area')?.value) || 0;
                var actualArea = (restoreArea > 0 && r.stats.total_pixel > 0)
                    ? parseFloat(((r.stats.change_pixel / r.stats.total_pixel) * restoreArea).toFixed(2))
                    : null;
                tr.innerHTML = `
                    <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${task.index + 1}</td>
                    <td class="thumb-cell" style="padding:8px 12px;border-bottom:1px solid var(--border);"><div class="batch-thumb"><img src="${t1Url}" class="thumb-img thumb-t1"><img src="${t2Url}" class="thumb-img thumb-t2"></div></td>
                    <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${task.fileName}</td>
                    <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${r.stats.ratio}%${actualArea != null ? ` (${actualArea}亩)` : ''}</td>
                    <td class="action-cell" style="padding:8px 10px;border-bottom:1px solid var(--border);"></td>
                    <td class="status-cell" style="padding:14px 16px;border-bottom:1px solid var(--border);color:#4ade80;">${I18n.t('batch.done')}</td>
                `;
                _putBatchResult({
                    name: task.fileName, ratio: r.stats.ratio,
                    changePixel: r.stats.change_pixel, totalPixel: r.stats.total_pixel,
                    model: task.modelName, threshold: task.threshold,
                    time: new Date().toLocaleString(), status: 'done',
                    maskUrl: r.mask, heatUrl: r.heat, fusionUrl: r.fusion,
                    t1Url, t2Url, actualArea
                });
            } else {
                tr.innerHTML = `
                    <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${task.index + 1}</td>
                    <td class="thumb-cell" style="padding:8px 12px;border-bottom:1px solid var(--border);"><span style="color:var(--text-light);font-size:12px;">${I18n.t('batch.queued')}</span></td>
                    <td style="padding:14px 16px;border-bottom:1px solid var(--border);">${task.fileName}</td>
                    <td style="padding:14px 16px;border-bottom:1px solid var(--border);">-</td>
                    <td class="action-cell" style="padding:8px 10px;border-bottom:1px solid var(--border);"><button class="btn-small-action btn-pause">⏸</button> <button class="btn-small-action btn-cancel">✕</button></td>
                    <td class="status-cell" style="padding:14px 16px;border-bottom:1px solid var(--border);">${I18n.t('batch.queued')}</td>
                `;
            }
            tableBody.appendChild(tr);

            if (task.status !== 'completed') {
                _taskMeta[task.id] = { tr, t1Url, t2Url, name: task.fileName, index: task.index, t1File, t2File, modelName: task.modelName, threshold: task.threshold, currentLatLng: task.latLng, currentLocation: task.location, currentChangeType: task.changeType };
            }
        }

        // Re-enqueue pending tasks
        pendingTasks.forEach(task => {
            const meta = _taskMeta[task.id];
            if (!meta) return;
            const { tr, t1Url, t2Url, t1File, t2File, modelName, threshold, currentLatLng, currentLocation, currentChangeType } = meta;

            const newId = taskQueue.add(async (signal) => {
                const statusCell = tr.querySelector('.status-cell');
                const thumbCell = tr.querySelector('.thumb-cell');
                statusCell.textContent = I18n.t('batch.running');
                statusCell.style.color = '';

                const fd = new FormData();
                fd.append("img1", t1File);
                fd.append("img2", t2File);
                fd.append("model", modelName);
                fd.append("threshold", threshold);
                fd.append("lat_lng", currentLatLng);
                fd.append("location", currentLocation);
                fd.append("change_type", currentChangeType);
                fd.append("t1_time", "");
                fd.append("t2_time", "");

                try {
                    const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect`, { method: 'POST', body: fd, signal });
                    const json = await res.json();
                    if (json.code !== 200) throw new Error(json.msg || I18n.t('detect.detectFailed'));

                    var retryArea = parseFloat(document.getElementById("area")?.value) || 0;
                    var actualArea = (retryArea > 0 && json.stats.total_pixel > 0)
                        ? parseFloat(((json.stats.change_pixel / json.stats.total_pixel) * retryArea).toFixed(2))
                        : null;
                    tr.children[3].textContent = json.stats.ratio + "%" + (actualArea != null ? ' (' + actualArea + I18n.t('unit.mu', '亩') + ')' : '');
                    thumbCell.innerHTML = '<div class="batch-thumb"><img src="' + t1Url + '" class="thumb-img thumb-t1"><img src="' + t2Url + '" class="thumb-img thumb-t2"></div>';
                    statusCell.textContent = I18n.t('batch.done');
                    statusCell.style.color = "#4ade80";
                    tr.querySelector('.action-cell').innerHTML = '';
                    _putBatchResult({
                        name: task.fileName, ratio: json.stats.ratio,
                        changePixel: json.stats.change_pixel, totalPixel: json.stats.total_pixel,
                        model: modelName, threshold: threshold, time: new Date().toLocaleString(),
                        status: 'done', maskUrl: json.mask, heatUrl: json.heat, fusionUrl: json.fusion,
                        t1Url: t1Url, t2Url: t2Url, actualArea: actualArea
                    });
                    _batchDone++;
                    state.persist();
                    BatchStore.updateTask(task.id, { status: 'completed', result: json }).catch(function () {});
                    return json;
                } catch (e) {
                    statusCell.textContent = e.name === 'AbortError' ? I18n.t('batch.cancelled') : I18n.t('batch.failed', '失败');
                    statusCell.style.color = '#f87171';
                    _putBatchResult({
                        name: task.fileName, ratio: null,
                        changePixel: null, totalPixel: null,
                        model: modelName, threshold: threshold, time: new Date().toLocaleString(),
                        status: 'error', maskUrl: null, heatUrl: null, fusionUrl: null,
                        t1Url: t1Url, t2Url: t2Url, actualArea: null,
                        error: e.message || String(e)
                    });
                    state.persist();
                    throw e;
                }
            }, { tr, index: task.index });
            tr.dataset.taskId = newId;
            _taskMeta[newId] = meta;
            // Update IndexedDB with new task id mapping
            BatchStore.deleteTask(task.id).catch(() => {});
        });

        _onBatchComplete = async () => {
            status.className = "status-badge show success";
            status.innerHTML = `<span>✅</span> ${I18n.t('batch.complete')}`;
            btn.disabled = false;
            exportBtn.style.display = "block";
            exportPDFBtn.style.display = "block";
            progressContainer.classList.add('hidden');

            const doneCount = state.batchResult.filter(r => r.status === 'done').length;
            const errCount = state.batchResult.filter(r => r.status === 'error').length;
            Notify.batchComplete(_batchTotal, doneCount, errCount);
            History.load();
            _onBatchComplete = null;
            // Clean up IndexedDB
            await BatchStore.clearAll().catch(() => {});
            // Dismiss restore banner
            const banner = document.getElementById('batchRestoreBanner');
            if (banner) banner.classList.add('hidden');
            // Navigate to batch page to show results
            document.querySelector('.nav-item[data-page="batch"]')?.click();
        };

        status.textContent = `${I18n.t('batch.running')}... (${_batchDone}/${_batchTotal})`;

        // If no pending tasks, trigger completion
        if (pendingTasks.length === 0 && _onBatchComplete) {
            _onBatchComplete();
        }
    }
};

function _retryTask(oldId) {
    const meta = _taskMeta[oldId];
    if (!meta) return;
    const { tr, t1File, t2File, name, index, modelName, threshold, currentLatLng, currentLocation, currentChangeType, t1Url, t2Url } = meta;
    tr.querySelector('.status-cell').textContent = I18n.t('batch.retrying');
    tr.querySelector('.status-cell').style.color = '';

    const newId = taskQueue.add(async (signal) => {
        const statusCell = tr.querySelector('.status-cell');
        const fd = new FormData();
        fd.append("img1", t1File);
        fd.append("img2", t2File);
        fd.append("model", modelName);
        fd.append("threshold", threshold);
        fd.append("lat_lng", currentLatLng);
        fd.append("location", currentLocation);
        fd.append("change_type", currentChangeType);
        fd.append("t1_time", "");
        fd.append("t2_time", "");

        try {
            const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect`, {
                method: 'POST', body: fd, signal
            });
            const json = await res.json();
            if (json.code !== 200) throw new Error(json.msg || I18n.t('detect.detectFailed'));

            var retryArea = parseFloat(document.getElementById("area")?.value) || 0;
            var actualArea = (retryArea > 0 && json.stats.total_pixel > 0)
                ? parseFloat(((json.stats.change_pixel / json.stats.total_pixel) * retryArea).toFixed(2))
                : null;
            tr.children[3].textContent = json.stats.ratio + "%" + (actualArea != null ? ' (' + actualArea + I18n.t('unit.mu', '亩') + ')' : '');
            const thumbCell = tr.querySelector('.thumb-cell');
            thumbCell.innerHTML = '<div class="batch-thumb"><img src="' + t1Url + '" class="thumb-img thumb-t1"><img src="' + t2Url + '" class="thumb-img thumb-t2"></div>';
            statusCell.textContent = I18n.t('batch.done');
            statusCell.style.color = "#4ade80";
            tr.querySelector('.action-cell').innerHTML = '';
            _putBatchResult({
                name: name, ratio: json.stats.ratio,
                changePixel: json.stats.change_pixel, totalPixel: json.stats.total_pixel,
                model: modelName, threshold: threshold, time: new Date().toLocaleString(),
                status: 'done', maskUrl: json.mask, heatUrl: json.heat, fusionUrl: json.fusion,
                t1Url: t1Url, t2Url: t2Url, actualArea: actualArea
            });
            // 与上面两条路径（开始执行 / 恢复）保持一致。
            // 注：_batchDone 实际只在开头拼一次 "(N/M)" 标签时被读，执行中的真实
            // 计数一律由 state.batchResult 重算（见 _updateBatchSummary 与
            // Notify.batchComplete 的 doneCount），所以这里补不补都不影响界面 ——
            // 补上是为了三条路径对称，免得下次有人照抄某一条时又少一行。
            _batchDone++;
            state.persist();
            return json;
        } catch (e) {
            statusCell.textContent = e.name === 'AbortError' ? I18n.t('batch.cancelled') : I18n.t('batch.failed', '失败');
            statusCell.style.color = '#f87171';
            _putBatchResult({
                name: name, ratio: null,
                changePixel: null, totalPixel: null,
                model: modelName, threshold: threshold, time: new Date().toLocaleString(),
                status: 'error', maskUrl: null, heatUrl: null, fusionUrl: null,
                t1Url: t1Url, t2Url: t2Url, actualArea: null,
                error: e.message || String(e)
            });
            state.persist();
            throw e;
        }
    }, { tr, index });
    tr.dataset.taskId = newId;
    _taskMeta[newId] = meta;
}

// 仅在确实完成时由 task-progress 事件调用，onBatchComplete 已置 null 防重入
/**
 * 写入一条结果，同一张图**替换**而不是追加。
 *
 * 三条执行路径原先都直接 push。对「开始执行 / 恢复」没问题（一张图只跑一次），
 * 但**重试**会让同一张图留下两条：旧的 status:'error' 不删，新的 status:'done'
 * 又追加上去。后果有两处：
 *   1. 汇总条把同一张图同时算进「已完成」和「失败」—— N 张图统计出 N+1 条；
 *   2. 导出的 CSV / PDF 报告里这张图出现两次，一次记失败、一次记成功。
 *
 * 用 t1Url 作键：它是每张图各自的对象 URL（blob:），同一张图在三份 meta 里
 * 是同一个值；而重名文件各有各的 URL，不会互相误删。
 */
function _putBatchResult(entry) {
    var i = state.batchResult.findIndex(function (r) { return r.t1Url === entry.t1Url; });
    if (i >= 0) state.batchResult[i] = entry;
    else state.batchResult.push(entry);
}

function _finishBatch() {
    if (!_onBatchComplete) return;
    var cb = _onBatchComplete;
    _onBatchComplete = null;
    BatchStore.clearAll().catch(function () {});
    cb();
}

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

async function _persistTaskToDB(id, index, t1File, t2File, modelName, threshold, latLng, location, changeType) {
    try {
        const t1Buf = await t1File.arrayBuffer();
        const t2Buf = await t2File.arrayBuffer();
        await BatchStore.saveTask({
            id, index,
            fileName: t1File.name,
            t1File: t1Buf,
            t2File: t2Buf,
            modelName, threshold,
            latLng, location, changeType,
            status: 'pending',
        });
    } catch {
        // IndexedDB 写入失败不影响检测流程
    }
}
