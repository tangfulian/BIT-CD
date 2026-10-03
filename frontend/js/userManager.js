import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { Toast } from './toast.js';
import { I18n } from './i18n.js';

var PAGE_SIZE = 20;

export var UserManager = {
    _currentPage: 1,
    _totalCount: 0,
    _users: [],

    init: function () {
        var refreshBtn = document.getElementById("umRefreshBtn");
        if (refreshBtn) refreshBtn.onclick = function () { UserManager.loadUsers(); };
    },

    render: async function () {
        var page = document.getElementById('page-usermgr');
        if (!page || !page.classList.contains('active')) return;
        if (state.currentUserRole !== 'admin') {
            document.getElementById('umTableBody').innerHTML =
                '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--danger);">' + I18n.t('auth.insufficientPermission', '需要管理员权限') + '</td></tr>';
            return;
        }
        await this.loadUsers();
    },

    loadUsers: async function () {
        var tbody = document.getElementById('umTableBody');
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;">' + I18n.t('common.loading', '加载中...') + '</td></tr>';
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/admin/users?page=' + this._currentPage + '&limit=' + PAGE_SIZE);
            var data;
            try { data = await res.json(); } catch (e) { throw new Error('响应格式错误'); }
            if (data.code !== 200) throw new Error(data.detail || I18n.t('history.requestFailed', '获取失败'));
            this._users = data.data || [];
            this._totalCount = data.total || 0;
            this.renderTable();
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--danger);">加载失败：' + e.message + '</td></tr>';
        }
    },

    renderTable: function () {
        var tbody = document.getElementById('umTableBody');
        var users = this._users;
        if (!users.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:60px 40px;">' +
                '<div class="empty-state" style="padding:0;">' +
                '<div class="empty-state-icon"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>' +
                '<div class="empty-state-title">' + I18n.t('usermgr.noUsers') + '</div>' +
                '<div class="empty-state-desc">' + I18n.t('usermgr.noUsersDesc') + '</div>' +
                '</div></td></tr>';
            document.getElementById("umPagination").innerHTML = '';
            return;
        }
        tbody.innerHTML = users.map(function (u) {
            var disabledStyle = u.disabled ? 'style="opacity:0.5;"' : '';
            var adminTag = u.role === 'admin' ? ' <span style="color:var(--primary);font-size:12px;">(' + I18n.t('usermgr.adminBadge', '管理员') + ')</span>' : '';
            var toggleText = u.disabled ? I18n.t('usermgr.enable') : I18n.t('usermgr.disable');
            return '<tr ' + disabledStyle + '>' +
                '<td>' + u.id + '</td>' +
                '<td><strong>' + u.username + '</strong>' + adminTag + '</td>' +
                '<td>' + u.role + '</td>' +
                '<td>' + u.detection_count + ' ' + I18n.t('status.countUnit', '次') + '</td>' +
                '<td>' + u.created_at + '</td>' +
                '<td>' +
                    '<button class="btn-small-action toggle-btn" data-id="' + u.id + '" data-disabled="' + u.disabled + '">' + toggleText + '</button>' +
                    '<button class="btn-small-action reset-btn" data-id="' + u.id + '">' + I18n.t('usermgr.resetPwd') + '</button>' +
                    '<button class="btn-small-danger del-btn" data-id="' + u.id + '">' + I18n.t('common.delete') + '</button>' +
                '</td></tr>';
        }).join('');

        tbody.querySelectorAll('.toggle-btn').forEach(function (btn) {
            btn.onclick = function () { UserManager.toggleUser(parseInt(btn.dataset.id)); };
        });
        tbody.querySelectorAll('.reset-btn').forEach(function (btn) {
            btn.onclick = function () { UserManager.resetPassword(parseInt(btn.dataset.id)); };
        });
        tbody.querySelectorAll('.del-btn').forEach(function (btn) {
            btn.onclick = function () { UserManager.deleteUser(parseInt(btn.dataset.id)); };
        });

        this._renderPagination();
    },

    _renderPagination: function () {
        var totalPages = Math.ceil(this._totalCount / PAGE_SIZE);
        var container = document.getElementById("umPagination");
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
        html += '<span class="pagination-info">共 ' + this._totalCount + ' 人</span>';

        container.innerHTML = html;

        var self = this;
        container.querySelectorAll('.pagination-btn[data-page]').forEach(function (btn) {
            btn.onclick = function () {
                var p = parseInt(this.dataset.page);
                if (p === self._currentPage) return;
                self._currentPage = p;
                self.loadUsers();
            };
        });
    },

    toggleUser: async function (userId) {
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/admin/users/' + userId + '/toggle-status', { method: 'PUT' });
            var data;
            try { data = await res.json(); } catch (e) { throw new Error('响应格式错误'); }
            if (data.code === 200) {
                Toast.success(data.msg || I18n.t('common.success'));
                this.loadUsers();
            } else {
                Toast.error(data.detail || I18n.t('common.error'));
            }
        } catch (e) {
            Toast.error(e.message || I18n.t('history.requestFailed'));
        }
    },

    resetPassword: async function (userId) {
        var ok = await Modal.confirm(I18n.t('usermgr.confirmResetPwd'));
        if (!ok) return;
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/admin/users/' + userId + '/password', { method: 'PUT' });
            var data;
            try { data = await res.json(); } catch (e) { throw new Error('响应格式错误'); }
            if (data.code === 200) {
                Toast.success(data.msg || I18n.t('common.success'));
            } else {
                Toast.error(data.detail || I18n.t('common.error'));
            }
        } catch (e) {
            Toast.error(e.message || I18n.t('history.requestFailed'));
        }
    },

    deleteUser: async function (userId) {
        var ok = await Modal.confirm(I18n.t('usermgr.confirmDelete'));
        if (!ok) return;
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/admin/users/' + userId, { method: 'DELETE' });
            var data;
            try { data = await res.json(); } catch (e) { throw new Error('响应格式错误'); }
            if (data.code === 200) {
                Toast.success(data.msg || I18n.t('common.success'));
                this.loadUsers();
            } else {
                Toast.error(data.detail || I18n.t('common.error'));
            }
        } catch (e) {
            Toast.error(e.message || I18n.t('history.requestFailed'));
        }
    }
};
