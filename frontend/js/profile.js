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
            if (!data) {
                // 此前是直接 return：骨架消失，页面留着占位符，用户以为数据就是这样。
                // 失败必须说出来。
                Toast.warning(I18n.t('profile.loadFailed', '个人资料加载失败，请刷新重试'));
                return;
            }
            _fillProfile(data);
        });
    },

    _loadData: async function () {
        try {
            var res = await Utils.authFetch(CONFIG.API_BASE_URL + '/profile');
            if (!res.ok) {
                console.warn('[profile] /profile 返回', res.status);
                return null;
            }
            return await res.json();
        } catch (e) {
            console.warn('[profile] /profile 请求失败', e);
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
    // 用 != null 判断而不是 || 0：字段缺失时渲染 0 会谎报成「这个账号一次检测都没有」，
    // 而真实原因可能是接口失败。缺值一律显示占位符。
    if (detEl) detEl.textContent = d.detection_count != null ? d.detection_count : '--';
    if (plotsEl) plotsEl.textContent = d.plot_count != null ? d.plot_count : '--';
    // 不要再乘 100：后端存进 detections.ratio 的**已经是百分数**
    // （detect_service.py:212 `change_pixel / total_pixel * 100`），
    // auth.py:94 返回的是这些百分数的均值。这里再乘一次会放大 100 倍
    // （实测显示成 1372.00%，而同一条记录在历史页是 21.9%）。
    // 全站只有这一处多乘，history.js / compare.js 都是直接 `ratio + '%'`。
    if (avgEl) avgEl.textContent = (d.avg_ratio != null ? d.avg_ratio.toFixed(2) + '%' : '--');
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
