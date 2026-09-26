import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { Toast } from './toast.js';
import { API } from './api.js';
import { Annotator } from './annotator.js';
import { CompareSlider } from './compareSlider.js';
import { I18n } from './i18n.js';
import { Auth } from './auth.js';

var PAGE_SIZE = 20;

export var History = {
    currentFilters: { keyword: '', type: 'all', model: 'all' },
    historyCache: [],
    _currentPage: 1,
    _totalCount: 0,

    init: function () {
        document.getElementById("historyFilterBtn").onclick = function () { History.applyFilters(); };
        document.getElementById("historyResetFilter").onclick = function () { History.resetFilters(); };
        var searchInput = document.getElementById("historySearch");
        if (searchInput) {
            searchInput.oninput = function () { History.applyFilters(); };
            searchInput.onkeyup = function (e) {
                if (e.key === 'Enter') History.applyFilters();
            };
        }
    },

    load: async function () {
        // 游客没有 token，跳过 API 请求
        if (Auth.isGuest()) return;
        try {
            // 拉取全部数据，客户端分页+筛选
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/history?limit=5000');
            if (!res.ok) return;
            var json = await res.json();
            if (json.code === 200) {
                this.historyCache = json.data || [];
                this.updateModelOptions();
                this.updateTypeOptions();
                this.renderList();
            }
        } catch (e) {
            Toast.error(I18n.t('history.requestFailed'));
        }
    },

    deleteOne: async function (id) {
        var confirmed = await Modal.confirm(I18n.t('history.confirmDeleteOne'));
        if (!confirmed) return;
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/history/' + id, { method: 'DELETE' });
            var data = await res.json();
            if (data.code === 200) {
                Toast.success(I18n.t('history.deleted'));
                this.load();
            } else {
                Toast.error(data.detail || I18n.t('history.deleteFailed'));
            }
        } catch (e) {
            Toast.error(I18n.t('history.requestFailed'));
        }
    },

    clearAll: async function () {
        var confirmed = await Modal.confirm(I18n.t('history.confirmClearAll'));
        if (!confirmed) return;
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/history', { method: 'DELETE' });
            var data = await res.json();
            if (data.code === 200) {
                this._currentPage = 1;
                this.load();
            } else {
                Toast.error(I18n.t('history.clearFailed'));
            }
        } catch (e) {
            Toast.error(I18n.t('history.requestFailed'));
        }
    },

    applyFilters: function () {
        var keyword = document.getElementById("historySearch").value.trim().toLowerCase();
        var type = document.getElementById("historyTypeFilter").value;
        var model = document.getElementById("historyModelFilter").value;
        this.currentFilters = { keyword: keyword, type: type, model: model };
        this._currentPage = 1;
        this.load();
    },

    resetFilters: function () {
        document.getElementById("historySearch").value = '';
        document.getElementById("historyTypeFilter").value = 'all';
        document.getElementById("historyModelFilter").value = 'all';
        this.currentFilters = { keyword: '', type: 'all', model: 'all' };
        this._currentPage = 1;
        this.load();
    },

    updateModelOptions: function () {
        var select = document.getElementById("historyModelFilter");
        if (!select) return;
        var models = new Set();
        this.historyCache.forEach(function (item) {
            if (item.model) models.add(item.model);
        });
        select.innerHTML = '<option value="all">' + I18n.t('history.allModels') + '</option>';
        models.forEach(function (m) {
            var opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            select.appendChild(opt);
        });
    },

    updateTypeOptions: function () {
        var select = document.getElementById("historyTypeFilter");
        if (!select) return;
        var types = new Set();
        this.historyCache.forEach(function (item) {
            if (item.change_type) types.add(item.change_type);
        });
        select.innerHTML = '<option value="all">' + I18n.t('history.allTypes') + '</option>';
        types.forEach(function (t) {
            var opt = document.createElement('option');
            opt.value = t;
            opt.textContent = t;
            select.appendChild(opt);
        });
    },

    _getFilteredList: function (list) {
        var _this = this;
        var kw = this.currentFilters.keyword;
        var type = this.currentFilters.type;
        var model = this.currentFilters.model;
        return list.filter(function (item) {
            if (kw) {
                var searchStr = (item.model || '') + ' ' + (item.ratio || '') + ' ' + (item.location || '') + ' ' + (item.time || '') + ' ' + (item.change_type || '');
                if (searchStr.toLowerCase().indexOf(kw) === -1) return false;
            }
            if (type !== 'all' && item.change_type !== type) return false;
            if (model !== 'all' && item.model !== model) return false;
            return true;
        });
    },

    renderList: function () {
        var allFiltered = this._getFilteredList(this.historyCache);
        this._totalCount = allFiltered.length;

        // 客户端分页
        var start = (this._currentPage - 1) * PAGE_SIZE;
        var filtered = allFiltered.slice(start, start + PAGE_SIZE);

        var dom = document.getElementById("historyList");
        var skeleton = document.getElementById("historySkeleton");
        var empty = document.getElementById("historyEmpty");

        if (skeleton) skeleton.classList.add('hidden');
        dom.querySelectorAll('.history-item').forEach(function (el) { el.remove(); });

        if (filtered.length === 0) {
            if (empty) empty.classList.remove('hidden');
            document.getElementById("historyPagination").innerHTML = '';
            return;
        }

        if (empty) empty.classList.add('hidden');
        var t = function (k) { return I18n.t(k); };

        filtered.forEach(function (item, idx) {
            var globalIdx = start + idx;
            var div = document.createElement("div");
            div.className = 'history-item';
            div.style.cssText = "padding:14px 16px;background:var(--bg-main);border-radius:var(--radius-md);margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;transition:background var(--duration-fast);";
            var displayModel = Utils.escapeHtml(item.model) || t('unknown');
            var displayRatio = item.ratio != null ? item.ratio + '%' : t('notFilled');
            var displayTime = item.time || "";
            var displayLocation = item.location ? ' · ' + Utils.escapeHtml(item.location) : "";
            var aiTag = item.ai_change_type ? ' <span class="ai-tag-inline">AI</span>' : '';
            div.innerHTML =
                '<div style="display:flex;flex-direction:column;gap:4px;overflow:hidden;min-width:0;flex:1;">' +
                    '<span style="font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + displayModel + aiTag + ' · ' + t('detect.changeRatio') + ' ' + displayRatio + displayLocation + '</span>' +
                    '<span style="font-size:13px;color:var(--text-secondary);">' + displayTime + '</span>' +
                '</div>' +
                '<div style="display:flex;gap:10px;flex-shrink:0;">' +
                    '<button class="btn-view" data-idx="' + globalIdx + '">' + t('common.view') + '</button>' +
                    '<button class="btn-small-danger btn-delete" data-id="' + item.id + '">' + t('common.delete') + '</button>' +
                '</div>';
            dom.appendChild(div);
        });

        dom.querySelectorAll('.btn-view').forEach(function (btn) {
            btn.onclick = function () {
                var fl = History._getFilteredList(History.historyCache);
                var idx = parseInt(btn.dataset.idx);
                History.showDetail(fl[idx]);
            };
        });
        dom.querySelectorAll('.btn-delete').forEach(function (btn) {
            btn.onclick = function () { History.deleteOne(parseInt(btn.dataset.id)); };
        });

        this._renderPagination();
    },

    _renderPagination: function () {
        var totalPages = Math.ceil(this._totalCount / PAGE_SIZE);
        var container = document.getElementById("historyPagination");
        if (!container) return;
        if (totalPages <= 1) { container.innerHTML = ''; return; }

        var html = '';
        var cp = this._currentPage;

        html += '<button class="pagination-btn" ' + (cp <= 1 ? 'disabled' : '') + ' data-page="' + (cp - 1) + '">‹</button>';

        var start = Math.max(1, cp - 2);
        var end = Math.min(totalPages, cp + 2);
        if (start > 1) html += '<button class="pagination-btn" data-page="1">1</button>';
        if (start > 2) html += '<span class="pagination-btn" style="cursor:default;border:none;">...</span>';
        for (var i = start; i <= end; i++) {
            html += '<button class="pagination-btn' + (i === cp ? ' active' : '') + '" data-page="' + i + '">' + i + '</button>';
        }
        if (end < totalPages - 1) html += '<span class="pagination-btn" style="cursor:default;border:none;">...</span>';
        if (end < totalPages) html += '<button class="pagination-btn" data-page="' + totalPages + '">' + totalPages + '</button>';

        html += '<button class="pagination-btn" ' + (cp >= totalPages ? 'disabled' : '') + ' data-page="' + (cp + 1) + '">›</button>';
        html += '<span class="pagination-info">共 ' + this._totalCount + ' 条</span>';

        container.innerHTML = html;

        var self = this;
        container.querySelectorAll('.pagination-btn[data-page]').forEach(function (btn) {
            btn.onclick = function () {
                var p = parseInt(this.dataset.page);
                if (p === self._currentPage) return;
                self._currentPage = p;
                self.renderList();
            };
        });
    },

    showDetail: async function (item) {
        if (!item) return;

        var annotatedMask = null;
        if (item.id) {
            try {
                var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/annotation/' + item.id);
                if (res.ok) {
                    var data = await res.json();
                    if (data.code === 200 && data.data && data.data.annotation_data) {
                        annotatedMask = data.data.annotation_data;
                    }
                }
            } catch (e) {}
        }
        var maskSrc = annotatedMask || item.mask;
        var t = function (k) { return I18n.t(k); };

        var innerHTML = '';
        innerHTML += '<div class="modal-box detail-modal-box">';
        innerHTML += '<div class="modal-title detail-modal-title"><span>' + t('history.detail') + ' #' + (item.id || '-') + '</span><span class="detail-time-label">' + (item.time || '') + '</span></div>';
        innerHTML += '<div class="modal-content">';
        innerHTML += '<div class="detail-info-grid">';
        innerHTML += '<div class="detail-info-item"><span class="detail-label">' + t('history.detailModel') + '</span><span class="detail-value">' + Utils.escapeHtml(item.model || '-') + '</span></div>';
        innerHTML += '<div class="detail-info-item"><span class="detail-label">' + t('history.detailRatio') + '</span><span class="detail-value highlight">' + (item.ratio != null ? item.ratio + '%' : '-') + '</span></div>';
        innerHTML += '<div class="detail-info-item"><span class="detail-label">' + t('history.detailChangePixel') + '</span><span class="detail-value">' + (item.change_pixel != null ? item.change_pixel : '-') + '</span></div>';
        innerHTML += '<div class="detail-info-item"><span class="detail-label">' + t('history.detailThreshold') + '</span><span class="detail-value">' + (item.threshold != null ? item.threshold : '-') + '</span></div>';
        innerHTML += '<div class="detail-info-item"><span class="detail-label">' + t('history.detailChangeType') + '</span><span class="detail-value">' + Utils.escapeHtml(item.change_type || '-') + '</span></div>';
        if (item.ai_change_type) {
            innerHTML += '<div class="detail-info-item"><span class="detail-label">' + t('classify.aiSuggestion') + '</span><span class="detail-value"><span class="ai-badge-inline">' + item.ai_change_type + '</span> <span class="ai-confidence-inline">(' + (item.ai_confidence * 100).toFixed(0) + '%)</span></span></div>';
        }
        innerHTML += '<div class="detail-info-item"><span class="detail-label">' + t('history.detailLocation') + '</span><span class="detail-value">' + Utils.escapeHtml(item.location || '-') + '</span></div>';
        innerHTML += '</div>';
        innerHTML += '<div class="detail-images-grid">';
        if (maskSrc) innerHTML += '<div class="detail-image-card"><h4>' + t('history.detailMask') + '</h4><img src="' + maskSrc + '" crossorigin="anonymous"></div>';
        if (item.heat) innerHTML += '<div class="detail-image-card"><h4>' + t('history.detailHeat') + '</h4><img src="' + item.heat + '" crossorigin="anonymous"></div>';
        if (item.fusion) innerHTML += '<div class="detail-image-card full-width"><h4>' + t('history.detailFusion') + '</h4><img src="' + item.fusion + '" crossorigin="anonymous"></div>';
        innerHTML += '</div></div>';
        innerHTML += '<div class="modal-footer detail-modal-footer">';
        innerHTML += '<div>';
        if (item.id) innerHTML += '<button class="btn-modal btn-modal-primary" id="detailAnnotateBtn">' + t('detect.annotate') + '</button>';
        if (item.mask && item.heat) innerHTML += '<button class="btn-modal btn-modal-primary" id="detailCompareBtn">' + t('common.compare') + '</button>';
        innerHTML += '</div>';
        innerHTML += '<div><button class="btn-modal btn-modal-secondary" id="modalCloseBtn">' + t('common.close') + '</button></div>';
        innerHTML += '</div></div>';

        var result = Modal.createOverlay(innerHTML, {
            '#detailAnnotateBtn': function () { if (item.id && maskSrc) Annotator.open(item.id, maskSrc); },
            '#detailCompareBtn': function () { CompareSlider.show(maskSrc, item.heat, I18n.t('slider.maskVsHeat')); }
        });
    }
};
