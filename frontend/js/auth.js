import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { LandInfo, PlotManager } from './landInfo.js';
import { I18n } from './i18n.js';
import { History } from './history.js';

function _isTokenExpired(token) {
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.exp * 1000 < Date.now();
    } catch {
        return true;
    }
}

export const Auth = {
    _captchaId: null,
    _isGuest: null, // null=uninitialized, true=guest, false=logged-in

    init() {
        const token = Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY);
        const savedUser = Utils.safeLocalStorage.getItem(CONFIG.LOGIN_KEY);
        if (token && savedUser && !_isTokenExpired(token)) {
            this._isGuest = false;
            state.currentUserRole = Utils.safeLocalStorage.getItem(CONFIG.LOGIN_KEY + '_role') || 'user';
            this.enterSystem(savedUser);
            // 本地只校验了 exp，但服务端数据重置、用户被删除、JWT 密钥轮换都会让
            // token 实际失效 —— 那种情况下界面显示"已登录"、各接口却全 401，
            // 表现为检测历史/数据看板等页面点开空白无内容。故向后端确认一次。
            this._verifySession();
        } else {
            if (token) {
                // Token 过期或无效，清除
                Utils.safeLocalStorage.removeItem(CONFIG.TOKEN_KEY);
                Utils.safeLocalStorage.removeItem(CONFIG.LOGIN_KEY);
            }
            this._isGuest = true;
            this.enterGuestMode();
        }
        this._bindCaptcha();
        // Captcha loaded on-demand when auth overlay opens (showAuthOverlay)
        // Auth overlay close button
        const closeBtn = document.getElementById('authOverlayClose');
        if (closeBtn) closeBtn.onclick = () => this.hideAuthOverlay();
        // Click outside auth card to close
        const authPage = document.getElementById('authPage');
        if (authPage) {
            authPage.addEventListener('click', (e) => {
                if (e.target === authPage) this.hideAuthOverlay();
            });
        }

    },

    // ========== Guest Mode ==========

    enterGuestMode() {
        this._isGuest = true;
        // Show main app
        document.getElementById('mainApp').classList.remove('hidden');
        document.getElementById('authPage').classList.add('hidden');
        // Sidebar bars
        document.getElementById('guestBar').classList.remove('hidden');
        const userBar = document.getElementById('userBar');
        if (userBar) userBar.classList.add('hidden');
        // Lock nav items
        this._setNavLocked(true);
        // Default to single detection page
        const singleNav = document.querySelector('.nav-item[data-page="single"]');
        if (singleNav) singleNav.click();
        // Update quota display
        this.updateQuotaDisplay();
        // Bind guest buttons
        const loginBtn = document.getElementById('guestLoginBtn');
        const regBtn = document.getElementById('guestRegisterBtn');
        if (loginBtn) loginBtn.onclick = () => this.showAuthOverlay('login');
        if (regBtn) regBtn.onclick = () => this.showAuthOverlay('register');
        // Hide chatbot for guests (requires login conceptually, but show it)
        document.getElementById('chatbotWidget').classList.remove('hidden');
        // Hide admin-only items
        document.querySelectorAll('.admin-only').forEach(el => el.classList.add('hidden'));
        // Load land info from localStorage only (no API calls without auth)
        LandInfo.load();
        // Skip PlotManager.init() and History.load() — they require auth
        _checkRestore();
    },

    isGuest() {
        return this._isGuest === true;
    },

    getGuestQuota() {
        const stored = Utils.safeLocalStorage.getItem(CONFIG.GUEST_QUOTA_KEY);
        if (stored === null) return CONFIG.GUEST_MAX_QUOTA;
        return Math.max(0, parseInt(stored) || 0);
    },

    useGuestQuota() {
        const current = this.getGuestQuota();
        const next = Math.max(0, current - 1);
        Utils.safeLocalStorage.setItem(CONFIG.GUEST_QUOTA_KEY, String(next));
        this.updateQuotaDisplay();
        return next;
    },

    updateQuotaDisplay() {
        const row = document.getElementById('guestQuotaRow');
        if (!row) return;
        const remaining = this.getGuestQuota();
        if (I18n.getLocale() === 'en') {
            row.innerHTML = 'Free: <strong id="guestQuota">' + remaining + '</strong>/' + CONFIG.GUEST_MAX_QUOTA;
        } else {
            row.innerHTML = '剩余 <strong id="guestQuota">' + remaining + '</strong> 次免费检测';
        }
    },

    // ========== Auth Overlay ==========

    showAuthOverlay(formType) {
        const authPage = document.getElementById('authPage');
        if (!authPage) return;
        var alreadyOpen = !authPage.classList.contains('hidden');
        authPage.classList.remove('hidden');
        this.toggleAuthForm(formType === 'login');
        if (!alreadyOpen) this.loadCaptcha();
    },

    hideAuthOverlay() {
        const authPage = document.getElementById('authPage');
        if (authPage) authPage.classList.add('hidden');
    },

    // ========== Nav Lock ==========

    _setNavLocked(locked) {
        document.querySelectorAll('.nav-item').forEach(item => {
            const page = item.getAttribute('data-page');
            if (page === 'single') return; // never lock single detection
            if (locked) {
                item.classList.add('locked');
                item.setAttribute('tabindex', '-1');
            } else {
                item.classList.remove('locked');
                item.removeAttribute('tabindex');
            }
        });
    },

    // ========== Existing Methods ==========

    _bindCaptcha() {
        const refreshReg = document.getElementById('refreshCaptcha');
        const imgReg = document.getElementById('captchaImg');
        if (refreshReg) refreshReg.onclick = () => this.loadCaptcha();
        if (imgReg) imgReg.onclick = () => this.loadCaptcha();
        const refreshLogin = document.getElementById('refreshLoginCaptcha');
        const imgLogin = document.getElementById('loginCaptchaImg');
        if (refreshLogin) refreshLogin.onclick = () => this.loadCaptcha();
        if (imgLogin) imgLogin.onclick = () => this.loadCaptcha();
    },

    async loadCaptcha() {
        if (this._captchaLoading) return;
        this._captchaLoading = true;
        try {
            const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/captcha`);
            const data = await res.json();
            if (data.code === 200 && data.data) {
                this._captchaId = data.data.captcha_id;
                const imgReg = document.getElementById('captchaImg');
                const imgLogin = document.getElementById('loginCaptchaImg');
                const img = data.data.captcha_image;
                if (imgReg) imgReg.src = img;
                if (imgLogin) imgLogin.src = img;
            }
        } catch {
            // 静默失败，后端会校验
        } finally {
            this._captchaLoading = false;
        }
    },

    toggleAuthForm(isLogin) {
        document.getElementById("loginForm").classList.toggle("hidden", !isLogin);
        document.getElementById("registerForm").classList.toggle("hidden", isLogin);
    },

    async handleRegister() {
        const u = document.getElementById("reg_user").value.trim();
        const p = document.getElementById("reg_pwd").value.trim();
        const captcha = document.getElementById("reg_captcha").value.trim();
        if (!u || !p) return Modal.alert(I18n.t('auth.fillAllFields'));
        if (p.length < 8) return Modal.alert(I18n.t('auth.pwdTooShort'));
        if (!captcha) return Modal.alert(I18n.t('auth.captchaRequired'));
        if (!this._captchaId) return Modal.alert(I18n.t('auth.captchaExpired'));
        const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: u,
                password: p,
                captcha_id: this._captchaId,
                captcha_answer: captcha
            })
        });
        if (res.status === 400) {
            const err = await res.json();
            this.loadCaptcha();
            document.getElementById("reg_captcha").value = '';
            return Modal.alert(err.detail || I18n.t('auth.registerFailed'));
        }
        await Modal.alert(I18n.t('auth.registerSuccessMsg'));
        this.loadCaptcha();
        document.getElementById("reg_captcha").value = '';
        this.toggleAuthForm(true);
    },

    async handleLogin() {
        const u = document.getElementById("login_user").value.trim();
        const p = document.getElementById("login_pwd").value.trim();
        const captcha = document.getElementById("login_captcha").value.trim();
        if (!u || !p) return Modal.alert(I18n.t('auth.enterCredentials'));
        if (!captcha) return Modal.alert(I18n.t('auth.captchaRequired'));
        if (!this._captchaId) return Modal.alert(I18n.t('auth.captchaExpired'));
        try {
            const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: u,
                    password: p,
                    captcha_id: this._captchaId,
                    captcha_answer: captcha
                })
            });
            if (res.status === 400) {
                const errData = await res.json();
                this.loadCaptcha();
                document.getElementById("login_captcha").value = '';
                return Modal.alert(errData.detail || I18n.t('auth.loginFailed'));
            }
            if (res.status === 401) {
                this.loadCaptcha();
                document.getElementById("login_captcha").value = '';
                return Modal.alert(I18n.t('auth.invalidCredentials'));
            }
            if (res.status === 403) {
                const errData = await res.json();
                this.loadCaptcha();
                document.getElementById("login_captcha").value = '';
                return Modal.alert(errData.detail || I18n.t('auth.accountDisabled'));
            }
            const data = await res.json();
            Utils.safeLocalStorage.setItem(CONFIG.TOKEN_KEY, data.token);
            Utils.safeLocalStorage.setItem(CONFIG.LOGIN_KEY, data.username);
            Utils.safeLocalStorage.setItem(CONFIG.LOGIN_KEY + '_role', data.role || 'user');
            state.currentUserRole = data.role || 'user';
            this.hideAuthOverlay();
            this.enterSystem(data.username);
        } catch (e) {
            if (e.name === 'AbortError') {
                Modal.alert(I18n.t('auth.requestTimeout'));
            } else {
                Modal.alert(I18n.t('auth.serverUnreachable'));
            }
        }
    },

    async handleLogout() {
        const ok = await Modal.confirm(I18n.t('auth.confirmLogout'));
        if (ok) {
            Utils.safeLocalStorage.removeItem(CONFIG.TOKEN_KEY);
            Utils.safeLocalStorage.removeItem(CONFIG.LOGIN_KEY);
            this.enterGuestMode();
        }
    },

    enterSystem(username) {
        this._isGuest = false;
        state.currentUser = username;
        document.getElementById("authPage").classList.add("hidden");
        document.getElementById("mainApp").classList.remove("hidden");
        // Sidebar bars
        document.getElementById("guestBar").classList.add("hidden");
        const userBar = document.getElementById("userBar");
        if (userBar) userBar.classList.remove("hidden");
        // Unlock nav items
        this._setNavLocked(false);
        // User info
        document.getElementById("showUser").innerText = username;
        document.getElementById("userAvatar").innerText = username.charAt(0).toUpperCase();
        const roleEl = document.getElementById("userRole");
        if (roleEl) roleEl.textContent = `${I18n.t('auth.role')}：${state.currentUserRole === 'admin' ? I18n.t('usermgr.adminBadge') : I18n.t('auth.normalUser')}`;
        document.getElementById("chatbotWidget").classList.remove("hidden");
        // Admin-only items
        const isAdmin = state.currentUserRole === 'admin';
        document.querySelectorAll('.admin-only').forEach(el => {
            el.classList.toggle('hidden', !isAdmin);
        });
        LandInfo.load();
        PlotManager.init();
        History.load();
        _checkRestore();
    },

    isLoggedIn() {
        return !!Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY);
    },

    /**
     * 向后端确认会话仍然有效。
     * 仅在明确收到 401 时清理登录态并提示；网络异常一律放行，
     * 避免接口抖动或离线时把用户无故踢出登录。
     */
    async _verifySession() {
        try {
            const res = await fetch(`${CONFIG.API_BASE_URL}/profile`, {
                headers: {
                    Authorization: `Bearer ${Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY)}`,
                },
            });
            if (res.status === 401) {
                Utils.safeLocalStorage.removeItem(CONFIG.TOKEN_KEY);
                Utils.safeLocalStorage.removeItem(CONFIG.LOGIN_KEY);
                this._isGuest = true;
                this.enterGuestMode();
                Modal.alert(I18n.t('auth.sessionExpired',
                    '登录状态已失效（服务端数据可能已重置），请重新登录'));
                this.showAuthOverlay('login');
            }
        } catch (e) {
            // 网络问题不作处理，交由各页面的请求自行提示
        }
    },

    checkLogin() {
        // Guest with quota remaining is allowed
        if (this.isGuest()) {
            if (this.getGuestQuota() <= 0) {
                Modal.alert(I18n.t('guest.quotaExhausted'));
                this.showAuthOverlay('login');
                return false;
            }
            return true;
        }
        // Not guest and not logged in (shouldn't happen, but safe fallback)
        if (!this.isLoggedIn()) {
            Modal.alert(I18n.t('auth.pleaseLogin'));
            return false;
        }
        return true;
    }
};

async function _checkRestore() {
    try {
        const { BatchStore } = await import('./indexedDB.js');
        const tasks = await BatchStore.getAllTasks();
        if (!tasks || tasks.length === 0) return;
        const incomplete = tasks.filter(t => t.status !== 'completed');
        if (incomplete.length === 0) {
            await BatchStore.clearAll().catch(() => {});
            return;
        }
        const doneCount = tasks.length - incomplete.length;
        const banner = document.getElementById('batchRestoreBanner');
        const textEl = document.getElementById('batchRestoreText');
        const restoreBtn = document.getElementById('batchRestoreBtn');
        const dismissBtn = document.getElementById('batchDismissBtn');
        if (!banner || !textEl) return;

        textEl.textContent = `检测到未完成的批量任务（已完成 ${doneCount}/${tasks.length}），是否恢复？`;
        banner.classList.remove('hidden');

        restoreBtn.onclick = async () => {
            banner.classList.add('hidden');
            const navBtn = document.querySelector('.nav-item[data-page="batch"]');
            if (navBtn) navBtn.click();
            const { BatchDetector } = await import('./batchDetector.js');
            await BatchDetector.restore(tasks);
        };
        dismissBtn.onclick = async () => {
            banner.classList.add('hidden');
            await BatchStore.clearAll().catch(() => {});
        };
    } catch { /* IndexedDB not available, skip */ }
}
