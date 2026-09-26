import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { Notify } from './notify.js';
import { I18n } from './i18n.js';

export const Agent = {
    _abortController: null,
    _screenshots: [],
    _currentIndex: 0,
    _progressInterval: null,

    init() {
        const startBtn = document.getElementById("agentStartBtn");
        const cancelBtn = document.getElementById("agentCancelBtn");
        const textarea = document.getElementById("agentInstruction");

        if (startBtn) startBtn.onclick = () => this.execute();
        if (cancelBtn) cancelBtn.onclick = () => this.cancel();

        if (textarea) {
            textarea.onkeydown = (e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    if (!startBtn.disabled) this.execute();
                }
            };
        }

        const strip = document.getElementById("agentScreenshotStrip");
        if (strip) {
            strip.onclick = (e) => {
                if (e.target.tagName === 'IMG') {
                    const idx = parseInt(e.target.dataset.index);
                    if (!isNaN(idx)) this._showScreenshot(idx);
                }
            };
        }
    },

    async execute() {
        const textarea = document.getElementById("agentInstruction");
        const startBtn = document.getElementById("agentStartBtn");
        const cancelBtn = document.getElementById("agentCancelBtn");
        const maxStepsInput = document.getElementById("agentMaxSteps");

        const instruction = textarea.value.trim();
        if (!instruction) { Notify.warn ? Notify.warn(I18n.t('agent.emptyInstruction')) : Utils.showToast(I18n.t('agent.emptyInstruction'), 'warn'); return; }

        this._resetUI();
        document.getElementById("agentStatusCard").classList.remove("hidden");
        document.getElementById("agentMaxStepsDisplay").textContent = maxStepsInput.value;
        document.getElementById("agentProgressFill").style.width = "0%";

        startBtn.disabled = true;
        cancelBtn.classList.remove("hidden");

        this._abortController = new AbortController();
        const timer = setTimeout(() => this._abortController.abort(), 600_000);

        try {
            const token = Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY);
            const res = await fetch(`${CONFIG.API_BASE_URL}/agent/execute`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`,
                },
                body: JSON.stringify({
                    instruction,
                    max_steps: parseInt(maxStepsInput.value) || 25,
                }),
                signal: this._abortController.signal,
            });

            clearTimeout(timer);
            const data = await res.json();

            document.getElementById("agentStatusCard").classList.add("hidden");
            this._stopProgress();
            document.getElementById("agentProgressFill").style.width = "100%";
            this._displayResult(data);
        } catch (e) {
            clearTimeout(timer);
            document.getElementById("agentStatusCard").classList.add("hidden");
            this._stopProgress();

            if (e.name === 'AbortError') {
                this._showError(I18n.t('agent.timeout'));
            } else {
                this._showError(`${I18n.t('agent.networkError')}：${Utils.escapeHtml(e.message)}`);
            }
        } finally {
            startBtn.disabled = false;
            cancelBtn.classList.add("hidden");
            this._abortController = null;
        }
    },

    cancel() {
        if (this._abortController) {
            this._abortController.abort();
            this._stopProgress();
            document.getElementById("agentStatusCard").classList.add("hidden");
            document.getElementById("agentStartBtn").disabled = false;
            document.getElementById("agentCancelBtn").classList.add("hidden");
        }
    },

    /* ---- UI ---- */
    _resetUI() {
        document.getElementById("agentResultCard").classList.add("hidden");
        document.getElementById("agentScreenshotMain").innerHTML = `
            <div class="agent-screenshot-placeholder">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:12px;opacity:0.4;"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                <p>${I18n.t('agent.executingPlaceholder')}</p>
            </div>`;
        document.getElementById("agentScreenshotStrip").classList.add("hidden");
        document.getElementById("agentScreenshotStrip").innerHTML = "";
        document.getElementById("agentScreenshotCount").textContent = "";
        this._screenshots = [];
        this._currentIndex = 0;

        document.getElementById("agentStatusText").textContent = I18n.t('agent.executing');
        document.getElementById("agentStepCount").textContent = "0";
        document.getElementById("agentDuration").textContent = "0s";

        let width = 0;
        this._progressInterval = setInterval(() => {
            width += Math.random() * 12;
            if (width > 90) width = 90;
            const bar = document.getElementById("agentProgressFill");
            if (bar) bar.style.width = Math.min(width, 90) + "%";
        }, 1000);
    },

    _stopProgress() {
        if (this._progressInterval) {
            clearInterval(this._progressInterval);
            this._progressInterval = null;
        }
    },

    _displayResult(data) {
        const resultCard = document.getElementById("agentResultCard");
        resultCard.classList.remove("hidden");

        const badge = document.getElementById("agentResultBadge");
        badge.textContent = data.success ? I18n.t('agent.completed') : I18n.t('agent.failed');
        badge.className = `status-badge ${data.success ? 'success' : 'error'}`;

        document.getElementById("agentStepCount").textContent = data.total_steps || 0;
        document.getElementById("agentDuration").textContent = `${data.duration_seconds || 0}s`;

        const content = document.getElementById("agentResultContent");
        content.innerHTML = Utils.parseMarkdown(data.final_result || I18n.t('agent.noResult'));

        this._screenshots = data.screenshots || [];
        if (this._screenshots.length > 0) {
            document.getElementById("agentScreenshotCount").textContent = `(${this._screenshots.length})`;
            this._showScreenshot(0);
            this._renderScreenshotStrip();
        } else {
            document.getElementById("agentScreenshotMain").innerHTML =
                `<div class="agent-screenshot-placeholder"><p>${I18n.t('agent.noScreenshots')}</p></div>`;
        }

        const errorList = document.getElementById("agentErrorList");
        if (data.errors && data.errors.length > 0) {
            errorList.classList.remove("hidden");
            errorList.innerHTML = '<strong>' + I18n.t('agent.errors') + '：</strong><br>' +
                data.errors.map(e => Utils.escapeHtml(e)).join('<br>');
        } else {
            errorList.classList.add("hidden");
        }
    },

    _showError(message) {
        const resultCard = document.getElementById("agentResultCard");
        resultCard.classList.remove("hidden");
        document.getElementById("agentResultBadge").textContent = I18n.t('agent.failed');
        document.getElementById("agentResultBadge").className = "status-badge error";
        document.getElementById("agentResultContent").textContent = message;
    },

    _showScreenshot(index) {
        if (index < 0 || index >= this._screenshots.length) return;
        this._currentIndex = index;

        const b64 = this._screenshots[index];
        const src = b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`;

        document.getElementById("agentScreenshotMain").innerHTML =
            `<img src="${src}" alt="Screenshot ${index + 1}" loading="lazy">`;

        document.querySelectorAll("#agentScreenshotStrip img").forEach((img, i) => {
            img.classList.toggle("active", i === index);
        });
    },

    _renderScreenshotStrip() {
        const strip = document.getElementById("agentScreenshotStrip");
        strip.classList.remove("hidden");
        strip.innerHTML = this._screenshots.map((b64, i) => {
            const src = b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`;
            return `<img src="${src}" alt="Step ${i + 1}" data-index="${i}" class="${i === 0 ? 'active' : ''}" loading="lazy">`;
        }).join('');
    },
};
