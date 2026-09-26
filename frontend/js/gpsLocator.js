import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { LandInfo } from './landInfo.js';
import { Modal } from './modal.js';
import { I18n } from './i18n.js';

export const GPSLocator = {
    mouseTool: null,
    drawnPolygon: null,

    init() {
        document.getElementById("getGPSBtn").onclick = () => this.getCurrentLocation();
        document.getElementById("drawAreaBtn").onclick = () => this.startDrawing();
        document.getElementById("clearDrawBtn").onclick = () => this.clearDrawing();
    },

    async getCurrentLocation() {
        const btn = document.getElementById("getGPSBtn");
        const status = document.getElementById("gpsStatus");
        btn.disabled = true;
        btn.textContent = I18n.t('gps.acquiring');
        status.textContent = I18n.t('gps.requesting');
        status.style.color = "var(--text-secondary)";

        // 三层定位策略：后端IP定位 → 高德SDK → 浏览器GPS
        const locateByBackendIP = async () => {
            const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/amap/ip-locate`);
            if (!res.ok) throw new Error('ip-locate-failed');
            const json = await res.json();
            if (!json.data || !json.data.longitude || !json.data.latitude) {
                throw new Error('ip-no-result');
            }
            return { lng: json.data.longitude, lat: json.data.latitude };
        };

        const locateByAMap = () => new Promise((resolve, reject) => {
            if (!window.AMap) { reject(new Error('amap-not-loaded')); return; }
            AMap.plugin('AMap.Geolocation', () => {
                const geo = new AMap.Geolocation({ enableHighAccuracy: true, timeout: 8000 });
                geo.getCurrentPosition((geoStatus, result) => {
                    if (geoStatus === 'complete' && result && result.position) {
                        resolve({ lng: result.position.lng, lat: result.position.lat });
                    } else {
                        reject(new Error(result ? (result.message || 'geo-failed') : 'geo-failed'));
                    }
                });
            });
        });

        const locateByBrowser = () => new Promise((resolve, reject) => {
            if (!navigator.geolocation) { reject(new Error('unsupported')); return; }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({ lng: pos.coords.longitude, lat: pos.coords.latitude }),
                (err) => reject(err),
                { enableHighAccuracy: true, timeout: 8000 }
            );
        });

        try {
            const pos = await locateByBackendIP();
            await this._onLocationSuccess(pos.lng, pos.lat, btn, status);
        } catch (e1) {
            try {
                const pos = await locateByAMap();
                await this._onLocationSuccess(pos.lng, pos.lat, btn, status);
            } catch (e2) {
                try {
                    const pos = await locateByBrowser();
                    await this._onLocationSuccess(pos.lng, pos.lat, btn, status);
                } catch (e3) {
                    status.textContent = I18n.t('gps.failed');
                    status.style.color = 'var(--accent)';
                    await Modal.alert(I18n.t('gps.failed'));
                    btn.disabled = false;
                    btn.textContent = I18n.t('gps.getLocation');
                }
            }
        }
    },

    async _onLocationSuccess(lng, lat, btn, status) {
        status.textContent = `✅ ${I18n.t('gps.resolving')}`;
        status.style.color = "var(--secondary)";
        try {
            const addr = await this._fetchAddress(lng, lat);
            this._fillAddress(addr);
            document.getElementById("lat_lng").value = `东经${lng.toFixed(4)}°，北纬${lat.toFixed(4)}°`;
            LandInfo.autoSave();
            this._updateMap(lng, lat);
            status.textContent = `${I18n.t('gps.addressOk')}${addr.formatted_address}`;
        } catch (e) {
            status.textContent = `${I18n.t('gps.addressFail')}${e.message}`;
            status.style.color = "var(--accent)";
            document.getElementById("lat_lng").value = `东经${lng.toFixed(4)}°，北纬${lat.toFixed(4)}°`;
            this._updateMap(lng, lat);
        } finally {
            btn.disabled = false;
            btn.textContent = I18n.t('gps.redo');
        }
    },

    async _fetchAddress(lng, lat) {
        const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/amap/regeo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ longitude: lng, latitude: lat })
        });
        if (!res.ok) throw new Error((await res.json()).detail || "地址解析服务异常");
        const data = await res.json();
        if (data.code !== 200) throw new Error("地址解析失败");
        return data.data;
    },

    _fillAddress(addr) {
        if (addr.province) {
            const sel = document.getElementById("province");
            const short = addr.province.replace('省','').replace('自治区','');
            for (let i = 0; i < sel.options.length; i++) {
                if (sel.options[i].value.includes(short)) {
                    sel.selectedIndex = i;
                    break;
                }
            }
        }
        document.getElementById("city").value = addr.city || addr.district || "";
    },

    _mapClickEnabled: false,

    _updateMap(lng, lat) {
        if (!state.map) {
            state.map = new AMap.Map("mapContainer", {
                zoom: 16,
                center: [lng, lat],
                resizeEnable: true
            });
        } else {
            state.map.setCenter([lng, lat]);
        }
        if (state.marker) state.marker.setMap(null);
        state.marker = new AMap.Marker({
            position: [lng, lat],
            title: "检测地块位置 (点击地图可移动)",
            draggable: true,
            icon: new AMap.Icon({
                size: new AMap.Size(32, 32),
                image: "https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png",
                imageSize: new AMap.Size(32, 32)
            })
        });
        state.marker.setMap(state.map);
        state.map.setFitView([state.marker]);

        // 拖拽标记更新地址
        state.marker.on('dragend', async (e) => {
            const pos = e.target.getPosition();
            await this._onMapClick(pos.lng, pos.lat);
        });

        // 点击地图移动标记并更新地址
        if (!this._mapClickEnabled) {
            this._mapClickEnabled = true;
            state.map.on('click', async (e) => {
                state.marker.setPosition(e.lnglat);
                state.map.setCenter(e.lnglat);
                await this._onMapClick(e.lnglat.lng, e.lnglat.lat);
            });
        }
    },

    async _onMapClick(lng, lat) {
        const status = document.getElementById("gpsStatus");
        try {
            const addr = await this._fetchAddress(lng, lat);
            this._fillAddress(addr);
            document.getElementById("lat_lng").value = `东经${lng.toFixed(4)}°，北纬${lat.toFixed(4)}°`;
            LandInfo.autoSave();
            status.textContent = `✅ 已定位：${addr.formatted_address}`;
            status.style.color = "var(--secondary)";
        } catch (e) {
            document.getElementById("lat_lng").value = `东经${lng.toFixed(4)}°，北纬${lat.toFixed(4)}°`;
        }
    },

    startDrawing() {
        if (!state.map) {
            Modal.alert(I18n.t('gps.initMapFirst'));
            return;
        }
        // 关闭之前的绘制工具
        if (this.mouseTool) this.mouseTool.close();

        // 确保 MouseTool 插件已加载（高德2.0需要动态加载）
        const doDraw = () => {
            this.mouseTool = new AMap.MouseTool(state.map);
            this.mouseTool.polygon();
            document.getElementById("drawAreaBtn").style.display = 'none';
            document.getElementById("clearDrawBtn").style.display = 'inline-block';
            document.getElementById("gpsStatus").textContent = I18n.t('gps.drawHint');
            document.getElementById("gpsStatus").style.color = "var(--text-secondary)";

            this.mouseTool.on('draw', (e) => {
                this.drawnPolygon = e.obj;
                const area = AMap.GeometryUtil.ringArea(e.obj.getPath()).toFixed(2);
                document.getElementById("area").value = area;
                document.getElementById("lat_lng").value = `绘制地块面积: ${area} 平方米`;
                LandInfo.autoSave();
                document.getElementById("gpsStatus").textContent = `✅ 地块范围已绘制，面积约 ${area} 平方米`;
                document.getElementById("gpsStatus").style.color = "var(--secondary)";
                this.mouseTool.close(false);
                document.getElementById("drawAreaBtn").style.display = 'inline-block';
                document.getElementById("clearDrawBtn").style.display = 'inline-block';
            });
        };

        if (window.AMap && !AMap.MouseTool) {
            AMap.plugin('AMap.MouseTool', () => doDraw());
        } else {
            doDraw();
        }
    },

    clearDrawing() {
        if (this.drawnPolygon) {
            state.map.remove(this.drawnPolygon);
            this.drawnPolygon = null;
        }
        document.getElementById("drawAreaBtn").style.display = 'inline-block';
        document.getElementById("clearDrawBtn").style.display = 'none';
        document.getElementById("area").value = '';
        document.getElementById("lat_lng").value = '';
        document.getElementById("gpsStatus").textContent = I18n.t('gps.cleared');
        document.getElementById("gpsStatus").style.color = "var(--text-secondary)";
        LandInfo.autoSave();
    }
};