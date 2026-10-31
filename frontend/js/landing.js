import { Auth } from './auth.js';
import { Detector } from './detector.js';
import { Modal } from './modal.js';
import { I18n } from './i18n.js';

// 本会话内关掉首屏就不再弹。用 sessionStorage 而不是 localStorage：
// 下次开新标签页还是想看到首屏，但同一个会话里反复弹会很烦。
const DISMISS_KEY = 'landing_dismissed';
const SLIDE_INTERVAL = 6500;

const SAMPLE = [
    ['#file1', 'images/samples/sample-t1.jpg', 'sample-T1.jpg'],
    ['#file2', 'images/samples/sample-t2.jpg', 'sample-T2.jpg'],
];

export const Landing = {
    _el: null,
    _slides: [],
    _dots: [],
    _idx: 0,
    _timer: null,
    _busy: false,

    init() {
        this._el = document.getElementById('landingPage');
        if (!this._el) return;

        // 单张检测空状态里的「用示例试一次」：不经过首屏也要能点
        const emptyBtn = document.getElementById('detectSampleBtn');
        if (emptyBtn) emptyBtn.onclick = () => this.runSample();

        // 显不显示已经由 <head> 的内联脚本在首绘前定好了
        if (document.documentElement.getAttribute('data-landing') !== 'show') return;

        // 先绑「进门」的三个按钮，再绑轮播。顺序有讲究：首屏盖着整个应用，
        // 万一后面的轮播代码抛错，用户至少还能从这里进去，不会卡死在首屏。
        const on = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.onclick = fn;
        };
        on('landingLoginBtn', () => Auth.showAuthOverlay('login'));
        on('landingEnterBtn', () => this.dismiss());
        on('landingUploadBtn', () => this.dismiss());
        on('landingSampleBtn', () => this.runSample());

        try {
            this._slides = Array.from(this._el.querySelectorAll('.landing-slide'));
            this._dots = Array.from(this._el.querySelectorAll('.landing-dot'));
            this._dots.forEach((dot, i) => {
                dot.onclick = () => {
                    this.goTo(i);
                    this._restart();
                };
            });
            this._restart();
        } catch (e) {
            console.error('[landing] 轮播初始化失败，首屏保持静态', e);
        }
    },

    dismiss() {
        try {
            sessionStorage.setItem(DISMISS_KEY, '1');
        } catch {
            /* 隐私模式下存不了，那就每次刷新都显示，不影响使用 */
        }
        document.documentElement.removeAttribute('data-landing');
        this._stop();
    },

    goTo(i) {
        if (!this._slides.length) return;
        this._idx = (i + this._slides.length) % this._slides.length;
        this._slides.forEach((s, k) => s.classList.toggle('is-active', k === this._idx));
        this._dots.forEach((d, k) => d.classList.toggle('is-active', k === this._idx));
    },

    _restart() {
        this._stop();
        this._timer = setInterval(() => this.goTo(this._idx + 1), SLIDE_INTERVAL);
    },

    _stop() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    },

    // 载入内置示例影像并直接跑一次检测 —— 陌生人不用先去硬盘里找两张图
    async runSample() {
        if (this._busy) return;
        this._busy = true;
        try {
            this.dismiss();
            const nav = document.querySelector('.nav-item[data-page="single"]');
            if (nav) nav.click();
            await new Promise((r) => setTimeout(r, 150));

            for (const [sel, url, name] of SAMPLE) {
                await this._loadFile(sel, url, name);
            }
            await Detector.start();
        } catch (e) {
            console.error('[landing] 示例影像加载失败', e);
            Modal.alert(I18n.t('landing.sampleFailed'));
        } finally {
            this._busy = false;
        }
    },

    async _loadFile(selector, url, name) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${url} -> ${res.status}`);
        const blob = await res.blob();
        const file = new File([blob], name, { type: blob.type || 'image/jpeg' });

        // <input type=file> 的 files 是只读的，但可以直接赋一个 DataTransfer 的
        // FileList；赋完再派发 change，Uploader 才会更新预览。
        const dt = new DataTransfer();
        dt.items.add(file);
        const input = document.querySelector(selector);
        input.files = dt.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
    },
};
