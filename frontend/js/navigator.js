import { state } from './state.js';
import { Auth } from './auth.js';
import { I18n } from './i18n.js';
import { Timeline } from './timeline.js';
import { BigScreen } from './bigscreen.js';
import { Compare } from './compare.js';
import { SystemStatus } from './status.js';
import { MapViewer } from './mapViewer.js';
import { UserManager } from './userManager.js';
import { History } from './history.js';
import { Disaster } from './disaster.js';
import { Overview } from './overview.js';
import { Insights } from './insights.js';

// 页面切到可见之后再渲染。
//
// 原先每处都是 setTimeout(…, 50)，那是「赌 50ms 够布局跑完」——慢机器上会赌输，
// 图表容器还没尺寸就初始化，画出来是空的。requestAnimationFrame 套两层是
// 「等这一帧画完」的确定写法，两者都保证容器此时已有尺寸，但后者不等死时间。
const afterPaint = (fn) => requestAnimationFrame(() => requestAnimationFrame(fn));

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
        // 游客只能访问概览与单张检测（概览是首页，锁上等于进门就弹登录框）
        if (Auth.isGuest() && page !== 'single' && page !== 'overview') {
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
        } else {
            // 页面不存在时展示 404
            target = document.getElementById("page-notfound");
            if (target) {
                target.classList.add("active");
            }
            return;
        }

        if (page === 'land' && state.map) {
            afterPaint(function () {
                state.map.resize();
                if (state.marker) state.map.setFitView([state.marker]);
            });
        }
        if (page === 'overview') {
            afterPaint(function () { Overview.render(); });
        }
        if (page === 'insights') {
            afterPaint(function () { Insights.render(); });
        }
        if (page === 'dashboard') {
            afterPaint(function () { BigScreen.render(); });
        }
        if (page === 'timeline') {
            afterPaint(function () { Timeline.render(); });
        }
        if (page === 'compare') {
            afterPaint(function () { Compare.render(); });
        }
        if (page === 'status') {
            afterPaint(function () { SystemStatus.render(); });
        }
        if (page === 'mapviewer') {
            afterPaint(function () { MapViewer.render(); });
        }
        if (page === 'usermgr') {
            afterPaint(function () { UserManager.render(); });
        }
        if (page === 'history') {
            // 此前没有这一条：History.init() 只绑事件不拉数据，于是切回历史页
            // 永远是上次的旧列表（别处新产生的检测看不到）。
            afterPaint(function () { History.load(); });
        }
        if (page === 'disaster') {
            afterPaint(function () { Disaster.render(); });
        }
        if (page === 'profile') {
            // 动态导入个人中心模块
            import('./profile.js').then(function (m) {
                afterPaint(function () { m.Profile.render(); });
            }).catch(function (e) { console.error('Failed to load profile module:', e); });
        }
    }
};