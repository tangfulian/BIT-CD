import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { Notify } from './notify.js';
import { I18n } from './i18n.js';

export const Agent = {
    _abortController: null,
    _screenshots: [],
    _currentIndex: 0,
    _progressInterval: null,
    // 默认走工具通道：它不经浏览器，一次任务通常 1~3 轮、十几秒即可完成。
    _mode: 'tools',
    TOOL_MAX_ROUNDS: 8,

    init() {
        const startBtn = document.getElementById("agentStartBtn");
        const cancelBtn = document.getElementById("agentCancelBtn");
        const textarea = document.getElementById("agentInstruction");

        if (startBtn) startBtn.onclick = () => this.execute();
        if (cancelBtn) cancelBtn.onclick = () => this.cancel();

        const modeTools = document.getElementById("agentModeTools");
        const modeBrowser = document.getElementById("agentModeBrowser");
        if (modeTools) modeTools.onclick = () => this._setMode('tools');
        if (modeBrowser) modeBrowser.onclick = () => this._setMode('browser');
        this._setMode(this._mode);

        if (textarea) {
            textarea.onkeydown = (e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    if (!startBtn.disabled) this.execute();
                }
            };
        }

        const fileInput = document.getElementById("agentFiles");
        if (fileInput) fileInput.onchange = () => this._renderFileList();

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

        const isTools = this._mode === 'tools';

        this._resetUI();
        document.getElementById("agentStatusCard").classList.remove("hidden");
        document.getElementById("agentMaxStepsDisplay").textContent =
            isTools ? String(this.TOOL_MAX_ROUNDS) : maxStepsInput.value;
        document.getElementById("agentProgressFill").style.width = "0%";

        startBtn.disabled = true;
        cancelBtn.classList.remove("hidden");

        this._abortController = new AbortController();
        const timer = setTimeout(() => this._abortController.abort(), 600_000);

        try {
            const token = Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY);

            const fd = new FormData();
            fd.append('instruction', instruction);
            if (isTools) {
                fd.append('max_rounds', String(this.TOOL_MAX_ROUNDS));
            } else {
                fd.append('max_steps', String(parseInt(maxStepsInput.value) || 25));
            }
            const fileInput = document.getElementById("agentFiles");
            if (fileInput && fileInput.files) {
                Array.from(fileInput.files).forEach((f) => fd.append('files', f));
            }

            const endpoint = isTools ? '/agent/execute-tools' : '/agent/execute';
            const res = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
                method: "POST",
                // 刻意不设 Content-Type：multipart 的 boundary 必须由浏览器生成，
                // 手写这个头会让后端解析不到任何文件（收到空附件且不报错）。
                headers: { "Authorization": `Bearer ${token}` },
                body: fd,
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

    /* ---- 执行方式 ---- */
    /**
     * 两种通道的界面差异：
     *   工具调用：无截图，右栏换成工具调用轨迹；无最大步数（轮次由服务端封顶）
     *   浏览器操控：保留截图与最大步数（步数是这个通道专有的概念）
     */
    _setMode(mode) {
        this._mode = mode === 'browser' ? 'browser' : 'tools';
        const isTools = this._mode === 'tools';

        const toolsBtn = document.getElementById("agentModeTools");
        const browserBtn = document.getElementById("agentModeBrowser");
        // 保留 agent-mode-btn：btn-primary 是通栏按钮，没有它这个类
        // 放进一行里会被拉满（见 styles.css 里该类的说明）
        if (toolsBtn) toolsBtn.className = (isTools ? 'btn-primary' : 'btn-gray') + ' agent-mode-btn';
        if (browserBtn) browserBtn.className = (isTools ? 'btn-gray' : 'btn-primary') + ' agent-mode-btn';

        const hint = document.getElementById("agentModeHint");
        if (hint) hint.textContent = I18n.t(isTools ? 'agent.modeToolsHint' : 'agent.modeBrowserHint');

        const stepsGroup = document.getElementById("agentMaxStepsGroup");
        if (stepsGroup) stepsGroup.style.display = isTools ? 'none' : 'flex';

        const title = document.getElementById("agentPanelTitle");
        if (title) title.textContent = I18n.t(isTools ? 'agent.toolTrace' : 'agent.screenshots');

        const main = document.getElementById("agentScreenshotMain");
        const strip = document.getElementById("agentScreenshotStrip");
        const trace = document.getElementById("agentToolTrace");
        if (trace) trace.classList.add("hidden");
        if (main) main.classList.toggle("hidden", isTools);
        if (strip && isTools) strip.classList.add("hidden");
        if (trace && isTools) {
            trace.textContent = '';
            trace.classList.remove("hidden");
        }
        const count = document.getElementById("agentScreenshotCount");
        if (count) count.textContent = "";
    },

    /** 渲染工具调用轨迹。
     *  参数与结果里都可能含用户数据（地块位置、文件名），一律转义后再插入。 */
    _renderToolTrace(trace) {
        const box = document.getElementById("agentToolTrace");
        if (!box) return;
        box.classList.remove("hidden");
        if (!trace.length) {
            box.innerHTML = `<div class="agent-screenshot-placeholder"><p>${Utils.escapeHtml(I18n.t('agent.noToolCalls'))}</p></div>`;
            return;
        }
        box.innerHTML = trace.map((step) => {
            const color = step.ok ? '#16a34a' : '#dc2626';
            const mark = step.ok ? '✓' : '✗';
            const args = Utils.escapeHtml(JSON.stringify(step.arguments || {}));
            const summary = Utils.escapeHtml(step.summary || '');
            return `<div style="margin-bottom:14px;">
                <div><strong style="color:${color};">${mark}</strong>
                     <code>${Utils.escapeHtml(step.tool || '')}</code></div>
                <div style="font-size:12px;opacity:0.7;margin-top:4px;word-break:break-all;">${args}</div>
                <div style="font-size:12px;margin-top:4px;word-break:break-all;">${summary}</div>
            </div>`;
        }).join('');
    },

    /** 渲染已选附件列表（只显示文件名与大小，不做预览也不上传） */
    _renderFileList() {
        const box = document.getElementById("agentFileList");
        const input = document.getElementById("agentFiles");
        if (!box || !input) return;
        const files = Array.from(input.files || []);
        if (!files.length) {
            box.innerHTML = '';
            return;
        }
        box.innerHTML = files.map((f, i) => {
            const kb = (f.size / 1024).toFixed(1);
            return `<div class="agent-file-item">
                <span class="agent-file-name">${Utils.escapeHtml(f.name)}</span>
                <span class="agent-file-size">${kb} KB</span>
                <button type="button" class="agent-file-remove" data-idx="${i}">×</button>
            </div>`;
        }).join('');
        box.querySelectorAll('.agent-file-remove').forEach((btn) => {
            btn.onclick = () => {
                const idx = parseInt(btn.dataset.idx, 10);
                const dt = new DataTransfer();
                files.forEach((f, i) => { if (i !== idx) dt.items.add(f); });
                input.files = dt.files;
                this._renderFileList();
            };
        });
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

        const traceBox = document.getElementById("agentToolTrace");
        if (traceBox) {
            if (this._mode === 'tools') {
                traceBox.innerHTML = `<div class="agent-screenshot-placeholder"><p>${Utils.escapeHtml(I18n.t('agent.toolPlaceholder'))}</p></div>`;
                traceBox.classList.remove("hidden");
            } else {
                traceBox.classList.add("hidden");
                traceBox.textContent = "";
            }
        }

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
        // 必须先转义：这段文字是模型写的，而模型读过被浏览页面的内容，
        // 页面里塞一句让模型照抄的 <img onerror=...> 就能在管理员浏览器里
        // 以同源身份执行，进而读走 localStorage 里的管理员令牌。
        // parseMarkdown 自身不做任何转义（只加 <strong>/<br>），所以顺序是
        // 先 escapeHtml 再 parseMarkdown —— 后者插入的标签是我们自己的，安全。
        content.innerHTML = Utils.parseMarkdown(
            Utils.escapeHtml(data.final_result || I18n.t('agent.noResult')));

        if (this._mode === 'tools') {
            // 工具通道不产生截图，右栏改为展示调用轨迹
            this._screenshots = [];
            const trace = data.tool_trace || [];
            this._renderToolTrace(trace);
            document.getElementById("agentScreenshotCount").textContent =
                trace.length ? `(${trace.length})` : "";
        } else {
            this._screenshots = data.screenshots || [];
            if (this._screenshots.length > 0) {
                document.getElementById("agentScreenshotCount").textContent = `(${this._screenshots.length})`;
                this._showScreenshot(0);
                this._renderScreenshotStrip();
            } else {
                document.getElementById("agentScreenshotMain").innerHTML =
                    `<div class="agent-screenshot-placeholder"><p>${I18n.t('agent.noScreenshots')}</p></div>`;
            }
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
