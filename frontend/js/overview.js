import { API } from './api.js';
import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { Auth } from './auth.js';
import { Landing } from './landing.js';

/**
 * 系统概览 —— 进系统后的第一屏。
 *
 * 原先进系统直接落在「单张检测」的空表单上：陌生人看到的第一个界面是一个
 * 上传框，不知道这个系统还能干什么。首屏（landing.js）解决的是门外的宣传，
 * 这里解决门内的 —— 一屏看清能力全貌，每张卡片直达对应页面。
 *
 * 不 import Navigator：导航模块要反过来 import 本模块去渲染，两边互相引
 * 会形成循环。跳页改成点对应的 nav 按钮，走它已有的 click 处理。
 */
export const Overview = {
    _loaded: false,

    init() {
        const on = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.onclick = fn;
        };
        on('ovStartBtn', () => this.go('single'));
        on('ovSampleBtn', () => Landing.runSample());

        document.querySelectorAll('#page-overview .ov-cap, #page-overview .ov-stat').forEach((card) => {
            card.onclick = () => this.go(card.dataset.go);
        });

        this.render();
    },

    go(page) {
        const nav = document.querySelector('.nav-item[data-page="' + page + '"]');
        if (nav) nav.click();
    },

    _set(id, value) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = value;
        // 「0」和「—」不是成绩，别用强调色摆着；顺带在标签后補一句「暂无」，
        // 免得读者以为是系统出错
        const cell = el.closest('.ov-stat');
        if (cell) {
            const empty = value === '—' || value === '0' || value === '0 / 0';
            cell.classList.toggle('is-empty', empty);
        }
    },

    // 初值是 HTML 里的「—」，没经过 _set；这里按屏幕上的实际内容再算一遍
    _refreshEmptyFlags() {
        document.querySelectorAll('#page-overview .ov-stat').forEach((cell) => {
            const v = (cell.querySelector('b') || {}).textContent || '';
            cell.classList.toggle('is-empty', v.trim() === '—' || v.trim() === '0');
        });
    },

    async render() {
        // 模型数走公开接口，游客也拿得到
        try {
            const res = await Utils.fetchWithTimeout(`${CONFIG.API_BASE_URL}/detect/models`);
            const body = await res.json();
            const models = body.models || [];
            if (models.length) {
                const available = models.filter((m) => m.available).length;
                this._set('ovStatModels', `${available} / ${models.length}`);
            }
        } catch {
            /* 拿不到就保持「—」，不编数字 */
        }

        // 其余三项要登录；游客看到的是「—」，这也是个显式的邀请
        if (Auth.isGuest() || this._loaded) {
            this._refreshEmptyFlags();
            return;
        }
        try {
            const [history, plots] = await Promise.all([API.fetchHistory(), API.fetchPlots()]);
            const records = Array.isArray(history) ? history : (history && history.data) || [];
            const cities = new Set();
            records.forEach((r) => {
                const loc = (r.location || '').trim();
                if (!loc) return;
                // 位置形如「吉林省·四平市」，取市
                const parts = loc.split(/[·\s]+/).filter(Boolean);
                cities.add(parts.length > 1 ? parts[1] : parts[0]);
            });
            this._set('ovStatDetections', String(records.length));
            this._set('ovStatRegions', String(cities.size));
            this._set('ovStatPlots', Array.isArray(plots) ? String(plots.length) : '—');
            this._loaded = true;
        } catch {
            /* 同上，保持「—」 */
        }
        this._refreshEmptyFlags();
    },
};
