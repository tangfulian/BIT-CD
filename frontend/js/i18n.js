import { Utils } from './utils.js';
import { zhCN } from './locales/zh-CN.js';
import { en } from './locales/en.js';
import { eventBus } from './eventBus.js';

const LOCALES = { 'zh-CN': zhCN, 'en': en };
let _current = Utils.safeLocalStorage.getItem('app_lang') || 'zh-CN';

const _observer = new MutationObserver((mutations) => {
    mutations.forEach(m => {
        m.addedNodes.forEach(node => {
            if (node.nodeType === 1) {
                _translateElement(node);
                node.querySelectorAll?.('[data-i18n]').forEach(_translateElement);
            }
        });
    });
});

function _translateElement(el) {
    const key = el.getAttribute('data-i18n');
    if (!key) return;
    const dict = LOCALES[_current] || zhCN;
    const text = key in dict ? dict[key] : key;
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') {
        el.placeholder = text;
    } else if (tag === 'SELECT' || tag === 'OPTION' || tag === 'BUTTON') {
        // SELECT/OPTION/BUTTON: use textContent for i18n spans inside or the element itself
        el.textContent = text;
    } else {
        el.textContent = text;
    }
}

export const I18n = {
    t(key, fallback, ...args) {
        const dict = LOCALES[_current] || zhCN;
        let text = dict[key];
        // fallback can be the default text string (when key is missing) or first replacement arg
        if (text === undefined) {
            text = (typeof fallback === 'string') ? fallback : key;
        } else if (args.length === 0 && fallback !== undefined && typeof fallback !== 'string') {
            args = [fallback];
        }
        if (args.length > 0) {
            args.forEach((v, i) => { text = text.replace(new RegExp(`\\{${i}\\}`, 'g'), v); });
        }
        return text;
    },

    getLocale() {
        return _current;
    },

    setLocale(lang) {
        if (!LOCALES[lang]) return;
        _current = lang;
        Utils.safeLocalStorage.setItem('app_lang', lang);
        document.querySelectorAll('[data-i18n]').forEach(_translateElement);
        eventBus.emit('lang-change', lang);
    },

    init() {
        _observer.observe(document.body, { childList: true, subtree: true });
        this.setLocale(_current);
    }
};
