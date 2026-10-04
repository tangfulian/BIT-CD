/**
 * 统一 API 层，所有后端接口调用集中于此。
 * @module api
 */
import { CONFIG } from './config.js';
import { Utils } from './utils.js';
import { I18n } from './i18n.js';
import { Auth } from './auth.js';

/**
 * 处理 401 未授权：清除 token 和登录状态，跳转登录页。
 * @param {Response} res - fetch 返回的 Response 对象
 * @returns {boolean} 是否触发了 401 处理
 */
function _handleAuthError(res) {
    if (res.status === 401) {
        Utils.safeLocalStorage.removeItem(CONFIG.TOKEN_KEY);
        Utils.safeLocalStorage.removeItem(CONFIG.LOGIN_KEY);
        // 清除过期 token，统一回到游客模式，不刷新页面
        Auth.enterGuestMode();
        return true;
    }
    if (res.status === 403) {
        Utils.showToast(I18n.t('auth.insufficientPermission', '权限不足，请联系管理员'), 'error');
        return true;
    }
    if (res.status >= 500) {
        Utils.showToast(I18n.t('auth.serverError', '服务器异常，请稍后重试'), 'error');
        return true;
    }
    return false;
}

/** @namespace API */
export const API = {
    /**
     * 获取当前用户的检测历史记录。
     * @returns {Promise<Array>} 检测记录数组
     */
    async fetchHistory() {
        // 失败返回 null，空数据返回 []，两者必须可区分。
        // 此前一律 return []，于是限流 429 / 500 / 断网在消费方眼里和
        // 「系统里本来就没有记录」长得一模一样：对比页渲染成 0 条 0%、
        // 看板渲染成全 0 空环图、地图页谎报「暂无带坐标记录」，
        // 而大屏的 _showError 兜底因为这里从不抛错而永远不触发。
        const token = Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY);
        if (!token) return [];
        try {
            const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/history?limit=500`);
            if (_handleAuthError(res)) return null;
            if (!res.ok) {
                console.warn('[api] /history 返回', res.status);
                return null;
            }
            const data = await res.json();
            return data.code === 200 ? (data.data || []) : null;
        } catch (e) {
            console.warn('[api] /history 请求失败', e);
            return null;
        }
    },

    /**
     * 提交单张变化检测请求。
     * @param {FormData} formData - 包含 img1, img2 及 model/threshold 等参数
     * @returns {Promise<Object>} 检测结果 JSON { code, mask, heat, fusion, stats, ... }
     */
    async postDetect(formData) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect`, { method: 'POST', body: formData });
        if (_handleAuthError(res)) throw new Error(I18n.t('auth.sessionExpired', '认证失败，请重新登录'));
        try { return await res.json(); } catch { throw new Error(I18n.t('detect.detectFailed')); }
    },

    /**
     * 获取推荐的变化检测阈值。
     * @param {File} file1 - T1 时相影像文件
     * @param {File} file2 - T2 时相影像文件
     * @returns {Promise<number>} 推荐阈值 (0.1-0.9)
     */
    async recommendThreshold(file1, file2) {
        const fd = new FormData();
        fd.append("img1", file1);
        fd.append("img2", file2);
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/recommend-threshold`, {
            method: 'POST',
            body: fd
        });
        let data;
        try { data = await res.json(); } catch { throw new Error(I18n.t('detect.thresholdFailed', '阈值推荐失败')); }
        if (data.code !== 200) throw new Error(I18n.t('detect.thresholdFailed', '阈值推荐失败'));
        return data.threshold;
    },

    /**
     * 调用 AI 对检测结果进行分类。
     * @param {Object} classifyData - 检测数据 { change_ratio, change_pixel, total_pixel, threshold, location, ... }
     * @returns {Promise<Object>} { code, change_type, confidence, reasoning }
     */
    async classifyChange(classifyData) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/ai/classify-change`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(classifyData),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /**
     * 更新检测记录的变化类型（采纳 AI 建议时使用）。
     * @param {number} detectionId - 检测记录 ID
     * @param {string} changeType - 新的变化类型
     * @returns {Promise<Object>} { code, msg }
     */
    async updateChangeType(detectionId, changeType) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/ai/update-change-type`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ detection_id: detectionId, change_type: changeType }),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    // ---- 地块管理 ----

    /** 获取当前用户的所有地块 */
    async fetchPlots() {
        const token = Utils.safeLocalStorage.getItem(CONFIG.TOKEN_KEY);
        if (!token) return [];
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/plots`);
        if (_handleAuthError(res)) return [];
        if (!res.ok) return [];
        const data = await res.json();
        return Array.isArray(data) ? data : [];
    },

    /** 创建新地块 */
    async createPlot(plotData) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/plots`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(plotData),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /** 更新地块 */
    async updatePlot(id, plotData) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/plots/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(plotData),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /** 删除地块 */
    async deletePlot(id) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/plots/${id}`, {
            method: 'DELETE',
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /** 多模型对比检测 */
    async compareModels(formData) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect/compare`, {
            method: 'POST',
            body: formData,
        });
        if (_handleAuthError(res)) throw new Error(I18n.t('auth.sessionExpired', '认证失败，请重新登录'));
        try { return await res.json(); } catch { throw new Error(I18n.t('detect.detectFailed')); }
    },

    /** 基于已有检测结果的 score_map 重新调阈值 */
    async rethreshold(detectionId, threshold) {
        const fd = new FormData();
        fd.append('detection_id', detectionId);
        fd.append('threshold', threshold);
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect/rethreshold`, {
            method: 'POST',
            body: fd,
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /** 获取已有检测结果的 Otsu 最优阈值 */
    async fetchOtsuThreshold(detectionId) {
        const fd = new FormData();
        fd.append('detection_id', detectionId);
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect/otsu`, {
            method: 'POST',
            body: fd,
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /** 导出检测掩膜为 GeoJSON */
    async exportGeoJSON(detectionId, simplify = true) {
        const fd = new FormData();
        fd.append('detection_id', detectionId);
        fd.append('simplify', simplify ? 'true' : 'false');
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect/export-geojson`, {
            method: 'POST',
            body: fd,
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /** 计算影像 NDVI */
    async computeNDVI(file) {
        const fd = new FormData();
        fd.append('img', file);
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect/ndvi`, {
            method: 'POST',
            body: fd,
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        try { return await res.json(); } catch { throw new Error('NDVI calculation failed'); }
    },

    /** 检查双时相影像配准状态 */
    async checkRegistration(file1, file2) {
        const fd = new FormData();
        fd.append('img1', file1);
        fd.append('img2', file2);
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect/check-registration`, {
            method: 'POST',
            body: fd,
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        try { return await res.json(); } catch { throw new Error('Registration check failed'); }
    },

    /** 计算变化区域面积统计 */
    async computeAreaStats(detectionId, resolution = 0) {
        const fd = new FormData();
        fd.append('detection_id', detectionId);
        fd.append('resolution', resolution);
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/detect/area-stats`, {
            method: 'POST',
            body: fd,
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    // ---- 灾害定损 ----

    /** 获取定损默认参数（含来源说明） */
    async fetchDisasterParams() {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/disaster/params`);
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    /**
     * 定损测算。纯算术，不调用大模型。
     * @param {Object} payload - { detection_id, area_mu, crop_type, yield_per_mu, ... }
     */
    async assessDisaster(payload) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/disaster/assess`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || I18n.t('disaster.assessFailed', '定损测算失败'));
        }
        return await res.json();
    },

    /** 生成定损说明草稿（AI，需人工复核） */
    async generateDisasterNarrative(payload) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/disaster/narrative`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    // ---- 多时相序列 ----

    async fetchSeriesList() {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/series`);
        if (_handleAuthError(res)) return [];
        if (!res.ok) return [];
        const data = await res.json();
        return data.code === 200 ? data.data : [];
    },

    async createSeries(payload) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/series`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || I18n.t('series.createFailed', '创建序列失败'));
        }
        return await res.json();
    },

    async fetchSeriesDetail(id) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/series/${id}`);
        if (_handleAuthError(res)) throw new Error('Auth error');
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || I18n.t('series.loadFailed', '序列加载失败'));
        }
        return await res.json();
    },

    async attachSeriesRecords(id, records) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/series/${id}/records`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ records }),
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || I18n.t('series.attachFailed', '挂载记录失败'));
        }
        return await res.json();
    },

    async deleteSeries(id) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/series/${id}`, {
            method: 'DELETE',
        });
        if (_handleAuthError(res)) throw new Error('Auth error');
        return await res.json();
    },

    async fetchSeriesTrend(id) {
        const res = await Utils.authFetch(`${CONFIG.API_BASE_URL}/series/${id}/trend`);
        if (_handleAuthError(res)) throw new Error('Auth error');
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || I18n.t('series.trendFailed', '趋势分析失败'));
        }
        return await res.json();
    }
};