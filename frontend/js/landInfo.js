import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { API } from './api.js';
import { I18n } from './i18n.js';

function _escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

export const LandInfo = {
    fieldIds: [
        "t1_time", "t2_time", "province", "city", "lat_lng",
        "area", "land_type", "crop_type", "data_source", "change_type_define"
    ],

    init() {
        document.getElementById("saveLandInfo").onclick = () => this.save();
        this.fieldIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.onchange = () => this.autoSave();
        });
    },

    autoSave() {
        if (!state.currentUser) return;
        const data = this.getData();
        Utils.safeLocalStorage.setItem(CONFIG.LAND_INFO_KEY + state.currentUser, JSON.stringify(data));
    },

    async save() {
        if (!state.currentUser) return;
        const data = this.getData();
        Utils.safeLocalStorage.setItem(CONFIG.LAND_INFO_KEY + state.currentUser, JSON.stringify(data));
        await Modal.alert(I18n.t('land.infoSaved'));
    },

    load() {
        if (!state.currentUser) return;
        const saved = Utils.safeLocalStorage.getItem(CONFIG.LAND_INFO_KEY + state.currentUser);
        if (!saved) return;
        try {
            const data = JSON.parse(saved);
            this.fieldIds.forEach(id => {
                const el = document.getElementById(id);
                if (el && data[id] !== undefined) el.value = data[id];
            });
        } catch (e) {
            console.error("地块配置加载失败:", e);
        }
    },

    getData() {
        const data = {};
        this.fieldIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) data[id] = el.value;
        });
        if (!data.change_type_define) {
            data.change_type_define = "黑土层变薄退化";
        }
        return data;
    }
};

// ---- PlotManager: 多地块管理 ----
export const PlotManager = {
    _plots: [],
    _currentId: null,

    async init() {
        await this.loadPlots();
        this._bindUI();
    },

    async loadPlots() {
        try {
            this._plots = await API.fetchPlots();
        } catch {
            this._plots = [];
        }
        this._populateSelect();
    },

    _bindUI() {
        const select = document.getElementById('detectPlotSelect');
        if (select) {
            select.onchange = () => this.selectPlot(select.value);
        }
        const manageBtn = document.getElementById('managePlotBtn');
        if (manageBtn) {
            manageBtn.onclick = () => this._openManager();
        }

        // Manager modal buttons
        const plotNewBtn = document.getElementById('plotNewBtn');
        const plotModalCloseBtn = document.getElementById('plotModalCloseBtn');
        const plotSaveBtn = document.getElementById('plotSaveBtn');
        const plotCancelEditBtn = document.getElementById('plotCancelEditBtn');

        if (plotNewBtn) plotNewBtn.onclick = () => this._showEditForm(null);
        if (plotModalCloseBtn) plotModalCloseBtn.onclick = () => this._closeManager();
        if (plotSaveBtn) plotSaveBtn.onclick = () => this._savePlot();
        if (plotCancelEditBtn) plotCancelEditBtn.onclick = () => this._hideEditForm();
    },

    _populateSelect() {
        const select = document.getElementById('detectPlotSelect');
        if (!select) return;
        select.innerHTML = '<option value="">-- 手动填写 --</option>';
        if (!Array.isArray(this._plots)) return;
        this._plots.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            select.appendChild(opt);
        });
        if (this._currentId && this._plots.find(p => p.id === this._currentId)) {
            select.value = this._currentId;
        }
    },

    selectPlot(id) {
        this._currentId = id ? parseInt(id) : null;
        if (!this._currentId) return;
        const plot = this._plots.find(p => p.id === this._currentId);
        if (!plot) return;

        // Fill LandInfo form fields
        const mapping = {
            't1_time': plot.t1_time,
            't2_time': plot.t2_time,
            'province': plot.province,
            'city': plot.city,
            'lat_lng': plot.lat_lng,
            'area': plot.area,
            'land_type': plot.land_type,
            'crop_type': plot.crop_type,
            'data_source': plot.data_source,
            'change_type_define': plot.change_type,
        };
        Object.entries(mapping).forEach(([id, val]) => {
            const el = document.getElementById(id);
            if (el && val !== undefined && val !== null) el.value = val;
        });
        LandInfo.autoSave();
    },

    _openManager() {
        this._hideEditForm();
        this._renderPlotList();
        const modal = document.getElementById('plotManagerModal');
        if (modal) modal.classList.remove('hidden');
    },

    _closeManager() {
        const modal = document.getElementById('plotManagerModal');
        if (modal) modal.classList.add('hidden');
    },

    _renderPlotList() {
        const container = document.getElementById('plotListContainer');
        if (!container) return;
        if (this._plots.length === 0) {
            container.innerHTML = `<p style="text-align:center;color:var(--text-secondary);padding:24px;" data-i18n="plot.noPlot">无已保存地块</p>`;
            return;
        }
        container.innerHTML = this._plots.map(p => `
            <div class="plot-list-item">
                <div class="plot-list-info">
                    <span class="plot-list-name">${_escapeHtml(p.name)}</span>
                    <span class="plot-list-detail">${p.province || ''} ${p.city || ''} · ${p.area || 0} 亩 · ${p.change_type || ''}</span>
                </div>
                <div class="plot-list-actions">
                    <button class="btn-small-action plot-edit-btn" data-id="${p.id}">${I18n.t('common.edit', '编辑')}</button>
                    <button class="btn-small-danger plot-delete-btn" data-id="${p.id}">${I18n.t('common.delete')}</button>
                </div>
            </div>
        `).join('');

        container.querySelectorAll('.plot-edit-btn').forEach(btn => {
            btn.onclick = () => {
                const id = parseInt(btn.dataset.id);
                const plot = this._plots.find(p => p.id === id);
                if (plot) this._showEditForm(plot);
            };
        });
        container.querySelectorAll('.plot-delete-btn').forEach(btn => {
            btn.onclick = async () => {
                const id = parseInt(btn.dataset.id);
                const confirmed = await Modal.confirm(I18n.t('plot.confirmDelete'));
                if (!confirmed) return;
                try {
                    await API.deletePlot(id);
                    Utils.showToast(I18n.t('plot.deleted'), 'success');
                    await this.loadPlots();
                    if (this._currentId === id) {
                        this._currentId = null;
                        const select = document.getElementById('detectPlotSelect');
                        if (select) select.value = '';
                    }
                    this._renderPlotList();
                } catch {
                    Utils.showToast(I18n.t('common.error'), 'error');
                }
            };
        });
    },

    _showEditForm(plot) {
        const container = document.getElementById('plotListContainer');
        const form = document.getElementById('plotEditForm');
        const title = document.getElementById('plotModalTitle');
        const newBtn = document.getElementById('plotNewBtn');

        if (container) container.classList.add('hidden');
        if (form) {
            form.classList.remove('hidden');
            form.dataset.editId = plot ? plot.id : '';
        }
        if (title) title.textContent = plot ? I18n.t('plot.editPlot') : I18n.t('plot.createPlot');
        if (newBtn) newBtn.style.display = 'none';

        document.getElementById('plotEditName').value = plot ? plot.name : '';
        document.getElementById('plotEditProvince').value = plot ? plot.province : '黑龙江省';
        document.getElementById('plotEditCity').value = plot ? plot.city : '';
        document.getElementById('plotEditLatLng').value = plot ? plot.lat_lng : '';
        document.getElementById('plotEditArea').value = plot ? plot.area : '';
        document.getElementById('plotEditLandType').value = plot ? plot.land_type : '';
        document.getElementById('plotEditCropType').value = plot ? plot.crop_type : '';
        document.getElementById('plotEditDataSource').value = plot ? plot.data_source : '';
        document.getElementById('plotEditChangeType').value = plot ? plot.change_type : '黑土层变薄退化';
        document.getElementById('plotEditT1Time').value = plot ? plot.t1_time : '';
        document.getElementById('plotEditT2Time').value = plot ? plot.t2_time : '';
    },

    _hideEditForm() {
        const container = document.getElementById('plotListContainer');
        const form = document.getElementById('plotEditForm');
        const title = document.getElementById('plotModalTitle');
        const newBtn = document.getElementById('plotNewBtn');

        if (container) container.classList.remove('hidden');
        if (form) form.classList.add('hidden');
        if (title) title.textContent = I18n.t('plot.managePlots');
        if (newBtn) newBtn.style.display = '';
    },

    async _savePlot() {
        const editId = document.getElementById('plotEditForm').dataset.editId;
        const data = {
            name: document.getElementById('plotEditName').value.trim(),
            province: document.getElementById('plotEditProvince').value,
            city: document.getElementById('plotEditCity').value,
            lat_lng: document.getElementById('plotEditLatLng').value,
            area: parseFloat(document.getElementById('plotEditArea').value) || 0,
            land_type: document.getElementById('plotEditLandType').value,
            crop_type: document.getElementById('plotEditCropType').value,
            data_source: document.getElementById('plotEditDataSource').value,
            change_type: document.getElementById('plotEditChangeType').value,
            t1_time: document.getElementById('plotEditT1Time').value,
            t2_time: document.getElementById('plotEditT2Time').value,
        };
        if (!data.name) {
            Utils.showToast(I18n.t('common.required'), 'error');
            return;
        }
        try {
            if (editId) {
                await API.updatePlot(parseInt(editId), data);
                Utils.showToast(I18n.t('plot.updated'), 'success');
            } else {
                await API.createPlot(data);
                Utils.showToast(I18n.t('plot.created'), 'success');
            }
            await this.loadPlots();
            this._renderPlotList();
            this._hideEditForm();
        } catch {
            Utils.showToast(I18n.t('plot.saveFailed'), 'error');
        }
    }
};
