import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { Toast } from './toast.js';
import { LandInfo, PlotManager } from './landInfo.js';
import { I18n } from './i18n.js';
import { History } from './history.js';

function _decodeToken(token) {
    try {
        // JWT 的 payload 是 base64url，atob 只认标准 base64，得先换字符表
        const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        return JSON.parse(atob(b64));
    } catch {
        return null;
    }
}

function _isTokenExpired(token) {
    const payload = _decodeToken(token);
    return !payload || !payload.exp || payload.exp * 1000 < Date.now();
}

export const Auth = {
    _captchaId: null,
    _isGuest: null, // null=uninitialized, true=guest, false=logged-in

    init() {
        this._consumeOAuthFragment();
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

        this._loadOAuthProviders();
        if (this._oauthWelcome) {
            Toast.success(this._oauthWelcome);
            this._oauthWelcome = null;
        }
        if (this._oauthError) {
            Modal.alert(this._oauthError);
            this._oauthError = null;
        }
    },

    // ========== 第三方登录 ==========

    // GitHub 回跳时把 token 放在 URL fragment 里：fragment 不会发给服务器、
    // 不进 Referer。但它仍会留在浏览器历史里，所以读到后立刻从地址栏抹掉。
    _consumeOAuthFragment() {
        const hash = window.location.hash || '';
        if (!hash.startsWith('#oauth_')) return;

        const params = new URLSearchParams(hash.slice(1));
        const token = params.get('oauth_token');
        const err = params.get('oauth_error');
        window.history.replaceState(null, '', window.location.pathname + window.location.search);

        if (token) {
            const payload = _decodeToken(token);
            if (!payload || !payload.sub) {
                this._oauthError = I18n.t('auth.oauthError');
                return;
            }
            // 名字和角色直接从 token 里取 —— 回调地址里只带 token，不多塞参数
            Utils.safeLocalStorage.setItem(CONFIG.TOKEN_KEY, token);
            Utils.safeLocalStorage.setItem(CONFIG.LOGIN_KEY, payload.sub);
            Utils.safeLocalStorage.setItem(CONFIG.LOGIN_KEY + '_role', payload.role || 'user');
            this._oauthWelcome = I18n.t('auth.oauthWelcome');
            return;
        }

        if (err) {
            const known = { denied: 'auth.oauthDenied', disabled: 'auth.oauthDisabled' };
            this._oauthError = I18n.t(known[err] || 'auth.oauthError');
        }
    },

    // 服务端没配 client_id 时不显示按钮。拿不到结果就按未配置处理 ——
    // 宁可少一个入口，也不要给用户一个点了必然失败的按钮。
    async _loadOAuthProviders() {
        try {
            const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/auth/providers`);
            if (!res.ok) return;
            const body = await res.json();
            const enabled = !!(body && body.data && body.data.github);
            ['oauthDivider', 'githubLoginBtn'].forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.classList.toggle('hidden', !enabled);
            });
        } catch {
            /* 静默：第三方登录只是附加入口，连不上后端不影响账号密码登录 */
        }
    },

    startGithubLogin() {
        // 授权页在 github.com 下，不能 fetch，必须整页跳转
        window.location.href = `${CONFIG.API_BASE_URL}/auth/github/authorize`;
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

    /**
     * 用服务端返回的数字覆盖本地那份。
     *
     * 本地计数只是离线兜底 —— 真正说了算的是服务端（按 IP 按天）。两边不
     * 一致时以服务端为准，否则换个浏览器、清个缓存，两边就各说各话了。
     */
    syncGuestQuota(remaining) {
        if (typeof remaining !== "number" || remaining < 0) return;
        Utils.safeLocalStorage.setItem(CONFIG.GUEST_QUOTA_KEY, String(remaining));
        this.updateQuotaDisplay();
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
            // 单张检测和系统概览都不锁：前者是游客唯一能用的功能，
            // 后者是首页 —— 把首页也锁上，游客进来只会看到一个弹窗
            if (page === 'single' || page === 'overview') return;
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
                this._captchaWarned = false;   // 恢复正常，下次失败可以再提示
            }
        } catch (e) {
            // 原先这里静默吞掉，结果是登录路径上的一条死路：用户看到的是一个空白
            // 验证码框，既不知道出了什么事，也不知道点一下图能刷新。后端确实会校验
            // 验证码，但读不到码就填不对 —— 不提示等于让人对着空白框猜。
            // 只提示一次，避免每次打开登录框都弹。
            console.warn('[auth] 验证码加载失败:', e);
            if (!this._captchaWarned) {
                this._captchaWarned = true;
                Toast.warning(I18n.t('auth.captchaFailed', '验证码加载失败，点击图片可重试'));
            }
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
        // 登录成功后首屏就该让位 —— 它只在未登录时有意义
        document.documentElement.removeAttribute("data-landing");
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
            // 「网络异常不踢用户下线」这个行为保留（见方法文档注释），但不能静默：
            // 确认不了会话时，后面各页面的请求失败就失去了解释。提示一次即可 ——
            // 每次进入应用都会走到这里，重复弹就是骚扰。
            console.warn('[auth] 会话校验失败（网络原因），保留本地登录态:', e);
            if (!this._offlineWarned) {
                this._offlineWarned = true;
                Toast.warning(I18n.t('auth.verifyOffline', '无法连接服务器，后续操作可能失败'));
            }
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
