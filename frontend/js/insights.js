import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { I18n } from './i18n.js';
import { Auth } from './auth.js';
import { Toast } from './toast.js';

/**
 * 前沿资讯：arXiv 农业遥感新论文。
 *
 * 论文标题与摘要是外部数据，一律用 textContent 写进 DOM，不拼 innerHTML ——
 * 拼字符串的话 arXiv 标题里一个 < 就能变成标签。
 */
export const Insights = {
    _loaded: false,

    init() {
        const btn = document.getElementById('insightsRefreshBtn');
        if (btn) btn.onclick = () => this.render(true);
    },

    async render(force) {
        const list = document.getElementById('insightsPapers');
        if (!list) return;
        if (this._loaded && !force) return;

        list.textContent = '';
        const loading = document.createElement('p');
        loading.className = 'ins-placeholder';
        loading.textContent = I18n.t('insights.loading');
        list.appendChild(loading);

        try {
            const url =
                `${CONFIG.API_BASE_URL}/insights/papers` + (force ? '?refresh=1' : '');
            const res = await Utils.fetchWithTimeout(url);
            const body = await res.json();
            const data = (body && body.data) || {};
            const items = data.items || [];

            list.textContent = '';
            if (!items.length) {
                const empty = document.createElement('p');
                empty.className = 'ins-placeholder';
                empty.textContent = I18n.t('insights.empty');
                list.appendChild(empty);
            } else {
                items.forEach((p) => list.appendChild(this._paperNode(p)));
            }

            this._setMeta(data);
            this._loaded = true;
        } catch {
            list.textContent = '';
            const err = document.createElement('p');
            err.className = 'ins-placeholder';
            err.textContent = I18n.t('insights.loadFailed');
            list.appendChild(err);
        }
    },

    _setMeta(data) {
        const el = document.getElementById('insightsMeta');
        if (!el) return;
        const parts = [];
        if (data.source) parts.push(data.source);
        if (data.fetched_at) parts.push(data.fetched_at.slice(0, 16).replace('T', ' '));
        if (data.stale) parts.push(I18n.t('insights.stale'));
        el.textContent = parts.join(' · ');
    },

    _paperNode(p) {
        const card = document.createElement('article');
        card.className = 'ins-paper';

        const head = document.createElement('div');
        head.className = 'ins-paper-head';

        const date = document.createElement('span');
        date.className = 'ins-date';
        date.textContent = p.published || '';
        head.appendChild(date);

        const title = document.createElement('a');
        title.className = 'ins-title';
        title.href = p.url;
        title.target = '_blank';
        title.rel = 'noopener noreferrer';
        title.textContent = p.title;
        head.appendChild(title);
        card.appendChild(head);

        if (p.authors && p.authors.length) {
            const au = document.createElement('p');
            au.className = 'ins-authors';
            au.textContent = p.authors.join(' · ');
            card.appendChild(au);
        }

        const abs = document.createElement('p');
        abs.className = 'ins-abstract';
        abs.textContent = p.abstract;
        card.appendChild(abs);

        const actions = document.createElement('div');
        actions.className = 'ins-actions';

        const sum = document.createElement('button');
        sum.className = 'ins-btn';
        sum.type = 'button';
        sum.textContent = I18n.t('insights.summarize');
        sum.onclick = () => this._summarize(p.id, sum, card);
        actions.appendChild(sum);

        const pdf = document.createElement('a');
        pdf.className = 'ins-btn ins-btn-link';
        pdf.href = p.pdf;
        pdf.target = '_blank';
        pdf.rel = 'noopener noreferrer';
        pdf.textContent = 'PDF';
        actions.appendChild(pdf);

        card.appendChild(actions);
        return card;
    },

    async _summarize(arxivId, btn, card) {
        // 这一步是真实付费的 LLM 调用，只对登录用户开放
        if (!Auth.isLoggedIn()) {
            Auth.showAuthOverlay('login');
            return;
        }

        const old = card.querySelector('.ins-summary');
        if (old) old.remove();

        const out = document.createElement('p');
        out.className = 'ins-summary';
        out.textContent = I18n.t('insights.summarizing');
        card.appendChild(out);

        btn.disabled = true;
        try {
            const res = await Utils.authFetch(
                `${CONFIG.API_BASE_URL}/insights/papers/${encodeURIComponent(arxivId)}/summary`,
                { method: 'POST' }
            );
            const body = await res.json();
            if (!res.ok) throw new Error((body && body.detail) || res.status);
            out.textContent = body.data.summary;
            out.classList.add('ready');
        } catch (e) {
            out.textContent = I18n.t('insights.summaryFailed');
            Toast.error(String(e.message || e));
        } finally {
            btn.disabled = false;
        }
    },
};
