import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { I18n } from './i18n.js';
import { eventBus } from './eventBus.js';

// 每次进入页面都要重取的字段。
const FIELDS = [
    'stModel', 'stDevice', 'stTorch', 'stPython', 'stDB',
    'stUptime', 'stReqTotal', 'stDiskUploads', 'stDiskResults'
];

// 后端 /status 的 requests 桶名 → 中文桶名；i18n 键由桶名拼成 status.req.<桶名>。
const REQ_BUCKETS = {
    detect: '检测', register: '注册', login: '登录',
    chat: 'AI 对话', analysis: 'AI 解读', regeo: '地理编码',
    history: '历史', compare: '对比', recommend: '推荐阈值'
};

// 并发保护：来回切页面时，旧的一次 fetch 可能后返回，只有最新一次的写入算数。
let _seq = 0;

// 上一次取到的运行秒数。运行时长是 JS 按当前语言拼出来的字符串，
// 不是 data-i18n 元素 —— 切语言时不会自己重排，得留着原料手动重排一次。
let _uptimeSeconds = null;

export const SystemStatus = {
    init() {
        eventBus.on('lang-change', () => {
            if (_uptimeSeconds !== null) setText('stUptime', formatUptime(_uptimeSeconds));
        });
    },

    async render() {
        const page = document.getElementById('page-status');
        if (!page || !page.classList.contains('active')) return;

        const me = ++_seq;

        // 先清成占位符再取数，这样失败分支可以**无条件**写 '--'。
        // 原来靠比较 `textContent === '加载中...'` 来判断「还没取到值」，
        // 那是拿中文串当逻辑哨兵：英文界面下占位符是 "Loading..."，
        // 判断永远不成立，后端一挂就永远停在加载中。
        FIELDS.forEach(id => setText(id, I18n.t('common.loading')));
        setHtml('stReqBars', '');
        toggleError(false);

        try {
            const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/status`);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const json = await res.json();
            if (json.code !== 200) throw new Error('code ' + json.code);
            if (me !== _seq) return;   // 已经有更新的一次在跑，丢弃本次结果

            const d = json.data;
            // Model info
            setText('stModel', d.model || '-');
            setText('stDevice', d.device || '-');
            setText('stTorch', d.pytorch_version || '-');
            setText('stPython', d.python_version || '-');
            setText('stDB', d.database || '-');

            // Runtime
            _uptimeSeconds = typeof d.uptime_seconds === 'number' ? d.uptime_seconds : null;
            setText('stUptime', _uptimeSeconds !== null ? formatUptime(_uptimeSeconds) : (d.uptime || '-'));

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
        } catch (e) {
            if (me !== _seq) return;
            // 一起清掉，否则失败后切一次语言，上面那个监听会把上一次成功取到的
            // 运行时长又写回来 —— 一排 '--' 里混着一个像模像样的旧值。
            _uptimeSeconds = null;
            FIELDS.forEach(id => setText(id, '--'));
            toggleError(true);
        }
    }
};

/**
 * 运行时长在前端拼。后端返回的 uptime 是写死的中文串（"0天 0小时 5分钟 12秒"），
 * 英文界面下会原样显示；秒数字段两边都能用。
 */
function formatUptime(total) {
    return I18n.t('status.uptimeFormat', null,
        Math.floor(total / 86400),
        Math.floor((total % 86400) / 3600),
        Math.floor((total % 3600) / 60),
        total % 60);
}

function toggleError(show) {
    const el = document.getElementById('statusError');
    if (el) el.classList.toggle('hidden', !show);
}

function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
}

function setHtml(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
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
    var maxVal = 0;
    Object.values(requests).forEach(function(v) { if (v > maxVal) maxVal = v; });
    if (maxVal === 0) maxVal = 1;

    var html = '';
    Object.keys(REQ_BUCKETS).forEach(function(key) {
        var count = requests[key] || 0;
        var pct = (count / maxVal * 100).toFixed(0);
        // data-i18n 挂在生成的标签上：插入时由 i18n 的 MutationObserver 译一次，
        // 切语言时由 setLocale 的全量重译覆盖，不必额外订阅 lang-change。
        html += '<div class="status-req-row">' +
            '<span class="status-req-label" data-i18n="status.req.' + key + '">' + (REQ_BUCKETS[key] || key) + '</span>' +
            '<div class="status-req-track"><div class="status-req-fill" style="width:' + pct + '%;"></div></div>' +
            '<span class="status-req-count">' + count + '</span>' +
            '</div>';
    });
    container.innerHTML = html;
}
