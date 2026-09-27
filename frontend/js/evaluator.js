import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { I18n } from './i18n.js';

// 模型清单以后端 /detect/models 为准，这里只是拿不到接口时的兜底。
// 此前写死 7 个：其中 3 个（FC_SIAM_DIFF/SNUNET/CHANGEFORMER）磁盘上没有权重，
// 列了也只会 503；同时又漏了实际可用的 BIT_LuojiaSET —— 结果筛选（见下方
// ALL_MODELS.includes）会把它的评估指标整个滤掉，评估完却看不到数。
const FALLBACK_MODELS = ["BIT", "DIFF", "AFCF3D", "BIT_LuojiaSET"];
let ALL_MODELS = FALLBACK_MODELS.slice();

async function syncAvailableModels() {
    try {
        const res = await fetch(CONFIG.API_BASE_URL + '/detect/models');
        const data = await res.json();
        if (data.code === 200 && Array.isArray(data.available) && data.available.length) {
            ALL_MODELS = data.available;
        }
    } catch (e) {
        // 接口不可用就沿用兜底清单，不影响评估流程
    }
}

function $(id) { return document.getElementById(id); }

export const Evaluator = {
    _pairs: [],
    _results: [],
    _running: false,
    _cancelled: false,

    init() {
        // 拉取真实可用模型，不阻塞渲染：用户选完文件夹再点评估，通常早已返回
        syncAvailableModels();
        const startBtn = $('evalStartBtn');
        if (startBtn) startBtn.onclick = () => this._start();
        const cancelBtn = $('evalCancelBtn');
        if (cancelBtn) cancelBtn.onclick = () => { this._cancelled = true; };
        const pickBtn = $('evalPickFolderBtn');
        if (pickBtn) {
            if (!window.isSecureContext) {
                pickBtn.style.display = 'none';
                const hint = document.createElement('span');
                hint.className = 'field-hint';
                hint.textContent = '文件夹选择需要 HTTPS 安全连接，当前为 HTTP';
                hint.style.color = 'var(--text-tertiary)';
                hint.style.fontSize = '12px';
                pickBtn.parentNode?.appendChild(hint);
            } else {
                pickBtn.onclick = () => this._pickFolder();
            }
        }
        const exportCsvBtn = $('evalExportCsvBtn');
        if (exportCsvBtn) exportCsvBtn.onclick = () => this._exportCsv();
    },

    async _pickFolder() {
        if (!window.showDirectoryPicker) {
            return Modal.alert('此功能需要 Chrome/Edge 浏览器 + HTTPS 安全连接');
        }
        try {
            const rootHandle = await window.showDirectoryPicker({ mode: 'read' });
            let aH, bH, lH;
            try { aH = await rootHandle.getDirectoryHandle('A'); } catch(e) {}
            try { aH = aH || await rootHandle.getDirectoryHandle('a'); } catch(e) {}
            try { bH = await rootHandle.getDirectoryHandle('B'); } catch(e) {}
            try { bH = bH || await rootHandle.getDirectoryHandle('b'); } catch(e) {}
            try { lH = await rootHandle.getDirectoryHandle('label'); } catch(e) {}
            try { lH = lH || await rootHandle.getDirectoryHandle('Label'); } catch(e) {}
            try { lH = lH || await rootHandle.getDirectoryHandle('LABEL'); } catch(e) {}

            if (!aH || !bH) return Modal.alert('未找到 A/ 或 B/ 文件夹。请选择 SUSY-CD 数据集根目录。');

            const aFiles = []; const bFiles = []; const lFiles = new Set();
            for await (const [n] of aH.entries()) { if (/\.(png|jpg|jpeg|tif|tiff|bmp)$/i.test(n)) aFiles.push(n); }
            for await (const [n] of bH.entries()) { if (/\.(png|jpg|jpeg|tif|tiff|bmp)$/i.test(n)) bFiles.push(n); }
            if (lH) { for await (const [n] of lH.entries()) { if (/\.(png|jpg|jpeg|tif|tiff|bmp)$/i.test(n)) lFiles.add(n.toLowerCase()); } }

            const bSet = new Set(bFiles.map(f => f.toLowerCase()));
            const pairs = aFiles.filter(f => bSet.has(f.toLowerCase()));
            if (pairs.length === 0) return Modal.alert('A/ 和 B/ 中没有同名文件。');

            // Store handles and pairs
            this._handles = { aH, bH, lH };
            this._pairs = pairs;
            this._hasLabels = lH && pairs.some(p => lFiles.has(p.toLowerCase()));

            $('evalPairCount').textContent = pairs.length;
            $('evalHasLabels').textContent = this._hasLabels ? '✅ 已检测到 label 文件夹' : '⚠️ 未找到 label 文件夹（无法计算指标）';
            $('evalHasLabels').style.color = this._hasLabels ? 'var(--primary)' : 'var(--accent)';
            $('evalFolderInfo').classList.remove('hidden');
            $('evalStartBtn').disabled = false;
        } catch(e) {
            if (e.name !== 'AbortError') Modal.alert('读取文件夹失败：' + e.message);
        }
    },

    async _start() {
        if (this._pairs.length === 0) return Modal.alert('请先选择数据集文件夹');
        const selectedModels = this._getSelectedModels();
        if (selectedModels.length === 0) return Modal.alert('请至少选择一个模型');

        this._running = true;
        this._cancelled = false;
        this._results = [];
        $('evalStartBtn').disabled = true;
        $('evalCancelBtn').classList.remove('hidden');
        $('evalProgressBar').classList.remove('hidden');
        $('evalResults').classList.add('hidden');
        $('evalCharts').classList.add('hidden');
        $('evalScanSection').classList.add('hidden');
        $('evalScanChart').classList.add('hidden');
        $('evalCases').classList.add('hidden');
        const fill = $('evalProgressFill');
        const text = $('evalProgressText');

        const threshold = parseFloat($('evalThreshold')?.value) || 0.5;
        const countLimit = parseInt($('evalCount')?.value) || 0;
        const total = countLimit > 0 ? Math.min(countLimit, this._pairs.length) : this._pairs.length;

        for (let i = 0; i < total; i++) {
            if (this._cancelled) break;
            const name = this._pairs[i];
            try {
                const { aH, bH, lH } = this._handles;
                const [aFile, bFile, lFile] = await Promise.all([
                    aH.getFileHandle(name).then(h => h.getFile()),
                    bH.getFileHandle(name).then(h => h.getFile()),
                    lH ? lH.getFileHandle(name).then(h => h.getFile()).catch(() => null) : Promise.resolve(null),
                ]);

                const fd = new FormData();
                fd.append('img1', aFile);
                fd.append('img2', bFile);
                if (lFile) fd.append('label', lFile);
                fd.append('models', JSON.stringify(selectedModels));
                fd.append('threshold', threshold);

                const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/evaluate`, {
                    method: 'POST',
                    body: fd,
                });
                const json = await res.json();
                if (json.code === 200) {
                    this._results.push({ name, ...json.results });
                }
            } catch(e) {
                console.error(`评估失败: ${name}`, e);
            }

            const pct = Math.round((i + 1) / total * 100);
            fill.style.width = pct + '%';
            text.textContent = `${i + 1} / ${total} (${pct}%)`;

            // Small delay to avoid rate-limit burst
            if (i < total - 1) await new Promise(r => setTimeout(r, 800));
        }

        this._running = false;
        $('evalStartBtn').disabled = false;
        $('evalCancelBtn').classList.add('hidden');
        fill.style.width = '100%';
        text.textContent = `完成！共评估 ${this._results.length} 对影像`;

        if (this._results.length > 0) {
            this._renderResults();
        }
    },

    _getSelectedModels() {
        return Array.from(document.querySelectorAll('.eval-model-check:checked')).map(cb => cb.value);
    },

    _renderResults() {
        const aggregated = this._aggregate();
        this._renderTable(aggregated);
        this._renderCases();
        // Show containers BEFORE initializing ECharts (needs visible DOM)
        $('evalResults').classList.remove('hidden');
        $('evalCharts').classList.remove('hidden');
        $('evalScanSection').classList.remove('hidden');
        $('evalCases').classList.remove('hidden');
        $('evalExportCsvBtn').classList.remove('hidden');
        // Init charts after DOM is visible
        setTimeout(() => this._renderCharts(aggregated), 100);
        // Bind scan button
        const scanBtn = $('evalScanBtn');
        if (scanBtn) scanBtn.onclick = () => this._scanThreshold();

        // Scroll to results
        $('evalResults').scrollIntoView({ behavior: 'smooth' });
    },

    _aggregate() {
        const agg = {};
        ALL_MODELS.forEach(m => {
            agg[m] = { precision: [], recall: [], f1: [], iou: [], time_ms: [], count: 0 };
        });

        this._results.forEach(r => {
            Object.entries(r).forEach(([model, metrics]) => {
                if (!agg[model] || !metrics || typeof metrics.f1 !== 'number') return;
                agg[model].precision.push(metrics.precision);
                agg[model].recall.push(metrics.recall);
                agg[model].f1.push(metrics.f1);
                agg[model].iou.push(metrics.iou);
                if (typeof metrics.time_ms === 'number') agg[model].time_ms.push(metrics.time_ms);
                agg[model].count++;
            });
        });

        const avg = v => v.length ? (v.reduce((a, b) => a + b, 0) / v.length).toFixed(2) : '--';
        const result = {};
        Object.entries(agg).forEach(([m, d]) => {
            if (d.count === 0) return;
            result[m] = {
                precision: avg(d.precision),
                recall: avg(d.recall),
                f1: avg(d.f1),
                iou: avg(d.iou),
                time_ms: avg(d.time_ms),
                count: d.count,
            };
        });
        return result;
    },

    _renderTable(aggregated) {
        const models = Object.keys(aggregated);
        if (models.length === 0) return;

        let bestF1 = 0, bestModel = '';
        models.forEach(m => { const v = parseFloat(aggregated[m].f1); if (v > bestF1) { bestF1 = v; bestModel = m; } });

        const rows = models.map(m => {
            const d = aggregated[m];
            const isBest = m === bestModel;
            return `<tr${isBest ? ' style="background:var(--primary-surface);"' : ''}>
                <td><strong>${m}</strong>${isBest ? ' 🏆' : ''}</td>
                <td>${d.precision}%</td>
                <td>${d.recall}%</td>
                <td style="font-weight:700;color:${isBest ? 'var(--primary)' : 'var(--text-primary)'};">${d.f1}%</td>
                <td>${d.iou}%</td>
                <td>${d.time_ms}ms</td>
                <td>${d.count}</td>
            </tr>`;
        }).join('');

        $('evalTableBody').innerHTML = rows;
        $('evalBestModel').textContent = `🏆 最佳模型：${bestModel} (F1=${bestF1}%)`;
        $('evalBestModel').style.color = 'var(--primary)';
    },

    _renderCharts(aggregated) {
        const models = Object.keys(aggregated);
        if (models.length === 0) return;

        // Bar chart
        const barDom = $('evalBarChart');
        if (barDom && window.echarts) {
            const barChart = window.echarts.init(barDom);
            barChart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: ['Precision', 'Recall', 'F1', 'IoU'], bottom: 0, textStyle: { color: 'var(--text-secondary)' } },
                grid: { left: 60, right: 30, top: 20, bottom: 40 },
                xAxis: { type: 'category', data: models, axisLabel: { fontSize: 11 } },
                yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
                series: [
                    { name: 'Precision', type: 'bar', data: models.map(m => parseFloat(aggregated[m].precision)), itemStyle: { color: '#667eea' } },
                    { name: 'Recall', type: 'bar', data: models.map(m => parseFloat(aggregated[m].recall)), itemStyle: { color: '#10b981' } },
                    { name: 'F1', type: 'bar', data: models.map(m => parseFloat(aggregated[m].f1)), itemStyle: { color: '#f59e0b' } },
                    { name: 'IoU', type: 'bar', data: models.map(m => parseFloat(aggregated[m].iou)), itemStyle: { color: '#ef4444' } },
                ],
            });
            this._barChart = barChart;
        }

        // Radar chart
        const radarDom = $('evalRadarChart');
        if (radarDom && window.echarts) {
            const radarChart = window.echarts.init(radarDom);
            const indicator = [
                { name: 'Precision', max: 100 },
                { name: 'Recall', max: 100 },
                { name: 'F1', max: 100 },
                { name: 'IoU', max: 100 },
            ];
            const colors = ['#667eea', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
            radarChart.setOption({
                tooltip: {},
                legend: { data: models, bottom: 0, textStyle: { color: 'var(--text-secondary)' } },
                grid: { left: 40, right: 20, top: 20, bottom: 40 },
                radar: { indicator, radius: '65%' },
                series: [{
                    type: 'radar',
                    data: models.map((m, i) => ({
                        name: m,
                        value: [parseFloat(aggregated[m].precision), parseFloat(aggregated[m].recall), parseFloat(aggregated[m].f1), parseFloat(aggregated[m].iou)],
                        lineStyle: { color: colors[i % colors.length] },
                        areaStyle: { color: colors[i % colors.length], opacity: 0.1 },
                    })),
                }],
            });
            this._radarChart = radarChart;
        }
    },

    _scanThreshold() {
        if (this._results.length === 0) return Modal.alert(I18n.t('eval.needResultsFirst'));
        // Use the best-F1 pair for threshold scanning
        const scored = this._results.map(r => {
            let sumF1 = 0, count = 0;
            Object.values(r).forEach(v => {
                if (v && typeof v.f1 === 'number') { sumF1 += v.f1; count++; }
            });
            return { name: r.name, avgF1: count ? sumF1 / count : 0, result: r };
        }).sort((a, b) => b.avgF1 - a.avgF1);
        const best = scored[0];
        this._doScan(best.name);
    },

    async _doScan(pairName) {
        const { aH, bH, lH } = this._handles;
        const selectedModels = this._getSelectedModels();
        if (selectedModels.length === 0) return Modal.alert(I18n.t('eval.selectModel'));

        $('evalScanBtn').disabled = true;
        $('evalScanStatus').classList.remove('hidden');
        $('evalScanStatus').textContent = I18n.t('eval.scanning');

        try {
            const [aFile, bFile, lFile] = await Promise.all([
                aH.getFileHandle(pairName).then(h => h.getFile()),
                bH.getFileHandle(pairName).then(h => h.getFile()),
                lH ? lH.getFileHandle(pairName).then(h => h.getFile()).catch(() => null) : Promise.resolve(null),
            ]);

            const fd = new FormData();
            fd.append('img1', aFile);
            fd.append('img2', bFile);
            if (lFile) fd.append('label', lFile);
            fd.append('models', JSON.stringify(selectedModels));

            const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/evaluate/scan`, {
                method: 'POST',
                body: fd,
            });
            const json = await res.json();
            if (json.code === 200) {
                this._scanData = json.results;
                this._scanPairName = pairName;
                $('evalScanChart').classList.remove('hidden');
                setTimeout(() => this._renderScanChart(json.results), 100);
                $('evalScanStatus').textContent = I18n.t('eval.scanDone').replace('{name}', pairName);
            } else {
                $('evalScanStatus').textContent = I18n.t('eval.scanFailed');
            }
        } catch(e) {
            console.error('阈值扫描失败:', e);
            $('evalScanStatus').textContent = I18n.t('eval.scanFailed');
        }
        $('evalScanBtn').disabled = false;
    },

    _renderScanChart(scanData) {
        const dom = $('evalScanChart');
        if (!dom || !window.echarts) return;

        const chart = window.echarts.init(dom);
        const models = Object.keys(scanData);
        const colors = ['#667eea', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

        chart.setOption({
            title: { text: I18n.t('eval.scanTitle').replace('{name}', this._scanPairName), left: 'center', textStyle: { fontSize: 14, color: 'var(--text-primary)' } },
            tooltip: { trigger: 'axis' },
            legend: { data: models.map(m => `${m} F1`), bottom: 0, textStyle: { color: 'var(--text-secondary)' } },
            grid: { left: 60, right: 30, top: 50, bottom: 40 },
            xAxis: {
                type: 'category',
                data: scanData[models[0]].map(p => p.threshold),
                name: I18n.t('eval.threshold'),
                axisLabel: { fontSize: 11 },
            },
            yAxis: {
                type: 'value',
                max: 100,
                name: 'F1 (%)',
                axisLabel: { formatter: '{value}%' },
            },
            series: models.map((m, i) => ({
                name: `${m} F1`,
                type: 'line',
                data: scanData[m].map(p => p.f1),
                smooth: true,
                symbol: 'circle',
                symbolSize: 4,
                lineStyle: { color: colors[i % colors.length], width: 2 },
                itemStyle: { color: colors[i % colors.length] },
            })),
        });
        this._scanChart = chart;
    },

    _renderCases() {
        // Find best and worst 3 by average F1 across all models
        const scored = this._results.map(r => {
            let sumF1 = 0, count = 0;
            Object.values(r).forEach(v => {
                if (v && typeof v.f1 === 'number') { sumF1 += v.f1; count++; }
            });
            return { name: r.name, avgF1: count ? sumF1 / count : 0 };
        }).sort((a, b) => b.avgF1 - a.avgF1);

        const best3 = scored.slice(0, 3);
        const worst3 = scored.slice(-3).reverse();

        const renderGroup = (title, items) => {
            if (items.length === 0) return '<p style="color:var(--text-tertiary);">暂无数据</p>';
            return `<h4 style="margin-bottom:8px;color:var(--text-primary);">${title}</h4>
                <div style="display:flex;gap:12px;flex-wrap:wrap;">${items.map(item => {
                    const r = this._results.find(r => r.name === item.name);
                    const models = Object.keys(r).filter(k => ALL_MODELS.includes(k));
                    const caseId = `case-${item.name.replace(/[^a-zA-Z0-9]/g, '_')}`;
                    // Load images async
                    this._loadCaseImages(caseId, item.name);
                    return `<div style="flex:1;min-width:280px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);padding:12px;">
                        <div style="font-family:monospace;font-size:12px;margin-bottom:6px;word-break:break-all;color:var(--text-primary);">${item.name}</div>
                        <div style="font-size:13px;font-weight:600;color:var(--primary);margin-bottom:4px;">Avg F1: ${item.avgF1.toFixed(1)}%</div>
                        ${models.map(m => `<div style="font-size:11px;color:var(--text-secondary);">${m}: F1=${r[m]?.f1 ?? '--'}% IoU=${r[m]?.iou ?? '--'}%</div>`).join('')}
                        <div id="${caseId}" style="display:flex;gap:4px;margin-top:8px;overflow-x:auto;">
                            <div style="width:60px;height:60px;background:var(--bg-tertiary);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--text-tertiary);flex-shrink:0;">加载中...</div>
                        </div>
                    </div>`;
                }).join('')}</div>`;
        };

        $('evalBestCases').innerHTML = renderGroup('✅ 最佳 3 例', best3);
        $('evalWorstCases').innerHTML = renderGroup('⚠️ 最差 3 例', worst3);
    },

    async _loadCaseImages(containerId, pairName) {
        const container = document.getElementById(containerId);
        if (!container || !this._handles) return;

        try {
            const { aH, bH, lH } = this._handles;
            const [aFile, bFile, lFile] = await Promise.all([
                aH.getFileHandle(pairName).then(h => h.getFile()),
                bH.getFileHandle(pairName).then(h => h.getFile()),
                lH ? lH.getFileHandle(pairName).then(h => h.getFile()).catch(() => null) : Promise.resolve(null),
            ]);

            const urls = [];
            urls.push({ url: await Utils.createImagePreview(aFile), label: 'T1' });
            urls.push({ url: await Utils.createImagePreview(bFile), label: 'T2' });
            if (lFile) {
                urls.push({ url: await Utils.createImagePreview(lFile), label: 'GT' });
            }

            container.innerHTML = urls.map(({ url, label }) =>
                `<div style="text-align:center;flex-shrink:0;">
                    <img src="${url}" style="width:60px;height:60px;object-fit:cover;border-radius:4px;border:1px solid var(--border);" alt="${label}">
                    <div style="font-size:9px;color:var(--text-tertiary);margin-top:2px;">${label}</div>
                </div>`
            ).join('');
        } catch(e) {
            container.innerHTML = '<div style="font-size:10px;color:var(--text-tertiary);">图片加载失败</div>';
        }
    },

    _exportCsv() {
        const models = this._getSelectedModels().length > 0 ? this._getSelectedModels() : Object.keys(this._aggregate());
        if (models.length === 0 || this._results.length === 0) return;

        const header = ['filename', ...models.flatMap(m => [`${m}_Precision`, `${m}_Recall`, `${m}_F1`, `${m}_IoU`, `${m}_Time_ms`])];
        const rows = this._results.map(r => {
            const row = [r.name];
            models.forEach(m => {
                const d = r[m];
                row.push(d?.precision ?? '', d?.recall ?? '', d?.f1 ?? '', d?.iou ?? '', d?.time_ms ?? '');
            });
            return row;
        });

        const csv = [header.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'evaluation_results.csv';
        a.click();
        Utils.releaseObjectURL(url);
    },
};
