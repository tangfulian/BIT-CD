import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { API } from './api.js';
import { I18n } from './i18n.js';
import { Toast } from './toast.js';

/**
 * 底图因高德鉴权失败而画不出来时的提示语。
 * AMap 自身不报错、map 的 complete 事件照样触发，画布只是整块空白；
 * 这个标志位由 index.html 里的 console 探针捕获 INVALID_USER_DOMAIN 后置位。
 */
const AUTH_MSG = '底图加载失败：高德 Key 未授权当前域名，标记仍可查看';

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

    init() {
        const toggleBtn = document.getElementById('heatmapToggleBtn');
        if (toggleBtn) {
            toggleBtn.onclick = () => this.toggleHeatmap();
        }
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

        // AMap 脚本可能整个没加载出来（未配 Key、CDN 不可达）
        if (typeof AMap === 'undefined') {
            console.warn('[MapViewer] AMap 未加载');
            this._showMapHint('地图组件未加载（未配置高德 Key 或网络不可达）');
            return;
        }

        try {
            this.map = new AMap.Map("mapviewerMap", {
                zoom: 6,
                center: [126.63, 45.75],
                resizeEnable: true
            });
        } catch (e) {
            console.error('[MapViewer] 地图初始化失败', e);
            this._showMapHint('底图加载失败，请检查高德 Key 的域名白名单是否包含当前域名');
            return;
        }

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
        this._heatmapData = [];
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

        if (this.markers.length > 0) this.map.setFitView(this.markers);

        // 异步加载热力图插件
        if (!this.heatmap) {
            AMap.plugin('AMap.HeatMap', () => {
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
