import { API } from './api.js';
import { I18n } from './i18n.js';
import { ChartUtils, createDoughnutOption, createBarOption, createTrendBarOption } from './chartUtils.js';

export const BigScreen = {
    _clockTimer: null,
    _autoRefreshTimer: null,
    _charts: ['bsTypeChart', 'bsModelChart', 'bsTrendChart'],

    init() {
        // Auto-refresh setup is handled by render() on page switch
    },

    /** 页面切换时清理定时器，避免后台继续运行 */
    cleanup() {
        if (this._clockTimer) {
            clearInterval(this._clockTimer);
            this._clockTimer = null;
        }
        if (this._autoRefreshTimer) {
            clearInterval(this._autoRefreshTimer);
            this._autoRefreshTimer = null;
        }
    },

    async render() {
        const page = document.getElementById('page-dashboard');
        if (!page || !page.classList.contains('active')) return;
        this.cleanup();
        this._startClock();
        this._startAutoRefresh();

        let history;
        try {
            history = await API.fetchHistory();
        } catch (e) {
            console.error('大屏数据加载失败:', e);
            this._showError();
            return;
        }
        // fetchHistory 失败返回 null（以前返回 []，所以这个兜底永远不触发，
        // 页面会把限流/断网渲染成「全 0 + 空环图」）
        if (history === null) {
            console.error('大屏数据加载失败：/history 未返回数据');
            this._showError();
            return;
        }

        // 四个区块各自独立渲染。此前共用一个 try/catch：只要前一个图表抛错，
        // 后面全部跳过 —— 连「最新检测记录」也一起变空。而那个列表是纯 HTML，
        // 根本不依赖 echarts，不该被图表的失败连坐。
        [
            ['统计卡', () => this.updateStats(history)],
            ['变化类型分布', () => this.renderTypeChart(history)],
            ['模型使用统计', () => this.renderModelChart(history)],
            ['近 7 天趋势', () => this.renderTrendChart(history)],
            ['最新检测记录', () => this.renderRecentList(history)],
        ].forEach(([name, fn]) => {
            try { fn(); } catch (e) { console.error('大屏「' + name + '」渲染失败:', e); }
        });
    },

    _startAutoRefresh() {
        this._autoRefreshTimer = setInterval(async () => {
            const page = document.getElementById('page-dashboard');
            if (!page || !page.classList.contains('active')) {
                this.cleanup();
                return;
            }
            try {
                const history = await API.fetchHistory();
                // 失败时保留屏幕上的上一次数据，绝不覆盖成 0 ——
                // 「静默不打扰」可以，但把正确数字换成错的不是静默，是撒谎。
                if (history === null) return;
                this.updateStats(history);
                this.renderRecentList(history);
            } catch(e) {
                // 静默失败，不打扰比赛展示
            }
        }, 30000);
    },

    /** 整批数据都没取到时的兜底：所有面板都填上可读的提示，不留白洞 */
    _showError() {
        const msg = I18n.t('dashboard.chartFailed', '数据加载失败，请刷新页面');
        ['bsTypeChart', 'bsModelChart', 'bsTrendChart'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;'
                + 'height:100%;color:var(--text-tertiary);">' + msg + '</div>';
        });
        const list = document.getElementById('bsRecentList');
        if (list) {
            list.innerHTML = '<div style="padding:16px;color:var(--text-tertiary);">' + msg + '</div>';
        }
    },

    _startClock() {
        const update = () => {
            const el = document.getElementById('bsDateTime');
            if (!el) return;
            const now = new Date();
            const pad = n => String(n).padStart(2, '0');
            const str = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
                `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
            el.textContent = str;
        };
        update();
        this._clockTimer = setInterval(update, 1000);
    },

    animateValue(el, target, duration = 900) {
        if (!el || target === undefined) return;
        const start = parseInt(el.textContent) || 0;
        if (start === target) return;
        const startTime = performance.now();
        const step = (currentTime) => {
            const progress = Math.min((currentTime - startTime) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            el.textContent = Math.floor(start + (target - start) * eased);
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    },

    updateStats(history) {
        const totalDetections = history.length;
        const totalChangePixels = history.reduce((sum, item) => sum + (parseInt(item.change_pixel) || 0), 0);
        const now = new Date();
        const todayPrefix = now.toISOString().slice(0, 10);
        const todayDetections = history.filter(item => item.time?.startsWith(todayPrefix)).length;
        const plots = new Set(history.map(item => item.location || item.lat_lng).filter(Boolean));

        this.animateValue(document.getElementById('bsTotalDetections'), totalDetections);
        this.animateValue(document.getElementById('bsTodayDetections'), todayDetections);
        this.animateValue(document.getElementById('bsActivePlots'), plots.size);

        const areaEl = document.getElementById('bsTotalChangeArea');
        // 单位也走 i18n：中文「万」= 10^4，英文用 ×10⁴，数值口径不变
        if (areaEl) areaEl.innerHTML = `${(totalChangePixels / 10000).toFixed(1)}`
            + `<span class="tech-unit">${I18n.t('dashboard.unitWan', '万')}</span>`;
    },

    renderTypeChart(history) {
        const typeCounts = {};
        history.forEach(item => {
            let type = item.change_type || I18n.t('notClassified');
            if (type.length > 8) type = type.slice(0, 8) + '…';
            typeCounts[type] = (typeCounts[type] || 0) + 1;
        });
        const labels = Object.keys(typeCounts);
        const values = Object.values(typeCounts);
        const chart = ChartUtils.init('bsTypeChart');
        if (!chart) return;
        ChartUtils.setAndTrack('bsTypeChart', chart, 'doughnut', { labels, values },
            createDoughnutOption({ labels, values }));
    },

    renderModelChart(history) {
        const modelCounts = {};
        history.forEach(item => {
            const m = item.model || I18n.t('chart.unknown');
            modelCounts[m] = (modelCounts[m] || 0) + 1;
        });
        const labels = Object.keys(modelCounts);
        const values = Object.values(modelCounts);
        const chart = ChartUtils.init('bsModelChart');
        if (!chart) return;
        ChartUtils.setAndTrack('bsModelChart', chart, 'bar', { labels, values },
            createBarOption({ labels, values }));
    },

    renderTrendChart(history) {
        const days = [];
        const now = new Date();
        for (let i = 6; i >= 0; i--) {
            const d = new Date(now);
            d.setDate(d.getDate() - i);
            days.push(d.toISOString().slice(0, 10));
        }
        const counts = days.map(day => history.filter(item => item.time?.startsWith(day)).length);
        const chart = ChartUtils.init('bsTrendChart');
        if (!chart) return;
        ChartUtils.setAndTrack('bsTrendChart', chart, 'trendBar',
            { labels: days.map(d => d.slice(5)), values: counts, seriesName: I18n.t('chart.detectionCount') },
            createTrendBarOption({
                labels: days.map(d => d.slice(5)),
                values: counts,
                seriesName: I18n.t('chart.detectionCount'),
            }));
    },

    renderRecentList(history) {
        const recent = history.slice(0, 8);
        const dom = document.getElementById('bsRecentList');
        if (!dom) return;
        if (recent.length === 0) {
            dom.innerHTML = `<div style="text-align:center;color:var(--text-tertiary);padding:20px;">${I18n.t('common.noData')}</div>`;
            return;
        }
        dom.innerHTML = recent.map((item, i) => `
            <div class="tech-recent-item" style="animation-delay:${i * 0.06}s">
                <span class="tech-recent-index">${String(i + 1).padStart(2, '0')}</span>
                <div class="tech-recent-info">
                    <span class="tech-recent-name">${item.batchName || I18n.t('chart.singleDetection')}</span>
                    <span class="tech-recent-time">${item.time || '-'}</span>
                </div>
                <span class="tech-recent-ratio">${item.ratio != null ? item.ratio + '%' : '-'}</span>
            </div>
        `).join('');
    }
};
