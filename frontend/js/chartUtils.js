import { I18n } from './i18n.js';

// 分类色板 —— 从黑土地的实物取色，而不是通用彩虹。
// 顺序即视觉权重：主色打头，后面是麦秆、遥感靛蓝、橄榄、壤土棕、浅绿。
// 这组颜色彼此可区分，且在亮/暗两套主题下都够稳（明度拉开、饱和度压低）。
//
// 注意别和 mapViewer / evaluator 里的那组混用：那组是**严重度**色阶
// （绿→靛→琥珀→红，对应变化率分档），语义不同，各管各的。
const COLORS_LIGHT = ['#2c5e44', '#c2852c', '#5b7a99', '#8a8f4a', '#a9673f', '#4ea877'];
// 暗色下把同一组色相整体提亮：深绿与橄榄压在 #0f1612 上会糊成一片，
// 环形图相邻扇区直接分不开。色相不动，只调明度与饱和度。
const COLORS_DARK = ['#6aa887', '#e0a84e', '#7f9fbd', '#b3b874', '#cf8a5f', '#6fc79a'];

/** 当前主题下的分类色板。主题切换时图表会整体重建，所以这里可以读实时状态。 */
function _palette() {
    return document.documentElement.getAttribute('data-theme') === 'dark'
        ? COLORS_DARK : COLORS_LIGHT;
}

const _instances = {};
const _lastParams = {};
const _resizeObservers = {};
let _themeObserver = null;

function _getThemeColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    // 与主题的中性色对齐。原先用的是 Tailwind 的冷灰（slate），
    // 压在本项目的暖灰底上发青，图与界面像两套东西。
    return {
        textColor: isDark ? '#99a89f' : '#5a6a60',
        bgColor: isDark ? '#1a2420' : '#ffffff',
        axisColor: isDark ? '#2a3630' : '#e0dcd5',
        emphasisLabelColor: isDark ? '#e6ece8' : '#1a231e',
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
    get COLORS() { return _palette(); },

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
            // 变化类型名最长到「耕地非粮化（种树/挖塘）」，一排放不下会被硬切。
            // 滚动图例接管溢出，超长名称截断加省略号（完整名称仍在 tooltip 里）。
            type: 'scroll',
            orient: 'horizontal',
            bottom: 0,
            textStyle: { color: textColor, fontSize: 12 },
            itemWidth: 12,
            itemHeight: 12,
            itemGap: 16,
            formatter(name) {
                return name.length > 9 ? name.slice(0, 9) + '…' : name;
            },
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
                itemStyle: { color: _palette()[i % _palette().length] },
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
                    color: _palette()[i % _palette().length],
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
                color: _palette()[0],
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
            lineStyle: { color: _palette()[0], width: 2 },
            itemStyle: { color: _palette()[0] },
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
