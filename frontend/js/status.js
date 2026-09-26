import { CONFIG } from './config.js';
import { Utils } from './utils.js';

export const SystemStatus = {
    init() {},
    async render() {
        const page = document.getElementById('page-status');
        if (!page || !page.classList.contains('active')) return;

        try {
            const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/status`);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const json = await res.json();
            if (json.code === 200) {
                var d = json.data;
                // Model info
                setText('stModel', d.model || '-');
                setText('stDevice', d.device || '-');
                setText('stTorch', d.pytorch_version || '-');
                setText('stPython', d.python_version || '-');
                setText('stDB', d.database || '-');

                // Runtime
                setText('stUptime', d.uptime || '-');

                // CPU / Memory bars
                var cpu = d.cpu_percent || 0;
                var memPct = d.memory_percent || 0;
                setBar('stCpuBar', 'stCpuVal', cpu);
                setBar('stMemBar', 'stMemVal', memPct);
                setText('stMemDetail', (d.memory_used_gb || '?') + ' / ' + (d.memory_total_gb || '?') + ' GB');

                // Request stats
                setText('stReqTotal', d.total_requests || 0);
                renderRequestBars(d.requests || {});

                // Storage
                setText('stDiskUploads', d.disk_uploads_gb != null ? d.disk_uploads_gb + ' GB' : '--');
                setText('stDiskResults', d.disk_results_gb != null ? d.disk_results_gb + ' GB' : '--');
            }
        } catch (e) {
            ['stModel','stDevice','stTorch','stPython','stDB','stUptime','stReqTotal','stDiskUploads','stDiskResults'].forEach(function(id) {
                var el = document.getElementById(id);
                if (el && el.textContent === '加载中...') el.textContent = '--';
            });
        }
    }
};

function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
}

function setBar(barId, valId, pct) {
    var bar = document.getElementById(barId);
    var val = document.getElementById(valId);
    var color = pct > 80 ? 'var(--danger)' : pct > 50 ? 'var(--accent)' : 'var(--primary)';
    if (bar) { bar.style.width = pct + '%'; bar.style.background = color; }
    if (val) val.textContent = pct + '%';
}

function renderRequestBars(requests) {
    var container = document.getElementById('stReqBars');
    if (!container) return;
    var names = {
        detect: '检测', register: '注册', login: '登录',
        chat: 'AI对话', analysis: 'AI解读', regeo: '地理编码',
        history: '历史', compare: '对比', recommend: '推荐阈值'
    };
    var maxVal = 0;
    Object.values(requests).forEach(function(v) { if (v > maxVal) maxVal = v; });
    if (maxVal === 0) maxVal = 1;

    var html = '';
    Object.keys(names).forEach(function(key) {
        var count = requests[key] || 0;
        var pct = (count / maxVal * 100).toFixed(0);
        html += '<div class="status-req-row">' +
            '<span class="status-req-label">' + (names[key] || key) + '</span>' +
            '<div class="status-req-track"><div class="status-req-fill" style="width:' + pct + '%;"></div></div>' +
            '<span class="status-req-count">' + count + '</span>' +
            '</div>';
    });
    container.innerHTML = html;
}