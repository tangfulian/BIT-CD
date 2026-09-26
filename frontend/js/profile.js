import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { Toast } from './toast.js';
import { I18n } from './i18n.js';
import { state } from './state.js';

export const Profile = {
    render: function () {
        var skeleton = document.getElementById('profileSkeleton');
        var content = document.getElementById('profileContent');
        if (skeleton) skeleton.classList.remove('hidden');
        if (content) content.classList.add('hidden');

        this._loadData().then(function (data) {
            if (skeleton) skeleton.classList.add('hidden');
            if (content) content.classList.remove('hidden');
            if (!data) return;
            _fillProfile(data);
        });
    },

    _loadData: async function () {
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/profile');
            if (!res.ok) return null;
            return await res.json();
        } catch (e) {
            return null;
        }
    },

    init: function () {
        var btn = document.getElementById('profChangePwdBtn');
        if (btn) {
            btn.onclick = function () { Profile._changePassword(); };
        }
    }
};

function _fillProfile(data) {
    var d = data.data || data;
    var nameEl = document.getElementById('profileUsername');
    var roleEl = document.getElementById('profileRole');
    var avatarEl = document.getElementById('profileAvatar');
    var createdEl = document.getElementById('profileCreatedAt');
    var detEl = document.getElementById('profDetections');
    var plotsEl = document.getElementById('profPlots');
    var avgEl = document.getElementById('profAvgRatio');
    var lastEl = document.getElementById('profLastActive');

    if (nameEl) nameEl.textContent = d.username || state.username || '--';
    if (roleEl) roleEl.textContent = (d.role === 'admin' ? I18n.t('usermgr.adminBadge') : I18n.t('auth.normalUser')) || '--';
    if (avatarEl) avatarEl.textContent = (d.username || 'U').charAt(0).toUpperCase();
    if (createdEl) createdEl.textContent = d.created_at || '--';
    if (detEl) detEl.textContent = d.detection_count || 0;
    if (plotsEl) plotsEl.textContent = d.plot_count || 0;
    if (avgEl) avgEl.textContent = (d.avg_ratio != null ? (d.avg_ratio * 100).toFixed(2) + '%' : '--');
    if (lastEl) lastEl.textContent = d.last_active || '--';
}

Profile._changePassword = async function () {
    var oldPwd = document.getElementById('profOldPwd');
    var newPwd = document.getElementById('profNewPwd');
    var msgEl = document.getElementById('profPwdMsg');
    var oldVal = oldPwd ? oldPwd.value.trim() : '';
    var newVal = newPwd ? newPwd.value.trim() : '';

    if (!oldVal || !newVal) {
        Toast.warning(I18n.t('profile.fillAllFields', '请填写所有密码字段'));
        return;
    }
    if (newVal.length < 8) {
        Toast.warning(I18n.t('auth.pwdTooShort', '新密码长度不能少于8位'));
        return;
    }

    try {
        var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/profile/change-password', {
            method: 'PUT',
            body: JSON.stringify({ old_password: oldVal, new_password: newVal })
        });
        var data = await res.json();
        if (res.ok) {
            Toast.success(data.msg || I18n.t('profile.pwdChanged', '密码修改成功'));
            if (oldPwd) oldPwd.value = '';
            if (newPwd) newPwd.value = '';
        } else {
            Toast.error(data.detail || I18n.t('profile.pwdChangeFailed', '密码修改失败'));
        }
    } catch (e) {
        Toast.error(I18n.t('profile.pwdChangeFailed', '密码修改失败'));
    }
};
