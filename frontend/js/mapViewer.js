import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { API } from './api.js';
import { I18n } from './i18n.js';

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

        let history;
        try {
            history = await API.fetchHistory();
        } catch (e) {
            console.error('加载地图数据失败:', e);
            history = [];
        }
        console.log('[MapViewer] 历史记录:', history.length, '条, 含坐标:', history.filter(function(i) { return !!i.lat_lng; }).length, '条');
        this.initMap(history);
    },

    initMap(history) {
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

        this.map = new AMap.Map("mapviewerMap", {
            zoom: 6,
            center: [126.63, 45.75],
            resizeEnable: true
        });

        if (geoItems.length === 0) {
            document.getElementById('heatmapToggleBtn').style.display = 'none';
            // 在无坐标记录时给出可见提示
            const msgEl = document.getElementById('mapEmptyHint');
            if (msgEl) msgEl.style.display = 'block';
            return;
        }
        const msgEl = document.getElementById('mapEmptyHint');
        if (msgEl) msgEl.style.display = 'none';

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
    }
};
