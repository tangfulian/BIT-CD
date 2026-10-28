import { I18n } from './i18n.js';

/**
 * 命令面板（Ctrl/Cmd+K）。
 *
 * 设计上的两个取舍：
 *
 * 1. **命令列表不另维护一份**。页面项每次打开时从侧边栏的 `[data-page]`
 *    动态读出来，所以以后加页面不用回来改这里；标签也直接取导航上的现行
 *    文案，中英文切换自动跟上。
 *
 * 2. **不做拼音搜索**。中文用户偶尔会想打拼音首字母，但那要引入一张映射表，
 *    收益不抵维护成本。匹配范围是：导航文案（含中英文）+ 页面 key。
 */
export const CommandPalette = {
    _overlay: null,
    _input: null,
    _list: null,
    _items: [],
    _filtered: [],
    _active: 0,
    _lastFocus: null,

    init() {
        this._overlay = document.getElementById('cmdPalette');
        this._input = document.getElementById('cmdInput');
        this._list = document.getElementById('cmdList');
        if (!this._overlay || !this._input || !this._list) return;

        // Ctrl+K（Windows/Linux）与 Cmd+K（macOS）
        document.addEventListener('keydown', (e) => {
            const isK = (e.key || '').toLowerCase() === 'k';
            if (isK && (e.ctrlKey || e.metaKey) && !e.altKey) {
                e.preventDefault();
                this.toggle();
            }
        });

        this._input.addEventListener('input', () => this._render(this._input.value));
        this._input.addEventListener('keydown', (e) => this._onKey(e));
        // 点遮罩空白处关闭
        this._overlay.addEventListener('mousedown', (e) => {
            if (e.target === this._overlay) this.close();
        });
        // 点条目执行（用 mousedown 而不是 click：避免 input 失焦导致的顺序问题）
        this._list.addEventListener('mousedown', (e) => {
            const li = e.target.closest('.cmd-item');
            if (!li) return;
            e.preventDefault();
            const idx = Number(li.dataset.index);
            const cmd = this._filtered[idx];
            if (cmd) this._run(cmd);
        });
    },

    toggle() {
        this._overlay.hidden ? this.open() : this.close();
    },

    open() {
        this._lastFocus = document.activeElement;
        this._overlay.hidden = false;
        this._input.value = '';
        this._render('');
        // 让浏览器先完成布局再聚焦，否则 iOS 上软键盘可能不弹
        requestAnimationFrame(() => this._input.focus());
    },

    close() {
        this._overlay.hidden = true;
        if (this._lastFocus && this._lastFocus.focus) {
            try { this._lastFocus.focus(); } catch (e) { /* 元素可能已被移除 */ }
        }
    },

    /** 每次打开都重建：导航文案会随语言切换而变 */
    _buildCommands() {
        const cmds = [];
        document.querySelectorAll('.nav-item[data-page]').forEach((el) => {
            // 隐藏的导航项（如无权限的页面）不进面板
            if (el.offsetParent === null) return;
            // 只取文案那一层：按钮里还有 SVG 图标和权限锁（🔒），
            // 直接读 textContent 会把锁也带进命令标签。
            const labelEl = el.querySelector('span[data-i18n]');
            const label = ((labelEl || el).textContent || '').trim();
            if (!label) return;
            cmds.push({
                key: 'page:' + el.dataset.page,
                label,
                kind: 'page',
                kindLabel: I18n.t('cmd.kindPage', '页面'),
                hint: el.dataset.page,
                run: () => el.click(),
            });
        });

        const actions = [
            ['action:theme', I18n.t('cmd.actionTheme', '切换亮色 / 暗色'), 'toggleThemeBtn'],
            ['action:lang', I18n.t('cmd.actionLang', '切换中 / 英文'), 'langSwitchBtn'],
            ['action:chat', I18n.t('cmd.actionChat', '打开 AI 助手'), 'chatbotToggle'],
        ];
        for (const [key, label, btnId] of actions) {
            const btn = document.getElementById(btnId);
            if (!btn) continue;
            cmds.push({
                key, label,
                kind: 'action',
                kindLabel: I18n.t('cmd.kindAction', '操作'),
                hint: '',
                run: () => btn.click(),
            });
        }
        return cmds;
    },

    _render(query) {
        this._items = this._buildCommands();
        const q = (query || '').trim().toLowerCase();
        this._filtered = q
            ? this._items.filter((c) =>
                c.label.toLowerCase().includes(q) ||
                (c.hint || '').toLowerCase().includes(q))
            : this._items;

        this._active = 0;
        this._list.innerHTML = '';

        if (!this._filtered.length) {
            const li = document.createElement('li');
            li.className = 'cmd-empty';
            li.textContent = I18n.t('cmd.noResult', '没有匹配的命令');
            this._list.appendChild(li);
            return;
        }

        this._filtered.forEach((cmd, i) => {
            const li = document.createElement('li');
            li.className = 'cmd-item';
            li.id = 'cmd-item-' + i;
            li.dataset.index = String(i);
            li.setAttribute('role', 'option');
            li.setAttribute('aria-selected', String(i === 0));

            const label = document.createElement('span');
            label.className = 'cmd-item-label';
            label.textContent = cmd.label;

            const kind = document.createElement('span');
            kind.className = 'cmd-item-kind';
            kind.textContent = cmd.kindLabel;

            li.appendChild(label);
            li.appendChild(kind);
            this._list.appendChild(li);
        });

        this._input.setAttribute('aria-activedescendant', 'cmd-item-0');
    },

    _move(delta) {
        if (!this._filtered.length) return;
        const n = this._filtered.length;
        this._active = (this._active + delta + n) % n;

        this._list.querySelectorAll('.cmd-item').forEach((li, i) => {
            li.setAttribute('aria-selected', String(i === this._active));
        });
        const activeEl = document.getElementById('cmd-item-' + this._active);
        if (activeEl) {
            this._input.setAttribute('aria-activedescendant', activeEl.id);
            activeEl.scrollIntoView({ block: 'nearest' });
        }
    },

    _onKey(e) {
        if (e.key === 'Escape') { e.preventDefault(); this.close(); return; }
        if (e.key === 'ArrowDown') { e.preventDefault(); this._move(1); return; }
        if (e.key === 'ArrowUp') { e.preventDefault(); this._move(-1); return; }
        if (e.key === 'Enter') {
            e.preventDefault();
            const cmd = this._filtered[this._active];
            if (cmd) this._run(cmd);
        }
    },

    _run(cmd) {
        this.close();
        // 先关面板再执行：命令可能会切页或改动 DOM
        try { cmd.run(); } catch (err) { console.warn('[CommandPalette] 执行失败', err); }
    },
};
