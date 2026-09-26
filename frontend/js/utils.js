/**
 * 通用工具函数集合。
 * @module utils
 */
import { CONFIG } from './config.js';
import { Toast } from './toast.js';

/** @namespace Utils */
export const Utils = {
    /**
     * 简单 Markdown 转 HTML（仅支持 **加粗** 和换行）。
     * @param {string} text - Markdown 文本
     * @returns {string} HTML 字符串
     */
    parseMarkdown(text) {
        if (!text) return "";
        return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    },

    /** localStorage 安全包装（处理隐私模式/无痕浏览下的访问异常）。 */
    safeLocalStorage: {
        /** @param {string} key @param {string} value @returns {boolean} */
        setItem(key, value) { try { localStorage.setItem(key, value); return true; } catch (e) { return false; } },
        /** @param {string} key @returns {string|null} */
        getItem(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
        /** @param {string} key @returns {boolean} */
        removeItem(key) { try { localStorage.removeItem(key); return true; } catch (e) { return false; } }
    },

    /** 释放 Blob URL 避免内存泄漏。 */
    releaseObjectURL(url) { if (url && url.startsWith('blob:')) URL.revokeObjectURL(url); },

    /**
     * 带超时的 fetch 封装。
     * @param {string} url
     * @param {RequestInit} [options={}]
     * @returns {Promise<Response>}
     */
    fetchWithTimeout(url, options = {}) {
        // 如果调用方已传入 signal（如 taskQueue 的 AbortController），则合并信号
        var existingSignal = options.signal;
        var timeoutCtrl = new AbortController();
        var timeoutId = setTimeout(function () {
            var err = new Error('Request timeout after ' + (CONFIG.REQUEST_TIMEOUT / 1000) + 's');
            err.name = 'TimeoutError';
            timeoutCtrl.abort(err);
        }, CONFIG.REQUEST_TIMEOUT);

        var mergedSignal = timeoutCtrl.signal;
        if (existingSignal) {
            if (existingSignal.aborted) {
                timeoutCtrl.abort(existingSignal.reason);
            } else {
                existingSignal.addEventListener('abort', function () {
                    timeoutCtrl.abort(existingSignal.reason);
                });
            }
        }

        return fetch(url, { ...options, signal: mergedSignal })
            .then(function (res) { clearTimeout(timeoutId); return res; })
            .catch(function (err) { clearTimeout(timeoutId); throw err; });
    },

    /**
     * 带 JWT 认证头的 fetch。
     * @param {string} url
     * @param {RequestInit} [options={}]
     * @returns {Promise<Response>}
     */
    authFetch(url, options = {}) {
        const token = Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY);
        const headers = options.headers || {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return this.fetchWithTimeout(url, { ...options, headers });
    },

    /**
     * 校验上传文件是否合法。
     * @param {File} file
     * @returns {{valid: boolean, msg?: string}}
     */
    validateFile(file) {
        if (!file) return { valid: false, msg: '请选择文件' };
        const typeOk = CONFIG.ACCEPTED_IMAGE_TYPES.includes(file.type)
            || /\.(png|jpg|jpeg|tif|tiff|bmp)$/i.test(file.name);
        if (!typeOk) return { valid: false, msg: '不支持的文件类型' };
        if (file.size > CONFIG.MAX_FILE_SIZE) return { valid: false, msg: '文件过大' };
        return { valid: true };
    },

    /**
     * 创建图片预览URL（自动处理TIFF解码）
     * @param {File} file
     * @returns {Promise<string>} blob URL 或 data URL
     */
    async createImagePreview(file) {
        const isTiff = /\.(tif|tiff)$/i.test(file.name)
            || file.type === 'image/tiff' || file.type === 'image/tif';
        if (!isTiff) return URL.createObjectURL(file);

        try {
            const arrayBuffer = await file.arrayBuffer();
            const tiff = await GeoTIFF.fromArrayBuffer(arrayBuffer);
            const image = await tiff.getImage();
            const raster = await image.readRasters({ window: [0, 0, image.getWidth(), image.getHeight()] });
            const width = image.getWidth();
            const height = image.getHeight();

            const canvas = document.createElement('canvas');
            const maxDim = 512;
            const scale = Math.min(maxDim / width, maxDim / height, 1);
            canvas.width = Math.round(width * scale);
            canvas.height = Math.round(height * scale);
            const ctx = canvas.getContext('2d');

            const imageData = ctx.createImageData(canvas.width, canvas.height);
            const bands = raster.length;

            for (let dy = 0; dy < canvas.height; dy++) {
                for (let dx = 0; dx < canvas.width; dx++) {
                    const sx = Math.floor(dx / scale);
                    const sy = Math.floor(dy / scale);
                    const srcIdx = sy * width + sx;
                    const dstIdx = (dy * canvas.width + dx) * 4;

                    if (bands >= 3) {
                        imageData.data[dstIdx] = raster[0][srcIdx];
                        imageData.data[dstIdx + 1] = raster[1][srcIdx];
                        imageData.data[dstIdx + 2] = raster[2][srcIdx];
                    } else {
                        const v = raster[0][srcIdx];
                        imageData.data[dstIdx] = v;
                        imageData.data[dstIdx + 1] = v;
                        imageData.data[dstIdx + 2] = v;
                    }
                    imageData.data[dstIdx + 3] = 255;
                }
            }
            ctx.putImageData(imageData, 0, 0);
            return canvas.toDataURL('image/png');
        } catch (e) {
            console.error('TIFF预览失败:', e);
            return URL.createObjectURL(file);
        }
    },

    base64Encode(str) { return btoa(str); },
    base64Decode(str) { return atob(str); },

    setupGlobalErrorHandler() {
        window.addEventListener('error', e => {
            console.error('全局错误:', e.message, e.filename, e.lineno);
        });
        window.addEventListener('unhandledrejection', e => {
            console.error('未处理的异步错误:', e.reason);
            if (e.reason && (e.reason.name === 'TypeError' || e.reason.message?.includes('fetch'))) {
                if (e.reason.name === 'AbortError') return;
            }
        });
    },

    /**
     * 在页面右下角显示 Toast 提示。
     * @param {string} message - 提示文本
     * @param {'info'|'success'|'error'} [type='info'] - 提示类型
     */
    /**
     * 导出 CSV 文件并触发下载。
     * @param {string[][]} rows - 二维数组，第一行为表头
     * @param {string} filename - 下载文件名（不含 .csv 后缀）
     */
    exportCSV(rows, filename) {
        const csv = '﻿' + rows.map(row =>
            row.map(cell => {
                if (cell == null) return '';
                const s = String(cell);
                return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
            }).join(',')
        ).join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${filename}_${Date.now()}.csv`;
        a.click();
        this.releaseObjectURL(url);
    },

    /**
     * 将图片 URL 转换为 base64 data URL。
     * @param {string} url - 图片 URL
     * @returns {Promise<string>} base64 data URL
     */
    async imageUrlToBase64(url) {
        const res = await fetch(url);
        const blob = await res.blob();
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    },

    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    showToast(message, type) {
        type = type || 'info';
        Toast[type] ? Toast[type](message) : Toast.info(message);
    }
};