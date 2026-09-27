import { Auth } from './auth.js';
import { Navigator } from './navigator.js';
import { Uploader } from './uploader.js';
import { GPSLocator } from './gpsLocator.js';
import { LandInfo, PlotManager } from './landInfo.js';
import { Detector } from './detector.js';
import { BatchDetector } from './batchDetector.js';
import { Chatbot } from './chatbot.js';
import { History } from './history.js';
import { Utils } from './utils.js';
import { Toast } from './toast.js';
import { Timeline } from './timeline.js';
import { BigScreen } from './bigscreen.js';
import { Compare } from './compare.js';
import { SystemStatus } from './status.js';
import { MapViewer } from './mapViewer.js';
import { UserManager } from './userManager.js';
import { Profile } from './profile.js';
import { Notify } from './notify.js';
import { I18n } from './i18n.js';
import { eventBus } from './eventBus.js';
import { state } from './state.js';
import { Shortcuts } from './shortcuts.js';
import { ShareView } from './shareView.js';
import { Evaluator } from './evaluator.js';
import { Gallery } from './gallery.js';
import { ImageTools } from './imageTools.js';
import { NDVIViewer } from './ndviViewer.js';
import { Agent } from './agent.js';
import { Disaster } from './disaster.js';

function initEventListeners() {
    const goRegister = document.getElementById("goRegister");
    const goLogin = document.getElementById("goLogin");
    const registerBtn = document.getElementById("registerBtn");
    const loginBtn = document.getElementById("loginBtn");
    const logoutBtn = document.getElementById("logoutBtn");
    const clearAllHistory = document.getElementById("clearAllHistory");

    if (goRegister) goRegister.onclick = () => Auth.toggleAuthForm(false);
    if (goLogin) goLogin.onclick = () => Auth.toggleAuthForm(true);
    if (registerBtn) registerBtn.onclick = () => Auth.handleRegister();
    if (loginBtn) loginBtn.onclick = () => Auth.handleLogin();
    if (logoutBtn) logoutBtn.onclick = () => Auth.handleLogout();
    if (clearAllHistory) clearAllHistory.onclick = () => History.clearAll();
}

function safeInit(name, fn) {
    try {
        fn();
    } catch (e) {
        console.error(`Failed to initialize ${name}:`, e);
    }
}

window.onload = () => {
    initEventListeners();
    safeInit('Auth', () => Auth.init());
    safeInit('Navigator', () => Navigator.init());
    safeInit('Uploader', () => Uploader.init());
    safeInit('GPSLocator', () => GPSLocator.init());
    safeInit('LandInfo', () => LandInfo.init());
    safeInit('Detector', () => Detector.init());
    safeInit('BatchDetector', () => BatchDetector.init());
    safeInit('Chatbot', () => Chatbot.init());
    safeInit('History', () => History.init());
    safeInit('Timeline', () => Timeline.init());
    safeInit('BigScreen', () => BigScreen.init());
    safeInit('Compare', () => Compare.init());
    safeInit('MapViewer', () => MapViewer.init());
    safeInit('UserManager', () => UserManager.init());
    safeInit('Profile', () => Profile.init());
    Utils.setupGlobalErrorHandler();
    safeInit('Notify', () => Notify.init());
    safeInit('I18n', () => I18n.init());
    safeInit('Gallery', () => Gallery.init());
    safeInit('NDVIViewer', () => NDVIViewer.init());
    safeInit('Agent', () => Agent.init());
    safeInit('Disaster', () => Disaster.init());

    const langBtn = document.getElementById("langSwitchBtn");
    if (langBtn) {
        langBtn.onclick = () => {
            const next = I18n.getLocale() === 'zh-CN' ? 'en' : 'zh-CN';
            I18n.setLocale(next);
            langBtn.textContent = next === 'zh-CN' ? '中/EN' : 'EN/中';
        };
    }

    const themeBtn = document.getElementById("toggleThemeBtn");
    if (themeBtn) {
        const savedTheme = Utils.safeLocalStorage.getItem("app_theme") || "light";
        document.documentElement.setAttribute("data-theme", savedTheme);
        themeBtn.textContent = savedTheme === "dark" ? I18n.t('theme.dark') : I18n.t('theme.light');
        themeBtn.setAttribute("aria-pressed", savedTheme === "dark");
        themeBtn.onclick = () => {
            const current = document.documentElement.getAttribute("data-theme");
            const next = current === "dark" ? "light" : "dark";
            const html = document.documentElement;
            html.classList.add("theme-transitioning");
            html.setAttribute("data-theme", next);
            Utils.safeLocalStorage.setItem("app_theme", next);
            themeBtn.setAttribute("aria-pressed", next === "dark");
            themeBtn.textContent = next === "dark" ? I18n.t('theme.dark') : I18n.t('theme.light');
            setTimeout(() => html.classList.remove("theme-transitioning"), 420);
        };
    }
    // 页面卸载时释放所有 blob URL
    window.addEventListener('beforeunload', () => {
        state.batchResult.forEach(item => {
            if (item.t1Url) Utils.releaseObjectURL(item.t1Url);
            if (item.t2Url) Utils.releaseObjectURL(item.t2Url);
        });
    });

    if ('serviceWorker' in navigator) {
        // 带版本参数注册：否则浏览器不会重新下载 sw.js，
        // 改了缓存策略与 CACHE_NAME 也无法生效（曾导致旧 JS 长期驻留）。
        // 每次改动 sw.js 时把这个版本号一起 +1。
        navigator.serviceWorker.register('sw.js?v=10', { scope: './' }).then(reg => {
            console.log('SW registered:', reg.scope);
            // 新 SW 就绪后立即接管，不必等所有标签页关闭
            if (reg.waiting) reg.waiting.postMessage({ type: 'SKIP_WAITING' });
        }).catch(() => {});
    }

    // Inject manifest as blob URL (bypasses JetBrains server MIME restriction on .json)
    const manifest = {
        name: 'BIT_CD 黑土地遥感变化检测系统',
        short_name: 'BIT_CD',
        description: '黑土地保护智能平台 - 遥感变化检测与AI分析',
        start_url: './index.html',
        display: 'standalone',
        background_color: '#f8fafc',
        theme_color: '#2d6a4f',
        orientation: 'any',
        icons: [{ src: 'images/logo.png', sizes: '80x80', type: 'image/png' }],
        categories: ['productivity', 'utilities']
    };
    const manifestBlob = new Blob([JSON.stringify(manifest)], { type: 'application/json' });
    const manifestLink = document.createElement('link');
    manifestLink.rel = 'manifest';
    manifestLink.href = URL.createObjectURL(manifestBlob);
    document.head.appendChild(manifestLink);

    eventBus.on('lang-change', () => {
        const themeBtn = document.getElementById("toggleThemeBtn");
        if (themeBtn) {
            const currentTheme = document.documentElement.getAttribute("data-theme");
            themeBtn.textContent = currentTheme === "dark" ? I18n.t('theme.dark') : I18n.t('theme.light');
            themeBtn.setAttribute("aria-pressed", currentTheme === "dark");
        }
        const roleEl = document.getElementById("userRole");
        if (roleEl) {
            roleEl.style.color = '';
            roleEl.textContent = `${I18n.t('auth.role')}：${state.currentUserRole === 'admin' ? I18n.t('usermgr.adminBadge') : I18n.t('auth.normalUser')}`;
        }
        // Refresh guest quota display for locale
        if (Auth.isGuest()) Auth.updateQuotaDisplay();
        const activeNav = document.querySelector(".nav-item.active");
        if (activeNav) {
            const page = activeNav.getAttribute("data-page");
            if (page) Navigator.switchPage(page, activeNav);
        }
        const langBtn = document.getElementById("langSwitchBtn");
        if (langBtn) {
            langBtn.textContent = I18n.getLocale() === 'zh-CN' ? '中/EN' : 'EN/中';
        }
    });

    eventBus.on('navigate', function(page) {
        var navItem = document.querySelector('.nav-item[data-page="' + page + '"]');
        if (navItem) Navigator.switchPage(page, navItem);
    });

    initMobileMenu();
    initShortcuts();
    ShareView.checkAndRender();
    Evaluator.init();

    console.log("✅ 黑土地遥感系统启动完成！");
};

function initMobileMenu() {
    const toggle = document.getElementById("mobileMenuToggle");
    const sidebar = document.querySelector(".sidebar");
    const backdrop = document.getElementById("sidebarBackdrop");
    if (!toggle || !sidebar || !backdrop) return;

    const open = () => {
        sidebar.classList.add('open');
        backdrop.classList.add('visible');
        toggle.classList.add('active');
    };
    const close = () => {
        sidebar.classList.remove('open');
        backdrop.classList.remove('visible');
        toggle.classList.remove('active');
    };

    toggle.onclick = () => {
        sidebar.classList.contains('open') ? close() : open();
    };
    backdrop.onclick = close;

    // Close sidebar when a nav item is clicked (mobile)
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            if (window.innerWidth <= 768) close();
        });
    });
}

function initShortcuts() {
    Shortcuts.init();

    Shortcuts.register('Ctrl+Enter', () => {
        const singlePage = document.getElementById('page-single');
        if (singlePage && singlePage.classList.contains('active')) {
            document.getElementById('startBtn')?.click();
        }
    });

    Shortcuts.register('Ctrl+Shift+B', () => {
        const batchPage = document.getElementById('page-batch');
        if (batchPage && batchPage.classList.contains('active')) {
            document.getElementById('batchStart')?.click();
        }
    });

    Shortcuts.register('none+?', () => {
        Shortcuts.showHelp();
    });

    // Left/Right arrows: navigate history pages or timeline strip
    Shortcuts.register('none+ArrowLeft', () => {
        const histPage = document.getElementById('page-history');
        if (histPage && histPage.classList.contains('active')) {
            if (History._currentPage > 1) {
                History._currentPage--;
                History.renderList();
            }
            return;
        }
        const tlPage = document.getElementById('page-timeline');
        if (tlPage && tlPage.classList.contains('active')) {
            document.getElementById('timelineScrollLeft')?.click();
        }
    });

    Shortcuts.register('none+ArrowRight', () => {
        const histPage = document.getElementById('page-history');
        if (histPage && histPage.classList.contains('active')) {
            History._currentPage++;
            History.renderList();
            return;
        }
        const tlPage = document.getElementById('page-timeline');
        if (tlPage && tlPage.classList.contains('active')) {
            document.getElementById('timelineScrollRight')?.click();
        }
    });
}