import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { I18n } from './i18n.js';

export const Annotator = {
    canvas: null,
    ctx: null,
    painting: false,
    brushSize: 8,
    eraseMode: false,
    detectionId: null,
    originalMaskUrl: null,

    init() {},

    open(detectionId, maskUrl) {
        this.detectionId = detectionId;
        this.originalMaskUrl = maskUrl;
        this._history = [];  // 撤销栈

        const { overlay, close } = Modal.createOverlay(`
            <div class="modal-box annotator-modal-box">
                <div class="modal-title">${I18n.t('annotate.title', '修正变化掩膜')}</div>
                <div class="modal-content annotator-modal-content">
                    <div class="annotator-toolbar">
                        <button class="btn-small-action active" id="drawModeBtn" data-mode="draw">${I18n.t('annotate.draw', '绘制')}</button>
                        <button class="btn-small-action" id="eraseModeBtn" data-mode="erase">${I18n.t('annotate.erase', '橡皮')}</button>
                        <label class="annotator-brush-label">${I18n.t('annotate.brushSize', '大小：')}</label>
                        <input type="range" id="brushSizeRange" min="2" max="30" value="8">
                        <span id="brushSizeLabel" class="annotator-brush-value">8</span>
                        <button class="btn-small-action" id="undoAnnoBtn">${I18n.t('common.retry', '撤销')}</button>
                    </div>
                    <canvas id="annoCanvas" width="512" height="512"></canvas>
                    <div class="annotator-hint">${I18n.t('annotate.hint', '画笔=添加变化区域（白色） | 橡皮=移除变化区域（黑色）')} | 快捷键: D=画笔 E=橡皮 Ctrl+Z=撤销 Ctrl+S=保存</div>
                </div>
                <div class="modal-footer annotator-modal-footer">
                    <button class="btn-modal btn-modal-secondary" id="cancelAnnoBtn">${I18n.t('common.cancel')}</button>
                    <button class="btn-modal btn-modal-primary" id="saveAnnoBtn">${I18n.t('annotate.save', '保存修正')}</button>
                </div>
            </div>
        `);

        this.canvas = document.getElementById('annoCanvas');
        this.ctx = this.canvas.getContext('2d');
        this.painting = false;
        this.eraseMode = false;

        this._loadMaskImage(maskUrl);
        this._bindEvents(overlay, close);
    },

    _absUrl(url) {
        if (!url || url.startsWith('http') || url.startsWith('blob:') || url.startsWith('data:')) return url;
        return (CONFIG.API_BASE_URL + '/' + url.replace(/^\//, '')).replace(/([^:]);$/, '$1');
    },

    _loadMaskImage(url) {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            this.canvas.width = img.width;
            this.canvas.height = img.height;
            this.ctx.drawImage(img, 0, 0);
        };
        img.src = this._absUrl(url);
    },

    _bindEvents(overlay, close) {
        const canvas = this.canvas;

        canvas.onmousedown = (e) => {
            this.painting = true;
            this._history.push(this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height));
            if (this._history.length > 30) this._history.shift();
            this._draw(e);
        };
        canvas.onmouseup = () => { this.painting = false; this.ctx.beginPath(); };
        canvas.onmouseleave = () => { this.painting = false; this.ctx.beginPath(); };
        canvas.onmousemove = (e) => {
            if (!this.painting) return;
            this._draw(e);
        };

        document.getElementById('drawModeBtn').onclick = () => {
            this.eraseMode = false;
            document.getElementById('drawModeBtn').classList.add('active');
            document.getElementById('eraseModeBtn').classList.remove('active');
        };
        document.getElementById('eraseModeBtn').onclick = () => {
            this.eraseMode = true;
            document.getElementById('eraseModeBtn').classList.add('active');
            document.getElementById('drawModeBtn').classList.remove('active');
        };

        const brushSizeRange = document.getElementById('brushSizeRange');
        brushSizeRange.oninput = () => {
            this.brushSize = parseInt(brushSizeRange.value);
            document.getElementById('brushSizeLabel').textContent = this.brushSize;
        };

        document.getElementById('cancelAnnoBtn').onclick = close;
        document.getElementById('saveAnnoBtn').onclick = () => this._save(close);
        document.getElementById('undoAnnoBtn').onclick = () => this._undo();

        // 键盘快捷键
        this._onKeyDown = (e) => {
            if (e.ctrlKey && e.key === 'z') { e.preventDefault(); this._undo(); }
            if (e.ctrlKey && e.key === 's') { e.preventDefault(); this._save(close); }
            if (e.key === 'd' || e.key === 'D') {
                this.eraseMode = false;
                document.getElementById('drawModeBtn').classList.add('active');
                document.getElementById('eraseModeBtn').classList.remove('active');
            }
            if (e.key === 'e' || e.key === 'E') {
                this.eraseMode = true;
                document.getElementById('eraseModeBtn').classList.add('active');
                document.getElementById('drawModeBtn').classList.remove('active');
            }
            if (e.key === '[') {
                this.brushSize = Math.max(2, this.brushSize - 2);
                document.getElementById('brushSizeRange').value = this.brushSize;
                document.getElementById('brushSizeLabel').textContent = this.brushSize;
            }
            if (e.key === ']') {
                this.brushSize = Math.min(30, this.brushSize + 2);
                document.getElementById('brushSizeRange').value = this.brushSize;
                document.getElementById('brushSizeLabel').textContent = this.brushSize;
            }
        };
        document.addEventListener('keydown', this._onKeyDown);
        const origClose = close;
        close = () => {
            document.removeEventListener('keydown', this._onKeyDown);
            origClose();
        };
    },

    _draw(e) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        this.ctx.lineWidth = this.brushSize;
        this.ctx.lineCap = 'round';
        this.ctx.strokeStyle = this.eraseMode ? '#000' : '#fff';
        this.ctx.lineTo(x, y);
        this.ctx.stroke();
        this.ctx.beginPath();
        this.ctx.moveTo(x, y);
    },

    _undo() {
        if (this._history.length === 0) return;
        const prev = this._history.pop();
        this.ctx.putImageData(prev, 0, 0);
    },

    async _save(close) {
        try {
            const base64 = this.canvas.toDataURL('image/png');
            const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/annotation/${this.detectionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ annotation_data: base64 })
            });
            const data = await res.json();
            if (data.code === 200) {
                if (!state.currentDetectResult._original_mask_url) {
                    state.currentDetectResult._original_mask_url = state.currentDetectResult.mask_url;
                }
                state.currentDetectResult.mask_url = base64;
                state.persist();

                const maskImg = document.getElementById('resultMask');
                if (maskImg) maskImg.src = base64;

                const revertBtn = document.getElementById('revertMaskBtn');
                if (revertBtn) revertBtn.style.display = 'inline-flex';

                Modal.alert(I18n.t('annotate.saved'));
                close();
            } else {
                throw new Error(data.detail || I18n.t('common.error'));
            }
        } catch (e) {
            if (e instanceof DOMException && e.name === 'SecurityError') {
                Modal.alert(I18n.t('annotate.corsError', '图片跨域导致无法保存，请联系管理员'));
            } else {
                Modal.alert(`${I18n.t('annotate.saveFailed', '标注保存失败')}：${e.message}`);
            }
        }
    }
};
