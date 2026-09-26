import { state } from './state.js';
import { Auth } from './auth.js';
import { I18n } from './i18n.js';
import { Timeline } from './timeline.js';
import { BigScreen } from './bigscreen.js';
import { Compare } from './compare.js';
import { SystemStatus } from './status.js';
import { MapViewer } from './mapViewer.js';
import { UserManager } from './userManager.js';

export const Navigator = {
    _currentPage: null,

    init() {
        document.querySelectorAll(".nav-item").forEach(item => {
            item.addEventListener("click", () => {
                const page = item.getAttribute("data-page");
                this.switchPage(page, item);
            });
        });
        // 侧边栏底部用户信息点击跳转个人中心
        var userInfo = document.querySelector('.user-info');
        if (userInfo) {
            userInfo.style.cursor = 'pointer';
            userInfo.addEventListener('click', function () {
                var profileNav = document.querySelector('.nav-item[data-page="profile"]');
                if (profileNav) Navigator.switchPage('profile', profileNav);
            });
        }
        // 地址栏同步：此前完全没有路由，刷新即回首页、后退/前进键失效
        window.addEventListener("hashchange", () => {
            const page = this._pageFromHash();
            if (page && page !== this._currentPage) {
                this.switchPage(page,
                    document.querySelector('.nav-item[data-page="' + page + '"]'),
                    { fromHash: true });
            }
        });
        const initial = this._pageFromHash();
        if (initial) {
            this.switchPage(initial,
                document.querySelector('.nav-item[data-page="' + initial + '"]'),
                { fromHash: true });
        }
    },

    _pageFromHash() {
        const h = (location.hash || "").replace(/^#\/?/, "");
        return h || null;
    },

    switchPage(page, navItem, opts) {
        // 游客只能访问单张检测页
        if (Auth.isGuest() && page !== 'single') {
            Auth.showAuthOverlay('login');
            return;
        }
        // 同步到地址栏，使刷新后能回到当前页、前进后退键可用
        if (!opts || !opts.fromHash) {
            try {
                history.pushState(null, "", "#/" + page);
            } catch (e) {
                location.hash = "#/" + page;
            }
        }
        // 离开当前页面时执行清理
        if (this._currentPage === 'dashboard') BigScreen.cleanup();
        this._currentPage = page;

        document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
        if (navItem) navItem.classList.add("active");
        document.querySelectorAll(".page-content").forEach(p => p.classList.remove("active"));
        var target = document.getElementById("page-" + page);
        if (target) {
            target.classList.add("active");
            target.classList.add("fade-in");
        } else {
            // 页面不存在时展示 404
            target = document.getElementById("page-notfound");
            if (target) {
                target.classList.add("active");
                target.classList.add("fade-in");
            }
            return;
        }

        if (page === 'land' && state.map) {
            setTimeout(function () {
                state.map.resize();
                if (state.marker) state.map.setFitView([state.marker]);
            }, 100);
        }
        if (page === 'dashboard') {
            setTimeout(function () { BigScreen.render(); }, 100);
        }
        if (page === 'timeline') {
            setTimeout(function () { Timeline.render(); }, 50);
        }
        if (page === 'compare') {
            setTimeout(function () { Compare.render(); }, 50);
        }
        if (page === 'status') {
            setTimeout(function () { SystemStatus.render(); }, 50);
        }
        if (page === 'mapviewer') {
            setTimeout(function () { MapViewer.render(); }, 150);
        }
        if (page === 'usermgr') {
            setTimeout(function () { UserManager.render(); }, 50);
        }
        if (page === 'profile') {
            // 动态导入个人中心模块
            import('./profile.js').then(function (m) {
                setTimeout(function () { m.Profile.render(); }, 50);
            }).catch(function (e) { console.error('Failed to load profile module:', e); });
        }
    }
};