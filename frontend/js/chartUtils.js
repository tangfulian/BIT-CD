import { I18n } from './i18n.js';

const COLORS = ['#667eea', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const _instances = {};
const _lastParams = {};
const _resizeObservers = {};
let _themeObserver = null;

function _getThemeColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
        textColor: isDark ? '#94a3b8' : '#475569',
        bgColor: isDark ? '#1e293b' : '#ffffff',
        axisColor: isDark ? '#334155' : '#e2e8f0',
        emphasisLabelColor: isDark ? '#f1f5f9' : '#1e293b',
    };
}

function _setupThemeObserver() {
    if (_themeObserver) return;
    _themeObserver = new MutationObserver(() => {
        Object.keys(_instances).forEach(domId => {
            const inst = _instances[domId];
            const params = _lastParams[domId];
            if (!inst || inst.isDisposed() || !params) return;
            const { type, data } = params;
            let option;
            if (type === 'doughnut') option = createDoughnutOption(data);
            else if (type === 'bar') option = createBarOption(data);
            else if (type === 'trendBar') option = createTrendBarOption(data);
            else if (type === 'line') option = createLineOption(data);
            if (option) inst.setOption(option, { notMerge: false });
        });
    });
    _themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}

function _observeResize(domId, instance) {
    const el = document.getElementById(domId);
    if (!el) return;
    if (_resizeObservers[domId]) _resizeObservers[domId].disconnect();
    const ro = new ResizeObserver(() => instance.resize());
    ro.observe(el);
    _resizeObservers[domId] = ro;
}

export const ChartUtils = {
    COLORS,

    init(domId) {
        const el = document.getElementById(domId);
        if (!el) return null;
        if (_instances[domId] && !_instances[domId].isDisposed()) {
            _instances[domId].dispose();
        }
        const instance = echarts.init(el);
        _instances[domId] = instance;
        _observeResize(domId, instance);
        _setupThemeObserver();
        return instance;
    },

    dispose(domId) {
        if (_instances[domId] && !_instances[domId].isDisposed()) {
            _instances[domId].dispose();
        }
        delete _instances[domId];
        delete _lastParams[domId];
        if (_resizeObservers[domId]) {
            _resizeObservers[domId].disconnect();
            delete _resizeObservers[domId];
        }
    },

    disposeAll() {
        Object.keys(_instances).forEach(id => this.dispose(id));
    },

    resizeAll() {
        Object.values(_instances).forEach(inst => {
            if (inst && !inst.isDisposed()) inst.resize();
        });
    },

    setAndTrack(domId, instance, type, data, option) {
        _lastParams[domId] = { type, data };
        instance.setOption(option);
    },
};

export function createDoughnutOption({ labels, values }) {
    const { textColor, emphasisLabelColor } = _getThemeColors();
    return {
        tooltip: {
            trigger: 'item',
            formatter(p) {
                return p.name + ': ' + p.value + ' ' + (I18n.t('status.countUnit') || I18n.t('status.countUnit', ''));
            },
        },
        legend: {
            orient: 'horizontal',
            bottom: 0,
            textStyle: { color: textColor, fontSize: 12 },
            itemWidth: 12,
            itemHeight: 12,
            itemGap: 16,
        },
        series: [{
            type: 'pie',
            radius: ['42%', '72%'],
            center: ['50%', '45%'],
            avoidLabelOverlap: false,
            itemStyle: {
                borderRadius: 4,
                borderColor: '#fff',
                borderWidth: 2,
            },
            label: { show: false },
            emphasis: {
                label: { show: true, fontWeight: 'bold', fontSize: 14, color: emphasisLabelColor },
                scaleSize: 10,
            },
            animationType: 'scale',
            animationEasing: 'elasticOut',
            data: labels.map((name, i) => ({
                name,
                value: values[i],
                itemStyle: { color: COLORS[i % COLORS.length] },
            })),
        }],
    };
}

export function createBarOption({ labels, values }) {
    const { textColor, axisColor } = _getThemeColors();
    const rotate = labels.length > 6 ? 30 : 0;
    return {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
        },
        grid: { left: 40, right: 20, top: 10, bottom: rotate ? 60 : 30 },
        xAxis: {
            type: 'category',
            data: labels,
            axisLabel: { color: textColor, rotate },
            axisLine: { lineStyle: { color: axisColor } },
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { color: textColor },
            splitLine: { lineStyle: { color: axisColor } },
        },
        series: [{
            type: 'bar',
            barMaxWidth: 50,
            data: values.map((v, i) => ({
                value: v,
                itemStyle: {
                    color: COLORS[i % COLORS.length],
                    borderRadius: [4, 4, 0, 0],
                },
            })),
            animationDelay(idx) { return idx * 80; },
        }],
    };
}

export function createTrendBarOption({ labels, values, seriesName }) {
    const { textColor, axisColor } = _getThemeColors();
    return {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
        },
        grid: { left: 45, right: 20, top: 10, bottom: 30 },
        xAxis: {
            type: 'category',
            data: labels,
            axisLabel: { color: textColor },
            axisLine: { lineStyle: { color: axisColor } },
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { color: textColor },
            splitLine: { lineStyle: { color: axisColor } },
        },
        series: [{
            name: seriesName || '',
            type: 'bar',
            barMaxWidth: 40,
            itemStyle: {
                color: COLORS[0],
                borderRadius: [6, 6, 0, 0],
            },
            data: values,
            animationDelay(idx) { return idx * 100; },
        }],
    };
}

export function createLineOption({ labels, values, seriesName, xLabel, yLabel, showDataZoom }) {
    const { textColor, axisColor } = _getThemeColors();
    const hasZoom = showDataZoom !== false && labels.length > 10;
    return {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            formatter(params) {
                const p = params[0];
                return p.axisValue + '<br/>' +
                    '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;' +
                    'background:' + p.color + ';margin-right:6px;"></span>' +
                    p.seriesName + ': <strong>' + p.value + '%</strong>';
            },
        },
        grid: { left: 55, right: 25, top: 20, bottom: hasZoom ? 60 : 30 },
        ...(hasZoom ? {
            dataZoom: [
                { type: 'slider', start: 0, end: 100, height: 20, bottom: 5, textStyle: { color: textColor } },
                { type: 'inside' },
            ],
        } : {}),
        xAxis: {
            type: 'category',
            data: labels,
            boundaryGap: false,
            name: xLabel || '',
            nameTextStyle: { color: textColor },
            axisLabel: { color: textColor },
            axisLine: { lineStyle: { color: axisColor } },
        },
        yAxis: {
            type: 'value',
            name: yLabel || '',
            nameTextStyle: { color: textColor },
            axisLabel: { color: textColor, formatter: '{value}%' },
            splitLine: { lineStyle: { color: axisColor } },
        },
        series: [{
            name: seriesName || '',
            type: 'line',
            data: values,
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            lineStyle: { color: COLORS[0], width: 2 },
            itemStyle: { color: COLORS[0] },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(102,126,234,0.35)' },
                    { offset: 1, color: 'rgba(102,126,234,0.02)' },
                ]),
            },
            emphasis: {
                focus: 'series',
                itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
            },
        }],
    };
}
