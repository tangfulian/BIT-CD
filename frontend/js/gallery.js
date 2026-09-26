/**
 * 结果图库 - 画廊模式浏览检测结果图片
 * @module gallery
 */
import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { I18n } from './i18n.js';
import { Auth } from './auth.js';

export const Gallery = {
    _images: [],
    _currentIdx: 0,

    init() {
        document.addEventListener('keydown', (e) => {
            if (!document.getElementById('galleryOverlay')?.classList.contains('show')) return;
            if (e.key === 'Escape') this.close();
            if (e.key === 'ArrowLeft') this._nav(-1);
            if (e.key === 'ArrowRight') this._nav(1);
        });
    },

    open(images, startIdx = 0) {
        if (!images || images.length === 0) return;
        this._images = images;
        this._currentIdx = Math.max(0, Math.min(startIdx, images.length - 1));
        this._render();
    },

    _render() {
        this._remove();
        const overlay = document.createElement('div');
        overlay.id = 'galleryOverlay';
        overlay.className = 'gallery-overlay';
        overlay.innerHTML = [
            '<div class="gallery-backdrop"></div>',
            '<button class="gallery-close" title="' + I18n.t('common.close') + '">&times;</button>',
            '<button class="gallery-nav gallery-prev" title="' + I18n.t('gallery.prev') + '"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg></button>',
            '<button class="gallery-nav gallery-next" title="' + I18n.t('gallery.next') + '"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg></button>',
            '<div class="gallery-main">',
                '<div class="gallery-counter" id="galleryCounter"></div>',
                '<img id="galleryMainImg" src="" alt="">',
                '<div class="gallery-caption" id="galleryCaption"></div>',
            '</div>',
            '<div class="gallery-strip" id="galleryStrip"></div>',
        ].join('');
        document.body.appendChild(overlay);

        overlay.querySelector('.gallery-backdrop').onclick = () => this.close();
        overlay.querySelector('.gallery-close').onclick = () => this.close();
        overlay.querySelector('.gallery-prev').onclick = () => this._nav(-1);
        overlay.querySelector('.gallery-next').onclick = () => this._nav(1);

        // Swipe support
        let touchStartX = 0;
        overlay.addEventListener('touchstart', (e) => { touchStartX = e.touches[0].clientX; });
        overlay.addEventListener('touchend', (e) => {
            const diff = touchStartX - e.changedTouches[0].clientX;
            if (Math.abs(diff) > 50) this._nav(diff > 0 ? 1 : -1);
        });

        this._updateMain();
        this._renderStrip();
        requestAnimationFrame(() => overlay.classList.add('show'));
    },

    _updateMain() {
        const img = this._images[this._currentIdx];
        if (!img) return;
        const mainImg = document.getElementById('galleryMainImg');
        const counter = document.getElementById('galleryCounter');
        const caption = document.getElementById('galleryCaption');
        if (mainImg) {
            mainImg.style.opacity = '0';
            setTimeout(() => {
                mainImg.src = img.url || img;
                mainImg.alt = img.label || '';
                mainImg.style.opacity = '1';
            }, 150);
        }
        if (counter) counter.textContent = (this._currentIdx + 1) + ' / ' + this._images.length;
        if (caption && img.label) caption.textContent = img.label;
    },

    _renderStrip() {
        const strip = document.getElementById('galleryStrip');
        if (!strip || this._images.length < 2) return;
        strip.innerHTML = this._images.map((img, i) => {
            const src = img.thumb || img.url || img;
            const active = i === this._currentIdx ? ' active' : '';
            return '<div class="gallery-thumb' + active + '" data-idx="' + i + '">' +
                '<img src="' + src + '" alt="" loading="lazy">' +
                '</div>';
        }).join('');
        strip.querySelectorAll('.gallery-thumb').forEach(el => {
            el.onclick = () => {
                this._currentIdx = parseInt(el.dataset.idx);
                this._updateMain();
                this._renderStrip();
            };
        });
    },

    _nav(dir) {
        const len = this._images.length;
        if (len === 0) return;
        this._currentIdx = (this._currentIdx + dir + len) % len;
        this._updateMain();
        this._renderStrip();
    },

    close() {
        const overlay = document.getElementById('galleryOverlay');
        if (overlay) {
            overlay.classList.remove('show');
            setTimeout(() => this._remove(), 300);
        }
    },

    _remove() {
        const el = document.getElementById('galleryOverlay');
        if (el) el.remove();
    }
};
