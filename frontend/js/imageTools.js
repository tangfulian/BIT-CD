/**
 * 影像预处理工具 - 裁切、旋转、缩放
 * @module imageTools
 */
import { I18n } from './i18n.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';

export const ImageTools = {
    _sourceImg: null,
    _canvas: null,
    _rotation: 0,
    _crop: null,
    _zoom: 1,

    init() {
        // Tools are invoked on-demand via this.open(imgElement/file)
    },

    /** 打开影像预处理弹窗 */
    open(sourceImgEl) {
        this._sourceImg = sourceImgEl;
        this._rotation = 0;
        this._crop = null;
        this._zoom = 1;
        this._renderModal();
    },

    _renderModal() {
        const html = [
            '<div class="modal-box" style="max-width:750px;">',
                '<div class="modal-title">' + I18n.t('imageTools.title') + '</div>',
                '<div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;">',
                    '<button class="btn-small-action" id="itRotateLeft" title="' + I18n.t('imageTools.rotateLeft') + '">↺ -90°</button>',
                    '<button class="btn-small-action" id="itRotateRight" title="' + I18n.t('imageTools.rotateRight') + '">↻ +90°</button>',
                    '<button class="btn-small-action" id="itFlipH" title="' + I18n.t('imageTools.flipH') + '">↔ ' + I18n.t('imageTools.flipH') + '</button>',
                    '<button class="btn-small-action" id="itFlipV" title="' + I18n.t('imageTools.flipV') + '">↕ ' + I18n.t('imageTools.flipV') + '</button>',
                    '<button class="btn-small-secondary" id="itReset" title="' + I18n.t('common.reset') + '">' + I18n.t('common.reset') + '</button>',
                    '<span style="font-size:13px;color:var(--text-tertiary);display:flex;align-items:center;">' + I18n.t('imageTools.cropHint') + '</span>',
                '</div>',
                '<div id="itCanvasContainer" style="position:relative;overflow:hidden;background:#1a231e;border-radius:var(--radius-md);min-height:300px;display:flex;align-items:center;justify-content:center;">',
                    '<canvas id="itCanvas" style="max-width:100%;max-height:500px;cursor:crosshair;"></canvas>',
                '</div>',
                '<div id="itCropInfo" style="margin-top:8px;font-size:12px;color:var(--text-secondary);text-align:center;"></div>',
                '<div class="modal-footer" style="margin-top:16px;">',
                    '<button class="btn-modal-secondary" id="itCancel">' + I18n.t('common.cancel') + '</button>',
                    '<button class="btn-modal-primary" id="itDownload">' + I18n.t('common.download') + '</button>',
                    '<button class="btn-modal-primary" id="itCropDownload" style="display:none;">' + I18n.t('imageTools.downloadCrop') + '</button>',
                '</div>',
            '</div>'
        ].join('');

        const { overlay, close } = Modal.createOverlay(html);

        // Wait for DOM
        setTimeout(() => {
            this._initCanvas();
            overlay.querySelector('#itRotateLeft').onclick = () => { this._rotation -= 90; this._redraw(); };
            overlay.querySelector('#itRotateRight').onclick = () => { this._rotation += 90; this._redraw(); };
            overlay.querySelector('#itFlipH').onclick = () => { this._flipH = !this._flipH; this._redraw(); };
            overlay.querySelector('#itFlipV').onclick = () => { this._flipV = !this._flipV; this._redraw(); };
            overlay.querySelector('#itReset').onclick = () => { this._rotation = 0; this._flipH = false; this._flipV = false; this._crop = null; this._zoom = 1; this._redraw(); };
            overlay.querySelector('#itCancel').onclick = close;
            overlay.querySelector('#itDownload').onclick = () => this._download();
            overlay.querySelector('#itCropDownload').onclick = () => this._downloadCropped();
        }, 100);
    },

    _initCanvas() {
        const canvas = document.getElementById('itCanvas');
        if (!canvas) return;
        this._canvas = canvas;
        const ctx = canvas.getContext('2d');

        const img = this._sourceImg;
        if (!img || !img.complete || img.naturalWidth === 0) {
            canvas.width = 700;
            canvas.height = 300;
            ctx.fillStyle = '#3a3a3a';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#888';
            ctx.font = '14px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(I18n.t('imageTools.invalidImage'), canvas.width / 2, canvas.height / 2);
            return;
        }
        let w = img.naturalWidth || img.width;
        let h = img.naturalHeight || img.height;
        const maxW = 700, maxH = 500;
        const scale = Math.min(maxW / w, maxH / h, 1);
        canvas.width = w * scale;
        canvas.height = h * scale;
        this._baseScale = scale;

        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        this._setupCropEvents();
    },

    _setupCropEvents() {
        const canvas = this._canvas;
        if (!canvas) return;
        let dragging = false, startX = 0, startY = 0;

        canvas.onmousedown = (e) => {
            const rect = canvas.getBoundingClientRect();
            startX = e.clientX - rect.left;
            startY = e.clientY - rect.top;
            dragging = true;
            this._crop = null;
        };

        canvas.onmousemove = (e) => {
            if (!dragging) return;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const sx = Math.min(startX, x), sy = Math.min(startY, y);
            const ex = Math.max(startX, x), ey = Math.max(startY, y);
            if (ex - sx < 5 || ey - sy < 5) return;
            this._crop = { x: sx, y: sy, w: ex - sx, h: ey - sy };
            this._redraw();
            this._updateCropInfo();
        };

        canvas.onmouseup = () => {
            dragging = false;
            if (this._crop) {
                document.getElementById('itCropDownload').style.display = '';
            }
        };
    },

    _redraw() {
        const canvas = this._canvas;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        ctx.save();
        ctx.translate(canvas.width / 2, canvas.height / 2);
        const rad = (this._rotation % 360) * Math.PI / 180;
        if (rad) ctx.rotate(rad);
        if (this._flipH) ctx.scale(-1, 1);
        if (this._flipV) ctx.scale(1, -1);
        ctx.drawImage(this._sourceImg, -canvas.width / 2, -canvas.height / 2, canvas.width, canvas.height);
        ctx.restore();

        // Draw crop rect
        if (this._crop) {
            ctx.strokeStyle = '#00d4ff';
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 3]);
            ctx.strokeRect(this._crop.x, this._crop.y, this._crop.w, this._crop.h);
            ctx.setLineDash([]);
            // Dim outside
            ctx.fillStyle = 'rgba(0,0,0,0.35)';
            ctx.fillRect(0, 0, canvas.width, this._crop.y);
            ctx.fillRect(0, this._crop.y, this._crop.x, this._crop.h);
            ctx.fillRect(this._crop.x + this._crop.w, this._crop.y, canvas.width - this._crop.x - this._crop.w, this._crop.h);
            ctx.fillRect(0, this._crop.y + this._crop.h, canvas.width, canvas.height - this._crop.y - this._crop.h);
        }
    },

    _updateCropInfo() {
        const info = document.getElementById('itCropInfo');
        if (info && this._crop) {
            info.textContent = I18n.t('imageTools.cropArea') + ': ' +
                Math.round(this._crop.w) + ' × ' + Math.round(this._crop.h) + ' px';
        }
    },

    _download() {
        const canvas = this._canvas;
        if (!canvas) return;
        const link = document.createElement('a');
        link.download = 'preprocessed_image.png';
        link.href = canvas.toDataURL('image/png');
        link.click();
        Utils.showToast(I18n.t('imageTools.downloaded'), 'success');
    },

    _downloadCropped() {
        if (!this._crop) return;
        const canvas = this._canvas;
        if (!canvas) return;
        const cropCanvas = document.createElement('canvas');
        cropCanvas.width = Math.round(this._crop.w);
        cropCanvas.height = Math.round(this._crop.h);
        const ctx = cropCanvas.getContext('2d');
        ctx.drawImage(canvas, this._crop.x, this._crop.y, this._crop.w, this._crop.h, 0, 0, cropCanvas.width, cropCanvas.height);
        const link = document.createElement('a');
        link.download = 'cropped_image.png';
        link.href = cropCanvas.toDataURL('image/png');
        link.click();
        Utils.showToast(I18n.t('imageTools.cropped'), 'success');
    }
};
