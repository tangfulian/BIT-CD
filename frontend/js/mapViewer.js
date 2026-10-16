import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { API } from './api.js';
import { I18n } from './i18n.js';
import { Toast } from './toast.js';
import { eventBus } from './eventBus.js';

/**
 * 底图因高德鉴权失败而画不出来时的提示语。
 * AMap 自身不报错、map 的 complete 事件照样触发，画布只是整块空白；
 * 这个标志位由 index.html 里的 console 探针捕获 INVALID_USER_DOMAIN 后置位。
 */
const AUTH_MSG = '底图加载失败：高德 Key 未授权当前域名，标记仍可查看';

// 矢量底图的样式与偏好键统一放在 config.js（地块信息页那张地图也用同一份）。
// 注意 setStyle() 对已渲染的地图不生效，样式只能在 new AMap.Map 时给（见 _buildMap）。
const LIGHT_STYLE = CONFIG.MAP_STYLE_LIGHT;
const DARK_STYLE = CONFIG.MAP_STYLE_DARK;
const BASE_MODE_KEY = CONFIG.MAP_BASE_KEY;

function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
}

export const MapViewer = {
    map: null,
    markers: [],
    heatmap: null,
    _heatmapData: [],
    _heatmapVisible: false,
    // 底图类型：'satellite'（默认，写实的卫星影像）| 'standard'（矢量路网）
    _baseMode: 'satellite',
    _history: [],
    _errorMsg: null,

    init() {
        const toggleBtn = document.getElementById('heatmapToggleBtn');
        if (toggleBtn) {
            toggleBtn.onclick = () => this.toggleHeatmap();
        }

        this._baseMode = Utils.safeLocalStorage.getItem(BASE_MODE_KEY) === 'standard'
            ? 'standard' : 'satellite';
        ['mapBaseStdBtn', 'mapBaseSatBtn'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.onclick = () => this.setBaseLayer(btn.dataset.mode);
        });
        this._syncBaseButtons();

        // 地图底图不吃 CSS 变量，主题换了得自己重挑底图（见 _onThemeChange）
        eventBus.on('theme-change', () => this._onThemeChange());
    },

    setBaseLayer(mode) {
        if (mode !== 'satellite' && mode !== 'standard') return;
        if (mode === this._baseMode) return;
        this._baseMode = mode;
        Utils.safeLocalStorage.setItem(BASE_MODE_KEY, mode);
        this._syncBaseButtons();
        this._rebuildMap();
    },

    _syncBaseButtons() {
        [['mapBaseStdBtn', 'standard'], ['mapBaseSatBtn', 'satellite']].forEach(([id, mode]) => {
            const btn = document.getElementById(id);
            if (btn) btn.setAttribute('aria-pressed', String(this._baseMode === mode));
        });
    },

    _isDark() {
        return document.documentElement.getAttribute('data-theme') === 'dark';
    },

    /**
     * 卫星模式下把 Satellite / RoadNet 图层叠到默认底图之上（它们不透明，会盖住）。
     * 失败就回退到矢量图 —— 卫星瓦片取不到（配额、网络）不该让整张地图空掉。
     */
    _attachSatellite() {
        if (this._baseMode !== 'satellite') return;
        try {
            this._satellite = new AMap.TileLayer.Satellite();
            this._roadNet = new AMap.TileLayer.RoadNet();
            this.map.add([this._satellite, this._roadNet]);
        } catch (e) {
            console.warn('[MapViewer] 卫星图层加载失败，回退到矢量底图', e);
            this._satellite = null;
            this._roadNet = null;
        }
    },

    /**
     * 暗色主题下压暗卫星底图。改的是容器上的一个类，由 CSS 去只作用于
     * canvas.amap-layer —— 因此标记点不受影响，也不需要重建地图。
     */
    _applyBaseTone() {
        const el = document.getElementById('mapviewerMap');
        if (el) el.classList.toggle('map-dark-base', this._isDark() && this._baseMode === 'satellite');
    },

    _onThemeChange() {
        if (!this.map) return;
        // 卫星模式只需换个滤镜（无闪烁）；矢量模式的样式只能在构造时定，
        // 所以必须重建。
        if (this._baseMode === 'satellite') this._applyBaseTone();
        else this._rebuildMap();
    },

    /** 按当前底图/主题重建地图，尽量保住用户当前的视野。 */
    _rebuildMap() {
        if (!this.map) return;
        let view = null;
        try {
            view = { center: this.map.getCenter(), zoom: this.map.getZoom() };
        } catch (e) {
            view = null;
        }
        this._buildMap(this._history, this._errorMsg, view);
    },

    async render() {
        const page = document.getElementById('page-mapviewer');
        if (!page || !page.classList.contains('active')) return;

        // fetchHistory 现在失败返回 null、空数据返回 []。
        // 以前它一律 return []，所以下面这个 catch 是死代码，而请求失败时
        // 页面会显示「暂无带坐标的检测记录 / 带坐标记录：0」—— 实测当时
        // 库里有 118 条带坐标记录，页面是在说谎。
        let history;
        try {
            history = await API.fetchHistory();
        } catch (e) {
            console.error('加载地图数据失败:', e);
            history = null;
        }
        if (history === null) {
            const msg = I18n.t('common.loadFailed', '数据加载失败，请重试');
            Toast.error(msg);
            this.initMap([], msg);
            return;
        }
        console.log('[MapViewer] 历史记录:', history.length, '条, 含坐标:', history.filter(function(i) { return !!i.lat_lng; }).length, '条');
        this.initMap(history);
    },

    /**
     * @param {Array} history - 检测记录
     * @param {string} [errorMsg] - 请求失败时的提示；给了就说明是「加载失败」，
     *   而不是「确实没有带坐标的记录」，两者不能共用同一句话
     */
    initMap(history, errorMsg) {
        // 缓存起来：切换底图/主题要按同一批数据重建地图，不能重新去请求
        this._history = history;
        this._errorMsg = errorMsg;
        this._buildMap(history, errorMsg, null);
    },

    /**
     * 建图并画点。切底图、切主题都会回来重建 —— 因为高德的自定义样式只能在
     * 构造时给（setStyle() 对已渲染的地图不重绘），重建是唯一可靠的办法。
     * @param {{center: object, zoom: number}|null} view - 传了就沿用这个视野
     *   （重建时保住用户当前的缩放和位置），不传则用默认视野 + setFitView
     */
    _buildMap(history, errorMsg, view) {
        const container = document.getElementById('mapviewerMap');
        if (!container) return;

        const geoItems = history.filter(item => {
            if (!item.lat_lng) return false;
            const ll = this._parseLatLng(item.lat_lng);
            return ll !== null;
        });

        // Update side panel stats
        this._updateSidePanel(geoItems);

        if (this.map) {
            this.map.destroy();
            this.map = null;
        }
        // 这些都挂在旧地图实例上，destroy 后必须一并丢弃：
        // 留着的话热力图会绑在一张已销毁的地图上，而且永远不会重建。
        this.markers = [];
        this.heatmap = null;
        this._heatmapData = [];
        this._heatmapVisible = false;
        // 按钮文案也得跟着回到初始态，否则重建后显示的是上一次的「标记点模式」
        const heatBtn = document.getElementById('heatmapToggleBtn');
        if (heatBtn) heatBtn.textContent = I18n.t('map.heatmapMode');

        // AMap 脚本可能整个没加载出来（未配 Key、CDN 不可达）
        if (typeof AMap === 'undefined') {
            console.warn('[MapViewer] AMap 未加载');
            this._showMapHint('地图组件未加载（未配置高德 Key 或网络不可达）');
            return;
        }

        try {
            this.map = new AMap.Map("mapviewerMap", {
                zoom: view ? view.zoom : 6,
                center: view ? [view.center.lng, view.center.lat] : [126.63, 45.75],
                resizeEnable: true,
                mapStyle: this._isDark() ? DARK_STYLE : LIGHT_STYLE
            });
        } catch (e) {
            console.error('[MapViewer] 地图初始化失败', e);
            this._showMapHint('底图加载失败，请检查高德 Key 的域名白名单是否包含当前域名');
            return;
        }

        try {
            this._attachSatellite();
        } catch (e) {
            console.warn('[MapViewer] 卫星图层异常', e);
        }
        this._applyBaseTone();

        // 底图瓦片/样式被高德拒绝时（域名未授权 → INVALID_USER_DOMAIN），
        // new AMap.Map 本身**不会**报错，画布只是整块空白，页面静默无提示，
        // 用户看到的就是「一张白纸上飘着一个标记点」。
        // AMap 在底图就绪时派发 complete 事件；超时仍未等到就判定为没画出来。
        let mapReady = false;
        clearTimeout(this._mapReadyTimer);
        this.map.on('complete', () => {
            mapReady = true;
            clearTimeout(this._mapReadyTimer);
            // 这里**不要**去收提示：底图就绪不代表有记录，
            // 收了会把「暂无带坐标的检测记录」的正常空态一起抹掉。
            // 提示的显隐由下面的空态分支与失败回调各自负责。
        });

        // 鉴权失败的确定性信号来自 index.html 的 console 探针（AMap 自身
        // 不提供任何可用的 API 信号，且瓦片全被拒时 complete 照样触发）。
        // 报错时机比任何定时猜测都准，所以以事件为主、超时为兜底。
        if (this._onAmapAuthFail) {
            window.removeEventListener('amap-auth-failed', this._onAmapAuthFail);
        }
        this._onAmapAuthFail = () => {
            console.warn('[MapViewer] 高德鉴权失败（域名未授权）');
            this._showMapHint(AUTH_MSG);
        };
        window.addEventListener('amap-auth-failed', this._onAmapAuthFail);

        this._mapReadyTimer = setTimeout(() => {
            // complete 在瓦片被拒时也会触发，这条纯粹是兜底猜测
            if (!mapReady) {
                console.warn('[MapViewer] 底图 8 秒内未就绪，判定为加载失败');
                this._showMapHint('底图加载失败，标记仍可查看');
            }
        }, 8000);

        if (geoItems.length === 0) {
            const btn = document.getElementById('heatmapToggleBtn');
            if (btn) btn.style.display = 'none';
            if (errorMsg) this._showMapHint(errorMsg);
            else if (window.__amapAuthFailed) this._showMapHint(AUTH_MSG);
            else this._clearMapHint(true);   // 显示原始的空态文案
            return;
        }
        // 鉴权失败的提示优先级最高：它不是「没有记录」，是底图没画出来。
        // 不加这个分支的话，下面这行 _clearMapHint() 会把事件回调刚弹出的
        // 警示又收掉（二次进入本页时就是这个顺序）。
        if (window.__amapAuthFailed) this._showMapHint(AUTH_MSG);
        else this._clearMapHint();

        const points = [];
        const infoWindow = new AMap.InfoWindow({ offset: new AMap.Pixel(0, -30) });

        geoItems.forEach((item, idx) => {
            const ll = this._parseLatLng(item.lat_lng);
            if (!ll) return;
            const ratio = parseFloat(item.ratio) || 0;
            const color = ratio > 30 ? '#ef4444' : ratio > 15 ? '#f59e0b' : ratio > 5 ? '#667eea' : '#10b981';
            const marker = new AMap.Marker({
                position: [ll.lng, ll.lat],
                icon: new AMap.Icon({
                    size: new AMap.Size(24, 24),
                    image: this._createMarkerSVG(color, ratio),
                    imageSize: new AMap.Size(24, 24)
                }),
                anchor: 'center'
            });
            marker.on('click', (function(item, color, ratio) {
                return function() {
                    infoWindow.setContent([
                        '<div style="font-size:13px;line-height:1.8;min-width:200px;">',
                        '<strong>' + (item.change_type || I18n.t('notClassified')) + '</strong><br>',
                        I18n.t('detect.changeRatio') + '：<span style="color:' + color + ';font-weight:700;">' + ratio + '%</span><br>',
                        I18n.t('common.model') + '：' + (item.model || '?') + '<br>',
                        I18n.t('common.location') + '：' + (item.location || I18n.t('unknown')) + '<br>',
                        I18n.t('common.time') + '：' + (item.time || ''),
                        item.mask ? '<br><a href="' + item.mask + '" target="_blank" style="color:#667eea;">' + I18n.t('map.viewResult') + '</a>' : '',
                        '</div>'
                    ].join(''));
                    infoWindow.open(this.map, marker.getPosition());

                    // Update side panel selected info
                    var selDiv = document.getElementById('mapSelectedInfo');
                    var selContent = document.getElementById('mapSelectedContent');
                    if (selDiv && selContent) {
                        selDiv.classList.remove('hidden');
                        selContent.innerHTML = [
                            '<p><strong>' + (item.change_type || I18n.t('notClassified')) + '</strong></p>',
                            '<p>' + I18n.t('detect.changeRatio') + '：<span style="color:' + color + ';font-weight:700;">' + ratio + '%</span></p>',
                            '<p>' + I18n.t('common.model') + '：' + (item.model || '?') + '</p>',
                            '<p>' + I18n.t('common.location') + '：' + (item.location || I18n.t('unknown')) + '</p>',
                            '<p>' + I18n.t('common.time') + '：' + (item.time || '--') + '</p>'
                        ].join('');
                    }
                };
            })(item, color, ratio));
            marker.setMap(this.map);
            this.markers.push(marker);
            points.push([ll.lng, ll.lat]);

            this._heatmapData.push({
                lng: ll.lng,
                lat: ll.lat,
                count: Math.max(1, (item.change_pixel || 2500) / 1000)
            });
        });

        // 重建时点了 setFitView 会把用户刚调好的视野又拉回去
        if (!view && this.markers.length > 0) this.map.setFitView(this.markers);

        // 异步加载热力图插件
        if (!this.heatmap) {
            // 回调是异步的，期间用户可能又切了底图/主题把地图换掉了。
            // 不加这道判断，热力图会挂到一张已销毁的地图上。
            const builtFor = this.map;
            AMap.plugin('AMap.HeatMap', () => {
                if (this.map !== builtFor) return;
                this.heatmap = new AMap.HeatMap(this.map, {
                    radius: 30,
                    opacity: [0, 0.7],
                    gradient: {
                        0.2: '#10b981',
                        0.4: '#667eea',
                        0.6: '#f59e0b',
                        0.8: '#ef4444'
                    }
                });
                this.heatmap.setDataSet({ data: this._heatmapData, max: 100 });
                document.getElementById('heatmapToggleBtn').style.display = 'inline-block';
            });
        } else {
            this.heatmap.setDataSet({ data: this._heatmapData, max: 100 });
        }
    },

    toggleHeatmap() {
        if (!this.heatmap) return;
        const btn = document.getElementById('heatmapToggleBtn');
        if (this._heatmapVisible) {
            this.heatmap.hide();
            this.markers.forEach(m => m.show());
            btn.textContent = I18n.t('map.heatmapMode');
        } else {
            this.heatmap.show();
            this.markers.forEach(m => m.hide());
            btn.textContent = I18n.t('map.markerMode');
        }
        this._heatmapVisible = !this._heatmapVisible;
    },

    _updateSidePanel(geoItems) {
        var geoCount = geoItems.length;
        setText('mapGeoCount', geoCount);
        if (geoCount === 0) {
            setText('mapAvgRatio', '--');
            setText('mapMaxRatio', '--');
            setText('mapUniqueLocs', '0');
            return;
        }
        var sumRatio = 0;
        var maxRatio = 0;
        var locations = {};
        geoItems.forEach(function(item) {
            var r = parseFloat(item.ratio) || 0;
            sumRatio += r;
            if (r > maxRatio) maxRatio = r;
            if (item.location) locations[item.location] = true;
        });
        setText('mapAvgRatio', (sumRatio / geoCount).toFixed(1) + '%');
        setText('mapMaxRatio', maxRatio.toFixed(1) + '%');
        setText('mapUniqueLocs', Object.keys(locations).length);
    },

    _parseLatLng(str) {
        if (!str) return null;
        // 东经/北纬 中文格式
        const lngMatch = str.match(/东经\s*([\d.]+)/);
        const latMatch = str.match(/北纬\s*([\d.]+)/);
        if (lngMatch && latMatch) {
            return { lng: parseFloat(lngMatch[1]), lat: parseFloat(latMatch[1]) };
        }
        // 逗号分隔: "126.63, 45.75" 或 "126.63，45.75"
        const numMatch = str.match(/([\d.]+)\s*[,，]\s*([\d.]+)/);
        if (numMatch) {
            return { lng: parseFloat(numMatch[1]), lat: parseFloat(numMatch[2]) };
        }
        // 空格分隔: "126.63 45.75"
        const spaceMatch = str.match(/([\d.]+)\s+([\d.]+)/);
        if (spaceMatch) {
            return { lng: parseFloat(spaceMatch[1]), lat: parseFloat(spaceMatch[2]) };
        }
        return null;
    },

    _createMarkerSVG(color, ratio) {
        const size = Math.min(24, 12 + ratio * 0.4);
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="${size/2}" fill="${color}" opacity="0.8" stroke="white" stroke-width="2"/>
        </svg>`;
        return 'data:image/svg+xml;base64,' + btoa(svg);
    },

    /**
     * 在地图容器上叠一条可见的警示。
     * 底图加载失败时页面原本是「一块纯色画布 + 一个标记点」，完全静默 ——
     * 用户不知道是底图坏了还是自己看错了。宁可给一句话。
     * @param {string} text
     */
    _showMapHint(text) {
        const el = document.getElementById('mapEmptyHint');
        if (!el) return;
        if (el.dataset.origHtml === undefined) el.dataset.origHtml = el.innerHTML;
        el.textContent = '⚠️ ' + text;
        el.style.color = 'var(--danger)';
        el.style.fontSize = '15px';
        el.style.maxWidth = '80%';
        el.style.display = 'block';
    },

    /**
     * 撤掉警示，还原成页面上原本的空态文案。
     * @param {boolean} [keepVisible] - true 时保留显示（用于「确实没有记录」的正常空态）
     */
    _clearMapHint(keepVisible) {
        const el = document.getElementById('mapEmptyHint');
        if (!el) return;
        // 先无条件还原文案：可能被 _showMapHint 换成过警示语，
        // 不还原的话「确实没有记录」的正常空态会一直显示上一条错误。
        if (el.dataset.origHtml !== undefined) {
            el.innerHTML = el.dataset.origHtml;
        }
        el.style.color = '';
        el.style.fontSize = '';
        el.style.maxWidth = '';
        el.style.display = keepVisible ? 'block' : 'none';
    }
};
