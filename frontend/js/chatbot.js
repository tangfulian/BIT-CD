import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Notify } from './notify.js';
import { I18n } from './i18n.js';

export const Chatbot = {
    _dragState: null,
    _saveTimer: null,

    init() {
        document.getElementById("chatbotToggle").onclick = (e) => {
            if (this._justDragged) { this._justDragged = false; return; }
            this.toggleWindow();
        };
        document.getElementById("chatbotClose").onclick = () => this.toggleWindow();
        document.getElementById("chatbotSend").onclick = () => this.send();
        document.getElementById("chatbotInput").onkeypress = (e) => {
            if (e.key === 'Enter') this.send();
        };

        this._setupToggleDrag();
        this._setupWindowResize();
        this._restorePosition();
    },

    toggleWindow() {
        document.getElementById("chatbotWindow").classList.toggle("show");
    },

    /* ---- 拖拽图标移动整个悬浮窗 ---- */
    _setupToggleDrag() {
        const btn = document.getElementById("chatbotToggle");
        const widget = document.getElementById("chatbotWidget");

        btn.style.cursor = "grab";
        btn.style.touchAction = "none";

        let startX, startY, startRight, startBottom, moved;

        const onDown = (e) => {
            const p = e.touches ? e.touches[0] : e;
            startX = p.clientX;
            startY = p.clientY;
            const rect = widget.getBoundingClientRect();
            startRight = window.innerWidth - rect.right;
            startBottom = window.innerHeight - rect.bottom;
            moved = false;
            btn.style.cursor = "grabbing";
            widget.style.transition = "none";
            e.preventDefault();
        };

        const onMove = (e) => {
            if (startX === undefined) return;
            const p = e.touches ? e.touches[0] : e;
            const dx = startX - p.clientX;
            const dy = startY - p.clientY;
            if (Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
            moved = true;
            widget.style.right = Math.max(0, Math.min(startRight + dx, window.innerWidth - 60)) + "px";
            widget.style.bottom = Math.max(0, Math.min(startBottom + dy, window.innerHeight - 60)) + "px";
        };

        const onUp = () => {
            if (startX === undefined) return;
            startX = undefined;
            btn.style.cursor = "grab";
            widget.style.transition = "";
            if (moved) {
                this._justDragged = true;
                this._scheduleSave();
            }
        };

        btn.addEventListener("mousedown", onDown);
        btn.addEventListener("touchstart", onDown, { passive: false });
        document.addEventListener("mousemove", onMove);
        document.addEventListener("touchmove", onMove, { passive: false });
        document.addEventListener("mouseup", onUp);
        document.addEventListener("touchend", onUp);
    },

    /* ---- 窗口右下角缩放 ---- */
    _setupWindowResize() {
        const win = document.getElementById("chatbotWindow");
        const handle = win.querySelector(".chatbot-resize-handle");
        if (!handle) return;

        let startX, startY, startW, startH;

        handle.addEventListener("mousedown", (e) => {
            startX = e.clientX;
            startY = e.clientY;
            startW = win.offsetWidth;
            startH = win.offsetHeight;
            win.classList.add("resizing");
            e.preventDefault();
            e.stopPropagation();
        });

        document.addEventListener("mousemove", (e) => {
            if (startX === undefined) return;
            const maxW = Math.min(window.innerWidth - 32, 900);
            const maxH = Math.min(window.innerHeight - 100, 800);
            win.style.width = Math.max(320, Math.min(startW + (e.clientX - startX), maxW)) + "px";
            win.style.height = Math.max(360, Math.min(startH + (e.clientY - startY), maxH)) + "px";
        });

        const endResize = () => {
            if (startX === undefined) return;
            startX = undefined;
            win.classList.remove("resizing");
            this._scheduleSave();
        };
        document.addEventListener("mouseup", endResize);
    },

    _scheduleSave() {
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => this._persistPosition(), 300);
    },

    _persistPosition() {
        try {
            const widget = document.getElementById("chatbotWidget");
            const win = document.getElementById("chatbotWindow");
            localStorage.setItem("chatbot_layout", JSON.stringify({
                r: widget.style.right || "",
                b: widget.style.bottom || "",
                w: win.style.width || "",
                h: win.style.height || "",
            }));
        } catch (e) { /* ignore */ }
    },

    _restorePosition() {
        try {
            const raw = localStorage.getItem("chatbot_layout");
            if (!raw) return;
            const pos = JSON.parse(raw);
            const widget = document.getElementById("chatbotWidget");
            const win = document.getElementById("chatbotWindow");
            if (pos.r) widget.style.right = pos.r;
            if (pos.b) widget.style.bottom = pos.b;
            if (pos.w) win.style.width = pos.w;
            if (pos.h) win.style.height = pos.h;
        } catch (e) { /* ignore */ }
    },

    /* ---- 消息 ---- */
    addMessage(content, isUser) {
        const container = document.getElementById("chatbotMessages");
        const div = document.createElement("div");
        div.className = `chat-message ${isUser ? 'user' : 'ai'}`;
        div.innerHTML = isUser ? content : Utils.parseMarkdown(content);
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    async send() {
        const input = document.getElementById("chatbotInput");
        const sendBtn = document.getElementById("chatbotSend");
        const text = input.value.trim();
        if (!text) return;

        // ── Agent 操控模式 → 引导到 AI Agent 页面 ──
        const AGENT_PREFIX_RE = /^(操作|操控|agent)[：:]\s*/i;
        if (AGENT_PREFIX_RE.test(text)) {
            this.addMessage(text, true);
            input.value = "";
            const hintDiv = document.createElement("div");
            hintDiv.className = "chat-message ai";
            hintDiv.innerHTML = `<p>${I18n.t('agent.hintFromChat')}</p>
                <p style="margin-top:6px;font-size:12px;"><a href="javascript:void(0)" onclick="document.querySelector('.nav-item[data-page=\\'agent\\']').click()" style="color:var(--primary);text-decoration:underline;">${I18n.t('agent.hintOpenLink')}</a></p>`;
            document.getElementById("chatbotMessages").appendChild(hintDiv);
            document.getElementById("chatbotMessages").scrollTop = document.getElementById("chatbotMessages").scrollHeight;
            return;
        }

        this.addMessage(text, true);
        input.value = "";
        sendBtn.disabled = true;

        const placeholder = document.createElement("div");
        placeholder.className = "chat-message ai";
        placeholder.textContent = I18n.t('chat.thinking');
        document.getElementById("chatbotMessages").appendChild(placeholder);

        try {
            const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/ai/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_input: text,
                    history: state.chatHistory
                })
            });
            const data = await res.json();
            placeholder.remove();

            if (data.code === 200) {
                this.addMessage(data.reply, false);
                Notify.aiReply(data.reply?.substring(0, 60));
                state.chatHistory.push({ role: "user", content: text });
                state.chatHistory.push({ role: "assistant", content: data.reply });
            } else {
                throw new Error(data.error || "AI服务异常");
            }
        } catch (e) {
            placeholder.textContent = `${I18n.t('chat.error')}：${e.message}`;
        } finally {
            sendBtn.disabled = false;
        }
    },

};
